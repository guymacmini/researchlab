"""Decorators for rate limiting specific endpoints and functions."""

import functools
import asyncio
from typing import Callable, Optional, Dict, Any, Union

from fastapi import Request, HTTPException
import structlog

from .backends import RateLimitBackend, MemoryBackend
from .strategies import RateLimitStrategy, SlidingWindowStrategy, RateLimitRule
from .middleware import RateLimitExceeded, RateLimitInfo

logger = structlog.get_logger()

# Global backend for decorators (can be configured)
_default_backend: Optional[RateLimitBackend] = None
_default_strategy: Optional[RateLimitStrategy] = None


def configure_rate_limiting(backend: RateLimitBackend, strategy: RateLimitStrategy):
    """Configure global backend and strategy for decorators."""
    global _default_backend, _default_strategy
    _default_backend = backend
    _default_strategy = strategy
    
    logger.info("Rate limiting decorators configured",
               backend_type=type(backend).__name__,
               strategy_type=type(strategy).__name__)


def get_default_backend() -> RateLimitBackend:
    """Get default backend, creating one if needed."""
    global _default_backend
    if _default_backend is None:
        _default_backend = MemoryBackend()
        logger.info("Created default memory backend for rate limiting decorators")
    return _default_backend


def get_default_strategy() -> RateLimitStrategy:
    """Get default strategy, creating one if needed."""
    global _default_strategy
    if _default_strategy is None:
        _default_strategy = SlidingWindowStrategy(get_default_backend())
        logger.info("Created default sliding window strategy for rate limiting decorators")
    return _default_strategy


def rate_limit_endpoint(
    requests_per_minute: int = 60,
    window: int = 60,
    cost: int = 1,
    key_func: Optional[Callable[[Request], str]] = None,
    backend: Optional[RateLimitBackend] = None,
    strategy: Optional[RateLimitStrategy] = None,
    error_message: str = "Rate limit exceeded"
):
    """Decorator for rate limiting FastAPI endpoints.
    
    Args:
        requests_per_minute: Number of requests allowed per minute
        window: Time window in seconds
        cost: Cost of each request (for token bucket)
        key_func: Function to generate rate limit key from request
        backend: Rate limiting backend to use
        strategy: Rate limiting strategy to use
        error_message: Custom error message
    """
    
    def decorator(func: Callable):
        # Create rule
        rule = RateLimitRule(
            limit=requests_per_minute,
            window=window,
            cost=cost
        )
        
        # Get backend and strategy
        backend_to_use = backend or get_default_backend()
        strategy_to_use = strategy or get_default_strategy()
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from args/kwargs
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if request is None:
                # Try to find request in kwargs
                request = kwargs.get('request')
            
            if request is None:
                logger.warning("No request found for rate limiting", function=func.__name__)
                # Skip rate limiting if no request found
                return await func(*args, **kwargs)
            
            # Generate rate limit key
            if key_func:
                try:
                    rate_limit_key = key_func(request)
                except Exception as e:
                    logger.warning("Custom key function failed", error=str(e))
                    rate_limit_key = f"endpoint:{func.__name__}"
            else:
                # Default key based on endpoint and client
                from .middleware import default_key_func
                client_key = default_key_func(request)
                rate_limit_key = f"{client_key}:endpoint:{func.__name__}"
            
            # Check rate limit
            try:
                result = await strategy_to_use.check_rate_limit(rate_limit_key, rule)
                
                if not result.allowed:
                    logger.info("Endpoint rate limit exceeded",
                               function=func.__name__,
                               key=rate_limit_key,
                               limit=result.limit,
                               remaining=result.remaining)
                    
                    rate_limit_info = RateLimitInfo(
                        limit=result.limit,
                        remaining=result.remaining,
                        reset_time=result.reset_time,
                        retry_after=result.retry_after
                    )
                    
                    raise RateLimitExceeded(rate_limit_info)
                
                # Rate limit passed, execute function
                return await func(*args, **kwargs)
            
            except RateLimitExceeded:
                # Re-raise rate limit exceptions
                raise
            
            except Exception as e:
                logger.error("Rate limiting check failed", 
                           function=func.__name__,
                           error=str(e))
                
                # Fail open - execute function if rate limiting fails
                return await func(*args, **kwargs)
        
        # Store rate limit metadata on function
        wrapper._rate_limit_rule = rule
        wrapper._rate_limit_key_func = key_func
        wrapper._rate_limit_backend = backend_to_use
        wrapper._rate_limit_strategy = strategy_to_use
        
        return wrapper
    
    return decorator


