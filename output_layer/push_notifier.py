import os
import yaml
import requests
import time
from datetime import datetime  # ✅ 修复：导入 datetime
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
        self._alert_cache = {}
        self._last_push_time = 0
        self._push_interval = 2

    def _load_config(self, path):
        if os.path.exists(path):
            with open(path, 'r') as f:
                return yaml.safe_load(f)
        return {}

    def _send_with_rate_limit(self, title, content):
        now = time.time()
        wait_time = self._push_interval - (now - self._last_push_time)
        if wait_time > 0:
            time.sleep(wait_time)
        self._last_push_time = time.time()
        return self._send_push(title, content)

    def _send_push(self, title, content):
        if not self.token:
            return False
        try:
            resp = requests.post("http://www.pushplus.plus/send", json={
                "token": self.token,
                "title": title,
                "content": content,
                "template": "txt"
            }, timeout=10)
            return resp.json().get("code") == 200
        except:
            return False

    def send(self, result: SignalResult, phase: str = "pre") -> bool:
        if not self.token:
            print("📢 [模拟] 无Token")
            self._store_to_notion(result, phase)
            return False

        phase_info = self.phase_config.get(phase, {"name": phase, "emoji": "📊"})
        title = f"📊 V系统 {phase_info.get('emoji', '')} {phase_info.get('name', phase)}"
        content = self._format_message(result, phase)

        success = self._send_with_rate_limit(title, content)
        print("✅ 主推送成功" if success else "❌ 主推送失败")

        # 黄金坑预警（仅 post 阶段）
        if self.alert_enabled and phase == "post":
            self._check_alerts_batch(result)

        self._store_to_notion(result, phase)
        return success

    def _check_alerts_batch(self, result: SignalResult):
        now = datetime.now()  # ✅ 现在 datetime 已导入
        triggered = []
        for s in result.signals:
            if s.drawdown >= s.threshold:
                key = s.name
                last = self._alert_cache.get(key)
                if last and (now - last).total_seconds() < self.alert_cooldown * 3600:
                    continue
                triggered.append(s)
                self._alert_cache[key] = now

        if not triggered:
            return

        lines = ["━━━━━━━━━━━━━━━━━━━━━━━━━━"]
        lines.append("🔔 黄金坑触发预警（批量）")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"触发数量：{len(triggered)} 个板块")
        lines.append("")
        lines.append("【触发板块列表】")
        for s in triggered:
            excess = s.drawdown - s.threshold
            emoji = "🟢" if s.signal_level >= 3 else "🟡" if s.signal_level >= 1 else "🟠"
            lines.append(f"  {emoji} {s.name}：回撤{s.drawdown}% / 阈值{s.threshold}% (超出{excess:.1f}%)")
        lines.append("")
        lines.append("📌 建议：关注以上板块，可考虑分批建仓")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")

        self._send_with_rate_limit("🔔 黄金坑触发预警", "\n".join(lines))
        print(f"🔔 黄金坑预警已发送（{len(triggered)}个板块）")

    def _store_to_notion(self, result: SignalResult, phase: str):
        try:
            from output_layer.notion_storage import NotionStorage
            storage = NotionStorage(self.config)
            storage.store(result, phase)
        except Exception as e:
            print(f"❌ Notion 存储失败: {e}")

    def _format_message(self, result: SignalResult, phase: str) -> str:
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
                emoji_s, status = "🟢", "机会信号"
            elif best_level >= 1:
                emoji_s, status = "🟡", "观察中"
            elif best_level >= -1:
                emoji_s, status = "🟠", "风险提示"
            else:
                emoji_s, status = "🔴", "风险信号"
            driver = f"（{best_sec}驱动）" if len(sector_signals) > 1 else ""
            holding_lines.append(
                f"  {emoji_s} {status} {fund_name}{driver} 回撤{best_dd}% / 阈值{best_th}%"
            )

        # 最强/最弱（非持仓）
        non_holding = [s for s in result.signals if s.name not in self.holding_sectors]
        strongest = max(non_holding, key=lambda x: x.signal_level) if non_holding else None
        weakest = min(non_holding, key=lambda x: x.signal_level) if non_holding else None

        def fmt(s):
            em = "🟢" if s.signal_level >= 3 else "🟡" if s.signal_level >= 1 else "🟠" if s.signal_level >= -1 else "🔴"
            return f"{em} {s.name} (回撤{s.drawdown}% / 阈值{s.threshold}%)"

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
            lines.append(f"  {fmt(strongest)}")
        if weakest:
            lines.append("")
            lines.append("【⚠️ 最弱信号（非持仓）】")
            lines.append(f"  {fmt(weakest)}")
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
