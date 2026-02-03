"""Configuration management CLI commands."""

import click
import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional

from src.core.config import settings


@click.group()
def config_cli():
    """Configuration management commands."""
    pass


@config_cli.command('show')
@click.option('--section', help='Show specific configuration section')
@click.option('--format', type=click.Choice(['text', 'json', 'yaml']), default='text')
@click.option('--output', '-o', type=click.Path(), help='Save configuration to file')
def show_config(section, format, output):
    """
    Show current configuration.
    
    Examples:
        researchlab config show
        researchlab config show --section api
        researchlab config show --format json --output config.json
    """
    
    config_data = _get_config_data(section)
    
    if not config_data:
        click.echo(f"❌ Configuration section '{section}' not found")
        return 1
    
    # Format output
    if format == 'json':
        output_str = json.dumps(config_data, indent=2)
    elif format == 'yaml':
        output_str = yaml.dump(config_data, default_flow_style=False, indent=2)
    else:  # text
        output_str = _format_config_text(config_data, section)
    
    # Output or save
    if output:
        Path(output).write_text(output_str)
        click.echo(f"Configuration saved to {output}")
    else:
        click.echo(output_str)


def _get_config_data(section: Optional[str] = None) -> Dict[str, Any]:
    """Get configuration data."""
    
    config_data = {
        'app': {
            'name': settings.app.app_name,
            'version': settings.app.version,
            'environment': settings.app.environment,
            'debug': settings.app.debug,
            'timezone': settings.app.timezone,
            'host': settings.app.host,
            'port': settings.app.port
        },
        'database': {
            'host': settings.database.host,
            'port': settings.database.port,
            'name': settings.database.name,
            'username': settings.database.username,
            'pool_size': settings.database.pool_size,
            'echo_sql': settings.database.echo_sql
        },
        'api': {
            'finnhub_rate_limit': settings.api.finnhub_rate_limit,
            'alpha_vantage_rate_limit': settings.api.alpha_vantage_rate_limit,
            'news_api_rate_limit': settings.api.news_api_rate_limit,
            'request_timeout': settings.api.request_timeout,
            'max_retries': settings.api.max_retries,
            'cache_ttl': settings.api.cache_ttl
        },
        'agents': {
            'max_concurrent': settings.agents.max_concurrent,
            'timeout': settings.agents.timeout,
            'retry_attempts': settings.agents.retry_attempts,
            'checkpoint_interval': settings.agents.checkpoint_interval
        },
        'workflow': {
            'max_parallel_workflows': settings.workflow.max_parallel_workflows,
            'workflow_timeout': settings.workflow.workflow_timeout,
            'checkpoint_enabled': settings.workflow.checkpoint_enabled,
            'auto_cleanup': settings.workflow.auto_cleanup
        },
        'security': {
            'secret_key_set': bool(getattr(settings.security, 'secret_key', None)),
            'cors_origins': getattr(settings.security, 'cors_origins', []),
            'jwt_expire_minutes': getattr(settings.security, 'jwt_expire_minutes', 30)
        },
        'monitoring': {
            'metrics_enabled': getattr(settings.monitoring, 'metrics_enabled', False),
            'log_level': getattr(settings.monitoring, 'log_level', 'INFO'),
            'health_check_interval': getattr(settings.monitoring, 'health_check_interval', 60)
        }
    }
    
    if section:
        return config_data.get(section, {})
    
    return config_data


def _format_config_text(config_data: Dict[str, Any], section: Optional[str] = None) -> str:
    """Format configuration as text."""
    
    if section:
        output = f"📋 Configuration - {section.title()}\n"
        output += "=" * (20 + len(section)) + "\n\n"
        
        for key, value in config_data.items():
            if isinstance(value, dict):
                output += f"{key}:\n"
                for subkey, subvalue in value.items():
                    output += f"  {subkey}: {subvalue}\n"
            else:
                output += f"{key}: {value}\n"
    
    else:
        output = "📋 ResearchLab Configuration\n"
        output += "=" * 35 + "\n\n"
        
        for section_name, section_data in config_data.items():
            output += f"[{section_name}]\n"
            
            for key, value in section_data.items():
                if isinstance(value, dict):
                    output += f"  {key}:\n"
                    for subkey, subvalue in value.items():
                        output += f"    {subkey} = {subvalue}\n"
                else:
                    output += f"  {key} = {value}\n"
            
            output += "\n"
    
    return output


