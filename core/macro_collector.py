#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观数据采集模块（优化版：每天仅获取1次）
- 缓存优先，减少网络请求
- 每日首次运行获取完整数据，后续复用缓存
- 超时控制，避免卡死
"""

import os
import logging
import time
import json
import concurrent.futures
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# ✅ 在导入 akshare 之前禁用 tqdm
os.environ['TQDM_DISABLE'] = '1'

from core.macro_cache import MacroCache

logger = logging.getLogger(__name__)


class MacroCollector:
    def __init__(self):
        self._cache = MacroCache()
        self._cache_ttl = 3600
        self._retry_count = 1               # 重试次数
        self._retry_delay = [2]             # 重试等待2秒
        self._timeout = 8                   # 超时8秒
        # ✅ 每天仅获取1次的标记
        self._today_fetched = False
        self._today_date = datetime.now().date()
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

    # ---------- 核心安全获取（缓存优先，减少重试） ----------
    def _safe_fetch(self, func, cache_key: str = None, *args, **kwargs) -> Any:
        # 1. 尝试从存储缓存读取（优先，0网络请求）
        if cache_key:
            cached_data = self._get_cached_from_storage(cache_key)
            if cached_data is not None and not self._is_empty_result(cached_data):
                logger.info(f"✅ 从存储缓存获取 {cache_key}")
                return cached_data

        # 2. 实时获取（带超时，仅1次重试）
        last_error = None
        for attempt in range(self._retry_count + 1):  # 0, 1
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(func, *args, **kwargs)
                    result = future.result(timeout=self._timeout)
                if result and not self._is_empty_result(result):
                    if cache_key:
                        self._save_cached_to_storage(cache_key, result)
                    return result
            except concurrent.futures.TimeoutError:
                last_error = f"超时 ({self._timeout}s)"
                if attempt < self._retry_count:
                    logger.warning(f"⏰ {cache_key} 超时，等待 {self._retry_delay[attempt]}s 后重试")
                    time.sleep(self._retry_delay[attempt])
                    continue
                else:
                    logger.warning(f"⏰ {cache_key} 超时，放弃")
            except Exception as e:
                last_error = str(e)
                if attempt < self._retry_count:
                    logger.warning(f"⚠️ {cache_key} 异常: {e}，等待 {self._retry_delay[attempt]}s 后重试")
                    time.sleep(self._retry_delay[attempt])
                    continue
                else:
                    logger.warning(f"⚠️ {cache_key} 异常，放弃")

        # 3. 获取失败，使用过期缓存（即使过期）
        if cache_key:
            stale_data = self._get_cached_from_storage(cache_key, ignore_ttl=True)
            if stale_data is not None and not self._is_empty_result(stale_data):
                logger.warning(f"⚠️ 使用过期缓存 {cache_key}")
                return stale_data

        # 4. 最终降级：空数据
        logger.warning(f"⚠️ {cache_key} 完全不可用")
        return self._get_empty_result()

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

    # ---------- 存储层缓存 ----------
    def _get_cached_from_storage(self, key, ignore_ttl=False):
        methods = {
            'us_market': self._cache.get_us_market,
            'asia_market': self._cache.get_asia_market,
            'europe_market': self._cache.get_europe_market,
            'commodities': self._cache.get_commodities,
            'forex': self._cache.get_forex,
            'a50_futures': self._cache.get_a50_futures,
        }
        if key in methods:
            return methods[key]()
        return None

    def _save_cached_to_storage(self, key, data):
        methods = {
            'us_market': self._cache.save_us_market,
            'asia_market': self._cache.save_asia_market,
            'europe_market': self._cache.save_europe_market,
            'commodities': self._cache.save_commodities,
            'forex': self._cache.save_forex,
            'a50_futures': self._cache.save_a50_futures,
        }
        if key in methods:
            file_path = methods[key](data)
            logger.info(f"✅ {key} 已保存到存储缓存: {file_path}")

    # ============================================================
    # 1. 美股市场
    # ============================================================
    def get_us_market(self) -> Dict:
        return self._safe_fetch(self._fetch_us_market_impl, 'us_market')

    def _fetch_us_market_impl(self) -> Dict:
        result = {"indices": {}, "semiconductor": {}, "tech_giants": {}, "data_source": "AKShare", "timestamp": datetime.now().isoformat()}
        try:
            import akshare as ak
            df = ak.stock_us_spot()
            if df is None or df.empty:
                logger.warning("美股数据为空")
                return result

            name_col = self._find_column(df, ['名称', 'name', 'Name'])
            price_col = self._find_column(df, ['最新价', 'price', 'close'])
            pct_col = self._find_column(df, ['涨跌幅', 'change', 'pct_change'])
            if not name_col or not price_col:
                logger.warning("美股列名不匹配")
                return result

            index_keywords = ["道琼斯", "纳斯达克", "标普500"]
            for keyword in index_keywords:
                matched = df[df[name_col].str.contains(keyword, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][keyword] = {"name": keyword, "price": self._safe_float(row.get(price_col)), "pct_change": self._safe_float(row.get(pct_col))}

            sem_matched = df[df[name_col].str.contains("费城半导体", na=False)]
            if not sem_matched.empty:
                row = sem_matched.iloc[0]
                result["semiconductor"] = {"name": "费城半导体", "price": self._safe_float(row.get(price_col)), "pct_change": self._safe_float(row.get(pct_col))}

            tech_giants = ["苹果", "英伟达", "微软", "谷歌", "亚马逊", "Meta", "特斯拉", "美光", "英特尔", "AMD"]
            for giant in tech_giants:
                matched = df[df[name_col].str.contains(giant, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["tech_giants"][giant] = {"name": giant, "price": self._safe_float(row.get(price_col)), "pct_change": self._safe_float(row.get(pct_col))}
            return result
        except Exception as e:
            logger.warning(f"美股获取异常: {e}")
            return result

    # ============================================================
    # 2. 亚太市场
    # ============================================================
    def get_asia_market(self) -> Dict:
        return self._safe_fetch(self._fetch_asia_market_impl, 'asia_market')

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
                    result["indices"][code] = {"name": name, "price": self._safe_float(row.get(price_col)), "pct_change": self._safe_float(row.get(pct_col))}
            return result
        except Exception as e:
            logger.warning(f"亚太获取异常: {e}")
            return result

    # ============================================================
    # 3. 欧洲市场
    # ============================================================
    def get_europe_market(self) -> Dict:
        return self._safe_fetch(self._fetch_europe_market_impl, 'europe_market')

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
                    result["indices"][code] = {"name": name, "price": self._safe_float(row.get(price_col)), "pct_change": self._safe_float(row.get(pct_col))}
            return result
        except Exception as e:
            logger.warning(f"欧洲获取异常: {e}")
            return result

    # ============================================================
    # 4. 大宗商品
    # ============================================================
    def get_commodities(self) -> Dict:
        return self._safe_fetch(self._fetch_commodities_impl, 'commodities')

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
                            result["oil"][name] = {"name": name, "price": self._safe_float(latest.get(price_col)), "pct_change": self._safe_float(latest.get(pct_col)) if pct_col else None}
                except:
                    pass
            try:
                gold_df = ak.futures_foreign_main_sina(symbol="GC")
                if gold_df is not None and not gold_df.empty:
                    latest = gold_df.iloc[-1]
                    price_col = self._find_column(gold_df, ['最新价', 'price'])
                    pct_col = self._find_column(gold_df, ['涨跌幅', 'change'])
                    if price_col:
                        result["gold"] = {"price": self._safe_float(latest.get(price_col)), "pct_change": self._safe_float(latest.get(pct_col)) if pct_col else None}
            except:
                pass
            return result
        except Exception as e:
            logger.warning(f"大宗商品获取异常: {e}")
            return result

    # ============================================================
    # 5. 汇率
    # ============================================================
    def get_forex(self) -> Dict:
        return self._safe_fetch(self._fetch_forex_impl, 'forex')

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
    # 6. A50期货
    # ============================================================
    def get_a50_futures(self) -> Dict:
        return self._safe_fetch(self._fetch_a50_impl, 'a50_futures')

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
    # 7. 宏观快照（每天仅获取1次）
    # ============================================================
    def _is_today_fetched(self) -> bool:
        """检查今天是否已经获取过宏观数据"""
        today = datetime.now().date()
        if today != self._today_date:
            self._today_date = today
            self._today_fetched = False
        return self._today_fetched

    def _mark_today_fetched(self):
        """标记今天已获取宏观数据"""
        self._today_fetched = True
        self._today_date = datetime.now().date()
        logger.info("✅ 今日宏观数据已获取（今日不再重复获取）")

    def _load_snapshot_from_cache(self) -> Optional[Dict]:
        """从缓存加载宏观快照"""
        cache_file = os.path.join(self._cache.storage_dir, "macro_snapshot.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return None

    def get_macro_snapshot(self) -> Dict:
        """
        获取宏观数据快照（每天仅获取1次）
        如果今天已获取过，直接返回缓存
        """
        # ✅ 如果今天已获取过，直接返回缓存
        if self._is_today_fetched():
            logger.info("📦 今日宏观数据已获取，从缓存返回")
            cached = self._load_snapshot_from_cache()
            if cached:
                return cached.get('data', {})
            else:
                # 理论上不应该出现，但以防万一
                logger.warning("⚠️ 缓存不存在，重新获取")
                return self._fetch_all_macro_data()

        # 尝试从缓存加载（如果今天没获取过，但缓存存在）
        cached = self._load_snapshot_from_cache()
        if cached:
            cache_time = cached.get('_cache_time', '')
            if cache_time:
                try:
                    cache_dt = datetime.fromisoformat(cache_time)
                    if cache_dt.date() == datetime.now().date():
                        logger.info("📦 今日缓存已存在，直接使用")
                        self._mark_today_fetched()
                        return cached.get('data', {})
                except:
                    pass

        # 真正获取数据
        logger.info("🌐 今日首次获取宏观数据（后续将使用缓存）")
        result = self._fetch_all_macro_data()
        self._mark_today_fetched()
        return result

    def _fetch_all_macro_data(self) -> Dict:
        """实际获取所有宏观数据（仅当今日首次运行时调用）"""
        result = {
            "us_market": self.get_us_market(),
            "asia_market": self.get_asia_market(),
            "europe_market": self.get_europe_market(),
            "commodities": self.get_commodities(),
            "forex": self.get_forex(),
            "a50_futures": self.get_a50_futures(),
            "timestamp": datetime.now().isoformat()
        }

        # 保存到缓存
        cache_file = os.path.join(self._cache.storage_dir, "macro_snapshot.json")
        try:
            with open(cache_file, 'w') as f:
                json.dump({'_cache_time': datetime.now().isoformat(), 'data': result}, f, ensure_ascii=False, indent=2)
            logger.info(f"✅ 宏观快照已保存到: {cache_file}")
        except Exception as e:
            logger.warning(f"保存宏观快照失败: {e}")

        return result

    # ============================================================
    # 8. 格式化宏观数据（供推送使用）
    # ============================================================
    def format_for_push(self) -> Dict:
        """获取并格式化宏观数据，供推送使用"""
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
                result["indices"].append({"name": name, "price": idx.get("price"), "pct_change": idx.get("pct_change")})
        sem = data.get("semiconductor", {})
        if sem.get("price"):
            result["semiconductor"] = {"name": "费城半导体", "price": sem.get("price"), "pct_change": sem.get("pct_change")}
        for name, giant in data.get("tech_giants", {}).items():
            if giant.get("price"):
                result["tech_giants"].append({"name": name, "price": giant.get("price"), "pct_change": giant.get("pct_change")})
        return result

    def _format_asia_market(self, data: Dict) -> Dict:
        result = {"indices": []}
        for code, idx in data.get("indices", {}).items():
            if idx.get("price"):
                result["indices"].append({"name": idx.get("name", code), "price": idx.get("price"), "pct_change": idx.get("pct_change")})
        return result

    def _format_europe_market(self, data: Dict) -> Dict:
        result = {"indices": []}
        for code, idx in data.get("indices", {}).items():
            if idx.get("price"):
                result["indices"].append({"name": idx.get("name", code), "price": idx.get("price"), "pct_change": idx.get("pct_change")})
        return result

    def _format_commodities(self, data: Dict) -> Dict:
        result = {"oil": [], "gold": None}
        for name, oil in data.get("oil", {}).items():
            if oil.get("price"):
                result["oil"].append({"name": oil.get("name", name), "price": oil.get("price"), "pct_change": oil.get("pct_change")})
        gold = data.get("gold", {})
        if gold.get("price"):
            result["gold"] = {"price": gold.get("price"), "pct_change": gold.get("pct_change")}
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
