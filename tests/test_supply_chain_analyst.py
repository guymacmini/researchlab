"""Tests for Supply Chain Analyst agent."""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.agents.supply_chain_analyst import SupplyChainAnalystAgent
from src.agents.base import AgentRole, AgentResult


class TestSupplyChainAnalystAgent:
    """Test cases for Supply Chain Analyst agent."""

    @pytest.fixture
    def agent(self):
        """Create a Supply Chain Analyst agent for testing."""
        with patch('src.agents.supply_chain_analyst.settings') as mock_settings:
            mock_settings.api.anthropic_api_key = "test_anthropic_key"
            mock_settings.api.finnhub_api_key = "test_finnhub_key"
            with patch('src.agents.supply_chain_analyst.FinnhubClient'):
                return SupplyChainAnalystAgent()

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
            'investment_thesis': 'Growth in electric vehicle adoption will benefit component suppliers',
            'query': 'Analyze supply chain relationships for EV growth thesis'
        }

    @pytest.fixture
    def mock_llm_response(self):
        """Mock LLM response for relationship extraction."""
        return {
            'suppliers': [
                {
                    'name': 'Taiwan Semiconductor',
                    'symbol': 'TSM',
                    'description': 'Primary chip supplier',
                    'confidence': 'high'
                },
                {
                    'name': 'Foxconn',
                    'symbol': None,
                    'description': 'Assembly and manufacturing partner',
                    'confidence': 'high'
                }
            ],
            'customers': [
                {
                    'name': 'AT&T',
                    'symbol': 'T',
                    'description': 'Telecommunications partner for services',
                    'confidence': 'medium'
                }
            ],
            'partners': [
                {
                    'name': 'Google',
                    'symbol': 'GOOGL',
                    'description': 'Maps and search integration',
                    'confidence': 'high'
                }
            ],
            'competitors': [
                {
                    'name': 'Samsung',
                    'symbol': None,
                    'description': 'Smartphone and technology competitor',
                    'confidence': 'high'
                }
            ],
            'distributors': [],
            'subsidiaries': [],
            'parent': []
        }

    @pytest.fixture
    def mock_supply_chain_analysis(self):
        """Mock supply chain impact analysis."""
        return {
            'supply_chain_risks': [
                'High dependency on Taiwan semiconductor manufacturing',
                'Geographic concentration in Asia for key components'
            ],
            'supply_chain_opportunities': [
                'Strong partnerships with leading technology companies',
                'Diversified supplier base reduces single points of failure'
            ],
            'second_order_effects': [
                'Taiwan geopolitical risks could impact chip supply',
                'Currency fluctuations affect component costs'
            ],
            'thesis_impact': 'Supply chain supports growth thesis through strong partnerships',
            'overall_risk_score': 0.6,
            'opportunity_score': 0.7,
            'thesis_alignment_score': 0.8
        }

    def test_agent_initialization(self, agent):
        """Test agent initializes correctly."""
        assert agent.role == AgentRole.SUPPLY_CHAIN_ANALYST
        assert hasattr(agent, 'client')
        assert hasattr(agent, 'finnhub_client')
        assert hasattr(agent, 'relationship_types')
        assert len(agent.relationship_types) == 8

    def test_relationship_types_defined(self, agent):
        """Test that all relationship types are properly defined."""
        expected_types = {
            'supplier', 'customer', 'partner', 'competitor',
            'distributor', 'contractor', 'subsidiary', 'parent'
        }
        assert set(agent.relationship_types.keys()) == expected_types
        
        # Verify descriptions exist
        for rel_type, description in agent.relationship_types.items():
            assert description
            assert len(description) > 10

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
    async def test_validate_inputs_empty_companies(self, agent, sample_context):
        """Test input validation fails with empty companies list."""
        sample_context['companies'] = []
        result = await agent.validate_inputs(sample_context)
        assert result is False

    @pytest.mark.asyncio
    @patch('src.agents.supply_chain_analyst.SupplyChainAnalystAgent._extract_company_relationships')
    @patch('src.agents.supply_chain_analyst.SupplyChainAnalystAgent._analyze_supply_chain_impact')
    @patch('src.agents.supply_chain_analyst.SupplyChainAnalystAgent._analyze_relationship_network')
    async def test_analyze_success(self, mock_network_analysis, mock_impact_analysis, 
                                 mock_extract_relationships, agent, sample_context,
                                 mock_llm_response, mock_supply_chain_analysis):
        """Test successful analysis workflow."""
        
        # Setup mocks
        mock_extract_relationships.return_value = mock_llm_response
        mock_impact_analysis.return_value = mock_supply_chain_analysis
        mock_network_analysis.return_value = {
            'interconnections': [],
            'network_risks': ['Test network risk'],
            'network_opportunities': ['Test network opportunity'],
            'portfolio_diversification': 'Well-diversified',
            'systemic_risk_score': 0.3
        }

        result = await agent.analyze(sample_context)

        assert isinstance(result, AgentResult)
        assert result.success is True
        assert result.agent == AgentRole.SUPPLY_CHAIN_ANALYST
        assert result.confidence > 0.0
        assert 'company_analyses' in result.data
        assert 'network_analysis' in result.data
        assert len(result.data['company_analyses']) == 2

        # Verify method calls
        mock_extract_relationships.assert_called()
        mock_impact_analysis.assert_called()
        mock_network_analysis.assert_called()

    @pytest.mark.asyncio
    @patch('src.data.clients.finnhub_client.FinnhubClient.get_company_profile')
    @patch('src.agents.supply_chain_analyst.SupplyChainAnalystAgent._llm_extract_relationships')
    async def test_extract_company_relationships(self, mock_llm_extract, mock_profile,
                                               agent, mock_llm_response):
        """Test company relationship extraction."""
        
        # Setup mocks
        mock_profile.return_value = {
            'description': 'Apple Inc. designs and manufactures consumer electronics',
            'name': 'Apple Inc.'
        }
        mock_llm_extract.return_value = mock_llm_response

        company_data = {'symbol': 'AAPL', 'name': 'Apple Inc.'}
        relationships = await agent._extract_company_relationships('AAPL', company_data)

        assert isinstance(relationships, dict)
        assert 'suppliers' in relationships
        assert 'customers' in relationships
        assert len(relationships['suppliers']) == 2
        assert len(relationships['customers']) == 1
        
        # Verify supplier data
        supplier = relationships['suppliers'][0]
        assert supplier['name'] == 'Taiwan Semiconductor'
        assert supplier['confidence'] == 'high'

    @pytest.mark.asyncio
    @patch('src.agents.supply_chain_analyst.SupplyChainAnalystAgent.client')
    async def test_llm_extract_relationships(self, mock_client, agent, mock_llm_response):
        """Test LLM-based relationship extraction."""
        
        # Setup mock LLM response
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps(mock_llm_response)
        mock_client.messages.create.return_value = mock_response

        company_data = {'name': 'Apple Inc.'}
        description = 'Apple designs consumer electronics'
        
        result = await agent._llm_extract_relationships('AAPL', description, company_data)

        assert result == mock_llm_response
        mock_client.messages.create.assert_called_once()
        
        # Verify prompt structure
        call_args = mock_client.messages.create.call_args
        messages = call_args.kwargs['messages']
        assert len(messages) == 1
        assert 'AAPL' in messages[0]['content']
        assert 'JSON' in messages[0]['content']

    @pytest.mark.asyncio
    @patch('src.agents.supply_chain_analyst.SupplyChainAnalystAgent.client')
    async def test_analyze_supply_chain_impact(self, mock_client, agent, mock_supply_chain_analysis):
        """Test supply chain impact analysis."""
        
        # Setup mock LLM response
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps(mock_supply_chain_analysis)
        mock_client.messages.create.return_value = mock_response

        company_data = {'name': 'Apple Inc.'}
        relationships = {'suppliers': [], 'customers': []}
        thesis = 'Test investment thesis'
        
        result = await agent._analyze_supply_chain_impact('AAPL', company_data, relationships, thesis)

        assert result == mock_supply_chain_analysis
        assert 'overall_risk_score' in result
        assert 'opportunity_score' in result
        assert 'thesis_alignment_score' in result

    def test_find_interconnections(self, agent):
        """Test finding interconnections between companies."""
        
        network = {
            'AAPL': {
                'suppliers': [
                    {'name': 'Taiwan Semiconductor', 'symbol': 'TSM', 'confidence': 'high'}
                ],
                'customers': []
            },
            'TSM': {
                'suppliers': [],
                'customers': [
                    {'name': 'Apple Inc.', 'symbol': 'AAPL', 'confidence': 'high'}
                ]
            }
        }

        connections = agent._find_interconnections('AAPL', 'TSM', network)

        assert len(connections) == 2  # Bidirectional relationship
        assert connections[0]['company1'] == 'AAPL'
        assert connections[0]['company2'] == 'TSM'

    def test_deduplicate_relationships(self, agent):
        """Test relationship deduplication."""
        
        relationships = [
            {'name': 'Taiwan Semiconductor', 'symbol': 'TSM', 'confidence': 'high'},
            {'name': 'taiwan semiconductor', 'symbol': 'TSM', 'confidence': 'medium'},
            {'name': 'Apple Inc.', 'symbol': 'AAPL', 'confidence': 'low'}
        ]

        result = agent._deduplicate_relationships(relationships)

        assert len(result) == 2  # Duplicates removed
        # Should keep the higher confidence version
        tsm_rel = next(r for r in result if r['symbol'] == 'TSM')
        assert tsm_rel['confidence'] == 'high'

    def test_identify_network_risks(self, agent):
        """Test network risk identification."""
        
        network = {
            'AAPL': {
                'supplier': [
                    {'name': 'Taiwan Semiconductor', 'symbol': 'TSM'}
                ],
                'customer': []
            },
            'NVDA': {
                'supplier': [
                    {'name': 'Taiwan Semiconductor', 'symbol': 'TSM'}
                ],
                'customer': []
            }
        }

        interconnections = []
        risks = agent._identify_network_risks(network, interconnections)

        assert len(risks) >= 1
        assert any('concentration risk' in risk.lower() for risk in risks)

    def test_assess_diversification(self, agent):
        """Test portfolio diversification assessment."""
        
        # Well-diversified network
        diversified_network = {
            'AAPL': {
                'supplier': [{'name': f'Supplier{i}'} for i in range(8)],
                'customer': [{'name': f'Customer{i}'} for i in range(4)]
            }
        }
        
        result = agent._assess_diversification(diversified_network)
        assert 'well-diversified' in result.lower()

        # Limited diversification  
        limited_network = {
            'AAPL': {
                'supplier': [{'name': 'Supplier1'}],
                'customer': [{'name': 'Customer1'}]
            }
        }
        
        result = agent._assess_diversification(limited_network)
        assert 'limited' in result.lower()

    def test_calculate_systemic_risk(self, agent):
        """Test systemic risk calculation."""
        
        network = {
            'AAPL': {'supplier': [], 'customer': []},
            'GOOGL': {'supplier': [], 'customer': []}
        }

        risk_score = agent._calculate_systemic_risk(network)

        assert 0.0 <= risk_score <= 1.0
        assert isinstance(risk_score, float)

    @pytest.mark.asyncio
    async def test_calculate_confidence(self, agent):
        """Test confidence calculation."""
        
        company_analyses = [
            {
                'symbol': 'AAPL',
                'relationships': {
                    'suppliers': [{'name': 'TSM'}],
                    'customers': [{'name': 'Customer1'}]
                },
                'supply_chain_analysis': {'overall_risk_score': 0.5}
            }
        ]
        
        network_analysis = {'interconnections': []}
        
        confidence = await agent._calculate_confidence(company_analyses, network_analysis)
        
        assert 0.0 <= confidence <= 1.0
        assert isinstance(confidence, float)

    def test_get_data_sources(self, agent):
        """Test data sources list."""
        
        sources = agent._get_data_sources()
        
        assert isinstance(sources, list)
        assert len(sources) > 0
        assert all(isinstance(source, str) for source in sources)
        assert 'Finnhub' in str(sources)

    def test_generate_analysis_reasoning(self, agent):
        """Test analysis reasoning generation."""
        
        result_data = {
            'company_analyses': [
                {
                    'symbol': 'AAPL',
                    'relationships': {
                        'suppliers': [{'name': 'TSM'}],
                        'customers': []
                    }
                }
            ],
            'network_analysis': {
                'network_risks': ['Risk1', 'Risk2'],
                'network_opportunities': ['Opp1']
            }
        }
        
        reasoning = agent._generate_analysis_reasoning(result_data)
        
        assert isinstance(reasoning, str)
        assert len(reasoning) > 50
        assert '1 companies' in reasoning
        assert '2 network-level risks' in reasoning

    def test_get_methodology_summary(self, agent):
        """Test methodology summary."""
        
        methodology = agent._get_methodology_summary()
        
        assert isinstance(methodology, dict)
        assert 'relationship_extraction' in methodology
        assert 'network_analysis' in methodology
        assert 'risk_assessment' in methodology
        assert all(isinstance(v, str) for v in methodology.values())

    @pytest.mark.asyncio
    @patch('src.agents.supply_chain_analyst.SupplyChainAnalystAgent._extract_company_relationships')
    async def test_analyze_handles_exceptions(self, mock_extract, agent, sample_context):
        """Test that analyze handles exceptions gracefully."""
        
        # Setup mock to raise exception
        mock_extract.side_effect = Exception("Test error")

        result = await agent.analyze(sample_context)

        assert isinstance(result, AgentResult)
        assert result.success is False
        assert result.confidence == 0.0
        assert len(result.errors) == 1
        assert "Test error" in result.errors[0]

    def test_empty_relationships_handling(self, agent):
        """Test handling of empty relationship lists."""
        
        empty_relationships = []
        result = agent._deduplicate_relationships(empty_relationships)
        assert result == []

        # Test network analysis with empty data
        empty_network = {}
        risks = agent._identify_network_risks(empty_network, [])
        assert isinstance(risks, list)

    @pytest.mark.asyncio
    async def test_llm_extraction_json_parsing_error(self, agent):
        """Test LLM extraction handles JSON parsing errors."""
        
        with patch.object(agent, 'client') as mock_client:
            # Mock response with invalid JSON
            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = "Invalid JSON response"
            mock_client.messages.create.return_value = mock_response

            result = await agent._llm_extract_relationships('AAPL', 'test desc', {'name': 'Apple'})

            # Should return empty relationships structure
            assert isinstance(result, dict)
            assert all(isinstance(relationships, list) for relationships in result.values())
            assert all(len(relationships) == 0 for relationships in result.values())

    @pytest.mark.asyncio
    @patch('src.data.clients.finnhub_client.FinnhubClient.get_company_news')
    async def test_extract_relationships_from_news(self, mock_news, agent):
        """Test relationship extraction from news."""
        
        # Setup mock news data
        mock_news.return_value = [
            {
                'headline': 'Apple partners with Tesla for new project',
                'summary': 'Strategic partnership announced for electric vehicle components'
            }
        ]
        
        with patch.object(agent, '_llm_extract_relationships') as mock_llm:
            mock_llm.return_value = {
                'partners': [{'name': 'Tesla', 'symbol': 'TSLA', 'confidence': 'high'}],
                'suppliers': [],
                'customers': [],
                'competitors': [],
                'distributors': [],
                'subsidiaries': [],
                'parent': [],
                'contractor': []
            }
            
            relationships = await agent._extract_relationships_from_news('AAPL')
            
            assert 'partners' in relationships
            assert len(relationships['partners']) == 1
            assert relationships['partners'][0]['source'] == 'news'
            assert relationships['partners'][0]['confidence'] == 'medium'  # News confidence is medium