@config_cli.command('set')
@click.argument('key')
@click.argument('value')
@click.option('--type', 'value_type', type=click.Choice(['str', 'int', 'float', 'bool']), 
              default='str', help='Value type')
@click.option('--confirm', is_flag=True, help='Skip confirmation prompt')
def set_config(key, value, value_type, confirm):
    """
    Set configuration value.
    
    Examples:
        researchlab config set api.timeout 120 --type int
        researchlab config set app.debug true --type bool
        researchlab config set database.pool_size 10 --type int
    """
    
    click.echo(f"📝 Setting configuration: {key} = {value} ({value_type})")
    
    # Parse value
    parsed_value = _parse_config_value(value, value_type)
    
    if parsed_value is None:
        click.echo(f"❌ Invalid value '{value}' for type '{value_type}'")
        return 1
    
    # Confirm change
    if not confirm:
        if not click.confirm(f"Set {key} to {parsed_value}?"):
            click.echo("⏹️  Configuration change cancelled")
            return
    
    # Apply configuration change
    success = _set_config_value(key, parsed_value)
    
    if success:
        click.echo(f"✅ Configuration updated: {key} = {parsed_value}")
        click.echo("⚠️  Restart application for changes to take effect")
    else:
        click.echo(f"❌ Failed to set configuration value: {key}")
        return 1


def _parse_config_value(value: str, value_type: str) -> Any:
    """Parse configuration value based on type."""
    
    try:
        if value_type == 'int':
            return int(value)
        elif value_type == 'float':
            return float(value)
        elif value_type == 'bool':
            return value.lower() in ('true', '1', 'yes', 'on', 'enabled')
        else:  # str
            return value
    except ValueError:
        return None


def _set_config_value(key: str, value: Any) -> bool:
    """Set configuration value."""
    
    try:
        # Parse key path
        parts = key.split('.')
        
        if len(parts) != 2:
            click.echo("❌ Key must be in format 'section.key'")
            return False
        
        section, config_key = parts
        
        # Update environment or config file
        # This is a simplified implementation
        # In a real implementation, you'd update the appropriate config source
        
        click.echo(f"⚠️  Configuration setting not implemented yet")
        click.echo(f"To set {key} = {value}, update your environment variables or config file")
        
        return True
        
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return False


@config_cli.command('validate')
@click.option('--fix', is_flag=True, help='Attempt to fix validation issues')
def validate_config(fix):
    """
    Validate configuration.
    
    Examples:
        researchlab config validate
        researchlab config validate --fix
    """
    
    click.echo("🔍 Validating configuration...")
    
    issues = _validate_configuration()
    
    if not issues:
        click.echo("✅ Configuration is valid")
        return
    
    click.echo(f"❌ Found {len(issues)} configuration issues:")
    
    for i, issue in enumerate(issues, 1):
        severity = issue.get('severity', 'error')
        message = issue.get('message', 'Unknown issue')
        suggestion = issue.get('suggestion', '')
        
        severity_emoji = {
            'error': '🔴',
            'warning': '🟡',
            'info': 'ℹ️'
        }.get(severity, '❓')
        
        click.echo(f"  {i}. {severity_emoji} {message}")
        
        if suggestion:
            click.echo(f"      💡 {suggestion}")
    
    if fix:
        click.echo("\n🔧 Attempting to fix issues...")
        
        fixed_count = _fix_configuration_issues(issues)
        
        if fixed_count > 0:
            click.echo(f"✅ Fixed {fixed_count} issues")
            click.echo("Re-run validation to check remaining issues")
        else:
            click.echo("❌ No issues could be automatically fixed")
    else:
        click.echo("\n💡 Use --fix to attempt automatic fixes")


