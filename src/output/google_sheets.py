"""Google Sheets output generator for research reports."""

import os
import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import asyncio

import structlog
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.core.config import settings

logger = structlog.get_logger()


class GoogleSheetsClient:
    """Client for Google Sheets API operations."""
    
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    
    def __init__(self, credentials_file: Optional[str] = None):
        self.credentials_file = credentials_file or settings.api.google_credentials_file
        self.service = None
        self.credentials = None
        self.logger = logger.bind(component="google_sheets")
        
    async def authenticate(self, token_file: str = "token.json") -> bool:
        """Authenticate with Google Sheets API."""
        try:
            # Load existing token
            if os.path.exists(token_file):
                self.credentials = Credentials.from_authorized_user_file(
                    token_file, self.SCOPES
                )
            
            # Refresh if expired
            if not self.credentials or not self.credentials.valid:
                if (self.credentials and self.credentials.expired and 
                    self.credentials.refresh_token):
                    self.credentials.refresh(Request())
                else:
                    # Need new authentication
                    if not self.credentials_file or not os.path.exists(self.credentials_file):
                        self.logger.error("google_credentials_file_not_found", 
                                        file=self.credentials_file)
                        return False
                    
                    flow = Flow.from_client_secrets_file(
                        self.credentials_file, self.SCOPES
                    )
                    flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
                    
                    auth_url, _ = flow.authorization_url(prompt='consent')
                    self.logger.info("google_auth_url_generated", url=auth_url)
                    
                    # In a real application, you'd redirect the user to auth_url
                    # For now, we'll return False to indicate manual setup needed
                    return False
                
                # Save credentials
                with open(token_file, 'w') as token:
                    token.write(self.credentials.to_json())
            
            # Build service
            self.service = build('sheets', 'v4', credentials=self.credentials)
            self.logger.info("google_sheets_authenticated_successfully")
            return True
            
        except Exception as e:
            self.logger.error("google_sheets_authentication_failed", error=str(e))
            return False
    
    async def create_spreadsheet(self, title: str) -> Optional[str]:
        """Create a new spreadsheet and return its ID."""
        if not self.service:
            self.logger.error("google_sheets_not_authenticated")
            return None
            
        try:
            spreadsheet_body = {
                'properties': {
                    'title': title
                }
            }
            
            result = self.service.spreadsheets().create(
                body=spreadsheet_body
            ).execute()
            
            spreadsheet_id = result.get('spreadsheetId')
            self.logger.info("spreadsheet_created", 
                           spreadsheet_id=spreadsheet_id, title=title)
            return spreadsheet_id
            
        except HttpError as e:
            self.logger.error("spreadsheet_creation_failed", error=str(e))
            return None
    
    async def update_sheet_data(self, spreadsheet_id: str, sheet_name: str,
                              data: List[List[Any]], start_cell: str = 'A1') -> bool:
        """Update sheet data starting from specified cell."""
        if not self.service:
            self.logger.error("google_sheets_not_authenticated")
            return False
            
        try:
            range_name = f"{sheet_name}!{start_cell}"
            
            body = {
                'values': data
            }
            
            result = self.service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()
            
            self.logger.info("sheet_data_updated", 
                           spreadsheet_id=spreadsheet_id, 
                           cells_updated=result.get('updatedCells', 0))
            return True
            
        except HttpError as e:
            self.logger.error("sheet_data_update_failed", 
                            spreadsheet_id=spreadsheet_id, error=str(e))
            return False
    
    async def add_sheet(self, spreadsheet_id: str, sheet_name: str, 
                       rows: int = 1000, cols: int = 26) -> bool:
        """Add a new sheet to existing spreadsheet."""
        if not self.service:
            self.logger.error("google_sheets_not_authenticated")
            return False
            
        try:
            body = {
                'requests': [{
                    'addSheet': {
                        'properties': {
                            'title': sheet_name,
                            'gridProperties': {
                                'rowCount': rows,
                                'columnCount': cols
                            }
                        }
                    }
                }]
            }
            
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body=body
            ).execute()
            
            self.logger.info("sheet_added", 
                           spreadsheet_id=spreadsheet_id, sheet_name=sheet_name)
            return True
            
        except HttpError as e:
            self.logger.error("sheet_addition_failed", 
                            spreadsheet_id=spreadsheet_id, error=str(e))
            return False
    
    async def format_cells(self, spreadsheet_id: str, sheet_name: str, 
                          start_row: int, end_row: int, start_col: int, end_col: int,
                          format_dict: Dict[str, Any]) -> bool:
        """Apply formatting to specified cell range."""
        if not self.service:
            self.logger.error("google_sheets_not_authenticated")
            return False
            
        try:
            # Get sheet ID
            sheet_metadata = self.service.spreadsheets().get(
                spreadsheetId=spreadsheet_id
            ).execute()
            
            sheet_id = None
            for sheet in sheet_metadata.get('sheets', []):
                if sheet.get('properties', {}).get('title') == sheet_name:
                    sheet_id = sheet.get('properties', {}).get('sheetId')
                    break
            
            if sheet_id is None:
                self.logger.error("sheet_not_found", sheet_name=sheet_name)
                return False
            
            body = {
                'requests': [{
                    'repeatCell': {
                        'range': {
                            'sheetId': sheet_id,
                            'startRowIndex': start_row - 1,
                            'endRowIndex': end_row,
                            'startColumnIndex': start_col - 1,
                            'endColumnIndex': end_col
                        },
                        'cell': {
                            'userEnteredFormat': format_dict
                        },
                        'fields': 'userEnteredFormat'
                    }
                }]
            }
            
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body=body
            ).execute()
            
            self.logger.info("cells_formatted", 
                           spreadsheet_id=spreadsheet_id, sheet_name=sheet_name)
            return True
            
        except HttpError as e:
            self.logger.error("cell_formatting_failed", 
                            spreadsheet_id=spreadsheet_id, error=str(e))
            return False


