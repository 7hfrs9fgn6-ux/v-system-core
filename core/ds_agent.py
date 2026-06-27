#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DS API 智能代理（大脑）- P3升级版
支持研报级分析输出
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
    DS API 智能代理 - P3 升级版
    自主识别意图 → 决策工具调用 → 多步推理 → 返回研报级结果
    """

    def __init__(self):
        self.api_key = os.environ.get("DEEPSEEK_API_KEY")
        self.base_url = "https://api.deepseek.com/v1"
        self.enabled = bool(self.api_key and self.api_key != "")
        self.max_tool_calls = 20
        self.max_reasoning_depth = 5
        self.timeout = 30

        self.tools = get_tool_schema()
        self.tool_functions = TOOL_REGISTRY

        if self.enabled:
            logger.info(f"✅ DS API 智能代理已初始化（P3研报级），已注册 {len(self.tools)} 个工具")
            logger.info(f"   📊 最大工具调用: {self.max_tool_calls} 次")
            logger.info(f"   📊 最大推理深度: {self.max_reasoning_depth} 层")
        else:
            logger.warning("⚠️ DS API Key 未配置，智能代理未启用")

    def think(self, user_query: str, context: Optional[Dict] = None) -> Dict:
        """核心方法：接收用户查询，返回推理结果"""
        if not self.enabled:
            return {"status": "error", "error": "DS API 未启用", "mode": "fallback"}

        messages = self._build_messages(user_query, context)
        tool_calls_made = 0
        reasoning_depth = 0
        all_tool_results = []
        all_responses = []

        try:
            while tool_calls_made < self.max_tool_calls and reasoning_depth < self.max_reasoning_depth:
                reasoning_depth += 1
                logger.info(f"🔄 推理轮次 {reasoning_depth}/{self.max_reasoning_depth}")

                response = self._call_ds_api(messages)
                if not response:
                    return {"status": "error", "error": "DS API 调用失败", "mode": "fallback"}

                message = response.get("choices", [{}])[0].get("message", {})
                tool_calls = message.get("tool_calls", [])

                content = message.get("content", "")
                if content:
                    all_responses.append(content)

                if not tool_calls:
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

                tool_results = self._execute_tool_calls(tool_calls)
                successful_calls = sum(1 for r in tool_results if r.get("result", {}).get("status") != "error")
                tool_calls_made += successful_calls
                all_tool_results.extend(tool_results)

                assistant_msg = {"role": "assistant", "content": content or "正在调用工具获取数据..."}
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                messages.append(assistant_msg)

                for result in tool_results:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": result["tool_call_id"],
                        "content": json.dumps(result["result"], ensure_ascii=False)
                    })

            # 达到最大次数，请求总结
            logger.info(f"⚠️ 达到最大工具调用次数 ({self.max_tool_calls})，生成总结")
            summary_prompt = {
                "role": "user",
                "content": """请根据以上所有工具调用结果，生成一份完整的研报级分析报告。

报告必须包含以下五部分（每部分至少2句话）：
1. 📊 市场概览：大盘指数、涨跌家数、市场情绪
2. 📈 板块逻辑分析：最强板块为什么强？最弱板块为什么弱？详细解释逻辑
3. ⚠️ 风险预警：列出主要风险，标注等级（高/中/低）和应对建议
4. 💡 操作建议：针对持仓基金给出具体操作建议
5. 📌 总结：一句话总结今日市场

请确保报告结构清晰，内容完整，语言专业但有温度。"""
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
            return {"status": "error", "error": str(e), "mode": "fallback"}

    def _build_messages(self, user_query: str, context: Optional[Dict] = None) -> List[Dict]:
        messages = [{"role": "system", "content": self._get_system_prompt()}]
        if context:
            messages.append({"role": "user", "content": f"当前上下文: {json.dumps(context, ensure_ascii=False)}"})
        messages.append({"role": "user", "content": user_query})
        return messages

    def _get_system_prompt(self) -> str:
        """✅ P3升级：强制研报级输出格式"""
        return """
