"""News source registry and configuration."""

from typing import Dict, List, Optional, Any
import asyncio
from datetime import datetime
from enum import Enum

import structlog
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.config import settings
from .monitor import NewsSource, SourceTier, NewsArticle

logger = structlog.get_logger()


class NewsSourceType(Enum):
    """Types of news sources."""
    RSS_FEED = "rss_feed"
    REST_API = "rest_api"
    WEB_SCRAPER = "web_scraper"
    SOCIAL_MEDIA = "social_media"


class NewsSourceRegistry:
    """Registry and manager for news sources."""
    
    def __init__(self):
        self.logger = logger.bind(component="news_sources")
        self.sources: Dict[str, NewsSource] = {}
        self.source_clients: Dict[str, 'BaseNewsClient'] = {}
        
        # Initialize built-in sources
        self._initialize_sources()
    
    def _initialize_sources(self):
        """Initialize built-in news sources."""
        
        # NewsAPI.org sources (Tier 1-3)
        if hasattr(settings, 'newsapi_key') and settings.newsapi_key:
            self._add_newsapi_sources()
        
        # Alpha Vantage News (Tier 2)
        if hasattr(settings.api, 'alpha_vantage_api_key') and settings.api.alpha_vantage_api_key:
            self._add_alpha_vantage_news()
        
        # Finnhub News (Tier 2)  
        if hasattr(settings.api, 'finnhub_api_key') and settings.api.finnhub_api_key:
            self._add_finnhub_news()
        
        # RSS feeds (Tier 2-3)
        self._add_rss_sources()
        
        # Social media sources (Tier 4)
        self._add_social_sources()
    
    def _add_newsapi_sources(self):
        """Add NewsAPI.org based sources."""
        
        # Tier 1 - Premium sources
        tier1_sources = [
            ("reuters", "Reuters", "reuters.com"),
            ("wsj", "Wall Street Journal", "wsj.com"),
            ("bloomberg", "Bloomberg", "bloomberg.com")
        ]
        
        for source_id, name, domain in tier1_sources:
            source = NewsSource(
                name=name,
                tier=SourceTier.TIER_1,
                base_url="https://newsapi.org/v2/everything",
                scan_interval_minutes=30,
                reliability_score=0.95,
                keywords=['finance', 'stocks', 'earnings', 'market']
            )
            
            self.sources[source_id] = source
            self.source_clients[source_id] = NewsAPIClient(source, domain)
        
        # Tier 2 - Major sources
        tier2_sources = [
            ("cnbc", "CNBC", "cnbc.com"),
            ("ft", "Financial Times", "ft.com"),
            ("economist", "The Economist", "economist.com")
        ]
        
        for source_id, name, domain in tier2_sources:
            source = NewsSource(
                name=name,
                tier=SourceTier.TIER_2,
                base_url="https://newsapi.org/v2/everything",
                scan_interval_minutes=60,
                reliability_score=0.85
            )
            
            self.sources[source_id] = source
            self.source_clients[source_id] = NewsAPIClient(source, domain)
    
    def _add_alpha_vantage_news(self):
        """Add Alpha Vantage news source."""
        
        source = NewsSource(
            name="Alpha Vantage News",
            tier=SourceTier.TIER_2,
            base_url="https://www.alphavantage.co/query",
            scan_interval_minutes=120,  # Less frequent due to rate limits
            reliability_score=0.80,
            rate_limit=5  # 5 requests per minute
        )
        
        self.sources['alpha_vantage_news'] = source
        self.source_clients['alpha_vantage_news'] = AlphaVantageNewsClient(source)
    
    def _add_finnhub_news(self):
        """Add Finnhub news source."""
        
        source = NewsSource(
            name="Finnhub News",
            tier=SourceTier.TIER_2,
            base_url="https://finnhub.io/api/v1/news",
            scan_interval_minutes=90,
            reliability_score=0.78,
            rate_limit=60  # 60 requests per minute
        )
        
        self.sources['finnhub_news'] = source
        self.source_clients['finnhub_news'] = FinnhubNewsClient(source)
    
    def _add_rss_sources(self):
        """Add RSS feed sources."""
        
        rss_sources = [
            ("yahoo_finance_rss", "Yahoo Finance RSS", SourceTier.TIER_3, 
             "https://feeds.finance.yahoo.com/rss/2.0/headline", 0.70),
            ("marketwatch_rss", "MarketWatch RSS", SourceTier.TIER_3,
             "https://feeds.marketwatch.com/marketwatch/realtimeheadlines/", 0.65),
            ("seeking_alpha_rss", "Seeking Alpha RSS", SourceTier.TIER_3,
             "https://seekingalpha.com/market_currents.xml", 0.68)
        ]
        
        for source_id, name, tier, url, reliability in rss_sources:
            source = NewsSource(
                name=name,
                tier=tier,
                base_url=url,
                scan_interval_minutes=120,
                reliability_score=reliability
            )
            
            self.sources[source_id] = source
            self.source_clients[source_id] = RSSNewsClient(source)
    
    def _add_social_sources(self):
        """Add social media sources."""
        
        # Reddit finance subreddits
        reddit_sources = [
            ("reddit_stocks", "Reddit r/stocks", "https://www.reddit.com/r/stocks.json"),
            ("reddit_investing", "Reddit r/investing", "https://www.reddit.com/r/investing.json"),
            ("reddit_securityanalysis", "Reddit r/SecurityAnalysis", "https://www.reddit.com/r/SecurityAnalysis.json")
        ]
        
        for source_id, name, url in reddit_sources:
            source = NewsSource(
                name=name,
                tier=SourceTier.TIER_4,
                base_url=url,
                scan_interval_minutes=180,  # Less frequent for social
                reliability_score=0.40  # Lower reliability
            )
            
            self.sources[source_id] = source
            self.source_clients[source_id] = RedditNewsClient(source)
    
    def get_source(self, source_id: str) -> Optional[NewsSource]:
        """Get news source by ID."""
        return self.sources.get(source_id)
    
    def get_sources_by_tier(self, tier: SourceTier) -> List[NewsSource]:
        """Get all sources for a specific tier."""
        return [source for source in self.sources.values() if source.tier == tier]
    
    def get_enabled_sources(self) -> List[NewsSource]:
        """Get all enabled sources."""
        return [source for source in self.sources.values() if source.enabled]
    
    async def fetch_articles(self, source_id: str, **kwargs) -> List[NewsArticle]:
        """Fetch articles from a specific source."""
        
        if source_id not in self.source_clients:
            self.logger.warning("source_client_not_found", source_id=source_id)
            return []
        
        try:
            client = self.source_clients[source_id]
            articles = await client.fetch_articles(**kwargs)
            
            self.logger.info("articles_fetched", 
                           source_id=source_id, 
                           article_count=len(articles))
            
            return articles
            
        except Exception as e:
            self.logger.error("article_fetch_failed", 
                            source_id=source_id, error=str(e))
            return []
    
    def add_custom_source(self, source_id: str, source: NewsSource, 
                         client: 'BaseNewsClient') -> None:
        """Add custom news source."""
        
        self.sources[source_id] = source
        self.source_clients[source_id] = client
        
        self.logger.info("custom_source_added", source_id=source_id, name=source.name)
    
    def remove_source(self, source_id: str) -> bool:
        """Remove news source."""
        
        if source_id in self.sources:
            del self.sources[source_id]
            
            if source_id in self.source_clients:
                del self.source_clients[source_id]
            
            self.logger.info("source_removed", source_id=source_id)
            return True
        
        return False
    
    def get_source_status(self) -> Dict[str, Any]:
        """Get status of all news sources."""
        
        status = {
            'total_sources': len(self.sources),
            'enabled_sources': len(self.get_enabled_sources()),
            'by_tier': {},
            'sources': {}
        }
        
        # Count by tier
        for tier in SourceTier:
            tier_sources = self.get_sources_by_tier(tier)
            status['by_tier'][tier.value] = {
                'count': len(tier_sources),
                'enabled': len([s for s in tier_sources if s.enabled])
            }
        
        # Individual source status
        for source_id, source in self.sources.items():
            status['sources'][source_id] = {
                'name': source.name,
                'tier': source.tier.value,
                'enabled': source.enabled,
                'last_scan': source.last_scan.isoformat() if source.last_scan else None,
                'reliability_score': source.reliability_score,
                'scan_interval_minutes': source.scan_interval_minutes
            }
        
        return status


