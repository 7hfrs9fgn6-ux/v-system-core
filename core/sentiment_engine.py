import os
import re
import logging
import requests
from typing import List, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class SentimentEngine:
    def __init__(self):
        self.newsapi_key = os.environ.get("SEARCH_API_KEY")
        self.tianxing_key = os.environ.get("TIANXING_API_KEY")
        self.enabled = bool(self.newsapi_key) or bool(self.tianxing_key)
        self.sentiment_cache = {}
        self.cache_ttl = 3600

        if self.newsapi_key:
            logger.info("✅ NewsAPI Key 已配置")
        if self.tianxing_key:
            logger.info("✅ 天行数据 Key 已配置")
        if not self.enabled:
            logger.warning("⚠️ 未配置新闻API，将使用模拟新闻")

    def analyze(self, sector_name: str, force_refresh: bool = False) -> Dict:
        cache_key = sector_name
        if not force_refresh and cache_key in self.sentiment_cache:
            cached = self.sentiment_cache[cache_key]
            if (datetime.now() - cached['time']).total_seconds() < self.cache_ttl:
                return cached['data']

        news = self._fetch_news(sector_name)
        if not news:
            result = self._get_default_sentiment()
            self._cache_sentiment(cache_key, result)
            return result

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
        if self.newsapi_key:
            news = self._fetch_from_newsapi(sector_name)
            if news:
                return news
        if self.tianxing_key:
            news = self._fetch_from_tianxing(sector_name)
            if news:
                return news
        return self._get_mock_news(sector_name)

    def _fetch_from_newsapi(self, sector_name: str) -> List[Dict]:
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            params = {
                "q": f"{sector_name} 板块 A股",
                "from": week_ago,
                "to": today,
                "language": "zh",
                "pageSize": 10,
                "sortBy": "relevancy",
                "apiKey": self.newsapi_key
            }
            resp = requests.get("https://newsapi.org/v2/everything", params=params, timeout=8)
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
        try:
            url = "https://api.tianapi.com/guonei/index"
            params = {"key": self.tianxing_key, "num": 10, "word": sector_name}
            resp = requests.get(url, params=params, timeout=8)
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
        return [
            {"title": f"{sector_name}板块今日市场动态", "snippet": f"{sector_name}板块近期受到市场关注", "source": "模拟", "date": datetime.now().strftime("%Y-%m-%d")},
            {"title": f"机构关注{sector_name}板块机会", "snippet": f"多家机构认为{sector_name}板块具备投资价值", "source": "模拟", "date": datetime.now().strftime("%Y-%m-%d")}
        ]

    def _score_market_heat(self, news: List[Dict]) -> float:
        if not news:
            return 3.0
        count_score = min(len(news) / 10, 5.0)
        quality_score = 0.0
        for n in news:
            snippet = n.get('snippet', '') + ' ' + n.get('title', '')
            if '政策' in snippet or '利好' in snippet:
                quality_score += 0.5
            elif '市场' in snippet or '资金' in snippet:
                quality_score += 0.3
        quality_score = min(quality_score, 3.0)
        time_score = 2.0
        return min(count_score + quality_score + time_score, 10.0)

    def _score_news_emotion(self, news: List[Dict]) -> float:
        if not news:
            return 0.0
        positive_words = ['利好', '上涨', '突破', '看好', '买入', '增持', '积极', '回升', '反弹', '增长']
        negative_words = ['利空', '下跌', '跌破', '看空', '卖出', '减持', '悲观', '回落', '调整', '风险']
        pos_score = 0
        neg_score = 0
        for n in news:
            text = n.get('title', '') + ' ' + n.get('snippet', '')
            for w in positive_words:
                if w in text:
                    pos_score += 1
            for w in negative_words:
                if w in text:
                    neg_score += 1
        total = pos_score + neg_score
        if total == 0:
            return 0.0
        normalized = (pos_score - neg_score) / (total + 1) * 10
        return max(-10, min(10, normalized))

    def _score_fund_flow(self, sector_name: str) -> float:
        import random
        random.seed(hash(sector_name) % 10000)
        score = random.uniform(-5, 5)
        random.seed()
        return round(score, 1)

    def _calculate_intensity(self, heat: float, emotion: float, flow: float) -> float:
        emotion_norm = (emotion + 10) / 2
        total = heat * 0.3 + emotion_norm * 0.4 + (flow + 10) / 2 * 0.3
        return total

    def _extract_keywords(self, news: List[Dict]) -> List[str]:
        text = ' '.join([n.get('title', '') + ' ' + n.get('snippet', '') for n in news[:5]])
        words = re.findall(r'[\u4e00-\u9fa5]{2,4}', text)
        stop_words = ['板块', '市场', '资金', '机构', '投资者', 'A股', '同时', '已经', '进行']
        freq = {}
        for w in words:
            if w in stop_words:
                continue
            freq[w] = freq.get(w, 0) + 1
        sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [w for w, _ in sorted_words[:5]]

    def _generate_summary(self, news: List[Dict], emotion_label: str) -> str:
        if not news:
            return "暂无相关新闻"
        if emotion_label == "积极":
            return "板块消息面整体偏积极，近期待关注政策动向"
        elif emotion_label == "消极":
            return "板块消息面存在压力，建议谨慎操作"
        else:
            return "板块消息面中性，建议结合技术面判断"

    def _get_default_sentiment(self) -> Dict:
        return {
            "intensity_score": 5.0,
            "heat_score": 5.0,
            "emotion_score": 0.0,
            "flow_score": 0.0,
            "emotion_label": "中性",
            "news_count": 0,
            "top_keywords": [],
            "summary": "暂无数据",
            "timestamp": datetime.now().isoformat(),
            "data_source": "无"
        }

    def _cache_sentiment(self, key: str, data: Dict):
        self.sentiment_cache[key] = {'data': data, 'time': datetime.now()}

    def batch_analyze(self, sectors: List[str]) -> Dict[str, Dict]:
        results = {}
        for sector in sectors:
            results[sector] = self.analyze(sector)
        return results
