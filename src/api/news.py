"""News monitoring and analysis API endpoints."""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field

from src.news.monitor import NewsMonitor, NewsArticle, NewsAlert, SourceTier, AlertSeverity
from src.news.analyzer import NewsAnalyzer, NewsRelevance, NewsCategory, NewsAnalysis
from src.news.sources import NewsSourceRegistry

router = APIRouter(prefix="/news", tags=["news"])

# Global instances
news_monitor = NewsMonitor()
news_analyzer = NewsAnalyzer()
source_registry = NewsSourceRegistry()


# Pydantic models
class NewsArticleResponse(BaseModel):
    """News article response model."""
    id: str
    title: str
    content: str
    source: str
    source_tier: str
    url: str
    published_at: datetime
    author: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    mentioned_companies: List[str] = Field(default_factory=list)
    mentioned_tickers: List[str] = Field(default_factory=list)
    sentiment_score: Optional[float] = None
    relevance_score: Optional[float] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "article_123",
                "title": "Apple Reports Strong Q4 Earnings",
                "content": "Apple Inc. announced quarterly earnings...",
                "source": "Reuters",
                "source_tier": "tier_1",
                "url": "https://example.com/article",
                "published_at": "2024-02-03T14:30:00Z",
                "mentioned_companies": ["Apple Inc."],
                "mentioned_tickers": ["AAPL"],
                "sentiment_score": 0.7
            }
        }


class NewsAlertResponse(BaseModel):
    """News alert response model."""
    id: str
    article_id: str
    title: str
    summary: str
    severity: str
    companies: List[str]
    tickers: List[str]
    created_at: datetime
    source_tier: str
    relevance_score: float
    sentiment_score: float
    delivered_at: Optional[datetime] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "alert_456",
                "article_id": "article_123",
                "title": "High Impact: Apple Earnings Beat",
                "summary": "Apple reports strong earnings with revenue growth",
                "severity": "high",
                "companies": ["Apple Inc."],
                "tickers": ["AAPL"],
                "created_at": "2024-02-03T14:35:00Z",
                "source_tier": "tier_1",
                "relevance_score": 0.85,
                "sentiment_score": 0.7
            }
        }


class NewsAnalysisResponse(BaseModel):
    """News analysis response model."""
    article_id: str
    relevance: str
    category: str
    confidence: float = Field(..., ge=0, le=1)
    overall_sentiment: float = Field(..., ge=-1, le=1)
    sentiment_confidence: float = Field(..., ge=0, le=1)
    primary_company: Optional[str] = None
    impact_assessment: str
    key_phrases: List[str] = Field(default_factory=list)
    financial_metrics: Dict[str, Any] = Field(default_factory=dict)
    urgency_score: float = Field(..., ge=0, le=1)
    analyzed_at: datetime
    
    class Config:
        json_schema_extra = {
            "example": {
                "article_id": "article_123",
                "relevance": "high",
                "category": "earnings",
                "confidence": 0.89,
                "overall_sentiment": 0.6,
                "sentiment_confidence": 0.85,
                "primary_company": "Apple Inc.",
                "impact_assessment": "Positive earnings impact from reliable source",
                "key_phrases": ["strong earnings", "revenue growth"],
                "urgency_score": 0.7,
                "analyzed_at": "2024-02-03T14:40:00Z"
            }
        }


class MonitoringStatusResponse(BaseModel):
    """News monitoring status response."""
    is_running: bool
    active_sources: int
    total_sources: int
    recent_articles_count: int
    monitoring_companies: List[str] = Field(default_factory=list)
    last_scan_times: Dict[str, Optional[datetime]] = Field(default_factory=dict)
    
    class Config:
        json_schema_extra = {
            "example": {
                "is_running": True,
                "active_sources": 8,
                "total_sources": 12,
                "recent_articles_count": 150,
                "monitoring_companies": ["AAPL", "GOOGL", "MSFT"],
                "last_scan_times": {
                    "reuters": "2024-02-03T14:30:00Z",
                    "cnbc": "2024-02-03T14:25:00Z"
                }
            }
        }


