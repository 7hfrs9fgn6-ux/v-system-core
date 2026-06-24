# 历史回测执行脚本

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.backtest_engine import BacktestEngine

def main():
    print("=" * 50)
    print("🚀 V系统历史回测启动")
    print("=" * 50)
    
    # 回测最近1年
    engine = BacktestEngine("2025-06-01", "2026-06-01")
    results = engine.run()
    
    report = engine.generate_report(results)
    print(report)
    
    # 保存报告到文件
    with open("backtest_report.txt", "w") as f:
        f.write(report)
    print("\n📁 报告已保存至 backtest_report.txt")

if __name__ == "__main__":
    main()
