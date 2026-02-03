"""FastAPI middleware for monitoring and metrics."""

import time
from typing import Callable
from fastapi import Request, Response, FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

import structlog

from .metrics import get_metrics_manager, request_duration, request_counter, error_counter
from .health import get_health_checker, HealthStatus

logger = structlog.get_logger()


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to collect HTTP request metrics."""
    
    def __init__(self, app: FastAPI, include_paths: bool = True):
        super().__init__(app)
        self.include_paths = include_paths
        self.metrics_manager = get_metrics_manager()
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and collect metrics."""
        start_time = time.time()
        
        # Extract request info
        method = request.method
        path = request.url.path if self.include_paths else "/"
        
        # Skip metrics endpoint itself to avoid recursion
        if path == "/metrics":
            return await call_next(request)
        
        response = None
        status_code = "500"  # Default for exceptions
        
        try:
            response = await call_next(request)
            status_code = str(response.status_code)
            
        except Exception as e:
            logger.error("Request processing failed", 
                        method=method, path=path, error=str(e))
            
            # Record error metric
            error_counter.inc(
                component="http_handler",
                error_type=type(e).__name__
            )
            
            raise
        
        finally:
            # Calculate request duration
            duration = time.time() - start_time
            
            # Record metrics
            request_duration.observe(
                duration,
                method=method,
                endpoint=path,
                status_code=status_code
            )
            
            request_counter.inc(
                method=method,
                endpoint=path,
                status_code=status_code
            )
            
            # Log slow requests
            if duration > 1.0:  # More than 1 second
                logger.warning("Slow request detected",
                             method=method,
                             path=path,
                             duration=duration,
                             status_code=status_code)
        
        return response


class HealthMiddleware(BaseHTTPMiddleware):
    """Middleware to add health check endpoints."""
    
    def __init__(self, app: FastAPI, health_path: str = "/health", 
                 metrics_path: str = "/metrics"):
        super().__init__(app)
        self.health_path = health_path
        self.metrics_path = metrics_path
        self.health_checker = get_health_checker()
        self.metrics_manager = get_metrics_manager()
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Handle health and metrics endpoints."""
        path = request.url.path
        
        # Health endpoint
        if path == self.health_path:
            return await self._handle_health_check(request)
        
        # Metrics endpoint
        elif path == self.metrics_path:
            return await self._handle_metrics(request)
        
        # Regular request
        else:
            return await call_next(request)
    
    async def _handle_health_check(self, request: Request) -> Response:
        """Handle health check requests."""
        try:
            # Check if specific components requested
            components = request.query_params.get("components")
            component_names = components.split(",") if components else None
            
            # Perform health check
            health_result = await self.health_checker.check_health(component_names)
            
            # Prepare response
            response_data = {
                "status": health_result.overall_status.value,
                "timestamp": health_result.timestamp,
                "duration": health_result.check_duration,
                "components": [
                    {
                        "name": comp.name,
                        "status": comp.status.value,
                        "message": comp.message,
                        "response_time": comp.response_time,
                        "metadata": comp.metadata
                    }
                    for comp in health_result.components
                ]
            }
            
            # Set appropriate HTTP status code
            if health_result.overall_status == HealthStatus.HEALTHY:
                status_code = 200
            elif health_result.overall_status == HealthStatus.DEGRADED:
                status_code = 200  # Still operational
            else:  # UNHEALTHY or UNKNOWN
                status_code = 503  # Service Unavailable
            
            return Response(
                content=self._json_response(response_data),
                media_type="application/json",
                status_code=status_code
            )
        
        except Exception as e:
            logger.error("Health check failed", error=str(e))
            
            error_response = {
                "status": "error",
                "message": f"Health check failed: {str(e)}",
                "timestamp": time.time()
            }
            
            return Response(
                content=self._json_response(error_response),
                media_type="application/json",
                status_code=500
            )
    
    async def _handle_metrics(self, request: Request) -> Response:
        """Handle metrics requests in Prometheus format."""
        try:
            # Get metrics format
            format_param = request.query_params.get("format", "prometheus")
            
            if format_param == "json":
                # JSON format
                samples = self.metrics_manager.collect_metrics()
                metrics_data = {
                    "timestamp": time.time(),
                    "metrics": [
                        {
                            "name": sample.name,
                            "labels": sample.labels,
                            "value": sample.value,
                            "timestamp": sample.timestamp
                        }
                        for sample in samples
                    ]
                }
                
                return Response(
                    content=self._json_response(metrics_data),
                    media_type="application/json"
                )
            
            else:
                # Prometheus format (default)
                metrics_text = self.metrics_manager.export_prometheus_format()
                
                return Response(
                    content=metrics_text,
                    media_type="text/plain; version=0.0.4; charset=utf-8"
                )
        
        except Exception as e:
            logger.error("Metrics export failed", error=str(e))
            
            return Response(
                content=f"# Error exporting metrics: {str(e)}\n",
                media_type="text/plain",
                status_code=500
            )
    
    def _json_response(self, data) -> str:
        """Convert data to JSON string."""
        import json
        return json.dumps(data, indent=2, default=str)


def setup_monitoring_middleware(app: FastAPI, 
                               include_metrics: bool = True,
                               include_health: bool = True,
                               health_path: str = "/health",
                               metrics_path: str = "/metrics") -> None:
    """Setup monitoring middleware for FastAPI app."""
    
    if include_metrics:
        app.add_middleware(MetricsMiddleware)
        logger.info("Added metrics middleware")
    
    if include_health:
        app.add_middleware(
            HealthMiddleware,
            health_path=health_path,
            metrics_path=metrics_path
        )
        logger.info("Added health middleware", 
                   health_path=health_path,
                   metrics_path=metrics_path)


# Additional middleware for specific monitoring needs

class DatabaseMetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to track database operations."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Track database metrics for requests that use database."""
        # This would be integrated with SQLAlchemy events
        # to track actual database operation metrics
        
        response = await call_next(request)
        
        # Database metrics would be recorded via SQLAlchemy events
        # or database connection instrumentation
        
        return response


class CacheMetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to track cache hit/miss rates."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Track cache metrics for requests."""
        # This would integrate with Redis/cache operations
        # to track hit rates, miss rates, etc.
        
        response = await call_next(request)
        
        # Cache metrics would be recorded via cache client instrumentation
        
        return response


# Prometheus-style metric decorators

def track_execution_time(metric_name: str = None, labels: dict = None):
    """Decorator to track function execution time."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                status = "success"
            except Exception as e:
                status = "error"
                raise
            finally:
                duration = time.time() - start_time
                
                # Record metric (would need to get appropriate histogram metric)
                # This is a simplified version - real implementation would
                # use the metrics manager to get the right metric
                logger.debug("Function execution tracked",
                           function=func.__name__,
                           duration=duration,
                           status=status)
            
            return result
        return wrapper
    return decorator


def count_calls(metric_name: str = None, labels: dict = None):
    """Decorator to count function calls."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                status = "success"
            except Exception as e:
                status = "error"
                raise
            finally:
                # Record counter metric
                logger.debug("Function call counted",
                           function=func.__name__,
                           status=status)
            
            return result
        return wrapper
    return decorator