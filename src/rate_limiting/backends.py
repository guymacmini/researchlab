"""Rate limiting backends for different storage mechanisms."""

import time
import asyncio
from typing import Optional, Dict, Any, List, Tuple
from abc import ABC, abstractmethod
from dataclasses import dataclass
import threading

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger()


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""
    allowed: bool
    limit: int
    remaining: int
    reset_time: float
    retry_after: Optional[float] = None


class RateLimitBackend(ABC):
    """Abstract base class for rate limiting backends."""
    
    @abstractmethod
    async def check_rate_limit(self, key: str, limit: int, window: int, 
                              cost: int = 1) -> RateLimitResult:
        """Check if a request is within the rate limit."""
        pass
    
    @abstractmethod
    async def reset_rate_limit(self, key: str) -> bool:
        """Reset rate limit for a key."""
        pass
    
    @abstractmethod
    async def get_rate_limit_info(self, key: str) -> Optional[Dict[str, Any]]:
        """Get current rate limit information for a key."""
        pass


class MemoryBackend(RateLimitBackend):
    """In-memory rate limiting backend using local storage."""
    
    def __init__(self, cleanup_interval: int = 300):
        """Initialize memory backend.
        
        Args:
            cleanup_interval: Interval in seconds to clean up expired entries
        """
        self.storage: Dict[str, List[Tuple[float, int]]] = {}
        self.lock = threading.RLock()
        self.cleanup_interval = cleanup_interval
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # Start cleanup task
        self._start_cleanup_task()
    
    def _start_cleanup_task(self):
        """Start the cleanup background task."""
        try:
            loop = asyncio.get_event_loop()
            self._cleanup_task = loop.create_task(self._cleanup_expired())
        except RuntimeError:
            # No event loop running, cleanup will be done manually
            pass
    
    async def _cleanup_expired(self):
        """Clean up expired entries periodically."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._perform_cleanup()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Rate limit cleanup failed", error=str(e))
    
    async def _perform_cleanup(self):
        """Perform cleanup of expired entries."""
        current_time = time.time()
        keys_to_remove = []
        
        with self.lock:
            for key, requests in self.storage.items():
                # Remove requests older than 1 hour (conservative cleanup)
                cutoff_time = current_time - 3600
                self.storage[key] = [(ts, cost) for ts, cost in requests if ts > cutoff_time]
                
                # If no requests remain, mark key for removal
                if not self.storage[key]:
                    keys_to_remove.append(key)
            
            # Remove empty keys
            for key in keys_to_remove:
                del self.storage[key]
        
        if keys_to_remove:
            logger.debug("Cleaned up expired rate limit entries", 
                        count=len(keys_to_remove))
    
    async def check_rate_limit(self, key: str, limit: int, window: int, 
                              cost: int = 1) -> RateLimitResult:
        """Check rate limit using sliding window approach."""
        current_time = time.time()
        window_start = current_time - window
        
        with self.lock:
            # Get or create request history for this key
            requests = self.storage.get(key, [])
            
            # Remove requests outside the window
            valid_requests = [(ts, c) for ts, c in requests if ts > window_start]
            
            # Calculate current usage
            current_usage = sum(c for _, c in valid_requests)
            
            # Check if request would exceed limit
            if current_usage + cost > limit:
                # Request would exceed limit
                remaining = max(0, limit - current_usage)
                
                # Calculate when the oldest request will expire
                if valid_requests:
                    oldest_request_time = min(ts for ts, _ in valid_requests)
                    retry_after = oldest_request_time + window - current_time
                else:
                    retry_after = window
                
                return RateLimitResult(
                    allowed=False,
                    limit=limit,
                    remaining=remaining,
                    reset_time=current_time + window,
                    retry_after=retry_after
                )
            
            # Request is allowed, record it
            valid_requests.append((current_time, cost))
            self.storage[key] = valid_requests
            
            remaining = limit - (current_usage + cost)
            
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=remaining,
                reset_time=current_time + window
            )
    
    async def reset_rate_limit(self, key: str) -> bool:
        """Reset rate limit for a key."""
        with self.lock:
            if key in self.storage:
                del self.storage[key]
                logger.debug("Rate limit reset", key=key)
                return True
            return False
    
    async def get_rate_limit_info(self, key: str) -> Optional[Dict[str, Any]]:
        """Get current rate limit information for a key."""
        with self.lock:
            requests = self.storage.get(key, [])
            if not requests:
                return None
            
            current_time = time.time()
            total_requests = len(requests)
            total_cost = sum(cost for _, cost in requests)
            
            # Get recent requests (last 60 seconds)
            recent_cutoff = current_time - 60
            recent_requests = [(ts, cost) for ts, cost in requests if ts > recent_cutoff]
            
            return {
                "key": key,
                "total_requests": total_requests,
                "total_cost": total_cost,
                "recent_requests": len(recent_requests),
                "recent_cost": sum(cost for _, cost in recent_requests),
                "oldest_request": min(ts for ts, _ in requests) if requests else None,
                "newest_request": max(ts for ts, _ in requests) if requests else None,
            }
    
    def __del__(self):
        """Cleanup when backend is destroyed."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()


