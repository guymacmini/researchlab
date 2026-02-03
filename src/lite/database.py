"""Simplified SQLite database for ResearchLab LITE."""

from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey
from datetime import datetime, timedelta
import structlog

from .config import settings

logger = structlog.get_logger()

# Database base
Base = declarative_base()

# Global engine and session factory
_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker] = None


# Simplified database models for LITE version
class Research(Base):
    """Research project model."""
    __tablename__ = "research"
    
    id = Column(Integer, primary_key=True)
    query = Column(String(500), nullable=False)
    status = Column(String(50), default="pending")
    results = Column(Text)  # JSON stored as text
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Company(Base):
    """Company data model."""
    __tablename__ = "companies"
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), unique=True, nullable=False)
    name = Column(String(200))
    sector = Column(String(100))
    data = Column(Text)  # JSON stored as text
    last_updated = Column(DateTime, default=datetime.utcnow)


class Cache(Base):
    """Simple cache model to replace Redis."""
    __tablename__ = "cache"
    
    id = Column(Integer, primary_key=True)
    key = Column(String(255), unique=True, nullable=False)
    value = Column(Text)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


async def get_engine() -> AsyncEngine:
    """Get the database engine."""
    global _engine
    
    if _engine is None:
        logger.info("Creating SQLite database engine", file=settings.database_file)
        
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
    
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
    """Get a database session."""
    session_factory = await get_session_factory()
    
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db():
    """Get database session context manager."""
    async with get_db_session() as session:
        yield session


async def init_database():
    """Initialize database and create tables."""
    logger.info("Initializing SQLite database")
    
    engine = await get_engine()
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
    
    logger.info("Database initialized successfully")


async def close_database():
    """Close database connections."""
    global _engine, _session_factory
    
    logger.info("Closing database connections")
    
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
    
    logger.info("Database connections closed")


class SimpleCache:
    """Simple in-memory cache with SQLite fallback."""
    
    def __init__(self):
        self._memory_cache = {}
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from cache."""
        # First try memory cache
        if key in self._memory_cache:
            value, expires_at = self._memory_cache[key]
            if expires_at is None or datetime.utcnow() < expires_at:
                return value
            else:
                del self._memory_cache[key]
        
        # Fall back to database cache
        async with get_db() as db:
            from sqlalchemy import select
            result = await db.execute(
                select(Cache.value, Cache.expires_at).where(Cache.key == key)
            )
            row = result.fetchone()
            
            if row and (row[1] is None or datetime.utcnow() < row[1]):
                # Update memory cache
                self._memory_cache[key] = (row[0], row[1])
                return row[0]
        
        return None
    
    async def set(self, key: str, value: str, ttl_seconds: Optional[int] = None):
        """Set value in cache."""
        expires_at = None
        if ttl_seconds:
            expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        
        # Update memory cache
        self._memory_cache[key] = (value, expires_at)
        
        # Update database cache
        async with get_db() as db:
            # Use SQLAlchemy merge to insert or update
            cache_obj = Cache(key=key, value=value, expires_at=expires_at)
            await db.merge(cache_obj)
            await db.commit()
    
    async def delete(self, key: str):
        """Delete key from cache."""
        # Remove from memory
        self._memory_cache.pop(key, None)
        
        # Remove from database
        async with get_db() as db:
            from sqlalchemy import delete
            await db.execute(delete(Cache).where(Cache.key == key))
            await db.commit()
    
    async def clear(self):
        """Clear all cache."""
        self._memory_cache.clear()
        
        async with get_db() as db:
            from sqlalchemy import delete
            await db.execute(delete(Cache))
            await db.commit()


# Global cache instance
cache = SimpleCache()