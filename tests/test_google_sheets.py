"""Tests for Google Sheets output functionality."""

import pytest
import os
import json
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from datetime import datetime

from src.output.google_sheets import GoogleSheetsClient, ResearchReportGenerator, GoogleSheetsOutputManager


class TestGoogleSheetsClient:
    """Test cases for Google Sheets client."""

    @pytest.fixture
    def sheets_client(self):
        """Create a Google Sheets client for testing."""
        with patch('src.output.google_sheets.settings') as mock_settings:
            mock_settings.api.google_credentials_file = "test_credentials.json"
            return GoogleSheetsClient()

    @pytest.fixture
    def mock_credentials(self):
        """Mock Google credentials."""
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds.expired = False
        mock_creds.refresh_token = "test_refresh_token"
        mock_creds.to_json.return_value = json.dumps({"token": "test_token"})
        return mock_creds

    @pytest.fixture
    def mock_service(self):
        """Mock Google Sheets service."""
        mock_service = MagicMock()
        
        # Mock spreadsheets operations
        mock_service.spreadsheets().create().execute.return_value = {
            'spreadsheetId': 'test_spreadsheet_id'
        }
        
        mock_service.spreadsheets().values().update().execute.return_value = {
            'updatedCells': 10
        }
        
        mock_service.spreadsheets().batchUpdate().execute.return_value = {}
        
        mock_service.spreadsheets().get().execute.return_value = {
            'sheets': [{
                'properties': {
                    'title': 'Sheet1',
                    'sheetId': 0
                }
            }]
        }
        
        return mock_service

    def test_client_initialization(self, sheets_client):
        """Test client initializes correctly."""
        assert sheets_client.credentials_file is not None
        assert sheets_client.SCOPES == ['https://www.googleapis.com/auth/spreadsheets']
        assert sheets_client.service is None
        assert sheets_client.credentials is None

    @pytest.mark.asyncio
    @patch('src.output.google_sheets.Credentials.from_authorized_user_file')
    @patch('src.output.google_sheets.build')
    @patch('os.path.exists')
    async def test_authenticate_with_existing_token(self, mock_exists, mock_build, 
                                                  mock_from_file, sheets_client, 
                                                  mock_credentials, mock_service):
        """Test authentication with existing valid token."""
        
        mock_exists.return_value = True
        mock_from_file.return_value = mock_credentials
        mock_build.return_value = mock_service
        
        result = await sheets_client.authenticate("test_token.json")
        
        assert result is True
        assert sheets_client.service == mock_service
        mock_from_file.assert_called_once_with("test_token.json", sheets_client.SCOPES)
        mock_build.assert_called_once_with('sheets', 'v4', credentials=mock_credentials)

    @pytest.mark.asyncio
    @patch('src.output.google_sheets.Credentials.from_authorized_user_file')
    @patch('src.output.google_sheets.build')
    @patch('src.output.google_sheets.Request')
    @patch('os.path.exists')
    async def test_authenticate_refresh_expired_token(self, mock_exists, mock_request,
                                                    mock_build, mock_from_file, 
                                                    sheets_client, mock_service):
        """Test authentication with expired token refresh."""
        
        # Mock expired credentials
        expired_creds = MagicMock()
        expired_creds.valid = False
        expired_creds.expired = True
        expired_creds.refresh_token = "test_refresh_token"
        expired_creds.to_json.return_value = json.dumps({"token": "refreshed_token"})
        
        mock_exists.return_value = True
        mock_from_file.return_value = expired_creds
        mock_build.return_value = mock_service
        
        with patch('builtins.open', mock_open()) as mock_file:
            result = await sheets_client.authenticate("test_token.json")
        
        assert result is True
        expired_creds.refresh.assert_called_once()
        mock_file.assert_called_once_with("test_token.json", 'w')

    @pytest.mark.asyncio
    @patch('src.output.google_sheets.Flow.from_client_secrets_file')
    @patch('os.path.exists')
    async def test_authenticate_new_flow_needed(self, mock_exists, mock_flow, sheets_client):
        """Test authentication when new OAuth flow is needed."""
        
        mock_exists.side_effect = lambda path: path == "test_credentials.json"
        
        mock_flow_instance = MagicMock()
        mock_flow_instance.authorization_url.return_value = ("http://auth.url", "state")
        mock_flow.return_value = mock_flow_instance
        
        result = await sheets_client.authenticate("test_token.json")
        
        assert result is False  # Should return False for manual setup needed
        mock_flow.assert_called_once_with("test_credentials.json", sheets_client.SCOPES)

    @pytest.mark.asyncio
    @patch('os.path.exists')
    async def test_authenticate_no_credentials_file(self, mock_exists, sheets_client):
        """Test authentication fails when credentials file doesn't exist."""
        
        mock_exists.return_value = False
        
        result = await sheets_client.authenticate("test_token.json")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_create_spreadsheet_success(self, sheets_client, mock_service):
        """Test successful spreadsheet creation."""
        
        sheets_client.service = mock_service
        
        result = await sheets_client.create_spreadsheet("Test Spreadsheet")
        
        assert result == "test_spreadsheet_id"
        mock_service.spreadsheets().create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_spreadsheet_not_authenticated(self, sheets_client):
        """Test spreadsheet creation fails when not authenticated."""
        
        result = await sheets_client.create_spreadsheet("Test Spreadsheet")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_update_sheet_data_success(self, sheets_client, mock_service):
        """Test successful sheet data update."""
        
        sheets_client.service = mock_service
        test_data = [["A1", "B1"], ["A2", "B2"]]
        
        result = await sheets_client.update_sheet_data(
            "test_spreadsheet_id", "Sheet1", test_data, "A1"
        )
        
        assert result is True
        mock_service.spreadsheets().values().update.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_sheet_success(self, sheets_client, mock_service):
        """Test successful sheet addition."""
        
        sheets_client.service = mock_service
        
        result = await sheets_client.add_sheet(
            "test_spreadsheet_id", "New Sheet", rows=500, cols=20
        )
        
        assert result is True
        mock_service.spreadsheets().batchUpdate.assert_called_once()

    @pytest.mark.asyncio
    async def test_format_cells_success(self, sheets_client, mock_service):
        """Test successful cell formatting."""
        
        sheets_client.service = mock_service
        format_dict = {'textFormat': {'bold': True}}
        
        result = await sheets_client.format_cells(
            "test_spreadsheet_id", "Sheet1", 1, 5, 1, 3, format_dict
        )
        
        assert result is True
        # Should call get() to find sheet ID, then batchUpdate() to format
        mock_service.spreadsheets().get.assert_called_once()
        mock_service.spreadsheets().batchUpdate.assert_called()


