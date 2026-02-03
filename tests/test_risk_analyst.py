"""Tests for Risk Analyst agent."""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
import statistics

from src.agents.risk_analyst import RiskAnalystAgent
from src.agents.base import AgentRole, AgentResult


class TestRiskAnalystAgent:
    """Test cases for Risk Analyst agent."""

    @pytest.fixture
    def agent(self):
        """Create a Risk Analyst agent for testing."""
        with patch('src.agents.risk_analyst.settings') as mock_settings:
            mock_settings.api.anthropic_api_key = "test_anthropic_key"
            mock_settings.api.finnhub_api_key = "test_finnhub_key"
            with patch('src.agents.risk_analyst.FinnhubClient'):
                return RiskAnalystAgent()

    @pytest.fixture
    def sample_context(self):
        """Sample context for testing."""
        return {
            'project_id': 'test-project-123',
            'companies': [
                {
                    'symbol': 'AAPL',
                    'name': 'Apple Inc.',
                    'sector': 'Technology'
                },
                {
                    'symbol': 'TSLA',
                    'name': 'Tesla Inc.',
                    'sector': 'Automotive'
                }
            ],
            'investment_thesis': 'Electric vehicle adoption will drive growth in battery technology companies',
            'fundamental_analysis': {'avg_growth_rate': 0.25},
            'sentiment_analysis': {'market_sentiment': 0.6},
            'supply_chain_analysis': {'supply_chain_risks': ['chip shortage']}
        }

    @pytest.fixture
    def mock_risk_assessment(self):
        """Mock comprehensive risk assessment result."""
        return {
            'market_risk': {
                'risk_factors': [
                    {
                        'factor': 'Interest rate sensitivity',
                        'severity': 'high',
                        'probability': 'medium',
                        'description': 'Growth stocks vulnerable to rate increases'
                    }
                ],
                'category_risk_score': 0.6,
                'thesis_impact': 'Could reduce EV adoption if financing becomes expensive'
            },
            'business_risk': {
                'risk_factors': [
                    {
                        'factor': 'Competitive pressure',
                        'severity': 'medium',
                        'probability': 'high',
                        'description': 'Traditional automakers entering EV market'
                    }
                ],
                'category_risk_score': 0.5,
                'thesis_impact': 'Increased competition may compress margins'
            },
            'financial_risk': {
                'category_risk_score': 0.4,
                'thesis_impact': 'Manageable debt levels'
            },
            'operational_risk': {
                'category_risk_score': 0.5,
                'thesis_impact': 'Supply chain constraints'
            },
            'strategic_risk': {
                'category_risk_score': 0.3,
                'thesis_impact': 'Well-positioned for EV transition'
            },
            'external_risk': {
                'category_risk_score': 0.6,
                'thesis_impact': 'Regulatory support for EVs'
            },
            'overall_risk_score': 0.5,
            'confidence': 0.8,
            'key_risk_themes': ['market volatility', 'competition', 'supply chain'],
            'risk_trend': 'stable',
            'summary': 'Moderate risk with manageable exposure to key factors'
        }

    @pytest.fixture
    def mock_contrarian_analysis(self):
        """Mock contrarian analysis result."""
        return {
            'thesis_challenges': [
                {
                    'challenge': 'EV adoption slower than expected',
                    'probability': 'medium',
                    'impact': 'Could delay growth timeline by 2-3 years',
                    'reasoning': 'Infrastructure buildout challenges'
                },
                {
                    'challenge': 'Battery technology disruption',
                    'probability': 'low',
                    'impact': 'Could obsolete current investments',
                    'reasoning': 'Solid state batteries or hydrogen'
                }
            ],
            'contrarian_viewpoints': [
                {
                    'viewpoint': 'EV market oversaturated',
                    'supporting_evidence': 'Too many companies entering market',
                    'counterargument_strength': 'moderate'
                }
            ],
            'consensus_risks': {
                'excessive_optimism': True,
                'crowded_trade': True,
                'expectations_too_high': False,
                'momentum_risk': True
            },
            'structural_headwinds': [
                'charging infrastructure gaps',
                'battery raw material constraints',
                'grid capacity limitations'
            ],
            'timing_risks': [
                'regulatory changes',
                'economic downturn impact',
                'technology transition speed'
            ],
            'valuation_concerns': {
                'current_valuation_fair': False,
                'downside_scenario': '40-60% decline in bear market',
                'fair_value_estimate': 'Currently overvalued by 20-30%'
            },
            'devil_advocate_summary': 'EV thesis may be overhyped with significant execution and timing risks',
            'thesis_vulnerability_score': 0.65
        }

    @pytest.fixture
    def mock_stress_test_results(self):
        """Mock stress test results."""
        return {
            'scenario_results': {
                'mild_recession': {
                    'impact_severity': 0.4,
                    'scenario_probability': 0.3,
                    'recovery_difficulty': 0.3,
                    'business_impact': {
                        'revenue_impact': '10-15% revenue decline',
                        'margin_impact': 'Some margin compression',
                        'operational_impact': 'Manageable with cost cuts'
                    },
                    'thesis_impact': 'Delays growth but thesis remains intact',
                    'summary': 'Manageable impact with good recovery prospects'
                },
                'severe_recession': {
                    'impact_severity': 0.8,
                    'scenario_probability': 0.15,
                    'recovery_difficulty': 0.7,
                    'business_impact': {
                        'revenue_impact': '30-40% revenue decline',
                        'margin_impact': 'Significant margin compression',
                        'operational_impact': 'Major restructuring needed'
                    },
                    'thesis_impact': 'Severe challenge to thesis timeline',
                    'summary': 'High impact requiring significant adaptation'
                }
            },
            'worst_case_scenario': {
                'name': 'severe_recession',
                'details': {'impact_severity': 0.8}
            },
            'average_impact_severity': 0.6,
            'scenarios_with_high_impact': ['severe_recession'],
            'overall_stress_test_score': 0.72
        }

    def test_agent_initialization(self, agent):
        """Test agent initializes correctly."""
        assert agent.role == AgentRole.RISK_ANALYST
        assert hasattr(agent, 'client')
        assert hasattr(agent, 'finnhub_client')
        assert hasattr(agent, 'risk_categories')
        assert hasattr(agent, 'stress_scenarios')
        assert hasattr(agent, 'contrarian_signals')
        assert len(agent.risk_categories) == 6

    def test_risk_categories_defined(self, agent):
        """Test risk categories are properly defined."""
        expected_categories = {
            'market_risk', 'business_risk', 'financial_risk', 
            'operational_risk', 'strategic_risk', 'external_risk'
        }
        assert set(agent.risk_categories.keys()) == expected_categories
        
        # All categories should have descriptions and factors
        for category, config in agent.risk_categories.items():
            assert 'description' in config
            assert 'factors' in config
            assert len(config['factors']) > 0
            assert len(config['description']) > 20

    def test_stress_scenarios_defined(self, agent):
        """Test stress scenarios are properly defined."""
        expected_scenarios = {
            'mild_recession', 'severe_recession', 'sector_disruption',
            'company_crisis', 'interest_rate_shock', 'geopolitical_crisis'
        }
        assert set(agent.stress_scenarios.keys()) == expected_scenarios
        
        # All scenarios should have descriptions and assumptions
        for scenario, config in agent.stress_scenarios.items():
            assert 'description' in config
            assert 'assumptions' in config
            assert isinstance(config['assumptions'], list)
            assert len(config['assumptions']) > 0

    def test_contrarian_signals_defined(self, agent):
        """Test contrarian signals list is defined."""
        assert isinstance(agent.contrarian_signals, list)
        assert len(agent.contrarian_signals) > 5
        assert 'excessive_optimism' in agent.contrarian_signals
        assert 'consensus_too_strong' in agent.contrarian_signals

    @pytest.mark.asyncio
    async def test_validate_inputs_success(self, agent, sample_context):
        """Test input validation with valid inputs."""
        result = await agent.validate_inputs(sample_context)
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_inputs_missing_project_id(self, agent, sample_context):
        """Test input validation fails without project_id."""
        del sample_context['project_id']
        result = await agent.validate_inputs(sample_context)
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_inputs_missing_companies(self, agent, sample_context):
        """Test input validation fails without companies."""
        del sample_context['companies']
        result = await agent.validate_inputs(sample_context)
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_inputs_missing_thesis(self, agent, sample_context):
        """Test input validation fails without investment thesis."""
        del sample_context['investment_thesis']
        result = await agent.validate_inputs(sample_context)
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_inputs_empty_thesis(self, agent, sample_context):
        """Test input validation fails with empty investment thesis."""
        sample_context['investment_thesis'] = '   '
        result = await agent.validate_inputs(sample_context)
        assert result is False

    @pytest.mark.asyncio
    @patch('src.agents.risk_analyst.RiskAnalystAgent._comprehensive_risk_assessment')
    @patch('src.agents.risk_analyst.RiskAnalystAgent._contrarian_analysis')
    @patch('src.agents.risk_analyst.RiskAnalystAgent._stress_test_scenarios')
    @patch('src.agents.risk_analyst.RiskAnalystAgent._analyze_thesis_vulnerabilities')
    @patch('src.agents.risk_analyst.RiskAnalystAgent._analyze_portfolio_risks')
    @patch('src.agents.risk_analyst.RiskAnalystAgent._generate_risk_recommendations')
    async def test_analyze_success(self, mock_recommendations, mock_portfolio_risks,
                                 mock_vulnerabilities, mock_stress_test, mock_contrarian,
                                 mock_risk_assessment_func, agent, sample_context,
                                 mock_risk_assessment, mock_contrarian_analysis,
                                 mock_stress_test_results):
        """Test successful risk analysis workflow."""
        
        # Setup mocks
        mock_risk_assessment_func.return_value = mock_risk_assessment
        mock_contrarian.return_value = mock_contrarian_analysis
        mock_stress_test.return_value = mock_stress_test_results
        mock_vulnerabilities.return_value = {
            'overall_thesis_vulnerability': 0.65,
            'thesis_robustness_assessment': 'Moderate vulnerability with key dependencies'
        }
        mock_portfolio_risks.return_value = {
            'portfolio_risk_score': 0.55,
            'common_risks': [{'risk': 'market volatility', 'frequency': 2}]
        }
        mock_recommendations.return_value = {
            'high_priority': [],
            'medium_priority': [{'symbol': 'AAPL', 'action': 'Monitor closely'}]
        }

        result = await agent.analyze(sample_context)

        assert isinstance(result, AgentResult)
        assert result.success is True
        assert result.agent == AgentRole.RISK_ANALYST
        assert result.confidence > 0.0
        assert 'company_risk_analyses' in result.data
        assert 'portfolio_risks' in result.data
        assert 'risk_recommendations' in result.data
        assert len(result.data['company_risk_analyses']) == 2

    @pytest.mark.asyncio
    @patch('src.agents.risk_analyst.RiskAnalystAgent.client')
    async def test_comprehensive_risk_assessment(self, mock_client, agent, 
                                               sample_context, mock_risk_assessment):
        """Test comprehensive risk assessment."""
        
        # Setup mock LLM response
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps(mock_risk_assessment)
        mock_client.messages.create.return_value = mock_response

        # Mock Finnhub client
        with patch.object(agent.finnhub_client, 'get_company_profile') as mock_profile:
            with patch.object(agent.finnhub_client, 'get_company_news') as mock_news:
                mock_profile.return_value = {'description': 'Test company', 'marketCapitalization': 1000000}
                mock_news.return_value = []
                
                result = await agent._comprehensive_risk_assessment(
                    'AAPL', {'name': 'Apple Inc.'}, 'Test thesis', sample_context
                )

        assert 'overall_risk_score' in result
        assert 'confidence' in result
        assert 'key_risk_themes' in result
        assert 'risk_trend' in result
        assert 'market_risk' in result
        assert 'business_risk' in result
        
        # Verify score ranges
        assert 0.0 <= result['overall_risk_score'] <= 1.0
        assert 0.0 <= result['confidence'] <= 1.0

    @pytest.mark.asyncio
    @patch('src.agents.risk_analyst.RiskAnalystAgent.client')
    async def test_contrarian_analysis(self, mock_client, agent, mock_contrarian_analysis):
        """Test contrarian analysis."""
        
        # Setup mock LLM response
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps(mock_contrarian_analysis)
        mock_client.messages.create.return_value = mock_response

        result = await agent._contrarian_analysis(
            'AAPL', {'name': 'Apple Inc.'}, 'Test thesis', {}
        )

        assert 'thesis_challenges' in result
        assert 'contrarian_viewpoints' in result
        assert 'consensus_risks' in result
        assert 'structural_headwinds' in result
        assert 'timing_risks' in result
        assert 'valuation_concerns' in result
        assert 'thesis_vulnerability_score' in result
        
        # Verify structure
        assert isinstance(result['thesis_challenges'], list)
        assert isinstance(result['contrarian_viewpoints'], list)
        assert isinstance(result['consensus_risks'], dict)
        assert 0.0 <= result['thesis_vulnerability_score'] <= 1.0

    @pytest.mark.asyncio
    @patch('src.agents.risk_analyst.RiskAnalystAgent._analyze_scenario_impact')
    async def test_stress_test_scenarios(self, mock_scenario_impact, agent):
        """Test stress test scenarios."""
        
        # Setup mock scenario impact
        mock_scenario_impact.return_value = {
            'impact_severity': 0.6,
            'scenario_probability': 0.3,
            'recovery_difficulty': 0.4,
            'business_impact': {'revenue_impact': '15-20% decline'},
            'thesis_impact': 'Moderate impact on thesis',
            'summary': 'Manageable scenario impact'
        }
        
        result = await agent._stress_test_scenarios(
            'AAPL', {'name': 'Apple Inc.'}, 'Test thesis', {}
        )
        
        assert 'scenario_results' in result
        assert 'worst_case_scenario' in result
        assert 'average_impact_severity' in result
        assert 'overall_stress_test_score' in result
        
        # Should have analyzed all scenarios
        assert len(result['scenario_results']) == len(agent.stress_scenarios)
        
        # Verify worst case identified
        assert 'name' in result['worst_case_scenario']
        assert 'details' in result['worst_case_scenario']

    @pytest.mark.asyncio
    @patch('src.agents.risk_analyst.RiskAnalystAgent.client')
    async def test_analyze_scenario_impact(self, mock_client, agent):
        """Test individual scenario impact analysis."""
        
        mock_response_data = {
            'impact_severity': 0.7,
            'scenario_probability': 0.2,
            'recovery_difficulty': 0.6,
            'business_impact': {
                'revenue_impact': '25-30% revenue decline',
                'margin_impact': 'Significant compression',
                'operational_impact': 'Major restructuring needed'
            },
            'thesis_impact': 'Challenges core thesis assumptions',
            'company_resilience': 'Moderate resilience with strong balance sheet',
            'recovery_timeline': '18-24 months',
            'summary': 'High impact scenario requiring adaptation'
        }
        
        # Setup mock LLM response
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps(mock_response_data)
        mock_client.messages.create.return_value = mock_response

        scenario_config = agent.stress_scenarios['severe_recession']
        
        result = await agent._analyze_scenario_impact(
            'AAPL', {'name': 'Apple Inc.'}, 'Test thesis', 
            'severe_recession', scenario_config, {}
        )

        assert 'impact_severity' in result
        assert 'scenario_probability' in result
        assert 'recovery_difficulty' in result
        assert 'business_impact' in result
        assert 'thesis_impact' in result
        
        # Verify score ranges
        assert 0.0 <= result['impact_severity'] <= 1.0
        assert 0.0 <= result['scenario_probability'] <= 1.0
        assert 0.0 <= result['recovery_difficulty'] <= 1.0

    @pytest.mark.asyncio
    @patch('src.agents.risk_analyst.RiskAnalystAgent.client')
    async def test_analyze_thesis_vulnerabilities(self, mock_client, agent):
        """Test thesis vulnerability analysis."""
        
        mock_vulnerability_data = {
            'assumption_risks': [
                {
                    'assumption': 'EV adoption will accelerate',
                    'reliability': 'medium',
                    'invalidation_risk': 'Infrastructure delays could slow adoption',
                    'vulnerability_score': 0.6
                }
            ],
            'dependency_risks': [
                {
                    'dependency': 'Battery technology improvements',
                    'control_level': 'low',
                    'failure_impact': 'Could limit market growth',
                    'vulnerability_score': 0.5
                }
            ],
            'timing_risks': [],
            'execution_risks': [],
            'market_risks': [],
            'overall_thesis_vulnerability': 0.55,
            'highest_vulnerability_area': 'assumption_risks',
            'thesis_robustness_assessment': 'Moderate vulnerability with key dependencies',
            'key_monitoring_points': ['EV sales data', 'Infrastructure buildout', 'Battery costs']
        }
        
        # Setup mock LLM response
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps(mock_vulnerability_data)
        mock_client.messages.create.return_value = mock_response

        result = await agent._analyze_thesis_vulnerabilities(
            'AAPL', {'name': 'Apple Inc.'}, 'Test thesis', {'key_risk_themes': ['competition']}
        )

        assert 'assumption_risks' in result
        assert 'dependency_risks' in result
        assert 'timing_risks' in result
        assert 'execution_risks' in result
        assert 'market_risks' in result
        assert 'overall_thesis_vulnerability' in result
        
        # Verify structure
        assert isinstance(result['assumption_risks'], list)
        assert isinstance(result['dependency_risks'], list)
        assert 0.0 <= result['overall_thesis_vulnerability'] <= 1.0

    @pytest.mark.asyncio
    async def test_analyze_portfolio_risks(self, agent):
        """Test portfolio-level risk analysis."""
        
        company_risk_analyses = [
            {
                'symbol': 'AAPL',
                'overall_risk_score': 0.4,
                'thesis_vulnerabilities': {'overall_thesis_vulnerability': 0.5},
                'risk_assessment': {'key_risk_themes': ['competition', 'market risk']}
            },
            {
                'symbol': 'GOOGL',
                'overall_risk_score': 0.6,
                'thesis_vulnerabilities': {'overall_thesis_vulnerability': 0.7},
                'risk_assessment': {'key_risk_themes': ['regulation', 'market risk']}
            }
        ]
        
        with patch.object(agent, '_analyze_portfolio_correlations') as mock_correlations:
            with patch.object(agent, '_identify_portfolio_vulnerabilities') as mock_vulnerabilities:
                mock_correlations.return_value = {
                    'high_correlation_risks': ['market risk'],
                    'correlation_score': 0.5
                }
                mock_vulnerabilities.return_value = [
                    {'type': 'high_risk_concentration', 'severity': 'medium'}
                ]
                
                result = await agent._analyze_portfolio_risks(company_risk_analyses, 'Test thesis')

        assert 'portfolio_risk_score' in result
        assert 'portfolio_vulnerability_score' in result
        assert 'risk_concentration' in result
        assert 'risk_distribution' in result
        assert 'common_risks' in result
        assert 'correlation_analysis' in result
        assert 'portfolio_vulnerabilities' in result
        
        # Verify calculations
        expected_avg_risk = statistics.mean([0.4, 0.6])
        assert abs(result['portfolio_risk_score'] - expected_avg_risk) < 0.01
        
        # Verify risk distribution
        assert result['risk_distribution']['low_risk_companies'] == 1  # AAPL < 0.4 is False, so 0
        assert result['risk_distribution']['medium_risk_companies'] == 1  # AAPL in range
        assert result['risk_distribution']['high_risk_companies'] == 0  # None >= 0.7

    @pytest.mark.asyncio
    async def test_analyze_portfolio_correlations(self, agent):
        """Test portfolio correlation analysis."""
        
        company_risk_analyses = [
            {
                'symbol': 'AAPL',
                'risk_assessment': {'key_risk_themes': ['market risk', 'competition']}
            },
            {
                'symbol': 'GOOGL',
                'risk_assessment': {'key_risk_themes': ['market risk', 'regulation']}
            },
            {
                'symbol': 'MSFT',
                'risk_assessment': {'key_risk_themes': ['market risk', 'competition']}
            }
        ]
        
        result = await agent._analyze_portfolio_correlations(company_risk_analyses)
        
        assert 'high_correlation_risks' in result
        assert 'risk_theme_overlap' in result
        assert 'correlation_score' in result
        
        # 'market risk' appears in all 3 companies (100%), so should be high correlation
        assert 'market risk' in result['high_correlation_risks']
        assert result['risk_theme_overlap']['market risk'] == 3

    @pytest.mark.asyncio
    async def test_generate_risk_recommendations(self, agent):
        """Test risk recommendation generation."""
        
        company_risk_analyses = [
            {
                'symbol': 'AAPL',
                'overall_risk_score': 0.9,  # Very high risk
                'thesis_vulnerabilities': {
                    'key_monitoring_points': ['quarterly earnings', 'competitive position']
                }
            },
            {
                'symbol': 'GOOGL',
                'overall_risk_score': 0.65,  # Elevated risk
                'thesis_vulnerabilities': {
                    'key_monitoring_points': ['regulatory changes']
                }
            }
        ]
        
        portfolio_risks = {
            'portfolio_risk_score': 0.75,
            'common_risks': [
                {'risk': 'market volatility', 'frequency': 2}
            ]
        }
        
        result = await agent._generate_risk_recommendations(
            company_risk_analyses, portfolio_risks, 'Test thesis'
        )
        
        assert 'high_priority' in result
        assert 'medium_priority' in result
        assert 'monitoring' in result
        assert 'position_sizing' in result
        assert 'hedging' in result
        
        # Should have high priority action for AAPL (risk > 0.8)
        assert len(result['high_priority']) >= 1
        high_priority_symbols = [rec.get('symbol') for rec in result['high_priority'] if 'symbol' in rec]
        assert 'AAPL' in high_priority_symbols
        
        # Should have medium priority action for GOOGL (risk > 0.6)
        assert len(result['medium_priority']) >= 1
        medium_priority_symbols = [rec.get('symbol') for rec in result['medium_priority'] if 'symbol' in rec]
        assert 'GOOGL' in medium_priority_symbols

    def test_assess_risk_diversification(self, agent):
        """Test risk diversification assessment."""
        
        # Test good diversification
        diverse_analyses = [
            {'overall_risk_score': 0.3},
            {'overall_risk_score': 0.7},
            {'overall_risk_score': 0.5}
        ]
        
        result = agent._assess_risk_diversification(diverse_analyses)
        assert 'good risk diversification' in result.lower()
        
        # Test poor diversification
        similar_analyses = [
            {'overall_risk_score': 0.5},
            {'overall_risk_score': 0.51},
            {'overall_risk_score': 0.49}
        ]
        
        result = agent._assess_risk_diversification(similar_analyses)
        assert 'poor risk diversification' in result.lower()
        
        # Test single company
        single_analysis = [{'overall_risk_score': 0.5}]
        result = agent._assess_risk_diversification(single_analysis)
        assert 'insufficient companies' in result.lower()

    @pytest.mark.asyncio
    async def test_calculate_confidence(self, agent):
        """Test confidence calculation."""
        
        company_risk_analyses = [
            {
                'risk_assessment': {'confidence': 0.8}
            },
            {
                'risk_assessment': {'confidence': 0.7}
            }
        ]
        
        portfolio_risks = {
            'portfolio_risk_score': 0.5  # Moderate risk
        }
        
        confidence = await agent._calculate_confidence(company_risk_analyses, portfolio_risks)
        
        assert 0.0 <= confidence <= 1.0
        assert isinstance(confidence, float)

    def test_get_fallback_risk_assessment(self, agent):
        """Test fallback risk assessment."""
        
        fallback = agent._get_fallback_risk_assessment()
        
        assert 'overall_risk_score' in fallback
        assert 'confidence' in fallback
        assert 'key_risk_themes' in fallback
        assert 'risk_trend' in fallback
        
        # Should have all risk categories
        for category in agent.risk_categories.keys():
            assert category in fallback

    def test_get_fallback_contrarian_analysis(self, agent):
        """Test fallback contrarian analysis."""
        
        fallback = agent._get_fallback_contrarian_analysis()
        
        assert 'thesis_challenges' in fallback
        assert 'contrarian_viewpoints' in fallback
        assert 'consensus_risks' in fallback
        assert 'structural_headwinds' in fallback
        assert 'timing_risks' in fallback
        assert 'valuation_concerns' in fallback
        assert 'thesis_vulnerability_score' in fallback

    def test_get_data_sources(self, agent):
        """Test data sources list."""
        
        sources = agent._get_data_sources()
        
        assert isinstance(sources, list)
        assert len(sources) > 0
        assert all(isinstance(source, str) for source in sources)
        assert any('Claude' in source for source in sources)
        assert any('Finnhub' in source for source in sources)

    def test_generate_analysis_reasoning(self, agent):
        """Test analysis reasoning generation."""
        
        result_data = {
            'company_risk_analyses': [
                {'overall_risk_score': 0.4},
                {'overall_risk_score': 0.6}
            ],
            'portfolio_risks': {
                'portfolio_risk_score': 0.5
            },
            'risk_recommendations': {
                'high_priority': [{'action': 'Reduce position'}]
            }
        }
        
        reasoning = agent._generate_analysis_reasoning(result_data)
        
        assert isinstance(reasoning, str)
        assert len(reasoning) > 50
        assert '2 companies' in reasoning
        assert 'moderate' in reasoning.lower()  # Should mention moderate risk
        assert '1 high-priority' in reasoning

    def test_get_methodology_summary(self, agent):
        """Test methodology summary."""
        
        methodology = agent._get_methodology_summary()
        
        assert isinstance(methodology, dict)
        assert 'risk_assessment' in methodology
        assert 'contrarian_analysis' in methodology
        assert 'stress_testing' in methodology
        assert 'vulnerability_analysis' in methodology
        assert 'portfolio_analysis' in methodology
        assert 'recommendations' in methodology
        assert all(isinstance(v, str) for v in methodology.values())

    @pytest.mark.asyncio
    @patch('src.agents.risk_analyst.RiskAnalystAgent._comprehensive_risk_assessment')
    async def test_analyze_handles_exceptions(self, mock_risk_assessment, agent, sample_context):
        """Test that analyze handles exceptions gracefully."""
        
        # Setup mock to raise exception
        mock_risk_assessment.side_effect = Exception("Test error")

        result = await agent.analyze(sample_context)

        assert isinstance(result, AgentResult)
        assert result.success is False
        assert result.confidence == 0.0
        assert len(result.errors) == 1
        assert "Test error" in result.errors[0]

    @pytest.mark.asyncio
    async def test_portfolio_risks_empty_analyses(self, agent):
        """Test portfolio risk analysis with empty company analyses."""
        
        result = await agent._analyze_portfolio_risks([], 'Test thesis')
        
        assert 'error' in result

    @pytest.mark.asyncio
    async def test_risk_assessment_api_failure(self, agent):
        """Test risk assessment with API failure."""
        
        with patch.object(agent.finnhub_client, 'get_company_profile') as mock_profile:
            with patch.object(agent.finnhub_client, 'get_company_news') as mock_news:
                mock_profile.side_effect = Exception("API failure")
                mock_news.side_effect = Exception("API failure")
                
                with patch.object(agent, 'client') as mock_client:
                    mock_response = MagicMock()
                    mock_response.content = [MagicMock()]
                    mock_response.content[0].text = "Invalid JSON response"
                    mock_client.messages.create.return_value = mock_response
                    
                    result = await agent._comprehensive_risk_assessment(
                        'AAPL', {'name': 'Apple Inc.'}, 'Test thesis', {}
                    )
                    
                    # Should return fallback assessment
                    assert result['overall_risk_score'] == 0.5
                    assert result['confidence'] == 0.3

    @pytest.mark.asyncio  
    async def test_identify_portfolio_vulnerabilities(self, agent):
        """Test portfolio vulnerability identification."""
        
        # High vulnerability companies
        company_risk_analyses = [
            {
                'symbol': 'AAPL',
                'overall_risk_score': 0.8,  # High risk
                'thesis_vulnerabilities': {'overall_thesis_vulnerability': 0.9}
            },
            {
                'symbol': 'GOOGL', 
                'overall_risk_score': 0.75,  # High risk
                'thesis_vulnerabilities': {'overall_thesis_vulnerability': 0.8}
            }
        ]
        
        result = await agent._identify_portfolio_vulnerabilities(company_risk_analyses, 'Test thesis')
        
        assert isinstance(result, list)
        
        # Should identify thesis vulnerability (avg > 0.6)
        thesis_vuln = next((v for v in result if v['type'] == 'thesis_vulnerability'), None)
        assert thesis_vuln is not None
        assert thesis_vuln['severity'] == 'high'  # avg > 0.8
        
        # Should identify high risk concentration (100% of companies have risk > 0.7)
        risk_concentration = next((v for v in result if v['type'] == 'high_risk_concentration'), None)
        assert risk_concentration is not None
        assert risk_concentration['affected_companies'] == 2