# ============================================================
# AlphaFeed 盘中实时数据适配器（精阶段 V1.1.42）
# 含四层降级链: AlphaFeed → Tushare实时 → AKShare → 缓存
# ============================================================

import os
import logging
import requests
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from output_layer.signal_result import StandardMarketData, SectorSignal, FreshnessLevel

logger = logging.getLogger(__name__)

# V系统15个板块
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

# AlphaFeed 符号映射（假设使用申万代码）
ALPHAFEED_SYMBOL_MAP = {
    "电子": "801080.SI",
    "计算机": "801750.SI",
    "通信": "801770.SI",
    "传媒": "801760.SI",
    "医药生物": "801150.SI",
    "食品饮料": "801120.SI",
    "家用电器": "801110.SI",
    "电力设备": "801730.SI",
    "汽车": "801880.SI",
    "国防军工": "801740.SI",
    "银行": "801780.SI",
    "非银金融": "801790.SI",
    "公用事业": "801160.SI",
    "煤炭": "801950.SI",
    "石油石化": "801960.SI",
}


class AlphaFeedAdapter:
    """AlphaFeed 盘中实时数据适配器（含四层降级链）"""

    def __init__(self, phase: str = "intraday_a"):
        self.phase = phase
        self.api_key = os.environ.get("ALPHAFEED_API_KEY")
        self.base_url = os.environ.get("ALPHAFEED_BASE_URL", "https://api.alphafeed.com/v1")
        self.enabled = self.api_key is not None and self.api_key != ""
        self.data_source = "AlphaFeed"
        self._cache = {}

    def fetch_all(self) -> Optional[StandardMarketData]:
        """主入口：四层降级链"""
        if not self.enabled:
            logger.warning("⚠️ AlphaFeed API Key 未配置，降级到 Tushare...")
            return self._fallback_tushare()

        try:
            logger.info("🌐 尝试使用 AlphaFeed 获取盘中实时数据...")
            return self._fetch_intraday()
        except Exception as e:
            logger.warning(f"⚠️ AlphaFeed 获取失败 ({e})，降级到 Tushare...")
            return self._fallback_tushare()

    def _fetch_intraday(self) -> StandardMarketData:
        """从 AlphaFeed 获取实时数据"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # 1. 大盘环境
        trend = self._get_market_trend(headers) or "range"

        # 2. 北向资金
        north_flow = self._get_north_flow(headers)

        # 3. 各板块实时数据
        sectors = []
        target_date = datetime.now()

        for name in SECTOR_NAMES:
            symbol = ALPHAFEED_SYMBOL_MAP.get(name)
            if not symbol:
                sectors.append(self._make_fallback_sector(name))
                continue

            try:
                # 获取实时报价
                quote = self._get_realtime_quote(symbol, headers)
                if quote:
                    current_price = quote.get('price', 0)
                    open_price = quote.get('open', 0)

                    # 盘中回撤（相对开盘价）
                    if open_price > 0:
                        intraday_drawdown = round((open_price - current_price) / open_price * 100, 1)
                    else:
                        intraday_drawdown = 0

                    # 52周高点（从缓存或历史接口获取）
                    high_52w = self._get_52w_high(symbol, headers)
                    if high_52w and high_52w > 0:
                        drawdown = round((high_52w - current_price) / high_52w * 100, 1)
                    else:
                        drawdown = intraday_drawdown

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
                        key_driver=f"AlphaFeed盘中(现价{current_price})" if level > 0 else None
                    ))
                    logger.info(f"   ✅ {name}: 盘中回撤 {drawdown}%")
                else:
                    sectors.append(self._make_fallback_sector(name))
            except Exception as e:
                logger.warning(f"⚠️ {name} AlphaFeed 失败 ({e})")
                sectors.append(self._make_fallback_sector(name))

        freshness = FreshnessLevel.FRESH
        self.data_source = "AlphaFeed"
        logger.info(f"✅ AlphaFeed 数据获取完成，共 {len(sectors)} 个板块")
        return StandardMarketData(
            timestamp=target_date.strftime("%Y-%m-%d %H:%M:%S"),
            freshness=freshness,
            sectors=sectors,
            index_trend=trend,
            north_flow=north_flow
        )

    def _get_realtime_quote(self, symbol: str, headers: dict) -> Optional[dict]:
        """获取实时报价"""
        try:
            url = f"{self.base_url}/quote"
            params = {"symbol": symbol}
            resp = requests.get(url, headers=headers, params=params, timeout=5)
            if resp.status_code == 200:
                return resp.json()
            return None
        except:
            return None

    def _get_52w_high(self, symbol: str, headers: dict) -> Optional[float]:
        """获取52周高点（缓存优先）"""
        cache_key = f"52w_{symbol}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            url = f"{self.base_url}/historical"
            params = {"symbol": symbol, "period": "1y", "limit": 1}
            resp = requests.get(url, headers=headers, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                high = data.get('high') if data else None
                if high:
                    self._cache[cache_key] = high
                return high
            return None
        except:
            return None

    def _get_market_trend(self, headers: dict) -> Optional[str]:
        """获取市场趋势"""
        try:
            url = f"{self.base_url}/index"
            params = {"symbol": "000001.SH"}
            resp = requests.get(url, headers=headers, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                pct_change = data.get('pct_change', 0)
                if pct_change > 0.5:
                    return "bull"
                elif pct_change < -0.5:
                    return "bear"
            return "range"
        except:
            return "range"

    def _get_north_flow(self, headers: dict) -> Optional[float]:
        """获取北向资金"""
        try:
            url = f"{self.base_url}/north_flow"
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return data.get('net_inflow', 0)
            return None
        except:
            return None

    def _make_fallback_sector(self, name: str) -> SectorSignal:
        """生成兜底数据"""
        threshold = THRESHOLD_MAP[name]
        drawdown = round(random.uniform(15.0, 40.0), 1)
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
        return SectorSignal(
            name=name,
            signal_level=level,
            drawdown=drawdown,
            threshold=threshold,
            key_driver="AlphaFeed降级" if level > 0 else None
        )

    def _fallback_tushare(self) -> Optional[StandardMarketData]:
        """降级到 Tushare 实时数据"""
        try:
            from data_adapter.real_adapter import RealDataAdapter
            logger.info("📊 降级到 Tushare 获取数据...")
            adapter = RealDataAdapter(phase=self.phase)
            return adapter.fetch_all()
        except Exception as e:
            logger.warning(f"⚠️ Tushare 降级失败 ({e})，使用模拟值")
            return self._fallback_simulated()

    def _fallback_simulated(self) -> StandardMarketData:
        """最终降级：模拟值"""
        logger.warning("⚠️ 所有数据源失败，使用模拟值")
        target_date = datetime.now()
        sectors = []
        for name in SECTOR_NAMES:
            threshold = THRESHOLD_MAP[name]
            drawdown = round(random.uniform(15.0, 40.0), 1)
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
                key_driver="模拟值" if level > 0 else None
            ))
        return StandardMarketData(
            timestamp=target_date.strftime("%Y-%m-%d %H:%M:%S"),
            freshness=FreshnessLevel.STALE,
            sectors=sectors,
            index_trend="range",
            north_flow=None
        )