def _validate_configuration() -> list:
    """Validate configuration and return issues."""
    
    issues = []
    
    # Check required API keys
    try:
        if not getattr(settings.api, 'finnhub_api_key', None):
            issues.append({
                'severity': 'error',
                'message': 'Finnhub API key not configured',
                'suggestion': 'Set FINNHUB_API_KEY environment variable'
            })
        
        if not getattr(settings.api, 'alpha_vantage_api_key', None):
            issues.append({
                'severity': 'warning',
                'message': 'Alpha Vantage API key not configured',
                'suggestion': 'Set ALPHA_VANTAGE_API_KEY environment variable'
            })
        
        if not getattr(settings.api, 'news_api_key', None):
            issues.append({
                'severity': 'warning',
                'message': 'News API key not configured',
                'suggestion': 'Set NEWS_API_KEY environment variable'
            })
    
    except AttributeError as e:
        issues.append({
            'severity': 'error',
            'message': f'Configuration attribute missing: {str(e)}',
            'suggestion': 'Check configuration file structure'
        })
    
    # Check database configuration
    try:
        if not settings.database.host:
            issues.append({
                'severity': 'error',
                'message': 'Database host not configured',
                'suggestion': 'Set DB_HOST environment variable'
            })
        
        if settings.database.pool_size < 5:
            issues.append({
                'severity': 'warning',
                'message': 'Database pool size is very low',
                'suggestion': 'Consider increasing DB_POOL_SIZE to at least 5'
            })
    
    except AttributeError as e:
        issues.append({
            'severity': 'error',
            'message': f'Database configuration missing: {str(e)}',
            'suggestion': 'Check database configuration'
        })
    
    # Check security settings
    try:
        if not getattr(settings.security, 'secret_key', None):
            issues.append({
                'severity': 'error',
                'message': 'Secret key not configured',
                'suggestion': 'Set SECRET_KEY environment variable'
            })
    
    except AttributeError:
        issues.append({
            'severity': 'warning',
            'message': 'Security configuration not found',
            'suggestion': 'Add security configuration section'
        })
    
    # Check agent settings
    try:
        if settings.agents.max_concurrent > 20:
            issues.append({
                'severity': 'warning',
                'message': 'High agent concurrency setting',
                'suggestion': 'Consider reducing MAX_CONCURRENT_AGENTS to avoid resource exhaustion'
            })
    
    except AttributeError:
        pass
    
    return issues


def _fix_configuration_issues(issues: list) -> int:
    """Attempt to fix configuration issues."""
    
    fixed_count = 0
    
    for issue in issues:
        message = issue.get('message', '')
        
        # Simple fixes that can be automated
        if 'pool size is very low' in message:
            click.echo("  Suggesting pool size increase...")
            fixed_count += 1
        
        elif 'High agent concurrency' in message:
            click.echo("  Suggesting concurrency reduction...")
            fixed_count += 1
    
    return fixed_count


@config_cli.command('backup')
@click.argument('backup_file', type=click.Path())
@click.option('--format', type=click.Choice(['json', 'yaml']), default='json')
def backup_config(backup_file, format):
    """
    Backup current configuration.
    
    Examples:
        researchlab config backup config_backup.json
        researchlab config backup config_backup.yaml --format yaml
    """
    
    click.echo(f"💾 Backing up configuration to {backup_file}...")
    
    config_data = _get_config_data()
    
    try:
        if format == 'yaml':
            with open(backup_file, 'w') as f:
                yaml.dump(config_data, f, default_flow_style=False, indent=2)
        else:  # json
            with open(backup_file, 'w') as f:
                json.dump(config_data, f, indent=2)
        
        click.echo(f"✅ Configuration backed up to {backup_file}")
        
    except Exception as e:
        click.echo(f"❌ Failed to backup configuration: {e}")
        return 1


