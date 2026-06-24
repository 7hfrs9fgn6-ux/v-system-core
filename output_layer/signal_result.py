from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

class FreshnessLevel(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    EXPIRED = "expired"

class SectorSignal(BaseModel):
    name: str
    signal_level: int
    drawdown: float
    threshold: float
    key_driver: Optional[str] = None

class StandardMarketData(BaseModel):
    timestamp: str
    freshness: FreshnessLevel
    sectors: List[SectorSignal]
    index_trend: str
    north_flow: Optional[float] = None

class SignalResult(BaseModel):
    version: str = "V1.1.55"
    analysis_time: str
    overall_suggestion: str
    trust_score: float
    health_score: int
    judge_status: str
    agent_mode: str
    drift_flag: bool
    signals: List[SectorSignal]
    warnings: List[str]