def rate_limit_function(
    calls_per_minute: int = 60,
    window: int = 60,
    key: Optional[str] = None,
    per_user: bool = False,
    backend: Optional[RateLimitBackend] = None,
    strategy: Optional[RateLimitStrategy] = None
):
    """Decorator for rate limiting regular functions (not FastAPI endpoints).
    
    Args:
        calls_per_minute: Number of calls allowed per minute
        window: Time window in seconds
        key: Fixed key to use (if not provided, uses function name)
        per_user: If True, rate limit per user (requires user context)
        backend: Rate limiting backend to use
        strategy: Rate limiting strategy to use
    """
    
    def decorator(func: Callable):
        # Create rule
        rule = RateLimitRule(
            limit=calls_per_minute,
            window=window,
            cost=1
        )
        
        # Get backend and strategy
        backend_to_use = backend or get_default_backend()
        strategy_to_use = strategy or get_default_strategy()
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Generate rate limit key
            if key:
                rate_limit_key = key
            elif per_user:
                # Try to extract user ID from context or arguments
                user_id = kwargs.get('user_id') or getattr(args[0], 'user_id', None) if args else None
                if user_id:
                    rate_limit_key = f"user:{user_id}:function:{func.__name__}"
                else:
                    rate_limit_key = f"function:{func.__name__}"
            else:
                rate_limit_key = f"function:{func.__name__}"
            
            # Check rate limit
            try:
                result = await strategy_to_use.check_rate_limit(rate_limit_key, rule)
                
                if not result.allowed:
                    logger.info("Function rate limit exceeded",
                               function=func.__name__,
                               key=rate_limit_key,
                               limit=result.limit,
                               remaining=result.remaining)
                    
                    raise HTTPException(
                        status_code=429,
                        detail={
                            "error": "Function rate limit exceeded",
                            "function": func.__name__,
                            "limit": result.limit,
                            "remaining": result.remaining,
                            "reset_time": result.reset_time,
                            "retry_after": result.retry_after
                        }
                    )
                
                # Rate limit passed, execute function
                return await func(*args, **kwargs)
            
            except HTTPException:
                # Re-raise HTTP exceptions (including rate limit)
                raise
            
            except Exception as e:
                logger.error("Function rate limiting check failed", 
                           function=func.__name__,
                           error=str(e))
                
                # Fail open - execute function if rate limiting fails
                return await func(*args, **kwargs)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For synchronous functions, run the async rate limit check
            try:
                loop = asyncio.get_event_loop()
                return loop.run_until_complete(async_wrapper(*args, **kwargs))
            except RuntimeError:
                # No event loop, create one
                return asyncio.run(async_wrapper(*args, **kwargs))
        
        # Determine if function is async or sync
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def rate_limit_user(
    requests_per_minute: int = 60,
    window: int = 60,
    user_key_func: Optional[Callable[..., str]] = None,
    backend: Optional[RateLimitBackend] = None,
    strategy: Optional[RateLimitStrategy] = None
):
    """Decorator for rate limiting based on user ID.
    
    Args:
        requests_per_minute: Number of requests allowed per minute per user
        window: Time window in seconds
        user_key_func: Function to extract user key from arguments
        backend: Rate limiting backend to use
        strategy: Rate limiting strategy to use
    """
    
    def decorator(func: Callable):
        # Create rule
        rule = RateLimitRule(
            limit=requests_per_minute,
            window=window,
            cost=1
        )
        
        # Get backend and strategy
        backend_to_use = backend or get_default_backend()
        strategy_to_use = strategy or get_default_strategy()
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract user key
            if user_key_func:
                try:
                    user_key = user_key_func(*args, **kwargs)
                except Exception as e:
                    logger.warning("User key function failed", error=str(e))
                    user_key = "unknown"
            else:
                # Try common patterns to extract user ID
                user_key = (
                    kwargs.get('user_id') or 
                    kwargs.get('current_user', {}).get('id') or
                    getattr(args[0], 'user_id', None) if args else None or
                    "unknown"
                )
            
            rate_limit_key = f"user:{user_key}:function:{func.__name__}"
            
            # Check rate limit
            try:
                result = await strategy_to_use.check_rate_limit(rate_limit_key, rule)
                
                if not result.allowed:
                    logger.info("User rate limit exceeded",
                               function=func.__name__,
                               user_key=user_key,
                               limit=result.limit,
                               remaining=result.remaining)
                    
                    raise HTTPException(
                        status_code=429,
                        detail={
                            "error": "User rate limit exceeded",
                            "function": func.__name__,
                            "limit": result.limit,
                            "remaining": result.remaining,
                            "reset_time": result.reset_time,
                            "retry_after": result.retry_after
                        }
                    )
                
                # Rate limit passed, execute function
                return await func(*args, **kwargs)
            
            except HTTPException:
                # Re-raise HTTP exceptions
                raise
            
            except Exception as e:
                logger.error("User rate limiting check failed", 
                           function=func.__name__,
                           error=str(e))
                
                # Fail open
                return await func(*args, **kwargs)
        
        # Store metadata
        wrapper._rate_limit_rule = rule
        wrapper._rate_limit_user_key_func = user_key_func
        
        return wrapper
    
    return decorator


