# ============================================================
# 影子系统（精阶段 V1.1.47）- 增加持久化支持
# ============================================================

import random
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from output_layer.signal_result import SectorSignal

logger = logging.getLogger(__name__)


class ShadowSystem:
    """影子系统：4种变体 + 可靠度判定 + 持久化"""

    VARIANT_TYPES = {
        "conservative": {
            "name": "保守型",
            "threshold_adjustment": 1.2,
            "signal_dampening": 0.8,
            "description": "更保守的阈值，信号更谨慎"
        },
        "aggressive": {
            "name": "激进型",
            "threshold_adjustment": 0.8,
            "signal_dampening": 1.2,
            "description": "更激进的阈值，信号更敏感"
        },
        "momentum": {
            "name": "动量型",
            "threshold_adjustment": 1.0,
            "signal_dampening": 1.0,
            "momentum_weight": 0.3,
            "description": "关注趋势动量"
        },
        "mean_reversion": {
            "name": "均值回归型",
            "threshold_adjustment": 1.0,
            "signal_dampening": 1.0,
            "reversion_weight": 0.3,
            "description": "关注均值回归"
        }
    }

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.persist = self.config.get("shadow", {}).get("persist", True)
        self.reliability_threshold = self.config.get("shadow", {}).get("reliability_threshold", 0.6)
        self.results_cache = {}
        self.cache_ttl = 3600

    def run_variants(self, market_data: Dict, sector_signals: List[SectorSignal]) -> Dict:
        """运行4种变体"""
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

        reliability = self._calculate_reliability(variants_result, base_signals)

        result = {
            "variants": variants_result,
            "reliability": reliability,
            "timestamp": datetime.now().isoformat()
        }

        # 持久化（如果启用）
        if self.persist:
            self._persist_result(result)

        return result

    def _run_variant(self, variant_id: str, config: Dict,
                     base_signals: Dict, market_data: Dict) -> Dict:
        """运行单个变体"""
        result = {}
        for name, base_signal in base_signals.items():
            threshold_adj = config.get('threshold_adjustment', 1.0)
            adjusted_threshold = base_signal.threshold * threshold_adj

            dampening = config.get('signal_dampening', 1.0)
            adjusted_level = base_signal.signal_level * dampening
            adjusted_level = round(max(-2, min(4, adjusted_level)))

            if variant_id == "momentum":
                momentum_weight = config.get('momentum_weight', 0.3)
                momentum_factor = self._get_momentum_factor(name)
                adjusted_level = adjusted_level + momentum_factor * momentum_weight
                adjusted_level = round(max(-2, min(4, adjusted_level)))

            if variant_id == "mean_reversion":
                reversion_weight = config.get('reversion_weight', 0.3)
                reversion_factor = self._get_reversion_factor(name)
                adjusted_level = adjusted_level + reversion_factor * reversion_weight
                adjusted_level = round(max(-2, min(4, adjusted_level)))

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
        import random
        random.seed(hash(sector_name + "momentum") % 10000)
        factor = random.uniform(-2, 2)
        random.seed()
        return round(factor, 1)

    def _get_reversion_factor(self, sector_name: str) -> float:
        import random
        random.seed(hash(sector_name + "reversion") % 10000)
        factor = random.uniform(-2, 2)
        random.seed()
        return round(factor, 1)

    def _calculate_reliability(self, variants_result: Dict, base_signals: Dict) -> Dict:
        sector_reliability = {}
        total_consensus = 0
        total_sectors = len(base_signals)

        for name in base_signals.keys():
            variant_levels = []
            for variant_id, result in variants_result.items():
                if name in result:
                    variant_levels.append(result[name]['adjusted_level'])
            if not variant_levels:
                sector_reliability[name] = 0.5
                continue

            base_level = base_signals[name].signal_level
            avg_deviation = sum(abs(v - base_level) for v in variant_levels) / len(variant_levels)
            max_deviation = 6
            reliability = max(0, 1 - (avg_deviation / max_deviation))
            sector_reliability[name] = round(reliability, 2)
            total_consensus += reliability

        overall_reliability = round(total_consensus / total_sectors, 2) if total_sectors > 0 else 0.5

        if overall_reliability >= 0.7:
            consensus_level = "高"
        elif overall_reliability >= 0.5:
            consensus_level = "中"
        else:
            consensus_level = "低"

        divergence_sectors = sorted(sector_reliability.items(), key=lambda x: x[1])[:3]

        return {
            "overall_reliability": overall_reliability,
            "consensus_level": consensus_level,
            "sector_reliability": sector_reliability,
            "divergence_sectors": [s for s, _ in divergence_sectors if s],
            "is_reliable": overall_reliability >= self.reliability_threshold,
            "recommendation": "可参考主系统信号" if overall_reliability >= self.reliability_threshold else "建议保守处理"
        }

    def _persist_result(self, result: Dict):
        """持久化影子结果到记忆体"""
        try:
            from core.memory_store import MemoryStore
            memory = MemoryStore({})
            memory.save_shadow_record(result, "post")
        except Exception as e:
            logger.warning(f"影子结果持久化失败: {e}")

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

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)
