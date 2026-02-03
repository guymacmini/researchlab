"""Test database models."""

import pytest
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.models import (
    ResearchProject, Company, AgentAnalysis, CompanyAnalysis,
    NewsItem, DataCache, ResearchStatus, ConfidenceLevel
)


class TestResearchProject:
    """Test ResearchProject model."""
    
    @pytest.mark.asyncio
    async def test_create_research_project(self, db_session: AsyncSession):
        """Test creating a research project."""
        project = ResearchProject(
            user_id="test-user",
            query="Test investment thesis",
            scope={
                "investment_horizon": "medium",
                "geographic_scope": "us_only", 
                "sectors": ["technology"]
            }
        )
        
        db_session.add(project)
        await db_session.commit()
        await db_session.refresh(project)
        
        assert project.id is not None
        assert project.user_id == "test-user"
        assert project.status == ResearchStatus.PENDING.value
        assert project.created_at is not None
        assert project.scope["sectors"] == ["technology"]
    
    @pytest.mark.asyncio 
    async def test_project_with_results(self, db_session: AsyncSession):
        """Test project with analysis results."""
        project = ResearchProject(
            user_id="test-user",
            query="AI investment opportunities", 
            scope={"sectors": ["technology"]},
            executive_summary="AI companies show strong growth",
            key_findings=["NVDA leading in AI chips", "Cloud providers benefiting"],
            total_companies_analyzed=25
        )
        
        db_session.add(project)
        await db_session.commit()
        await db_session.refresh(project)
        
        assert len(project.key_findings) == 2
        assert project.total_companies_analyzed == 25


class TestCompany:
    """Test Company model."""
    
    @pytest.mark.asyncio
    async def test_create_company(self, db_session: AsyncSession):
        """Test creating a company."""
        company = Company(
            symbol="AAPL",
            name="Apple Inc",
            sector="Technology",
            industry="Consumer Electronics",
            market_cap=3000000000000.0,
            pe_ratio=25.5
        )
        
        db_session.add(company)
        await db_session.commit()
        await db_session.refresh(company)
        
        assert company.symbol == "AAPL"
        assert company.name == "Apple Inc"
        assert company.market_cap == 3000000000000.0
        assert company.country == "US"  # Default
        assert company.created_at is not None


class TestAgentAnalysis:
    """Test AgentAnalysis model."""
    
    @pytest.mark.asyncio
    async def test_create_agent_analysis(self, db_session: AsyncSession):
        """Test creating an agent analysis."""
        # Create a project first
        project = ResearchProject(
            user_id="test-user",
            query="Test query",
            scope={"sectors": ["technology"]}
        )
        db_session.add(project)
        await db_session.commit()
        await db_session.refresh(project)
        
        # Create agent analysis
        analysis = AgentAnalysis(
            project_id=project.id,
            agent_role="fundamental_analyst",
            success=True,
            confidence=0.85,
            data={"companies_analyzed": 10, "top_pick": "AAPL"},
            reasoning="Strong fundamentals across tech sector",
            sources=["finnhub", "alpha_vantage"],
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(), 
            duration_seconds=45.2
        )
        
        db_session.add(analysis)
        await db_session.commit()
        await db_session.refresh(analysis)
        
        assert analysis.project_id == project.id
        assert analysis.success is True
        assert analysis.confidence == 0.85
        assert analysis.data["top_pick"] == "AAPL"
        assert "finnhub" in analysis.sources


class TestCompanyAnalysis:
    """Test CompanyAnalysis model."""
    
    @pytest.mark.asyncio
    async def test_create_company_analysis(self, db_session: AsyncSession):
        """Test creating a company analysis."""
        # Create dependencies
        project = ResearchProject(
            user_id="test-user",
            query="Test query", 
            scope={"sectors": ["technology"]}
        )
        company = Company(
            symbol="NVDA",
            name="NVIDIA Corporation",
            sector="Technology"
        )
        
        db_session.add(project)
        db_session.add(company)
        await db_session.commit()
        await db_session.refresh(project)
        await db_session.refresh(company)
        
        # Create company analysis
        analysis = CompanyAnalysis(
            project_id=project.id,
            symbol=company.symbol,
            relevance_score=9.2,
            investment_thesis="Leader in AI chip design with strong moat",
            primary_exposure_pct=85.0,
            metrics={
                "pe_ratio": 65.2,
                "revenue_growth": 0.58,
                "gross_margin": 0.73
            },
            bull_case="AI adoption accelerates demand",
            bear_case="Competition from AMD and Intel",
            catalyst_timeline="6-12 months",
            confidence_level=ConfidenceLevel.HIGH.value
        )
        
        db_session.add(analysis)
        await db_session.commit()
        await db_session.refresh(analysis)
        
        assert analysis.relevance_score == 9.2
        assert analysis.primary_exposure_pct == 85.0
        assert analysis.metrics["revenue_growth"] == 0.58
        assert analysis.confidence_level == ConfidenceLevel.HIGH.value


class TestNewsItem:
    """Test NewsItem model."""
    
    @pytest.mark.asyncio
    async def test_create_news_item(self, db_session: AsyncSession):
        """Test creating a news item."""
        news = NewsItem(
            title="NVIDIA Reports Record Q4 Earnings",
            url="https://example.com/nvda-earnings",
            source="Reuters",
            published_at=datetime.utcnow(),
            summary="NVIDIA exceeded expectations with strong AI chip demand",
            sentiment_score=0.8,
            mentioned_symbols=["NVDA"],
            relevance_tags=["earnings", "ai", "semiconductors"],
            source_tier=1,
            credibility_score=0.95
        )
        
        db_session.add(news)
        await db_session.commit()
        await db_session.refresh(news)
        
        assert news.title.startswith("NVIDIA Reports")
        assert news.sentiment_score == 0.8
        assert "NVDA" in news.mentioned_symbols
        assert news.source_tier == 1


class TestDataCache:
    """Test DataCache model."""
    
    @pytest.mark.asyncio
    async def test_create_cache_entry(self, db_session: AsyncSession):
        """Test creating a cache entry."""
        cache = DataCache(
            key="finnhub:quote:AAPL",
            data={
                "c": 150.0,
                "t": 1699123200,
                "pc": 148.5
            },
            expires_at=datetime.utcnow()
        )
        
        db_session.add(cache)
        await db_session.commit()
        await db_session.refresh(cache)
        
        assert cache.key == "finnhub:quote:AAPL"
        assert cache.data["c"] == 150.0
        assert cache.created_at is not None