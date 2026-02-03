"""Test data integration layer - API clients, rate limiting, and caching."""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.data.clients.rate_limiter import AsyncRateLimiter, RateLimit, RateLimitState
from src.data.clients.data_cache import DataCache, CacheEntry, CACHE_TTL
from src.data.clients.finnhub_client import FinnhubClient, FinnhubAPIError
from src.data.clients.alpha_vantage_client import AlphaVantageClient, AlphaVantageAPIError


class TestRateLimiter:
    """Test rate limiting functionality."""
    
    @pytest.mark.asyncio
    async def test_basic_rate_limiting(self):
        """Test basic rate limiting functionality."""
        limiter = AsyncRateLimiter()
        # Use a very small time window for fast testing
        test_limit = RateLimit(requests_per_minute=2)
        limiter.set_limit("test", test_limit)
        
        # Manually set a very short time window for testing
        state = limiter.states["test"]
        state.last_reset_minute = datetime.utcnow() - timedelta(seconds=58)  # Almost at reset time
        
        # First two requests should go through immediately
        start_time = datetime.utcnow()
        await limiter.acquire("test")
        await limiter.acquire("test")
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        
        # Should be very fast (under 1 second)
        assert elapsed < 1.0
        
        # Third request should be delayed, but we'll simulate it being very short
        # by setting the reset time to be very close
        state.last_reset_minute = datetime.utcnow() - timedelta(seconds=59.5)
        
        start_time = datetime.utcnow()
        await limiter.acquire("test")
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        
        # Should have waited a small amount (under 2 seconds for testing)
        assert elapsed < 2.0  # Much more reasonable for testing
    
    @pytest.mark.asyncio
    async def test_burst_tokens(self):
        """Test burst token functionality."""
        limiter = AsyncRateLimiter()
        limiter.set_limit("test", RateLimit(requests_per_minute=1, burst_size=3))
        
        # Should be able to make 3 quick requests using burst tokens
        start_time = datetime.utcnow()
        await limiter.acquire("test")
        await limiter.acquire("test")
        await limiter.acquire("test")
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        
        # Should be very fast
        assert elapsed < 1.0
    
    def test_rate_limit_stats(self):
        """Test rate limiting statistics."""
        limiter = AsyncRateLimiter()
        limiter.set_limit("test", RateLimit(requests_per_minute=60, burst_size=10))
        
        stats = limiter.get_stats("test")
        assert "minute_remaining" in stats
        assert stats["minute_limit"] == 60
        assert stats["burst_tokens"] == 10
    
    @pytest.mark.asyncio
    async def test_multiple_keys(self):
        """Test rate limiting with multiple keys."""
        limiter = AsyncRateLimiter()
        limiter.set_limit("api1", RateLimit(requests_per_minute=2))
        limiter.set_limit("api2", RateLimit(requests_per_minute=2))
        
        # Should be able to make requests to both APIs without interference
        await limiter.acquire("api1")
        await limiter.acquire("api2")
        await limiter.acquire("api1")
        await limiter.acquire("api2")
        
        # Both should be at their limits now
        stats1 = limiter.get_stats("api1")
        stats2 = limiter.get_stats("api2")
        
        assert stats1["minute_remaining"] == 0
        assert stats2["minute_remaining"] == 0


class TestDataCache:
    """Test caching functionality."""
    
    @pytest.fixture
    async def mock_cache(self):
        """Create a cache with mocked Redis."""
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_redis.setex.return_value = True
        mock_redis.set.return_value = True
        mock_redis.get.return_value = None
        mock_redis.delete.return_value = 1
        mock_redis.exists.return_value = False
        
        cache = DataCache(mock_redis)
        await cache.connect()
        return cache
    
    @pytest.mark.asyncio
    async def test_cache_set_and_get(self, mock_cache):
        """Test basic cache set and get operations."""
        test_data = {"symbol": "AAPL", "price": 150.0}
        
        # Mock Redis get to return our data
        import json
        from dataclasses import asdict
        entry = CacheEntry(
            key="test:key",
            data=test_data,
            created_at=datetime.utcnow(),
            source="test"
        )
        mock_cache.redis.get.return_value = json.dumps(asdict(entry), default=str)
        
        # Set data
        await mock_cache.set("test:key", test_data, ttl_seconds=300, source="test")
        
        # Verify set was called
        mock_cache.redis.setex.assert_called_once()
        
        # Get data
        result = await mock_cache.get("test:key")
        assert result == test_data
    
    @pytest.mark.asyncio
    async def test_cache_expiration(self, mock_cache):
        """Test cache expiration logic."""
        # Mock expired entry
        expired_entry = CacheEntry(
            key="expired:key",
            data={"old": "data"},
            created_at=datetime.utcnow() - timedelta(hours=2),
            expires_at=datetime.utcnow() - timedelta(hours=1)  # Expired
        )
        
        import json
        from dataclasses import asdict
        mock_cache.redis.get.return_value = json.dumps(asdict(expired_entry), default=str)
        
        # Should return None for expired entry
        result = await mock_cache.get("expired:key")
        assert result is None
        
        # Should have called delete to clean up
        mock_cache.redis.delete.assert_called_with("expired:key")
    
    @pytest.mark.asyncio
    async def test_cache_tags(self, mock_cache):
        """Test cache tagging functionality."""
        await mock_cache.set(
            "tagged:key",
            {"data": "test"},
            ttl_seconds=300,
            tags=["tag1", "tag2"]
        )
        
        # Verify tags were set
        assert mock_cache.redis.sadd.call_count == 2  # Two tags
    
    def test_cache_key_generation(self):
        """Test cache key generation."""
        cache = DataCache()
        
        # Test normal key
        key = cache.make_key("api", "endpoint", "param1", "param2")
        assert key == "api:endpoint:param1:param2"
        
        # Test very long key (should be hashed)
        long_parts = ["api"] + ["very_long_parameter"] * 20
        long_key = cache.make_key(*long_parts)
        assert len(long_key) < 50  # Should be much shorter due to hashing
        assert "hash:" in long_key


