#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场数据采集模块（P2阶段）
提供：多指数行情、涨跌家数、板块资金流向
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class MarketDataCollector:
    """市场数据采集器"""

    def __init__(self):
        self._cache = {}
        self._cache_ttl = 60  # 1分钟缓存

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

    # ============================================================
    # 1. 多指数行情（上证/深证/创业板/科创50/北证50）
    # ============================================================
    def get_indices(self) -> Dict:
        """获取主要指数行情"""
        cache_key = "indices"
        if self._is_cached_valid(cache_key):
            return self._get_cached(cache_key)

        result = {
            "indices": {},
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak
            df = ak.stock_zh_index_spot()
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
                matched = df[df['代码'] == code]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][name] = {
                        "code": code,
                        "price": self._safe_float(row.get('最新价')),
                        "pct_change": self._safe_float(row.get('涨跌幅')),
                        "volume": self._safe_float(row.get('成交量')),
                        "amount": self._safe_float(row.get('成交额'))
                    }
                else:
                    # 尝试按名称匹配
                    matched = df[df['名称'].str.contains(name, na=False)]
                    if not matched.empty:
                        row = matched.iloc[0]
                        result["indices"][name] = {
                            "code": row.get('代码'),
                            "price": self._safe_float(row.get('最新价')),
                            "pct_change": self._safe_float(row.get('涨跌幅')),
                            "volume": self._safe_float(row.get('成交量')),
                            "amount": self._safe_float(row.get('成交额'))
                        }

            self._set_cache(cache_key, result)
            logger.info(f"✅ 获取到 {len(result['indices'])} 个指数数据")
            return result

        except Exception as e:
            logger.warning(f"指数行情获取失败: {e}")
            return result

    # ============================================================
    # 2. 涨跌家数统计
    # ============================================================
    def get_market_stats(self) -> Dict:
        """获取市场涨跌家数统计"""
        cache_key = "market_stats"
        if self._is_cached_valid(cache_key):
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
            # 尝试获取全市场涨跌统计
            df = ak.stock_zh_a_spot_em()  # 东方财富A股实时行情
            if df is not None and not df.empty:
                # 统计涨跌幅
                pct_col = self._find_column(df, ['涨跌幅', 'change'])
                if pct_col:
                    up = (df[pct_col] > 0).sum()
                    down = (df[pct_col] < 0).sum()
                    flat = (df[pct_col] == 0).sum()
                    result["up"] = int(up)
                    result["down"] = int(down)
                    result["flat"] = int(flat)
                    result["total"] = int(up + down + flat)
                    logger.info(f"✅ 涨跌家数: 上涨{up}家, 下跌{down}家, 平盘{flat}家")
                    self._set_cache(cache_key, result)
                    return result
            else:
                # 备选方案：使用股票列表统计
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
                        return result

            logger.warning("涨跌家数统计失败，返回空数据")
            return result

        except Exception as e:
            logger.warning(f"涨跌家数获取失败: {e}")
            return result

    # ============================================================
    # 3. 板块资金流向TOP5（主力净流入/流出）
    # ============================================================
    def get_sector_flow(self) -> Dict:
        """获取申万一级行业资金流向TOP5"""
        cache_key = "sector_flow"
        if self._is_cached_valid(cache_key):
            return self._get_cached(cache_key)

        result = {
            "net_inflow_top5": [],
            "net_outflow_top5": [],
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak
            # 尝试获取行业资金流向
            df = ak.stock_sector_spot()  # 行业板块实时行情
            if df is not None and not df.empty:
                # 尝试识别资金流向列
                inflow_col = self._find_column(df, ['主力净流入', 'main_net_inflow'])
                if inflow_col:
                    # 按主力净流入排序
                    df_sorted = df.sort_values(by=inflow_col, ascending=False)
                    # 取TOP5流入
                    top_inflow = df_sorted.head(5)
                    for _, row in top_inflow.iterrows():
                        result["net_inflow_top5"].append({
                            "sector": row.get('名称', ''),
                            "flow": self._safe_float(row.get(inflow_col))
                        })
                    # 取TOP5流出（即净流入最少）
                    top_outflow = df_sorted.tail(5)
                    for _, row in top_outflow.iterrows():
                        result["net_outflow_top5"].append({
                            "sector": row.get('名称', ''),
                            "flow": self._safe_float(row.get(inflow_col))
                        })
                    self._set_cache(cache_key, result)
                    logger.info(f"✅ 板块资金流向: 流入TOP5, 流出TOP5")
                    return result
            else:
                # 备选：使用行业指数涨跌幅作为资金流向的近似
                df = ak.stock_zh_index_spot()
                if df is not None and not df.empty:
                    # 筛选申万行业指数（名称中包含"申万"或"行业"）
                    sector_df = df[df['名称'].str.contains('申万|行业', na=False)]
                    if not sector_df.empty:
                        pct_col = self._find_column(sector_df, ['涨跌幅', 'change'])
                        if pct_col:
                            # 用涨跌幅代替资金流向
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
                            logger.info("✅ 板块资金流向（基于涨跌幅近似）")
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
