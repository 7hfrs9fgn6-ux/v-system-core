# 推送通知器（PushPlus 微信推送）
# 对应 03-full-closure.yml

import os
import requests
import json
from output_layer.signal_result import SignalResult

class PushNotifier:
    def __init__(self):
        self.token = os.environ.get("PUSHPLUS_TOKEN")
        if not self.token:
            print("⚠️ 未设置 PUSHPLUS_TOKEN，将只打印不推送")
    
    def send(self, result: SignalResult, phase: str = "pre") -> bool:
        """发送推送，返回是否成功"""
        if not self.token:
            print("📢 [模拟推送] 无Token，仅打印内容：")
            print(self._format_message(result, phase))
            return False
        
        # 构造推送消息
        title = f"📊 V系统{phase}分析简报"
        content = self._format_message(result, phase)
        
        # 调用PushPlus API
        url = "http://www.pushplus.plus/send"
        payload = {
            "token": self.token,
            "title": title,
            "content": content,
            "template": "txt"
        }
        
        try:
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()
            if data.get("code") == 200:
                print("✅ 微信推送成功！")
                return True
            else:
                print(f"❌ 推送失败: {data.get('msg')}")
                return False
        except Exception as e:
            print(f"❌ 推送异常: {e}")
            return False
    
    def _format_message(self, result: SignalResult, phase: str) -> str:
        """格式化推送文本（简阶段L1风格）"""
        # 根据阶段调整标题
        phase_map = {"pre": "盘前预判", "intraday": "盘中提醒", "post": "盘后复盘"}
        phase_text = phase_map.get(phase, "分析")
        
        # 构建板块预览（只显示前3个，避免微信字数超限）
        top_signals = result.signals[:5]
        signal_lines = []
        for s in top_signals:
            emoji = "🟢" if s.signal_level >= 3 else "🟡" if s.signal_level >= 1 else "🟠" if s.signal_level >= -1 else "🔴"
            signal_lines.append(f"{emoji} {s.name}: 回撤{s.drawdown}% (阈值{s.threshold}%)")
        
        if len(result.signals) > 5:
            signal_lines.append(f"... 共{len(result.signals)}个板块，完整数据请查看L3附录")
        
        msg = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 V系统 {phase_text} [{result.analysis_time}]
━━━━━━━━━━━━━━━━━━━━━━━━━━
【综合建议】{result.overall_suggestion}
【判断状态】{result.judge_status}
【运行模式】{result.agent_mode}
【健康度】{result.health_score}/100

【板块速览】
{chr(10).join(signal_lines)}

⚠️ 告警: {', '.join(result.warnings) if result.warnings else '无'}
━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 操作指引：判断{result.judge_status}，建议{"正常参考" if result.judge_status == "正常" else "结合其他信息确认" if result.judge_status == "偏低" else "暂缓操作"}
        """
        return msg.strip()
