# ============================================================
# 消息面烈度评分引擎
# 对应精阶段 V1.1.45 消息面烈度评分体系
# ============================================================

import os
import re
import logging
import requests
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SentimentEngine:
    """
    消息面烈度评分引擎
    三维度评分：市场热度 + 新闻情绪 + 资金流向
    """

    def __init__(self):
        self.enabled = False
        self.search_api_key = os.environ.get("SEARCH_API_KEY")  # 如 SerpAPI 或自定义搜索
        self.search_engine = os.environ.get("SEARCH_ENGINE", "google")
        self.sentiment_cache = {}
        self.cache_ttl = 3600  # 1小时缓存

    def analyze(self, sector_name: str, force_refresh: bool = False) -> Dict:
        """
        分析单个板块的消息面烈度
        返回：烈度评分（0-10）、情绪标签、关键词
        """
        cache_key = sector_name
        if not force_refresh and cache_key in self.sentiment_cache:
            cached = self.sentiment_cache[cache_key]
            if (datetime.now() - cached['time']).total_seconds() < self.cache_ttl:
                return cached['data']

        # 获取相关新闻
        news = self._fetch_news(sector_name)
        if not news:
            result = self._get_default_sentiment()
            self._cache_sentiment(cache_key, result)
            return result

        # 三维度评分
        heat_score = self._score_market_heat(news)          # 市场热度 0-10
        emotion_score = self._score_news_emotion(news)      # 新闻情绪 -10~10
        flow_score = self._score_fund_flow(sector_name)     # 资金流向 -10~10

        # 综合烈度评分（归一化到 0-10）
        total_score = self._calculate_intensity(heat_score, emotion_score, flow_score)

        # 判断情绪标签
        if emotion_score > 3:
            emotion_label = "积极"
        elif emotion_score < -3:
            emotion_label = "消极"
        else:
            emotion_label = "中性"

        result = {
            "intensity_score": round(total_score, 1),      # 烈度评分 0-10
            "heat_score": round(heat_score, 1),            # 热度 0-10
            "emotion_score": round(emotion_score, 1),      # 情绪 -10~10
            "flow_score": round(flow_score, 1),            # 资金 -10~10
            "emotion_label": emotion_label,                # 情绪标签
            "news_count": len(news),
            "top_keywords": self._extract_keywords(news),
            "summary": self._generate_summary(news, emotion_label),
            "timestamp": datetime.now().isoformat()
        }

        self._cache_sentiment(cache_key, result)
        return result

    def _fetch_news(self, sector_name: str) -> List[Dict]:
        """获取板块相关新闻"""
        if not self.search_api_key:
            logger.warning("⚠️ 未配置 SEARCH_API_KEY，使用模拟新闻")
            return self._get_mock_news(sector_name)

        try:
            # 使用搜索API获取新闻
            query = f"{sector_name} 板块 A股 最新消息"
            params = {
                "engine": self.search_engine,
                "q": query,
                "api_key": self.search_api_key,
                "num": 10,
                "tbm": "nws"
            }
            resp = requests.get("https://serpapi.com/search", params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                news_results = data.get('news_results', [])
                return [{
                    'title': n.get('title', ''),
                    'snippet': n.get('snippet', ''),
                    'source': n.get('source', ''),
                    'date': n.get('date', '')
                } for n in news_results]
            return self._get_mock_news(sector_name)
        except:
            return self._get_mock_news(sector_name)

    def _get_mock_news(self, sector_name: str) -> List[Dict]:
        """模拟新闻数据（用于测试）"""
        mock_news = [
            {"title": f"{sector_name}板块今日表现活跃", "snippet": f"{sector_name}板块受政策利好影响，多只个股上涨", "source": "财联社", "date": datetime.now().strftime("%Y-%m-%d")},
            {"title": f"机构看好{sector_name}板块后市", "snippet": f"多家机构表示{sector_name}板块估值处于历史低位", "source": "证券时报", "date": datetime.now().strftime("%Y-%m-%d")},
        ]
        return mock_news

    def _score_market_heat(self, news: List[Dict]) -> float:
        """评分市场热度"""
        if not news:
            return 3.0
        # 根据新闻数量和质量评分
        count_score = min(len(news) / 10, 5.0)  # 最多5分
        quality_score = 0.0
        for n in news:
            snippet = n.get('snippet', '')
            if '政策' in snippet or '利好' in snippet:
                quality_score += 0.5
            elif '市场' in snippet or '资金' in snippet:
                quality_score += 0.3
        quality_score = min(quality_score, 3.0)  # 最多3分
        time_score = 2.0  # 基础分
        return min(count_score + quality_score + time_score, 10.0)

    def _score_news_emotion(self, news: List[Dict]) -> float:
        """评分新闻情绪"""
        if not news:
            return 0.0

        positive_words = ['利好', '上涨', '突破', '看好', '买入', '增持', '积极', '回升', '反弹']
        negative_words = ['利空', '下跌', '跌破', '看空', '卖出', '减持', '悲观', '回落', '调整']

        pos_score = 0
        neg_score = 0
        for n in news:
            text = n.get('title', '') + ' ' + n.get('snippet', '')
            for word in positive_words:
                if word in text:
                    pos_score += 1
            for word in negative_words:
                if word in text:
                    neg_score += 1

        total = pos_score + neg_score
        if total == 0:
            return 0.0

        # 归一化到 -10~10
        normalized = (pos_score - neg_score) / (total + 1) * 10
        return max(-10, min(10, normalized))

    def _score_fund_flow(self, sector_name: str) -> float:
        """评分资金流向"""
        # 实际需要调用资金流向API
        # 目前用模拟值
        import random
        # 使用固定种子保证一致性
        random.seed(hash(sector_name) % 10000)
        score = random.uniform(-5, 5)
        random.seed()  # 重置
        return round(score, 1)

    def _calculate_intensity(self, heat: float, emotion: float, flow: float) -> float:
        """计算综合烈度评分"""
        # 热度权重 0.3，情绪权重 0.4，资金权重 0.3
        # 情绪需要归一化到 0-10
        emotion_norm = (emotion + 10) / 2
        total = heat * 0.3 + emotion_norm * 0.4 + (flow + 10) / 2 * 0.3
        return total

    def _extract_keywords(self, news: List[Dict]) -> List[str]:
        """提取关键词"""
        text = ' '.join([n.get('title', '') + ' ' + n.get('snippet', '') for n in news[:5]])
        words = re.findall(r'[\u4e00-\u9fa5]{2,4}', text)
        # 简单频率统计
        freq = {}
        for w in words:
            if w in ['板块', '市场', '资金', '机构', '投资者']:
                continue
            freq[w] = freq.get(w, 0) + 1
        sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [w for w, _ in sorted_words[:5]]

    def _generate_summary(self, news: List[Dict], emotion_label: str) -> str:
        """生成新闻摘要"""
        if not news:
            return "暂无相关新闻"

        if emotion_label == "积极":
            return f"板块消息面整体偏积极，近期待关注政策动向"
        elif emotion_label == "消极":
            return f"板块消息面存在压力，建议谨慎操作"
        else:
            return f"板块消息面中性，建议结合技术面判断"

    def _get_default_sentiment(self) -> Dict:
        """获取默认的烈度评分（当无法获取新闻时）"""
        return {
            "intensity_score": 5.0,
            "heat_score": 5.0,
            "emotion_score": 0.0,
            "flow_score": 0.0,
            "emotion_label": "中性",
            "news_count": 0,
            "top_keywords": [],
            "summary": "暂无数据",
            "timestamp": datetime.now().isoformat()
        }

    def _cache_sentiment(self, key: str, data: Dict):
        """缓存烈度评分结果"""
        self.sentiment_cache[key] = {
            'data': data,
            'time': datetime.now()
        }

    def batch_analyze(self, sectors: List[str]) -> Dict[str, Dict]:
        """批量分析多个板块的烈度评分"""
        results = {}
        for sector in sectors:
            results[sector] = self.analyze(sector)
        return results
