"""Tests for the rate limiting system."""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock

from src.rate_limiting.backends import (
    MemoryBackend, RedisBackend, RateLimitResult
)
from src.rate_limiting.strategies import (
    FixedWindowStrategy, SlidingWindowStrategy, TokenBucketStrategy,
    RateLimitRule, AdaptiveStrategy, MultiTierStrategy
)
from src.rate_limiting.middleware import (
    RateLimitMiddleware, RateLimitExceeded, 
    default_key_func, user_key_func, api_key_func,
    setup_rate_limiting
)
from src.rate_limiting.decorators import (
    rate_limit_endpoint, rate_limit_function, rate_limit_user,
    configure_rate_limiting
)


class TestMemoryBackend:
    """Test memory-based rate limiting backend."""
    
    @pytest.mark.asyncio
    async def test_memory_backend_basic_usage(self):
        """Test basic rate limiting with memory backend."""
        backend = MemoryBackend()
        
        # First request should be allowed
        result = await backend.check_rate_limit("test_key", 5, 60, 1)
        assert result.allowed is True
        assert result.limit == 5
        assert result.remaining == 4
        
        # Multiple requests within limit
        for i in range(4):
            result = await backend.check_rate_limit("test_key", 5, 60, 1)
            assert result.allowed is True
            assert result.remaining == 4 - i - 1
        
        # Sixth request should be blocked
        result = await backend.check_rate_limit("test_key", 5, 60, 1)
        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after > 0
    
    @pytest.mark.asyncio
    async def test_memory_backend_sliding_window(self):
        """Test sliding window behavior."""
        backend = MemoryBackend()
        key = "sliding_test"
        
        # Fill up the limit
        for i in range(3):
            result = await backend.check_rate_limit(key, 3, 2, 1)  # 3 requests per 2 seconds
            assert result.allowed is True
        
        # Should be blocked now
        result = await backend.check_rate_limit(key, 3, 2, 1)
        assert result.allowed is False
        
        # Wait for window to slide
        await asyncio.sleep(2.1)
        
        # Should be allowed again
        result = await backend.check_rate_limit(key, 3, 2, 1)
        assert result.allowed is True
    
    @pytest.mark.asyncio
    async def test_memory_backend_reset(self):
        """Test rate limit reset."""
        backend = MemoryBackend()
        key = "reset_test"
        
        # Use up the limit
        for i in range(3):
            await backend.check_rate_limit(key, 3, 60, 1)
        
        # Should be blocked
        result = await backend.check_rate_limit(key, 3, 60, 1)
        assert result.allowed is False
        
        # Reset rate limit
        reset_result = await backend.reset_rate_limit(key)
        assert reset_result is True
        
        # Should be allowed again
        result = await backend.check_rate_limit(key, 3, 60, 1)
        assert result.allowed is True
        assert result.remaining == 2
    
    @pytest.mark.asyncio
    async def test_memory_backend_info(self):
        """Test getting rate limit info."""
        backend = MemoryBackend()
        key = "info_test"
        
        # No info initially
        info = await backend.get_rate_limit_info(key)
        assert info is None
        
        # Make some requests
        for i in range(3):
            await backend.check_rate_limit(key, 5, 60, 1)
        
        # Should have info now
        info = await backend.get_rate_limit_info(key)
        assert info is not None
        assert info["total_requests"] == 3
        assert info["total_cost"] == 3


class TestRedisBackend:
    """Test Redis-based rate limiting backend."""
    
    @pytest.mark.asyncio
    async def test_redis_backend_basic(self):
        """Test basic Redis backend functionality."""
        # Mock Redis client
        mock_redis = AsyncMock()
        mock_redis.pipeline.return_value.__aenter__ = AsyncMock()
        mock_redis.pipeline.return_value.__aexit__ = AsyncMock()
        
        # Mock pipeline operations
        mock_pipeline = AsyncMock()
        mock_pipeline.execute.return_value = [0, 0]  # removed count, current count
        mock_redis.pipeline.return_value.__aenter__.return_value = mock_pipeline
        
        backend = RedisBackend(mock_redis)
        
        # Test first request
        result = await backend.check_rate_limit("test_key", 5, 60, 1)
        
        # Should be allowed (mocked as empty set)
        assert result.allowed is True
        assert result.limit == 5
    
    @pytest.mark.asyncio
    async def test_redis_backend_failure_handling(self):
        """Test Redis backend handles failures gracefully."""
        # Mock Redis client that raises exceptions
        mock_redis = AsyncMock()
        mock_redis.pipeline.side_effect = Exception("Redis connection failed")
        
        backend = RedisBackend(mock_redis)
        
        # Should fail open (allow request) when Redis is unavailable
        result = await backend.check_rate_limit("test_key", 5, 60, 1)
        assert result.allowed is True


