"""Health checking system for ResearchLab."""

import asyncio
import time
import httpx
from typing import Dict, List, Optional, Any, Callable, Awaitable
from dataclasses import dataclass
from enum import Enum
import threading

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from ..core.database import get_async_session
from ..core.config import get_settings

logger = structlog.get_logger()


class HealthStatus(Enum):
    """Health check status."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health status of a component."""
    name: str
    status: HealthStatus
    message: str = ""
    response_time: Optional[float] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class HealthCheckResult:
    """Result of a complete health check."""
    overall_status: HealthStatus
    components: List[ComponentHealth]
    timestamp: float
    check_duration: float


class BaseHealthCheck:
    """Base class for health checks."""
    
    def __init__(self, name: str, timeout: float = 5.0):
        self.name = name
        self.timeout = timeout
    
    async def check(self) -> ComponentHealth:
        """Perform the health check."""
        start_time = time.time()
        
        try:
            # Run the check with timeout
            result = await asyncio.wait_for(
                self._perform_check(),
                timeout=self.timeout
            )
            
            response_time = time.time() - start_time
            
            return ComponentHealth(
                name=self.name,
                status=result.get("status", HealthStatus.UNKNOWN),
                message=result.get("message", ""),
                response_time=response_time,
                metadata=result.get("metadata", {})
            )
        
        except asyncio.TimeoutError:
            response_time = time.time() - start_time
            return ComponentHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check timed out after {self.timeout}s",
                response_time=response_time
            )
        
        except Exception as e:
            response_time = time.time() - start_time
            logger.error("Health check failed", component=self.name, error=str(e))
            return ComponentHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {str(e)}",
                response_time=response_time
            )
    
    async def _perform_check(self) -> Dict[str, Any]:
        """Perform the actual health check. Override in subclasses."""
        raise NotImplementedError


class DatabaseHealthCheck(BaseHealthCheck):
    """Database connectivity health check."""
    
    def __init__(self, timeout: float = 5.0):
        super().__init__("database", timeout)
    
    async def _perform_check(self) -> Dict[str, Any]:
        """Check database connectivity."""
        try:
            async with get_async_session() as session:
                # Simple query to test connectivity
                result = await session.execute("SELECT 1")
                await result.fetchone()
                
                return {
                    "status": HealthStatus.HEALTHY,
                    "message": "Database connection successful",
                    "metadata": {"driver": "postgresql+asyncpg"}
                }
        
        except Exception as e:
            return {
                "status": HealthStatus.UNHEALTHY,
                "message": f"Database connection failed: {str(e)}"
            }


class RedisHealthCheck(BaseHealthCheck):
    """Redis connectivity health check."""
    
    def __init__(self, timeout: float = 5.0):
        super().__init__("redis", timeout)
    
    async def _perform_check(self) -> Dict[str, Any]:
        """Check Redis connectivity."""
        settings = get_settings()
        
        try:
            redis = Redis.from_url(settings.database.redis_url)
            
            # Test connection with PING
            await redis.ping()
            
            # Test basic operations
            await redis.set("health_check", "ok", ex=1)
            result = await redis.get("health_check")
            
            await redis.close()
            
            if result == b"ok":
                return {
                    "status": HealthStatus.HEALTHY,
                    "message": "Redis connection successful",
                    "metadata": {"url": settings.database.redis_url}
                }
            else:
                return {
                    "status": HealthStatus.DEGRADED,
                    "message": "Redis set/get operation failed"
                }
        
        except Exception as e:
            return {
                "status": HealthStatus.UNHEALTHY,
                "message": f"Redis connection failed: {str(e)}"
            }


