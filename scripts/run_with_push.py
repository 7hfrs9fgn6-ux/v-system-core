#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V系统完整闭环执行脚本
支持五阶段：pre / intraday_a / intraday_b / post / night
"""

import sys
import os
import argparse
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
from data_adapter.real_adapter import RealDataAdapter
from data_adapter.alphafeed_adapter import AlphaFeedAdapter
from data_adapter.mock_adapter import MockDataAdapter
from data_adapter.market_data import MarketDataCollector
from core.state_machine import VSystemStateMachine
from core.sentiment_engine import SentimentEngine
from core.shadow_system import ShadowSystem
from core.memory_store import MemoryStore
from core.relative_strength import RelativeStrengthEngine
from output_layer.push_notifier import PushNotifier


def load_config(config_path="config.yaml"):
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase',
                        choices=['pre', 'intraday_a', 'intraday_b', 'post', 'night'],
                        default='post')
    parser.add_argument('--mock', action='store_true')
    args = parser.parse_args()

    config = load_config()
    phase_names = {
        "pre": "盘前预测",
        "intraday_a": "盘中A",
        "intraday_b": "盘中B",
        "post": "盘后复盘",
        "night": "夜间预测"
    }

    print("=" * 50)
    print(f"🚀 V系统完整闭环启动 ({phase_names.get(args.phase, args.phase)})")
    print("=" * 50)

    # ---------- 1. 数据获取 ----------
    print("\n📊 步骤1：获取数据...")
    phase_config = config.get('phases', {}).get(args.phase, {})
    use_alphafeed = phase_config.get('use_alphafeed', False)

    if args.mock:
        print("   使用模拟数据（测试模式）")
        adapter = MockDataAdapter()
        market_data = adapter.fetch_all()
    elif use_alphafeed:
        print("   使用 AlphaFeed 盘中实时数据...")
        adapter = AlphaFeedAdapter(phase=args.phase)
        market_data = adapter.fetch_all()
        if market_data is None:
            print("   ⚠️ AlphaFeed 失败，降级到 AKShare...")
            adapter = RealDataAdapter(phase=args.phase)
            market_data = adapter.fetch_all()
    else:
        print("   使用 AKShare/Tushare 数据...")
        adapter = RealDataAdapter(phase=args.phase)
        market_data = adapter.fetch_all()

    print(f"   ✅ 数据源: {getattr(adapter, 'data_source', 'Unknown')}")
    print(f"   ✅ 板块数: {len(market_data.sectors)}")
    print(f"   🟢 新鲜度: {market_data.freshness.value}")

    # 将大盘数据附加到 market_data
    if hasattr(adapter, '_index_close') and hasattr(adapter, '_index_pct'):
        market_data._index_data = {
            'close': adapter._index_close,
            'pct': adapter._index_pct
        }

    # ---------- 2. 核心逻辑 ----------
    print("\n🧠 步骤2：核心逻辑分析...")
    sm = VSystemStateMachine(phase=args.phase)
    result = sm.run(market_data)
    print(f"   ✅ 分析完成，信任度: {result.trust_score:.2f}, 判断: {result.judge_status}")

    if hasattr(market_data, '_index_data'):
        result._index_data = market_data._index_data

# ---------- 2.5 宏观数据采集 ----------
print("\n🌐 步骤2.5：宏观数据采集...")
try:
    from core.macro_collector import MacroCollector
    macro = MacroCollector()
    # ✅ 移除 force_refresh 参数
    macro_data = macro.format_for_push()
    result._macro_data = macro_data
    us_count = len(macro_data.get('us_market', {}).get('indices', []))
    asia_count = len(macro_data.get('asia_market', {}).get('indices', []))
    print(f"   ✅ 宏观数据: 美股{us_count}个指数, 亚太{asia_count}个指数")
except Exception as e:
    print(f"   ⚠️ 宏观数据获取失败: {e}")
    result._macro_data = {}

# ---------- 2.6 市场数据采集 ----------
print("\n📈 步骤2.6：市场数据采集...")
try:
    from data_adapter.market_data import MarketDataCollector
    market = MarketDataCollector(storage_dir="memory_data/")
    # ✅ 移除所有 force_refresh 参数
    indices_data = market.get_indices()
    stats_data = market.get_market_stats()
    flow_data = market.get_sector_flow()
    result._indices = indices_data
    result._market_stats = stats_data
    result._sector_flow = flow_data
    print(f"   ✅ 获取到 {len(indices_data.get('indices', {}))} 个指数数据")
    print(f"   📊 涨跌: {stats_data.get('up',0)}涨 / {stats_data.get('down',0)}跌")
    print(f"   💰 流入TOP5: {len(flow_data.get('net_inflow_top5', []))}个板块")
except Exception as e:
    print(f"   ⚠️ 市场数据采集失败: {e}")
    result._indices = {}
    result._market_stats = {}
    result._sector_flow = {}

    # ---------- 3. 烈度评分 ----------
    print("\n📰 步骤3：消息面烈度评分...")
    sentiment_config = config.get('sentiment', {})
    if sentiment_config.get('enabled', False):
        sent_engine = SentimentEngine()
        sector_names = [s.name for s in result.signals]
        sentiment_results = sent_engine.batch_analyze(sector_names)
        result.sentiment = sentiment_results
        sources = set()
        for s in sentiment_results.values():
            if '数据源' in s:
                sources.add(s['数据源'])
        print(f"   ✅ 烈度评分完成，覆盖 {len(sentiment_results)} 个板块")
        print(f"   📌 数据源: {', '.join(sources) if sources else '未知'}")
    else:
        result.sentiment = {}
        print("   ⏭️ 烈度评分未启用")

    # ---------- 4. 影子系统 ----------
    print("\n👻 步骤4：影子系统运行...")
    shadow_config = config.get('shadow', {})
    if shadow_config.get('enabled', False):
        shadow_sys = ShadowSystem(config)
        shadow_result = shadow_sys.run_variants({}, result.signals)
        result.shadow = shadow_result
        reliability = shadow_result.get('reliability', {})
        print(f"   ✅ 影子系统完成，可靠度: {reliability.get('overall_reliability', 0):.2%}")
        print(f"   📌 建议: {reliability.get('recommendation', '')}")
    else:
        result.shadow = {}
        print("   ⏭️ 影子系统未启用")

    # ---------- 5. 相对强度 ----------
    print("\n📊 步骤5：相对强度计算...")
    rs_config = config.get('relative_strength', {})
    if rs_config.get('enabled', False):
        rs_engine = RelativeStrengthEngine(config)
        rs_results = {}
        for s in result.signals:
            rs_results[s.name] = rs_engine.calculate(s.name)
        result.relative_strength = rs_results
        print(f"   ✅ 相对强度计算完成，覆盖 {len(rs_results)} 个板块")
    else:
        result.relative_strength = {}
        print("   ⏭️ 相对强度未启用")

    # ---------- 6. 记忆体 ----------
    print("\n💾 步骤6：记忆体存储...")
    memory_config = config.get('memory', {})
    if memory_config.get('enabled', False):
        memory = MemoryStore(config)
        memory.save_signal_record(result, args.phase)
        if hasattr(result, 'shadow') and result.shadow:
            memory.save_shadow_record(result.shadow, args.phase)
        memory.save_trust_record(result.trust_score, result.judge_status, args.phase)
        print("   ✅ 记忆体存储完成")
    else:
        print("   ⏭️ 记忆体未启用")

    # ---------- 7. 智能代理分析 ----------
    print("\n🧠 步骤7：智能代理分析...")
    agent_config = config.get('agent', {})
    if agent_config.get('enabled', False):
        try:
            from core.ds_agent import DSAgent
            from core.bridge import Bridge

            agent = DSAgent()
            if agent.enabled:
                agent_result = agent.get_daily_summary()
                result.agent_analysis = agent_result
                print(f"   ✅ 智能代理分析完成，工具调用: {agent_result.get('tool_calls_made', 0)} 次")

                stats = Bridge.get_stats()
                print(f"   🔧 Bridge 统计: 成功率 {stats.get('success_rate', 0)}%")
            else:
                print("   ⏭️ Agent 未启用（API Key 未配置）")
        except Exception as e:
            print(f"   ⚠️ Agent 分析失败: {e}")
    else:
        print("   ⏭️ Agent 未配置（请在 config.yaml 中设置 agent.enabled: true）")

    # ---------- 8. 推送 ----------
    print("\n📲 步骤8：推送结果并存储...")
    notifier = PushNotifier()
    notifier.send(result, args.phase)

    print("\n" + "=" * 50)
    print("✅ 闭环执行完成！")
    print("=" * 50)


if __name__ == "__main__":
    main()