class ResearchReportGenerator:
    """Generates research reports in Google Sheets format."""
    
    def __init__(self, sheets_client: GoogleSheetsClient):
        self.sheets_client = sheets_client
        self.logger = logger.bind(component="report_generator")
        
        # Report formatting styles
        self.header_format = {
            'backgroundColor': {'red': 0.2, 'green': 0.4, 'blue': 0.6},
            'textFormat': {
                'foregroundColor': {'red': 1.0, 'green': 1.0, 'blue': 1.0},
                'bold': True,
                'fontSize': 12
            }
        }
        
        self.title_format = {
            'textFormat': {
                'bold': True,
                'fontSize': 14
            }
        }
        
        self.positive_format = {
            'backgroundColor': {'red': 0.85, 'green': 0.95, 'blue': 0.85},
            'textFormat': {
                'foregroundColor': {'red': 0.0, 'green': 0.6, 'blue': 0.0}
            }
        }
        
        self.negative_format = {
            'backgroundColor': {'red': 0.95, 'green': 0.85, 'blue': 0.85},
            'textFormat': {
                'foregroundColor': {'red': 0.8, 'green': 0.0, 'blue': 0.0}
            }
        }
        
    async def generate_research_report(self, research_data: Dict[str, Any], 
                                     project_name: str) -> Optional[str]:
        """Generate a complete research report in Google Sheets."""
        
        try:
            # Create spreadsheet
            title = f"Research Report - {project_name} - {datetime.now().strftime('%Y-%m-%d')}"
            spreadsheet_id = await self.sheets_client.create_spreadsheet(title)
            
            if not spreadsheet_id:
                return None
            
            # Generate different sections
            await self._create_executive_summary_sheet(spreadsheet_id, research_data)
            await self._create_company_analysis_sheet(spreadsheet_id, research_data)
            await self._create_risk_analysis_sheet(spreadsheet_id, research_data)
            await self._create_recommendations_sheet(spreadsheet_id, research_data)
            
            # Create shareable URL
            url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
            
            self.logger.info("research_report_generated", 
                           spreadsheet_id=spreadsheet_id, url=url)
            
            return url
            
        except Exception as e:
            self.logger.error("research_report_generation_failed", error=str(e))
            return None
    
    async def _create_executive_summary_sheet(self, spreadsheet_id: str, 
                                            research_data: Dict[str, Any]) -> bool:
        """Create executive summary sheet."""
        
        # Prepare summary data
        summary_data = [
            ["EXECUTIVE SUMMARY", "", "", ""],
            ["", "", "", ""],
            ["Investment Thesis:", research_data.get('investment_thesis', 'Not provided')],
            ["Analysis Date:", datetime.now().strftime('%Y-%m-%d')],
            ["Companies Analyzed:", str(len(research_data.get('companies', [])))],
            ["", "", "", ""],
            ["KEY FINDINGS", "", "", ""],
        ]
        
        # Add sentiment summary
        sentiment_data = research_data.get('sentiment_analysis', {})
        market_sentiment = sentiment_data.get('market_sentiment', {})
        
        if market_sentiment:
            sentiment_score = market_sentiment.get('market_sentiment_score', 0)
            sentiment_regime = market_sentiment.get('sentiment_regime', 'unknown')
            
            summary_data.extend([
                ["Market Sentiment:", f"{sentiment_score:.2f} ({sentiment_regime})"],
                ["Sentiment Confidence:", f"{sentiment_data.get('confidence', 0):.1%}"]
            ])
        
        # Add risk summary
        risk_data = research_data.get('risk_analysis', {})
        portfolio_risks = risk_data.get('portfolio_risks', {})
        
        if portfolio_risks:
            risk_score = portfolio_risks.get('portfolio_risk_score', 0)
            risk_regime = "High" if risk_score > 0.7 else "Medium" if risk_score > 0.4 else "Low"
            
            summary_data.extend([
                ["Portfolio Risk:", f"{risk_score:.2f} ({risk_regime})"],
                ["Risk Trend:", risk_data.get('risk_trend', 'Unknown')]
            ])
        
        # Add company performance summary
        summary_data.extend([
            ["", "", "", ""],
            ["COMPANY PERFORMANCE SUMMARY", "", "", ""],
            ["Company", "Risk Score", "Sentiment", "Recommendation"]
        ])
        
        companies = research_data.get('companies', [])
        for i, company in enumerate(companies[:10]):  # Limit to top 10
            symbol = company.get('symbol', 'Unknown')
            
            # Get company-specific data
            company_risk = self._get_company_metric(research_data, 'risk_analysis', symbol, 'overall_risk_score', 0.5)
            company_sentiment = self._get_company_metric(research_data, 'sentiment_analysis', symbol, 'sentiment_score', 0.0)
            
            # Simple recommendation logic
            if company_risk < 0.4 and company_sentiment > 0.2:
                recommendation = "BUY"
            elif company_risk > 0.7 or company_sentiment < -0.2:
                recommendation = "SELL"
            else:
                recommendation = "HOLD"
            
            summary_data.append([
                symbol,
                f"{company_risk:.2f}",
                f"{company_sentiment:.2f}",
                recommendation
            ])
        
        # Update sheet
        success = await self.sheets_client.update_sheet_data(
            spreadsheet_id, "Sheet1", summary_data
        )
        
        if success:
            # Apply formatting
            await self.sheets_client.format_cells(
                spreadsheet_id, "Sheet1", 1, 1, 1, 4, self.title_format
            )
            await self.sheets_client.format_cells(
                spreadsheet_id, "Sheet1", 7, 7, 1, 4, self.header_format
            )
            await self.sheets_client.format_cells(
                spreadsheet_id, "Sheet1", len(summary_data) - len(companies) + 1, 
                len(summary_data) - len(companies) + 1, 1, 4, self.header_format
            )
        
        return success
    
    async def _create_company_analysis_sheet(self, spreadsheet_id: str, 
                                          research_data: Dict[str, Any]) -> bool:
        """Create detailed company analysis sheet."""
        
        sheet_name = "Company Analysis"
        
        # Add the sheet
        success = await self.sheets_client.add_sheet(spreadsheet_id, sheet_name)
        if not success:
            return False
        
        # Prepare company analysis data
        analysis_data = [
            ["DETAILED COMPANY ANALYSIS", "", "", "", "", "", ""],
            ["", "", "", "", "", "", ""],
            ["Company", "Sector", "Risk Score", "Sentiment", "Supply Chain Risk", 
             "Key Strengths", "Key Risks"]
        ]
        
        companies = research_data.get('companies', [])
        
        for company in companies:
            symbol = company.get('symbol', 'Unknown')
            name = company.get('name', symbol)
            sector = company.get('sector', 'Unknown')
            
            # Get analysis data for this company
            risk_score = self._get_company_metric(research_data, 'risk_analysis', symbol, 'overall_risk_score', 0.5)
            sentiment_score = self._get_company_metric(research_data, 'sentiment_analysis', symbol, 'sentiment_score', 0.0)
            supply_risk = self._get_company_metric(research_data, 'supply_chain_analysis', symbol, 'risk_score', 0.5)
            
            # Get key insights
            strengths = self._get_company_insights(research_data, symbol, 'strengths')
            risks = self._get_company_insights(research_data, symbol, 'risks')
            
            analysis_data.append([
                f"{name} ({symbol})",
                sector,
                f"{risk_score:.2f}",
                f"{sentiment_score:.2f}",
                f"{supply_risk:.2f}",
                strengths,
                risks
            ])
        
        # Update sheet
        success = await self.sheets_client.update_sheet_data(
            spreadsheet_id, sheet_name, analysis_data
        )
        
        if success:
            # Apply formatting
            await self.sheets_client.format_cells(
                spreadsheet_id, sheet_name, 1, 1, 1, 7, self.title_format
            )
            await self.sheets_client.format_cells(
                spreadsheet_id, sheet_name, 3, 3, 1, 7, self.header_format
            )
        
        return success
    
    async def _create_risk_analysis_sheet(self, spreadsheet_id: str, 
                                        research_data: Dict[str, Any]) -> bool:
        """Create risk analysis sheet."""
        
        sheet_name = "Risk Analysis"
        
        # Add the sheet
        success = await self.sheets_client.add_sheet(spreadsheet_id, sheet_name)
        if not success:
            return False
        
        risk_data = research_data.get('risk_analysis', {})
        
        # Prepare risk analysis data
        risk_analysis_data = [
            ["PORTFOLIO RISK ANALYSIS", "", "", ""],
            ["", "", "", ""],
            ["Overall Portfolio Risk:", f"{risk_data.get('portfolio_risks', {}).get('portfolio_risk_score', 0):.2f}"],
            ["Risk Concentration:", f"{risk_data.get('portfolio_risks', {}).get('risk_concentration', 0):.2f}"],
            ["", "", "", ""],
            ["COMPANY RISK BREAKDOWN", "", "", ""],
            ["Company", "Overall Risk", "Key Risk Themes", "Stress Test Score"]
        ]
        
        # Add company risk details
        company_analyses = risk_data.get('company_risk_analyses', [])
        for analysis in company_analyses:
            symbol = analysis.get('symbol', 'Unknown')
            risk_score = analysis.get('overall_risk_score', 0.5)
            risk_themes = ', '.join(analysis.get('risk_assessment', {}).get('key_risk_themes', [])[:3])
            stress_score = analysis.get('stress_test_results', {}).get('overall_stress_test_score', 0.5)
            
            risk_analysis_data.append([
                symbol,
                f"{risk_score:.2f}",
                risk_themes,
                f"{stress_score:.2f}"
            ])
        
        # Add portfolio vulnerabilities
        vulnerabilities = risk_data.get('portfolio_risks', {}).get('portfolio_vulnerabilities', [])
        if vulnerabilities:
            risk_analysis_data.extend([
                ["", "", "", ""],
                ["PORTFOLIO VULNERABILITIES", "", "", ""],
                ["Type", "Severity", "Description", "Mitigation"]
            ])
            
            for vuln in vulnerabilities[:5]:  # Top 5
                risk_analysis_data.append([
                    vuln.get('type', 'Unknown'),
                    vuln.get('severity', 'Medium'),
                    vuln.get('description', 'No description'),
                    vuln.get('mitigation', 'No mitigation specified')
                ])
        
        # Update sheet
        success = await self.sheets_client.update_sheet_data(
            spreadsheet_id, sheet_name, risk_analysis_data
        )
        
        if success:
            # Apply formatting
            await self.sheets_client.format_cells(
                spreadsheet_id, sheet_name, 1, 1, 1, 4, self.title_format
            )
            await self.sheets_client.format_cells(
                spreadsheet_id, sheet_name, 6, 6, 1, 4, self.header_format
            )
            
            if vulnerabilities:
                vuln_row = len(risk_analysis_data) - len(vulnerabilities) - 1
                await self.sheets_client.format_cells(
                    spreadsheet_id, sheet_name, vuln_row, vuln_row, 1, 4, self.header_format
                )
        
        return success
    
    async def _create_recommendations_sheet(self, spreadsheet_id: str, 
                                         research_data: Dict[str, Any]) -> bool:
        """Create recommendations sheet."""
        
        sheet_name = "Recommendations"
        
        # Add the sheet
        success = await self.sheets_client.add_sheet(spreadsheet_id, sheet_name)
        if not success:
            return False
        
        # Prepare recommendations data
        recommendations_data = [
            ["INVESTMENT RECOMMENDATIONS", "", "", ""],
            ["", "", "", ""],
            ["HIGH PRIORITY ACTIONS", "", "", ""],
            ["Action", "Company", "Reason", "Timeline"]
        ]
        
        # Add risk-based recommendations
        risk_recommendations = research_data.get('risk_analysis', {}).get('risk_recommendations', {})
        high_priority = risk_recommendations.get('high_priority', [])
        
        for rec in high_priority:
            recommendations_data.append([
                rec.get('action', 'Unknown action'),
                rec.get('symbol', 'Portfolio'),
                rec.get('reason', 'No reason specified'),
                'Immediate'
            ])
        
        # Add sentiment-based signals
        sentiment_signals = research_data.get('sentiment_analysis', {}).get('sentiment_signals', {})
        
        if sentiment_signals.get('buy_signals'):
            recommendations_data.extend([
                ["", "", "", ""],
                ["BUY SIGNALS", "", "", ""],
                ["Company", "Signal Strength", "Reason", "Confidence"]
            ])
            
            for signal in sentiment_signals['buy_signals']:
                recommendations_data.append([
                    signal.get('symbol', 'Unknown'),
                    f"{signal.get('sentiment_score', 0):.2f}",
                    signal.get('reason', 'Positive sentiment'),
                    f"{signal.get('confidence', 0):.1%}"
                ])
        
        if sentiment_signals.get('sell_signals'):
            recommendations_data.extend([
                ["", "", "", ""],
                ["SELL SIGNALS", "", "", ""],
                ["Company", "Signal Strength", "Reason", "Confidence"]
            ])
            
            for signal in sentiment_signals['sell_signals']:
                recommendations_data.append([
                    signal.get('symbol', 'Unknown'),
                    f"{signal.get('sentiment_score', 0):.2f}",
                    signal.get('reason', 'Negative sentiment'),
                    f"{signal.get('confidence', 0):.1%}"
                ])
        
        # Add monitoring recommendations
        recommendations_data.extend([
            ["", "", "", ""],
            ["MONITORING POINTS", "", "", ""],
            ["Area", "Frequency", "Key Metrics", "Threshold"]
        ])
        
        # Default monitoring recommendations
        monitoring_points = [
            ["Market Sentiment", "Weekly", "News sentiment, social indicators", "Score < -0.3"],
            ["Risk Levels", "Monthly", "Company risk scores, stress tests", "Score > 0.7"],
            ["Supply Chain", "Bi-weekly", "Supplier issues, logistics", "Major disruptions"]
        ]
        
        recommendations_data.extend(monitoring_points)
        
        # Update sheet
        success = await self.sheets_client.update_sheet_data(
            spreadsheet_id, sheet_name, recommendations_data
        )
        
        if success:
            # Apply formatting
            await self.sheets_client.format_cells(
                spreadsheet_id, sheet_name, 1, 1, 1, 4, self.title_format
            )
            await self.sheets_client.format_cells(
                spreadsheet_id, sheet_name, 3, 3, 1, 4, self.header_format
            )
        
        return success
    
    def _get_company_metric(self, research_data: Dict, analysis_type: str, 
                           symbol: str, metric: str, default: float) -> float:
        """Extract specific metric for a company from research data."""
        
        analysis_data = research_data.get(analysis_type, {})
        
        if analysis_type == 'risk_analysis':
            company_analyses = analysis_data.get('company_risk_analyses', [])
            for analysis in company_analyses:
                if analysis.get('symbol') == symbol:
                    return analysis.get(metric, default)
        
        elif analysis_type == 'sentiment_analysis':
            company_analyses = analysis_data.get('company_analyses', [])
            for analysis in company_analyses:
                if analysis.get('symbol') == symbol:
                    return analysis.get(metric, default)
        
        elif analysis_type == 'supply_chain_analysis':
            company_analyses = analysis_data.get('company_analyses', [])
            for analysis in company_analyses:
                if analysis.get('symbol') == symbol:
                    return analysis.get(metric, default)
        
        return default
    
    def _get_company_insights(self, research_data: Dict, symbol: str, 
                            insight_type: str) -> str:
        """Extract key insights for a company."""
        
        insights = []
        
        # Get insights from different analyses
        if insight_type == 'strengths':
            # Look for positive indicators
            sentiment_data = research_data.get('sentiment_analysis', {})
            company_analyses = sentiment_data.get('company_analyses', [])
            
            for analysis in company_analyses:
                if analysis.get('symbol') == symbol:
                    themes = analysis.get('news_sentiment', {}).get('key_themes', [])
                    positive_themes = [theme for theme in themes if 
                                     any(word in theme.lower() for word in 
                                         ['growth', 'strong', 'positive', 'success', 'innovation'])]
                    insights.extend(positive_themes[:2])
        
        else:  # risks
            # Look for risk indicators
            risk_data = research_data.get('risk_analysis', {})
            company_analyses = risk_data.get('company_risk_analyses', [])
            
            for analysis in company_analyses:
                if analysis.get('symbol') == symbol:
                    risk_themes = analysis.get('risk_assessment', {}).get('key_risk_themes', [])
                    insights.extend(risk_themes[:2])
        
        return ', '.join(insights[:3]) if insights else 'None identified'


