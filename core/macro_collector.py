#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观数据采集模块（P1阶段原始版）
不包含缓存持久化，仅简单采集
"""

import logging
import time
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class MacroCollector:
    """宏观数据采集器（P1原始版）"""

    def __init__(self):
        self._cache = {}
        self._cache_ttl = 300  # 5分钟内存缓存

    def _is_cached_valid(self, key: str) -> bool:
        if key in self._cache:
            cached_time, _ = self._cache[key]
            if (datetime.now() - cached_time).total_seconds() < self._cache_ttl:
                return True
        return False

    def _get_cached(self, key: str) -> Any:
        if key in self._cache:
            _, data = self._cache[key]
            return data
        return None

    def _set_cache(self, key: str, data: Any):
        self._cache[key] = (datetime.now(), data)

    # ============================================================
    # 各数据源获取（直接调用AKShare，无重试）
    # ============================================================
    def get_us_market(self) -> Dict:
        cache_key = "us_market"
        if self._is_cached_valid(cache_key):
            return self._get_cached(cache_key)

        result = {
            "indices": {},
            "semiconductor": {},
            "tech_giants": {},
            "data_source": "AKShare",
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak
            df = ak.stock_us_spot()
            if df is None or df.empty:
                return result

            # 指数
            index_keywords = ["道琼斯", "纳斯达克", "标普500"]
            for keyword in index_keywords:
                matched = df[df['名称'].str.contains(keyword, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][keyword] = {
                        "name": keyword,
                        "price": self._safe_float(row.get('最新价')),
                        "pct_change": self._safe_float(row.get('涨跌幅'))
                    }

            # 费城半导体
            sem_matched = df[df['名称'].str.contains("费城半导体", na=False)]
            if not sem_matched.empty:
                row = sem_matched.iloc[0]
                result["semiconductor"] = {
                    "name": "费城半导体",
                    "price": self._safe_float(row.get('最新价')),
                    "pct_change": self._safe_float(row.get('涨跌幅'))
                }

            # 科技巨头
            tech_giants = ["苹果", "英伟达", "微软", "谷歌", "亚马逊", "Meta", "特斯拉", "美光", "英特尔", "AMD"]
            for giant in tech_giants:
                matched = df[df['名称'].str.contains(giant, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["tech_giants"][giant] = {
                        "name": giant,
                        "price": self._safe_float(row.get('最新价')),
                        "pct_change": self._safe_float(row.get('涨跌幅'))
                    }

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            logger.warning(f"美股数据获取异常: {e}")
            return result

    def get_asia_market(self) -> Dict:
        cache_key = "asia_market"
        if self._is_cached_valid(cache_key):
            return self._get_cached(cache_key)

        result = {
            "indices": {},
            "data_source": "AKShare",
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak
            df = ak.stock_zh_index_spot()
            if df is None or df.empty:
                return result

            asia_map = {
                "日经225": "N225",
                "韩国KOSPI": "KOSPI",
                "恒生指数": "HSI",
                "台湾加权": "TWII"
            }

            for name, code in asia_map.items():
                matched = df[df['名称'].str.contains(name, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][code] = {
                        "name": name,
                        "price": self._safe_float(row.get('最新价')),
                        "pct_change": self._safe_float(row.get('涨跌幅'))
                    }

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            logger.warning(f"亚太数据获取异常: {e}")
            return result

    def get_europe_market(self) -> Dict:
        cache_key = "europe_market"
        if self._is_cached_valid(cache_key):
            return self._get_cached(cache_key)

        result = {
            "indices": {},
            "data_source": "AKShare",
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak
            df = ak.stock_zh_index_spot()
            if df is None or df.empty:
                return result

            europe_map = {
                "德国DAX": "GDAXI",
                "英国富时": "FTSE",
                "法国CAC": "FCHI"
            }

            for name, code in europe_map.items():
                matched = df[df['名称'].str.contains(name, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][code] = {
                        "name": name,
                        "price": self._safe_float(row.get('最新价')),
                        "pct_change": self._safe_float(row.get('涨跌幅'))
                    }

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            logger.warning(f"欧洲数据获取异常: {e}")
            return result

    def get_commodities(self) -> Dict:
        cache_key = "commodities"
        if self._is_cached_valid(cache_key):
            return self._get_cached(cache_key)

        result = {
            "oil": {},
            "gold": {},
            "data_source": "AKShare",
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak

            try:
                oil_df = ak.futures_foreign_main_sina(symbol="CL")
                if oil_df is not None and not oil_df.empty:
                    latest = oil_df.iloc[-1]
                    result["oil"]["WTI"] = {
                        "name": "WTI",
                        "price": self._safe_float(latest.get('最新价')),
                        "pct_change": self._safe_float(latest.get('涨跌幅'))
                    }
            except:
                pass

            try:
                oil_df_b = ak.futures_foreign_main_sina(symbol="B")
                if oil_df_b is not None and not oil_df_b.empty:
                    latest = oil_df_b.iloc[-1]
                    result["oil"]["Brent"] = {
                        "name": "布伦特",
                        "price": self._safe_float(latest.get('最新价')),
                        "pct_change": self._safe_float(latest.get('涨跌幅'))
                    }
            except:
                pass

            try:
                gold_df = ak.futures_foreign_main_sina(symbol="GC")
                if gold_df is not None and not gold_df.empty:
                    latest = gold_df.iloc[-1]
                    result["gold"] = {
                        "price": self._safe_float(latest.get('最新价')),
                        "pct_change": self._safe_float(latest.get('涨跌幅'))
                    }
            except:
                pass

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            logger.warning(f"大宗商品获取异常: {e}")
            return result

    def get_forex(self) -> Dict:
        cache_key = "forex"
        if self._is_cached_valid(cache_key):
            return self._get_cached(cache_key)

        result = {
            "usd_cny": {},
            "data_source": "AKShare",
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak

            try:
                cny_df = ak.currency_rates()
                if cny_df is not None and not cny_df.empty:
                    matched = cny_df[cny_df['货币名称'].str.contains('美元', na=False)]
                    if not matched.empty:
                        row = matched.iloc[0]
                        result["usd_cny"]["onshore"] = self._safe_float(row.get('最新价'))
                        result["usd_cny"]["pct_change"] = self._safe_float(row.get('涨跌幅'))
            except:
                pass

            try:
                mid_df = ak.currency_rates_central()
                if mid_df is not None and not mid_df.empty:
                    matched = mid_df[mid_df['货币名称'].str.contains('美元', na=False)]
                    if not matched.empty:
                        row = matched.iloc[0]
                        result["usd_cny"]["central"] = self._safe_float(row.get('最新价'))
            except:
                pass

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            logger.warning(f"汇率获取异常: {e}")
            return result

    def get_a50_futures(self) -> Dict:
        cache_key = "a50_futures"
        if self._is_cached_valid(cache_key):
            return self._get_cached(cache_key)

        result = {
            "price": None,
            "pct_change": None,
            "data_source": "AKShare",
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak

            try:
                a50_df = ak.futures_foreign_main_sina(symbol="A50")
                if a50_df is not None and not a50_df.empty:
                    latest = a50_df.iloc[-1]
                    result["price"] = self._safe_float(latest.get('最新价'))
                    result["pct_change"] = self._safe_float(latest.get('涨跌幅'))
            except:
                pass

            if result["price"] is None:
                try:
                    a50_df2 = ak.futures_main_sina(symbol="A50")
                    if a50_df2 is not None and not a50_df2.empty:
                        latest = a50_df2.iloc[-1]
                        result["price"] = self._safe_float(latest.get('最新价'))
                        result["pct_change"] = self._safe_float(latest.get('涨跌幅'))
                except:
                    pass

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            logger.warning(f"A50期货获取异常: {e}")
            return result

    def get_macro_snapshot(self) -> Dict:
        cache_key = "macro_snapshot"
        if self._is_cached_valid(cache_key):
            return self._get_cached(cache_key)

        result = {
            "us_market": self.get_us_market(),
            "asia_market": self.get_asia_market(),
            "europe_market": self.get_europe_market(),
            "commodities": self.get_commodities(),
            "forex": self.get_forex(),
            "a50_futures": self.get_a50_futures(),
            "timestamp": datetime.now().isoformat()
        }

        self._set_cache(cache_key, result)
        return result

    def format_for_push(self) -> Dict:
        snapshot = self.get_macro_snapshot()
        formatted = {
            "us_market": self._format_us_market(snapshot.get("us_market", {})),
            "asia_market": self._format_asia_market(snapshot.get("asia_market", {})),
            "europe_market": self._format_europe_market(snapshot.get("europe_market", {})),
            "commodities": self._format_commodities(snapshot.get("commodities", {})),
            "forex": self._format_forex(snapshot.get("forex", {})),
            "a50_futures": snapshot.get("a50_futures", {}),
            "timestamp": snapshot.get("timestamp", "")
        }
        return formatted

    # ---------- 格式化辅助 ----------
    def _format_us_market(self, data):
        result = {"indices": [], "tech_giants": [], "semiconductor": None}
        for name, idx in data.get("indices", {}).items():
            if idx.get("price"):
                result["indices"].append(idx)
        sem = data.get("semiconductor")
        if sem and sem.get("price"):
            result["semiconductor"] = sem
        for name, giant in data.get("tech_giants", {}).items():
            if giant.get("price"):
                result["tech_giants"].append(giant)
        return result

    def _format_asia_market(self, data):
        result = {"indices": []}
        for code, idx in data.get("indices", {}).items():
            if idx.get("price"):
                result["indices"].append(idx)
        return result

    def _format_europe_market(self, data):
        result = {"indices": []}
        for code, idx in data.get("indices", {}).items():
            if idx.get("price"):
                result["indices"].append(idx)
        return result

    def _format_commodities(self, data):
        result = {"oil": [], "gold": None}
        for name, oil in data.get("oil", {}).items():
            if oil.get("price"):
                result["oil"].append(oil)
        gold = data.get("gold")
        if gold and gold.get("price"):
            result["gold"] = gold
        return result

    def _format_forex(self, data):
        result = {"usd_cny": {}}
        usd = data.get("usd_cny", {})
        if usd.get("onshore"):
            result["usd_cny"]["onshore"] = usd["onshore"]
        if usd.get("central"):
            result["usd_cny"]["central"] = usd["central"]
        if usd.get("pct_change"):
            result["usd_cny"]["pct_change"] = usd["pct_change"]
        return result

    def _safe_float(self, value):
        if value is None:
            return None
        try:
            return float(value)
        except:
            return None
