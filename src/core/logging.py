"""Enhanced structured logging configuration with performance tracking and security."""

import sys
import logging
import time
import uuid
import functools
import re
from typing import Any, Dict, Optional, List, Union, Callable
from contextvars import ContextVar
from pathlib import Path

import structlog
from structlog.types import Processor

from .config import settings

# Context variables for request tracking
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
session_id_var: ContextVar[Optional[str]] = ContextVar("session_id", default=None)

# Sensitive data patterns to filter from logs
SENSITIVE_PATTERNS = [
    r"password",
    r"token", 
    r"key",
    r"secret",
    r"api[-_]?key",
    r"authorization",
    r"bearer",
    r"credentials",
    r"private[-_]?key",
    r"access[-_]?token",
    r"refresh[-_]?token"
]

SENSITIVE_REGEX = re.compile("|".join(SENSITIVE_PATTERNS), re.IGNORECASE)


def filter_sensitive_data(logger: logging.Logger, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Filter sensitive data from log events."""
    def mask_value(key: str, value: Any) -> Any:
        if isinstance(value, str) and SENSITIVE_REGEX.search(key):
            if len(value) <= 8:
                return "***"
            return value[:4] + "***" + value[-4:]
        elif isinstance(value, dict):
            return {k: mask_value(k, v) for k, v in value.items()}
        elif isinstance(value, list):
            return [mask_value(f"{key}_{i}", item) for i, item in enumerate(value)]
        return value
    
    return {k: mask_value(k, v) for k, v in event_dict.items()}


def add_app_context(logger: logging.Logger, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add application context to log events."""
    event_dict["app"] = settings.app.app_name
    event_dict["version"] = settings.app.version 
    event_dict["environment"] = settings.app.environment
    
    # Add request tracking context
    request_id = request_id_var.get()
    if request_id:
        event_dict["request_id"] = request_id
    
    user_id = user_id_var.get()
    if user_id:
        event_dict["user_id"] = user_id
    
    session_id = session_id_var.get()
    if session_id:
        event_dict["session_id"] = session_id
    
    return event_dict


def add_performance_context(logger: logging.Logger, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add performance-related context."""
    # Add process and thread info for debugging
    import os
    import threading
    
    event_dict["process_id"] = os.getpid()
    event_dict["thread_id"] = threading.get_ident()
    event_dict["thread_name"] = threading.current_thread().name
    
    return event_dict


class PerformanceLoggerMixin:
    """Mixin to add performance logging to any class."""
    
    def log_performance(self, operation: str, duration: float, **kwargs):
        """Log performance metrics for an operation."""
        logger = get_logger(self.__class__.__name__)
        logger.info(
            "operation_completed",
            operation=operation,
            duration_ms=round(duration * 1000, 2),
            **kwargs
        )


def log_performance(
    operation: Optional[str] = None,
    include_args: bool = False,
    include_result: bool = False,
    level: str = "info"
):
    """Decorator to log function performance and execution details."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            operation_name = operation or f"{func.__module__}.{func.__name__}"
            logger = get_logger(func.__module__)
            
            # Log function start
            log_data = {
                "operation": operation_name,
                "function": func.__name__,
                "module": func.__module__
            }
            
            if include_args:
                log_data["args"] = args[:5]  # Limit args to prevent huge logs
                log_data["kwargs"] = {k: v for i, (k, v) in enumerate(kwargs.items()) if i < 10}
            
            logger.debug("function_started", **log_data)
            
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                
                # Log successful completion
                completion_data = {
                    **log_data,
                    "duration_ms": round(duration * 1000, 2),
                    "status": "success"
                }
                
                if include_result and result is not None:
                    # Safely include result data
                    if isinstance(result, (dict, list)) and len(str(result)) < 1000:
                        completion_data["result"] = result
                    else:
                        completion_data["result_type"] = type(result).__name__
                        completion_data["result_size"] = len(str(result))
                
                getattr(logger, level)("function_completed", **completion_data)
                return result
                
            except Exception as e:
                duration = time.time() - start_time
                logger.error(
                    "function_failed",
                    **log_data,
                    duration_ms=round(duration * 1000, 2),
                    error_type=type(e).__name__,
                    error_message=str(e),
                    status="error"
                )
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            operation_name = operation or f"{func.__module__}.{func.__name__}"
            logger = get_logger(func.__module__)
            
            log_data = {
                "operation": operation_name,
                "function": func.__name__,
                "module": func.__module__
            }
            
            if include_args:
                log_data["args"] = args[:5]
                log_data["kwargs"] = {k: v for i, (k, v) in enumerate(kwargs.items()) if i < 10}
            
            logger.debug("function_started", **log_data)
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                completion_data = {
                    **log_data,
                    "duration_ms": round(duration * 1000, 2),
                    "status": "success"
                }
                
                if include_result and result is not None:
                    if isinstance(result, (dict, list)) and len(str(result)) < 1000:
                        completion_data["result"] = result
                    else:
                        completion_data["result_type"] = type(result).__name__
                        completion_data["result_size"] = len(str(result))
                
                getattr(logger, level)("function_completed", **completion_data)
                return result
                
            except Exception as e:
                duration = time.time() - start_time
                logger.error(
                    "function_failed",
                    **log_data,
                    duration_ms=round(duration * 1000, 2),
                    error_type=type(e).__name__,
                    error_message=str(e),
                    status="error"
                )
                raise
        
        # Return appropriate wrapper based on function type
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def setup_file_logging() -> None:
    """Setup file-based logging for production."""
    if settings.app.environment == "production" and hasattr(settings.app, 'log_file'):
        log_file = Path(settings.app.log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Setup rotating file handler
        from logging.handlers import RotatingFileHandler
        
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=100 * 1024 * 1024,  # 100MB
            backupCount=5,
            encoding='utf-8'
        )
        
        file_handler.setFormatter(
            logging.Formatter('%(message)s')  # structlog will handle formatting
        )
        
        # Add file handler to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)


def setup_logging() -> None:
    """Configure enhanced structured logging with security and performance features."""
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.app.log_level.upper()),
    )
    
    # Setup file logging for production
    setup_file_logging()
    
    # Disable noisy loggers in production
    if settings.app.environment == "production":
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    else:
        # Keep detailed logs in development
        logging.getLogger("uvicorn.access").handlers = []
    
    # Configure processors based on environment
    processors: list[Processor] = [
        structlog.stdlib.filter_by_level,
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        add_app_context,
    ]
    
    # Add performance context in development
    if settings.app.environment == "development":
        processors.append(add_performance_context)
    
    # Always filter sensitive data
    processors.append(filter_sensitive_data)
    
    # Add stack info in development
    if settings.app.environment != "production":
        processors.append(structlog.processors.StackInfoRenderer())
    
    # Add appropriate renderer based on log format
    if settings.app.log_format == "json" or settings.app.environment == "production":
        # JSON formatting for production/JSON mode
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
    
    # Log startup message
    logger = get_logger("logging")
    logger.info(
        "logging_configured",
        level=settings.app.log_level,
        format=settings.app.log_format,
        environment=settings.app.environment
    )


