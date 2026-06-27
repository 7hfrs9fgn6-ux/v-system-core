#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观历史数据存储器（增量追加版）
将宏观数据按日期存储到 CSV，支持历史查询和趋势分析
"""

import os
import pandas as pd
import logging
from datetime import datetime
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


class MacroHistory:
    """宏观历史数据存储器"""

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
        """检查今天的数据是否已经存在"""
        if df.empty or date_col not in df.columns:
            return False
        today = datetime.now().strftime("%Y-%m-%d")
        return today in df[date_col].values

    # ============================================================
    # 美股指数历史
    # ============================================================
    def record_us_indices(self, indices: Dict):
        """记录美股指数（道指、纳指、标普500）"""
        filename = "macro_us_indices.csv"
        df = self._load_csv(filename)

        # 检查今天是否已记录
        if self._is_today_recorded(df):
            logger.info("⏭️ 今日美股指数已记录，跳过")
            return

        new_records = []
        today = datetime.now().strftime("%Y-%m-%d")
        for name, data in indices.items():
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

    # ============================================================
    # 科技巨头历史
    # ============================================================
    def record_tech_giants(self, giants: Dict):
        """记录科技巨头（苹果、英伟达等）"""
        filename = "macro_tech_giants.csv"
        df = self._load_csv(filename)

        if self._is_today_recorded(df):
            logger.info("⏭️ 今日科技巨头已记录，跳过")
            return

        new_records = []
        today = datetime.now().strftime("%Y-%m-%d")
        for name, data in giants.items():
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
    # 亚太指数历史
    # ============================================================
    def record_asia_indices(self, indices: Dict):
        """记录亚太指数（日经、韩国、恒生、台湾）"""
        filename = "macro_asia_indices.csv"
        df = self._load_csv(filename)

        if self._is_today_recorded(df):
            logger.info("⏭️ 今日亚太指数已记录，跳过")
            return

        new_records = []
        today = datetime.now().strftime("%Y-%m-%d")
        for name, data in indices.items():
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

    # ============================================================
    # 欧洲指数历史
    # ============================================================
    def record_europe_indices(self, indices: Dict):
        """记录欧洲指数（德国DAX、英国FTSE、法国CAC）"""
        filename = "macro_europe_indices.csv"
        df = self._load_csv(filename)

        if self._is_today_recorded(df):
            logger.info("⏭️ 今日欧洲指数已记录，跳过")
            return

        new_records = []
        today = datetime.now().strftime("%Y-%m-%d")
        for name, data in indices.items():
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
    # 大宗商品历史
    # ============================================================
    def record_commodities(self, oil: Dict, gold: Dict):
        """记录大宗商品（原油、黄金）"""
        filename = "macro_commodities.csv"
        df = self._load_csv(filename)

        if self._is_today_recorded(df):
            logger.info("⏭️ 今日大宗商品已记录，跳过")
            return

        new_records = []
        today = datetime.now().strftime("%Y-%m-%d")
        for name, data in oil.items():
            new_records.append({
                "date": today,
                "type": "原油",
                "name": name,
                "price": data.get("price"),
                "pct_change": data.get("pct_change")
            })
        if gold.get("price"):
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
    # 汇率历史
    # ============================================================
    def record_forex(self, usd_cny: Dict):
        """记录人民币汇率"""
        filename = "macro_forex.csv"
        df = self._load_csv(filename)

        if self._is_today_recorded(df):
            logger.info("⏭️ 今日汇率已记录，跳过")
            return

        today = datetime.now().strftime("%Y-%m-%d")
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
    # A50期货历史
    # ============================================================
    def record_a50(self, a50: Dict):
        """记录A50期货"""
        filename = "macro_a50.csv"
        df = self._load_csv(filename)

        if self._is_today_recorded(df):
            logger.info("⏭️ 今日A50已记录，跳过")
            return

        today = datetime.now().strftime("%Y-%m-%d")
        new_record = {
            "date": today,
            "price": a50.get("price"),
            "pct_change": a50.get("pct_change")
        }

        new_df = pd.DataFrame([new_record])
        df = pd.concat([df, new_df], ignore_index=True)
        self._save_csv(filename, df)
        logger.info(f"✅ 记录A50: {a50.get('price')}")