class RedisBackend(RateLimitBackend):
    """Redis-based rate limiting backend using distributed storage."""
    
    def __init__(self, redis: Redis, key_prefix: str = "rate_limit:"):
        """Initialize Redis backend.
        
        Args:
            redis: Redis client instance
            key_prefix: Prefix for Redis keys
        """
        self.redis = redis
        self.key_prefix = key_prefix
    
    def _make_key(self, key: str) -> str:
        """Create Redis key with prefix."""
        return f"{self.key_prefix}{key}"
    
    async def check_rate_limit(self, key: str, limit: int, window: int,
                              cost: int = 1) -> RateLimitResult:
        """Check rate limit using Redis sorted sets for sliding window."""
        redis_key = self._make_key(key)
        current_time = time.time()
        window_start = current_time - window
        
        # Use Redis pipeline for atomic operations
        pipe = self.redis.pipeline(transaction=True)
        
        try:
            # Remove expired entries
            pipe.zremrangebyscore(redis_key, 0, window_start)
            
            # Count current requests in window
            pipe.zcard(redis_key)
            
            # Execute pipeline
            results = await pipe.execute()
            current_count = results[1]
            
            # Calculate current usage (simplified - assuming cost=1 for each entry)
            # For more complex cost handling, we'd need to store costs in the sorted set
            current_usage = current_count
            
            if current_usage + cost > limit:
                # Request would exceed limit
                remaining = max(0, limit - current_usage)
                
                # Get the oldest entry to calculate retry_after
                oldest_entries = await self.redis.zrange(redis_key, 0, 0, withscores=True)
                if oldest_entries:
                    oldest_time = oldest_entries[0][1]
                    retry_after = oldest_time + window - current_time
                else:
                    retry_after = window
                
                return RateLimitResult(
                    allowed=False,
                    limit=limit,
                    remaining=remaining,
                    reset_time=current_time + window,
                    retry_after=max(0, retry_after)
                )
            
            # Request is allowed, add it to the sorted set
            pipe = self.redis.pipeline(transaction=True)
            
            # Add current request with timestamp as score
            pipe.zadd(redis_key, {str(current_time): current_time})
            
            # Set expiry for the key (cleanup)
            pipe.expire(redis_key, window + 60)
            
            await pipe.execute()
            
            remaining = limit - (current_usage + cost)
            
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=remaining,
                reset_time=current_time + window
            )
        
        except Exception as e:
            logger.error("Redis rate limit check failed", key=key, error=str(e))
            
            # Fail open - allow request if Redis is unavailable
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=limit - 1,
                reset_time=current_time + window
            )
    
    async def reset_rate_limit(self, key: str) -> bool:
        """Reset rate limit for a key."""
        redis_key = self._make_key(key)
        
        try:
            result = await self.redis.delete(redis_key)
            logger.debug("Rate limit reset", key=key, deleted=bool(result))
            return bool(result)
        
        except Exception as e:
            logger.error("Failed to reset rate limit", key=key, error=str(e))
            return False
    
    async def get_rate_limit_info(self, key: str) -> Optional[Dict[str, Any]]:
        """Get current rate limit information for a key."""
        redis_key = self._make_key(key)
        
        try:
            # Get all entries with scores
            entries = await self.redis.zrange(redis_key, 0, -1, withscores=True)
            
            if not entries:
                return None
            
            current_time = time.time()
            timestamps = [score for _, score in entries]
            
            # Calculate statistics
            total_requests = len(entries)
            oldest_request = min(timestamps) if timestamps else None
            newest_request = max(timestamps) if timestamps else None
            
            # Recent requests (last 60 seconds)
            recent_cutoff = current_time - 60
            recent_requests = sum(1 for ts in timestamps if ts > recent_cutoff)
            
            return {
                "key": key,
                "total_requests": total_requests,
                "recent_requests": recent_requests,
                "oldest_request": oldest_request,
                "newest_request": newest_request,
                "ttl": await self.redis.ttl(redis_key)
            }
        
        except Exception as e:
            logger.error("Failed to get rate limit info", key=key, error=str(e))
            return None


