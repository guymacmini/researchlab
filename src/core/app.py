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
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "version": settings.app.version,
            "environment": settings.app.environment
        }
    
    # Include API routers
    from src.api.research import router as research_router
    from src.api.companies import router as companies_router
    from src.api.agents import router as agents_router
    
    app.include_router(research_router, prefix="/api/v1/research", tags=["research"])
    app.include_router(companies_router, prefix="/api/v1/companies", tags=["companies"])  
    app.include_router(agents_router, prefix="/api/v1/agents", tags=["agents"])
    
    return app


# Create app instance
app = create_app()