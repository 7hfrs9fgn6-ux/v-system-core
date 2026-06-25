#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
板块数据聚合器
通过个股数据反推板块数据
策略：Tushare成分股 + 个股行情 → 加权聚合 → 板块指标
"""

import os
import time
import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 申万一级行业代码（用于获取成分股）
SECTOR_CODE_MAP = {
    "电子": "801080",
    "计算机": "801750",
    "通信": "801770",
    "传媒": "801760",
    "医药生物": "801150",
    "食品饮料": "801120",
    "家用电器": "801110",
    "电力设备": "801730",
    "汽车": "801880",
    "国防军工": "801740",
    "银行": "801780",
    "非银金融": "801790",
    "公用事业": "801160",
    "煤炭": "801950",
    "石油石化": "801960",
}

# 板块阈值（沿用现有配置）
THRESHOLD_MAP = {
    "电子": 25.0, "计算机": 25.0, "通信": 20.0, "传媒": 25.0, "医药生物": 30.0,
    "食品饮料": 25.0, "家用电器": 18.0, "电力设备": 25.0, "汽车": 25.0, "国防军工": 25.0,
    "银行": 20.0, "非银金融": 20.0, "公用事业": 15.0, "煤炭": 20.0, "石油石化": 20.0,
}


class SectorAggregator:
    """
    板块数据聚合器
    使用 Tushare 个股数据聚合得到板块数据
    """

    def __init__(self):
        self.tushare_token = os.environ.get("TUSHARE_TOKEN")
        self.use_tushare = bool(self.tushare_token and self.tushare_token != "dummy")
        self._cache = {}
        self._cache_ttl = 3600  # 1小时缓存

        # 成分股缓存
        self._members_cache = {}
        self._members_ttl = 86400  # 24小时缓存

    def get_sector_constituents(self, sector_code: str) -> List[str]:
        """
        获取板块成分股列表
        使用 Tushare index_member 接口
        """
        cache_key = sector_code
        if cache_key in self._members_cache:
            cached_time, data = self._members_cache[cache_key]
            if (datetime.now() - cached_time).total_seconds() < self._members_ttl:
                return data

        if not self.use_tushare:
            logger.warning("Tushare 未配置，无法获取成分股")
            return []

        try:
            import tushare as ts
            ts.set_token(self.tushare_token)
            pro = ts.pro_api()

            # 获取指数成分股
            df = pro.index_member(ts_code=f"{sector_code}.SI", fields="con_code")
            if df is not None and not df.empty:
                stocks = df['con_code'].tolist()
                logger.info(f"✅ 获取到 {len(stocks)} 只成分股")
                self._members_cache[cache_key] = (datetime.now(), stocks)
                return stocks
            else:
                logger.warning(f"⚠️ 板块 {sector_code} 无成分股数据")
                return []

        except Exception as e:
            logger.warning(f"⚠️ 获取成分股失败 ({e})")
            return []

    def get_stock_daily(self, stock_codes: List[str], days: int = 365) -> pd.DataFrame:
        """
        批量获取个股日线数据
        使用 Tushare daily 接口
        """
        if not self.use_tushare or not stock_codes:
            return pd.DataFrame()

        try:
            import tushare as ts
            ts.set_token(self.tushare_token)
            pro = ts.pro_api()

            # 分批获取（避免请求过大）
            all_data = []
            batch_size = 50
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

            for i in range(0, len(stock_codes), batch_size):
                batch = stock_codes[i:i + batch_size]
                codes_str = ','.join(batch)

                df = pro.daily(ts_code=codes_str, start_date=start_date, end_date=end_date)

                if df is not None and not df.empty:
                    all_data.append(df)

                # 限流保护
                time.sleep(0.5)

            if all_data:
                result = pd.concat(all_data, ignore_index=True)
                logger.info(f"✅ 获取到 {len(result)} 条个股日线数据")
                return result
            else:
                logger.warning("⚠️ 个股日线数据为空")
                return pd.DataFrame()

        except Exception as e:
            logger.warning(f"⚠️ 获取个股日线失败 ({e})")
            return pd.DataFrame()

    def aggregate_sector(self, sector_name: str, stock_data: pd.DataFrame) -> Dict:
        """
        聚合个股数据得到板块指标
        """
        if stock_data.empty:
            return self._get_empty_result(sector_name)

        try:
            # 1. 计算每只股票的52周回撤
            stock_drawdowns = []
            for stock_code, group in stock_data.groupby('ts_code'):
                if len(group) > 1:
                    high_52w = group['high'].max()
                    current = group['close'].iloc[-1]
                    if high_52w > 0:
                        drawdown = round((high_52w - current) / high_52w * 100, 1)
                    else:
                        drawdown = 0
                    stock_drawdowns.append({
                        'ts_code': stock_code,
                        'drawdown': drawdown,
                        'close': current,
                        'high_52w': high_52w
                    })

            if not stock_drawdowns:
                return self._get_empty_result(sector_name)

            # 2. 加权计算（等权/市值加权）
            df_stocks = pd.DataFrame(stock_drawdowns)

            # 等权平均回撤
            avg_drawdown = df_stocks['drawdown'].mean()

            # 中位数回撤（抗异常值）
            median_drawdown = df_stocks['drawdown'].median()

            # 最大值回撤
            max_drawdown = df_stocks['drawdown'].max()

            # 3. 计算信号等级
            threshold = THRESHOLD_MAP.get(sector_name, 25.0)
            drawdown = round(avg_drawdown, 1)

            excess = drawdown - threshold
            if excess >= 10:
                level = 4
            elif excess >= 5:
                level = 3
            elif excess >= 0:
                level = 2
            elif excess >= -5:
                level = 1
            elif excess >= -10:
                level = -1
            else:
                level = -2

            return {
                "sector": sector_name,
                "drawdown": drawdown,
                "threshold": threshold,
                "avg_drawdown": round(avg_drawdown, 1),
                "median_drawdown": round(median_drawdown, 1),
                "max_drawdown": round(max_drawdown, 1),
                "stock_count": len(df_stocks),
                "signal_level": level,
                "key_driver": f"成分股聚合({len(df_stocks)}只)" if level > 0 else None,
                "data_source": "Tushare个股聚合",
            }

        except Exception as e:
            logger.warning(f"⚠️ 板块聚合失败 {sector_name}: {e}")
            return self._get_empty_result(sector_name)

    def _get_empty_result(self, sector_name: str) -> Dict:
        """返回空结果"""
        return {
            "sector": sector_name,
            "drawdown": 0,
            "threshold": THRESHOLD_MAP.get(sector_name, 25.0),
            "signal_level": 0,
            "key_driver": None,
            "data_source": "无数据",
            "stock_count": 0,
        }

    def get_all_sectors(self, use_cache: bool = True) -> Dict[str, Dict]:
        """
        获取所有板块的聚合数据
        """
        if use_cache and "all_sectors" in self._cache:
            cached_time, data = self._cache["all_sectors"]
            if (datetime.now() - cached_time).total_seconds() < self._cache_ttl:
                logger.info("使用缓存的板块聚合数据")
                return data

        results = {}

        for sector_name, sector_code in SECTOR_CODE_MAP.items():
            logger.info(f"📊 处理板块: {sector_name}")

            # 1. 获取成分股
            stocks = self.get_sector_constituents(sector_code)
            if not stocks:
                results[sector_name] = self._get_empty_result(sector_name)
                continue

            # 2. 获取成分股日线
            stock_data = self.get_stock_daily(stocks, days=365)
            if stock_data.empty:
                results[sector_name] = self._get_empty_result(sector_name)
                continue

            # 3. 聚合
            result = self.aggregate_sector(sector_name, stock_data)
            results[sector_name] = result

            # 限流保护
            time.sleep(1)

        # 缓存结果
        self._cache["all_sectors"] = (datetime.now(), results)
        return results


def compare_with_akshare(akshare_data: Dict, tushare_data: Dict) -> Dict:
    """
    对比 Tushare 聚合数据 和 AKShare 数据
    用于交叉验证
    """
    comparison = {}

    for sector, ts_result in tushare_data.items():
        ak_result = akshare_data.get(sector, {})

        ts_drawdown = ts_result.get('drawdown', 0)
        ak_drawdown = ak_result.get('drawdown', 0)

        # 差异计算
        diff = abs(ts_drawdown - ak_drawdown)

        if diff < 2:
            status = "✅ 一致"
        elif diff < 5:
            status = "🟡 存在偏差"
        else:
            status = "🔴 差异较大"

        comparison[sector] = {
            "tushare_聚合回撤": ts_drawdown,
            "akshare_回撤": ak_drawdown,
            "差异": diff,
            "状态": status,
            "ts_成分股数": ts_result.get('stock_count', 0),
        }

    return comparison
