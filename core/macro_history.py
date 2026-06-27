#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观历史数据存储器（增量追加版）
所有数据永久保存，每天新增一行，永不覆盖
支持：美股指数、科技巨头、亚太指数、欧洲指数、大宗商品、汇率、A50期货
"""

import os
import pandas as pd
import logging
from datetime import datetime
from typing import Dict, Optional, List, Any

logger = logging.getLogger(__name__)


class MacroHistory:
    """
    宏观历史数据存储器
    所有数据以 CSV 格式永久保存，每天只追加一行
    """

    def __init__(self, storage_dir: str = "memory_data/"):
        self.storage_dir = storage_dir
        self.today = datetime.now().strftime("%Y-%m-%d")
        self._ensure_storage_dir()

    def _ensure_storage_dir(self):
        """确保存储目录存在"""
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir, exist_ok=True)
            logger.info(f"📁 创建目录: {self.storage_dir}")

    def _get_file_path(self, filename: str) -> str:
        """获取完整文件路径"""
        return os.path.join(self.storage_dir, filename)

    def _load_csv(self, filename: str) -> pd.DataFrame:
        """加载 CSV 文件，不存在则返回空 DataFrame"""
        file_path = self._get_file_path(filename)
        if os.path.exists(file_path):
            try:
                return pd.read_csv(file_path)
            except Exception as e:
                logger.warning(f"⚠️ 读取 {filename} 失败: {e}")
                return pd.DataFrame()
        return pd.DataFrame()

    def _save_csv(self, filename: str, df: pd.DataFrame):
        """保存 CSV 文件"""
        file_path = self._get_file_path(filename)
        df.to_csv(file_path, index=False, encoding='utf-8')
        logger.info(f"✅ 保存 {filename}: {len(df)} 条记录")

    def _is_today_recorded(self, df: pd.DataFrame, date_col: str = "date") -> bool:
        """检查今天的数据是否已经存在"""
        if df.empty or date_col not in df.columns:
            return False
        return self.today in df[date_col].values

    def _append_record(self, filename: str, new_records: List[Dict]):
        """通用追加记录方法"""
        if not new_records:
            return

        df = self._load_csv(filename)

        # 检查今日是否已记录（针对批量记录，检查第一条）
        if self._is_today_recorded(df):
            logger.info(f"⏭️ 今日 {filename} 已存在，跳过")
            return

        new_df = pd.DataFrame(new_records)
        df = pd.concat([df, new_df], ignore_index=True)
        self._save_csv(filename, df)

    # ============================================================
    # 1. 美股指数（道琼斯、纳斯达克、标普500）
    # ============================================================
    def record_us_indices(self, indices: Dict[str, Dict]) -> bool:
        """
        记录美股指数
        indices: {"道琼斯": {"price": 12345, "pct_change": 0.5}, ...}
        """
        filename = "macro_us_indices.csv"

        # 检查今日是否已记录
        df = self._load_csv(filename)
        if self._is_today_recorded(df):
            logger.info("⏭️ 今日美股指数已存在，跳过")
            return False

        new_records = []
        for name, data in indices.items():
            if data.get("price") is not None:
                new_records.append({
                    "date": self.today,
                    "index_name": name,
                    "price": data.get("price"),
                    "pct_change": data.get("pct_change")
                })

        if new_records:
            new_df = pd.DataFrame(new_records)
            df = pd.concat([df, new_df], ignore_index=True)
            self._save_csv(filename, df)
            logger.info(f"✅ 记录 {len(new_records)} 条美股指数")
            return True

        return False

    def get_latest_us_indices(self) -> Dict[str, Dict]:
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
                "price": row.get('price'),
                "pct_change": row.get('pct_change')
            }
        return result

    # ============================================================
    # 2. 科技巨头（苹果、英伟达、微软等）
    # ============================================================
    def record_tech_giants(self, giants: Dict[str, Dict]) -> bool:
        """
        记录科技巨头
        giants: {"苹果": {"price": 180, "pct_change": 0.5}, ...}
        """
        filename = "macro_tech_giants.csv"

        df = self._load_csv(filename)
        if self._is_today_recorded(df):
            logger.info("⏭️ 今日科技巨头已存在，跳过")
            return False

        new_records = []
        for name, data in giants.items():
            if data.get("price") is not None:
                new_records.append({
                    "date": self.today,
                    "name": name,
                    "price": data.get("price"),
                    "pct_change": data.get("pct_change")
                })

        if new_records:
            new_df = pd.DataFrame(new_records)
            df = pd.concat([df, new_df], ignore_index=True)
            self._save_csv(filename, df)
            logger.info(f"✅ 记录 {len(new_records)} 条科技巨头")
            return True

        return False

    def get_latest_tech_giants(self) -> Dict[str, Dict]:
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
                "price": row.get('price'),
                "pct_change": row.get('pct_change')
            }
        return result

    # ============================================================
    # 3. 亚太指数（日经225、韩国KOSPI、恒生指数、台湾加权）
    # ============================================================
    def record_asia_indices(self, indices: Dict[str, Dict]) -> bool:
        filename = "macro_asia_indices.csv"

        df = self._load_csv(filename)
        if self._is_today_recorded(df):
            logger.info("⏭️ 今日亚太指数已存在，跳过")
            return False

        new_records = []
        for name, data in indices.items():
            if data.get("price") is not None:
                new_records.append({
                    "date": self.today,
                    "index_name": name,
                    "price": data.get("price"),
                    "pct_change": data.get("pct_change")
                })

        if new_records:
            new_df = pd.DataFrame(new_records)
            df = pd.concat([df, new_df], ignore_index=True)
            self._save_csv(filename, df)
            logger.info(f"✅ 记录 {len(new_records)} 条亚太指数")
            return True

        return False

    def get_latest_asia_indices(self) -> Dict[str, Dict]:
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
                "price": row.get('price'),
                "pct_change": row.get('pct_change')
            }
        return result

    # ============================================================
    # 4. 欧洲指数（德国DAX、英国富时、法国CAC）
    # ============================================================
    def record_europe_indices(self, indices: Dict[str, Dict]) -> bool:
        filename = "macro_europe_indices.csv"

        df = self._load_csv(filename)
        if self._is_today_recorded(df):
            logger.info("⏭️ 今日欧洲指数已存在，跳过")
            return False

        new_records = []
        for name, data in indices.items():
            if data.get("price") is not None:
                new_records.append({
                    "date": self.today,
                    "index_name": name,
                    "price": data.get("price"),
                    "pct_change": data.get("pct_change")
                })

        if new_records:
            new_df = pd.DataFrame(new_records)
            df = pd.concat([df, new_df], ignore_index=True)
            self._save_csv(filename, df)
            logger.info(f"✅ 记录 {len(new_records)} 条欧洲指数")
            return True

        return False

    def get_latest_europe_indices(self) -> Dict[str, Dict]:
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
                "price": row.get('price'),
                "pct_change": row.get('pct_change')
            }
        return result

    # ============================================================
    # 5. 大宗商品（WTI原油、布伦特原油、黄金）
    # ============================================================
    def record_commodities(self, oil: Dict[str, Dict], gold: Dict) -> bool:
        filename = "macro_commodities.csv"

        df = self._load_csv(filename)
        if self._is_today_recorded(df):
            logger.info("⏭️ 今日大宗商品已存在，跳过")
            return False

        new_records = []

        for name, data in oil.items():
            if data.get("price") is not None:
                new_records.append({
                    "date": self.today,
                    "type": "原油",
                    "name": name,
                    "price": data.get("price"),
                    "pct_change": data.get("pct_change")
                })

        if gold and gold.get("price") is not None:
            new_records.append({
                "date": self.today,
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
            return True

        return False

    def get_latest_commodities(self) -> Dict:
        """获取最新一天的大宗商品数据"""
        filename = "macro_commodities.csv"
        df = self._load_csv(filename)
        if df.empty:
            return {"oil": {}, "gold": None}

        latest_date = df['date'].max()
        latest_df = df[df['date'] == latest_date]

        result = {"oil": {}, "gold": None}

        for _, row in latest_df.iterrows():
            if row.get('type') == "原油":
                result["oil"][row['name']] = {
                    "price": row.get('price'),
                    "pct_change": row.get('pct_change')
                }
            elif row.get('type') == "黄金":
                result["gold"] = {
                    "price": row.get('price'),
                    "pct_change": row.get('pct_change')
                }

        return result

    # ============================================================
    # 6. 人民币汇率（在岸价、中间价）
    # ============================================================
    def record_forex(self, usd_cny: Dict) -> bool:
        filename = "macro_forex.csv"

        df = self._load_csv(filename)
        if self._is_today_recorded(df):
            logger.info("⏭️ 今日汇率已存在，跳过")
            return False

        # 检查是否有有效数据
        if usd_cny.get("onshore") is None and usd_cny.get("central") is None:
            logger.warning("⚠️ 汇率数据为空，跳过记录")
            return False

        new_record = {
            "date": self.today,
            "onshore": usd_cny.get("onshore"),
            "central": usd_cny.get("central"),
            "pct_change": usd_cny.get("pct_change")
        }

        new_df = pd.DataFrame([new_record])
        df = pd.concat([df, new_df], ignore_index=True)
        self._save_csv(filename, df)
        logger.info(f"✅ 记录汇率: 在岸 {usd_cny.get('onshore')}, 中间价 {usd_cny.get('central')}")
        return True

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
                "onshore": row.get('onshore'),
                "central": row.get('central'),
                "pct_change": row.get('pct_change')
            }
        }

    # ============================================================
    # 7. A50期货
    # ============================================================
    def record_a50(self, a50: Dict) -> bool:
        filename = "macro_a50.csv"

        df = self._load_csv(filename)
        if self._is_today_recorded(df):
            logger.info("⏭️ 今日A50已存在，跳过")
            return False

        if a50.get("price") is None:
            logger.warning("⚠️ A50数据为空，跳过记录")
            return False

        new_record = {
            "date": self.today,
            "price": a50.get("price"),
            "pct_change": a50.get("pct_change")
        }

        new_df = pd.DataFrame([new_record])
        df = pd.concat([df, new_df], ignore_index=True)
        self._save_csv(filename, df)
        logger.info(f"✅ 记录A50: {a50.get('price')}")
        return True

    def get_latest_a50(self) -> Dict:
        """获取最新一天的A50数据"""
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
            "price": row.get('price'),
            "pct_change": row.get('pct_change')
        }

    # ============================================================
    # 8. 综合查询方法
    # ============================================================
    def get_all_latest(self) -> Dict:
        """获取所有类型的最新数据（用于推送展示）"""
        return {
            "us_indices": self.get_latest_us_indices(),
            "tech_giants": self.get_latest_tech_giants(),
            "asia_indices": self.get_latest_asia_indices(),
            "europe_indices": self.get_latest_europe_indices(),
            "commodities": self.get_latest_commodities(),
            "forex": self.get_latest_forex(),
            "a50": self.get_latest_a50(),
            "date": self.today
        }

    def get_history(self, filename: str, days: int = 30) -> pd.DataFrame:
        """获取指定文件的历史数据（最近N天）"""
        df = self._load_csv(filename)
        if df.empty:
            return df

        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            cutoff = datetime.now() - pd.Timedelta(days=days)
            return df[df['date'] >= cutoff]

        return df

    def clear_all(self):
        """清空所有历史数据（危险操作）"""
        files = [
            "macro_us_indices.csv",
            "macro_tech_giants.csv",
            "macro_asia_indices.csv",
            "macro_europe_indices.csv",
            "macro_commodities.csv",
            "macro_forex.csv",
            "macro_a50.csv"
        ]
        for f in files:
            file_path = self._get_file_path(f)
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"🗑️ 删除 {f}")

    def get_file_list(self) -> List[str]:
        """获取所有历史文件列表"""
        files = [
            "macro_us_indices.csv",
            "macro_tech_giants.csv",
            "macro_asia_indices.csv",
            "macro_europe_indices.csv",
            "macro_commodities.csv",
            "macro_forex.csv",
            "macro_a50.csv"
        ]
        existing = []
        for f in files:
            if os.path.exists(self._get_file_path(f)):
                existing.append(f)
        return existing
