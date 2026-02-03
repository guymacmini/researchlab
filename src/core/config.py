"""Configuration management for ResearchLab."""

import os
from typing import Optional, List
from pathlib import Path

from pydantic_settings import BaseSettings
from pydantic import Field, validator


class DatabaseConfig(BaseSettings):
    """Database configuration."""
    
    # PostgreSQL settings
    host: str = Field(default="localhost", env="DB_HOST")
    port: int = Field(default=5432, env="DB_PORT") 
    name: str = Field(default="researchlab", env="DB_NAME")
    user: str = Field(default="postgres", env="DB_USER")
    password: str = Field(default="", env="DB_PASSWORD")
    
    # Connection pool settings
    pool_size: int = Field(default=10, env="DB_POOL_SIZE")
    max_overflow: int = Field(default=20, env="DB_MAX_OVERFLOW")
    
    # Redis settings
    redis_url: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    
    @property
    def url(self) -> str:
        """Get the database URL."""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
    
    @property
    def sync_url(self) -> str:
        """Get the synchronous database URL (for migrations)."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class APIConfig(BaseSettings):
    """External API configuration."""
    
    # Financial data APIs
    finnhub_api_key: str = Field(default="", env="FINNHUB_API_KEY")
    alpha_vantage_api_key: str = Field(default="", env="ALPHA_VANTAGE_API_KEY")
    
    # LLM APIs
    anthropic_api_key: str = Field(default="", env="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")
    
    # Google services
    google_credentials_file: Optional[str] = Field(default=None, env="GOOGLE_CREDENTIALS_FILE")
    
    # Rate limiting (requests per minute)
    finnhub_rate_limit: int = Field(default=60, env="FINNHUB_RATE_LIMIT")
    alpha_vantage_rate_limit: int = Field(default=5, env="ALPHA_VANTAGE_RATE_LIMIT")
    
    @validator("google_credentials_file")
    def validate_google_credentials(cls, v):
        """Validate Google credentials file exists."""
        if v and not Path(v).exists():
            raise ValueError(f"Google credentials file not found: {v}")
        return v


class AppConfig(BaseSettings):
    """Main application configuration."""
    
    # App metadata
    app_name: str = Field(default="ResearchLab", env="APP_NAME")
    version: str = Field(default="0.1.0", env="APP_VERSION")
    environment: str = Field(default="development", env="ENVIRONMENT")
    debug: bool = Field(default=False, env="DEBUG")
    
    # Server settings
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")
    
    # Security
    secret_key: str = Field(default="dev-secret-key-change-in-production", env="SECRET_KEY")
    access_token_expire_minutes: int = Field(default=1440, env="ACCESS_TOKEN_EXPIRE_MINUTES")  # 24 hours
    
    # CORS settings
    cors_origins: List[str] = Field(default=["http://localhost:3000", "http://localhost:8080"], env="CORS_ORIGINS")
    
    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_format: str = Field(default="json", env="LOG_FORMAT")  # json or console
    
    @validator("environment")
    def validate_environment(cls, v):
        """Validate environment value."""
        valid_envs = ["development", "testing", "staging", "production"]
        if v.lower() not in valid_envs:
            raise ValueError(f"Environment must be one of: {valid_envs}")
        return v.lower()
    
    @validator("cors_origins", pre=True)
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v


class AgentConfig(BaseSettings):
    """AI agent configuration."""
    
    # Default LLM settings
    default_model: str = Field(default="claude-3-sonnet-20240229", env="DEFAULT_MODEL")
    max_tokens: int = Field(default=4000, env="MAX_TOKENS")
    temperature: float = Field(default=0.1, env="TEMPERATURE")
    
    # Agent-specific models
    research_director_model: str = Field(default="claude-3-sonnet-20240229", env="RESEARCH_DIRECTOR_MODEL")
    fundamental_analyst_model: str = Field(default="claude-3-sonnet-20240229", env="FUNDAMENTAL_ANALYST_MODEL")
    
    # Execution settings
    max_concurrent_agents: int = Field(default=5, env="MAX_CONCURRENT_AGENTS")
    agent_timeout_seconds: int = Field(default=300, env="AGENT_TIMEOUT_SECONDS")  # 5 minutes
    
    # Confidence thresholds
    min_confidence_threshold: float = Field(default=0.3, env="MIN_CONFIDENCE_THRESHOLD")
    high_confidence_threshold: float = Field(default=0.8, env="HIGH_CONFIDENCE_THRESHOLD")


class Settings(BaseSettings):
    """Complete application settings."""
    
    # Sub-configurations
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    app: AppConfig = Field(default_factory=AppConfig)
    agents: AgentConfig = Field(default_factory=AgentConfig)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings."""
    return settings


def is_production() -> bool:
    """Check if running in production environment."""
    return settings.app.environment == "production"


def is_development() -> bool:
    """Check if running in development environment."""
    return settings.app.environment == "development"


def is_testing() -> bool:
    """Check if running in testing environment."""
    return settings.app.environment == "testing"