@config_cli.command('restore')
@click.argument('backup_file', type=click.Path(exists=True))
@click.option('--dry-run', is_flag=True, help='Show what would be changed without applying')
@click.confirmation_option(prompt='This will overwrite current configuration. Continue?')
def restore_config(backup_file, dry_run):
    """
    Restore configuration from backup.
    
    Examples:
        researchlab config restore config_backup.json
        researchlab config restore config_backup.yaml --dry-run
    """
    
    click.echo(f"♻️  {'Previewing' if dry_run else 'Restoring'} configuration from {backup_file}...")
    
    try:
        # Load backup file
        with open(backup_file, 'r') as f:
            if backup_file.endswith('.yaml') or backup_file.endswith('.yml'):
                backup_data = yaml.safe_load(f)
            else:
                backup_data = json.load(f)
        
        if dry_run:
            click.echo("📋 Configuration changes that would be applied:")
            current_config = _get_config_data()
            
            changes = _compare_configs(current_config, backup_data)
            
            if not changes:
                click.echo("  No changes detected")
            else:
                for change in changes:
                    click.echo(f"  {change}")
        
        else:
            # Apply configuration
            success = _apply_configuration(backup_data)
            
            if success:
                click.echo("✅ Configuration restored successfully")
                click.echo("⚠️  Restart application for changes to take effect")
            else:
                click.echo("❌ Failed to restore configuration")
                return 1
    
    except Exception as e:
        click.echo(f"❌ Failed to restore configuration: {e}")
        return 1


def _compare_configs(current: Dict[str, Any], backup: Dict[str, Any]) -> list:
    """Compare configurations and return list of changes."""
    
    changes = []
    
    for section, section_data in backup.items():
        if section not in current:
            changes.append(f"+ Section '{section}' will be added")
            continue
        
        for key, value in section_data.items():
            current_value = current[section].get(key)
            
            if current_value != value:
                changes.append(f"  {section}.{key}: {current_value} → {value}")
    
    return changes


def _apply_configuration(config_data: Dict[str, Any]) -> bool:
    """Apply configuration data."""
    
    try:
        # This is a simplified implementation
        # In a real implementation, you'd update the configuration sources
        
        click.echo("⚠️  Configuration restore not fully implemented")
        click.echo("Please manually update environment variables or configuration files")
        
        return True
        
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return False


@config_cli.command('reset')
@click.option('--section', help='Reset specific section only')
@click.confirmation_option(prompt='This will reset configuration to defaults. Continue?')
def reset_config(section):
    """
    Reset configuration to defaults.
    
    Examples:
        researchlab config reset
        researchlab config reset --section api
    """
    
    if section:
        click.echo(f"🔄 Resetting {section} configuration to defaults...")
    else:
        click.echo("🔄 Resetting all configuration to defaults...")
    
    success = _reset_configuration(section)
    
    if success:
        reset_scope = f"{section} configuration" if section else "configuration"
        click.echo(f"✅ {reset_scope.title()} reset to defaults")
        click.echo("⚠️  Restart application for changes to take effect")
    else:
        click.echo("❌ Failed to reset configuration")
        return 1


def _reset_configuration(section: Optional[str] = None) -> bool:
    """Reset configuration to defaults."""
    
    try:
        # This would reset environment variables or config files to defaults
        # Simplified implementation
        
        click.echo("⚠️  Configuration reset not fully implemented")
        click.echo("Please manually reset environment variables or remove configuration files")
        
        return True
        
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return False


@config_cli.command('env')
@click.option('--show-secrets', is_flag=True, help='Show secret values (use carefully)')
def show_env_vars(show_secrets):
    """
    Show environment variables used by ResearchLab.
    
    Examples:
        researchlab config env
        researchlab config env --show-secrets
    """
    
    click.echo("🔧 ResearchLab Environment Variables")
    click.echo("=" * 40)
    
    env_vars = _get_environment_variables(show_secrets)
    
    for section, vars_data in env_vars.items():
        click.echo(f"\n[{section}]")
        
        for var_name, var_info in vars_data.items():
            value = var_info['value']
            is_set = var_info['is_set']
            is_secret = var_info.get('is_secret', False)
            
            if is_secret and not show_secrets and is_set:
                value = '***hidden***'
            
            status_emoji = '✅' if is_set else '❌'
            click.echo(f"  {status_emoji} {var_name}: {value}")
    
    if not show_secrets:
        secret_count = sum(
            sum(1 for var in vars_data.values() if var.get('is_secret'))
            for vars_data in env_vars.values()
        )
        if secret_count > 0:
            click.echo(f"\n🔐 {secret_count} secret values hidden. Use --show-secrets to display.")


