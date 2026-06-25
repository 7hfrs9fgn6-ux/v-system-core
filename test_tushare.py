#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tushare API 可用性验证脚本
用于诊断 Tushare 数据获取问题
"""

import os
import sys
from datetime import datetime, timedelta

# 尝试导入 tushare
try:
    import tushare as ts
except ImportError:
    print("❌ tushare 未安装，请运行: pip install tushare")
    sys.exit(1)


def print_section(title):
    """打印分隔标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_result(success, message, detail=""):
    """打印测试结果"""
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"{status} | {message}")
    if detail:
        print(f"       详情: {detail}")


def test_tushare_connection(token):
    """测试 Tushare 连接和 Token 有效性"""
    print_section("1. 测试 Tushare 连接")
    
    try:
        ts.set_token(token)
        pro = ts.pro_api()
        print(f"   Token: {token[:8]}...{token[-4:]}")
        
        # 尝试获取一个简单的数据来验证连接
        df = pro.index_daily(ts_code="000001.SH", start_date="20260601", end_date="20260620")
        
        if df is not None and not df.empty:
            print_result(True, "Tushare 连接成功，Token 有效")
            print(f"   📊 获取到 {len(df)} 条上证指数数据")
            print(f"   📅 最新日期: {df['trade_date'].iloc[-1]}")
            return pro
        else:
            print_result(False, "Tushare 连接成功但返回空数据")
            print("   可能原因: Token 权限不足或日期范围内无数据")
            return None
            
    except Exception as e:
        print_result(False, f"Tushare 连接失败: {str(e)}")
        return None


def test_market_index(pro):
    """测试大盘指数数据获取"""
    print_section("2. 测试大盘指数数据")
    
    if pro is None:
        print("❌ 跳过测试: Tushare 连接未建立")
        return
    
    # 测试最近5个交易日
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
    
    try:
        df = pro.index_daily(ts_code="000001.SH", start_date=start_date, end_date=end_date)
        
        if df is not None and not df.empty:
            print_result(True, f"上证指数: 获取到 {len(df)} 条数据")
            latest = df.iloc[-1]
            print(f"   📊 最新日期: {latest['trade_date']}")
            print(f"   📈 最新收盘: {latest['close']:.2f}")
            print(f"   📈 涨跌幅: {latest.get('pct_chg', 0):.2f}%")
            
            # 也测试深证
            df_sz = pro.index_daily(ts_code="399001.SZ", start_date=start_date, end_date=end_date)
            if df_sz is not None and not df_sz.empty:
                print_result(True, f"深证成指: 获取到 {len(df_sz)} 条数据")
            else:
                print_result(False, "深证成指: 返回空数据")
        else:
            print_result(False, "上证指数: 返回空数据")
            
    except Exception as e:
        print_result(False, f"大盘指数获取失败: {str(e)}")


def test_sector_index(pro):
    """测试行业指数数据获取（核心问题）"""
    print_section("3. 测试行业指数数据（核心问题）")
    
    if pro is None:
        print("❌ 跳过测试: Tushare 连接未建立")
        return
    
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
    
    # 测试代码列表（带 .SI 和不带 .SI）
    test_codes = [
        ("801080.SI", "电子 (.SI)"),
        ("801080", "电子 (无后缀)"),
        ("801750.SI", "计算机 (.SI)"),
        ("801750", "计算机 (无后缀)"),
        ("000001.SH", "上证指数 (对比)"),
    ]
    
    for code, desc in test_codes:
        try:
            df = pro.index_daily(ts_code=code, start_date=start_date, end_date=end_date)
            
            if df is not None and not df.empty:
                print_result(True, f"{desc}: 成功，{len(df)} 条数据")
                latest = df.iloc[-1]
                print(f"       最新日期: {latest['trade_date']}, 收盘: {latest['close']:.2f}")
            else:
                print_result(False, f"{desc}: 返回空数据")
                
        except Exception as e:
            print_result(False, f"{desc}: 异常 - {str(e)}")