def rate_limit_api_key(
    requests_per_minute: int = 1000,
    window: int = 60,
    backend: Optional[RateLimitBackend] = None,
    strategy: Optional[RateLimitStrategy] = None
):
    """Decorator for rate limiting based on API key.
    
    Args:
        requests_per_minute: Number of requests allowed per minute per API key
        window: Time window in seconds
        backend: Rate limiting backend to use
        strategy: Rate limiting strategy to use
    """
    
    def decorator(func: Callable):
        # Create rule
        rule = RateLimitRule(
            limit=requests_per_minute,
            window=window,
            cost=1
        )
        
        # Get backend and strategy
        backend_to_use = backend or get_default_backend()
        strategy_to_use = strategy or get_default_strategy()
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request to get API key
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if request is None:
                request = kwargs.get('request')
            
            if request is None:
                logger.warning("No request found for API key rate limiting", 
                             function=func.__name__)
                # Skip rate limiting if no request found
                return await func(*args, **kwargs)
            
            # Extract API key
            api_key = (
                request.headers.get("X-API-Key") or
                request.headers.get("Authorization", "").replace("Bearer ", "") or
                request.query_params.get("api_key")
            )
            
            if not api_key:
                # No API key found, use IP-based rate limiting
                from .middleware import default_key_func
                rate_limit_key = f"{default_key_func(request)}:function:{func.__name__}"
            else:
                # Hash API key for privacy
                import hashlib
                key_hash = hashlib.md5(api_key.encode()).hexdigest()[:16]
                rate_limit_key = f"api_key:{key_hash}:function:{func.__name__}"
            
            # Check rate limit
            try:
                result = await strategy_to_use.check_rate_limit(rate_limit_key, rule)
                
                if not result.allowed:
                    logger.info("API key rate limit exceeded",
                               function=func.__name__,
                               has_api_key=bool(api_key),
                               limit=result.limit,
                               remaining=result.remaining)
                    
                    rate_limit_info = RateLimitInfo(
                        limit=result.limit,
                        remaining=result.remaining,
                        reset_time=result.reset_time,
                        retry_after=result.retry_after
                    )
                    
                    raise RateLimitExceeded(rate_limit_info)
                
                # Rate limit passed, execute function
                return await func(*args, **kwargs)
            
            except RateLimitExceeded:
                # Re-raise rate limit exceptions
                raise
            
            except Exception as e:
                logger.error("API key rate limiting check failed", 
                           function=func.__name__,
                           error=str(e))
                
                # Fail open
                return await func(*args, **kwargs)
        
        # Store metadata
        wrapper._rate_limit_rule = rule
        
        return wrapper
    
    return decorator


# Utility functions for decorator management
def get_rate_limit_info_from_function(func: Callable) -> Optional[Dict[str, Any]]:
    """Get rate limit information from a decorated function."""
    if hasattr(func, '_rate_limit_rule'):
        rule = func._rate_limit_rule
        return {
            "limit": rule.limit,
            "window": rule.window,
            "cost": rule.cost,
            "burst": rule.burst,
            "backend_type": type(getattr(func, '_rate_limit_backend', None)).__name__,
            "strategy_type": type(getattr(func, '_rate_limit_strategy', None)).__name__
        }
    return None


def list_rate_limited_functions() -> List[Dict[str, Any]]:
    """List all functions with rate limit decorators."""
    # This would require a registry of decorated functions
    # For now, return empty list as placeholder
    return []