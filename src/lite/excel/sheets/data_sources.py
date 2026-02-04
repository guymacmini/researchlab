"""Data sources sheet for institutional research workbook."""

from typing import List, Optional
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter


class DataSourcesSheet:
    """Creates data sources and methodology sheet."""
    
    def __init__(self, workbook: Workbook):
        self.workbook = workbook
        self.ws = workbook.create_sheet("Data Sources")
    
    def create_sheet(self, data_sources: List[str], timestamp: Optional[str] = None):
        """Create data sources documentation sheet."""
        
        # Sheet title
        self.ws['A1'] = "DATA SOURCES & METHODOLOGY"
        self.ws['A1'].style = 'header_style'
        self.ws.merge_cells('A1:F1')
        
        # Report timestamp
        report_time = timestamp or datetime.utcnow().isoformat()
        self.ws['A2'] = f"Report Generated: {report_time}"
        self.ws['A2'].font = Font(size=10, italic=True)
        
        current_row = 4
        
        # Data sources section
        current_row = self._create_data_sources_section(data_sources, current_row)
        current_row += 3
        
        # Methodology section
        current_row = self._create_methodology_section(current_row)
        current_row += 3
        
        # Disclaimers section
        current_row = self._create_disclaimers_section(current_row)
        
        self._adjust_column_widths()
    
    def _create_data_sources_section(self, data_sources: List[str], start_row: int) -> int:
        """Create data sources documentation."""
        current_row = start_row
        
        # Section header
        self.ws[f'A{current_row}'] = "PRIMARY DATA SOURCES"
        self.ws[f'A{current_row}'].style = 'subheader_style'
        self.ws.merge_cells(f'A{current_row}:F{current_row}')
        current_row += 1
        
        # Table headers
        headers = ['Data Provider', 'Data Type', 'Coverage', 'Update Frequency', 'Reliability']
        for col, header in enumerate(headers, 1):
            cell = self.ws.cell(row=current_row, column=col, value=header)
            cell.style = 'subheader_style'
        current_row += 1
        
        # Define comprehensive data source information
        source_details = {
            'financial_modeling_prep': {
                'name': 'Financial Modeling Prep',
                'data_type': 'Financial Statements, Ratios, Valuation Metrics',
                'coverage': '25,000+ Public Companies',
                'frequency': 'Real-time to Daily',
                'reliability': 'High'
            },
            'alpha_vantage': {
                'name': 'Alpha Vantage',
                'data_type': 'Fundamental Data, Economic Indicators',
                'coverage': 'US & Global Markets',
                'frequency': 'Real-time to Daily',
                'reliability': 'High'
            },
            'sec_edgar': {
                'name': 'SEC EDGAR',
                'data_type': 'Official Filings (10-K, 10-Q, 8-K)',
                'coverage': 'US Public Companies',
                'frequency': 'Filing-based',
                'reliability': 'Highest'
            },
            'finnhub': {
                'name': 'Finnhub',
                'data_type': 'Market Data, News, Basic Financials',
                'coverage': 'Global Markets',
                'frequency': 'Real-time',
                'reliability': 'High'
            },
            'anthropic_claude': {
                'name': 'Anthropic Claude',
                'data_type': 'Analysis, Insights, Text Processing',
                'coverage': 'AI-Generated Analysis',
                'frequency': 'On-demand',
                'reliability': 'Model-dependent'
            }
        }
        
        # Add rows for each data source used
        sources_used = data_sources if data_sources else ['financial_modeling_prep', 'alpha_vantage', 'sec_edgar', 'finnhub', 'anthropic_claude']
        
        for source_key in sources_used:
            # Map source names to keys
            source_map = {
                'fmp': 'financial_modeling_prep',
                'alpha_vantage': 'alpha_vantage',
                'sec': 'sec_edgar',
                'finnhub': 'finnhub',
                'anthropic': 'anthropic_claude',
                'claude': 'anthropic_claude'
            }
            
            # Get the correct key
            lookup_key = source_map.get(source_key, source_key)
            details = source_details.get(lookup_key)
            
            if not details:
                continue
            
            row_data = [
                details['name'],
                details['data_type'],
                details['coverage'],
                details['frequency'],
                details['reliability']
            ]
            
            for col, value in enumerate(row_data, 1):
                cell = self.ws.cell(row=current_row, column=col, value=value)
                cell.style = 'data_style'
                
                # Color code reliability
                if col == 5:  # Reliability column
                    if value == 'Highest':
                        cell.fill = PatternFill(start_color='90EE90', end_color='90EE90', fill_type='solid')
                    elif value == 'High':
                        cell.fill = PatternFill(start_color='FFFFE0', end_color='FFFFE0', fill_type='solid')
                    else:
                        cell.fill = PatternFill(start_color='FFE4E1', end_color='FFE4E1', fill_type='solid')
            
            current_row += 1
        
        # Add data quality notes
        current_row += 1
        self.ws[f'A{current_row}'] = "Data Quality Notes:"
        self.ws[f'A{current_row}'].font = Font(bold=True, size=10)
        current_row += 1
        
        quality_notes = [
            "• All financial data is sourced from official company filings when available",
            "• Real-time market data may have up to 15-minute delays",
            "• Historical data accuracy verified against multiple sources",
            "• AI-generated analysis is based on factual data inputs",
            "• Currency conversions use prevailing exchange rates at report date"
        ]
        
        for note in quality_notes:
            self.ws[f'A{current_row}'] = note
            self.ws[f'A{current_row}'].font = Font(size=9)
            self.ws.merge_cells(f'A{current_row}:F{current_row}')
            current_row += 1
        
        return current_row
    
    def _create_methodology_section(self, start_row: int) -> int:
        """Create methodology documentation."""
        current_row = start_row
        
        # Section header
        self.ws[f'A{current_row}'] = "RESEARCH METHODOLOGY"
        self.ws[f'A{current_row}'].style = 'subheader_style'
        self.ws.merge_cells(f'A{current_row}:F{current_row}')
        current_row += 2
        
        # Methodology steps
        methodology_sections = [
            {
                'title': '1. DATA COLLECTION',
                'steps': [
                    'Extract financial statements from SEC filings and financial data providers',
                    'Gather real-time market data and trading metrics',
                    'Collect industry and economic context data',
                    'Cross-validate data points across multiple sources'
                ]
            },
            {
                'title': '2. FINANCIAL ANALYSIS',
                'steps': [
                    'Calculate key financial ratios and growth metrics',
                    'Perform historical trend analysis (3-5 years)',
                    'Compare metrics against industry peers',
                    'Assess financial health and debt capacity'
                ]
            },
            {
                'title': '3. VALUATION ANALYSIS',
                'steps': [
                    'Calculate trading multiples (P/E, P/B, EV/EBITDA, P/S)',
                    'Perform peer group comparison analysis',
                    'Apply relative valuation methodologies',
                    'Consider DCF analysis where appropriate'
                ]
            },
            {
                'title': '4. SCENARIO MODELING',
                'steps': [
                    'Develop Bull/Base/Bear case scenarios',
                    'Stress test financial metrics under different conditions',
                    'Model impact of key risk factors',
                    'Calculate risk-adjusted return expectations'
                ]
            },
            {
                'title': '5. SYNTHESIS & RECOMMENDATIONS',
                'steps': [
                    'Integrate quantitative and qualitative analysis',
                    'Generate investment recommendations with confidence levels',
                    'Identify key catalysts and risk factors',
                    'Provide actionable investment guidance'
                ]
            }
        ]
        
        for section in methodology_sections:
            # Section title
            self.ws[f'A{current_row}'] = section['title']
            self.ws[f'A{current_row}'].font = Font(bold=True, size=11)
            current_row += 1
            
            # Section steps
            for step in section['steps']:
                self.ws[f'A{current_row}'] = f"• {step}"
                self.ws[f'A{current_row}'].font = Font(size=10)
                self.ws[f'A{current_row}'].alignment = Alignment(wrap_text=True)
                self.ws.merge_cells(f'A{current_row}:F{current_row}')
                current_row += 1
            
            current_row += 1  # Space between sections
        
        return current_row
    
    def _create_disclaimers_section(self, start_row: int) -> int:
        """Create disclaimers and limitations section."""
        current_row = start_row
        
        # Section header
        self.ws[f'A{current_row}'] = "DISCLAIMERS & LIMITATIONS"
        self.ws[f'A{current_row}'].style = 'subheader_style'
        self.ws.merge_cells(f'A{current_row}:F{current_row}')
        current_row += 2
        
        disclaimers = [
            "INVESTMENT DISCLAIMER:",
            "This research report is for informational purposes only and does not constitute investment advice, "
            "a recommendation to buy or sell securities, or a solicitation of any kind. Past performance does not "
            "guarantee future results. All investments carry risk of loss.",
            "",
            "DATA LIMITATIONS:",
            "• Historical data may contain errors or revisions not reflected in real-time",
            "• Forward-looking statements are subject to uncertainty and may not materialize",
            "• AI-generated analysis is based on available data and may not capture all relevant factors",
            "• Market conditions can change rapidly, affecting the validity of analysis",
            "",
            "METHODOLOGY LIMITATIONS:",
            "• Peer comparisons may not account for all business model differences",
            "• Scenario analysis is based on assumptions that may prove incorrect",
            "• Valuation models are simplified and may not capture all value drivers",
            "• Analysis is point-in-time and may become outdated quickly",
            "",
            "PROFESSIONAL ADVICE:",
            "Investors should consult with qualified financial advisors before making investment decisions. "
            "This report should be used in conjunction with other research and analysis tools. "
            "Consider your risk tolerance, investment objectives, and time horizon before investing."
        ]
        
        for disclaimer in disclaimers:
            if disclaimer == "":
                current_row += 1
                continue
            
            if disclaimer.endswith(':'):
                # Header
                self.ws[f'A{current_row}'] = disclaimer
                self.ws[f'A{current_row}'].font = Font(bold=True, size=10)
            elif disclaimer.startswith('•'):
                # Bullet point
                self.ws[f'A{current_row}'] = disclaimer
                self.ws[f'A{current_row}'].font = Font(size=9)
            else:
                # Paragraph text
                self.ws[f'A{current_row}'] = disclaimer
                self.ws[f'A{current_row}'].font = Font(size=9)
                self.ws[f'A{current_row}'].alignment = Alignment(wrap_text=True)
                self.ws.row_dimensions[current_row].height = 40
            
            self.ws.merge_cells(f'A{current_row}:F{current_row}')
            current_row += 1
        
        # Footer
        current_row += 2
        footer_text = f"ResearchLab Institutional Research System | Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        self.ws[f'A{current_row}'] = footer_text
        self.ws[f'A{current_row}'].font = Font(size=8, italic=True, color='666666')
        self.ws.merge_cells(f'A{current_row}:F{current_row}')
        
        return current_row
    
    def _adjust_column_widths(self):
        """Auto-adjust column widths for readability."""
        # Set specific widths for better layout
        column_widths = {
            'A': 25,  # Data Provider / Main content
            'B': 35,  # Data Type
            'C': 20,  # Coverage
            'D': 15,  # Frequency
            'E': 12,  # Reliability
            'F': 15   # Extra space
        }
        
        for col_letter, width in column_widths.items():
            self.ws.column_dimensions[col_letter].width = width