"""FastAPI middleware for rate limiting."""

import time
from typing import Callable, Optional, Dict, Any, List
from dataclasses import dataclass
import ipaddress

from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

from .backends import RateLimitBackend, MemoryBackend, RedisBackend
from .strategies import RateLimitStrategy, SlidingWindowStrategy, RateLimitRule

logger = structlog.get_logger()


@dataclass
class RateLimitInfo:
    """Rate limit information for responses."""
    limit: int
    remaining: int
    reset_time: float
    retry_after: Optional[float] = None


class RateLimitExceeded(HTTPException):
    """Exception raised when rate limit is exceeded."""
    
    def __init__(self, rate_limit_info: RateLimitInfo):
        self.rate_limit_info = rate_limit_info
        
        detail = {
            "error": "Rate limit exceeded",
            "limit": rate_limit_info.limit,
            "remaining": rate_limit_info.remaining,
            "reset_time": rate_limit_info.reset_time
        }
        
        if rate_limit_info.retry_after:
            detail["retry_after"] = rate_limit_info.retry_after
        
        headers = {
            "X-RateLimit-Limit": str(rate_limit_info.limit),
            "X-RateLimit-Remaining": str(rate_limit_info.remaining),
            "X-RateLimit-Reset": str(int(rate_limit_info.reset_time)),
        }
        
        if rate_limit_info.retry_after:
            headers["Retry-After"] = str(int(rate_limit_info.retry_after))
        
        super().__init__(
            status_code=429,
            detail=detail,
            headers=headers
        )


def default_key_func(request: Request) -> str:
    """Default function to generate rate limit keys."""
    # Use client IP as default identifier
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"
    
    return f"ip:{client_ip}"


def user_key_func(request: Request) -> str:
    """Generate rate limit key based on authenticated user."""
    # This would integrate with your authentication system
    user_id = getattr(request.state, 'user_id', None)
    if user_id:
        return f"user:{user_id}"
    
    # Fallback to IP-based limiting
    return default_key_func(request)


