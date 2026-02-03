"""FastAPI middleware for enhanced request/response logging."""

import time
import uuid
import json
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from fastapi import FastAPI

from .logging import (
    get_logger, 
    set_request_id, 
    log_api_call,
    LoggingContext
)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log HTTP requests and responses with detailed context."""
    
    def __init__(
        self, 
        app: FastAPI,
        include_request_body: bool = False,
        include_response_body: bool = False,
        max_body_size: int = 1024,
        skip_paths: Optional[list] = None
    ):
        super().__init__(app)
        self.include_request_body = include_request_body
        self.include_response_body = include_response_body  
        self.max_body_size = max_body_size
        self.skip_paths = skip_paths or ["/health", "/metrics", "/docs", "/openapi.json"]
        self.logger = get_logger("request_middleware")
    
    async def dispatch(self, request: Request, call_next):
        """Process request and response with comprehensive logging."""
        # Skip logging for certain paths
        if any(request.url.path.startswith(path) for path in self.skip_paths):
            return await call_next(request)
        
        # Generate and set request ID
        request_id = str(uuid.uuid4())
        set_request_id(request_id)
        
        # Start timing
        start_time = time.time()
        
        # Extract client information
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        
        # Log request start
        request_data = {
            "event": "request_started",
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params) if request.query_params else None,
            "client_ip": client_ip,
            "user_agent": user_agent[:200],  # Truncate long user agents
            "content_length": request.headers.get("content-length"),
            "content_type": request.headers.get("content-type")
        }
        
        # Include request body if configured
        if self.include_request_body and request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await self._get_request_body(request)
                if body and len(body) <= self.max_body_size:
                    request_data["request_body"] = body
                elif body:
                    request_data["request_body_size"] = len(body)
                    request_data["request_body_truncated"] = True
            except Exception as e:
                self.logger.warning("Failed to read request body", error=str(e))
        
        self.logger.info("http_request_started", **request_data)
        
        # Process request
        response = None
        error_occurred = False
        error_details = None
        
        try:
            response = await call_next(request)
            
        except Exception as e:
            error_occurred = True
            error_details = {
                "error_type": type(e).__name__,
                "error_message": str(e)
            }
            # Re-raise to let error handlers deal with it
            raise
        
        finally:
            # Calculate timing
            duration_ms = (time.time() - start_time) * 1000
            
            # Log response or error
            response_data = {
                "event": "request_completed",
                "method": request.method,
                "path": request.url.path,
                "duration_ms": round(duration_ms, 2),
                "client_ip": client_ip
            }
            
            if response:
                response_data.update({
                    "status_code": response.status_code,
                    "response_size": response.headers.get("content-length")
                })
                
                # Add response headers of interest
                interesting_headers = ["content-type", "cache-control", "x-rate-limit-remaining"]
                for header in interesting_headers:
                    value = response.headers.get(header)
                    if value:
                        response_data[f"response_{header.replace('-', '_')}"] = value
            
            if error_occurred:
                response_data.update(error_details)
                self.logger.error("http_request_failed", **response_data)
            else:
                # Use log_api_call for standardized API logging
                log_api_call(
                    endpoint=request.url.path,
                    method=request.method,
                    status_code=response.status_code if response else 500,
                    duration_ms=duration_ms,
                    client_ip=client_ip
                )
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request headers."""
        # Check various headers for real IP
        for header in ["x-forwarded-for", "x-real-ip", "x-forwarded-host"]:
            ip = request.headers.get(header)
            if ip:
                # Take the first IP if multiple are present
                return ip.split(",")[0].strip()
        
        # Fallback to remote address
        if hasattr(request, "client") and request.client:
            return request.client.host
        
        return "unknown"
    
    async def _get_request_body(self, request: Request) -> Optional[str]:
        """Safely extract request body for logging."""
        try:
            body = await request.body()
            if not body:
                return None
            
            # Try to decode as text
            try:
                text_body = body.decode("utf-8")
                
                # Try to parse as JSON for pretty formatting
                try:
                    json_body = json.loads(text_body)
                    return json.dumps(json_body, separators=(",", ":"))  # Compact JSON
                except json.JSONDecodeError:
                    return text_body
                    
            except UnicodeDecodeError:
                # Binary content
                return f"<binary content, {len(body)} bytes>"
                
        except Exception:
            return None


def setup_request_logging(app: FastAPI, **kwargs) -> None:
    """Add request logging middleware to FastAPI app."""
    app.add_middleware(RequestLoggingMiddleware, **kwargs)
    
    logger = get_logger("middleware")
    logger.info("Request logging middleware added to application")