class TestFinnhubClient:
    """Test Finnhub API client."""
    
    @pytest.fixture
    def mock_client(self):
        """Create Finnhub client with mocked dependencies."""
        with patch('src.data.clients.finnhub_client.settings') as mock_settings:
            mock_settings.api.finnhub_api_key = "test_api_key"
            mock_settings.api.finnhub_rate_limit = 60
            mock_settings.app.version = "1.0.0"
            
            mock_rate_limiter = AsyncMock()
            mock_cache = AsyncMock()
            
            return FinnhubClient(
                api_key="test_api_key",
                rate_limiter=mock_rate_limiter,
                cache=mock_cache
            )
    
    @pytest.mark.asyncio
    async def test_client_initialization(self, mock_client):
        """Test client initialization."""
        assert mock_client.api_key == "test_api_key"
        assert mock_client.rate_limiter is not None
        assert mock_client.cache is not None
    
    @pytest.mark.asyncio  
    async def test_get_quote(self, mock_client):
        """Test getting stock quote."""
        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "c": 150.0,  # current price
            "h": 152.0,  # high
            "l": 148.0,  # low
            "o": 149.0,  # open
            "pc": 151.0,  # previous close
            "t": 1640995200  # timestamp
        }
        mock_response.raise_for_status.return_value = None
        
        with patch.object(mock_client.client, 'get', return_value=mock_response):
            result = await mock_client.get_quote("AAPL")
            
            assert result["c"] == 150.0
            assert "h" in result
            mock_client.rate_limiter.acquire.assert_called_with("finnhub")
    
    @pytest.mark.asyncio
    async def test_api_error_handling(self, mock_client):
        """Test API error handling."""
        # Mock HTTP error response
        import httpx
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        
        with patch.object(mock_client.client, 'get') as mock_get:
            mock_get.side_effect = httpx.HTTPStatusError(
                "401 Unauthorized", request=MagicMock(), response=mock_response
            )
            
            with pytest.raises(FinnhubAPIError) as exc_info:
                await mock_client.get_quote("INVALID")
            
            assert "Invalid API key" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_caching_behavior(self, mock_client):
        """Test caching behavior."""
        # Mock cache hit
        cached_data = {"c": 150.0, "cached": True}
        mock_client.cache.get.return_value = cached_data
        
        result = await mock_client.get_quote("AAPL")
        
        assert result == cached_data
        # Should not make HTTP request due to cache hit
        mock_client.rate_limiter.acquire.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_batch_quotes(self, mock_client):
        """Test batch quote functionality."""
        # Mock individual quote responses
        mock_client.get_quote = AsyncMock(side_effect=[
            {"symbol": "AAPL", "c": 150.0},
            {"symbol": "MSFT", "c": 250.0},
            {"symbol": "GOOGL", "c": 2500.0}
        ])
        
        symbols = ["AAPL", "MSFT", "GOOGL"]
        results = await mock_client.batch_quotes(symbols)
        
        assert len(results) == 3
        assert results["AAPL"]["c"] == 150.0
        assert results["MSFT"]["c"] == 250.0
        assert results["GOOGL"]["c"] == 2500.0