class TestResearchReportGenerator:
    """Test cases for Research Report Generator."""

    @pytest.fixture
    def mock_sheets_client(self):
        """Mock sheets client for report generator."""
        mock_client = MagicMock()
        mock_client.create_spreadsheet = AsyncMock(return_value="test_spreadsheet_id")
        mock_client.add_sheet = AsyncMock(return_value=True)
        mock_client.update_sheet_data = AsyncMock(return_value=True)
        mock_client.format_cells = AsyncMock(return_value=True)
        return mock_client

    @pytest.fixture
    def report_generator(self, mock_sheets_client):
        """Create report generator with mocked sheets client."""
        return ResearchReportGenerator(mock_sheets_client)

    @pytest.fixture
    def sample_research_data(self):
        """Sample research data for testing."""
        return {
            'investment_thesis': 'AI will drive growth in technology companies',
            'companies': [
                {'symbol': 'AAPL', 'name': 'Apple Inc.', 'sector': 'Technology'},
                {'symbol': 'GOOGL', 'name': 'Alphabet Inc.', 'sector': 'Technology'}
            ],
            'sentiment_analysis': {
                'market_sentiment': {
                    'market_sentiment_score': 0.65,
                    'sentiment_regime': 'bullish'
                },
                'confidence': 0.8,
                'company_analyses': [
                    {
                        'symbol': 'AAPL',
                        'sentiment_score': 0.7,
                        'news_sentiment': {
                            'key_themes': ['strong growth', 'innovation', 'market leadership']
                        }
                    },
                    {
                        'symbol': 'GOOGL',
                        'sentiment_score': 0.5,
                        'news_sentiment': {
                            'key_themes': ['regulatory concerns', 'AI development']
                        }
                    }
                ],
                'sentiment_signals': {
                    'buy_signals': [
                        {
                            'symbol': 'AAPL',
                            'sentiment_score': 0.7,
                            'reason': 'Strong positive sentiment trend',
                            'confidence': 0.85
                        }
                    ],
                    'sell_signals': []
                }
            },
            'risk_analysis': {
                'portfolio_risks': {
                    'portfolio_risk_score': 0.45,
                    'risk_concentration': 0.15,
                    'portfolio_vulnerabilities': [
                        {
                            'type': 'market_correlation',
                            'severity': 'medium',
                            'description': 'High correlation between companies',
                            'mitigation': 'Diversify across sectors'
                        }
                    ]
                },
                'company_risk_analyses': [
                    {
                        'symbol': 'AAPL',
                        'overall_risk_score': 0.4,
                        'risk_assessment': {
                            'key_risk_themes': ['market competition', 'supply chain']
                        },
                        'stress_test_results': {
                            'overall_stress_test_score': 0.35
                        }
                    },
                    {
                        'symbol': 'GOOGL',
                        'overall_risk_score': 0.5,
                        'risk_assessment': {
                            'key_risk_themes': ['regulatory risk', 'market saturation']
                        },
                        'stress_test_results': {
                            'overall_stress_test_score': 0.45
                        }
                    }
                ],
                'risk_recommendations': {
                    'high_priority': [
                        {
                            'action': 'Monitor regulatory developments',
                            'symbol': 'GOOGL',
                            'reason': 'Increasing regulatory scrutiny'
                        }
                    ]
                }
            },
            'supply_chain_analysis': {
                'company_analyses': [
                    {
                        'symbol': 'AAPL',
                        'risk_score': 0.6
                    },
                    {
                        'symbol': 'GOOGL',
                        'risk_score': 0.3
                    }
                ]
            }
        }

    def test_report_generator_initialization(self, report_generator):
        """Test report generator initializes correctly."""
        assert report_generator.sheets_client is not None
        assert hasattr(report_generator, 'header_format')
        assert hasattr(report_generator, 'title_format')
        assert hasattr(report_generator, 'positive_format')
        assert hasattr(report_generator, 'negative_format')

    def test_formatting_styles_defined(self, report_generator):
        """Test that formatting styles are properly defined."""
        # Header format should have background color and bold text
        assert 'backgroundColor' in report_generator.header_format
        assert 'textFormat' in report_generator.header_format
        assert report_generator.header_format['textFormat']['bold'] is True
        
        # Title format should be bold
        assert report_generator.title_format['textFormat']['bold'] is True
        
        # Positive format should have green tints
        positive_bg = report_generator.positive_format['backgroundColor']
        assert positive_bg['green'] > 0.8
        
        # Negative format should have red tints
        negative_bg = report_generator.negative_format['backgroundColor']
        assert negative_bg['red'] > 0.8

    @pytest.mark.asyncio
    async def test_generate_research_report_success(self, report_generator, 
                                                  sample_research_data, mock_sheets_client):
        """Test successful research report generation."""
        
        result = await report_generator.generate_research_report(
            sample_research_data, "Test Project"
        )
        
        assert result is not None
        assert "https://docs.google.com/spreadsheets/d/test_spreadsheet_id/edit" in result
        
        # Verify all sheets were created
        mock_sheets_client.create_spreadsheet.assert_called_once()
        assert mock_sheets_client.add_sheet.call_count == 3  # Company Analysis, Risk Analysis, Recommendations
        assert mock_sheets_client.update_sheet_data.call_count >= 4  # All sheets updated

    @pytest.mark.asyncio
    async def test_generate_research_report_creation_fails(self, report_generator, 
                                                         sample_research_data, 
                                                         mock_sheets_client):
        """Test report generation when spreadsheet creation fails."""
        
        mock_sheets_client.create_spreadsheet.return_value = None
        
        result = await report_generator.generate_research_report(
            sample_research_data, "Test Project"
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_create_executive_summary_sheet(self, report_generator, 
                                                sample_research_data, mock_sheets_client):
        """Test executive summary sheet creation."""
        
        result = await report_generator._create_executive_summary_sheet(
            "test_spreadsheet_id", sample_research_data
        )
        
        assert result is True
        mock_sheets_client.update_sheet_data.assert_called_once()
        mock_sheets_client.format_cells.assert_called()

    @pytest.mark.asyncio
    async def test_create_company_analysis_sheet(self, report_generator, 
                                               sample_research_data, mock_sheets_client):
        """Test company analysis sheet creation."""
        
        result = await report_generator._create_company_analysis_sheet(
            "test_spreadsheet_id", sample_research_data
        )
        
        assert result is True
        mock_sheets_client.add_sheet.assert_called_once_with("test_spreadsheet_id", "Company Analysis")
        mock_sheets_client.update_sheet_data.assert_called()

    @pytest.mark.asyncio
    async def test_create_risk_analysis_sheet(self, report_generator, 
                                            sample_research_data, mock_sheets_client):
        """Test risk analysis sheet creation."""
        
        result = await report_generator._create_risk_analysis_sheet(
            "test_spreadsheet_id", sample_research_data
        )
        
        assert result is True
        mock_sheets_client.add_sheet.assert_called_once_with("test_spreadsheet_id", "Risk Analysis")
        mock_sheets_client.update_sheet_data.assert_called()

    @pytest.mark.asyncio
    async def test_create_recommendations_sheet(self, report_generator, 
                                              sample_research_data, mock_sheets_client):
        """Test recommendations sheet creation."""
        
        result = await report_generator._create_recommendations_sheet(
            "test_spreadsheet_id", sample_research_data
        )
        
        assert result is True
        mock_sheets_client.add_sheet.assert_called_once_with("test_spreadsheet_id", "Recommendations")
        mock_sheets_client.update_sheet_data.assert_called()

    def test_get_company_metric_risk_analysis(self, report_generator, sample_research_data):
        """Test extracting company metrics from risk analysis."""
        
        result = report_generator._get_company_metric(
            sample_research_data, 'risk_analysis', 'AAPL', 'overall_risk_score', 0.5
        )
        
        assert result == 0.4  # From sample data

    def test_get_company_metric_sentiment_analysis(self, report_generator, sample_research_data):
        """Test extracting company metrics from sentiment analysis."""
        
        result = report_generator._get_company_metric(
            sample_research_data, 'sentiment_analysis', 'AAPL', 'sentiment_score', 0.0
        )
        
        assert result == 0.7  # From sample data

    def test_get_company_metric_not_found(self, report_generator, sample_research_data):
        """Test extracting company metrics when company not found."""
        
        result = report_generator._get_company_metric(
            sample_research_data, 'risk_analysis', 'UNKNOWN', 'overall_risk_score', 0.5
        )
        
        assert result == 0.5  # Default value

    def test_get_company_insights_strengths(self, report_generator, sample_research_data):
        """Test extracting company strengths."""
        
        result = report_generator._get_company_insights(
            sample_research_data, 'AAPL', 'strengths'
        )
        
        assert 'strong growth' in result.lower() or 'innovation' in result.lower()

    def test_get_company_insights_risks(self, report_generator, sample_research_data):
        """Test extracting company risks."""
        
        result = report_generator._get_company_insights(
            sample_research_data, 'AAPL', 'risks'
        )
        
        assert 'competition' in result.lower() or 'supply chain' in result.lower()

    def test_get_company_insights_none_identified(self, report_generator):
        """Test company insights when none are identified."""
        
        empty_data = {'companies': [{'symbol': 'TEST'}]}
        
        result = report_generator._get_company_insights(empty_data, 'TEST', 'strengths')
        
        assert result == 'None identified'


class TestGoogleSheetsOutputManager:
    """Test cases for Google Sheets Output Manager."""

    @pytest.fixture
    def output_manager(self):
        """Create output manager for testing."""
        with patch('src.output.google_sheets.GoogleSheetsClient'):
            with patch('src.output.google_sheets.ResearchReportGenerator'):
                return GoogleSheetsOutputManager()

    @pytest.fixture
    def sample_research_results(self):
        """Sample research results for testing."""
        return {
            'investment_thesis': 'Test investment thesis',
            'companies': [
                {'symbol': 'TEST1', 'name': 'Test Company 1'},
                {'symbol': 'TEST2', 'name': 'Test Company 2'}
            ],
            'analysis_completed': True
        }

    @pytest.mark.asyncio
    async def test_initialize_success(self, output_manager):
        """Test successful initialization."""
        
        output_manager.sheets_client.authenticate = AsyncMock(return_value=True)
        
        result = await output_manager.initialize()
        
        assert result is True
        output_manager.sheets_client.authenticate.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_failure(self, output_manager):
        """Test initialization failure."""
        
        output_manager.sheets_client.authenticate = AsyncMock(return_value=False)
        
        result = await output_manager.initialize()
        
        assert result is False

    @pytest.mark.asyncio
    async def test_create_research_report_success(self, output_manager, sample_research_results):
        """Test successful research report creation."""
        
        output_manager.sheets_client.authenticate = AsyncMock(return_value=True)
        output_manager.report_generator.generate_research_report = AsyncMock(
            return_value="https://docs.google.com/spreadsheets/d/test_id/edit"
        )
        
        result = await output_manager.create_research_report(
            sample_research_results, "Test Project"
        )
        
        assert result is not None
        assert "https://docs.google.com/spreadsheets" in result
        output_manager.report_generator.generate_research_report.assert_called_once_with(
            sample_research_results, "Test Project"
        )

    @pytest.mark.asyncio
    async def test_create_research_report_auth_failure(self, output_manager, sample_research_results):
        """Test research report creation when authentication fails."""
        
        output_manager.sheets_client.authenticate = AsyncMock(return_value=False)
        
        result = await output_manager.create_research_report(
            sample_research_results, "Test Project"
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_create_quick_summary_success(self, output_manager, sample_research_results):
        """Test successful quick summary creation."""
        
        output_manager.sheets_client.authenticate = AsyncMock(return_value=True)
        output_manager.sheets_client.create_spreadsheet = AsyncMock(return_value="test_id")
        output_manager.sheets_client.update_sheet_data = AsyncMock(return_value=True)
        
        result = await output_manager.create_quick_summary(
            sample_research_results, "Test Project"
        )
        
        assert result is not None
        assert "https://docs.google.com/spreadsheets/d/test_id/edit" in result

    @pytest.mark.asyncio
    async def test_create_quick_summary_spreadsheet_creation_fails(self, output_manager, 
                                                                 sample_research_results):
        """Test quick summary creation when spreadsheet creation fails."""
        
        output_manager.sheets_client.authenticate = AsyncMock(return_value=True)
        output_manager.sheets_client.create_spreadsheet = AsyncMock(return_value=None)
        
        result = await output_manager.create_quick_summary(
            sample_research_results, "Test Project"
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_create_quick_summary_with_exception(self, output_manager, sample_research_results):
        """Test quick summary creation handles exceptions."""
        
        output_manager.sheets_client.authenticate = AsyncMock(return_value=True)
        output_manager.sheets_client.create_spreadsheet = AsyncMock(
            side_effect=Exception("Test error")
        )
        
        result = await output_manager.create_quick_summary(
            sample_research_results, "Test Project"
        )
        
        assert result is None

    def test_output_manager_initialization(self, output_manager):
        """Test output manager initializes correctly."""
        assert output_manager.sheets_client is not None
        assert output_manager.report_generator is not None
        assert hasattr(output_manager, 'logger')


class TestIntegration:
    """Integration tests for Google Sheets functionality."""

    @pytest.mark.asyncio
    async def test_end_to_end_report_generation_mock(self):
        """Test end-to-end report generation with mocked dependencies."""
        
        # Create mock research data
        research_data = {
            'investment_thesis': 'Technology companies will benefit from AI adoption',
            'companies': [
                {'symbol': 'AAPL', 'name': 'Apple Inc.', 'sector': 'Technology'}
            ],
            'sentiment_analysis': {
                'market_sentiment': {'market_sentiment_score': 0.6},
                'company_analyses': [
                    {'symbol': 'AAPL', 'sentiment_score': 0.7}
                ]
            },
            'risk_analysis': {
                'portfolio_risks': {'portfolio_risk_score': 0.4},
                'company_risk_analyses': [
                    {'symbol': 'AAPL', 'overall_risk_score': 0.3}
                ]
            }
        }
        
        # Mock all Google API components
        with patch('src.output.google_sheets.GoogleSheetsClient') as MockClient:
            with patch('src.output.google_sheets.ResearchReportGenerator') as MockGenerator:
                
                # Setup mocks
                mock_client = MockClient.return_value
                mock_client.authenticate = AsyncMock(return_value=True)
                
                mock_generator = MockGenerator.return_value
                mock_generator.generate_research_report = AsyncMock(
                    return_value="https://docs.google.com/spreadsheets/d/test_id/edit"
                )
                
                # Create output manager
                output_manager = GoogleSheetsOutputManager()
                
                # Generate report
                result = await output_manager.create_research_report(
                    research_data, "AI Investment Analysis"
                )
                
                # Verify results
                assert result is not None
                assert "https://docs.google.com/spreadsheets" in result
                mock_client.authenticate.assert_called_once()
                mock_generator.generate_research_report.assert_called_once()

    def test_report_data_extraction_edge_cases(self):
        """Test report data extraction with edge cases."""
        
        generator = ResearchReportGenerator(MagicMock())
        
        # Test with empty data
        empty_data = {}
        result = generator._get_company_metric(empty_data, 'risk_analysis', 'AAPL', 'risk_score', 0.5)
        assert result == 0.5
        
        # Test with missing company
        data_missing_company = {
            'risk_analysis': {
                'company_risk_analyses': [
                    {'symbol': 'GOOGL', 'overall_risk_score': 0.6}
                ]
            }
        }
        result = generator._get_company_metric(
            data_missing_company, 'risk_analysis', 'AAPL', 'overall_risk_score', 0.5
        )
        assert result == 0.5
        
        # Test insights with empty themes
        empty_themes_data = {
            'sentiment_analysis': {
                'company_analyses': [
                    {'symbol': 'AAPL', 'news_sentiment': {'key_themes': []}}
                ]
            }
        }
        result = generator._get_company_insights(empty_themes_data, 'AAPL', 'strengths')
        assert result == 'None identified'