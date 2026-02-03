#!/usr/bin/env python3
"""Configuration validation script for ResearchLab."""

import sys
import os
from pathlib import Path
import argparse
from typing import List, Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.config import get_settings, ConfigValidationError
import structlog

# Configure logging
structlog.configure(
    processors=[
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    logger_factory=structlog.dev.LoggerFactory(),
    wrapper_class=structlog.make_filtering_bound_logger(30),  # WARNING level
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


class ConfigValidator:
    """Validates ResearchLab configuration."""
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []
    
    def validate_environment_variables(self, environment: str) -> None:
        """Validate environment variables for specific environment."""
        logger.info("Validating environment variables", environment=environment)
        
        # Required environment variables by environment
        required_vars = {
            "development": [],
            "testing": [],
            "production": [
                "SECRET_KEY",
                "FINNHUB_API_KEY", 
                "ALPHA_VANTAGE_API_KEY",
                "ANTHROPIC_API_KEY",
                "DB_PASSWORD"
            ]
        }
        
        # Check required variables
        required = required_vars.get(environment, [])
        missing = []
        
        for var in required:
            if not os.getenv(var):
                missing.append(var)
        
        if missing:
            self.errors.extend([f"Missing required environment variable: {var}" for var in missing])
        else:
            self.info.append(f"All required environment variables present for {environment}")
    
    def validate_api_keys(self, settings) -> None:
        """Validate API key configuration."""
        logger.info("Validating API keys")
        
        api_keys = {
            "Finnhub": settings.api.finnhub_api_key,
            "Alpha Vantage": settings.api.alpha_vantage_api_key,
            "Anthropic": settings.api.anthropic_api_key,
            "OpenAI": settings.api.openai_api_key,
        }
        
        for name, key in api_keys.items():
            if key:
                self.info.append(f"{name} API key configured")
            else:
                if settings.app.environment == "production":
                    self.errors.append(f"{name} API key not configured (required in production)")
                else:
                    self.warnings.append(f"{name} API key not configured")
    
    def validate_database_connection(self, settings) -> None:
        """Validate database configuration."""
        logger.info("Validating database configuration")
        
        try:
            # Basic URL validation
            db_url = settings.database.url
            if not db_url.startswith("postgresql"):
                self.errors.append("Database URL must use PostgreSQL")
            else:
                self.info.append("Database configuration valid")
        except Exception as e:
            self.errors.append(f"Database configuration error: {e}")
    
    def validate_file_paths(self, settings) -> None:
        """Validate file path configurations."""
        logger.info("Validating file paths")
        
        # Google credentials file
        if settings.api.google_credentials_file:
            creds_path = Path(settings.api.google_credentials_file)
            if creds_path.exists():
                self.info.append("Google credentials file found")
            else:
                self.errors.append(f"Google credentials file not found: {creds_path}")
        else:
            self.warnings.append("Google credentials file not configured")
        
        # Log directory
        if hasattr(settings.app, 'log_file'):
            log_path = Path(settings.app.log_file).parent
            if not log_path.exists():
                self.warnings.append(f"Log directory does not exist: {log_path}")
                try:
                    log_path.mkdir(parents=True, exist_ok=True)
                    self.info.append(f"Created log directory: {log_path}")
                except Exception as e:
                    self.errors.append(f"Failed to create log directory: {e}")
    
    def validate_security_settings(self, settings) -> None:
        """Validate security configuration."""
        logger.info("Validating security settings")
        
        # Secret key
        if settings.app.secret_key == "dev-secret-key-change-in-production":
            if settings.app.environment == "production":
                self.errors.append("Default secret key used in production")
            else:
                self.warnings.append("Using default secret key (change for production)")
        else:
            self.info.append("Custom secret key configured")
        
        # CORS origins
        if settings.app.cors_origins:
            self.info.append(f"CORS origins configured: {len(settings.app.cors_origins)}")
            for origin in settings.app.cors_origins:
                if origin == "*":
                    if settings.app.environment == "production":
                        self.errors.append("Wildcard CORS origin not allowed in production")
                    else:
                        self.warnings.append("Wildcard CORS origin configured")
        else:
            self.warnings.append("No CORS origins configured")
    
    def validate_agent_configuration(self, settings) -> None:
        """Validate AI agent configuration."""
        logger.info("Validating agent configuration")
        
        # Model availability
        if settings.agents.default_model:
            self.info.append(f"Default model configured: {settings.agents.default_model}")
        else:
            self.errors.append("No default model configured")
        
        # Timeout settings
        if settings.agents.agent_timeout_seconds < 30:
            self.warnings.append("Agent timeout is very short (< 30 seconds)")
        elif settings.agents.agent_timeout_seconds > 600:
            self.warnings.append("Agent timeout is very long (> 10 minutes)")
        else:
            self.info.append(f"Agent timeout configured: {settings.agents.agent_timeout_seconds}s")
        
        # Concurrency settings
        if settings.agents.max_concurrent_agents > 10:
            self.warnings.append("High concurrent agent limit may impact performance")
        else:
            self.info.append(f"Concurrent agents limit: {settings.agents.max_concurrent_agents}")
    
    def validate_monitoring_configuration(self, settings) -> None:
        """Validate monitoring configuration."""
        logger.info("Validating monitoring configuration")
        
        if settings.monitoring.metrics_enabled:
            self.info.append(f"Metrics enabled on port {settings.monitoring.metrics_port}")
        else:
            self.warnings.append("Metrics disabled")
        
        if settings.monitoring.health_enabled:
            self.info.append(f"Health checks enabled at {settings.monitoring.health_path}")
        else:
            self.warnings.append("Health checks disabled")
        
        if settings.monitoring.alerts_enabled:
            self.info.append("Alerts enabled")
        else:
            self.warnings.append("Alerts disabled")
    
    def run_validation(self, environment: str = None) -> bool:
        """Run complete configuration validation."""
        try:
            # Load settings
            settings = get_settings()
            
            if environment:
                os.environ["ENVIRONMENT"] = environment
                settings = get_settings(reload=True)
            
            # Run validations
            self.validate_environment_variables(settings.app.environment)
            self.validate_api_keys(settings)
            self.validate_database_connection(settings)
            self.validate_file_paths(settings)
            self.validate_security_settings(settings)
            self.validate_agent_configuration(settings)
            self.validate_monitoring_configuration(settings)
            
            return len(self.errors) == 0
            
        except ConfigValidationError as e:
            self.errors.append(f"Configuration validation failed: {e}")
            return False
        except Exception as e:
            self.errors.append(f"Unexpected validation error: {e}")
            return False
    
    def print_results(self, verbose: bool = False) -> None:
        """Print validation results."""
        if self.errors:
            print(f"\n❌ Configuration validation FAILED ({len(self.errors)} errors)")
            for error in self.errors:
                print(f"  ERROR: {error}")
        else:
            print("\n✅ Configuration validation PASSED")
        
        if self.warnings:
            print(f"\n⚠️  Warnings ({len(self.warnings)})")
            for warning in self.warnings:
                print(f"  WARNING: {warning}")
        
        if verbose and self.info:
            print(f"\n📋 Information ({len(self.info)})")
            for info in self.info:
                print(f"  INFO: {info}")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Validate ResearchLab configuration")
    parser.add_argument(
        "--environment", "-e",
        choices=["development", "testing", "staging", "production"],
        help="Environment to validate"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed validation info"
    )
    
    args = parser.parse_args()
    
    validator = ConfigValidator()
    success = validator.run_validation(args.environment)
    validator.print_results(args.verbose)
    
    if not success:
        sys.exit(1)
    
    print("\n🚀 Configuration is ready!")


if __name__ == "__main__":
    main()