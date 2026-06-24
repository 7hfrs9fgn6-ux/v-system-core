# ============================================================
# AlphaFeed 盘中实时数据适配器
# 功能：获取盘中实时报价、分时数据、盘中回撤
# 对应精阶段 V1.1.42 多源数据矩阵
# ============================================================

import os
import logging
import requests
from datetime import datetime
from typing import List, Dict, Optional
from output_layer.signal_result import StandardMarketData, SectorSignal, FreshnessLevel

logger = logging.getLogger(__name__)

# V系统15个板块对应的 AlphaFeed 符号映射（需根据实际API调整）
# 假设 AlphaFeed 使用申万行业指数符号
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

THRESHOLD_MAP = {
    "电子": 25.0, "计算机": 25.0, "通信": 20.0, "传媒": 25.0, "医药生物": 30.0,
    "食品饮料": 25.0, "家用电器": 18.0, "电力设备": 25.0, "汽车": 25.0, "国防军工": 25.0,
    "银行": 20.0, "非银金融": 20.0, "公用事业": 15.0, "煤炭": 20.0, "石油石化": 20.0
}


class AlphaFeedAdapter:
    """
    AlphaFeed 盘中实时数据适配器
    用于 intraday_a 和 intraday_b 阶段获取实时数据
    """

    def __init__(self, phase: str = "intraday_a"):
        self.phase = phase
        self.api_key = os.environ.get("ALPHAFEED_API_KEY")
        self.base_url = os.environ.get("ALPHAFEED_BASE_URL", "https://api.alphafeed.com/v1")
        self.enabled = self.api_key is not None and self.api_key != ""
        self.data_source = "AlphaFeed" if self.enabled else "AlphaFeed(未启用)"

    def fetch_all(self) -> Optional[StandardMarketData]:
        """获取所有板块的盘中实时数据"""
        if not self.enabled:
            logger.warning("⚠️ AlphaFeed API Key 未配置，跳过")
            return None

        try:
            logger.info("🌐 尝试使用 AlphaFeed 获取盘中实时数据...")
            return self._fetch_intraday()
        except Exception as e:
            logger.warning(f"⚠️ AlphaFeed 获取失败 ({e})")
            return None

    def _fetch_intraday(self) -> StandardMarketData:
        """获取盘中实时数据"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        sectors = []
        now = datetime.now()

        for name in ALPHAFEED_SYMBOL_MAP:
            symbol = ALPHAFEED_SYMBOL_MAP[name]
            try:
                # 获取实时报价
                quote = self._get_realtime_quote(symbol, headers)
                if quote:
                    # 获取当日开盘价计算盘中回撤
                    open_price = quote.get('open', 0)
                    current_price = quote.get('price', 0)
                    if open_price > 0:
                        intraday_drawdown = round((open_price - current_price) / open_price * 100, 1)
                    else:
                        intraday_drawdown = 0

                    # 获取52周数据（从缓存或历史接口）
                    high_52w = self._get_52w_high(symbol, headers) or current_price
                    if high_52w > 0:
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
                    logger.warning(f"⚠️ {name} 无实时数据")
                    # 使用模拟值（保持系统完整性）
                    drawdown = 0.0
                    threshold = THRESHOLD_MAP[name]
                    sectors.append(SectorSignal(
                        name=name,
                        signal_level=0,
                        drawdown=0,
                        threshold=threshold,
                        key_driver=None
                    ))
            except Exception as e:
                logger.warning(f"⚠️ {name} 获取失败 ({e})")
                # 降级
                sectors.append(SectorSignal(
                    name=name,
                    signal_level=0,
                    drawdown=0,
                    threshold=THRESHOLD_MAP[name],
                    key_driver=None
                ))

        # 大盘环境（盘中用实时涨跌幅）
        trend = self._get_market_trend(headers) or "range"

        return StandardMarketData(
            timestamp=now.strftime("%Y-%m-%d %H:%M:%S"),
            freshness=FreshnessLevel.FRESH,  # 盘中数据算新鲜
            sectors=sectors,
            index_trend=trend,
            north_flow=self._get_north_flow(headers)
        )

    def _get_realtime_quote(self, symbol: str, headers: dict) -> Optional[dict]:
        """获取单个符号的实时报价"""
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
        """获取52周最高价"""
        try:
            url = f"{self.base_url}/historical"
            params = {"symbol": symbol, "period": "1y", "limit": 1}
            resp = requests.get(url, headers=headers, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data and 'high' in data:
                    return data['high']
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
                else:
                    return "range"
            return None
        except:
            return None

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
