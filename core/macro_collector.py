#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观数据采集模块（P0修复版）
增强列名识别，多备选接口，确保数据获取
"""

import os
import logging
import time
import json
import concurrent.futures
from datetime import datetime
from typing import Dict, Optional

os.environ['TQDM_DISABLE'] = '1'

from core.macro_cache import MacroCache

logger = logging.getLogger(__name__)


class MacroCollector:
    def __init__(self):
        self._cache = MacroCache()
        self._retry_count = 1
        self._retry_delay = [2]
        self._timeout = 8
        logger.info(f"📁 宏观缓存目录: {self._cache.storage_dir}")

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

    def _get_empty_result(self) -> Dict:
        return {
            "indices": {},
            "semiconductor": {},
            "tech_giants": {},
            "oil": {},
            "gold": {},
            "usd_cny": {},
            "price": None,
            "pct_change": None,
            "data_source": "empty",
            "timestamp": datetime.now().isoformat()
        }

    def _is_empty_result(self, data) -> bool:
        if data is None:
            return True
        if isinstance(data, dict):
            for key, value in data.items():
                if value and not self._is_empty_result(value):
                    return False
            return True
        if isinstance(data, list):
            return len(data) == 0
        return False

    # ---------- 获取并缓存宏观快照 ----------
    def get_macro_snapshot(self, force_refresh: bool = False) -> Dict:
        cache_file = os.path.join(self._cache.storage_dir, "macro_snapshot.json")

        if not force_refresh and os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                # 检查是否包含今日数据
                if '_cache_date' in data and data['_cache_date'] == datetime.now().strftime("%Y-%m-%d"):
                    logger.info(f"✅ 使用今日缓存宏观快照: {cache_file}")
                    return data.get('data', {})
            except:
                pass

        logger.info("📊 刷新宏观数据...")
        result = {
            "us_market": self._fetch_us_market_impl(),
            "asia_market": self._fetch_asia_market_impl(),
            "europe_market": self._fetch_europe_market_impl(),
            "commodities": self._fetch_commodities_impl(),
            "forex": self._fetch_forex_impl(),
            "a50_futures": self._fetch_a50_impl(),
            "timestamp": datetime.now().isoformat()
        }
        try:
            with open(cache_file, 'w') as f:
                json.dump({
                    '_cache_date': datetime.now().strftime("%Y-%m-%d"),
                    '_cache_time': datetime.now().isoformat(),
                    'data': result
                }, f, ensure_ascii=False, indent=2)
            logger.info(f"✅ 宏观快照已保存: {cache_file}")
        except Exception as e:
            logger.warning(f"保存宏观快照失败: {e}")
        return result

    def format_for_push(self, force_refresh: bool = False) -> Dict:
        snapshot = self.get_macro_snapshot(force_refresh)
        return {
            "us_market": self._format_us_market(snapshot.get("us_market", {})),
            "asia_market": self._format_asia_market(snapshot.get("asia_market", {})),
            "europe_market": self._format_europe_market(snapshot.get("europe_market", {})),
            "commodities": self._format_commodities(snapshot.get("commodities", {})),
            "forex": self._format_forex(snapshot.get("forex", {})),
            "a50_futures": self._format_a50(snapshot.get("a50_futures", {})),
            "timestamp": snapshot.get("timestamp", "")
        }

    # ============================================================
    # 美股获取（增强列名识别）
    # ============================================================
    def _fetch_us_market_impl(self) -> Dict:
        result = {"indices": {}, "semiconductor": {}, "tech_giants": {}, "data_source": "AKShare", "timestamp": datetime.now().isoformat()}
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
                        "name": keyword,
                        "price": self._safe_float(row.get(price_col)),
                        "pct_change": self._safe_float(row.get(pct_col)) if pct_col else None
                    }

            # 费城半导体
            sem_matched = df[df[name_col].str.contains("费城半导体", na=False)]
            if not sem_matched.empty:
                row = sem_matched.iloc[0]
                result["semiconductor"] = {
                    "name": "费城半导体",
                    "price": self._safe_float(row.get(price_col)),
                    "pct_change": self._safe_float(row.get(pct_col)) if pct_col else None
                }

            # 科技巨头
            for giant in ["苹果", "英伟达", "微软", "谷歌", "亚马逊", "Meta", "特斯拉", "美光", "英特尔", "AMD"]:
                matched = df[df[name_col].str.contains(giant, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["tech_giants"][giant] = {
                        "name": giant,
                        "price": self._safe_float(row.get(price_col)),
                        "pct_change": self._safe_float(row.get(pct_col)) if pct_col else None
                    }

            logger.info(f"✅ 美股: {len(result['indices'])}个指数, {len(result['tech_giants'])}只科技股")
            return result
        except Exception as e:
            logger.warning(f"美股获取异常: {e}")
            return result

    # ============================================================
    # 亚太市场（多备选接口）
    # ============================================================
    def _fetch_asia_market_impl(self) -> Dict:
        result = {"indices": {}, "data_source": "AKShare", "timestamp": datetime.now().isoformat()}
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
                        "name": name,
                        "price": self._safe_float(row.get(price_col)),
                        "pct_change": self._safe_float(row.get(pct_col)) if pct_col else None
                    }
            logger.info(f"✅ 亚太: {len(result['indices'])}个指数")
            return result
        except Exception as e:
            logger.warning(f"亚太获取异常: {e}")
            return result

    # ============================================================
    # 欧洲市场（同亚太）
    # ============================================================
    def _fetch_europe_market_impl(self) -> Dict:
        result = {"indices": {}, "data_source": "AKShare", "timestamp": datetime.now().isoformat()}
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
                        "name": name,
                        "price": self._safe_float(row.get(price_col)),
                        "pct_change": self._safe_float(row.get(pct_col)) if pct_col else None
                    }
            logger.info(f"✅ 欧洲: {len(result['indices'])}个指数")
            return result
        except Exception as e:
            logger.warning(f"欧洲获取异常: {e}")
            return result

    # ============================================================
    # 大宗商品（保持不变，已有容错）
    # ============================================================
    def _fetch_commodities_impl(self) -> Dict:
        result = {"oil": {}, "gold": {}, "data_source": "AKShare", "timestamp": datetime.now().isoformat()}
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
                                "name": name,
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

    # ============================================================
    # 汇率（同）
    # ============================================================
    def _fetch_forex_impl(self) -> Dict:
        result = {"usd_cny": {}, "data_source": "AKShare", "timestamp": datetime.now().isoformat()}
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

    # ============================================================
    # A50期货
    # ============================================================
    def _fetch_a50_impl(self) -> Dict:
        result = {"price": None, "pct_change": None, "data_source": "AKShare", "timestamp": datetime.now().isoformat()}
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

    # ============================================================
    # 格式化方法（兼容空值）
    # ============================================================
    def _format_us_market(self, data: Dict) -> Dict:
        result = {"indices": [], "tech_giants": [], "semiconductor": None}
        for name, idx in data.get("indices", {}).items():
            if idx.get("price") is not None:
                result["indices"].append({"name": name, "price": idx.get("price"), "pct_change": idx.get("pct_change")})
        sem = data.get("semiconductor", {})
        if sem.get("price") is not None:
            result["semiconductor"] = {"name": "费城半导体", "price": sem.get("price"), "pct_change": sem.get("pct_change")}
        for name, giant in data.get("tech_giants", {}).items():
            if giant.get("price") is not None:
                result["tech_giants"].append({"name": name, "price": giant.get("price"), "pct_change": giant.get("pct_change")})
        return result

    def _format_asia_market(self, data: Dict) -> Dict:
        result = {"indices": []}
        for code, idx in data.get("indices", {}).items():
            if idx.get("price") is not None:
                result["indices"].append({"name": idx.get("name", code), "price": idx.get("price"), "pct_change": idx.get("pct_change")})
        return result

    def _format_europe_market(self, data: Dict) -> Dict:
        result = {"indices": []}
        for code, idx in data.get("indices", {}).items():
            if idx.get("price") is not None:
                result["indices"].append({"name": idx.get("name", code), "price": idx.get("price"), "pct_change": idx.get("pct_change")})
        return result

    def _format_commodities(self, data: Dict) -> Dict:
        result = {"oil": [], "gold": None}
        for name, oil in data.get("oil", {}).items():
            if oil.get("price") is not None:
                result["oil"].append({"name": oil.get("name", name), "price": oil.get("price"), "pct_change": oil.get("pct_change")})
        gold = data.get("gold", {})
        if gold.get("price") is not None:
            result["gold"] = {"price": gold.get("price"), "pct_change": gold.get("pct_change")}
        return result

    def _format_forex(self, data: Dict) -> Dict:
        result = {"usd_cny": {}}
        usd = data.get("usd_cny", {})
        if usd.get("onshore") is not None:
            result["usd_cny"]["onshore"] = usd.get("onshore")
        if usd.get("central") is not None:
            result["usd_cny"]["central"] = usd.get("central")
        if usd.get("pct_change") is not None:
            result["usd_cny"]["pct_change"] = usd.get("pct_change")
        return result

    def _format_a50(self, data: Dict) -> Dict:
        result = {}
        if data.get("price") is not None:
            result["price"] = data.get("price")
        if data.get("pct_change") is not None:
            result["pct_change"] = data.get("pct_change")
        return result
