#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观数据采集模块（P0阶段 + 强化容错 + 缓存集成）
独立于AKShare行业数据，即使AKShare过载也能正常返回
绝不修改 data_adapter/real_adapter.py
集成 MacroCache 实现本地缓存，大幅提升后续运行速度
"""

import os
import logging
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# ✅ 导入缓存模块
from core.macro_cache import MacroCache

logger = logging.getLogger(__name__)


class MacroCollector:
    """
    宏观数据采集器（强化容错版 + 缓存集成）
    采集范围：美股、欧股、亚太、大宗商品、汇率、A50期货
    容错策略：缓存优先 → 实时获取 → 缓存降级 → 模拟值兜底
    """

    def __init__(self):
        self._cache = MacroCache()  # ✅ 缓存管理器
        self._cache_ttl = 3600  # 缓存有效期1小时（配合存储层的2小时）
        self._retry_count = 3
        self._retry_delay = [1, 2, 4]  # 递增延迟
        self._last_success_data = {}  # 最后成功的数据（永久缓存）
        self._has_ever_succeeded = False

    def _is_cached_valid(self, key: str) -> bool:
        """检查内存缓存是否有效"""
        if key in self._cache._cache:
            cached_time, _ = self._cache._cache[key]
            if (datetime.now() - cached_time).total_seconds() < self._cache_ttl:
                return True
        return False

    def _get_cached(self, key: str) -> Any:
        """获取内存缓存数据"""
        if key in self._cache._cache:
            _, data = self._cache._cache[key]
            return data
        return None

    def _set_cache(self, key: str, data: Any):
        """设置内存缓存"""
        self._cache._cache[key] = (datetime.now(), data)

    # ============================================================
    # 存储层缓存方法（持久化到 JSON 文件）
    # ============================================================
    def _get_cached_from_storage(self, key: str, ignore_ttl: bool = False) -> Any:
        """从存储层获取缓存数据"""
        methods = {
            'us_market': self._cache.get_us_market,
            'asia_market': self._cache.get_asia_market,
            'europe_market': self._cache.get_europe_market,
            'commodities': self._cache.get_commodities,
            'forex': self._cache.get_forex,
            'a50_futures': self._cache.get_a50_futures,
        }
        if key in methods:
            data = methods[key]()
            if data:
                logger.debug(f"✅ 从存储层读取 {key} 缓存")
                return data
        return None

    def _save_cached_to_storage(self, key: str, data: Any):
        """保存数据到存储层"""
        methods = {
            'us_market': self._cache.save_us_market,
            'asia_market': self._cache.save_asia_market,
            'europe_market': self._cache.save_europe_market,
            'commodities': self._cache.save_commodities,
            'forex': self._cache.save_forex,
            'a50_futures': self._cache.save_a50_futures,
        }
        if key in methods:
            methods[key](data)
            logger.info(f"✅ {key} 已保存到存储缓存")

    # ============================================================
    # 安全获取：缓存优先 + 实时获取 + 降级
    # ============================================================
    def _safe_fetch(self, func, cache_key: str = None, *args, **kwargs) -> Any:
        """
        安全获取数据：缓存优先 → 实时获取 → 兜底
        """
        # 1. ✅ 优先从存储层缓存读取（超快，无网络请求）
        if cache_key:
            cached_data = self._get_cached_from_storage(cache_key)
            if cached_data is not None and not self._is_empty_result(cached_data):
                logger.info(f"✅ 从存储缓存获取 {cache_key}（无网络请求）")
                return cached_data

        # 2. 缓存不存在或过期，执行实时获取
        last_error = None
        for attempt in range(self._retry_count):
            try:
                result = func(*args, **kwargs)
                if result and not self._is_empty_result(result):
                    # 保存到存储层缓存
                    if cache_key:
                        self._save_cached_to_storage(cache_key, result)
                    return result
            except Exception as e:
                last_error = e
                if attempt < self._retry_count - 1:
                    logger.debug(f"⏳ {cache_key} 重试 {attempt+2}/{self._retry_count}，等待 {self._retry_delay[attempt]}s")
                    time.sleep(self._retry_delay[attempt])
                    continue

        # 3. 获取失败，尝试从存储层读取（即使过期）
        if cache_key:
            stale_data = self._get_cached_from_storage(cache_key, ignore_ttl=True)
            if stale_data is not None and not self._is_empty_result(stale_data):
                logger.warning(f"⚠️ {cache_key} 实时获取失败，使用过期缓存（数据可能不是最新）")
                return stale_data

        # 4. 最终降级：返回空但格式正确的数据
        logger.warning(f"⚠️ {cache_key} 完全不可用，返回空数据")
        return self._get_empty_result()

    def _is_empty_result(self, data) -> bool:
        """检查数据是否为空"""
        if data is None:
            return True
        if isinstance(data, dict):
            # 检查是否所有值都为空
            for key, value in data.items():
                if value and not self._is_empty_result(value):
                    return False
            return True
        if isinstance(data, list):
            return len(data) == 0
        return False

    def _get_empty_result(self) -> Dict:
        """返回空结果格式"""
        return {
            "indices": {},
            "semiconductor": {},
            "tech_giants": {},
            "oil": {},
            "gold": {},
            "usd_cny": {},
            "price": None,
            "pct_change": None,
            "data_source": "cache_fallback",
            "timestamp": datetime.now().isoformat()
        }

    # ============================================================
    # 1. 美股数据
    # ============================================================
    def get_us_market(self) -> Dict:
        """获取美股市场数据（带容错 + 缓存）"""
        return self._safe_fetch(self._fetch_us_market_impl, 'us_market')

    def _fetch_us_market_impl(self) -> Dict:
        """实际获取美股数据的实现"""
        result = {
            "indices": {},
            "semiconductor": {},
            "tech_giants": {},
            "data_source": "AKShare",
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak
            # ✅ 只获取最新数据（不获取历史）
            df = ak.stock_us_spot()

            if df is None or df.empty:
                logger.warning("美股行情数据为空")
                return result

            # 指数
            index_keywords = ["道琼斯", "纳斯达克", "标普500"]
            for keyword in index_keywords:
                matched = df[df['名称'].str.contains(keyword, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][keyword] = {
                        "name": keyword,
                        "price": self._safe_float(row.get('最新价')),
                        "pct_change": self._safe_float(row.get('涨跌幅'))
                    }

            # 费城半导体
            sem_matched = df[df['名称'].str.contains("费城半导体", na=False)]
            if not sem_matched.empty:
                row = sem_matched.iloc[0]
                result["semiconductor"] = {
                    "name": "费城半导体",
                    "price": self._safe_float(row.get('最新价')),
                    "pct_change": self._safe_float(row.get('涨跌幅'))
                }

            # 科技巨头（只获取价格和涨跌幅）
            tech_giants = ["苹果", "英伟达", "微软", "谷歌", "亚马逊", "Meta", "特斯拉", "美光", "英特尔", "AMD"]
            for giant in tech_giants:
                matched = df[df['名称'].str.contains(giant, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["tech_giants"][giant] = {
                        "name": giant,
                        "price": self._safe_float(row.get('最新价')),
                        "pct_change": self._safe_float(row.get('涨跌幅'))
                    }

            logger.info(f"✅ 美股数据获取成功: {len(result['indices'])}个指数, {len(result['tech_giants'])}只科技股")
            return result

        except Exception as e:
            logger.warning(f"美股数据获取异常: {e}")
            return result

    # ============================================================
    # 2. 亚太市场
    # ============================================================
    def get_asia_market(self) -> Dict:
        """获取亚太市场数据（带容错 + 缓存）"""
        return self._safe_fetch(self._fetch_asia_market_impl, 'asia_market')

    def _fetch_asia_market_impl(self) -> Dict:
        """实际获取亚太数据的实现"""
        result = {
            "indices": {},
            "data_source": "AKShare",
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak
            df = ak.stock_zh_index_spot()

            if df is None or df.empty:
                logger.warning("亚太市场数据为空")
                return result

            asia_map = {
                "日经225": "N225",
                "韩国KOSPI": "KOSPI",
                "恒生指数": "HSI",
                "台湾加权": "TWII"
            }

            for name, code in asia_map.items():
                matched = df[df['名称'].str.contains(name, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][code] = {
                        "name": name,
                        "price": self._safe_float(row.get('最新价')),
                        "pct_change": self._safe_float(row.get('涨跌幅'))
                    }

            logger.info(f"✅ 亚太数据获取成功: {len(result['indices'])}个指数")
            return result

        except Exception as e:
            logger.warning(f"亚太数据获取异常: {e}")
            return result

    # ============================================================
    # 3. 欧洲市场
    # ============================================================
    def get_europe_market(self) -> Dict:
        """获取欧洲市场数据（带容错 + 缓存）"""
        return self._safe_fetch(self._fetch_europe_market_impl, 'europe_market')

    def _fetch_europe_market_impl(self) -> Dict:
        """实际获取欧洲数据的实现"""
        result = {
            "indices": {},
            "data_source": "AKShare",
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak
            df = ak.stock_zh_index_spot()

            if df is None or df.empty:
                logger.warning("欧洲市场数据为空")
                return result

            europe_map = {
                "德国DAX": "GDAXI",
                "英国富时": "FTSE",
                "法国CAC": "FCHI"
            }

            for name, code in europe_map.items():
                matched = df[df['名称'].str.contains(name, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][code] = {
                        "name": name,
                        "price": self._safe_float(row.get('最新价')),
                        "pct_change": self._safe_float(row.get('涨跌幅'))
                    }

            logger.info(f"✅ 欧洲数据获取成功: {len(result['indices'])}个指数")
            return result

        except Exception as e:
            logger.warning(f"欧洲数据获取异常: {e}")
            return result

    # ============================================================
    # 4. 大宗商品
    # ============================================================
    def get_commodities(self) -> Dict:
        """获取大宗商品数据（带容错 + 缓存）"""
        return self._safe_fetch(self._fetch_commodities_impl, 'commodities')

    def _fetch_commodities_impl(self) -> Dict:
        """实际获取大宗商品数据的实现"""
        result = {
            "oil": {},
            "gold": {},
            "data_source": "AKShare",
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak

            # 原油 WTI
            try:
                oil_df = ak.futures_foreign_main_sina(symbol="CL")
                if oil_df is not None and not oil_df.empty:
                    latest = oil_df.iloc[-1]
                    result["oil"]["WTI"] = {
                        "name": "WTI",
                        "price": self._safe_float(latest.get('最新价')),
                        "pct_change": self._safe_float(latest.get('涨跌幅'))
                    }
            except Exception as e:
                logger.debug(f"WTI原油获取失败: {e}")

            # 原油 布伦特
            try:
                oil_df_b = ak.futures_foreign_main_sina(symbol="B")
                if oil_df_b is not None and not oil_df_b.empty:
                    latest = oil_df_b.iloc[-1]
                    result["oil"]["Brent"] = {
                        "name": "布伦特",
                        "price": self._safe_float(latest.get('最新价')),
                        "pct_change": self._safe_float(latest.get('涨跌幅'))
                    }
            except Exception as e:
                logger.debug(f"布伦特原油获取失败: {e}")

            # 黄金
            try:
                gold_df = ak.futures_foreign_main_sina(symbol="GC")
                if gold_df is not None and not gold_df.empty:
                    latest = gold_df.iloc[-1]
                    result["gold"] = {
                        "price": self._safe_float(latest.get('最新价')),
                        "pct_change": self._safe_float(latest.get('涨跌幅'))
                    }
            except Exception as e:
                logger.debug(f"黄金获取失败: {e}")

            logger.info(f"✅ 大宗商品获取成功: {len(result['oil'])}种原油, 黄金: {'有' if result['gold'] else '无'}")
            return result

        except Exception as e:
            logger.warning(f"大宗商品获取异常: {e}")
            return result

    # ============================================================
    # 5. 人民币汇率
    # ============================================================
    def get_forex(self) -> Dict:
        """获取人民币汇率数据（带容错 + 缓存）"""
        return self._safe_fetch(self._fetch_forex_impl, 'forex')

    def _fetch_forex_impl(self) -> Dict:
        """实际获取汇率数据的实现"""
        result = {
            "usd_cny": {},
            "data_source": "AKShare",
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak

            # 在岸人民币
            try:
                cny_df = ak.currency_rates()
                if cny_df is not None and not cny_df.empty:
                    matched = cny_df[cny_df['货币名称'].str.contains('美元', na=False)]
                    if not matched.empty:
                        row = matched.iloc[0]
                        result["usd_cny"]["onshore"] = self._safe_float(row.get('最新价'))
                        result["usd_cny"]["pct_change"] = self._safe_float(row.get('涨跌幅'))
            except Exception as e:
                logger.debug(f"在岸人民币获取失败: {e}")

            # 人民币中间价
            try:
                mid_df = ak.currency_rates_central()
                if mid_df is not None and not mid_df.empty:
                    matched = mid_df[mid_df['货币名称'].str.contains('美元', na=False)]
                    if not matched.empty:
                        row = matched.iloc[0]
                        result["usd_cny"]["central"] = self._safe_float(row.get('最新价'))
            except Exception as e:
                logger.debug(f"中间价获取失败: {e}")

            logger.info(f"✅ 汇率数据获取成功: 在岸: {result['usd_cny'].get('onshore', '无')}")
            return result

        except Exception as e:
            logger.warning(f"汇率数据获取异常: {e}")
            return result

    # ============================================================
    # 6. A50期货
    # ============================================================
    def get_a50_futures(self) -> Dict:
        """获取A50期货数据（带容错 + 缓存）"""
        return self._safe_fetch(self._fetch_a50_impl, 'a50_futures')

    def _fetch_a50_impl(self) -> Dict:
        """实际获取A50期货数据的实现"""
        result = {
            "price": None,
            "pct_change": None,
            "data_source": "AKShare",
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak

            # 尝试获取A50期货
            try:
                a50_df = ak.futures_foreign_main_sina(symbol="A50")
                if a50_df is not None and not a50_df.empty:
                    latest = a50_df.iloc[-1]
                    result["price"] = self._safe_float(latest.get('最新价'))
                    result["pct_change"] = self._safe_float(latest.get('涨跌幅'))
                    logger.info(f"✅ A50期货获取成功: {result['price']}")
                    return result
            except:
                pass

            # 备选方案
            try:
                a50_df2 = ak.futures_main_sina(symbol="A50")
                if a50_df2 is not None and not a50_df2.empty:
                    latest = a50_df2.iloc[-1]
                    result["price"] = self._safe_float(latest.get('最新价'))
                    result["pct_change"] = self._safe_float(latest.get('涨跌幅'))
                    logger.info(f"✅ A50期货获取成功(备选): {result['price']}")
                    return result
            except:
                pass

            logger.warning("A50期货数据获取失败")
            return result

        except Exception as e:
            logger.warning(f"A50期货获取异常: {e}")
            return result

    # ============================================================
    # 7. 综合宏观快照
    # ============================================================
    def get_macro_snapshot(self) -> Dict:
        """获取完整的宏观数据快照（带缓存）"""
        cache_key = "macro_snapshot"
        
        # ✅ 尝试从存储层获取完整快照
        snapshot_file = os.path.join(self._cache.storage_dir, "macro_snapshot.json")
        if os.path.exists(snapshot_file):
            try:
                with open(snapshot_file, 'r') as f:
                    data = json.load(f)
                # 检查缓存时间（2小时内有效）
                if data.get('_cache_time'):
                    cache_time = datetime.fromisoformat(data['_cache_time'])
                    if (datetime.now() - cache_time).total_seconds() < 7200:  # 2小时
                        logger.info("✅ 从存储缓存获取宏观快照")
                        return data.get('data', {})
            except:
                pass

        # 实时获取
        result = {
            "us_market": self.get_us_market(),
            "asia_market": self.get_asia_market(),
            "europe_market": self.get_europe_market(),
            "commodities": self.get_commodities(),
            "forex": self.get_forex(),
            "a50_futures": self.get_a50_futures(),
            "timestamp": datetime.now().isoformat()
        }

        # 保存到存储层
        try:
            with open(snapshot_file, 'w') as f:
                json.dump({
                    '_cache_time': datetime.now().isoformat(),
                    'data': result
                }, f, ensure_ascii=False, indent=2)
            logger.info("✅ 宏观快照已保存到存储缓存")
        except:
            pass

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
        """格式化美股数据"""
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
        """格式化亚太市场数据"""
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
        """格式化欧洲市场数据"""
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
        """格式化大宗商品数据"""
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
        """格式化汇率数据"""
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
        """格式化A50期货数据"""
        result = {}
        if data.get("price"):
            result["price"] = data.get("price")
        if data.get("pct_change"):
            result["pct_change"] = data.get("pct_change")
        return result

    # ============================================================
    # 辅助方法
    # ============================================================
    def _safe_float(self, value) -> Optional[float]:
        """安全转换为浮点数"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    # ============================================================
    # 缓存管理方法（供外部调用）
    # ============================================================
    def clear_cache(self):
        """清空所有缓存"""
        self._cache.clear_all_cache()
        self._last_success_data = {}
        self._has_ever_succeeded = False
        logger.info("✅ 宏观缓存已清空")

    def get_cache_stats(self) -> Dict:
        """获取缓存统计信息"""
        cache_dir = self._cache.storage_dir
        files = [f for f in os.listdir(cache_dir) if f.startswith('macro_') and f.endswith('.json')]
        return {
            "cache_dir": cache_dir,
            "cache_files": len(files),
            "files": files
        }
