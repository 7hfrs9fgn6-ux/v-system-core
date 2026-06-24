# ============================================================
# 影子系统 - 4种变体 + 可靠度判定
# 对应精阶段 V1.1.47 影子系统与记忆体协同升级
# ============================================================

import random
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from output_layer.signal_result import SectorSignal

logger = logging.getLogger(__name__)


class ShadowSystem:
    """
    影子系统：运行4种变体策略，对比主系统结果
    用于评估主系统的稳定性和可靠性
    """

    # 4种变体定义
    VARIANT_TYPES = {
        "conservative": {
            "name": "保守型",
            "threshold_adjustment": 1.2,  # 阈值上浮20%
            "signal_dampening": 0.8,       # 信号等级打折
            "description": "更保守的阈值，信号更谨慎"
        },
        "aggressive": {
            "name": "激进型",
            "threshold_adjustment": 0.8,   # 阈值下降20%
            "signal_dampening": 1.2,       # 信号等级放大
            "description": "更激进的阈值，信号更敏感"
        },
        "momentum": {
            "name": "动量型",
            "threshold_adjustment": 1.0,
            "signal_dampening": 1.0,
            "momentum_weight": 0.3,        # 动量因子权重
            "description": "关注趋势动量"
        },
        "mean_reversion": {
            "name": "均值回归型",
            "threshold_adjustment": 1.0,
            "signal_dampening": 1.0,
            "reversion_weight": 0.3,       # 均值回归权重
            "description": "关注均值回归"
        }
    }

    def __init__(self):
        self.results_cache = {}
        self.cache_ttl = 3600
        self.reliability_threshold = 0.6   # 可靠度阈值

    def run_variants(self, market_data: Dict, sector_signals: List[SectorSignal]) -> Dict:
        """
        运行4种变体，返回各变体的信号结果
        """
        base_signals = {s.name: s for s in sector_signals}
        variants_result = {}

        for variant_id, config in self.VARIANT_TYPES.items():
            variant_signals = self._run_variant(
                variant_id,
                config,
                base_signals,
                market_data
            )
            variants_result[variant_id] = variant_signals

        # 计算可靠度
        reliability = self._calculate_reliability(variants_result, base_signals)

        return {
            "variants": variants_result,
            "reliability": reliability,
            "timestamp": datetime.now().isoformat()
        }

    def _run_variant(self, variant_id: str, config: Dict,
                     base_signals: Dict, market_data: Dict) -> Dict:
        """运行单个变体"""
        result = {}

        for name, base_signal in base_signals.items():
            # 应用阈值调整
            threshold_adj = config.get('threshold_adjustment', 1.0)
            adjusted_threshold = base_signal.threshold * threshold_adj

            # 应用信号打折
            dampening = config.get('signal_dampening', 1.0)
            adjusted_level = base_signal.signal_level * dampening
            adjusted_level = round(adjusted_level)

            # 限幅到 -2 ~ 4
            adjusted_level = max(-2, min(4, adjusted_level))

            # 动量或均值回归调整
            if variant_id == "momentum":
                momentum_weight = config.get('momentum_weight', 0.3)
                # 模拟动量因子
                momentum_factor = self._get_momentum_factor(name)
                adjusted_level = adjusted_level + momentum_factor * momentum_weight
                adjusted_level = round(max(-2, min(4, adjusted_level)))

            if variant_id == "mean_reversion":
                reversion_weight = config.get('reversion_weight', 0.3)
                # 模拟均值回归因子
                reversion_factor = self._get_reversion_factor(name)
                adjusted_level = adjusted_level + reversion_factor * reversion_weight
                adjusted_level = round(max(-2, min(4, adjusted_level)))

            # 调整后的回撤（用于展示）
            adjusted_drawdown = base_signal.drawdown * (1 + (threshold_adj - 1) * 0.5)

            result[name] = {
                "original_level": base_signal.signal_level,
                "adjusted_level": adjusted_level,
                "original_threshold": base_signal.threshold,
                "adjusted_threshold": round(adjusted_threshold, 1),
                "drawdown": round(adjusted_drawdown, 1),
                "signal_diff": adjusted_level - base_signal.signal_level
            }

        return result

    def _get_momentum_factor(self, sector_name: str) -> float:
        """获取动量因子值（模拟）"""
        # 实际需要计算近期涨跌幅动量
        import random
        random.seed(hash(sector_name + "momentum") % 10000)
        factor = random.uniform(-2, 2)
        random.seed()
        return round(factor, 1)

    def _get_reversion_factor(self, sector_name: str) -> float:
        """获取均值回归因子值（模拟）"""
        import random
        random.seed(hash(sector_name + "reversion") % 10000)
        factor = random.uniform(-2, 2)
        random.seed()
        return round(factor, 1)

    def _calculate_reliability(self, variants_result: Dict,
                               base_signals: Dict) -> Dict:
        """
        计算影子系统可靠度
        返回：整体可靠度、各板块可靠度、分歧度
        """
        sector_reliability = {}
        total_consensus = 0
        total_sectors = len(base_signals)

        for name in base_signals.keys():
            # 收集所有变体对该板块的信号
            variant_levels = []
            for variant_id, result in variants_result.items():
                if name in result:
                    variant_levels.append(result[name]['adjusted_level'])

            if not variant_levels:
                sector_reliability[name] = 0.5
                continue

            base_level = base_signals[name].signal_level

            # 计算变体与主系统的平均偏差
            avg_deviation = sum(abs(v - base_level) for v in variant_levels) / len(variant_levels)

            # 可靠度 = 1 - 平均偏差/最大可能偏差
            max_deviation = 6  # -2到4的范围
            reliability = max(0, 1 - (avg_deviation / max_deviation))
            sector_reliability[name] = round(reliability, 2)

            total_consensus += reliability

        # 整体可靠度
        overall_reliability = round(total_consensus / total_sectors, 2) if total_sectors > 0 else 0.5

        # 判断分歧度
        if overall_reliability >= 0.7:
            consensus_level = "高"  # 一致性强
        elif overall_reliability >= 0.5:
            consensus_level = "中"  # 存在分歧
        else:
            consensus_level = "低"  # 分歧严重

        # 找出分歧最大的板块
        divergence_sectors = sorted(
            sector_reliability.items(),
            key=lambda x: x[1]
        )[:3]

        return {
            "overall_reliability": overall_reliability,
            "consensus_level": consensus_level,
            "sector_reliability": sector_reliability,
            "divergence_sectors": [s for s, _ in divergence_sectors if s],
            "is_reliable": overall_reliability >= self.reliability_threshold,
            "recommendation": "可参考主系统信号" if overall_reliability >= self.reliability_threshold else "建议保守处理"
        }

    def get_shadow_report(self, result: Dict) -> str:
        """生成影子系统报告"""
        lines = []
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("👻 影子系统运行报告")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")

        reliability = result.get('reliability', {})
        lines.append(f"【整体可靠度】{reliability.get('overall_reliability', 0):.2%}")
        lines.append(f"【共识水平】{reliability.get('consensus_level', '未知')}")
        lines.append(f"【可靠判定】{'✅ 可信' if reliability.get('is_reliable', False) else '⚠️ 建议谨慎'}")

        divergence = reliability.get('divergence_sectors', [])
        if divergence:
            lines.append(f"【分歧板块】{', '.join(divergence)}")

        lines.append("")
        lines.append("【各变体信号示例】")
        variants = result.get('variants', {})
        sample_sector = list(reliability.get('sector_reliability', {}).keys())[:3]
        for sector in sample_sector:
            lines.append(f"  {sector}:")
            for vid, vdata in variants.items():
                if sector in vdata:
                    level = vdata[sector]['adjusted_level']
                    lines.append(f"    {self.VARIANT_TYPES[vid]['name']}: {level}")
            lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)
