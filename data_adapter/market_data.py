#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场数据采集模块（永久存储 + 按日期去重）
提供：多指数行情、涨跌家数、板块资金流向
数据永久保存，每天只获取一次新数据，同一天数据不重复写入
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class MarketDataCache:
    """
    市场数据永久缓存管理器
    数据存储在 memory_data/market_*.json，永久保存，不过期
    """

    def __init__(self, storage_dir: str = "memory_data/"):
        self.storage_dir = storage_dir
        self._ensure_storage_dir()
        logger.info(f"📁 市场数据缓存目录: {os.path.abspath(self.storage_dir)}")

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

    def _is_today(self, data: Dict) -> bool:
        """检查数据是否包含今日记录（永久存储但需要判断今日数据是否存在）"""
        if not data:
            return False
        today = datetime.now().strftime("%Y-%m-%d")
        if 'timestamp' in data:
            if today in data['timestamp']:
                return True
        if 'date' in data:
            if data['date'] == today:
                return True
        if 'indices' in data:
            for idx in data['indices'].values():
                if isinstance(idx, dict) and 'date' in idx and idx['date'] == today:
                    return True
        return False

    # ============================================================
    # 指数数据（永久存储）
    # ============================================================
    def get_indices(self) -> Optional[Dict]:
        """获取缓存的指数数据"""
        data = self._load_json("market_indices.json")
        if data:
            return data.get('data', {})
        return None

    def save_indices(self, data: Dict) -> str:
        """保存指数数据（永久）"""
        cache_data = {
            '_cache_time': datetime.now().isoformat(),
            'date': datetime.now().strftime("%Y-%m-%d"),
            'data': data
        }
        return self._save_json("market_indices.json", cache_data)

    def has_today_indices(self) -> bool:
        """检查是否已有今日的指数数据"""
        data = self._load_json("market_indices.json")
        if data and self._is_today(data):
            return True
        return False

    # ============================================================
    # 涨跌家数数据（永久存储）
    # ============================================================
    def get_market_stats(self) -> Optional[Dict]:
        data = self._load_json("market_stats.json")
        if data:
            return data.get('data', {})
        return None

    def save_market_stats(self, data: Dict) -> str:
        cache_data = {
            '_cache_time': datetime.now().isoformat(),
            'date': datetime.now().strftime("%Y-%m-%d"),
            'data': data
        }
        return self._save_json("market_stats.json", cache_data)

    def has_today_stats(self) -> bool:
        data = self._load_json("market_stats.json")
        if data and self._is_today(data):
            return True
        return False

    # ============================================================
    # 板块资金流向数据（永久存储）
    # ============================================================
    def get_sector_flow(self) -> Optional[Dict]:
        data = self._load_json("market_sector_flow.json")
        if data:
            return data.get('data', {})
        return None

    def save_sector_flow(self, data: Dict) -> str:
        cache_data = {
            '_cache_time': datetime.now().isoformat(),
            'date': datetime.now().strftime("%Y-%m-%d"),
            'data': data
        }
        return self._save_json("market_sector_flow.json", cache_data)

    def has_today_sector_flow(self) -> bool:
        data = self._load_json("market_sector_flow.json")
        if data and self._is_today(data):
            return True
        return False


