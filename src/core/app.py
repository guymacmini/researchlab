"""FastAPI application factory."""

import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .logging import setup_logging
from .database import init_db, close_db
from ..monitoring import setup_monitoring_middleware


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
    """Create and configure FastAPI application."""
    
    app = FastAPI(
        title=settings.app.app_name,
        version=settings.app.version,
        description="AI-led investment research platform",
        lifespan=lifespan,
        debug=settings.app.debug,
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
    
    # Request ID middleware
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        """Add request ID to structured logging context."""
        import uuid
        request_id = str(uuid.uuid4())
        
        # Bind request ID to logger context
        logger = structlog.get_logger().bind(request_id=request_id)
        request.state.logger = logger
        
        # Add to response headers
        response = await call_next(request)
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
    from src.api.research import router as research_router
    from src.api.workflow import router as workflow_router
    from src.api.news import router as news_router
    
    app.include_router(research_router, prefix="/api/v1", tags=["research"])
    app.include_router(workflow_router, prefix="/api/v1", tags=["workflow"])
    app.include_router(news_router, prefix="/api/v1", tags=["news"])
    
    return app


# Create app instance
app = create_app()