# ============================================================
# 记忆体（精阶段 V1.1.47 四表联动 + 模式记忆库）
# 四表：信号历史 / 影子结果 / 信任度 / 偏差归因
# ============================================================

import os
import pandas as pd
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class MemoryStore:
    """记忆体 - 四表联动存储"""

    def __init__(self, config: dict):
        self.config = config.get("memory", {})
        self.enabled = self.config.get("enabled", True)
        self.storage_dir = self.config.get("storage_dir", "memory_data/")
        self.max_records = self.config.get("max_records", 1000)

        # 四表文件路径
        tables = self.config.get("tables", {})
        self.signal_file = os.path.join(self.storage_dir, tables.get("signals", "signal_history.csv"))
        self.shadow_file = os.path.join(self.storage_dir, tables.get("shadow", "shadow_history.csv"))
        self.trust_file = os.path.join(self.storage_dir, tables.get("trust", "trust_history.csv"))
        self.deviation_file = os.path.join(self.storage_dir, tables.get("deviations", "deviation_history.csv"))

        self._ensure_storage_dir()

    def _ensure_storage_dir(self):
        """确保存储目录存在"""
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir, exist_ok=True)

    # ========== 表1：信号历史 ==========
    def save_signal_record(self, result, phase: str):
        """保存信号记录"""
        if not self.enabled:
            return

        df = self._load_csv(self.signal_file)
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

        if len(df) > self.max_records:
            df = df.tail(self.max_records)

        df.to_csv(self.signal_file, index=False)
        logger.info(f"✅ 信号历史已保存 ({len(records)} 条记录)")

    # ========== 表2：影子系统结果 ==========
    def save_shadow_record(self, shadow_result: Dict, phase: str):
        """保存影子系统结果"""
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

        if len(df) > self.max_records:
            df = df.tail(self.max_records)

        df.to_csv(self.shadow_file, index=False)
        logger.info("✅ 影子结果已保存")

    # ========== 表3：信任度历史 ==========
    def save_trust_record(self, trust_score: float, judge_status: str, phase: str):
        """保存信任度记录"""
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

        if len(df) > self.max_records:
            df = df.tail(self.max_records)

        df.to_csv(self.trust_file, index=False)
        logger.info(f"✅ 信任度已保存: {trust_score:.2f}")

    # ========== 表4：偏差归因 ==========
    def save_deviation_record(self, sector: str, expected_signal: int,
                              actual_performance: float, deviation: str):
        """保存偏差归因记录"""
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

        if len(df) > self.max_records:
            df = df.tail(self.max_records)

        df.to_csv(self.deviation_file, index=False)
        logger.info(f"✅ 偏差归因已保存: {sector}")

    # ========== 辅助方法 ==========
    def _load_csv(self, file_path: str) -> pd.DataFrame:
        """加载CSV，如果不存在则返回空DataFrame"""
        if os.path.exists(file_path):
            try:
                return pd.read_csv(file_path)
            except:
                return pd.DataFrame()
        return pd.DataFrame()

    # ========== 查询方法 ==========
    def get_historical_signals(self, sector: Optional[str] = None,
                               days: int = 30) -> pd.DataFrame:
        """获取历史信号"""
        df = self._load_csv(self.signal_file)
        if df.empty:
            return df

        df['date'] = pd.to_datetime(df['date'])
        cutoff = datetime.now() - pd.Timedelta(days=days)
        df = df[df['date'] >= cutoff]

        if sector:
            df = df[df['sector'] == sector]

        return df

    def get_trust_history(self, days: int = 30) -> pd.DataFrame:
        """获取信任度历史"""
        df = self._load_csv(self.trust_file)
        if df.empty:
            return df

        df['date'] = pd.to_datetime(df['date'])
        cutoff = datetime.now() - pd.Timedelta(days=days)
        return df[df['date'] >= cutoff]

    def get_deviation_summary(self, days: int = 30) -> Dict:
        """获取偏差归因汇总"""
        df = self._load_csv(self.deviation_file)
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
