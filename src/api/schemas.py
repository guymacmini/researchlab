"""Pydantic schemas for API requests and responses."""

from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum

from pydantic import BaseModel, Field, validator

from src.data.models import ResearchStatus, ConfidenceLevel


class InvestmentHorizon(str, Enum):
    """Investment horizon options."""
    SHORT = "short"  # < 6 months
    MEDIUM = "medium"  # 6-24 months  
    LONG = "long"  # > 2 years


class GeographicScope(str, Enum):
    """Geographic scope options."""
    US_ONLY = "us_only"
    DEVELOPED_MARKETS = "developed_markets"
    EMERGING_MARKETS = "emerging_markets"
    GLOBAL = "global"


class MarketCap(str, Enum):
    """Market cap categories."""
    MICRO_CAP = "micro_cap"
    SMALL_CAP = "small_cap"
    MID_CAP = "mid_cap"
    LARGE_CAP = "large_cap"


class RiskTolerance(str, Enum):
    """Risk tolerance levels."""
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class AnalysisDepth(str, Enum):
    """Analysis depth options."""
    QUICK = "quick"  # 10-15 companies
    STANDARD = "standard"  # 25-50 companies
    DEEP = "deep"  # 100+ companies


class ResearchScopeDefinition(BaseModel):
    """Research scope configuration."""
    
    investment_horizon: InvestmentHorizon
    geographic_scope: GeographicScope
    market_cap: List[MarketCap] = Field(default=[MarketCap.LARGE_CAP, MarketCap.MID_CAP])
    sectors: List[str] = Field(default=[], description="GICS sectors to include/exclude")
    excluded_sectors: List[str] = Field(default=[], description="Sectors to explicitly exclude")
    risk_tolerance: RiskTolerance = RiskTolerance.MODERATE
    analysis_depth: AnalysisDepth = AnalysisDepth.STANDARD
    
    # Additional filters
    min_market_cap: Optional[float] = Field(default=None, description="Minimum market cap in USD")
    max_market_cap: Optional[float] = Field(default=None, description="Maximum market cap in USD")
    include_recent_ipos: bool = Field(default=True, description="Include companies that IPO'd in last 24 months")


class ResearchProjectCreate(BaseModel):
    """Schema for creating a research project."""
    
    user_id: str
    query: str = Field(..., min_length=10, max_length=2000)
    scope: Optional[ResearchScopeDefinition] = None


class ResearchProjectUpdate(BaseModel):
    """Schema for updating a research project."""
    
    status: Optional[ResearchStatus] = None
    executive_summary: Optional[str] = None
    key_findings: Optional[List[str]] = None
    total_companies_analyzed: Optional[int] = None
    google_sheets_url: Optional[str] = None


class ResearchProjectResponse(BaseModel):
    """Schema for research project response."""
    
    id: str
    user_id: str
    query: str
    scope: Dict[str, Any]
    status: str
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    executive_summary: Optional[str]
    key_findings: Optional[List[str]]
    total_companies_analyzed: int
    google_sheets_url: Optional[str]
    
    class Config:
        from_attributes = True


class CompanyCreate(BaseModel):
    """Schema for creating a company."""
    
    symbol: str = Field(..., min_length=1, max_length=10)
    name: str = Field(..., min_length=1, max_length=200)
    exchange: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    country: str = "US"


class CompanyResponse(BaseModel):
    """Schema for company response."""
    
    symbol: str
    name: str
    exchange: Optional[str]
    sector: Optional[str] 
    industry: Optional[str]
    country: str
    market_cap: Optional[float]
    enterprise_value: Optional[float]
    pe_ratio: Optional[float]
    revenue_ttm: Optional[float]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class AgentAnalysisResponse(BaseModel):
    """Schema for agent analysis response."""
    
    id: str
    project_id: str
    agent_role: str
    success: bool
    confidence: float
    data: Dict[str, Any]
    reasoning: str
    sources: List[str]
    errors: Optional[List[str]]
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    
    class Config:
        from_attributes = True


class CompanyAnalysisResponse(BaseModel):
    """Schema for company analysis response."""
    
    id: str
    project_id: str
    symbol: str
    relevance_score: float
    investment_thesis: str
    primary_exposure_pct: Optional[float]
    metrics: Dict[str, Any]
    bull_case: Optional[str]
    bear_case: Optional[str]
    catalyst_timeline: Optional[str]
    confidence_level: str
    analyzed_at: datetime
    
    class Config:
        from_attributes = True


class ClarificationQuestion(BaseModel):
    """Schema for clarification questions from Research Director."""
    
    question: str = Field(..., min_length=10)
    question_type: str = Field(..., description="Type of clarification needed")
    options: Optional[List[str]] = Field(default=None, description="Multiple choice options if applicable")
    required: bool = Field(default=True, description="Whether this question must be answered")


class ClarificationResponse(BaseModel):
    """Schema for user responses to clarification questions."""
    
    question_id: str
    answer: str
    selected_options: Optional[List[str]] = None


class ResearchPlan(BaseModel):
    """Schema for generated research plan."""
    
    sectors_to_analyze: List[str]
    second_order_effects: List[str] = Field(description="Second-order companies to investigate")
    third_order_effects: List[str] = Field(description="Third-order companies to investigate")
    data_sources: List[str] = Field(description="Data sources that will be queried")
    estimated_completion_time: int = Field(description="Estimated completion time in minutes")
    estimated_companies: int = Field(description="Estimated number of companies to analyze")


class NewsItemResponse(BaseModel):
    """Schema for news item response."""
    
    id: str
    title: str
    url: str
    source: str
    published_at: datetime
    summary: Optional[str]
    sentiment_score: Optional[float]
    relevance_tags: Optional[List[str]]
    mentioned_symbols: Optional[List[str]]
    source_tier: int
    credibility_score: float
    created_at: datetime
    
    class Config:
        from_attributes = True


class AgentExecutionRequest(BaseModel):
    """Schema for requesting agent execution."""
    
    project_id: str
    agent_roles: List[str] = Field(description="Which agents to execute")
    force_refresh: bool = Field(default=False, description="Force refresh of cached data")


class AgentExecutionStatus(BaseModel):
    """Schema for agent execution status."""
    
    project_id: str
    total_agents: int
    completed_agents: int
    failed_agents: int
    in_progress_agents: int
    estimated_remaining_time: Optional[int] = Field(description="Estimated remaining time in seconds")