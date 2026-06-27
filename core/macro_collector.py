#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观数据采集模块（增量历史版）
永久保存历史，每日追加一行
"""

import os
import logging
import time
import akshare as ak
from datetime import datetime
from typing import Dict, Optional

from core.macro_history import MacroHistory

logger = logging.getLogger(__name__)


class MacroCollector:
    def __init__(self):
        self._history = MacroHistory()
        self._timeout = 8

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

    def _is_data_valid(self, data: Dict) -> bool:
        if not data:
            return False
        for key, value in data.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if sub_value and isinstance(sub_value, dict) and sub_value.get('price') is not None:
                        return True
        return False

    # ============================================================
    # 核心方法：刷新今日数据（增量追加）
    # ============================================================
    def refresh_today(self) -> bool:
        """获取当日宏观数据并追加到历史，返回 True 表示新增记录"""
        # 检查今日是否已记录
        us_df = self._history._load_csv("macro_us_indices.csv")
        if self._history._is_today_recorded(us_df):
            logger.info("⏭️ 今日宏观数据已存在，无需刷新")
            return False

        logger.info("📊 刷新宏观数据（今日首条）...")
        result = self._fetch_all_impl()
        if not result or not self._is_data_valid(result):
            logger.warning("⚠️ 宏观数据获取失败，无法记录")
            return False

        # 记录各品种
        us = result.get("us_market", {})
        self._history.record_us_indices(us.get("indices", {}))
        self._history.record_tech_giants(us.get("tech_giants", {}))

        asia = result.get("asia_market", {})
        self._history.record_asia_indices(asia.get("indices", {}))

        euro = result.get("europe_market", {})
        self._history.record_europe_indices(euro.get("indices", {}))

        comm = result.get("commodities", {})
        self._history.record_commodities(comm.get("oil", {}), comm.get("gold", {}))

        forex = result.get("forex", {})
        self._history.record_forex(forex.get("usd_cny", {}))

        a50 = result.get("a50_futures", {})
        self._history.record_a50(a50)

        logger.info("✅ 当日宏观数据已追加到历史")
        return True

    def get_latest_data(self) -> Dict:
        """获取最新数据（用于推送展示）"""
        return {
            "us_market": {
                "indices": self._history.get_latest_us_indices(),
                "tech_giants": self._history.get_latest_tech_giants(),
            },
            "asia_market": {
                "indices": self._history.get_latest_asia_indices(),
            },
            "europe_market": {
                "indices": self._history.get_latest_europe_indices(),
            },
            "commodities": self._history.get_latest_commodities(),
            "forex": self._history.get_latest_forex(),
            "a50_futures": self._history.get_latest_a50(),
            "timestamp": datetime.now().isoformat()
        }

    # ============================================================
    # 各品种获取实现（与之前相同，确保可用）
    # ============================================================
    def _fetch_all_impl(self) -> Dict:
        return {
            "us_market": self._fetch_us_market_impl(),
            "asia_market": self._fetch_asia_market_impl(),
            "europe_market": self._fetch_europe_market_impl(),
            "commodities": self._fetch_commodities_impl(),
            "forex": self._fetch_forex_impl(),
            "a50_futures": self._fetch_a50_impl(),
        }

    def _fetch_us_market_impl(self) -> Dict:
        result = {"indices": {}, "tech_giants": {}}
        try:
            df = ak.stock_us_spot()
            if df is None or df.empty:
                return result
            name_col = self._find_column(df, ['名称', 'name', 'Name'])
            price_col = self._find_column(df, ['最新价', 'price', 'close'])
            pct_col = self._find_column(df, ['涨跌幅', 'change', 'pct_change'])
            if not name_col or not price_col:
                return result
            for keyword in ["道琼斯", "纳斯达克", "标普500"]:
                matched = df[df[name_col].str.contains(keyword, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][keyword] = {
                        "price": self._safe_float(row.get(price_col)),
                        "pct_change": self._safe_float(row.get(pct_col)) if pct_col else None
                    }
            for giant in ["苹果", "英伟达", "微软", "谷歌", "亚马逊", "Meta", "特斯拉", "美光", "英特尔", "AMD"]:
                matched = df[df[name_col].str.contains(giant, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["tech_giants"][giant] = {
                        "price": self._safe_float(row.get(price_col)),
                        "pct_change": self._safe_float(row.get(pct_col)) if pct_col else None
                    }
        except Exception as e:
            logger.warning(f"美股获取异常: {e}")
        return result

    def _fetch_asia_market_impl(self) -> Dict:
        result = {"indices": {}}
        try:
            df = ak.index_zh_spot() if hasattr(ak, 'index_zh_spot') else ak.stock_zh_index_spot()
            if df is None or df.empty:
                return result
            name_col = self._find_column(df, ['名称', 'name'])
            price_col = self._find_column(df, ['最新价', 'price'])
            pct_col = self._find_column(df, ['涨跌幅', 'change'])
            if not name_col or not price_col:
                return result
            asia_map = {"日经225": "N225", "韩国KOSPI": "KOSPI", "恒生指数": "HSI", "台湾加权": "TWII"}
            for name, code in asia_map.items():
                matched = df[df[name_col].str.contains(name, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][code] = {
                        "price": self._safe_float(row.get(price_col)),
                        "pct_change": self._safe_float(row.get(pct_col)) if pct_col else None
                    }
        except Exception as e:
            logger.warning(f"亚太获取异常: {e}")
        return result

    def _fetch_europe_market_impl(self) -> Dict:
        result = {"indices": {}}
        try:
            df = ak.index_zh_spot() if hasattr(ak, 'index_zh_spot') else ak.stock_zh_index_spot()
            if df is None or df.empty:
                return result
            name_col = self._find_column(df, ['名称', 'name'])
            price_col = self._find_column(df, ['最新价', 'price'])
            pct_col = self._find_column(df, ['涨跌幅', 'change'])
            if not name_col or not price_col:
                return result
            europe_map = {"德国DAX": "GDAXI", "英国富时": "FTSE", "法国CAC": "FCHI"}
            for name, code in europe_map.items():
                matched = df[df[name_col].str.contains(name, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][code] = {
                        "price": self._safe_float(row.get(price_col)),
                        "pct_change": self._safe_float(row.get(pct_col)) if pct_col else None
                    }
        except Exception as e:
            logger.warning(f"欧洲获取异常: {e}")
        return result

    def _fetch_commodities_impl(self) -> Dict:
        result = {"oil": {}, "gold": {}}
        try:
            for symbol, name in [("CL", "WTI"), ("B", "布伦特")]:
                df = ak.futures_foreign_main_sina(symbol=symbol)
                if df is not None and not df.empty:
                    latest = df.iloc[-1]
                    price_col = self._find_column(df, ['最新价', 'price'])
                    pct_col = self._find_column(df, ['涨跌幅', 'change'])
                    if price_col:
                        result["oil"][name] = {
                            "price": self._safe_float(latest.get(price_col)),
                            "pct_change": self._safe_float(latest.get(pct_col)) if pct_col else None
                        }
            gold_df = ak.futures_foreign_main_sina(symbol="GC")
            if gold_df is not None and not gold_df.empty:
                latest = gold_df.iloc[-1]
                price_col = self._find_column(gold_df, ['最新价', 'price'])
                pct_col = self._find_column(gold_df, ['涨跌幅', 'change'])
                if price_col:
                    result["gold"] = {
                        "price": self._safe_float(latest.get(price_col)),
                        "pct_change": self._safe_float(latest.get(pct_col)) if pct_col else None
                    }
        except Exception as e:
            logger.warning(f"大宗商品获取异常: {e}")
        return result

    def _fetch_forex_impl(self) -> Dict:
        result = {"usd_cny": {}}
        try:
            df = ak.currency_rates()
            if df is not None and not df.empty:
                name_col = self._find_column(df, ['货币名称', 'name'])
                price_col = self._find_column(df, ['最新价', 'price'])
                pct_col = self._find_column(df, ['涨跌幅', 'change'])
                if name_col and price_col:
                    matched = df[df[name_col].str.contains('美元', na=False)]
                    if not matched.empty:
                        row = matched.iloc[0]
                        result["usd_cny"]["onshore"] = self._safe_float(row.get(price_col))
                        result["usd_cny"]["pct_change"] = self._safe_float(row.get(pct_col)) if pct_col else None
            df_central = ak.currency_rates_central()
            if df_central is not None and not df_central.empty:
                name_col = self._find_column(df_central, ['货币名称', 'name'])
                price_col = self._find_column(df_central, ['最新价', 'price'])
                if name_col and price_col:
                    matched = df_central[df_central[name_col].str.contains('美元', na=False)]
                    if not matched.empty:
                        row = matched.iloc[0]
                        result["usd_cny"]["central"] = self._safe_float(row.get(price_col))
        except Exception as e:
            logger.warning(f"汇率获取异常: {e}")
        return result

    def _fetch_a50_impl(self) -> Dict:
        result = {"price": None, "pct_change": None}
        try:
            for symbol in ["A50", "SGXCN"]:
                df = ak.futures_foreign_main_sina(symbol=symbol)
                if df is not None and not df.empty:
                    latest = df.iloc[-1]
                    price_col = self._find_column(df, ['最新价', 'price'])
                    pct_col = self._find_column(df, ['涨跌幅', 'change'])
                    if price_col:
                        result["price"] = self._safe_float(latest.get(price_col))
                        result["pct_change"] = self._safe_float(latest.get(pct_col)) if pct_col else None
                        if result["price"] is not None:
                            break
        except Exception as e:
            logger.warning(f"A50期货获取异常: {e}")
        return result
