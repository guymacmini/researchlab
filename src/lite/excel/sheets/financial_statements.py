"""Financial statements sheet for institutional research workbook."""

from typing import Dict, Any, List, Tuple
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule


class FinancialStatementsSheet:
    """Creates financial statements sheet with 3-5 year historical data."""
    
    def __init__(self, workbook: Workbook):
        self.workbook = workbook
        self.ws = workbook.create_sheet("Financial Statements")
    
    def create_sheet(self, company_data: Dict[str, Dict[str, Any]]):
        """Create financial statements sheet with historical data."""
        
        # Sheet title
        self.ws['A1'] = "FINANCIAL STATEMENTS ANALYSIS"
        self.ws['A1'].style = 'header_style'
        self.ws.merge_cells('A1:I1')
        
        current_row = 3
        
        # Process each company's financial data
        for ticker, data in company_data.items():
            company_name = self._get_company_name(data)
            
            # Company header
            self.ws[f'A{current_row}'] = f"{company_name} ({ticker})"
            self.ws[f'A{current_row}'].style = 'subheader_style'
            self.ws.merge_cells(f'A{current_row}:I{current_row}')
            current_row += 2
            
            # Income Statement
            current_row = self._create_income_statement(data, current_row)
            current_row += 2
            
            # Balance Sheet (key items)
            current_row = self._create_balance_sheet(data, current_row)
            current_row += 2
            
            # Cash Flow Statement (key items)
            current_row = self._create_cash_flow(data, current_row)
            current_row += 3
        
        # Apply formatting
        self._apply_formatting()
        self._adjust_column_widths()
    
    def _get_company_name(self, data: Dict[str, Any]) -> str:
        """Extract company name from various data sources."""
        # Try different data sources
        if 'info' in data and 'name' in data['info']:
            return data['info']['name']
        
        if 'financial_data' in data:
            financial_data = data['financial_data']
            if 'profile' in financial_data and 'name' in financial_data['profile']:
                return financial_data['profile']['name']
        
        return "Unknown Company"
    
    def _create_income_statement(self, data: Dict[str, Any], start_row: int) -> int:
        """Create income statement section."""
        current_row = start_row
        
        # Section header
        self.ws[f'A{current_row}'] = "INCOME STATEMENT ($ Millions)"
        self.ws[f'A{current_row}'].style = 'subheader_style'
        self.ws.merge_cells(f'A{current_row}:F{current_row}')
        current_row += 1
        
        # Get financial data
        income_data = self._extract_income_data(data)
        
        if not income_data:
            self.ws[f'A{current_row}'] = "Income statement data not available"
            return current_row + 1
        
        # Create table headers (years)
        years = list(income_data.keys())[:5]  # Limit to 5 years
        self.ws[f'A{current_row}'] = "Metric"
        self.ws[f'A{current_row}'].style = 'subheader_style'
        
        for col, year in enumerate(years, 2):
            cell = self.ws.cell(row=current_row, column=col, value=str(year))
            cell.style = 'subheader_style'
        current_row += 1
        
        # Income statement line items
        income_items = [
            ('Revenue', 'revenue'),
            ('Cost of Revenue', 'costOfRevenue'),
            ('Gross Profit', 'grossProfit'),
            ('Operating Expenses', 'operatingExpenses'),
            ('Operating Income', 'operatingIncome'),
            ('Net Income', 'netIncome'),
            ('EPS', 'eps'),
            ('EBITDA', 'ebitda')
        ]
        
        for item_name, item_key in income_items:
            self.ws[f'A{current_row}'] = item_name
            self.ws[f'A{current_row}'].style = 'data_style'
            
            for col, year in enumerate(years, 2):
                value = income_data.get(year, {}).get(item_key, 'N/A')
                formatted_value = self._format_financial_value(value)
                cell = self.ws.cell(row=current_row, column=col, value=formatted_value)
                
                # Apply currency style for monetary values
                if item_key != 'eps':
                    cell.style = 'currency_style'
                else:
                    cell.style = 'data_style'
            
            current_row += 1
        
        # Calculate margins
        margin_row = current_row + 1
        self.ws[f'A{margin_row}'] = "MARGINS (%)"
        self.ws[f'A{margin_row}'].style = 'subheader_style'
        margin_row += 1
        
        margin_items = [
            ('Gross Margin', 'grossProfitMargin'),
            ('Operating Margin', 'operatingIncomeMargin'),
            ('Net Margin', 'netIncomeMargin')
        ]
        
        for margin_name, margin_key in margin_items:
            self.ws[f'A{margin_row}'] = margin_name
            self.ws[f'A{margin_row}'].style = 'data_style'
            
            for col, year in enumerate(years, 2):
                # Calculate margin from raw data
                year_data = income_data.get(year, {})
                margin_value = self._calculate_margin(year_data, margin_key)
                
                cell = self.ws.cell(row=margin_row, column=col, value=margin_value)
                cell.style = 'percentage_style'
            
            margin_row += 1
        
        return margin_row
    
    def _create_balance_sheet(self, data: Dict[str, Any], start_row: int) -> int:
        """Create balance sheet section with key items."""
        current_row = start_row
        
        # Section header
        self.ws[f'A{current_row}'] = "BALANCE SHEET ($ Millions)"
        self.ws[f'A{current_row}'].style = 'subheader_style'
        self.ws.merge_cells(f'A{current_row}:F{current_row}')
        current_row += 1
        
        # Get balance sheet data
        balance_data = self._extract_balance_data(data)
        
        if not balance_data:
            self.ws[f'A{current_row}'] = "Balance sheet data not available"
            return current_row + 1
        
        # Create table headers (years)
        years = list(balance_data.keys())[:5]
        self.ws[f'A{current_row}'] = "Metric"
        self.ws[f'A{current_row}'].style = 'subheader_style'
        
        for col, year in enumerate(years, 2):
            cell = self.ws.cell(row=current_row, column=col, value=str(year))
            cell.style = 'subheader_style'
        current_row += 1
        
        # Key balance sheet items
        balance_items = [
            ('Total Assets', 'totalAssets'),
            ('Current Assets', 'totalCurrentAssets'),
            ('Cash & Equivalents', 'cashAndCashEquivalents'),
            ('Total Debt', 'totalDebt'),
            ('Current Liabilities', 'totalCurrentLiabilities'),
            ('Total Equity', 'totalStockholdersEquity'),
            ('Working Capital', 'workingCapital')
        ]
        
        for item_name, item_key in balance_items:
            self.ws[f'A{current_row}'] = item_name
            self.ws[f'A{current_row}'].style = 'data_style'
            
            for col, year in enumerate(years, 2):
                value = balance_data.get(year, {}).get(item_key, 'N/A')
                formatted_value = self._format_financial_value(value)
                cell = self.ws.cell(row=current_row, column=col, value=formatted_value)
                cell.style = 'currency_style'
            
            current_row += 1
        
        return current_row
    
    def _create_cash_flow(self, data: Dict[str, Any], start_row: int) -> int:
        """Create cash flow statement section."""
        current_row = start_row
        
        # Section header
        self.ws[f'A{current_row}'] = "CASH FLOW STATEMENT ($ Millions)"
        self.ws[f'A{current_row}'].style = 'subheader_style'
        self.ws.merge_cells(f'A{current_row}:F{current_row}')
        current_row += 1
        
        # Get cash flow data
        cashflow_data = self._extract_cashflow_data(data)
        
        if not cashflow_data:
            self.ws[f'A{current_row}'] = "Cash flow data not available"
            return current_row + 1
        
        # Create table headers (years)
        years = list(cashflow_data.keys())[:5]
        self.ws[f'A{current_row}'] = "Metric"
        self.ws[f'A{current_row}'].style = 'subheader_style'
        
        for col, year in enumerate(years, 2):
            cell = self.ws.cell(row=current_row, column=col, value=str(year))
            cell.style = 'subheader_style'
        current_row += 1
        
        # Cash flow items
        cashflow_items = [
            ('Operating Cash Flow', 'operatingCashFlow'),
            ('Capital Expenditure', 'capitalExpenditure'),
            ('Free Cash Flow', 'freeCashFlow'),
            ('Financing Cash Flow', 'netCashUsedProvidedByFinancingActivities'),
            ('Dividend Payments', 'dividendsPaid')
        ]
        
        for item_name, item_key in cashflow_items:
            self.ws[f'A{current_row}'] = item_name
            self.ws[f'A{current_row}'].style = 'data_style'
            
            for col, year in enumerate(years, 2):
                value = cashflow_data.get(year, {}).get(item_key, 'N/A')
                formatted_value = self._format_financial_value(value)
                cell = self.ws.cell(row=current_row, column=col, value=formatted_value)
                cell.style = 'currency_style'
            
            current_row += 1
        
        return current_row
    
    def _extract_income_data(self, data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Extract income statement data from company data."""
        income_data = {}
        
        # Try to get FMP data first
        if 'financial_data' in data:
            financial_data = data['financial_data']
            if 'income_statements' in financial_data:
                for statement in financial_data['income_statements']:
                    if 'date' in statement:
                        year = statement['date'][:4]  # Extract year
                        income_data[year] = statement
        
        return income_data
    
    def _extract_balance_data(self, data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Extract balance sheet data from company data."""
        balance_data = {}
        
        if 'financial_data' in data:
            financial_data = data['financial_data']
            if 'balance_sheets' in financial_data:
                for statement in financial_data['balance_sheets']:
                    if 'date' in statement:
                        year = statement['date'][:4]
                        balance_data[year] = statement
        
        return balance_data
    
    def _extract_cashflow_data(self, data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Extract cash flow data from company data."""
        cashflow_data = {}
        
        if 'financial_data' in data:
            financial_data = data['financial_data']
            if 'cash_flows' in financial_data:
                for statement in financial_data['cash_flows']:
                    if 'date' in statement:
                        year = statement['date'][:4]
                        cashflow_data[year] = statement
        
        return cashflow_data
    
    def _format_financial_value(self, value: Any) -> Any:
        """Format financial values for display."""
        if value is None or value == 'N/A':
            return 'N/A'
        
        try:
            if isinstance(value, str):
                if value.replace('.', '').replace('-', '').isdigit():
                    value = float(value)
                else:
                    return value
            
            if isinstance(value, (int, float)):
                # Convert to millions
                return round(value / 1_000_000, 1)
            
            return value
            
        except (ValueError, TypeError):
            return 'N/A'
    
    def _calculate_margin(self, year_data: Dict[str, Any], margin_type: str) -> float:
        """Calculate financial margins."""
        try:
            revenue = year_data.get('revenue', 0)
            if not revenue or revenue == 0:
                return 0.0
            
            if margin_type == 'grossProfitMargin':
                gross_profit = year_data.get('grossProfit', 0)
                return round((gross_profit / revenue) * 100, 1)
            elif margin_type == 'operatingIncomeMargin':
                operating_income = year_data.get('operatingIncome', 0)
                return round((operating_income / revenue) * 100, 1)
            elif margin_type == 'netIncomeMargin':
                net_income = year_data.get('netIncome', 0)
                return round((net_income / revenue) * 100, 1)
            
            return 0.0
            
        except (TypeError, ValueError, ZeroDivisionError):
            return 0.0
    
    def _apply_formatting(self):
        """Apply conditional formatting to highlight trends."""
        # Add color scale for numerical data
        try:
            for row in range(1, self.ws.max_row + 1):
                for col in range(2, min(7, self.ws.max_column + 1)):  # Only numerical columns
                    cell = self.ws.cell(row=row, column=col)
                    if isinstance(cell.value, (int, float)) and cell.value != 0:
                        # Apply color scale rule (green for positive, red for negative)
                        rule = ColorScaleRule(
                            start_type='min', start_color='FF6B6B',  # Red
                            mid_type='num', mid_value=0, mid_color='FFFFFF',  # White
                            end_type='max', end_color='4ECDC4'  # Teal
                        )
                        range_string = f"{get_column_letter(col)}{row}"
                        self.ws.conditional_formatting.add(range_string, rule)
        except Exception:
            pass  # Skip formatting if it fails
    
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
            
            adjusted_width = min(max_length + 3, 20)
            self.ws.column_dimensions[column_letter].width = max(adjusted_width, 10)