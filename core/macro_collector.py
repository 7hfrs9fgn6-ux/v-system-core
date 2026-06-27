#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观数据采集模块（P0阶段 + 强化容错）
独立于AKShare行业数据，即使AKShare过载也能正常返回
绝不修改 data_adapter/real_adapter.py
"""

import os
import logging
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class MacroCollector:
    """
    宏观数据采集器（强化容错版）
    采集范围：美股、欧股、亚太、大宗商品、汇率、A50期货
    容错策略：独立重试 + 缓存降级 + 模拟值兜底
    """

    def __init__(self):
        self._cache = {}
        self._cache_ttl = 300  # 5分钟缓存
        self._retry_count = 3
        self._retry_delay = [1, 2, 4]  # 递增延迟
        self._last_success_data = {}  # 最后成功的数据（永久缓存）
        self._has_ever_succeeded = False

    def _is_cached_valid(self, key: str) -> bool:
        """检查缓存是否有效"""
        if key in self._cache:
            cached_time, _ = self._cache[key]
            if (datetime.now() - cached_time).total_seconds() < self._cache_ttl:
                return True
        return False

    def _get_cached(self, key: str) -> Any:
        """获取缓存数据"""
        if key in self._cache:
            _, data = self._cache[key]
            return data
        return None

    def _set_cache(self, key: str, data: Any):
        """设置缓存"""
        self._cache[key] = (datetime.now(), data)

    def _safe_fetch(self, func, *args, **kwargs) -> Any:
        """
        安全获取数据：带重试 + 缓存降级
        """
        cache_key = func.__name__ if hasattr(func, '__name__') else str(func)

        # 1. 尝试从缓存获取
        if self._is_cached_valid(cache_key):
            return self._get_cached(cache_key)

        # 2. 执行获取（带重试）
        last_error = None
        for attempt in range(self._retry_count):
            try:
                result = func(*args, **kwargs)
                if result and not self._is_empty_result(result):
                    self._set_cache(cache_key, result)
                    self._last_success_data[cache_key] = result
                    self._has_ever_succeeded = True
                    return result
            except Exception as e:
                last_error = e
                if attempt < self._retry_count - 1:
                    time.sleep(self._retry_delay[attempt])
                    continue

        # 3. 降级：使用上次成功的数据
        if cache_key in self._last_success_data:
            logger.warning(f"⚠️ {cache_key} 获取失败，使用上次成功数据")
            return self._last_success_data[cache_key]

        # 4. 最终降级：返回空但格式正确的数据
        logger.warning(f"⚠️ {cache_key} 完全不可用，返回空数据")
        return self._get_empty_result()

    def _is_empty_result(self, data) -> bool:
        """检查数据是否为空"""
        if data is None:
            return True
        if isinstance(data, dict):
            # 检查是否所有值都为空
            for key, value in data.items():
                if value and not self._is_empty_result(value):
                    return False
            return True
        if isinstance(data, list):
            return len(data) == 0
        return False

    def _get_empty_result(self) -> Dict:
        """返回空结果格式"""
        return {
            "indices": {},
            "semiconductor": {},
            "tech_giants": {},
            "oil": {},
            "gold": {},
            "usd_cny": {},
            "price": None,
            "pct_change": None,
            "data_source": "cache_fallback",
            "timestamp": datetime.now().isoformat()
        }

    # ============================================================
    # 1. 美股数据
    # ============================================================
    def get_us_market(self) -> Dict:
        """获取美股市场数据（带容错）"""
        return self._safe_fetch(self._fetch_us_market_impl)

    def _fetch_us_market_impl(self) -> Dict:
        """实际获取美股数据的实现"""
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

            return result

        except Exception as e:
            logger.warning(f"美股数据获取异常: {e}")
            return result

    # ============================================================
    # 2. 亚太市场
    # ============================================================
    def get_asia_market(self) -> Dict:
        """获取亚太市场数据（带容错）"""
        return self._safe_fetch(self._fetch_asia_market_impl)

    def _fetch_asia_market_impl(self) -> Dict:
        """实际获取亚太数据的实现"""
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

            return result

        except Exception as e:
            logger.warning(f"亚太数据获取异常: {e}")
            return result

    # ============================================================
    # 3. 欧洲市场
    # ============================================================
    def get_europe_market(self) -> Dict:
        """获取欧洲市场数据（带容错）"""
        return self._safe_fetch(self._fetch_europe_market_impl)

    def _fetch_europe_market_impl(self) -> Dict:
        """实际获取欧洲数据的实现"""
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

            return result

        except Exception as e:
            logger.warning(f"欧洲数据获取异常: {e}")
            return result

    # ============================================================
    # 4. 大宗商品
    # ============================================================
    def get_commodities(self) -> Dict:
        """获取大宗商品数据（带容错）"""
        return self._safe_fetch(self._fetch_commodities_impl)

    def _fetch_commodities_impl(self) -> Dict:
        """实际获取大宗商品数据的实现"""
        result = {
            "oil": {},
            "gold": {},
            "data_source": "AKShare",
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak

            # 原油 WTI
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

            # 原油 布伦特
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

            # 黄金
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

            return result

        except Exception as e:
            logger.warning(f"大宗商品获取异常: {e}")
            return result

    # ============================================================
    # 5. 人民币汇率
    # ============================================================
    def get_forex(self) -> Dict:
        """获取人民币汇率数据（带容错）"""
        return self._safe_fetch(self._fetch_forex_impl)

    def _fetch_forex_impl(self) -> Dict:
        """实际获取汇率数据的实现"""
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

            return result

        except Exception as e:
            logger.warning(f"汇率数据获取异常: {e}")
            return result

    # ============================================================
    # 6. A50期货
    # ============================================================
    def get_a50_futures(self) -> Dict:
        """获取A50期货数据（带容错）"""
        return self._safe_fetch(self._fetch_a50_impl)

    def _fetch_a50_impl(self) -> Dict:
        """实际获取A50期货数据的实现"""
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

            return result

        except Exception as e:
            logger.warning(f"A50期货获取异常: {e}")
            return result

    # ============================================================
    # 7. 综合宏观快照
    # ============================================================
    def get_macro_snapshot(self) -> Dict:
        """获取完整的宏观数据快照（带容错）"""
        # 使用缓存，避免重复请求
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

    # ============================================================
    # 8. 格式化宏观数据（供推送使用）
    # ============================================================
    def format_for_push(self) -> Dict:
        """获取并格式化宏观数据，供推送使用"""
        snapshot = self.get_macro_snapshot()

        formatted = {
            "us_market": self._format_us_market(snapshot.get("us_market", {})),
            "asia_market": self._format_asia_market(snapshot.get("asia_market", {})),
            "europe_market": self._format_europe_market(snapshot.get("europe_market", {})),
            "commodities": self._format_commodities(snapshot.get("commodities", {})),
            "forex": self._format_forex(snapshot.get("forex", {})),
            "a50_futures": self._format_a50(snapshot.get("a50_futures", {})),
            "timestamp": snapshot.get("timestamp", "")
        }
        return formatted

    def _format_us_market(self, data: Dict) -> Dict:
        """格式化美股数据"""
        result = {"indices": [], "tech_giants": [], "semiconductor": None}

        for name, idx in data.get("indices", {}).items():
            if idx.get("price"):
                result["indices"].append({
                    "name": idx.get("name", name),
                    "price": idx.get("price"),
                    "pct_change": idx.get("pct_change")
                })

        sem = data.get("semiconductor", {})
        if sem.get("price"):
            result["semiconductor"] = {
                "name": sem.get("name", "费城半导体"),
                "price": sem.get("price"),
                "pct_change": sem.get("pct_change")
            }

        for name, giant in data.get("tech_giants", {}).items():
            if giant.get("price"):
                result["tech_giants"].append({
                    "name": name,
                    "price": giant.get("price"),
                    "pct_change": giant.get("pct_change")
                })

        return result

    def _format_asia_market(self, data: Dict) -> Dict:
        """格式化亚太市场数据"""
        result = {"indices": []}
        for code, idx in data.get("indices", {}).items():
            if idx.get("price"):
                result["indices"].append({
                    "name": idx.get("name", code),
                    "price": idx.get("price"),
                    "pct_change": idx.get("pct_change")
                })
        return result

    def _format_europe_market(self, data: Dict) -> Dict:
        """格式化欧洲市场数据"""
        result = {"indices": []}
        for code, idx in data.get("indices", {}).items():
            if idx.get("price"):
                result["indices"].append({
                    "name": idx.get("name", code),
                    "price": idx.get("price"),
                    "pct_change": idx.get("pct_change")
                })
        return result

    def _format_commodities(self, data: Dict) -> Dict:
        """格式化大宗商品数据"""
        result = {"oil": [], "gold": None}

        for name, oil in data.get("oil", {}).items():
            if oil.get("price"):
                result["oil"].append({
                    "name": oil.get("name", name),
                    "price": oil.get("price"),
                    "pct_change": oil.get("pct_change")
                })

        gold = data.get("gold", {})
        if gold.get("price"):
            result["gold"] = {
                "price": gold.get("price"),
                "pct_change": gold.get("pct_change")
            }

        return result

    def _format_forex(self, data: Dict) -> Dict:
        """格式化汇率数据"""
        result = {"usd_cny": {}}
        usd = data.get("usd_cny", {})
        if usd.get("onshore"):
            result["usd_cny"]["onshore"] = usd.get("onshore")
        if usd.get("central"):
            result["usd_cny"]["central"] = usd.get("central")
        if usd.get("pct_change"):
            result["usd_cny"]["pct_change"] = usd.get("pct_change")
        return result

    def _format_a50(self, data: Dict) -> Dict:
        """格式化A50期货数据"""
        result = {}
        if data.get("price"):
            result["price"] = data.get("price")
        if data.get("pct_change"):
            result["pct_change"] = data.get("pct_change")
        return result

    # ============================================================
    # 辅助方法
    # ============================================================
    def _safe_float(self, value) -> Optional[float]:
        """安全转换为浮点数"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
