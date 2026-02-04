"""Enhanced Alpha Vantage API client for institutional-grade financial data."""

import asyncio
import json
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
import structlog

import httpx
from ..config import settings

logger = structlog.get_logger()


class AlphaVantageClient:
    """
    Enhanced Alpha Vantage API client for financial data.
    Focuses on earnings data, fundamental analysis, and economic indicators.
    
    Free tier: 25 requests/day, 5 requests/minute
    Docs: https://www.alphavantage.co/documentation/
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.alpha_vantage_api_key
        if not self.api_key or self.api_key == "demo":
            raise ValueError("Alpha Vantage API key is required")
        
        self.base_url = "https://www.alphavantage.co/query"
        self.session = httpx.AsyncClient(timeout=30.0)
        self._last_request = None
        self._request_interval = 12  # seconds (5 req/min = 12s interval)
    
    async def _rate_limit(self):
        """Implement rate limiting for free tier."""
        if self._last_request:
            elapsed = (datetime.utcnow() - self._last_request).total_seconds()
            if elapsed < self._request_interval:
                wait_time = self._request_interval - elapsed
                logger.debug(f"Rate limiting: waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
        
        self._last_request = datetime.utcnow()
    
    async def _request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Make rate-limited request to Alpha Vantage API."""
        await self._rate_limit()
        
        params['apikey'] = self.api_key
        
        try:
            response = await self.session.get(self.base_url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # Check for API error messages
            if 'Error Message' in data:
                logger.error("Alpha Vantage API error", error=data['Error Message'])
                return {}
            
            if 'Information' in data:
                logger.warning("Alpha Vantage API info", info=data['Information'])
                return {}
            
            if 'Note' in data:
                logger.warning("Alpha Vantage rate limit hit", note=data['Note'])
                # Wait longer and retry once
                await asyncio.sleep(60)
                response = await self.session.get(self.base_url, params=params)
                data = response.json()
            
            return data
            
        except Exception as e:
            logger.error("Alpha Vantage API request failed", error=str(e))
            return {}
    
    async def get_company_overview(self, symbol: str) -> Dict[str, Any]:
        """Get comprehensive company overview and fundamental data."""
        params = {
            'function': 'OVERVIEW',
            'symbol': symbol
        }
        
        return await self._request(params)
    
    async def get_income_statement(self, symbol: str) -> Dict[str, Any]:
        """Get annual and quarterly income statements."""
        params = {
            'function': 'INCOME_STATEMENT',
            'symbol': symbol
        }
        
        return await self._request(params)
    
    async def get_balance_sheet(self, symbol: str) -> Dict[str, Any]:
        """Get annual and quarterly balance sheets."""
        params = {
            'function': 'BALANCE_SHEET',
            'symbol': symbol
        }
        
        return await self._request(params)
    
    async def get_cash_flow(self, symbol: str) -> Dict[str, Any]:
        """Get annual and quarterly cash flow statements."""
        params = {
            'function': 'CASH_FLOW',
            'symbol': symbol
        }
        
        return await self._request(params)
    
    async def get_earnings(self, symbol: str) -> Dict[str, Any]:
        """Get historical earnings (EPS) data."""
        params = {
            'function': 'EARNINGS',
            'symbol': symbol
        }
        
        return await self._request(params)
    
    async def get_earnings_calendar(self) -> Dict[str, Any]:
        """Get upcoming earnings calendar (premium feature)."""
        params = {
            'function': 'EARNINGS_CALENDAR',
            'horizon': '3month'
        }
        
        return await self._request(params)
    
    async def get_analyst_recommendations(self, symbol: str) -> Dict[str, Any]:
        """Get analyst recommendations and price targets (premium feature)."""
        params = {
            'function': 'ANALYST_RECOMMENDATIONS',
            'symbol': symbol
        }
        
        return await self._request(params)
    
    async def get_insider_transactions(self, symbol: str) -> Dict[str, Any]:
        """Get insider trading transactions (premium feature)."""
        params = {
            'function': 'INSIDER_TRANSACTIONS',
            'symbol': symbol
        }
        
        return await self._request(params)
    
    async def get_ipo_calendar(self) -> Dict[str, Any]:
        """Get IPO calendar (premium feature)."""
        params = {
            'function': 'IPO_CALENDAR'
        }
        
        return await self._request(params)
    
    async def get_economic_indicator(self, indicator: str, interval: str = 'annual') -> Dict[str, Any]:
        """
        Get economic indicators.
        
        Available indicators:
        - REAL_GDP, REAL_GDP_PER_CAPITA
        - TREASURY_YIELD
        - FEDERAL_FUNDS_RATE
        - CPI, INFLATION
        - RETAIL_SALES
        - DURABLES
        - UNEMPLOYMENT
        - NONFARM_PAYROLL
        """
        params = {
            'function': indicator,
            'interval': interval
        }
        
        return await self._request(params)
    
    async def get_sector_performance(self) -> Dict[str, Any]:
        """Get real-time and historical sector performance."""
        params = {
            'function': 'SECTOR'
        }
        
        return await self._request(params)
    
    async def get_market_sentiment(self, symbol: str) -> Dict[str, Any]:
        """Get market sentiment from news articles."""
        params = {
            'function': 'NEWS_SENTIMENT',
            'tickers': symbol,
            'time_from': (datetime.utcnow() - timedelta(days=30)).strftime('%Y%m%dT%H%M'),
            'limit': 200
        }
        
        return await self._request(params)
    
    async def get_comprehensive_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """
        Get comprehensive fundamental data for institutional analysis.
        
        Note: This makes multiple API calls, so use sparingly due to rate limits.
        """
        logger.info("Fetching comprehensive Alpha Vantage data", symbol=symbol)
        
        # Fetch core fundamental data
        overview = await self.get_company_overview(symbol)
        
        # For free tier, we'll focus on overview data which is most comprehensive
        # Premium features would include more detailed statements
        
        result = {
            'symbol': symbol,
            'overview': overview,
            'retrieved_at': datetime.utcnow().isoformat(),
            'data_source': 'alpha_vantage'
        }
        
        # Extract key metrics from overview for easier access
        if overview:
            result['key_metrics'] = {
                'market_cap': overview.get('MarketCapitalization'),
                'pe_ratio': overview.get('PERatio'),
                'peg_ratio': overview.get('PEGRatio'),
                'pb_ratio': overview.get('PriceToBookRatio'),
                'ps_ratio': overview.get('PriceToSalesRatioTTM'),
                'ev_revenue': overview.get('EVToRevenue'),
                'ev_ebitda': overview.get('EVToEBITDA'),
                'profit_margin': overview.get('ProfitMargin'),
                'operating_margin': overview.get('OperatingMarginTTM'),
                'roe': overview.get('ReturnOnEquityTTM'),
                'roa': overview.get('ReturnOnAssetsTTM'),
                'revenue_ttm': overview.get('RevenueTTM'),
                'gross_profit_ttm': overview.get('GrossProfitTTM'),
                'diluted_eps_ttm': overview.get('DilutedEPSTTM'),
                'beta': overview.get('Beta'),
                'week_52_high': overview.get('52WeekHigh'),
                'week_52_low': overview.get('52WeekLow'),
                'dividend_yield': overview.get('DividendYield'),
                'dividend_date': overview.get('DividendDate'),
                'ex_dividend_date': overview.get('ExDividendDate'),
                'analyst_target_price': overview.get('AnalystTargetPrice'),
                'book_value': overview.get('BookValue'),
                'ebitda': overview.get('EBITDA'),
                'shares_outstanding': overview.get('SharesOutstanding'),
                'dividend_per_share': overview.get('DividendPerShare'),
                'quarterly_earnings_growth': overview.get('QuarterlyEarningsGrowthYOY'),
                'quarterly_revenue_growth': overview.get('QuarterlyRevenueGrowthYOY')
            }
            
            result['company_info'] = {
                'name': overview.get('Name'),
                'description': overview.get('Description'),
                'sector': overview.get('Sector'),
                'industry': overview.get('Industry'),
                'country': overview.get('Country'),
                'currency': overview.get('Currency'),
                'exchange': overview.get('Exchange'),
                'fiscal_year_end': overview.get('FiscalYearEnd'),
                'latest_quarter': overview.get('LatestQuarter')
            }
        
        logger.info("Alpha Vantage data fetch completed", symbol=symbol, 
                   has_overview=bool(overview))
        
        return result
    
    async def get_sector_data(self) -> Dict[str, Any]:
        """Get sector performance data for macro analysis."""
        try:
            sector_data = await self.get_sector_performance()
            
            if sector_data:
                return {
                    'sector_performance': sector_data,
                    'retrieved_at': datetime.utcnow().isoformat(),
                    'data_source': 'alpha_vantage'
                }
            
            return {}
            
        except Exception as e:
            logger.error("Failed to get sector data", error=str(e))
            return {}
    
    async def get_economic_context(self) -> Dict[str, Any]:
        """Get economic indicators for macro analysis."""
        try:
            # Get key economic indicators
            indicators = ['REAL_GDP', 'FEDERAL_FUNDS_RATE', 'CPI', 'UNEMPLOYMENT']
            results = {}
            
            for indicator in indicators:
                try:
                    data = await self.get_economic_indicator(indicator)
                    if data:
                        results[indicator.lower()] = data
                except Exception as e:
                    logger.warning(f"Failed to get {indicator}", error=str(e))
                    continue
            
            if results:
                return {
                    'economic_indicators': results,
                    'retrieved_at': datetime.utcnow().isoformat(),
                    'data_source': 'alpha_vantage'
                }
            
            return {}
            
        except Exception as e:
            logger.error("Failed to get economic context", error=str(e))
            return {}
    
    async def close(self):
        """Close HTTP session."""
        await self.session.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# Convenience functions
async def get_alpha_vantage_fundamentals(symbol: str) -> Dict[str, Any]:
    """Get comprehensive Alpha Vantage fundamental data."""
    async with AlphaVantageClient() as client:
        return await client.get_comprehensive_fundamentals(symbol)


async def get_market_context() -> Dict[str, Any]:
    """Get market sector performance and economic context."""
    async with AlphaVantageClient() as client:
        sector_data = await client.get_sector_data()
        economic_data = await client.get_economic_context()
        
        return {
            'sector_performance': sector_data,
            'economic_indicators': economic_data,
            'retrieved_at': datetime.utcnow().isoformat()
        }


# Test function
async def test_alpha_vantage_client():
    """Test Alpha Vantage client with a known ticker."""
    async with AlphaVantageClient() as client:
        data = await client.get_comprehensive_fundamentals("AAPL")
        print(f"Company: {data.get('company_info', {}).get('name')}")
        print(f"Market Cap: {data.get('key_metrics', {}).get('market_cap')}")
        print(f"P/E Ratio: {data.get('key_metrics', {}).get('pe_ratio')}")


if __name__ == "__main__":
    asyncio.run(test_alpha_vantage_client())