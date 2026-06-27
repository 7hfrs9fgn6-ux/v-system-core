#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
记忆体（V2.0 - 支持归档压缩）
四表联动 + 自动归档，保存3年以上数据
"""

import os
import pandas as pd
import logging
import gzip
import shutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class MemoryStore:
    def __init__(self, config: dict):
        self.config = config.get("memory", {})
        self.enabled = self.config.get("enabled", True)
        self.storage_dir = self.config.get("storage_dir", "memory_data/")
        self.max_active_records = self.config.get("max_active_records", 1000)   # 热数据最大条数
        self.archive_threshold = self.config.get("archive_threshold", 500)     # 每次归档移动的条数
        self.max_archive_files = self.config.get("max_archive_files", 20)      # 最多保留归档文件数

        tables = self.config.get("tables", {})
        self.signal_file = os.path.join(self.storage_dir, tables.get("signals", "signal_history.csv"))
        self.shadow_file = os.path.join(self.storage_dir, tables.get("shadow", "shadow_history.csv"))
        self.trust_file = os.path.join(self.storage_dir, tables.get("trust", "trust_history.csv"))
        self.deviation_file = os.path.join(self.storage_dir, tables.get("deviations", "deviation_history.csv"))

        self._ensure_storage_dir()

    def _ensure_storage_dir(self):
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir, exist_ok=True)

    # ---------- 核心归档方法 ----------
    def _archive_file(self, file_path: str, archive_prefix: str):
        """
        检查文件大小，如果超过 max_active_records 则进行归档
        file_path: 原始CSV文件路径
        archive_prefix: 归档文件前缀（如 "signal"）
        """
        if not os.path.exists(file_path):
            return
        df = pd.read_csv(file_path)
        if len(df) <= self.max_active_records:
            return

        # 保留最新的 max_active_records 条
        active_df = df.tail(self.max_active_records)
        # 需要归档的部分（最旧的）
        archive_df = df.head(len(df) - self.max_active_records)

        # 保存归档文件（gzip压缩）
        archive_filename = f"{archive_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv.gz"
        archive_path = os.path.join(self.storage_dir, archive_filename)
        with gzip.open(archive_path, 'wt', encoding='utf-8') as f:
            archive_df.to_csv(f, index=False)
        logger.info(f"📦 归档 {len(archive_df)} 条记录到 {archive_filename}")

        # 保留最新的 active 数据
        active_df.to_csv(file_path, index=False)
        logger.info(f"✅ {file_path} 保留最新 {len(active_df)} 条记录")

        # 删除过旧的归档文件（保留最新 max_archive_files 个）
        archive_files = [f for f in os.listdir(self.storage_dir) if f.startswith(archive_prefix) and f.endswith('.csv.gz')]
        if len(archive_files) > self.max_archive_files:
            archive_files.sort()
            for f in archive_files[:-self.max_archive_files]:
                os.remove(os.path.join(self.storage_dir, f))
                logger.info(f"🗑️ 删除旧归档文件: {f}")

    def _load_all_data(self, file_path: str, archive_prefix: str) -> pd.DataFrame:
        """加载所有数据（包括归档）"""
        dfs = []
        # 1. 加载 active 文件
        if os.path.exists(file_path):
            dfs.append(pd.read_csv(file_path))

        # 2. 加载所有归档文件
        archive_pattern = f"{archive_prefix}_*.csv.gz"
        import glob
        for gz_file in sorted(glob.glob(os.path.join(self.storage_dir, archive_pattern))):
            try:
                with gzip.open(gz_file, 'rt', encoding='utf-8') as f:
                    dfs.append(pd.read_csv(f))
            except Exception as e:
                logger.warning(f"⚠️ 无法读取归档文件 {gz_file}: {e}")

        if not dfs:
            return pd.DataFrame()
        return pd.concat(dfs, ignore_index=True).sort_values(by='date')

    # ---------- 保存方法（自动触发归档） ----------
    def save_signal_record(self, result, phase: str):
        if not self.enabled:
            return
        df = self._load_csv(self.signal_file)  # 加载当前所有数据（含归档）
        records = []
        for s in result.signals:
            records.append({
                "date": result.analysis_time[:10],
                "time": result.analysis_time,
                "phase": phase,
                "sector": s.name,
                "signal_level": s.signal_level,
                "drawdown": s.drawdown,
                "threshold": s.threshold,
                "overall": result.overall_suggestion,
                "judge_status": result.judge_status,
                "trust_score": result.trust_score
            })
        new_df = pd.DataFrame(records)
        df = pd.concat([df, new_df], ignore_index=True)
        df.to_csv(self.signal_file, index=False)
        self._archive_file(self.signal_file, "signal")

    # 其他 save_* 类似，复用 _archive_file
    def save_shadow_record(self, shadow_result: Dict, phase: str):
        if not self.enabled:
            return
        df = self._load_csv(self.shadow_file)
        reliability = shadow_result.get('reliability', {})
        record = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "time": datetime.now().isoformat(),
            "phase": phase,
            "overall_reliability": reliability.get('overall_reliability', 0),
            "consensus_level": reliability.get('consensus_level', '未知'),
            "is_reliable": reliability.get('is_reliable', False),
            "divergence_sectors": str(reliability.get('divergence_sectors', []))
        }
        new_df = pd.DataFrame([record])
        df = pd.concat([df, new_df], ignore_index=True)
        df.to_csv(self.shadow_file, index=False)
        self._archive_file(self.shadow_file, "shadow")

    def save_trust_record(self, trust_score: float, judge_status: str, phase: str):
        if not self.enabled:
            return
        df = self._load_csv(self.trust_file)
        record = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "time": datetime.now().isoformat(),
            "phase": phase,
            "trust_score": trust_score,
            "judge_status": judge_status
        }
        new_df = pd.DataFrame([record])
        df = pd.concat([df, new_df], ignore_index=True)
        df.to_csv(self.trust_file, index=False)
        self._archive_file(self.trust_file, "trust")

    def save_deviation_record(self, sector: str, expected_signal: int, actual_performance: float, deviation: str):
        if not self.enabled:
            return
        df = self._load_csv(self.deviation_file)
        record = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "time": datetime.now().isoformat(),
            "sector": sector,
            "expected_signal": expected_signal,
            "actual_performance": actual_performance,
            "deviation_type": deviation,
            "severity": "高" if abs(actual_performance) > 3 else "中" if abs(actual_performance) > 1 else "低"
        }
        new_df = pd.DataFrame([record])
        df = pd.concat([df, new_df], ignore_index=True)
        df.to_csv(self.deviation_file, index=False)
        self._archive_file(self.deviation_file, "deviation")

    # ---------- 辅助方法 ----------
    def _load_csv(self, file_path: str) -> pd.DataFrame:
        if os.path.exists(file_path):
            try:
                return pd.read_csv(file_path)
            except:
                return pd.DataFrame()
        return pd.DataFrame()

    # ---------- 查询方法 ----------
    def get_historical_signals(self, sector: Optional[str] = None, days: int = 30) -> pd.DataFrame:
        """获取历史信号（自动加载归档）"""
        df = self._load_all_data(self.signal_file, "signal")
        if df.empty:
            return df
        df['date'] = pd.to_datetime(df['date'])
        cutoff = datetime.now() - pd.Timedelta(days=days)
        df = df[df['date'] >= cutoff]
        if sector:
            df = df[df['sector'] == sector]
        return df

    def get_trust_history(self, days: int = 30) -> pd.DataFrame:
        df = self._load_all_data(self.trust_file, "trust")
        if df.empty:
            return df
        df['date'] = pd.to_datetime(df['date'])
        cutoff = datetime.now() - pd.Timedelta(days=days)
        return df[df['date'] >= cutoff]

    def get_deviation_summary(self, days: int = 30) -> Dict:
        df = self._load_all_data(self.deviation_file, "deviation")
        if df.empty:
            return {"total": 0, "by_type": {}, "by_sector": {}}
        df['date'] = pd.to_datetime(df['date'])
        cutoff = datetime.now() - pd.Timedelta(days=days)
        df = df[df['date'] >= cutoff]
        return {
            "total": len(df),
            "by_type": df['deviation_type'].value_counts().to_dict(),
            "by_sector": df['sector'].value_counts().to_dict()
        }
