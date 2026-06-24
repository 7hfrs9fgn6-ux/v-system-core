# ============================================================
# 消息面烈度评分引擎（NewsAPI + 天行数据 双源）
# 优先使用 NewsAPI，失败时自动降级到天行数据（国内）
# ============================================================

import os
import re
import logging
import requests
from typing import List, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SentimentEngine:
    """
    消息面烈度评分引擎 - 双数据源
    1. NewsAPI（国际新闻，优先）
    2. 天行数据（国内财经新闻，备用）
    """

    def __init__(self):
        self.newsapi_key = os.environ.get("SEARCH_API_KEY")  # NewsAPI Key
        self.tianxing_key = os.environ.get("TIANXING_API_KEY")  # 天行数据 Key
        self.enabled = bool(self.newsapi_key) or bool(self.tianxing_key)
        self.sentiment_cache = {}
        self.cache_ttl = 3600

        if self.newsapi_key:
            logger.info("✅ NewsAPI Key 已配置，将优先使用")
        if self.tianxing_key:
            logger.info("✅ 天行数据 Key 已配置，将作为备用")
        if not self.enabled:
            logger.warning("⚠️ 未配置任何新闻API，烈度评分将使用模拟新闻")

    def analyze(self, sector_name: str, force_refresh: bool = False) -> Dict:
        """分析单个板块的消息面烈度"""
        cache_key = sector_name
        if not force_refresh and cache_key in self.sentiment_cache:
            cached = self.sentiment_cache[cache_key]
            if (datetime.now() - cached['time']).total_seconds() < self.cache_ttl:
                return cached['data']

        # 获取新闻：优先 NewsAPI，失败则天行数据
        news = self._fetch_news(sector_name)

        if not news:
            result = self._get_default_sentiment()
            self._cache_sentiment(cache_key, result)
            return result

        # 三维度评分
        heat_score = self._score_market_heat(news)
        emotion_score = self._score_news_emotion(news)
        flow_score = self._score_fund_flow(sector_name)

        total_score = self._calculate_intensity(heat_score, emotion_score, flow_score)

        if emotion_score > 3:
            emotion_label = "积极"
        elif emotion_score < -3:
            emotion_label = "消极"
        else:
            emotion_label = "中性"

        result = {
            "intensity_score": round(total_score, 1),
            "heat_score": round(heat_score, 1),
            "emotion_score": round(emotion_score, 1),
            "flow_score": round(flow_score, 1),
            "emotion_label": emotion_label,
            "news_count": len(news),
            "top_keywords": self._extract_keywords(news),
            "summary": self._generate_summary(news, emotion_label),
            "timestamp": datetime.now().isoformat(),
            "data_source": "NewsAPI" if self.newsapi_key else "天行数据"
        }

        self._cache_sentiment(cache_key, result)
        return result

    def _fetch_news(self, sector_name: str) -> List[Dict]:
        """获取新闻：优先 NewsAPI，失败则天行数据"""
        news = []
        
        # 1. 尝试 NewsAPI
        if self.newsapi_key:
            news = self._fetch_from_newsapi(sector_name)
            if news:
                logger.info(f"✅ {sector_name}: NewsAPI 获取 {len(news)} 条新闻")
                return news
            else:
                logger.warning(f"⚠️ {sector_name}: NewsAPI 无数据，尝试天行数据...")
        
        # 2. 尝试天行数据
        if self.tianxing_key:
            news = self._fetch_from_tianxing(sector_name)
            if news:
                logger.info(f"✅ {sector_name}: 天行数据获取 {len(news)} 条新闻")
                return news
        
        # 3. 都失败，使用模拟
        logger.warning(f"⚠️ {sector_name}: 所有新闻源均失败，使用模拟")
        return self._get_mock_news(sector_name)

    def _fetch_from_newsapi(self, sector_name: str) -> List[Dict]:
        """使用 NewsAPI 获取"""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            
            query = f"{sector_name} 板块 A股"
            params = {
                "q": query,
                "from": week_ago,
                "to": today,
                "language": "zh",
                "pageSize": 10,
                "sortBy": "relevancy",
                "apiKey": self.newsapi_key
            }
            resp = requests.get("https://newsapi.org/v2/everything", params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('status') == 'ok':
                    articles = data.get('articles', [])
                    return [{
                        'title': a.get('title', ''),
                        'snippet': a.get('description', '') or a.get('content', ''),
                        'source': a.get('source', {}).get('name', ''),
                        'date': a.get('publishedAt', '').split('T')[0]
                    } for a in articles if a.get('title')]
            return []
        except Exception as e:
            logger.warning(f"NewsAPI 异常: {e}")
            return []

    def _fetch_from_tianxing(self, sector_name: str) -> List[Dict]:
        """
        使用天行数据获取国内财经新闻
        注册地址：https://www.tianapi.com/
        免费额度：100次/天
        """
        try:
            # 天行数据财经新闻接口
            url = "https://api.tianapi.com/guonei/index"
            params = {
                "key": self.tianxing_key,
                "num": 10,
                "word": sector_name  # 支持关键词搜索
            }
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == 200:
                    news_list = data.get('newslist', [])
                    return [{
                        'title': n.get('title', ''),
                        'snippet': n.get('description', '') or n.get('content', ''),
                        'source': n.get('source', '天行数据'),
                        'date': n.get('ctime', '').split(' ')[0] if 'ctime' in n else ''
                    } for n in news_list if n.get('title')]
            return []
        except Exception as e:
            logger.warning(f"天行数据异常: {e}")
            return []

    def _get_mock_news(self, sector_name: str) -> List[Dict]:
        """模拟新闻"""
        return [
            {"title": f"{sector_name}板块今日市场动态", "snippet": f"{sector_name}板块近期受到市场关注", "source": "模拟", "date": datetime.now().strftime("%Y-%m-%d")},
            {"title": f"机构关注{sector_name}板块机会", "snippet": f"多家机构认为{sector_name}板块具备投资价值", "source": "模拟", "date": datetime.now().strftime("%Y-%m-%d")}
        ]

    # 以下评分方法与之前相同，此处省略（保持原有代码）
    # _score_market_heat, _score_news_emotion, _score_fund_flow,
    # _calculate_intensity, _extract_keywords, _generate_summary,
    # _get_default_sentiment, _cache_sentiment, batch_analyze
