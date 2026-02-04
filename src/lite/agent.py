"""Simplified research agent for ResearchLab LITE."""

import asyncio
import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum

import httpx
import pandas as pd
from anthropic import AsyncAnthropic
import finnhub
import structlog

from .config import settings
from .database import get_db, Research, Company, cache

logger = structlog.get_logger()


class QueryType(Enum):
    """Types of research queries."""
    SPECIFIC_COMPANY = "specific_company"  # "Should I buy NVIDIA?"
    THEMATIC = "thematic"  # "What companies benefit from AI boom?"
    COMPARISON = "comparison"  # "Tesla vs Rivian"


class ConversationState(Enum):
    """States in the research conversation flow."""
    INITIAL_QUERY = "initial_query"
    CLARIFYING_QUESTIONS = "clarifying_questions"
    COMPANY_IDENTIFICATION = "company_identification"  
    ANALYSIS_COMPLETE = "analysis_complete"


class ResearchAgent:
    """Simplified research agent with core functionality."""
    
    def __init__(self):
        self.anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.finnhub_client = finnhub.Client(api_key=settings.finnhub_api_key)
        self.session = httpx.AsyncClient()
        self.conversation_states = {}  # Track conversation state by session
    
    async def start_conversation(self, query: str, session_id: str = "default") -> Dict[str, Any]:
        """Start a new research conversation or continue an existing one."""
        logger.info("Starting research conversation", query=query, session_id=session_id)
        
        try:
            # Classify the query type
            query_type = await self._classify_query(query)
            
            # If it's a specific company query, skip clarifying questions
            if query_type == QueryType.SPECIFIC_COMPANY:
                logger.info("Specific company query detected, proceeding directly to analysis")
                return await self.research_company(query)
            
            # For thematic/comparison queries, start with clarifying questions
            clarifying_questions = await self._generate_clarifying_questions(query, query_type)
            
            # Store conversation state
            self.conversation_states[session_id] = {
                "state": ConversationState.CLARIFYING_QUESTIONS,
                "original_query": query,
                "query_type": query_type,
                "questions": clarifying_questions,
                "answers": {},
                "timestamp": datetime.utcnow().isoformat()
            }
            
            return {
                "conversation_id": session_id,
                "state": ConversationState.CLARIFYING_QUESTIONS.value,
                "original_query": query,
                "query_type": query_type.value,
                "clarifying_questions": clarifying_questions,
                "message": "I have some clarifying questions to provide better, more targeted analysis.",
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error("Failed to start conversation", query=query, error=str(e))
            # Fallback to old behavior
            return await self.research_company(query)
    
    async def continue_conversation(self, session_id: str, answers: Dict[str, str]) -> Dict[str, Any]:
        """Continue conversation with answers to clarifying questions."""
        if session_id not in self.conversation_states:
            raise ValueError("Invalid session ID or session expired")
        
        state = self.conversation_states[session_id]
        
        if state["state"] != ConversationState.CLARIFYING_QUESTIONS:
            raise ValueError("Invalid conversation state")
        
        # Store answers
        state["answers"] = answers
        state["state"] = ConversationState.COMPANY_IDENTIFICATION
        
        # Identify relevant companies based on query and answers
        companies = await self._identify_companies_for_theme(
            state["original_query"], 
            state["query_type"],
            answers
        )
        
        if not companies:
            raise ValueError("Could not identify relevant companies for analysis")
        
        # Perform thematic analysis
        analysis = await self._perform_thematic_analysis(
            state["original_query"],
            answers, 
            companies
        )
        
        # Update state
        state["state"] = ConversationState.ANALYSIS_COMPLETE
        state["companies"] = companies
        state["analysis"] = analysis
        
        # Clean up session (optional - could keep for history)
        # del self.conversation_states[session_id]
        
        return {
            "conversation_id": session_id,
            "state": ConversationState.ANALYSIS_COMPLETE.value,
            "original_query": state["original_query"],
            "answers": answers,
            "companies_analyzed": companies,
            "analysis": analysis,
            "timestamp": datetime.utcnow().isoformat()
        }

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
    
    async def _classify_query(self, query: str) -> QueryType:
        """Classify the type of research query."""
        cache_key = f"query_classification:{query}"
        cached = await cache.get(cache_key)
        if cached:
            return QueryType(cached)
        
        prompt = f"""
        Classify this research query into one of these categories:

        1. SPECIFIC_COMPANY: Asks about a specific, named company (e.g., "Should I buy Apple?", "Analyze Tesla stock", "NVDA outlook")
        2. THEMATIC: Asks about companies in a theme, sector, or trend (e.g., "AI stocks", "companies benefiting from war", "best EV stocks")
        3. COMPARISON: Compares 2+ specific companies (e.g., "Tesla vs Rivian", "Apple vs Microsoft")

        Query: "{query}"

        Respond with exactly one word: SPECIFIC_COMPANY, THEMATIC, or COMPARISON
        """
        
        response = await self.anthropic.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=20,
            messages=[{"role": "user", "content": prompt}]
        )
        
        classification = response.content[0].text.strip().upper()
        
        # Map to enum, default to THEMATIC if unclear
        if "SPECIFIC_COMPANY" in classification:
            result = QueryType.SPECIFIC_COMPANY
        elif "COMPARISON" in classification:
            result = QueryType.COMPARISON  
        else:
            result = QueryType.THEMATIC
        
        # Cache for 1 hour
        await cache.set(cache_key, result.value, ttl_seconds=3600)
        
        return result
    
    async def _generate_clarifying_questions(self, query: str, query_type: QueryType) -> List[str]:
        """Generate clarifying questions based on query type."""
        
        if query_type == QueryType.THEMATIC:
            prompt = f"""
            User asked: "{query}"
            
            This is a thematic investment query. Generate 2-4 clarifying questions that help scope the analysis:
            
            Focus on:
            - Investment time horizon (short-term, long-term)
            - Risk tolerance / investment style
            - Specific sectors or aspects to prioritize
            - Geographic focus if relevant
            - Position size / portfolio allocation
            
            Return questions as a simple list, one per line, no bullets.
            Make them conversational and practical.
            """
        elif query_type == QueryType.COMPARISON:
            prompt = f"""
            User asked: "{query}"
            
            This is a comparison query. Generate 2-3 clarifying questions:
            
            Focus on:
            - What specific aspects to compare (growth, valuation, risk, etc.)
            - Investment time horizon  
            - Whether this is for portfolio allocation
            
            Return questions as a simple list, one per line, no bullets.
            """
        else:
            # Fallback 
            prompt = f"""
            Generate 3 clarifying questions for: "{query}"
            
            Focus on time horizon, risk tolerance, and specific analysis focus.
            Return as simple list, one per line, no bullets.
            """
        
        try:
            response = await self.anthropic.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            
            questions_text = response.content[0].text.strip()
            questions = [q.strip() for q in questions_text.split('\n') if q.strip()]
            
            return questions[:4]  # Max 4 questions
            
        except Exception as e:
            logger.error("Failed to generate clarifying questions", error=str(e))
            # Fallback questions based on query type
            if query_type == QueryType.THEMATIC:
                return [
                    "What time horizon are you considering (short-term momentum vs long-term growth)?",
                    "Are you looking for growth stocks, dividend income, or a balanced approach?",
                    "What's your risk tolerance for this investment theme?"
                ]
            else:
                return [
                    "What specific time horizon are you considering?",
                    "What aspects are most important to compare?"
                ]
    
    async def _identify_companies_for_theme(self, query: str, query_type: QueryType, answers: Dict[str, str]) -> List[Dict[str, str]]:
        """Identify 3-5 relevant companies for thematic analysis."""
        
        # Combine query and answers for context
        context = f"Original query: {query}\n\n"
        if answers:
            context += "User preferences:\n"
            for q, a in answers.items():
                context += f"- {q}: {a}\n"
        
        prompt = f"""
        {context}
        
        Based on this thematic investment query and user preferences, identify 3-5 most relevant publicly traded companies to analyze.
        
        For each company, provide:
        1. Ticker symbol (must be accurate)
        2. Company name  
        3. Brief rationale (1 sentence why it fits the theme)
        
        Focus on:
        - Companies with good liquidity/market cap (avoid penny stocks)
        - Clear connection to the investment theme
        - Diversification across sub-themes or approaches
        
        Format as JSON array:
        [
          {{"ticker": "AAPL", "name": "Apple Inc.", "rationale": "Dominant player in consumer electronics with strong ecosystem."}},
          {{"ticker": "MSFT", "name": "Microsoft Corp.", "rationale": "Leading cloud provider benefiting from digital transformation."}}
        ]
        
        Return ONLY the JSON array, no other text.
        """
        
        try:
            response = await self.anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}]
            )
            
            companies_text = response.content[0].text.strip()
            
            # Extract JSON from response
            import re
            json_match = re.search(r'\[.*\]', companies_text, re.DOTALL)
            if json_match:
                companies = json.loads(json_match.group())
                
                # Validate structure
                for company in companies:
                    if not all(k in company for k in ["ticker", "name", "rationale"]):
                        logger.warning("Invalid company structure", company=company)
                        continue
                
                logger.info("Identified companies for theme", count=len(companies), companies=[c["ticker"] for c in companies])
                return companies[:5]  # Max 5 companies
            
        except Exception as e:
            logger.error("Failed to identify companies", error=str(e))
        
        # Fallback - return empty list (will trigger error in caller)
        return []
    
    async def _perform_thematic_analysis(self, query: str, answers: Dict[str, str], companies: List[Dict[str, str]]) -> Dict[str, Any]:
        """Perform comprehensive thematic analysis across multiple companies."""
        
        # Get data for all companies
        company_data = {}
        for company in companies:
            ticker = company["ticker"]
            try:
                data = await self._get_company_data(ticker)
                news = await self._get_news_data(ticker)
                company_data[ticker] = {
                    "info": company,
                    "financial_data": data,
                    "news": news
                }
            except Exception as e:
                logger.warning("Failed to get data for company", ticker=ticker, error=str(e))
                company_data[ticker] = {
                    "info": company,
                    "financial_data": {"error": str(e)},
                    "news": {"articles": []}
                }
        
        # Generate comprehensive thematic analysis
        analysis_text = await self._generate_thematic_analysis(query, answers, company_data)
        
        return {
            "analysis_text": analysis_text,
            "company_data": company_data,
            "companies_analyzed": companies,
            "data_sources": ["finnhub", "anthropic_claude"],
            "generated_at": datetime.utcnow().isoformat()
        }
    
    async def _generate_thematic_analysis(self, query: str, answers: Dict[str, str], company_data: Dict) -> str:
        """Generate comprehensive AI analysis for thematic research."""
        
        # Build context with all company data
        context = f"RESEARCH QUERY: {query}\n\n"
        
        if answers:
            context += "USER PREFERENCES:\n"
            for q, a in answers.items():
                context += f"- {q}: {a}\n"
            context += "\n"
        
        context += "=== COMPANIES TO ANALYZE ===\n"
        
        for ticker, data in company_data.items():
            info = data["info"]
            financial = data["financial_data"]
            news = data["news"]
            
            context += f"\n{ticker} - {info['name']}\n"
            context += f"Rationale: {info['rationale']}\n"
            
            # Add key financial metrics
            if "profile" in financial:
                profile = financial["profile"]
                context += f"Sector: {profile.get('finnhubIndustry', 'Unknown')}\n"
                context += f"Market Cap: ${profile.get('marketCapitalization', 'Unknown')}M\n"
            
            if "quote" in financial:
                quote = financial["quote"]
                context += f"Price: ${quote.get('c', 'N/A')}\n"
                context += f"Change: {quote.get('d', 'N/A')} ({quote.get('dp', 'N/A')}%)\n"
            
            if "metrics" in financial and financial["metrics"].get("metric"):
                metrics = financial["metrics"]["metric"]
                pe = metrics.get('peBasicExclExtraTTM', 'N/A')
                roe = metrics.get('roeTTM', 'N/A')
                context += f"P/E: {pe}, ROE: {roe}%\n"
            
            # Add recent news headlines
            if news.get("articles"):
                context += "Recent News:\n"
                for article in news["articles"][:3]:
                    context += f"• {article.get('headline', 'No headline')}\n"
        
        # Generate comprehensive analysis prompt
        prompt = f"""
        {context}
        
        You are a senior portfolio manager at a top investment fund. Provide COMPREHENSIVE, QUANTIFIED thematic analysis.
        
        Structure your analysis exactly as follows:
        
        ## 1. THESIS SUMMARY
        - Clear 2-3 sentence investment thesis
        - Key macro drivers and timeline
        - Expected return potential with confidence level (X/10)
        
        ## 2. THEMATIC ANALYSIS
        - Why this theme matters now (quantified drivers)
        - Market size and growth rates
        - Key risks to the thesis
        
        ## 3. SECTOR BREAKDOWN
        - Which sectors benefit most and why
        - Estimated revenue impact by sector
        - Competitive dynamics
        
        ## 4. INDIVIDUAL COMPANY ANALYSIS
        For EACH company, provide:
        
        ### [TICKER] - [Company Name]
        **Investment Rating: BUY/HOLD/SELL (Confidence: X/10)**
        **12-Month Target: $XXX (XX% upside/downside)**
        
        **Why it fits the theme:**
        - Specific business exposure to the theme
        - Revenue % from relevant segments
        
        **Valuation:**
        - Current vs historical/peer multiples
        - Is it cheap/fair/expensive for the growth?
        
        **Key Risks (exactly 2):**
        1. [Risk 1 with severity X/10]: [Description]
        2. [Risk 2 with severity X/10]: [Description]
        
        **Catalyst Timeline:**
        - Next 3 months: [Specific catalyst]
        - 6-12 months: [Major catalyst]
        
        ## 5. PORTFOLIO CONSTRUCTION
        - Recommended allocation across companies
        - Position sizing based on conviction/risk
        - Hedging strategies if applicable
        - What would make you change the thesis?
        
        ## 6. ACTIONABLE SUMMARY
        - Clear BUY/AVOID list with entry prices
        - Timeline for investment thesis to play out
        - Key metrics to monitor monthly
        
        CRITICAL RULES:
        1. Every claim needs a NUMBER - no vague terms
        2. State confidence levels for uncertain estimates  
        3. Be genuinely critical in risk analysis
        4. Address the user's specific preferences from their answers
        5. Make it actionable - specific prices, allocations, timeframes
        """
        
        try:
            response = await self.anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=6000,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}]
            )
            
            return response.content[0].text
            
        except Exception as e:
            logger.error("Failed to generate thematic analysis", error=str(e))
            return f"Analysis generation failed: {str(e)}"

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
            model="claude-3-5-haiku-20241022",  # Use faster model for symbol extraction
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
            
            # Save to companies table with proper upsert
            async with get_db() as db:
                from sqlalchemy import select
                # Check if company exists
                result = await db.execute(select(Company).where(Company.symbol == symbol))
                existing_company = result.scalar_one_or_none()
                
                if existing_company:
                    # Update existing company
                    existing_company.name = profile.get('name')
                    existing_company.sector = profile.get('finnhubIndustry')
                    existing_company.data = json.dumps(data)
                    existing_company.last_updated = datetime.utcnow()
                else:
                    # Create new company
                    company = Company(
                        symbol=symbol,
                        name=profile.get('name'),
                        sector=profile.get('finnhubIndustry'),
                        data=json.dumps(data)
                    )
                    db.add(company)
                
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
        
        # Extract key metrics for analysis
        metrics = company_metrics.get('metric', {})
        pe_ratio = metrics.get('peBasicExclExtraTTM', metrics.get('peTTM', 'N/A'))
        pb_ratio = metrics.get('pbQuarterly', 'N/A')
        ps_ratio = metrics.get('psAnnual', 'N/A')
        roe = metrics.get('roeTTM', 'N/A')
        debt_equity = metrics.get('totalDebt/totalEquityQuarterly', 'N/A')
        revenue_growth = metrics.get('revenueGrowthTTMYoy', 'N/A')
        eps_growth = metrics.get('epsGrowthTTMYoy', 'N/A')
        gross_margin = metrics.get('grossMarginTTM', 'N/A')
        dividend_yield = metrics.get('dividendYieldIndicatedAnnual', 'N/A')
        beta = metrics.get('beta', 'N/A')
        
        # Build rigorous analysis prompt (first principles)
        prompt = f"""You are a senior investment analyst at a top hedge fund. Provide RIGOROUS, QUANTIFIED analysis.

RESEARCH QUERY: {query}

=== COMPANY DATA ===
Company: {company_profile.get('name', 'Unknown')} ({company_data.get('symbol', '')})
Sector: {company_profile.get('finnhubIndustry', 'Unknown')}
Country: {company_profile.get('country', 'Unknown')}
Market Cap: ${company_profile.get('marketCapitalization', 'Unknown')}M

=== CURRENT PRICE ===
Price: ${company_quote.get('c', 'N/A')}
Daily Change: {company_quote.get('d', 'N/A')} ({company_quote.get('dp', 'N/A')}%)
52W High: ${company_quote.get('h', 'N/A')} | 52W Low: ${company_quote.get('l', 'N/A')}

=== VALUATION METRICS ===
P/E Ratio: {pe_ratio} | P/B: {pb_ratio} | P/S: {ps_ratio}
Dividend Yield: {dividend_yield}%

=== FINANCIAL HEALTH ===
ROE: {roe}% | Gross Margin: {gross_margin}%
Debt/Equity: {debt_equity} | Beta: {beta}
Revenue Growth (YoY): {revenue_growth}% | EPS Growth (YoY): {eps_growth}%

=== RECENT NEWS ({len(news_articles)} articles) ===
{chr(10).join([f"• {article.get('headline', 'No headline')}" for article in news_articles[:5]])}

=== ANALYSIS REQUIREMENTS ===
You MUST provide ALL of the following sections with SPECIFIC NUMBERS:

## 1. EXECUTIVE SUMMARY (2-3 sentences)
- Clear BUY/HOLD/SELL recommendation with confidence level (X/10)
- 12-month price target with % upside/downside
- One-sentence thesis

## 2. QUANTIFIED BUSINESS ANALYSIS
- Revenue breakdown by segment (estimate % if not provided)
- Competitive position: market share, key advantages, moat durability
- Growth drivers with specific metrics
- NO VAGUE TERMS like "strong" or "good" - USE NUMBERS

## 3. VALUATION ANALYSIS
- Compare P/E, P/B, P/S to sector averages (estimate if needed)
- Is it cheap/fair/expensive vs history and peers?
- Calculate implied growth rate from current multiple

## 4. RISK ANALYSIS (MANDATORY - list exactly 3 risks)
Each risk must include:
- Risk Factor [N] (Severity: X/10): [Description]
- Quantified impact if risk materializes
Example: "Risk Factor 1 (Severity: 7/10): Customer concentration - top 3 customers = 45% revenue"

## 5. CONTRARIAN ANALYSIS (MANDATORY - devil's advocate)
- What is the BEAR CASE? Why might this investment FAIL?
- What key assumption could be WRONG?
- What would make you SELL?
- Be genuinely critical, not just token skepticism

## 6. ACTIONABLE RECOMMENDATION
- Specific entry price (buy below $X)
- Stop loss level ($X, representing Y% downside)
- Position size recommendation (X% of portfolio)
- Key catalyst to watch with expected timing
- What metric would change your view?

CRITICAL RULES:
1. Every claim needs a NUMBER - no adjectives without quantification
2. State confidence levels for uncertain estimates
3. Contrarian section must be GENUINELY critical
4. Answer the specific research query directly at the end
"""
        
        try:
            response = await self.anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4000,
                temperature=0.2,
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
        """Legacy method for backward compatibility."""
        query_type = await self._classify_query(query)
        return await self._generate_clarifying_questions(query, query_type)
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.session.aclose()


# Global agent instance
agent = ResearchAgent()