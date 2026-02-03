"""Tests for CLI functionality."""

import pytest
import json
from unittest.mock import Mock, AsyncMock, patch
from click.testing import CliRunner

from src.cli.main import cli
from src.cli.research import research_cli
from src.cli.workflow import workflow_cli
from src.cli.news import news_cli
from src.cli.config import config_cli


class TestCLIMain:
    """Test main CLI functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
    
    def test_cli_help(self):
        """Test CLI help command."""
        result = self.runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert 'ResearchLab CLI' in result.output
        assert 'research' in result.output
        assert 'workflow' in result.output
        assert 'news' in result.output
        assert 'config' in result.output
    
    def test_version_command(self):
        """Test version command."""
        result = self.runner.invoke(cli, ['version'])
        assert result.exit_code == 0
        assert 'ResearchLab CLI' in result.output
    
    def test_health_command_basic(self):
        """Test basic health check."""
        result = self.runner.invoke(cli, ['health'])
        assert result.exit_code == 0
        assert 'Health Check' in result.output
        assert 'Configuration loaded' in result.output
    
    def test_health_command_with_flags(self):
        """Test health check with flags."""
        result = self.runner.invoke(cli, ['health', '--check-api', '--check-db', '--check-agents'])
        assert result.exit_code == 0
        assert 'API endpoints accessible' in result.output
        assert 'Database connection successful' in result.output
        assert 'All agents initialized' in result.output
    
    @patch('src.cli.main._run_quick_research')
    def test_quick_research_with_query(self, mock_research):
        """Test quick research with query."""
        mock_research.return_value = {
            'project_id': 'test_123',
            'status': 'started'
        }
        
        result = self.runner.invoke(cli, ['quick-research', 'Is AAPL a good buy?'])
        assert result.exit_code == 0
        assert 'Starting quick research analysis' in result.output
        assert 'Research completed' in result.output
    
    @patch('src.cli.main._run_quick_research')
    def test_quick_research_interactive(self, mock_research):
        """Test quick research interactive mode."""
        mock_research.return_value = {
            'project_id': 'test_123',
            'status': 'started'
        }
        
        result = self.runner.invoke(
            cli, 
            ['quick-research', '--interactive'],
            input='Tech sector analysis\nAAPL,GOOGL\n'
        )
        assert result.exit_code == 0
        assert 'Starting quick research analysis' in result.output
    
    def test_examples_basic(self):
        """Test basic examples command."""
        result = self.runner.invoke(cli, ['examples', 'basic'])
        assert result.exit_code == 0
        assert 'Basic ResearchLab CLI Examples' in result.output
        assert 'quick-research' in result.output
        assert 'research start' in result.output
    
    def test_examples_advanced(self):
        """Test advanced examples command."""
        result = self.runner.invoke(cli, ['examples', 'advanced'])
        assert result.exit_code == 0
        assert 'Advanced ResearchLab CLI Examples' in result.output
        assert 'research batch' in result.output
        assert 'workflow create' in result.output
    
    def test_export_config_text(self):
        """Test export config in text format."""
        result = self.runner.invoke(cli, ['export-config', '--format', 'text'])
        assert result.exit_code == 0
        assert 'ResearchLab Configuration' in result.output
        assert '[app]' in result.output
        assert '[database]' in result.output
    
    def test_export_config_json(self):
        """Test export config in JSON format."""
        result = self.runner.invoke(cli, ['export-config', '--format', 'json'])
        assert result.exit_code == 0
        
        # Should be valid JSON
        try:
            json.loads(result.output)
        except json.JSONDecodeError:
            pytest.fail("Output is not valid JSON")
    
    def test_export_config_to_file(self, tmp_path):
        """Test export config to file."""
        output_file = tmp_path / "test_config.json"
        
        result = self.runner.invoke(
            cli, 
            ['export-config', '--format', 'json', '--output', str(output_file)]
        )
        assert result.exit_code == 0
        assert output_file.exists()
        
        # Verify file content is valid JSON
        with open(output_file) as f:
            config_data = json.load(f)
        assert 'app' in config_data
        assert 'database' in config_data


class TestResearchCLI:
    """Test research CLI commands."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
    
    def test_research_help(self):
        """Test research help command."""
        result = self.runner.invoke(research_cli, ['--help'])
        assert result.exit_code == 0
        assert 'Research project management' in result.output
    
    @patch('src.cli.research._start_research_project')
    def test_start_research_basic(self, mock_start):
        """Test basic research start command."""
        mock_start.return_value = {
            'project_id': 'proj_123',
            'workflow_id': 'wf_123',
            'status': 'pending'
        }
        
        result = self.runner.invoke(
            research_cli, 
            ['start', 'Is AAPL undervalued?', '--companies', 'AAPL']
        )
        assert result.exit_code == 0
        assert 'Starting research project' in result.output
        assert 'proj_123' in result.output
    
    @patch('src.cli.research._start_research_project')
    def test_start_research_with_options(self, mock_start):
        """Test research start with all options."""
        mock_start.return_value = {
            'project_id': 'proj_123',
            'workflow_id': 'wf_123',
            'status': 'pending'
        }
        
        result = self.runner.invoke(
            research_cli, [
                'start', 'Tech analysis',
                '--companies', 'AAPL,GOOGL',
                '--thesis', 'AI growth will drive revenue',
                '--horizon', '24',
                '--risk', 'aggressive',
                '--agents', 'fundamental,quantitative',
                '--priority', 'high'
            ]
        )
        assert result.exit_code == 0
        assert 'AAPL, GOOGL' in result.output
        assert mock_start.called
    
    def test_start_research_missing_companies(self):
        """Test research start without companies."""
        result = self.runner.invoke(
            research_cli,
            ['start', 'Test query']
        )
        assert result.exit_code == 2  # Click validation error
    
    @patch('src.cli.research._get_project_status')
    def test_status_command(self, mock_status):
        """Test research status command."""
        mock_status.return_value = {
            'workflow_id': 'wf_123',
            'status': 'running',
            'progress_percentage': 45.0,
            'current_stage': 'agent_analysis'
        }
        
        result = self.runner.invoke(research_cli, ['status', 'proj_123'])
        assert result.exit_code == 0
        assert 'Research Status' in result.output
        assert 'running' in result.output
        assert '45.0%' in result.output
    
    @patch('src.cli.research._get_project_status')
    def test_status_not_found(self, mock_status):
        """Test research status for non-existent project."""
        mock_status.return_value = None
        
        result = self.runner.invoke(research_cli, ['status', 'proj_nonexistent'])
        assert result.exit_code == 1
        assert 'not found' in result.output
    
    @patch('src.cli.research._get_project_results')
    def test_results_command(self, mock_results):
        """Test research results command."""
        mock_results.return_value = {
            'query': 'Test query',
            'companies': [{'name': 'Apple Inc.', 'symbol': 'AAPL'}],
            'workflow_metadata': {'total_confidence': 0.85}
        }
        
        result = self.runner.invoke(research_cli, ['results', 'proj_123'])
        assert result.exit_code == 0
        assert 'Research Summary' in result.output
        assert 'Test query' in result.output
        assert 'Apple Inc.' in result.output
    
    def test_list_command(self):
        """Test research list command."""
        result = self.runner.invoke(research_cli, ['list'])
        assert result.exit_code == 0
        assert 'Research Projects' in result.output
    
    def test_list_with_filters(self):
        """Test research list with filters."""
        result = self.runner.invoke(
            research_cli, 
            ['list', '--status', 'completed', '--limit', '5']
        )
        assert result.exit_code == 0
    
    @patch('src.cli.research._cancel_project')
    def test_cancel_command(self, mock_cancel):
        """Test research cancel command."""
        mock_cancel.return_value = True
        
        result = self.runner.invoke(
            research_cli,
            ['cancel', 'proj_123'],
            input='y\n'
        )
        assert result.exit_code == 0
        assert 'cancelled successfully' in result.output
    
    def test_batch_command_missing_file(self):
        """Test batch research with missing file."""
        result = self.runner.invoke(
            research_cli,
            ['batch', 'nonexistent.json']
        )
        assert result.exit_code == 2  # File not found
    
    @patch('src.cli.research._run_batch_research')
    def test_batch_command_success(self, mock_batch, tmp_path):
        """Test batch research command."""
        # Create test input file
        input_file = tmp_path / "batch_input.json"
        batch_data = [
            {
                "query": "Is Apple undervalued?",
                "companies": ["AAPL"],
                "thesis": "Strong fundamentals"
            }
        ]
        with open(input_file, 'w') as f:
            json.dump(batch_data, f)
        
        mock_batch.return_value = [
            {'success': True, 'request': batch_data[0], 'result': {'project_id': 'proj_123'}}
        ]
        
        result = self.runner.invoke(
            research_cli,
            ['batch', str(input_file)]
        )
        assert result.exit_code == 0
        assert 'Starting batch research' in result.output
        assert '1/1 successful' in result.output


