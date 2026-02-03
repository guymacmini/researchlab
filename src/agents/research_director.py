"""Research Director agent for query interpretation and research scoping."""

from typing import Dict, List, Any, Optional
import re

import structlog
import anthropic

from src.core.config import settings
from .base import BaseAgent, AgentRole, AgentResult


class ResearchDirectorAgent(BaseAgent):
    """
    Research Director agent responsible for:
    - Interpreting user queries and investment theses
    - Asking clarifying questions to refine scope
    - Defining research parameters and methodology
    - Coordinating other specialist agents
    """
    
    role = AgentRole.RESEARCH_DIRECTOR
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.client = anthropic.Anthropic(api_key=settings.api.anthropic_api_key)
        self.model = settings.agents.research_director_model
        
    async def validate_inputs(self, context: Dict[str, Any]) -> bool:
        """Validate that required inputs are present."""
        required_fields = ['query', 'user_id', 'project_id']
        
        for field in required_fields:
            if field not in context:
                self.logger.error("missing_required_field", field=field)
                return False
                
        query = context.get('query', '').strip()
        if len(query) < 10:
            self.logger.error("query_too_short", length=len(query))
            return False
            
        return True
    
    async def analyze(self, context: Dict[str, Any]) -> AgentResult:
        """Analyze the research query and create research plan."""
        
        self.logger.info("research_director_analysis_started")
        
        try:
            query = context['query']
            scope = context.get('scope', {})
            
            # Step 1: Parse and understand the investment thesis
            thesis_analysis = await self._analyze_investment_thesis(query)
            
            # Step 2: Generate clarifying questions if scope is incomplete
            clarifying_questions = await self._generate_clarifying_questions(
                query, scope, thesis_analysis
            )
            
            # Step 3: Create research methodology and plan
            research_plan = await self._create_research_plan(
                query, scope, thesis_analysis
            )
            
            # Step 4: Identify relevant sectors and effects
            sector_analysis = await self._identify_sector_effects(
                query, thesis_analysis
            )
            
            confidence = self._calculate_confidence(
                thesis_analysis, research_plan, len(clarifying_questions)
            )
            
            analysis_data = {
                'thesis_analysis': thesis_analysis,
                'clarifying_questions': clarifying_questions,
                'research_plan': research_plan,
                'sector_analysis': sector_analysis,
                'methodology': self._get_research_methodology(),
                'estimated_completion_time': research_plan.get('estimated_time_minutes', 30),
                'estimated_companies': research_plan.get('estimated_companies', 50),
            }
            
            reasoning = self._build_reasoning(thesis_analysis, research_plan)
            sources = ['anthropic_claude', 'research_director_knowledge']
            
            self.logger.info(
                "research_director_analysis_completed",
                confidence=confidence,
                questions=len(clarifying_questions),
                sectors=len(sector_analysis.get('sectors', []))
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
            self.logger.error("research_director_analysis_failed", error=str(e))
            
            return AgentResult(
                agent=self.role,
                success=False,
                data={},
                confidence=0.0,
                sources=[],
                reasoning=f"Analysis failed: {str(e)}",
                errors=[str(e)]
            )
    
    async def _analyze_investment_thesis(self, query: str) -> Dict[str, Any]:
        """Analyze the investment thesis to understand intent and scope."""
        
        prompt = f"""
        Analyze the following investment research query and extract key components:

        Query: "{query}"

        Please analyze and provide:
        1. Core investment thesis (what the user believes will happen)
        2. Causal chain (cause -> effect relationships)
        3. Investment horizon (short/medium/long term based on context)
        4. Risk level (conservative/moderate/aggressive based on thesis)
        5. Primary sectors likely to be affected
        6. Geographic scope (US/global/specific regions)
        7. Market cap preferences (if any can be inferred)
        8. Thesis clarity score (1-10, how clear and specific the thesis is)

        Respond in JSON format with these exact keys:
        - thesis_summary
        - causal_chain
        - investment_horizon  
        - risk_level
        - primary_sectors
        - geographic_scope
        - market_cap_preference
        - clarity_score
        - analysis_notes
        """
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=settings.agents.max_tokens,
            temperature=settings.agents.temperature,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Parse JSON response
        import json
        try:
            analysis = json.loads(response.content[0].text)
            return analysis
        except json.JSONDecodeError:
            # Fallback parsing if JSON is malformed
            return self._fallback_thesis_analysis(query)
    
    async def _generate_clarifying_questions(
        self,
        query: str,
        existing_scope: Dict[str, Any],
        thesis_analysis: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate clarifying questions to refine the research scope."""
        
        # If scope is already well-defined, fewer questions needed
        if len(existing_scope) >= 5 and thesis_analysis.get('clarity_score', 0) >= 7:
            return []
        
        prompt = f"""
        Based on this investment research query and initial analysis, generate clarifying questions:

        Query: "{query}"
        Current Scope: {existing_scope}
        Thesis Analysis: {thesis_analysis}

        Generate 3-5 clarifying questions to help refine the research scope. Focus on:
        - Investment horizon if not clear
        - Geographic preferences if ambiguous  
        - Sector inclusions/exclusions
        - Market cap preferences
        - Risk tolerance
        - Specific metrics or catalysts to track

        Provide questions that have clear answer options when possible.

        Respond in JSON format as a list of question objects with keys:
        - question (the question text)
        - type (multiple_choice, text, boolean)
        - options (for multiple_choice type)
        - priority (high, medium, low)
        """
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=settings.agents.max_tokens,
            temperature=settings.agents.temperature,
            messages=[{"role": "user", "content": prompt}]
        )
        
        try:
            import json
            questions = json.loads(response.content[0].text)
            return questions if isinstance(questions, list) else []
        except (json.JSONDecodeError, IndexError):
            return []
    
    async def _create_research_plan(
        self,
        query: str,
        scope: Dict[str, Any],
        thesis_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create detailed research plan and methodology."""
        
        prompt = f"""
        Create a detailed research plan for this investment thesis:

        Query: "{query}"
        Scope: {scope}
        Analysis: {thesis_analysis}

        Provide a comprehensive research plan including:
        1. Research objectives (3-5 specific goals)
        2. Data sources to query (financial APIs, news sources, filings)
        3. Analysis methodology for each specialist agent
        4. Success metrics and validation criteria
        5. Estimated timeline (in minutes)
        6. Expected number of companies to analyze
        7. Risk factors to monitor
        8. Key questions to answer

        Respond in JSON format with keys:
        - objectives
        - data_sources
        - methodology
        - success_metrics
        - estimated_time_minutes
        - estimated_companies
        - risk_factors
        - key_questions
        """
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=settings.agents.max_tokens,
            temperature=settings.agents.temperature,
            messages=[{"role": "user", "content": prompt}]
        )
        
        try:
            import json
            plan = json.loads(response.content[0].text)
            return plan
        except (json.JSONDecodeError, IndexError):
            return self._fallback_research_plan()
    
    async def _identify_sector_effects(
        self,
        query: str,
        thesis_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Identify sectors and second/third-order effects."""
        
        prompt = f"""
        Analyze the sector implications and ripple effects for this investment thesis:

        Query: "{query}"
        Thesis: {thesis_analysis}

        Identify:
        1. Primary sectors (directly affected)
        2. Secondary sectors (suppliers, customers, competitors)
        3. Tertiary sectors (infrastructure, commodities, support services)
        4. Geographic concentrations
        5. Market cap distribution (which cap ranges most affected)

        For each sector group, provide:
        - GICS sector names
        - Impact direction (positive/negative)
        - Impact magnitude (high/medium/low)
        - Timeline (immediate/6-12 months/long-term)

        Respond in JSON format with keys:
        - primary_sectors
        - secondary_sectors  
        - tertiary_sectors
        - geographic_concentrations
        - market_cap_distribution
        """
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=settings.agents.max_tokens,
            temperature=settings.agents.temperature,
            messages=[{"role": "user", "content": prompt}]
        )
        
        try:
            import json
            sector_analysis = json.loads(response.content[0].text)
            return sector_analysis
        except (json.JSONDecodeError, IndexError):
            return {'primary_sectors': [], 'secondary_sectors': [], 'tertiary_sectors': []}
    
    def _calculate_confidence(
        self,
        thesis_analysis: Dict[str, Any],
        research_plan: Dict[str, Any],
        questions_count: int
    ) -> float:
        """Calculate confidence level in the research direction."""
        
        base_confidence = 0.7
        
        # Adjust based on thesis clarity
        clarity_score = thesis_analysis.get('clarity_score', 5)
        clarity_adjustment = (clarity_score - 5) * 0.05
        
        # Adjust based on research plan completeness
        plan_completeness = len(research_plan.get('objectives', [])) * 0.03
        
        # Adjust based on remaining questions (fewer questions = higher confidence)
        questions_adjustment = max(0, questions_count * -0.05)
        
        confidence = min(1.0, max(0.1, base_confidence + clarity_adjustment + plan_completeness + questions_adjustment))
        
        return round(confidence, 2)
    
    def _build_reasoning(
        self,
        thesis_analysis: Dict[str, Any],
        research_plan: Dict[str, Any]
    ) -> str:
        """Build explanation of the research direction."""
        
        thesis = thesis_analysis.get('thesis_summary', 'Investment thesis')
        sectors = thesis_analysis.get('primary_sectors', [])
        objectives = research_plan.get('objectives', [])
        
        reasoning = f"Research Direction: {thesis}\n\n"
        reasoning += f"Primary Focus: {', '.join(sectors[:3])}\n\n"
        reasoning += "Key Objectives:\n"
        for i, objective in enumerate(objectives[:3], 1):
            reasoning += f"{i}. {objective}\n"
        
        return reasoning
    
    def _get_research_methodology(self) -> Dict[str, str]:
        """Get standardized research methodology."""
        
        return {
            'fundamental_analysis': 'Extract financial metrics, ratios, and growth trends',
            'sector_screening': 'Screen companies by sector exposure and relevance',
            'news_monitoring': 'Track relevant news and sentiment indicators',
            'risk_assessment': 'Identify thesis-breaking scenarios and risks',
            'validation': 'Cross-reference findings across multiple data sources'
        }
    
    def _fallback_thesis_analysis(self, query: str) -> Dict[str, Any]:
        """Fallback thesis analysis if LLM parsing fails."""
        
        return {
            'thesis_summary': f"Investment opportunity analysis: {query[:100]}...",
            'causal_chain': ['Market conditions change', 'Company performance affected', 'Stock prices react'],
            'investment_horizon': 'medium',
            'risk_level': 'moderate',
            'primary_sectors': ['Technology', 'Healthcare', 'Financial Services'],
            'geographic_scope': 'us_only',
            'market_cap_preference': 'large_mid_cap',
            'clarity_score': 5,
            'analysis_notes': 'Fallback analysis - LLM parsing failed'
        }
    
    def _fallback_research_plan(self) -> Dict[str, Any]:
        """Fallback research plan if LLM parsing fails."""
        
        return {
            'objectives': [
                'Identify relevant companies and sectors',
                'Analyze financial performance metrics', 
                'Assess market sentiment and news flow',
                'Evaluate investment risks and opportunities'
            ],
            'data_sources': ['finnhub', 'alpha_vantage', 'news_apis'],
            'methodology': self._get_research_methodology(),
            'estimated_time_minutes': 30,
            'estimated_companies': 50,
            'risk_factors': ['Market volatility', 'Sector rotation', 'Economic conditions'],
            'key_questions': [
                'Which companies have highest exposure to thesis?',
                'What are the key financial metrics to track?',
                'What could invalidate this investment thesis?'
            ]
        }