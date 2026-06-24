import os
import yaml
import requests
import json
from datetime import datetime, timedelta
from output_layer.signal_result import SignalResult
from output_layer.ai_commentator import AICommentator

class PushNotifier:
    def __init__(self, config_path="config.yaml"):
        self.token = os.environ.get("PUSHPLUS_TOKEN")
        self.commentator = AICommentator()
        self.config = self._load_config(config_path)
        self.holding_map = self.config.get("holdings", {})
        self.holding_sectors = []
        for fund in self.holding_map.values():
            self.holding_sectors.extend(fund.get("sectors", []))
        self.holding_sectors = list(set(self.holding_sectors))
        self.phase_config = self.config.get("phases", {})
        self.alert_config = self.config.get("alert", {})
        self.alert_enabled = self.alert_config.get("enabled", False)
        self.alert_cooldown = self.alert_config.get("cooldown_hours", 24)
        # 简单内存缓存，实际生产可改用 Redis
        self._alert_cache = {}

    def _load_config(self, path):
        if os.path.exists(path):
            with open(path, 'r') as f:
                return yaml.safe_load(f)
        return {}

    def send(self, result: SignalResult, phase: str = "pre") -> bool:
        if not self.token:
            print("📢 [模拟] 无Token，仅打印")
            print(self._format_message(result, phase))
            # 仍然尝试存储到 Notion
            self._store_to_notion(result, phase)
            return False

        # 1. 发送主推送
        phase_info = self.phase_config.get(phase, {"name": phase, "emoji": "📊"})
        title = f"📊 V系统 {phase_info.get('emoji', '')} {phase_info.get('name', phase)}"
        content = self._format_message(result, phase)
        url = "http://www.pushplus.plus/send"

        try:
            resp = requests.post(url, json={
                "token": self.token,
                "title": title,
                "content": content,
                "template": "txt"
            }, timeout=10)
            if resp.json().get("code") == 200:
                print("✅ 主推送成功")
            else:
                print(f"❌ 主推送失败: {resp.json()}")
        except Exception as e:
            print(f"❌ 推送异常: {e}")

        # 2. 黄金坑预警（仅在 post 阶段检查，避免重复）
        if self.alert_enabled and phase == "post":
            self._check_alerts(result)

        # 3. 存储 L3 到 Notion
        self._store_to_notion(result, phase)

        return True

    def _check_alerts(self, result: SignalResult):
        """检查是否有板块触发黄金坑预警"""
        now = datetime.now()
        for s in result.signals:
            if s.drawdown >= s.threshold:
                key = s.name
                last_alert = self._alert_cache.get(key)
                if last_alert and (now - last_alert).total_seconds() < self.alert_cooldown * 3600:
                    continue  # 冷却中
                # 发送独立预警推送
                alert_title = self.alert_config.get("push_title", "🔔 黄金坑触发预警")
                alert_content = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━
