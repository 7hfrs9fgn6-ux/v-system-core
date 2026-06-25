# ============================================================
# 相对强度因子（精阶段 V1.1.45）
# 计算板块相对大盘的强度比值
# ============================================================

import logging
import pandas as pd
import akshare as ak
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class RelativeStrengthEngine:
    """相对强度因子计算引擎"""

    def __init__(self, config: dict):
        self.config = config.get("relative_strength", {})
        self.enabled = self.config.get("enabled", True)
        self.lookback_days = self.config.get("lookback_days", 60)
        self.threshold = self.config.get("threshold", 1.2)

    def calculate(self, sector_name: str) -> Dict:
        """
        计算单个板块的相对强度
        返回: {strength_ratio, interpretation, signal_adjustment}
        """
        if not self.enabled:
            return {
                "strength_ratio": 1.0,
                "interpretation": "未启用",
                "signal_adjustment": 0
            }

        sector_return = self._get_sector_return(sector_name)
        market_return = self._get_market_return()

        if sector_return is None or market_return is None or market_return == 0:
            return {
                "strength_ratio": 1.0,
                "interpretation": "数据不足",
                "signal_adjustment": 0
            }

        ratio = sector_return / market_return

        # 解读
        if ratio > 1.2:
            interpretation = "强势"
            adjustment = 1  # 信号上调一级
        elif ratio > 0.8:
            interpretation = "中性"
            adjustment = 0
        else:
            interpretation = "弱势"
            adjustment = -1  # 信号下调一级

        return {
            "strength_ratio": round(ratio, 2),
            "sector_return": round(sector_return, 2),
            "market_return": round(market_return, 2),
            "interpretation": interpretation,
            "signal_adjustment": adjustment
        }

    def _get_sector_return(self, sector_name: str) -> Optional[float]:
        """获取板块指定周期的收益率"""
        try:
            # 获取行业指数历史数据
            code = self._get_sector_code(sector_name)
            if not code:
                return None

            df = ak.index_hist_sw(symbol=code)
            if df is None or df.empty:
                return None

            # 识别收盘价列
            close_col = None
            for c in df.columns:
                if '收' in c or 'close' in c.lower():
                    close_col = c
                    break

            if not close_col:
                return None

            # 计算指定周期的收益率
            end_date = datetime.now()
            start_date = end_date - timedelta(days=self.lookback_days)

            df['date'] = pd.to_datetime(df['date'])
            df = df[df['date'] <= end_date]

            if len(df) < 2:
                return None

            start_price = df[close_col].iloc[-min(self.lookback_days, len(df))-1]
            end_price = df[close_col].iloc[-1]

            return (end_price - start_price) / start_price * 100

        except Exception as e:
            logger.warning(f"获取板块收益率失败 {sector_name}: {e}")
            return None

    def _get_market_return(self) -> Optional[float]:
        """获取市场（上证指数）指定周期的收益率"""
        try:
            df = ak.stock_zh_index_daily(symbol="sh000001")
            if df is None or df.empty:
                return None

            # 识别收盘价列
            close_col = None
            for c in df.columns:
                if '收' in c or 'close' in c.lower():
                    close_col = c
                    break

            if not close_col:
                return None

            end_date = datetime.now()
            start_date = end_date - timedelta(days=self.lookback_days)

            df['date'] = pd.to_datetime(df['date'])
            df = df[df['date'] <= end_date]

            if len(df) < 2:
                return None

            start_price = df[close_col].iloc[-min(self.lookback_days, len(df))-1]
            end_price = df[close_col].iloc[-1]

            return (end_price - start_price) / start_price * 100

        except Exception as e:
            logger.warning(f"获取大盘收益率失败: {e}")
            return None

    def _get_sector_code(self, sector_name: str) -> Optional[str]:
        """获取板块对应的申万代码"""
        code_map = {
            "电子": "801080",
            "计算机": "801750",
            "通信": "801770",
            "传媒": "801760",
            "医药生物": "801150",
            "食品饮料": "801120",
            "家用电器": "801110",
            "电力设备": "801730",
            "汽车": "801880",
            "国防军工": "801740",
            "银行": "801780",
            "非银金融": "801790",
            "公用事业": "801160",
            "煤炭": "801950",
            "石油石化": "801960",
        }
        return code_map.get(sector_name)