def get_logger(name: str = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


def set_request_id(request_id: str) -> None:
    """Set the current request ID for logging context."""
    request_id_var.set(request_id)


def set_user_id(user_id: str) -> None:
    """Set the current user ID for logging context."""
    user_id_var.set(user_id)


def set_session_id(session_id: str) -> None:
    """Set the current session ID for logging context."""
    session_id_var.set(session_id)


def get_request_id() -> Optional[str]:
    """Get the current request ID from context."""
    return request_id_var.get()


class LoggingContext:
    """Context manager for setting logging context variables."""
    
    def __init__(self, **context):
        self.context = context
        self.previous_values = {}
    
    def __enter__(self):
        # Store previous values
        if "request_id" in self.context:
            self.previous_values["request_id"] = request_id_var.get()
            request_id_var.set(self.context["request_id"])
        
        if "user_id" in self.context:
            self.previous_values["user_id"] = user_id_var.get()
            user_id_var.set(self.context["user_id"])
        
        if "session_id" in self.context:
            self.previous_values["session_id"] = session_id_var.get()
            session_id_var.set(self.context["session_id"])
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore previous values
        for key, value in self.previous_values.items():
            if key == "request_id":
                request_id_var.set(value)
            elif key == "user_id":
                user_id_var.set(value)
            elif key == "session_id":
                session_id_var.set(value)


def log_api_call(
    endpoint: str,
    method: str,
    status_code: int,
    duration_ms: float,
    request_size: Optional[int] = None,
    response_size: Optional[int] = None,
    **extra_context
):
    """Log an API call with standardized format."""
    logger = get_logger("api")
    
    log_data = {
        "event": "api_call",
        "endpoint": endpoint,
        "method": method.upper(),
        "status_code": status_code,
        "duration_ms": round(duration_ms, 2),
        **extra_context
    }
    
    if request_size is not None:
        log_data["request_size_bytes"] = request_size
    
    if response_size is not None:
        log_data["response_size_bytes"] = response_size
    
    # Choose log level based on status code
    if status_code < 400:
        logger.info("api_request_completed", **log_data)
    elif status_code < 500:
        logger.warning("api_request_client_error", **log_data)
    else:
        logger.error("api_request_server_error", **log_data)


def log_agent_execution(
    agent_name: str,
    operation: str,
    duration_ms: float,
    success: bool,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    confidence: Optional[float] = None,
    **extra_context
):
    """Log agent execution with standardized format."""
    logger = get_logger("agents")
    
    log_data = {
        "event": "agent_execution",
        "agent": agent_name,
        "operation": operation,
        "duration_ms": round(duration_ms, 2),
        "success": success,
        **extra_context
    }
    
    if input_tokens is not None:
        log_data["input_tokens"] = input_tokens
    
    if output_tokens is not None:
        log_data["output_tokens"] = output_tokens
    
    if confidence is not None:
        log_data["confidence"] = round(confidence, 3)
    
    if success:
        logger.info("agent_execution_completed", **log_data)
    else:
        logger.error("agent_execution_failed", **log_data)


def log_database_operation(
    operation: str,
    table: Optional[str],
    duration_ms: float,
    rows_affected: Optional[int] = None,
    query_hash: Optional[str] = None,
    **extra_context
):
    """Log database operation with standardized format."""
    logger = get_logger("database")
    
    log_data = {
        "event": "database_operation",
        "operation": operation,
        "duration_ms": round(duration_ms, 2),
        **extra_context
    }
    
    if table:
        log_data["table"] = table
    
    if rows_affected is not None:
        log_data["rows_affected"] = rows_affected
    
    if query_hash:
        log_data["query_hash"] = query_hash
    
    # Log at different levels based on performance
    if duration_ms > 5000:  # > 5 seconds
        logger.warning("slow_database_operation", **log_data)
    elif duration_ms > 1000:  # > 1 second
        logger.info("database_operation_completed", **log_data)
    else:
        logger.debug("database_operation_completed", **log_data)


# Export commonly used items
__all__ = [
    "setup_logging",
    "get_logger",
    "log_performance", 
    "LoggingContext",
    "PerformanceLoggerMixin",
    "set_request_id",
    "set_user_id", 
    "set_session_id",
    "get_request_id",
    "log_api_call",
    "log_agent_execution",
    "log_database_operation"
]