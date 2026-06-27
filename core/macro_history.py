#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观历史数据存储器（增量追加版）
所有数据永久保存，每天新增一行
"""

import os
import pandas as pd
import logging
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class MacroHistory:
    def __init__(self, storage_dir: str = "memory_data/"):
        self.storage_dir = storage_dir
        self._ensure_storage_dir()
        self.today = datetime.now().strftime("%Y-%m-%d")

    def _ensure_storage_dir(self):
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir, exist_ok=True)

    def _get_file_path(self, filename: str) -> str:
        return os.path.join(self.storage_dir, filename)

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
        logger.info(f"✅ 保存 {filename}: {len(df)} 条记录")

    def _is_today_recorded(self, df: pd.DataFrame, date_col: str = "date") -> bool:
        if df.empty or date_col not in df.columns:
            return False
        return self.today in df[date_col].values

    # ============================================================
    # 美股指数
    # ============================================================
    def record_us_indices(self, indices: Dict):
        filename = "macro_us_indices.csv"
        df = self._load_csv(filename)
        if self._is_today_recorded(df):
            logger.info("⏭️ 今日美股指数已存在，跳过")
            return

        new_records = []
        today = self.today
        for name, data in indices.items():
            if data.get("price") is not None:
                new_records.append({
                    "date": today,
                    "index_name": name,
                    "price": data.get("price"),
                    "pct_change": data.get("pct_change")
                })

        if new_records:
            new_df = pd.DataFrame(new_records)
            df = pd.concat([df, new_df], ignore_index=True)
            self._save_csv(filename, df)
            logger.info(f"✅ 记录 {len(new_records)} 条美股指数")

    def get_latest_us_indices(self) -> Dict:
        """获取最新一天的美股指数数据（用于展示）"""
        filename = "macro_us_indices.csv"
        df = self._load_csv(filename)
        if df.empty:
            return {}
        latest_date = df['date'].max()
        latest_df = df[df['date'] == latest_date]
        result = {}
        for _, row in latest_df.iterrows():
            name = row['index_name']
            result[name] = {
                "price": row['price'],
                "pct_change": row['pct_change']
            }
        return result

    # ============================================================
    # 科技巨头
    # ============================================================
    def record_tech_giants(self, giants: Dict):
        filename = "macro_tech_giants.csv"
        df = self._load_csv(filename)
        if self._is_today_recorded(df):
            logger.info("⏭️ 今日科技巨头已存在，跳过")
            return

        new_records = []
        today = self.today
        for name, data in giants.items():
            if data.get("price") is not None:
                new_records.append({
                    "date": today,
                    "name": name,
                    "price": data.get("price"),
                    "pct_change": data.get("pct_change")
                })

        if new_records:
            new_df = pd.DataFrame(new_records)
            df = pd.concat([df, new_df], ignore_index=True)
            self._save_csv(filename, df)
            logger.info(f"✅ 记录 {len(new_records)} 条科技巨头")

    # ============================================================
    # 亚太指数
    # ============================================================
    def record_asia_indices(self, indices: Dict):
        filename = "macro_asia_indices.csv"
        df = self._load_csv(filename)
        if self._is_today_recorded(df):
            logger.info("⏭️ 今日亚太指数已存在，跳过")
            return

        new_records = []
        today = self.today
        for name, data in indices.items():
            if data.get("price") is not None:
                new_records.append({
                    "date": today,
                    "index_name": name,
                    "price": data.get("price"),
                    "pct_change": data.get("pct_change")
                })

        if new_records:
            new_df = pd.DataFrame(new_records)
            df = pd.concat([df, new_df], ignore_index=True)
            self._save_csv(filename, df)
            logger.info(f"✅ 记录 {len(new_records)} 条亚太指数")

    def get_latest_asia_indices(self) -> Dict:
        filename = "macro_asia_indices.csv"
        df = self._load_csv(filename)
        if df.empty:
            return {}
        latest_date = df['date'].max()
        latest_df = df[df['date'] == latest_date]
        result = {}
        for _, row in latest_df.iterrows():
            name = row['index_name']
            result[name] = {
                "price": row['price'],
                "pct_change": row['pct_change']
            }
        return result

    # ============================================================
    # 欧洲指数
    # ============================================================
    def record_europe_indices(self, indices: Dict):
        filename = "macro_europe_indices.csv"
        df = self._load_csv(filename)
        if self._is_today_recorded(df):
            logger.info("⏭️ 今日欧洲指数已存在，跳过")
            return

        new_records = []
        today = self.today
        for name, data in indices.items():
            if data.get("price") is not None:
                new_records.append({
                    "date": today,
                    "index_name": name,
                    "price": data.get("price"),
                    "pct_change": data.get("pct_change")
                })

        if new_records:
            new_df = pd.DataFrame(new_records)
            df = pd.concat([df, new_df], ignore_index=True)
            self._save_csv(filename, df)
            logger.info(f"✅ 记录 {len(new_records)} 条欧洲指数")

    # ============================================================
    # 大宗商品
    # ============================================================
    def record_commodities(self, oil: Dict, gold: Dict):
        filename = "macro_commodities.csv"
        df = self._load_csv(filename)
        if self._is_today_recorded(df):
            logger.info("⏭️ 今日大宗商品已存在，跳过")
            return

        new_records = []
        today = self.today
        for name, data in oil.items():
            if data.get("price") is not None:
                new_records.append({
                    "date": today,
                    "type": "原油",
                    "name": name,
                    "price": data.get("price"),
                    "pct_change": data.get("pct_change")
                })
        if gold and gold.get("price") is not None:
            new_records.append({
                "date": today,
                "type": "黄金",
                "name": "黄金",
                "price": gold.get("price"),
                "pct_change": gold.get("pct_change")
            })

        if new_records:
            new_df = pd.DataFrame(new_records)
            df = pd.concat([df, new_df], ignore_index=True)
            self._save_csv(filename, df)
            logger.info(f"✅ 记录 {len(new_records)} 条大宗商品")

    # ============================================================
    # 汇率
    # ============================================================
    def record_forex(self, usd_cny: Dict):
        filename = "macro_forex.csv"
        df = self._load_csv(filename)
        if self._is_today_recorded(df):
            logger.info("⏭️ 今日汇率已存在，跳过")
            return

        today = self.today
        new_record = {
            "date": today,
            "onshore": usd_cny.get("onshore"),
            "central": usd_cny.get("central"),
            "pct_change": usd_cny.get("pct_change")
        }
        new_df = pd.DataFrame([new_record])
        df = pd.concat([df, new_df], ignore_index=True)
        self._save_csv(filename, df)
        logger.info(f"✅ 记录汇率: {usd_cny.get('onshore')}")

    # ============================================================
    # A50期货
    # ============================================================
    def record_a50(self, a50: Dict):
        filename = "macro_a50.csv"
        df = self._load_csv(filename)
        if self._is_today_recorded(df):
            logger.info("⏭️ 今日A50已存在，跳过")
            return

        today = self.today
        new_record = {
            "date": today,
            "price": a50.get("price"),
            "pct_change": a50.get("pct_change")
        }
        new_df = pd.DataFrame([new_record])
        df = pd.concat([df, new_df], ignore_index=True)
        self._save_csv(filename, df)
        logger.info(f"✅ 记录A50: {a50.get('price')}")