def api_key_func(request: Request) -> str:
    """Generate rate limit key based on API key."""
    api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if api_key:
        # Use a hash for privacy
        import hashlib
        key_hash = hashlib.md5(api_key.encode()).hexdigest()[:16]
        return f"api_key:{key_hash}"
    
    # Fallback to IP-based limiting
    return default_key_func(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting."""
    
    def __init__(
        self,
        app,
        backend: RateLimitBackend,
        strategy: RateLimitStrategy,
        default_rule: RateLimitRule,
        key_func: Callable[[Request], str] = default_key_func,
        skip_paths: Optional[List[str]] = None,
        skip_ips: Optional[List[str]] = None,
        custom_rules: Optional[Dict[str, RateLimitRule]] = None
    ):
        super().__init__(app)
        self.backend = backend
        self.strategy = strategy
        self.default_rule = default_rule
        self.key_func = key_func
        self.skip_paths = skip_paths or []
        self.skip_ips = self._parse_ip_list(skip_ips or [])
        self.custom_rules = custom_rules or {}
        
        logger.info("Rate limiting middleware initialized",
                   strategy=strategy.get_strategy_name(),
                   default_limit=default_rule.limit,
                   default_window=default_rule.window)
    
    def _parse_ip_list(self, ip_list: List[str]) -> List[ipaddress.IPv4Network]:
        """Parse list of IP addresses/networks to skip."""
        networks = []
        for ip_str in ip_list:
            try:
                if "/" not in ip_str:
                    ip_str += "/32"  # Single IP
                networks.append(ipaddress.IPv4Network(ip_str, strict=False))
            except ValueError as e:
                logger.warning("Invalid IP address in skip list", ip=ip_str, error=str(e))
        return networks
    
    def _should_skip_request(self, request: Request) -> bool:
        """Check if request should skip rate limiting."""
        
        # Skip certain paths
        if request.url.path in self.skip_paths:
            return True
        
        # Skip certain IPs
        if self.skip_ips:
            try:
                client_ip = request.client.host if request.client else None
                if client_ip:
                    client_addr = ipaddress.IPv4Address(client_ip)
                    for network in self.skip_ips:
                        if client_addr in network:
                            return True
            except (ValueError, AttributeError):
                # Invalid IP or no client info
                pass
        
        return False
    
    def _get_rule_for_request(self, request: Request) -> RateLimitRule:
        """Get appropriate rate limit rule for request."""
        
        # Check for custom rules based on path
        path = request.url.path
        for pattern, rule in self.custom_rules.items():
            if self._path_matches_pattern(path, pattern):
                return rule
        
        # Use default rule
        return self.default_rule
    
    def _path_matches_pattern(self, path: str, pattern: str) -> bool:
        """Check if path matches pattern (simple glob-style matching)."""
        if pattern == path:
            return True
        
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return path.startswith(prefix)
        
        if pattern.startswith("*"):
            suffix = pattern[1:]
            return path.endswith(suffix)
        
        return False
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting."""
        
        # Skip rate limiting for certain requests
        if self._should_skip_request(request):
            return await call_next(request)
        
        # Generate rate limit key
        try:
            rate_limit_key = self.key_func(request)
        except Exception as e:
            logger.warning("Failed to generate rate limit key", error=str(e))
            rate_limit_key = default_key_func(request)
        
        # Get appropriate rule
        rule = self._get_rule_for_request(request)
        
        # Check rate limit
        try:
            result = await self.strategy.check_rate_limit(rate_limit_key, rule)
            
            # Create rate limit info
            rate_limit_info = RateLimitInfo(
                limit=result.limit,
                remaining=result.remaining,
                reset_time=result.reset_time,
                retry_after=result.retry_after
            )
            
            # Check if request is allowed
            if not result.allowed:
                logger.info("Rate limit exceeded",
                           key=rate_limit_key,
                           path=request.url.path,
                           limit=result.limit,
                           remaining=result.remaining)
                
                # Record rate limit violation in monitoring
                from ..monitoring import error_counter
                error_counter.inc(
                    component="rate_limiting",
                    error_type="rate_limit_exceeded"
                )
                
                raise RateLimitExceeded(rate_limit_info)
            
            # Request allowed, process it
            response = await call_next(request)
            
            # Add rate limit headers to response
            response.headers["X-RateLimit-Limit"] = str(rate_limit_info.limit)
            response.headers["X-RateLimit-Remaining"] = str(rate_limit_info.remaining)
            response.headers["X-RateLimit-Reset"] = str(int(rate_limit_info.reset_time))
            
            if rate_limit_info.retry_after:
                response.headers["X-RateLimit-Retry-After"] = str(int(rate_limit_info.retry_after))
            
            return response
        
        except RateLimitExceeded:
            # Re-raise rate limit exceptions
            raise
        
        except Exception as e:
            logger.error("Rate limiting failed", 
                        key=rate_limit_key, 
                        error=str(e))
            
            # Fail open - allow request if rate limiting fails
            return await call_next(request)


def setup_rate_limiting(
    app,
    backend: Optional[RateLimitBackend] = None,
    strategy_name: str = "sliding_window",
    requests_per_minute: int = 60,
    burst_size: Optional[int] = None,
    key_func: Optional[Callable[[Request], str]] = None,
    skip_paths: Optional[List[str]] = None,
    skip_ips: Optional[List[str]] = None,
    custom_rules: Optional[Dict[str, Dict[str, int]]] = None
) -> None:
    """Setup rate limiting middleware for FastAPI app.
    
    Args:
        app: FastAPI application
        backend: Rate limiting backend (default: MemoryBackend)
        strategy_name: Rate limiting strategy name
        requests_per_minute: Default requests per minute limit
        burst_size: Burst size for token bucket strategy
        key_func: Function to generate rate limit keys
        skip_paths: Paths to skip rate limiting
        skip_ips: IP addresses to skip rate limiting
        custom_rules: Custom rules for specific paths
    """
    
    # Create backend if not provided
    if backend is None:
        backend = MemoryBackend()
    
    # Create strategy
    from .strategies import create_strategy
    strategy = create_strategy(strategy_name, backend)
    
    # Create default rule
    default_rule = RateLimitRule(
        limit=requests_per_minute,
        window=60,  # 1 minute
        burst=burst_size,
        cost=1
    )
    
    # Convert custom rules
    parsed_custom_rules = {}
    if custom_rules:
        for path_pattern, rule_config in custom_rules.items():
            parsed_custom_rules[path_pattern] = RateLimitRule(
                limit=rule_config.get("limit", requests_per_minute),
                window=rule_config.get("window", 60),
                burst=rule_config.get("burst", burst_size),
                cost=rule_config.get("cost", 1)
            )
    
    # Setup default skip paths
    default_skip_paths = ["/health", "/metrics", "/docs", "/redoc", "/openapi.json"]
    if skip_paths:
        skip_paths.extend(default_skip_paths)
    else:
        skip_paths = default_skip_paths
    
    # Add middleware
    app.add_middleware(
        RateLimitMiddleware,
        backend=backend,
        strategy=strategy,
        default_rule=default_rule,
        key_func=key_func or default_key_func,
        skip_paths=skip_paths,
        skip_ips=skip_ips,
        custom_rules=parsed_custom_rules
    )
    
    logger.info("Rate limiting middleware added to application",
               strategy=strategy_name,
               requests_per_minute=requests_per_minute,
               skip_paths=len(skip_paths))


# Decorator for function-level rate limiting
def rate_limit_key_func(func: Callable[[Request], str]):
    """Decorator to mark a function as a rate limit key generator."""
    func._is_rate_limit_key_func = True
    return func


def rate_limit(
    rule: Optional[RateLimitRule] = None,
    requests_per_minute: int = 60,
    window: int = 60,
    cost: int = 1,
    key_func: Optional[Callable[[Request], str]] = None
):
    """Decorator for endpoint-specific rate limiting.
    
    Note: This decorator would need integration with the middleware
    to work effectively. For now, it's a placeholder for future implementation.
    """
    def decorator(func):
        # Store rate limit configuration on function
        if rule:
            func._rate_limit_rule = rule
        else:
            func._rate_limit_rule = RateLimitRule(
                limit=requests_per_minute,
                window=window,
                cost=cost
            )
        
        if key_func:
            func._rate_limit_key_func = key_func
        
        return func
    
    return decorator


# Admin functions for rate limit management
async def reset_rate_limit(backend: RateLimitBackend, key: str) -> bool:
    """Reset rate limit for a specific key."""
    return await backend.reset_rate_limit(key)


async def get_rate_limit_status(backend: RateLimitBackend, key: str) -> Optional[Dict[str, Any]]:
    """Get current rate limit status for a key."""
    return await backend.get_rate_limit_info(key)


async def list_active_rate_limits(backend: RateLimitBackend) -> List[Dict[str, Any]]:
    """List all active rate limits (implementation depends on backend)."""
    # This would need backend-specific implementation
    # For now, return empty list as placeholder
    logger.warning("list_active_rate_limits not implemented for backend type",
                  backend_type=type(backend).__name__)
    return []