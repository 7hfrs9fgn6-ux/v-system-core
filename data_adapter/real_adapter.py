import os
import random
import logging
import time
import json
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
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

AK_CODE_MAP = {
    "电子": "801080", "计算机": "801750", "通信": "801770", "传媒": "801760", "医药生物": "801150",
    "食品饮料": "801120", "家用电器": "801110", "电力设备": "801730", "汽车": "801880", "国防军工": "801740",
    "银行": "801780", "非银金融": "801790", "公用事业": "801160", "煤炭": "801950", "石油石化": "801960",
}

CACHE_FILE = "memory_data/last_market_data.json"


def save_market_data(data: StandardMarketData):
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, 'w') as f:
            json.dump(data.dict(), f, default=str)
        logger.info(f"✅ 市场数据已缓存")
    except Exception as e:
        logger.warning(f"⚠️ 缓存失败: {e}")


def load_market_data() -> StandardMarketData:
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, 'r') as f:
            data_dict = json.load(f)
        sectors = [SectorSignal(**s) for s in data_dict['sectors']]
        return StandardMarketData(
            timestamp=data_dict['timestamp'],
            freshness=FreshnessLevel(data_dict['freshness']),
            sectors=sectors,
            index_trend=data_dict['index_trend'],
            north_flow=data_dict.get('north_flow')
        )
    except:
        return None


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
    def __init__(self, phase: str = "pre"):
        self.phase = phase
        self.tushare_token = os.environ.get("TUSHARE_TOKEN")
        self.use_tushare = bool(self.tushare_token and self.tushare_token != "dummy")
        self.data_source = "AKShare"
        self._rate_limiter = RateLimiter(max_calls=60, period=60)
        self._index_close = 0
        self._index_pct = 0

    def fetch_all(self) -> StandardMarketData:
        logger.info("🌐 开始获取数据...")

        # ✅ 只有 pre 阶段尝试网络请求
        if self.phase == "pre":
            return self._fetch_with_network()

        # ✅ 其他阶段（intraday_a/b, post, night）直接使用缓存
        cached = load_market_data()
        if cached is not None:
            logger.info(f"📂 {self.phase} 阶段使用缓存数据")
            self.data_source = "Cache"
            return cached

        # 如果缓存不存在，fallback 到网络请求
        logger.warning(f"⚠️ {self.phase} 阶段无缓存，尝试网络请求...")
        return self._fetch_with_network()

    def _fetch_with_network(self) -> StandardMarketData:
        """尝试网络请求，失败则使用缓存或模拟值"""
        try:
            logger.info("📊 尝试 AKShare 获取数据...")
            self.data_source = "AKShare"
            result = self._fetch_from_akshare()
            save_market_data(result)
            return result
        except Exception as e:
            logger.warning(f"⚠️ AKShare 失败: {e}")

        if self.use_tushare:
            try:
                logger.info("📊 降级到 Tushare...")
                self.data_source = "Tushare"
                result = self._fetch_from_tushare()
                save_market_data(result)
                return result
            except Exception as e:
                logger.warning(f"⚠️ Tushare 失败: {e}")

        # 所有网络请求失败，尝试加载缓存
        cached = load_market_data()
        if cached is not None:
            logger.warning("⚠️ 网络失败，使用缓存数据")
            self.data_source = "Cache"
            return cached

        logger.warning("⚠️ 无缓存，使用模拟值")
        self.data_source = "Simulated"
        return self._fetch_simulated()

    # --------------------------------------------------------------
    # 以下方法与稳定版相同
    # --------------------------------------------------------------
    def _get_target_date(self):
        phase_days_back = {"pre": 1, "intraday_a": 0, "intraday_b": 0, "post": 0, "night": 0}
        days_back = phase_days_back.get(self.phase, 0)
        target = datetime.now() - timedelta(days=days_back)
        while target.weekday() >= 5:
            target -= timedelta(days=1)
        return target

    def _make_fallback_sector(self, name: str) -> SectorSignal:
        threshold = THRESHOLD_MAP[name]
        drawdown = round(random.uniform(15.0, 40.0), 1)
        excess = drawdown - threshold
        if excess >= 10: level = 4
        elif excess >= 5: level = 3
        elif excess >= 0: level = 2
        elif excess >= -5: level = 1
        elif excess >= -10: level = -1
        else: level = -2
        return SectorSignal(name=name, signal_level=level, drawdown=drawdown, threshold=threshold, key_driver="兜底值" if level > 0 else None)

    def _find_column(self, df, candidates):
        if df is None or df.empty:
            return None
        for c in df.columns:
            for cand in candidates:
                if cand in c or c in cand:
                    return c
        return None

    def _fetch_from_akshare(self) -> StandardMarketData:
        import akshare as ak
        target_date = self._get_target_date()

        # 大盘
        try:
            index_df = ak.stock_zh_index_daily(symbol="sh000001")
            if index_df is not None and not index_df.empty:
                latest = index_df.iloc[-1]
                close_col = self._find_column(index_df, ['收', 'close'])
                if close_col:
                    current_close = latest[close_col]
                    if len(index_df) > 1:
                        prev_close = index_df.iloc[-2][close_col]
                        pct_change = (current_close - prev_close) / prev_close * 100
                    else:
                        pct_change = 0
                    trend = "bull" if pct_change > 0.5 else "bear" if pct_change < -0.5 else "range"
                    logger.info(f"📈 上证指数: {current_close:.2f} 涨跌幅: {pct_change:.2f}%, 环境: {trend}")
                    self._index_close = current_close
                    self._index_pct = pct_change
                else:
                    trend = "range"
                    self._index_close = 0
                    self._index_pct = 0
            else:
                trend = "range"
                self._index_close = 0
                self._index_pct = 0
        except Exception as e:
            logger.warning(f"大盘获取失败: {e}")
            trend = "range"
            self._index_close = 0
            self._index_pct = 0

        north_flow = None
        try:
            north_df = ak.stock_hsgt_north_net_flow_in(symbol="北上")
            if not north_df.empty:
                value_col = self._find_column(north_df, ['value', '净流入'])
                if value_col:
                    north_flow = round(float(north_df[value_col].iloc[-1]) / 10000, 2)
        except:
            pass

        sectors = []
        logger.info("📊 AKShare 获取各板块52周回撤...")
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_to_name = {executor.submit(self._fetch_single_sector, name): name for name in SECTOR_NAMES}
            for future in future_to_name:
                name = future_to_name[future]
                try:
                    result = future.result(timeout=10)
                    sectors.append(result)
                except FuturesTimeoutError:
                    logger.warning(f"⚠️ {name} 超时，使用随机值")
                    sectors.append(self._make_fallback_sector(name))
                except Exception as e:
                    logger.warning(f"⚠️ {name} 异常 ({e})，使用随机值")
                    sectors.append(self._make_fallback_sector(name))

        freshness = FreshnessLevel.STALE if self.phase in ["pre", "night"] else FreshnessLevel.FRESH
        logger.info(f"✅ AKShare 完成，共 {len(sectors)} 个板块")
        return StandardMarketData(
            timestamp=target_date.strftime("%Y-%m-%d %H:%M:%S"),
            freshness=freshness,
            sectors=sectors,
            index_trend=trend,
            north_flow=north_flow
        )

    def _fetch_single_sector(self, name: str) -> SectorSignal:
        import akshare as ak
        code = AK_CODE_MAP.get(name)
        if not code:
            return self._make_fallback_sector(name)
        if not self._rate_limiter.acquire():
            time.sleep(self._rate_limiter.wait())
        try:
            df = ak.index_hist_sw(symbol=code)
            if df is not None and not df.empty:
                high_col = self._find_column(df, ['高', 'high'])
                close_col = self._find_column(df, ['收', 'close'])
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
                logger.warning(f"⚠️ {name}: 无数据")
        except Exception as e:
            logger.warning(f"⚠️ {name}: 异常 ({e})，使用随机值")
            drawdown = round(random.uniform(15.0, 40.0), 1)

        threshold = THRESHOLD_MAP[name]
        excess = drawdown - threshold
        if excess >= 10: level = 4
        elif excess >= 5: level = 3
        elif excess >= 0: level = 2
        elif excess >= -5: level = 1
        elif excess >= -10: level = -1
        else: level = -2
        return SectorSignal(name=name, signal_level=level, drawdown=drawdown, threshold=threshold, key_driver="AKShare" if level > 0 else None)

    def _fetch_from_tushare(self) -> StandardMarketData:
        import tushare as ts
        ts.set_token(self.tushare_token)
        pro = ts.pro_api()
        target_date = self._get_target_date()
        date_str = target_date.strftime("%Y%m%d")
        try:
            index_df = pro.index_daily(ts_code="000001.SH", start_date=date_str, end_date=date_str)
            if index_df.empty:
                prev = (target_date - timedelta(days=1)).strftime("%Y%m%d")
                index_df = pro.index_daily(ts_code="000001.SH", start_date=prev, end_date=prev)
            if not index_df.empty:
                pct_change = index_df['pct_chg'].iloc[0]
                trend = "bull" if pct_change > 0.5 else "bear" if pct_change < -0.5 else "range"
                logger.info(f"📈 上证指数: {index_df['close'].iloc[-1]:.2f} 涨跌幅: {pct_change:.2f}%")
            else:
                trend = "range"
        except:
            trend = "range"

        north_flow = None
        try:
            north_df = pro.moneyflow_hsgt(start_date=date_str, end_date=date_str)
            north_flow = round(north_df['net_inflow'].iloc[0] / 10000, 2) if not north_df.empty else 0
        except:
            pass

        logger.info("📊 Tushare 备用模式，行业数据从 AKShare 获取...")
        return self._fetch_from_akshare()

    def _fetch_simulated(self) -> StandardMarketData:
        target_date = self._get_target_date()
        sectors = []
        for name in SECTOR_NAMES:
            drawdown = round(random.uniform(15.0, 40.0), 1)
            threshold = THRESHOLD_MAP[name]
            excess = drawdown - threshold
            if excess >= 10: level = 4
            elif excess >= 5: level = 3
            elif excess >= 0: level = 2
            elif excess >= -5: level = 1
            elif excess >= -10: level = -1
            else: level = -2
            sectors.append(SectorSignal(name=name, signal_level=level, drawdown=drawdown, threshold=threshold, key_driver="模拟值" if level > 0 else None))
        freshness = FreshnessLevel.STALE
        return StandardMarketData(timestamp=target_date.strftime("%Y-%m-%d %H:%M:%S"), freshness=freshness, sectors=sectors, index_trend="range", north_flow=None)
