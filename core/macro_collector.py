#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观数据采集模块（增量历史版）
不再使用覆盖式缓存，改为通过 MacroHistory 增量追加到 CSV
每日首次运行获取当日数据并追加，后续运行直接跳过
"""

import os
import logging
import time
from datetime import datetime
from typing import Dict, Optional

from core.macro_history import MacroHistory

logger = logging.getLogger(__name__)


class MacroCollector:
    def __init__(self):
        self._history = MacroHistory()
        self._timeout = 8

    # ---------- 通用辅助 ----------
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
        """检查数据是否有效（至少有一个指数或价格）"""
        if not data:
            return False
        for key, value in data.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if sub_value and isinstance(sub_value, dict) and sub_value.get('price') is not None:
                        return True
        return False

    # ============================================================
    # 核心方法：获取并记录当日宏观数据（增量追加）
    # ============================================================
    def refresh_today(self) -> bool:
        """
        获取当日宏观数据并追加到历史
        返回 True 表示成功记录，False 表示今日已存在或获取失败
        """
        # 检查今日是否已记录（快速判断，避免重复获取）
        us_df = self._history._load_csv("macro_us_indices.csv")
        if self._history._is_today_recorded(us_df):
            logger.info("⏭️ 今日宏观数据已存在，无需刷新")
            return False

        logger.info("📊 获取当日宏观数据...")
        result = self._fetch_all_impl()
        if not result or not self._is_data_valid(result):
            logger.warning("⚠️ 宏观数据获取失败，无法记录")
            return False

        # 记录各品种（调用 MacroHistory 的方法）
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
        """获取最新数据（用于推送展示），优先今日数据，否则取最近一日"""
        # 尝试从历史中读取最新数据
        us_indices = self._history.get_latest_us_indices()
        us_giants = self._history.get_latest_tech_giants()
        asia_indices = self._history.get_latest_asia_indices()
        euro_indices = self._history.get_latest_europe_indices()
        commodities = self._history.get_latest_commodities()
        forex = self._history.get_latest_forex()
        a50 = self._history.get_latest_a50()

        # 构造与之前兼容的格式
        result = {
            "us_market": {
                "indices": us_indices,
                "tech_giants": us_giants,
            },
            "asia_market": {
                "indices": asia_indices,
            },
            "europe_market": {
                "indices": euro_indices,
            },
            "commodities": commodities,
            "forex": forex,
            "a50_futures": a50,
            "timestamp": datetime.now().isoformat()
        }
        return result

    # ============================================================
    # 实际获取各数据（内部实现，与之前稳定版相同）
    # ============================================================
    def _fetch_all_impl(self) -> Dict:
        """获取所有宏观数据"""
        result = {
            "us_market": self._fetch_us_market_impl(),
            "asia_market": self._fetch_asia_market_impl(),
            "europe_market": self._fetch_europe_market_impl(),
            "commodities": self._fetch_commodities_impl(),
            "forex": self._fetch_forex_impl(),
            "a50_futures": self._fetch_a50_impl(),
        }
        return result

    def _fetch_us_market_impl(self) -> Dict:
        result = {"indices": {}, "tech_giants": {}, "semiconductor": {}}
        try:
            import akshare as ak
            df = ak.stock_us_spot()
            if df is None or df.empty:
                logger.warning("美股数据为空")
                return result

            # 增强列名识别
            name_col = None
            for col in df.columns:
                if any(k in col for k in ['名称', 'name', 'Name']):
                    name_col = col
                    break
            price_col = None
            for col in df.columns:
                if any(k in col for k in ['最新价', 'price', 'close', '收盘']):
                    price_col = col
                    break
            pct_col = None
            for col in df.columns:
                if any(k in col for k in ['涨跌幅', 'change', 'pct_change']):
                    pct_col = col
                    break

            if not name_col or not price_col:
                logger.warning("美股列名识别失败")
                return result

            # 指数
            for keyword in ["道琼斯", "纳斯达克", "标普500"]:
                matched = df[df[name_col].str.contains(keyword, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][keyword] = {
                        "price": self._safe_float(row.get(price_col)),
                        "pct_change": self._safe_float(row.get(pct_col)) if pct_col else None
                    }

            # 费城半导体
            sem_matched = df[df[name_col].str.contains("费城半导体", na=False)]
            if not sem_matched.empty:
                row = sem_matched.iloc[0]
                result["semiconductor"] = {
                    "price": self._safe_float(row.get(price_col)),
                    "pct_change": self._safe_float(row.get(pct_col)) if pct_col else None
                }

            # 科技巨头
            for giant in ["苹果", "英伟达", "微软", "谷歌", "亚马逊", "Meta", "特斯拉", "美光", "英特尔", "AMD"]:
                matched = df[df[name_col].str.contains(giant, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["tech_giants"][giant] = {
                        "price": self._safe_float(row.get(price_col)),
                        "pct_change": self._safe_float(row.get(pct_col)) if pct_col else None
                    }

            logger.info(f"✅ 美股: {len(result['indices'])}个指数, {len(result['tech_giants'])}只科技股")
            return result
        except Exception as e:
            logger.warning(f"美股获取异常: {e}")
            return result

    def _fetch_asia_market_impl(self) -> Dict:
        result = {"indices": {}}
        try:
            import akshare as ak
            df = None
            for func_name in ['stock_zh_index_spot', 'index_zh_spot']:
                try:
                    if hasattr(ak, func_name):
                        df = getattr(ak, func_name)()
                        if df is not None and not df.empty:
                            break
                except:
                    continue
            if df is None or df.empty:
                try:
                    df = ak.index_zh_spot()
                except:
                    pass
            if df is None or df.empty:
                logger.warning("亚太数据为空")
                return result

            name_col = self._find_column(df, ['名称', 'name', 'Name'])
            price_col = self._find_column(df, ['最新价', 'price', 'close'])
            pct_col = self._find_column(df, ['涨跌幅', 'change', 'pct_change'])
            if not name_col or not price_col:
                logger.warning("亚太列名不匹配")
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
            logger.info(f"✅ 亚太: {len(result['indices'])}个指数")
            return result
        except Exception as e:
            logger.warning(f"亚太获取异常: {e}")
            return result

    def _fetch_europe_market_impl(self) -> Dict:
        result = {"indices": {}}
        try:
            import akshare as ak
            df = None
            for func_name in ['stock_zh_index_spot', 'index_zh_spot']:
                try:
                    if hasattr(ak, func_name):
                        df = getattr(ak, func_name)()
                        if df is not None and not df.empty:
                            break
                except:
                    continue
            if df is None or df.empty:
                try:
                    df = ak.index_zh_spot()
                except:
                    pass
            if df is None or df.empty:
                logger.warning("欧洲数据为空")
                return result

            name_col = self._find_column(df, ['名称', 'name', 'Name'])
            price_col = self._find_column(df, ['最新价', 'price', 'close'])
            pct_col = self._find_column(df, ['涨跌幅', 'change', 'pct_change'])
            if not name_col or not price_col:
                logger.warning("欧洲列名不匹配")
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
            logger.info(f"✅ 欧洲: {len(result['indices'])}个指数")
            return result
        except Exception as e:
            logger.warning(f"欧洲获取异常: {e}")
            return result

    def _fetch_commodities_impl(self) -> Dict:
        result = {"oil": {}, "gold": {}}
        try:
            import akshare as ak
            for symbol, name in [("CL", "WTI"), ("B", "布伦特")]:
                try:
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
                except:
                    pass
            try:
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
            except:
                pass
            return result
        except Exception as e:
            logger.warning(f"大宗商品获取异常: {e}")
            return result

    def _fetch_forex_impl(self) -> Dict:
        result = {"usd_cny": {}}
        try:
            import akshare as ak
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
                            if pct_col:
                                result["usd_cny"]["pct_change"] = self._safe_float(row.get(pct_col))
            except:
                pass
            try:
                df = ak.currency_rates_central()
                if df is not None and not df.empty:
                    name_col = self._find_column(df, ['货币名称', 'name'])
                    price_col = self._find_column(df, ['最新价', 'price'])
                    if name_col and price_col:
                        matched = df[df[name_col].str.contains('美元', na=False)]
                        if not matched.empty:
                            row = matched.iloc[0]
                            result["usd_cny"]["central"] = self._safe_float(row.get(price_col))
            except:
                pass
            return result
        except Exception as e:
            logger.warning(f"汇率获取异常: {e}")
            return result

    def _fetch_a50_impl(self) -> Dict:
        result = {"price": None, "pct_change": None}
        try:
            import akshare as ak
            for symbol in ["A50", "SGXCN"]:
                try:
                    df = ak.futures_foreign_main_sina(symbol=symbol)
                    if df is not None and not df.empty:
                        latest = df.iloc[-1]
                        price_col = self._find_column(df, ['最新价', 'price'])
                        pct_col = self._find_column(df, ['涨跌幅', 'change'])
                        if price_col:
                            result["price"] = self._safe_float(latest.get(price_col))
                            if pct_col:
                                result["pct_change"] = self._safe_float(latest.get(pct_col))
                            if result["price"] is not None:
                                break
                except:
                    continue
            return result
        except Exception as e:
            logger.warning(f"A50期货获取异常: {e}")
            return result
