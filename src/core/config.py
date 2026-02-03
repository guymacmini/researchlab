"""Enhanced configuration management for ResearchLab with YAML support."""

import os
import yaml
from typing import Optional, List, Dict, Any
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, ValidationError
import structlog

logger = structlog.get_logger()


class BaseConfigModel(BaseSettings):
    """Base configuration model with common settings."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8", 
        case_sensitive=False,
        validate_assignment=True,
        extra="ignore"  # Allow extra fields from YAML
    )


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""
    pass


class YAMLConfigLoader:
    """Loads and validates YAML configuration files."""
    
    @staticmethod
    def load_yaml(config_path: Path) -> Dict[str, Any]:
        """Load YAML configuration file."""
        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)
                logger.info("Loaded YAML configuration", path=str(config_path))
                return config or {}
        except FileNotFoundError:
            logger.warning("YAML config file not found", path=str(config_path))
            return {}
        except yaml.YAMLError as e:
            logger.error("Failed to parse YAML config", path=str(config_path), error=str(e))
            raise ConfigValidationError(f"Invalid YAML configuration: {e}")
    
    @staticmethod
    def merge_configs(base_config: Dict[str, Any], override_config: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively merge configuration dictionaries."""
        result = base_config.copy()
        
        for key, value in override_config.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = YAMLConfigLoader.merge_configs(result[key], value)
            else:
                result[key] = value
        
        return result


class DatabaseConfig(BaseConfigModel):
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


class APIConfig(BaseConfigModel):
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
    
    @field_validator("google_credentials_file")
    @classmethod
    def validate_google_credentials(cls, v):
        """Validate Google credentials file exists."""
        if v and not Path(v).exists():
            raise ValueError(f"Google credentials file not found: {v}")
        return v


class AppConfig(BaseConfigModel):
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
    
    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v):
        """Validate environment value."""
        valid_envs = ["development", "testing", "staging", "production"]
        if v.lower() not in valid_envs:
            raise ValueError(f"Environment must be one of: {valid_envs}")
        return v.lower()
    
    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v


class AgentConfig(BaseConfigModel):
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


class WorkflowConfig(BaseConfigModel):
    """Workflow and HITL configuration."""
    
    max_concurrent_workflows: int = Field(default=3, env="MAX_CONCURRENT_WORKFLOWS")
    default_timeout_minutes: int = Field(default=60, env="DEFAULT_TIMEOUT_MINUTES")
    checkpoint_timeout_minutes: int = Field(default=30, env="CHECKPOINT_TIMEOUT_MINUTES")
    
    # HITL settings
    hitl_enabled: bool = Field(default=True, env="HITL_ENABLED")
    auto_approve_high_confidence: bool = Field(default=False, env="AUTO_APPROVE_HIGH_CONFIDENCE")
    approval_timeout_hours: int = Field(default=24, env="APPROVAL_TIMEOUT_HOURS")


class MonitoringConfig(BaseConfigModel):
    """Monitoring and alerting configuration."""
    
    # Metrics
    metrics_enabled: bool = Field(default=True, env="METRICS_ENABLED")
    metrics_port: int = Field(default=9090, env="METRICS_PORT")
    metrics_path: str = Field(default="/metrics", env="METRICS_PATH")
    
    # Health checks
    health_enabled: bool = Field(default=True, env="HEALTH_ENABLED")
    health_path: str = Field(default="/health", env="HEALTH_PATH")
    
    # Alerts
    alerts_enabled: bool = Field(default=True, env="ALERTS_ENABLED")
    error_threshold: int = Field(default=10, env="ERROR_THRESHOLD")
    latency_threshold: int = Field(default=1000, env="LATENCY_THRESHOLD")


class SecurityConfig(BaseConfigModel):
    """Security and rate limiting configuration."""
    
    rate_limit_enabled: bool = Field(default=True, env="RATE_LIMIT_ENABLED")
    requests_per_minute: int = Field(default=100, env="REQUESTS_PER_MINUTE")
    burst_size: int = Field(default=20, env="BURST_SIZE")
    
    # API validation
    api_key_validation_enabled: bool = Field(default=True, env="API_KEY_VALIDATION_ENABLED")
    max_request_size: str = Field(default="10MB", env="MAX_REQUEST_SIZE")


