# ============================================================
# 信任度动态累积引擎（精阶段 V1.1.52 双模信任度累积）
# 公式: 信任度 = 0.5×历史准确率 + 0.3×近期表现 + 0.2×置信度均值
# ============================================================

import os
import pandas as pd
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class TrustEngine:
    """信任度动态累积引擎"""

    def __init__(self, config: dict, storage_dir: str = "memory_data/"):
        self.config = config.get("trust", {}).get("accumulation", {})
        self.enabled = self.config.get("enabled", True)
        self.history_weight = self.config.get("history_weight", 0.5)
        self.recent_weight = self.config.get("recent_weight", 0.3)
        self.confidence_weight = self.config.get("confidence_weight", 0.2)
        self.min_samples = self.config.get("min_samples", 5)
        self.decay_factor = self.config.get("decay_factor", 0.95)

        self.storage_dir = storage_dir
        self.history_file = os.path.join(storage_dir, "trust_history.csv")
        self._ensure_storage_dir()

    def _ensure_storage_dir(self):
        """确保存储目录存在"""
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir, exist_ok=True)

    def load_history(self) -> pd.DataFrame:
        """加载信任度历史记录"""
        if os.path.exists(self.history_file):
            try:
                df = pd.read_csv(self.history_file)
                return df
            except Exception as e:
                logger.warning(f"读取信任度历史失败: {e}")
        return pd.DataFrame(columns=["date", "trust_score", "accuracy", "confidence_mean"])

    def save_record(self, date: str, trust_score: float,
                    accuracy: float, confidence_mean: float):
        """保存一条信任度记录"""
        df = self.load_history()
        new_row = pd.DataFrame([{
            "date": date,
            "trust_score": trust_score,
            "accuracy": accuracy,
            "confidence_mean": confidence_mean
        }])
        df = pd.concat([df, new_row], ignore_index=True)
        # 保留最近记录
        if len(df) > 1000:
            df = df.tail(1000)
        df.to_csv(self.history_file, index=False)
        logger.info(f"✅ 信任度记录已保存: {date}")

    def calculate_trust(self, current_accuracy: Optional[float] = None,
                        confidence_mean: Optional[float] = None,
                        default_trust: float = 0.76) -> float:
        """
        计算动态信任度
        current_accuracy: 本次预测准确率（0~1）
        confidence_mean: 本次置信度均值（0~1）
        """
        if not self.enabled:
            return default_trust

        history_df = self.load_history()

        if len(history_df) < self.min_samples:
            logger.info(f"信任度样本不足({len(history_df)}/{self.min_samples})，使用默认值")
            return default_trust

        # 1. 计算历史准确率（带衰减）
        historical_accuracy = self._calculate_historical_accuracy(history_df)

        # 2. 计算近期表现（最近10次）
        recent_accuracy = self._calculate_recent_accuracy(history_df, n=10)

        # 3. 置信度均值
        if confidence_mean is None:
            confidence_mean = history_df['confidence_mean'].mean() if 'confidence_mean' in history_df.columns else 0.5

        # 4. 加权计算
        trust_score = (
            self.history_weight * historical_accuracy +
            self.recent_weight * recent_accuracy +
            self.confidence_weight * confidence_mean
        )

        # 限幅到 0.10 ~ 0.95
        trust_score = max(0.10, min(0.95, trust_score))

        logger.info(f"📊 信任度计算: 历史{historical_accuracy:.2%} + 近期{recent_accuracy:.2%} + 置信度{confidence_mean:.2%} = {trust_score:.2%}")
        return round(trust_score, 2)

    def _calculate_historical_accuracy(self, df: pd.DataFrame) -> float:
        """计算历史准确率（带指数衰减）"""
        if df.empty or 'accuracy' not in df.columns:
            return 0.5

        # 按日期排序
        df_sorted = df.sort_values('date')
        accuracy_values = df_sorted['accuracy'].values
        n = len(accuracy_values)

        # 指数衰减加权
        weights = [self.decay_factor ** (n - 1 - i) for i in range(n)]
        total_weight = sum(weights)

        weighted_avg = sum(a * w for a, w in zip(accuracy_values, weights)) / total_weight
        return weighted_avg

    def _calculate_recent_accuracy(self, df: pd.DataFrame, n: int = 10) -> float:
        """计算近期准确率（最近n次）"""
        if df.empty or 'accuracy' not in df.columns:
            return 0.5

        recent = df.tail(n)
        if len(recent) < 1:
            return 0.5
        return recent['accuracy'].mean()

    def update_from_result(self, result, actual_performance: float):
        """
        根据实际表现更新信任度
        actual_performance: 实际涨跌幅（用于判断预测是否正确）
        """
        # 判断信号是否正确（综合建议方向 vs 实际涨跌幅）
        if result.overall_suggestion == "偏多":
            is_correct = actual_performance > 0
        elif result.overall_suggestion == "偏空":
            is_correct = actual_performance < 0
        else:
            is_correct = abs(actual_performance) < 0.5  # 震荡判断

        accuracy = 1.0 if is_correct else 0.0
        confidence_mean = result.trust_score

        self.save_record(
            date=datetime.now().strftime("%Y-%m-%d"),
            trust_score=result.trust_score,
            accuracy=accuracy,
            confidence_mean=confidence_mean
        )

        return accuracy