class HybridBackend(RateLimitBackend):
    """Hybrid backend that uses memory for hot paths and Redis for persistence."""
    
    def __init__(self, redis: Redis, memory_cache_size: int = 1000,
                 memory_ttl: int = 300):
        """Initialize hybrid backend.
        
        Args:
            redis: Redis client instance
            memory_cache_size: Maximum number of keys to cache in memory
            memory_ttl: TTL for memory cache entries in seconds
        """
        self.redis_backend = RedisBackend(redis)
        self.memory_backend = MemoryBackend()
        self.memory_cache_size = memory_cache_size
        self.memory_ttl = memory_ttl
        
        # Track memory cache usage
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0
        }
    
    async def check_rate_limit(self, key: str, limit: int, window: int,
                              cost: int = 1) -> RateLimitResult:
        """Check rate limit using memory cache first, then Redis."""
        
        # For high-frequency keys, use memory backend
        if await self._should_use_memory(key, limit, window):
            self.cache_stats["hits"] += 1
            return await self.memory_backend.check_rate_limit(key, limit, window, cost)
        
        # Use Redis backend for distributed consistency
        self.cache_stats["misses"] += 1
        return await self.redis_backend.check_rate_limit(key, limit, window, cost)
    
    async def _should_use_memory(self, key: str, limit: int, window: int) -> bool:
        """Determine if memory backend should be used for this key."""
        
        # Use memory for high-rate limits or short windows
        if limit > 100 or window < 60:
            return True
        
        # Check if key is already in memory cache
        info = await self.memory_backend.get_rate_limit_info(key)
        if info and info["recent_requests"] > 5:
            return True
        
        return False
    
    async def reset_rate_limit(self, key: str) -> bool:
        """Reset rate limit in both backends."""
        memory_result = await self.memory_backend.reset_rate_limit(key)
        redis_result = await self.redis_backend.reset_rate_limit(key)
        
        return memory_result or redis_result
    
    async def get_rate_limit_info(self, key: str) -> Optional[Dict[str, Any]]:
        """Get rate limit info, preferring Redis for accuracy."""
        redis_info = await self.redis_backend.get_rate_limit_info(key)
        memory_info = await self.memory_backend.get_rate_limit_info(key)
        
        # Combine information from both backends
        if redis_info and memory_info:
            return {
                **redis_info,
                "memory_cache": memory_info,
                "cache_stats": self.cache_stats
            }
        
        return redis_info or memory_info