# 核心逻辑层状态机（V1.1.55 可配置版）
# 支持从 config.yaml 读取阈值参数

import os
import yaml
from datetime import datetime
from output_layer.signal_result import StandardMarketData, SignalResult, FreshnessLevel

# 默认配置（如果 config.yaml 不存在）
DEFAULT_CONFIG = {
    "trust": {
        "fresh_threshold": 0.70,      # 新鲜数据信任度下限
        "stale_threshold": 0.50,      # 陈旧数据信任度上限
        "expired_threshold": 0.30,    # 过期数据信任度上限
        "default_trust": 0.76,        # 默认初始信任度
        "penalty_rate": 0.90,         # 安全违规惩罚系数
    },
    "health": {
        "base_score": 85,
        "warning_penalty": 10,
    }
}


class VSystemStateMachine:
    """V系统核心状态机 - 可配置版"""

    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)

    def _load_config(self, path: str) -> dict:
        """加载配置文件，不存在则使用默认"""
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

        # ---------- 关键裁决1：新鲜度封顶 ----------
        trust_cfg = self.config["trust"]
        if market_data.freshness == FreshnessLevel.FRESH:
            pass  # 信任度保持不变
        elif market_data.freshness == FreshnessLevel.STALE:
            trust_score = min(trust_score, trust_cfg["stale_threshold"])
            warnings.append(f"数据源新鲜度偏低（STALE），信任度已封顶至{trust_cfg['stale_threshold']}")
            agent_mode = "规则分析"
        elif market_data.freshness == FreshnessLevel.EXPIRED:
            trust_score = min(trust_score, trust_cfg["expired_threshold"])
            warnings.append(f"⚠️ 数据源已过期（EXPIRED），信任度已封顶至{trust_cfg['expired_threshold']}，请勿据此操作")
            agent_mode = "AI已暂停"

        # ---------- 关键裁决2：判断状态映射 ----------
        if trust_score >= trust_cfg["fresh_threshold"]:
            judge_status = "正常"
        elif trust_score >= trust_cfg["stale_threshold"]:
            judge_status = "偏低"
        else:
            judge_status = "需谨慎"

        # ---------- 关键裁决3：综合建议 ----------
        avg_signal = sum(s.signal_level for s in market_data.sectors) / len(market_data.sectors)
        if avg_signal > 0.5:
            overall_suggestion = "偏多"
        elif avg_signal < -0.5:
            overall_suggestion = "偏空"
        else:
            overall_suggestion = "震荡"

        # ---------- 关键裁决4：健康度 ----------
        health_cfg = self.config["health"]
        health_score = health_cfg["base_score"]
        if len(warnings) > 0:
            health_score -= len(warnings) * health_cfg["warning_penalty"]
        health_score = max(0, min(100, health_score))

        return SignalResult(
            version="V1.1.55 (可配置)",
            analysis_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            overall_suggestion=overall_suggestion,
            trust_score=trust_score,
            health_score=health_score,
            judge_status=judge_status,
            agent_mode=agent_mode,
            drift_flag=drift_flag,
            signals=market_data.sectors,
            warnings=warnings
        )
