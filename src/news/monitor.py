"""News monitoring system with tiered sources and real-time alerts."""

import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Any
from enum import Enum
from dataclasses import dataclass, field
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import DatabaseManager
from src.data.clients.data_cache import DataCache

logger = structlog.get_logger()


class SourceTier(Enum):
    """News source tiers by reliability and priority."""
    TIER_1 = "tier_1"  # Premium: WSJ, Reuters, Bloomberg
    TIER_2 = "tier_2"  # Major: CNN, BBC, Financial Times  
    TIER_3 = "tier_3"  # General: Yahoo Finance, MarketWatch
    TIER_4 = "tier_4"  # Social: Reddit, Twitter


class AlertSeverity(Enum):
    """Alert severity levels."""
    CRITICAL = "critical"    # Breaking news, major events
    HIGH = "high"           # Significant company news
    MEDIUM = "medium"       # Relevant industry news
    LOW = "low"             # General market news


@dataclass
class NewsArticle:
    """Individual news article."""
    id: str
    title: str
    content: str
    source: str
    source_tier: SourceTier
    url: str
    published_at: datetime
    author: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    mentioned_companies: List[str] = field(default_factory=list)
    mentioned_tickers: List[str] = field(default_factory=list)
    sentiment_score: Optional[float] = None
    relevance_score: Optional[float] = None
    
    @property
    def content_hash(self) -> str:
        """Generate unique hash for content deduplication."""
        content_text = f"{self.title}{self.content}{self.source}"
        return hashlib.md5(content_text.encode()).hexdigest()


@dataclass 
class NewsSource:
    """News source configuration."""
    name: str
    tier: SourceTier
    base_url: str
    api_key: Optional[str] = None
    rate_limit: int = 100  # requests per hour
    enabled: bool = True
    keywords: List[str] = field(default_factory=list)
    company_filters: List[str] = field(default_factory=list)
    
    # Scanning configuration
    scan_interval_minutes: int = 60  # Default hourly
    last_scan: Optional[datetime] = None
    articles_per_scan: int = 50
    
    # Quality metrics
    reliability_score: float = 1.0  # 0.0 - 1.0
    historical_accuracy: float = 1.0


@dataclass
class NewsAlert:
    """News alert for significant events."""
    id: str
    article_id: str
    title: str
    summary: str
    severity: AlertSeverity
    companies: List[str]
    tickers: List[str]
    created_at: datetime
    source_tier: SourceTier
    relevance_score: float
    sentiment_score: float
    
    # Delivery configuration
    email_sent: bool = False
    webhook_sent: bool = False
    delivered_at: Optional[datetime] = None


