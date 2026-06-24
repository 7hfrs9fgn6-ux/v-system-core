# 模拟数据适配器（用于测试）
import random
from datetime import datetime
from output_layer.signal_result import StandardMarketData, SectorSignal, FreshnessLevel

SECTOR_NAMES = [
    "电子", "计算机", "通信", "传媒", "医药生物",
    "食品饮料", "家用电器", "电力设备", "汽车", "国防军工",
    "银行", "非银金融", "公用事业", "煤炭", "石油石化"
]

THRESHOLD_MAP = {
    "电子": 25.0, "计算机": 25.0, "通信": 20.0, "传媒": 25.0, "医药生物": 30.0,
    "食品饮料": 25.0, "家用电器": 18.0, "电力设备": 25.0, "汽车": 25.0, "国防军工": 25.0,
    "银行": 20.0, "非银金融": 20.0, "公用事业": 15.0, "煤炭": 20.0, "石油石化": 20.0
}

class MockDataAdapter:
    def fetch_all(self) -> StandardMarketData:
        sectors = []
        for name in SECTOR_NAMES:
            drawdown = round(random.uniform(15.0, 40.0), 1)
            threshold = THRESHOLD_MAP[name]
            excess = drawdown - threshold
            if excess >= 10:
                level = 4
            elif excess >= 5:
                level = 3
            elif excess >= 0:
                level = 2
            elif excess >= -5:
                level = 1
            elif excess >= -10:
                level = -1
            else:
                level = -2
            sectors.append(SectorSignal(
                name=name,
                signal_level=level,
                drawdown=drawdown,
                threshold=threshold,
                key_driver="模拟数据" if level > 0 else None
            ))
        return StandardMarketData(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            freshness=FreshnessLevel.FRESH,
            sectors=sectors,
            index_trend=random.choice(["bull", "bear", "range"]),
            north_flow=round(random.uniform(-50, 80), 2)
        )
