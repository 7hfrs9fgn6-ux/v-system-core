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
        # 大盘数据
        self._index_close = 0
        self._index_pct = 0
        # 宏观数据（P1新增）
        self._macro_data = {}

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

        # 读取大盘数据
        if hasattr(result, '_index_data'):
            self._index_close = result._index_data.get('close', 0)
            self._index_pct = result._index_data.get('pct', 0)

        # 读取宏观数据（P1新增）
        self._macro_data = getattr(result, '_macro_data', {})

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
        """根据阶段选择对应的推送格式"""
        if phase == "night":
            return self._format_night_message(result)
        else:
            return self._format_normal_message(result, phase)

    # ============================================================
    # 正常阶段（pre / intraday_a / intraday_b / post）推送格式
    # ============================================================
    def _format_normal_message(self, result: SignalResult, phase: str) -> str:
        phase_info = self.phase_config.get(phase, {"name": phase, "emoji": "📊"})
        phase_text = phase_info.get("name", phase)
        emoji = phase_info.get("emoji", "📊")

        signal_dict = {s.name: s for s in result.signals}
        lines = []

        # 头部
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"{emoji} V系统 {phase_text}")
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

        # ========== 宏观数据展示（P1新增） ==========
        if self._macro_data:
            macro = self._macro_data
            lines.append("")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
            lines.append("【🌍 隔夜外围市场】")
            
            # 美股
            us = macro.get('us_market', {})
            us_indices = us.get('indices', [])
            if us_indices:
                us_line = "  🇺🇸 美股: "
                for idx in us_indices[:3]:
                    pct = idx.get('pct_change', 0)
                    arrow = "▲" if pct and pct > 0 else "▼" if pct and pct < 0 else "→"
                    us_line += f"{idx.get('name', '')} {arrow} {abs(pct or 0):.2f}%  "
                lines.append(us_line)
            
            # 费城半导体
            sem = us.get('semiconductor', {})
            if sem.get('price'):
                pct = sem.get('pct_change', 0)
                arrow = "▲" if pct > 0 else "▼" if pct < 0 else "→"
                lines.append(f"  🔌 费城半导体: {arrow} {abs(pct):.2f}%")
            
            # 科技巨头
            techs = us.get('tech_giants', [])
            if techs:
                sorted_techs = sorted(techs, key=lambda x: abs(x.get('pct_change', 0)), reverse=True)
                top_techs = sorted_techs[:3]
                tech_line = "  💻 科技巨头: "
                for t in top_techs:
                    pct = t.get('pct_change', 0)
                    arrow = "▲" if pct > 0 else "▼" if pct < 0 else "→"
                    tech_line += f"{t.get('name', '')} {arrow} {abs(pct):.2f}%  "
                lines.append(tech_line)
            
            # 亚太
            asia = macro.get('asia_market', {})
            asia_indices = asia.get('indices', [])
            if asia_indices:
                asia_line = "  🌏 亚太: "
                for idx in asia_indices[:4]:
                    pct = idx.get('pct_change', 0)
                    arrow = "▲" if pct and pct > 0 else "▼" if pct and pct < 0 else "→"
                    asia_line += f"{idx.get('name', '')} {arrow} {abs(pct or 0):.2f}%  "
                lines.append(asia_line)
            
            # 欧洲
            euro = macro.get('europe_market', {})
            euro_indices = euro.get('indices', [])
            if euro_indices:
                euro_line = "  🇪🇺 欧洲: "
                for idx in euro_indices[:3]:
                    pct = idx.get('pct_change', 0)
                    arrow = "▲" if pct and pct > 0 else "▼" if pct and pct < 0 else "→"
                    euro_line += f"{idx.get('name', '')} {arrow} {abs(pct or 0):.2f}%  "
                lines.append(euro_line)
            
            # 大宗商品
            comm = macro.get('commodities', {})
            oil_list = comm.get('oil', [])
            if oil_list:
                oil_line = "  🛢️ 原油: "
                for oil in oil_list:
                    pct = oil.get('pct_change', 0)
                    arrow = "▲" if pct > 0 else "▼" if pct < 0 else "→"
                    oil_line += f"{oil.get('name', '')} {arrow} {abs(pct):.2f}%  "
                lines.append(oil_line)
            
            # 黄金
            gold = comm.get('gold', {})
            if gold.get('price'):
                pct = gold.get('pct_change', 0)
                arrow = "▲" if pct > 0 else "▼" if pct < 0 else "→"
                lines.append(f"  🥇 黄金: {arrow} {abs(pct):.2f}%  (${gold.get('price', 0):.2f})")
            
            # 汇率 + A50
            forex = macro.get('forex', {})
            usd_cny = forex.get('usd_cny', {})
            if usd_cny.get('onshore'):
                lines.append(f"  💱 人民币: {usd_cny.get('onshore', 0):.4f}")
            
            a50 = macro.get('a50_futures', {})
            if a50.get('price'):
                pct = a50.get('pct_change', 0)
                arrow = "▲" if pct > 0 else "▼" if pct < 0 else "→"
                lines.append(f"  📊 A50期货: {a50.get('price', 0):.2f} {arrow} {abs(pct):.2f}%")
            
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # 核心建议
        lines.append("")
        lines.append("【💡 今日核心建议】")
        suggestion = result.overall_suggestion
        if suggestion == "偏多":
            lines.append(f"   📌 方向判断：看好后市（偏多）")
            lines.append(f"   💬 解读：系统认为市场整体向上概率较大")
        elif suggestion == "偏空":
            lines.append(f"   📌 方向判断：看淡后市（偏空）")
            lines.append(f"   💬 解读：系统认为市场整体向下概率较大")
        else:
            lines.append(f"   📌 方向判断：震荡整理")
            lines.append(f"   💬 解读：系统认为市场方向不明，建议观望")

        judge = result.judge_status
        trust = result.trust_score
        if judge == "正常":
            lines.append(f"   📊 可信度：🟢 可信（信任度 {trust:.2f}）")
            lines.append(f"   💬 解读：数据质量好，建议可参考")
        elif judge == "偏低":
            lines.append(f"   📊 可信度：🟡 偏低（信任度 {trust:.2f}）")
            lines.append(f"   💬 解读：数据可能有延迟，建议结合其他信息确认")
        else:
            lines.append(f"   📊 可信度：🟠 需谨慎（信任度 {trust:.2f}）")
            lines.append(f"   💬 解读：数据质量不佳，不建议据此操作")

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
            for h in unique_holdings:
                lines.append(f"  {h['emoji']} {h['status']} {h['sector']} {h['funds']}")
                lines.append(f"     └─ 回撤 {h['drawdown']}% / 阈值 {h['threshold']}%")
        else:
            lines.append("  （暂无持仓信号数据）")

        # 最强/最弱信号
        non_holding = [s for s in result.signals if s.name not in self.holding_sectors]
        strongest = max(non_holding, key=lambda x: x.signal_level) if non_holding else None
        weakest = min(non_holding, key=lambda x: x.signal_level) if non_holding else None

        if strongest:
            em = "🟢" if strongest.signal_level >= 3 else "🟡" if strongest.signal_level >= 1 else "🟠"
            lines.append("")
            lines.append(f"【🔥 市场最强信号】{em} {strongest.name}")
            lines.append(f"     └─ 回撤 {strongest.drawdown}% / 阈值 {strongest.threshold}%")
            if strongest.drawdown >= strongest.threshold + 10:
                lines.append("     └─ ⚠️ 深度超跌，可能出现反弹机会")

        if weakest:
            em = "🟠" if weakest.signal_level >= -1 else "🔴"
            lines.append("")
            lines.append(f"【⚠️ 市场最弱信号】{em} {weakest.name}")
            lines.append(f"     └─ 回撤 {weakest.drawdown}% / 阈值 {weakest.threshold}%")
            if weakest.drawdown < weakest.threshold - 10:
                lines.append("     └─ 📈 相对强势，暂不适合抄底")

        # 烈度评分（持仓板块）
        if hasattr(result, 'sentiment') and result.sentiment:
            lines.append("")
            lines.append("【📰 消息面烈度评分】")
            for sec in self.holding_sectors:
                if sec in result.sentiment:
                    s = result.sentiment[sec]
                    intensity = s.get('intensity_score', 0)
                    emotion = s.get('emotion_label', '中性')
                    bar = "█" * int(intensity) + "░" * (10 - int(intensity))
                    lines.append(f"  {sec}: {bar} {intensity}/10 ({emotion})")
                    if intensity >= 7:
                        lines.append(f"     └─ 🔥 消息面高度活跃，关注度较高")
                    elif intensity <= 3:
                        lines.append(f"     └─ 💤 消息面平淡，暂无明显催化剂")

        # 影子系统
        if hasattr(result, 'shadow') and result.shadow:
            reliability = result.shadow.get('reliability', {})
            lines.append("")
            lines.append("【👻 影子系统验证】")
            lines.append(f"  可靠度: {reliability.get('overall_reliability', 0):.2%}")
            if reliability.get('overall_reliability', 0) >= 0.7:
                lines.append("  ✅ 各策略基本一致，信号可信度高")
            else:
                lines.append("  ⚠️ 各策略存在分歧，建议保守操作")

        # 相对强度
        if hasattr(result, 'relative_strength') and result.relative_strength:
            lines.append("")
            lines.append("【📊 相对强度】")
            for sec in self.holding_sectors:
                if sec in result.relative_strength:
                    rs = result.relative_strength[sec]
                    ratio = rs.get('strength_ratio', 1.0)
                    interp = rs.get('interpretation', '中性')
                    emoji_r = "🟢" if interp == "强势" else "🟡" if interp == "中性" else "🔴"
                    lines.append(f"  {sec}: {emoji_r} {ratio:.2f} ({interp})")

        # AI点评
        ai_comment = self.commentator.generate_comment(result, self.holding_sectors)
        if ai_comment:
            lines.append("")
            lines.append("【🤖 AI 点评】")
            lines.append(f"  {ai_comment}")

        # 智能代理分析
        if hasattr(result, 'agent_analysis') and result.agent_analysis:
            agent_data = result.agent_analysis
            response = agent_data.get('response', '')
            if response:
                if len(response) > 250:
                    response = response[:250] + "..."
                lines.append("")
                lines.append("【🧠 智能代理分析】")
                for line in response.split('\n')[:5]:
                    if line.strip():
                        lines.append(f"  {line.strip()}")

        # 黄金坑预警
        if self.alert_enabled and phase == "post":
            now = datetime.now()
            triggered = []
            for s in result.signals:
                if s.drawdown >= s.threshold:
                    key = s.name
                    last = self._alert_cache.get(key)
                    if not last or (now - last).total_seconds() >= self.alert_cooldown * 3600:
                        triggered.append(s)
            if triggered:
                lines.append("")
                lines.append("【🔔 黄金坑触发预警】")
                lines.append(f"  触发数量：{len(triggered)} 个板块")
                for s in triggered:
                    excess = s.drawdown - s.threshold
                    em = "🟢" if s.signal_level >= 3 else "🟡" if s.signal_level >= 1 else "🟠"
                    lines.append(f"    {em} {s.name}：回撤{s.drawdown}% / 阈值{s.threshold}% (超出{excess:.1f}%)")
                lines.append("  📌 建议：关注以上板块，可考虑分批建仓")

        # 操作建议
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("【📌 操作建议】")
        if result.judge_status == "正常":
            lines.append("  ✅ 系统判断可信，可参考信号做决策")
            lines.append("  📍 关注持仓中信号最强的板块")
        elif result.judge_status == "偏低":
            lines.append("  🟡 系统判断参考价值有限")
            lines.append("  📍 建议：查看其他信息源（财经新闻、研报）后综合判断")
            lines.append("  ⚠️ 暂不建议仅据此操作")
        else:
            lines.append("  🔴 系统判断不可靠，建议暂停决策")
            lines.append("  📍 等待下一时段数据更新后再做判断")

        if result.warnings:
            lines.append("")
            lines.append("【⚠️ 系统提示】")
            for w in result.warnings:
                if "STALE" in w:
                    lines.append("  ⏰ 数据可能有延迟（使用前一日数据）")
                elif "封顶" in w:
                    lines.append("  📊 因数据延迟，系统自动降低了可信度")
                elif "计划漂移" in w:
                    lines.append("  🔄 系统检测到分析方向略有偏离，已自动修正")
                elif "健康度" in w:
                    lines.append("  🩺 系统部分功能存在异常，建议谨慎")
                else:
                    lines.append(f"  ⚠️ {w}")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    # ============================================================
    # 夜间预测专用格式（只显示消息面 + 次日预判）
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

        # 1. 今日收盘
        if self._index_close > 0:
            arrow = "📈" if self._index_pct > 0 else "📉" if self._index_pct < 0 else "➡️"
            lines.append(f"【📊 今日收盘】{self._index_close:.2f}  {arrow} {self._index_pct:+.2f}%")
            if abs(self._index_pct) < 0.5:
                lines.append("   └─ 窄幅震荡，市场方向不明")
            elif self._index_pct > 1:
                lines.append("   └─ 强势上涨，多头占优")
            elif self._index_pct < -1:
                lines.append("   └─ 明显回调，注意风险")

        # 2. 消息面烈度评分
        if hasattr(result, 'sentiment') and result.sentiment:
            lines.append("")
            lines.append("【📰 今日消息面扫描】")
            # 按烈度排序
            sorted_sentiment = sorted(
                result.sentiment.items(),
                key=lambda x: x[1].get('intensity_score', 0),
                reverse=True
            )[:6]  # 最多显示6个

            for sec, data in sorted_sentiment:
                intensity = data.get('intensity_score', 0)
                emotion = data.get('emotion_label', '中性')
                bar = "█" * int(intensity) + "░" * (10 - int(intensity))
                summary = data.get('summary', '')
                lines.append(f"  {sec}: {bar} {intensity}/10 ({emotion})")
                if summary:
                    lines.append(f"     └─ {summary[:40]}...")

            sources = set()
            for v in result.sentiment.values():
                if '数据源' in v:
                    sources.add(v['数据源'])
            lines.append(f"  📌 数据来源: {', '.join(sources) if sources else '未知'}")

        # 3. Agent 消息面分析
        if hasattr(result, 'agent_analysis') and result.agent_analysis:
            agent_data = result.agent_analysis
            response = agent_data.get('response', '')
            if response:
                lines.append("")
                lines.append("【🧠 晚间消息汇总】")
                if len(response) > 250:
                    response = response[:250] + "..."
                lines.append(f"  {response}")

        # 4. 次日预判
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

        # 高烈度板块提示
        if hasattr(result, 'sentiment') and result.sentiment:
            high_sectors = [
                sec for sec, data in result.sentiment.items()
                if data.get('intensity_score', 0) >= 6
            ]
            if high_sectors:
                lines.append(f"  🔥 重点关注: {', '.join(high_sectors[:3])}")

        lines.append("  💡 明日开盘前请查看盘前预测（09:00）")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")

        return "\n".join(lines)
