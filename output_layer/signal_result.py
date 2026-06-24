# 这是整个V系统的"数据宪法"
# 所有层之间传递数据，都必须严格遵循这个格式

from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

# 1. 数据新鲜度等级（数据适配层必须标注）
class FreshnessLevel(str, Enum):
    FRESH = "fresh"      # 数据在15分钟以内
    STALE = "stale"      # 数据在15分钟~2小时
    EXPIRED = "expired"  # 数据超过2小时（不可靠）

# 2. 单个板块的信号结构
class SectorSignal(BaseModel):
    name: str                     # 板块名（如"电子"）
    signal_level: int             # -3 到 4（核心逻辑层算出）
    drawdown: float               # 当前回撤百分比（如 25.5）
    threshold: float              # 该板块的黄金坑阈值（如 25.0）
    key_driver: Optional[str] = None  # 驱动因素（如有）

# 3. 数据适配层 → 核心逻辑层的输入格式
class StandardMarketData(BaseModel):
    timestamp: str                # 时间戳 "2026-06-25 09:30:00"
    freshness: FreshnessLevel     # 数据新鲜度
    sectors: List[SectorSignal]   # 15个板块的列表
    index_trend: str              # "bull"(牛) / "bear"(熊) / "range"(震荡)
    north_flow: Optional[float] = None  # 北向资金（如有）

# 4. 核心逻辑层 → 输出层的输出格式（这也是L3附录的数据源）
class SignalResult(BaseModel):
    version: str = "V1.1.54"
    analysis_time: str
    overall_suggestion: str       # "偏多" / "震荡" / "偏空"
    trust_score: float            # 0.00 ~ 1.00
    health_score: int             # 0 ~ 100
    judge_status: str             # "正常" / "偏低" / "需谨慎"
    agent_mode: str               # "AI分析" / "规则分析" / "AI已暂停"
    drift_flag: bool              # 是否发生过漂移修正
    signals: List[SectorSignal]   # 15个板块完整信号
    warnings: List[str]           # 告警列表（如"数据陈旧"）
