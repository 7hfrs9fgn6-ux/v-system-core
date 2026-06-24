# 模拟数据适配器：假装从API拿数据，实际是写死的测试数据
# 对应 00-mock-data-fetch.yml 和 01-full-analysis.yml

import random
from datetime import datetime
from output_layer.signal_result import StandardMarketData, SectorSignal, FreshnessLevel

# V系统固定的15个板块
SECTOR_NAMES = [
    "电子", "计算机", "通信", "传媒", "医药生物",
    "食品饮料", "家用电器", "电力设备", "汽车", "国防军工",
    "银行", "非银金融", "公用事业", "煤炭", "石油石化"
]

# 各板块的黄金坑回撤阈值（来自简阶段V2.0.2第6.1节映射逻辑）
THRESHOLD_MAP = {
    "电子": 25.0, "计算机": 25.0, "通信": 20.0, "传媒": 25.0, "医药生物": 30.0,
    "食品饮料": 25.0, "家用电器": 18.0, "电力设备": 25.0, "汽车": 25.0, "国防军工": 25.0,
    "银行": 20.0, "非银金融": 20.0, "公用事业": 15.0, "煤炭": 20.0, "石油石化": 20.0
}

class MockDataAdapter:
    """模拟适配器 - 永远返回新鲜数据（用于测试逻辑层）"""
    
    def fetch_all(self) -> StandardMarketData:
        # 生成15个板块的模拟数据
        sectors = []
        for name in SECTOR_NAMES:
            # 随机生成回撤值（15%~35%之间），用来测试阈值触发
            drawdown = round(random.uniform(15.0, 35.0), 1)
            threshold = THRESHOLD_MAP[name]
            
            # 根据回撤是否超过阈值，预判一个信号等级（-3~4）
            # 这里简化：超过阈值给正信号（机会），否则给0或负信号
            if drawdown >= threshold:
                level = random.choice([3, 4])  # 建议关注或强烈建议
            else:
                level = random.choice([0, 1, -1])  # 无信号或弱观察
            
            sectors.append(SectorSignal(
                name=name,
                signal_level=level,
                drawdown=drawdown,
                threshold=threshold,
                key_driver="模拟测试驱动" if level > 0 else None
            ))
        
        # 返回标准化的数据，标记为"新鲜"
        return StandardMarketData(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            freshness=FreshnessLevel.STALE,  # 注意：这里永远给新鲜，后续测试"陈旧"我们再改
            sectors=sectors,
            index_trend=random.choice(["bull", "bear", "range"]),
            north_flow=round(random.uniform(-50, 80), 2)
        )
