#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观数据采集模块（强化容错 + 接口适配）
修正：AKShare 接口变更 + 缓存强制写入
"""

import os
import logging
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class MacroCollector:
    """
    宏观数据采集器（强化容错版）
    采集范围：美股、欧股、亚太、大宗商品、汇率、A50期货
    """

    def __init__(self):
        self._cache = {}
        self._cache_ttl = 300  # 5分钟缓存
        self._retry_count = 3
        self._retry_delay = [1, 2, 4]
        self._last_success_data = {}
        self._has_ever_succeeded = False
        # 强制缓存目录
        self._cache_dir = "memory_data/"
        os.makedirs(self._cache_dir, exist_ok=True)

    def _is_cached_valid(self, key: str) -> bool:
        if key in self._cache:
            cached_time, _ = self._cache[key]
            if (datetime.now() - cached_time).total_seconds() < self._cache_ttl:
                return True
        return False

    def _get_cached(self, key: str) -> Any:
        if key in self._cache:
            _, data = self._cache[key]
            return data
        return None

    def _set_cache(self, key: str, data: Any):
        self._cache[key] = (datetime.now(), data)

    def _force_write_cache(self, key: str, data: Any):
        """强制写入缓存文件（即使数据为空）"""
        try:
            cache_file = os.path.join(self._cache_dir, f"macro_{key}.json")
            cache_data = {
                '_cache_time': datetime.now().isoformat(),
                'data': data
            }
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            logger.info(f"✅ 缓存已写入: {cache_file}")
        except Exception as e:
            logger.warning(f"⚠️ 缓存写入失败: {e}")

    def _safe_fetch(self, func, cache_key: str) -> Any:
        """安全获取数据（缓存优先 + 重试 + 降级）"""
        # 1. 尝试从文件缓存读取
        cache_file = os.path.join(self._cache_dir, f"macro_{cache_key}.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                cache_time = data.get('_cache_time', '')
                if cache_time:
                    cache_dt = datetime.fromisoformat(cache_time)
                    if (datetime.now() - cache_dt).total_seconds() < self._cache_ttl * 2:
                        logger.info(f"✅ 从缓存文件加载 {cache_key}")
                        return data.get('data', {})
            except:
                pass

        # 2. 执行实时获取
        last_error = None
        for attempt in range(self._retry_count):
            try:
                result = func()
                if result is not None:
                    # 保存到内存和文件
                    self._set_cache(cache_key, result)
                    self._force_write_cache(cache_key, result)
                    return result
            except Exception as e:
                last_error = e
                if attempt < self._retry_count - 1:
                    time.sleep(self._retry_delay[attempt])
                    continue

        # 3. 获取失败，尝试用之前保存的缓存（即使过期）
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                logger.warning(f"⚠️ {cache_key} 获取失败，使用过期缓存")
                return data.get('data', {})
            except:
                pass

        # 4. 最终返回空数据
        logger.warning(f"⚠️ {cache_key} 完全不可用，返回空数据")
        return {}

    # ============================================================
    # 各数据获取实现（修正接口）
    # ============================================================
    def _fetch_us_market_impl(self) -> Dict:
        result = {
            "indices": {},
            "semiconductor": {},
            "tech_giants": {},
            "data_source": "AKShare",
            "timestamp": datetime.now().isoformat()
        }
        try:
            import akshare as ak
            df = ak.stock_us_spot()
            if df is None or df.empty:
                return result
            # 列名可能是 '名称' 或 'name'，尝试适配
            name_col = None
            for col in df.columns:
                if '名' in col or 'name' in col.lower():
                    name_col = col
                    break
            if name_col is None:
                return result
            # 指数
            index_keywords = ["道琼斯", "纳斯达克", "标普500"]
            for keyword in index_keywords:
                matched = df[df[name_col].str.contains(keyword, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][keyword] = {
                        "name": keyword,
                        "price": self._safe_float(row.get('最新价') or row.get('price')),
                        "pct_change": self._safe_float(row.get('涨跌幅') or row.get('pct_chg'))
                    }
            # 费城半导体
            sem_matched = df[df[name_col].str.contains("费城半导体", na=False)]
            if not sem_matched.empty:
                row = sem_matched.iloc[0]
                result["semiconductor"] = {
                    "name": "费城半导体",
                    "price": self._safe_float(row.get('最新价') or row.get('price')),
                    "pct_change": self._safe_float(row.get('涨跌幅') or row.get('pct_chg'))
                }
            # 科技巨头
            tech_giants = ["苹果", "英伟达", "微软", "谷歌", "亚马逊", "Meta", "特斯拉", "美光", "英特尔", "AMD"]
            for giant in tech_giants:
                matched = df[df[name_col].str.contains(giant, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["tech_giants"][giant] = {
                        "name": giant,
                        "price": self._safe_float(row.get('最新价') or row.get('price')),
                        "pct_change": self._safe_float(row.get('涨跌幅') or row.get('pct_chg'))
                    }
        except Exception as e:
            logger.warning(f"美股获取异常: {e}")
        return result

    def _fetch_asia_market_impl(self) -> Dict:
        result = {"indices": {}, "data_source": "AKShare", "timestamp": datetime.now().isoformat()}
        try:
            import akshare as ak
            # 使用最新的指数接口
            df = ak.stock_zh_index_spot()
            if df is None or df.empty:
                # 尝试备用接口
                df = ak.stock_zh_index_spot()
            if df is None or df.empty:
                return result
            name_col = None
            for col in df.columns:
                if '名' in col or 'name' in col.lower():
                    name_col = col
                    break
            if name_col is None:
                return result
            asia_map = {
                "日经225": "N225",
                "韩国KOSPI": "KOSPI",
                "恒生指数": "HSI",
                "台湾加权": "TWII"
            }
            for name, code in asia_map.items():
                matched = df[df[name_col].str.contains(name, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][code] = {
                        "name": name,
                        "price": self._safe_float(row.get('最新价') or row.get('price')),
                        "pct_change": self._safe_float(row.get('涨跌幅') or row.get('pct_chg'))
                    }
        except Exception as e:
            logger.warning(f"亚太获取异常: {e}")
        return result

    def _fetch_europe_market_impl(self) -> Dict:
        result = {"indices": {}, "data_source": "AKShare", "timestamp": datetime.now().isoformat()}
        try:
            import akshare as ak
            df = ak.stock_zh_index_spot()
            if df is None or df.empty:
                return result
            name_col = None
            for col in df.columns:
                if '名' in col or 'name' in col.lower():
                    name_col = col
                    break
            if name_col is None:
                return result
            europe_map = {
                "德国DAX": "GDAXI",
                "英国富时": "FTSE",
                "法国CAC": "FCHI"
            }
            for name, code in europe_map.items():
                matched = df[df[name_col].str.contains(name, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][code] = {
                        "name": name,
                        "price": self._safe_float(row.get('最新价') or row.get('price')),
                        "pct_change": self._safe_float(row.get('涨跌幅') or row.get('pct_chg'))
                    }
        except Exception as e:
            logger.warning(f"欧洲获取异常: {e}")
        return result

    def _fetch_commodities_impl(self) -> Dict:
        result = {"oil": {}, "gold": {}, "data_source": "AKShare", "timestamp": datetime.now().isoformat()}
        try:
            import akshare as ak
            # WTI
            try:
                oil_df = ak.futures_foreign_main_sina(symbol="CL")
                if oil_df is not None and not oil_df.empty:
                    latest = oil_df.iloc[-1]
                    result["oil"]["WTI"] = {
                        "name": "WTI",
                        "price": self._safe_float(latest.get('最新价')),
                        "pct_change": self._safe_float(latest.get('涨跌幅'))
                    }
            except:
                pass
            # 布伦特
            try:
                oil_df_b = ak.futures_foreign_main_sina(symbol="B")
                if oil_df_b is not None and not oil_df_b.empty:
                    latest = oil_df_b.iloc[-1]
                    result["oil"]["Brent"] = {
                        "name": "布伦特",
                        "price": self._safe_float(latest.get('最新价')),
                        "pct_change": self._safe_float(latest.get('涨跌幅'))
                    }
            except:
                pass
            # 黄金
            try:
                gold_df = ak.futures_foreign_main_sina(symbol="GC")
                if gold_df is not None and not gold_df.empty:
                    latest = gold_df.iloc[-1]
                    result["gold"] = {
                        "price": self._safe_float(latest.get('最新价')),
                        "pct_change": self._safe_float(latest.get('涨跌幅'))
                    }
            except:
                pass
        except Exception as e:
            logger.warning(f"大宗商品获取异常: {e}")
        return result

    def _fetch_forex_impl(self) -> Dict:
        result = {"usd_cny": {}, "data_source": "AKShare", "timestamp": datetime.now().isoformat()}
        try:
            import akshare as ak
            try:
                cny_df = ak.currency_rates()
                if cny_df is not None and not cny_df.empty:
                    # 查找美元兑人民币
                    name_col = None
                    for col in cny_df.columns:
                        if '名' in col or 'name' in col.lower():
                            name_col = col
                            break
                    if name_col:
                        matched = cny_df[cny_df[name_col].str.contains('美元', na=False)]
                        if not matched.empty:
                            row = matched.iloc[0]
                            result["usd_cny"]["onshore"] = self._safe_float(row.get('最新价'))
                            result["usd_cny"]["pct_change"] = self._safe_float(row.get('涨跌幅'))
            except:
                pass
            try:
                mid_df = ak.currency_rates_central()
                if mid_df is not None and not mid_df.empty:
                    name_col = None
                    for col in mid_df.columns:
                        if '名' in col or 'name' in col.lower():
                            name_col = col
                            break
                    if name_col:
                        matched = mid_df[mid_df[name_col].str.contains('美元', na=False)]
                        if not matched.empty:
                            row = matched.iloc[0]
                            result["usd_cny"]["central"] = self._safe_float(row.get('最新价'))
            except:
                pass
        except Exception as e:
            logger.warning(f"汇率获取异常: {e}")
        return result

    def _fetch_a50_impl(self) -> Dict:
        result = {"price": None, "pct_change": None, "data_source": "AKShare", "timestamp": datetime.now().isoformat()}
        try:
            import akshare as ak
            try:
                a50_df = ak.futures_foreign_main_sina(symbol="A50")
                if a50_df is not None and not a50_df.empty:
                    latest = a50_df.iloc[-1]
                    result["price"] = self._safe_float(latest.get('最新价'))
                    result["pct_change"] = self._safe_float(latest.get('涨跌幅'))
            except:
                pass
            if result["price"] is None:
                try:
                    a50_df2 = ak.futures_main_sina(symbol="A50")
                    if a50_df2 is not None and not a50_df2.empty:
                        latest = a50_df2.iloc[-1]
                        result["price"] = self._safe_float(latest.get('最新价'))
                        result["pct_change"] = self._safe_float(latest.get('涨跌幅'))
                except:
                    pass
        except Exception as e:
            logger.warning(f"A50期货获取异常: {e}")
        return result

    # ============================================================
    # 对外接口（使用安全包装）
    # ============================================================
    def get_us_market(self) -> Dict:
        return self._safe_fetch(self._fetch_us_market_impl, 'us_market')

    def get_asia_market(self) -> Dict:
        return self._safe_fetch(self._fetch_asia_market_impl, 'asia_market')

    def get_europe_market(self) -> Dict:
        return self._safe_fetch(self._fetch_europe_market_impl, 'europe_market')

    def get_commodities(self) -> Dict:
        return self._safe_fetch(self._fetch_commodities_impl, 'commodities')

    def get_forex(self) -> Dict:
        return self._safe_fetch(self._fetch_forex_impl, 'forex')

    def get_a50_futures(self) -> Dict:
        return self._safe_fetch(self._fetch_a50_impl, 'a50_futures')

    def get_macro_snapshot(self) -> Dict:
        cache_key = "macro_snapshot"
        if self._is_cached_valid(cache_key):
            return self._get_cached(cache_key)
        result = {
            "us_market": self.get_us_market(),
            "asia_market": self.get_asia_market(),
            "europe_market": self.get_europe_market(),
            "commodities": self.get_commodities(),
            "forex": self.get_forex(),
            "a50_futures": self.get_a50_futures(),
            "timestamp": datetime.now().isoformat()
        }
        self._set_cache(cache_key, result)
        self._force_write_cache("snapshot", result)
        return result

    # ---------- 格式化（供推送使用）----------
    def format_for_push(self) -> Dict:
        snapshot = self.get_macro_snapshot()
        formatted = {
            "us_market": self._format_us_market(snapshot.get("us_market", {})),
            "asia_market": self._format_asia_market(snapshot.get("asia_market", {})),
            "europe_market": self._format_europe_market(snapshot.get("europe_market", {})),
            "commodities": self._format_commodities(snapshot.get("commodities", {})),
            "forex": self._format_forex(snapshot.get("forex", {})),
            "a50_futures": self._format_a50(snapshot.get("a50_futures", {})),
            "timestamp": snapshot.get("timestamp", "")
        }
        return formatted

    def _format_us_market(self, data: Dict) -> Dict:
        result = {"indices": [], "tech_giants": [], "semiconductor": None}
        for name, idx in data.get("indices", {}).items():
            if idx.get("price"):
                result["indices"].append({
                    "name": idx.get("name", name),
                    "price": idx.get("price"),
                    "pct_change": idx.get("pct_change")
                })
        sem = data.get("semiconductor", {})
        if sem.get("price"):
            result["semiconductor"] = {
                "name": sem.get("name", "费城半导体"),
                "price": sem.get("price"),
                "pct_change": sem.get("pct_change")
            }
        for name, giant in data.get("tech_giants", {}).items():
            if giant.get("price"):
                result["tech_giants"].append({
                    "name": name,
                    "price": giant.get("price"),
                    "pct_change": giant.get("pct_change")
                })
        return result

    def _format_asia_market(self, data: Dict) -> Dict:
        result = {"indices": []}
        for code, idx in data.get("indices", {}).items():
            if idx.get("price"):
                result["indices"].append({
                    "name": idx.get("name", code),
                    "price": idx.get("price"),
                    "pct_change": idx.get("pct_change")
                })
        return result

    def _format_europe_market(self, data: Dict) -> Dict:
        result = {"indices": []}
        for code, idx in data.get("indices", {}).items():
            if idx.get("price"):
                result["indices"].append({
                    "name": idx.get("name", code),
                    "price": idx.get("price"),
                    "pct_change": idx.get("pct_change")
                })
        return result

    def _format_commodities(self, data: Dict) -> Dict:
        result = {"oil": [], "gold": None}
        for name, oil in data.get("oil", {}).items():
            if oil.get("price"):
                result["oil"].append({
                    "name": oil.get("name", name),
                    "price": oil.get("price"),
                    "pct_change": oil.get("pct_change")
                })
        gold = data.get("gold", {})
        if gold.get("price"):
            result["gold"] = {
                "price": gold.get("price"),
                "pct_change": gold.get("pct_change")
            }
        return result

    def _format_forex(self, data: Dict) -> Dict:
        result = {"usd_cny": {}}
        usd = data.get("usd_cny", {})
        if usd.get("onshore"):
            result["usd_cny"]["onshore"] = usd.get("onshore")
        if usd.get("central"):
            result["usd_cny"]["central"] = usd.get("central")
        if usd.get("pct_change"):
            result["usd_cny"]["pct_change"] = usd.get("pct_change")
        return result

    def _format_a50(self, data: Dict) -> Dict:
        result = {}
        if data.get("price"):
            result["price"] = data.get("price")
        if data.get("pct_change"):
            result["pct_change"] = data.get("pct_change")
        return result

    # ---------- 辅助 ----------
    def _safe_float(self, value) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
