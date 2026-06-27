#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观历史数据存储器（增量追加版）
所有数据永久保存，每天新增一行
支持：美股指数、科技巨头、亚太指数、欧洲指数、大宗商品、汇率、A50期货
"""

import os
import pandas as pd
import logging
from datetime import datetime
from typing import Dict, Optional, List, Any

logger = logging.getLogger(__name__)


class MacroHistory:
    def __init__(self, storage_dir: str = "memory_data/"):
        self.storage_dir = storage_dir
        self._ensure_storage_dir()
        self.today = datetime.now().strftime("%Y-%m-%d")
        logger.info(f"📁 宏观历史存储目录: {os.path.abspath(self.storage_dir)}")

    def _ensure_storage_dir(self):
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir, exist_ok=True)

    def _get_file_path(self, filename: str) -> str:
        return os.path.join(self.storage_dir, filename)

    def _load_csv(self, filename: str) -> pd.DataFrame:
        """加载 CSV 文件，若不存在则返回空 DataFrame"""
        file_path = self._get_file_path(filename)
        if os.path.exists(file_path):
            try:
                return pd.read_csv(file_path)
            except Exception as e:
                logger.warning(f"加载 {filename} 失败: {e}")
                return pd.DataFrame()
        return pd.DataFrame()

    def _save_csv(self, filename: str, df: pd.DataFrame):
        """保存 DataFrame 到 CSV"""
        file_path = self._get_file_path(filename)
        df.to_csv(file_path, index=False)
        logger.debug(f"✅ 保存 {filename}: {len(df)} 条记录")

    def _is_today_recorded(self, df: pd.DataFrame, date_col: str = "date") -> bool:
        """检查今日数据是否已存在"""
        if df.empty or date_col not in df.columns:
            return False
        return self.today in df[date_col].values

    # ============================================================
    # 美股指数
    # ============================================================
    def record_us_indices(self, indices: Dict):
        """
        记录美股指数（道琼斯、纳斯达克、标普500）
        indices: {'道琼斯': {'price': 38400, 'pct_change': 0.5}, ...}
        """
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
        else:
            logger.warning("⚠️ 无有效美股指数数据可记录")

    def get_latest_us_indices(self) -> Dict:
        """获取最新一天的美股指数数据"""
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
                "pct_change": row['pct_change'] if pd.notna(row.get('pct_change')) else None
            }
        return result

    # ============================================================
    # 科技巨头
    # ============================================================
    def record_tech_giants(self, giants: Dict):
        """
        记录科技巨头（苹果、英伟达等）
        giants: {'苹果': {'price': 190, 'pct_change': 1.2}, ...}
        """
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

    def get_latest_tech_giants(self) -> Dict:
        """获取最新一天的科技巨头数据"""
        filename = "macro_tech_giants.csv"
        df = self._load_csv(filename)
        if df.empty:
            return {}
        latest_date = df['date'].max()
        latest_df = df[df['date'] == latest_date]
        result = {}
        for _, row in latest_df.iterrows():
            name = row['name']
            result[name] = {
                "price": row['price'],
                "pct_change": row['pct_change'] if pd.notna(row.get('pct_change')) else None
            }
        return result

    # ============================================================
    # 亚太指数
    # ============================================================
    def record_asia_indices(self, indices: Dict):
        """
        记录亚太指数（日经225、韩国KOSPI、恒生指数、台湾加权）
        indices: {'日经225': {'price': 38500, 'pct_change': -0.3}, ...}
        """
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
        """获取最新一天的亚太指数数据"""
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
                "pct_change": row['pct_change'] if pd.notna(row.get('pct_change')) else None
            }
        return result

    # ============================================================
    # 欧洲指数
    # ============================================================
    def record_europe_indices(self, indices: Dict):
        """
        记录欧洲指数（德国DAX、英国富时、法国CAC）
        indices: {'德国DAX': {'price': 18500, 'pct_change': 0.8}, ...}
        """
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

    def get_latest_europe_indices(self) -> Dict:
        """获取最新一天的欧洲指数数据"""
        filename = "macro_europe_indices.csv"
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
                "pct_change": row['pct_change'] if pd.notna(row.get('pct_change')) else None
            }
        return result

    # ============================================================
    # 大宗商品
    # ============================================================
    def record_commodities(self, oil: Dict, gold: Dict):
        """
        记录大宗商品（原油、黄金）
        oil: {'WTI': {'price': 72.5, 'pct_change': -1.2}, ...}
        gold: {'price': 1950, 'pct_change': 0.5}
        """
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

    def get_latest_commodities(self) -> Dict:
        """获取最新一天的大宗商品数据"""
        filename = "macro_commodities.csv"
        df = self._load_csv(filename)
        if df.empty:
            return {}
        latest_date = df['date'].max()
        latest_df = df[df['date'] == latest_date]
        result = {"oil": {}, "gold": None}
        for _, row in latest_df.iterrows():
            if row['type'] == "原油":
                result["oil"][row['name']] = {
                    "price": row['price'],
                    "pct_change": row['pct_change'] if pd.notna(row.get('pct_change')) else None
                }
            elif row['type'] == "黄金":
                result["gold"] = {
                    "price": row['price'],
                    "pct_change": row['pct_change'] if pd.notna(row.get('pct_change')) else None
                }
        return result

    # ============================================================
    # 汇率
    # ============================================================
    def record_forex(self, usd_cny: Dict):
        """
        记录人民币汇率
        usd_cny: {'onshore': 6.82, 'central': 6.80, 'pct_change': -0.02}
        """
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
        logger.info(f"✅ 记录汇率: 在岸 {usd_cny.get('onshore')}")

    def get_latest_forex(self) -> Dict:
        """获取最新一天的汇率数据"""
        filename = "macro_forex.csv"
        df = self._load_csv(filename)
        if df.empty:
            return {"usd_cny": {}}
        latest_date = df['date'].max()
        latest_df = df[df['date'] == latest_date]
        if latest_df.empty:
            return {"usd_cny": {}}
        row = latest_df.iloc[0]
        return {
            "usd_cny": {
                "onshore": row['onshore'] if pd.notna(row.get('onshore')) else None,
                "central": row['central'] if pd.notna(row.get('central')) else None,
                "pct_change": row['pct_change'] if pd.notna(row.get('pct_change')) else None
            }
        }

    # ============================================================
    # A50期货
    # ============================================================
    def record_a50(self, a50: Dict):
        """
        记录A50期货
        a50: {'price': 15765, 'pct_change': -0.57}
        """
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

    def get_latest_a50(self) -> Dict:
        """获取最新一天的A50期货数据"""
        filename = "macro_a50.csv"
        df = self._load_csv(filename)
        if df.empty:
            return {}
        latest_date = df['date'].max()
        latest_df = df[df['date'] == latest_date]
        if latest_df.empty:
            return {}
        row = latest_df.iloc[0]
        return {
            "price": row['price'] if pd.notna(row.get('price')) else None,
            "pct_change": row['pct_change'] if pd.notna(row.get('pct_change')) else None
        }

    # ============================================================
    # 清理方法（用于维护）
    # ============================================================
    def clear_all(self):
        """清空所有历史数据（危险操作）"""
        for filename in ["macro_us_indices.csv", "macro_tech_giants.csv", 
                         "macro_asia_indices.csv", "macro_europe_indices.csv",
                         "macro_commodities.csv", "macro_forex.csv", "macro_a50.csv"]:
            file_path = self._get_file_path(filename)
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"🗑️ 已删除 {filename}")
