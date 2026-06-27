#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bridge - 协议转换 + 安全过滤层（神经）- P2修复版
对应精阶段 V1.1.51 Bridge 层安全过滤白名单
"""

import logging
import re
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class Bridge:
    """
    Bridge 安全过滤层
    职责：
    1. 安全过滤：检查工具调用是否在白名单内
    2. 协议转换：将 DS API 的决策转换为 Codex 可执行的指令
    3. 日志记录：记录所有请求和响应
    """

    # ✅ 完整白名单：所有允许调用的工具（包含宏观工具）
    ALLOWED_TOOLS = [
        # 核心工具
        "get_sector_quote",
        "calculate_drawdown",
        "get_market_environment",
        "get_north_flow",
        "get_sentiment_score",
        "get_holding_signal",
        "get_extreme_sectors",
        "get_historical_data",
        "generate_analysis_report",
        "fetch_webpage",
        # ✅ 新增：宏观工具（P2修复）
        "get_macro_snapshot",
        "get_us_market",
        "get_asia_market",
        "get_europe_market",
        "get_commodities",
        "get_forex",
        "get_a50_futures",
    ]

    # ✅ 黑名单：禁止的敏感操作
    FORBIDDEN_PATTERNS = [
        r"delete|drop|truncate|alter",  # 数据库操作
        r"exec|eval|system|subprocess",  # 系统命令
        r"token|secret|password|key",    # 敏感信息
        r"rm\s+-rf|format|del\s+/f",     # 危险系统操作
        r"http://[^/]+/admin|/config",   # 敏感路径
    ]

    # 请求历史
    _request_history: List[Dict] = []
    MAX_HISTORY = 1000  # 最多保留1000条记录

    @classmethod
    def filter_request(cls, tool_name: str, parameters: Dict) -> Tuple[bool, str]:
        """
        安全过滤：检查请求是否安全
        返回: (是否允许, 原因)
        """
        # 1. 检查工具是否在白名单内
        if tool_name not in cls.ALLOWED_TOOLS:
            logger.warning(f"🚫 拒绝调用: {tool_name} 不在白名单内")
            logger.debug(f"   可用工具: {cls.ALLOWED_TOOLS}")
            return False, f"工具 {tool_name} 不在白名单内"

        # 2. 检查参数是否包含敏感内容
        param_str = str(parameters)
        for pattern in cls.FORBIDDEN_PATTERNS:
            if re.search(pattern, param_str, re.IGNORECASE):
                logger.warning(f"🚫 拒绝调用: 参数包含敏感内容 - {pattern}")
                logger.debug(f"   参数: {param_str}")
                return False, f"参数包含敏感内容: {pattern}"

        # 3. 检查调用频率（防止滥用）
        if not cls._check_rate_limit(tool_name):
            return False, f"工具 {tool_name} 调用频率过高，请稍后再试"

        return True, "允许调用"

    @classmethod
    def _check_rate_limit(cls, tool_name: str, max_per_minute: int = 10) -> bool:
        """检查调用频率限制"""
        now = datetime.now()
        recent_calls = [
            r for r in cls._request_history
            if r["tool"] == tool_name
            and (now - r["time"]).total_seconds() < 60
        ]
        if len(recent_calls) >= max_per_minute:
            logger.warning(f"⏰ {tool_name} 调用频率超限 ({len(recent_calls)}/{max_per_minute})")
            return False
        return True

    @classmethod
    def record_request(cls, tool_name: str, parameters: Dict, result: Dict):
        """记录请求日志"""
        cls._request_history.append({
            "tool": tool_name,
            "parameters": parameters,
            "result_status": result.get("status", "unknown"),
            "time": datetime.now()
        })
        # 保留最近记录
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
        failed = total - success
        tools_used = list(set([r["tool"] for r in cls._request_history]))
        return {
            "total_requests": total,
            "success": success,
            "failed": failed,
            "success_rate": round(success / total * 100, 2),
            "tools_used": tools_used,
            "last_10": cls._request_history[-10:]  # 最近10条记录（用于调试）
        }

    @classmethod
    def reset(cls):
        """重置 Bridge 状态"""
        cls._request_history = []
        logger.info("🔄 Bridge 已重置")

    @classmethod
    def is_allowed(cls, tool_name: str) -> bool:
        """检查工具是否在白名单中"""
        return tool_name in cls.ALLOWED_TOOLS

    @classmethod
    def get_allowed_tools(cls) -> List[str]:
        """获取所有白名单工具"""
        return cls.ALLOWED_TOOLS.copy()
