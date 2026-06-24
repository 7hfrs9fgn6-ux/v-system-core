import os
import requests

class AICommentator:
    def __init__(self):
        self.api_key = os.environ.get("DEEPSEEK_API_KEY")
        self.enabled = self.api_key is not None and self.api_key != ""

    def generate_comment(self, result, holdings: list) -> str:
        if not self.enabled:
            return "（AI点评未启用，请配置DEEPSEEK_API_KEY）"

        signals = result.signals
        strongest = max(signals, key=lambda x: x.signal_level)
        weakest = min(signals, key=lambda x: x.signal_level)

        prompt = f"""
你是一个专业的A股投资顾问。请根据以下V系统分析结果，生成一段**50字以内**的精炼点评：

综合建议：{result.overall_suggestion}
判断状态：{result.judge_status}
最强信号：{strongest.name}（信号等级{strongest.signal_level}，回撤{strongest.drawdown}%）
最弱信号：{weakest.name}（信号等级{weakest.signal_level}，回撤{weakest.drawdown}%）
持仓板块：{', '.join(holdings) if holdings else '无'}

要求：
1. 只说最重要的1-2个观点
2. 语气专业但不啰嗦
3. 如果判断状态为"偏低"或"需谨慎"，务必提醒风险
4. 直接输出点评内容，不要加标题或前缀
"""
        try:
            response = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 100,
                    "temperature": 0.7
                },
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()
            else:
                return f"（AI点评生成失败: {response.status_code}）"
        except Exception as e:
            return f"（AI点评生成异常: {str(e)}）"
