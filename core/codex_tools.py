#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Codex - 工具执行层（手脚）
包含 17 个工具函数：
  原有工具（10个）：行情、回撤、市场环境、北向、烈度、持仓、极端、历史、报告、网页抓取
  P0新增工具（7个）：宏观快照、美股、亚太、欧洲、大宗商品、汇率、A50期货
"""

import os
import logging
import json
import requests
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# 尝试导入网页解析库
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None
    logging.warning("⚠️ beautifulsoup4 未安装，网页抓取工具不可用")

# P0阶段新增：导入宏观采集器
from core.macro_collector import MacroCollector

logger = logging.getLogger(__name__)


class CodexTools:
    """Codex 工具执行层 - 所有工具函数"""

    def __init__(self):
        self.tushare_token = os.environ.get("TUSHARE_TOKEN")
        self._ts_pro = None
        self._init_tushare()
        # P0阶段新增：宏观采集器实例
        self._macro = MacroCollector()

    def _init_tushare(self):
        if self.tushare_token:
            try:
                import tushare as ts
                ts.set_token(self.tushare_token)
                self._ts_pro = ts.pro_api()
            except:
                pass

    # ============================================================
    # 原有工具（1-10）
    # ============================================================

    # 工具1：获取板块行情
    def get_sector_quote(self, sector_name: str) -> Dict:
        try:
            import akshare as ak
            code = self._get_sector_code(sector_name)
            if not code:
                return {"status": "error", "error": f"未知板块: {sector_name}"}
            df = ak.index_hist_sw(symbol=code)
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                close_col = self._find_column(df, ['收', 'close'])
                high_col = self._find_column(df, ['高', 'high'])
                return {
                    "status": "success",
                    "sector": sector_name,
                    "code": code,
                    "close": float(latest[close_col]) if close_col else 0,
                    "high": float(latest[high_col]) if high_col else 0,
                    "data_source": "AKShare"
                }
            return {"status": "error", "error": f"无法获取 {sector_name} 数据"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # 工具2：计算52周回撤
    def calculate_drawdown(self, sector_name: str) -> Dict:
        try:
            import akshare as ak
            code = self._get_sector_code(sector_name)
            if not code:
                return {"status": "error", "error": f"未知板块: {sector_name}"}
            df = ak.index_hist_sw(symbol=code)
            if df is not None and not df.empty:
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
                            "status": "success",
                            "sector": sector_name,
                            "drawdown": drawdown,
                            "threshold": threshold,
                            "signal_level": signal_level,
                            "data_source": "AKShare"
                        }
            return {"status": "error", "error": f"无法计算 {sector_name} 回撤"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # 工具3：获取市场环境
    def get_market_environment(self) -> Dict:
        try:
            import akshare as ak
            df = ak.stock_zh_index_daily(symbol="sh000001")
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                recent = df.tail(20)
                close_col = self._find_column(df, ['收', 'close'])
                if close_col:
                    pct = (latest[close_col] - recent.iloc[0][close_col]) / recent.iloc[0][close_col] * 100
                    trend = "bull" if pct > 3 else "bear" if pct < -3 else "range"
                    return {
                        "status": "success",
                        "trend": trend,
                        "pct_change": round(pct, 2),
                        "current": latest[close_col],
                        "data_source": "AKShare"
                    }
            return {"status": "error", "error": "无法获取市场环境"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # 工具4：获取北向资金
    def get_north_flow(self) -> Dict:
        try:
            import akshare as ak
            df = ak.stock_hsgt_north_net_flow_in(symbol="北上")
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                value_col = self._find_column(df, ['value', '净流入'])
                if value_col:
                    return {
                        "status": "success",
                        "north_flow": float(latest[value_col]),
                        "data_source": "AKShare"
                    }
            return {"status": "error", "error": "无法获取北向资金"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # 工具5：获取烈度评分
    def get_sentiment_score(self, sector_name: str) -> Dict:
        try:
            from core.sentiment_engine import SentimentEngine
            engine = SentimentEngine()
            result = engine.analyze(sector_name, force_refresh=True)
            return {
                "status": "success",
                "sector": sector_name,
                "intensity_score": result.get('intensity_score', 0),
                "emotion_label": result.get('emotion_label', '中性'),
                "news_count": result.get('news_count', 0),
                "data_source": result.get('数据源', '未知')
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # 工具6：获取持仓信号
    def get_holding_signal(self, fund_code: str) -> Dict:
        try:
            import yaml
            config_path = "config.yaml"
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                holdings = config.get('holdings', {})
                if fund_code in holdings:
                    fund_info = holdings[fund_code]
                    sectors = fund_info.get('sectors', [])
                    signals = []
                    for sec in sectors:
                        result = self.calculate_drawdown(sec)
                        if result.get('status') == 'success':
                            signals.append({
                                "sector": sec,
                                "signal_level": result.get('signal_level', 0),
                                "drawdown": result.get('drawdown', 0)
                            })
                    if signals:
                        best = max(signals, key=lambda x: x['signal_level'])
                        return {
                            "status": "success",
                            "fund_code": fund_code,
                            "fund_name": fund_info.get('name', fund_code),
                            "best_sector": best['sector'],
                            "signal_level": best['signal_level'],
                            "drawdown": best['drawdown']
                        }
            return {"status": "error", "error": f"基金 {fund_code} 未找到"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # 工具7：获取最强/最弱板块
    def get_extreme_sectors(self) -> Dict:
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
                    "status": "success",
                    "strongest": strongest,
                    "weakest": weakest,
                    "data_source": "AKShare"
                }
            return {"status": "error", "error": "无法获取板块数据"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # 工具8：获取历史数据
    def get_historical_data(self, sector_name: str, days: int = 30) -> Dict:
        try:
            import akshare as ak
            code = self._get_sector_code(sector_name)
            if not code:
                return {"status": "error", "error": f"未知板块: {sector_name}"}
            df = ak.index_hist_sw(symbol=code)
            if df is not None and not df.empty:
                close_col = self._find_column(df, ['收', 'close'])
                if close_col:
                    historical = df.tail(days)[[close_col]].to_dict()
                    return {
                        "status": "success",
                        "sector": sector_name,
                        "days": days,
                        "data": historical,
                        "data_source": "AKShare"
                    }
            return {"status": "error", "error": f"无法获取 {sector_name} 历史数据"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # 工具9：生成分析报告
    def generate_analysis_report(self, sector_name: str) -> Dict:
        try:
            quote = self.get_sector_quote(sector_name)
            drawdown = self.calculate_drawdown(sector_name)
            sentiment = self.get_sentiment_score(sector_name)
            return {
                "status": "success",
                "sector": sector_name,
                "timestamp": datetime.now().isoformat(),
                "quote": quote if quote.get('status') == 'success' else None,
                "drawdown": drawdown if drawdown.get('status') == 'success' else None,
                "sentiment": sentiment if sentiment.get('status') == 'success' else None,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # 工具10：网页抓取（原有）
    def fetch_webpage(self, url: str) -> Dict:
        if BeautifulSoup is None:
            return {
                "status": "error",
                "error": "beautifulsoup4 未安装，请运行: pip install beautifulsoup4 lxml"
            }
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                return {"status": "error", "error": f"HTTP {resp.status_code}", "url": url}
            soup = BeautifulSoup(resp.text, 'html.parser')
            for script in soup(["script", "style", "noscript", "meta", "link"]):
                script.decompose()
            text = soup.get_text(separator='\n')
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            content = '\n'.join(lines[:200])
            return {
                "status": "success",
                "url": url,
                "content": content,
                "content_length": len(content),
                "line_count": len(lines[:200]),
                "data_source": "Web"
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "url": url}

    # ============================================================
    # P0阶段新增宏观工具（11-17）
    # ============================================================

    # 工具11：宏观快照（一次性获取所有宏观数据）
    def get_macro_snapshot(self) -> Dict:
        """获取完整的宏观数据快照（美股、亚太、欧洲、大宗、汇率、A50期货）"""
        try:
            result = self._macro.get_macro_snapshot()
            return {"status": "success", "data": result, "data_source": "MacroCollector"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # 工具12：美股市场
    def get_us_market(self) -> Dict:
        """获取美股市场数据（三大指数、费城半导体、科技巨头）"""
        try:
            result = self._macro.get_us_market()
            return {"status": "success", "data": result, "data_source": "MacroCollector"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # 工具13：亚太市场
    def get_asia_market(self) -> Dict:
        """获取亚太市场数据（日经、韩国、恒生、台湾）"""
        try:
            result = self._macro.get_asia_market()
            return {"status": "success", "data": result, "data_source": "MacroCollector"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # 工具14：欧洲市场
    def get_europe_market(self) -> Dict:
        """获取欧洲市场数据（德国DAX、英国FTSE、法国CAC）"""
        try:
            result = self._macro.get_europe_market()
            return {"status": "success", "data": result, "data_source": "MacroCollector"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # 工具15：大宗商品
    def get_commodities(self) -> Dict:
        """获取大宗商品数据（WTI原油、布伦特原油、黄金）"""
        try:
            result = self._macro.get_commodities()
            return {"status": "success", "data": result, "data_source": "MacroCollector"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # 工具16：汇率
    def get_forex(self) -> Dict:
        """获取人民币汇率数据（在岸价、中间价）"""
        try:
            result = self._macro.get_forex()
            return {"status": "success", "data": result, "data_source": "MacroCollector"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # 工具17：A50期货
    def get_a50_futures(self) -> Dict:
        """获取A50期货夜盘数据"""
        try:
            result = self._macro.get_a50_futures()
            return {"status": "success", "data": result, "data_source": "MacroCollector"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ============================================================
    # 辅助方法（不变）
    # ============================================================
    def _get_sector_code(self, sector_name: str) -> Optional[str]:
        code_map = {
            "电子": "801080", "计算机": "801750", "通信": "801770",
            "传媒": "801760", "医药生物": "801150", "食品饮料": "801120",
            "家用电器": "801110", "电力设备": "801730", "汽车": "801880",
            "国防军工": "801740", "银行": "801780", "非银金融": "801790",
            "公用事业": "801160", "煤炭": "801950", "石油石化": "801960",
        }
        return code_map.get(sector_name)

    def _get_all_sectors(self) -> List[str]:
        return ["电子", "计算机", "通信", "传媒", "医药生物", "食品饮料",
                "家用电器", "电力设备", "汽车", "国防军工", "银行", "非银金融",
                "公用事业", "煤炭", "石油石化"]

    def _get_threshold(self, sector_name: str) -> float:
        threshold_map = {
            "电子": 25.0, "计算机": 25.0, "通信": 20.0, "传媒": 25.0, "医药生物": 30.0,
            "食品饮料": 25.0, "家用电器": 18.0, "电力设备": 25.0, "汽车": 25.0,
            "国防军工": 25.0, "银行": 20.0, "非银金融": 20.0, "公用事业": 15.0,
            "煤炭": 20.0, "石油石化": 20.0,
        }
        return threshold_map.get(sector_name, 25.0)

    def _calculate_signal_level(self, drawdown: float, threshold: float) -> int:
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
        for c in df.columns:
            for candidate in candidates:
                if candidate in c or c in candidate:
                    return c
        return None


# ============================================================
# 工具注册表（包含全部 17 个工具）
# ============================================================
tools_instance = CodexTools()

TOOL_REGISTRY = {
    # ---- 原有工具 ----
    "get_sector_quote": {
        "name": "get_sector_quote",
        "description": "获取指定板块的实时行情数据（价格、涨跌幅）",
        "parameters": {"type": "object", "properties": {"sector_name": {"type": "string"}}, "required": ["sector_name"]},
        "function": tools_instance.get_sector_quote
    },
    "calculate_drawdown": {
        "name": "calculate_drawdown",
        "description": "计算指定板块的52周回撤百分比和信号等级",
        "parameters": {"type": "object", "properties": {"sector_name": {"type": "string"}}, "required": ["sector_name"]},
        "function": tools_instance.calculate_drawdown
    },
    "get_market_environment": {
        "name": "get_market_environment",
        "description": "获取当前市场环境（bull=牛市、bear=熊市、range=震荡）",
        "parameters": {"type": "object", "properties": {}},
        "function": tools_instance.get_market_environment
    },
    "get_north_flow": {
        "name": "get_north_flow",
        "description": "获取北向资金净流入/流出数据（单位：万元）",
        "parameters": {"type": "object", "properties": {}},
        "function": tools_instance.get_north_flow
    },
    "get_sentiment_score": {
        "name": "get_sentiment_score",
        "description": "获取指定板块的消息面烈度评分（0-10分）和情绪标签",
        "parameters": {"type": "object", "properties": {"sector_name": {"type": "string"}}, "required": ["sector_name"]},
        "function": tools_instance.get_sentiment_score
    },
    "get_holding_signal": {
        "name": "get_holding_signal",
        "description": "获取指定持仓基金的合并信号（基于其映射板块）",
        "parameters": {"type": "object", "properties": {"fund_code": {"type": "string"}}, "required": ["fund_code"]},
        "function": tools_instance.get_holding_signal
    },
    "get_extreme_sectors": {
        "name": "get_extreme_sectors",
        "description": "获取当前所有板块中最强和最弱的板块",
        "parameters": {"type": "object", "properties": {}},
        "function": tools_instance.get_extreme_sectors
    },
    "get_historical_data": {
        "name": "get_historical_data",
        "description": "获取板块最近N天的历史价格数据",
        "parameters": {"type": "object", "properties": {"sector_name": {"type": "string"}, "days": {"type": "integer", "default": 30}}, "required": ["sector_name"]},
        "function": tools_instance.get_historical_data
    },
    "generate_analysis_report": {
        "name": "generate_analysis_report",
        "description": "生成单个板块的综合分析报告（含行情、回撤、烈度）",
        "parameters": {"type": "object", "properties": {"sector_name": {"type": "string"}}, "required": ["sector_name"]},
        "function": tools_instance.generate_analysis_report
    },
    "fetch_webpage": {
        "name": "fetch_webpage",
        "description": "抓取指定URL的网页内容，提取纯文本信息。用于获取新闻、公告、研报等外部信息",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "要抓取的网页完整URL（需以http://或https://开头）"}
            },
            "required": ["url"]
        },
        "function": tools_instance.fetch_webpage
    },
    # ---- P0阶段新增宏观工具 ----
    "get_macro_snapshot": {
        "name": "get_macro_snapshot",
        "description": "获取完整的宏观数据快照，包括美股、亚太、欧洲、大宗商品、汇率、A50期货。用于盘前预测和夜间预测的宏观分析。",
        "parameters": {"type": "object", "properties": {}},
        "function": tools_instance.get_macro_snapshot
    },
    "get_us_market": {
        "name": "get_us_market",
        "description": "获取美股市场数据，包括道指、纳指、标普500、费城半导体指数、科技巨头（苹果、英伟达等）",
        "parameters": {"type": "object", "properties": {}},
        "function": tools_instance.get_us_market
    },
    "get_asia_market": {
        "name": "get_asia_market",
        "description": "获取亚太市场数据，包括日经225、韩国KOSPI、恒生指数、台湾加权指数",
        "parameters": {"type": "object", "properties": {}},
        "function": tools_instance.get_asia_market
    },
    "get_europe_market": {
        "name": "get_europe_market",
        "description": "获取欧洲市场数据，包括德国DAX、英国富时100、法国CAC40",
        "parameters": {"type": "object", "properties": {}},
        "function": tools_instance.get_europe_market
    },
    "get_commodities": {
        "name": "get_commodities",
        "description": "获取大宗商品数据，包括WTI原油、布伦特原油、黄金",
        "parameters": {"type": "object", "properties": {}},
        "function": tools_instance.get_commodities
    },
    "get_forex": {
        "name": "get_forex",
        "description": "获取人民币汇率数据，包括在岸价、离岸价、中间价",
        "parameters": {"type": "object", "properties": {}},
        "function": tools_instance.get_forex
    },
    "get_a50_futures": {
        "name": "get_a50_futures",
        "description": "获取A50期货夜盘数据，用于预判A股次日开盘",
        "parameters": {"type": "object", "properties": {}},
        "function": tools_instance.get_a50_futures
    }
}


def get_tool_schema() -> List[Dict]:
    """获取所有工具的 OpenAPI Schema"""
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
    """执行指定的工具"""
    if tool_name in TOOL_REGISTRY:
        try:
            result = TOOL_REGISTRY[tool_name]["function"](**kwargs)
            return result if isinstance(result, dict) else {"status": "success", "data": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    return {"status": "error", "error": f"未知工具: {tool_name}"}
