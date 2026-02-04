"""
Excel workbook generation for institutional research reports.

This module provides comprehensive Excel workbook generation with:
- Executive summary with key findings and recommendations
- Historical financial statements (3-5 years)
- Valuation comparables with peer analysis
- Scenario analysis with bull/base/bear cases
- Detailed company profiles
- Data sources and methodology documentation

Professional formatting with conditional formatting, charts, and institutional-grade presentation.
"""

from .workbook import InstitutionalWorkbook, create_institutional_report, create_company_report

__all__ = [
    'InstitutionalWorkbook',
    'create_institutional_report', 
    'create_company_report'
]