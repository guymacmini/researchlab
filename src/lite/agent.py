"""Simplified research agent for ResearchLab LITE."""

import asyncio
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

import httpx
import pandas as pd
from anthropic import AsyncAnthropic
import finnhub
import structlog

from .config import settings
from .database import get_db, Research, Company, cache

logger = structlog.get_logger()


class ResearchAgent:
    """Simplified research agent with core functionality."""
    
    def __init__(self):
        self.anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.finnhub_client = finnhub.Client(api_key=settings.finnhub_api_key)
        self.session = httpx.AsyncClient()
    
    async def research_company(self, query: str) -> Dict[str, Any]:
        """Research a company based on query."""
        logger.info("Starting company research", query=query)
        
        try:
            # Extract company symbol/name from query
            symbol = await self._extract_symbol(query)
            
            # Gather basic company data
            company_data = await self._get_company_data(symbol)
            
            # Get recent news and sentiment
            news_data = await self._get_news_data(symbol)
            
            # Analyze with AI
            analysis = await self._analyze_with_ai(query, company_data, news_data)
            
            # Compile results
            results = {
                "query": query,
                "symbol": symbol,
                "company_data": company_data,
                "news_data": news_data,
                "analysis": analysis,
                "timestamp": datetime.utcnow().isoformat(),
                "status": "completed"
            }
            
            # Save to database
            async with get_db() as db:
                research = Research(
                    query=query,
                    status="completed", 
                    results=json.dumps(results)
                )
                db.add(research)
                await db.commit()
                results["id"] = research.id
            
            logger.info("Research completed", query=query, symbol=symbol)
            return results
            
        except Exception as e:
            logger.error("Research failed", query=query, error=str(e))
            
            # Save failed result
            async with get_db() as db:
                research = Research(
                    query=query,
                    status="failed",
                    results=json.dumps({"error": str(e), "timestamp": datetime.utcnow().isoformat()})
                )
                db.add(research)
                await db.commit()
            
            raise
    
    async def _extract_symbol(self, query: str) -> str:
        """Extract stock symbol from query using AI."""
        cache_key = f"symbol_extraction:{query}"
        cached = await cache.get(cache_key)
        if cached:
            return cached
        
        prompt = f"""
        Extract the stock ticker symbol from this research query. If no specific symbol is mentioned, 
        try to identify the most likely company being referenced.
        
        Query: {query}
        
        Respond with just the ticker symbol (e.g. "AAPL", "MSFT", "TSLA").
        If you cannot determine a symbol, respond with "UNKNOWN".
        """
        
        response = await self.anthropic.messages.create(
            model="claude-3-haiku-20240307",  # Use faster model for symbol extraction
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}]
        )
        
        symbol = response.content[0].text.strip().upper()
        if symbol != "UNKNOWN":
            await cache.set(cache_key, symbol, ttl_seconds=3600)  # Cache for 1 hour
        
        return symbol
    
    async def _get_company_data(self, symbol: str) -> Dict[str, Any]:
        """Get basic company data from Finnhub."""
        cache_key = f"company_data:{symbol}"
        cached = await cache.get(cache_key)
        if cached:
            return json.loads(cached)
        
        try:
            # Company profile
            profile = self.finnhub_client.company_profile2(symbol=symbol)
            
            # Basic financials
            metrics = self.finnhub_client.company_basic_financials(symbol, 'all')
            
            # Recent quote
            quote = self.finnhub_client.quote(symbol)
            
            data = {
                "symbol": symbol,
                "profile": profile,
                "metrics": metrics,
                "quote": quote,
                "retrieved_at": datetime.utcnow().isoformat()
            }
            
            # Cache for 15 minutes
            await cache.set(cache_key, json.dumps(data), ttl_seconds=900)
            
            # Save to companies table
            async with get_db() as db:
                company = Company(
                    symbol=symbol,
                    name=profile.get('name'),
                    sector=profile.get('finnhubIndustry'),
                    data=json.dumps(data)
                )
                await db.merge(company)  # Insert or update
                await db.commit()
            
            return data
            
        except Exception as e:
            logger.error("Failed to get company data", symbol=symbol, error=str(e))
            return {"error": str(e), "symbol": symbol}
    
    async def _get_news_data(self, symbol: str) -> Dict[str, Any]:
        """Get recent news for the company."""
        cache_key = f"news_data:{symbol}"
        cached = await cache.get(cache_key)
        if cached:
            return json.loads(cached)
        
        try:
            # Get news from past week
            from_date = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d')
            to_date = datetime.utcnow().strftime('%Y-%m-%d')
            
            news = self.finnhub_client.company_news(symbol, _from=from_date, to=to_date)
            
            # Limit to top 10 most recent articles
            recent_news = sorted(news, key=lambda x: x.get('datetime', 0), reverse=True)[:10]
            
            data = {
                "symbol": symbol,
                "articles": recent_news,
                "count": len(recent_news),
                "retrieved_at": datetime.utcnow().isoformat()
            }
            
            # Cache for 30 minutes
            await cache.set(cache_key, json.dumps(data), ttl_seconds=1800)
            
            return data
            
        except Exception as e:
            logger.error("Failed to get news data", symbol=symbol, error=str(e))
            return {"error": str(e), "symbol": symbol, "articles": []}
    
    async def _analyze_with_ai(self, query: str, company_data: Dict, news_data: Dict) -> Dict[str, Any]:
        """Analyze company data with AI."""
        
        # Prepare data summary
        company_profile = company_data.get('profile', {})
        company_metrics = company_data.get('metrics', {})
        company_quote = company_data.get('quote', {})
        news_articles = news_data.get('articles', [])
        
        # Build analysis prompt
        prompt = f"""
        You are a financial analyst. Analyze this company based on the provided data and answer the research query.
        
        RESEARCH QUERY: {query}
        
        COMPANY: {company_profile.get('name', 'Unknown')} ({company_data.get('symbol', '')})
        
        BASIC INFO:
        - Sector: {company_profile.get('finnhubIndustry', 'Unknown')}
        - Country: {company_profile.get('country', 'Unknown')}  
        - Market Cap: {company_profile.get('marketCapitalization', 'Unknown')}
        
        CURRENT STOCK PRICE: ${company_quote.get('c', 'N/A')}
        - Change: {company_quote.get('d', 'N/A')} ({company_quote.get('dp', 'N/A')}%)
        - 52-week High: ${company_quote.get('h', 'N/A')}
        - 52-week Low: ${company_quote.get('l', 'N/A')}
        
        RECENT NEWS HEADLINES ({len(news_articles)} articles):
        {chr(10).join([f"- {article.get('headline', 'No headline')}" for article in news_articles[:5]])}
        
        FINANCIAL METRICS:
        {json.dumps(company_metrics.get('metric', {}), indent=2) if company_metrics.get('metric') else 'No metrics available'}
        
        Provide a comprehensive analysis addressing:
        1. Company overview and business model
        2. Financial health and key metrics
        3. Recent developments and news sentiment
        4. Investment thesis (bullish/bearish factors)
        5. Risks and opportunities
        6. Direct answer to the research query
        
        Format your response as a structured analysis with clear sections.
        """
        
        try:
            response = await self.anthropic.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=2000,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}]
            )
            
            analysis_text = response.content[0].text
            
            return {
                "analysis_text": analysis_text,
                "data_sources": ["finnhub", "anthropic_claude"],
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error("AI analysis failed", error=str(e))
            return {
                "error": f"Analysis failed: {str(e)}",
                "analysis_text": "Unable to generate analysis due to an error.",
                "generated_at": datetime.utcnow().isoformat()
            }
    
    async def get_clarifying_questions(self, query: str) -> List[str]:
        """Generate clarifying questions for a research query."""
        
        prompt = f"""
        A user wants to research: "{query}"
        
        Generate 3-5 clarifying questions that would help provide better, more targeted research.
        Focus on:
        - Specific aspects they want to analyze
        - Time horizon for the analysis  
        - Risk tolerance or investment goals
        - Specific metrics or factors they care about
        
        Return questions as a simple bullet list, one per line.
        """
        
        try:
            response = await self.anthropic.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            
            questions_text = response.content[0].text.strip()
            questions = [q.strip().lstrip('•-* ') for q in questions_text.split('\n') if q.strip()]
            
            return questions[:5]  # Max 5 questions
            
        except Exception as e:
            logger.error("Failed to generate clarifying questions", error=str(e))
            return [
                "What specific time horizon are you considering for this investment?",
                "Are you more interested in growth potential or dividend income?",
                "What level of risk are you comfortable with?",
                "Are there specific financial metrics you want to focus on?"
            ]
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.session.aclose()


# Global agent instance
agent = ResearchAgent()