🔔 黄金坑触发预警
━━━━━━━━━━━━━━━━━━━━━━━━━━
板块：{s.name}
当前回撤：{s.drawdown}%
触发阈值：{s.threshold}%
超出幅度：{s.drawdown - s.threshold:.1f}%
信号等级：{s.signal_level}
时间：{result.analysis_time}
━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 建议：关注该板块，可考虑分批建仓
                """
                self._send_alert(alert_title, alert_content.strip())
                self._alert_cache[key] = now
                print(f"🔔 黄金坑预警已发送: {s.name}")

    def _send_alert(self, title, content):
        if not self.token:
            return
        try:
            resp = requests.post("http://www.pushplus.plus/send", json={
                "token": self.token,
                "title": title,
                "content": content,
                "template": "txt"
            }, timeout=10)
            if resp.json().get("code") == 200:
                print("✅ 预警推送成功")
            else:
                print(f"❌ 预警推送失败: {resp.json()}")
        except Exception as e:
            print(f"❌ 预警推送异常: {e}")

    def _store_to_notion(self, result: SignalResult, phase: str):
        """调用 Notion 存储"""
        try:
            from output_layer.notion_storage import NotionStorage
            storage = NotionStorage(self.config)
            storage.store(result, phase)
        except ImportError:
            print("ℹ️  NotionStorage 未找到，跳过存储")
        except Exception as e:
            print(f"❌ Notion 存储失败: {e}")

    def _format_message(self, result: SignalResult, phase: str) -> str:
        # 与之前相同，略作精简，但保持完整
        phase_info = self.phase_config.get(phase, {"name": phase, "emoji": "📊"})
        phase_text = phase_info.get("name", phase)
        emoji = phase_info.get("emoji", "📊")

        signal_dict = {s.name: s for s in result.signals}

        # 持仓信号
        holding_lines = []
        for fund_code, fund_info in self.holding_map.items():
            fund_name = fund_info["name"]
            sectors = fund_info["sectors"]
            sector_signals = []
            for sec in sectors:
                if sec in signal_dict:
                    s = signal_dict[sec]
                    sector_signals.append((sec, s.signal_level, s.drawdown, s.threshold))
            if not sector_signals:
                holding_lines.append(f"  ⚪ {fund_name}：无数据")
                continue
            best = max(sector_signals, key=lambda x: x[1])
            best_sec, best_level, best_dd, best_th = best
            if best_level >= 3:
                emoji_signal, status = "🟢", "机会信号"
            elif best_level >= 1:
                emoji_signal, status = "🟡", "观察中"
            elif best_level >= -1:
                emoji_signal, status = "🟠", "风险提示"
            else:
                emoji_signal, status = "🔴", "风险信号"
            driver = f"（{best_sec}驱动）" if len(sector_signals) > 1 else ""
            holding_lines.append(
                f"  {emoji_signal} {status} {fund_name}{driver} 回撤{best_dd}% / 阈值{best_th}%"
            )

        # 最强/最弱
        non_holding = [s for s in result.signals if s.name not in self.holding_sectors]
        strongest = max(non_holding, key=lambda x: x.signal_level) if non_holding else None
        weakest = min(non_holding, key=lambda x: x.signal_level) if non_holding else None

        def format_signal(s, prefix=""):
            emoji_s = "🟢" if s.signal_level >= 3 else "🟡" if s.signal_level >= 1 else "🟠" if s.signal_level >= -1 else "🔴"
            return f"{prefix}{emoji_s} {s.name} (回撤{s.drawdown}% / 阈值{s.threshold}%)"

        ai_comment = self.commentator.generate_comment(result, self.holding_sectors)

        lines = []
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"{emoji} V系统 {phase_text} [{result.analysis_time}]")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"【综合建议】{result.overall_suggestion}")
        lines.append(f"【判断状态】{result.judge_status}")
        lines.append(f"【运行模式】{result.agent_mode}")
        lines.append("")
        lines.append("【📌 你的持仓信号】")
        if holding_lines:
            lines.extend(holding_lines)
        else:
            lines.append("  （无持仓数据）")
        if strongest:
            lines.append("")
            lines.append("【🔥 最强信号（非持仓）】")
            lines.append(f"  {format_signal(strongest)}")
        if weakest:
            lines.append("")
            lines.append("【⚠️ 最弱信号（非持仓）】")
            lines.append(f"  {format_signal(weakest)}")
        lines.append("")
        lines.append("【🤖 AI 点评】")
        lines.append(f"  {ai_comment}")
        lines.append("")
        if result.warnings:
            lines.append(f"⚠️ 告警: {', '.join(result.warnings)}")
        else:
            lines.append("✅ 无异常告警")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        if result.judge_status == "正常":
            advice = "建议正常参考信号决策"
        elif result.judge_status == "偏低":
            advice = "建议结合其他信息确认"
        else:
            advice = "⚠️ 不建议据此操作"
        lines.append(f"📌 操作指引：{advice}")
        return "\n".join(lines)
