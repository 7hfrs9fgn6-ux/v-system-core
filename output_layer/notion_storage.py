import os
import requests
import json
from output_layer.signal_result import SignalResult

class NotionStorage:
    def __init__(self, config: dict):
        self.enabled = config.get("notion", {}).get("enabled", False)
        self.token = config.get("notion", {}).get("token") or os.environ.get("NOTION_TOKEN")
        self.database_id = config.get("notion", {}).get("database_id") or os.environ.get("NOTION_DATABASE_ID")
        if self.token:
            self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

    def store(self, result: SignalResult, phase: str) -> bool:
        if not self.enabled or not self.token or not self.database_id:
            print("ℹ️  Notion 存储未启用")
            return False

        signals_json = json.dumps([s.dict() for s in result.signals], ensure_ascii=False)
        if len(signals_json) > 2000:
            signals_json = signals_json[:2000] + "..."

        properties = {
            "日期": {"title": [{"text": {"content": result.analysis_time[:10]}}]},
            "阶段": {"select": {"name": phase}},
            "综合建议": {"select": {"name": result.overall_suggestion}},
            "判断状态": {"select": {"name": result.judge_status}},
            "信任度": {"number": round(result.trust_score, 2)},
            "健康度": {"number": result.health_score},
            "分析时间": {"date": {"start": result.analysis_time}},
            "信号列表": {"rich_text": [{"text": {"content": signals_json}}]},
        }

        try:
            resp = requests.post("https://api.notion.com/v1/pages", headers=self.headers, json={"parent": {"database_id": self.database_id}, "properties": properties}, timeout=10)
            if resp.status_code == 200:
                print("✅ Notion 存储成功")
                return True
            print(f"❌ Notion 存储失败: {resp.status_code}")
            return False
        except Exception as e:
            print(f"❌ Notion 存储异常: {e}")
            return False