class StartMonitoringRequest(BaseModel):
    """Request to start news monitoring."""
    companies: Optional[List[str]] = Field(None, description="Company names to monitor")
    tickers: Optional[List[str]] = Field(None, description="Stock tickers to monitor") 
    sources: Optional[List[str]] = Field(None, description="Specific sources to use")
    alert_thresholds: Optional[Dict[str, float]] = Field(None, description="Custom alert thresholds")
    
    class Config:
        json_schema_extra = {
            "example": {
                "companies": ["Apple Inc.", "Google LLC", "Microsoft Corp."],
                "tickers": ["AAPL", "GOOGL", "MSFT"],
                "sources": ["reuters", "cnbc", "financial_times"],
                "alert_thresholds": {
                    "critical": 0.9,
                    "high": 0.7,
                    "medium": 0.5
                }
            }
        }


# API Endpoints
@router.post("/monitoring/start", summary="Start news monitoring")
async def start_news_monitoring(
    request: StartMonitoringRequest,
    background_tasks: BackgroundTasks
) -> Dict[str, str]:
    """
    Start news monitoring for specified companies and tickers.
    
    Begins continuous monitoring of news sources for mentions of
    the specified companies. Generates alerts based on configured thresholds.
    """
    
    try:
        # Configure alert thresholds if provided
        if request.alert_thresholds:
            for severity_name, threshold in request.alert_thresholds.items():
                try:
                    severity = AlertSeverity(severity_name)
                    news_monitor.configure_alerts(severity, threshold, 1.0)
                except ValueError:
                    pass  # Skip invalid severity levels
        
        # Start monitoring
        await news_monitor.start_monitoring(
            companies=request.companies,
            tickers=request.tickers
        )
        
        return {"message": "News monitoring started successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start monitoring: {str(e)}")


@router.post("/monitoring/stop", summary="Stop news monitoring") 
async def stop_news_monitoring() -> Dict[str, str]:
    """
    Stop news monitoring and cleanup background tasks.
    
    Stops all active news source scanning and cancels any pending alerts.
    """
    
    try:
        await news_monitor.stop_monitoring()
        return {"message": "News monitoring stopped successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop monitoring: {str(e)}")


@router.get("/monitoring/status", response_model=MonitoringStatusResponse,
           summary="Get monitoring status")