class BaseNewsClient:
    """Base class for news source clients."""
    
    def __init__(self, source: NewsSource):
        self.source = source
        self.logger = logger.bind(source=source.name)
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def fetch_articles(self, **kwargs) -> List[NewsArticle]:
        """Fetch articles from source. Override in subclasses."""
        raise NotImplementedError
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()


class NewsAPIClient(BaseNewsClient):
    """Client for NewsAPI.org sources."""
    
    def __init__(self, source: NewsSource, domain: str):
        super().__init__(source)
        self.domain = domain
        self.api_key = getattr(settings, 'newsapi_key', None)
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def fetch_articles(self, query: str = None, **kwargs) -> List[NewsArticle]:
        """Fetch articles from NewsAPI."""
        
        if not self.api_key:
            self.logger.warning("newsapi_key_not_configured")
            return []
        
        params = {
            'apiKey': self.api_key,
            'domains': self.domain,
            'sortBy': 'publishedAt',
            'pageSize': 50,
            'language': 'en'
        }
        
        if query:
            params['q'] = query
        
        try:
            response = await self.client.get(self.source.base_url, params=params)
            response.raise_for_status()
            
            data = response.json()
            articles = []
            
            for item in data.get('articles', []):
                if self._is_valid_article(item):
                    article = self._convert_to_news_article(item)
                    articles.append(article)
            
            return articles
            
        except Exception as e:
            self.logger.error("newsapi_fetch_failed", error=str(e))
            return []
    
    def _is_valid_article(self, item: Dict) -> bool:
        """Check if article item is valid."""
        return (item.get('title') and 
                item.get('description') and
                item.get('url') and
                item.get('publishedAt'))
    
    def _convert_to_news_article(self, item: Dict) -> NewsArticle:
        """Convert NewsAPI item to NewsArticle."""
        
        published_at = datetime.fromisoformat(
            item['publishedAt'].replace('Z', '+00:00')
        )
        
        return NewsArticle(
            id=f"newsapi_{hash(item['url'])}",
            title=item['title'],
            content=item.get('description', ''),
            source=self.source.name,
            source_tier=self.source.tier,
            url=item['url'],
            published_at=published_at,
            author=item.get('author')
        )