class MarketDataCollector:
    """
    市场数据采集器（永久存储 + 按日期去重）
    每天只获取一次数据，后续直接使用缓存
    """

    def __init__(self):
        self._cache = MarketDataCache()

    # ============================================================
    # 辅助方法
    # ============================================================
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

    # ============================================================
    # 1. 多指数行情（永久存储，按日期去重）
    # ============================================================
    def get_indices(self, force_refresh: bool = False) -> Dict:
        """
        获取主要指数行情
        force_refresh: True 强制刷新，False 使用缓存（如果今日已有数据）
        """
        # ✅ 如果今日已有数据且不强制刷新，直接返回缓存
        if not force_refresh and self._cache.has_today_indices():
            cached = self._cache.get_indices()
            if cached:
                logger.info("✅ 使用缓存的今日指数数据（永久存储）")
                return cached

        logger.info("📊 获取指数行情数据...")
        result = {
            "indices": {},
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak
            # 优先使用 index_zh_spot（新版接口）
            df = None
            for func_name in ['index_zh_spot', 'stock_zh_index_spot']:
                try:
                    if hasattr(ak, func_name):
                        df = getattr(ak, func_name)()
                        if df is not None and not df.empty:
                            break
                except:
                    continue

            if df is None or df.empty:
                logger.warning("指数行情数据为空")
                return result

            # 指数映射
            index_map = {
                "上证指数": "000001.SH",
                "深证成指": "399001.SZ",
                "创业板指": "399006.SZ",
                "科创50": "000688.SH",
                "北证50": "899050.BJ"
            }

            for name, code in index_map.items():
                # 先按代码匹配
                matched = df[df['代码'] == code]
                if matched.empty:
                    # 按名称匹配
                    matched = df[df['名称'].str.contains(name, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][name] = {
                        "code": code,
                        "price": self._safe_float(row.get('最新价')),
                        "pct_change": self._safe_float(row.get('涨跌幅')),
                        "volume": self._safe_float(row.get('成交量')),
                        "amount": self._safe_float(row.get('成交额'))
                    }

            # ✅ 永久保存到缓存
            self._cache.save_indices(result)
            logger.info(f"✅ 指数数据已获取并永久保存: {len(result['indices'])}个指数")
            return result

        except Exception as e:
            logger.warning(f"指数行情获取失败: {e}")
            return result

    # ============================================================
    # 2. 涨跌家数统计（永久存储，按日期去重）
    # ============================================================
    def get_market_stats(self, force_refresh: bool = False) -> Dict:
        """获取市场涨跌家数统计"""
        # ✅ 如果今日已有数据且不强制刷新，直接返回缓存
        if not force_refresh and self._cache.has_today_stats():
            cached = self._cache.get_market_stats()
            if cached:
                logger.info("✅ 使用缓存的今日涨跌家数数据（永久存储）")
                return cached

        logger.info("📊 获取涨跌家数数据...")
        result = {
            "up": 0,
            "down": 0,
            "flat": 0,
            "total": 0,
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak
            # 尝试东方财富A股实时行情
            df = ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                pct_col = self._find_column(df, ['涨跌幅', 'change'])
                if pct_col:
                    up = (df[pct_col] > 0).sum()
                    down = (df[pct_col] < 0).sum()
                    flat = (df[pct_col] == 0).sum()
                    result["up"] = int(up)
                    result["down"] = int(down)
                    result["flat"] = int(flat)
                    result["total"] = int(up + down + flat)
                    # ✅ 永久保存
                    self._cache.save_market_stats(result)
                    logger.info(f"✅ 涨跌家数已获取并永久保存: 上涨{up}家, 下跌{down}家, 平盘{flat}家")
                    return result
        except Exception as e:
            logger.debug(f"东方财富涨跌家数获取失败: {e}")

        # 备选方案：使用指数统计
        try:
            import akshare as ak
            df = ak.stock_zh_index_spot()
            if df is not None and not df.empty:
                pct_col = self._find_column(df, ['涨跌幅', 'change'])
                if pct_col:
                    up = (df[pct_col] > 0).sum()
                    down = (df[pct_col] < 0).sum()
                    flat = (df[pct_col] == 0).sum()
                    result["up"] = int(up)
                    result["down"] = int(down)
                    result["flat"] = int(flat)
                    result["total"] = int(up + down + flat)
                    self._cache.save_market_stats(result)
                    logger.info(f"✅ 涨跌家数（备选）已获取并永久保存: 上涨{up}家, 下跌{down}家")
                    return result
        except Exception as e:
            logger.warning(f"涨跌家数获取失败: {e}")

        return result

    # ============================================================
    # 3. 板块资金流向TOP5（永久存储，按日期去重）
    # ============================================================
    def get_sector_flow(self, force_refresh: bool = False) -> Dict:
        """获取申万一级行业资金流向TOP5"""
        # ✅ 如果今日已有数据且不强制刷新，直接返回缓存
        if not force_refresh and self._cache.has_today_sector_flow():
            cached = self._cache.get_sector_flow()
            if cached:
                logger.info("✅ 使用缓存的今日板块资金流向数据（永久存储）")
                return cached

        logger.info("📊 获取板块资金流向数据...")
        result = {
            "net_inflow_top5": [],
            "net_outflow_top5": [],
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak
            # 尝试获取行业资金流向
            df = ak.stock_sector_spot()
            if df is not None and not df.empty:
                inflow_col = self._find_column(df, ['主力净流入', 'main_net_inflow'])
                if inflow_col:
                    df_sorted = df.sort_values(by=inflow_col, ascending=False)
                    top_inflow = df_sorted.head(5)
                    for _, row in top_inflow.iterrows():
                        result["net_inflow_top5"].append({
                            "sector": row.get('名称', ''),
                            "flow": self._safe_float(row.get(inflow_col))
                        })
                    top_outflow = df_sorted.tail(5)
                    for _, row in top_outflow.iterrows():
                        result["net_outflow_top5"].append({
                            "sector": row.get('名称', ''),
                            "flow": self._safe_float(row.get(inflow_col))
                        })
                    self._cache.save_sector_flow(result)
                    logger.info("✅ 板块资金流向已获取并永久保存")
                    return result
        except Exception as e:
            logger.debug(f"板块资金流向获取失败: {e}")

        # 备选方案：使用行业指数涨跌幅近似
        try:
            import akshare as ak
            df = ak.stock_zh_index_spot()
            if df is not None and not df.empty:
                sector_df = df[df['名称'].str.contains('申万|行业', na=False)]
                if not sector_df.empty:
                    pct_col = self._find_column(sector_df, ['涨跌幅', 'change'])
                    if pct_col:
                        df_sorted = sector_df.sort_values(by=pct_col, ascending=False)
                        top = df_sorted.head(5)
                        for _, row in top.iterrows():
                            result["net_inflow_top5"].append({
                                "sector": row.get('名称', ''),
                                "flow": self._safe_float(row.get(pct_col))
                            })
                        bottom = df_sorted.tail(5)
                        for _, row in bottom.iterrows():
                            result["net_outflow_top5"].append({
                                "sector": row.get('名称', ''),
                                "flow": self._safe_float(row.get(pct_col))
                            })
                        self._cache.save_sector_flow(result)
                        logger.info("✅ 板块资金流向（基于涨跌幅近似）已获取并永久保存")
                        return result
        except Exception as e:
            logger.warning(f"板块资金流向获取失败: {e}")

        return result

    # ============================================================
    # 4. 便捷方法：获取所有市场数据
    # ============================================================
    def get_all_market_data(self, force_refresh: bool = False) -> Dict:
        """获取所有市场数据（指数、涨跌家数、资金流向）"""
        return {
            "indices": self.get_indices(force_refresh),
            "market_stats": self.get_market_stats(force_refresh),
            "sector_flow": self.get_sector_flow(force_refresh),
            "timestamp": datetime.now().isoformat()
        }
