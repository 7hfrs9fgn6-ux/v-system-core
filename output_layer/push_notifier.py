import os
import yaml
import requests
import time
import hashlib
from datetime import datetime
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
        self._sent_cache = {}
        self._cache_ttl = 3600
        self._index_close = 0
        self._index_pct = 0
        self._macro_data = {}
        self._indices = {}
        self._market_stats = {}
        self._sector_flow = {}

    def _load_config(self, path):
        if os.path.exists(path):
            with open(path, 'r') as f:
                return yaml.safe_load(f)
        return {}

    def _get_content_hash(self, content: str) -> str:
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def _is_duplicate(self, content: str) -> bool:
        content_hash = self._get_content_hash(content)
        if content_hash in self._sent_cache:
            last_time = self._sent_cache[content_hash]
            if (time.time() - last_time) < self._cache_ttl:
                return True
        self._sent_cache[content_hash] = time.time()
        return False

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
            if resp.json().get("code") == 200:
                return True
            else:
                print(f"❌ 推送失败: {resp.json().get('msg')}")
                return False
        except Exception as e:
            print(f"❌ 推送异常: {e}")
            return False

    def send(self, result: SignalResult, phase: str = "pre") -> bool:
        if not self.token:
            print("📢 [模拟] 无Token")
            self._store_to_notion(result, phase)
            return False

        if hasattr(result, '_index_data'):
            self._index_close = result._index_data.get('close', 0)
            self._index_pct = result._index_data.get('pct', 0)

        self._macro_data = getattr(result, '_macro_data', {})
        self._indices = getattr(result, '_indices', {})
        self._market_stats = getattr(result, '_market_stats', {})
        self._sector_flow = getattr(result, '_sector_flow', {})

        phase_info = self.phase_config.get(phase, {"name": phase, "emoji": "📊"})
        title = f"📊 V系统 {phase_info.get('emoji', '')} {phase_info.get('name', phase)}"

        content = self._format_message(result, phase)

        if self._is_duplicate(content):
            print("⏭️ 重复推送已跳过（内容相同）")
            self._store_to_notion(result, phase)
            return True

        success = self._send_with_rate_limit(title, content)
        print("✅ 主推送成功" if success else "❌ 主推送失败")

        if self.alert_enabled and phase == "post":
            self._update_alert_cache(result)

        self._store_to_notion(result, phase)
        return success

    def _update_alert_cache(self, result: SignalResult):
        now = datetime.now()
        for s in result.signals:
            if s.drawdown >= s.threshold:
                key = s.name
                last = self._alert_cache.get(key)
                if not last or (now - last).total_seconds() >= self.alert_cooldown * 3600:
                    self._alert_cache[key] = now
                    print(f"🔔 黄金坑缓存已更新: {s.name} (回撤{s.drawdown}%)")

    def _store_to_notion(self, result: SignalResult, phase: str):
        try:
            from output_layer.notion_storage import NotionStorage
            storage = NotionStorage(self.config)
            storage.store(result, phase)
        except Exception as e:
            print(f"❌ Notion 存储失败: {e}")

    # ============================================================
    # 主格式化入口
    # ============================================================
    def _format_message(self, result: SignalResult, phase: str) -> str:
        if phase == "night":
            return self._format_night_message(result)
        # ✅ P3：如果 Agent 已生成研报级内容，使用研报级格式
        if hasattr(result, 'agent_analysis') and result.agent_analysis:
            agent_data = result.agent_analysis
            if agent_data.get('status') in ['success', 'warning']:
                return self._format_p3_report(result, phase)
        return self._format_p2_normal(result, phase)

    # ============================================================
    # P2正常格式（降级方案）
    # ============================================================
    def _format_p2_normal(self, result: SignalResult, phase: str) -> str:
        phase_info = self.phase_config.get(phase, {"name": phase, "emoji": "📊"})
        phase_text = phase_info.get("name", phase)
        emoji = phase_info.get("emoji", "📊")

        signal_dict = {s.name: s for s in result.signals}
        lines = []

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"{emoji} V系统 {phase_text}")
        lines.append(f"📅 {result.analysis_time[:16]}")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")

        if self._index_close > 0:
            arrow = "📈" if self._index_pct > 0 else "📉" if self._index_pct < 0 else "➡️"
            lines.append(f"【📊 上证指数】{self._index_close:.2f}  {arrow} {self._index_pct:+.2f}%")

        # 简化版持仓信号
        lines.append("")
        lines.append("【📌 你的持仓信号】")
        seen_sectors = set()
        unique_holdings = []
        for fund_code, fund_info in self.holding_map.items():
            sectors = fund_info["sectors"]
            for sec in sectors:
                if sec in seen_sectors:
                    continue
                seen_sectors.add(sec)
                if sec in signal_dict:
                    s = signal_dict[sec]
                    emoji_s = "🟢" if s.signal_level >= 3 else "🟡" if s.signal_level >= 1 else "🟠" if s.signal_level >= -1 else "🔴"
                    status = "机会信号" if s.signal_level >= 3 else "观察中" if s.signal_level >= 1 else "风险提示" if s.signal_level >= -1 else "风险信号"
                    funds_with_sector = [f["name"] for f in self.holding_map.values() if sec in f["sectors"]]
                    fund_label = f"（{','.join(funds_with_sector)}）"
                    unique_holdings.append({
                        "sector": sec,
                        "level": s.signal_level,
                        "drawdown": s.drawdown,
                        "threshold": s.threshold,
                        "emoji": emoji_s,
                        "status": status,
                        "funds": fund_label
                    })
        unique_holdings.sort(key=lambda x: x["level"], reverse=True)
        if unique_holdings:
            for h in unique_holdings[:6]:
                lines.append(f"  {h['emoji']} {h['status']} {h['sector']} {h['funds']}")
                lines.append(f"     └─ 回撤 {h['drawdown']}% / 阈值 {h['threshold']}%")

        # AI点评
        ai_comment = self.commentator.generate_comment(result, self.holding_sectors)
        if ai_comment:
            lines.append("")
            lines.append("【🤖 AI 点评】")
            lines.append(f"  {ai_comment}")

        # Agent分析（简短）
        if hasattr(result, 'agent_analysis') and result.agent_analysis:
            agent_data = result.agent_analysis
            response = agent_data.get('response', '')
            if response:
                cleaned = self._clean_agent_response(response)
                if cleaned:
                    lines.append("")
                    lines.append("【🧠 智能代理分析】")
                    if len(cleaned) > 300:
                        cleaned = cleaned[:300] + "..."
                    lines.append(f"  {cleaned}")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    # ============================================================
    # P3研报级格式（过滤内部信息）
    # ============================================================
    def _format_p3_report(self, result: SignalResult, phase: str) -> str:
        phase_info = self.phase_config.get(phase, {"name": phase, "emoji": "📊"})
        phase_text = phase_info.get("name", phase)
        emoji = phase_info.get("emoji", "📊")

        lines = []
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"{emoji} V系统 {phase_text} 【研报级分析】")
        lines.append(f"📅 {result.analysis_time[:16]}")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # 大盘指数
        if self._index_close > 0:
            arrow = "📈" if self._index_pct > 0 else "📉" if self._index_pct < 0 else "➡️"
            lines.append(f"【📊 上证指数】{self._index_close:.2f}  {arrow} {self._index_pct:+.2f}%")
            if abs(self._index_pct) < 0.5:
                lines.append("   └─ 震荡行情，方向不明")
            elif self._index_pct > 1:
                lines.append("   └─ 强势上涨，市场偏暖")
            elif self._index_pct < -1:
                lines.append("   └─ 明显回调，注意风险")
            else:
                lines.append("   └─ 小幅波动，正常整理")

        # 涨跌家数
        if self._market_stats:
            stats = self._market_stats
            up = stats.get('up', 0)
            down = stats.get('down', 0)
            flat = stats.get('flat', 0)
            if up + down + flat > 0:
                if down > 0 and up / down > 2:
                    status = "🟢 普涨"
                elif down > 0 and up / down > 0.5:
                    status = "🟡 震荡"
                else:
                    status = "🔴 普跌"
                lines.append(f"【📊 涨跌家数】{status} | 上涨{up}家 / 下跌{down}家")

        # ✅ Agent研报内容（过滤内部思考）
        if hasattr(result, 'agent_analysis') and result.agent_analysis:
            agent_data = result.agent_analysis
            response = agent_data.get('response', '')
            if response:
                cleaned_response = self._clean_agent_response(response)
                if cleaned_response:
                    lines.append("")
                    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
                    # 按段落分割
                    paragraphs = cleaned_response.split('\n\n')
                    for para in paragraphs:
                        if para.strip():
                            if para.startswith('#'):
                                # 标题
                                title = para.lstrip('#').strip()
                                lines.append(f"【{title}】")
                            else:
                                # 普通段落，保留缩进，但过滤掉表格中的分隔线
                                for line in para.split('\n'):
                                    clean_line = line.strip()
                                    if clean_line:
                                        # 跳过表格分隔符行（如 |---|）
                                        if clean_line.startswith('|') and '---' in clean_line:
                                            continue
                                        # 跳过单独的分隔线
                                        if clean_line in ['---', '***', '___']:
                                            continue
                                        lines.append(f"  {clean_line}")
                    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # ✅ 不显示工具调用次数，不显示告警信息

        # 操作建议（纯净版）
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("【📌 操作建议】")
        if result.judge_status == "正常":
            lines.append("  ✅ 系统判断可信，可参考信号做决策")
        elif result.judge_status == "偏低":
            lines.append("  🟡 系统判断参考价值有限，建议结合其他信息确认")
        else:
            lines.append("  🔴 系统判断不可靠，建议暂停决策")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    # ============================================================
    # 夜间预测格式
    # ============================================================
    def _format_night_message(self, result: SignalResult) -> str:
        phase_info = self.phase_config.get("night", {"name": "夜间预测", "emoji": "🌙"})
        phase_text = phase_info.get("name", "夜间预测")
        emoji = phase_info.get("emoji", "🌙")

        lines = []
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"{emoji} V系统 {phase_text}")
        lines.append(f"📅 {result.analysis_time[:16]}")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")

        if self._index_close > 0:
            arrow = "📈" if self._index_pct > 0 else "📉" if self._index_pct < 0 else "➡️"
            lines.append(f"【📊 今日收盘】{self._index_close:.2f}  {arrow} {self._index_pct:+.2f}%")

        if hasattr(result, 'sentiment') and result.sentiment:
            lines.append("")
            lines.append("【📰 今日消息面扫描】")
            sorted_sentiment = sorted(
                result.sentiment.items(),
                key=lambda x: x[1].get('intensity_score', 0),
                reverse=True
            )[:5]
            for sec, data in sorted_sentiment:
                intensity = data.get('intensity_score', 0)
                emotion = data.get('emotion_label', '中性')
                bar = "█" * int(intensity) + "░" * (10 - int(intensity))
                lines.append(f"  {sec}: {bar} {intensity}/10 ({emotion})")

        if hasattr(result, 'agent_analysis') and result.agent_analysis:
            agent_data = result.agent_analysis
            response = agent_data.get('response', '')
            if response:
                cleaned = self._clean_agent_response(response)
                if cleaned:
                    lines.append("")
                    lines.append("【🧠 晚间消息汇总】")
                    if len(cleaned) > 200:
                        cleaned = cleaned[:200] + "..."
                    lines.append(f"  {cleaned}")

        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("【🌅 次日开盘预判】")
        if self._index_pct > 1:
            lines.append("  📈 今日强势收盘，明日有望延续")
        elif self._index_pct > 0.3:
            lines.append("  📈 今日温和上涨，关注隔夜外盘")
        elif self._index_pct > -0.3:
            lines.append("  ➡️ 今日窄幅波动，等待方向选择")
        elif self._index_pct > -1:
            lines.append("  📉 今日小幅回调，关注企稳信号")
        else:
            lines.append("  📉 今日明显下跌，短期或有惯性下探")
        lines.append("  💡 明日开盘前请查看盘前预测（09:00）")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")

        return "\n".join(lines)

    # ============================================================
    # 辅助方法：过滤Agent内部思考
    # ============================================================
    def _clean_agent_response(self, response: str) -> str:
        """过滤掉Agent的内部思考过程"""
        if not response:
            return ""

        # 需要过滤的关键词（内部思考特征）
        filter_patterns = [
            "好的，现在我来",
            "现在我来获取",
            "接下来我来",
            "让我来",
            "我先",
            "data already collected",
            "now I will",
            "let me",
            "I'll get",
            "I will",
            "proceeding to",
            "获取更多补充数据",
            "我们开始",
            "先获取",
            "好的，以下是根据",
            "根据所有获取到的数据",
            "根据以上所有工具调用结果",
            "现在生成",
            "开始生成",
        ]

        lines = response.split('\n')
        cleaned_lines = []
        for line in lines:
            # 跳过空行
            if not line.strip():
                continue
            # 检查是否包含内部思考关键词
            skip = False
            for pattern in filter_patterns:
                if pattern in line:
                    skip = True
                    break
            if skip:
                continue
            # 过滤掉只有分隔符的行
            if line.strip() in ['---', '***', '___', '===']:
                continue
            cleaned_lines.append(line)

        return '\n'.join(cleaned_lines)
