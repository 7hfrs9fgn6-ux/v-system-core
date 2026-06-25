#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DS API 智能代理（大脑）- 优化版
支持更多工具调用 + 增强响应内容
对应精阶段 V1.1.50 智能代理架构
"""

import os
import json
import logging
import requests
from typing import Dict, List, Any, Optional
from datetime import datetime

from core.codex_tools import TOOL_REGISTRY, get_tool_schema, execute_tool
from core.bridge import Bridge

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
        
        # ✅ 优化：提高调用限制
        self.max_tool_calls = 10      # 从 5 提高到 10
        self.max_reasoning_depth = 5  # 从 3 提高到 5
        self.timeout = 30             # 从 15 提高到 30

        # 工具注册表
        self.tools = get_tool_schema()
        self.tool_functions = TOOL_REGISTRY

        if self.enabled:
            logger.info(f"✅ DS API 智能代理已初始化，已注册 {len(self.tools)} 个工具")
            logger.info(f"   📊 最大工具调用: {self.max_tool_calls} 次")
            logger.info(f"   📊 最大推理深度: {self.max_reasoning_depth} 层")
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
        all_tool_results = []
        all_responses = []

        try:
            while tool_calls_made < self.max_tool_calls and reasoning_depth < self.max_reasoning_depth:
                reasoning_depth += 1
                logger.info(f"🔄 推理轮次 {reasoning_depth}/{self.max_reasoning_depth}")

                # 调用 DS API
                response = self._call_ds_api(messages)

                if not response:
                    return {
                        "status": "error",
                        "error": "DS API 调用失败",
                        "mode": "fallback",
                        "tool_calls_made": tool_calls_made,
                        "reasoning_depth": reasoning_depth
                    }

                message = response.get("choices", [{}])[0].get("message", {})
                tool_calls = message.get("tool_calls", [])

                # ✅ 保存助手响应内容
                content = message.get("content", "")
                if content:
                    all_responses.append(content)

                # ✅ 如果没有工具调用，直接返回结果
                if not tool_calls:
                    # 如果有响应内容则使用，否则使用最后一条响应
                    final_response = content if content else (all_responses[-1] if all_responses else "分析完成")
                    return {
                        "status": "success",
                        "response": final_response,
                        "tool_calls_made": tool_calls_made,
                        "reasoning_depth": reasoning_depth,
                        "tool_results": all_tool_results,
                        "all_responses": all_responses,
                        "mode": "agent_complete"
                    }

                # ✅ 执行工具调用
                tool_results = self._execute_tool_calls(tool_calls)
                
                # 记录成功执行的工具
                successful_calls = sum(1 for r in tool_results if r.get("result", {}).get("status") != "error")
                tool_calls_made += successful_calls
                all_tool_results.extend(tool_results)

                # ✅ 将助手消息添加到对话中
                assistant_msg = {
                    "role": "assistant",
                    "content": content or "正在调用工具获取数据..."
                }
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                messages.append(assistant_msg)

                # ✅ 将工具执行结果添加到对话中
                for result in tool_results:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": result["tool_call_id"],
                        "content": json.dumps(result["result"], ensure_ascii=False)
                    })

            # ✅ 达到最大调用次数，生成最终总结
            logger.info(f"⚠️ 达到最大工具调用次数 ({self.max_tool_calls})，生成总结")
            
            # 要求 DS API 生成最终总结
            summary_prompt = {
                "role": "user",
                "content": """请根据以上所有工具调用结果，生成一份完整的中文分析报告。

报告必须包含以下三个部分（每部分至少2句话）：
1. 📊 数据摘要：列出所有关键数据和发现
2. 📈 分析结论：基于数据给出明确判断
3. 💡 操作建议：给出具体可执行的操作建议

