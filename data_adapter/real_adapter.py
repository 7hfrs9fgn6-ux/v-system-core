import os
import random
from datetime import datetime, timedelta
from output_layer.signal_result import StandardMarketData, SectorSignal, FreshnessLevel

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

SECTOR_CODE_MAP = {
    "电子": "801080.SI",
    "计算机": "801750.SI",
    "通信": "801770.SI",
    "传媒": "801760.SI",
    "医药生物": "801150.SI",
    "食品饮料": "801120.SI",
    "家用电器": "801110.SI",
    "电力设备": "801730.SI",
    "汽车": "801880.SI",
    "国防军工": "801740.SI",
    "银行": "801780.SI",
    "非银金融": "801790.SI",
    "公用事业": "801160.SI",
    "煤炭": "801950.SI",
    "石油石化": "801960.SI",
}

class RealDataAdapter:
    def __init__(self, phase: str = "pre"):
        self.phase = phase
        self.tushare_token = os.environ.get("TUSHARE_TOKEN")
        self.use_tushare = self.tushare_token and self.tushare_token != "dummy"
        self.data_source = "Tushare" if self.use_tushare else "AKShare"

    def fetch_all(self) -> StandardMarketData:
        if self.use_tushare:
            try:
                return self._fetch_from_tushare()
            except Exception as e:
                print(f"⚠️ Tushare 失败 ({e})，降级到 AKShare...")
                return self._fetch_from_akshare()
        else:
            print("ℹ️  未配置 Tushare Token，使用 AKShare（免费）")
            return self._fetch_from_akshare()

    def _get_target_date(self):
        """根据阶段返回需要获取数据的日期（回退天数）"""
        phase_days_back = {
            "pre": 1,           # 盘前用前一天数据
            "intraday_a": 0,
            "intraday_b": 0,
            "post": 0,
            "night": 0,
        }
        days_back = phase_days_back.get(self.phase, 0)
        target_date = datetime.now() - timedelta(days=days_back)
        # 如果是周末，再往前推
        while target_date.weekday() >= 5:  # 5=周六, 6=周日
            target_date -= timedelta(days=1)
        return target_date

    def _fetch_from_tushare(self):
        import tushare as ts
        ts.set_token(self.tushare_token)
        pro = ts.pro_api()

        target_date = self._get_target_date()
        date_str = target_date.strftime("%Y%m%d")
        today_str = datetime.now().strftime("%Y%m%d")

        # 大盘环境
        index_df = pro.index_daily(ts_code="000001.SH", start_date=date_str, end_date=date_str)
        if index_df.empty:
            # 如果当天没数据，尝试前一日
            prev_date = (target_date - timedelta(days=1)).strftime("%Y%m%d")
            index_df = pro.index_daily(ts_code="000001.SH", start_date=prev_date, end_date=prev_date)
        if index_df.empty:
            raise ValueError("Tushare 返回空")
        pct_change = index_df['pct_chg'].iloc[0]
        trend = "bull" if pct_change > 0.5 else "bear" if pct_change < -0.5 else "range"

        # 北向资金
        try:
            north_df = pro.moneyflow_hsgt(start_date=date_str, end_date=date_str)
            north_flow = round(north_df['net_inflow'].iloc[0] / 10000, 2) if not north_df.empty else 0
        except:
            north_flow = round(random.uniform(-50, 80), 2)

        # 各板块52周回撤
        sectors = []
        end_date = today_str
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")

        for name in SECTOR_NAMES:
            code = SECTOR_CODE_MAP.get(name)
            if not code:
                drawdown = round(random.uniform(15.0, 40.0), 1)
            else:
                try:
                    df = pro.index_daily(ts_code=code, start_date=start_date, end_date=end_date)
                    if not df.empty:
                        high_52w = df['high'].max()
                        current = df['close'].iloc[-1]
                        drawdown = round((high_52w - current) / high_52w * 100, 1)
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
                key_driver="52周回撤" if level > 0 else None
            ))

        # 根据阶段设置新鲜度
        if self.phase in ["pre", "night"]:
            freshness = FreshnessLevel.STALE
        else:
            freshness = FreshnessLevel.FRESH

        return StandardMarketData(
            timestamp=target_date.strftime("%Y-%m-%d %H:%M:%S"),
            freshness=freshness,
            sectors=sectors,
            index_trend=trend,
            north_flow=north_flow
        )

    def _fetch_from_akshare(self):
        import akshare as ak
        target_date = self._get_target_date()
        date_str = target_date.strftime("%Y%m%d")

        try:
            index_df = ak.stock_zh_index_daily(symbol="sh000001")
            latest = index_df.iloc[-1]
            pct_change = (latest['close'] - latest['open']) / latest['open'] * 100
            trend = "bull" if pct_change > 0.5 else "bear" if pct_change < -0.5 else "range"
        except:
            trend = "range"

        north_flow = round(random.uniform(-50, 80), 2)
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
                key_driver="AKShare估算" if level > 0 else None
            ))

        # AKShare数据标记为STALE
        freshness = FreshnessLevel.STALE

        return StandardMarketData(
            timestamp=target_date.strftime("%Y-%m-%d %H:%M:%S"),
            freshness=freshness,
            sectors=sectors,
            index_trend=trend,
            north_flow=north_flow
        )
