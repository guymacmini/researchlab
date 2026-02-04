"""Financial Modeling Prep API client for institutional-grade financial data."""

import asyncio
import json
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
import structlog

import httpx
from ..config import settings

logger = structlog.get_logger()


class FinancialModelingPrepClient:
    """
    Client for Financial Modeling Prep API.
    Provides real financial statements, ratios, and valuation data.
    
    Free tier: 250 requests/day
    Docs: https://financialmodelingprep.com/developer/docs
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or getattr(settings, 'fmp_api_key', None)
        if not self.api_key:
            logger.warning("No FMP API key provided - will use demo key with limited functionality")
            self.api_key = "demo"  # FMP provides demo key for testing
        
        self.base_url = "https://financialmodelingprep.com/api"
        self.session = httpx.AsyncClient(timeout=30.0)
    
    async def _request(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make authenticated request to FMP API."""
        if params is None:
            params = {}
        
        params['apikey'] = self.api_key
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # Handle empty responses or error messages
            if not data:
                logger.warning("Empty response from FMP API", endpoint=endpoint)
                return {}
            
            if isinstance(data, dict) and 'Error Message' in data:
                logger.error("FMP API error", error=data['Error Message'], endpoint=endpoint)
                return {}
            
            return data
            
        except httpx.HTTPStatusError as e:
            logger.error("FMP API HTTP error", status=e.response.status_code, endpoint=endpoint)
            return {}
        except Exception as e:
            logger.error("FMP API request failed", error=str(e), endpoint=endpoint)
            return {}
    
    async def get_company_profile(self, symbol: str) -> Dict[str, Any]:
        """Get comprehensive company profile."""
        endpoint = f"/v3/profile/{symbol}"
        response = await self._request(endpoint)
        
        if isinstance(response, list) and len(response) > 0:
            return response[0]
        return response or {}
    
    async def get_income_statements(self, symbol: str, period: str = "annual", limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get historical income statements.
        
        Args:
            symbol: Stock ticker
            period: 'annual' or 'quarter'
            limit: Number of periods to retrieve (max 40)
        """
        endpoint = f"/v3/income-statement/{symbol}"
        params = {"period": period, "limit": limit}
        
        response = await self._request(endpoint, params)
        return response if isinstance(response, list) else []
    
    async def get_balance_sheets(self, symbol: str, period: str = "annual", limit: int = 5) -> List[Dict[str, Any]]:
        """Get historical balance sheets."""
        endpoint = f"/v3/balance-sheet-statement/{symbol}"
        params = {"period": period, "limit": limit}
        
        response = await self._request(endpoint, params)
        return response if isinstance(response, list) else []
    
    async def get_cash_flows(self, symbol: str, period: str = "annual", limit: int = 5) -> List[Dict[str, Any]]:
        """Get historical cash flow statements."""
        endpoint = f"/v3/cash-flow-statement/{symbol}"
        params = {"period": period, "limit": limit}
        
        response = await self._request(endpoint, params)
        return response if isinstance(response, list) else []
    
    async def get_financial_ratios(self, symbol: str, period: str = "annual", limit: int = 5) -> List[Dict[str, Any]]:
        """Get comprehensive financial ratios."""
        endpoint = f"/v3/ratios/{symbol}"
        params = {"period": period, "limit": limit}
        
        response = await self._request(endpoint, params)
        return response if isinstance(response, list) else []
    
    async def get_key_metrics(self, symbol: str, period: str = "annual", limit: int = 5) -> List[Dict[str, Any]]:
        """Get key financial metrics (P/E, P/B, ROE, etc.)."""
        endpoint = f"/v3/key-metrics/{symbol}"
        params = {"period": period, "limit": limit}
        
        response = await self._request(endpoint, params)
        return response if isinstance(response, list) else []
    
    async def get_enterprise_value(self, symbol: str, period: str = "annual", limit: int = 5) -> List[Dict[str, Any]]:
        """Get enterprise value and related metrics."""
        endpoint = f"/v3/enterprise-values/{symbol}"
        params = {"period": period, "limit": limit}
        
        response = await self._request(endpoint, params)
        return response if isinstance(response, list) else []
    
    async def get_financial_growth(self, symbol: str, period: str = "annual", limit: int = 5) -> List[Dict[str, Any]]:
        """Get financial growth metrics."""
        endpoint = f"/v3/financial-growth/{symbol}"
        params = {"period": period, "limit": limit}
        
        response = await self._request(endpoint, params)
        return response if isinstance(response, list) else []
    
    async def get_dcf_valuation(self, symbol: str) -> Dict[str, Any]:
        """Get DCF valuation if available."""
        endpoint = f"/v3/discounted-cash-flow/{symbol}"
        response = await self._request(endpoint)
        
        if isinstance(response, list) and len(response) > 0:
            return response[0]
        return response or {}
    
    async def get_peer_comparison(self, symbol: str) -> List[str]:
        """Get list of peer companies (using same sector)."""
        try:
            # First get company profile to find sector
            profile = await self.get_company_profile(symbol)
            sector = profile.get('sector', '')
            
            if not sector:
                return []
            
            # Get companies in same sector (simplified approach)
            endpoint = f"/v3/stock-screener"
            params = {
                "sector": sector,
                "limit": 10,
                "marketCapMoreThan": 1000000000  # $1B+ market cap
            }
            
            response = await self._request(endpoint, params)
            
            if isinstance(response, list):
                # Return ticker symbols excluding the original
                peers = [company.get('symbol', '') for company in response 
                        if company.get('symbol', '').upper() != symbol.upper()]
                return peers[:5]  # Top 5 peers
            
            return []
            
        except Exception as e:
            logger.error("Failed to get peer comparison", symbol=symbol, error=str(e))
            return []
    
    async def get_comprehensive_data(self, symbol: str) -> Dict[str, Any]:
        """
        Get comprehensive financial data package for a company.
        This is the main method for institutional research.
        """
        logger.info("Fetching comprehensive FMP data", symbol=symbol)
        
        # Fetch all data in parallel
        tasks = {
            'profile': self.get_company_profile(symbol),
            'income_statements': self.get_income_statements(symbol, limit=5),
            'balance_sheets': self.get_balance_sheets(symbol, limit=5),
            'cash_flows': self.get_cash_flows(symbol, limit=5),
            'ratios': self.get_financial_ratios(symbol, limit=5),
            'key_metrics': self.get_key_metrics(symbol, limit=5),
            'enterprise_values': self.get_enterprise_value(symbol, limit=5),
            'growth_metrics': self.get_financial_growth(symbol, limit=5),
            'dcf_valuation': self.get_dcf_valuation(symbol),
            'peers': self.get_peer_comparison(symbol)
        }
        
        results = {}
        for key, task in tasks.items():
            try:
                results[key] = await task
            except Exception as e:
                logger.error(f"Failed to fetch {key}", symbol=symbol, error=str(e))
                results[key] = [] if key in ['income_statements', 'balance_sheets', 'cash_flows', 
                                           'ratios', 'key_metrics', 'enterprise_values', 
                                           'growth_metrics', 'peers'] else {}
        
        # Add metadata
        results['symbol'] = symbol
        results['retrieved_at'] = datetime.utcnow().isoformat()
        results['data_source'] = 'financial_modeling_prep'
        
        logger.info("FMP data fetch completed", symbol=symbol, 
                   has_income=len(results['income_statements']),
                   has_balance=len(results['balance_sheets']),
                   has_ratios=len(results['ratios']))
        
        return results
    
    async def close(self):
        """Close HTTP session."""
        await self.session.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# For backward compatibility and easy imports
async def get_fmp_data(symbol: str) -> Dict[str, Any]:
    """Convenience function to get comprehensive FMP data."""
    async with FinancialModelingPrepClient() as client:
        return await client.get_comprehensive_data(symbol)


# Test function for validation
async def test_fmp_client():
    """Test FMP client with a known ticker."""
    async with FinancialModelingPrepClient() as client:
        data = await client.get_comprehensive_data("AAPL")
        print(f"Profile keys: {list(data.get('profile', {}).keys())}")
        print(f"Income statements: {len(data.get('income_statements', []))}")
        print(f"Balance sheets: {len(data.get('balance_sheets', []))}")
        print(f"Ratios: {len(data.get('ratios', []))}")


if __name__ == "__main__":
    asyncio.run(test_fmp_client())