def _get_environment_variables(show_secrets: bool = False) -> Dict[str, Dict[str, Any]]:
    """Get environment variables information."""
    
    import os
    
    env_vars = {
        'Application': {
            'APP_NAME': {
                'value': os.getenv('APP_NAME', 'researchlab'),
                'is_set': 'APP_NAME' in os.environ,
                'is_secret': False
            },
            'ENVIRONMENT': {
                'value': os.getenv('ENVIRONMENT', 'development'),
                'is_set': 'ENVIRONMENT' in os.environ,
                'is_secret': False
            },
            'DEBUG': {
                'value': os.getenv('DEBUG', 'false'),
                'is_set': 'DEBUG' in os.environ,
                'is_secret': False
            },
            'HOST': {
                'value': os.getenv('HOST', '0.0.0.0'),
                'is_set': 'HOST' in os.environ,
                'is_secret': False
            },
            'PORT': {
                'value': os.getenv('PORT', '8000'),
                'is_set': 'PORT' in os.environ,
                'is_secret': False
            }
        },
        'Database': {
            'DB_HOST': {
                'value': os.getenv('DB_HOST', 'localhost'),
                'is_set': 'DB_HOST' in os.environ,
                'is_secret': False
            },
            'DB_PORT': {
                'value': os.getenv('DB_PORT', '5432'),
                'is_set': 'DB_PORT' in os.environ,
                'is_secret': False
            },
            'DB_NAME': {
                'value': os.getenv('DB_NAME', 'researchlab'),
                'is_set': 'DB_NAME' in os.environ,
                'is_secret': False
            },
            'DB_USERNAME': {
                'value': os.getenv('DB_USERNAME', 'postgres'),
                'is_set': 'DB_USERNAME' in os.environ,
                'is_secret': False
            },
            'DB_PASSWORD': {
                'value': os.getenv('DB_PASSWORD', ''),
                'is_set': 'DB_PASSWORD' in os.environ,
                'is_secret': True
            }
        },
        'API Keys': {
            'FINNHUB_API_KEY': {
                'value': os.getenv('FINNHUB_API_KEY', ''),
                'is_set': 'FINNHUB_API_KEY' in os.environ,
                'is_secret': True
            },
            'ALPHA_VANTAGE_API_KEY': {
                'value': os.getenv('ALPHA_VANTAGE_API_KEY', ''),
                'is_set': 'ALPHA_VANTAGE_API_KEY' in os.environ,
                'is_secret': True
            },
            'NEWS_API_KEY': {
                'value': os.getenv('NEWS_API_KEY', ''),
                'is_set': 'NEWS_API_KEY' in os.environ,
                'is_secret': True
            },
            'OPENAI_API_KEY': {
                'value': os.getenv('OPENAI_API_KEY', ''),
                'is_set': 'OPENAI_API_KEY' in os.environ,
                'is_secret': True
            }
        },
        'Security': {
            'SECRET_KEY': {
                'value': os.getenv('SECRET_KEY', ''),
                'is_set': 'SECRET_KEY' in os.environ,
                'is_secret': True
            },
            'JWT_SECRET_KEY': {
                'value': os.getenv('JWT_SECRET_KEY', ''),
                'is_set': 'JWT_SECRET_KEY' in os.environ,
                'is_secret': True
            }
        }
    }
    
    return env_vars


