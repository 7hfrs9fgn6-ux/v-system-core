#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
相对强度因子计算引擎（P2修复版）
增加重试机制、健壮的列名识别、接口降级
计算板块相对大盘的强度比值
"""

import logging
import time
import pandas as pd
import akshare as ak
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class RelativeStrengthEngine:
    """相对强度因子计算引擎"""

    def __init__(self, config: dict):
        self.config = config.get("relative_strength", {})
        self.enabled = self.config.get("enabled", True)
        self.lookback_days = self.config.get("lookback_days", 60)
        self.threshold = self.config.get("threshold", 1.2)
        self._cache = {}
        self._cache_ttl = 300  # 5分钟缓存

    def _is_cached_valid(self, key: str) -> bool:
        if key in self._cache:
            cached_time, _ = self._cache[key]
            if (datetime.now() - cached_time).total_seconds() < self._cache_ttl:
                return True
        return False

    def _get_cached(self, key: str):
        if key in self._cache:
            _, data = self._cache[key]
            return data
        return None

    def _set_cache(self, key: str, data):
        self._cache[key] = (datetime.now(), data)

    def calculate(self, sector_name: str, max_retries: int = 3) -> Dict:
        """
        计算单个板块的相对强度，带重试
        """
        if not self.enabled:
            return {"strength_ratio": 1.0, "interpretation": "未启用", "signal_adjustment": 0}

        cache_key = sector_name
        if self._is_cached_valid(cache_key):
            return self._get_cached(cache_key)

        for attempt in range(max_retries):
            try:
                result = self._calculate_impl(sector_name)
                if result and result.get('strength_ratio') is not None:
                    self._set_cache(cache_key, result)
                    return result
            except Exception as e:
                logger.warning(f"相对强度计算 {sector_name} 第{attempt+1}次尝试失败: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1 * (attempt + 1))  # 递增等待
                continue

        # 所有重试失败，返回默认值
        logger.warning(f"相对强度计算 {sector_name} 所有重试均失败")
        default = {"strength_ratio": 1.0, "interpretation": "数据不足", "signal_adjustment": 0}
        self._set_cache(cache_key, default)
        return default

    def _calculate_impl(self, sector_name: str) -> Dict:
        """实际计算逻辑"""
        sector_return = self._get_sector_return(sector_name)
        market_return = self._get_market_return()

        if sector_return is None or market_return is None or abs(market_return) < 0.01:
            # 如果市场收益率接近0，无法计算有效比值
            return {
                "strength_ratio": 1.0,
                "interpretation": "数据不足",
                "signal_adjustment": 0,
                "sector_return": sector_return,
                "market_return": market_return
            }

        ratio = sector_return / market_return

        if ratio > 1.2:
            interpretation = "强势"
            adjustment = 1
        elif ratio > 0.8:
            interpretation = "中性"
            adjustment = 0
        else:
            interpretation = "弱势"
            adjustment = -1

        return {
            "strength_ratio": round(ratio, 2),
            "sector_return": round(sector_return, 2),
            "market_return": round(market_return, 2),
            "interpretation": interpretation,
            "signal_adjustment": adjustment
        }

    def _get_sector_return(self, sector_name: str) -> Optional[float]:
        """获取板块指定周期的收益率（健壮列名识别）"""
        try:
            code = self._get_sector_code(sector_name)
            if not code:
                return None

            # 尝试获取行业指数历史数据
            df = None
            try:
                df = ak.index_hist_sw(symbol=code)
            except Exception as e:
                logger.debug(f"AKShare index_hist_sw 失败 ({code}): {e}")
                # 备选：尝试其他接口
                try:
                    df = ak.stock_zh_index_hist(symbol=code, period="daily")
                except:
                    pass

            if df is None or df.empty:
                return None

            # 识别列名（支持中英文）
            date_col = None
            close_col = None
            for c in df.columns:
                if '日' in c or 'date' in c.lower():
                    date_col = c
                if '收' in c or 'close' in c.lower():
                    close_col = c
            if not date_col or not close_col:
                # 尝试使用默认列
                if 'date' in df.columns:
                    date_col = 'date'
                if 'close' in df.columns:
                    close_col = 'close'
            if not date_col or not close_col:
                logger.warning(f"无法识别列名: {df.columns.tolist()}")
                return None

            df[date_col] = pd.to_datetime(df[date_col])
            end_date = datetime.now()
            start_date = end_date - timedelta(days=self.lookback_days)
            df = df[df[date_col] <= end_date]
            if len(df) < 2:
                return None

            start_price = df[close_col].iloc[-min(self.lookback_days, len(df))-1]
            end_price = df[close_col].iloc[-1]
            if start_price == 0:
                return None
            return (end_price - start_price) / start_price * 100

        except Exception as e:
            logger.warning(f"获取板块收益率失败 {sector_name}: {e}")
            return None

    def _get_market_return(self) -> Optional[float]:
        """获取市场（上证指数）指定周期的收益率"""
        try:
            # 获取上证指数
            df = None
            try:
                df = ak.stock_zh_index_daily(symbol="sh000001")
            except Exception as e:
                logger.debug(f"AKShare stock_zh_index_daily 失败: {e}")
                try:
                    df = ak.index_zh_spot()
                    # 如果只能获取实时数据，无法计算历史收益率
                    return None
                except:
                    pass
            if df is None or df.empty:
                return None

            # 识别列名
            date_col = None
            close_col = None
            for c in df.columns:
                if '日' in c or 'date' in c.lower():
                    date_col = c
                if '收' in c or 'close' in c.lower():
                    close_col = c
            if not date_col or not close_col:
                if 'date' in df.columns:
                    date_col = 'date'
                if 'close' in df.columns:
                    close_col = 'close'
            if not date_col or not close_col:
                logger.warning(f"无法识别大盘列名: {df.columns.tolist()}")
                return None

            df[date_col] = pd.to_datetime(df[date_col])
            end_date = datetime.now()
            start_date = end_date - timedelta(days=self.lookback_days)
            df = df[df[date_col] <= end_date]
            if len(df) < 2:
                return None

            start_price = df[close_col].iloc[-min(self.lookback_days, len(df))-1]
            end_price = df[close_col].iloc[-1]
            if start_price == 0:
                return None
            return (end_price - start_price) / start_price * 100

        except Exception as e:
            logger.warning(f"获取大盘收益率失败: {e}")
            return None

    def _get_sector_code(self, sector_name: str) -> Optional[str]:
        """获取板块对应的申万代码"""
        code_map = {
            "电子": "801080",
            "计算机": "801750",
            "通信": "801770",
            "传媒": "801760",
            "医药生物": "801150",
            "食品饮料": "801120",
            "家用电器": "801110",
            "电力设备": "801730",
            "汽车": "801880",
            "国防军工": "801740",
            "银行": "801780",
            "非银金融": "801790",
            "公用事业": "801160",
            "煤炭": "801950",
            "石油石化": "801960",
        }
        return code_map.get(sector_name)

    def batch_calculate(self, sectors: list) -> Dict[str, Dict]:
        """批量计算多个板块的相对强度"""
        results = {}
        for sector in sectors:
            results[sector] = self.calculate(sector)
        return results
