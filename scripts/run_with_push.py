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

    # ========== 1. 数据获取 ==========
    print("\n📊 步骤1：获取数据...")

    # ✅ 盘中阶段优先使用 AlphaFeed
    use_alphafeed = config.get('phases', {}).get(args.phase, {}).get('use_alphafeed', False)

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

    # ========== 2. 核心逻辑分析 ==========
    print("\n🧠 步骤2：核心逻辑分析...")
    sm = VSystemStateMachine(phase=args.phase)
    result = sm.run(market_data)
    print(f"   ✅ 分析完成，信任度: {result.trust_score:.2f}, 判断: {result.judge_status}")

    # ========== 3. ✅ 消息面烈度评分 ==========
    print("\n📰 步骤3：消息面烈度评分...")
    sentiment_config = config.get('sentiment', {})
    if sentiment_config.get('enabled', False):
        sent_engine = SentimentEngine()
        sector_names = [s.name for s in result.signals]
        sentiment_results = sent_engine.batch_analyze(sector_names)

        # 将烈度评分附加到 result（用于推送展示）
        result.sentiment = sentiment_results
        print(f"   ✅ 烈度评分完成，覆盖 {len(sentiment_results)} 个板块")
    else:
        result.sentiment = {}
        print("   ⏭️ 烈度评分未启用")

    # ========== 4. ✅ 影子系统 ==========
    print("\n👻 步骤4：影子系统运行...")
    shadow_config = config.get('shadow', {})
    if shadow_config.get('enabled', False):
        shadow_sys = ShadowSystem()
        shadow_result = shadow_sys.run_variants({}, result.signals)
        result.shadow = shadow_result

        reliability = shadow_result.get('reliability', {})
        print(f"   ✅ 影子系统完成，可靠度: {reliability.get('overall_reliability', 0):.2%}")
        print(f"   📌 建议: {reliability.get('recommendation', '')}")
    else:
        result.shadow = {}
        print("   ⏭️ 影子系统未启用")

    # ========== 5. 推送 ==========
    print("\n📲 步骤5：推送结果并存储...")
    notifier = PushNotifier()
    notifier.send(result, args.phase)

    print("\n" + "=" * 50)
    print("✅ 闭环执行完成！")
    print("=" * 50)


if __name__ == "__main__":
    main()