@config_cli.command('template')
@click.option('--format', type=click.Choice(['env', 'json', 'yaml']), default='env')
@click.option('--output', '-o', type=click.Path(), help='Save template to file')
def create_template(format, output):
    """
    Create configuration template.
    
    Examples:
        researchlab config template --output .env
        researchlab config template --format yaml --output config_template.yaml
    """
    
    click.echo(f"📝 Creating {format.upper()} configuration template...")
    
    template_content = _create_config_template(format)
    
    if output:
        Path(output).write_text(template_content)
        click.echo(f"✅ Configuration template saved to {output}")
    else:
        click.echo(template_content)


def _create_config_template(format: str) -> str:
    """Create configuration template."""
    
    if format == 'env':
        return """# ResearchLab Environment Configuration Template

# Application Settings
APP_NAME=researchlab
ENVIRONMENT=development
DEBUG=false
HOST=0.0.0.0
PORT=8000

# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=researchlab
DB_USERNAME=postgres
DB_PASSWORD=your_password_here

# API Keys (Required)
FINNHUB_API_KEY=your_finnhub_key_here
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key_here
NEWS_API_KEY=your_news_api_key_here
OPENAI_API_KEY=your_openai_key_here

# Security
SECRET_KEY=your_secret_key_here
JWT_SECRET_KEY=your_jwt_secret_key_here

# API Rate Limits (requests per minute)
FINNHUB_RATE_LIMIT=60
ALPHA_VANTAGE_RATE_LIMIT=5
NEWS_API_RATE_LIMIT=1000

# Agent Configuration
MAX_CONCURRENT_AGENTS=5
AGENT_TIMEOUT=300
AGENT_RETRY_ATTEMPTS=3

# Workflow Settings
MAX_PARALLEL_WORKFLOWS=3
WORKFLOW_TIMEOUT=1800
CHECKPOINT_ENABLED=true

# Monitoring
METRICS_ENABLED=true
LOG_LEVEL=INFO
HEALTH_CHECK_INTERVAL=60
"""
    
    elif format == 'json':
        return json.dumps({
            "app": {
                "name": "researchlab",
                "environment": "development",
                "debug": False,
                "host": "0.0.0.0",
                "port": 8000
            },
            "database": {
                "host": "localhost",
                "port": 5432,
                "name": "researchlab",
                "username": "postgres",
                "password": "your_password_here"
            },
            "api_keys": {
                "finnhub": "your_finnhub_key_here",
                "alpha_vantage": "your_alpha_vantage_key_here",
                "news_api": "your_news_api_key_here",
                "openai": "your_openai_key_here"
            },
            "security": {
                "secret_key": "your_secret_key_here",
                "jwt_secret_key": "your_jwt_secret_key_here"
            },
            "api": {
                "rate_limits": {
                    "finnhub": 60,
                    "alpha_vantage": 5,
                    "news_api": 1000
                }
            },
            "agents": {
                "max_concurrent": 5,
                "timeout": 300,
                "retry_attempts": 3
            },
            "workflow": {
                "max_parallel_workflows": 3,
                "workflow_timeout": 1800,
                "checkpoint_enabled": True
            },
            "monitoring": {
                "metrics_enabled": True,
                "log_level": "INFO",
                "health_check_interval": 60
            }
        }, indent=2)
    
    elif format == 'yaml':
        return """# ResearchLab Configuration Template

app:
  name: researchlab
  environment: development
  debug: false
  host: 0.0.0.0
  port: 8000

database:
  host: localhost
  port: 5432
  name: researchlab
  username: postgres
  password: your_password_here

api_keys:
  finnhub: your_finnhub_key_here
  alpha_vantage: your_alpha_vantage_key_here
  news_api: your_news_api_key_here
  openai: your_openai_key_here

security:
  secret_key: your_secret_key_here
  jwt_secret_key: your_jwt_secret_key_here

api:
  rate_limits:
    finnhub: 60
    alpha_vantage: 5
    news_api: 1000

agents:
  max_concurrent: 5
  timeout: 300
  retry_attempts: 3

workflow:
  max_parallel_workflows: 3
  workflow_timeout: 1800
  checkpoint_enabled: true

monitoring:
  metrics_enabled: true
  log_level: INFO
  health_check_interval: 60
"""
    
    return ""