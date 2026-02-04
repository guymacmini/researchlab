"""Company profiles sheet for institutional research workbook."""

from typing import Dict, Any, List
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter


class CompanyProfilesSheet:
    """Creates detailed company profiles sheet."""
    
    def __init__(self, workbook: Workbook):
        self.workbook = workbook
        self.ws = workbook.create_sheet("Company Profiles")
    
    def create_sheet(self, company_data: Dict[str, Dict[str, Any]], companies: List[Dict[str, str]]):
        """Create company profiles sheet with detailed information."""
        
        # Sheet title
        self.ws['A1'] = "COMPANY PROFILES"
        self.ws['A1'].style = 'header_style'
        self.ws.merge_cells('A1:H1')
        
        current_row = 3
        
        # Create profile for each company
        for company in companies:
            ticker = company.get('ticker', '')
            data = company_data.get(ticker, {})
            
            current_row = self._create_company_profile(company, data, current_row)
            current_row += 3  # Space between companies
        
        self._adjust_column_widths()
    
    def _create_company_profile(self, company_info: Dict[str, str], data: Dict[str, Any], start_row: int) -> int:
        """Create individual company profile."""
        current_row = start_row
        ticker = company_info.get('ticker', '')
        company_name = company_info.get('name', 'Unknown Company')
        
        # Company header
        self.ws[f'A{current_row}'] = f"{company_name} ({ticker})"
        self.ws[f'A{current_row}'].style = 'subheader_style'
        self.ws.merge_cells(f'A{current_row}:H{current_row}')
        current_row += 1
        
        # Business overview
        current_row = self._add_business_overview(data, current_row)
        current_row += 1
        
        # Key metrics summary
        current_row = self._add_key_metrics_summary(data, current_row)
        current_row += 1
        
        # Investment highlights
        current_row = self._add_investment_highlights(company_info, current_row)
        
        return current_row
    
    def _add_business_overview(self, data: Dict[str, Any], start_row: int) -> int:
        """Add business overview section."""
        current_row = start_row
        
        # Section header
        self.ws[f'A{current_row}'] = "Business Overview"
        self.ws[f'A{current_row}'].font = Font(bold=True, size=11)
        current_row += 1
        
        # Extract business information
        business_info = self._extract_business_info(data)
        
        # Add business details in a structured format
        info_items = [
            ('Sector:', business_info.get('sector', 'N/A')),
            ('Industry:', business_info.get('industry', 'N/A')),
            ('Country:', business_info.get('country', 'N/A')),
            ('Exchange:', business_info.get('exchange', 'N/A')),
            ('Employees:', business_info.get('employees', 'N/A')),
            ('Founded:', business_info.get('founded', 'N/A')),
            ('Market Cap:', business_info.get('market_cap', 'N/A')),
            ('Website:', business_info.get('website', 'N/A'))
        ]
        
        for label, value in info_items:
            self.ws[f'A{current_row}'] = label
            self.ws[f'A{current_row}'].font = Font(bold=True, size=10)
            self.ws[f'B{current_row}'] = value
            self.ws[f'B{current_row}'].font = Font(size=10)
            current_row += 1
        
        # Business description
        description = business_info.get('description', 'No description available')
        if description and description != 'No description available':
            current_row += 1
            self.ws[f'A{current_row}'] = "Description:"
            self.ws[f'A{current_row}'].font = Font(bold=True, size=10)
            current_row += 1
            
            # Split long descriptions into manageable chunks
            desc_chunks = [description[i:i+100] for i in range(0, len(description), 100)][:3]
            for chunk in desc_chunks:
                self.ws[f'A{current_row}'] = chunk
                self.ws[f'A{current_row}'].font = Font(size=10)
                self.ws[f'A{current_row}'].alignment = Alignment(wrap_text=True)
                self.ws.merge_cells(f'A{current_row}:H{current_row}')
                self.ws.row_dimensions[current_row].height = 30
                current_row += 1
        
        return current_row
    
    def _add_key_metrics_summary(self, data: Dict[str, Any], start_row: int) -> int:
        """Add key financial metrics summary."""
        current_row = start_row
        
        # Section header
        self.ws[f'A{current_row}'] = "Key Financial Metrics"
        self.ws[f'A{current_row}'].font = Font(bold=True, size=11)
        current_row += 1
        
        # Extract key metrics
        metrics = self._extract_key_metrics(data)
        
        # Create metrics table
        metric_headers = ['Metric', 'Value', 'Metric', 'Value']
        for col, header in enumerate(metric_headers, 1):
            cell = self.ws.cell(row=current_row, column=col, value=header)
            cell.style = 'subheader_style'
        current_row += 1
        
        # Organize metrics into pairs for better layout
        metric_pairs = [
            (('Revenue (TTM)', metrics.get('revenue', 'N/A')), 
             ('Market Cap', metrics.get('market_cap', 'N/A'))),
            (('Net Income (TTM)', metrics.get('net_income', 'N/A')), 
             ('P/E Ratio', metrics.get('pe_ratio', 'N/A'))),
            (('Operating Margin', metrics.get('operating_margin', 'N/A')), 
             ('P/B Ratio', metrics.get('pb_ratio', 'N/A'))),
            (('ROE', metrics.get('roe', 'N/A')), 
             ('Dividend Yield', metrics.get('dividend_yield', 'N/A'))),
            (('Debt/Equity', metrics.get('debt_equity', 'N/A')), 
             ('Beta', metrics.get('beta', 'N/A'))),
            (('Free Cash Flow', metrics.get('free_cash_flow', 'N/A')), 
             ('52W High/Low', metrics.get('week_52_range', 'N/A')))
        ]
        
        for (metric1, value1), (metric2, value2) in metric_pairs:
            self.ws[f'A{current_row}'] = metric1
            self.ws[f'B{current_row}'] = value1
            self.ws[f'C{current_row}'] = metric2
            self.ws[f'D{current_row}'] = value2
            
            # Style the cells
            for col in range(1, 5):
                cell = self.ws.cell(row=current_row, column=col)
                cell.style = 'data_style'
                if col in [2, 4]:  # Value columns
                    cell.number_format = '#,##0.00'
            
            current_row += 1
        
        return current_row
    
    def _add_investment_highlights(self, company_info: Dict[str, str], start_row: int) -> int:
        """Add investment highlights section."""
        current_row = start_row
        
        # Section header
        self.ws[f'A{current_row}'] = "Investment Rationale"
        self.ws[f'A{current_row}'].font = Font(bold=True, size=11)
        current_row += 1
        
        # Get rationale from company info
        rationale = company_info.get('rationale', 'Investment rationale not provided')
        
        self.ws[f'A{current_row}'] = rationale
        self.ws[f'A{current_row}'].font = Font(size=10)
        self.ws[f'A{current_row}'].alignment = Alignment(wrap_text=True, vertical='top')
        self.ws.merge_cells(f'A{current_row}:H{current_row}')
        self.ws.row_dimensions[current_row].height = 40
        current_row += 1
        
        # Add generic investment considerations
        current_row += 1
        self.ws[f'A{current_row}'] = "Key Investment Considerations:"
        self.ws[f'A{current_row}'].font = Font(bold=True, size=10)
        current_row += 1
        
        considerations = [
            "• Evaluate company's competitive position in the sector",
            "• Monitor key financial metrics and debt levels",
            "• Consider macroeconomic factors affecting the industry",
            "• Review management team track record and strategy",
            "• Assess dividend sustainability and capital allocation"
        ]
        
        for consideration in considerations:
            self.ws[f'A{current_row}'] = consideration
            self.ws[f'A{current_row}'].font = Font(size=10)
            self.ws.merge_cells(f'A{current_row}:H{current_row}')
            current_row += 1
        
        return current_row
    
    def _extract_business_info(self, data: Dict[str, Any]) -> Dict[str, str]:
        """Extract business information from company data."""
        business_info = {}
        
        # Try different data sources
        sources = [
            data.get('financial_data', {}),
            data.get('info', {}),
            data
        ]
        
        for source in sources:
            if not source:
                continue
            
            # Check profile data first (Financial Modeling Prep)
            if 'profile' in source and isinstance(source['profile'], dict):
                profile = source['profile']
                business_info.update({
                    'sector': profile.get('sector', business_info.get('sector')),
                    'industry': profile.get('industry', business_info.get('industry')),
                    'country': profile.get('country', business_info.get('country')),
                    'exchange': profile.get('exchange', profile.get('exchangeShortName', business_info.get('exchange'))),
                    'employees': self._format_number(profile.get('fullTimeEmployees')),
                    'founded': profile.get('ipoDate', business_info.get('founded')),
                    'market_cap': self._format_market_cap(profile.get('mktCap')),
                    'website': profile.get('website', business_info.get('website')),
                    'description': profile.get('description', business_info.get('description'))
                })
            
            # Check Alpha Vantage overview data
            if 'overview' in source and isinstance(source['overview'], dict):
                overview = source['overview']
                business_info.update({
                    'sector': overview.get('Sector', business_info.get('sector')),
                    'industry': overview.get('Industry', business_info.get('industry')),
                    'country': overview.get('Country', business_info.get('country')),
                    'exchange': overview.get('Exchange', business_info.get('exchange')),
                    'market_cap': self._format_market_cap(overview.get('MarketCapitalization')),
                    'description': overview.get('Description', business_info.get('description'))
                })
            
            # Check direct fields
            for field, keys in {
                'sector': ['sector', 'Sector', 'finnhubIndustry'],
                'industry': ['industry', 'Industry'],
                'country': ['country', 'Country'],
                'exchange': ['exchange', 'Exchange', 'exchangeShortName']
            }.items():
                if business_info.get(field):
                    continue
                for key in keys:
                    value = source.get(key)
                    if value:
                        business_info[field] = str(value)
                        break
        
        return business_info
    
    def _extract_key_metrics(self, data: Dict[str, Any]) -> Dict[str, str]:
        """Extract key financial metrics."""
        metrics = {}
        
        sources = [
            data.get('financial_data', {}),
            data.get('info', {}),
            data
        ]
        
        for source in sources:
            if not source:
                continue
            
            # Revenue
            for key in ['revenue', 'revenueTTM', 'RevenueTTM']:
                value = source.get(key)
                if value and not metrics.get('revenue'):
                    metrics['revenue'] = self._format_currency(value)
            
            # Net Income
            for key in ['netIncome', 'netIncomeTTM']:
                value = source.get(key)
                if value and not metrics.get('net_income'):
                    metrics['net_income'] = self._format_currency(value)
            
            # Market Cap
            for key in ['marketCapitalization', 'MarketCapitalization', 'mktCap']:
                value = source.get(key)
                if value and not metrics.get('market_cap'):
                    metrics['market_cap'] = self._format_market_cap(value)
            
            # Ratios
            for metric, keys in {
                'pe_ratio': ['peRatio', 'PERatio', 'peBasicExclExtraTTM'],
                'pb_ratio': ['priceToBookRatio', 'PriceToBookRatio', 'pbQuarterly'],
                'roe': ['returnOnEquityTTM', 'ReturnOnEquityTTM', 'roeTTM'],
                'operating_margin': ['operatingMarginTTM', 'OperatingMarginTTM'],
                'dividend_yield': ['dividendYield', 'DividendYield'],
                'beta': ['beta', 'Beta'],
                'debt_equity': ['debtToEquity', 'DebtToEquityRatio']
            }.items():
                if metrics.get(metric):
                    continue
                for key in keys:
                    value = source.get(key)
                    if value:
                        metrics[metric] = self._format_ratio(value, metric)
                        break
            
            # 52-week range
            high = source.get('52WeekHigh') or source.get('week_52_high')
            low = source.get('52WeekLow') or source.get('week_52_low')
            if high and low and not metrics.get('week_52_range'):
                metrics['week_52_range'] = f"${float(low):.2f} - ${float(high):.2f}"
        
        return metrics
    
    def _format_number(self, value: Any) -> str:
        """Format numbers for display."""
        if not value:
            return 'N/A'
        try:
            return f"{int(float(value)):,}"
        except (ValueError, TypeError):
            return str(value)
    
    def _format_currency(self, value: Any) -> str:
        """Format currency values."""
        if not value:
            return 'N/A'
        try:
            val = float(value)
            if val >= 1_000_000_000:
                return f"${val/1_000_000_000:.1f}B"
            elif val >= 1_000_000:
                return f"${val/1_000_000:.1f}M"
            else:
                return f"${val:,.0f}"
        except (ValueError, TypeError):
            return str(value)
    
    def _format_market_cap(self, value: Any) -> str:
        """Format market cap values."""
        if not value:
            return 'N/A'
        try:
            val = float(value)
            # If value is already in millions (common for some APIs)
            if val < 100_000:  # Assume it's already in millions
                return f"${val:,.0f}M"
            else:  # Raw dollar amount
                if val >= 1_000_000_000:
                    return f"${val/1_000_000_000:.1f}B"
                else:
                    return f"${val/1_000_000:.0f}M"
        except (ValueError, TypeError):
            return str(value)
    
    def _format_ratio(self, value: Any, metric_type: str) -> str:
        """Format ratio values based on type."""
        if not value:
            return 'N/A'
        try:
            val = float(value)
            if metric_type in ['roe', 'operating_margin', 'dividend_yield']:
                # Convert to percentage if needed
                if val < 1:
                    val *= 100
                return f"{val:.1f}%"
            else:
                return f"{val:.2f}"
        except (ValueError, TypeError):
            return str(value)
    
    def _adjust_column_widths(self):
        """Auto-adjust column widths."""
        for column in self.ws.columns:
            max_length = 0
            column_letter = get_column_letter(column[0].column)
            
            for cell in column:
                try:
                    if cell.value and len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            
            adjusted_width = min(max_length + 3, 50)
            self.ws.column_dimensions[column_letter].width = max(adjusted_width, 12)