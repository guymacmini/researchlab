"""Finnhub API client with rate limiting and caching."""

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


class FinnhubAPIError(Exception):
    """Finnhub API specific error."""
    def __init__(self, message: str, status_code: Optional[int] = None, response: Optional[Dict] = None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(message)


class FinnhubClient:
    """Async Finnhub API client with rate limiting and caching."""
    
    BASE_URL = "https://finnhub.io/api/v1"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        rate_limiter: Optional[AsyncRateLimiter] = None,
        cache: Optional[DataCache] = None
    ):
        self.api_key = api_key or settings.api.finnhub_api_key
        if not self.api_key:
            raise ValueError("Finnhub API key is required")
        
        self.rate_limiter = rate_limiter or AsyncRateLimiter()
        self.cache = cache or DataCache()
        
        # Set up rate limiting (Finnhub free tier: 60 requests/minute)
        self.rate_limiter.set_limit(
            "finnhub",
            RateLimit(
                requests_per_minute=settings.api.finnhub_rate_limit,
                requests_per_hour=3600,  # Conservative estimate
                burst_size=10  # Allow small bursts
            )
        )
        
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                'X-Finnhub-Token': self.api_key,
                'User-Agent': f'ResearchLab/{settings.app.version}'
            }
        )
        
        self.logger = logger.bind(component="finnhub_client")
    
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
    async def _make_request(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make rate-limited API request with retries."""
        # Apply rate limiting
        await self.rate_limiter.acquire("finnhub")
        
        # Build URL and make request
        url = f"{self.BASE_URL}/{endpoint}"
        params = params or {}
        
        try:
            self.logger.debug("api_request", endpoint=endpoint, params=params)
            
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # Check for API-level errors
            if isinstance(data, dict) and data.get('error'):
                raise FinnhubAPIError(
                    f"API error: {data['error']}", 
                    status_code=response.status_code,
                    response=data
                )
            
            return data
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                # Rate limited - wait and retry
                self.logger.warning("rate_limited_by_api", endpoint=endpoint)
                await asyncio.sleep(61)  # Wait just over a minute
                raise
            elif e.response.status_code == 401:
                raise FinnhubAPIError("Invalid API key", status_code=401)
            elif e.response.status_code == 403:
                raise FinnhubAPIError("API access forbidden", status_code=403)
            else:
                raise FinnhubAPIError(
                    f"HTTP error {e.response.status_code}: {e.response.text}",
                    status_code=e.response.status_code
                )
        
        except Exception as e:
            self.logger.error("api_request_failed", endpoint=endpoint, error=str(e))
            raise FinnhubAPIError(f"Request failed: {str(e)}")
    
    async def _cached_request(
        self,
        endpoint: str,
        params: Dict[str, Any] = None,
        cache_ttl: int = None,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Make cached API request."""
        params = params or {}
        cache_key = cache_key_for_api_call("finnhub", endpoint, **params)
        
        # Check cache first (unless force refresh)
        if not force_refresh:
            cached_data = await self.cache.get(cache_key)
            if cached_data is not None:
                self.logger.debug("cache_hit", endpoint=endpoint)
                return cached_data
        
        # Make API request
        data = await self._make_request(endpoint, params)
        
        # Cache the result
        ttl = cache_ttl or CACHE_TTL.get(endpoint.split('/')[0], CACHE_TTL['default'])
        await self.cache.set(
            cache_key,
            data,
            ttl_seconds=ttl,
            source="finnhub",
            tags=["finnhub", endpoint.split('/')[0]]
        )
        
        return data
    
    async def get_quote(self, symbol: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Get real-time stock quote."""
        return await self._cached_request(
            "quote",
            {"symbol": symbol.upper()},
            cache_ttl=CACHE_TTL['stock_quote'],
            force_refresh=force_refresh
        )
    
    async def get_company_profile(self, symbol: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Get company profile information."""
        return await self._cached_request(
            "stock/profile2",
            {"symbol": symbol.upper()},
            cache_ttl=CACHE_TTL['company_profile'],
            force_refresh=force_refresh
        )
    
    async def get_company_news(
        self,
        symbol: str,
        from_date: str,
        to_date: str,
        force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """Get company news."""
        data = await self._cached_request(
            "company-news",
            {
                "symbol": symbol.upper(),
                "from": from_date,
                "to": to_date
            },
            cache_ttl=CACHE_TTL['news'],
            force_refresh=force_refresh
        )
        
        return data if isinstance(data, list) else []
    
    async def get_financials_reported(
        self,
        symbol: str,
        freq: str = "quarterly",
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Get reported financials."""
        return await self._cached_request(
            "stock/financials-reported",
            {"symbol": symbol.upper(), "freq": freq},
            cache_ttl=CACHE_TTL['financial_statements'],
            force_refresh=force_refresh
        )
    
    async def get_basic_financials(
        self,
        symbol: str,
        metric: str = "all",
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Get basic financial metrics."""
        return await self._cached_request(
            "stock/metric",
            {"symbol": symbol.upper(), "metric": metric},
            cache_ttl=CACHE_TTL['financial_statements'],
            force_refresh=force_refresh
        )
    
    async def get_earnings(self, symbol: str, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Get earnings data."""
        data = await self._cached_request(
            "stock/earnings",
            {"symbol": symbol.upper()},
            cache_ttl=CACHE_TTL['financial_statements'],
            force_refresh=force_refresh
        )
        
        return data if isinstance(data, list) else []
    
    async def get_recommendation_trends(
        self,
        symbol: str,
        force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """Get analyst recommendation trends."""
        data = await self._cached_request(
            "stock/recommendation",
            {"symbol": symbol.upper()},
            cache_ttl=CACHE_TTL['analyst_estimates'],
            force_refresh=force_refresh
        )
        
        return data if isinstance(data, list) else []
    
    async def get_price_target(self, symbol: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Get analyst price targets."""
        return await self._cached_request(
            "stock/price-target",
            {"symbol": symbol.upper()},
            cache_ttl=CACHE_TTL['analyst_estimates'],
            force_refresh=force_refresh
        )
    
    async def get_company_peers(self, symbol: str, force_refresh: bool = False) -> List[str]:
        """Get company peers."""
        data = await self._cached_request(
            "stock/peers",
            {"symbol": symbol.upper()},
            cache_ttl=CACHE_TTL['company_profile'],
            force_refresh=force_refresh
        )
        
        return data if isinstance(data, list) else []
    
    async def search_symbol(self, query: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Search for symbols."""
        return await self._cached_request(
            "search",
            {"q": query},
            cache_ttl=CACHE_TTL['default'],
            force_refresh=force_refresh
        )
    
    async def get_market_news(
        self,
        category: str = "general",
        min_id: str = None,
        force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """Get market news."""
        params = {"category": category}
        if min_id:
            params["minId"] = min_id
        
        data = await self._cached_request(
            "news",
            params,
            cache_ttl=CACHE_TTL['news'],
            force_refresh=force_refresh
        )
        
        return data if isinstance(data, list) else []
    
    async def get_company_executive(self, symbol: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Get company executives."""
        return await self._cached_request(
            "stock/executive",
            {"symbol": symbol.upper()},
            cache_ttl=CACHE_TTL['company_profile'],
            force_refresh=force_refresh
        )
    
    async def batch_quotes(self, symbols: List[str], force_refresh: bool = False) -> Dict[str, Dict[str, Any]]:
        """Get quotes for multiple symbols efficiently."""
        # For small batches, make concurrent requests
        if len(symbols) <= 10:
            tasks = [self.get_quote(symbol, force_refresh) for symbol in symbols]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            quotes = {}
            for symbol, result in zip(symbols, results):
                if isinstance(result, Exception):
                    self.logger.error("batch_quote_failed", symbol=symbol, error=str(result))
                    quotes[symbol] = None
                else:
                    quotes[symbol] = result
            
            return quotes
        
        # For larger batches, process in chunks to respect rate limits
        quotes = {}
        chunk_size = 10
        
        for i in range(0, len(symbols), chunk_size):
            chunk = symbols[i:i + chunk_size]
            chunk_quotes = await self.batch_quotes(chunk, force_refresh)
            quotes.update(chunk_quotes)
            
            # Small delay between chunks
            if i + chunk_size < len(symbols):
                await asyncio.sleep(1)
        
        return quotes
    
    async def get_rate_limit_stats(self) -> Dict[str, Any]:
        """Get current rate limiting statistics."""
        return self.rate_limiter.get_stats("finnhub")


# Global client instance
_client: Optional[FinnhubClient] = None


async def get_finnhub_client() -> FinnhubClient:
    """Get global Finnhub client instance."""
    global _client
    if _client is None:
        _client = FinnhubClient()
    return _client