class TestRateLimitStrategies:
    """Test rate limiting strategies."""
    
    @pytest.mark.asyncio
    async def test_fixed_window_strategy(self):
        """Test fixed window strategy."""
        backend = MemoryBackend()
        strategy = FixedWindowStrategy(backend)
        rule = RateLimitRule(limit=3, window=60, cost=1)
        
        # Make requests within same window
        for i in range(3):
            result = await strategy.check_rate_limit("test_key", rule)
            assert result.allowed is True
        
        # Fourth request should be blocked
        result = await strategy.check_rate_limit("test_key", rule)
        assert result.allowed is False
    
    @pytest.mark.asyncio
    async def test_sliding_window_strategy(self):
        """Test sliding window strategy."""
        backend = MemoryBackend()
        strategy = SlidingWindowStrategy(backend)
        rule = RateLimitRule(limit=2, window=2, cost=1)
        
        # First request
        result = await strategy.check_rate_limit("test_key", rule)
        assert result.allowed is True
        assert result.remaining == 1
        
        # Second request
        result = await strategy.check_rate_limit("test_key", rule)
        assert result.allowed is True
        assert result.remaining == 0
        
        # Third request should be blocked
        result = await strategy.check_rate_limit("test_key", rule)
        assert result.allowed is False
    
    @pytest.mark.asyncio
    async def test_token_bucket_strategy(self):
        """Test token bucket strategy."""
        backend = MemoryBackend()
        strategy = TokenBucketStrategy(backend)
        rule = RateLimitRule(limit=2, window=2, burst=3, cost=1)  # 2 tokens/2sec, burst=3
        
        # Should allow burst requests initially
        for i in range(3):
            result = await strategy.check_rate_limit("test_key", rule)
            assert result.allowed is True
        
        # Fourth request should be blocked
        result = await strategy.check_rate_limit("test_key", rule)
        assert result.allowed is False
    
    @pytest.mark.asyncio
    async def test_adaptive_strategy(self):
        """Test adaptive strategy that adjusts based on system load."""
        backend = MemoryBackend()
        base_strategy = SlidingWindowStrategy(backend)
        
        with patch('src.rate_limiting.strategies.psutil') as mock_psutil:
            # Mock high system load
            mock_psutil.cpu_percent.return_value = 90.0  # 90% CPU
            mock_psutil.virtual_memory.return_value.percent = 85.0  # 85% memory
            
            strategy = AdaptiveStrategy(backend, base_strategy, load_threshold=0.8)
            rule = RateLimitRule(limit=10, window=60, cost=1)
            
            result = await strategy.check_rate_limit("test_key", rule)
            
            # Should still be allowed but with reduced limit due to high load
            assert result.allowed is True
            # Limit should be reduced due to high system load
            assert result.limit < 10
    
    @pytest.mark.asyncio
    async def test_multi_tier_strategy(self):
        """Test multi-tier strategy with different time windows."""
        backend = MemoryBackend()
        
        # Multiple tiers: 5 per minute, 50 per hour
        rules = [
            RateLimitRule(limit=5, window=60, cost=1),    # 5 per minute
            RateLimitRule(limit=50, window=3600, cost=1)  # 50 per hour
        ]
        
        strategy = MultiTierStrategy(backend, rules)
        
        # Should be limited by the most restrictive tier (5 per minute)
        for i in range(5):
            result = await strategy.check_rate_limit("test_key", None)
            assert result.allowed is True
        
        # Sixth request should be blocked by first tier
        result = await strategy.check_rate_limit("test_key", None)
        assert result.allowed is False


