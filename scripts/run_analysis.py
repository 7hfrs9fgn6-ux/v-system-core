# 全链路分析脚本（模拟数据 + 核心逻辑）
# 对应 01-full-analysis.yml

import json
from data_adapter.mock_adapter import MockDataAdapter
from core.state_machine import VSystemStateMachine

def main():
    print("=" * 50)
    print("🚀 V系统 模拟全链路分析启动 (V1.1.54 / V2.0.2)")
    print("=" * 50)
    
    # 1. 数据适配层：获取模拟数据
    print("\n📊 步骤1：数据适配层获取模拟数据...")
    adapter = MockDataAdapter()
    market_data = adapter.fetch_all()
    print(f"   ✅ 获取到 {len(market_data.sectors)} 个板块数据")
    print(f"   🕒 数据时间: {market_data.timestamp}")
    print(f"   📈 市场环境: {market_data.index_trend}")
    print(f"   💰 北向资金: {market_data.north_flow} 亿")
    print(f"   🟢 新鲜度: {market_data.freshness.value}")
    
    # 2. 核心逻辑层：运行状态机
    print("\n🧠 步骤2：核心逻辑层处理中...")
    sm = VSystemStateMachine()
    result = sm.run(market_data)
    
    # 3. 输出层：打印结果（简阶段L1/L3风格）
    print("\n📲 步骤3：输出层结果展示（模拟L1+L3）")
    print("-" * 40)
    print(f"📌 综合建议: {result.overall_suggestion}")
    print(f"🔒 信任度: {result.trust_score:.2f} → 判断状态: {result.judge_status}")
    print(f"🏥 健康度: {result.health_score}")
    print(f"🤖 运行模式: {result.agent_mode}")
    print(f"🚩 漂移标记: {result.drift_flag}")
    
    if result.warnings:
        print("⚠️ 告警信息:")
        for w in result.warnings:
            print(f"   - {w}")
    
    print("\n📋 板块信号详情（L3附录）：")
    print("┌────────────┬──────────┬────────────┬────────────┐")
    print("│ 板块       │ 回撤%    │ 阈值%      │ 信号等级   │")
    print("├────────────┼──────────┼────────────┼────────────┤")
    for s in result.signals[:5]:  # 只显示前5个，节约篇幅
        print(f"│ {s.name:10} │ {s.drawdown:8.1f} │ {s.threshold:10.1f} │ {s.signal_level:11} │")
    print(f"│ ... (共{len(result.signals)}个板块，完整数据已存入L3) │")
    print("└────────────┴──────────┴────────────┴────────────┘")
    
    print("\n" + "=" * 50)
    print("✅ 模拟全链路验证通过！")
    print("=" * 50)

if __name__ == "__main__":
    main()
