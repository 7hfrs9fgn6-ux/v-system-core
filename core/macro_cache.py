#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观数据缓存模块（记忆体集成版）
将宏观历史数据存储到 memory_data/ 目录
每次只获取增量更新，大幅提升速度
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class MacroCache:
    """
    宏观数据缓存管理器
    数据存储在 memory_data/macro_* 目录下
    """

    def __init__(self, storage_dir: str = "memory_data/"):
        self.storage_dir = storage_dir
        self._ensure_storage_dir()
        self._cache_ttl = 3600  # 缓存有效期1小时（仅对增量更新有效）
        self._last_update_file = os.path.join(storage_dir, "macro_last_update.json")
        logger.info(f"📁 MacroCache 存储目录: {os.path.abspath(self.storage_dir)}")

    def _ensure_storage_dir(self):
        """确保存储目录存在"""
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir, exist_ok=True)
            logger.info(f"📁 创建目录: {self.storage_dir}")

    def _get_file_path(self, filename: str) -> str:
        """获取完整文件路径"""
        return os.path.join(self.storage_dir, filename)

    def _load_json(self, filename: str) -> Optional[Dict]:
        """加载 JSON 文件"""
        file_path = self._get_file_path(filename)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return None
        return None

    def _save_json(self, filename: str, data: Dict) -> str:
        """保存 JSON 文件，返回文件路径"""
        file_path = self._get_file_path(filename)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return file_path

    def _is_cache_valid(self, cache_time: str) -> bool:
        """检查缓存是否在有效期内"""
        if not cache_time:
            return False
        try:
            cache_dt = datetime.fromisoformat(cache_time)
            now = datetime.now()
            return (now - cache_dt).total_seconds() < self._cache_ttl * 2
        except:
            return False

    # ============================================================
    # 美股数据缓存
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
    # 亚太市场数据缓存
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
    # 欧洲市场数据缓存
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
    # 大宗商品数据缓存
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
    # 汇率数据缓存
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
    # A50期货数据缓存
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
    # 辅助方法
    # ============================================================
    def get_last_update_time(self) -> Optional[datetime]:
        if os.path.exists(self._last_update_file):
            try:
                with open(self._last_update_file, 'r') as f:
                    data = json.load(f)
                    return datetime.fromisoformat(data.get('last_update', ''))
            except:
                pass
        return None

    def set_last_update_time(self):
        with open(self._last_update_file, 'w') as f:
            json.dump({'last_update': datetime.now().isoformat()}, f)

    def clear_all_cache(self):
        for file in os.listdir(self.storage_dir):
            if file.startswith('macro_') and file.endswith('.json'):
                os.remove(os.path.join(self.storage_dir, file))
        if os.path.exists(self._last_update_file):
            os.remove(self._last_update_file)
        logger.info("✅ 宏观缓存已全部清空")