class TestRateLimitMiddleware:
    """Test FastAPI rate limiting middleware."""
    
    def test_default_key_func(self):
        """Test default key generation function."""
        # Mock request
        request = Mock()
        request.client.host = "192.168.1.100"
        request.headers = {}
        
        key = default_key_func(request)
        assert key == "ip:192.168.1.100"
    
    def test_default_key_func_with_forwarded_header(self):
        """Test key generation with X-Forwarded-For header."""
        request = Mock()
        request.client.host = "10.0.0.1"
        request.headers = {"X-Forwarded-For": "203.0.113.1, 198.51.100.1"}
        
        key = default_key_func(request)
        assert key == "ip:203.0.113.1"
    
    def test_user_key_func(self):
        """Test user-based key generation."""
        request = Mock()
        request.state.user_id = "user123"
        request.client.host = "192.168.1.100"
        request.headers = {}
        
        key = user_key_func(request)
        assert key == "user:user123"
    
    def test_api_key_func(self):
        """Test API key-based key generation."""
        request = Mock()
        request.headers = {"X-API-Key": "secret-api-key-123"}
        request.query_params = {}
        request.client.host = "192.168.1.100"
        
        key = api_key_func(request)
        assert key.startswith("api_key:")
        assert len(key.split(":")[1]) == 16  # MD5 hash truncated to 16 chars
    
    @pytest.mark.asyncio
    async def test_rate_limit_middleware_basic(self):
        """Test basic rate limiting middleware functionality."""
        backend = MemoryBackend()
        strategy = SlidingWindowStrategy(backend)
        rule = RateLimitRule(limit=2, window=60, cost=1)
        
        # Mock FastAPI app and request
        app = Mock()
        request = Mock()
        request.url.path = "/api/test"
        request.client.host = "192.168.1.100"
        request.headers = {}
        
        middleware = RateLimitMiddleware(
            app, backend, strategy, rule
        )
        
        # Mock next handler
        response = Mock()
        response.headers = {}
        
        async def mock_call_next(req):
            return response
        
        # First two requests should pass
        for i in range(2):
            result = await middleware.dispatch(request, mock_call_next)
            assert result == response
            assert "X-RateLimit-Limit" in result.headers
            assert "X-RateLimit-Remaining" in result.headers
        
        # Third request should be rate limited
        with pytest.raises(RateLimitExceeded):
            await middleware.dispatch(request, mock_call_next)
    
    @pytest.mark.asyncio
    async def test_rate_limit_middleware_skip_paths(self):
        """Test middleware skipping certain paths."""
        backend = MemoryBackend()
        strategy = SlidingWindowStrategy(backend)
        rule = RateLimitRule(limit=1, window=60, cost=1)  # Very restrictive
        
        app = Mock()
        request = Mock()
        request.url.path = "/health"  # Should be skipped
        request.client.host = "192.168.1.100"
        request.headers = {}
        
        middleware = RateLimitMiddleware(
            app, backend, strategy, rule, 
            skip_paths=["/health", "/metrics"]
        )
        
        response = Mock()
        response.headers = {}
        
        async def mock_call_next(req):
            return response
        
        # Should not be rate limited despite restrictive rule
        result = await middleware.dispatch(request, mock_call_next)
        assert result == response
        # Should not have rate limit headers
        assert "X-RateLimit-Limit" not in result.headers


