#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场数据采集模块（永久缓存版 - 无强制刷新）
提供：多指数行情、涨跌家数、板块资金流向（用于推送展示）
数据永久存储到 memory_data/，每天只获取一次（自动判断）
"""

import os
import json
import pandas as pd
import logging
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class MarketDataCollector:
    """市场数据采集器（永久缓存版）"""

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

    # ---------- 辅助方法 ----------
    def _safe_float(self, value) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _find_column(self, df, candidates):
        for c in df.columns:
            for cand in candidates:
                if cand in c or c in cand:
                    return c
        return None

    def _is_data_today(self, data: Dict) -> bool:
        """检查数据是否包含今日记录"""
        if not data:
            return False
        # 检查 timestamp 字段
        if 'timestamp' in data and self.today in data['timestamp']:
            return True
        # 检查 indices 中的 date 字段
        if 'indices' in data:
            for idx in data['indices'].values():
                if isinstance(idx, dict) and idx.get('date') == self.today:
                    return True
        # 检查是否有单独的 date 字段
        if 'date' in data and data['date'] == self.today:
            return True
        return False

    # ============================================================
    # 1. 多指数行情（永久缓存）
    # ============================================================
    def get_indices(self) -> Dict:
        """
        获取主要指数行情
        永久缓存：今天只获取一次，之后直接读缓存
        """
        cache_file = "market_indices.json"
        cached = self._load_json(cache_file)
        if cached and self._is_data_today(cached):
            logger.info(f"✅ 从缓存读取指数数据: {cache_file}")
            return cached

        logger.info("📊 刷新指数数据...")
        result = self._fetch_indices_impl()
        self._save_json(cache_file, result)
        return result

    def _fetch_indices_impl(self) -> Dict:
        """实际获取指数数据"""
        result = {"indices": {}, "timestamp": datetime.now().isoformat()}

        try:
            import akshare as ak
            # 优先使用 index_zh_spot
            df = None
            try:
                df = ak.index_zh_spot()
            except:
                pass
            if df is None or df.empty:
                try:
                    df = ak.stock_zh_index_spot()
                except:
                    pass
            if df is None or df.empty:
                logger.warning("指数行情数据为空")
                return result

            index_map = {
                "上证指数": "000001.SH",
                "深证成指": "399001.SZ",
                "创业板指": "399006.SZ",
                "科创50": "000688.SH",
                "北证50": "899050.BJ"
            }

            for name, code in index_map.items():
                matched = df[df['代码'] == code]
                if matched.empty:
                    matched = df[df['名称'].str.contains(name, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][name] = {
                        "code": code,
                        "price": self._safe_float(row.get('最新价')),
                        "pct_change": self._safe_float(row.get('涨跌幅')),
                        "volume": self._safe_float(row.get('成交量')),
                        "amount": self._safe_float(row.get('成交额')),
                        "date": self.today
                    }

            logger.info(f"✅ 获取到 {len(result['indices'])} 个指数数据")
            return result

        except Exception as e:
            logger.warning(f"指数行情获取失败: {e}")
            return result

    # ============================================================
    # 2. 涨跌家数统计（永久缓存）
    # ============================================================
    def get_market_stats(self) -> Dict:
        """获取市场涨跌家数统计"""
        cache_file = "market_stats.json"
        cached = self._load_json(cache_file)
        if cached and self._is_data_today(cached):
            logger.info(f"✅ 从缓存读取涨跌家数: {cache_file}")
            return cached

        logger.info("📊 刷新涨跌家数...")
        result = self._fetch_stats_impl()
        self._save_json(cache_file, result)
        return result

    def _fetch_stats_impl(self) -> Dict:
        """实际获取涨跌家数"""
        result = {
            "up": 0,
            "down": 0,
            "flat": 0,
            "total": 0,
            "timestamp": datetime.now().isoformat(),
            "date": self.today
        }

        try:
            import akshare as ak
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
        except Exception as e:
            logger.warning(f"涨跌家数获取失败: {e}")
        return result

    # ============================================================
    # 3. 板块资金流向TOP5（永久缓存）
    # ============================================================
    def get_sector_flow(self) -> Dict:
        """获取板块资金流向TOP5"""
        cache_file = "sector_flow.json"
        cached = self._load_json(cache_file)
        if cached and self._is_data_today(cached):
            logger.info(f"✅ 从缓存读取板块资金流向: {cache_file}")
            return cached

        logger.info("📊 刷新板块资金流向...")
        result = self._fetch_flow_impl()
        self._save_json(cache_file, result)
        return result

    def _fetch_flow_impl(self) -> Dict:
        """实际获取板块资金流向"""
        result = {
            "net_inflow_top5": [],
            "net_outflow_top5": [],
            "timestamp": datetime.now().isoformat(),
            "date": self.today
        }

        try:
            import akshare as ak
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
        except Exception as e:
            logger.warning(f"板块资金流向获取失败: {e}")
        return result

    # ============================================================
    # 4. 增量历史记录（新增核心功能）
    # ============================================================
    def record_today_history(self, indices_data: Dict, stats_data: Dict) -> bool:
        """
        将今日市场数据追加到历史 CSV
        返回: True 表示写入成功，False 表示今日已存在或写入失败
        """
        filename = "market_history.csv"
        df = self._load_csv(filename)

        # 检查今天是否已记录
        if not df.empty and 'date' in df.columns:
            if self.today in df['date'].values:
                logger.info("⏭️ 今日市场历史已存在，跳过记录")
                return False

        # 构建今日记录
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
            # 将指数名称作为列前缀，如 "上证指数_price"
            prefix = name.replace("指数", "").strip()
            record[f"{prefix}_price"] = idx.get("price")
            record[f"{prefix}_pct"] = idx.get("pct_change")

        # 追加到 DataFrame
        new_df = pd.DataFrame([record])
        df = pd.concat([df, new_df], ignore_index=True)

        # 保存
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
