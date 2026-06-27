# output_layer/signal_result.py
# V系统数据契约 - 支持所有模块的数据传递

from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from enum import Enum


class FreshnessLevel(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    EXPIRED = "expired"


class SectorSignal(BaseModel):
    """单个板块的信号数据"""
    name: str
    signal_level: int  # -2 ~ 4
    drawdown: float
    threshold: float
    key_driver: Optional[str] = None


class StandardMarketData(BaseModel):
    """数据适配层 → 核心逻辑层的输入"""
    timestamp: str
    freshness: FreshnessLevel
    sectors: List[SectorSignal]
    index_trend: str  # bull / bear / range
    north_flow: Optional[float] = None


class SignalResult(BaseModel):
    """核心逻辑层 → 输出层的输出（L3附录的数据源）"""
    # 核心字段
    version: str = "V1.1.55"
    analysis_time: str
    overall_suggestion: str  # 偏多 / 偏空 / 震荡
    trust_score: float       # 0.00 ~ 1.00
    health_score: int        # 0 ~ 100
    judge_status: str        # 正常 / 偏低 / 需谨慎
    agent_mode: str          # AI分析 / 规则分析 / AI已暂停
    drift_flag: bool
    signals: List[SectorSignal]
    warnings: List[str]
    phase: str = ""

    # 扩展字段（可选，用于传递额外数据）
    sentiment: Optional[Dict[str, Any]] = None          # 消息面烈度评分
    shadow: Optional[Dict[str, Any]] = None             # 影子系统结果
    relative_strength: Optional[Dict[str, Any]] = None  # 相对强度
    agent_analysis: Optional[Dict[str, Any]] = None     # Agent研报分析

    # 动态附加字段（用于推送展示，不参与Pydantic验证）
    # 使用 Pydantic 的 Extra 允许额外字段，但为了安全，我们显式声明为可选
    _index_data: Optional[Dict] = None
    _macro_data: Optional[Dict] = None
    _indices: Optional[Dict] = None
    _market_stats: Optional[Dict] = None
    _sector_flow: Optional[Dict] = None

    class Config:
        # 允许任意额外字段，以便在运行时动态添加属性
        extra = "allow"
