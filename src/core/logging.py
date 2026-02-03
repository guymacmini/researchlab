"""Structured logging configuration."""

import sys
import logging
from typing import Any, Dict

import structlog
from structlog.types import Processor

from .config import settings


def add_app_context(logger: logging.Logger, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add application context to log events."""
    event_dict["app"] = settings.app.app_name
    event_dict["version"] = settings.app.version 
    event_dict["environment"] = settings.app.environment
    return event_dict


def setup_logging() -> None:
    """Configure structured logging."""
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.app.log_level.upper()),
    )
    
    # Disable uvicorn default formatter
    logging.getLogger("uvicorn.access").handlers = []
    
    # Configure processors based on environment
    processors: list[Processor] = [
        structlog.stdlib.filter_by_level,
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        add_app_context,
    ]
    
    # Add appropriate renderer based on log format
    if settings.app.log_format == "json" or settings.app.environment == "production":
        # JSON formatting for production
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Pretty formatting for development
        processors.extend([
            structlog.processors.ExceptionPrettyPrinter(),
            structlog.dev.ConsoleRenderer(colors=True)
        ])
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)