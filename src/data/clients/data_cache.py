"""Data caching system with Redis backend."""

import json
import hashlib
from typing import Any, Optional, Dict, List
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict

import structlog
import redis.asyncio as redis

from src.core.config import settings

logger = structlog.get_logger()


@dataclass
class CacheEntry:
    """Cache entry with metadata."""
    key: str
    data: Any
    created_at: datetime
    expires_at: Optional[datetime] = None
    source: Optional[str] = None
    tags: List[str] = None
    
    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at
    
    def time_to_expiry(self) -> Optional[timedelta]:
        """Get time until expiry."""
        if self.expires_at is None:
            return None
        return self.expires_at - datetime.utcnow()


class DataCache:
    """Redis-backed data cache with expiration and tagging."""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis = redis_client
        self.logger = logger.bind(component="data_cache")
        self._connected = False
    
    async def connect(self) -> None:
        """Connect to Redis if not already connected."""
        if not self.redis:
            self.redis = redis.from_url(
                settings.database.redis_url,
                decode_responses=True,
                health_check_interval=30
            )
        
        if not self._connected:
            try:
                await self.redis.ping()
                self._connected = True
                self.logger.info("cache_connected")
            except Exception as e:
                self.logger.error("cache_connection_failed", error=str(e))
                raise
    
    async def set(
        self,
        key: str,
        data: Any,
        ttl_seconds: Optional[int] = None,
        source: str = None,
        tags: List[str] = None
    ) -> None:
        """Store data in cache with optional expiration and tags."""
        await self.connect()
        
        entry = CacheEntry(
            key=key,
            data=data,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(seconds=ttl_seconds) if ttl_seconds else None,
            source=source,
            tags=tags or []
        )
        
        try:
            # Serialize the entry
            serialized = json.dumps(asdict(entry), default=str)
            
            # Store in Redis
            if ttl_seconds:
                await self.redis.setex(key, ttl_seconds, serialized)
            else:
                await self.redis.set(key, serialized)
            
            # Add tags for easier querying
            if tags:
                for tag in tags:
                    await self.redis.sadd(f"tag:{tag}", key)
                    if ttl_seconds:
                        await self.redis.expire(f"tag:{tag}", ttl_seconds + 3600)  # Tag expires 1 hour later
            
            self.logger.debug("cache_set", key=key, ttl=ttl_seconds, tags=len(tags) if tags else 0)
            
        except Exception as e:
            self.logger.error("cache_set_failed", key=key, error=str(e))
            raise
    
    async def get(self, key: str) -> Optional[Any]:
        """Get data from cache."""
        await self.connect()
        
        try:
            serialized = await self.redis.get(key)
            
            if not serialized:
                self.logger.debug("cache_miss", key=key)
                return None
            
            # Deserialize entry
            entry_dict = json.loads(serialized)
            entry = CacheEntry(**entry_dict)
            
            # Check if expired (additional check beyond Redis TTL)
            if entry.is_expired():
                await self.delete(key)
                self.logger.debug("cache_expired", key=key)
                return None
            
            self.logger.debug("cache_hit", key=key, age_seconds=(datetime.utcnow() - entry.created_at).total_seconds())
            return entry.data
            
        except json.JSONDecodeError:
            self.logger.warning("cache_invalid_data", key=key)
            await self.delete(key)
            return None
        except Exception as e:
            self.logger.error("cache_get_failed", key=key, error=str(e))
            return None
    
    async def get_entry(self, key: str) -> Optional[CacheEntry]:
        """Get full cache entry with metadata."""
        await self.connect()
        
        try:
            serialized = await self.redis.get(key)
            
            if not serialized:
                return None
            
            entry_dict = json.loads(serialized)
            entry = CacheEntry(**entry_dict)
            
            if entry.is_expired():
                await self.delete(key)
                return None
            
            return entry
            
        except Exception as e:
            self.logger.error("cache_get_entry_failed", key=key, error=str(e))
            return None
    
    async def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        await self.connect()
        
        try:
            result = await self.redis.delete(key)
            self.logger.debug("cache_delete", key=key, existed=bool(result))
            return bool(result)
        except Exception as e:
            self.logger.error("cache_delete_failed", key=key, error=str(e))
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        await self.connect()
        
        try:
            return bool(await self.redis.exists(key))
        except Exception as e:
            self.logger.error("cache_exists_failed", key=key, error=str(e))
            return False
    
    async def clear_by_tag(self, tag: str) -> int:
        """Clear all cache entries with a specific tag."""
        await self.connect()
        
        try:
            # Get all keys with this tag
            keys = await self.redis.smembers(f"tag:{tag}")
            
            if keys:
                # Delete all keys
                deleted = await self.redis.delete(*keys)
                # Clean up the tag set
                await self.redis.delete(f"tag:{tag}")
                
                self.logger.info("cache_cleared_by_tag", tag=tag, count=deleted)
                return deleted
            
            return 0
            
        except Exception as e:
            self.logger.error("cache_clear_tag_failed", tag=tag, error=str(e))
            return 0
    
    async def clear_expired(self) -> int:
        """Clear all expired entries (Redis should handle this automatically with TTL)."""
        await self.connect()
        
        # This is mainly for cleanup of entries without TTL that have logical expiration
        cleared = 0
        try:
            # Scan through all keys (use cursor for large datasets)
            async for key in self.redis.scan_iter(match="*"):
                if not key.startswith("tag:"):  # Skip tag keys
                    entry = await self.get_entry(key)
                    if entry and entry.is_expired():
                        await self.delete(key)
                        cleared += 1
            
            if cleared > 0:
                self.logger.info("cache_expired_cleared", count=cleared)
            
            return cleared
            
        except Exception as e:
            self.logger.error("cache_clear_expired_failed", error=str(e))
            return 0
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        await self.connect()
        
        try:
            info = await self.redis.info('memory')
            keyspace = await self.redis.info('keyspace')
            
            # Count total keys
            total_keys = 0
            if 'db0' in keyspace:
                total_keys = keyspace['db0']['keys']
            
            return {
                'total_keys': total_keys,
                'memory_used_bytes': info.get('used_memory', 0),
                'memory_used_human': info.get('used_memory_human', '0B'),
                'connected': self._connected,
                'redis_version': info.get('redis_version', 'unknown')
            }
            
        except Exception as e:
            self.logger.error("cache_stats_failed", error=str(e))
            return {'error': str(e)}
    
    def make_key(self, *parts: str) -> str:
        """Create a cache key from multiple parts."""
        # Join parts and create a hash for very long keys
        key = ":".join(str(part) for part in parts)
        
        # If key is too long, hash it
        if len(key) > 200:
            hash_digest = hashlib.sha256(key.encode()).hexdigest()[:16]
            key = f"{parts[0]}:hash:{hash_digest}" if parts else f"hash:{hash_digest}"
        
        return key
    
    async def close(self) -> None:
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()
            self._connected = False
            self.logger.info("cache_disconnected")


# Global cache instance
_cache: Optional[DataCache] = None


async def get_cache() -> DataCache:
    """Get the global cache instance."""
    global _cache
    if _cache is None:
        _cache = DataCache()
    return _cache


def cache_key_for_api_call(api_name: str, endpoint: str, **params) -> str:
    """Generate a consistent cache key for API calls."""
    # Sort parameters for consistent key generation
    param_parts = []
    for key, value in sorted(params.items()):
        if value is not None:
            param_parts.append(f"{key}={value}")
    
    param_string = "&".join(param_parts)
    return f"api:{api_name}:{endpoint}:{param_string}"


# Common cache TTL values
CACHE_TTL = {
    'stock_quote': 60,           # 1 minute for real-time data
    'company_profile': 3600,     # 1 hour for company info  
    'financial_statements': 14400,  # 4 hours for financials
    'news': 1800,               # 30 minutes for news
    'market_data': 300,         # 5 minutes for market data
    'analyst_estimates': 7200,  # 2 hours for estimates
    'default': 3600            # 1 hour default
}