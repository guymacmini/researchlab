"""Database models for ResearchLab."""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Boolean, Text, JSON,
    ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

Base = declarative_base()


class ResearchStatus(Enum):
    """Research project status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress" 
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ConfidenceLevel(Enum):
    """Analysis confidence levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ResearchProject(Base):
    """Main research project entity."""
    __tablename__ = "research_projects"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False)
    query = Column(Text, nullable=False)
    scope = Column(JSON, nullable=False)  # Serialized research scope
    status = Column(String, nullable=False, default=ResearchStatus.PENDING.value)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Results
    executive_summary = Column(Text, nullable=True)
    key_findings = Column(JSON, nullable=True)  # List of findings
    total_companies_analyzed = Column(Integer, default=0)
    google_sheets_url = Column(String, nullable=True)
    
    # Relationships
    agent_results = relationship("AgentAnalysis", back_populates="project")
    companies = relationship("CompanyAnalysis", back_populates="project")
    
    __table_args__ = (
        Index("ix_research_user_created", "user_id", "created_at"),
        Index("ix_research_status", "status"),
    )


class Company(Base):
    """Company master data."""
    __tablename__ = "companies"
    
    symbol = Column(String, primary_key=True)  # Ticker symbol
    name = Column(String, nullable=False)
    exchange = Column(String, nullable=True)
    sector = Column(String, nullable=True) 
    industry = Column(String, nullable=True)
    country = Column(String, default="US", nullable=False)
    
    # Basic financials (cached for quick access)
    market_cap = Column(Float, nullable=True)
    enterprise_value = Column(Float, nullable=True)
    pe_ratio = Column(Float, nullable=True)
    revenue_ttm = Column(Float, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Data freshness tracking
    financials_updated_at = Column(DateTime, nullable=True)
    profile_updated_at = Column(DateTime, nullable=True)
    
    # Relationships
    analyses = relationship("CompanyAnalysis", back_populates="company")
    
    __table_args__ = (
        Index("ix_company_sector", "sector"),
        Index("ix_company_market_cap", "market_cap"),
    )


class AgentAnalysis(Base):
    """Results from individual agent analysis."""
    __tablename__ = "agent_analyses"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("research_projects.id"), nullable=False)
    agent_role = Column(String, nullable=False)  # AgentRole enum value
    
    # Analysis results
    success = Column(Boolean, nullable=False)
    confidence = Column(Float, nullable=False)  # 0.0 - 1.0
    data = Column(JSON, nullable=False)  # Agent-specific analysis data
    reasoning = Column(Text, nullable=False)
    sources = Column(JSON, nullable=False)  # List of data sources used
    errors = Column(JSON, nullable=True)  # List of error messages
    
    # Timing
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=False)
    duration_seconds = Column(Float, nullable=False)
    
    # Relationships
    project = relationship("ResearchProject", back_populates="agent_results")
    
    __table_args__ = (
        Index("ix_agent_analysis_project", "project_id"),
        Index("ix_agent_analysis_role", "agent_role"),
    )


class CompanyAnalysis(Base):
    """Per-company analysis results within a research project."""
    __tablename__ = "company_analyses"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("research_projects.id"), nullable=False)
    symbol = Column(String, ForeignKey("companies.symbol"), nullable=False)
    
    # Relevance to research thesis
    relevance_score = Column(Float, nullable=False)  # 0.0 - 10.0
    investment_thesis = Column(Text, nullable=False)
    primary_exposure_pct = Column(Float, nullable=True)  # % of business exposed
    
    # Financial metrics (normalized for comparison)
    metrics = Column(JSON, nullable=False)  # Standardized financial ratios
    
    # Investment case
    bull_case = Column(Text, nullable=True)
    bear_case = Column(Text, nullable=True) 
    catalyst_timeline = Column(String, nullable=True)  # e.g., "6-12 months"
    
    # Analysis metadata
    confidence_level = Column(String, nullable=False)  # ConfidenceLevel enum
    analyzed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    project = relationship("ResearchProject", back_populates="companies")
    company = relationship("Company", back_populates="analyses")
    
    __table_args__ = (
        UniqueConstraint("project_id", "symbol", name="uq_project_company"),
        Index("ix_company_analysis_relevance", "relevance_score"),
    )


class NewsItem(Base):
    """News articles and their analysis."""
    __tablename__ = "news_items"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Article metadata
    title = Column(String, nullable=False)
    url = Column(String, nullable=False, unique=True)
    source = Column(String, nullable=False)
    published_at = Column(DateTime, nullable=False)
    
    # Content
    summary = Column(Text, nullable=True)
    full_text = Column(Text, nullable=True)
    
    # Analysis
    sentiment_score = Column(Float, nullable=True)  # -1.0 to 1.0
    relevance_tags = Column(JSON, nullable=True)  # List of relevant topics/companies
    mentioned_symbols = Column(JSON, nullable=True)  # List of ticker symbols
    
    # Quality scoring
    source_tier = Column(Integer, default=3, nullable=False)  # 1=highest quality
    credibility_score = Column(Float, default=0.5, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_news_published", "published_at"),
        Index("ix_news_source", "source"),
        Index("ix_news_symbols", "mentioned_symbols"),
    )


class DataCache(Base):
    """Generic cache for API responses and computed data."""
    __tablename__ = "data_cache"
    
    key = Column(String, primary_key=True)
    data = Column(JSON, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_cache_expires", "expires_at"),
    )