"""Database connection and session management."""

from typing import AsyncGenerator, Optional
import structlog

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.pool import StaticPool
import redis.asyncio as redis

from .config import settings
from src.data.models import Base

logger = structlog.get_logger()

# Global connections
_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker] = None
_redis_client: Optional[redis.Redis] = None


async def get_engine() -> AsyncEngine:
    """Get the database engine."""
    global _engine
    
    if _engine is None:
        logger.info("creating_database_engine", url=settings.database.url.split("@")[-1])  # Don't log credentials
        
        # Engine configuration
        engine_kwargs = {
            "echo": settings.app.debug,
            "pool_size": settings.database.pool_size,
            "max_overflow": settings.database.max_overflow,
            "pool_pre_ping": True,  # Verify connections before use
        }
        
        # For SQLite (testing), use StaticPool to avoid issues with threading
        if settings.database.url.startswith("sqlite"):
            engine_kwargs.update({
                "poolclass": StaticPool,
                "connect_args": {"check_same_thread": False},
            })
        
        _engine = create_async_engine(settings.database.url, **engine_kwargs)
    
    return _engine


async def get_session_factory() -> async_sessionmaker:
    """Get the session factory."""
    global _session_factory
    
    if _session_factory is None:
        engine = await get_engine()
        _session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session for dependency injection."""
    session_factory = await get_session_factory()
    
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_redis_client() -> redis.Redis:
    """Get Redis client."""
    global _redis_client
    
    if _redis_client is None:
        logger.info("creating_redis_connection", url=settings.database.redis_url.split("@")[-1])
        _redis_client = redis.from_url(
            settings.database.redis_url,
            decode_responses=True,
            health_check_interval=30,
        )
    
    return _redis_client


async def init_db() -> None:
    """Initialize database connections."""
    logger.info("initializing_database")
    
    # Test database connection
    try:
        engine = await get_engine()
        async with engine.begin() as conn:
            # Create tables if they don't exist
            await conn.run_sync(Base.metadata.create_all)
        logger.info("database_initialized")
    except Exception as e:
        logger.error("database_initialization_failed", error=str(e))
        raise
    
    # Test Redis connection
    try:
        redis_client = await get_redis_client()
        await redis_client.ping()
        logger.info("redis_connected")
    except Exception as e:
        logger.error("redis_connection_failed", error=str(e))
        # Redis failures shouldn't prevent startup in development
        if settings.app.environment == "production":
            raise


async def close_db() -> None:
    """Close database connections."""
    global _engine, _session_factory, _redis_client
    
    logger.info("closing_database_connections")
    
    # Close Redis connection
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
    
    # Close database engine
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
    
    logger.info("database_connections_closed")


class DatabaseManager:
    """Database context manager for manual session management."""
    
    def __init__(self):
        self.session: Optional[AsyncSession] = None
    
    async def __aenter__(self) -> AsyncSession:
        """Enter async context and create session."""
        session_factory = await get_session_factory()
        self.session = session_factory()
        return self.session
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context and close session."""
        if self.session:
            if exc_type:
                await self.session.rollback()
            await self.session.close()
            self.session = None