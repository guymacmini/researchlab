"""Test agent orchestration and individual agents."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime

from src.agents import (
    BaseAgent, AgentRole, AgentMessage, AgentResult,
    AgentOrchestrator, ResearchDirectorAgent, FundamentalAnalystAgent
)
from src.data.models import ResearchProject, ResearchStatus


class MockAgent(BaseAgent):
    """Mock agent for testing."""
    
    role = AgentRole.RESEARCH_DIRECTOR
    
    async def validate_inputs(self, context):
        return True
    
    async def analyze(self, context):
        return AgentResult(
            agent=self.role,
            success=True,
            data={'test': 'data'},
            confidence=0.8,
            sources=['test'],
            reasoning='Test reasoning'
        )


class TestAgentMessage:
    """Test AgentMessage dataclass."""
    
    def test_create_message(self):
        """Test creating an agent message."""
        message = AgentMessage(
            sender=AgentRole.RESEARCH_DIRECTOR,
            recipient=AgentRole.FUNDAMENTAL_ANALYST,
            content={'query': 'test query'},
            correlation_id='test-123'
        )
        
        assert message.sender == AgentRole.RESEARCH_DIRECTOR
        assert message.recipient == AgentRole.FUNDAMENTAL_ANALYST
        assert message.content['query'] == 'test query'
        assert message.correlation_id == 'test-123'


class TestAgentResult:
    """Test AgentResult dataclass."""
    
    def test_create_result(self):
        """Test creating an agent result."""
        result = AgentResult(
            agent=AgentRole.FUNDAMENTAL_ANALYST,
            success=True,
            data={'companies': 10},
            confidence=0.85,
            sources=['finnhub', 'alpha_vantage'],
            reasoning='Strong fundamental analysis',
            errors=None
        )
        
        assert result.agent == AgentRole.FUNDAMENTAL_ANALYST
        assert result.success is True
        assert result.data['companies'] == 10
        assert result.confidence == 0.85
        assert len(result.sources) == 2
        assert result.errors is None


class TestBaseAgent:
    """Test BaseAgent base class."""
    
    def test_agent_initialization(self):
        """Test agent initialization."""
        config = {'test': 'config'}
        agent = MockAgent(config)
        
        assert agent.config == config
        assert agent.role == AgentRole.RESEARCH_DIRECTOR
    
    def test_confidence_level_mapping(self):
        """Test confidence level conversion."""
        agent = MockAgent()
        
        assert agent.get_confidence_level(0.9) == "High"
        assert agent.get_confidence_level(0.7) == "Medium"  
        assert agent.get_confidence_level(0.3) == "Low"
        assert agent.get_confidence_level(0.4) == "Low"
    
    @pytest.mark.asyncio
    async def test_handle_message_default(self):
        """Test default message handling."""
        agent = MockAgent()
        message = AgentMessage(
            sender=AgentRole.FUNDAMENTAL_ANALYST,
            recipient=AgentRole.RESEARCH_DIRECTOR,
            content={'data': 'test'},
            correlation_id='test'
        )
        
        # Default implementation returns None
        result = await agent.handle_message(message)
        assert result is None


class TestAgentOrchestrator:
    """Test AgentOrchestrator."""
    
    def test_orchestrator_initialization(self):
        """Test orchestrator initialization."""
        orchestrator = AgentOrchestrator()
        
        # Should have initialized agents
        assert AgentRole.RESEARCH_DIRECTOR in orchestrator.agents
        assert AgentRole.FUNDAMENTAL_ANALYST in orchestrator.agents
        assert len(orchestrator.active_sessions) == 0
    
    @pytest.mark.asyncio
    async def test_start_research_project(self):
        """Test starting a research project."""
        orchestrator = AgentOrchestrator()
        
        session = await orchestrator.start_research_project("test-project-123")
        
        assert session.project_id == "test-project-123"
        assert session.correlation_id is not None
        assert len(session.agent_roles) == 2  # Default agents
        assert "test-project-123" in orchestrator.active_sessions
    
    @pytest.mark.asyncio
    async def test_send_message(self):
        """Test sending messages through orchestrator."""
        orchestrator = AgentOrchestrator()
        
        message = AgentMessage(
            sender=AgentRole.RESEARCH_DIRECTOR,
            recipient=AgentRole.FUNDAMENTAL_ANALYST,
            content={'test': 'data'},
            correlation_id='test'
        )
        
        await orchestrator.send_message(message)
        
        # Message should be in queue
        assert not orchestrator.message_queue.empty()
    
    @pytest.mark.asyncio
    async def test_stop_research_project(self):
        """Test stopping a research project."""
        orchestrator = AgentOrchestrator()
        
        # Start a project
        session = await orchestrator.start_research_project("test-project")
        assert "test-project" in orchestrator.active_sessions
        
        # Stop the project
        await orchestrator.stop_research_project("test-project")
        assert "test-project" not in orchestrator.active_sessions


class TestResearchDirectorAgent:
    """Test ResearchDirectorAgent."""
    
    def test_agent_role(self):
        """Test agent has correct role."""
        agent = ResearchDirectorAgent()
        assert agent.role == AgentRole.RESEARCH_DIRECTOR
    
    @pytest.mark.asyncio
    async def test_validate_inputs_success(self):
        """Test successful input validation."""
        agent = ResearchDirectorAgent()
        
        context = {
            'query': 'Which AI companies will benefit from increased adoption?',
            'user_id': 'test-user',
            'project_id': 'test-project'
        }
        
        is_valid = await agent.validate_inputs(context)
        assert is_valid is True
    
    @pytest.mark.asyncio
    async def test_validate_inputs_missing_fields(self):
        """Test input validation with missing fields."""
        agent = ResearchDirectorAgent()
        
        # Missing query
        context = {
            'user_id': 'test-user',
            'project_id': 'test-project'
        }
        
        is_valid = await agent.validate_inputs(context)
        assert is_valid is False
    
    @pytest.mark.asyncio
    async def test_validate_inputs_short_query(self):
        """Test input validation with too short query."""
        agent = ResearchDirectorAgent()
        
        context = {
            'query': 'AI',  # Too short
            'user_id': 'test-user',
            'project_id': 'test-project'
        }
        
        is_valid = await agent.validate_inputs(context)
        assert is_valid is False
    
    @pytest.mark.asyncio 
    @patch('src.agents.research_director.anthropic.Anthropic')
    async def test_analyze_success(self, mock_anthropic):
        """Test successful analysis."""
        # Mock Anthropic API response
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = '''
        {
            "thesis_summary": "AI adoption will drive technology company growth",
            "causal_chain": ["AI adoption increases", "Tech companies benefit", "Stock prices rise"],
            "investment_horizon": "medium",
            "risk_level": "moderate",
            "primary_sectors": ["Technology"],
            "geographic_scope": "us_only",
            "market_cap_preference": "large_cap",
            "clarity_score": 8,
            "analysis_notes": "Clear thesis with strong rationale"
        }
        '''
        
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client
        
        agent = ResearchDirectorAgent()
        context = {
            'query': 'Which AI companies will benefit most from increased AI adoption?',
            'user_id': 'test-user',
            'project_id': 'test-project',
            'scope': {}
        }
        
        result = await agent.analyze(context)
        
        assert result.success is True
        assert result.confidence > 0
        assert 'thesis_analysis' in result.data
        assert 'research_plan' in result.data
        assert len(result.sources) > 0


class TestFundamentalAnalystAgent:
    """Test FundamentalAnalystAgent."""
    
    def test_agent_role(self):
        """Test agent has correct role."""
        agent = FundamentalAnalystAgent()
        assert agent.role == AgentRole.FUNDAMENTAL_ANALYST
    
    @pytest.mark.asyncio
    async def test_validate_inputs_success(self):
        """Test successful input validation."""
        agent = FundamentalAnalystAgent()
        
        context = {
            'project_id': 'test-project',
            'query': 'AI investment opportunities'
        }
        
        is_valid = await agent.validate_inputs(context)
        assert is_valid is True
    
    @pytest.mark.asyncio
    async def test_validate_inputs_missing_fields(self):
        """Test input validation with missing fields."""
        agent = FundamentalAnalystAgent()
        
        # Missing project_id
        context = {
            'query': 'AI investment opportunities'
        }
        
        is_valid = await agent.validate_inputs(context)
        assert is_valid is False
    
    def test_financial_health_calculation(self):
        """Test financial health scoring."""
        agent = FundamentalAnalystAgent()
        
        # Strong financials
        strong_financials = {
            'roe': 0.20,  # Strong ROE
            'revenue_growth_yoy': 0.25,  # Strong growth
            'operating_margin': 0.25,  # Strong margins  
            'debt_to_equity': 0.2,  # Low debt
            'current_ratio': 2.0  # Good liquidity
        }
        
        score = agent._calculate_financial_health(strong_financials)
        assert score >= 7.0  # Should be high score
        
        # Weak financials
        weak_financials = {
            'roe': 0.05,  # Weak ROE
            'revenue_growth_yoy': -0.1,  # Declining
            'operating_margin': 0.05,  # Weak margins
            'debt_to_equity': 2.0,  # High debt
            'current_ratio': 0.8  # Poor liquidity
        }
        
        score = agent._calculate_financial_health(weak_financials)
        assert score <= 5.0  # Should be low score
    
    def test_fallback_relevance_score(self):
        """Test fallback relevance scoring."""
        agent = FundamentalAnalystAgent()
        
        # Tech company with AI query
        tech_company = {'sector': 'Technology'}
        ai_context = {'query': 'AI companies to invest in'}
        
        score = agent._fallback_relevance_score(tech_company, ai_context)
        assert score >= 8.0  # Should be high relevance
        
        # Non-tech company with tech query
        finance_company = {'sector': 'Financial Services'}
        score = agent._fallback_relevance_score(finance_company, ai_context)
        assert score == 6.0  # Should be moderate relevance


@pytest.mark.asyncio
@patch('src.agents.orchestrator.DatabaseManager')
async def test_research_session_workflow(mock_db_manager):
    """Test complete research session workflow."""
    # Mock database operations
    mock_db = AsyncMock()
    mock_db_manager.return_value.__aenter__.return_value = mock_db
    mock_db.get.return_value = MagicMock(
        id='test-project',
        user_id='test-user', 
        query='Test AI investment query',
        scope={}
    )
    
    # Mock agent results
    with patch.object(ResearchDirectorAgent, 'analyze') as mock_rd_analyze, \
         patch.object(FundamentalAnalystAgent, 'analyze') as mock_fa_analyze, \
         patch.object(ResearchDirectorAgent, 'validate_inputs', return_value=True), \
         patch.object(FundamentalAnalystAgent, 'validate_inputs', return_value=True):
        
        mock_rd_analyze.return_value = AgentResult(
            agent=AgentRole.RESEARCH_DIRECTOR,
            success=True,
            data={'research_plan': 'Generated plan'},
            confidence=0.8,
            sources=['anthropic'],
            reasoning='Research direction defined'
        )
        
        mock_fa_analyze.return_value = AgentResult(
            agent=AgentRole.FUNDAMENTAL_ANALYST,
            success=True,
            data={'companies_analyzed': 5},
            confidence=0.75,
            sources=['financial_apis'],
            reasoning='Companies analyzed'
        )
        
        orchestrator = AgentOrchestrator()
        results = await orchestrator.execute_research_workflow('test-project')
        
        assert len(results) == 2
        assert AgentRole.RESEARCH_DIRECTOR in results
        assert AgentRole.FUNDAMENTAL_ANALYST in results
        assert results[AgentRole.RESEARCH_DIRECTOR].success is True
        assert results[AgentRole.FUNDAMENTAL_ANALYST].success is True