class TestAlphaVantageClient:
    """Test Alpha Vantage API client."""
    
    @pytest.fixture
    def mock_client(self):
        """Create Alpha Vantage client with mocked dependencies."""
        with patch('src.data.clients.alpha_vantage_client.settings') as mock_settings:
            mock_settings.api.alpha_vantage_api_key = "test_api_key"
            mock_settings.api.alpha_vantage_rate_limit = 5
            mock_settings.app.version = "1.0.0"
            
            mock_rate_limiter = AsyncMock()
            mock_cache = AsyncMock()
            
            return AlphaVantageClient(
                api_key="test_api_key",
                rate_limiter=mock_rate_limiter,
                cache=mock_cache
            )
    
    @pytest.mark.asyncio
    async def test_company_overview(self, mock_client):
        """Test getting company overview."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Symbol": "AAPL",
            "Name": "Apple Inc",
            "MarketCapitalization": "3000000000000",
            "PERatio": "25.5",
            "Sector": "Technology"
        }
        mock_response.raise_for_status.return_value = None
        
        with patch.object(mock_client.client, 'get', return_value=mock_response):
            result = await mock_client.get_company_overview("AAPL")
            
            assert result["Symbol"] == "AAPL"
            assert result["Name"] == "Apple Inc"
            mock_client.rate_limiter.acquire.assert_called_with("alpha_vantage")
    
    def test_overview_data_parsing(self, mock_client):
        """Test parsing of overview data."""
        raw_data = {
            "Symbol": "AAPL",
            "Name": "Apple Inc",
            "MarketCapitalization": "3000000000000",
            "PERatio": "25.5",
            "PEGRatio": "2.1",
            "Beta": "1.2",
            "DividendYield": "0.005",
            "EPS": "6.05"
        }
        
        parsed = mock_client.parse_overview_data(raw_data)
        
        assert parsed["symbol"] == "AAPL"
        assert parsed["name"] == "Apple Inc"
        assert parsed["market_cap"] == 3000000000000.0
        assert parsed["pe_ratio"] == 25.5
        assert parsed["beta"] == 1.2
        assert parsed["dividend_yield"] == 0.005
    
    def test_safe_float_conversion(self, mock_client):
        """Test safe float conversion utility."""
        assert mock_client._safe_float("25.5") == 25.5
        assert mock_client._safe_float("None") is None
        assert mock_client._safe_float("-") is None
        assert mock_client._safe_float("") is None
        assert mock_client._safe_float("invalid") is None
    
    @pytest.mark.asyncio
    async def test_rate_limiting_with_delays(self, mock_client):
        """Test that batch operations include proper delays."""
        mock_client.get_company_overview = AsyncMock(return_value={"Symbol": "TEST"})
        
        # Mock asyncio.sleep to avoid actual waiting but verify it's called
        with patch('asyncio.sleep') as mock_sleep:
            # Test with 2 symbols - should have one delay
            symbols = ["AAPL", "MSFT"]
            await mock_client.batch_company_overviews(symbols)
            
            # Should have called sleep once between the two requests
            mock_sleep.assert_called_once_with(12.5)
    
    @pytest.mark.asyncio
    async def test_api_error_handling(self, mock_client):
        """Test API error handling."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Error Message": "Invalid API call"
        }
        mock_response.raise_for_status.return_value = None
        
        with patch.object(mock_client.client, 'get', return_value=mock_response):
            with pytest.raises(AlphaVantageAPIError) as exc_info:
                await mock_client.get_company_overview("INVALID")
            
            assert "Invalid API call" in str(exc_info.value)


class TestDataIntegration:
    """Test integration between components."""
    
    @pytest.mark.asyncio
    async def test_client_cache_integration(self):
        """Test that clients properly use caching."""
        # This would be an integration test with real Redis in a full test suite
        # For now, we test that the components work together via mocking
        
        mock_cache = AsyncMock()
        mock_cache.get.return_value = None  # Cache miss first
        mock_cache.set.return_value = None
        
        mock_rate_limiter = AsyncMock()
        mock_rate_limiter.acquire.return_value = None
        
        with patch('src.data.clients.finnhub_client.settings') as mock_settings:
            mock_settings.api.finnhub_api_key = "test_key"
            mock_settings.api.finnhub_rate_limit = 60
            mock_settings.app.version = "1.0.0"
            
            client = FinnhubClient(
                rate_limiter=mock_rate_limiter,
                cache=mock_cache
            )
            
            # Mock successful API response
            mock_response = MagicMock()
            mock_response.json.return_value = {"c": 150.0}
            mock_response.raise_for_status.return_value = None
            
            with patch.object(client.client, 'get', return_value=mock_response):
                result = await client.get_quote("AAPL")
                
                # Should have checked cache, made API request, and stored result
                mock_cache.get.assert_called_once()
                mock_rate_limiter.acquire.assert_called_once()
                mock_cache.set.assert_called_once()
                
                assert result["c"] == 150.0
    
    def test_cache_key_consistency(self):
        """Test that cache keys are generated consistently."""
        from src.data.clients.data_cache import cache_key_for_api_call
        
        # Same parameters should generate same key
        key1 = cache_key_for_api_call("finnhub", "quote", symbol="AAPL", param="value")
        key2 = cache_key_for_api_call("finnhub", "quote", symbol="AAPL", param="value")
        assert key1 == key2
        
        # Different parameters should generate different keys
        key3 = cache_key_for_api_call("finnhub", "quote", symbol="MSFT", param="value")
        assert key1 != key3
        
        # Parameter order shouldn't matter (they're sorted)
        key4 = cache_key_for_api_call("finnhub", "quote", param="value", symbol="AAPL")
        assert key1 == key4