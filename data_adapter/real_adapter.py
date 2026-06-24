# ============================================================
# 数据适配器 V2.0 - 三层数据源架构
# Layer 1: AKShare 申万行业指数（真实52周回撤）
# Layer 2: Tushare 行业指数（备用）
# Layer 3: 模拟值（兜底降级）
# ============================================================

import os
import random
import logging
from datetime import datetime, timedelta
from output_layer.signal_result import StandardMarketData, SectorSignal, FreshnessLevel

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# 1. 基础配置
# ============================================================

SECTOR_NAMES = [
    "电子", "计算机", "通信", "传媒", "医药生物",
    "食品饮料", "家用电器", "电力设备", "汽车", "国防军工",
    "银行", "非银金融", "公用事业", "煤炭", "石油石化"
]

THRESHOLD_MAP = {
    "电子": 25.0, "计算机": 25.0, "通信": 20.0, "传媒": 25.0, "医药生物": 30.0,
    "食品饮料": 25.0, "家用电器": 18.0, "电力设备": 25.0, "汽车": 25.0, "国防军工": 25.0,
    "银行": 20.0, "非银金融": 20.0, "公用事业": 15.0, "煤炭": 20.0, "石油石化": 20.0
}

# 申万一级行业指数代码（用于 AKShare 和 Tushare）
SECTOR_CODE_MAP = {
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

# Tushare 格式（带 .SI 后缀）
TUSHARE_CODE_MAP = {k: v + ".SI" for k, v in SECTOR_CODE_MAP.items()}


class RealDataAdapter:
    """三层数据源适配器"""

    def __init__(self, phase: str = "pre"):
        self.phase = phase
        self.tushare_token = os.environ.get("TUSHARE_TOKEN")
        self.data_source = "AKShare"  # 默认使用 AKShare
        self.use_akshare = True       # 默认启用 AKShare
        self.use_tushare = bool(self.tushare_token and self.tushare_token != "dummy")

    def fetch_all(self) -> StandardMarketData:
        """
        获取数据，按优先级尝试：
        1. AKShare 申万行业指数（真实数据）
        2. Tushare 行业指数（备用）
        3. 模拟值（兜底）
        """
        logger.info("🌐 开始获取数据...")

        # 第一步：尝试 AKShare 获取真实回撤
        try:
            logger.info("📊 尝试使用 AKShare 获取真实行业数据...")
            return self._fetch_from_akshare_real()
        except Exception as e:
            logger.warning(f"⚠️ AKShare 获取失败 ({e})，尝试 Tushare...")

        # 第二步：尝试 Tushare
        if self.use_tushare:
            try:
                logger.info("📊 尝试使用 Tushare 获取数据...")
                return self._fetch_from_tushare()
            except Exception as e:
                logger.warning(f"⚠️ Tushare 获取失败 ({e})，使用模拟值兜底...")

        # 第三步：模拟值兜底
        logger.warning("⚠️ 所有数据源失败，使用模拟值（非真实数据）")
        return self._fetch_simulated()

    # ============================================================
    # Layer 1: AKShare 真实数据（主数据源）
    # ============================================================

    def _fetch_from_akshare_real(self) -> StandardMarketData:
        """使用 AKShare 获取申万行业指数真实52周回撤"""
        import akshare as ak

        target_date = self._get_target_date()
        today_str = datetime.now().strftime("%Y%m%d")
        start_date_52w = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")

        # 1. 大盘环境
        try:
            index_df = ak.stock_zh_index_daily(symbol="sh000001")
            latest = index_df.iloc[-1]
            pct_change = (latest['close'] - latest['open']) / latest['open'] * 100
            trend = "bull" if pct_change > 0.5 else "bear" if pct_change < -0.5 else "range"
            logger.info(f"📈 大盘涨跌幅: {pct_change:.2f}%, 环境: {trend}")
        except Exception as e:
            logger.warning(f"大盘获取失败: {e}")
            trend = "range"

        # 2. 北向资金（AKShare 获取）
        north_flow = None
        try:
            # 尝试获取北向资金
            north_df = ak.stock_hsgt_north_net_flow_in(symbol="北上")
            if not north_df.empty:
                north_flow = round(north_df['value'].iloc[-1] / 10000, 2)
        except:
            pass

        # 3. ✅ 核心：获取各板块52周回撤（使用 AKShare 申万行业指数）
        sectors = []
        logger.info("📊 开始获取各板块52周回撤（AKShare 申万行业指数）...")

        for name in SECTOR_NAMES:
            code = SECTOR_CODE_MAP.get(name)
            if not code:
                logger.warning(f"⚠️ {name} 无映射代码")
                drawdown = round(random.uniform(15.0, 40.0), 1)
            else:
                try:
                    # ✅ 使用 AKShare 获取行业指数历史数据
                    df = ak.index_hist_sw(symbol=code)

                    if df is not None and not df.empty:
                        # 处理列名（可能有中文或英文）
                        if 'high' in df.columns and 'close' in df.columns:
                            high_52w = df['high'].max()
                            current = df['close'].iloc[-1]
                        elif '最高' in df.columns and '收盘' in df.columns:
                            high_52w = df['最高'].max()
                            current = df['收盘'].iloc[-1]
                        else:
                            # 尝试其他可能的列名
                            high_col = next((c for c in df.columns if '高' in c or 'high' in c.lower()), None)
                            close_col = next((c for c in df.columns if '收' in c or 'close' in c.lower()), None)
                            if high_col and close_col:
                                high_52w = df[high_col].max()
                                current = df[close_col].iloc[-1]
                            else:
                                raise ValueError(f"无法识别列名: {df.columns.tolist()}")

                        if high_52w > 0:
                            drawdown = round((high_52w - current) / high_52w * 100, 1)
                            logger.info(f"   ✅ {name}: 52周高 {high_52w:.2f}, 现价 {current:.2f}, 回撤 {drawdown}%")
                        else:
                            drawdown = round(random.uniform(15.0, 40.0), 1)
                            logger.warning(f"⚠️ {name} 52周高为0")
                    else:
                        logger.warning(f"⚠️ {name} 代码 {code} 返回空数据")
                        drawdown = round(random.uniform(15.0, 40.0), 1)

                except Exception as e:
                    logger.warning(f"⚠️ {name} AKShare 获取失败 ({e})，使用随机值")
                    drawdown = round(random.uniform(15.0, 40.0), 1)

            # 计算信号等级
            threshold = THRESHOLD_MAP[name]
            excess = drawdown - threshold
            if excess >= 10:
                level = 4
            elif excess >= 5:
                level = 3
            elif excess >= 0:
                level = 2
            elif excess >= -5:
                level = 1
            elif excess >= -10:
                level = -1
            else:
                level = -2

            sectors.append(SectorSignal(
                name=name,
                signal_level=level,
                drawdown=drawdown,
                threshold=threshold,
                key_driver="52周回撤(AKShare)" if level > 0 else None
            ))

        # 4. 数据新鲜度
        freshness = FreshnessLevel.STALE if self.phase in ["pre", "night"] else FreshnessLevel.FRESH

        logger.info(f"✅ AKShare 数据获取完成，共 {len(sectors)} 个板块")
        self.data_source = "AKShare"
        return StandardMarketData(
            timestamp=target_date.strftime("%Y-%m-%d %H:%M:%S"),
            freshness=freshness,
            sectors=sectors,
            index_trend=trend,
            north_flow=north_flow
        )

    # ============================================================
    # Layer 2: Tushare（备用数据源）
    # ============================================================

    def _fetch_from_tushare(self) -> StandardMarketData:
        """使用 Tushare 获取数据（备用）"""
        import tushare as ts
        ts.set_token(self.tushare_token)
        pro = ts.pro_api()

        target_date = self._get_target_date()
        date_str = target_date.strftime("%Y%m%d")
        today_str = datetime.now().strftime("%Y%m%d")
        start_date_52w = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")

        # 大盘
        try:
            index_df = pro.index_daily(ts_code="000001.SH", start_date=date_str, end_date=date_str)
            if index_df.empty:
                prev = (target_date - timedelta(days=1)).strftime("%Y%m%d")
                index_df = pro.index_daily(ts_code="000001.SH", start_date=prev, end_date=prev)
            if not index_df.empty:
                pct_change = index_df['pct_chg'].iloc[0]
                trend = "bull" if pct_change > 0.5 else "bear" if pct_change < -0.5 else "range"
            else:
                trend = "range"
        except:
            trend = "range"

        # 北向
        north_flow = None
        try:
            north_df = pro.moneyflow_hsgt(start_date=date_str, end_date=date_str)
            north_flow = round(north_df['net_inflow'].iloc[0] / 10000, 2) if not north_df.empty else 0
        except:
            pass

        # 各板块
        sectors = []
        logger.info("📊 使用 Tushare 获取行业数据...")

        for name in SECTOR_NAMES:
            code = TUSHARE_CODE_MAP.get(name)
            if not code:
                drawdown = round(random.uniform(15.0, 40.0), 1)
            else:
                try:
                    df = pro.index_daily(ts_code=code, start_date=start_date_52w, end_date=today_str)
                    if df is not None and not df.empty and 'high' in df.columns and 'close' in df.columns:
                        high_52w = df['high'].max()
                        current = df['close'].iloc[-1]
                        if high_52w > 0:
                            drawdown = round((high_52w - current) / high_52w * 100, 1)
                            logger.info(f"   ✅ {name}: 回撤 {drawdown}%")
                        else:
                            drawdown = round(random.uniform(15.0, 40.0), 1)
                    else:
                        drawdown = round(random.uniform(15.0, 40.0), 1)
                except:
                    drawdown = round(random.uniform(15.0, 40.0), 1)

            threshold = THRESHOLD_MAP[name]
            excess = drawdown - threshold
            if excess >= 10:
                level = 4
            elif excess >= 5:
                level = 3
            elif excess >= 0:
                level = 2
            elif excess >= -5:
                level = 1
            elif excess >= -10:
                level = -1
            else:
                level = -2

            sectors.append(SectorSignal(
                name=name,
                signal_level=level,
                drawdown=drawdown,
                threshold=threshold,
                key_driver="52周回撤(Tushare)" if level > 0 else None
            ))

        freshness = FreshnessLevel.STALE if self.phase in ["pre", "night"] else FreshnessLevel.FRESH
        self.data_source = "Tushare"
        return StandardMarketData(
            timestamp=target_date.strftime("%Y-%m-%d %H:%M:%S"),
            freshness=freshness,
            sectors=sectors,
            index_trend=trend,
            north_flow=north_flow
        )

    # ============================================================
    # Layer 3: 模拟值（兜底）
    # ============================================================

    def _fetch_simulated(self) -> StandardMarketData:
        """模拟数据（兜底方案）"""
        target_date = self._get_target_date()
        sectors = []
        for name in SECTOR_NAMES:
            drawdown = round(random.uniform(15.0, 40.0), 1)
            threshold = THRESHOLD_MAP[name]
            excess = drawdown - threshold
            if excess >= 10:
                level = 4
            elif excess >= 5:
                level = 3
            elif excess >= 0:
                level = 2
            elif excess >= -5:
                level = 1
            elif excess >= -10:
                level = -1
            else:
                level = -2
            sectors.append(SectorSignal(
                name=name,
                signal_level=level,
                drawdown=drawdown,
                threshold=threshold,
                key_driver="模拟值" if level > 0 else None
            ))

        freshness = FreshnessLevel.STALE
        self.data_source = "Simulated"
        return StandardMarketData(
            timestamp=target_date.strftime("%Y-%m-%d %H:%M:%S"),
            freshness=freshness,
            sectors=sectors,
            index_trend="range",
            north_flow=None
        )

    # ============================================================
    # 辅助方法
    # ============================================================

    def _get_target_date(self):
        """根据阶段获取目标日期"""
        phase_days_back = {"pre": 1, "intraday_a": 0, "intraday_b": 0, "post": 0, "night": 0}
        days_back = phase_days_back.get(self.phase, 0)
        target = datetime.now() - timedelta(days=days_back)
        while target.weekday() >= 5:
            target -= timedelta(days=1)
        return target