请确保报告结构清晰，内容完整。"""
            }
            messages.append(summary_prompt)
            
            final_response = self._call_ds_api(messages)
            if final_response:
                final_content = final_response.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                final_content = "分析完成，详情请查看工具调用结果。"

            return {
                "status": "warning",
                "response": final_content,
                "tool_calls_made": tool_calls_made,
                "reasoning_depth": reasoning_depth,
                "tool_results": all_tool_results,
                "all_responses": all_responses,
                "mode": "agent_terminated"
            }

        except Exception as e:
            logger.error(f"DS Agent 执行异常: {e}")
            return {
                "status": "error",
                "error": str(e),
                "mode": "fallback",
                "tool_calls_made": tool_calls_made,
                "reasoning_depth": reasoning_depth
            }

    def _build_messages(self, user_query: str, context: Optional[Dict] = None) -> List[Dict]:
        """构建消息列表"""
        system_prompt = self._get_system_prompt()

        messages = [{
            "role": "system",
            "content": system_prompt
        }]

        if context:
            messages.append({
                "role": "user",
                "content": f"当前上下文: {json.dumps(context, ensure_ascii=False)}"
            })

        messages.append({
            "role": "user",
            "content": user_query
        })

        return messages

    def _get_system_prompt(self) -> str:
        """✅ 优化：增强系统提示词，强制生成文字总结"""
        return """
你是 V 系统的智能分析代理（DS API Agent）。

你的职责：
1. 理解用户的分析需求
2. 决定需要调用哪些工具获取数据
3. 基于数据生成分析结论
4. 返回结构化的分析报告

【重要】输出格式要求：
每次工具调用后，必须生成至少 3 句话的文本总结。
最终报告必须包含以下三部分：
1. 📊 数据摘要：（列出所有关键数据点，至少3个）
2. 📈 分析结论：（给出明确判断，至少2句话）
3. 💡 操作建议：（给出具体建议，至少2条）

禁止只返回工具调用结果而不生成文字总结。
禁止使用"根据数据..."等模糊表述，必须给出明确结论。

可用工具说明：
1. get_sector_quote - 获取板块实时行情（价格、涨跌幅）
2. calculate_drawdown - 计算52周回撤百分比
3. get_market_environment - 获取市场环境（牛/熊/震荡）
4. get_north_flow - 获取北向资金净流入/流出
5. get_sentiment_score - 获取消息面烈度评分（0-10分）
6. get_holding_signal - 获取持仓基金合并信号
7. get_extreme_sectors - 获取最强和最弱板块
8. get_historical_data - 获取板块历史数据
9. generate_analysis_report - 生成综合分析报告

规则约束：
1. 每次最多调用 5 个工具
2. 推理深度不超过 5 层
3. 工具调用失败时，尝试降级方案
4. 返回结果必须包含数据来源标注（AKShare/NewsAPI/Tushare）

示例输出：
📊 数据摘要：
- 电子板块回撤 0.1%，接近52周高点
- 计算机板块回撤 55.6%，深度超跌
- 市场环境：震荡
📈 分析结论：
计算机板块回撤充分，接近历史低位，存在反弹机会。
电子板块相对强势，但追高风险较大。
💡 操作建议：
1. 建议关注计算机板块的超跌机会
2. 电子板块暂不建议追高，等待回调
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
                "max_tokens": 4096,
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

            # ✅ 通过 Bridge 安全过滤
            allowed, reason = Bridge.filter_request(tool_name, arguments)
            if not allowed:
                logger.warning(f"🚫 Bridge 拒绝: {reason}")
                results.append({
                    "tool_call_id": tool_call.get("id", ""),
                    "result": {"status": "error", "error": reason}
                })
                continue

            # 执行工具
            result = execute_tool(tool_name, **arguments)

            # 记录到 Bridge
            Bridge.record_request(tool_name, arguments, result)

            results.append({
                "tool_call_id": tool_call.get("id", ""),
                "result": result
            })

        return results

    # ============================================================
    # 快捷方法
    # ============================================================
    def analyze_sector(self, sector_name: str) -> Dict:
        """分析单个板块"""
        query = f"请分析 {sector_name} 板块的当前状态，包括回撤、烈度评分和市场环境"
        return self.think(query)

    def analyze_holdings(self) -> Dict:
        """分析持仓"""
        query = "请分析所有持仓基金的当前信号状态，并给出操作建议"
        return self.think(query)

    def get_daily_summary(self) -> Dict:
        """获取每日摘要"""
        query = "请生成今日市场摘要，包括最强/最弱板块、市场环境、北向资金流向"
        return self.think(query)
