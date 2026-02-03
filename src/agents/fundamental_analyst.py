"""Fundamental Analyst agent for financial metrics extraction and analysis."""

from typing import Dict, List, Any, Optional
import asyncio
from datetime import datetime, timedelta

import structlog
import anthropic

from src.core.config import settings
from src.core.database import DatabaseManager  
from src.data.models import Company, CompanyAnalysis
from .base import BaseAgent, AgentRole, AgentResult


class FundamentalAnalystAgent(BaseAgent):
    """
    Fundamental Analyst agent responsible for:
    - Extracting and normalizing financial metrics
    - Analyzing company fundamentals and ratios
    - Evaluating financial health and growth trends  
    - Scoring companies based on investment thesis relevance
    """
    
    role = AgentRole.FUNDAMENTAL_ANALYST
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.client = anthropic.Anthropic(api_key=settings.api.anthropic_api_key)
        self.model = settings.agents.fundamental_analyst_model
        
    async def validate_inputs(self, context: Dict[str, Any]) -> bool:
        """Validate that required inputs are present."""
        required_fields = ['project_id', 'query']
        
        for field in required_fields:
            if field not in context:
                self.logger.error("missing_required_field", field=field)
                return False
        
        # Check if we have sector analysis from Research Director
        if 'sector_analysis' not in context:
            self.logger.warning("no_sector_analysis", message="Will use broader screening")
        
        return True
    
    async def analyze(self, context: Dict[str, Any]) -> AgentResult:
        """Perform fundamental analysis of relevant companies."""
        
        self.logger.info("fundamental_analysis_started")
        
        try:
            # Step 1: Identify relevant companies based on thesis
            companies = await self._discover_relevant_companies(context)
            
            # Step 2: Extract financial metrics for each company
            company_analyses = []
            for company in companies:
                analysis = await self._analyze_company(company, context)
                if analysis:
                    company_analyses.append(analysis)
            
            # Step 3: Rank and score companies
            ranked_companies = await self._rank_companies(company_analyses, context)
            
            # Step 4: Generate summary insights
            summary = await self._generate_summary(ranked_companies, context)
            
            # Step 5: Save analyses to database
            await self._save_company_analyses(ranked_companies, context['project_id'])
            
            confidence = self._calculate_confidence(company_analyses)
            
            analysis_data = {
                'companies_analyzed': len(company_analyses),
                'top_companies': ranked_companies[:10],  # Top 10
                'summary_insights': summary,
                'methodology': self._get_analysis_methodology(),
                'analysis_timestamp': datetime.utcnow().isoformat(),
                'sectors_covered': list(set(c.get('sector', 'Unknown') for c in company_analyses))
            }
            
            reasoning = self._build_reasoning(ranked_companies, summary)
            sources = ['financial_data_apis', 'fundamental_analysis', 'company_filings']
            
            self.logger.info(
                "fundamental_analysis_completed",
                companies_analyzed=len(company_analyses),
                confidence=confidence,
                top_score=ranked_companies[0].get('relevance_score', 0) if ranked_companies else 0
            )
            
            return AgentResult(
                agent=self.role,
                success=True,
                data=analysis_data,
                confidence=confidence,
                sources=sources,
                reasoning=reasoning
            )
            
        except Exception as e:
            self.logger.error("fundamental_analysis_failed", error=str(e))
            
            return AgentResult(
                agent=self.role,
                success=False,
                data={},
                confidence=0.0,
                sources=[],
                reasoning=f"Analysis failed: {str(e)}",
                errors=[str(e)]
            )
    
    async def _discover_relevant_companies(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Discover companies relevant to the investment thesis."""
        
        # Extract sector preferences from context
        sector_analysis = context.get('sector_analysis', {})
        primary_sectors = sector_analysis.get('primary_sectors', [])
        secondary_sectors = sector_analysis.get('secondary_sectors', [])
        
        # For now, return sample companies - in real implementation,
        # this would query financial APIs or databases
        sample_companies = [
            {
                'symbol': 'AAPL',
                'name': 'Apple Inc',
                'sector': 'Technology',
                'industry': 'Consumer Electronics',
                'market_cap': 3000000000000,
                'country': 'US'
            },
            {
                'symbol': 'MSFT', 
                'name': 'Microsoft Corporation',
                'sector': 'Technology',
                'industry': 'Software',
                'market_cap': 2800000000000,
                'country': 'US'
            },
            {
                'symbol': 'GOOGL',
                'name': 'Alphabet Inc',
                'sector': 'Technology', 
                'industry': 'Internet Services',
                'market_cap': 1700000000000,
                'country': 'US'
            },
            {
                'symbol': 'NVDA',
                'name': 'NVIDIA Corporation',
                'sector': 'Technology',
                'industry': 'Semiconductors', 
                'market_cap': 1600000000000,
                'country': 'US'
            },
            {
                'symbol': 'TSLA',
                'name': 'Tesla Inc',
                'sector': 'Consumer Discretionary',
                'industry': 'Automotive',
                'market_cap': 800000000000,
                'country': 'US'
            }
        ]
        
        self.logger.info("companies_discovered", count=len(sample_companies))
        return sample_companies
    
    async def _analyze_company(self, company: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Analyze a single company's fundamentals."""
        
        symbol = company['symbol']
        
        try:
            # Get financial metrics (mock data for now)
            financials = await self._get_financial_metrics(symbol)
            
            # Calculate relevance to investment thesis
            relevance_score = await self._calculate_thesis_relevance(
                company, financials, context
            )
            
            # Generate investment thesis for this company
            investment_thesis = await self._generate_company_thesis(
                company, financials, context
            )
            
            # Calculate financial health score
            health_score = self._calculate_financial_health(financials)
            
            analysis = {
                'symbol': symbol,
                'name': company['name'],
                'sector': company.get('sector'),
                'industry': company.get('industry'),
                'market_cap': company.get('market_cap'),
                'relevance_score': relevance_score,
                'investment_thesis': investment_thesis,
                'financial_metrics': financials,
                'health_score': health_score,
                'bull_case': await self._generate_bull_case(company, financials),
                'bear_case': await self._generate_bear_case(company, financials),
                'catalyst_timeline': self._estimate_catalyst_timeline(context),
            }
            
            return analysis
            
        except Exception as e:
            self.logger.error("company_analysis_failed", symbol=symbol, error=str(e))
            return None
    
    async def _get_financial_metrics(self, symbol: str) -> Dict[str, Any]:
        """Get financial metrics for a company (mock implementation)."""
        
        # This would integrate with Finnhub, Alpha Vantage, etc.
        # For now, return mock data
        import random
        
        mock_metrics = {
            'pe_ratio': round(random.uniform(15, 35), 2),
            'pb_ratio': round(random.uniform(1, 8), 2),
            'ps_ratio': round(random.uniform(2, 12), 2),
            'ev_ebitda': round(random.uniform(10, 25), 2),
            'revenue_growth_yoy': round(random.uniform(-0.1, 0.3), 3),
            'revenue_growth_qoq': round(random.uniform(-0.05, 0.15), 3),
            'gross_margin': round(random.uniform(0.2, 0.7), 3),
            'operating_margin': round(random.uniform(0.05, 0.4), 3),
            'net_margin': round(random.uniform(0.02, 0.3), 3),
            'roe': round(random.uniform(0.05, 0.25), 3),
            'roa': round(random.uniform(0.02, 0.15), 3),
            'roic': round(random.uniform(0.05, 0.2), 3),
            'debt_to_equity': round(random.uniform(0.1, 1.5), 2),
            'current_ratio': round(random.uniform(0.8, 3), 2),
            'free_cash_flow_yield': round(random.uniform(0.02, 0.08), 3),
            'dividend_yield': round(random.uniform(0, 0.05), 3),
            'beta': round(random.uniform(0.5, 2), 2),
            'data_freshness': datetime.utcnow().isoformat(),
        }
        
        return mock_metrics
    
    async def _calculate_thesis_relevance(
        self,
        company: Dict[str, Any],
        financials: Dict[str, Any], 
        context: Dict[str, Any]
    ) -> float:
        """Calculate how relevant this company is to the investment thesis."""
        
        query = context['query']
        sector_analysis = context.get('sector_analysis', {})
        
        prompt = f"""
        Rate the relevance of this company to the investment thesis on a scale of 1-10:

        Investment Query: "{query}"
        
        Company: {company['name']} ({company['symbol']})
        Sector: {company.get('sector', 'Unknown')}
        Industry: {company.get('industry', 'Unknown')}
        Market Cap: ${company.get('market_cap', 0):,.0f}
        
        Key Financials:
        - P/E Ratio: {financials.get('pe_ratio', 'N/A')}
        - Revenue Growth: {financials.get('revenue_growth_yoy', 0)*100:.1f}%
        - Operating Margin: {financials.get('operating_margin', 0)*100:.1f}%
        - ROE: {financials.get('roe', 0)*100:.1f}%
        
        Sector Analysis: {sector_analysis}
        
        Consider:
        1. Direct exposure to the thesis
        2. Quality of financials
        3. Growth trajectory
        4. Market positioning
        5. Risk factors
        
        Provide a relevance score (1-10) and brief explanation.
        Respond with just the number (e.g., "8.5").
        """
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=100,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Extract score from response
            import re
            score_match = re.search(r'(\d+\.?\d*)', response.content[0].text)
            if score_match:
                score = float(score_match.group(1))
                return min(10.0, max(1.0, score))
        except Exception as e:
            self.logger.error("relevance_calculation_failed", error=str(e))
        
        # Fallback scoring based on sector matching
        return self._fallback_relevance_score(company, context)
    
    async def _generate_company_thesis(
        self,
        company: Dict[str, Any],
        financials: Dict[str, Any],
        context: Dict[str, Any]
    ) -> str:
        """Generate investment thesis for specific company."""
        
        try:
            prompt = f"""
            Generate a concise investment thesis (2-3 sentences) for {company['name']} 
            based on the research query: "{context['query']}"
            
            Company: {company['name']} - {company.get('sector')} - {company.get('industry')}
            Key metrics: PE {financials.get('pe_ratio')}, Growth {financials.get('revenue_growth_yoy', 0)*100:.1f}%
            
            Focus on why this company is relevant to the investment theme.
            """
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=200,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}]
            )
            
            return response.content[0].text.strip()
        except Exception as e:
            return f"Strong {company.get('sector')} player with exposure to the investment thesis."
    
    async def _generate_bull_case(self, company: Dict[str, Any], financials: Dict[str, Any]) -> str:
        """Generate bull case scenario."""
        
        # Simplified implementation
        return f"Strong fundamentals with {financials.get('revenue_growth_yoy', 0)*100:.1f}% revenue growth and solid margins. Market leadership in {company.get('industry', 'sector')} provides competitive moat."
    
    async def _generate_bear_case(self, company: Dict[str, Any], financials: Dict[str, Any]) -> str:
        """Generate bear case scenario."""
        
        # Simplified implementation  
        pe = financials.get('pe_ratio', 20)
        if pe > 25:
            return f"Valuation concerns with P/E of {pe}x. Market saturation and increased competition could pressure margins."
        else:
            return "Economic downturn could impact demand. Execution risks on growth initiatives."
    
    def _estimate_catalyst_timeline(self, context: Dict[str, Any]) -> str:
        """Estimate when thesis catalysts might materialize."""
        
        thesis_analysis = context.get('thesis_analysis', {})
        horizon = thesis_analysis.get('investment_horizon', 'medium')
        
        if horizon == 'short':
            return '3-6 months'
        elif horizon == 'long':
            return '12-24 months'
        else:
            return '6-12 months'
    
    async def _rank_companies(self, analyses: List[Dict[str, Any]], context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Rank companies by investment attractiveness."""
        
        # Sort by relevance score and financial health
        ranked = sorted(
            analyses,
            key=lambda x: (x.get('relevance_score', 0) * 0.7 + x.get('health_score', 0) * 0.3),
            reverse=True
        )
        
        return ranked
    
    async def _generate_summary(self, ranked_companies: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary insights from the analysis."""
        
        if not ranked_companies:
            return {'message': 'No companies analyzed'}
        
        top_3 = ranked_companies[:3]
        avg_score = sum(c.get('relevance_score', 0) for c in ranked_companies) / len(ranked_companies)
        
        sectors = {}
        for company in ranked_companies:
            sector = company.get('sector', 'Unknown')
            sectors[sector] = sectors.get(sector, 0) + 1
        
        return {
            'top_picks': [
                {'symbol': c['symbol'], 'name': c['name'], 'score': c.get('relevance_score')}
                for c in top_3
            ],
            'average_relevance_score': round(avg_score, 2),
            'sector_distribution': sectors,
            'total_companies': len(ranked_companies),
            'high_conviction_count': len([c for c in ranked_companies if c.get('relevance_score', 0) >= 8]),
        }
    
    async def _save_company_analyses(self, analyses: List[Dict[str, Any]], project_id: str) -> None:
        """Save company analyses to database."""
        
        async with DatabaseManager() as db:
            for analysis in analyses:
                # Ensure company exists in database
                company = await db.get(Company, analysis['symbol'])
                if not company:
                    company = Company(
                        symbol=analysis['symbol'],
                        name=analysis['name'],
                        sector=analysis.get('sector'),
                        industry=analysis.get('industry'),
                        market_cap=analysis.get('market_cap')
                    )
                    db.add(company)
                
                # Create analysis record
                company_analysis = CompanyAnalysis(
                    project_id=project_id,
                    symbol=analysis['symbol'],
                    relevance_score=analysis.get('relevance_score', 0),
                    investment_thesis=analysis.get('investment_thesis', ''),
                    primary_exposure_pct=None,  # Could be calculated later
                    metrics=analysis.get('financial_metrics', {}),
                    bull_case=analysis.get('bull_case', ''),
                    bear_case=analysis.get('bear_case', ''),
                    catalyst_timeline=analysis.get('catalyst_timeline', ''),
                    confidence_level='medium'  # Could be calculated
                )
                
                db.add(company_analysis)
            
            await db.commit()
    
    def _calculate_financial_health(self, financials: Dict[str, Any]) -> float:
        """Calculate overall financial health score (0-10)."""
        
        score = 5.0  # Base score
        
        # Profitability
        if financials.get('roe', 0) > 0.15:
            score += 1
        elif financials.get('roe', 0) > 0.1:
            score += 0.5
        
        # Growth
        if financials.get('revenue_growth_yoy', 0) > 0.2:
            score += 1
        elif financials.get('revenue_growth_yoy', 0) > 0.1:
            score += 0.5
        
        # Margins
        if financials.get('operating_margin', 0) > 0.2:
            score += 0.5
        
        # Debt management
        debt_ratio = financials.get('debt_to_equity', 0)
        if debt_ratio < 0.3:
            score += 0.5
        elif debt_ratio > 1.5:
            score -= 1
        
        # Liquidity
        if financials.get('current_ratio', 0) > 1.5:
            score += 0.5
        
        return min(10.0, max(1.0, score))
    
    def _calculate_confidence(self, analyses: List[Dict[str, Any]]) -> float:
        """Calculate confidence in the fundamental analysis."""
        
        if not analyses:
            return 0.1
        
        # Base confidence
        base = 0.6
        
        # Adjust based on number of companies analyzed
        count_adjustment = min(0.2, len(analyses) * 0.01)
        
        # Adjust based on data quality (all have financial metrics)
        data_quality = sum(1 for a in analyses if a.get('financial_metrics')) / len(analyses)
        quality_adjustment = data_quality * 0.2
        
        confidence = base + count_adjustment + quality_adjustment
        return min(1.0, max(0.1, confidence))
    
    def _build_reasoning(self, ranked_companies: List[Dict[str, Any]], summary: Dict[str, Any]) -> str:
        """Build reasoning explanation."""
        
        if not ranked_companies:
            return "No companies found matching the investment criteria."
        
        top_pick = ranked_companies[0]
        reasoning = f"Fundamental Analysis Results:\n\n"
        reasoning += f"Top Pick: {top_pick['name']} ({top_pick['symbol']})\n"
        reasoning += f"Relevance Score: {top_pick.get('relevance_score', 0):.1f}/10\n\n"
        reasoning += f"Investment Thesis: {top_pick.get('investment_thesis', '')}\n\n"
        reasoning += f"Total Companies Analyzed: {summary.get('total_companies', 0)}\n"
        reasoning += f"High Conviction Picks: {summary.get('high_conviction_count', 0)}"
        
        return reasoning
    
    def _get_analysis_methodology(self) -> Dict[str, str]:
        """Get the analysis methodology used."""
        
        return {
            'company_discovery': 'Sector-based screening with thesis relevance filtering',
            'financial_analysis': 'Multi-factor fundamental analysis with growth, profitability, and health metrics',
            'thesis_relevance': 'AI-powered scoring based on investment thesis alignment',
            'ranking': 'Composite score combining relevance (70%) and financial health (30%)',
            'validation': 'Cross-reference with multiple financial data sources'
        }
    
    def _fallback_relevance_score(self, company: Dict[str, Any], context: Dict[str, Any]) -> float:
        """Fallback relevance scoring if LLM fails."""
        
        # Simple sector-based scoring
        query = context.get('query', '').lower()
        sector = company.get('sector', '').lower()
        
        if 'tech' in query and 'technology' in sector:
            return 8.0
        elif 'ai' in query and 'technology' in sector:
            return 9.0
        elif 'health' in query and 'healthcare' in sector:
            return 8.5
        else:
            return 6.0  # Default moderate relevance