class GoogleSheetsOutputManager:
    """Main manager for Google Sheets output operations."""
    
    def __init__(self):
        self.sheets_client = GoogleSheetsClient()
        self.report_generator = ResearchReportGenerator(self.sheets_client)
        self.logger = logger.bind(component="sheets_output_manager")
        
    async def initialize(self) -> bool:
        """Initialize Google Sheets client and authentication."""
        return await self.sheets_client.authenticate()
    
    async def create_research_report(self, research_results: Dict[str, Any], 
                                   project_name: str) -> Optional[str]:
        """Create a comprehensive research report in Google Sheets."""
        
        if not await self.initialize():
            self.logger.error("failed_to_initialize_google_sheets")
            return None
        
        return await self.report_generator.generate_research_report(
            research_results, project_name
        )
    
    async def create_quick_summary(self, research_results: Dict[str, Any], 
                                 project_name: str) -> Optional[str]:
        """Create a quick summary sheet for research results."""
        
        if not await self.initialize():
            self.logger.error("failed_to_initialize_google_sheets")
            return None
        
        try:
            # Create simple spreadsheet
            title = f"Quick Summary - {project_name} - {datetime.now().strftime('%Y-%m-%d')}"
            spreadsheet_id = await self.sheets_client.create_spreadsheet(title)
            
            if not spreadsheet_id:
                return None
            
            # Create summary data
            summary_data = [
                [f"Research Summary - {project_name}"],
                [""],
                ["Investment Thesis:", research_results.get('investment_thesis', 'Not provided')],
                ["Analysis Date:", datetime.now().strftime('%Y-%m-%d %H:%M')],
                ["Companies Analyzed:", str(len(research_results.get('companies', [])))],
                [""],
                ["Company", "Risk", "Sentiment", "Recommendation"]
            ]
            
            # Add company summaries
            companies = research_results.get('companies', [])
            for company in companies:
                symbol = company.get('symbol', 'Unknown')
                
                # Simple metrics extraction
                risk_score = 0.5  # Default
                sentiment_score = 0.0  # Default
                
                # Determine recommendation
                if risk_score < 0.4 and sentiment_score > 0.2:
                    recommendation = "BUY"
                elif risk_score > 0.7 or sentiment_score < -0.2:
                    recommendation = "SELL"
                else:
                    recommendation = "HOLD"
                
                summary_data.append([
                    symbol,
                    f"{risk_score:.2f}",
                    f"{sentiment_score:.2f}",
                    recommendation
                ])
            
            # Update sheet
            success = await self.sheets_client.update_sheet_data(
                spreadsheet_id, "Sheet1", summary_data
            )
            
            if success:
                url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
                self.logger.info("quick_summary_created", spreadsheet_id=spreadsheet_id, url=url)
                return url
            
            return None
            
        except Exception as e:
            self.logger.error("quick_summary_creation_failed", error=str(e))
            return None