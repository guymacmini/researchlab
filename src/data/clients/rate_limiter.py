"""Rate limiting utilities for API clients."""

import asyncio
import time
from typing import Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import structlog

logger = structlog.get_logger()


@dataclass
class RateLimit:
    """Rate limit configuration."""
    requests_per_minute: int
    requests_per_hour: Optional[int] = None
    requests_per_day: Optional[int] = None
    burst_size: Optional[int] = None  # Allow burst requests up to this size


@dataclass 
class RateLimitState:
    """Current state of rate limiting for a specific key."""
    minute_requests: int = 0
    hour_requests: int = 0
    day_requests: int = 0
    last_reset_minute: datetime = field(default_factory=datetime.utcnow)
    last_reset_hour: datetime = field(default_factory=datetime.utcnow)
    last_reset_day: datetime = field(default_factory=datetime.utcnow)
    burst_tokens: int = 0


class AsyncRateLimiter:
    """Async rate limiter with multiple time windows and burst support."""
    
    def __init__(self, default_limit: RateLimit = None):
        self.limits: Dict[str, RateLimit] = {}
        self.states: Dict[str, RateLimitState] = {}
        self.locks: Dict[str, asyncio.Lock] = {}
        self.default_limit = default_limit or RateLimit(requests_per_minute=60)
        
        self.logger = logger.bind(component="rate_limiter")
    
    def set_limit(self, key: str, limit: RateLimit) -> None:
        """Set rate limit for a specific key."""
        self.limits[key] = limit
        if key not in self.states:
            self.states[key] = RateLimitState()
            self.locks[key] = asyncio.Lock()
        
        # Initialize burst tokens
        if limit.burst_size:
            self.states[key].burst_tokens = limit.burst_size
        
        self.logger.info("rate_limit_set", key=key, limit=limit.requests_per_minute)
    
    async def acquire(self, key: str, cost: int = 1) -> None:
        """Acquire permission for API request, waiting if necessary."""
        if key not in self.limits:
            self.set_limit(key, self.default_limit)
        
        async with self.locks[key]:
            await self._acquire_internal(key, cost)
    
    async def _acquire_internal(self, key: str, cost: int) -> None:
        """Internal acquire logic."""
        limit = self.limits[key]
        state = self.states[key]
        
        # Reset counters if time windows have passed
        now = datetime.utcnow()
        self._reset_counters(state, now)
        
        # Check if we can use burst tokens first
        if limit.burst_size and state.burst_tokens >= cost:
            state.burst_tokens -= cost
            self.logger.debug("request_allowed_burst", key=key, cost=cost, tokens_remaining=state.burst_tokens)
            return
        
        # Check rate limits in order of restrictiveness
        delays = []
        
        # Check minute limit
        if state.minute_requests + cost > limit.requests_per_minute:
            next_minute = state.last_reset_minute + timedelta(minutes=1)
            delay_seconds = (next_minute - now).total_seconds()
            if delay_seconds > 0:
                delays.append(delay_seconds)
        
        # Check hour limit
        if limit.requests_per_hour and state.hour_requests + cost > limit.requests_per_hour:
            next_hour = state.last_reset_hour + timedelta(hours=1)
            delay_seconds = (next_hour - now).total_seconds()
            if delay_seconds > 0:
                delays.append(delay_seconds)
        
        # Check day limit
        if limit.requests_per_day and state.day_requests + cost > limit.requests_per_day:
            next_day = state.last_reset_day + timedelta(days=1)
            delay_seconds = (next_day - now).total_seconds()
            if delay_seconds > 0:
                delays.append(delay_seconds)
        
        # If any limits exceeded, wait for the shortest required time
        if delays:
            wait_time = min(delays)
            self.logger.info("rate_limit_exceeded", key=key, wait_time=wait_time)
            await asyncio.sleep(wait_time)
            
            # Reset counters again after waiting
            now = datetime.utcnow()
            self._reset_counters(state, now)
        
        # Update counters
        state.minute_requests += cost
        state.hour_requests += cost
        state.day_requests += cost
        
        self.logger.debug(
            "request_allowed",
            key=key,
            cost=cost,
            minute_remaining=limit.requests_per_minute - state.minute_requests
        )
    
    def _reset_counters(self, state: RateLimitState, now: datetime) -> None:
        """Reset rate limit counters if time windows have passed."""
        # Reset minute counter
        if now >= state.last_reset_minute + timedelta(minutes=1):
            state.minute_requests = 0
            state.last_reset_minute = now
            
            # Replenish some burst tokens
            if hasattr(state, 'burst_tokens'):
                max_tokens = self._get_burst_size_for_state(state)
                if max_tokens:
                    # Replenish 25% of burst tokens each minute
                    replenish = max(1, max_tokens // 4)
                    state.burst_tokens = min(max_tokens, state.burst_tokens + replenish)
        
        # Reset hour counter
        if now >= state.last_reset_hour + timedelta(hours=1):
            state.hour_requests = 0
            state.last_reset_hour = now
        
        # Reset day counter  
        if now >= state.last_reset_day + timedelta(days=1):
            state.day_requests = 0
            state.last_reset_day = now
    
    def _get_burst_size_for_state(self, state: RateLimitState) -> Optional[int]:
        """Get burst size for a state (helper method)."""
        # This is a bit hacky - in a real implementation you'd store this with the state
        for limit in self.limits.values():
            if limit.burst_size:
                return limit.burst_size
        return None
    
    def get_stats(self, key: str) -> Dict[str, any]:
        """Get current rate limiting stats for a key."""
        if key not in self.states:
            return {}
        
        limit = self.limits.get(key, self.default_limit)
        state = self.states[key]
        
        return {
            'minute_requests': state.minute_requests,
            'minute_limit': limit.requests_per_minute,
            'minute_remaining': limit.requests_per_minute - state.minute_requests,
            'hour_requests': state.hour_requests if limit.requests_per_hour else None,
            'hour_remaining': (limit.requests_per_hour - state.hour_requests) if limit.requests_per_hour else None,
            'day_requests': state.day_requests if limit.requests_per_day else None,
            'day_remaining': (limit.requests_per_day - state.day_requests) if limit.requests_per_day else None,
            'burst_tokens': getattr(state, 'burst_tokens', 0)
        }


class RateLimiter:
    """Synchronous rate limiter (wrapper around AsyncRateLimiter)."""
    
    def __init__(self, default_limit: RateLimit = None):
        self.async_limiter = AsyncRateLimiter(default_limit)
    
    def set_limit(self, key: str, limit: RateLimit) -> None:
        """Set rate limit for a specific key."""
        self.async_limiter.set_limit(key, limit)
    
    def acquire(self, key: str, cost: int = 1) -> None:
        """Acquire permission for API request, waiting if necessary."""
        # For synchronous usage, we need to run the async method
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If already in an async context, this won't work
                raise RuntimeError("Cannot use synchronous rate limiter in async context")
            else:
                loop.run_until_complete(self.async_limiter.acquire(key, cost))
        except RuntimeError:
            # Create new event loop for sync usage
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                new_loop.run_until_complete(self.async_limiter.acquire(key, cost))
            finally:
                new_loop.close()
    
    def get_stats(self, key: str) -> Dict[str, any]:
        """Get current rate limiting stats for a key."""
        return self.async_limiter.get_stats(key)


# Global rate limiter instances
_async_rate_limiter: Optional[AsyncRateLimiter] = None
_sync_rate_limiter: Optional[RateLimiter] = None


def get_async_rate_limiter() -> AsyncRateLimiter:
    """Get the global async rate limiter instance."""
    global _async_rate_limiter
    if _async_rate_limiter is None:
        _async_rate_limiter = AsyncRateLimiter()
    return _async_rate_limiter


def get_rate_limiter() -> RateLimiter:
    """Get the global synchronous rate limiter instance.""" 
    global _sync_rate_limiter
    if _sync_rate_limiter is None:
        _sync_rate_limiter = RateLimiter()
    return _sync_rate_limiter