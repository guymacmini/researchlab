"""FastAPI application factory with comprehensive middleware and monitoring.

This module creates and configures the main FastAPI application instance with:
- Structured logging and request tracing
- Rate limiting and security middleware  
- Health checks and metrics collection
- OpenAPI documentation enhancements
- CORS and security headers
- Database and Redis integration
- Multi-agent research API endpoints

The application follows enterprise patterns with proper error handling,
monitoring, and observability features for production deployment.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any

import structlog
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .logging import setup_logging
from .logging_middleware import setup_request_logging
from .database import init_db, close_db
from ..monitoring import setup_monitoring_middleware
from ..rate_limiting import setup_rate_limiting

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan management."""
    logger = structlog.get_logger()
    
    # Startup
    logger.info("starting_application", version=settings.app.version)
    setup_logging()
    await init_db()
    logger.info("application_started")
    
    yield
    
    # Shutdown
    logger.info("shutting_down_application")
    await close_db()
    logger.info("application_shutdown")


def create_app() -> FastAPI:
    """Create and configure FastAPI application.
    
    Returns:
        FastAPI: Fully configured FastAPI application instance with middleware,
                 routes, and monitoring enabled.
    """
    
    app = FastAPI(
        title=settings.app.app_name,
        version=settings.app.version,
        description="AI-Led Investment Research Platform - Multi-agent system for comprehensive equity analysis",
        summary="Professional-grade investment research through specialized AI agents",
        lifespan=lifespan,
        debug=settings.app.debug,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=[
            {
                "name": "research",
                "description": "Research project management - Start, monitor, and retrieve investment research analyses",
            },
            {
                "name": "workflow", 
                "description": "Workflow orchestration - Control and monitor agent execution workflows",
            },
            {
                "name": "news",
                "description": "News monitoring - Track and analyze market-relevant news and sentiment",
            },
            {
                "name": "agents",
                "description": "Agent management - Direct interaction with specialized research agents", 
            },
            {
                "name": "companies",
                "description": "Company data - Access company profiles, financials, and market data",
            },
            {
                "name": "monitoring",
                "description": "System monitoring - Health checks, metrics, and performance monitoring",
            }
        ],
        contact={
            "name": "ResearchLab Support",
            "email": "support@researchlab.com",
            "url": "https://researchlab.com/support"
        },
        license_info={
            "name": "Proprietary",
            "url": "https://researchlab.com/license"
        },
        servers=[
            {
                "url": "http://localhost:8000",
                "description": "Development server"
            },
            {
                "url": "https://api.researchlab.com", 
                "description": "Production server"
            }
        ]
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )
    
    # Setup monitoring middleware
    setup_monitoring_middleware(
        app,
        include_metrics=settings.monitoring.metrics_enabled,
        include_health=settings.monitoring.health_enabled,
        health_path=settings.monitoring.health_path,
        metrics_path=settings.monitoring.metrics_path
    )
    
    # Setup rate limiting middleware
    if settings.security.rate_limit_enabled:
        # Create Redis backend if Redis is available, otherwise use memory
        backend = None
        if settings.database.redis_url and settings.app.environment != "testing":
            try:
                from redis.asyncio import Redis
                redis_client = Redis.from_url(settings.database.redis_url)
                from ..rate_limiting.backends import RedisBackend
                backend = RedisBackend(redis_client)
                logger.info("Using Redis backend for rate limiting")
            except ImportError:
                logger.warning("Redis not available, using memory backend for rate limiting")
        
        setup_rate_limiting(
            app,
            backend=backend,
            requests_per_minute=settings.security.requests_per_minute,
            burst_size=settings.security.burst_size,
            skip_ips=["127.0.0.1", "::1"],  # Skip localhost
            custom_rules={
                "/api/v1/research/*": {"limit": 30, "window": 60},  # More restrictive for research endpoints
                "/api/v1/workflow/execute": {"limit": 10, "window": 60},  # Very restrictive for workflow execution
                "/api/v1/news/*": {"limit": 100, "window": 60}  # Higher limit for news endpoints
            }
        )
    
    # Setup enhanced request logging (this includes request ID management)
    setup_request_logging(
        app,
        include_request_body=settings.app.environment == "development",
        include_response_body=False,  # Usually too verbose
        max_body_size=2048,
        skip_paths=["/health", "/metrics", "/docs", "/openapi.json", "/redoc"]
    )
    
    # Simple request ID middleware for response headers (request ID is set by logging middleware)
    @app.middleware("http")
    async def add_request_id_header(request: Request, call_next):
        """Add request ID to response headers."""
        from .logging import get_request_id
        
        response = await call_next(request)
        
        # Get request ID from logging context (set by logging middleware)
        request_id = get_request_id()
        if request_id:
            response.headers["X-Request-ID"] = request_id
        
        return response
    
    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Handle uncaught exceptions."""
        logger = getattr(request.state, 'logger', structlog.get_logger())
        logger.error(
            "unhandled_exception",
            exception_type=type(exc).__name__,
            exception_message=str(exc),
            path=request.url.path,
            method=request.method,
        )
        
        # Don't expose internal errors in production
        if settings.app.environment == "production":
            detail = "Internal server error"
        else:
            detail = str(exc)
        
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": detail}
        )
    
    # Note: Health check endpoint is handled by monitoring middleware
    
    # Include API routers
    from src.api import (
        research_router,
        workflow_router,
        news_router,
        agents_router,
        companies_router
    )
    
    app.include_router(research_router, prefix="/api/v1", tags=["research"])
    app.include_router(workflow_router, prefix="/api/v1", tags=["workflow"])  
    app.include_router(news_router, prefix="/api/v1", tags=["news"])
    app.include_router(agents_router, prefix="/api/v1", tags=["agents"])
    app.include_router(companies_router, prefix="/api/v1", tags=["companies"])
    
    # Customize OpenAPI schema
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        
        from fastapi.openapi.utils import get_openapi
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        
        # Add custom components
        openapi_schema["components"]["schemas"]["ErrorResponse"] = {
            "type": "object",
            "properties": {
                "error": {"type": "string", "description": "Error type"},
                "detail": {"type": "string", "description": "Detailed error message"},
                "request_id": {"type": "string", "description": "Request correlation ID"}
            },
            "required": ["error", "detail"]
        }
        
        # Add security schemes
        openapi_schema["components"]["securitySchemes"] = {
            "ApiKeyAuth": {
                "type": "apiKey",
                "in": "header", 
                "name": "X-API-Key",
                "description": "API key for authentication"
            },
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "JWT token for authentication"
            }
        }
        
        # Add common response codes
        common_responses = {
            "400": {
                "description": "Bad Request",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                    }
                }
            },
            "401": {
                "description": "Unauthorized", 
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                    }
                }
            },
            "429": {
                "description": "Rate Limit Exceeded",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                    }
                }
            },
            "500": {
                "description": "Internal Server Error",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                    }
                }
            }
        }
        
        # Add common responses to all paths
        for path in openapi_schema["paths"].values():
            for method in path.values():
                if isinstance(method, dict) and "responses" in method:
                    method["responses"].update(common_responses)
        
        # Add info about rate limiting
        openapi_schema["info"]["x-rate-limits"] = {
            "default": "100 requests per minute",
            "research": "30 requests per hour", 
            "workflow": "10 concurrent executions"
        }
        
        app.openapi_schema = openapi_schema
        return app.openapi_schema
    
    app.openapi = custom_openapi
    
    return app


# Create app instance
app = create_app()