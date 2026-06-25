#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能代理独立运行脚本
测试 DS API + Codex + Bridge 完整链路
不影响现有主流程
"""

import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ds_agent import DSAgent
from core.bridge import Bridge


def main():
    print("=" * 60)
    print("🧠 V系统 智能代理测试")
    print("=" * 60)

    # 初始化 Agent
    agent = DSAgent()

    if not agent.enabled:
        print("\n❌ DS API Key 未配置，智能代理无法启动")
        print("请在 GitHub Secrets 中配置 DEEPSEEK_API_KEY")
        return

    print("\n📋 已注册工具:")
    for tool in agent.tools:
        print(f"   - {tool['function']['name']}: {tool['function']['description']}")

    # 测试1：分析单个板块
    print("\n" + "=" * 60)
    print("📊 测试1：分析电子板块")
    print("=" * 60)
    result = agent.analyze_sector("电子")
    print(f"结果: {json.dumps(result, ensure_ascii=False, indent=2)}")

    # 测试2：查看 Bridge 状态
    print("\n" + "=" * 60)
    print("🔧 Bridge 统计信息")
    print("=" * 60)
    stats = Bridge.get_stats()
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    print("\n" + "=" * 60)
    print("✅ Agent 测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
