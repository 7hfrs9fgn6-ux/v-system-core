# ============================================================
# 计划漂移检测器（精阶段 V1.1.52 三层检测 + 自动修正）
# 三层检测: 目标一致性 / 工具模式 / 推理进度
# ============================================================

import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class DriftDetector:
    """计划漂移检测器"""

    def __init__(self, config: dict):
        self.enabled = config.get("drift_detection", {}).get("enabled", True)
        self.similarity_threshold = config.get("drift_detection", {}).get("similarity_threshold", 0.85)
        self.max_correction_attempts = config.get("drift_detection", {}).get("max_correction_attempts", 2)
        self._initial_goal = None
        self._current_step = 0
        self._tool_usage = []
        self._drift_count = 0
        self._correction_attempts = 0

    def set_initial_goal(self, goal: str):
        """设置初始目标"""
        self._initial_goal = goal
        self._current_step = 0
        self._tool_usage = []
        self._drift_count = 0
        self._correction_attempts = 0
        logger.info(f"🎯 初始目标已设置: {goal[:50]}...")

    def record_step(self, step_description: str, tool_used: Optional[str] = None):
        """记录推理步骤"""
        self._current_step += 1
        if tool_used:
            self._tool_usage.append({
                "step": self._current_step,
                "tool": tool_used,
                "time": datetime.now().isoformat()
            })

    def check_drift(self, current_reasoning: str) -> Tuple[bool, str, float]:
        """
        检测计划漂移
        返回: (是否漂移, 漂移类型, 相似度)
        """
        if not self.enabled or self._initial_goal is None:
            return False, "正常", 1.0

        # 1. 目标一致性检测（基于关键词重叠率）
        similarity = self._calculate_similarity(self._initial_goal, current_reasoning)

        if similarity < self.similarity_threshold:
            self._drift_count += 1
            return True, "目标偏移", similarity

        # 2. 工具模式检测（连续使用同一工具超过3次）
        tool_pattern = self._detect_tool_pattern()
        if tool_pattern == "循环":
            self._drift_count += 1
            return True, "工具循环", similarity

        # 3. 推理进度检测（超过10步仍无进展）
        if self._current_step > 10:
            self._drift_count += 1
            return True, "推理过深", similarity

        return False, "正常", similarity

    def _calculate_similarity(self, goal: str, current: str) -> float:
        """计算目标与当前推理的相似度（基于关键词重叠）"""
        if not goal or not current:
            return 0.0

        # 提取关键词（简单实现：中文分词+去重）
        goal_keywords = set(self._extract_keywords(goal))
        current_keywords = set(self._extract_keywords(current))

        if not goal_keywords or not current_keywords:
            return 0.0

        intersection = goal_keywords.intersection(current_keywords)
        union = goal_keywords.union(current_keywords)

        return len(intersection) / len(union) if union else 0.0

    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词（简单实现）"""
        import re
        # 提取中文词汇（2-4个字）
        words = re.findall(r'[\u4e00-\u9fa5]{2,4}', text)
        # 过滤常见停用词
        stop_words = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己'}
        return [w for w in words if w not in stop_words]

    def _detect_tool_pattern(self) -> str:
        """检测工具使用模式"""
        if len(self._tool_usage) < 3:
            return "正常"

        recent_tools = [t['tool'] for t in self._tool_usage[-5:]]
        if len(set(recent_tools)) == 1:  # 连续使用同一工具
            return "循环"

        return "正常"

    def auto_correct(self) -> bool:
        """自动修正漂移"""
        self._correction_attempts += 1

        if self._correction_attempts > self.max_correction_attempts:
            logger.warning(f"⚠️ 修正尝试超过上限 ({self.max_correction_attempts})，停止修正")
            return False

        logger.info(f"🔄 计划漂移自动修正 (尝试 {self._correction_attempts}/{self.max_correction_attempts})")
        # 修正动作：重置工具记录，重新聚焦目标
        self._tool_usage = []
        self._drift_count = 0
        return True

    def reset(self):
        """重置检测器状态"""
        self._current_step = 0
        self._tool_usage = []
        self._drift_count = 0

    def get_drift_report(self) -> Dict:
        """获取漂移报告"""
        return {
            "total_steps": self._current_step,
            "drift_count": self._drift_count,
            "tool_usage": len(self._tool_usage),
            "correction_attempts": self._correction_attempts,
            "status": "已修正" if self._correction_attempts > 0 else "正常"
        }
