#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bridge - 协议转换 + 安全过滤层（神经）- 修复版
"""

import logging
import re
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class Bridge:
    """Bridge 安全过滤层"""

    ALLOWED_TOOLS = [
        "get_sector_quote",
        "calculate_drawdown",
        "get_market_environment",
        "get_north_flow",
        "get_sentiment_score",
        "get_holding_signal",
        "get_extreme_sectors",
        "get_historical_data",
        "generate_analysis_report",
        "fetch_webpage",  # ✅ 新增
    ]

    FORBIDDEN_PATTERNS = [
        r"delete|drop|truncate|alter",
        r"exec|eval|system|subprocess",
        r"token|secret|password|key",
    ]

    _request_history: List[Dict] = []
    MAX_HISTORY = 100

    @classmethod
    def filter_request(cls, tool_name: str, parameters: Dict) -> Tuple[bool, str]:
        """安全过滤"""
        if tool_name not in cls.ALLOWED_TOOLS:
            logger.warning(f"🚫 拒绝调用: {tool_name} 不在白名单内")
            return False, f"工具 {tool_name} 不在白名单内"

        param_str = str(parameters)
        for pattern in cls.FORBIDDEN_PATTERNS:
            if re.search(pattern, param_str, re.IGNORECASE):
                logger.warning(f"🚫 拒绝调用: 参数包含敏感内容 - {pattern}")
                return False, f"参数包含敏感内容: {pattern}"

        return True, "允许调用"

    @classmethod
    def record_request(cls, tool_name: str, parameters: Dict, result: Dict):
        """记录请求日志"""
        cls._request_history.append({
            "tool": tool_name,
            "parameters": parameters,
            "result_status": result.get("status", "unknown"),
            "time": datetime.now()
        })
        if len(cls._request_history) > cls.MAX_HISTORY:
            cls._request_history = cls._request_history[-cls.MAX_HISTORY:]

    @classmethod
    def get_stats(cls) -> Dict:
        """获取 Bridge 统计信息"""
        total = len(cls._request_history)
        if total == 0:
            return {
                "total_requests": 0,
                "success": 0,
                "failed": 0,
                "success_rate": 0,
                "tools_used": []
            }
        success = len([r for r in cls._request_history if r["result_status"] == "success"])
        return {
            "total_requests": total,
            "success": success,
            "failed": total - success,
            "success_rate": round(success / total * 100, 2),
            "tools_used": list(set([r["tool"] for r in cls._request_history]))
        }

    @classmethod
    def reset(cls):
        cls._request_history = []
        logger.info("🔄 Bridge 已重置")
