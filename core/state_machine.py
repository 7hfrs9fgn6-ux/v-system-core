# ============================================================
# 核心逻辑层状态机 V1.1.55（精阶段完整版）
# 集成：信任度累积 + 漂移检测 + 健康度熔断 + 相对强度
# ============================================================

import os
import yaml
import logging
from datetime import datetime
from output_layer.signal_result import StandardMarketData, SignalResult, FreshnessLevel

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "trust": {
        "fresh_threshold": 0.70,
        "stale_threshold": 0.50,
        "expired_threshold": 0.30,
        "default_trust": 0.76,
        "penalty_rate": 0.90,
        "accumulation": {"enabled": True}
    },
    "health": {
        "base_score": 85,
        "warning_penalty": 10,
        "circuit_breaker": {"enabled": True, "threshold": 30, "auto_recover": True, "recover_threshold": 50}
    },
    "phases": {
        "pre": {"trust_adjustment": 0.95},
        "intraday_a": {"trust_adjustment": 1.0},
        "intraday_b": {"trust_adjustment": 1.0},
        "post": {"trust_adjustment": 1.0},
        "night": {"trust_adjustment": 0.90},
    }
}


class VSystemStateMachine:
    """V系统核心状态机（升级版）"""

    def __init__(self, phase: str = "pre", config_path: str = "config.yaml"):
        self.phase = phase
        self.config = self._load_config(config_path)
        self._drift_detector = None
        self._trust_engine = None
        self._circuit_breaker_triggered = False

    def _load_config(self, path: str) -> dict:
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    return yaml.safe_load(f)
            except:
                return DEFAULT_CONFIG
        return DEFAULT_CONFIG

    def _init_engines(self):
        """初始化引擎（延迟加载）"""
        if self._trust_engine is None:
            from core.trust_engine import TrustEngine
            self._trust_engine = TrustEngine(self.config)

        if self._drift_detector is None:
            from core.drift_detector import DriftDetector
            self._drift_detector = DriftDetector(self.config)

    def run(self, market_data: StandardMarketData) -> SignalResult:
        self._init_engines()

        warnings = []
        trust_score = self.config["trust"]["default_trust"]
        drift_flag = False
        agent_mode = "AI分析"

        # ---------- 1. 动态信任度计算 ----------
        if self._trust_engine and self._trust_engine.enabled:
            trust_score = self._trust_engine.calculate_trust(default_trust=trust_score)

        # ---------- 2. 阶段信任度调整 ----------
        phase_config = self.config.get("phases", {}).get(self.phase, {})
        trust_adjustment = phase_config.get("trust_adjustment", 1.0)
        trust_score = trust_score * trust_adjustment

        # ---------- 3. 数据新鲜度封顶 ----------
        trust_cfg = self.config["trust"]
        if market_data.freshness == FreshnessLevel.FRESH:
            pass
        elif market_data.freshness == FreshnessLevel.STALE:
            trust_score = min(trust_score, trust_cfg["stale_threshold"])
            warnings.append(f"数据源新鲜度偏低（STALE），信任度已封顶至{trust_cfg['stale_threshold']}")
            agent_mode = "规则分析"
        elif market_data.freshness == FreshnessLevel.EXPIRED:
            trust_score = min(trust_score, trust_cfg["expired_threshold"])
            warnings.append(f"⚠️ 数据已过期，信任度封顶至{trust_cfg['expired_threshold']}")
            agent_mode = "AI已暂停"

        # ---------- 4. 判断状态 ----------
        if trust_score >= trust_cfg["fresh_threshold"]:
            judge_status = "正常"
        elif trust_score >= trust_cfg["stale_threshold"]:
            judge_status = "偏低"
        else:
            judge_status = "需谨慎"

        # ---------- 5. 综合建议（含相对强度修正） ----------
        avg_signal = sum(s.signal_level for s in market_data.sectors) / len(market_data.sectors)

        # 相对强度修正
        try:
            from core.relative_strength import RelativeStrengthEngine
            rs_engine = RelativeStrengthEngine(self.config)
            if rs_engine.enabled:
                total_adjustment = 0
                for s in market_data.sectors:
                    rs_result = rs_engine.calculate(s.name)
                    total_adjustment += rs_result.get('signal_adjustment', 0)
                avg_adjustment = total_adjustment / len(market_data.sectors)
                avg_signal = avg_signal + avg_adjustment * 0.3  # 30%权重
        except:
            pass

        if avg_signal > 0.5:
            overall_suggestion = "偏多"
        elif avg_signal < -0.5:
            overall_suggestion = "偏空"
        else:
            overall_suggestion = "震荡"

        # ---------- 6. 健康度 ----------
        health_cfg = self.config["health"]
        health_score = health_cfg["base_score"]
        if len(warnings) > 0:
            health_score -= len(warnings) * health_cfg["warning_penalty"]

        # ---------- 7. 健康度熔断 ----------
        cb_config = health_cfg.get("circuit_breaker", {})
        if cb_config.get("enabled", True):
            if health_score < cb_config.get("threshold", 30):
                self._circuit_breaker_triggered = True
                agent_mode = "AI已暂停"
                warnings.append("🔴 健康度低于阈值，已触发熔断保护")
            elif self._circuit_breaker_triggered and health_score >= cb_config.get("recover_threshold", 50):
                self._circuit_breaker_triggered = False
                agent_mode = "AI分析"
                warnings.append("✅ 健康度已恢复，熔断解除")

        health_score = max(0, min(100, health_score))

        # ---------- 8. 计划漂移检测 ----------
        if self._drift_detector and self._drift_detector.enabled:
            # 设置初始目标
            self._drift_detector.set_initial_goal(f"分析{self.phase}阶段市场信号，给出{overall_suggestion}建议")
            self._drift_detector.record_step(f"综合建议生成: {overall_suggestion}")

            # 检测漂移
            is_drift, drift_type, similarity = self._drift_detector.check_drift(
                f"当前{self.phase}阶段，信号{overall_suggestion}，信任度{trust_score:.2f}"
            )
            if is_drift:
                drift_flag = True
                warnings.append(f"⚠️ 计划漂移检测: {drift_type}")
                # 尝试自动修正
                if self._drift_detector.auto_correct():
                    warnings.append("🔄 已执行自动修正")
                else:
                    warnings.append("⚠️ 自动修正失败，继续使用当前结果")

        # ---------- 9. 返回结果 ----------
        phase_names = {
            "pre": "盘前预测",
            "intraday_a": "盘中A",
            "intraday_b": "盘中B",
            "post": "盘后复盘",
            "night": "夜间预测"
        }

        return SignalResult(
            version="V1.1.55",
            analysis_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            overall_suggestion=overall_suggestion,
            trust_score=trust_score,
            health_score=health_score,
            judge_status=judge_status,
            agent_mode=agent_mode,
            drift_flag=drift_flag,
            signals=market_data.sectors,
            warnings=warnings,
            phase=phase_names.get(self.phase, self.phase)
        )

    def get_trust_engine(self):
        """获取信任度引擎（用于外部更新）"""
        self._init_engines()
        return self._trust_engine

    def get_drift_detector(self):
        """获取漂移检测器（用于外部更新）"""
        self._init_engines()
        return self._drift_detector
