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

        # ✅ P3：如果 Agent 已生成研报级内容，使用研报格式
        if hasattr(result, 'agent_analysis') and result.agent_analysis:
            agent_data = result.agent_analysis
            if agent_data.get('status') == 'success' or agent_data.get('status') == 'warning':
                return self._format_p3_report(result, phase)

        # 降级：使用 P2 正常格式
        return self._format_p2_normal(result, phase)

    # ============================================================
    # P3 研报级格式（过滤内部思考过程）
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

        # ✅ 核心：Agent 研报内容（过滤思考过程）
        if hasattr(result, 'agent_analysis') and result.agent_analysis:
            agent_data = result.agent_analysis
            response = agent_data.get('response', '')
            if response:
                # 过滤内部思考
                cleaned_response = self._clean_agent_response(response)
                if cleaned_response:
                    lines.append("")
                    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
                    # 按段落分割
                    paragraphs = cleaned_response.split('\n\n')
                    for para in paragraphs:
                        if para.strip():
                            if para.startswith('#'):
                                title = para.lstrip('#').strip()
                                lines.append(f"【{title}】")
                            else:
                                for line in para.split('\n'):
                                    if line.strip():
                                        # 跳过表格分隔线
                                        if line.strip().startswith('|') and '---' in line:
                                            continue
                                        lines.append(f"  {line.strip()}")
                    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # ✅ 不显示工具调用次数、告警等内部信息

        # 操作建议（仅显示判断状态）
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

    def _clean_agent_response(self, response: str) -> str:
        """
        过滤掉 Agent 的内部思考过程（如“好的，现在我来...”）
        只保留真正的分析内容
        """
        # 需要过滤的关键词（中英文）
        filter_patterns = [
            "好的，现在我来",
            "现在我来获取",
            "接下来我来",
            "让我来",
            "我先",
            "我们开始",
            "获取更多补充数据",
            "data already collected",
            "now I will",
            "let me",
            "I'll get",
            "I will",
            "proceeding to",
            "starting to",
            "going to fetch",
            "will now",
            "going to get",
            "before I continue",
            "let's proceed",
            "I'm going to",
            "接下来我将",
            "现在开始",
            "我先获取",
        ]

        lines = response.split('\n')
        cleaned_lines = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # 跳过内部思考行
            skip = False
            for pattern in filter_patterns:
                if pattern in stripped:
                    skip = True
                    break
            if skip:
                continue

            # 跳过纯分隔符
            if stripped in ['---', '***', '___', '===']:
                continue

            # 跳过只有几个字的无意义句子
            if len(stripped) < 5 and stripped in ['好的', 'OK', 'ok', 'yes', '是']:
                continue

            cleaned_lines.append(line)

        return '\n'.join(cleaned_lines)

    # ============================================================
    # P2 正常格式（降级备用）
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

        lines.append("")
        lines.append("【💡 今日核心建议】")
        suggestion = result.overall_suggestion
        if suggestion == "偏多":
            lines.append(f"   📌 方向判断：看好后市（偏多）")
        elif suggestion == "偏空":
            lines.append(f"   📌 方向判断：看淡后市（偏空）")
        else:
            lines.append(f"   📌 方向判断：震荡整理")

        judge = result.judge_status
        trust = result.trust_score
        if judge == "正常":
            lines.append(f"   📊 可信度：🟢 可信（信任度 {trust:.2f}）")
        elif judge == "偏低":
            lines.append(f"   📊 可信度：🟡 偏低（信任度 {trust:.2f}）")
        else:
            lines.append(f"   📊 可信度：🟠 需谨慎（信任度 {trust:.2f}）")

        mode = result.agent_mode
        if mode == "AI分析":
            lines.append(f"   🤖 模式：AI智能分析（推荐）")
        elif mode == "规则分析":
            lines.append(f"   ⚙️  模式：规则分析（数据不足，AI暂未启用）")
        else:
            lines.append(f"   ⚠️  模式：AI已暂停（系统保守运行）")

        # 持仓信号（去重）
        lines.append("")
        lines.append("【📌 你的持仓信号】")
        seen_sectors = set()
        unique_holdings = []
        for fund_code, fund_info in self.holding_map.items():
            fund_name = fund_info["name"]
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

        # Agent分析（仅限研报内容，不显示内部信息）
        if hasattr(result, 'agent_analysis') and result.agent_analysis:
            agent_data = result.agent_analysis
            response = agent_data.get('response', '')
            if response:
                cleaned = self._clean_agent_response(response)
                if cleaned:
                    lines.append("")
                    lines.append("【🧠 智能代理分析】")
                    for line in cleaned.split('\n')[:10]:
                        if line.strip():
                            lines.append(f"  {line.strip()}")

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
                    for line in cleaned.split('\n')[:8]:
                        if line.strip():
                            lines.append(f"  {line.strip()}")

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
