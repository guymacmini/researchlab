"""Configuration models and data structures."""

import os
from enum import Enum
from datetime import datetime
from typing import Dict, Any, Optional, List, Union, Type, Callable
from pathlib import Path

from pydantic import BaseModel, Field, validator, root_validator
from pydantic.types import SecretStr


class ConfigValueType(str, Enum):
    """Configuration value types."""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    DICT = "dict"
    SECRET = "secret"
    PATH = "path"
    URL = "url"
    EMAIL = "email"


class ConfigSource(str, Enum):
    """Configuration sources."""
    DEFAULT = "default"
    ENVIRONMENT = "environment"
    YAML_FILE = "yaml_file"
    JSON_FILE = "json_file"
    COMMAND_LINE = "command_line"
    DATABASE = "database"
    REMOTE = "remote"


class ConfigValidationError(Exception):
    """Configuration validation error."""
    
    def __init__(self, key: str, message: str, value: Any = None):
        self.key = key
        self.message = message
        self.value = value
        super().__init__(f"Configuration error for '{key}': {message}")


class ConfigValue(BaseModel):
    """Represents a single configuration value."""
    
    key: str = Field(..., description="Configuration key")
    value: Any = Field(..., description="Configuration value")
    value_type: ConfigValueType = Field(..., description="Value type")
    source: ConfigSource = Field(..., description="Source of value")
    
    # Metadata
    description: Optional[str] = Field(default=None, description="Value description")
    default: Any = Field(default=None, description="Default value")
    required: bool = Field(default=False, description="Whether value is required")
    sensitive: bool = Field(default=False, description="Whether value contains sensitive data")
    
    # Validation
    min_value: Optional[Union[int, float]] = Field(default=None, description="Minimum value for numbers")
    max_value: Optional[Union[int, float]] = Field(default=None, description="Maximum value for numbers")
    pattern: Optional[str] = Field(default=None, description="Regex pattern for strings")
    choices: Optional[List[Any]] = Field(default=None, description="Valid choices")
    
    # Metadata for tracking
    updated_at: datetime = Field(default_factory=datetime.now)
    updated_by: Optional[str] = Field(default=None, description="Who updated the value")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            SecretStr: lambda v: "***HIDDEN***" if v else None
        }
    
    def validate_value(self) -> bool:
        """Validate the configuration value."""
        if self.required and self.value is None:
            raise ConfigValidationError(self.key, "Required value is missing")
        
        if self.value is None:
            return True
        
        # Type validation
        if self.value_type == ConfigValueType.INTEGER:
            if not isinstance(self.value, int):
                raise ConfigValidationError(self.key, f"Expected integer, got {type(self.value).__name__}")
        
        elif self.value_type == ConfigValueType.FLOAT:
            if not isinstance(self.value, (int, float)):
                raise ConfigValidationError(self.key, f"Expected float, got {type(self.value).__name__}")
        
        elif self.value_type == ConfigValueType.BOOLEAN:
            if not isinstance(self.value, bool):
                raise ConfigValidationError(self.key, f"Expected boolean, got {type(self.value).__name__}")
        
        elif self.value_type == ConfigValueType.LIST:
            if not isinstance(self.value, list):
                raise ConfigValidationError(self.key, f"Expected list, got {type(self.value).__name__}")
        
        elif self.value_type == ConfigValueType.DICT:
            if not isinstance(self.value, dict):
                raise ConfigValidationError(self.key, f"Expected dict, got {type(self.value).__name__}")
        
        elif self.value_type == ConfigValueType.PATH:
            if not isinstance(self.value, (str, Path)):
                raise ConfigValidationError(self.key, f"Expected path string, got {type(self.value).__name__}")
        
        elif self.value_type == ConfigValueType.EMAIL:
            if not isinstance(self.value, str) or "@" not in self.value:
                raise ConfigValidationError(self.key, "Invalid email address format")
        
        elif self.value_type == ConfigValueType.URL:
            if not isinstance(self.value, str) or not (
                self.value.startswith("http://") or self.value.startswith("https://")
            ):
                raise ConfigValidationError(self.key, "Invalid URL format")
        
        # Range validation for numbers
        if self.value_type in [ConfigValueType.INTEGER, ConfigValueType.FLOAT]:
            if self.min_value is not None and self.value < self.min_value:
                raise ConfigValidationError(self.key, f"Value {self.value} is below minimum {self.min_value}")
            
            if self.max_value is not None and self.value > self.max_value:
                raise ConfigValidationError(self.key, f"Value {self.value} is above maximum {self.max_value}")
        
        # Pattern validation for strings
        if self.value_type == ConfigValueType.STRING and self.pattern:
            import re
            if not re.match(self.pattern, str(self.value)):
                raise ConfigValidationError(self.key, f"Value does not match pattern {self.pattern}")
        
        # Choices validation
        if self.choices and self.value not in self.choices:
            raise ConfigValidationError(self.key, f"Value must be one of {self.choices}")
        
        return True
    
    def get_display_value(self) -> str:
        """Get value for display (masking sensitive data)."""
        if self.sensitive and self.value:
            return "***HIDDEN***"
        return str(self.value)
    
    def update_value(self, new_value: Any, source: ConfigSource, updated_by: Optional[str] = None):
        """Update configuration value."""
        self.value = new_value
        self.source = source
        self.updated_at = datetime.now()
        self.updated_by = updated_by
        self.validate_value()


