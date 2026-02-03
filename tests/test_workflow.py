"""Tests for research workflow orchestration."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from src.core.workflow import (
    ResearchWorkflowOrchestrator, 
    WorkflowSession, 
    WorkflowStage, 
    WorkflowStatus
)
from src.agents.base import AgentRole, AgentResult


class TestResearchWorkflowOrchestrator:
    """Test cases for Research Workflow Orchestrator."""

    @pytest.fixture
    def orchestrator(self):
        """Create workflow orchestrator for testing."""
        with patch('src.core.workflow.AgentOrchestrator'):
            with patch('src.core.workflow.GoogleSheetsOutputManager'):
                with patch('src.core.workflow.DatabaseManager'):
                    return ResearchWorkflowOrchestrator()

    @pytest.fixture
    def sample_research_request(self):
        """Sample research request for testing."""
        return {
            'project_id': 'test-project-123',
            'query': 'Analyze AI companies for growth potential',
            'investment_thesis': 'AI adoption will drive significant growth',
            'companies': [
                {'symbol': 'AAPL', 'name': 'Apple Inc.', 'sector': 'Technology'},
                {'symbol': 'GOOGL', 'name': 'Alphabet Inc.', 'sector': 'Technology'}
            ],
            'time_horizon': 12
        }

    def test_orchestrator_initialization(self, orchestrator):
        """Test orchestrator initializes correctly."""
        assert orchestrator.agent_orchestrator is not None
        assert orchestrator.sheets_output is not None
        assert orchestrator.db_manager is not None
        
        # Test workflow stages are defined
        assert len(orchestrator.workflow_stages) > 0
        assert WorkflowStage.INITIALIZATION in orchestrator.workflow_stages
        assert WorkflowStage.COMPLETED == orchestrator.workflow_stages[-1]
        
        # Test agent dependencies are defined
        assert AgentRole.RESEARCH_DIRECTOR in orchestrator.agent_dependencies
        assert AgentRole.RISK_ANALYST in orchestrator.agent_dependencies
        
        # Risk analyst should depend on other agents
        risk_deps = orchestrator.agent_dependencies[AgentRole.RISK_ANALYST]
        assert AgentRole.FUNDAMENTAL_ANALYST in risk_deps
        assert AgentRole.SENTIMENT_ANALYST in risk_deps
        assert AgentRole.SUPPLY_CHAIN_ANALYST in risk_deps

    @pytest.mark.asyncio
    async def test_start_research_workflow(self, orchestrator, sample_research_request):
        """Test starting a new research workflow."""
        
        workflow_id = await orchestrator.start_research_workflow(sample_research_request)
        
        assert workflow_id is not None
        assert workflow_id in orchestrator.active_workflows
        
        workflow = orchestrator.active_workflows[workflow_id]
        assert workflow.workflow_id == workflow_id
        assert workflow.research_request == sample_research_request
        assert workflow.status == WorkflowStatus.PENDING

    @pytest.mark.asyncio
    async def test_get_workflow_status_existing(self, orchestrator, sample_research_request):
        """Test getting status of existing workflow."""
        
        workflow_id = await orchestrator.start_research_workflow(sample_research_request)
        
        # Wait a moment for workflow to start
        await asyncio.sleep(0.1)
        
        status = await orchestrator.get_workflow_status(workflow_id)
        
        assert status['workflow_id'] == workflow_id
        assert 'status' in status
        assert 'current_stage' in status
        assert 'progress_percentage' in status

    @pytest.mark.asyncio
    async def test_get_workflow_status_not_found(self, orchestrator):
        """Test getting status of non-existent workflow."""
        
        status = await orchestrator.get_workflow_status('nonexistent-id')
        
        assert status['workflow_id'] == 'nonexistent-id'
        assert status['status'] == WorkflowStatus.CANCELLED.value
        assert 'error' in status

    @pytest.mark.asyncio
    async def test_get_workflow_results(self, orchestrator, sample_research_request):
        """Test getting workflow results."""
        
        workflow_id = await orchestrator.start_research_workflow(sample_research_request)
        
        # Mock completed workflow
        workflow = orchestrator.active_workflows[workflow_id]
        workflow.status = WorkflowStatus.COMPLETED
        workflow.stage_results[WorkflowStage.REPORT_GENERATION] = {
            'research_results': {'test': 'results'}
        }
        
        results = await orchestrator.get_workflow_results(workflow_id)
        
        assert results is not None

    @pytest.mark.asyncio
    async def test_cancel_workflow(self, orchestrator, sample_research_request):
        """Test cancelling a workflow."""
        
        workflow_id = await orchestrator.start_research_workflow(sample_research_request)
        
        # Wait for workflow to start
        await asyncio.sleep(0.1)
        
        result = await orchestrator.cancel_workflow(workflow_id)
        
        assert result is True

    def test_cleanup_completed_workflows(self, orchestrator):
        """Test cleanup of old completed workflows."""
        
        # Add some mock completed workflows
        old_workflow = MagicMock()
        old_workflow.status = WorkflowStatus.COMPLETED
        old_workflow.completion_time = datetime.now() - timedelta(hours=25)
        
        recent_workflow = MagicMock()
        recent_workflow.status = WorkflowStatus.COMPLETED
        recent_workflow.completion_time = datetime.now() - timedelta(hours=1)
        
        running_workflow = MagicMock()
        running_workflow.status = WorkflowStatus.RUNNING
        
        orchestrator.active_workflows = {
            'old': old_workflow,
            'recent': recent_workflow,
            'running': running_workflow
        }
        
        orchestrator.cleanup_completed_workflows(max_age_hours=24)
        
        # Old workflow should be removed, others should remain
        assert 'old' not in orchestrator.active_workflows
        assert 'recent' in orchestrator.active_workflows
        assert 'running' in orchestrator.active_workflows


class TestWorkflowSession:
    """Test cases for Workflow Session."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Mock orchestrator for testing."""
        mock_orch = MagicMock()
        mock_orch.workflow_stages = [
            WorkflowStage.INITIALIZATION,
            WorkflowStage.RESEARCH_PLANNING,
            WorkflowStage.FUNDAMENTAL_ANALYSIS,
            WorkflowStage.REPORT_GENERATION,
            WorkflowStage.COMPLETED
        ]
        mock_orch.agent_dependencies = {
            AgentRole.RESEARCH_DIRECTOR: [],
            AgentRole.FUNDAMENTAL_ANALYST: [AgentRole.RESEARCH_DIRECTOR]
        }
        
        # Mock agent orchestrator
        mock_agent_orch = MagicMock()
        mock_orch.agent_orchestrator = mock_agent_orch
        
        # Mock sheets output
        mock_sheets = MagicMock()
        mock_orch.sheets_output = mock_sheets
        
        # Mock DB manager
        mock_db = MagicMock()
        mock_orch.db_manager = mock_db
        mock_db.get_session.return_value.__aenter__ = AsyncMock()
        mock_db.get_session.return_value.__aexit__ = AsyncMock()
        
        return mock_orch

    @pytest.fixture
    def sample_request(self):
        """Sample research request."""
        return {
            'project_id': 'test-123',
            'query': 'Test query',
            'investment_thesis': 'Test thesis',
            'companies': [
                {'symbol': 'AAPL', 'name': 'Apple Inc.'}
            ]
        }

    @pytest.fixture
    def workflow_session(self, mock_orchestrator, sample_request):
        """Create workflow session for testing."""
        return WorkflowSession(
            workflow_id='test-workflow-id',
            research_request=sample_request,
            orchestrator=mock_orchestrator
        )

    def test_workflow_session_initialization(self, workflow_session):
        """Test workflow session initializes correctly."""
        assert workflow_session.workflow_id == 'test-workflow-id'
        assert workflow_session.status == WorkflowStatus.PENDING
        assert workflow_session.current_stage == WorkflowStage.INITIALIZATION
        assert workflow_session.progress_percentage == 0.0
        assert workflow_session.start_time is not None
        assert not workflow_session._cancelled

    @pytest.mark.asyncio
    async def test_get_status(self, workflow_session):
        """Test getting workflow session status."""
        
        status = await workflow_session.get_status()
        
        assert status['workflow_id'] == 'test-workflow-id'
        assert status['status'] == WorkflowStatus.PENDING.value
        assert status['current_stage'] == WorkflowStage.INITIALIZATION.value
        assert status['progress_percentage'] == 0.0
        assert 'start_time' in status
        assert 'agents_completed' in status
        assert status['overall_confidence'] == 0.0

    @pytest.mark.asyncio
    async def test_get_results_not_completed(self, workflow_session):
        """Test getting results when workflow not completed."""
        
        results = await workflow_session.get_results()
        
        assert results is None

    @pytest.mark.asyncio
    async def test_cancel_workflow_session(self, workflow_session):
        """Test cancelling workflow session."""
        
        workflow_session.status = WorkflowStatus.RUNNING
        
        result = await workflow_session.cancel()
        
        assert result is True
        assert workflow_session._cancelled is True
        assert workflow_session.status == WorkflowStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_execute_initialization_success(self, workflow_session):
        """Test successful initialization stage."""
        
        result = await workflow_session._execute_initialization()
        
        assert result['success'] is True
        assert result['companies_count'] == 1
        assert 'project_id' in result

    @pytest.mark.asyncio
    async def test_execute_initialization_missing_query(self, workflow_session):
        """Test initialization with missing query."""
        
        del workflow_session.research_request['query']
        
        result = await workflow_session._execute_initialization()
        
        assert result['success'] is False
        assert 'query' in result['error']

    @pytest.mark.asyncio
    async def test_execute_initialization_no_companies(self, workflow_session):
        """Test initialization with no companies."""
        
        workflow_session.research_request['companies'] = []
        
        result = await workflow_session._execute_initialization()
        
        assert result['success'] is False
        assert 'companies' in result['error']

    @pytest.mark.asyncio
    async def test_execute_data_collection(self, workflow_session):
        """Test data collection stage."""
        
        result = await workflow_session._execute_data_collection()
        
        assert result['success'] is True
        assert 'collected_data' in result
        assert result['collected_data']['companies_prepared'] == 1

    @pytest.mark.asyncio
    async def test_execute_single_agent_success(self, workflow_session, mock_orchestrator):
        """Test successful single agent execution."""
        
        # Mock agent
        mock_agent = MagicMock()
        mock_agent.validate_inputs = AsyncMock(return_value=True)
        mock_agent.analyze = AsyncMock(return_value=AgentResult(
            agent=AgentRole.FUNDAMENTAL_ANALYST,
            success=True,
            data={'test': 'data'},
            confidence=0.8,
            sources=['test'],
            reasoning='test reasoning'
        ))
        
        mock_orchestrator.agent_orchestrator.agents = {
            AgentRole.FUNDAMENTAL_ANALYST: mock_agent
        }
        
        result = await workflow_session._execute_single_agent(AgentRole.FUNDAMENTAL_ANALYST)
        
        assert result is not None
        assert result.success is True
        assert result.agent == AgentRole.FUNDAMENTAL_ANALYST
        assert result.confidence == 0.8

    @pytest.mark.asyncio
    async def test_execute_single_agent_not_found(self, workflow_session, mock_orchestrator):
        """Test single agent execution when agent not found."""
        
        mock_orchestrator.agent_orchestrator.agents = {}
        
        result = await workflow_session._execute_single_agent(AgentRole.FUNDAMENTAL_ANALYST)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_execute_single_agent_validation_failed(self, workflow_session, mock_orchestrator):
        """Test single agent execution with validation failure."""
        
        # Mock agent with validation failure
        mock_agent = MagicMock()
        mock_agent.validate_inputs = AsyncMock(return_value=False)
        
        mock_orchestrator.agent_orchestrator.agents = {
            AgentRole.FUNDAMENTAL_ANALYST: mock_agent
        }
        
        result = await workflow_session._execute_single_agent(AgentRole.FUNDAMENTAL_ANALYST)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_execute_agent_analysis_success(self, workflow_session, mock_orchestrator):
        """Test successful agent analysis execution."""
        
        # Setup dependencies
        workflow_session.agent_results[AgentRole.RESEARCH_DIRECTOR] = MagicMock()
        
        # Mock agent
        mock_agent = MagicMock()
        mock_agent.validate_inputs = AsyncMock(return_value=True)
        mock_agent.analyze = AsyncMock(return_value=AgentResult(
            agent=AgentRole.FUNDAMENTAL_ANALYST,
            success=True,
            data={'analysis': 'results'},
            confidence=0.75,
            sources=['test'],
            reasoning='test reasoning'
        ))
        
        mock_orchestrator.agent_orchestrator.agents = {
            AgentRole.FUNDAMENTAL_ANALYST: mock_agent
        }
        
        result = await workflow_session._execute_agent_analysis(AgentRole.FUNDAMENTAL_ANALYST)
        
        assert result['success'] is True
        assert 'agent_result' in result
        assert result['agent_result']['confidence'] == 0.75
        assert AgentRole.FUNDAMENTAL_ANALYST in workflow_session.agent_results

    @pytest.mark.asyncio
    async def test_execute_agent_analysis_missing_dependency(self, workflow_session, mock_orchestrator):
        """Test agent analysis with missing dependency."""
        
        # Don't add the required dependency
        result = await workflow_session._execute_agent_analysis(AgentRole.FUNDAMENTAL_ANALYST)
        
        assert result['success'] is False
        assert 'Dependency' in result['error']

    @pytest.mark.asyncio
    async def test_execute_report_generation_success(self, workflow_session, mock_orchestrator):
        """Test successful report generation."""
        
        # Add some agent results
        workflow_session.agent_results[AgentRole.FUNDAMENTAL_ANALYST] = MagicMock()
        workflow_session.agent_results[AgentRole.FUNDAMENTAL_ANALYST].data = {'test': 'data'}
        
        # Mock sheets output
        mock_orchestrator.sheets_output.create_research_report = AsyncMock(
            return_value="https://docs.google.com/spreadsheets/d/test_id/edit"
        )
        
        result = await workflow_session._execute_report_generation()
        
        assert result['success'] is True
        assert 'report_url' in result
        assert 'research_results' in result
        assert result['agents_executed'] == 1

    @pytest.mark.asyncio
    async def test_execute_report_generation_sheets_failure(self, workflow_session, mock_orchestrator):
        """Test report generation with Google Sheets failure."""
        
        # Mock sheets output failure
        mock_orchestrator.sheets_output.create_research_report = AsyncMock(return_value=None)
        
        result = await workflow_session._execute_report_generation()
        
        assert result['success'] is True  # Should succeed with fallback
        assert result['report_url'] is None
        assert 'note' in result

    def test_update_context_with_results(self, workflow_session):
        """Test updating context with agent results."""
        
        # Mock agent result
        mock_result = MagicMock()
        mock_result.data = {'test': 'fundamental_data'}
        
        workflow_session._update_context_with_results(AgentRole.FUNDAMENTAL_ANALYST, mock_result)
        
        assert 'fundamental_analysis' in workflow_session.research_request
        assert workflow_session.research_request['fundamental_analysis'] == {'test': 'fundamental_data'}

    def test_summarize_agent_data(self, workflow_session):
        """Test agent data summarization."""
        
        test_data = {
            'company_analyses': [{'symbol': 'AAPL'}, {'symbol': 'GOOGL'}],
            'analysis_timestamp': '2024-02-03T10:00:00',
            'methodology': {'approach1': 'desc1', 'approach2': 'desc2'}
        }
        
        summary = workflow_session._summarize_agent_data(test_data)
        
        assert summary['companies_analyzed'] == 2
        assert summary['analysis_timestamp'] == '2024-02-03T10:00:00'
        assert summary['methodology_count'] == 2

    def test_calculate_overall_confidence(self, workflow_session):
        """Test overall confidence calculation."""
        
        # No results
        assert workflow_session._calculate_overall_confidence() == 0.0
        
        # Add mock results
        result1 = MagicMock()
        result1.confidence = 0.8
        result2 = MagicMock()
        result2.confidence = 0.6
        
        workflow_session.agent_results = {
            AgentRole.FUNDAMENTAL_ANALYST: result1,
            AgentRole.SENTIMENT_ANALYST: result2
        }
        
        confidence = workflow_session._calculate_overall_confidence()
        assert confidence == 0.7  # (0.8 + 0.6) / 2

    @pytest.mark.asyncio
    async def test_full_workflow_execution_mock(self, workflow_session, mock_orchestrator):
        """Test full workflow execution with mocked stages."""
        
        # Mock all stage executions to succeed
        workflow_session._execute_initialization = AsyncMock(return_value={'success': True})
        workflow_session._execute_research_planning = AsyncMock(return_value={'success': True})
        workflow_session._execute_data_collection = AsyncMock(return_value={'success': True})
        workflow_session._execute_agent_analysis = AsyncMock(return_value={'success': True})
        workflow_session._execute_report_generation = AsyncMock(return_value={
            'success': True,
            'research_results': {'test': 'final_results'}
        })
        
        # Start execution
        await workflow_session.execute()
        
        # Verify final state
        assert workflow_session.status == WorkflowStatus.COMPLETED
        assert workflow_session.current_stage == WorkflowStage.COMPLETED
        assert workflow_session.progress_percentage == 100.0
        assert workflow_session.completion_time is not None

    @pytest.mark.asyncio
    async def test_workflow_execution_stage_failure(self, workflow_session, mock_orchestrator):
        """Test workflow execution with stage failure."""
        
        # Mock initialization to succeed but planning to fail
        workflow_session._execute_initialization = AsyncMock(return_value={'success': True})
        workflow_session._execute_research_planning = AsyncMock(return_value={
            'success': False,
            'error': 'Planning failed'
        })
        
        await workflow_session.execute()
        
        # Verify failure state
        assert workflow_session.status == WorkflowStatus.FAILED
        assert len(workflow_session.errors) > 0
        assert 'Planning failed' in workflow_session.errors[0]

    @pytest.mark.asyncio
    async def test_workflow_execution_cancellation(self, workflow_session, mock_orchestrator):
        """Test workflow execution with cancellation."""
        
        # Cancel immediately
        workflow_session._cancelled = True
        
        await workflow_session.execute()
        
        assert workflow_session.status == WorkflowStatus.CANCELLED


