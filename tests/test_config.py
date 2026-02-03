"""Tests for enhanced configuration management."""

import os
import pytest
import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch

from src.core.config import (
    Settings, 
    YAMLConfigLoader, 
    ConfigValidationError,
    get_settings
)


class TestYAMLConfigLoader:
    """Test YAML configuration loading functionality."""
    
    def test_load_yaml_valid_file(self):
        """Test loading valid YAML configuration."""
        test_config = {
            "app": {"name": "TestApp", "debug": True},
            "database": {"host": "testhost", "port": 5433}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(test_config, f)
            config_path = Path(f.name)
        
        try:
            loader = YAMLConfigLoader()
            loaded_config = loader.load_yaml(config_path)
            
            assert loaded_config == test_config
        finally:
            config_path.unlink()
    
    def test_load_yaml_nonexistent_file(self):
        """Test loading nonexistent YAML file returns empty dict."""
        loader = YAMLConfigLoader()
        config = loader.load_yaml(Path("nonexistent.yaml"))
        assert config == {}
    
    def test_load_yaml_invalid_yaml(self):
        """Test loading invalid YAML raises ConfigValidationError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("invalid: yaml: content: [unclosed")
            config_path = Path(f.name)
        
        try:
            loader = YAMLConfigLoader()
            with pytest.raises(ConfigValidationError):
                loader.load_yaml(config_path)
        finally:
            config_path.unlink()
    
    def test_merge_configs(self):
        """Test configuration merging."""
        base_config = {
            "app": {"name": "BaseApp", "debug": False},
            "database": {"host": "localhost", "port": 5432},
            "new_section": {"value": 1}
        }
        
        override_config = {
            "app": {"debug": True, "version": "1.0"},
            "database": {"port": 5433},
            "another_section": {"value": 2}
        }
        
        loader = YAMLConfigLoader()
        merged = loader.merge_configs(base_config, override_config)
        
        expected = {
            "app": {"name": "BaseApp", "debug": True, "version": "1.0"},
            "database": {"host": "localhost", "port": 5433},
            "new_section": {"value": 1},
            "another_section": {"value": 2}
        }
        
        assert merged == expected


class TestEnhancedSettings:
    """Test enhanced Settings class with YAML support."""
    
    @patch.dict(os.environ, {}, clear=True)
    def test_settings_default_values(self):
        """Test settings with default values."""
        settings = Settings()
        
        assert settings.app.app_name == "ResearchLab"
        assert settings.app.environment == "development"
        assert settings.database.host == "localhost"
        assert settings.database.port == 5432
        assert settings.agents.default_model == "claude-3-sonnet-20240229"
    
    @patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True)
    def test_settings_production_validation_fails(self):
        """Test that production validation fails with default values."""
        with pytest.raises(ConfigValidationError):
            Settings()
    
    @patch.dict(os.environ, {
        "ENVIRONMENT": "production",
        "SECRET_KEY": "production-secret-key",
        "FINNHUB_API_KEY": "test-finnhub-key",
        "ALPHA_VANTAGE_API_KEY": "test-av-key", 
        "ANTHROPIC_API_KEY": "test-anthropic-key",
        "DB_PASSWORD": "test-password"
    }, clear=True)
    def test_settings_production_validation_passes(self):
        """Test that production validation passes with required env vars."""
        settings = Settings()
        
        assert settings.app.environment == "production"
        assert settings.app.secret_key == "production-secret-key"
        assert settings.api.finnhub_api_key == "test-finnhub-key"
    
    def test_settings_with_yaml_config(self):
        """Test settings loading with YAML configuration."""
        yaml_config = {
            "app": {
                "name": "CustomApp",
                "version": "2.0.0",
                "debug": True
            },
            "database": {
                "host": "custom-host",
                "port": 5433
            },
            "agents": {
                "max_concurrent_agents": 10,
                "temperature": 0.2
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(yaml_config, f)
            config_path = Path(f.name)
        
        try:
            with patch.object(Settings, '_load_yaml_config') as mock_load:
                mock_load.return_value = yaml_config
                settings = Settings()
                
                assert settings.app.app_name == "CustomApp"
                assert settings.app.version == "2.0.0" 
                assert settings.app.debug == True
                assert settings.database.host == "custom-host"
                assert settings.database.port == 5433
                assert settings.agents.max_concurrent_agents == 10
                assert settings.agents.temperature == 0.2
        finally:
            config_path.unlink()
    
    def test_environment_specific_overrides(self):
        """Test environment-specific configuration overrides."""
        yaml_config = {
            "app": {
                "name": "TestApp",
                "debug": False
            },
            "environments": {
                "testing": {
                    "app": {
                        "debug": True,
                        "log_level": "DEBUG"
                    },
                    "database": {
                        "name": "test_db"
                    }
                }
            }
        }
        
        with patch.dict(os.environ, {"ENVIRONMENT": "testing"}, clear=True):
            with patch.object(Settings, '_load_yaml_config') as mock_load:
                mock_load.return_value = yaml_config
                
                # Mock the environment-specific config merge
                with patch.object(YAMLConfigLoader, 'merge_configs') as mock_merge:
                    expected_merged = {
                        "app": {"name": "TestApp", "debug": True, "log_level": "DEBUG"},
                        "database": {"name": "test_db"}
                    }
                    mock_merge.return_value = expected_merged
                    mock_load.return_value = expected_merged
                    
                    settings = Settings()
                    assert settings.app.debug == True
    
    def test_google_credentials_validation(self):
        """Test Google credentials file validation."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            creds_file = Path(f.name)
        
        try:
            with patch.dict(os.environ, {"GOOGLE_CREDENTIALS_FILE": str(creds_file)}, clear=True):
                settings = Settings()
                assert settings.api.google_credentials_file == str(creds_file)
        finally:
            creds_file.unlink()
    
    def test_google_credentials_validation_missing_file(self):
        """Test validation fails for missing Google credentials file."""
        nonexistent_file = "/nonexistent/credentials.json"
        
        with patch.dict(os.environ, {"GOOGLE_CREDENTIALS_FILE": nonexistent_file}, clear=True):
            with pytest.raises(ConfigValidationError):
                Settings()


class TestGetSettings:
    """Test settings singleton functionality."""
    
    def test_get_settings_caching(self):
        """Test that get_settings caches the settings instance."""
        settings1 = get_settings()
        settings2 = get_settings()
        
        assert settings1 is settings2
    
    def test_get_settings_reload(self):
        """Test that get_settings can reload settings."""
        settings1 = get_settings()
        settings2 = get_settings(reload=True)
        
        # Should be different instances after reload
        assert settings1 is not settings2
        # But should have same values
        assert settings1.app.app_name == settings2.app.app_name


class TestConfigValidation:
    """Test configuration validation logic."""
    
    @patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True)
    def test_production_requires_secret_key(self):
        """Test that production environment requires secret key."""
        with pytest.raises(ConfigValidationError, match="SECRET_KEY must be set"):
            Settings()
    
    @patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True)
    def test_production_requires_api_keys(self):
        """Test that production environment requires API keys."""
        with patch.dict(os.environ, {"SECRET_KEY": "test-secret"}, clear=True):
            with pytest.raises(ConfigValidationError, match="FINNHUB_API_KEY is required"):
                Settings()
    
    def test_cors_origins_parsing(self):
        """Test CORS origins can be parsed from string."""
        cors_string = "http://localhost:3000,http://localhost:8080,https://example.com"
        
        with patch.dict(os.environ, {"CORS_ORIGINS": cors_string}, clear=True):
            settings = Settings()
            
            expected_origins = [
                "http://localhost:3000",
                "http://localhost:8080", 
                "https://example.com"
            ]
            
            assert settings.app.cors_origins == expected_origins
    
    def test_environment_validation(self):
        """Test environment value validation."""
        with patch.dict(os.environ, {"ENVIRONMENT": "invalid"}, clear=True):
            with pytest.raises(ConfigValidationError):
                Settings()


@pytest.fixture
def sample_yaml_config():
    """Fixture providing sample YAML configuration."""
    return {
        "app": {
            "name": "TestResearchLab",
            "version": "1.0.0",
            "environment": "testing",
            "debug": True
        },
        "database": {
            "host": "test-db-host",
            "port": 5433,
            "name": "test_researchlab"
        },
        "api": {
            "finnhub": {"api_key": "test-finnhub-key"},
            "alpha_vantage": {"api_key": "test-av-key"}
        },
        "agents": {
            "default_model": "test-model",
            "max_concurrent_agents": 3,
            "temperature": 0.5
        }
    }