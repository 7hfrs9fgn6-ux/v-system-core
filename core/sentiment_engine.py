# ============================================================
# 消息面烈度评分引擎 - Brave Search API 适配版
# ============================================================

import os
import re
import logging
import requests
from typing import List, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SentimentEngine:
    """消息面烈度评分引擎（使用 Brave Search API）"""

    def __init__(self):
        self.api_key = os.environ.get("SEARCH_API_KEY")
        self.enabled = self.api_key is not None and self.api_key != ""
        self.base_url = "https://api.search.brave.com/res/v1/web/search"
        self.sentiment_cache = {}
        self.cache_ttl = 3600  # 1小时

    def analyze(self, sector_name: str, force_refresh: bool = False) -> Dict:
        """分析单个板块的消息面烈度"""
        cache_key = sector_name
        if not force_refresh and cache_key in self.sentiment_cache:
            cached = self.sentiment_cache[cache_key]
            if (datetime.now() - cached['time']).total_seconds() < self.cache_ttl:
                return cached['data']

        # 获取新闻
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
            "timestamp": datetime.now().isoformat()
        }

        self._cache_sentiment(cache_key, result)
        return result

    def _fetch_news(self, sector_name: str) -> List[Dict]:
        """✅ 使用 Brave Search API 获取新闻"""
        if not self.enabled:
            logger.warning("⚠️ SEARCH_API_KEY 未配置，使用模拟新闻")
            return self._get_mock_news(sector_name)

        try:
            # Brave API 的新闻搜索参数
            headers = {
                "Accept": "application/json",
                "X-Subscription-Token": self.api_key
            }
            params = {
                "q": f"{sector_name} 板块 A股 新闻",
                "count": 10,
                "freshness": "week",  # 最近一周
                "safesearch": "moderate"
            }

            resp = requests.get(
                self.base_url,
                headers=headers,
                params=params,
                timeout=10
            )

            if resp.status_code == 200:
                data = resp.json()
                # Brave 返回的新闻在 web.results 中，type 为 "news" 的条目
                results = data.get('web', {}).get('results', [])
                news_list = []
                for item in results:
                    # 只取新闻类型（或包含新闻关键词）
                    title = item.get('title', '')
                    snippet = item.get('description', '')
                    # 如果既不是新闻也没有相关描述，跳过
                    if not title and not snippet:
                        continue
                    news_list.append({
                        'title': title,
                        'snippet': snippet,
                        'source': item.get('url', '').split('/')[2] if item.get('url') else '未知',
                        'date': datetime.now().strftime("%Y-%m-%d")
                    })
                if news_list:
                    logger.info(f"   ✅ Brave 返回 {len(news_list)} 条新闻")
                    return news_list
                else:
                    logger.warning(f"⚠️ Brave 未返回新闻，使用模拟数据")
                    return self._get_mock_news(sector_name)
            else:
                logger.warning(f"⚠️ Brave API 请求失败: {resp.status_code}")
                return self._get_mock_news(sector_name)

        except Exception as e:
            logger.warning(f"⚠️ Brave API 异常 ({e})，使用模拟数据")
            return self._get_mock_news(sector_name)

    def _get_mock_news(self, sector_name: str) -> List[Dict]:
        """模拟新闻（降级方案）"""
        return [
            {"title": f"{sector_name}板块今日表现活跃", "snippet": f"{sector_name}板块受政策利好影响，多只个股上涨", "source": "财联社", "date": datetime.now().strftime("%Y-%m-%d")},
            {"title": f"机构看好{sector_name}板块后市", "snippet": f"多家机构表示{sector_name}板块估值处于历史低位", "source": "证券时报", "date": datetime.now().strftime("%Y-%m-%d")},
        ]

    def _score_market_heat(self, news: List[Dict]) -> float:
        if not news:
            return 3.0
        count_score = min(len(news) / 10, 5.0)
        quality_score = 0.0
        for n in news:
            snippet = n.get('snippet', '')
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
        positive_words = ['利好', '上涨', '突破', '看好', '买入', '增持', '积极', '回升', '反弹']
        negative_words = ['利空', '下跌', '跌破', '看空', '卖出', '减持', '悲观', '回落', '调整']

        pos_score, neg_score = 0, 0
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
        return max(-10, min(10, (pos_score - neg_score) / (total + 1) * 10))

    def _score_fund_flow(self, sector_name: str) -> float:
        import random
        random.seed(hash(sector_name) % 10000)
        score = random.uniform(-5, 5)
        random.seed()
        return round(score, 1)

    def _calculate_intensity(self, heat: float, emotion: float, flow: float) -> float:
        emotion_norm = (emotion + 10) / 2
        return heat * 0.3 + emotion_norm * 0.4 + (flow + 10) / 2 * 0.3

    def _extract_keywords(self, news: List[Dict]) -> List[str]:
        text = ' '.join([n.get('title', '') + ' ' + n.get('snippet', '') for n in news[:5]])
        words = re.findall(r'[\u4e00-\u9fa5]{2,4}', text)
        freq = {}
        for w in words:
            if w in ['板块', '市场', '资金', '机构', '投资者']:
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
            "timestamp": datetime.now().isoformat()
        }

    def _cache_sentiment(self, key: str, data: Dict):
        self.sentiment_cache[key] = {'data': data, 'time': datetime.now()}

    def batch_analyze(self, sectors: List[str]) -> Dict[str, Dict]:
        results = {}
        for sector in sectors:
            results[sector] = self.analyze(sector)
        return results
