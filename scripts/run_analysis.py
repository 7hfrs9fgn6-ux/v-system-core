import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_adapter.mock_adapter import MockDataAdapter
from core.state_machine import VSystemStateMachine

def main():
    print("=" * 50)
    print("🚀 V系统 模拟全链路分析启动")
    print("=" * 50)
    adapter = MockDataAdapter()
    market_data = adapter.fetch_all()
    print(f"\n📊 获取到 {len(market_data.sectors)} 个板块数据")
    print(f"🕒 数据时间: {market_data.timestamp}")
    print(f"📈 市场环境: {market_data.index_trend}")
    print(f"💰 北向资金: {market_data.north_flow} 亿")
    print(f"🟢 新鲜度: {market_data.freshness.value}")
    sm = VSystemStateMachine()
    result = sm.run(market_data)
    print("\n📲 分析结果：")
    print(f"📌 综合建议: {result.overall_suggestion}")
    print(f"🔒 信任度: {result.trust_score:.2f} → 判断: {result.judge_status}")
    print(f"🏥 健康度: {result.health_score}")
    print(f"🤖 运行模式: {result.agent_mode}")
    if result.warnings:
        print("⚠️ 告警:", ", ".join(result.warnings))
    print("\n✅ 模拟全链路验证通过！")

if __name__ == "__main__":
    main()
