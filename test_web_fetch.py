#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试网页抓取工具
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.codex_tools import CodexTools

def main():
    print("=" * 60)
    print("🌐 测试网页抓取工具")
    print("=" * 60)

    tools = CodexTools()
    
    # 测试抓取财联社新闻
    test_url = "https://www.cls.cn/detail/123456"  # 示例URL
    
    print(f"\n📥 正在抓取: {test_url}")
    result = tools.fetch_webpage(test_url)
    
    if result.get('status') == 'success':
        print(f"✅ 抓取成功!")
        print(f"   📊 内容长度: {result.get('content_length')} 字符")
        print(f"   📊 行数: {result.get('line_count')}")
        print(f"\n📄 内容预览:\n{result.get('content', '')[:500]}...")
    else:
        print(f"❌ 抓取失败: {result.get('error')}")
    
    print("\n" + "=" * 60)
    print("✅ 测试完成！")
    print("=" * 60)

if __name__ == "__main__":
    main()