async def get_monitoring_status() -> MonitoringStatusResponse:
    """
    Get current status of news monitoring system.
    
    Returns information about active sources, recent articles,
    and monitoring configuration.
    """
    
    try:
        status = await news_monitor.get_monitoring_status()
        
        # Extract last scan times
        last_scan_times = {}
        for source_id, source_info in status.get('source_details', {}).items():
            last_scan = source_info.get('last_scan')
            if last_scan:
                last_scan_times[source_id] = datetime.fromisoformat(last_scan)
            else:
                last_scan_times[source_id] = None
        
        return MonitoringStatusResponse(
            is_running=status['is_running'],
            active_sources=status['active_sources'],
            total_sources=status['total_sources'],
            recent_articles_count=status['recent_articles_count'],
            monitoring_companies=[],  # Would extract from source filters
            last_scan_times=last_scan_times
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get monitoring status: {str(e)}")


@router.get("/articles", response_model=List[NewsArticleResponse],
           summary="Get recent news articles")
async def get_recent_articles(
    hours: int = Query(24, ge=1, le=168, description="Hours back to search"),
    source_tier: Optional[str] = Query(None, description="Filter by source tier"),
    companies: Optional[str] = Query(None, description="Comma-separated company names"),
    limit: int = Query(50, ge=1, le=200, description="Maximum articles to return")
) -> List[NewsArticleResponse]:
    """
    Get recent news articles with optional filtering.
    
    Returns articles from the last N hours, optionally filtered by
    source tier, companies, or other criteria.
    """
    
    try:
        # Parse filters
        tier_filter = None
        if source_tier:
            try:
                tier_filter = SourceTier(source_tier)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid source tier: {source_tier}")
        
        companies_filter = None
        if companies:
            companies_filter = [company.strip() for company in companies.split(',')]
        
        # Get articles
        articles = await news_monitor.get_recent_articles(
            hours=hours,
            source_tier=tier_filter,
            companies=companies_filter
        )
        
        # Convert to response format
        article_responses = []
        for article in articles[:limit]:
            article_responses.append(NewsArticleResponse(
                id=article.id,
                title=article.title,
                content=article.content,
                source=article.source,
                source_tier=article.source_tier.value,
                url=article.url,
                published_at=article.published_at,
                author=article.author,
                tags=article.tags,
                mentioned_companies=article.mentioned_companies,
                mentioned_tickers=article.mentioned_tickers,
                sentiment_score=article.sentiment_score,
                relevance_score=article.relevance_score
            ))
        
        return article_responses
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get articles: {str(e)}")


@router.post("/articles/{article_id}/analyze", response_model=NewsAnalysisResponse,
           summary="Analyze news article")
async def analyze_news_article(
    article_id: str,
    target_companies: Optional[List[str]] = Query(None, description="Target companies for relevance"),
    target_tickers: Optional[List[str]] = Query(None, description="Target tickers for relevance")
) -> NewsAnalysisResponse:
    """
    Perform comprehensive analysis of a news article.
    
    Analyzes sentiment, relevance, category, and extracts key insights
    from the article content.
    """
    
    try:
        # Find article in recent articles
        article = None
        for recent_article in news_monitor.recent_articles:
            if recent_article.id == article_id:
                article = recent_article
                break
        
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        # Perform analysis
        analysis = await news_analyzer.analyze_article(
            article, 
            target_companies=target_companies,
            target_tickers=target_tickers
        )
        
        return NewsAnalysisResponse(
            article_id=analysis.article_id,
            relevance=analysis.relevance.value,
            category=analysis.category.value,
            confidence=analysis.confidence,
            overall_sentiment=analysis.overall_sentiment,
            sentiment_confidence=analysis.sentiment_confidence,
            primary_company=analysis.primary_company,
            impact_assessment=analysis.impact_assessment,
            key_phrases=analysis.key_phrases,
            financial_metrics=analysis.financial_metrics,
            urgency_score=analysis.urgency_score,
            analyzed_at=analysis.analyzed_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze article: {str(e)}")


@router.get("/sources", summary="List news sources")
async def list_news_sources(
    tier: Optional[str] = Query(None, description="Filter by tier"),
    enabled_only: bool = Query(True, description="Only show enabled sources")
) -> Dict[str, Any]:
    """
    List available news sources with their configuration.
    
    Returns information about all configured news sources including
    their reliability scores, scan intervals, and current status.
    """
    
    try:
        status = source_registry.get_source_status()
        
        # Apply filters
        sources = status['sources']
        
        if tier:
            sources = {
                source_id: source_info 
                for source_id, source_info in sources.items()
                if source_info['tier'] == tier
            }
        
        if enabled_only:
            sources = {
                source_id: source_info
                for source_id, source_info in sources.items()
                if source_info['enabled']
            }
        
        return {
            "sources": sources,
            "summary": {
                "total": len(sources),
                "by_tier": status['by_tier']
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list sources: {str(e)}")


@router.post("/sources/{source_id}/test", summary="Test news source")
async def test_news_source(
    source_id: str,
    query: str = Query("market stocks finance", description="Test query")
) -> Dict[str, Any]:
    """
    Test a specific news source by fetching sample articles.
    
    Useful for verifying source configuration and API connectivity.
    """
    
    try:
        articles = await source_registry.fetch_articles(source_id, query=query)
        
        return {
            "source_id": source_id,
            "test_query": query,
            "articles_fetched": len(articles),
            "sample_titles": [article.title for article in articles[:3]],
            "status": "success" if articles else "no_results"
        }
        
    except Exception as e:
        return {
            "source_id": source_id,
            "test_query": query,
            "articles_fetched": 0,
            "status": "error",
            "error": str(e)
        }


@router.get("/alerts", response_model=List[NewsAlertResponse],
           summary="Get recent news alerts")
async def get_recent_alerts(
    hours: int = Query(24, ge=1, le=168, description="Hours back to search"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    companies: Optional[str] = Query(None, description="Comma-separated company names"),
    limit: int = Query(100, ge=1, le=500, description="Maximum alerts to return")
) -> List[NewsAlertResponse]:
    """
    Get recent news alerts with optional filtering.
    
    Returns alerts generated by the monitoring system based on
    configured thresholds and relevance scoring.
    """
    
    try:
        # This would typically query a database of alerts
        # For now, return empty list as alerts are handled by background tasks
        return []
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get alerts: {str(e)}")


@router.post("/analysis/batch", response_model=List[NewsAnalysisResponse],
           summary="Batch analyze articles")
async def batch_analyze_articles(
    article_ids: List[str],
    target_companies: Optional[List[str]] = None,
    target_tickers: Optional[List[str]] = None
) -> List[NewsAnalysisResponse]:
    """
    Analyze multiple articles in batch for efficiency.
    
    Performs comprehensive analysis on multiple articles simultaneously,
    useful for processing large volumes of news content.
    """
    
    try:
        if len(article_ids) > 50:
            raise HTTPException(status_code=400, detail="Maximum 50 articles per batch")
        
        # Find articles
        articles_to_analyze = []
        for article_id in article_ids:
            for article in news_monitor.recent_articles:
                if article.id == article_id:
                    articles_to_analyze.append(article)
                    break
        
        if not articles_to_analyze:
            return []
        
        # Perform batch analysis
        analyses = await news_analyzer.batch_analyze_articles(
            articles_to_analyze,
            target_companies=target_companies,
            target_tickers=target_tickers
        )
        
        # Convert to response format
        analysis_responses = []
        for analysis in analyses:
            analysis_responses.append(NewsAnalysisResponse(
                article_id=analysis.article_id,
                relevance=analysis.relevance.value,
                category=analysis.category.value,
                confidence=analysis.confidence,
                overall_sentiment=analysis.overall_sentiment,
                sentiment_confidence=analysis.sentiment_confidence,
                primary_company=analysis.primary_company,
                impact_assessment=analysis.impact_assessment,
                key_phrases=analysis.key_phrases,
                financial_metrics=analysis.financial_metrics,
                urgency_score=analysis.urgency_score,
                analyzed_at=analysis.analyzed_at
            ))
        
        return analysis_responses
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to batch analyze articles: {str(e)}")


@router.get("/trends", summary="Get news trends")
async def get_news_trends(
    hours: int = Query(24, ge=1, le=168, description="Time window in hours"),
    min_mentions: int = Query(3, ge=1, le=50, description="Minimum mentions for trending")
) -> Dict[str, Any]:
    """
    Get trending topics and companies from recent news.
    
    Analyzes recent articles to identify trending topics, companies,
    and sentiment patterns in the news cycle.
    """
    
    try:
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        # Analyze recent articles for trends
        company_mentions = {}
        sentiment_by_company = {}
        category_counts = {}
        
        for article in news_monitor.recent_articles:
            if article.published_at < cutoff_time:
                continue
            
            # Count company mentions
            for company in article.mentioned_companies:
                company_mentions[company] = company_mentions.get(company, 0) + 1
                
                # Track sentiment
                if article.sentiment_score is not None:
                    if company not in sentiment_by_company:
                        sentiment_by_company[company] = []
                    sentiment_by_company[company].append(article.sentiment_score)
        
        # Find trending companies
        trending_companies = {
            company: {
                "mentions": count,
                "avg_sentiment": sum(sentiment_by_company.get(company, [0])) / len(sentiment_by_company.get(company, [1]))
            }
            for company, count in company_mentions.items()
            if count >= min_mentions
        }
        
        # Sort by mentions
        trending_companies = dict(
            sorted(trending_companies.items(), key=lambda x: x[1]["mentions"], reverse=True)
        )
        
        return {
            "time_window_hours": hours,
            "trending_companies": trending_companies,
            "total_articles_analyzed": len([
                a for a in news_monitor.recent_articles 
                if a.published_at >= cutoff_time
            ]),
            "generated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get trends: {str(e)}")