class ConfigSection(BaseModel):
    """Represents a section of configuration."""
    
    name: str = Field(..., description="Section name")
    description: Optional[str] = Field(default=None, description="Section description")
    values: Dict[str, ConfigValue] = Field(default_factory=dict, description="Configuration values")
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    def add_value(self, config_value: ConfigValue):
        """Add configuration value to section."""
        self.values[config_value.key] = config_value
        self.updated_at = datetime.now()
    
    def get_value(self, key: str) -> Optional[ConfigValue]:
        """Get configuration value by key."""
        return self.values.get(key)
    
    def set_value(
        self, 
        key: str, 
        value: Any, 
        source: ConfigSource = ConfigSource.DEFAULT,
        updated_by: Optional[str] = None
    ):
        """Set configuration value."""
        if key in self.values:
            self.values[key].update_value(value, source, updated_by)
        else:
            # Create new config value
            config_value = ConfigValue(
                key=key,
                value=value,
                value_type=self._infer_value_type(value),
                source=source,
                updated_by=updated_by
            )
            self.add_value(config_value)
    
    def _infer_value_type(self, value: Any) -> ConfigValueType:
        """Infer configuration value type from Python value."""
        if isinstance(value, bool):
            return ConfigValueType.BOOLEAN
        elif isinstance(value, int):
            return ConfigValueType.INTEGER
        elif isinstance(value, float):
            return ConfigValueType.FLOAT
        elif isinstance(value, list):
            return ConfigValueType.LIST
        elif isinstance(value, dict):
            return ConfigValueType.DICT
        elif isinstance(value, (Path, str)) and str(value).startswith("/"):
            return ConfigValueType.PATH
        elif isinstance(value, str) and value.startswith(("http://", "https://")):
            return ConfigValueType.URL
        elif isinstance(value, str) and "@" in value:
            return ConfigValueType.EMAIL
        else:
            return ConfigValueType.STRING
    
    def validate_all(self) -> List[ConfigValidationError]:
        """Validate all values in section."""
        errors = []
        for value in self.values.values():
            try:
                value.validate_value()
            except ConfigValidationError as e:
                errors.append(e)
        return errors
    
    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Convert section to dictionary."""
        result = {}
        for key, config_value in self.values.items():
            if config_value.sensitive and not include_sensitive:
                result[key] = "***HIDDEN***"
            else:
                result[key] = config_value.value
        return result


class ConfigSchema(BaseModel):
    """Schema definition for configuration validation."""
    
    schema_name: str = Field(..., description="Schema name")
    version: str = Field(default="1.0", description="Schema version")
    sections: Dict[str, Dict[str, Dict[str, Any]]] = Field(
        default_factory=dict, 
        description="Schema definitions by section"
    )
    
    def validate_config(self, config_sections: Dict[str, ConfigSection]) -> List[ConfigValidationError]:
        """Validate configuration against schema."""
        errors = []
        
        for section_name, section_schema in self.sections.items():
            if section_name not in config_sections:
                # Check if any values in this section are required
                for key, key_schema in section_schema.items():
                    if key_schema.get("required", False):
                        errors.append(ConfigValidationError(
                            f"{section_name}.{key}",
                            f"Required section '{section_name}' is missing"
                        ))
                continue
            
            section = config_sections[section_name]
            
            for key, key_schema in section_schema.items():
                full_key = f"{section_name}.{key}"
                
                if key not in section.values:
                    if key_schema.get("required", False):
                        errors.append(ConfigValidationError(
                            full_key,
                            f"Required configuration '{key}' is missing"
                        ))
                    continue
                
                config_value = section.values[key]
                
                # Update config value with schema information
                if "description" in key_schema:
                    config_value.description = key_schema["description"]
                if "default" in key_schema:
                    config_value.default = key_schema["default"]
                if "required" in key_schema:
                    config_value.required = key_schema["required"]
                if "sensitive" in key_schema:
                    config_value.sensitive = key_schema["sensitive"]
                if "min_value" in key_schema:
                    config_value.min_value = key_schema["min_value"]
                if "max_value" in key_schema:
                    config_value.max_value = key_schema["max_value"]
                if "pattern" in key_schema:
                    config_value.pattern = key_schema["pattern"]
                if "choices" in key_schema:
                    config_value.choices = key_schema["choices"]
                
                # Validate value against schema
                try:
                    config_value.validate_value()
                except ConfigValidationError as e:
                    errors.append(e)
        
        return errors


# Specific configuration models for different components

class DatabaseConfig(BaseModel):
    """Database configuration."""
    
    host: str = Field(default="localhost", description="Database host")
    port: int = Field(default=5432, description="Database port", ge=1, le=65535)
    name: str = Field(default="researchlab", description="Database name")
    username: str = Field(default="postgres", description="Database username")
    password: SecretStr = Field(default="", description="Database password")
    
    # Connection pool settings
    pool_size: int = Field(default=10, description="Connection pool size", ge=1, le=100)
    max_overflow: int = Field(default=20, description="Max pool overflow", ge=0, le=100)
    pool_timeout: int = Field(default=30, description="Pool timeout in seconds", ge=1)
    
    # SSL settings
    use_ssl: bool = Field(default=False, description="Use SSL connection")
    ssl_cert: Optional[str] = Field(default=None, description="SSL certificate path")
    ssl_key: Optional[str] = Field(default=None, description="SSL key path")
    
    # Query settings
    echo_sql: bool = Field(default=False, description="Echo SQL queries for debugging")
    
    def get_connection_url(self, include_password: bool = True) -> str:
        """Get database connection URL."""
        password_str = ""
        if include_password and self.password:
            password_str = f":{self.password.get_secret_value()}"
        
        return f"postgresql://{self.username}{password_str}@{self.host}:{self.port}/{self.name}"


class APIConfig(BaseModel):
    """API configuration."""
    
    # API Keys (sensitive)
    finnhub_api_key: SecretStr = Field(default="", description="Finnhub API key")
    alpha_vantage_api_key: SecretStr = Field(default="", description="Alpha Vantage API key")
    news_api_key: SecretStr = Field(default="", description="News API key")
    openai_api_key: SecretStr = Field(default="", description="OpenAI API key")
    anthropic_api_key: SecretStr = Field(default="", description="Anthropic API key")
    
    # Rate limiting
    finnhub_rate_limit: int = Field(default=60, description="Finnhub requests per minute", ge=1)
    alpha_vantage_rate_limit: int = Field(default=5, description="Alpha Vantage requests per minute", ge=1)
    news_api_rate_limit: int = Field(default=1000, description="News API requests per day", ge=1)
    
    # Request settings
    request_timeout: int = Field(default=30, description="Request timeout in seconds", ge=1, le=300)
    max_retries: int = Field(default=3, description="Maximum retry attempts", ge=0, le=10)
    retry_delay: float = Field(default=1.0, description="Retry delay in seconds", ge=0.1)
    
    # Cache settings
    cache_ttl: int = Field(default=300, description="Cache TTL in seconds", ge=0)
    enable_caching: bool = Field(default=True, description="Enable response caching")


class AgentConfig(BaseModel):
    """Agent configuration."""
    
    # Execution settings
    max_concurrent: int = Field(default=5, description="Max concurrent agents", ge=1, le=20)
    timeout: int = Field(default=300, description="Agent timeout in seconds", ge=30, le=1800)
    retry_attempts: int = Field(default=3, description="Retry attempts", ge=0, le=10)
    
    # Model settings
    default_model: str = Field(default="claude-3-sonnet-20240229", description="Default LLM model")
    temperature: float = Field(default=0.1, description="Model temperature", ge=0.0, le=2.0)
    max_tokens: int = Field(default=4000, description="Max tokens per request", ge=100, le=100000)
    
    # Checkpoint settings
    checkpoint_interval: int = Field(default=60, description="Checkpoint interval in seconds", ge=10)
    enable_checkpoints: bool = Field(default=True, description="Enable HITL checkpoints")
    checkpoint_timeout: int = Field(default=3600, description="Checkpoint timeout in seconds", ge=60)
    
    # Quality settings
    min_confidence_threshold: float = Field(default=0.3, description="Min confidence threshold", ge=0.0, le=1.0)
    high_confidence_threshold: float = Field(default=0.8, description="High confidence threshold", ge=0.0, le=1.0)


class AlertConfig(BaseModel):
    """Alert system configuration."""
    
    # Email settings
    email_smtp_host: str = Field(default="smtp.gmail.com", description="SMTP host")
    email_smtp_port: int = Field(default=587, description="SMTP port", ge=1, le=65535)
    email_username: str = Field(default="", description="Email username")
    email_password: SecretStr = Field(default="", description="Email password")
    email_from: str = Field(default="", description="From email address")
    email_use_tls: bool = Field(default=True, description="Use TLS for email")
    
    # Slack settings
    slack_webhook_url: str = Field(default="", description="Slack webhook URL")
    slack_username: str = Field(default="ResearchLab", description="Slack bot username")
    slack_icon_emoji: str = Field(default=":chart_with_upwards_trend:", description="Slack icon emoji")
    
    # Webhook settings
    webhook_timeout: int = Field(default=10, description="Webhook timeout in seconds", ge=1, le=60)
    webhook_retries: int = Field(default=3, description="Webhook retry attempts", ge=0, le=10)
    webhook_verify_ssl: bool = Field(default=True, description="Verify SSL for webhooks")
    
    # Rate limiting
    max_alerts_per_minute: int = Field(default=10, description="Max alerts per minute", ge=1)
    max_alerts_per_hour: int = Field(default=100, description="Max alerts per hour", ge=1)
    
    # Cleanup
    alert_retention_days: int = Field(default=30, description="Alert retention in days", ge=1)


class WorkflowConfig(BaseModel):
    """Workflow configuration."""
    
    # Execution settings
    max_parallel_workflows: int = Field(default=3, description="Max parallel workflows", ge=1, le=10)
    workflow_timeout: int = Field(default=1800, description="Workflow timeout in seconds", ge=300)
    stage_timeout: int = Field(default=600, description="Stage timeout in seconds", ge=60)
    
    # Auto-cleanup
    auto_cleanup: bool = Field(default=True, description="Enable auto cleanup")
    cleanup_after_days: int = Field(default=7, description="Cleanup after days", ge=1)
    
    # Error handling
    max_retries: int = Field(default=2, description="Max workflow retries", ge=0, le=5)
    retry_delay: int = Field(default=60, description="Retry delay in seconds", ge=10)
    
    # Monitoring
    enable_monitoring: bool = Field(default=True, description="Enable workflow monitoring")
    metrics_interval: int = Field(default=60, description="Metrics collection interval", ge=10)


class SecurityConfig(BaseModel):
    """Security configuration."""
    
    # Authentication
    secret_key: SecretStr = Field(default="dev-secret-change-in-production", description="Application secret key")
    jwt_secret_key: SecretStr = Field(default="", description="JWT secret key")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    access_token_expire_minutes: int = Field(default=30, description="Access token expiry", ge=5, le=1440)
    
    # CORS
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"], 
        description="CORS allowed origins"
    )
    cors_methods: List[str] = Field(default=["GET", "POST", "PUT", "DELETE"], description="CORS allowed methods")
    
    # Rate limiting
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_requests: int = Field(default=100, description="Rate limit requests per window", ge=1)
    rate_limit_window: int = Field(default=3600, description="Rate limit window in seconds", ge=60)
    
    # API Security
    require_api_key: bool = Field(default=False, description="Require API key for requests")
    api_key_header: str = Field(default="X-API-Key", description="API key header name")


class LoggingConfig(BaseModel):
    """Logging configuration."""
    
    # Basic settings
    level: str = Field(default="INFO", description="Log level")
    format: str = Field(default="json", description="Log format (json|console)")
    
    # Output settings
    console_enabled: bool = Field(default=True, description="Enable console logging")
    file_enabled: bool = Field(default=True, description="Enable file logging")
    file_path: str = Field(default="logs/researchlab.log", description="Log file path")
    
    # Rotation settings
    file_max_size: str = Field(default="10MB", description="Max log file size")
    file_backup_count: int = Field(default=5, description="Number of backup files", ge=0)
    
    # Structured logging
    include_caller: bool = Field(default=True, description="Include caller info in logs")
    include_timestamp: bool = Field(default=True, description="Include timestamp in logs")
    include_level: bool = Field(default=True, description="Include level in logs")
    
    @validator('level')
    def validate_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v.upper()
    
    @validator('format')
    def validate_format(cls, v):
        valid_formats = ['json', 'console', 'text']
        if v.lower() not in valid_formats:
            raise ValueError(f"Log format must be one of: {valid_formats}")
        return v.lower()


class MonitoringConfig(BaseModel):
    """Monitoring and metrics configuration."""
    
    # Metrics
    metrics_enabled: bool = Field(default=True, description="Enable metrics collection")
    metrics_port: int = Field(default=9090, description="Metrics server port", ge=1024, le=65535)
    metrics_path: str = Field(default="/metrics", description="Metrics endpoint path")
    
    # Health checks
    health_check_enabled: bool = Field(default=True, description="Enable health checks")
    health_check_interval: int = Field(default=60, description="Health check interval", ge=10)
    health_check_timeout: int = Field(default=10, description="Health check timeout", ge=1)
    
    # Performance monitoring
    performance_monitoring: bool = Field(default=True, description="Enable performance monitoring")
    slow_query_threshold: int = Field(default=1000, description="Slow query threshold in ms", ge=100)
    
    # Alerting thresholds
    cpu_usage_threshold: float = Field(default=80.0, description="CPU usage alert threshold", ge=0.0, le=100.0)
    memory_usage_threshold: float = Field(default=85.0, description="Memory usage alert threshold", ge=0.0, le=100.0)
    disk_usage_threshold: float = Field(default=90.0, description="Disk usage alert threshold", ge=0.0, le=100.0)
    
    # Data retention
    metrics_retention_days: int = Field(default=30, description="Metrics retention in days", ge=1)