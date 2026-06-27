#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观数据采集模块（永久缓存 + 健壮列名识别）
支持美股、亚太、欧洲、大宗商品、汇率、A50期货
数据永久缓存，每日首次获取后不再重复请求
"""

import os
import json
import logging
import time
from datetime import datetime
from typing import Dict, Optional, List, Any

os.environ['TQDM_DISABLE'] = '1'

from core.macro_cache import MacroCache
from core.macro_history import MacroHistory

logger = logging.getLogger(__name__)


class MacroCollector:
    """宏观数据采集器（修复列名识别版）"""

    def __init__(self):
        self._cache = MacroCache()
        self._retry_count = 2
        self._retry_delay = [1, 2]
        self._timeout = 10
        logger.info(f"📁 宏观缓存目录: {self._cache.storage_dir}")

    # ============================================================
    # 通用辅助方法
    # ============================================================
    def _safe_float(self, value) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _find_column(self, df, candidates: List[str]) -> Optional[str]:
        """🔧 增强列名查找：支持中英文、大小写、部分匹配"""
        if df is None or df.empty:
            return None
        for col in df.columns:
            col_lower = col.lower().strip()
            for cand in candidates:
                cand_lower = cand.lower().strip()
                if cand_lower in col_lower or col_lower in cand_lower:
                    return col
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

    # ============================================================
    # 核心：获取宏观快照（永久缓存）
    # ============================================================
    def get_macro_snapshot(self) -> Dict:
        """
        获取宏观快照：永久缓存，每天只获取一次
        """
        cache_file = os.path.join(self._cache.storage_dir, "macro_snapshot.json")

        # 如果缓存存在且包含今日数据，直接返回
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                if self._is_today_data(data):
                    logger.info(f"✅ 使用今日缓存宏观快照: {cache_file}")
                    return data.get('data', {})
                else:
                    logger.info("📅 缓存存在但非今日数据，刷新...")
            except:
                pass

        # 缓存不存在或非今日数据，重新获取
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
        # 保存时标记今日日期
        with open(cache_file, 'w') as f:
            json.dump({
                '_cache_date': datetime.now().strftime("%Y-%m-%d"),
                '_cache_time': datetime.now().isoformat(),
                'data': result
            }, f, ensure_ascii=False, indent=2)
        logger.info(f"✅ 宏观快照已保存: {cache_file}")
        return result

    def _is_today_data(self, data: Dict) -> bool:
        """检查缓存是否包含今日数据"""
        if '_cache_date' in data:
            return data['_cache_date'] == datetime.now().strftime("%Y-%m-%d")
        if '_cache_time' in data:
            try:
                cache_date = datetime.fromisoformat(data['_cache_time']).strftime("%Y-%m-%d")
                return cache_date == datetime.now().strftime("%Y-%m-%d")
            except:
                pass
        return False

    # ============================================================
    # 格式化输出（供推送使用）
    # ============================================================
    def format_for_push(self) -> Dict:
        snapshot = self.get_macro_snapshot()
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
    # 1. 美股市场（修复列名识别）
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
                logger.warning("美股数据为空")
                return result

            # 🔧 健壮列名查找
            name_col = self._find_column(df, ['名称', 'name', 'Name'])
            price_col = self._find_column(df, ['最新价', 'price', 'close', '收盘'])
            pct_col = self._find_column(df, ['涨跌幅', 'change', 'pct_change', '涨幅'])

            if not name_col or not price_col:
                logger.warning(f"美股列名不匹配: 名称列={name_col}, 价格列={price_col}")
                return result

            # 指数
            index_keywords = ["道琼斯", "纳斯达克", "标普500"]
            for keyword in index_keywords:
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
            tech_giants = ["苹果", "英伟达", "微软", "谷歌", "亚马逊", "Meta", "特斯拉", "美光", "英特尔", "AMD"]
            for giant in tech_giants:
                matched = df[df[name_col].str.contains(giant, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["tech_giants"][giant] = {
                        "name": giant,
                        "price": self._safe_float(row.get(price_col)),
                        "pct_change": self._safe_float(row.get(pct_col)) if pct_col else None
                    }

            logger.info(f"✅ 美股获取: {len(result['indices'])}个指数, {len(result['tech_giants'])}只科技股")
            return result

        except Exception as e:
            logger.warning(f"美股获取异常: {e}")
            return result

    # ============================================================
    # 2. 亚太市场
    # ============================================================
    def _fetch_asia_market_impl(self) -> Dict:
        result = {
            "indices": {},
            "data_source": "AKShare",
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak
            df = None
            # 尝试多个接口
            for func_name in ['index_zh_spot', 'stock_zh_index_spot']:
                try:
                    if hasattr(ak, func_name):
                        df = getattr(ak, func_name)()
                        if df is not None and not df.empty:
                            break
                except:
                    continue
            if df is None or df.empty:
                logger.warning("亚太数据为空")
                return result

            name_col = self._find_column(df, ['名称', 'name', 'Name'])
            price_col = self._find_column(df, ['最新价', 'price', 'close', '收盘'])
            pct_col = self._find_column(df, ['涨跌幅', 'change', 'pct_change', '涨幅'])

            if not name_col or not price_col:
                logger.warning(f"亚太列名不匹配: 名称列={name_col}, 价格列={price_col}")
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
                        "price": self._safe_float(row.get(price_col)),
                        "pct_change": self._safe_float(row.get(pct_col)) if pct_col else None
                    }

            logger.info(f"✅ 亚太获取: {len(result['indices'])}个指数")
            return result

        except Exception as e:
            logger.warning(f"亚太获取异常: {e}")
            return result

    # ============================================================
    # 3. 欧洲市场
    # ============================================================
    def _fetch_europe_market_impl(self) -> Dict:
        result = {
            "indices": {},
            "data_source": "AKShare",
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak
            df = None
            for func_name in ['index_zh_spot', 'stock_zh_index_spot']:
                try:
                    if hasattr(ak, func_name):
                        df = getattr(ak, func_name)()
                        if df is not None and not df.empty:
                            break
                except:
                    continue
            if df is None or df.empty:
                logger.warning("欧洲数据为空")
                return result

            name_col = self._find_column(df, ['名称', 'name', 'Name'])
            price_col = self._find_column(df, ['最新价', 'price', 'close', '收盘'])
            pct_col = self._find_column(df, ['涨跌幅', 'change', 'pct_change', '涨幅'])

            if not name_col or not price_col:
                logger.warning(f"欧洲列名不匹配: 名称列={name_col}, 价格列={price_col}")
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
                        "price": self._safe_float(row.get(price_col)),
                        "pct_change": self._safe_float(row.get(pct_col)) if pct_col else None
                    }

            logger.info(f"✅ 欧洲获取: {len(result['indices'])}个指数")
            return result

        except Exception as e:
            logger.warning(f"欧洲获取异常: {e}")
            return result

    # ============================================================
    # 4. 大宗商品
    # ============================================================
    def _fetch_commodities_impl(self) -> Dict:
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
                df = ak.futures_foreign_main_sina(symbol="CL")
                if df is not None and not df.empty:
                    latest = df.iloc[-1]
                    price_col = self._find_column(df, ['最新价', 'price'])
                    pct_col = self._find_column(df, ['涨跌幅', 'change'])
                    result["oil"]["WTI"] = {
                        "name": "WTI",
                        "price": self._safe_float(latest.get(price_col)) if price_col else None,
                        "pct_change": self._safe_float(latest.get(pct_col)) if pct_col else None
                    }
            except Exception as e:
                logger.debug(f"WTI原油获取失败: {e}")

            # 原油 布伦特
            try:
                df = ak.futures_foreign_main_sina(symbol="B")
                if df is not None and not df.empty:
                    latest = df.iloc[-1]
                    price_col = self._find_column(df, ['最新价', 'price'])
                    pct_col = self._find_column(df, ['涨跌幅', 'change'])
                    result["oil"]["Brent"] = {
                        "name": "布伦特",
                        "price": self._safe_float(latest.get(price_col)) if price_col else None,
                        "pct_change": self._safe_float(latest.get(pct_col)) if pct_col else None
                    }
            except Exception as e:
                logger.debug(f"布伦特原油获取失败: {e}")

            # 黄金
            try:
                df = ak.futures_foreign_main_sina(symbol="GC")
                if df is not None and not df.empty:
                    latest = df.iloc[-1]
                    price_col = self._find_column(df, ['最新价', 'price'])
                    pct_col = self._find_column(df, ['涨跌幅', 'change'])
                    result["gold"] = {
                        "price": self._safe_float(latest.get(price_col)) if price_col else None,
                        "pct_change": self._safe_float(latest.get(pct_col)) if pct_col else None
                    }
            except Exception as e:
                logger.debug(f"黄金获取失败: {e}")

            logger.info(f"✅ 大宗商品获取: 原油{len(result['oil'])}种, 黄金{'有' if result['gold'] else '无'}")
            return result

        except Exception as e:
            logger.warning(f"大宗商品获取异常: {e}")
            return result

    # ============================================================
    # 5. 人民币汇率
    # ============================================================
    def _fetch_forex_impl(self) -> Dict:
        result = {
            "usd_cny": {},
            "data_source": "AKShare",
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak

            # 在岸人民币
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
            except Exception as e:
                logger.debug(f"在岸汇率获取失败: {e}")

            # 中间价
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
            except Exception as e:
                logger.debug(f"中间价获取失败: {e}")

            logger.info(f"✅ 汇率获取: 在岸 {result['usd_cny'].get('onshore', '无')}")
            return result

        except Exception as e:
            logger.warning(f"汇率获取异常: {e}")
            return result

    # ============================================================
    # 6. A50期货
    # ============================================================
    def _fetch_a50_impl(self) -> Dict:
        result = {
            "price": None,
            "pct_change": None,
            "data_source": "AKShare",
            "timestamp": datetime.now().isoformat()
        }

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
                except Exception as e:
                    logger.debug(f"A50期货 {symbol} 获取失败: {e}")
                    continue

            logger.info(f"✅ A50期货: {result['price'] if result['price'] else '无'}")
            return result

        except Exception as e:
            logger.warning(f"A50期货获取异常: {e}")
            return result

    # ============================================================
    # 格式化方法（供推送使用）
    # ============================================================
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

    # ============================================================
    # 历史记录（post阶段调用）
    # ============================================================
    def record_today_data(self):
        """将今日宏观数据追加到历史记录（仅post阶段调用）"""
        try:
            from core.macro_history import MacroHistory
            history = MacroHistory()
            snapshot = self.get_macro_snapshot()

            # 美股
            us = snapshot.get("us_market", {})
            history.record_us_indices(us.get("indices", {}))
            history.record_tech_giants(us.get("tech_giants", {}))

            # 亚太
            asia = snapshot.get("asia_market", {})
            history.record_asia_indices(asia.get("indices", {}))

            # 欧洲
            euro = snapshot.get("europe_market", {})
            history.record_europe_indices(euro.get("indices", {}))

            # 大宗商品
            comm = snapshot.get("commodities", {})
            history.record_commodities(comm.get("oil", {}), comm.get("gold", {}))

            # 汇率
            forex = snapshot.get("forex", {})
            history.record_forex(forex.get("usd_cny", {}))

            # A50
            a50 = snapshot.get("a50_futures", {})
            history.record_a50(a50)

            logger.info("✅ 今日宏观数据已追加到历史记录")
        except Exception as e:
            logger.warning(f"记录宏观历史失败: {e}")
