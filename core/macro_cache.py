#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观数据缓存模块（永久存储版）
数据一旦获取，永久保存在 memory_data/ 目录中，永不自动过期
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class MacroCache:
    """
    宏观数据缓存管理器（永久存储）
    数据存储在 memory_data/macro_*.json 文件中，永久有效
    """

    def __init__(self, storage_dir: str = "memory_data/"):
        self.storage_dir = storage_dir
        self._ensure_storage_dir()
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
            except Exception as e:
                logger.warning(f"⚠️ 加载 {filename} 失败: {e}")
                return None
        return None

    def _save_json(self, filename: str, data: Dict) -> str:
        """
        保存 JSON 文件，返回文件路径
        """
        file_path = self._get_file_path(filename)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return file_path

    # ============================================================
    # ✅ 永久有效：只要文件存在，数据就有效
    # ============================================================
    def _is_cache_valid(self, cache_time: str) -> bool:
        """
        永久有效：只要缓存时间存在，就认为数据有效
        不检查任何过期时间
        """
        return cache_time is not None and len(cache_time) > 0

    # ============================================================
    # 美股数据缓存
    # ============================================================
    def get_us_market(self) -> Optional[Dict]:
        """获取美股缓存数据"""
        data = self._load_json("macro_us_market.json")
        if data and self._is_cache_valid(data.get('_cache_time', '')):
            return data.get('data', {})
        return None

    def save_us_market(self, data: Dict) -> str:
        """保存美股数据到缓存，返回文件路径"""
        cache_data = {
            '_cache_time': datetime.now().isoformat(),
            'data': data
        }
        return self._save_json("macro_us_market.json", cache_data)

    # ============================================================
    # 亚太市场数据缓存
    # ============================================================
    def get_asia_market(self) -> Optional[Dict]:
        """获取亚太市场缓存数据"""
        data = self._load_json("macro_asia_market.json")
        if data and self._is_cache_valid(data.get('_cache_time', '')):
            return data.get('data', {})
        return None

    def save_asia_market(self, data: Dict) -> str:
        """保存亚太市场数据到缓存，返回文件路径"""
        cache_data = {
            '_cache_time': datetime.now().isoformat(),
            'data': data
        }
        return self._save_json("macro_asia_market.json", cache_data)

    # ============================================================
    # 欧洲市场数据缓存
    # ============================================================
    def get_europe_market(self) -> Optional[Dict]:
        """获取欧洲市场缓存数据"""
        data = self._load_json("macro_europe_market.json")
        if data and self._is_cache_valid(data.get('_cache_time', '')):
            return data.get('data', {})
        return None

    def save_europe_market(self, data: Dict) -> str:
        """保存欧洲市场数据到缓存，返回文件路径"""
        cache_data = {
            '_cache_time': datetime.now().isoformat(),
            'data': data
        }
        return self._save_json("macro_europe_market.json", cache_data)

    # ============================================================
    # 大宗商品数据缓存
    # ============================================================
    def get_commodities(self) -> Optional[Dict]:
        """获取大宗商品缓存数据"""
        data = self._load_json("macro_commodities.json")
        if data and self._is_cache_valid(data.get('_cache_time', '')):
            return data.get('data', {})
        return None

    def save_commodities(self, data: Dict) -> str:
        """保存大宗商品数据到缓存，返回文件路径"""
        cache_data = {
            '_cache_time': datetime.now().isoformat(),
            'data': data
        }
        return self._save_json("macro_commodities.json", cache_data)

    # ============================================================
    # 汇率数据缓存
    # ============================================================
    def get_forex(self) -> Optional[Dict]:
        """获取汇率缓存数据"""
        data = self._load_json("macro_forex.json")
        if data and self._is_cache_valid(data.get('_cache_time', '')):
            return data.get('data', {})
        return None

    def save_forex(self, data: Dict) -> str:
        """保存汇率数据到缓存，返回文件路径"""
        cache_data = {
            '_cache_time': datetime.now().isoformat(),
            'data': data
        }
        return self._save_json("macro_forex.json", cache_data)

    # ============================================================
    # A50期货数据缓存
    # ============================================================
    def get_a50_futures(self) -> Optional[Dict]:
        """获取A50期货缓存数据"""
        data = self._load_json("macro_a50.json")
        if data and self._is_cache_valid(data.get('_cache_time', '')):
            return data.get('data', {})
        return None

    def save_a50_futures(self, data: Dict) -> str:
        """保存A50期货数据到缓存，返回文件路径"""
        cache_data = {
            '_cache_time': datetime.now().isoformat(),
            'data': data
        }
        return self._save_json("macro_a50.json", cache_data)

    # ============================================================
    # 辅助方法
    # ============================================================
    def get_last_update_time(self) -> Optional[datetime]:
        """获取最后更新时间"""
        if os.path.exists(self._last_update_file):
            try:
                with open(self._last_update_file, 'r') as f:
                    data = json.load(f)
                    return datetime.fromisoformat(data.get('last_update', ''))
            except:
                pass
        return None

    def set_last_update_time(self):
        """设置最后更新时间"""
        with open(self._last_update_file, 'w') as f:
            json.dump({'last_update': datetime.now().isoformat()}, f)

    def clear_all_cache(self):
        """清空所有缓存（调试用）"""
        for file in os.listdir(self.storage_dir):
            if file.startswith('macro_') and file.endswith('.json'):
                file_path = os.path.join(self.storage_dir, file)
                os.remove(file_path)
                logger.info(f"🗑️ 删除: {file_path}")
        if os.path.exists(self._last_update_file):
            os.remove(self._last_update_file)
        logger.info("✅ 宏观缓存已全部清空")

    def is_empty(self) -> bool:
        """检查是否没有任何缓存数据"""
        files = [f for f in os.listdir(self.storage_dir) 
                 if f.startswith('macro_') and f.endswith('.json')]
        return len(files) == 0

    def get_cache_files(self) -> list:
        """获取所有缓存文件名列表"""
        return [f for f in os.listdir(self.storage_dir) 
                if f.startswith('macro_') and f.endswith('.json')]