def test_north_flow(pro):
    """测试北向资金数据"""
    print_section("4. 测试北向资金数据")
    
    if pro is None:
        print("❌ 跳过测试: Tushare 连接未建立")
        return
    
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=5)).strftime("%Y%m%d")
    
    try:
        df = pro.moneyflow_hsgt(start_date=start_date, end_date=end_date)
        
        if df is not None and not df.empty:
            print_result(True, f"北向资金: 获取到 {len(df)} 条数据")
            latest = df.iloc[-1]
            print(f"   📅 最新日期: {latest.get('trade_date', '未知')}")
            print(f"   💰 净流入: {latest.get('net_inflow', 0):.2f} 万元")
        else:
            print_result(False, "北向资金: 返回空数据")
            
    except Exception as e:
        print_result(False, f"北向资金获取失败: {str(e)}")


def test_tushare_user_info(pro):
    """测试用户信息"""
    print_section("5. 用户信息")
    
    if pro is None:
        print("❌ 跳过测试: Tushare 连接未建立")
        return
    
    try:
        # 尝试获取用户信息
        df = pro.user_info()
        
        if df is not None and not df.empty:
            print_result(True, "用户信息获取成功")
            row = df.iloc[0]
            print(f"   👤 用户: {row.get('name', 'N/A')}")
            print(f"   💳 积分: {row.get('points', 0)}")
            print(f"   📅 到期: {row.get('expires', 'N/A')}")
        else:
            print_result(False, "用户信息获取失败")
            
    except Exception as e:
        # 某些版本可能不支持 user_info
        print_result(True, f"用户信息接口不可用（非关键）: {str(e)[:50]}...")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("  🔍 Tushare API 可用性验证工具")
    print("=" * 60)
    
    # 读取 Token
    token = os.environ.get("TUSHARE_TOKEN")
    
    if not token:
        print("\n⚠️ 未设置 TUSHARE_TOKEN 环境变量")
        print("\n请通过以下方式设置:")
        print("  1. GitHub Secrets: TUSHARE_TOKEN")
        print("  2. 本地环境变量: export TUSHARE_TOKEN='your_token'")
        print("  3. 直接输入 Token (不安全，仅测试用)")
        
        # 询问是否手动输入
        try:
            manual_input = input("\n是否手动输入 Token？(y/N): ").strip().lower()
            if manual_input == 'y':
                token = input("请输入 Tushare Token: ").strip()
                if not token:
                    print("❌ Token 为空，退出")
                    return
            else:
                print("❌ 未提供 Token，退出")
                return
        except:
            print("❌ 无法获取输入，退出")
            return
    
    # 开始测试
    pro = test_tushare_connection(token)
    
    if pro is None:
        print("\n" + "=" * 60)
        print("  ❌ 验证失败：Tushare 连接无法建立")
        print("=" * 60)
        print("\n请检查:")
        print("  1. Token 是否正确")
        print("  2. 网络是否可访问 tushare.pro")
        print("  3. Token 是否已过期")
        return
    
    # 执行各项测试
    test_market_index(pro)
    test_sector_index(pro)
    test_north_flow(pro)
    test_tushare_user_info(pro)
    
    # 输出总结
    print_section("📊 验证总结")
    print("""
如果行业指数 (.SI) 返回空数据，可能原因：
1. Tushare 积分不足（需要2000分以上访问行业指数）
2. 行业指数代码格式错误（需登录 Tushare 官网确认）
3. 当前非交易日，行业指数无数据
4. 接口权限未开通

解决方案：
1. 登录 https://tushare.pro 查看积分和权限
2. 在"数据"→"指数"→"行业指数"中查看正确的 ts_code
3. 如果积分不足，可考虑使用 AKShare 替代（已验证可用）
    """)
    
    print("=" * 60)
    print("  验证完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