class TestWorkflowCLI:
    """Test workflow CLI commands."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
    
    def test_workflow_help(self):
        """Test workflow help command."""
        result = self.runner.invoke(workflow_cli, ['--help'])
        assert result.exit_code == 0
        assert 'Workflow management' in result.output
    
    @patch('src.cli.workflow._get_workflows')
    def test_list_workflows(self, mock_get):
        """Test workflow list command."""
        mock_get.return_value = [
            {
                'workflow_id': 'wf_123',
                'status': 'running',
                'current_stage': 'agent_analysis',
                'progress_percentage': 50.0,
                'start_time': '2024-02-01T10:00:00'
            }
        ]
        
        result = self.runner.invoke(workflow_cli, ['list'])
        assert result.exit_code == 0
        assert 'Workflows' in result.output
        assert 'wf_123' in result.output
    
    @patch('src.cli.workflow._get_workflow_status')
    def test_status_command(self, mock_status):
        """Test workflow status command."""
        mock_status.return_value = {
            'workflow_id': 'wf_123',
            'status': 'running',
            'progress_percentage': 75.0,
            'current_stage': 'report_generation',
            'start_time': '2024-02-01T10:00:00'
        }
        
        result = self.runner.invoke(workflow_cli, ['status', 'wf_123'])
        assert result.exit_code == 0
        assert 'Workflow Status' in result.output
        assert '75.0%' in result.output
    
    @patch('src.cli.workflow._cancel_workflow')
    def test_cancel_workflow(self, mock_cancel):
        """Test workflow cancel command."""
        mock_cancel.return_value = True
        
        result = self.runner.invoke(
            workflow_cli,
            ['cancel', 'wf_123'],
            input='y\n'
        )
        assert result.exit_code == 0
        assert 'cancelled successfully' in result.output
    
    @patch('src.cli.workflow._get_workflow_results')
    def test_results_command(self, mock_results):
        """Test workflow results command."""
        mock_results.return_value = {
            'workflow_id': 'wf_123',
            'companies': [{'name': 'Apple Inc.'}],
            'workflow_metadata': {'total_confidence': 0.9}
        }
        
        result = self.runner.invoke(workflow_cli, ['results', 'wf_123'])
        assert result.exit_code == 0
        assert 'Workflow Results Summary' in result.output
    
    def test_logs_command(self):
        """Test workflow logs command."""
        result = self.runner.invoke(workflow_cli, ['logs', 'wf_123'])
        assert result.exit_code == 0
        assert 'Workflow Logs' in result.output
    
    @patch('src.cli.workflow._get_system_status')
    def test_system_command(self, mock_system):
        """Test workflow system status."""
        mock_system.return_value = {
            'total_workflows': 5,
            'active_workflows': 2,
            'completed_workflows': 3,
            'system_load': 0.4,
            'success_rate': 0.85
        }
        
        result = self.runner.invoke(workflow_cli, ['system'])
        assert result.exit_code == 0
        assert 'Workflow System Status' in result.output
        assert 'Total Workflows: 5' in result.output
    
    @patch('src.cli.workflow._cleanup_workflows')
    def test_cleanup_command(self, mock_cleanup):
        """Test workflow cleanup command."""
        mock_cleanup.return_value = 3
        
        result = self.runner.invoke(
            workflow_cli,
            ['cleanup', '--max-age', '48'],
            input='y\n'
        )
        assert result.exit_code == 0
        assert 'Cleaned up 3 old workflows' in result.output


class TestNewsCLI:
    """Test news CLI commands."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
    
    def test_news_help(self):
        """Test news help command."""
        result = self.runner.invoke(news_cli, ['--help'])
        assert result.exit_code == 0
        assert 'News monitoring and analysis' in result.output
    
    @patch('src.cli.news._start_monitoring_interactive')
    def test_monitor_start_basic(self, mock_start):
        """Test news monitoring start command."""
        mock_start.return_value = True
        
        result = self.runner.invoke(
            news_cli,
            ['monitor', 'start', '--companies', 'Apple Inc.', '--tickers', 'AAPL']
        )
        assert result.exit_code == 0
        assert 'Starting news monitoring' in result.output
        assert 'Companies: Apple Inc.' in result.output
        assert 'Tickers: AAPL' in result.output
    
    def test_monitor_start_no_criteria(self):
        """Test news monitoring without criteria."""
        result = self.runner.invoke(news_cli, ['monitor', 'start'])
        assert result.exit_code == 1
        assert 'Must specify at least one of' in result.output
    
    @patch('src.cli.news._stop_monitoring_daemon')
    def test_monitor_stop(self, mock_stop):
        """Test news monitoring stop command."""
        mock_stop.return_value = True
        
        result = self.runner.invoke(news_cli, ['monitor', 'stop'])
        assert result.exit_code == 0
        assert 'Stopping news monitoring' in result.output
    
    @patch('src.cli.news._get_monitoring_status')
    def test_monitor_status(self, mock_status):
        """Test news monitoring status command."""
        mock_status.return_value = {
            'status': 'running',
            'uptime': '2 hours',
            'articles_processed': 150,
            'alerts_generated': 5
        }
        
        result = self.runner.invoke(news_cli, ['monitor', 'status'])
        assert result.exit_code == 0
        assert 'News Monitoring Status' in result.output
        assert 'Articles Processed: 150' in result.output
    
    @patch('src.cli.news._get_news_articles')
    def test_articles_command(self, mock_articles):
        """Test news articles command."""
        mock_articles.return_value = [
            {
                'title': 'Apple Reports Strong Earnings',
                'source': 'Reuters',
                'published_at': '2024-02-01T10:00:00',
                'sentiment': {'label': 'positive', 'score': 0.8}
            }
        ]
        
        result = self.runner.invoke(
            news_cli,
            ['articles', '--hours', '12', '--companies', 'Apple Inc.']
        )
        assert result.exit_code == 0
        assert 'Getting articles from last 12 hours' in result.output
        assert 'Found 1 articles' in result.output
    
    @patch('src.cli.news._analyze_news_trends')
    def test_trends_command(self, mock_trends):
        """Test news trends command."""
        mock_trends.return_value = {
            'overall_sentiment': {'label': 'positive', 'average_score': 0.65},
            'trending_keywords': [('AI', 50), ('growth', 30)],
            'company_trends': {
                'Apple': {'sentiment': 'positive', 'average_score': 0.8}
            }
        }
        
        result = self.runner.invoke(news_cli, ['trends', '--hours', '24'])
        assert result.exit_code == 0
        assert 'Analyzing news trends' in result.output
        assert 'News Trends Analysis' in result.output
    
    @patch('src.cli.news._analyze_article')
    def test_analyze_command(self, mock_analyze):
        """Test news analyze command."""
        mock_analyze.return_value = {
            'title': 'Apple Reports Earnings',
            'sentiment': {'label': 'positive', 'score': 0.8},
            'entities': {'companies': ['Apple Inc.']},
            'key_themes': ['earnings', 'growth']
        }
        
        result = self.runner.invoke(
            news_cli,
            ['analyze', 'article_123', '--targets', 'AAPL']
        )
        assert result.exit_code == 0
        assert 'Analyzing article article_123' in result.output
        assert 'Article Analysis' in result.output
    
    @patch('src.cli.news._export_news_data')
    def test_export_command(self, mock_export):
        """Test news export command."""
        mock_export.return_value = True
        
        result = self.runner.invoke(
            news_cli,
            ['export', '--hours', '24', '--format', 'csv', '--output', 'news.csv']
        )
        assert result.exit_code == 0
        assert 'Exporting 24 hours of news data' in result.output
        assert 'News data exported to news.csv' in result.output