class TestWorkflowIntegration:
    """Integration tests for workflow functionality."""

    @pytest.mark.asyncio
    async def test_end_to_end_workflow_mock(self):
        """Test complete end-to-end workflow with mocked components."""
        
        with patch('src.core.workflow.AgentOrchestrator') as MockAgentOrch:
            with patch('src.core.workflow.GoogleSheetsOutputManager') as MockSheets:
                with patch('src.core.workflow.DatabaseManager') as MockDB:
                    
                    # Setup mocks
                    mock_db = MockDB.return_value
                    mock_db.get_session.return_value.__aenter__ = AsyncMock()
                    mock_db.get_session.return_value.__aexit__ = AsyncMock()
                    
                    mock_sheets = MockSheets.return_value
                    mock_sheets.create_research_report = AsyncMock(
                        return_value="https://docs.google.com/test"
                    )
                    
                    # Create orchestrator
                    orchestrator = ResearchWorkflowOrchestrator()
                    
                    # Start workflow
                    research_request = {
                        'query': 'Test query',
                        'companies': [{'symbol': 'AAPL', 'name': 'Apple Inc.'}],
                        'investment_thesis': 'Test thesis'
                    }
                    
                    workflow_id = await orchestrator.start_research_workflow(research_request)
                    
                    # Verify workflow was created
                    assert workflow_id in orchestrator.active_workflows
                    
                    # Get initial status
                    status = await orchestrator.get_workflow_status(workflow_id)
                    assert status['workflow_id'] == workflow_id
                    assert 'status' in status

    def test_workflow_stage_sequence(self):
        """Test workflow stage sequence is logical."""
        
        with patch('src.core.workflow.AgentOrchestrator'):
            with patch('src.core.workflow.GoogleSheetsOutputManager'):
                with patch('src.core.workflow.DatabaseManager'):
                    orchestrator = ResearchWorkflowOrchestrator()
                    
                    stages = orchestrator.workflow_stages
                    
                    # Verify logical sequence
                    assert stages[0] == WorkflowStage.INITIALIZATION
                    assert WorkflowStage.RESEARCH_PLANNING in stages
                    assert WorkflowStage.FUNDAMENTAL_ANALYSIS in stages
                    assert WorkflowStage.RISK_ANALYSIS in stages
                    assert WorkflowStage.REPORT_GENERATION in stages
                    assert stages[-1] == WorkflowStage.COMPLETED

    def test_agent_dependency_validation(self):
        """Test agent dependencies are logically structured."""
        
        with patch('src.core.workflow.AgentOrchestrator'):
            with patch('src.core.workflow.GoogleSheetsOutputManager'):
                with patch('src.core.workflow.DatabaseManager'):
                    orchestrator = ResearchWorkflowOrchestrator()
                    
                    deps = orchestrator.agent_dependencies
                    
                    # Research Director should have no dependencies
                    assert deps[AgentRole.RESEARCH_DIRECTOR] == []
                    
                    # Risk Analyst should depend on analysis agents
                    risk_deps = deps[AgentRole.RISK_ANALYST]
                    assert AgentRole.FUNDAMENTAL_ANALYST in risk_deps
                    assert AgentRole.SENTIMENT_ANALYST in risk_deps
                    assert AgentRole.SUPPLY_CHAIN_ANALYST in risk_deps
                    
                    # Analysis agents should depend on Research Director
                    for agent in [AgentRole.FUNDAMENTAL_ANALYST, AgentRole.SENTIMENT_ANALYST, AgentRole.SUPPLY_CHAIN_ANALYST]:
                        if agent in deps:
                            assert AgentRole.RESEARCH_DIRECTOR in deps[agent]