class NewsMonitor:
    """News monitoring system with tiered sources and real-time scanning."""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.cache = DataCache()
        self.logger = logger.bind(component="news_monitor")
        
        # Active sources by tier
        self.sources: Dict[str, NewsSource] = {}
        self.active_scans: Set[str] = set()
        
        # Monitoring state
        self.is_running = False
        self.scan_tasks: Dict[str, asyncio.Task] = {}
        
        # Article storage and deduplication
        self.seen_articles: Set[str] = set()  # Content hashes
        self.recent_articles: List[NewsArticle] = []
        self.max_recent_articles = 10000
        
        # Alert configuration
        self.alert_thresholds = {
            AlertSeverity.CRITICAL: {'relevance': 0.9, 'tier_weight': 2.0},
            AlertSeverity.HIGH: {'relevance': 0.7, 'tier_weight': 1.5},
            AlertSeverity.MEDIUM: {'relevance': 0.5, 'tier_weight': 1.0},
            AlertSeverity.LOW: {'relevance': 0.3, 'tier_weight': 0.5}
        }
        
        # Initialize default sources
        self._initialize_default_sources()
        
    def _initialize_default_sources(self):
        """Initialize default news sources by tier."""
        
        # Tier 1 - Premium sources
        self.sources['reuters'] = NewsSource(
            name="Reuters",
            tier=SourceTier.TIER_1,
            base_url="https://newsapi.org/v2/everything",
            scan_interval_minutes=30,  # More frequent for premium
            reliability_score=0.95,
            keywords=['earnings', 'merger', 'acquisition', 'bankruptcy', 'IPO', 'dividend']
        )
        
        self.sources['wsj'] = NewsSource(
            name="Wall Street Journal",
            tier=SourceTier.TIER_1, 
            base_url="https://newsapi.org/v2/everything",
            scan_interval_minutes=30,
            reliability_score=0.98
        )
        
        # Tier 2 - Major sources
        self.sources['cnbc'] = NewsSource(
            name="CNBC",
            tier=SourceTier.TIER_2,
            base_url="https://newsapi.org/v2/everything",
            scan_interval_minutes=60,
            reliability_score=0.85
        )
        
        self.sources['financial_times'] = NewsSource(
            name="Financial Times",
            tier=SourceTier.TIER_2,
            base_url="https://newsapi.org/v2/everything", 
            scan_interval_minutes=60,
            reliability_score=0.90
        )
        
        # Tier 3 - General financial
        self.sources['yahoo_finance'] = NewsSource(
            name="Yahoo Finance",
            tier=SourceTier.TIER_3,
            base_url="https://newsapi.org/v2/everything",
            scan_interval_minutes=90,
            reliability_score=0.75
        )
        
        self.sources['marketwatch'] = NewsSource(
            name="MarketWatch",
            tier=SourceTier.TIER_3,
            base_url="https://newsapi.org/v2/everything",
            scan_interval_minutes=90,
            reliability_score=0.70
        )
        
    async def start_monitoring(self, companies: List[str] = None, 
                             tickers: List[str] = None) -> None:
        """Start news monitoring for specified companies/tickers."""
        
        if self.is_running:
            self.logger.warning("news_monitoring_already_running")
            return
        
        self.is_running = True
        self.logger.info("starting_news_monitoring", 
                        companies=len(companies or []),
                        tickers=len(tickers or []))
        
        # Update source filters
        if companies:
            for source in self.sources.values():
                source.company_filters.extend(companies)
        
        # Start scanning tasks for each source
        for source_id, source in self.sources.items():
            if source.enabled:
                task = asyncio.create_task(
                    self._run_source_monitor(source_id, source)
                )
                self.scan_tasks[source_id] = task
        
        self.logger.info("news_monitoring_started", 
                        active_sources=len(self.scan_tasks))
    
    async def stop_monitoring(self) -> None:
        """Stop news monitoring and cleanup tasks."""
        
        if not self.is_running:
            return
        
        self.is_running = False
        self.logger.info("stopping_news_monitoring")
        
        # Cancel all scanning tasks
        for source_id, task in self.scan_tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self.scan_tasks.clear()
        self.active_scans.clear()
        
        self.logger.info("news_monitoring_stopped")
    
    async def _run_source_monitor(self, source_id: str, source: NewsSource) -> None:
        """Run continuous monitoring for a specific news source."""
        
        self.logger.info("starting_source_monitor", source=source.name, tier=source.tier.value)
        
        while self.is_running:
            try:
                if source_id not in self.active_scans:
                    self.active_scans.add(source_id)
                    
                    await self._scan_news_source(source)
                    source.last_scan = datetime.now()
                    
                    self.active_scans.discard(source_id)
                
                # Wait for next scan interval
                await asyncio.sleep(source.scan_interval_minutes * 60)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("source_monitor_error", 
                                source=source.name, error=str(e))
                # Back off on error
                await asyncio.sleep(300)  # 5 minutes
    
    async def _scan_news_source(self, source: NewsSource) -> List[NewsArticle]:
        """Scan a specific news source for new articles."""
        
        self.logger.info("scanning_news_source", 
                        source=source.name, 
                        tier=source.tier.value)
        
        try:
            # Build search query
            query_terms = []
            
            # Add company filters
            if source.company_filters:
                query_terms.extend(source.company_filters[:10])  # Limit query length
            
            # Add keywords for financial relevance
            if source.keywords:
                query_terms.extend(source.keywords[:5])
            
            query = " OR ".join(query_terms) if query_terms else "stocks market finance"
            
            # Mock API call (would be replaced with actual news API integration)
            articles = await self._fetch_articles_from_api(source, query)
            
            # Process and filter articles
            new_articles = []
            for article in articles:
                if self._is_new_article(article) and self._is_relevant_article(article):
                    new_articles.append(article)
                    self.recent_articles.append(article)
                    self.seen_articles.add(article.content_hash)
            
            # Cleanup old articles
            self._cleanup_old_articles()
            
            # Generate alerts for significant articles
            for article in new_articles:
                await self._evaluate_article_for_alerts(article)
            
            self.logger.info("news_scan_completed",
                           source=source.name,
                           new_articles=len(new_articles),
                           total_recent=len(self.recent_articles))
            
            return new_articles
            
        except Exception as e:
            self.logger.error("news_scan_failed", 
                            source=source.name, error=str(e))
            return []
    
    async def _fetch_articles_from_api(self, source: NewsSource, query: str) -> List[NewsArticle]:
        """Fetch articles from news API (mock implementation)."""
        
        # This would be replaced with actual API calls to:
        # - NewsAPI.org
        # - Alpha Vantage News
        # - Finnhub News
        # - RSS feeds
        # - Direct API integrations
        
        # Mock articles for testing
        mock_articles = []
        
        for i in range(3):  # Generate a few mock articles
            article_id = str(uuid.uuid4())
            
            mock_articles.append(NewsArticle(
                id=article_id,
                title=f"Mock {source.name} Article {i+1}: Market Update",
                content=f"This is a mock article from {source.name} about market conditions. "
                       f"Contains relevant financial information and company updates. Query: {query}",
                source=source.name,
                source_tier=source.tier,
                url=f"https://example.com/article/{article_id}",
                published_at=datetime.now() - timedelta(minutes=i*10),
                tags=['finance', 'market', 'stocks'],
                mentioned_companies=['AAPL', 'GOOGL', 'MSFT'] if i == 0 else [],
                mentioned_tickers=['AAPL', 'GOOGL'] if i == 0 else []
            ))
        
        return mock_articles
    
    def _is_new_article(self, article: NewsArticle) -> bool:
        """Check if article is new (not seen before)."""
        return article.content_hash not in self.seen_articles
    
    def _is_relevant_article(self, article: NewsArticle) -> bool:
        """Check if article is relevant to monitored companies/topics."""
        
        # Check for company mentions
        if article.mentioned_companies or article.mentioned_tickers:
            return True
        
        # Check for financial keywords in title/content
        financial_keywords = {
            'earnings', 'revenue', 'profit', 'loss', 'acquisition', 'merger',
            'IPO', 'dividend', 'buyback', 'bankruptcy', 'guidance', 'forecast',
            'analyst', 'upgrade', 'downgrade', 'price target', 'recommendation'
        }
        
        text = f"{article.title} {article.content}".lower()
        
        for keyword in financial_keywords:
            if keyword in text:
                return True
        
        return False
    
    def _cleanup_old_articles(self) -> None:
        """Remove old articles to prevent memory bloat."""
        
        if len(self.recent_articles) > self.max_recent_articles:
            # Keep only the most recent articles
            self.recent_articles = self.recent_articles[-self.max_recent_articles:]
            
            # Rebuild seen_articles set from remaining articles
            self.seen_articles = {article.content_hash for article in self.recent_articles}
    
    async def _evaluate_article_for_alerts(self, article: NewsArticle) -> Optional[NewsAlert]:
        """Evaluate article and generate alert if significant."""
        
        try:
            # Calculate relevance score (simplified)
            relevance_score = self._calculate_relevance_score(article)
            
            # Calculate sentiment score (would use actual sentiment analysis)
            sentiment_score = self._mock_sentiment_analysis(article)
            
            # Determine alert severity
            severity = self._determine_alert_severity(article, relevance_score)
            
            if severity is None:
                return None  # Not significant enough for alert
            
            # Create alert
            alert = NewsAlert(
                id=str(uuid.uuid4()),
                article_id=article.id,
                title=f"News Alert: {article.title[:100]}...",
                summary=self._generate_article_summary(article),
                severity=severity,
                companies=article.mentioned_companies,
                tickers=article.mentioned_tickers,
                created_at=datetime.now(),
                source_tier=article.source_tier,
                relevance_score=relevance_score,
                sentiment_score=sentiment_score
            )
            
            # Send alert
            await self._send_alert(alert)
            
            self.logger.info("news_alert_generated",
                           alert_id=alert.id,
                           severity=severity.value,
                           relevance=relevance_score,
                           companies=len(article.mentioned_companies))
            
            return alert
            
        except Exception as e:
            self.logger.error("alert_evaluation_failed", 
                            article_id=article.id, error=str(e))
            return None
    
    def _calculate_relevance_score(self, article: NewsArticle) -> float:
        """Calculate article relevance score (0.0 - 1.0)."""
        
        score = 0.0
        
        # Source tier bonus
        tier_weights = {
            SourceTier.TIER_1: 0.4,
            SourceTier.TIER_2: 0.3,
            SourceTier.TIER_3: 0.2,
            SourceTier.TIER_4: 0.1
        }
        score += tier_weights.get(article.source_tier, 0.1)
        
        # Company mention bonus
        if article.mentioned_companies:
            score += 0.3
        
        if article.mentioned_tickers:
            score += 0.2
        
        # Keyword relevance
        high_impact_keywords = {
            'acquisition', 'merger', 'earnings', 'bankruptcy', 'IPO',
            'guidance', 'lawsuit', 'FDA approval', 'CEO', 'scandal'
        }
        
        text = f"{article.title} {article.content}".lower()
        
        for keyword in high_impact_keywords:
            if keyword in text:
                score += 0.1
                break
        
        return min(1.0, score)
    
    def _mock_sentiment_analysis(self, article: NewsArticle) -> float:
        """Mock sentiment analysis (would use actual NLP)."""
        
        # Simple keyword-based sentiment
        positive_words = ['growth', 'profit', 'success', 'strong', 'beat', 'upgrade', 'buy']
        negative_words = ['loss', 'decline', 'weak', 'miss', 'downgrade', 'sell', 'warning']
        
        text = f"{article.title} {article.content}".lower()
        
        positive_count = sum(1 for word in positive_words if word in text)
        negative_count = sum(1 for word in negative_words if word in text)
        
        if positive_count > negative_count:
            return 0.7  # Positive
        elif negative_count > positive_count:
            return 0.3  # Negative
        else:
            return 0.5  # Neutral
    
    def _determine_alert_severity(self, article: NewsArticle, relevance_score: float) -> Optional[AlertSeverity]:
        """Determine appropriate alert severity based on article characteristics."""
        
        # Source tier weighting
        tier_multiplier = {
            SourceTier.TIER_1: 1.0,
            SourceTier.TIER_2: 0.8,
            SourceTier.TIER_3: 0.6,
            SourceTier.TIER_4: 0.4
        }.get(article.source_tier, 0.4)
        
        weighted_relevance = relevance_score * tier_multiplier
        
        # Check against thresholds
        for severity in [AlertSeverity.CRITICAL, AlertSeverity.HIGH, 
                        AlertSeverity.MEDIUM, AlertSeverity.LOW]:
            threshold = self.alert_thresholds[severity]
            
            if weighted_relevance >= threshold['relevance']:
                return severity
        
        return None  # Below threshold
    
    def _generate_article_summary(self, article: NewsArticle) -> str:
        """Generate a concise summary of the article."""
        
        # Simple summary (would use actual summarization)
        summary_parts = []
        
        if article.mentioned_companies:
            companies_str = ", ".join(article.mentioned_companies[:3])
            summary_parts.append(f"Companies: {companies_str}")
        
        if article.mentioned_tickers:
            tickers_str = ", ".join(article.mentioned_tickers[:3])
            summary_parts.append(f"Tickers: {tickers_str}")
        
        # Add first sentence of content
        first_sentence = article.content.split('.')[0][:200]
        summary_parts.append(first_sentence)
        
        return " | ".join(summary_parts)
    
    async def _send_alert(self, alert: NewsAlert) -> None:
        """Send alert via configured channels."""
        
        try:
            # Email alerts (mock)
            if settings.app.environment != "testing":
                self.logger.info("sending_email_alert", 
                               alert_id=alert.id,
                               severity=alert.severity.value)
                # Would integrate with email service
                alert.email_sent = True
            
            # Webhook alerts (mock)
            self.logger.info("sending_webhook_alert",
                           alert_id=alert.id,
                           companies=len(alert.companies))
            # Would send HTTP POST to webhook URL
            alert.webhook_sent = True
            
            alert.delivered_at = datetime.now()
            
        except Exception as e:
            self.logger.error("alert_delivery_failed", 
                            alert_id=alert.id, error=str(e))
    
    async def get_recent_articles(self, hours: int = 24, 
                                source_tier: Optional[SourceTier] = None,
                                companies: Optional[List[str]] = None) -> List[NewsArticle]:
        """Get recent articles with optional filtering."""
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        filtered_articles = []
        
        for article in self.recent_articles:
            # Time filter
            if article.published_at < cutoff_time:
                continue
            
            # Source tier filter
            if source_tier and article.source_tier != source_tier:
                continue
            
            # Company filter
            if companies and not any(company in article.mentioned_companies 
                                   for company in companies):
                continue
            
            filtered_articles.append(article)
        
        # Sort by publication time (newest first)
        return sorted(filtered_articles, key=lambda x: x.published_at, reverse=True)
    
    async def get_monitoring_status(self) -> Dict[str, Any]:
        """Get current monitoring status and statistics."""
        
        active_sources = sum(1 for source in self.sources.values() if source.enabled)
        
        # Calculate scanning statistics
        source_stats = {}
        for source_id, source in self.sources.items():
            source_stats[source_id] = {
                'name': source.name,
                'tier': source.tier.value,
                'enabled': source.enabled,
                'last_scan': source.last_scan.isoformat() if source.last_scan else None,
                'scan_interval_minutes': source.scan_interval_minutes,
                'is_scanning': source_id in self.active_scans
            }
        
        return {
            'is_running': self.is_running,
            'active_sources': active_sources,
            'total_sources': len(self.sources),
            'recent_articles_count': len(self.recent_articles),
            'seen_articles_count': len(self.seen_articles),
            'active_scan_tasks': len(self.scan_tasks),
            'source_details': source_stats
        }
    
    def add_source(self, source: NewsSource) -> None:
        """Add a new news source to monitoring."""
        
        self.sources[source.name.lower().replace(' ', '_')] = source
        
        self.logger.info("news_source_added", 
                        source=source.name, tier=source.tier.value)
    
    def remove_source(self, source_id: str) -> bool:
        """Remove a news source from monitoring."""
        
        if source_id in self.sources:
            # Cancel any active task
            if source_id in self.scan_tasks:
                self.scan_tasks[source_id].cancel()
                del self.scan_tasks[source_id]
            
            del self.sources[source_id]
            self.active_scans.discard(source_id)
            
            self.logger.info("news_source_removed", source_id=source_id)
            return True
        
        return False
    
    def configure_alerts(self, severity: AlertSeverity, 
                        relevance_threshold: float,
                        tier_weight: float) -> None:
        """Configure alert thresholds for a severity level."""
        
        self.alert_thresholds[severity] = {
            'relevance': relevance_threshold,
            'tier_weight': tier_weight
        }
        
        self.logger.info("alert_threshold_configured",
                        severity=severity.value,
                        relevance_threshold=relevance_threshold)