class AlphaVantageNewsClient(BaseNewsClient):
    """Client for Alpha Vantage news."""
    
    def __init__(self, source: NewsSource):
        super().__init__(source)
        self.api_key = settings.api.alpha_vantage_api_key
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def fetch_articles(self, tickers: List[str] = None, **kwargs) -> List[NewsArticle]:
        """Fetch news from Alpha Vantage."""
        
        params = {
            'function': 'NEWS_SENTIMENT',
            'apikey': self.api_key
        }
        
        if tickers:
            params['tickers'] = ','.join(tickers[:10])  # Limit to 10 tickers
        
        try:
            response = await self.client.get(self.source.base_url, params=params)
            response.raise_for_status()
            
            data = response.json()
            articles = []
            
            for item in data.get('feed', []):
                article = self._convert_alpha_vantage_item(item)
                if article:
                    articles.append(article)
            
            return articles
            
        except Exception as e:
            self.logger.error("alpha_vantage_news_fetch_failed", error=str(e))
            return []
    
    def _convert_alpha_vantage_item(self, item: Dict) -> Optional[NewsArticle]:
        """Convert Alpha Vantage item to NewsArticle."""
        
        try:
            published_at = datetime.strptime(
                item['time_published'], '%Y%m%dT%H%M%S'
            )
            
            # Extract mentioned tickers
            tickers = [ticker['ticker'] for ticker in item.get('ticker_sentiment', [])]
            
            return NewsArticle(
                id=f"av_{hash(item['url'])}",
                title=item['title'],
                content=item.get('summary', ''),
                source=self.source.name,
                source_tier=self.source.tier,
                url=item['url'],
                published_at=published_at,
                mentioned_tickers=tickers,
                sentiment_score=float(item.get('overall_sentiment_score', 0))
            )
            
        except Exception as e:
            self.logger.warning("alpha_vantage_item_conversion_failed", error=str(e))
            return None


