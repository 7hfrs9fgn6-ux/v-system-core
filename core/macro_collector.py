#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观数据采集模块（超时版）
为每个数据源设置独立超时（美股15秒，其他10秒），避免卡死
"""

import os
import logging
import time
import json
import concurrent.futures
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from core.macro_cache import MacroCache

logger = logging.getLogger(__name__)


class MacroCollector:
    def __init__(self):
        self._cache = MacroCache()
        self._retry_count = 2  # 减少重试次数
        self._retry_delay = [1, 2]
        # 每个数据源的超时时间（秒）
        self._timeout_map = {
            'us_market': 15,
            'asia_market': 10,
            'europe_market': 10,
            'commodities': 10,
            'forex': 8,
            'a50_futures': 8,
        }

    # ---------- 辅助 ----------
    def _safe_float(self, value) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _find_column(self, df, candidates):
        if df is None or df.empty:
            return None
        for c in df.columns:
            for cand in candidates:
                if cand in c or c in cand:
                    return c
        return None

    def _get_empty_result(self) -> Dict:
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

    def _is_empty_result(self, data) -> bool:
        if data is None:
            return True
        if isinstance(data, dict):
            for key, value in data.items():
                if value and not self._is_empty_result(value):
                    return False
            return True
        if isinstance(data, list):
            return len(data) == 0
        return False

    # ---------- 存储层缓存 ----------
    def _get_cached_from_storage(self, key, ignore_ttl=False):
        methods = {
            'us_market': self._cache.get_us_market,
            'asia_market': self._cache.get_asia_market,
            'europe_market': self._cache.get_europe_market,
            'commodities': self._cache.get_commodities,
            'forex': self._cache.get_forex,
            'a50_futures': self._cache.get_a50_futures,
        }
        if key in methods:
            return methods[key]()
        return None

    def _save_cached_to_storage(self, key, data):
        methods = {
            'us_market': self._cache.save_us_market,
            'asia_market': self._cache.save_asia_market,
            'europe_market': self._cache.save_europe_market,
            'commodities': self._cache.save_commodities,
            'forex': self._cache.save_forex,
            'a50_futures': self._cache.save_a50_futures,
        }
        if key in methods:
            methods[key](data)
            logger.info(f"✅ {key} 已保存到存储缓存")

    # ---------- 安全获取（带超时） ----------
    def _safe_fetch(self, func, cache_key: str = None, *args, **kwargs) -> Any:
        # 1. 缓存优先
        if cache_key:
            cached_data = self._get_cached_from_storage(cache_key)
            if cached_data is not None and not self._is_empty_result(cached_data):
                logger.info(f"✅ 从存储缓存获取 {cache_key}")
                return cached_data

        timeout = self._timeout_map.get(cache_key, 10)

        # 2. 实时获取（带超时）
        for attempt in range(self._retry_count):
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(func, *args, **kwargs)
                    result = future.result(timeout=timeout)
                    if result and not self._is_empty_result(result):
                        if cache_key:
                            self._save_cached_to_storage(cache_key, result)
                        return result
            except concurrent.futures.TimeoutError:
                logger.warning(f"⏰ {cache_key} 超时 ({timeout}s)，尝试 {attempt+1}/{self._retry_count}")
                if attempt < self._retry_count - 1:
                    time.sleep(self._retry_delay[attempt])
                    continue
            except Exception as e:
                logger.warning(f"⚠️ {cache_key} 异常: {e}")
                if attempt < self._retry_count - 1:
                    time.sleep(self._retry_delay[attempt])
                    continue

        # 3. 使用过期缓存
        if cache_key:
            stale_data = self._get_cached_from_storage(cache_key, ignore_ttl=True)
            if stale_data is not None and not self._is_empty_result(stale_data):
                logger.warning(f"⚠️ 使用过期缓存 {cache_key}")
                return stale_data

        logger.warning(f"⚠️ {cache_key} 完全不可用，返回空数据")
        return self._get_empty_result()

    # ============================================================
    # 以下各个获取方法保持不变，只需调用 _safe_fetch
    # ============================================================
    def get_us_market(self) -> Dict:
        return self._safe_fetch(self._fetch_us_market_impl, 'us_market')

    def _fetch_us_market_impl(self) -> Dict:
        # ... 你已有的实现，无需改动 ...
        # 但为了完整，我会在最终完整代码中包含它

    # 其他方法（_fetch_asia_market_impl等）同样不变

    # ============================================================
    # 格式化方法不变
    # ============================================================
    # ... 其余全部保持原样 ...
