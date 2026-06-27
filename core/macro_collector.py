#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观数据采集模块（P0阶段）
提供全球市场、大宗商品、汇率、宏观政策等数据
绝不修改 data_adapter/real_adapter.py
"""

import os
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class MacroCollector:
    """
    宏观数据采集器
    采集范围：美股、欧股、亚太、大宗商品、汇率、A50期货
    """

    def __init__(self):
        self._cache = {}
        self._cache_ttl = 300  # 5分钟缓存

    def _is_cached_valid(self, key: str) -> bool:
        """检查缓存是否有效"""
        if key in self._cache:
            cached_time, _ = self._cache[key]
            if (datetime.now() - cached_time).total_seconds() < self._cache_ttl:
                return True
        return False

    def _get_cached(self, key: str) -> Any:
        """获取缓存数据"""
        if key in self._cache:
            _, data = self._cache[key]
            return data
        return None

    def _set_cache(self, key: str, data: Any):
        """设置缓存"""
        self._cache[key] = (datetime.now(), data)

    # ============================================================
    # 1. 美股数据（三大指数 + 科技巨头 + 费城半导体）
    # ============================================================
    def get_us_market(self) -> Dict:
        """
        获取美股市场数据
        包括：道指、纳指、标普500、费城半导体、科技巨头
        """
        cache_key = "us_market"
        if self._is_cached_valid(cache_key):
            return self._get_cached(cache_key)

        result = {
            "indices": {},
            "semiconductor": {},
            "tech_giants": {},
            "data_source": "AKShare",
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak

            # 获取美股行情
            df = ak.stock_us_spot()

            if df is None or df.empty:
                logger.warning("⚠️ 美股行情数据为空")
                return result

            # 1.1 美股三大指数
            index_keywords = {
                "道琼斯": "DJI",
                "纳斯达克": "IXIC",
                "标普500": "SPX"
            }
            for keyword, code in index_keywords.items():
                matched = df[df['名称'].str.contains(keyword, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][code] = {
                        "name": keyword,
                        "price": self._safe_float(row.get('最新价')),
                        "pct_change": self._safe_float(row.get('涨跌幅')),
                        "volume": self._safe_float(row.get('成交量'))
                    }

            # 1.2 费城半导体指数（SOX）
            sox_keywords = ["费城半导体", "半导体"]
            for kw in sox_keywords:
                matched = df[df['名称'].str.contains(kw, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["semiconductor"] = {
                        "name": row.get('名称', '费城半导体'),
                        "price": self._safe_float(row.get('最新价')),
                        "pct_change": self._safe_float(row.get('涨跌幅'))
                    }
                    break

            # 1.3 科技巨头
            tech_giants = ["苹果", "英伟达", "微软", "谷歌", "亚马逊", "Meta", "特斯拉", "美光", "英特尔", "AMD"]
            for giant in tech_giants:
                matched = df[df['名称'].str.contains(giant, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["tech_giants"][giant] = {
                        "price": self._safe_float(row.get('最新价')),
                        "pct_change": self._safe_float(row.get('涨跌幅'))
                    }

            self._set_cache(cache_key, result)
            logger.info("✅ 美股数据获取成功")
            return result

        except Exception as e:
            logger.warning(f"⚠️ 美股数据获取失败: {e}")
            return result

    # ============================================================
    # 2. 亚太市场数据（日经、韩国、恒生、台湾）
    # ============================================================
    def get_asia_market(self) -> Dict:
        """获取亚太市场数据"""
        cache_key = "asia_market"
        if self._is_cached_valid(cache_key):
            return self._get_cached(cache_key)

        result = {
            "indices": {},
            "data_source": "AKShare",
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak

            # 获取全球指数行情
            df = ak.stock_zh_index_spot()

            if df is None or df.empty:
                logger.warning("⚠️ 亚太市场数据为空")
                return result

            # 亚太指数映射
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
                        "pct_change": self._safe_float(row.get('涨跌幅')),
                        "volume": self._safe_float(row.get('成交量'))
                    }

            self._set_cache(cache_key, result)
            logger.info("✅ 亚太市场数据获取成功")
            return result

        except Exception as e:
            logger.warning(f"⚠️ 亚太市场数据获取失败: {e}")
            return result

    # ============================================================
    # 3. 欧洲市场数据（德国DAX、英国FTSE、法国CAC）
    # ============================================================
    def get_europe_market(self) -> Dict:
        """获取欧洲市场数据"""
        cache_key = "europe_market"
        if self._is_cached_valid(cache_key):
            return self._get_cached(cache_key)

        result = {
            "indices": {},
            "data_source": "AKShare",
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak

            df = ak.stock_zh_index_spot()

            if df is None or df.empty:
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

            self._set_cache(cache_key, result)
            logger.info("✅ 欧洲市场数据获取成功")
            return result

        except Exception as e:
            logger.warning(f"⚠️ 欧洲市场数据获取失败: {e}")
            return result

    # ============================================================
    # 4. 国际大宗商品（原油、黄金）
    # ============================================================
    def get_commodities(self) -> Dict:
        """获取大宗商品数据（WTI原油、布伦特原油、黄金）"""
        cache_key = "commodities"
        if self._is_cached_valid(cache_key):
            return self._get_cached(cache_key)

        result = {
            "oil": {},
            "gold": {},
            "data_source": "AKShare",
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak

            # 4.1 原油
            try:
                oil_df = ak.futures_foreign_main_sina(symbol="CL")
                if oil_df is not None and not oil_df.empty:
                    latest = oil_df.iloc[-1]
                    result["oil"]["WTI"] = {
                        "price": self._safe_float(latest.get('最新价')),
                        "pct_change": self._safe_float(latest.get('涨跌幅')),
                        "volume": self._safe_float(latest.get('成交量'))
                    }
            except:
                pass

            try:
                oil_df_b = ak.futures_foreign_main_sina(symbol="B")
                if oil_df_b is not None and not oil_df_b.empty:
                    latest = oil_df_b.iloc[-1]
                    result["oil"]["Brent"] = {
                        "price": self._safe_float(latest.get('最新价')),
                        "pct_change": self._safe_float(latest.get('涨跌幅'))
                    }
            except:
                pass

            # 4.2 黄金
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

            self._set_cache(cache_key, result)
            logger.info("✅ 大宗商品数据获取成功")
            return result

        except Exception as e:
            logger.warning(f"⚠️ 大宗商品数据获取失败: {e}")
            return result

    # ============================================================
    # 5. 人民币汇率
    # ============================================================
    def get_forex(self) -> Dict:
        """获取人民币汇率数据"""
        cache_key = "forex"
        if self._is_cached_valid(cache_key):
            return self._get_cached(cache_key)

        result = {
            "usd_cny": {},
            "data_source": "AKShare",
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak

            # 获取在岸人民币
            try:
                cny_df = ak.currency_rates()
                if cny_df is not None and not cny_df.empty:
                    # 查找美元兑人民币
                    matched = cny_df[cny_df['货币名称'].str.contains('美元', na=False)]
                    if not matched.empty:
                        row = matched.iloc[0]
                        result["usd_cny"]["onshore"] = self._safe_float(row.get('最新价'))
                        result["usd_cny"]["pct_change"] = self._safe_float(row.get('涨跌幅'))
            except:
                pass

            # 获取人民币中间价（备选方案）
            try:
                mid_df = ak.currency_rates_central()
                if mid_df is not None and not mid_df.empty:
                    # 查找美元兑人民币中间价
                    matched = mid_df[mid_df['货币名称'].str.contains('美元', na=False)]
                    if not matched.empty:
                        row = matched.iloc[0]
                        result["usd_cny"]["central"] = self._safe_float(row.get('最新价'))
            except:
                pass

            self._set_cache(cache_key, result)
            logger.info("✅ 汇率数据获取成功")
            return result

        except Exception as e:
            logger.warning(f"⚠️ 汇率数据获取失败: {e}")
            return result

    # ============================================================
    # 6. A50期货夜盘
    # ============================================================
    def get_a50_futures(self) -> Dict:
        """获取A50期货数据"""
        cache_key = "a50_futures"
        if self._is_cached_valid(cache_key):
            return self._get_cached(cache_key)

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
            except:
                pass

            # 如果失败，尝试另一种方式
            if result["price"] is None:
                try:
                    a50_df2 = ak.futures_main_sina(symbol="A50")
                    if a50_df2 is not None and not a50_df2.empty:
                        latest = a50_df2.iloc[-1]
                        result["price"] = self._safe_float(latest.get('最新价'))
                        result["pct_change"] = self._safe_float(latest.get('涨跌幅'))
                except:
                    pass

            self._set_cache(cache_key, result)
            logger.info("✅ A50期货数据获取成功")
            return result

        except Exception as e:
            logger.warning(f"⚠️ A50期货数据获取失败: {e}")
            return result

    # ============================================================
    # 7. 综合宏观快照（一次性获取所有宏观数据）
    # ============================================================
    def get_macro_snapshot(self) -> Dict:
        """
        获取完整的宏观数据快照
        包含：美股、亚太、欧洲、大宗商品、汇率、A50期货
        """
        result = {
            "us_market": self.get_us_market(),
            "asia_market": self.get_asia_market(),
            "europe_market": self.get_europe_market(),
            "commodities": self.get_commodities(),
            "forex": self.get_forex(),
            "a50_futures": self.get_a50_futures(),
            "timestamp": datetime.now().isoformat()
        }
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
    # 8. 格式化宏观数据（供推送使用）
    # ============================================================
    def format_for_push(self) -> Dict:
        """
        获取并格式化宏观数据，供推送使用
        返回结构化的宏观数据
        """
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
        
        # 指数
        for code, idx in data.get("indices", {}).items():
            if idx.get("price"):
                result["indices"].append({
                    "name": idx.get("name", code),
                    "price": idx.get("price"),
                    "pct_change": idx.get("pct_change")
                })
        
        # 半导体
        sem = data.get("semiconductor", {})
        if sem.get("price"):
            result["semiconductor"] = {
                "name": sem.get("name", "费城半导体"),
                "price": sem.get("price"),
                "pct_change": sem.get("pct_change")
            }
        
        # 科技巨头
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
        
        # 原油
        for name, oil in data.get("oil", {}).items():
            if oil.get("price"):
                result["oil"].append({
                    "name": name,
                    "price": oil.get("price"),
                    "pct_change": oil.get("pct_change")
                })
        
        # 黄金
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
