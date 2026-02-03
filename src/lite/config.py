"""Simplified configuration for ResearchLab LITE version."""

import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings
from pydantic import Field


class LiteSettings(BaseSettings):
    """Simplified settings for ResearchLab LITE."""
    
    # Required API Keys
    anthropic_api_key: str = Field(..., env="ANTHROPIC_API_KEY")
    finnhub_api_key: str = Field(..., env="FINNHUB_API_KEY") 
    
    # Optional API Keys
    alpha_vantage_api_key: str = Field("", env="ALPHA_VANTAGE_API_KEY")
    
    # Database (SQLite)
    database_file: str = Field("researchlab.db", env="DATABASE_FILE")
    
    # App Settings
    debug: bool = Field(True, env="DEBUG")
    host: str = Field("localhost", env="HOST")
    port: int = Field(8000, env="PORT")
    
    # Internal settings
    app_name: str = "ResearchLab LITE"
    version: str = "1.0.0"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    @property
    def database_url(self) -> str:
        """Get SQLite database URL."""
        return f"sqlite+aiosqlite:///./{self.database_file}"
    
    def validate_required_keys(self):
        """Validate that required API keys are provided."""
        if not self.anthropic_api_key or self.anthropic_api_key == "sk-ant-your_anthropic_key_here":
            raise ValueError("ANTHROPIC_API_KEY must be set to a valid key")
        
        if not self.finnhub_api_key or self.finnhub_api_key == "your_finnhub_key_here":
            raise ValueError("FINNHUB_API_KEY must be set to a valid key")


# Global settings instance
settings = LiteSettings()