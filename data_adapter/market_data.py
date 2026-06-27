#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场数据采集模块（稳定版 - JSON缓存）
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class MarketDataCollector:
    def __init__(self, storage_dir: str = "memory_data/"):
        self.storage_dir = storage_dir
        self._ensure_storage_dir()
        self.today = datetime.now().strftime("%Y-%m-%d")
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
        if not data:
            return False
        if 'timestamp' in data and self.today in data['timestamp']:
            return True
        return False

    def get_indices(self, force_refresh: bool = False) -> Dict:
        cache_file = "market_indices.json"
        if not force_refresh:
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
        result = {"indices": {}, "timestamp": datetime.now().isoformat()}
        try:
            import akshare as ak
            df = None
            for func in [ak.index_zh_spot, ak.stock_zh_index_spot]:
                try:
                    df = func()
                    if df is not None and not df.empty:
                        break
                except:
                    continue
            if df is None or df.empty:
                return result
            name_col = self._find_column(df, ['名称', 'name', 'Name'])
            code_col = self._find_column(df, ['代码', 'code'])
            price_col = self._find_column(df, ['最新价', 'price', 'close'])
            pct_col = self._find_column(df, ['涨跌幅', 'change', 'pct_change'])
            if not name_col or not price_col:
                return result
            index_map = {"上证指数": "000001.SH", "深证成指": "399001.SZ", "创业板指": "399006.SZ", "科创50": "000688.SH", "北证50": "899050.BJ"}
            for name, code in index_map.items():
                matched = df[df[code_col] == code] if code_col in df.columns else pd.DataFrame()
                if matched.empty:
                    matched = df[df[name_col].str.contains(name, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][name] = {"code": code, "price": self._safe_float(row.get(price_col)), "pct_change": self._safe_float(row.get(pct_col)) if pct_col else None, "date": datetime.now().strftime("%Y-%m-%d")}
            logger.info(f"✅ 获取到 {len(result['indices'])} 个指数数据")
            return result
        except Exception as e:
            logger.warning(f"指数获取异常: {e}")
            return result

    def get_market_stats(self, force_refresh: bool = False) -> Dict:
        cache_file = "market_stats.json"
        if not force_refresh:
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
        result = {"up": 0, "down": 0, "flat": 0, "total": 0, "timestamp": datetime.now().isoformat()}
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
                    logger.info(f"✅ 涨跌家数: 上涨{up}家, 下跌{down}家")
                    return result
        except Exception as e:
            logger.warning(f"涨跌家数获取失败: {e}")
        return result

    def get_sector_flow(self, force_refresh: bool = False) -> Dict:
        cache_file = "sector_flow.json"
        if not force_refresh:
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
        result = {"net_inflow_top5": [], "net_outflow_top5": [], "timestamp": datetime.now().isoformat()}
        try:
            import akshare as ak
            df = ak.stock_sector_spot()
            if df is not None and not df.empty:
                inflow_col = self._find_column(df, ['主力净流入', 'main_net_inflow'])
                if inflow_col:
                    df_sorted = df.sort_values(by=inflow_col, ascending=False)
                    for _, row in df_sorted.head(5).iterrows():
                        result["net_inflow_top5"].append({"sector": row.get('名称', ''), "flow": self._safe_float(row.get(inflow_col))})
                    for _, row in df_sorted.tail(5).iterrows():
                        result["net_outflow_top5"].append({"sector": row.get('名称', ''), "flow": self._safe_float(row.get(inflow_col))})
                    logger.info("✅ 板块资金流向获取成功")
                    return result
        except Exception as e:
            logger.warning(f"板块资金流向获取失败: {e}")
        return result
