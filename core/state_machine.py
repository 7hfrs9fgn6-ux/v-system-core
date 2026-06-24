import os
import yaml
from datetime import datetime
from output_layer.signal_result import StandardMarketData, SignalResult, FreshnessLevel

DEFAULT_CONFIG = {
    "trust": {
        "fresh_threshold": 0.70,
        "stale_threshold": 0.50,
        "expired_threshold": 0.30,
        "default_trust": 0.76,
        "penalty_rate": 0.90,
    },
    "health": {
        "base_score": 85,
        "warning_penalty": 10,
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
    def __init__(self, phase: str = "pre", config_path: str = "config.yaml"):
        self.phase = phase
        self.config = self._load_config(config_path)

    def _load_config(self, path: str) -> dict:
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    return yaml.safe_load(f)
            except:
                return DEFAULT_CONFIG
        return DEFAULT_CONFIG

    def run(self, market_data: StandardMarketData) -> SignalResult:
        warnings = []
        trust_score = self.config["trust"]["default_trust"]
        drift_flag = False
        agent_mode = "AI分析"

        # 1. 根据阶段调整信任度
        phase_config = self.config.get("phases", {}).get(self.phase, {})
        trust_adjustment = phase_config.get("trust_adjustment", 1.0)
        trust_score = trust_score * trust_adjustment

        # 2. 新鲜度封顶
        trust_cfg = self.config["trust"]
        if market_data.freshness == FreshnessLevel.FRESH:
            pass
        elif market_data.freshness == FreshnessLevel.STALE:
            trust_score = min(trust_score, trust_cfg["stale_threshold"])
            warnings.append(f"数据源新鲜度偏低（STALE），信任度已封顶至{trust_cfg['stale_threshold']}")
            agent_mode = "规则分析"
        elif market_data.freshness == FreshnessLevel.EXPIRED:
            trust_score = min(trust_score, trust_cfg["expired_threshold"])
            warnings.append(f"⚠️ 数据源已过期，信任度已封顶至{trust_cfg['expired_threshold']}")
            agent_mode = "AI已暂停"

        # 3. 判断状态
        if trust_score >= trust_cfg["fresh_threshold"]:
            judge_status = "正常"
        elif trust_score >= trust_cfg["stale_threshold"]:
            judge_status = "偏低"
        else:
            judge_status = "需谨慎"

        # 4. 综合建议
        avg_signal = sum(s.signal_level for s in market_data.sectors) / len(market_data.sectors)
        if avg_signal > 0.5:
            overall_suggestion = "偏多"
        elif avg_signal < -0.5:
            overall_suggestion = "偏空"
        else:
            overall_suggestion = "震荡"

        # 5. 健康度
        health_cfg = self.config["health"]
        health_score = health_cfg["base_score"]
        if len(warnings) > 0:
            health_score -= len(warnings) * health_cfg["warning_penalty"]
        health_score = max(0, min(100, health_score))

        phase_names = {
            "pre": "盘前预测",
            "intraday_a": "盘中A",
            "intraday_b": "盘中B",
            "post": "盘后复盘",
            "night": "夜间预测"
        }
        phase_note = phase_names.get(self.phase, self.phase)

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
            phase=phase_note
        )
