import os
import yaml
import requests
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

    def _load_config(self, path):
        if os.path.exists(path):
            with open(path, 'r') as f:
                return yaml.safe_load(f)
        return {}

    def send(self, result: SignalResult, phase: str = "pre") -> bool:
        if not self.token:
            print("📢 [模拟] 无Token，仅打印")
            print(self._format_message(result, phase))
            return False

        phase_map = {"pre": "盘前预判", "intraday": "盘中提醒", "post": "盘后复盘"}
        title = f"📊 V系统{phase_map.get(phase, '分析')}"
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
                print("✅ 微信推送成功！")
                return True
            else:
                print(f"❌ 推送失败: {resp.json()}")
                return False
        except Exception as e:
            print(f"❌ 推送异常: {e}")
            return False

    def _format_message(self, result: SignalResult, phase: str) -> str:
        phase_map = {"pre": "盘前预判", "intraday": "盘中提醒", "post": "盘后复盘"}
        phase_text = phase_map.get(phase, "分析")

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
                emoji, status = "🟢", "机会信号"
            elif best_level >= 1:
                emoji, status = "🟡", "观察中"
            elif best_level >= -1:
                emoji, status = "🟠", "风险提示"
            else:
                emoji, status = "🔴", "风险信号"
            driver = f"（{best_sec}驱动）" if len(sector_signals) > 1 else ""
            holding_lines.append(
                f"  {emoji} {status} {fund_name}{driver} 回撤{best_dd}% / 阈值{best_th}%"
            )

        # 最强/最弱
        non_holding = [s for s in result.signals if s.name not in self.holding_sectors]
        strongest = max(non_holding, key=lambda x: x.signal_level) if non_holding else None
        weakest = min(non_holding, key=lambda x: x.signal_level) if non_holding else None

        def format_signal(s, prefix=""):
            emoji = "🟢" if s.signal_level >= 3 else "🟡" if s.signal_level >= 1 else "🟠" if s.signal_level >= -1 else "🔴"
            return f"{prefix}{emoji} {s.name} (回撤{s.drawdown}% / 阈值{s.threshold}%)"

        ai_comment = self.commentator.generate_comment(result, self.holding_sectors)

        lines = []
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"📊 V系统 {phase_text} [{result.analysis_time}]")
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
