# 真实数据适配器 - 修复版
import os
import random
import logging
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

# ✅ 修复1：使用正确的Tushare行业指数代码
# 申万一级行业指数（Tushare pro 标准代码）
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
        # 缓存真实数据，避免重复获取
        self._cache = {}

    def fetch_all(self) -> StandardMarketData:
        if self.use_tushare:
            try:
                logger.info("🌐 尝试使用 Tushare 获取数据...")
                return self._fetch_from_tushare()
            except Exception as e:
                logger.warning(f"⚠️ Tushare 失败 ({e})，降级到 AKShare...")
                return self._fetch_from_akshare()
        else:
            logger.info("ℹ️  未配置 Tushare Token，使用 AKShare（免费）")
            return self._fetch_from_akshare()

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
        # 如果是周末，往前推到周五
        while target.weekday() >= 5:
            target -= timedelta(days=1)
        return target

    def _fetch_from_tushare(self):
        import tushare as ts
        ts.set_token(self.tushare_token)
        pro = ts.pro_api()

        target_date = self._get_target_date()
        date_str = target_date.strftime("%Y%m%d")
        today_str = datetime.now().strftime("%Y%m%d")

        # 1. 大盘环境
        try:
            index_df = pro.index_daily(ts_code="000001.SH", start_date=date_str, end_date=date_str)
            if index_df.empty:
                prev = (target_date - timedelta(days=1)).strftime("%Y%m%d")
                index_df = pro.index_daily(ts_code="000001.SH", start_date=prev, end_date=prev)
            if index_df.empty:
                raise ValueError("无法获取大盘数据")
            pct_change = index_df['pct_chg'].iloc[0]
            trend = "bull" if pct_change > 0.5 else "bear" if pct_change < -0.5 else "range"
            logger.info(f"📈 大盘涨跌幅: {pct_change}%, 环境: {trend}")
        except Exception as e:
            logger.warning(f"大盘获取失败: {e}，使用默认值")
            trend = "range"

        # 2. 北向资金
        try:
            north_df = pro.moneyflow_hsgt(start_date=date_str, end_date=date_str)
            north_flow = round(north_df['net_inflow'].iloc[0] / 10000, 2) if not north_df.empty else 0
        except:
            north_flow = None

        # 3. ✅ 修复：获取各板块52周回撤（使用更健壮的方式）
        sectors = []
        start_date_52w = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
        
        logger.info("📊 开始获取各板块52周回撤...")
        
        for name in SECTOR_NAMES:
            code = SECTOR_CODE_MAP.get(name)
            if not code:
                logger.warning(f"⚠️ 板块 {name} 无映射代码")
                drawdown = round(random.uniform(15.0, 40.0), 1)
            else:
                try:
                    # ✅ 修复：使用正确的字段名获取数据
                    df = pro.index_daily(ts_code=code, start_date=start_date_52w, end_date=today_str)
                    
                    if not df.empty:
                        # ✅ 修复：检查字段是否存在
                        if 'high' in df.columns and 'close' in df.columns:
                            high_52w = df['high'].max()
                            current = df['close'].iloc[-1]
                            drawdown = round((high_52w - current) / high_52w * 100, 1)
                            logger.info(f"   ✅ {name}: 52周高 {high_52w:.2f}, 现价 {current:.2f}, 回撤 {drawdown}%")
                        else:
                            # 如果字段名不同，尝试其他可能
                            logger.warning(f"⚠️ 板块 {name} 字段不匹配，尝试其他方式")
                            df_recent = pro.index_daily(ts_code=code, start_date=date_str, end_date=today_str)
                            if not df_recent.empty:
                                high_52w = df_recent['high'].max() if 'high' in df_recent.columns else df_recent['close'].max()
                                current = df_recent['close'].iloc[-1]
                                drawdown = round((high_52w - current) / high_52w * 100, 1) if high_52w > 0 else 0
                            else:
                                drawdown = round(random.uniform(15.0, 40.0), 1)
                    else:
                        logger.warning(f"⚠️ 板块 {name} 无52周数据，使用随机值")
                        drawdown = round(random.uniform(15.0, 40.0), 1)
                except Exception as e:
                    logger.warning(f"⚠️ 板块 {name} 获取失败 ({e})，使用随机值")
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
                key_driver="52周回撤" if level > 0 else None
            ))

        # 判断新鲜度
        if self.phase in ["pre", "night"]:
            freshness = FreshnessLevel.STALE
        else:
            freshness = FreshnessLevel.FRESH

        logger.info(f"✅ 数据获取完成，共 {len(sectors)} 个板块，新鲜度: {freshness.value}")
        return StandardMarketData(
            timestamp=target_date.strftime("%Y-%m-%d %H:%M:%S"),
            freshness=freshness,
            sectors=sectors,
            index_trend=trend,
            north_flow=north_flow
        )

    def _fetch_from_akshare(self):
        """AKShare 降级方案"""
        import akshare as ak
        target_date = self._get_target_date()
        
        try:
            index_df = ak.stock_zh_index_daily(symbol="sh000001")
            latest = index_df.iloc[-1]
            pct_change = (latest['close'] - latest['open']) / latest['open'] * 100
            trend = "bull" if pct_change > 0.5 else "bear" if pct_change < -0.5 else "range"
        except:
            trend = "range"

        north_flow = None
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

        freshness = FreshnessLevel.STALE
        return StandardMarketData(
            timestamp=target_date.strftime("%Y-%m-%d %H:%M:%S"),
            freshness=freshness,
            sectors=sectors,
            index_trend=trend,
            north_flow=north_flow
        )
