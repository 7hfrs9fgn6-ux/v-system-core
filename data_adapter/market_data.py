#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场数据采集模块（修复版）
提供：多指数行情、涨跌家数、板块资金流向（用于推送展示）
同时将每日市场数据增量追加到历史 CSV，永不覆盖
修复：指数接口使用多个备选，增强列名识别，永久缓存按日期去重
"""

import os
import json
import pandas as pd
import logging
from datetime import datetime
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


class MarketDataCollector:
    """市场数据采集器（永久缓存 + 增量历史记录）"""

    def __init__(self, storage_dir: str = "memory_data/"):
        self.storage_dir = storage_dir
        self._ensure_storage_dir()
        self.today = datetime.now().strftime("%Y-%m-%d")
        logger.info(f"📁 市场数据缓存目录: {os.path.abspath(self.storage_dir)}")

    def _ensure_storage_dir(self):
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir, exist_ok=True)

    def _get_file_path(self, filename: str) -> str:
        return os.path.join(self.storage_dir, filename)

    def _save_json(self, filename: str, data: Dict) -> str:
        file_path = self._get_file_path(filename)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return file_path

    def _load_json(self, filename: str) -> Optional[Dict]:
        file_path = self._get_file_path(filename)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return None
        return None

    def _load_csv(self, filename: str) -> pd.DataFrame:
        file_path = self._get_file_path(filename)
        if os.path.exists(file_path):
            try:
                return pd.read_csv(file_path)
            except:
                return pd.DataFrame()
        return pd.DataFrame()

    def _save_csv(self, filename: str, df: pd.DataFrame):
        file_path = self._get_file_path(filename)
        df.to_csv(file_path, index=False)
        logger.debug(f"✅ 保存 {filename}: {len(df)} 条记录")

    def _is_today_recorded(self, df: pd.DataFrame, date_col: str = "date") -> bool:
        """检查今天的数据是否已经存在"""
        if df.empty or date_col not in df.columns:
            return False
        return self.today in df[date_col].values

    # ---------- 辅助方法 ----------
    def _safe_float(self, value) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _find_column(self, df, candidates):
        """增强的列名查找：支持多个候选词，忽略大小写"""
        if df is None or df.empty:
            return None
        for c in df.columns:
            c_lower = c.lower()
            for cand in candidates:
                if cand.lower() in c_lower or c_lower in cand.lower():
                    return c
        return None

    # ============================================================
    # 1. 获取指数数据（用于推送展示 + 历史记录）
    # ============================================================
    def get_indices(self) -> Dict:
        """
        获取主要指数行情：永久缓存，今天只获取一次
        """
        cache_file = "market_indices.json"
        cached = self._load_json(cache_file)
        if cached and self._is_data_today(cached):
            logger.info(f"✅ 从缓存读取指数数据: {cache_file}")
            return cached

        logger.info("📊 刷新指数数据...")
        result = self._fetch_indices_impl()
        if result and result.get('indices'):
            self._save_json(cache_file, result)
            logger.info(f"✅ 指数数据已缓存: {len(result['indices'])} 个指数")
        else:
            logger.warning("⚠️ 指数数据获取失败，保留旧缓存")
        return result

    def _fetch_indices_impl(self) -> Dict:
        """实际获取指数数据（使用多个备选接口）"""
        result = {"indices": {}, "timestamp": datetime.now().isoformat()}

        try:
            import akshare as ak
            df = None
            # 方法1：index_zh_spot（新版）
            try:
                df = ak.index_zh_spot()
            except:
                pass
            # 方法2：stock_zh_index_spot（旧版）
            if df is None or df.empty:
                try:
                    df = ak.stock_zh_index_spot()
                except:
                    pass
            # 方法3：stock_zh_a_spot_em（备选）
            if df is None or df.empty:
                try:
                    df = ak.stock_zh_a_spot_em()
                except:
                    pass

            if df is None or df.empty:
                logger.warning("所有指数接口均返回空数据")
                return result

            # 识别列名
            name_col = self._find_column(df, ['名称', 'name'])
            code_col = self._find_column(df, ['代码', 'code'])
            price_col = self._find_column(df, ['最新价', 'price', 'close'])
            pct_col = self._find_column(df, ['涨跌幅', 'change', 'pct_change'])
            volume_col = self._find_column(df, ['成交量', 'volume'])
            amount_col = self._find_column(df, ['成交额', 'amount'])

            if not name_col or not price_col:
                logger.warning("指数数据列名不匹配，尝试使用默认列")
                # 尝试硬编码列名
                if '名称' in df.columns and '最新价' in df.columns:
                    name_col, price_col = '名称', '最新价'
                    pct_col = '涨跌幅' if '涨跌幅' in df.columns else None
                else:
                    return result

            index_map = {
                "上证指数": "000001.SH",
                "深证成指": "399001.SZ",
                "创业板指": "399006.SZ",
                "科创50": "000688.SH",
                "北证50": "899050.BJ"
            }

            for name, code in index_map.items():
                # 先按代码匹配
                matched = df[df[code_col] == code] if code_col in df.columns else pd.DataFrame()
                if matched.empty:
                    # 按名称匹配
                    matched = df[df[name_col].str.contains(name, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    idx_data = {
                        "code": code,
                        "price": self._safe_float(row.get(price_col)),
                        "pct_change": self._safe_float(row.get(pct_col)) if pct_col else 0,
                        "volume": self._safe_float(row.get(volume_col)) if volume_col else 0,
                        "amount": self._safe_float(row.get(amount_col)) if amount_col else 0,
                        "date": datetime.now().strftime("%Y-%m-%d")
                    }
                    result["indices"][name] = idx_data

            logger.info(f"✅ 获取到 {len(result['indices'])} 个指数数据")
            return result

        except Exception as e:
            logger.warning(f"指数行情获取失败: {e}")
            return result

    # ============================================================
    # 2. 涨跌家数统计
    # ============================================================
    def get_market_stats(self) -> Dict:
        """获取市场涨跌家数统计：永久缓存，今天只获取一次"""
        cache_file = "market_stats.json"
        cached = self._load_json(cache_file)
        if cached and self._is_data_today(cached):
            logger.info(f"✅ 从缓存读取涨跌家数: {cache_file}")
            return cached

        logger.info("📊 刷新涨跌家数...")
        result = self._fetch_stats_impl()
        if result and result.get('total', 0) > 0:
            self._save_json(cache_file, result)
        return result

    def _fetch_stats_impl(self) -> Dict:
        """实际获取涨跌家数"""
        result = {
            "up": 0,
            "down": 0,
            "flat": 0,
            "total": 0,
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak
            # 方法1：stock_zh_a_spot_em
            df = ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                pct_col = self._find_column(df, ['涨跌幅', 'change'])
                if pct_col:
                    up = (df[pct_col] > 0).sum()
                    down = (df[pct_col] < 0).sum()
                    flat = (df[pct_col] == 0).sum()
                    result["up"] = int(up)
                    result["down"] = int(down)
                    result["flat"] = int(flat)
                    result["total"] = int(up + down + flat)
                    logger.info(f"✅ 涨跌家数: 上涨{up}家, 下跌{down}家, 平盘{flat}家")
                    return result
            # 方法2：stock_zh_index_spot（备选）
            df = ak.stock_zh_index_spot()
            if df is not None and not df.empty:
                pct_col = self._find_column(df, ['涨跌幅', 'change'])
                if pct_col:
                    up = (df[pct_col] > 0).sum()
                    down = (df[pct_col] < 0).sum()
                    flat = (df[pct_col] == 0).sum()
                    result["up"] = int(up)
                    result["down"] = int(down)
                    result["flat"] = int(flat)
                    result["total"] = int(up + down + flat)
                    logger.info(f"✅ 涨跌家数（备选）: 上涨{up}家, 下跌{down}家, 平盘{flat}家")
                    return result
        except Exception as e:
            logger.warning(f"涨跌家数获取失败: {e}")
        return result

    # ============================================================
    # 3. 板块资金流向TOP5
    # ============================================================
    def get_sector_flow(self) -> Dict:
        """获取板块资金流向TOP5：永久缓存，今天只获取一次"""
        cache_file = "sector_flow.json"
        cached = self._load_json(cache_file)
        if cached and self._is_data_today(cached):
            logger.info(f"✅ 从缓存读取板块资金流向: {cache_file}")
            return cached

        logger.info("📊 刷新板块资金流向...")
        result = self._fetch_flow_impl()
        if result and (result.get('net_inflow_top5') or result.get('net_outflow_top5')):
            self._save_json(cache_file, result)
        return result

    def _fetch_flow_impl(self) -> Dict:
        """实际获取板块资金流向"""
        result = {
            "net_inflow_top5": [],
            "net_outflow_top5": [],
            "timestamp": datetime.now().isoformat()
        }

        try:
            import akshare as ak
            # 方法1：stock_sector_spot
            df = ak.stock_sector_spot()
            if df is not None and not df.empty:
                inflow_col = self._find_column(df, ['主力净流入', 'main_net_inflow'])
                if inflow_col:
                    df_sorted = df.sort_values(by=inflow_col, ascending=False)
                    for _, row in df_sorted.head(5).iterrows():
                        result["net_inflow_top5"].append({
                            "sector": row.get('名称', ''),
                            "flow": self._safe_float(row.get(inflow_col))
                        })
                    for _, row in df_sorted.tail(5).iterrows():
                        result["net_outflow_top5"].append({
                            "sector": row.get('名称', ''),
                            "flow": self._safe_float(row.get(inflow_col))
                        })
                    logger.info("✅ 板块资金流向: 流入TOP5, 流出TOP5")
                    return result
            # 方法2：使用行业指数涨跌幅近似
            df = ak.stock_zh_index_spot()
            if df is not None and not df.empty:
                sector_df = df[df['名称'].str.contains('申万|行业', na=False)]
                if not sector_df.empty:
                    pct_col = self._find_column(sector_df, ['涨跌幅', 'change'])
                    if pct_col:
                        df_sorted = sector_df.sort_values(by=pct_col, ascending=False)
                        for _, row in df_sorted.head(5).iterrows():
                            result["net_inflow_top5"].append({
                                "sector": row.get('名称', ''),
                                "flow": self._safe_float(row.get(pct_col))
                            })
                        for _, row in df_sorted.tail(5).iterrows():
                            result["net_outflow_top5"].append({
                                "sector": row.get('名称', ''),
                                "flow": self._safe_float(row.get(pct_col))
                            })
                        logger.info("✅ 板块资金流向（近似）: 流入TOP5, 流出TOP5")
                        return result
        except Exception as e:
            logger.warning(f"板块资金流向获取失败: {e}")
        return result

    # ============================================================
    # 4. 日期检查
    # ============================================================
    def _is_data_today(self, data: Dict) -> bool:
        """检查数据是否包含今日记录"""
        if not data:
            return False
        if 'timestamp' in data and self.today in data['timestamp']:
            return True
        if 'indices' in data:
            for idx in data['indices'].values():
                if isinstance(idx, dict) and idx.get('date') == self.today:
                    return True
        if 'up' in data and 'timestamp' in data and self.today in data['timestamp']:
            return True
        return False

    # ============================================================
    # 5. 增量历史记录
    # ============================================================
    def record_today_history(self, indices_data: Dict, stats_data: Dict) -> bool:
        """
        将今日市场数据追加到历史 CSV
        返回: True 表示写入成功，False 表示今日已存在或写入失败
        """
        filename = "market_history.csv"
        df = self._load_csv(filename)

        if self._is_today_recorded(df):
            logger.info("⏭️ 今日市场历史已存在，跳过记录")
            return False

        record = {
            "date": self.today,
            "up": stats_data.get("up", 0),
            "down": stats_data.get("down", 0),
            "flat": stats_data.get("flat", 0),
            "total": stats_data.get("total", 0)
        }

        # 添加各指数数据
        indices = indices_data.get("indices", {})
        for name, idx in indices.items():
            prefix = name.replace("指数", "").strip()
            record[f"{prefix}_price"] = idx.get("price")
            record[f"{prefix}_pct"] = idx.get("pct_change")

        new_df = pd.DataFrame([record])
        df = pd.concat([df, new_df], ignore_index=True)
        self._save_csv(filename, df)
        logger.info(f"✅ 今日市场历史已追加: {self.today} (上涨{record['up']}家, 下跌{record['down']}家)")
        return True

    def get_market_history(self, days: int = 30) -> pd.DataFrame:
        """获取最近 N 天的市场历史数据"""
        filename = "market_history.csv"
        df = self._load_csv(filename)
        if df.empty:
            return df
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            cutoff = datetime.now() - pd.Timedelta(days=days)
            return df[df['date'] >= cutoff]
        return df
