# 推送通知器 V2.0.2 风格（真实持仓映射版）
# 对应 03-full-closure.yml

import os
import requests
from output_layer.signal_result import SignalResult

# ============================================================
# 📌 你的真实持仓映射（基金代码 → 映射板块列表）
# 按照 V2.0.2 第6.1节 规则配置
# ============================================================
HOLDING_MAP = {
    "009777": {"name": "中欧阿尔法混合C", "sectors": ["电子", "计算机", "通信"]},
    "006229": {"name": "中欧医疗创新股票C", "sectors": ["医药生物"]},
    "001632": {"name": "天弘食品饮料ETF联接C", "sectors": ["食品饮料"]},
    "260108": {"name": "景顺长城新兴成长A", "sectors": ["食品饮料", "家用电器"]},
    "012414": {"name": "招商中证白酒指数C", "sectors": ["食品饮料"]},
    "012417": {"name": "招商国证生物医药C", "sectors": ["医药生物"]},
}

# 提取所有持仓板块（用于信号筛选）
HOLDING_SECTORS = []
for fund in HOLDING_MAP.values():
    HOLDING_SECTORS.extend(fund["sectors"])
HOLDING_SECTORS = list(set(HOLDING_SECTORS))  # 去重


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

        # ---------- 1. 获取所有板块的信号字典（按板块名索引） ----------
        signal_dict = {s.name: s for s in result.signals}

        # ---------- 2. 遍历你的持仓，生成持仓信号 ----------
        holding_lines = []
        for fund_code, fund_info in HOLDING_MAP.items():
            fund_name = fund_info["name"]
            sectors = fund_info["sectors"]

            # 收集该基金所有映射板块的信号等级
            sector_signals = []
            for sec in sectors:
                if sec in signal_dict:
                    s = signal_dict[sec]
                    sector_signals.append((sec, s.signal_level, s.drawdown, s.threshold))

            if not sector_signals:
                holding_lines.append(f"  ⚪ {fund_name}：无数据")
                continue

            # 取信号最强的板块作为该基金的代表信号
            best = max(sector_signals, key=lambda x: x[1])
            best_sec, best_level, best_dd, best_th = best

            # 映射为颜色和文字
            if best_level >= 3:
                emoji = "🟢"
                status = "机会信号"
            elif best_level >= 1:
                emoji = "🟡"
                status = "观察中"
            elif best_level >= -1:
                emoji = "🟠"
                status = "风险提示"
            else:
                emoji = "🔴"
                status = "风险信号"

            # 多板块时显示驱动板块
            if len(sector_signals) > 1:
                driver = f"（{best_sec}驱动）"
            else:
                driver = ""

            holding_lines.append(
                f"  {emoji} {status} {fund_name}{driver} 回撤{best_dd}% / 阈值{best_th}%"
            )

        # ---------- 3. 找出非持仓中的最强和最弱信号 ----------
        non_holding = [s for s in result.signals if s.name not in HOLDING_SECTORS]
        strongest = max(non_holding, key=lambda x: x.signal_level) if non_holding else None
        weakest = min(non_holding, key=lambda x: x.signal_level) if non_holding else None

        def format_signal(s, prefix=""):
            emoji = "🟢" if s.signal_level >= 3 else "🟡" if s.signal_level >= 1 else "🟠" if s.signal_level >= -1 else "🔴"
            return f"{prefix}{emoji} {s.name} (回撤{s.drawdown}% / 阈值{s.threshold}%)"

        # ---------- 4. 组装推送文本 ----------
        lines = []
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"📊 V系统 {phase_text} [{result.analysis_time}]")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"【综合建议】{result.overall_suggestion}")
        lines.append(f"【判断状态】{result.judge_status}")
        lines.append(f"【运行模式】{result.agent_mode}")
        lines.append("")

        # 持仓板块信号（P0 优先级）
        lines.append("【📌 你的持仓信号】")
        if holding_lines:
            lines.extend(holding_lines)
        else:
            lines.append("  （无持仓数据）")

        # 最强信号（P1 优先级）
        if strongest:
            lines.append("")
            lines.append("【🔥 最强信号（非持仓）】")
            lines.append(f"  {format_signal(strongest)}")

        # 最弱信号（P2 优先级）
        if weakest:
            lines.append("")
            lines.append("【⚠️ 最弱信号（非持仓）】")
            lines.append(f"  {format_signal(weakest)}")

        # 告警
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
