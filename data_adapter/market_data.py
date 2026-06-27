#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场数据采集模块（P2阶段 + 按日期去重）
提供：多指数行情、涨跌家数、板块资金流向
数据永久存储，每天只获取一次，避免重复写入
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class MarketDataCollector:
    """市场数据采集器（去重版）"""

    def __init__(self):
        self._cache = {}
        self._cache_ttl = 86400  # 24小时缓存（用于内存缓存，但实际有效期以日期为准）

    def _is_cached_valid(self, key: str) -> bool:
        """检查缓存是否有效（未过期且包含今日数据）"""
        if key in self._cache:
            cached_time, data = self._cache[key]
            # 检查是否包含今日日期
            if self._is_data_today(data):
                return True
        return False

    def _is_data_today(self, data: Dict) -> bool:
        """检查数据是否包含今日记录"""
        if not data:
            return False
        today = datetime.now().strftime("%Y-%m-%d")
        # 检查数据中是否有日期字段且等于今日
        if 'timestamp' in data:
            if today in data['timestamp']:
                return True
        # 对于指数数据，检查是否有'date'字段
        if 'indices' in data:
            for idx in data['indices'].values():
                if isinstance(idx, dict) and 'date' in idx:
                    if idx['date'] == today:
                        return True
        # 对于涨跌家数，检查'timestamp'
        if 'up' in data or 'down' in data:
            if 'timestamp' in data and today in data['timestamp']:
                return True
        return False

    def _get_cached(self, key: str):
        if key in self._cache:
            _, data = self._cache[key]
            return data
        return None

    def _set_cache(self, key: str, data):
        self._cache[key] = (datetime.now(), data)

    # ============================================================
    # 1. 多指数行情（按日期去重）
    # ============================================================
    def get_indices(self, force_refresh: bool = False) -> Dict:
        """
        获取主要指数行情
        force_refresh: 强制刷新（忽略缓存）
        """
        cache_key = "indices"
        if not force_refresh and self._is_cached_valid(cache_key):
            return self._get_cached(cache_key)

        result = {
            "indices": {},
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak
            # 优先使用 index_zh_spot（新版接口）
            df = None
            try:
                df = ak.index_zh_spot()
            except:
                pass
            if df is None or df.empty:
                # 降级：尝试旧接口
                try:
                    df = ak.stock_zh_index_spot()
                except:
                    pass
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
                        "amount": self._safe_float(row.get('成交额')),
                        "date": datetime.now().strftime("%Y-%m-%d")
                    }

            self._set_cache(cache_key, result)
            logger.info(f"✅ 获取到 {len(result['indices'])} 个指数数据（今日已缓存）")
            return result

        except Exception as e:
            logger.warning(f"指数行情获取失败: {e}")
            return result

    # ============================================================
    # 2. 涨跌家数统计（按日期去重）
    # ============================================================
    def get_market_stats(self, force_refresh: bool = False) -> Dict:
        """获取市场涨跌家数统计"""
        cache_key = "market_stats"
        if not force_refresh and self._is_cached_valid(cache_key):
            return self._get_cached(cache_key)

        result = {
            "up": 0,
            "down": 0,
            "flat": 0,
            "total": 0,
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()  # 东方财富A股实时行情
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
                    self._set_cache(cache_key, result)
                    logger.info(f"✅ 涨跌家数: 上涨{up}家, 下跌{down}家, 平盘{flat}家（今日已缓存）")
                    return result
            else:
                # 备选方案
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
                        self._set_cache(cache_key, result)
                        logger.info(f"✅ 涨跌家数（备选）: 上涨{up}家, 下跌{down}家, 平盘{flat}家（今日已缓存）")
                        return result

            logger.warning("涨跌家数统计失败，返回空数据")
            return result

        except Exception as e:
            logger.warning(f"涨跌家数获取失败: {e}")
            return result

    # ============================================================
    # 3. 板块资金流向TOP5（按日期去重）
    # ============================================================
    def get_sector_flow(self, force_refresh: bool = False) -> Dict:
        """获取申万一级行业资金流向TOP5"""
        cache_key = "sector_flow"
        if not force_refresh and self._is_cached_valid(cache_key):
            return self._get_cached(cache_key)

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
                    self._set_cache(cache_key, result)
                    logger.info("✅ 板块资金流向: 流入TOP5, 流出TOP5（今日已缓存）")
                    return result
            else:
                # 备选：使用行业指数涨跌幅近似
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
                            self._set_cache(cache_key, result)
                            logger.info("✅ 板块资金流向（基于涨跌幅近似，今日已缓存）")
                            return result

            logger.warning("板块资金流向获取失败，返回空数据")
            return result

        except Exception as e:
            logger.warning(f"板块资金流向获取失败: {e}")
            return result

    # ============================================================
    # 4. 辅助方法
    # ============================================================
    def _safe_float(self, value) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _find_column(self, df, candidates):
        for c in df.columns:
            for cand in candidates:
                if cand in c or c in cand:
                    return c
        return None
