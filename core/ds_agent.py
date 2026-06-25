#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DS API 智能代理（大脑）
接收用户意图 → 自主决策工具调用 → 返回结果
对应精阶段 V1.1.50 智能代理架构
"""

import os
import json
import logging
import requests
from typing import Dict, List, Any, Optional
from datetime import datetime

from core.codex_tools import TOOL_REGISTRY, get_tool_schema, execute_tool

logger = logging.getLogger(__name__)


class DSAgent:
    """
    DS API 智能代理
    自主识别意图 → 决策工具调用 → 多步推理 → 返回结果
    """

    def __init__(self):
        self.api_key = os.environ.get("DEEPSEEK_API_KEY")
        self.base_url = "https://api.deepseek.com/v1"
        self.enabled = bool(self.api_key and self.api_key != "")
        self.max_tool_calls = 5
        self.max_reasoning_depth = 3
        self.timeout = 10

        # 工具注册表
        self.tools = get_tool_schema()
        self.tool_functions = TOOL_REGISTRY

        if self.enabled:
            logger.info("✅ DS API 智能代理已初始化")
            logger.info(f"📋 已注册 {len(self.tools)} 个工具")
        else:
            logger.warning("⚠️ DS API Key 未配置，智能代理未启用")

    def think(self, user_query: str, context: Optional[Dict] = None) -> Dict:
        """
        核心方法：接收用户查询，返回推理结果
        """
        if not self.enabled:
            return {
                "status": "error",
                "error": "DS API 未启用",
                "mode": "fallback"
            }

        messages = self._build_messages(user_query, context)
        tool_calls_made = 0
        reasoning_depth = 0

        try:
            while tool_calls_made < self.max_tool_calls and reasoning_depth < self.max_reasoning_depth:
                reasoning_depth += 1

                # 调用 DS API
                response = self._call_ds_api(messages)

                if not response:
                    return {
                        "status": "error",
                        "error": "DS API 调用失败",
                        "mode": "fallback"
                    }

                message = response.get("choices", [{}])[0].get("message", {})
                tool_calls = message.get("tool_calls", [])

                # 如果不需要调用工具，直接返回
                if not tool_calls:
                    return {
                        "status": "success",
                        "response": message.get("content", ""),
                        "tool_calls_made": tool_calls_made,
                        "reasoning_depth": reasoning_depth,
                        "mode": "agent"
                    }

                # 执行工具调用
                tool_results = self._execute_tool_calls(tool_calls)
                tool_calls_made += len(tool_calls)

                # 将工具结果添加到对话中
                messages.append(message)
                for result in tool_results:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": result["tool_call_id"],
                        "content": json.dumps(result["result"], ensure_ascii=False)
                    })

            # 达到最大调用次数，强制终止
            return {
                "status": "warning",
                "response": "推理达到最大工具调用次数，返回当前结果",
                "tool_calls_made": tool_calls_made,
                "reasoning_depth": reasoning_depth,
                "mode": "agent_terminated"
            }

        except Exception as e:
            logger.error(f"DS Agent 执行异常: {e}")
            return {
                "status": "error",
                "error": str(e),
                "mode": "fallback"
            }

    def _build_messages(self, user_query: str, context: Optional[Dict] = None) -> List[Dict]:
        """构建消息列表"""
        system_prompt = self._get_system_prompt()

        messages = [{
            "role": "system",
            "content": system_prompt
        }]

        # 添加上下文
        if context:
            messages.append({
                "role": "user",
                "content": f"当前上下文: {json.dumps(context, ensure_ascii=False)}"
            })

        # 添加用户查询
        messages.append({
            "role": "user",
            "content": user_query
        })

        return messages

    def _get_system_prompt(self) -> str:
        """获取系统提示词"""
        return """
你是 V 系统的智能分析代理（DS API Agent）。

你的职责：
1. 理解用户的分析需求
2. 决定需要调用哪些工具获取数据
3. 基于数据生成分析结论
4. 返回结构化的分析报告

可用工具说明：
1. get_sector_quote - 获取板块实时行情
2. calculate_drawdown - 计算52周回撤
3. get_market_environment - 获取市场环境
4. get_north_flow - 获取北向资金
5. get_sentiment_score - 获取消息面烈度评分
6. get_holding_signal - 获取持仓基金信号
7. get_extreme_sectors - 获取最强/最弱板块
8. get_historical_data - 获取历史数据
9. generate_analysis_report - 生成综合分析报告

规则约束：
1. 每次最多调用 5 个工具
2. 推理深度不超过 3 层
3. 如果工具调用失败，使用备用方案
4. 返回结果必须包含数据来源标注
5. 对敏感数据（如资金流向）必须标注来源

输出格式：返回 JSON 格式的结果，包含 status、data、source 字段。
"""

    def _call_ds_api(self, messages: List[Dict]) -> Optional[Dict]:
        """调用 DS API"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": "deepseek-chat",
                "messages": messages,
                "tools": self.tools,
                "tool_choice": "auto",
                "max_tokens": 2000,
                "temperature": 0.3
            }

            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"DS API 调用失败: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"DS API 调用异常: {e}")
            return None

    def _execute_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        """执行工具调用"""
        results = []

        for tool_call in tool_calls:
            function = tool_call.get("function", {})
            tool_name = function.get("name", "")
            arguments = json.loads(function.get("arguments", "{}"))

            logger.info(f"🔧 执行工具: {tool_name}({arguments})")

            result = execute_tool(tool_name, **arguments)

            results.append({
                "tool_call_id": tool_call.get("id", ""),
                "result": result
            })

        return results

    def analyze_sector(self, sector_name: str) -> Dict:
        """
        快捷方法：分析单个板块
        """
        query = f"请分析 {sector_name} 板块的当前状态，包括回撤、烈度评分和市场环境"
        return self.think(query)

    def analyze_holdings(self) -> Dict:
        """
        快捷方法：分析持仓
        """
        query = "请分析所有持仓基金的当前信号状态，并给出操作建议"
        return self.think(query)

    def get_daily_summary(self) -> Dict:
        """
        快捷方法：获取每日摘要
        """
        query = "请生成今日市场摘要，包括最强/最弱板块、市场环境、北向资金流向"
        return self.think(query)
