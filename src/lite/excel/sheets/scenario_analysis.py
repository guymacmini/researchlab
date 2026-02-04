"""Scenario analysis sheet for institutional research workbook."""

from typing import Dict, Any, List, Tuple
from datetime import datetime
import re

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter


class ScenarioAnalysisSheet:
    """Creates scenario analysis sheet with bull/base/bear cases."""
    
    def __init__(self, workbook: Workbook):
        self.workbook = workbook
        self.ws = workbook.create_sheet("Scenario Analysis")
    
    def create_sheet(self, company_data: Dict[str, Dict[str, Any]], analysis_text: str):
        """Create scenario analysis sheet with stress tests."""
        
        # Sheet title
        self.ws['A1'] = "SCENARIO ANALYSIS"
        self.ws['A1'].style = 'header_style'
        self.ws.merge_cells('A1:H1')
        
        current_row = 3
        
        # Scenario overview
        self.ws[f'A{current_row}'] = "SCENARIO OVERVIEW"
        self.ws[f'A{current_row}'].style = 'subheader_style'
        self.ws.merge_cells(f'A{current_row}:H{current_row}')
        current_row += 2
        
        # Create scenarios table
        current_row = self._create_scenarios_table(current_row)
        current_row += 3
        
        # Financial impact analysis
        current_row = self._create_financial_impact_table(company_data, current_row)
        current_row += 3
        
        # Risk-return matrix
        current_row = self._create_risk_return_matrix(company_data, current_row)
        
        self._adjust_column_widths()
    
    def _create_scenarios_table(self, start_row: int) -> int:
        """Create the main scenarios comparison table."""
        current_row = start_row
        
        # Headers
        headers = ['Scenario', 'Probability (%)', 'Key Assumptions', 'Expected Return (%)', 'Risk Level']
        for col, header in enumerate(headers, 1):
            cell = self.ws.cell(row=current_row, column=col, value=header)
            cell.style = 'subheader_style'
        current_row += 1
        
        # Define scenarios
        scenarios = [
            {
                'name': 'BULL CASE',
                'probability': 25,
                'assumptions': 'Strong economic growth, favorable regulations, market expansion',
                'expected_return': 35,
                'risk_level': 'Medium',
                'color': '90EE90'
            },
            {
                'name': 'BASE CASE',
                'probability': 50,
                'assumptions': 'Steady growth, stable market conditions, current trends continue',
                'expected_return': 15,
                'risk_level': 'Low',
                'color': 'FFFFE0'
            },
            {
                'name': 'BEAR CASE',
                'probability': 25,
                'assumptions': 'Economic slowdown, increased competition, regulatory headwinds',
                'expected_return': -10,
                'risk_level': 'High',
                'color': 'FFB6C1'
            }
        ]
        
        for scenario in scenarios:
            row_data = [
                scenario['name'],
                scenario['probability'],
                scenario['assumptions'],
                scenario['expected_return'],
                scenario['risk_level']
            ]
            
            for col, value in enumerate(row_data, 1):
                cell = self.ws.cell(row=current_row, column=col, value=value)
                
                # Apply styling
                if col == 1:  # Scenario name
                    cell.style = 'subheader_style'
                    cell.fill = PatternFill(start_color=scenario['color'], end_color=scenario['color'], fill_type='solid')
                elif col == 2:  # Probability
                    cell.style = 'percentage_style'
                elif col == 4:  # Expected return
                    cell.style = 'percentage_style'
                else:
                    cell.style = 'data_style'
                
                # Wrap text for assumptions
                if col == 3:
                    cell.alignment = Alignment(wrap_text=True, vertical='top')
            
            # Increase row height for wrapped text
            self.ws.row_dimensions[current_row].height = 45
            current_row += 1
        
        return current_row
    
    def _create_financial_impact_table(self, company_data: Dict[str, Dict[str, Any]], start_row: int) -> int:
        """Create financial impact stress test table."""
        current_row = start_row
        
        # Section header
        self.ws[f'A{current_row}'] = "FINANCIAL IMPACT STRESS TESTS"
        self.ws[f'A{current_row}'].style = 'subheader_style'
        self.ws.merge_cells(f'A{current_row}:H{current_row}')
        current_row += 2
        
        # Table headers
        headers = ['Stress Test', 'Current', 'Bull Case (+20%)', 'Base Case', 'Bear Case (-30%)']
        for col, header in enumerate(headers, 1):
            cell = self.ws.cell(row=current_row, column=col, value=header)
            cell.style = 'subheader_style'
        current_row += 1
        
        # Get representative company data (use first company)
        if company_data:
            ticker = list(company_data.keys())[0]
            data = company_data[ticker]
            base_metrics = self._extract_base_metrics(data)
            
            # Define stress test scenarios
            stress_tests = [
                ('Revenue ($M)', base_metrics.get('revenue', 1000)),
                ('Operating Margin (%)', base_metrics.get('operating_margin', 15)),
                ('Net Income ($M)', base_metrics.get('net_income', 100)),
                ('Free Cash Flow ($M)', base_metrics.get('free_cash_flow', 80)),
                ('Debt/Equity Ratio', base_metrics.get('debt_equity', 0.3)),
                ('ROE (%)', base_metrics.get('roe', 12))
            ]
            
            for test_name, base_value in stress_tests:
                if base_value == 'N/A' or not isinstance(base_value, (int, float)):
                    continue
                
                # Calculate scenario values
                bull_value = base_value * 1.2 if 'Ratio' not in test_name else base_value * 0.8
                base_case_value = base_value
                bear_value = base_value * 0.7 if 'Ratio' not in test_name else base_value * 1.3
                
                row_data = [
                    test_name,
                    base_value,
                    bull_value,
                    base_case_value,
                    bear_value
                ]
                
                for col, value in enumerate(row_data, 1):
                    cell = self.ws.cell(row=current_row, column=col, value=value)
                    
                    if col == 1:  # Test name
                        cell.style = 'data_style'
                    else:  # Numerical values
                        if '%' in test_name:
                            cell.style = 'percentage_style'
                            if isinstance(value, (int, float)):
                                cell.value = value / 100  # Convert to decimal for percentage format
                        elif '$M' in test_name:
                            cell.style = 'currency_style'
                            if isinstance(value, (int, float)):
                                cell.value = value * 1_000_000  # Convert to actual dollars
                        else:
                            cell.style = 'data_style'
                            if isinstance(value, (int, float)):
                                cell.number_format = '0.00'
                
                current_row += 1
        
        return current_row
    
    def _create_risk_return_matrix(self, company_data: Dict[str, Dict[str, Any]], start_row: int) -> int:
        """Create risk-return analysis matrix."""
        current_row = start_row
        
        # Section header
        self.ws[f'A{current_row}'] = "RISK-RETURN ANALYSIS"
        self.ws[f'A{current_row}'].style = 'subheader_style'
        self.ws.merge_cells(f'A{current_row}:F{current_row}')
        current_row += 2
        
        # Risk factors table
        risk_factors = [
            {
                'factor': 'Market Risk',
                'probability': 'Medium',
                'impact': 'High',
                'mitigation': 'Diversification, hedging',
                'severity': 7
            },
            {
                'factor': 'Operational Risk',
                'probability': 'Low',
                'impact': 'Medium',
                'mitigation': 'Strong management, processes',
                'severity': 4
            },
            {
                'factor': 'Regulatory Risk',
                'probability': 'Medium',
                'impact': 'Medium',
                'mitigation': 'Compliance, government relations',
                'severity': 5
            },
            {
                'factor': 'Competition Risk',
                'probability': 'High',
                'impact': 'Medium',
                'mitigation': 'Innovation, market position',
                'severity': 6
            },
            {
                'factor': 'Liquidity Risk',
                'probability': 'Low',
                'impact': 'High',
                'mitigation': 'Cash management, credit lines',
                'severity': 5
            }
        ]
        
        # Risk table headers
        headers = ['Risk Factor', 'Probability', 'Impact', 'Mitigation Strategy', 'Risk Score (1-10)']
        for col, header in enumerate(headers, 1):
            cell = self.ws.cell(row=current_row, column=col, value=header)
            cell.style = 'subheader_style'
        current_row += 1
        
        for risk in risk_factors:
            row_data = [
                risk['factor'],
                risk['probability'],
                risk['impact'],
                risk['mitigation'],
                risk['severity']
            ]
            
            for col, value in enumerate(row_data, 1):
                cell = self.ws.cell(row=current_row, column=col, value=value)
                cell.style = 'data_style'
                
                # Color code risk severity
                if col == 5:  # Risk score
                    if value >= 7:
                        cell.fill = PatternFill(start_color='FFB6C1', end_color='FFB6C1', fill_type='solid')
                    elif value >= 5:
                        cell.fill = PatternFill(start_color='FFFFE0', end_color='FFFFE0', fill_type='solid')
                    else:
                        cell.fill = PatternFill(start_color='90EE90', end_color='90EE90', fill_type='solid')
            
            current_row += 1
        
        # Add portfolio recommendations
        current_row += 2
        self.ws[f'A{current_row}'] = "PORTFOLIO RECOMMENDATIONS"
        self.ws[f'A{current_row}'].style = 'subheader_style'
        self.ws.merge_cells(f'A{current_row}:D{current_row}')
        current_row += 1
        
        recommendations = [
            "• Conservative investors: Focus on base case scenario (65% allocation)",
            "• Moderate investors: Balanced approach with 60% base, 25% bull, 15% bear hedge",
            "• Aggressive investors: Overweight bull case (45% allocation) with strict stop-losses",
            "• Risk management: Monitor key catalysts and adjust positions quarterly"
        ]
        
        for rec in recommendations:
            self.ws[f'A{current_row}'] = rec
            self.ws[f'A{current_row}'].font = Font(size=11)
            self.ws[f'A{current_row}'].alignment = Alignment(wrap_text=True)
            self.ws.merge_cells(f'A{current_row}:F{current_row}')
            current_row += 1
        
        return current_row
    
    def _extract_base_metrics(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract base financial metrics for stress testing."""
        metrics = {}
        
        # Try to get metrics from various data sources
        sources = [
            data.get('financial_data', {}),
            data.get('info', {}),
            data
        ]
        
        for source in sources:
            if not source:
                continue
            
            # Revenue (try different keys)
            for rev_key in ['revenue', 'revenueTTM', 'totalRevenue']:
                value = source.get(rev_key)
                if value and metrics.get('revenue') is None:
                    try:
                        metrics['revenue'] = float(value) / 1_000_000  # Convert to millions
                    except (ValueError, TypeError):
                        pass
            
            # Operating margin
            for om_key in ['operatingMarginTTM', 'operatingMargin', 'operating_margin']:
                value = source.get(om_key)
                if value and metrics.get('operating_margin') is None:
                    try:
                        metrics['operating_margin'] = float(value) * 100 if float(value) < 1 else float(value)
                    except (ValueError, TypeError):
                        pass
            
            # Net income
            for ni_key in ['netIncome', 'netIncomeTTM']:
                value = source.get(ni_key)
                if value and metrics.get('net_income') is None:
                    try:
                        metrics['net_income'] = float(value) / 1_000_000
                    except (ValueError, TypeError):
                        pass
            
            # Free cash flow
            for fcf_key in ['freeCashFlow', 'operatingCashFlow']:
                value = source.get(fcf_key)
                if value and metrics.get('free_cash_flow') is None:
                    try:
                        metrics['free_cash_flow'] = float(value) / 1_000_000
                    except (ValueError, TypeError):
                        pass
            
            # Debt/Equity
            for de_key in ['debtToEquity', 'totalDebt/totalEquityQuarterly']:
                value = source.get(de_key)
                if value and metrics.get('debt_equity') is None:
                    try:
                        metrics['debt_equity'] = float(value)
                    except (ValueError, TypeError):
                        pass
            
            # ROE
            for roe_key in ['returnOnEquityTTM', 'roeTTM', 'roe']:
                value = source.get(roe_key)
                if value and metrics.get('roe') is None:
                    try:
                        metrics['roe'] = float(value) * 100 if float(value) < 1 else float(value)
                    except (ValueError, TypeError):
                        pass
        
        # Set defaults for missing values
        defaults = {
            'revenue': 1000,
            'operating_margin': 15,
            'net_income': 100,
            'free_cash_flow': 80,
            'debt_equity': 0.3,
            'roe': 12
        }
        
        for key, default_value in defaults.items():
            if key not in metrics:
                metrics[key] = default_value
        
        return metrics
    
    def _adjust_column_widths(self):
        """Auto-adjust column widths for readability."""
        for column in self.ws.columns:
            max_length = 0
            column_letter = get_column_letter(column[0].column)
            
            for cell in column:
                try:
                    if cell.value and len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            
            adjusted_width = min(max_length + 3, 40)
            self.ws.column_dimensions[column_letter].width = max(adjusted_width, 15)