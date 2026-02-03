"""Pytest configuration and fixtures for ResearchLab."""

import pytest
import pytest_asyncio
from typing import AsyncGenerator
from unittest.mock import Mock

import redis
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Test database URL - use SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    # Create tables
    from src.data.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
    
    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    return Mock(spec=redis.Redis)


@pytest.fixture
def mock_finnhub_client():
    """Mock Finnhub API client."""
    mock = Mock()
    mock.quote.return_value = {
        'c': 150.0,  # current price
        't': 1699123200,  # timestamp
        'pc': 148.5,  # previous close
    }
    mock.company_profile2.return_value = {
        'name': 'Test Company Inc',
        'ticker': 'TEST',
        'marketCapitalization': 1000000,
        'shareOutstanding': 100000,
        'finnhubIndustry': 'Technology'
    }
    return mock


@pytest.fixture
def mock_alpha_vantage_client():
    """Mock Alpha Vantage API client."""
    mock = Mock()
    mock.get_company_overview.return_value = {
        'Symbol': 'TEST',
        'Name': 'Test Company Inc',
        'MarketCapitalization': '1000000000',
        'PERatio': '25.5',
        'BookValue': '10.50'
    }
    return mock


@pytest.fixture
def sample_research_context():
    """Sample research context for testing agents."""
    return {
        'query': 'Which companies will benefit from AI adoption?',
        'scope': {
            'investment_horizon': 'medium',
            'geographic_scope': 'us_only',
            'market_cap': ['large_cap', 'mid_cap'],
            'sectors': ['technology', 'healthcare'],
            'risk_tolerance': 'moderate',
            'analysis_depth': 'standard'
        },
        'correlation_id': 'test-123',
        'user_id': 'test-user'
    }


@pytest.fixture
def sample_companies():
    """Sample company data for testing."""
    return [
        {
            'symbol': 'AAPL',
            'name': 'Apple Inc',
            'market_cap': 3000000000000,
            'sector': 'Technology',
            'industry': 'Consumer Electronics'
        },
        {
            'symbol': 'MSFT', 
            'name': 'Microsoft Corporation',
            'market_cap': 2800000000000,
            'sector': 'Technology',
            'industry': 'Software'
        },
        {
            'symbol': 'NVDA',
            'name': 'NVIDIA Corporation', 
            'market_cap': 1700000000000,
            'sector': 'Technology',
            'industry': 'Semiconductors'
        }
    ]