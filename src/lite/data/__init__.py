"""
Data clients for institutional-grade financial research.

This module provides clients for multiple financial data sources:
- Financial Modeling Prep: Comprehensive financial statements and ratios
- Alpha Vantage: Fundamental data and economic indicators  
- SEC EDGAR: Official SEC filings and earnings transcripts
"""

from .fmp_client import FinancialModelingPrepClient, get_fmp_data
from .alpha_vantage_client import AlphaVantageClient, get_alpha_vantage_fundamentals, get_market_context
from .sec_client import SECClient, get_sec_filings, get_latest_10k_summary

__all__ = [
    'FinancialModelingPrepClient',
    'AlphaVantageClient', 
    'SECClient',
    'get_fmp_data',
    'get_alpha_vantage_fundamentals',
    'get_market_context',
    'get_sec_filings',
    'get_latest_10k_summary'
]