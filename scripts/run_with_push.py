# 完整闭环脚本（真实数据 + 核心逻辑 + 微信推送）
# 对应 03-full-closure.yml

import sys
import os
import argparse
# 将项目根目录添加到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_adapter.real_adapter import RealDataAdapter
from data_adapter.mock_adapter import MockDataAdapter
from core.state_machine import VSystemStateMachine
from output_layer.push_notifier import PushNotifier

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['pre', 'intraday', 'post'], default='pre')
    parser.add_argument('--mock', action='store_true', help='使用模拟数据（测试用）')
    args = parser.parse_args()
    
    print("=" * 50)
    print(f"🚀 V系统完整闭环启动 ({args.phase}阶段)")
    print("=" * 50)
    
    # 1. 数据适配层（真实 or 模拟）
    print("\n📊 步骤1：获取数据...")
    if args.mock:
        print("   使用模拟数据（测试模式）")
        adapter = MockDataAdapter()
    else:
        print("   使用真实数据（Tushare/AKShare）")
        adapter = RealDataAdapter()
    
    market_data = adapter.fetch_all()
    print(f"   ✅ 数据源: {getattr(adapter, 'data_source', 'Mock')}")
    print(f"   ✅ 板块数: {len(market_data.sectors)}")
    print(f"   🟢 新鲜度: {market_data.freshness.value}")
    
    # 2. 核心逻辑层
    print("\n🧠 步骤2：核心逻辑分析...")
    sm = VSystemStateMachine()
    result = sm.run(market_data)
    print(f"   ✅ 分析完成，信任度: {result.trust_score:.2f}, 判断: {result.judge_status}")
    
    # 3. 输出层（微信推送）
    print("\n📲 步骤3：推送结果...")
    notifier = PushNotifier()
    success = notifier.send(result, args.phase)
    
    print("\n" + "=" * 50)
    print("✅ 闭环执行完成！")
    print("=" * 50)

if __name__ == "__main__":
    main()