class TestConfigCLI:
    """Test config CLI commands."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
    
    def test_config_help(self):
        """Test config help command."""
        result = self.runner.invoke(config_cli, ['--help'])
        assert result.exit_code == 0
        assert 'Configuration management' in result.output
    
    def test_show_config(self):
        """Test config show command."""
        result = self.runner.invoke(config_cli, ['show'])
        assert result.exit_code == 0
        assert 'ResearchLab Configuration' in result.output
        assert '[app]' in result.output
    
    def test_show_config_section(self):
        """Test config show specific section."""
        result = self.runner.invoke(config_cli, ['show', '--section', 'app'])
        assert result.exit_code == 0
        assert 'Configuration - App' in result.output
    
    def test_show_config_json(self):
        """Test config show in JSON format."""
        result = self.runner.invoke(config_cli, ['show', '--format', 'json'])
        assert result.exit_code == 0
        
        # Should be valid JSON
        try:
            json.loads(result.output)
        except json.JSONDecodeError:
            pytest.fail("Output is not valid JSON")
    
    def test_set_config(self):
        """Test config set command."""
        result = self.runner.invoke(
            config_cli,
            ['set', 'api.timeout', '120', '--type', 'int', '--confirm'],
            input='y\n'
        )
        assert result.exit_code == 0
        assert 'Setting configuration: api.timeout = 120' in result.output
    
    def test_set_config_invalid_format(self):
        """Test config set with invalid key format."""
        result = self.runner.invoke(
            config_cli,
            ['set', 'invalid_key', '120', '--confirm']
        )
        # Should handle the error gracefully
        assert 'section.key' in result.output
    
    def test_validate_config(self):
        """Test config validate command."""
        result = self.runner.invoke(config_cli, ['validate'])
        assert result.exit_code == 0
        assert 'Validating configuration' in result.output
    
    def test_backup_config(self, tmp_path):
        """Test config backup command."""
        backup_file = tmp_path / "config_backup.json"
        
        result = self.runner.invoke(
            config_cli,
            ['backup', str(backup_file)]
        )
        assert result.exit_code == 0
        assert 'Configuration backed up' in result.output
        assert backup_file.exists()
    
    def test_env_vars_command(self):
        """Test config env command."""
        result = self.runner.invoke(config_cli, ['env'])
        assert result.exit_code == 0
        assert 'Environment Variables' in result.output
        assert '[Application]' in result.output
        assert 'APP_NAME' in result.output
    
    def test_template_command(self):
        """Test config template command."""
        result = self.runner.invoke(config_cli, ['template'])
        assert result.exit_code == 0
        assert 'Creating ENV configuration template' in result.output
        assert 'APP_NAME=researchlab' in result.output
    
    def test_template_yaml(self):
        """Test config template in YAML format."""
        result = self.runner.invoke(
            config_cli,
            ['template', '--format', 'yaml']
        )
        assert result.exit_code == 0
        assert 'app:' in result.output
        assert 'database:' in result.output


class TestCLIIntegration:
    """Integration tests for CLI components."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
    
    def test_cli_subcommands_exist(self):
        """Test that all main subcommands are available."""
        result = self.runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        
        # Check all main subcommands are present
        assert 'research' in result.output
        assert 'workflow' in result.output  
        assert 'news' in result.output
        assert 'config' in result.output
        assert 'health' in result.output
        assert 'version' in result.output
    
    def test_research_subcommands_exist(self):
        """Test that research subcommands are available."""
        result = self.runner.invoke(cli, ['research', '--help'])
        assert result.exit_code == 0
        assert 'start' in result.output
        assert 'status' in result.output
        assert 'results' in result.output
        assert 'list' in result.output
        assert 'cancel' in result.output
    
    def test_workflow_subcommands_exist(self):
        """Test that workflow subcommands are available."""
        result = self.runner.invoke(cli, ['workflow', '--help'])
        assert result.exit_code == 0
        assert 'list' in result.output
        assert 'status' in result.output
        assert 'cancel' in result.output
        assert 'results' in result.output
    
    def test_news_subcommands_exist(self):
        """Test that news subcommands are available."""
        result = self.runner.invoke(cli, ['news', '--help'])
        assert result.exit_code == 0
        assert 'monitor' in result.output
        assert 'articles' in result.output
        assert 'trends' in result.output
        assert 'analyze' in result.output
    
    def test_config_subcommands_exist(self):
        """Test that config subcommands are available."""
        result = self.runner.invoke(cli, ['config', '--help'])
        assert result.exit_code == 0
        assert 'show' in result.output
        assert 'set' in result.output
        assert 'validate' in result.output
        assert 'backup' in result.output
    
    def test_error_handling(self):
        """Test CLI error handling."""
        # Test invalid command
        result = self.runner.invoke(cli, ['nonexistent-command'])
        assert result.exit_code == 2
        
        # Test invalid subcommand
        result = self.runner.invoke(cli, ['research', 'nonexistent'])
        assert result.exit_code == 2
    
    def test_verbose_flag(self):
        """Test verbose flag."""
        result = self.runner.invoke(cli, ['--verbose', 'version'])
        assert result.exit_code == 0
        # Should still work with verbose flag
        assert 'ResearchLab CLI' in result.output
    
    def test_debug_flag(self):
        """Test debug flag."""
        result = self.runner.invoke(cli, ['--debug', 'version'])
        assert result.exit_code == 0
        assert 'ResearchLab CLI' in result.output
    
    @patch('src.core.config.settings')
    def test_config_loading(self, mock_settings):
        """Test configuration loading in CLI."""
        mock_settings.app.version = "1.0.0"
        mock_settings.app.environment = "test"
        
        result = self.runner.invoke(cli, ['version'])
        assert result.exit_code == 0
        assert '1.0.0' in result.output
    
    def test_output_formats_json(self):
        """Test JSON output format where supported."""
        result = self.runner.invoke(config_cli, ['show', '--format', 'json'])
        assert result.exit_code == 0
        
        # Should be valid JSON
        try:
            data = json.loads(result.output)
            assert isinstance(data, dict)
        except json.JSONDecodeError:
            pytest.fail("JSON output is not valid")
    
    def test_cli_with_config_file(self, tmp_path):
        """Test CLI with config file option."""
        config_file = tmp_path / "test_config.json"
        config_data = {"test": "value"}
        
        with open(config_file, 'w') as f:
            json.dump(config_data, f)
        
        result = self.runner.invoke(
            cli,
            ['--config', str(config_file), 'version']
        )
        assert result.exit_code == 0


