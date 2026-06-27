#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场数据采集模块（永久缓存+每日增量）
提供：多指数行情、涨跌家数、板块资金流向
数据永久存储到 memory_data/，自动判断是否今日，过期则刷新
"""

import os
import json
import pandas as pd
import logging
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class MarketDataCollector:
    """市场数据采集器（永久缓存版，无强制刷新）"""

    def __init__(self, storage_dir: str = "memory_data/"):
        self.storage_dir = storage_dir
        self.today = datetime.now().strftime("%Y-%m-%d")
        self._ensure_storage_dir()
        logger.info(f"📁 市场数据缓存目录: {os.path.abspath(self.storage_dir)}")

    def _ensure_storage_dir(self):
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir, exist_ok=True)

    def _get_file_path(self, filename: str) -> str:
        return os.path.join(self.storage_dir, filename)

    def _save_json(self, filename: str, data: Dict) -> str:
        file_path = self._get_file_path(filename)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return file_path

    def _load_json(self, filename: str) -> Optional[Dict]:
        file_path = self._get_file_path(filename)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return None
        return None

    # ---------- 辅助方法 ----------
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

    def _is_data_today(self, data: Dict) -> bool:
        """检查缓存数据是否包含今日记录"""
        if not data:
            return False
        if 'timestamp' in data and self.today in data['timestamp']:
            return True
        if 'indices' in data:
            for idx in data['indices'].values():
                if isinstance(idx, dict) and idx.get('date') == self.today:
                    return True
        return False

    # ============================================================
    # 1. 多指数行情（永久缓存，自动判断日期）
    # ============================================================
    def get_indices(self) -> Dict:
        """
        获取主要指数行情
        如果缓存存在且是今日数据，直接返回；否则刷新
        """
        cache_file = "market_indices.json"
        cached = self._load_json(cache_file)
        if cached and self._is_data_today(cached):
            logger.info(f"✅ 从缓存读取指数数据: {cache_file}")
            return cached

        logger.info("📊 刷新指数数据...")
        result = self._fetch_indices_impl()
        if result.get('indices'):
            self._save_json(cache_file, result)
        return result

    def _fetch_indices_impl(self) -> Dict:
        """实际获取指数数据（多备选接口）"""
        result = {"indices": {}, "timestamp": datetime.now().isoformat()}

        try:
            import akshare as ak
            # 尝试多个接口
            df = None
            for func in [ak.index_zh_spot, ak.stock_zh_index_spot]:
                try:
                    df = func()
                    if df is not None and not df.empty:
                        break
                except:
                    continue
            if df is None or df.empty:
                logger.warning("所有指数接口均失败")
                return result

            name_col = self._find_column(df, ['名称', 'name', 'Name'])
            code_col = self._find_column(df, ['代码', 'code'])
            price_col = self._find_column(df, ['最新价', 'price', 'close'])
            pct_col = self._find_column(df, ['涨跌幅', 'change', 'pct_change'])
            amount_col = self._find_column(df, ['成交额', 'amount'])

            if not name_col or not price_col:
                logger.warning("指数列名识别失败")
                return result

            index_map = {
                "上证指数": ["000001.SH", "上证指数"],
                "深证成指": ["399001.SZ", "深证成指"],
                "创业板指": ["399006.SZ", "创业板指"],
                "科创50": ["000688.SH", "科创50"],
                "北证50": ["899050.BJ", "北证50"]
            }

            for name, (code, keyword) in index_map.items():
                matched = df[df[code_col] == code] if code_col in df.columns else pd.DataFrame()
                if matched.empty:
                    matched = df[df[name_col].str.contains(keyword, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][name] = {
                        "code": code,
                        "price": self._safe_float(row.get(price_col)),
                        "pct_change": self._safe_float(row.get(pct_col)) if pct_col else None,
                        "amount": self._safe_float(row.get(amount_col)) if amount_col else None,
                        "date": datetime.now().strftime("%Y-%m-%d")
                    }

            logger.info(f"✅ 获取到 {len(result['indices'])} 个指数数据")
            return result

        except Exception as e:
            logger.warning(f"指数获取异常: {e}")
            return result

    # ============================================================
    # 2. 涨跌家数统计（永久缓存）
    # ============================================================
    def get_market_stats(self) -> Dict:
        """获取市场涨跌家数统计"""
        cache_file = "market_stats.json"
        cached = self._load_json(cache_file)
        if cached and self._is_data_today(cached):
            logger.info(f"✅ 从缓存读取涨跌家数: {cache_file}")
            return cached

        logger.info("📊 刷新涨跌家数...")
        result = self._fetch_stats_impl()
        if result.get('total', 0) > 0:
            self._save_json(cache_file, result)
        return result

    def _fetch_stats_impl(self) -> Dict:
        """实际获取涨跌家数"""
        result = {
            "up": 0,
            "down": 0,
            "flat": 0,
            "total": 0,
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak
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
                    logger.info(f"✅ 涨跌家数: 上涨{up}家, 下跌{down}家, 平盘{flat}家")
                    return result
        except Exception as e:
            logger.warning(f"涨跌家数获取失败: {e}")
        return result

    # ============================================================
    # 3. 板块资金流向TOP5（永久缓存）
    # ============================================================
    def get_sector_flow(self) -> Dict:
        """获取板块资金流向TOP5"""
        cache_file = "sector_flow.json"
        cached = self._load_json(cache_file)
        if cached and self._is_data_today(cached):
            logger.info(f"✅ 从缓存读取板块资金流向: {cache_file}")
            return cached

        logger.info("📊 刷新板块资金流向...")
        result = self._fetch_flow_impl()
        if result.get('net_inflow_top5'):
            self._save_json(cache_file, result)
        return result

    def _fetch_flow_impl(self) -> Dict:
        """实际获取板块资金流向（使用备选方案）"""
        result = {
            "net_inflow_top5": [],
            "net_outflow_top5": [],
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak
            df = ak.stock_sector_spot()
            if df is not None and not df.empty:
                inflow_col = self._find_column(df, ['主力净流入', 'main_net_inflow'])
                if inflow_col:
                    df_sorted = df.sort_values(by=inflow_col, ascending=False)
                    for _, row in df_sorted.head(5).iterrows():
                        result["net_inflow_top5"].append({
                            "sector": row.get('名称', ''),
                            "flow": self._safe_float(row.get(inflow_col))
                        })
                    for _, row in df_sorted.tail(5).iterrows():
                        result["net_outflow_top5"].append({
                            "sector": row.get('名称', ''),
                            "flow": self._safe_float(row.get(inflow_col))
                        })
                    logger.info("✅ 板块资金流向: 流入TOP5, 流出TOP5")
                    return result
        except Exception as e:
            logger.warning(f"板块资金流向获取失败: {e}")

        # 备选方案：返回空
        return result
