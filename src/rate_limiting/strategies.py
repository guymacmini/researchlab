"""Rate limiting strategies implementation."""

import time
import math
from typing import Optional, Dict, Any, List
from abc import ABC, abstractmethod
from dataclasses import dataclass

import structlog

from .backends import RateLimitBackend, RateLimitResult

logger = structlog.get_logger()


@dataclass
class RateLimitRule:
    """Rate limiting rule configuration."""
    limit: int
    window: int
    burst: Optional[int] = None  # For token bucket
    cost: int = 1


class RateLimitStrategy(ABC):
    """Abstract base class for rate limiting strategies."""
    
    def __init__(self, backend: RateLimitBackend):
        self.backend = backend
    
    @abstractmethod
    async def check_rate_limit(self, key: str, rule: RateLimitRule) -> RateLimitResult:
        """Check if request is within rate limit."""
        pass
    
    @abstractmethod
    def get_strategy_name(self) -> str:
        """Get strategy name."""
        pass


class FixedWindowStrategy(RateLimitStrategy):
    """Fixed window rate limiting strategy.
    
    Divides time into fixed windows and allows a fixed number of requests per window.
    Simple but can allow bursts at window boundaries.
    """
    
    def get_strategy_name(self) -> str:
        return "fixed_window"
    
    async def check_rate_limit(self, key: str, rule: RateLimitRule) -> RateLimitResult:
        """Check rate limit using fixed window approach."""
        current_time = time.time()
        
        # Calculate current window
        window_start = int(current_time // rule.window) * rule.window
        window_key = f"{key}:fw:{window_start}"
        
        # Use backend to check/update counter for this window
        result = await self.backend.check_rate_limit(
            window_key, rule.limit, rule.window, rule.cost
        )
        
        # Adjust reset time to end of current window
        result.reset_time = window_start + rule.window
        
        return result


class SlidingWindowStrategy(RateLimitStrategy):
    """Sliding window rate limiting strategy.
    
    Maintains a sliding window that moves with each request.
    More accurate than fixed window but requires more storage.
    """
    
    def get_strategy_name(self) -> str:
        return "sliding_window"
    
    async def check_rate_limit(self, key: str, rule: RateLimitRule) -> RateLimitResult:
        """Check rate limit using sliding window approach."""
        # The backend handles sliding window logic
        return await self.backend.check_rate_limit(
            key, rule.limit, rule.window, rule.cost
        )


class TokenBucketStrategy(RateLimitStrategy):
    """Token bucket rate limiting strategy.
    
    Maintains a bucket of tokens that refill at a steady rate.
    Allows for burst traffic up to bucket capacity.
    """
    
    def get_strategy_name(self) -> str:
        return "token_bucket"
    
    async def check_rate_limit(self, key: str, rule: RateLimitRule) -> RateLimitResult:
        """Check rate limit using token bucket approach."""
        current_time = time.time()
        
        # Get current bucket state
        bucket_info = await self.backend.get_rate_limit_info(f"{key}:tb")
        
        if bucket_info is None:
            # Initialize new bucket
            bucket_state = {
                "tokens": rule.burst or rule.limit,
                "last_refill": current_time
            }
        else:
            # Load existing bucket state
            bucket_state = bucket_info.get("bucket_state", {
                "tokens": rule.burst or rule.limit,
                "last_refill": current_time
            })
        
        # Calculate tokens to add based on time elapsed
        time_elapsed = current_time - bucket_state["last_refill"]
        refill_rate = rule.limit / rule.window  # tokens per second
        tokens_to_add = time_elapsed * refill_rate
        
        # Update bucket
        max_tokens = rule.burst or rule.limit
        bucket_state["tokens"] = min(max_tokens, bucket_state["tokens"] + tokens_to_add)
        bucket_state["last_refill"] = current_time
        
        # Check if enough tokens available
        if bucket_state["tokens"] >= rule.cost:
            # Consume tokens
            bucket_state["tokens"] -= rule.cost
            
            # Store updated bucket state
            await self._store_bucket_state(key, bucket_state)
            
            return RateLimitResult(
                allowed=True,
                limit=max_tokens,
                remaining=int(bucket_state["tokens"]),
                reset_time=current_time + (max_tokens - bucket_state["tokens"]) / refill_rate
            )
        else:
            # Not enough tokens
            tokens_needed = rule.cost - bucket_state["tokens"]
            retry_after = tokens_needed / refill_rate
            
            return RateLimitResult(
                allowed=False,
                limit=max_tokens,
                remaining=int(bucket_state["tokens"]),
                reset_time=current_time + retry_after,
                retry_after=retry_after
            )
    
    async def _store_bucket_state(self, key: str, bucket_state: Dict[str, Any]):
        """Store bucket state using backend."""
        # This is a simplified implementation
        # In practice, you'd need a proper way to store complex state
        bucket_key = f"{key}:tb"
        
        # For now, we'll use a mock storage approach
        # Real implementation would need backend support for complex data
        try:
            # Store as a single "request" with encoded state
            await self.backend.check_rate_limit(bucket_key, 1, 3600, 0)
        except Exception as e:
            logger.warning("Failed to store bucket state", key=key, error=str(e))


class AdaptiveStrategy(RateLimitStrategy):
    """Adaptive rate limiting strategy that adjusts limits based on system load."""
    
    def __init__(self, backend: RateLimitBackend, base_strategy: RateLimitStrategy,
                 load_threshold: float = 0.8, adaptation_factor: float = 0.5):
        super().__init__(backend)
        self.base_strategy = base_strategy
        self.load_threshold = load_threshold
        self.adaptation_factor = adaptation_factor
    
    def get_strategy_name(self) -> str:
        return f"adaptive_{self.base_strategy.get_strategy_name()}"
    
    async def check_rate_limit(self, key: str, rule: RateLimitRule) -> RateLimitResult:
        """Check rate limit with adaptive adjustment based on system load."""
        
        # Get current system load (simplified)
        system_load = await self._get_system_load()
        
        # Adjust rule based on load
        adjusted_rule = self._adjust_rule_for_load(rule, system_load)
        
        # Use base strategy with adjusted rule
        result = await self.base_strategy.check_rate_limit(key, adjusted_rule)
        
        # Add adaptation info to result metadata
        if hasattr(result, 'metadata'):
            result.metadata = getattr(result, 'metadata', {})
            result.metadata.update({
                "system_load": system_load,
                "adaptation_applied": adjusted_rule.limit != rule.limit,
                "original_limit": rule.limit,
                "adapted_limit": adjusted_rule.limit
            })
        
        return result
    
    async def _get_system_load(self) -> float:
        """Get current system load (0.0 to 1.0)."""
        try:
            import psutil
            
            # Combine CPU and memory usage
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory_percent = psutil.virtual_memory().percent
            
            # Weighted average
            load = (cpu_percent * 0.6 + memory_percent * 0.4) / 100
            return min(1.0, load)
        
        except ImportError:
            # psutil not available, assume normal load
            return 0.5
        except Exception as e:
            logger.warning("Failed to get system load", error=str(e))
            return 0.5
    
    def _adjust_rule_for_load(self, rule: RateLimitRule, load: float) -> RateLimitRule:
        """Adjust rate limit rule based on system load."""
        
        if load < self.load_threshold:
            # System under normal load, use original rule
            return rule
        
        # System under high load, reduce limits
        overload_factor = (load - self.load_threshold) / (1.0 - self.load_threshold)
        reduction_factor = 1.0 - (overload_factor * self.adaptation_factor)
        
        adjusted_limit = max(1, int(rule.limit * reduction_factor))
        
        return RateLimitRule(
            limit=adjusted_limit,
            window=rule.window,
            burst=rule.burst,
            cost=rule.cost
        )


class MultiTierStrategy(RateLimitStrategy):
    """Multi-tier rate limiting with different limits for different time windows."""
    
    def __init__(self, backend: RateLimitBackend, rules: List[RateLimitRule]):
        super().__init__(backend)
        self.rules = sorted(rules, key=lambda r: r.window)  # Sort by window size
    
    def get_strategy_name(self) -> str:
        return "multi_tier"
    
    async def check_rate_limit(self, key: str, rule: RateLimitRule) -> RateLimitResult:
        """Check rate limit across multiple tiers."""
        
        # Check all tiers, starting with the most restrictive
        for i, tier_rule in enumerate(self.rules):
            tier_key = f"{key}:tier:{i}"
            
            # Use sliding window for each tier
            sliding_strategy = SlidingWindowStrategy(self.backend)
            result = await sliding_strategy.check_rate_limit(tier_key, tier_rule)
            
            if not result.allowed:
                # Request blocked by this tier
                logger.debug("Rate limit exceeded", 
                           key=key, tier=i, window=tier_rule.window, 
                           limit=tier_rule.limit)
                return result
        
        # All tiers passed, request is allowed
        # Return result from the most permissive tier (last one checked)
        return result


class GeographicStrategy(RateLimitStrategy):
    """Geographic-based rate limiting with different limits per region."""
    
    def __init__(self, backend: RateLimitBackend, 
                 region_rules: Dict[str, RateLimitRule],
                 default_rule: RateLimitRule):
        super().__init__(backend)
        self.region_rules = region_rules
        self.default_rule = default_rule
    
    def get_strategy_name(self) -> str:
        return "geographic"
    
    async def check_rate_limit(self, key: str, rule: RateLimitRule) -> RateLimitResult:
        """Check rate limit with geographic considerations."""
        
        # Extract region from key (assumes key format includes region)
        region = self._extract_region_from_key(key)
        
        # Get appropriate rule for region
        region_rule = self.region_rules.get(region, self.default_rule)
        
        # Use sliding window strategy with region-specific rule
        regional_key = f"{key}:geo:{region}"
        sliding_strategy = SlidingWindowStrategy(self.backend)
        
        return await sliding_strategy.check_rate_limit(regional_key, region_rule)
    
    def _extract_region_from_key(self, key: str) -> str:
        """Extract region from rate limit key."""
        # Simple implementation - assumes key format like "user:123:US"
        parts = key.split(":")
        if len(parts) >= 3:
            return parts[-1]
        return "default"


# Factory function to create strategies
def create_strategy(strategy_name: str, backend: RateLimitBackend, 
                   **kwargs) -> RateLimitStrategy:
    """Factory function to create rate limiting strategies."""
    
    strategies = {
        "fixed_window": FixedWindowStrategy,
        "sliding_window": SlidingWindowStrategy,
        "token_bucket": TokenBucketStrategy,
        "adaptive": AdaptiveStrategy,
        "multi_tier": MultiTierStrategy,
        "geographic": GeographicStrategy,
    }
    
    if strategy_name not in strategies:
        raise ValueError(f"Unknown strategy: {strategy_name}")
    
    strategy_class = strategies[strategy_name]
    
    try:
        return strategy_class(backend, **kwargs)
    except TypeError as e:
        logger.error("Failed to create strategy", 
                    strategy=strategy_name, error=str(e))
        # Fallback to sliding window
        return SlidingWindowStrategy(backend)