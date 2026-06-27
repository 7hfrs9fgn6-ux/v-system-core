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

        # ✅ 安全获取大盘数据
        if hasattr(result, '_index_data') and result._index_data is not None:
            self._index_close = result._index_data.get('close', 0)
            self._index_pct = result._index_data.get('pct', 0)
        else:
            self._index_close = 0
            self._index_pct = 0

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
        # 对于有研报级Agent分析的情况，使用P3格式（已过滤内部信息）
        if hasattr(result, 'agent_analysis') and result.agent_analysis:
            agent_data = result.agent_analysis
            if agent_data.get('status') in ('success', 'warning') and agent_data.get('response'):
                return self._format_structured_report(result, phase)
        # 否则使用结构化展示（基于信号数据）
        return self._format_structured_report(result, phase)

    # ============================================================
    # 核心：结构化研报级推送（融合旧版清晰结构）
    # ============================================================
    def _format_structured_report(self, result: SignalResult, phase: str) -> str:
        """生成结构化研报级推送（隐藏内部信息，展示关键数据）"""
        phase_info = self.phase_config.get(phase, {"name": phase, "emoji": "📊"})
        phase_text = phase_info.get("name", phase)
        emoji = phase_info.get("emoji", "📊")

        lines = []
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"{emoji} V系统 {phase_text} 【研报级分析】")
        lines.append(f"📅 {result.analysis_time[:16]}")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # ---------- 1. 市场概览 ----------
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

        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # ---------- 2. 信号汇总（按等级分组） ----------
        signal_dict = {s.name: s for s in result.signals}
        holding_sector_names = list(set(self.holding_sectors))

        strong_buy = [s for s in result.signals if s.signal_level >= 3]
        watch = [s for s in result.signals if 1 <= s.signal_level < 3]
        risk = [s for s in result.signals if s.signal_level < 0]

        strong_buy.sort(key=lambda x: (-x.signal_level, x.name))
        watch.sort(key=lambda x: (-x.signal_level, x.name))
        risk.sort(key=lambda x: (x.signal_level, x.name))

        if strong_buy:
            lines.append("【🟢 机会信号】")
            for s in strong_buy:
                tag = " 📌" if s.name in holding_sector_names else ""
                emoji_s = "🟢" if s.signal_level >= 4 else "🟢"
                lines.append(f"  {emoji_s} {s.name}{tag}")
                if s.drawdown >= s.threshold:
                    excess = s.drawdown - s.threshold
                    lines.append(f"    └─ 回撤{s.drawdown}% (阈值{s.threshold}%) 超出{excess:.1f}%")
                else:
                    lines.append(f"    └─ 回撤{s.drawdown}% (阈值{s.threshold}%)")
                if hasattr(result, 'sentiment') and result.sentiment and s.name in result.sentiment:
                    sent = result.sentiment[s.name]
                    intensity = sent.get('intensity_score', 0)
                    emotion = sent.get('emotion_label', '中性')
                    lines.append(f"    └─ 消息面: {intensity}/10 ({emotion})")
                lines.append("")
        else:
            lines.append("【🟢 机会信号】无")

        if watch:
            lines.append("【🟡 观察中】")
            for s in watch:
                tag = " 📌" if s.name in holding_sector_names else ""
                emoji_s = "🟡" if s.signal_level >= 2 else "🟡"
                lines.append(f"  {emoji_s} {s.name}{tag}")
                if s.drawdown >= s.threshold:
                    excess = s.drawdown - s.threshold
                    lines.append(f"    └─ 回撤{s.drawdown}% (阈值{s.threshold}%) 超出{excess:.1f}%")
                else:
                    lines.append(f"    └─ 回撤{s.drawdown}% (阈值{s.threshold}%)")
                if hasattr(result, 'sentiment') and result.sentiment and s.name in result.sentiment:
                    sent = result.sentiment[s.name]
                    intensity = sent.get('intensity_score', 0)
                    emotion = sent.get('emotion_label', '中性')
                    lines.append(f"    └─ 消息面: {intensity}/10 ({emotion})")
                lines.append("")
        else:
            lines.append("【🟡 观察中】无")

        if risk:
            lines.append("【🔴 风险信号】")
            for s in risk:
                tag = " 📌" if s.name in holding_sector_names else ""
                emoji_s = "🔴" if s.signal_level <= -2 else "🟠"
                lines.append(f"  {emoji_s} {s.name}{tag}")
                if s.drawdown >= s.threshold:
                    excess = s.drawdown - s.threshold
                    lines.append(f"    └─ 回撤{s.drawdown}% (阈值{s.threshold}%) 超出{excess:.1f}%")
                else:
                    lines.append(f"    └─ 回撤{s.drawdown}% (阈值{s.threshold}%)")
                if hasattr(result, 'sentiment') and result.sentiment and s.name in result.sentiment:
                    sent = result.sentiment[s.name]
                    intensity = sent.get('intensity_score', 0)
                    emotion = sent.get('emotion_label', '中性')
                    lines.append(f"    └─ 消息面: {intensity}/10 ({emotion})")
                lines.append("")
        else:
            lines.append("【🔴 风险信号】无")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # ---------- 3. 持仓基金信号汇总 ----------
        lines.append("")
        lines.append("【📌 持仓基金信号汇总】")
        if self.holding_map:
            for fund_code, fund_info in self.holding_map.items():
                fund_name = fund_info["name"]
                sectors = fund_info["sectors"]
                best_sector = None
                best_level = -99
                best_drawdown = 0
                best_threshold = 0
                for sec in sectors:
                    if sec in signal_dict:
                        s = signal_dict[sec]
                        if s.signal_level > best_level:
                            best_level = s.signal_level
                            best_sector = sec
                            best_drawdown = s.drawdown
                            best_threshold = s.threshold
                if best_sector:
                    if best_level >= 3:
                        emoji_f = "🟢"
                        status = "机会信号"
                        action = "✅ 关注"
                    elif best_level >= 1:
                        emoji_f = "🟡"
                        status = "观察中"
                        action = "🔍 等待"
                    else:
                        emoji_f = "🔴"
                        status = "风险信号"
                        action = "⚠️ 谨慎"
                    lines.append(f"  {emoji_f} {fund_name}：{status}（{best_sector}驱动）{action}")
                else:
                    lines.append(f"  ⚪ {fund_name}：暂不操作")
        else:
            lines.append("  （无持仓数据）")

        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # ---------- 4. 风险预警 ----------
        if risk:
            lines.append("【⚠️ 风险预警】")
            for s in risk[:3]:
                lines.append(f"  🔴 {s.name}：回撤仅{s.drawdown}%，接近高位，注意风险")
            lines.append("")

        # ---------- 5. 影子系统验证 ----------
        if hasattr(result, 'shadow') and result.shadow:
            reliability = result.shadow.get('reliability', {})
            lines.append("【👻 影子系统验证】")
            lines.append(f"  可靠度: {reliability.get('overall_reliability', 0):.2%}")
            consensus = reliability.get('consensus_level', '未知')
            if consensus == "高":
                lines.append("  ✅ 各策略基本一致，信号可信度高")
            elif consensus == "中":
                lines.append("  🟡 各策略存在部分分歧，建议谨慎")
            else:
                lines.append("  ⚠️ 各策略分歧较大，建议保守操作")
            divergence = reliability.get('divergence_sectors', [])
            if divergence:
                lines.append(f"  差异板块: {', '.join(divergence)}")
            lines.append("")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # ---------- 6. AI 总结 ----------
        ai_summary = ""
        if hasattr(result, 'agent_analysis') and result.agent_analysis:
            agent_data = result.agent_analysis
            response = agent_data.get('response', '')
            if response:
                cleaned = self._clean_agent_response(response)
                ai_summary = cleaned.strip()
        if not ai_summary:
            ai_summary = self.commentator.generate_comment(result, self.holding_sectors)

        if ai_summary:
            lines.append("【🤖 AI 盘后总结】")
            if len(ai_summary) > 500:
                ai_summary = ai_summary[:500] + "..."
            lines.append(f"  {ai_summary}")
            lines.append("")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # ---------- 7. 操作建议 ----------
        lines.append("【📌 L4综合建议】")
        if result.judge_status == "正常":
            lines.append("  ✅ 系统判断可信，可参考信号做决策")
        elif result.judge_status == "偏低":
            lines.append("  🟡 系统判断参考价值有限，建议结合其他信息确认")
        else:
            lines.append("  🔴 系统判断不可靠，建议暂停决策")
        lines.append(f"⏰ 数据时间：{result.analysis_time[:16]} CST")

        return "\n".join(lines)

    # ============================================================
    # 辅助：过滤Agent内部思考
    # ============================================================
    def _clean_agent_response(self, response: str) -> str:
        filter_patterns = [
            "好的，现在我来", "现在我来获取", "接下来我来", "让我来", "我先",
            "data already collected", "now I will", "let me", "I'll get", "I will",
            "proceeding to", "获取更多补充数据", "我们开始", "先获取",
            "好的，以下", "正在获取", "我来生成", "现在开始", "首先",
            "然后", "接着", "我再", "还需要", "为了获取", "我们看看", "接下来"
        ]
        lines = response.split('\n')
        cleaned = []
        for line in lines:
            line_strip = line.strip()
            if not line_strip:
                continue
            skip = False
            for pat in filter_patterns:
                if pat in line:
                    skip = True
                    break
            if skip:
                continue
            if line_strip in ['---', '***', '___']:
                continue
            cleaned.append(line)
        return '\n'.join(cleaned)

    # ============================================================
    # 夜间预测专用格式
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