class TestRateLimitDecorators:
    """Test rate limiting decorators."""
    
    @pytest.mark.asyncio
    async def test_rate_limit_endpoint_decorator(self):
        """Test endpoint rate limiting decorator."""
        # Configure rate limiting
        backend = MemoryBackend()
        strategy = SlidingWindowStrategy(backend)
        configure_rate_limiting(backend, strategy)
        
        # Mock FastAPI endpoint
        @rate_limit_endpoint(requests_per_minute=2, window=60)
        async def mock_endpoint(request):
            return {"message": "success"}
        
        # Mock request
        request = Mock()
        request.client.host = "192.168.1.100"
        request.headers = {}
        
        # First two calls should succeed
        for i in range(2):
            result = await mock_endpoint(request)
            assert result == {"message": "success"}
        
        # Third call should be rate limited
        with pytest.raises(RateLimitExceeded):
            await mock_endpoint(request)
    
    @pytest.mark.asyncio
    async def test_rate_limit_function_decorator(self):
        """Test function rate limiting decorator."""
        backend = MemoryBackend()
        strategy = SlidingWindowStrategy(backend)
        configure_rate_limiting(backend, strategy)
        
        @rate_limit_function(calls_per_minute=2, window=60)
        async def mock_function():
            return "result"
        
        # First two calls should succeed
        for i in range(2):
            result = await mock_function()
            assert result == "result"
        
        # Third call should raise HTTPException
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await mock_function()
        
        assert exc_info.value.status_code == 429
    
    @pytest.mark.asyncio
    async def test_rate_limit_user_decorator(self):
        """Test user-based rate limiting decorator."""
        backend = MemoryBackend()
        strategy = SlidingWindowStrategy(backend)
        configure_rate_limiting(backend, strategy)
        
        @rate_limit_user(requests_per_minute=2, window=60)
        async def mock_user_function(user_id):
            return f"result for {user_id}"
        
        # Different users should have separate limits
        result1 = await mock_user_function(user_id="user1")
        result2 = await mock_user_function(user_id="user2")
        
        assert result1 == "result for user1"
        assert result2 == "result for user2"
        
        # Same user should be rate limited after limit
        await mock_user_function(user_id="user1")  # Second call for user1
        
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            await mock_user_function(user_id="user1")  # Third call should fail
        
        # Different user should still work
        result = await mock_user_function(user_id="user3")
        assert result == "result for user3"


class TestRateLimitIntegration:
    """Integration tests for rate limiting system."""
    
    def test_setup_rate_limiting_function(self):
        """Test the setup function for FastAPI integration."""
        app = Mock()
        app.add_middleware = Mock()
        
        setup_rate_limiting(
            app,
            requests_per_minute=100,
            skip_paths=["/custom/path"],
            custom_rules={
                "/api/expensive": {"limit": 10, "window": 60}
            }
        )
        
        # Should add middleware to app
        app.add_middleware.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_end_to_end_rate_limiting(self):
        """Test complete rate limiting flow."""
        # Create backend and strategy
        backend = MemoryBackend()
        strategy = SlidingWindowStrategy(backend)
        rule = RateLimitRule(limit=3, window=10, cost=1)
        
        # Simulate multiple requests from same client
        client_key = "ip:192.168.1.100"
        
        # First three should succeed
        for i in range(3):
            result = await strategy.check_rate_limit(client_key, rule)
            assert result.allowed is True
            print(f"Request {i+1}: remaining = {result.remaining}")
        
        # Fourth should fail
        result = await strategy.check_rate_limit(client_key, rule)
        assert result.allowed is False
        assert result.retry_after > 0
        
        print(f"Rate limited: retry_after = {result.retry_after}")
        
        # Wait for window to reset (partial)
        await asyncio.sleep(1)
        
        # Still should be limited
        result = await strategy.check_rate_limit(client_key, rule)
        assert result.allowed is False
        
        # Reset rate limit manually
        await backend.reset_rate_limit(client_key)
        
        # Should work again
        result = await strategy.check_rate_limit(client_key, rule)
        assert result.allowed is True
        assert result.remaining == 2


# Fixtures for testing
@pytest.fixture
def memory_backend():
    """Fixture providing memory backend."""
    return MemoryBackend()


@pytest.fixture
def redis_backend():
    """Fixture providing mocked Redis backend."""
    mock_redis = AsyncMock()
    return RedisBackend(mock_redis)


@pytest.fixture
def sliding_window_strategy(memory_backend):
    """Fixture providing sliding window strategy."""
    return SlidingWindowStrategy(memory_backend)


@pytest.fixture
def rate_limit_rule():
    """Fixture providing basic rate limit rule."""
    return RateLimitRule(limit=5, window=60, cost=1)