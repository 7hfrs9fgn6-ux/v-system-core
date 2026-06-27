#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P0阶段测试脚本：验证宏观数据采集是否正常
"""

import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.macro_collector import MacroCollector


def print_section(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_data(label, data):
    print(f"\n📊 {label}:")
    if data:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print("  无数据")


def main():
    print("\n" + "=" * 60)
    print("  🔍 P0阶段验证：宏观数据采集")
    print("  (不修改任何AK代码，仅测试新增模块)")
    print("=" * 60)

    collector = MacroCollector()

    # 1. 美股市场
    print_section("1. 美股市场")
    us = collector.get_us_market()
    print_data("美股", us)

    # 2. 亚太市场
    print_section("2. 亚太市场")
    asia = collector.get_asia_market()
    print_data("亚太", asia)

    # 3. 欧洲市场
    print_section("3. 欧洲市场")
    euro = collector.get_europe_market()
    print_data("欧洲", euro)

    # 4. 大宗商品
    print_section("4. 大宗商品")
    comm = collector.get_commodities()
    print_data("大宗商品", comm)

    # 5. 汇率
    print_section("5. 人民币汇率")
    forex = collector.get_forex()
    print_data("汇率", forex)

    # 6. A50期货
    print_section("6. A50期货")
    a50 = collector.get_a50_futures()
    print_data("A50期货", a50)

    # 7. 宏观快照
    print_section("7. 宏观快照（汇总）")
    snapshot = collector.get_macro_snapshot()
    print(f"   ✅ 宏观快照获取成功")
    print(f"   📅 时间: {snapshot.get('timestamp')}")
    print(f"   📊 美股指数数量: {len(snapshot.get('us_market', {}).get('indices', {}))}")
    print(f"   📊 亚太指数数量: {len(snapshot.get('asia_market', {}).get('indices', {}))}")
    print(f"   📊 欧洲指数数量: {len(snapshot.get('europe_market', {}).get('indices', {}))}")

    print("\n" + "=" * 60)
    print("  ✅ P0阶段测试完成！")
    print("=" * 60)
    print("\n如果数据都有值，说明宏观数据采集模块工作正常。")


if __name__ == "__main__":
    main()