class TestCLIHelpers:
    """Test CLI helper functions."""
    
    def test_format_status_function(self):
        """Test status formatting helper."""
        from src.cli.research import _format_status
        
        assert _format_status('pending') == '⏳ Pending'
        assert _format_status('running') == '🔄 Running'
        assert _format_status('completed') == '✅ Completed'
        assert _format_status('failed') == '❌ Failed'
        assert _format_status('unknown') == '❓ Unknown'
    
    def test_format_confidence_function(self):
        """Test confidence formatting helper."""
        from src.cli.research import _format_confidence
        
        assert _format_confidence(0.9) == "High"
        assert _format_confidence(0.7) == "Medium"
        assert _format_confidence(0.5) == "Low"
        assert _format_confidence(0.2) == "Very Low"
    
    def test_parse_config_value_function(self):
        """Test config value parsing helper."""
        from src.cli.config import _parse_config_value
        
        assert _parse_config_value("123", "int") == 123
        assert _parse_config_value("12.5", "float") == 12.5
        assert _parse_config_value("true", "bool") == True
        assert _parse_config_value("false", "bool") == False
        assert _parse_config_value("test", "str") == "test"
        
        # Test invalid values
        assert _parse_config_value("invalid", "int") is None
        assert _parse_config_value("invalid", "float") is None