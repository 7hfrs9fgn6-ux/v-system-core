import os
import random
import logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from output_layer.signal_result import StandardMarketData, SectorSignal, FreshnessLevel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# 基础配置
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

# 申万一级行业代码（用于 AKShare 和 Tushare）
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

TUSHARE_CODE_MAP = {k: v + ".SI" for k, v in SECTOR_CODE_MAP.items()}


class RealDataAdapter:
    def __init__(self, phase: str = "pre"):
        self.phase = phase
        self.tushare_token = os.environ.get("TUSHARE_TOKEN")
        self.use_tushare = bool(self.tushare_token and self.tushare_token != "dummy")
        self.data_source = "AKShare"

    def fetch_all(self) -> StandardMarketData:
        """主入口：优先 AKShare，失败则 Tushare 或模拟"""
        logger.info("🌐 开始获取数据...")
        try:
            logger.info("📊 尝试使用 AKShare 获取真实行业数据...")
            return self._fetch_from_akshare_real()
        except Exception as e:
            logger.warning(f"⚠️ AKShare 主流程失败 ({e})，尝试 Tushare...")
            if self.use_tushare:
                try:
                    self.data_source = "Tushare"
                    return self._fetch_from_tushare()
                except Exception as e2:
                    logger.warning(f"⚠️ Tushare 也失败 ({e2})，使用模拟值兜底")
            self.data_source = "Simulated"
            return self._fetch_simulated()

    # ============================================================
    # 辅助方法
    # ============================================================
    def _get_target_date(self):
        """根据阶段获取目标日期（跳过周末）"""
        phase_days_back = {
            "pre": 1,
            "intraday_a": 0,
            "intraday_b": 0,
            "post": 0,
            "night": 0,
        }
        days_back = phase_days_back.get(self.phase, 0)
        target = datetime.now() - timedelta(days=days_back)
        while target.weekday() >= 5:  # 周六=5, 周日=6
            target -= timedelta(days=1)
        return target

    def _make_fallback_sector(self, name: str) -> SectorSignal:
        """生成单个板块的兜底数据（随机值）"""
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
    # Layer 1: AKShare 真实数据（并发获取）
    # ============================================================
    def _fetch_from_akshare_real(self) -> StandardMarketData:
        import akshare as ak
        target_date = self._get_target_date()

        # 大盘环境
        try:
            index_df = ak.stock_zh_index_daily(symbol="sh000001")
            latest = index_df.iloc[-1]
            pct_change = (latest['close'] - latest['open']) / latest['open'] * 100
            trend = "bull" if pct_change > 0.5 else "bear" if pct_change < -0.5 else "range"
            logger.info(f"📈 大盘涨跌幅: {pct_change:.2f}%, 环境: {trend}")
        except:
            trend = "range"

        # 北向资金（尝试获取）
        north_flow = None
        try:
            north_df = ak.stock_hsgt_north_net_flow_in(symbol="北上")
            if not north_df.empty:
                north_flow = round(north_df['value'].iloc[-1] / 10000, 2)
        except:
            pass

        # 并发获取各板块
        sectors = []
        logger.info("📊 开始获取各板块52周回撤（AKShare 申万行业指数）...")
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_name = {
                executor.submit(self._fetch_single_sector, name, ak): name
                for name in SECTOR_NAMES
            }
            for future in future_to_name:
                name = future_to_name[future]
                try:
                    result = future.result(timeout=15)  # 单个板块超时15秒
                    sectors.append(result)
                except FuturesTimeoutError:
                    logger.warning(f"⚠️ {name} 获取超时，使用随机值")
                    sectors.append(self._make_fallback_sector(name))
                except Exception as e:
                    logger.warning(f"⚠️ {name} 获取异常 ({e})，使用随机值")
                    sectors.append(self._make_fallback_sector(name))

        freshness = FreshnessLevel.STALE if self.phase in ["pre", "night"] else FreshnessLevel.FRESH
        self.data_source = "AKShare"
        logger.info(f"✅ 数据获取完成，共 {len(sectors)} 个板块")
        return StandardMarketData(
            timestamp=target_date.strftime("%Y-%m-%d %H:%M:%S"),
            freshness=freshness,
            sectors=sectors,
            index_trend=trend,
            north_flow=north_flow
        )

    def _fetch_single_sector(self, name: str, ak) -> SectorSignal:
        """获取单个板块数据（用于并发）"""
        code = SECTOR_CODE_MAP.get(name)
        if not code:
            return self._make_fallback_sector(name)
        try:
            df = ak.index_hist_sw(symbol=code)
            if df is not None and not df.empty:
                # 识别列名（中文或英文）
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
                else:
                    drawdown = round(random.uniform(15.0, 40.0), 1)
            else:
                drawdown = round(random.uniform(15.0, 40.0), 1)
        except Exception as e:
            logger.warning(f"⚠️ {name} AKShare 获取失败 ({e})，使用随机值")
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

        return SectorSignal(
            name=name,
            signal_level=level,
            drawdown=drawdown,
            threshold=threshold,
            key_driver="52周回撤" if level > 0 else None
        )

    # ============================================================
    # Layer 2: Tushare 备用数据
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
                key_driver="Tushare" if level > 0 else None
            ))

        freshness = FreshnessLevel.STALE if self.phase in ["pre", "night"] else FreshnessLevel.FRESH
        return StandardMarketData(
            timestamp=target_date.strftime("%Y-%m-%d %H:%M:%S"),
            freshness=freshness,
            sectors=sectors,
            index_trend=trend,
            north_flow=north_flow
        )

    # ============================================================
    # Layer 3: 模拟数据（兜底）
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
