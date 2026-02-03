"""Alpha Vantage API client with rate limiting and caching."""

from typing import Dict, List, Optional, Any
import asyncio
from datetime import datetime

import structlog
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.core.config import settings
from .rate_limiter import AsyncRateLimiter, RateLimit
from .data_cache import DataCache, cache_key_for_api_call, CACHE_TTL

logger = structlog.get_logger()


class AlphaVantageAPIError(Exception):
    """Alpha Vantage API specific error."""
    def __init__(self, message: str, status_code: Optional[int] = None, response: Optional[Dict] = None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(message)


class AlphaVantageClient:
    """Async Alpha Vantage API client with rate limiting and caching."""
    
    BASE_URL = "https://www.alphavantage.co/query"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        rate_limiter: Optional[AsyncRateLimiter] = None,
        cache: Optional[DataCache] = None
    ):
        self.api_key = api_key or settings.api.alpha_vantage_api_key
        if not self.api_key:
            raise ValueError("Alpha Vantage API key is required")
        
        self.rate_limiter = rate_limiter or AsyncRateLimiter()
        self.cache = cache or DataCache()
        
        # Set up rate limiting (Alpha Vantage free tier: 5 requests/minute, 500/day)
        self.rate_limiter.set_limit(
            "alpha_vantage",
            RateLimit(
                requests_per_minute=settings.api.alpha_vantage_rate_limit,
                requests_per_hour=300,  # Conservative: 5/min * 60min = 300/hour
                requests_per_day=500,   # Free tier daily limit
                burst_size=2  # Very small burst for this limited API
            )
        )
        
        self.client = httpx.AsyncClient(
            timeout=60.0,  # Alpha Vantage can be slow
            headers={
                'User-Agent': f'ResearchLab/{settings.app.version}'
            }
        )
        
        self.logger = logger.bind(component="alpha_vantage_client")
    
    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException))
    )
    async def _make_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Make rate-limited API request with retries."""
        # Apply rate limiting
        await self.rate_limiter.acquire("alpha_vantage")
        
        # Add API key to params
        request_params = {**params, "apikey": self.api_key}
        
        try:
            self.logger.debug("api_request", function=params.get("function"), symbol=params.get("symbol"))
            
            response = await self.client.get(self.BASE_URL, params=request_params)
            response.raise_for_status()
            
            data = response.json()
            
            # Check for API-level errors
            if isinstance(data, dict):
                if "Error Message" in data:
                    raise AlphaVantageAPIError(f"API error: {data['Error Message']}")
                
                if "Note" in data and "call frequency" in data["Note"].lower():
                    # Rate limited by API
                    raise AlphaVantageAPIError(f"Rate limited: {data['Note']}")
                
                if "Information" in data and "premium" in data["Information"].lower():
                    # Hit premium feature limit
                    raise AlphaVantageAPIError(f"Premium feature required: {data['Information']}")
            
            return data
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                # Rate limited - wait longer for Alpha Vantage
                self.logger.warning("rate_limited_by_api", params=params)
                await asyncio.sleep(70)  # Wait more than a minute
                raise
            else:
                raise AlphaVantageAPIError(
                    f"HTTP error {e.response.status_code}: {e.response.text}",
                    status_code=e.response.status_code
                )
        
        except Exception as e:
            self.logger.error("api_request_failed", params=params, error=str(e))
            raise AlphaVantageAPIError(f"Request failed: {str(e)}")
    
    async def _cached_request(
        self,
        params: Dict[str, Any],
        cache_ttl: int = None,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Make cached API request."""
        function = params.get("function", "unknown")
        cache_key = cache_key_for_api_call("alpha_vantage", function, **params)
        
        # Check cache first (unless force refresh)
        if not force_refresh:
            cached_data = await self.cache.get(cache_key)
            if cached_data is not None:
                self.logger.debug("cache_hit", function=function)
                return cached_data
        
        # Make API request
        data = await self._make_request(params)
        
        # Cache the result
        ttl = cache_ttl or CACHE_TTL.get(function.lower(), CACHE_TTL['default'])
        await self.cache.set(
            cache_key,
            data,
            ttl_seconds=ttl,
            source="alpha_vantage",
            tags=["alpha_vantage", function.lower()]
        )
        
        return data
    
    async def get_company_overview(self, symbol: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Get company overview/fundamentals."""
        return await self._cached_request(
            {"function": "OVERVIEW", "symbol": symbol.upper()},
            cache_ttl=CACHE_TTL['company_profile'],
            force_refresh=force_refresh
        )
    
    async def get_income_statement(
        self,
        symbol: str,
        annual: bool = True,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Get income statement data."""
        return await self._cached_request(
            {
                "function": "INCOME_STATEMENT",
                "symbol": symbol.upper(),
                "datatype": "json"
            },
            cache_ttl=CACHE_TTL['financial_statements'],
            force_refresh=force_refresh
        )
    
    async def get_balance_sheet(
        self,
        symbol: str,
        annual: bool = True,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Get balance sheet data."""
        return await self._cached_request(
            {
                "function": "BALANCE_SHEET",
                "symbol": symbol.upper(),
                "datatype": "json"
            },
            cache_ttl=CACHE_TTL['financial_statements'],
            force_refresh=force_refresh
        )
    
    async def get_cash_flow(
        self,
        symbol: str,
        annual: bool = True,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Get cash flow statement data."""
        return await self._cached_request(
            {
                "function": "CASH_FLOW",
                "symbol": symbol.upper(),
                "datatype": "json"
            },
            cache_ttl=CACHE_TTL['financial_statements'],
            force_refresh=force_refresh
        )
    
    async def get_earnings(self, symbol: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Get earnings data."""
        return await self._cached_request(
            {"function": "EARNINGS", "symbol": symbol.upper()},
            cache_ttl=CACHE_TTL['financial_statements'],
            force_refresh=force_refresh
        )
    
    async def get_daily_prices(
        self,
        symbol: str,
        outputsize: str = "compact",
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Get daily time series data."""
        return await self._cached_request(
            {
                "function": "TIME_SERIES_DAILY",
                "symbol": symbol.upper(),
                "outputsize": outputsize,
                "datatype": "json"
            },
            cache_ttl=CACHE_TTL['market_data'],
            force_refresh=force_refresh
        )
    
    async def get_intraday_prices(
        self,
        symbol: str,
        interval: str = "5min",
        outputsize: str = "compact",
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Get intraday time series data."""
        return await self._cached_request(
            {
                "function": "TIME_SERIES_INTRADAY",
                "symbol": symbol.upper(),
                "interval": interval,
                "outputsize": outputsize,
                "datatype": "json"
            },
            cache_ttl=300,  # 5 minutes for intraday
            force_refresh=force_refresh
        )
    
    async def get_global_quote(self, symbol: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Get global quote (real-time-ish data)."""
        return await self._cached_request(
            {"function": "GLOBAL_QUOTE", "symbol": symbol.upper()},
            cache_ttl=CACHE_TTL['stock_quote'],
            force_refresh=force_refresh
        )
    
    async def search_endpoint(self, keywords: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Search for symbols."""
        return await self._cached_request(
            {"function": "SYMBOL_SEARCH", "keywords": keywords},
            cache_ttl=CACHE_TTL['default'],
            force_refresh=force_refresh
        )
    
    async def get_fx_rate(
        self,
        from_currency: str,
        to_currency: str,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Get foreign exchange rate."""
        return await self._cached_request(
            {
                "function": "CURRENCY_EXCHANGE_RATE",
                "from_currency": from_currency.upper(),
                "to_currency": to_currency.upper()
            },
            cache_ttl=CACHE_TTL['market_data'],
            force_refresh=force_refresh
        )
    
    async def get_technical_indicator(
        self,
        symbol: str,
        function: str,
        interval: str = "daily",
        time_period: int = None,
        series_type: str = "close",
        force_refresh: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Get technical indicator data."""
        params = {
            "function": function.upper(),
            "symbol": symbol.upper(),
            "interval": interval,
            "series_type": series_type,
            "datatype": "json"
        }
        
        if time_period:
            params["time_period"] = time_period
        
        # Add any additional parameters
        params.update(kwargs)
        
        return await self._cached_request(
            params,
            cache_ttl=CACHE_TTL['market_data'],
            force_refresh=force_refresh
        )
    
    async def get_sma(
        self,
        symbol: str,
        interval: str = "daily",
        time_period: int = 20,
        series_type: str = "close",
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Get Simple Moving Average."""
        return await self.get_technical_indicator(
            symbol, "SMA", interval, time_period, series_type, force_refresh
        )
    
    async def get_rsi(
        self,
        symbol: str,
        interval: str = "daily",
        time_period: int = 14,
        series_type: str = "close",
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Get Relative Strength Index."""
        return await self.get_technical_indicator(
            symbol, "RSI", interval, time_period, series_type, force_refresh
        )
    
    async def batch_company_overviews(
        self,
        symbols: List[str],
        force_refresh: bool = False
    ) -> Dict[str, Dict[str, Any]]:
        """Get company overviews for multiple symbols with careful rate limiting."""
        # Alpha Vantage has very strict rate limits, so we need to be extra careful
        results = {}
        
        for i, symbol in enumerate(symbols):
            try:
                result = await self.get_company_overview(symbol, force_refresh)
                results[symbol] = result
                
                # Add delay between requests to respect rate limits
                if i < len(symbols) - 1:  # Don't wait after the last request
                    # Wait based on rate limit: 5 req/min = 12 seconds between requests
                    await asyncio.sleep(12.5)  # A bit more than 12 seconds to be safe
                    
            except Exception as e:
                self.logger.error("batch_overview_failed", symbol=symbol, error=str(e))
                results[symbol] = None
        
        return results
    
    def parse_financial_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse and normalize financial statement data."""
        normalized = {}
        
        # Handle different response formats from Alpha Vantage
        if "Symbol" in data:
            normalized["symbol"] = data["Symbol"]
        
        # Extract quarterly and annual reports
        if "quarterlyReports" in data:
            normalized["quarterly"] = data["quarterlyReports"]
        
        if "annualReports" in data:
            normalized["annual"] = data["annualReports"]
        
        # Add metadata
        normalized["source"] = "alpha_vantage"
        normalized["retrieved_at"] = datetime.utcnow().isoformat()
        
        return normalized
    
    def parse_overview_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse and normalize company overview data."""
        if not data or "Symbol" not in data:
            return {}
        
        # Extract key metrics and convert to proper types
        try:
            normalized = {
                "symbol": data.get("Symbol"),
                "name": data.get("Name"),
                "description": data.get("Description"),
                "exchange": data.get("Exchange"),
                "currency": data.get("Currency"),
                "country": data.get("Country"),
                "sector": data.get("Sector"),
                "industry": data.get("Industry"),
                "market_cap": self._safe_float(data.get("MarketCapitalization")),
                "pe_ratio": self._safe_float(data.get("PERatio")),
                "peg_ratio": self._safe_float(data.get("PEGRatio")),
                "pb_ratio": self._safe_float(data.get("PriceToBookRatio")),
                "ps_ratio": self._safe_float(data.get("PriceToSalesRatioTTM")),
                "ev_revenue": self._safe_float(data.get("EVToRevenue")),
                "ev_ebitda": self._safe_float(data.get("EVToEBITDA")),
                "beta": self._safe_float(data.get("Beta")),
                "dividend_yield": self._safe_float(data.get("DividendYield")),
                "eps": self._safe_float(data.get("EPS")),
                "revenue_ttm": self._safe_float(data.get("RevenueTTM")),
                "gross_profit_ttm": self._safe_float(data.get("GrossProfitTTM")),
                "diluted_eps_ttm": self._safe_float(data.get("DilutedEPSTTM")),
                "quarterly_earnings_growth_yoy": self._safe_float(data.get("QuarterlyEarningsGrowthYOY")),
                "quarterly_revenue_growth_yoy": self._safe_float(data.get("QuarterlyRevenueGrowthYOY")),
                "analyst_target_price": self._safe_float(data.get("AnalystTargetPrice")),
                "52_week_high": self._safe_float(data.get("52WeekHigh")),
                "52_week_low": self._safe_float(data.get("52WeekLow")),
                "50_day_ma": self._safe_float(data.get("50DayMovingAverage")),
                "200_day_ma": self._safe_float(data.get("200DayMovingAverage")),
                "shares_outstanding": self._safe_float(data.get("SharesOutstanding")),
                "book_value": self._safe_float(data.get("BookValue")),
                "profit_margin": self._safe_float(data.get("ProfitMargin")),
                "operating_margin_ttm": self._safe_float(data.get("OperatingMarginTTM")),
                "return_on_assets_ttm": self._safe_float(data.get("ReturnOnAssetsTTM")),
                "return_on_equity_ttm": self._safe_float(data.get("ReturnOnEquityTTM")),
                "revenue_per_share_ttm": self._safe_float(data.get("RevenuePerShareTTM")),
                "forward_pe": self._safe_float(data.get("ForwardPE")),
                "trailing_pe": self._safe_float(data.get("TrailingPE")),
            }
            
            # Remove None values
            return {k: v for k, v in normalized.items() if v is not None}
            
        except Exception as e:
            self.logger.error("overview_parsing_failed", error=str(e))
            return {"symbol": data.get("Symbol"), "raw_data": data}
    
    def _safe_float(self, value: str) -> Optional[float]:
        """Safely convert string to float."""
        if not value or value == "None" or value == "-":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    async def get_rate_limit_stats(self) -> Dict[str, Any]:
        """Get current rate limiting statistics."""
        return self.rate_limiter.get_stats("alpha_vantage")


# Global client instance
_client: Optional[AlphaVantageClient] = None


async def get_alpha_vantage_client() -> AlphaVantageClient:
    """Get global Alpha Vantage client instance."""
    global _client
    if _client is None:
        _client = AlphaVantageClient()
    return _client