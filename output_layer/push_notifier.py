# 推送通知器 V2.0.2 风格（持仓优先 + 最强/最弱）
# 对应 03-full-closure.yml

import os
import requests
from output_layer.signal_result import SignalResult

# 📌 模拟用户持仓（你可以改成自己的基金映射板块）
# 真实场景下，这个列表应该从配置文件或数据库读取
MOCK_HOLDINGS = ["电子", "食品饮料", "医药生物"]  # 假设你持有这三个板块

class PushNotifier:
    def __init__(self):
        self.token = os.environ.get("PUSHPLUS_TOKEN")
    
    def send(self, result: SignalResult, phase: str = "pre") -> bool:
        if not self.token:
            print("📢 [模拟] 无Token，仅打印")
            print(self._format_message(result, phase))
            return False
        
        title = f"📊 V系统{phase}简报"
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
        
        # ---------- 1. 筛选持仓板块 ----------
        holding_signals = [s for s in result.signals if s.name in MOCK_HOLDINGS]
        
        # ---------- 2. 找出最强和最弱（排除持仓，避免重复） ----------
        non_holding = [s for s in result.signals if s.name not in MOCK_HOLDINGS]
        strongest = max(non_holding, key=lambda x: x.signal_level) if non_holding else None
        weakest = min(non_holding, key=lambda x: x.signal_level) if non_holding else None
        
        # ---------- 3. 按格式组织文本 ----------
        def format_signal(s, prefix=""):
            emoji = "🟢" if s.signal_level >= 3 else "🟡" if s.signal_level >= 1 else "🟠" if s.signal_level >= -1 else "🔴"
            return f"{prefix}{emoji} {s.name} (回撤{s.drawdown}% / 阈值{s.threshold}%)"
        
        lines = []
        lines.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"📊 V系统 {phase_text} [{result.analysis_time}]")
        lines.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"【综合建议】{result.overall_suggestion}")
        lines.append(f"【判断状态】{result.judge_status}")
        lines.append(f"【运行模式】{result.agent_mode}")
        lines.append("")
        
        # 持仓板块（优先级P0）
        lines.append("【📌 持仓板块信号】")
        if holding_signals:
            for s in holding_signals:
                lines.append(f"  {format_signal(s)}")
        else:
            lines.append("  （无持仓板块数据）")
        
        # 最强信号（优先级P1）
        if strongest:
            lines.append("")
            lines.append("【🔥 最强信号】")
            lines.append(f"  {format_signal(strongest)}")
        
        # 最弱信号（优先级P2）
        if weakest:
            lines.append("")
            lines.append("【⚠️ 最弱信号】")
            lines.append(f"  {format_signal(weakest)}")
        
        # 告警信息
        if result.warnings:
            lines.append("")
            lines.append(f"⚠️ 告警: {', '.join(result.warnings)}")
        else:
            lines.append("")
            lines.append("✅ 无异常告警")
        
        lines.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━")
        # 操作指引
        if result.judge_status == "正常":
            advice = "建议正常参考信号决策"
        elif result.judge_status == "偏低":
            advice = "建议结合其他信息确认"
        else:
            advice = "⚠️ 不建议据此操作"
        lines.append(f"📌 操作指引：{advice}")
        
        return "\n".join(lines)
