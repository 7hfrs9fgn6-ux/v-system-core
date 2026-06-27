#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观数据采集模块（最终修复版）
- 强制缓存写入（即使数据为空）
- 适配最新 AKShare 接口
- 多级降级保证不崩溃
"""

import os
import logging
import time
import json
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class MacroCollector:
    def __init__(self):
        self._cache_dir = "memory_data/"
        os.makedirs(self._cache_dir, exist_ok=True)
        self._cache_ttl = 3600  # 缓存1小时

    def _load_cache(self, key: str) -> Optional[Dict]:
        cache_file = os.path.join(self._cache_dir, f"macro_{key}.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                cache_time = data.get('_cache_time', '')
                if cache_time:
                    cache_dt = datetime.fromisoformat(cache_time)
                    if (datetime.now() - cache_dt).total_seconds() < self._cache_ttl * 2:
                        return data.get('data', {})
            except:
                pass
        return None

    def _save_cache(self, key: str, data: Dict):
        cache_file = os.path.join(self._cache_dir, f"macro_{key}.json")
        cache_data = {
            '_cache_time': datetime.now().isoformat(),
            'data': data
        }
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        logger.info(f"✅ 缓存已写入: {cache_file}")

    def _safe_fetch(self, func, key: str) -> Dict:
        # 1. 优先从缓存读取
        cached = self._load_cache(key)
        if cached is not None:
            logger.info(f"📦 从缓存加载 {key}")
            return cached

        # 2. 实时获取（带重试）
        for attempt in range(3):
            try:
                result = func()
                # 即使结果为空也缓存（避免反复请求）
                self._save_cache(key, result)
                return result
            except Exception as e:
                logger.warning(f"⚠️ 获取 {key} 失败 (尝试 {attempt+1}/3): {e}")
                time.sleep(1)
        # 3. 完全失败时返回空字典，并写入空缓存
        empty = {}
        self._save_cache(key, empty)
        return empty

    # ---------- 各数据源获取（已适配最新接口） ----------
    def _fetch_us_market(self) -> Dict:
        result = {"indices": {}, "semiconductor": {}, "tech_giants": {}}
        try:
            import akshare as ak
            df = ak.stock_us_spot()
            if df is None or df.empty:
                return result
            # 查找名称列
            name_col = None
            for col in df.columns:
                if '名' in col or 'name' in col.lower():
                    name_col = col
                    break
            if name_col is None:
                return result
            # 指数
            for idx in ["道琼斯", "纳斯达克", "标普500"]:
                matched = df[df[name_col].str.contains(idx, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][idx] = {
                        "name": idx,
                        "price": self._to_float(row.get('最新价') or row.get('price')),
                        "pct_change": self._to_float(row.get('涨跌幅') or row.get('pct_chg'))
                    }
            # 费城半导体
            sem = df[df[name_col].str.contains("费城半导体", na=False)]
            if not sem.empty:
                row = sem.iloc[0]
                result["semiconductor"] = {
                    "name": "费城半导体",
                    "price": self._to_float(row.get('最新价') or row.get('price')),
                    "pct_change": self._to_float(row.get('涨跌幅') or row.get('pct_chg'))
                }
            # 科技巨头
            for giant in ["苹果", "英伟达", "微软", "谷歌", "亚马逊", "Meta", "特斯拉", "美光", "英特尔", "AMD"]:
                matched = df[df[name_col].str.contains(giant, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["tech_giants"][giant] = {
                        "name": giant,
                        "price": self._to_float(row.get('最新价') or row.get('price')),
                        "pct_change": self._to_float(row.get('涨跌幅') or row.get('pct_chg'))
                    }
        except Exception as e:
            logger.warning(f"美股获取异常: {e}")
        return result

    def _fetch_asia_market(self) -> Dict:
        result = {"indices": {}}
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
            for name, code in [("日经225", "N225"), ("韩国KOSPI", "KOSPI"), ("恒生指数", "HSI"), ("台湾加权", "TWII")]:
                matched = df[df[name_col].str.contains(name, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][code] = {
                        "name": name,
                        "price": self._to_float(row.get('最新价') or row.get('price')),
                        "pct_change": self._to_float(row.get('涨跌幅') or row.get('pct_chg'))
                    }
        except Exception as e:
            logger.warning(f"亚太获取异常: {e}")
        return result

    def _fetch_europe_market(self) -> Dict:
        result = {"indices": {}}
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
            for name, code in [("德国DAX", "GDAXI"), ("英国富时", "FTSE"), ("法国CAC", "FCHI")]:
                matched = df[df[name_col].str.contains(name, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][code] = {
                        "name": name,
                        "price": self._to_float(row.get('最新价') or row.get('price')),
                        "pct_change": self._to_float(row.get('涨跌幅') or row.get('pct_chg'))
                    }
        except Exception as e:
            logger.warning(f"欧洲获取异常: {e}")
        return result

    def _fetch_commodities(self) -> Dict:
        result = {"oil": {}, "gold": {}}
        try:
            import akshare as ak
            # WTI
            try:
                df = ak.futures_foreign_main_sina(symbol="CL")
                if df is not None and not df.empty:
                    latest = df.iloc[-1]
                    result["oil"]["WTI"] = {
                        "name": "WTI",
                        "price": self._to_float(latest.get('最新价')),
                        "pct_change": self._to_float(latest.get('涨跌幅'))
                    }
            except:
                pass
            # 布伦特
            try:
                df = ak.futures_foreign_main_sina(symbol="B")
                if df is not None and not df.empty:
                    latest = df.iloc[-1]
                    result["oil"]["Brent"] = {
                        "name": "布伦特",
                        "price": self._to_float(latest.get('最新价')),
                        "pct_change": self._to_float(latest.get('涨跌幅'))
                    }
            except:
                pass
            # 黄金
            try:
                df = ak.futures_foreign_main_sina(symbol="GC")
                if df is not None and not df.empty:
                    latest = df.iloc[-1]
                    result["gold"] = {
                        "price": self._to_float(latest.get('最新价')),
                        "pct_change": self._to_float(latest.get('涨跌幅'))
                    }
            except:
                pass
        except Exception as e:
            logger.warning(f"大宗商品获取异常: {e}")
        return result

    def _fetch_forex(self) -> Dict:
        result = {"usd_cny": {}}
        try:
            import akshare as ak
            try:
                df = ak.currency_rates()
                if df is not None and not df.empty:
                    name_col = None
                    for col in df.columns:
                        if '名' in col or 'name' in col.lower():
                            name_col = col
                            break
                    if name_col:
                        matched = df[df[name_col].str.contains('美元', na=False)]
                        if not matched.empty:
                            row = matched.iloc[0]
                            result["usd_cny"]["onshore"] = self._to_float(row.get('最新价'))
                            result["usd_cny"]["pct_change"] = self._to_float(row.get('涨跌幅'))
            except:
                pass
            try:
                df = ak.currency_rates_central()
                if df is not None and not df.empty:
                    name_col = None
                    for col in df.columns:
                        if '名' in col or 'name' in col.lower():
                            name_col = col
                            break
                    if name_col:
                        matched = df[df[name_col].str.contains('美元', na=False)]
                        if not matched.empty:
                            row = matched.iloc[0]
                            result["usd_cny"]["central"] = self._to_float(row.get('最新价'))
            except:
                pass
        except Exception as e:
            logger.warning(f"汇率获取异常: {e}")
        return result

    def _fetch_a50(self) -> Dict:
        result = {"price": None, "pct_change": None}
        try:
            import akshare as ak
            try:
                df = ak.futures_foreign_main_sina(symbol="A50")
                if df is not None and not df.empty:
                    latest = df.iloc[-1]
                    result["price"] = self._to_float(latest.get('最新价'))
                    result["pct_change"] = self._to_float(latest.get('涨跌幅'))
            except:
                pass
            if result["price"] is None:
                try:
                    df = ak.futures_main_sina(symbol="A50")
                    if df is not None and not df.empty:
                        latest = df.iloc[-1]
                        result["price"] = self._to_float(latest.get('最新价'))
                        result["pct_change"] = self._to_float(latest.get('涨跌幅'))
                except:
                    pass
        except Exception as e:
            logger.warning(f"A50期货获取异常: {e}")
        return result

    # ---------- 对外接口 ----------
    def get_us_market(self) -> Dict:
        return self._safe_fetch(self._fetch_us_market, "us_market")

    def get_asia_market(self) -> Dict:
        return self._safe_fetch(self._fetch_asia_market, "asia_market")

    def get_europe_market(self) -> Dict:
        return self._safe_fetch(self._fetch_europe_market, "europe_market")

    def get_commodities(self) -> Dict:
        return self._safe_fetch(self._fetch_commodities, "commodities")

    def get_forex(self) -> Dict:
        return self._safe_fetch(self._fetch_forex, "forex")

    def get_a50_futures(self) -> Dict:
        return self._safe_fetch(self._fetch_a50, "a50_futures")

    def get_macro_snapshot(self) -> Dict:
        cached = self._load_cache("snapshot")
        if cached is not None:
            return cached
        result = {
            "us_market": self.get_us_market(),
            "asia_market": self.get_asia_market(),
            "europe_market": self.get_europe_market(),
            "commodities": self.get_commodities(),
            "forex": self.get_forex(),
            "a50_futures": self.get_a50_futures(),
            "timestamp": datetime.now().isoformat()
        }
        self._save_cache("snapshot", result)
        return result

    def format_for_push(self) -> Dict:
        snapshot = self.get_macro_snapshot()
        formatted = {
            "us_market": self._format_us(snapshot.get("us_market", {})),
            "asia_market": self._format_indices(snapshot.get("asia_market", {})),
            "europe_market": self._format_indices(snapshot.get("europe_market", {})),
            "commodities": self._format_comm(snapshot.get("commodities", {})),
            "forex": self._format_forex(snapshot.get("forex", {})),
            "a50_futures": snapshot.get("a50_futures", {}),
            "timestamp": snapshot.get("timestamp", "")
        }
        return formatted

    # ---------- 格式化辅助 ----------
    def _format_us(self, data):
        result = {"indices": [], "tech_giants": [], "semiconductor": None}
        for name, idx in data.get("indices", {}).items():
            if idx.get("price"):
                result["indices"].append(idx)
        sem = data.get("semiconductor")
        if sem and sem.get("price"):
            result["semiconductor"] = sem
        for name, giant in data.get("tech_giants", {}).items():
            if giant.get("price"):
                result["tech_giants"].append(giant)
        return result

    def _format_indices(self, data):
        result = {"indices": []}
        for code, idx in data.get("indices", {}).items():
            if idx.get("price"):
                result["indices"].append(idx)
        return result

    def _format_comm(self, data):
        result = {"oil": [], "gold": None}
        for name, oil in data.get("oil", {}).items():
            if oil.get("price"):
                result["oil"].append(oil)
        gold = data.get("gold")
        if gold and gold.get("price"):
            result["gold"] = gold
        return result

    def _format_forex(self, data):
        result = {"usd_cny": {}}
        usd = data.get("usd_cny", {})
        if usd.get("onshore"):
            result["usd_cny"]["onshore"] = usd["onshore"]
        if usd.get("central"):
            result["usd_cny"]["central"] = usd["central"]
        if usd.get("pct_change"):
            result["usd_cny"]["pct_change"] = usd["pct_change"]
        return result

    def _to_float(self, value):
        if value is None:
            return None
        try:
            return float(value)
        except:
            return None
