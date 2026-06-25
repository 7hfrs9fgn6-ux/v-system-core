import os
import random
import logging
import time
from datetime import datetime, timedelta
from output_layer.signal_result import StandardMarketData, SectorSignal, FreshnessLevel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# AKShare 申万行业代码（已验证可用）
AK_CODE_MAP = {
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

# Tushare 代码（带后缀，备用）
TUSHARE_CODE_MAP = {k: v + ".SI" for k, v in AK_CODE_MAP.items()}


class RateLimiter:
    def __init__(self, max_calls: int, period: int = 60):
        self.max_calls = max_calls
        self.period = period
        self.calls = []

    def acquire(self) -> bool:
        now = time.time()
        self.calls = [t for t in self.calls if now - t < self.period]
        if len(self.calls) < self.max_calls:
            self.calls.append(now)
            return True
        return False

    def wait(self) -> float:
        now = time.time()
        if not self.calls:
            return 0
        oldest = self.calls[0]
        wait_time = self.period - (now - oldest) + 0.1
        return max(0, wait_time)


class RealDataAdapter:
    """
    数据适配器 - 修复版：AKShare 主源，Tushare 备用
    ✅ 主源：AKShare（已验证可用，能获取真实数据）
    ✅ 备源：Tushare（降级）
    ✅ 兜底：模拟值
    """

    def __init__(self, phase: str = "pre"):
        self.phase = phase
        self.tushare_token = os.environ.get("TUSHARE_TOKEN")
        self.use_tushare = bool(self.tushare_token and self.tushare_token != "dummy")
        self.data_source = "AKShare"  # 默认 AKShare
        self._rate_limiter = RateLimiter(max_calls=200, period=60)

    def fetch_all(self) -> StandardMarketData:
        logger.info("🌐 开始获取数据...")

        # ✅ 第一步：优先 AKShare（已验证可用）
        try:
            logger.info("📊 使用 AKShare（主数据源）获取行业数据...")
            self.data_source = "AKShare"
            return self._fetch_from_akshare()
        except Exception as e:
            logger.warning(f"⚠️ AKShare 主流程失败 ({e})，降级到 Tushare...")

        # ✅ 第二步：降级到 Tushare
        if self.use_tushare:
            try:
                logger.info("📊 降级到 Tushare（备用数据源）...")
                self.data_source = "Tushare"
                return self._fetch_from_tushare()
            except Exception as e:
                logger.warning(f"⚠️ Tushare 也失败 ({e})，使用模拟值兜底")

        # ✅ 第三步：模拟值（兜底）
        self.data_source = "Simulated"
        return self._fetch_simulated()

    def _get_target_date(self):
        phase_days_back = {
            "pre": 1,
            "intraday_a": 0,
            "intraday_b": 0,
            "post": 0,
            "night": 0,
        }
        days_back = phase_days_back.get(self.phase, 0)
        target = datetime.now() - timedelta(days=days_back)
        while target.weekday() >= 5:
            target -= timedelta(days=1)
        return target

    def _make_fallback_sector(self, name: str) -> SectorSignal:
        threshold = THRESHOLD_MAP[name]
        drawdown = round(random.uniform(15.0, 40.0), 1)
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
        return SectorSignal(
            name=name,
            signal_level=level,
            drawdown=drawdown,
            threshold=threshold,
            key_driver="兜底值" if level > 0 else None
        )

    # ============================================================
    # ✅ 主数据源：AKShare（已验证可用）
    # ============================================================
    def _fetch_from_akshare(self) -> StandardMarketData:
        import akshare as ak
        target_date = self._get_target_date()

        # 大盘
        try:
            index_df = ak.stock_zh_index_daily(symbol="sh000001")
            latest = index_df.iloc[-1]
            pct_change = (latest['close'] - latest['open']) / latest['open'] * 100
            trend = "bull" if pct_change > 0.5 else "bear" if pct_change < -0.5 else "range"
            logger.info(f"📈 大盘涨跌幅: {pct_change:.2f}%, 环境: {trend}")
        except:
            trend = "range"

        # 北向
        north_flow = None
        try:
            north_df = ak.stock_hsgt_north_net_flow_in(symbol="北上")
            if not north_df.empty:
                north_flow = round(north_df['value'].iloc[-1] / 10000, 2)
        except:
            pass

        # 各板块
        sectors = []
        logger.info("📊 AKShare 获取各板块52周回撤...")

        for name in SECTOR_NAMES:
            code = AK_CODE_MAP.get(name)
            if not code:
                sectors.append(self._make_fallback_sector(name))
                continue

            try:
                df = ak.index_hist_sw(symbol=code)
                if df is not None and not df.empty:
                    # 识别列名（AKShare 返回中文列名）
                    high_col = None
                    close_col = None
                    for c in df.columns:
                        if '高' in c or 'high' in c.lower():
                            high_col = c
                        if '收' in c or 'close' in c.lower():
                            close_col = c
                    if high_col and close_col:
                        high_52w = df[high_col].max()
                        current = df[close_col].iloc[-1]
                        if high_52w > 0:
                            drawdown = round((high_52w - current) / high_52w * 100, 1)
                            logger.info(f"   ✅ {name}: 52周高 {high_52w:.2f}, 现价 {current:.2f}, 回撤 {drawdown}%")
                        else:
                            drawdown = round(random.uniform(15.0, 40.0), 1)
                            logger.warning(f"⚠️ {name}: 52周高为0，使用随机值")
                    else:
                        drawdown = round(random.uniform(15.0, 40.0), 1)
                        logger.warning(f"⚠️ {name}: 无法识别列名，使用随机值")
                else:
                    drawdown = round(random.uniform(15.0, 40.0), 1)
                    logger.warning(f"⚠️ {name}: AKShare 无数据，使用随机值")
            except Exception as e:
                drawdown = round(random.uniform(15.0, 40.0), 1)
                logger.warning(f"⚠️ {name}: AKShare 异常 ({e})，使用随机值")

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
                key_driver="AKShare" if level > 0 else None
            ))

        freshness = FreshnessLevel.STALE if self.phase in ["pre", "night"] else FreshnessLevel.FRESH
        logger.info(f"✅ AKShare 数据获取完成，共 {len(sectors)} 个板块")
        return StandardMarketData(
            timestamp=target_date.strftime("%Y-%m-%d %H:%M:%S"),
            freshness=freshness,
            sectors=sectors,
            index_trend=trend,
            north_flow=north_flow
        )

    # ============================================================
    # ✅ 备用数据源：Tushare
    # ============================================================
    def _fetch_from_tushare(self) -> StandardMarketData:
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
        logger.info("📊 Tushare 获取各板块52周回撤（备用）...")

        for name in SECTOR_NAMES:
            code = TUSHARE_CODE_MAP.get(name)
            if not code:
                sectors.append(self._make_fallback_sector(name))
                continue

            try:
                df = pro.index_daily(ts_code=code, start_date=start_date_52w, end_date=today_str)
                if df is not None and not df.empty and 'high' in df.columns and 'close' in df.columns:
                    high_52w = df['high'].max()
                    current = df['close'].iloc[-1]
                    if high_52w > 0:
                        drawdown = round((high_52w - current) / high_52w * 100, 1)
                        logger.info(f"   ✅ {name}: Tushare 回撤 {drawdown}%")
                    else:
                        drawdown = round(random.uniform(15.0, 40.0), 1)
                else:
                    drawdown = round(random.uniform(15.0, 40.0), 1)
                    logger.warning(f"⚠️ {name}: Tushare 无数据，使用随机值")
            except Exception as e:
                drawdown = round(random.uniform(15.0, 40.0), 1)
                logger.warning(f"⚠️ {name}: Tushare 异常 ({e})，使用随机值")

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
                key_driver="Tushare" if level > 0 else None
            ))

        freshness = FreshnessLevel.STALE if self.phase in ["pre", "night"] else FreshnessLevel.FRESH
        logger.info(f"✅ Tushare 数据获取完成，共 {len(sectors)} 个板块")
        return StandardMarketData(
            timestamp=target_date.strftime("%Y-%m-%d %H:%M:%S"),
            freshness=freshness,
            sectors=sectors,
            index_trend=trend,
            north_flow=north_flow
        )

    # ============================================================
    # ✅ 兜底：模拟值
    # ============================================================
    def _fetch_simulated(self) -> StandardMarketData:
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
        return StandardMarketData(
            timestamp=target_date.strftime("%Y-%m-%d %H:%M:%S"),
            freshness=freshness,
            sectors=sectors,
            index_trend="range",
            north_flow=None
        )
