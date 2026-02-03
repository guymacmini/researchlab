"""Risk Analyst agent for contrarian analysis and thesis-breaking scenario identification."""

from typing import Dict, List, Any, Optional, Tuple
import asyncio
from datetime import datetime, timedelta
import json
import re
import statistics
from collections import defaultdict

import structlog
import anthropic

from src.core.config import settings
from src.core.database import DatabaseManager
from src.data.models import Company, CompanyAnalysis
from src.data.clients.finnhub_client import FinnhubClient
from .base import BaseAgent, AgentRole, AgentResult


class RiskAnalystAgent(BaseAgent):
    """
    Risk Analyst agent responsible for:
    - Identifying contrarian viewpoints and challenging assumptions
    - Analyzing thesis-breaking scenarios and edge cases
    - Evaluating downside risks and potential failure modes
    - Stress-testing investment assumptions under adverse conditions
    - Quantifying uncertainty and confidence intervals
    - Building devil's advocate arguments and red team analysis
    """
    
    role = AgentRole.RISK_ANALYST
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.client = anthropic.Anthropic(api_key=settings.api.anthropic_api_key)
        self.finnhub_client = FinnhubClient()
        self.model = settings.agents.get('risk_analyst_model', 'claude-3-sonnet-20240229')
        
        # Risk assessment frameworks
        self.risk_categories = {
            'market_risk': {
                'description': 'Market-wide risks affecting sector or entire market',
                'factors': ['market_downturns', 'interest_rate_changes', 'inflation', 'recession', 'liquidity_crisis']
            },
            'business_risk': {
                'description': 'Company-specific operational and strategic risks',
                'factors': ['competitive_pressure', 'demand_decline', 'execution_risk', 'technology_disruption', 'regulatory_changes']
            },
            'financial_risk': {
                'description': 'Financial structure and credit risks',
                'factors': ['debt_burden', 'cash_flow_issues', 'currency_risk', 'credit_rating_downgrades', 'covenant_breaches']
            },
            'operational_risk': {
                'description': 'Day-to-day operational and execution risks',
                'factors': ['supply_chain_disruption', 'key_person_risk', 'cyber_security', 'quality_issues', 'capacity_constraints']
            },
            'strategic_risk': {
                'description': 'Long-term strategic positioning and adaptation risks',
                'factors': ['strategic_misalignment', 'innovation_lag', 'market_positioning', 'capital_allocation', 'transformation_failure']
            },
            'external_risk': {
                'description': 'External factors beyond company control',
                'factors': ['regulatory_changes', 'geopolitical_events', 'natural_disasters', 'social_changes', 'environmental_factors']
            }
        }
        
        # Stress test scenarios
        self.stress_scenarios = {
            'mild_recession': {
                'description': 'Mild economic downturn with 10-15% market decline',
                'assumptions': ['GDP decline 1-2%', 'Unemployment rises to 6-7%', 'Consumer spending down 5-10%']
            },
            'severe_recession': {
                'description': 'Severe recession with 30-40% market decline',
                'assumptions': ['GDP decline 3-5%', 'Unemployment rises to 10%+', 'Consumer spending down 20-30%']
            },
            'sector_disruption': {
                'description': 'Major technological or competitive disruption in sector',
                'assumptions': ['New technology obsoletes current products', 'New entrant captures market share', 'Regulatory changes favor competitors']
            },
            'company_crisis': {
                'description': 'Company-specific crisis or scandal',
                'assumptions': ['Management scandal', 'Product recall', 'Major cybersecurity breach', 'Key talent departure']
            },
            'interest_rate_shock': {
                'description': 'Rapid interest rate increases',
                'assumptions': ['Fed funds rate rises 3-5%', 'Credit tightening', 'Higher discount rates for growth stocks']
            },
            'geopolitical_crisis': {
                'description': 'Major geopolitical event or conflict',
                'assumptions': ['Trade war escalation', 'Supply chain disruptions', 'Currency volatility', 'Safe haven flows']
            }
        }
        
        # Contrarian indicators to look for
        self.contrarian_signals = [
            'excessive_optimism',
            'consensus_too_strong',
            'valuation_extremes',
            'ignored_risks',
            'momentum_overextension',
            'structural_changes',
            'mean_reversion_setup',
            'sentiment_extremes'
        ]
        
    async def validate_inputs(self, context: Dict[str, Any]) -> bool:
        """Validate that required inputs are present."""
        required_fields = ['project_id', 'companies', 'investment_thesis']
        
        for field in required_fields:
            if field not in context:
                self.logger.error("missing_required_field", field=field)
                return False
        
        companies = context.get('companies', [])
        if not companies:
            self.logger.error("no_companies_provided")
            return False
        
        thesis = context.get('investment_thesis', '').strip()
        if not thesis:
            self.logger.error("no_investment_thesis_provided")
            return False
            
        return True
    
    async def analyze(self, context: Dict[str, Any]) -> AgentResult:
        """Perform risk analysis and contrarian evaluation of investment thesis."""
        
        self.logger.info("risk_analysis_started", 
                        companies_count=len(context.get('companies', [])))
        
        try:
            companies = context.get('companies', [])
            project_id = context['project_id']
            investment_thesis = context['investment_thesis']
            
            # Get additional context from other agents if available
            fundamental_analysis = context.get('fundamental_analysis', {})
            sentiment_analysis = context.get('sentiment_analysis', {})
            supply_chain_analysis = context.get('supply_chain_analysis', {})
            
            # Analyze risks for each company
            company_risk_analyses = []
            
            for company in companies:
                symbol = company.get('symbol')
                if not symbol:
                    continue
                    
                self.logger.info("analyzing_company_risks", symbol=symbol)
                
                # Comprehensive risk assessment
                risk_assessment = await self._comprehensive_risk_assessment(
                    symbol, company, investment_thesis, context
                )
                
                # Contrarian analysis
                contrarian_analysis = await self._contrarian_analysis(
                    symbol, company, investment_thesis, context
                )
                
                # Stress testing
                stress_test_results = await self._stress_test_scenarios(
                    symbol, company, investment_thesis, risk_assessment
                )
                
                # Thesis vulnerability analysis
                thesis_vulnerabilities = await self._analyze_thesis_vulnerabilities(
                    symbol, company, investment_thesis, risk_assessment
                )
                
                company_risk_analyses.append({
                    'symbol': symbol,
                    'company_name': company.get('name', symbol),
                    'risk_assessment': risk_assessment,
                    'contrarian_analysis': contrarian_analysis,
                    'stress_test_results': stress_test_results,
                    'thesis_vulnerabilities': thesis_vulnerabilities,
                    'overall_risk_score': risk_assessment.get('overall_risk_score', 0.5),
                    'confidence': risk_assessment.get('confidence', 0.5)
                })
            
            # Portfolio-level risk analysis
            portfolio_risks = await self._analyze_portfolio_risks(
                company_risk_analyses, investment_thesis
            )
            
            # Generate risk-based recommendations
            risk_recommendations = await self._generate_risk_recommendations(
                company_risk_analyses, portfolio_risks, investment_thesis
            )
            
            # Calculate overall confidence
            confidence = await self._calculate_confidence(
                company_risk_analyses, portfolio_risks
            )
            
            result_data = {
                'company_risk_analyses': company_risk_analyses,
                'portfolio_risks': portfolio_risks,
                'risk_recommendations': risk_recommendations,
                'analysis_timestamp': datetime.now().isoformat(),
                'methodology': self._get_methodology_summary()
            }
            
            avg_risk_score = statistics.mean([
                c['overall_risk_score'] for c in company_risk_analyses
            ])
            
            self.logger.info("risk_analysis_completed", 
                           confidence=confidence,
                           companies_analyzed=len(company_risk_analyses),
                           avg_risk_score=avg_risk_score)
            
            return AgentResult(
                agent=self.role,
                success=True,
                data=result_data,
                confidence=confidence,
                sources=self._get_data_sources(),
                reasoning=self._generate_analysis_reasoning(result_data),
                errors=None
            )
            
        except Exception as e:
            self.logger.error("risk_analysis_failed", error=str(e))
            return AgentResult(
                agent=self.role,
                success=False,
                data={},
                confidence=0.0,
                sources=[],
                reasoning=f"Analysis failed: {str(e)}",
                errors=[str(e)]
            )
    
    async def _comprehensive_risk_assessment(self, symbol: str, company: Dict, 
                                           investment_thesis: str, context: Dict) -> Dict[str, Any]:
        """Perform comprehensive risk assessment across all risk categories."""
        
        # Get company financial data and news
        try:
            company_profile = await self.finnhub_client.get_company_profile(symbol)
            recent_news = await self.finnhub_client.get_company_news(symbol, days_back=60)
        except Exception as e:
            self.logger.warning("data_fetch_error", symbol=symbol, error=str(e))
            company_profile = {}
            recent_news = []
        
        # Build comprehensive risk analysis prompt
        prompt = f"""
        Perform a comprehensive risk assessment for {symbol} - {company.get('name', 'Unknown')}.

        Investment Thesis: {investment_thesis}

        Company Information:
        - Symbol: {symbol}
        - Name: {company.get('name', 'Unknown')}
        - Sector: {company.get('sector', 'Unknown')}
        - Description: {company_profile.get('description', 'Not available')}
        - Market Cap: {company_profile.get('marketCapitalization', 'Unknown')}

        Analyze risks across these categories:

        1. MARKET RISK: Market-wide risks affecting the company
        2. BUSINESS RISK: Company-specific operational and strategic risks  
        3. FINANCIAL RISK: Financial structure and credit risks
        4. OPERATIONAL RISK: Day-to-day operational risks
        5. STRATEGIC RISK: Long-term strategic positioning risks
        6. EXTERNAL RISK: External factors beyond company control

        For each category, identify:
        - Specific risk factors (2-4 per category)
        - Severity assessment (low/medium/high)
        - Probability assessment (low/medium/high) 
        - Potential impact on investment thesis
        - Mitigation factors or company strengths that reduce risk

        Recent news context: Company has been in news recently - consider any emerging risks.

        Provide overall assessment:
        - Overall risk score (0.0 = very low risk, 1.0 = very high risk)
        - Confidence in assessment (0.0 to 1.0)
        - Key risk themes (top 3-5 biggest concerns)
        - Risk trend (increasing, stable, decreasing)

        Focus on being objective and identifying real risks that could impair the investment thesis.

        Return as JSON:
        {{
            "market_risk": {{
                "risk_factors": [
                    {{"factor": "<name>", "severity": "<low/medium/high>", "probability": "<low/medium/high>", "description": "<description>"}}
                ],
                "category_risk_score": <float>,
                "thesis_impact": "<impact description>"
            }},
            "business_risk": {{ ... }},
            "financial_risk": {{ ... }},
            "operational_risk": {{ ... }},
            "strategic_risk": {{ ... }},
            "external_risk": {{ ... }},
            "overall_risk_score": <float>,
            "confidence": <float>,
            "key_risk_themes": ["<theme1>", "<theme2>", "<theme3>"],
            "risk_trend": "<increasing/stable/decreasing>",
            "summary": "<2-3 sentence risk summary>"
        }}
        """
        
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            
            if json_match:
                risk_data = json.loads(json_match.group())
                
                # Add metadata
                risk_data['analysis_timestamp'] = datetime.now().isoformat()
                risk_data['data_sources'] = ['company_profile', 'recent_news', 'llm_analysis']
                
                return risk_data
            else:
                return self._get_fallback_risk_assessment()
                
        except Exception as e:
            self.logger.error("risk_assessment_error", symbol=symbol, error=str(e))
            return self._get_fallback_risk_assessment()
    
    async def _contrarian_analysis(self, symbol: str, company: Dict, 
                                 investment_thesis: str, context: Dict) -> Dict[str, Any]:
        """Perform contrarian analysis to challenge the investment thesis."""
        
        # Get sentiment and consensus data if available
        sentiment_data = context.get('sentiment_analysis', {})
        fundamental_data = context.get('fundamental_analysis', {})
        
        prompt = f"""
        Perform a contrarian analysis for {symbol} to challenge the investment thesis.

        Investment Thesis: {investment_thesis}

        Company: {symbol} - {company.get('name', 'Unknown')}
        Sector: {company.get('sector', 'Unknown')}

        Take the role of a devil's advocate and identify:

        1. THESIS CHALLENGES: What could go wrong with this investment thesis?
           - Identify 3-5 specific ways the thesis could fail
           - What assumptions might be incorrect?
           - What changes could invalidate the thesis?

        2. CONTRARIAN VIEWPOINTS: Alternative perspectives on the company/sector
           - What would a bear case look like?
           - What risks are being ignored or underestimated?
           - What could cause a dramatic revaluation?

        3. CONSENSUS RISKS: Is there too much agreement?
           - Are expectations too high?
           - What if consensus estimates are wrong?
           - Signs of excessive optimism or momentum?

        4. STRUCTURAL HEADWINDS: Long-term challenges
           - Industry disruption risks
           - Competitive threats
           - Regulatory or social changes
           - Technology shifts

        5. TIMING RISKS: Why the thesis might be wrong on timing
           - Is it too early or too late?
           - What could delay expected catalysts?
           - Market cycle considerations

        6. VALUATION CONCERNS: Price vs. value assessment
           - Is current valuation fair?
           - What if growth slows or margins compress?
           - Downside price targets under stress

        Be thorough and critical. The goal is to stress-test the investment thesis.

        Return as JSON:
        {{
            "thesis_challenges": [
                {{"challenge": "<name>", "probability": "<low/medium/high>", "impact": "<description>", "reasoning": "<explanation>"}}
            ],
            "contrarian_viewpoints": [
                {{"viewpoint": "<perspective>", "supporting_evidence": "<evidence>", "counterargument_strength": "<weak/moderate/strong>"}}
            ],
            "consensus_risks": {{
                "excessive_optimism": <boolean>,
                "crowded_trade": <boolean>,
                "expectations_too_high": <boolean>,
                "momentum_risk": <boolean>
            }},
            "structural_headwinds": ["<headwind1>", "<headwind2>", "<headwind3>"],
            "timing_risks": ["<risk1>", "<risk2>", "<risk3>"],
            "valuation_concerns": {{
                "current_valuation_fair": <boolean>,
                "downside_scenario": "<description>",
                "fair_value_estimate": "<qualitative assessment>"
            }},
            "devil_advocate_summary": "<2-3 sentence contrarian summary>",
            "thesis_vulnerability_score": <float 0.0-1.0>
        }}
        """
        
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=3500,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            
            if json_match:
                return json.loads(json_match.group())
            else:
                return self._get_fallback_contrarian_analysis()
                
        except Exception as e:
            self.logger.error("contrarian_analysis_error", symbol=symbol, error=str(e))
            return self._get_fallback_contrarian_analysis()
    
    async def _stress_test_scenarios(self, symbol: str, company: Dict, 
                                   investment_thesis: str, risk_assessment: Dict) -> Dict[str, Any]:
        """Stress test the investment under various adverse scenarios."""
        
        scenario_results = {}
        
        for scenario_name, scenario_config in self.stress_scenarios.items():
            scenario_result = await self._analyze_scenario_impact(
                symbol, company, investment_thesis, scenario_name, scenario_config, risk_assessment
            )
            scenario_results[scenario_name] = scenario_result
        
        # Aggregate scenario analysis
        worst_case_scenario = max(
            scenario_results.items(), 
            key=lambda x: x[1].get('impact_severity', 0)
        )
        
        avg_impact_severity = statistics.mean([
            result.get('impact_severity', 0) for result in scenario_results.values()
        ])
        
        return {
            'scenario_results': scenario_results,
            'worst_case_scenario': {
                'name': worst_case_scenario[0],
                'details': worst_case_scenario[1]
            },
            'average_impact_severity': avg_impact_severity,
            'scenarios_with_high_impact': [
                name for name, result in scenario_results.items()
                if result.get('impact_severity', 0) > 0.7
            ],
            'overall_stress_test_score': min(1.0, avg_impact_severity * 1.2)  # Amplify average impact
        }
    
    async def _analyze_scenario_impact(self, symbol: str, company: Dict, 
                                     investment_thesis: str, scenario_name: str,
                                     scenario_config: Dict, risk_assessment: Dict) -> Dict[str, Any]:
        """Analyze impact of a specific stress scenario on the company."""
        
        prompt = f"""
        Analyze the impact of the following stress scenario on {symbol}:

        SCENARIO: {scenario_name.upper().replace('_', ' ')}
        Description: {scenario_config['description']}
        Key Assumptions: {', '.join(scenario_config['assumptions'])}

        Company: {symbol} - {company.get('name', 'Unknown')}
        Sector: {company.get('sector', 'Unknown')}
        Investment Thesis: {investment_thesis}

        Analyze:
        1. Direct impact on the company's business model and operations
        2. Impact on financial performance (revenue, margins, cash flow)
        3. Impact on competitive position and market share
        4. Impact on the investment thesis validity
        5. Company's resilience and ability to weather the scenario
        6. Recovery timeline and probability

        Rate the impact:
        - Impact severity: 0.0 (no impact) to 1.0 (devastating impact)
        - Probability: 0.0 (very unlikely) to 1.0 (very likely)
        - Recovery difficulty: 0.0 (quick recovery) to 1.0 (permanent damage)

        Return as JSON:
        {{
            "impact_severity": <float>,
            "scenario_probability": <float>,
            "recovery_difficulty": <float>,
            "business_impact": {{
                "revenue_impact": "<description and % estimate>",
                "margin_impact": "<description>",
                "operational_impact": "<description>"
            }},
            "thesis_impact": "<how scenario affects investment thesis>",
            "company_resilience": "<assessment of company's ability to weather scenario>",
            "recovery_timeline": "<estimated recovery time>",
            "mitigation_factors": ["<factor1>", "<factor2>", "<factor3>"],
            "summary": "<2 sentence scenario impact summary>"
        }}
        """
        
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            
            if json_match:
                return json.loads(json_match.group())
            else:
                return {
                    'impact_severity': 0.5,
                    'scenario_probability': 0.3,
                    'recovery_difficulty': 0.5,
                    'business_impact': {'revenue_impact': 'Analysis unavailable'},
                    'thesis_impact': 'Unable to assess',
                    'summary': f'Unable to analyze {scenario_name} scenario impact'
                }
                
        except Exception as e:
            self.logger.error("scenario_analysis_error", 
                            symbol=symbol, scenario=scenario_name, error=str(e))
            return {
                'impact_severity': 0.5,
                'scenario_probability': 0.3,
                'recovery_difficulty': 0.5,
                'business_impact': {'revenue_impact': f'Analysis failed: {str(e)}'},
                'thesis_impact': 'Analysis failed',
                'summary': f'Failed to analyze {scenario_name} scenario'
            }
    
    async def _analyze_thesis_vulnerabilities(self, symbol: str, company: Dict,
                                            investment_thesis: str, risk_assessment: Dict) -> Dict[str, Any]:
        """Analyze specific vulnerabilities in the investment thesis."""
        
        prompt = f"""
        Analyze vulnerabilities and potential failure points in this investment thesis:

        Investment Thesis: {investment_thesis}
        Company: {symbol} - {company.get('name', 'Unknown')}

        Key risk themes identified: {', '.join(risk_assessment.get('key_risk_themes', []))}
        Overall risk score: {risk_assessment.get('overall_risk_score', 'Unknown')}

        Identify thesis vulnerabilities:

        1. ASSUMPTION RISKS: What key assumptions could be wrong?
           - List 3-5 critical assumptions the thesis depends on
           - Rate each assumption's reliability (low/medium/high)
           - What evidence would invalidate each assumption?

        2. DEPENDENCY RISKS: What does success depend on?
           - Single points of failure
           - Key variables that must go right
           - External factors beyond company control

        3. TIMING RISKS: Time-sensitive elements
           - What if catalysts are delayed?
           - Market cycle dependencies
           - Competitive timing risks

        4. EXECUTION RISKS: Internal capability risks
           - Management execution capability
           - Operational complexity
           - Resource requirements

        5. MARKET RISKS: External market factors
           - Market acceptance risks
           - Regulatory risks
           - Economic sensitivity

        Rate each category's vulnerability (0.0 = low vulnerability, 1.0 = high vulnerability).

        Return as JSON:
        {{
            "assumption_risks": [
                {{"assumption": "<assumption>", "reliability": "<low/medium/high>", "invalidation_risk": "<description>", "vulnerability_score": <float>}}
            ],
            "dependency_risks": [
                {{"dependency": "<dependency>", "control_level": "<low/medium/high>", "failure_impact": "<description>", "vulnerability_score": <float>}}
            ],
            "timing_risks": [
                {{"timing_factor": "<factor>", "delay_probability": "<low/medium/high>", "delay_impact": "<description>", "vulnerability_score": <float>}}
            ],
            "execution_risks": [
                {{"execution_area": "<area>", "difficulty": "<low/medium/high>", "failure_probability": "<assessment>", "vulnerability_score": <float>}}
            ],
            "market_risks": [
                {{"market_factor": "<factor>", "volatility": "<low/medium/high>", "impact": "<description>", "vulnerability_score": <float>}}
            ],
            "overall_thesis_vulnerability": <float>,
            "highest_vulnerability_area": "<category with highest average vulnerability>",
            "thesis_robustness_assessment": "<qualitative assessment>",
            "key_monitoring_points": ["<point1>", "<point2>", "<point3>"]
        }}
        """
        
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=3000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            
            if json_match:
                return json.loads(json_match.group())
            else:
                return {
                    'assumption_risks': [],
                    'dependency_risks': [],
                    'timing_risks': [],
                    'execution_risks': [],
                    'market_risks': [],
                    'overall_thesis_vulnerability': 0.5,
                    'thesis_robustness_assessment': 'Analysis unavailable'
                }
                
        except Exception as e:
            self.logger.error("thesis_vulnerability_analysis_error", 
                            symbol=symbol, error=str(e))
            return {
                'assumption_risks': [],
                'dependency_risks': [],
                'timing_risks': [],
                'execution_risks': [],
                'market_risks': [],
                'overall_thesis_vulnerability': 0.5,
                'thesis_robustness_assessment': f'Analysis failed: {str(e)}'
            }
    
    async def _analyze_portfolio_risks(self, company_risk_analyses: List[Dict], 
                                     investment_thesis: str) -> Dict[str, Any]:
        """Analyze portfolio-level risks and correlations."""
        
        if not company_risk_analyses:
            return {'error': 'No company analyses provided'}
        
        # Calculate portfolio risk metrics
        risk_scores = [analysis['overall_risk_score'] for analysis in company_risk_analyses]
        vulnerability_scores = [
            analysis.get('thesis_vulnerabilities', {}).get('overall_thesis_vulnerability', 0.5)
            for analysis in company_risk_analyses
        ]
        
        portfolio_risk_score = statistics.mean(risk_scores)
        portfolio_vulnerability_score = statistics.mean(vulnerability_scores)
        risk_concentration = statistics.stdev(risk_scores) if len(risk_scores) > 1 else 0.0
        
        # Identify common risks across companies
        all_risk_themes = []
        for analysis in company_risk_analyses:
            themes = analysis.get('risk_assessment', {}).get('key_risk_themes', [])
            all_risk_themes.extend(themes)
        
        from collections import Counter
        common_risks = Counter(all_risk_themes).most_common(5)
        
        # Analyze correlation risks
        correlation_analysis = await self._analyze_portfolio_correlations(company_risk_analyses)
        
        # Identify portfolio-level vulnerabilities
        portfolio_vulnerabilities = await self._identify_portfolio_vulnerabilities(
            company_risk_analyses, investment_thesis
        )
        
        return {
            'portfolio_risk_score': round(portfolio_risk_score, 3),
            'portfolio_vulnerability_score': round(portfolio_vulnerability_score, 3),
            'risk_concentration': round(risk_concentration, 3),
            'risk_distribution': {
                'low_risk_companies': sum(1 for r in risk_scores if r < 0.4),
                'medium_risk_companies': sum(1 for r in risk_scores if 0.4 <= r < 0.7),
                'high_risk_companies': sum(1 for r in risk_scores if r >= 0.7)
            },
            'common_risks': [{'risk': risk, 'frequency': freq} for risk, freq in common_risks],
            'correlation_analysis': correlation_analysis,
            'portfolio_vulnerabilities': portfolio_vulnerabilities,
            'diversification_assessment': self._assess_risk_diversification(company_risk_analyses)
        }
    
    async def _analyze_portfolio_correlations(self, company_risk_analyses: List[Dict]) -> Dict[str, Any]:
        """Analyze risk correlations between portfolio companies."""
        
        # Simplified correlation analysis based on risk themes and sectors
        sector_concentration = defaultdict(int)
        risk_theme_overlap = defaultdict(int)
        
        for analysis in company_risk_analyses:
            # Count sector concentration
            symbol = analysis['symbol']
            # Would need sector data - simplified for now
            
            # Count overlapping risk themes
            themes = analysis.get('risk_assessment', {}).get('key_risk_themes', [])
            for theme in themes:
                risk_theme_overlap[theme] += 1
        
        # Identify high correlation risks
        high_correlation_risks = [
            theme for theme, count in risk_theme_overlap.items()
            if count >= len(company_risk_analyses) * 0.6  # 60%+ of companies share this risk
        ]
        
        return {
            'high_correlation_risks': high_correlation_risks,
            'risk_theme_overlap': dict(risk_theme_overlap),
            'correlation_score': len(high_correlation_risks) / max(len(risk_theme_overlap), 1),
            'systemic_risk_indicators': high_correlation_risks
        }
    
    async def _identify_portfolio_vulnerabilities(self, company_risk_analyses: List[Dict],
                                                investment_thesis: str) -> List[Dict]:
        """Identify portfolio-level vulnerabilities that could affect multiple companies."""
        
        vulnerabilities = []
        
        # Thesis-wide vulnerabilities
        thesis_vulnerability_scores = [
            analysis.get('thesis_vulnerabilities', {}).get('overall_thesis_vulnerability', 0.5)
            for analysis in company_risk_analyses
        ]
        
        avg_thesis_vulnerability = statistics.mean(thesis_vulnerability_scores)
        
        if avg_thesis_vulnerability > 0.6:
            vulnerabilities.append({
                'type': 'thesis_vulnerability',
                'severity': 'high' if avg_thesis_vulnerability > 0.8 else 'medium',
                'description': 'Investment thesis shows structural vulnerabilities across portfolio',
                'affected_companies': len(company_risk_analyses),
                'mitigation': 'Consider thesis refinement or position sizing'
            })
        
        # Concentration risks
        high_risk_companies = [
            analysis for analysis in company_risk_analyses
            if analysis['overall_risk_score'] > 0.7
        ]
        
        if len(high_risk_companies) >= len(company_risk_analyses) * 0.5:
            vulnerabilities.append({
                'type': 'high_risk_concentration',
                'severity': 'high',
                'description': 'High proportion of companies have elevated risk scores',
                'affected_companies': len(high_risk_companies),
                'mitigation': 'Consider risk-based position sizing or portfolio rebalancing'
            })
        
        return vulnerabilities
    
    def _assess_risk_diversification(self, company_risk_analyses: List[Dict]) -> str:
        """Assess risk diversification across the portfolio."""
        
        if len(company_risk_analyses) <= 1:
            return 'Insufficient companies for diversification assessment'
        
        risk_scores = [analysis['overall_risk_score'] for analysis in company_risk_analyses]
        risk_std = statistics.stdev(risk_scores)
        
        if risk_std < 0.1:
            return 'Poor risk diversification - all companies have similar risk profiles'
        elif risk_std < 0.2:
            return 'Moderate risk diversification - some variation in risk profiles'
        else:
            return 'Good risk diversification - varied risk profiles across portfolio'
    
    async def _generate_risk_recommendations(self, company_risk_analyses: List[Dict],
                                           portfolio_risks: Dict, 
                                           investment_thesis: str) -> Dict[str, Any]:
        """Generate risk-based recommendations and actions."""
        
        recommendations = {
            'high_priority': [],
            'medium_priority': [],
            'monitoring': [],
            'position_sizing': [],
            'hedging': []
        }
        
        # Company-specific recommendations
        for analysis in company_risk_analyses:
            symbol = analysis['symbol']
            risk_score = analysis['overall_risk_score']
            
            if risk_score > 0.8:
                recommendations['high_priority'].append({
                    'symbol': symbol,
                    'action': 'Consider reducing position size or exiting',
                    'reason': 'Very high risk score with multiple risk factors',
                    'risk_score': risk_score
                })
            elif risk_score > 0.6:
                recommendations['medium_priority'].append({
                    'symbol': symbol,
                    'action': 'Implement closer monitoring and consider hedge',
                    'reason': 'Elevated risk requires active management',
                    'risk_score': risk_score
                })
            
            # Monitoring recommendations based on vulnerabilities
            vulnerabilities = analysis.get('thesis_vulnerabilities', {})
            monitoring_points = vulnerabilities.get('key_monitoring_points', [])
            
            if monitoring_points:
                recommendations['monitoring'].append({
                    'symbol': symbol,
                    'monitoring_points': monitoring_points,
                    'frequency': 'weekly' if risk_score > 0.6 else 'monthly'
                })
        
        # Portfolio-level recommendations
        portfolio_risk_score = portfolio_risks.get('portfolio_risk_score', 0.5)
        
        if portfolio_risk_score > 0.7:
            recommendations['high_priority'].append({
                'action': 'Portfolio-wide risk reduction',
                'reason': 'Overall portfolio risk is elevated',
                'details': 'Consider reducing overall exposure or adding hedges'
            })
        
        # Common risk hedging suggestions
        common_risks = portfolio_risks.get('common_risks', [])
        for risk_item in common_risks:
            if risk_item['frequency'] >= len(company_risk_analyses) * 0.6:
                recommendations['hedging'].append({
                    'risk': risk_item['risk'],
                    'hedge_suggestion': f'Consider hedging against {risk_item["risk"]}',
                    'affected_companies': risk_item['frequency']
                })
        
        return recommendations
    
    async def _calculate_confidence(self, company_risk_analyses: List[Dict], 
                                  portfolio_risks: Dict) -> float:
        """Calculate overall confidence in risk analysis."""
        
        if not company_risk_analyses:
            return 0.1
        
        # Base confidence
        base_confidence = 0.4
        
        # Boost based on number of companies analyzed
        company_bonus = min(0.2, len(company_risk_analyses) * 0.04)
        
        # Boost based on average individual confidence
        individual_confidences = [
            analysis.get('risk_assessment', {}).get('confidence', 0.5)
            for analysis in company_risk_analyses
        ]
        avg_individual_confidence = statistics.mean(individual_confidences)
        confidence_bonus = (avg_individual_confidence - 0.5) * 0.3
        
        # Reduce confidence for high uncertainty scenarios
        portfolio_risk_score = portfolio_risks.get('portfolio_risk_score', 0.5)
        high_risk_penalty = max(0, (portfolio_risk_score - 0.7) * 0.2)
        
        final_confidence = (base_confidence + company_bonus + confidence_bonus - high_risk_penalty)
        
        return max(0.1, min(0.9, final_confidence))
    
    def _get_fallback_risk_assessment(self) -> Dict[str, Any]:
        """Get fallback risk assessment when analysis fails."""
        return {
            'market_risk': {'category_risk_score': 0.5, 'thesis_impact': 'Unable to assess'},
            'business_risk': {'category_risk_score': 0.5, 'thesis_impact': 'Unable to assess'},
            'financial_risk': {'category_risk_score': 0.5, 'thesis_impact': 'Unable to assess'},
            'operational_risk': {'category_risk_score': 0.5, 'thesis_impact': 'Unable to assess'},
            'strategic_risk': {'category_risk_score': 0.5, 'thesis_impact': 'Unable to assess'},
            'external_risk': {'category_risk_score': 0.5, 'thesis_impact': 'Unable to assess'},
            'overall_risk_score': 0.5,
            'confidence': 0.3,
            'key_risk_themes': ['Analysis unavailable'],
            'risk_trend': 'unknown',
            'summary': 'Risk assessment could not be completed'
        }
    
    def _get_fallback_contrarian_analysis(self) -> Dict[str, Any]:
        """Get fallback contrarian analysis when analysis fails."""
        return {
            'thesis_challenges': [],
            'contrarian_viewpoints': [],
            'consensus_risks': {
                'excessive_optimism': False,
                'crowded_trade': False,
                'expectations_too_high': False,
                'momentum_risk': False
            },
            'structural_headwinds': [],
            'timing_risks': [],
            'valuation_concerns': {
                'current_valuation_fair': True,
                'downside_scenario': 'Unable to assess',
                'fair_value_estimate': 'Unable to assess'
            },
            'devil_advocate_summary': 'Contrarian analysis could not be completed',
            'thesis_vulnerability_score': 0.5
        }
    
    def _get_data_sources(self) -> List[str]:
        """Get list of data sources used."""
        return [
            "Claude LLM Risk Analysis",
            "Finnhub Company Profiles",
            "Finnhub Company News", 
            "Multi-scenario Stress Testing",
            "Contrarian Analysis Framework"
        ]
    
    def _generate_analysis_reasoning(self, result_data: Dict) -> str:
        """Generate human-readable reasoning for the analysis."""
        
        company_count = len(result_data.get('company_risk_analyses', []))
        portfolio_risks = result_data.get('portfolio_risks', {})
        avg_risk_score = portfolio_risks.get('portfolio_risk_score', 0.5)
        
        reasoning = f"Analyzed risk factors for {company_count} companies using comprehensive risk framework. "
        
        if avg_risk_score > 0.7:
            reasoning += "Portfolio shows elevated risk levels requiring attention. "
        elif avg_risk_score > 0.5:
            reasoning += "Portfolio risk is moderate with some areas of concern. "
        else:
            reasoning += "Portfolio risk appears manageable with appropriate monitoring. "
        
        recommendations = result_data.get('risk_recommendations', {})
        high_priority_count = len(recommendations.get('high_priority', []))
        
        if high_priority_count > 0:
            reasoning += f"Generated {high_priority_count} high-priority risk recommendations requiring immediate action."
        else:
            reasoning += "No immediate high-priority risk actions required."
        
        return reasoning
    
    def _get_methodology_summary(self) -> Dict[str, str]:
        """Get summary of risk analysis methodology."""
        return {
            'risk_assessment': 'Six-category comprehensive risk analysis (market, business, financial, operational, strategic, external)',
            'contrarian_analysis': 'Devil\'s advocate analysis challenging investment thesis assumptions',
            'stress_testing': 'Multiple scenario stress testing including recession, disruption, and crisis scenarios',
            'vulnerability_analysis': 'Systematic identification of thesis dependencies and failure points',
            'portfolio_analysis': 'Cross-company correlation analysis and portfolio-level risk assessment',
            'recommendations': 'Risk-based action recommendations with priority classification'
        }