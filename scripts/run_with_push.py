#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V系统完整闭环执行脚本
修复：Agent分析在推送之前完成，只推送一次
"""

import sys
import os
import argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
from data_adapter.real_adapter import RealDataAdapter
from data_adapter.alphafeed_adapter import AlphaFeedAdapter
from data_adapter.mock_adapter import MockDataAdapter
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

 # ---------- 2. 核心逻辑 ----------
    print("\n🧠 步骤2：核心逻辑分析...")
    sm = VSystemStateMachine(phase=args.phase)
    result = sm.run(market_data)
    print(f"   ✅ 分析完成，信任度: {result.trust_score:.2f}, 判断: {result.judge_status}")
    
    # 将大盘数据附加到 result
    if hasattr(adapter, '_index_close') and hasattr(adapter, '_index_pct'):
        result._index_data = {
            'close': adapter._index_close,
            'pct': adapter._index_pct
        }
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

    # ---------- 7. ✅ 智能代理分析（移到推送之前） ----------
    print("\n🧠 步骤7：智能代理分析...")
    agent_config = config.get('agent', {})
    if agent_config.get('enabled', False):
        try:
            from core.ds_agent import DSAgent
            from core.bridge import Bridge

            agent = DSAgent()
            if agent.enabled:
                # 生成每日摘要
                agent_result = agent.get_daily_summary()
                result.agent_analysis = agent_result
                print(f"   ✅ 智能代理分析完成，工具调用: {agent_result.get('tool_calls_made', 0)} 次")

                # 打印 Bridge 统计
                stats = Bridge.get_stats()
                print(f"   🔧 Bridge 统计: 成功率 {stats.get('success_rate', 0)}%")
            else:
                print("   ⏭️ Agent 未启用（API Key 未配置）")
        except Exception as e:
            print(f"   ⚠️ Agent 分析失败: {e}")
    else:
        print("   ⏭️ Agent 未配置（请在 config.yaml 中设置 agent.enabled: true）")

    # ---------- 8. ✅ 推送结果（只推送一次，包含Agent分析） ----------
    print("\n📲 步骤8：推送结果并存储...")
    notifier = PushNotifier()
    notifier.send(result, args.phase)

    print("\n" + "=" * 50)
    print("✅ 闭环执行完成！")
    print("=" * 50)


if __name__ == "__main__":
    main()
