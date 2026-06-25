#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tushare API 验证脚本
验证：大盘指数、行业指数（两种代码格式）是否可获取
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def verify_tushare():
    print("=" * 60)
    print("🔍 Tushare API 验证开始")
    print("=" * 60)

    # 1. 检查 Token
    token = os.environ.get("TUSHARE_TOKEN")
    if not token or token == "dummy":
        print("❌ TUSHARE_TOKEN 未配置或为 dummy")
        return False
    print(f"✅ TUSHARE_TOKEN 已配置: {token[:10]}...")

    # 2. 导入 Tushare
    try:
        import tushare as ts
        print("✅ Tushare 库导入成功")
    except ImportError as e:
        print(f"❌ Tushare 库导入失败: {e}")
        return False

    ts.set_token(token)
    pro = ts.pro_api()

    # 3. 验证大盘指数（基准测试）
    print("\n" + "-" * 40)
    print("📊 测试1: 大盘指数 (000001.SH)")
    print("-" * 40)
    try:
        df = pro.index_daily(ts_code="000001.SH", start_date="20260620", end_date="20260625")
        if df is not None and not df.empty:
            print(f"✅ 大盘指数获取成功，共 {len(df)} 条数据")
            print(f"   最近: {df['close'].iloc[-1] if 'close' in df.columns else 'N/A'}")
        else:
            print("❌ 大盘指数返回空数据")
            return False
    except Exception as e:
        print(f"❌ 大盘指数获取失败: {e}")
        return False

    # 4. 验证行业指数（两种格式）
    test_codes = [
        ("纯数字", "801080"),
        (".SI后缀", "801080.SI"),
        ("纯数字", "801750"),
        (".SI后缀", "801750.SI"),
    ]

    print("\n" + "-" * 40)
    print("📊 测试2: 行业指数 (电子 801080 / 计算机 801750)")
    print("-" * 40)

    success_formats = []
    fail_formats = []

    for fmt_name, code in test_codes:
        try:
            df = pro.index_daily(ts_code=code, start_date="20260620", end_date="20260625")
            if df is not None and not df.empty:
                print(f"✅ {fmt_name} ({code}) 成功，共 {len(df)} 条数据")
                success_formats.append((fmt_name, code))
            else:
                print(f"❌ {fmt_name} ({code}) 返回空数据")
                fail_formats.append((fmt_name, code))
        except Exception as e:
            print(f"❌ {fmt_name} ({code}) 异常: {e}")
            fail_formats.append((fmt_name, code))

    # 5. 结论
    print("\n" + "=" * 60)
    print("📋 验证结论")
    print("=" * 60)

    if success_formats:
        print(f"✅ 成功的代码格式: {success_formats}")
        print("\n📌 建议: 使用上述成功格式配置 TUSHARE_CODE_MAP")
    else:
        print("❌ 所有行业指数格式均失败")
        print("\n📌 建议: 可能原因:")
        print("  1. Tushare 账户积分不足（行业指数需要较高权限）")
        print("  2. 行业指数接口需要单独申请权限")
        print("  3. 代码格式仍不正确（建议去 Tushare 官网查询）")
        print("\n📌 临时方案: 继续使用 AKShare 作为行业数据主源")

    if fail_formats:
        print(f"\n❌ 失败的代码格式: {fail_formats}")

    print("\n" + "=" * 60)
    return len(success_formats) > 0


if __name__ == "__main__":
    success = verify_tushare()
    sys.exit(0 if success else 1)