class ExternalAPIHealthCheck(BaseHealthCheck):
    """External API health check."""
    
    def __init__(self, api_name: str, url: str, headers: Optional[Dict[str, str]] = None, 
                 timeout: float = 10.0):
        super().__init__(f"api_{api_name}", timeout)
        self.api_name = api_name
        self.url = url
        self.headers = headers or {}
    
    async def _perform_check(self) -> Dict[str, Any]:
        """Check external API availability."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.url, headers=self.headers)
                
                if response.status_code < 400:
                    return {
                        "status": HealthStatus.HEALTHY,
                        "message": f"{self.api_name} API is accessible",
                        "metadata": {
                            "status_code": response.status_code,
                            "url": self.url
                        }
                    }
                else:
                    return {
                        "status": HealthStatus.DEGRADED,
                        "message": f"{self.api_name} API returned status {response.status_code}",
                        "metadata": {
                            "status_code": response.status_code,
                            "url": self.url
                        }
                    }
        
        except httpx.TimeoutException:
            return {
                "status": HealthStatus.UNHEALTHY,
                "message": f"{self.api_name} API request timed out"
            }
        
        except Exception as e:
            return {
                "status": HealthStatus.UNHEALTHY,
                "message": f"{self.api_name} API check failed: {str(e)}"
            }


class DiskSpaceHealthCheck(BaseHealthCheck):
    """Disk space health check."""
    
    def __init__(self, path: str = "/", warning_threshold: float = 0.8, 
                 critical_threshold: float = 0.9, timeout: float = 5.0):
        super().__init__("disk_space", timeout)
        self.path = path
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
    
    async def _perform_check(self) -> Dict[str, Any]:
        """Check disk space usage."""
        try:
            import shutil
            
            total, used, free = shutil.disk_usage(self.path)
            usage_ratio = used / total
            
            metadata = {
                "path": self.path,
                "total_bytes": total,
                "used_bytes": used,
                "free_bytes": free,
                "usage_percent": round(usage_ratio * 100, 2)
            }
            
            if usage_ratio >= self.critical_threshold:
                return {
                    "status": HealthStatus.UNHEALTHY,
                    "message": f"Disk usage critical: {usage_ratio:.1%} used",
                    "metadata": metadata
                }
            elif usage_ratio >= self.warning_threshold:
                return {
                    "status": HealthStatus.DEGRADED,
                    "message": f"Disk usage warning: {usage_ratio:.1%} used",
                    "metadata": metadata
                }
            else:
                return {
                    "status": HealthStatus.HEALTHY,
                    "message": f"Disk usage normal: {usage_ratio:.1%} used",
                    "metadata": metadata
                }
        
        except Exception as e:
            return {
                "status": HealthStatus.UNKNOWN,
                "message": f"Could not check disk space: {str(e)}"
            }


class MemoryHealthCheck(BaseHealthCheck):
    """Memory usage health check."""
    
    def __init__(self, warning_threshold: float = 0.8, critical_threshold: float = 0.9,
                 timeout: float = 5.0):
        super().__init__("memory", timeout)
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
    
    async def _perform_check(self) -> Dict[str, Any]:
        """Check memory usage."""
        try:
            import psutil
            
            memory = psutil.virtual_memory()
            usage_ratio = memory.percent / 100
            
            metadata = {
                "total_bytes": memory.total,
                "available_bytes": memory.available,
                "used_bytes": memory.used,
                "usage_percent": memory.percent
            }
            
            if usage_ratio >= self.critical_threshold:
                return {
                    "status": HealthStatus.UNHEALTHY,
                    "message": f"Memory usage critical: {memory.percent:.1f}%",
                    "metadata": metadata
                }
            elif usage_ratio >= self.warning_threshold:
                return {
                    "status": HealthStatus.DEGRADED,
                    "message": f"Memory usage warning: {memory.percent:.1f}%",
                    "metadata": metadata
                }
            else:
                return {
                    "status": HealthStatus.HEALTHY,
                    "message": f"Memory usage normal: {memory.percent:.1f}%",
                    "metadata": metadata
                }
        
        except ImportError:
            return {
                "status": HealthStatus.UNKNOWN,
                "message": "psutil not available for memory monitoring"
            }
        except Exception as e:
            return {
                "status": HealthStatus.UNKNOWN,
                "message": f"Could not check memory usage: {str(e)}"
            }


class HealthChecker:
    """Central health checking system."""
    
    def __init__(self):
        self.checks: List[BaseHealthCheck] = []
        self._lock = threading.Lock()
        
        # Register default checks
        self._register_default_checks()
        
        logger.info("Health checker initialized")
    
    def _register_default_checks(self):
        """Register default health checks."""
        settings = get_settings()
        
        # Database check
        if settings.monitoring.health_enabled:
            self.add_check(DatabaseHealthCheck())
            
            # Redis check
            self.add_check(RedisHealthCheck())
            
            # System checks
            self.add_check(DiskSpaceHealthCheck())
            self.add_check(MemoryHealthCheck())
            
            # External API checks if keys are configured
            if settings.api.finnhub_api_key:
                self.add_check(ExternalAPIHealthCheck(
                    "finnhub",
                    "https://finnhub.io/api/v1/quote?symbol=AAPL",
                    {"X-Finnhub-Token": settings.api.finnhub_api_key}
                ))
            
            if settings.api.alpha_vantage_api_key:
                self.add_check(ExternalAPIHealthCheck(
                    "alpha_vantage",
                    f"https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=AAPL&interval=1min&apikey={settings.api.alpha_vantage_api_key}&outputsize=compact"
                ))
            
            if settings.api.anthropic_api_key:
                self.add_check(ExternalAPIHealthCheck(
                    "anthropic",
                    "https://api.anthropic.com/v1/models",
                    {"x-api-key": settings.api.anthropic_api_key}
                ))
    
    def add_check(self, check: BaseHealthCheck) -> None:
        """Add a health check."""
        with self._lock:
            self.checks.append(check)
            logger.debug("Added health check", name=check.name)
    
    def remove_check(self, name: str) -> bool:
        """Remove a health check by name."""
        with self._lock:
            for i, check in enumerate(self.checks):
                if check.name == name:
                    del self.checks[i]
                    logger.debug("Removed health check", name=name)
                    return True
            return False
    
    async def check_health(self, component_names: Optional[List[str]] = None) -> HealthCheckResult:
        """Perform health checks."""
        start_time = time.time()
        
        # Filter checks if component names specified
        checks_to_run = self.checks
        if component_names:
            checks_to_run = [c for c in self.checks if c.name in component_names]
        
        # Run all checks concurrently
        tasks = [check.check() for check in checks_to_run]
        component_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        components = []
        for result in component_results:
            if isinstance(result, ComponentHealth):
                components.append(result)
            else:
                # Handle unexpected exceptions
                components.append(ComponentHealth(
                    name="unknown",
                    status=HealthStatus.UNKNOWN,
                    message=f"Unexpected error: {str(result)}"
                ))
        
        # Determine overall status
        overall_status = self._calculate_overall_status(components)
        
        check_duration = time.time() - start_time
        
        result = HealthCheckResult(
            overall_status=overall_status,
            components=components,
            timestamp=start_time,
            check_duration=check_duration
        )
        
        logger.info("Health check completed", 
                   overall_status=overall_status.value,
                   components_checked=len(components),
                   duration=check_duration)
        
        return result
    
    def _calculate_overall_status(self, components: List[ComponentHealth]) -> HealthStatus:
        """Calculate overall status from component statuses."""
        if not components:
            return HealthStatus.UNKNOWN
        
        statuses = [c.status for c in components]
        
        # If any component is unhealthy, overall is unhealthy
        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY
        
        # If any component is degraded, overall is degraded
        if HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED
        
        # If any component is unknown, overall is unknown
        if HealthStatus.UNKNOWN in statuses:
            return HealthStatus.UNKNOWN
        
        # All components are healthy
        return HealthStatus.HEALTHY
    
    def get_component_names(self) -> List[str]:
        """Get list of registered component names."""
        with self._lock:
            return [check.name for check in self.checks]


# Global health checker instance
_health_checker: Optional[HealthChecker] = None
_checker_lock = threading.Lock()


def get_health_checker() -> HealthChecker:
    """Get the global health checker instance."""
    global _health_checker
    
    with _checker_lock:
        if _health_checker is None:
            _health_checker = HealthChecker()
        
        return _health_checker