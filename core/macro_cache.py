#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观数据缓存模块（永久存储）
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class MacroCache:
    def __init__(self, storage_dir: str = "memory_data/"):
        self.storage_dir = storage_dir
        self._ensure_storage_dir()
        self._last_update_file = os.path.join(storage_dir, "macro_last_update.json")
        logger.info(f"📁 MacroCache 存储目录: {os.path.abspath(self.storage_dir)}")

    def _ensure_storage_dir(self):
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir, exist_ok=True)

    def _get_file_path(self, filename: str) -> str:
        return os.path.join(self.storage_dir, filename)

    def _load_json(self, filename: str) -> Optional[Dict]:
        file_path = self._get_file_path(filename)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return None
        return None

    def _save_json(self, filename: str, data: Dict) -> str:
        file_path = self._get_file_path(filename)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return file_path

    def _is_cache_valid(self, cache_time: str) -> bool:
        if not cache_time:
            return False
        return True

    # ============================================================
    # 美股数据
    # ============================================================
    def get_us_market(self) -> Optional[Dict]:
        data = self._load_json("macro_us_market.json")
        if data and self._is_cache_valid(data.get('_cache_time', '')):
            return data.get('data', {})
        return None

    def save_us_market(self, data: Dict) -> str:
        cache_data = {'_cache_time': datetime.now().isoformat(), 'data': data}
        return self._save_json("macro_us_market.json", cache_data)

    # ============================================================
    # 亚太市场
    # ============================================================
    def get_asia_market(self) -> Optional[Dict]:
        data = self._load_json("macro_asia_market.json")
        if data and self._is_cache_valid(data.get('_cache_time', '')):
            return data.get('data', {})
        return None

    def save_asia_market(self, data: Dict) -> str:
        cache_data = {'_cache_time': datetime.now().isoformat(), 'data': data}
        return self._save_json("macro_asia_market.json", cache_data)

    # ============================================================
    # 欧洲市场
    # ============================================================
    def get_europe_market(self) -> Optional[Dict]:
        data = self._load_json("macro_europe_market.json")
        if data and self._is_cache_valid(data.get('_cache_time', '')):
            return data.get('data', {})
        return None

    def save_europe_market(self, data: Dict) -> str:
        cache_data = {'_cache_time': datetime.now().isoformat(), 'data': data}
        return self._save_json("macro_europe_market.json", cache_data)

    # ============================================================
    # 大宗商品
    # ============================================================
    def get_commodities(self) -> Optional[Dict]:
        data = self._load_json("macro_commodities.json")
        if data and self._is_cache_valid(data.get('_cache_time', '')):
            return data.get('data', {})
        return None

    def save_commodities(self, data: Dict) -> str:
        cache_data = {'_cache_time': datetime.now().isoformat(), 'data': data}
        return self._save_json("macro_commodities.json", cache_data)

    # ============================================================
    # 汇率
    # ============================================================
    def get_forex(self) -> Optional[Dict]:
        data = self._load_json("macro_forex.json")
        if data and self._is_cache_valid(data.get('_cache_time', '')):
            return data.get('data', {})
        return None

    def save_forex(self, data: Dict) -> str:
        cache_data = {'_cache_time': datetime.now().isoformat(), 'data': data}
        return self._save_json("macro_forex.json", cache_data)

    # ============================================================
    # A50期货
    # ============================================================
    def get_a50_futures(self) -> Optional[Dict]:
        data = self._load_json("macro_a50.json")
        if data and self._is_cache_valid(data.get('_cache_time', '')):
            return data.get('data', {})
        return None

    def save_a50_futures(self, data: Dict) -> str:
        cache_data = {'_cache_time': datetime.now().isoformat(), 'data': data}
        return self._save_json("macro_a50.json", cache_data)

    # ============================================================
    # 宏观快照
    # ============================================================
    def get_macro_snapshot(self) -> Optional[Dict]:
        data = self._load_json("macro_snapshot.json")
        if data and self._is_cache_valid(data.get('_cache_time', '')):
            return data.get('data', {})
        return None

    def save_macro_snapshot(self, data: Dict) -> str:
        cache_data = {'_cache_time': datetime.now().isoformat(), 'data': data}
        return self._save_json("macro_snapshot.json", cache_data)