class CacheConfig(BaseConfigModel):
    """Caching configuration."""
    
    default_ttl: int = Field(default=3600, env="CACHE_DEFAULT_TTL")
    max_connections: int = Field(default=20, env="CACHE_MAX_CONNECTIONS")
    
    # TTL by data type
    stock_data_ttl: int = Field(default=300, env="STOCK_DATA_TTL")
    news_data_ttl: int = Field(default=1800, env="NEWS_DATA_TTL")
    sec_filings_ttl: int = Field(default=86400, env="SEC_FILINGS_TTL")
    analysis_results_ttl: int = Field(default=3600, env="ANALYSIS_RESULTS_TTL")


class Settings(BaseConfigModel):
    """Complete application settings with YAML support."""
    
    # Configuration file paths
    config_file: Optional[Path] = Field(default=None, env="CONFIG_FILE")
    
    # Sub-configurations
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    app: AppConfig = Field(default_factory=AppConfig)
    agents: AgentConfig = Field(default_factory=AgentConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    
    def __init__(self, **kwargs):
        """Initialize settings with YAML configuration support."""
        # Load YAML configuration if available
        config_file = kwargs.get('config_file') or os.getenv('CONFIG_FILE')
        yaml_config = self._load_yaml_config(config_file)
        
        # Merge YAML config with kwargs
        if yaml_config:
            kwargs = self._merge_configs(yaml_config, kwargs)
        
        super().__init__(**kwargs)
        
        # Validate configuration
        self._validate_config()
    
    def _load_yaml_config(self, config_file: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Load YAML configuration files."""
        loader = YAMLConfigLoader()
        base_config = {}
        
        # Default config file paths
        config_paths = [
            Path("config/settings.yaml"),
            Path("settings.yaml"),
            Path("config.yaml")
        ]
        
        # Add custom config file if specified
        if config_file:
            config_paths.insert(0, Path(config_file))
        
        # Load base configuration
        for config_path in config_paths:
            if config_path.exists():
                base_config = loader.load_yaml(config_path)
                break
        
        if not base_config:
            logger.info("No YAML configuration file found, using defaults")
            return None
        
        # Load environment-specific overrides
        environment = os.getenv("ENVIRONMENT", "development").lower()
        if "environments" in base_config and environment in base_config["environments"]:
            env_overrides = base_config["environments"][environment]
            base_config = loader.merge_configs(base_config, env_overrides)
            logger.info("Applied environment-specific configuration", environment=environment)
        
        return base_config
    
    def _merge_configs(self, yaml_config: Dict[str, Any], kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Merge YAML configuration with initialization kwargs."""
        return YAMLConfigLoader.merge_configs(yaml_config, kwargs)
    
    def _validate_config(self) -> None:
        """Validate critical configuration settings."""
        errors = []
        
        # Validate production environment settings
        if self.app.environment == "production":
            if self.app.secret_key == "dev-secret-key-change-in-production":
                errors.append("SECRET_KEY must be set in production")
            
            if not self.api.finnhub_api_key:
                errors.append("FINNHUB_API_KEY is required in production")
            
            if not self.api.alpha_vantage_api_key:
                errors.append("ALPHA_VANTAGE_API_KEY is required in production")
            
            if not self.api.anthropic_api_key:
                errors.append("ANTHROPIC_API_KEY is required in production")
        
        # Validate database configuration
        if not self.database.password and self.app.environment == "production":
            errors.append("Database password is required in production")
        
        # Validate file paths
        if self.api.google_credentials_file:
            if not Path(self.api.google_credentials_file).exists():
                errors.append(f"Google credentials file not found: {self.api.google_credentials_file}")
        
        if errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {error}" for error in errors)
            logger.error("Configuration validation failed", errors=errors)
            raise ConfigValidationError(error_msg)
        
        logger.info("Configuration validation passed", environment=self.app.environment)
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        validate_assignment=True,
        extra="ignore"  # Allow extra fields from YAML
    )


# Global settings instance
_settings: Optional[Settings] = None


def get_settings(reload: bool = False) -> Settings:
    """Get application settings with caching."""
    global _settings
    
    if _settings is None or reload:
        try:
            _settings = Settings()
            logger.info("Settings loaded successfully", 
                       environment=_settings.app.environment,
                       app_name=_settings.app.app_name)
        except Exception as e:
            logger.error("Failed to load settings", error=str(e))
            raise
    
    return _settings


# Initialize settings on import
settings = get_settings()


def is_production() -> bool:
    """Check if running in production environment."""
    return settings.app.environment == "production"


def is_development() -> bool:
    """Check if running in development environment."""
    return settings.app.environment == "development"


def is_testing() -> bool:
    """Check if running in testing environment."""
    return settings.app.environment == "testing"