class FinnhubNewsClient(BaseNewsClient):
    """Client for Finnhub news."""
    
    def __init__(self, source: NewsSource):
        super().__init__(source)
        self.api_key = settings.api.finnhub_api_key
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def fetch_articles(self, **kwargs) -> List[NewsArticle]:
        """Fetch market news from Finnhub."""
        
        params = {
            'category': 'general',
            'token': self.api_key
        }
        
        try:
            response = await self.client.get(self.source.base_url, params=params)
            response.raise_for_status()
            
            data = response.json()
            articles = []
            
            for item in data:
                article = self._convert_finnhub_item(item)
                if article:
                    articles.append(article)
            
            return articles
            
        except Exception as e:
            self.logger.error("finnhub_news_fetch_failed", error=str(e))
            return []
    
    def _convert_finnhub_item(self, item: Dict) -> Optional[NewsArticle]:
        """Convert Finnhub item to NewsArticle."""
        
        try:
            published_at = datetime.fromtimestamp(item['datetime'])
            
            return NewsArticle(
                id=f"finnhub_{item['id']}",
                title=item['headline'],
                content=item.get('summary', ''),
                source=self.source.name,
                source_tier=self.source.tier,
                url=item['url'],
                published_at=published_at,
                tags=item.get('category', '').split(',') if item.get('category') else []
            )
            
        except Exception as e:
            self.logger.warning("finnhub_item_conversion_failed", error=str(e))
            return None


class RSSNewsClient(BaseNewsClient):
    """Client for RSS feed sources."""
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def fetch_articles(self, **kwargs) -> List[NewsArticle]:
        """Fetch articles from RSS feed."""
        
        try:
            response = await self.client.get(self.source.base_url)
            response.raise_for_status()
            
            # Parse RSS (simplified - would use proper RSS parser)
            articles = self._parse_rss_content(response.text)
            
            return articles
            
        except Exception as e:
            self.logger.error("rss_fetch_failed", error=str(e))
            return []
    
    def _parse_rss_content(self, content: str) -> List[NewsArticle]:
        """Parse RSS content (simplified implementation)."""
        
        # This is a simplified implementation
        # In production, would use feedparser or similar library
        articles = []
        
        # Mock RSS parsing
        # Would extract items, titles, descriptions, links, dates
        
        return articles


class RedditNewsClient(BaseNewsClient):
    """Client for Reddit sources."""
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def fetch_articles(self, **kwargs) -> List[NewsArticle]:
        """Fetch posts from Reddit."""
        
        try:
            headers = {'User-Agent': 'ResearchLab/1.0'}
            response = await self.client.get(self.source.base_url, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            articles = []
            
            for post in data.get('data', {}).get('children', []):
                article = self._convert_reddit_post(post['data'])
                if article:
                    articles.append(article)
            
            return articles
            
        except Exception as e:
            self.logger.error("reddit_fetch_failed", error=str(e))
            return []
    
    def _convert_reddit_post(self, post: Dict) -> Optional[NewsArticle]:
        """Convert Reddit post to NewsArticle."""
        
        try:
            # Skip non-relevant posts
            if post.get('is_self') and not post.get('selftext'):
                return None
            
            published_at = datetime.fromtimestamp(post['created_utc'])
            
            return NewsArticle(
                id=f"reddit_{post['id']}",
                title=post['title'],
                content=post.get('selftext', '')[:1000],  # Limit content
                source=self.source.name,
                source_tier=self.source.tier,
                url=f"https://reddit.com{post['permalink']}",
                published_at=published_at,
                author=post.get('author'),
                tags=[post.get('subreddit', '')]
            )
            
        except Exception as e:
            self.logger.warning("reddit_post_conversion_failed", error=str(e))
            return None