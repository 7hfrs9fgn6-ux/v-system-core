#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场数据采集模块（增量历史版）
- 永久保存历史数据到 CSV（每日追加一行）
- JSON 缓存用于快速读取最新数据
- 每日首次运行获取并追加，后续直接读取
"""

import os
import json
import pandas as pd
import logging
from datetime import datetime
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


class MarketDataCollector:
    def __init__(self, storage_dir: str = "memory_data/"):
        self.storage_dir = storage_dir
        self._ensure_storage_dir()
        self.today = datetime.now().strftime("%Y-%m-%d")
        logger.info(f"📁 市场数据缓存目录: {os.path.abspath(self.storage_dir)}")

    def _ensure_storage_dir(self):
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir, exist_ok=True)

    # ---------- 文件操作辅助 ----------
    def _get_file_path(self, filename: str) -> str:
        return os.path.join(self.storage_dir, filename)

    def _load_json(self, filename: str) -> Optional[Dict]:
        file_path = self._get_file_path(filename)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return None
        return None

    def _save_json(self, filename: str, data: Dict) -> str:
        file_path = self._get_file_path(filename)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return file_path

    def _load_csv(self, filename: str) -> pd.DataFrame:
        file_path = self._get_file_path(filename)
        if os.path.exists(file_path):
            try:
                return pd.read_csv(file_path)
            except:
                return pd.DataFrame()
        return pd.DataFrame()

    def _save_csv(self, filename: str, df: pd.DataFrame):
        file_path = self._get_file_path(filename)
        df.to_csv(file_path, index=False)
        logger.debug(f"✅ 保存 {filename}: {len(df)} 条记录")

    def _is_today_recorded(self, df: pd.DataFrame, date_col: str = "date") -> bool:
        if df.empty or date_col not in df.columns:
            return False
        return self.today in df[date_col].values

    # ---------- 数据获取辅助 ----------
    def _safe_float(self, value) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _find_column(self, df, candidates):
        if df is None or df.empty:
            return None
        for c in df.columns:
            for cand in candidates:
                if cand in c or c in cand:
                    return c
        return None

    # ============================================================
    # 1. 指数数据（增量历史）
    # ============================================================
    def get_indices(self) -> Dict:
        """
        获取指数数据（用于推送展示），返回今日最新数据
        同时将今日数据追加到历史 CSV
        """
        # 检查历史是否已有今日记录
        history_df = self._load_csv("market_indices_history.csv")
        if not self._is_today_recorded(history_df):
            # 获取今日数据
            logger.info("📊 获取今日指数数据...")
            result = self._fetch_indices_impl()
            if result.get('indices'):
                # 追加到历史
                self._append_indices_history(result)
                # 保存最新快照到 JSON（用于快速读取）
                self._save_json("market_indices.json", result)
                return result
        else:
            # 从 JSON 读取最新数据
            cached = self._load_json("market_indices.json")
            if cached:
                logger.info("✅ 从缓存读取指数数据（今日已记录）")
                return cached
        # 降级：从历史读取最新一条
        return self._get_latest_indices_from_history()

    def _fetch_indices_impl(self) -> Dict:
        """实际获取指数数据"""
        result = {"indices": {}, "timestamp": datetime.now().isoformat()}
        try:
            import akshare as ak
            df = None
            for func in [ak.index_zh_spot, ak.stock_zh_index_spot]:
                try:
                    df = func()
                    if df is not None and not df.empty:
                        break
                except:
                    continue
            if df is None or df.empty:
                logger.warning("指数数据获取失败")
                return result
            name_col = self._find_column(df, ['名称', 'name', 'Name'])
            code_col = self._find_column(df, ['代码', 'code'])
            price_col = self._find_column(df, ['最新价', 'price', 'close'])
            pct_col = self._find_column(df, ['涨跌幅', 'change', 'pct_change'])
            amount_col = self._find_column(df, ['成交额', 'amount'])
            if not name_col or not price_col:
                logger.warning("指数列名识别失败")
                return result
            index_map = {
                "上证指数": ["000001.SH", "上证指数"],
                "深证成指": ["399001.SZ", "深证成指"],
                "创业板指": ["399006.SZ", "创业板指"],
                "科创50": ["000688.SH", "科创50"],
                "北证50": ["899050.BJ", "北证50"]
            }
            for name, (code, keyword) in index_map.items():
                matched = df[df[code_col] == code] if code_col in df.columns else pd.DataFrame()
                if matched.empty:
                    matched = df[df[name_col].str.contains(keyword, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    result["indices"][name] = {
                        "code": code,
                        "price": self._safe_float(row.get(price_col)),
                        "pct_change": self._safe_float(row.get(pct_col)) if pct_col else None,
                        "amount": self._safe_float(row.get(amount_col)) if amount_col else None,
                        "date": self.today
                    }
            logger.info(f"✅ 获取到 {len(result['indices'])} 个指数数据")
            return result
        except Exception as e:
            logger.warning(f"指数获取异常: {e}")
            return result

    def _append_indices_history(self, data: Dict):
        """将今日指数数据追加到历史 CSV"""
        filename = "market_indices_history.csv"
        df = self._load_csv(filename)
        if self._is_today_recorded(df):
            return
        indices = data.get('indices', {})
        if not indices:
            return
        new_records = []
        today = self.today
        for name, idx in indices.items():
            new_records.append({
                "date": today,
                "index_name": name,
                "price": idx.get("price"),
                "pct_change": idx.get("pct_change"),
                "amount": idx.get("amount")
            })
        new_df = pd.DataFrame(new_records)
        df = pd.concat([df, new_df], ignore_index=True)
        self._save_csv(filename, df)
        logger.info(f"✅ 追加指数历史: {len(new_records)} 条")

    def _get_latest_indices_from_history(self) -> Dict:
        """从历史读取最新一条记录（用于降级）"""
        filename = "market_indices_history.csv"
        df = self._load_csv(filename)
        if df.empty:
            return {"indices": {}, "timestamp": datetime.now().isoformat()}
        # 取最新日期
        latest_date = df['date'].max()
        latest_df = df[df['date'] == latest_date]
        result = {"indices": {}, "timestamp": datetime.now().isoformat()}
        for _, row in latest_df.iterrows():
            name = row['index_name']
            result["indices"][name] = {
                "price": row['price'],
                "pct_change": row['pct_change'],
                "amount": row['amount'],
                "date": row['date']
            }
        return result

    # ============================================================
    # 2. 涨跌家数（增量历史）
    # ============================================================
    def get_market_stats(self) -> Dict:
        """获取涨跌家数，增量追加到历史"""
        history_df = self._load_csv("market_stats_history.csv")
        if not self._is_today_recorded(history_df):
            logger.info("📊 获取今日涨跌家数...")
            result = self._fetch_stats_impl()
            if result.get('total', 0) > 0:
                self._append_stats_history(result)
                self._save_json("market_stats.json", result)
                return result
        else:
            cached = self._load_json("market_stats.json")
            if cached:
                logger.info("✅ 从缓存读取涨跌家数（今日已记录）")
                return cached
        return self._get_latest_stats_from_history()

    def _fetch_stats_impl(self) -> Dict:
        result = {"up": 0, "down": 0, "flat": 0, "total": 0, "timestamp": datetime.now().isoformat()}
        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                pct_col = self._find_column(df, ['涨跌幅', 'change'])
                if pct_col:
                    up = (df[pct_col] > 0).sum()
                    down = (df[pct_col] < 0).sum()
                    flat = (df[pct_col] == 0).sum()
                    result["up"] = int(up)
                    result["down"] = int(down)
                    result["flat"] = int(flat)
                    result["total"] = int(up + down + flat)
                    logger.info(f"✅ 涨跌家数: 上涨{up}家, 下跌{down}家")
                    return result
        except Exception as e:
            logger.warning(f"涨跌家数获取失败: {e}")
        return result

    def _append_stats_history(self, data: Dict):
        filename = "market_stats_history.csv"
        df = self._load_csv(filename)
        if self._is_today_recorded(df):
            return
        new_record = {
            "date": self.today,
            "up": data.get("up", 0),
            "down": data.get("down", 0),
            "flat": data.get("flat", 0),
            "total": data.get("total", 0)
        }
        new_df = pd.DataFrame([new_record])
        df = pd.concat([df, new_df], ignore_index=True)
        self._save_csv(filename, df)
        logger.info("✅ 追加涨跌家数历史")

    def _get_latest_stats_from_history(self) -> Dict:
        filename = "market_stats_history.csv"
        df = self._load_csv(filename)
        if df.empty:
            return {"up": 0, "down": 0, "flat": 0, "total": 0, "timestamp": datetime.now().isoformat()}
        latest_df = df[df['date'] == df['date'].max()]
        row = latest_df.iloc[0]
        return {
            "up": row['up'],
            "down": row['down'],
            "flat": row['flat'],
            "total": row['total'],
            "timestamp": datetime.now().isoformat()
        }

    # ============================================================
    # 3. 板块资金流向（增量历史，但可复用）
    # ============================================================
    def get_sector_flow(self) -> Dict:
        """获取板块资金流向TOP5，增量历史存储（存储为JSON或CSV均可）"""
        history_df = self._load_csv("sector_flow_history.csv")
        if not self._is_today_recorded(history_df):
            logger.info("📊 获取今日板块资金流向...")
            result = self._fetch_flow_impl()
            if result.get('net_inflow_top5') or result.get('net_outflow_top5'):
                self._append_flow_history(result)
                self._save_json("sector_flow.json", result)
                return result
        else:
            cached = self._load_json("sector_flow.json")
            if cached:
                logger.info("✅ 从缓存读取板块资金流向（今日已记录）")
                return cached
        return self._get_latest_flow_from_history()

    def _fetch_flow_impl(self) -> Dict:
        result = {"net_inflow_top5": [], "net_outflow_top5": [], "timestamp": datetime.now().isoformat()}
        try:
            import akshare as ak
            df = ak.stock_sector_spot()
            if df is not None and not df.empty:
                inflow_col = self._find_column(df, ['主力净流入', 'main_net_inflow'])
                if inflow_col:
                    df_sorted = df.sort_values(by=inflow_col, ascending=False)
                    for _, row in df_sorted.head(5).iterrows():
                        result["net_inflow_top5"].append({
                            "sector": row.get('名称', ''),
                            "flow": self._safe_float(row.get(inflow_col))
                        })
                    for _, row in df_sorted.tail(5).iterrows():
                        result["net_outflow_top5"].append({
                            "sector": row.get('名称', ''),
                            "flow": self._safe_float(row.get(inflow_col))
                        })
                    logger.info("✅ 板块资金流向获取成功")
                    return result
        except Exception as e:
            logger.warning(f"板块资金流向获取失败: {e}")
        return result

    def _append_flow_history(self, data: Dict):
        filename = "sector_flow_history.csv"
        df = self._load_csv(filename)
        if self._is_today_recorded(df):
            return
        # 由于数据是列表，存储为JSON字符串
        new_record = {
            "date": self.today,
            "net_inflow_top5": json.dumps(data.get("net_inflow_top5", [])),
            "net_outflow_top5": json.dumps(data.get("net_outflow_top5", []))
        }
        new_df = pd.DataFrame([new_record])
        df = pd.concat([df, new_df], ignore_index=True)
        self._save_csv(filename, df)
        logger.info("✅ 追加板块资金流向历史")

    def _get_latest_flow_from_history(self) -> Dict:
        filename = "sector_flow_history.csv"
        df = self._load_csv(filename)
        if df.empty:
            return {"net_inflow_top5": [], "net_outflow_top5": [], "timestamp": datetime.now().isoformat()}
        latest_df = df[df['date'] == df['date'].max()]
        row = latest_df.iloc[0]
        return {
            "net_inflow_top5": json.loads(row['net_inflow_top5']) if row['net_inflow_top5'] else [],
            "net_outflow_top5": json.loads(row['net_outflow_top5']) if row['net_outflow_top5'] else [],
            "timestamp": datetime.now().isoformat()
        }

    # ============================================================
    # 市场数据历史快速查询（供外部使用）
    # ============================================================
    def get_market_history(self, days: int = 30) -> pd.DataFrame:
        """获取市场历史数据（合并指数、涨跌、资金等）"""
        # 简化：返回指数历史
        return self._load_csv("market_indices_history.csv")
