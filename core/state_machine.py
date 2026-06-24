# 核心逻辑层状态机（V1.1.54 精阶段逻辑的精简可执行版）
# 输入：StandardMarketData，输出：SignalResult

from datetime import datetime
from output_layer.signal_result import StandardMarketData, SignalResult, FreshnessLevel

class VSystemStateMachine:
    """V系统核心状态机"""
    
    def run(self, market_data: StandardMarketData) -> SignalResult:
        warnings = []
        trust_score = 0.76  # 默认初始信任度（来自V1.1.54冷启动Phase 1）
        drift_flag = False
        agent_mode = "AI分析"
        
        # ---------- 关键裁决1：检查数据新鲜度（我们讨论的"新鲜度封顶"） ----------
        if market_data.freshness == FreshnessLevel.FRESH:
            # 数据新鲜，信任度维持不变
            pass
        elif market_data.freshness == FreshnessLevel.STALE:
            # 数据陈旧（15分钟~2小时），信任度强制封顶到0.50
            trust_score = min(trust_score, 0.50)
            warnings.append("数据源新鲜度偏低（STALE），信任度已封顶至0.50")
            agent_mode = "规则分析"  # 降级为规则分析，不依赖AI推理
        elif market_data.freshness == FreshnessLevel.EXPIRED:
            # 数据过期（>2小时），信任度强制封顶到0.30，并强烈告警
            trust_score = min(trust_score, 0.30)
            warnings.append("⚠️ 数据源已过期（EXPIRED），信任度已封顶至0.30，请勿据此操作")
            agent_mode = "AI已暂停"
        
        # ---------- 关键裁决2：判断状态映射（简阶段V2.0.2） ----------
        if trust_score >= 0.70:
            judge_status = "正常"
        elif 0.50 <= trust_score < 0.70:
            judge_status = "偏低"
        else:
            judge_status = "需谨慎"
        
        # ---------- 关键裁决3：生成综合建议（基于板块信号汇总） ----------
        # 简单汇总：计算所有板块信号的平均值，正数偏多，负数偏空
        avg_signal = sum(s.signal_level for s in market_data.sectors) / len(market_data.sectors)
        if avg_signal > 0.5:
            overall_suggestion = "偏多"
        elif avg_signal < -0.5:
            overall_suggestion = "偏空"
        else:
            overall_suggestion = "震荡"
        
        # 健康度：简单模拟（85分基础，若有告警扣分）
        health_score = 85
        if len(warnings) > 0:
            health_score -= len(warnings) * 10
        health_score = max(0, min(100, health_score))
        
        # ---------- 返回最终结果 ----------
        return SignalResult(
            version="V1.1.54 (模拟)",
            analysis_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            overall_suggestion=overall_suggestion,
            trust_score=trust_score,
            health_score=health_score,
            judge_status=judge_status,
            agent_mode=agent_mode,
            drift_flag=drift_flag,
            signals=market_data.sectors,  # 透传15个板块数据
            warnings=warnings
        )
