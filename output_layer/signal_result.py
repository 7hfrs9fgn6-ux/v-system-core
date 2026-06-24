from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

class FreshnessLevel(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    EXPIRED = "expired"

class SectorSignal(BaseModel):
    name: str
    signal_level: int          # -2 到 4
    drawdown: float            # 当前回撤（%）
    threshold: float           # 黄金坑阈值（%）
    key_driver: Optional[str] = None

class StandardMarketData(BaseModel):
    timestamp: str
    freshness: FreshnessLevel
    sectors: List[SectorSignal]
    index_trend: str           # bull / bear / range
    north_flow: Optional[float] = None

class SignalResult(BaseModel):
    version: str = "V1.1.55"
    analysis_time: str
    overall_suggestion: str    # 偏多 / 偏空 / 震荡
    trust_score: float         # 0.00 ~ 1.00
    health_score: int          # 0 ~ 100
    judge_status: str          # 正常 / 偏低 / 需谨慎
    agent_mode: str            # AI分析 / 规则分析 / AI已暂停
    drift_flag: bool
    signals: List[SectorSignal]
    warnings: List[str]
    phase: str = ""
