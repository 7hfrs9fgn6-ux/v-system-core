#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Codex - 工具执行层（手脚）
提供 DS API 可调用的 9 个预定义工具函数
对应精阶段 V1.1.44 的 9 个工具函数定义
"""

import os
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable

logger = logging.getLogger(__name__)


class CodexTools:
    """
    Codex 工具执行层
    所有工具函数供 DS API Agent 调用
    """

    def __init__(self):
        self.tushare_token = os.environ.get("TUSHARE_TOKEN")
        self._init_tushare()

    def _init_tushare(self):
        """初始化 Tushare"""
        if self.tushare_token:
            try:
                import tushare as ts
                ts.set_token(self.tushare_token)
                self._ts_pro = ts.pro_api()
            except:
                self._ts_pro = None
        else:
            self._ts_pro = None

    # ============================================================
    # 工具1：获取板块行情
    # ============================================================
    def get_sector_quote(self, sector_name: str) -> Dict:
        """
        获取单个板块的实时行情数据
        对应规则：获取板块价格、涨跌幅、成交量等
        """
        try:
            # 直接调用 AKShare 获取行业指数
            import akshare as ak
            code = self._get_sector_code(sector_name)
            if not code:
                return {"error": f"未知板块: {sector_name}"}

            df = ak.index_hist_sw(symbol=code)
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                return {
                    "sector": sector_name,
                    "code": code,
                    "close": float(latest.get('close', 0)),
                    "high": float(latest.get('high', 0)),
                    "low": float(latest.get('low', 0)),
                    "volume": float(latest.get('volume', 0)),
                    "status": "success"
                }
            return {"error": f"无法获取 {sector_name} 数据"}
        except Exception as e:
            return {"error": str(e)}

    # ============================================================
    # 工具2：计算52周回撤
    # ============================================================
    def calculate_drawdown(self, sector_name: str) -> Dict:
        """
        计算板块的52周回撤
        对应规则：精阶段 V1.1.43 回撤计算
        """
        try:
            import akshare as ak
            code = self._get_sector_code(sector_name)
            if not code:
                return {"error": f"未知板块: {sector_name}"}

            df = ak.index_hist_sw(symbol=code)
            if df is not None and not df.empty:
                # 识别列名
                high_col = self._find_column(df, ['高', 'high'])
                close_col = self._find_column(df, ['收', 'close'])
                if high_col and close_col:
                    high_52w = df[high_col].max()
                    current = df[close_col].iloc[-1]
                    if high_52w > 0:
                        drawdown = round((high_52w - current) / high_52w * 100, 1)
                        threshold = self._get_threshold(sector_name)
                        signal_level = self._calculate_signal_level(drawdown, threshold)
                        return {
                            "sector": sector_name,
                            "code": code,
                            "high_52w": high_52w,
                            "current": current,
                            "drawdown": drawdown,
                            "threshold": threshold,
                            "signal_level": signal_level,
                            "status": "success"
                        }
            return {"error": f"无法计算 {sector_name} 回撤"}
        except Exception as e:
            return {"error": str(e)}

    # ============================================================
    # 工具3：获取市场环境
    # ============================================================
    def get_market_environment(self) -> Dict:
        """
        获取当前市场环境（牛/熊/震荡）
        对应规则：精阶段 V1.1.45 市场环境分级
        """
        try:
            import akshare as ak
            df = ak.stock_zh_index_daily(symbol="sh000001")
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                # 计算近20日涨跌幅
                recent = df.tail(20)
                pct_change = (latest['close'] - recent.iloc[0]['close']) / recent.iloc[0]['close'] * 100
                trend = "bull" if pct_change > 3 else "bear" if pct_change < -3 else "range"
                return {
                    "trend": trend,
                    "pct_change_20d": round(pct_change, 2),
                    "current": latest['close'],
                    "status": "success"
                }
            return {"error": "无法获取市场环境"}
        except Exception as e:
            return {"error": str(e)}

    # ============================================================
    # 工具4：获取北向资金
    # ============================================================
    def get_north_flow(self) -> Dict:
        """
        获取北向资金流向
        对应规则：精阶段 V1.1.46 资金维度
        """
        try:
            import akshare as ak
            df = ak.stock_hsgt_north_net_flow_in(symbol="北上")
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                # 识别列名
                value_col = self._find_column(df, ['value', '净流入', 'net_inflow'])
                if value_col:
                    return {
                        "north_flow": float(latest[value_col]),
                        "status": "success"
                    }
            return {"error": "无法获取北向资金"}
        except Exception as e:
            return {"error": str(e)}

    # ============================================================
    # 工具5：获取板块烈度评分
    # ============================================================
    def get_sentiment_score(self, sector_name: str) -> Dict:
        """
        获取板块的消息面烈度评分
        对应规则：精阶段 V1.1.45 烈度评分体系
        """
        try:
            from core.sentiment_engine import SentimentEngine
            engine = SentimentEngine()
            result = engine.analyze(sector_name, force_refresh=True)
            return {
                "sector": sector_name,
                "intensity_score": result.get('intensity_score', 0),
                "emotion_label": result.get('emotion_label', '中性'),
                "news_count": result.get('news_count', 0),
                "summary": result.get('summary', ''),
                "status": "success"
            }
        except Exception as e:
            return {"error": str(e)}

    # ============================================================
    # 工具6：获取持仓基金信号
    # ============================================================
    def get_holding_signal(self, fund_code: str) -> Dict:
        """
        获取单个持仓基金的合并信号
        对应规则：简阶段 V2.0.2 持仓映射规则
        """
        try:
            # 从配置读取持仓映射
            import yaml
            config_path = "config.yaml"
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                holdings = config.get('holdings', {})
                if fund_code in holdings:
                    fund_info = holdings[fund_code]
                    sectors = fund_info.get('sectors', [])
                    # 获取各板块信号
                    signals = []
                    for sec in sectors:
                        drawdown_result = self.calculate_drawdown(sec)
                        if drawdown_result.get('status') == 'success':
                            signals.append({
                                "sector": sec,
                                "signal_level": drawdown_result.get('signal_level', 0),
                                "drawdown": drawdown_result.get('drawdown', 0)
                            })
                    # 取最强信号
                    if signals:
                        best = max(signals, key=lambda x: x['signal_level'])
                        return {
                            "fund_code": fund_code,
                            "fund_name": fund_info.get('name', fund_code),
                            "best_sector": best['sector'],
                            "signal_level": best['signal_level'],
                            "drawdown": best['drawdown'],
                            "status": "success"
                        }
            return {"error": f"基金 {fund_code} 未找到"}
        except Exception as e:
            return {"error": str(e)}

    # ============================================================
    # 工具7：获取最强/最弱板块
    # ============================================================
    def get_extreme_sectors(self) -> Dict:
        """
        获取最强和最弱的板块
        对应规则：简阶段 V2.0.2 最强/最弱信号
        """
        try:
            sector_names = self._get_all_sectors()
            results = []
            for sector in sector_names:
                result = self.calculate_drawdown(sector)
                if result.get('status') == 'success':
                    results.append({
                        "sector": sector,
                        "drawdown": result.get('drawdown', 0),
                        "signal_level": result.get('signal_level', 0)
                    })

            if results:
                strongest = max(results, key=lambda x: x['signal_level'])
                weakest = min(results, key=lambda x: x['signal_level'])
                return {
                    "strongest": strongest,
                    "weakest": weakest,
                    "status": "success"
                }
            return {"error": "无法获取板块数据"}
        except Exception as e:
            return {"error": str(e)}

    # ============================================================
    # 工具8：获取历史数据
    # ============================================================
    def get_historical_data(self, sector_name: str, days: int = 30) -> Dict:
        """
        获取板块历史数据
        对应规则：精阶段 V1.1.52 记忆体查询
        """
        try:
            import akshare as ak
            code = self._get_sector_code(sector_name)
            if not code:
                return {"error": f"未知板块: {sector_name}"}

            df = ak.index_hist_sw(symbol=code)
            if df is not None and not df.empty:
                # 识别列名
                close_col = self._find_column(df, ['收', 'close'])
                if close_col:
                    historical = df.tail(days)[[close_col]].to_dict()
                    return {
                        "sector": sector_name,
                        "days": days,
                        "data": historical,
                        "status": "success"
                    }
            return {"error": f"无法获取 {sector_name} 历史数据"}
        except Exception as e:
            return {"error": str(e)}

    # ============================================================
    # 工具9：生成分析报告
    # ============================================================
    def generate_analysis_report(self, sector_name: str) -> Dict:
        """
        生成单个板块的综合分析报告
        对应规则：多个规则的综合输出
        """
        try:
            # 收集所有数据
            quote = self.get_sector_quote(sector_name)
            drawdown = self.calculate_drawdown(sector_name)
            sentiment = self.get_sentiment_score(sector_name)
            historical = self.get_historical_data(sector_name, days=30)

            report = {
                "sector": sector_name,
                "timestamp": datetime.now().isoformat(),
                "quote": quote if quote.get('status') == 'success' else None,
                "drawdown": drawdown if drawdown.get('status') == 'success' else None,
                "sentiment": sentiment if sentiment.get('status') == 'success' else None,
                "historical": historical if historical.get('status') == 'success' else None,
                "status": "success"
            }
            return report
        except Exception as e:
            return {"error": str(e)}

    # ============================================================
    # 辅助方法
    # ============================================================
    def _get_sector_code(self, sector_name: str) -> Optional[str]:
        """获取板块对应的申万代码"""
        code_map = {
            "电子": "801080", "计算机": "801750", "通信": "801770",
            "传媒": "801760", "医药生物": "801150", "食品饮料": "801120",
            "家用电器": "801110", "电力设备": "801730", "汽车": "801880",
            "国防军工": "801740", "银行": "801780", "非银金融": "801790",
            "公用事业": "801160", "煤炭": "801950", "石油石化": "801960",
        }
        return code_map.get(sector_name)

    def _get_all_sectors(self) -> List[str]:
        """获取所有板块名称"""
        return [
            "电子", "计算机", "通信", "传媒", "医药生物",
            "食品饮料", "家用电器", "电力设备", "汽车", "国防军工",
            "银行", "非银金融", "公用事业", "煤炭", "石油石化"
        ]

    def _get_threshold(self, sector_name: str) -> float:
        """获取板块阈值"""
        threshold_map = {
            "电子": 25.0, "计算机": 25.0, "通信": 20.0, "传媒": 25.0, "医药生物": 30.0,
            "食品饮料": 25.0, "家用电器": 18.0, "电力设备": 25.0, "汽车": 25.0, "国防军工": 25.0,
            "银行": 20.0, "非银金融": 20.0, "公用事业": 15.0, "煤炭": 20.0, "石油石化": 20.0,
        }
        return threshold_map.get(sector_name, 25.0)

    def _calculate_signal_level(self, drawdown: float, threshold: float) -> int:
        """计算信号等级"""
        excess = drawdown - threshold
        if excess >= 10:
            return 4
        elif excess >= 5:
            return 3
        elif excess >= 0:
            return 2
        elif excess >= -5:
            return 1
        elif excess >= -10:
            return -1
        else:
            return -2

    def _find_column(self, df, candidates: List[str]) -> Optional[str]:
        """查找匹配的列名"""
        for c in df.columns:
            for candidate in candidates:
                if candidate in c or c in candidate:
                    return c
        return None


# ============================================================
# 工具注册表（供 DS API 调用）
# ============================================================
TOOL_REGISTRY = {
    "get_sector_quote": {
        "name": "get_sector_quote",
        "description": "获取指定板块的实时行情数据（价格、涨跌幅、成交量等）",
        "parameters": {
            "type": "object",
            "properties": {
                "sector_name": {
                    "type": "string",
                    "description": "板块名称，如：电子、计算机、医药生物"
                }
            },
            "required": ["sector_name"]
        },
        "function": CodexTools().get_sector_quote
    },
    "calculate_drawdown": {
        "name": "calculate_drawdown",
        "description": "计算指定板块的52周回撤，返回回撤百分比和信号等级",
        "parameters": {
            "type": "object",
            "properties": {
                "sector_name": {
                    "type": "string",
                    "description": "板块名称"
                }
            },
            "required": ["sector_name"]
        },
        "function": CodexTools().calculate_drawdown
    },
    "get_market_environment": {
        "name": "get_market_environment",
        "description": "获取当前市场环境（bull=牛市、bear=熊市、range=震荡）",
        "parameters": {"type": "object", "properties": {}},
        "function": CodexTools().get_market_environment
    },
    "get_north_flow": {
        "name": "get_north_flow",
        "description": "获取北向资金净流入/流出数据",
        "parameters": {"type": "object", "properties": {}},
        "function": CodexTools().get_north_flow
    },
    "get_sentiment_score": {
        "name": "get_sentiment_score",
        "description": "获取指定板块的消息面烈度评分（0-10分）",
        "parameters": {
            "type": "object",
            "properties": {
                "sector_name": {
                    "type": "string",
                    "description": "板块名称"
                }
            },
            "required": ["sector_name"]
        },
        "function": CodexTools().get_sentiment_score
    },
    "get_holding_signal": {
        "name": "get_holding_signal",
        "description": "获取指定持仓基金的合并信号",
        "parameters": {
            "type": "object",
            "properties": {
                "fund_code": {
                    "type": "string",
                    "description": "基金代码，如：009777"
                }
            },
            "required": ["fund_code"]
        },
        "function": CodexTools().get_holding_signal
    },
    "get_extreme_sectors": {
        "name": "get_extreme_sectors",
        "description": "获取当前最强和最弱的板块",
        "parameters": {"type": "object", "properties": {}},
        "function": CodexTools().get_extreme_sectors
    },
    "get_historical_data": {
        "name": "get_historical_data",
        "description": "获取板块的历史数据（最近N天）",
        "parameters": {
            "type": "object",
            "properties": {
                "sector_name": {"type": "string"},
                "days": {"type": "integer", "default": 30}
            },
            "required": ["sector_name"]
        },
        "function": CodexTools().get_historical_data
    },
    "generate_analysis_report": {
        "name": "generate_analysis_report",
        "description": "生成单个板块的综合分析报告",
        "parameters": {
            "type": "object",
            "properties": {
                "sector_name": {"type": "string"}
            },
            "required": ["sector_name"]
        },
        "function": CodexTools().generate_analysis_report
    }
}


def get_tool_schema() -> List[Dict]:
    """
    获取所有工具的 OpenAPI Schema（供 DS API 调用）
    """
    schemas = []
    for name, tool in TOOL_REGISTRY.items():
        schemas.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"]
            }
        })
    return schemas


def execute_tool(tool_name: str, **kwargs) -> Dict:
    """
    执行指定的工具
    """
    if tool_name in TOOL_REGISTRY:
        tool = TOOL_REGISTRY[tool_name]
        try:
            result = tool["function"](**kwargs)
            return {"status": "success", "data": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    return {"status": "error", "error": f"未知工具: {tool_name}"}
