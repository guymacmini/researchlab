"""Tests for news monitoring system."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from src.news.monitor import (
    NewsMonitor, NewsSource, NewsArticle, NewsAlert,
    SourceTier, AlertSeverity
)
from src.news.analyzer import NewsAnalyzer, NewsRelevance, NewsCategory
from src.news.sources import NewsSourceRegistry


class TestNewsMonitor:
    """Test cases for News Monitor."""

    @pytest.fixture
    def monitor(self):
        """Create news monitor for testing."""
        with patch('src.news.monitor.DatabaseManager'):
            with patch('src.news.monitor.DataCache'):
                return NewsMonitor()

    @pytest.fixture
    def sample_news_source(self):
        """Sample news source for testing."""
        return NewsSource(
            name="Test Financial News",
            tier=SourceTier.TIER_2,
            base_url="https://api.test.com/news",
            scan_interval_minutes=60,
            reliability_score=0.85,
            keywords=['earnings', 'stocks', 'market'],
            company_filters=['AAPL', 'GOOGL']
        )

    @pytest.fixture
    def sample_news_article(self):
        """Sample news article for testing."""
        return NewsArticle(
            id="test_article_123",
            title="Apple Reports Strong Q4 Earnings",
            content="Apple Inc. reported strong fourth quarter earnings with revenue exceeding expectations. The tech giant showed robust growth in iPhone sales and services revenue.",
            source="Test Financial News",
            source_tier=SourceTier.TIER_2,
            url="https://example.com/apple-earnings",
            published_at=datetime.now(),
            mentioned_companies=["Apple Inc."],
            mentioned_tickers=["AAPL"],
            tags=["earnings", "technology", "quarterly-results"]
        )

    def test_monitor_initialization(self, monitor):
        """Test monitor initializes correctly."""
        assert not monitor.is_running
        assert len(monitor.sources) > 0  # Should have default sources
        assert monitor.max_recent_articles == 10000
        assert AlertSeverity.CRITICAL in monitor.alert_thresholds

    @pytest.mark.asyncio
    async def test_start_monitoring(self, monitor):
        """Test starting news monitoring."""
        
        companies = ['Apple Inc.', 'Google LLC']
        tickers = ['AAPL', 'GOOGL']
        
        with patch.object(monitor, '_run_source_monitor', new_callable=AsyncMock) as mock_run:
            await monitor.start_monitoring(companies, tickers)
            
            assert monitor.is_running is True
            assert len(monitor.scan_tasks) > 0
            
            # Check that source filters were updated
            for source in monitor.sources.values():
                if source.enabled:
                    assert any(company in source.company_filters for company in companies)

    @pytest.mark.asyncio
    async def test_stop_monitoring(self, monitor):
        """Test stopping news monitoring."""
        
        # Start monitoring first
        monitor.is_running = True
        
        # Mock some running tasks
        mock_task1 = AsyncMock()
        mock_task2 = AsyncMock()
        monitor.scan_tasks = {'source1': mock_task1, 'source2': mock_task2}
        
        await monitor.stop_monitoring()
        
        assert monitor.is_running is False
        assert len(monitor.scan_tasks) == 0
        assert len(monitor.active_scans) == 0
        
        mock_task1.cancel.assert_called_once()
        mock_task2.cancel.assert_called_once()

    def test_is_new_article(self, monitor, sample_news_article):
        """Test new article detection."""
        
        # Article should be new initially
        assert monitor._is_new_article(sample_news_article) is True
        
        # Add to seen articles
        monitor.seen_articles.add(sample_news_article.content_hash)
        
        # Should not be new anymore
        assert monitor._is_new_article(sample_news_article) is False

    def test_is_relevant_article(self, monitor, sample_news_article):
        """Test article relevance detection."""
        
        # Article with company mentions should be relevant
        assert monitor._is_relevant_article(sample_news_article) is True
        
        # Article without company mentions but with financial keywords
        article_no_companies = NewsArticle(
            id="test_2",
            title="Market Analysis: Earnings Season Preview",
            content="Analysts expect strong earnings results across major sectors this quarter.",
            source="Test News",
            source_tier=SourceTier.TIER_3,
            url="https://example.com/market-analysis",
            published_at=datetime.now(),
            mentioned_companies=[],
            mentioned_tickers=[]
        )
        
        assert monitor._is_relevant_article(article_no_companies) is True
        
        # Irrelevant article
        irrelevant_article = NewsArticle(
            id="test_3",
            title="Weather Update",
            content="Today will be sunny with mild temperatures.",
            source="Test News",
            source_tier=SourceTier.TIER_3,
            url="https://example.com/weather",
            published_at=datetime.now(),
            mentioned_companies=[],
            mentioned_tickers=[]
        )
        
        assert monitor._is_relevant_article(irrelevant_article) is False

    def test_cleanup_old_articles(self, monitor):
        """Test cleanup of old articles."""
        
        # Add more than max articles
        for i in range(monitor.max_recent_articles + 100):
            article = NewsArticle(
                id=f"test_{i}",
                title=f"Test Article {i}",
                content=f"Content {i}",
                source="Test",
                source_tier=SourceTier.TIER_3,
                url=f"https://example.com/{i}",
                published_at=datetime.now()
            )
            monitor.recent_articles.append(article)
            monitor.seen_articles.add(article.content_hash)
        
        initial_count = len(monitor.recent_articles)
        monitor._cleanup_old_articles()
        
        assert len(monitor.recent_articles) == monitor.max_recent_articles
        assert len(monitor.recent_articles) < initial_count
        assert len(monitor.seen_articles) == len(monitor.recent_articles)

    def test_calculate_relevance_score(self, monitor, sample_news_article):
        """Test relevance score calculation."""
        
        score = monitor._calculate_relevance_score(sample_news_article)
        
        assert 0.0 <= score <= 1.0
        assert score > 0.5  # Should be high due to company mentions and source tier

    def test_mock_sentiment_analysis(self, monitor):
        """Test mock sentiment analysis."""
        
        # Positive content
        positive_article = NewsArticle(
            id="positive_test",
            title="Strong Growth and Profit Beat Expectations",
            content="Company shows strong growth with profit beating analyst expectations. Stock upgrade recommended.",
            source="Test",
            source_tier=SourceTier.TIER_2,
            url="https://example.com/positive",
            published_at=datetime.now()
        )
        
        sentiment = monitor._mock_sentiment_analysis(positive_article)
        assert sentiment > 0.5  # Should be positive
        
        # Negative content
        negative_article = NewsArticle(
            id="negative_test",
            title="Company Reports Loss and Weak Performance",
            content="Significant loss reported with weak performance missing analyst estimates. Stock downgrade warning.",
            source="Test",
            source_tier=SourceTier.TIER_2,
            url="https://example.com/negative",
            published_at=datetime.now()
        )
        
        sentiment = monitor._mock_sentiment_analysis(negative_article)
        assert sentiment < 0.5  # Should be negative

    def test_determine_alert_severity(self, monitor, sample_news_article):
        """Test alert severity determination."""
        
        # High relevance should trigger alert
        relevance_score = 0.8
        severity = monitor._determine_alert_severity(sample_news_article, relevance_score)
        
        assert severity is not None
        assert severity in [AlertSeverity.CRITICAL, AlertSeverity.HIGH, AlertSeverity.MEDIUM]
        
        # Low relevance should not trigger alert
        low_relevance = 0.1
        severity = monitor._determine_alert_severity(sample_news_article, low_relevance)
        
        assert severity is None

    def test_generate_article_summary(self, monitor, sample_news_article):
        """Test article summary generation."""
        
        summary = monitor._generate_article_summary(sample_news_article)
        
        assert isinstance(summary, str)
        assert len(summary) > 0
        assert "AAPL" in summary  # Should include tickers
        assert "Apple Inc." in summary  # Should include companies

    @pytest.mark.asyncio
    async def test_evaluate_article_for_alerts(self, monitor, sample_news_article):
        """Test article evaluation for alerts."""
        
        with patch.object(monitor, '_send_alert', new_callable=AsyncMock) as mock_send:
            alert = await monitor._evaluate_article_for_alerts(sample_news_article)
            
            if alert:  # Alert may or may not be generated based on thresholds
                assert alert.article_id == sample_news_article.id
                assert alert.severity in AlertSeverity
                assert 0.0 <= alert.relevance_score <= 1.0
                mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_articles_from_api_mock(self, monitor, sample_news_source):
        """Test mock article fetching."""
        
        articles = await monitor._fetch_articles_from_api(sample_news_source, "test query")
        
        assert isinstance(articles, list)
        assert len(articles) > 0
        
        for article in articles:
            assert isinstance(article, NewsArticle)
            assert article.source == sample_news_source.name
            assert article.source_tier == sample_news_source.tier

    @pytest.mark.asyncio
    async def test_get_recent_articles(self, monitor):
        """Test getting recent articles with filters."""
        
        # Add test articles
        now = datetime.now()
        
        articles = [
            NewsArticle(
                id="recent_1",
                title="Recent Article 1",
                content="Content 1",
                source="Test",
                source_tier=SourceTier.TIER_1,
                url="https://example.com/1",
                published_at=now - timedelta(hours=1),
                mentioned_companies=["Apple Inc."]
            ),
            NewsArticle(
                id="old_1", 
                title="Old Article",
                content="Content old",
                source="Test",
                source_tier=SourceTier.TIER_2,
                url="https://example.com/old",
                published_at=now - timedelta(hours=30),
                mentioned_companies=["Microsoft Corp."]
            )
        ]
        
        monitor.recent_articles.extend(articles)
        
        # Test time filter
        recent = await monitor.get_recent_articles(hours=24)
        assert len(recent) == 1
        assert recent[0].id == "recent_1"
        
        # Test tier filter
        tier1 = await monitor.get_recent_articles(hours=48, source_tier=SourceTier.TIER_1)
        assert len(tier1) == 1
        assert tier1[0].source_tier == SourceTier.TIER_1
        
        # Test company filter
        apple_news = await monitor.get_recent_articles(hours=48, companies=["Apple Inc."])
        assert len(apple_news) == 1
        assert "Apple Inc." in apple_news[0].mentioned_companies

    @pytest.mark.asyncio
    async def test_get_monitoring_status(self, monitor):
        """Test getting monitoring status."""
        
        status = await monitor.get_monitoring_status()
        
        assert isinstance(status, dict)
        assert 'is_running' in status
        assert 'active_sources' in status
        assert 'total_sources' in status
        assert 'recent_articles_count' in status
        assert 'source_details' in status
        
        assert isinstance(status['source_details'], dict)

    def test_add_source(self, monitor, sample_news_source):
        """Test adding custom news source."""
        
        initial_count = len(monitor.sources)
        monitor.add_source(sample_news_source)
        
        assert len(monitor.sources) == initial_count + 1
        
        source_id = sample_news_source.name.lower().replace(' ', '_')
        assert source_id in monitor.sources
        assert monitor.sources[source_id] == sample_news_source

    def test_remove_source(self, monitor):
        """Test removing news source."""
        
        # Get existing source ID
        source_ids = list(monitor.sources.keys())
        if source_ids:
            source_id = source_ids[0]
            initial_count = len(monitor.sources)
            
            result = monitor.remove_source(source_id)
            
            assert result is True
            assert len(monitor.sources) == initial_count - 1
            assert source_id not in monitor.sources
        
        # Test removing non-existent source
        result = monitor.remove_source("non_existent")
        assert result is False

    def test_configure_alerts(self, monitor):
        """Test alert configuration."""
        
        initial_threshold = monitor.alert_thresholds[AlertSeverity.HIGH]['relevance']
        
        monitor.configure_alerts(AlertSeverity.HIGH, 0.9, 2.0)
        
        assert monitor.alert_thresholds[AlertSeverity.HIGH]['relevance'] == 0.9
        assert monitor.alert_thresholds[AlertSeverity.HIGH]['tier_weight'] == 2.0
        assert monitor.alert_thresholds[AlertSeverity.HIGH]['relevance'] != initial_threshold


class TestNewsAnalyzer:
    """Test cases for News Analyzer."""

    @pytest.fixture
    def analyzer(self):
        """Create news analyzer for testing."""
        return NewsAnalyzer()

    @pytest.fixture
    def sample_article_with_companies(self):
        """Sample article with company mentions."""
        return NewsArticle(
            id="analysis_test_1",
            title="Apple Inc. and Google LLC Report Earnings",
            content="Apple Inc. (AAPL) reported quarterly earnings of $1.20 per share, beating analyst estimates of $1.15. Revenue came in at $95 billion, up 5% year-over-year. Google LLC (GOOGL) also announced strong results with revenue growth driven by cloud services.",
            source="Financial Times",
            source_tier=SourceTier.TIER_1,
            url="https://example.com/earnings-report",
            published_at=datetime.now()
        )

    def test_analyzer_initialization(self, analyzer):
        """Test analyzer initializes correctly."""
        assert len(analyzer.earnings_keywords) > 0
        assert len(analyzer.acquisition_keywords) > 0
        assert len(analyzer.positive_indicators) > 0
        assert len(analyzer.negative_indicators) > 0

    @pytest.mark.asyncio
    async def test_analyze_article(self, analyzer, sample_article_with_companies):
        """Test comprehensive article analysis."""
        
        target_companies = ["Apple Inc.", "Google LLC"]
        target_tickers = ["AAPL", "GOOGL"]
        
        analysis = await analyzer.analyze_article(
            sample_article_with_companies, 
            target_companies, 
            target_tickers
        )
        
        assert analysis.article_id == sample_article_with_companies.id
        assert analysis.relevance in NewsRelevance
        assert analysis.category in NewsCategory
        assert 0.0 <= analysis.confidence <= 1.0
        assert -1.0 <= analysis.overall_sentiment <= 1.0
        assert isinstance(analysis.company_mentions, list)
        assert isinstance(analysis.key_phrases, list)
        assert isinstance(analysis.financial_metrics, dict)

    def test_extract_company_mentions(self, analyzer, sample_article_with_companies):
        """Test company mention extraction."""
        
        mentions = analyzer._extract_company_mentions(sample_article_with_companies.content)
        
        assert len(mentions) > 0
        
        # Check for expected mentions
        mentioned_names = [m.company_name for m in mentions]
        mentioned_tickers = [m.ticker for m in mentions if m.ticker]
        
        assert any("Apple" in name or name == "AAPL" for name in mentioned_names + mentioned_tickers)

    def test_determine_relevance(self, analyzer, sample_article_with_companies):
        """Test relevance determination."""
        
        # Mock company mentions
        company_mentions = [
            MagicMock(company_name="Apple Inc.", ticker="AAPL"),
            MagicMock(company_name="Google LLC", ticker="GOOGL")
        ]
        
        relevance = analyzer._determine_relevance(
            sample_article_with_companies,
            company_mentions,
            ["Apple Inc."],
            ["AAPL"]
        )
        
        assert relevance in [NewsRelevance.CRITICAL, NewsRelevance.HIGH, NewsRelevance.MEDIUM]

    def test_categorize_news(self, analyzer):
        """Test news categorization."""
        
        # Earnings news
        earnings_category = analyzer._categorize_news(
            "Q4 Earnings Report",
            "Company reported earnings per share of $2.50, beating estimates."
        )
        assert earnings_category == NewsCategory.EARNINGS
        
        # Acquisition news
        acquisition_category = analyzer._categorize_news(
            "Major Acquisition Announced",
            "Company announces acquisition of competitor for $10 billion."
        )
        assert acquisition_category == NewsCategory.ACQUISITION
        
        # Management news
        management_category = analyzer._categorize_news(
            "New CEO Appointed",
            "Board of directors appoints new chief executive officer."
        )
        assert management_category == NewsCategory.MANAGEMENT

    def test_analyze_sentiment(self, analyzer):
        """Test sentiment analysis."""
        
        # Positive content
        positive_sentiment, confidence = analyzer._analyze_sentiment(
            "Strong growth, excellent profits, outstanding performance, beating expectations significantly."
        )
        assert positive_sentiment > 0
        assert 0.0 <= confidence <= 1.0
        
        # Negative content
        negative_sentiment, confidence = analyzer._analyze_sentiment(
            "Significant losses, poor performance, disappointing results, missing estimates badly."
        )
        assert negative_sentiment < 0
        assert 0.0 <= confidence <= 1.0

    def test_extract_financial_metrics(self, analyzer):
        """Test financial metrics extraction."""
        
        content = """
        Company reported revenue of $95.5 billion, up from $89.2 billion last year.
        Earnings per share came in at $1.20, beating the consensus estimate of $1.15.
        Analysts raised price target to $180 from $165.
        Q4 2023 results exceeded expectations.
        """
        
        metrics = analyzer._extract_financial_metrics(content)
        
        assert isinstance(metrics, dict)
        
        # Check for extracted metrics (may vary based on regex patterns)
        if 'revenue_mentions' in metrics:
            assert len(metrics['revenue_mentions']) > 0
        
        if 'eps_mentions' in metrics:
            assert len(metrics['eps_mentions']) > 0

    def test_calculate_urgency_score(self, analyzer, sample_article_with_companies):
        """Test urgency score calculation."""
        
        urgency = analyzer._calculate_urgency_score(sample_article_with_companies)
        
        assert 0.0 <= urgency <= 1.0
        
        # Recent article from tier 1 source should have higher urgency
        assert urgency > 0.3

    def test_extract_key_phrases(self, analyzer, sample_article_with_companies):
        """Test key phrase extraction."""
        
        phrases = analyzer._extract_key_phrases(sample_article_with_companies.content)
        
        assert isinstance(phrases, list)
        # May be empty depending on content and keyword matching

    def test_update_company_mappings(self, analyzer):
        """Test company mapping updates."""
        
        mappings = [
            ("Apple Inc.", "AAPL"),
            ("Microsoft Corporation", "MSFT"),
            ("Alphabet Inc.", "GOOGL")
        ]
        
        analyzer.update_company_mappings(mappings)
        
        assert analyzer.company_ticker_map["Apple Inc."] == "AAPL"
        assert analyzer.ticker_company_map["AAPL"] == "Apple Inc."
        assert analyzer.company_ticker_map["Microsoft Corporation"] == "MSFT"

    @pytest.mark.asyncio
    async def test_batch_analyze_articles(self, analyzer):
        """Test batch article analysis."""
        
        articles = [
            NewsArticle(
                id="batch_1",
                title="Tech Earnings Strong",
                content="Technology companies report strong earnings.",
                source="Test",
                source_tier=SourceTier.TIER_2,
                url="https://example.com/1",
                published_at=datetime.now()
            ),
            NewsArticle(
                id="batch_2",
                title="Market Update",
                content="Stock market shows mixed results today.",
                source="Test",
                source_tier=SourceTier.TIER_3,
                url="https://example.com/2",
                published_at=datetime.now()
            )
        ]
        
        analyses = await analyzer.batch_analyze_articles(articles)
        
        assert len(analyses) == len(articles)
        
        for analysis in analyses:
            assert hasattr(analysis, 'article_id')
            assert hasattr(analysis, 'relevance')
            assert hasattr(analysis, 'confidence')


class TestNewsSourceRegistry:
    """Test cases for News Source Registry."""

    @pytest.fixture
    def registry(self):
        """Create news source registry for testing."""
        return NewsSourceRegistry()

    def test_registry_initialization(self, registry):
        """Test registry initializes with sources."""
        assert len(registry.sources) > 0
        assert len(registry.source_clients) >= 0  # May be 0 if no API keys configured

    def test_get_sources_by_tier(self, registry):
        """Test getting sources by tier."""
        
        tier1_sources = registry.get_sources_by_tier(SourceTier.TIER_1)
        tier2_sources = registry.get_sources_by_tier(SourceTier.TIER_2)
        
        assert isinstance(tier1_sources, list)
        assert isinstance(tier2_sources, list)
        
        for source in tier1_sources:
            assert source.tier == SourceTier.TIER_1
        
        for source in tier2_sources:
            assert source.tier == SourceTier.TIER_2

    def test_get_enabled_sources(self, registry):
        """Test getting enabled sources."""
        
        enabled_sources = registry.get_enabled_sources()
        
        assert isinstance(enabled_sources, list)
        
        for source in enabled_sources:
            assert source.enabled is True

    def test_add_custom_source(self, registry):
        """Test adding custom source."""
        
        custom_source = NewsSource(
            name="Custom Test Source",
            tier=SourceTier.TIER_3,
            base_url="https://custom.test.com/api",
            reliability_score=0.75
        )
        
        # Mock client
        mock_client = MagicMock()
        
        initial_count = len(registry.sources)
        registry.add_custom_source("custom_test", custom_source, mock_client)
        
        assert len(registry.sources) == initial_count + 1
        assert "custom_test" in registry.sources
        assert registry.sources["custom_test"] == custom_source
        assert "custom_test" in registry.source_clients

    def test_remove_source(self, registry):
        """Test removing source."""
        
        # Add a test source first
        test_source = NewsSource(
            name="Remove Test",
            tier=SourceTier.TIER_4,
            base_url="https://test.com"
        )
        
        registry.sources["remove_test"] = test_source
        initial_count = len(registry.sources)
        
        # Remove it
        result = registry.remove_source("remove_test")
        
        assert result is True
        assert len(registry.sources) == initial_count - 1
        assert "remove_test" not in registry.sources
        
        # Try to remove non-existent source
        result = registry.remove_source("non_existent")
        assert result is False

    def test_get_source_status(self, registry):
        """Test getting source status."""
        
        status = registry.get_source_status()
        
        assert isinstance(status, dict)
        assert 'total_sources' in status
        assert 'enabled_sources' in status
        assert 'by_tier' in status
        assert 'sources' in status
        
        assert isinstance(status['by_tier'], dict)
        assert isinstance(status['sources'], dict)
        
        # Check tier breakdown
        for tier in SourceTier:
            if tier.value in status['by_tier']:
                tier_info = status['by_tier'][tier.value]
                assert 'count' in tier_info
                assert 'enabled' in tier_info

    @pytest.mark.asyncio
    async def test_fetch_articles_no_client(self, registry):
        """Test fetching articles with no client configured."""
        
        articles = await registry.fetch_articles("non_existent_source")
        
        assert articles == []


class TestNewsIntegration:
    """Integration tests for news monitoring system."""

    @pytest.mark.asyncio
    async def test_end_to_end_monitoring_workflow(self):
        """Test complete news monitoring workflow."""
        
        with patch('src.news.monitor.DatabaseManager'):
            with patch('src.news.monitor.DataCache'):
                monitor = NewsMonitor()
                
                # Mock article fetching
                mock_articles = [
                    NewsArticle(
                        id="integration_test_1",
                        title="Breaking: Major Tech Acquisition",
                        content="Technology giant acquires startup for $5 billion in cash deal.",
                        source="Reuters",
                        source_tier=SourceTier.TIER_1,
                        url="https://example.com/acquisition",
                        published_at=datetime.now(),
                        mentioned_companies=["Apple Inc."],
                        mentioned_tickers=["AAPL"]
                    )
                ]
                
                with patch.object(monitor, '_fetch_articles_from_api', return_value=mock_articles):
                    # Test article processing
                    source = monitor.sources['reuters']
                    new_articles = await monitor._scan_news_source(source)
                    
                    assert len(new_articles) > 0
                    assert len(monitor.recent_articles) > 0
                    
                    # Verify article was processed
                    processed_article = new_articles[0]
                    assert processed_article.id in [a.id for a in monitor.recent_articles]

    def test_alert_severity_escalation(self):
        """Test alert severity determination with different scenarios."""
        
        with patch('src.news.monitor.DatabaseManager'):
            with patch('src.news.monitor.DataCache'):
                monitor = NewsMonitor()
                
                # High relevance, Tier 1 source -> Should trigger high severity
                high_impact_article = NewsArticle(
                    id="high_impact",
                    title="BREAKING: FDA Approves Revolutionary Drug",
                    content="FDA grants approval for breakthrough cancer treatment.",
                    source="Reuters",
                    source_tier=SourceTier.TIER_1,
                    url="https://example.com/fda",
                    published_at=datetime.now()
                )
                
                relevance_score = monitor._calculate_relevance_score(high_impact_article)
                severity = monitor._determine_alert_severity(high_impact_article, relevance_score)
                
                assert severity is not None
                assert severity in [AlertSeverity.CRITICAL, AlertSeverity.HIGH]

    def test_source_tier_impact_on_processing(self):
        """Test how source tier affects article processing and scoring."""
        
        with patch('src.news.monitor.DatabaseManager'):
            with patch('src.news.monitor.DataCache'):
                monitor = NewsMonitor()
                
                # Same content, different tiers
                tier1_article = NewsArticle(
                    id="tier1_test",
                    title="Market Update",
                    content="Stock market shows volatility amid economic uncertainty.",
                    source="Reuters",
                    source_tier=SourceTier.TIER_1,
                    url="https://example.com/tier1",
                    published_at=datetime.now()
                )
                
                tier4_article = NewsArticle(
                    id="tier4_test",
                    title="Market Update",
                    content="Stock market shows volatility amid economic uncertainty.",
                    source="Reddit Finance",
                    source_tier=SourceTier.TIER_4,
                    url="https://example.com/tier4",
                    published_at=datetime.now()
                )
                
                tier1_relevance = monitor._calculate_relevance_score(tier1_article)
                tier4_relevance = monitor._calculate_relevance_score(tier4_article)
                
                # Tier 1 should have higher relevance score
                assert tier1_relevance > tier4_relevance