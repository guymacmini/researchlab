"""Valuation comparables sheet for institutional research workbook."""

from typing import Dict, Any, List, Tuple
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule


class ValuationCompsSheet:
    """Creates valuation comparables sheet with trading multiples analysis."""
    
    def __init__(self, workbook: Workbook):
        self.workbook = workbook
        self.ws = workbook.create_sheet("Valuation Comps")
    
    def create_sheet(self, company_data: Dict[str, Dict[str, Any]], companies: List[Dict[str, str]]):
        """Create valuation comparables sheet."""
        
        # Sheet title
        self.ws['A1'] = "VALUATION COMPARABLES ANALYSIS"
        self.ws['A1'].style = 'header_style'
        self.ws.merge_cells('A1:L1')
        
        # Last updated
        self.ws['A2'] = f"As of: {datetime.utcnow().strftime('%Y-%m-%d')}"
        self.ws['A2'].font = Font(size=10, italic=True)
        
        current_row = 4
        
        # Trading multiples section
        current_row = self._create_trading_multiples_table(company_data, companies, current_row)
        current_row += 3
        
        # Financial metrics comparison
        current_row = self._create_financial_metrics_table(company_data, companies, current_row)
        current_row += 3
        
        # Valuation summary
        current_row = self._create_valuation_summary(company_data, companies, current_row)
        
        # Apply formatting
        self._apply_conditional_formatting()
        self._adjust_column_widths()
    
    def _create_trading_multiples_table(self, company_data: Dict[str, Dict[str, Any]], 
                                      companies: List[Dict[str, str]], start_row: int) -> int:
        """Create trading multiples comparison table."""
        current_row = start_row
        
        # Section header
        self.ws[f'A{current_row}'] = "TRADING MULTIPLES"
        self.ws[f'A{current_row}'].style = 'subheader_style'
        self.ws.merge_cells(f'A{current_row}:L{current_row}')
        current_row += 1
        
        # Table headers
        headers = [
            'Company', 'Ticker', 'Market Cap ($M)', 'Enterprise Value ($M)',
            'P/E Ratio', 'P/B Ratio', 'P/S Ratio', 'EV/Revenue', 
            'EV/EBITDA', 'Dividend Yield (%)', 'Beta'
        ]
        
        for col, header in enumerate(headers, 1):
            cell = self.ws.cell(row=current_row, column=col, value=header)
            cell.style = 'subheader_style'
        current_row += 1
        
        # Data rows for each company
        for company in companies:
            ticker = company.get('ticker', '')
            company_name = company.get('name', 'Unknown')
            data = company_data.get(ticker, {})
            
            # Extract valuation metrics
            metrics = self._extract_valuation_metrics(data)
            
            row_data = [
                company_name,
                ticker,
                metrics.get('market_cap', 'N/A'),
                metrics.get('enterprise_value', 'N/A'),
                metrics.get('pe_ratio', 'N/A'),
                metrics.get('pb_ratio', 'N/A'),
                metrics.get('ps_ratio', 'N/A'),
                metrics.get('ev_revenue', 'N/A'),
                metrics.get('ev_ebitda', 'N/A'),
                metrics.get('dividend_yield', 'N/A'),
                metrics.get('beta', 'N/A')
            ]
            
            for col, value in enumerate(row_data, 1):
                cell = self.ws.cell(row=current_row, column=col, value=value)
                
                # Apply appropriate styling
                if col <= 2:  # Company name and ticker
                    cell.style = 'data_style'
                elif col in [3, 4]:  # Market cap and EV
                    cell.style = 'currency_style'
                elif col == 10:  # Dividend yield
                    cell.style = 'percentage_style'
                else:  # Other ratios
                    cell.style = 'data_style'
                    if isinstance(value, (int, float)):
                        cell.number_format = '0.00'
            
            current_row += 1
        
        # Add sector averages if we have multiple companies
        if len(companies) > 1:
            current_row += 1
            self.ws[f'A{current_row}'] = "PEER GROUP AVERAGES"
            self.ws[f'A{current_row}'].style = 'subheader_style'
            self.ws.merge_cells(f'A{current_row}:B{current_row}')
            
            # Calculate averages
            averages = self._calculate_peer_averages(company_data, companies)
            
            avg_data = [
                '', '',  # Empty for company name and ticker
                averages.get('avg_market_cap', 'N/A'),
                averages.get('avg_enterprise_value', 'N/A'),
                averages.get('avg_pe_ratio', 'N/A'),
                averages.get('avg_pb_ratio', 'N/A'),
                averages.get('avg_ps_ratio', 'N/A'),
                averages.get('avg_ev_revenue', 'N/A'),
                averages.get('avg_ev_ebitda', 'N/A'),
                averages.get('avg_dividend_yield', 'N/A'),
                averages.get('avg_beta', 'N/A')
            ]
            
            for col, value in enumerate(avg_data, 1):
                if col > 2 and value != 'N/A':  # Skip empty cells
                    cell = self.ws.cell(row=current_row, column=col, value=value)
                    cell.style = 'subheader_style'
                    if isinstance(value, (int, float)):
                        if col in [3, 4]:  # Market cap and EV
                            cell.number_format = '$#,##0.0,,"M"'
                        elif col == 10:  # Dividend yield
                            cell.number_format = '0.0%'
                        else:
                            cell.number_format = '0.00'
            
            current_row += 1
        
        return current_row
    
    def _create_financial_metrics_table(self, company_data: Dict[str, Dict[str, Any]], 
                                       companies: List[Dict[str, str]], start_row: int) -> int:
        """Create financial metrics comparison table."""
        current_row = start_row
        
        # Section header
        self.ws[f'A{current_row}'] = "FINANCIAL METRICS COMPARISON"
        self.ws[f'A{current_row}'].style = 'subheader_style'
        self.ws.merge_cells(f'A{current_row}:J{current_row}')
        current_row += 1
        
        # Table headers
        headers = [
            'Company', 'Ticker', 'Revenue Growth (%)', 'Gross Margin (%)',
            'Operating Margin (%)', 'Net Margin (%)', 'ROE (%)', 'ROA (%)',
            'Debt/Equity', 'Current Ratio'
        ]
        
        for col, header in enumerate(headers, 1):
            cell = self.ws.cell(row=current_row, column=col, value=header)
            cell.style = 'subheader_style'
        current_row += 1
        
        # Data rows
        for company in companies:
            ticker = company.get('ticker', '')
            company_name = company.get('name', 'Unknown')
            data = company_data.get(ticker, {})
            
            # Extract financial metrics
            financial_metrics = self._extract_financial_metrics(data)
            
            row_data = [
                company_name,
                ticker,
                financial_metrics.get('revenue_growth', 'N/A'),
                financial_metrics.get('gross_margin', 'N/A'),
                financial_metrics.get('operating_margin', 'N/A'),
                financial_metrics.get('net_margin', 'N/A'),
                financial_metrics.get('roe', 'N/A'),
                financial_metrics.get('roa', 'N/A'),
                financial_metrics.get('debt_equity', 'N/A'),
                financial_metrics.get('current_ratio', 'N/A')
            ]
            
            for col, value in enumerate(row_data, 1):
                cell = self.ws.cell(row=current_row, column=col, value=value)
                
                if col <= 2:  # Company name and ticker
                    cell.style = 'data_style'
                elif col in [3, 4, 5, 6, 7, 8]:  # Percentage metrics
                    cell.style = 'percentage_style'
                else:  # Ratios
                    cell.style = 'data_style'
                    if isinstance(value, (int, float)):
                        cell.number_format = '0.00'
            
            current_row += 1
        
        return current_row
    
    def _create_valuation_summary(self, company_data: Dict[str, Dict[str, Any]], 
                                 companies: List[Dict[str, str]], start_row: int) -> int:
        """Create valuation summary with relative valuations."""
        current_row = start_row
        
        # Section header
        self.ws[f'A{current_row}'] = "VALUATION SUMMARY"
        self.ws[f'A{current_row}'].style = 'subheader_style'
        self.ws.merge_cells(f'A{current_row}:F{current_row}')
        current_row += 1
        
        # Summary headers
        headers = ['Company', 'Current Price', 'Relative P/E', 'Relative P/B', 'Relative EV/EBITDA', 'Valuation']
        
        for col, header in enumerate(headers, 1):
            cell = self.ws.cell(row=current_row, column=col, value=header)
            cell.style = 'subheader_style'
        current_row += 1
        
        # Calculate peer averages for relative valuation
        peer_averages = self._calculate_peer_averages(company_data, companies)
        
        # Data rows with relative valuations
        for company in companies:
            ticker = company.get('ticker', '')
            company_name = company.get('name', 'Unknown')
            data = company_data.get(ticker, {})
            
            # Get company metrics
            metrics = self._extract_valuation_metrics(data)
            current_price = self._get_current_price(data)
            
            # Calculate relative valuations
            relative_pe = self._calculate_relative_metric(
                metrics.get('pe_ratio'), peer_averages.get('avg_pe_ratio')
            )
            relative_pb = self._calculate_relative_metric(
                metrics.get('pb_ratio'), peer_averages.get('avg_pb_ratio')
            )
            relative_ev_ebitda = self._calculate_relative_metric(
                metrics.get('ev_ebitda'), peer_averages.get('avg_ev_ebitda')
            )
            
            # Determine overall valuation assessment
            valuation_assessment = self._assess_valuation(relative_pe, relative_pb, relative_ev_ebitda)
            
            row_data = [
                company_name,
                current_price,
                relative_pe,
                relative_pb,
                relative_ev_ebitda,
                valuation_assessment
            ]
            
            for col, value in enumerate(row_data, 1):
                cell = self.ws.cell(row=current_row, column=col, value=value)
                
                if col == 1:  # Company name
                    cell.style = 'data_style'
                elif col == 2:  # Current price
                    cell.style = 'currency_style'
                elif col in [3, 4, 5]:  # Relative ratios
                    cell.style = 'data_style'
                    if isinstance(value, (int, float)):
                        cell.number_format = '0.00x'
                else:  # Valuation assessment
                    cell.style = 'data_style'
                    # Color code the valuation
                    if value == 'Undervalued':
                        cell.fill = PatternFill(start_color='90EE90', end_color='90EE90', fill_type='solid')
                    elif value == 'Overvalued':
                        cell.fill = PatternFill(start_color='FFB6C1', end_color='FFB6C1', fill_type='solid')
                    else:  # Fair Value
                        cell.fill = PatternFill(start_color='FFFFE0', end_color='FFFFE0', fill_type='solid')
            
            current_row += 1
        
        return current_row
    
    def _extract_valuation_metrics(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract valuation metrics from company data."""
        metrics = {}
        
        # Try different data sources
        sources = [
            data.get('financial_data', {}),
            data.get('info', {}),
            data
        ]
        
        for source in sources:
            if not source:
                continue
            
            # Check different structures
            for key_prefix in ['', 'metrics.metric.', 'key_metrics.', 'overview.']:
                
                # Market cap
                for market_cap_key in ['marketCapitalization', 'marketCap', 'market_cap']:
                    value = self._safe_get_nested(source, f"{key_prefix}{market_cap_key}")
                    if value and metrics.get('market_cap') is None:
                        metrics['market_cap'] = self._format_large_number(value)
                
                # P/E ratio
                for pe_key in ['peRatio', 'pe_ratio', 'peBasicExclExtraTTM', 'peTTM']:
                    value = self._safe_get_nested(source, f"{key_prefix}{pe_key}")
                    if value and metrics.get('pe_ratio') is None:
                        metrics['pe_ratio'] = self._format_ratio(value)
                
                # P/B ratio
                for pb_key in ['priceToBookRatio', 'pb_ratio', 'pbQuarterly']:
                    value = self._safe_get_nested(source, f"{key_prefix}{pb_key}")
                    if value and metrics.get('pb_ratio') is None:
                        metrics['pb_ratio'] = self._format_ratio(value)
                
                # P/S ratio
                for ps_key in ['priceToSalesRatioTTM', 'ps_ratio', 'psAnnual']:
                    value = self._safe_get_nested(source, f"{key_prefix}{ps_key}")
                    if value and metrics.get('ps_ratio') is None:
                        metrics['ps_ratio'] = self._format_ratio(value)
                
                # EV/Revenue
                for ev_rev_key in ['evToRevenue', 'ev_revenue']:
                    value = self._safe_get_nested(source, f"{key_prefix}{ev_rev_key}")
                    if value and metrics.get('ev_revenue') is None:
                        metrics['ev_revenue'] = self._format_ratio(value)
                
                # EV/EBITDA
                for ev_ebitda_key in ['evToEBITDA', 'ev_ebitda']:
                    value = self._safe_get_nested(source, f"{key_prefix}{ev_ebitda_key}")
                    if value and metrics.get('ev_ebitda') is None:
                        metrics['ev_ebitda'] = self._format_ratio(value)
                
                # Dividend yield
                for div_key in ['dividendYield', 'dividend_yield']:
                    value = self._safe_get_nested(source, f"{key_prefix}{div_key}")
                    if value and metrics.get('dividend_yield') is None:
                        metrics['dividend_yield'] = self._format_percentage(value)
                
                # Beta
                for beta_key in ['beta']:
                    value = self._safe_get_nested(source, f"{key_prefix}{beta_key}")
                    if value and metrics.get('beta') is None:
                        metrics['beta'] = self._format_ratio(value)
        
        return metrics
    
    def _extract_financial_metrics(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract financial performance metrics."""
        metrics = {}
        
        # Similar extraction logic for financial metrics
        sources = [
            data.get('financial_data', {}),
            data.get('info', {}),
            data
        ]
        
        for source in sources:
            if not source:
                continue
            
            # Revenue growth
            for key in ['quarterlyRevenueGrowthYOY', 'revenue_growth', 'revenueGrowthTTMYoy']:
                value = self._safe_get_nested(source, key)
                if value and metrics.get('revenue_growth') is None:
                    metrics['revenue_growth'] = self._format_percentage(value)
            
            # Margins
            for margin_key, metric_name in [
                ('grossMargin', 'gross_margin'),
                ('operatingMarginTTM', 'operating_margin'),
                ('profitMargin', 'net_margin')
            ]:
                value = self._safe_get_nested(source, margin_key)
                if value and metrics.get(metric_name) is None:
                    metrics[metric_name] = self._format_percentage(value)
            
            # ROE and ROA
            for roe_key in ['returnOnEquityTTM', 'roe', 'roeTTM']:
                value = self._safe_get_nested(source, roe_key)
                if value and metrics.get('roe') is None:
                    metrics['roe'] = self._format_percentage(value)
            
            for roa_key in ['returnOnAssetsTTM', 'roa']:
                value = self._safe_get_nested(source, roa_key)
                if value and metrics.get('roa') is None:
                    metrics['roa'] = self._format_percentage(value)
            
            # Debt/Equity
            for de_key in ['debtToEquity', 'totalDebt/totalEquityQuarterly']:
                value = self._safe_get_nested(source, de_key)
                if value and metrics.get('debt_equity') is None:
                    metrics['debt_equity'] = self._format_ratio(value)
            
            # Current ratio
            for cr_key in ['currentRatio']:
                value = self._safe_get_nested(source, cr_key)
                if value and metrics.get('current_ratio') is None:
                    metrics['current_ratio'] = self._format_ratio(value)
        
        return metrics
    
    def _safe_get_nested(self, data: Dict[str, Any], key_path: str) -> Any:
        """Safely get nested dictionary value."""
        try:
            keys = key_path.split('.')
            value = data
            for key in keys:
                if key == '':
                    continue
                value = value[key]
            return value
        except (KeyError, TypeError, AttributeError):
            return None
    
    def _format_large_number(self, value: Any) -> float:
        """Format large numbers to millions."""
        try:
            num_value = float(value)
            return round(num_value / 1_000_000, 1)
        except (ValueError, TypeError):
            return 'N/A'
    
    def _format_ratio(self, value: Any) -> float:
        """Format ratio values."""
        try:
            return round(float(value), 2)
        except (ValueError, TypeError):
            return 'N/A'
    
    def _format_percentage(self, value: Any) -> float:
        """Format percentage values."""
        try:
            num_value = float(value)
            # If the value is already in percentage form (0-100)
            if num_value > 1:
                return round(num_value, 1)
            else:
                # Convert decimal to percentage
                return round(num_value * 100, 1)
        except (ValueError, TypeError):
            return 'N/A'
    
    def _get_current_price(self, data: Dict[str, Any]) -> str:
        """Extract current stock price."""
        try:
            # Try different sources for current price
            if 'financial_data' in data and 'quote' in data['financial_data']:
                price = data['financial_data']['quote'].get('c')
                if price:
                    return f"${float(price):.2f}"
            
            return "N/A"
        except (ValueError, TypeError, KeyError):
            return "N/A"
    
    def _calculate_peer_averages(self, company_data: Dict[str, Dict[str, Any]], 
                               companies: List[Dict[str, str]]) -> Dict[str, float]:
        """Calculate peer group averages."""
        averages = {}
        
        # Collect all values for averaging
        all_metrics = {}
        for company in companies:
            ticker = company.get('ticker', '')
            data = company_data.get(ticker, {})
            
            valuation_metrics = self._extract_valuation_metrics(data)
            
            for key, value in valuation_metrics.items():
                if value != 'N/A' and isinstance(value, (int, float)):
                    if key not in all_metrics:
                        all_metrics[key] = []
                    all_metrics[key].append(value)
        
        # Calculate averages
        for key, values in all_metrics.items():
            if values:
                averages[f"avg_{key}"] = round(sum(values) / len(values), 2)
        
        return averages
    
    def _calculate_relative_metric(self, company_value: Any, peer_average: Any) -> Any:
        """Calculate relative valuation metric."""
        try:
            if (company_value == 'N/A' or peer_average is None or 
                not isinstance(company_value, (int, float)) or 
                not isinstance(peer_average, (int, float)) or peer_average == 0):
                return 'N/A'
            
            return round(company_value / peer_average, 2)
        except (ValueError, TypeError, ZeroDivisionError):
            return 'N/A'
    
    def _assess_valuation(self, relative_pe: Any, relative_pb: Any, relative_ev_ebitda: Any) -> str:
        """Assess overall valuation based on relative metrics."""
        # Count how many metrics suggest undervaluation
        undervalued_count = 0
        overvalued_count = 0
        total_metrics = 0
        
        for metric in [relative_pe, relative_pb, relative_ev_ebitda]:
            if metric != 'N/A' and isinstance(metric, (int, float)):
                total_metrics += 1
                if metric < 0.85:  # More than 15% below peer average
                    undervalued_count += 1
                elif metric > 1.15:  # More than 15% above peer average
                    overvalued_count += 1
        
        if total_metrics == 0:
            return 'N/A'
        
        # Determine overall assessment
        if undervalued_count > overvalued_count:
            return 'Undervalued'
        elif overvalued_count > undervalued_count:
            return 'Overvalued'
        else:
            return 'Fair Value'
    
    def _apply_conditional_formatting(self):
        """Apply conditional formatting to highlight relative performance."""
        # Apply color scales to numerical data
        for row in range(1, self.ws.max_row + 1):
            for col in range(3, min(self.ws.max_column + 1, 12)):
                cell = self.ws.cell(row=row, column=col)
                if isinstance(cell.value, (int, float)) and cell.value != 0:
                    try:
                        # Green for better values, red for worse
                        rule = ColorScaleRule(
                            start_type='percentile', start_value=10, start_color='FFB6C1',
                            mid_type='percentile', mid_value=50, mid_color='FFFFFF',
                            end_type='percentile', end_value=90, end_color='90EE90'
                        )
                        range_string = f"{get_column_letter(col)}{row}"
                        self.ws.conditional_formatting.add(range_string, rule)
                    except Exception:
                        pass
    
    def _adjust_column_widths(self):
        """Auto-adjust column widths for better readability."""
        for column in self.ws.columns:
            max_length = 0
            column_letter = get_column_letter(column[0].column)
            
            for cell in column:
                try:
                    if cell.value and len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            
            adjusted_width = min(max_length + 3, 25)
            self.ws.column_dimensions[column_letter].width = max(adjusted_width, 12)