你是 V 系统的智能分析代理（DS API Agent）。你的核心职责是生成研报级的市场分析报告。

【输出格式要求】你的每次分析必须严格按以下格式输出：

📊 市场概览
- 上证指数收盘价和涨跌幅
- 涨跌家数统计（上涨/下跌/平盘）
- 市场情绪判断（普涨/震荡/普跌）

📈 板块逻辑分析
- 最强板块：列出信号最强的2-3个板块
  - 为什么强？（结合回撤数据、相对强度、消息面等）
  - 是否有持续性？
- 最弱板块：列出信号最弱的2-3个板块
  - 为什么弱？
  - 是否应该回避？

⚠️ 风险预警
- 风险1：[风险名称] | 等级：高/中/低 | 应对建议：[具体建议]
- 风险2：[风险名称] | 等级：高/中/低 | 应对建议：[具体建议]

💡 操作建议
- 针对每个持仓基金给出具体操作（如：009777科技基金：等待企稳，暂不加仓）
- 明确是加仓、减仓、持有还是观望

📌 总结
- 一句话概括今日市场核心观点

【数据来源说明】
所有数据均来自 AKShare（A股行情）、NewsAPI（新闻）、Tushare（备用），分析基于52周回撤、相对强度和消息面烈度评分。

【规则约束】
1. 每次最多调用 5 个工具
2. 推理深度不超过 5 层
3. 工具调用失败时，尝试降级方案
4. 每个结论必须有数据支撑
5. 禁止使用“可能”“或许”等模糊词汇，给出明确判断
"""

    def _call_ds_api(self, messages: List[Dict]) -> Optional[Dict]:
        try:
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            payload = {
                "model": "deepseek-chat",
                "messages": messages,
                "tools": self.tools,
                "tool_choice": "auto",
                "max_tokens": 4096,
                "temperature": 0.3
            }
            response = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=self.timeout)
            if response.status_code == 200:
                return response.json()
            logger.error(f"DS API 调用失败: {response.status_code} - {response.text}")
            return None
        except Exception as e:
            logger.error(f"DS API 调用异常: {e}")
            return None

    def _execute_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        results = []
        for tool_call in tool_calls:
            function = tool_call.get("function", {})
            tool_name = function.get("name", "")
            arguments = json.loads(function.get("arguments", "{}"))
            logger.info(f"🔧 执行工具: {tool_name}({arguments})")
            allowed, reason = Bridge.filter_request(tool_name, arguments)
            if not allowed:
                logger.warning(f"🚫 Bridge 拒绝: {reason}")
                results.append({"tool_call_id": tool_call.get("id", ""), "result": {"status": "error", "error": reason}})
                continue
            result = execute_tool(tool_name, **arguments)
            Bridge.record_request(tool_name, arguments, result)
            results.append({"tool_call_id": tool_call.get("id", ""), "result": result})
        return results

    # ============================================================
    # P3：研报级分析方法
    # ============================================================
    def get_daily_summary(self) -> Dict:
        """获取每日摘要（P3升级：研报级）"""
        query = """请生成今日完整的研报级市场分析报告，包含：市场概览、板块逻辑、风险预警、操作建议、总结五大部分。请确保分析深入、逻辑清晰、建议具体。"""
        return self.think(query)

    def get_analysis_report(self) -> Dict:
        """P3新增：专门获取研报级分析报告"""
        return self.get_daily_summary()

    def analyze_sector(self, sector_name: str) -> Dict:
        """分析单个板块（P3升级）"""
        query = f"""请对 {sector_name} 板块进行深入分析，包含：
        1. 当前行情（价格、回撤、相对强度）
        2. 逻辑解读：为什么涨/跌？
        3. 投资建议：是否值得关注？
        """
        return self.think(query)

    def analyze_holdings(self) -> Dict:
        """分析持仓（P3升级）"""
        query = """请分析所有持仓基金，给出具体操作建议（加仓/减仓/持有/观望），并说明理由。"""
        return self.think(query)
