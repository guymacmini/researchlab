"""Tests for research API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from fastapi.testclient import TestClient

from src.core.app import app
from src.api.research import ResearchRequest, CompanyInfo

client = TestClient(app)


class TestResearchAPI:
    """Test cases for Research API."""

    @pytest.fixture
    def sample_research_request(self):
        """Sample research request data."""
        return {
            "query": "Is Apple a good long-term investment?",
            "investment_thesis": "Apple will benefit from AI integration across its ecosystem",
            "companies": [
                {
                    "symbol": "AAPL",
                    "name": "Apple Inc.",
                    "sector": "Technology",
                    "market_cap": 3000000000000
                }
            ],
            "time_horizon": 24,
            "risk_tolerance": "moderate"
        }

    def test_research_request_model(self, sample_research_request):
        """Test research request Pydantic model."""
        
        request = ResearchRequest(**sample_research_request)
        
        assert request.query == "Is Apple a good long-term investment?"
        assert request.investment_thesis == "Apple will benefit from AI integration across its ecosystem"
        assert len(request.companies) == 1
        assert request.companies[0].symbol == "AAPL"
        assert request.time_horizon == 24
        assert request.risk_tolerance == "moderate"

    def test_company_info_model(self):
        """Test company info Pydantic model."""
        
        company_data = {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "sector": "Technology",
            "market_cap": 3000000000000
        }
        
        company = CompanyInfo(**company_data)
        
        assert company.symbol == "AAPL"
        assert company.name == "Apple Inc."
        assert company.sector == "Technology"
        assert company.market_cap == 3000000000000

    @patch('src.api.research.get_db_session')
    @patch('src.api.research.ResearchWorkflowOrchestrator')
    def test_start_research_success(self, mock_orchestrator, mock_db_session, sample_research_request):
        """Test successful research project start."""
        
        # Mock database session
        mock_db = AsyncMock()
        mock_db_session.return_value = mock_db
        
        # Mock workflow orchestrator
        mock_workflow = AsyncMock()
        mock_workflow.start_research_workflow.return_value = "wf_test_123"
        mock_orchestrator.return_value = mock_workflow
        
        response = client.post("/api/v1/research/", json=sample_research_request)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "project_id" in data
        assert "workflow_id" in data
        assert data["workflow_id"] == "wf_test_123"
        assert data["status"] == "pending"
        assert "estimated_completion" in data
        assert data["agents_count"] == 5

    def test_start_research_invalid_data(self):
        """Test research start with invalid data."""
        
        invalid_request = {
            "query": "",  # Empty query
            "companies": []  # No companies
        }
        
        response = client.post("/api/v1/research/", json=invalid_request)
        
        assert response.status_code == 422  # Validation error

    @patch('src.api.research.get_db_session')
    @patch('src.api.research.ResearchWorkflowOrchestrator')
    def test_get_research_status_success(self, mock_orchestrator, mock_db_session):
        """Test successful research status retrieval."""
        
        # Mock database session and project
        mock_db = AsyncMock()
        mock_project = MagicMock()
        mock_project.workflow_id = "wf_test_123"
        mock_db.get.return_value = mock_project
        mock_db_session.return_value = mock_db
        
        # Mock workflow status
        mock_workflow = AsyncMock()
        mock_workflow.get_workflow_status.return_value = {
            "status": "running",
            "current_stage": "fundamental_analysis",
            "progress_percentage": 50.0,
            "current_operation": "Running Fundamental Analyst",
            "start_time": datetime.now().isoformat(),
            "completion_time": None,
            "agents_completed": ["research_director"],
            "errors": [],
            "overall_confidence": 0.75
        }
        mock_orchestrator.return_value = mock_workflow
        
        response = client.get("/api/v1/research/test_project_123/status")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "running"
        assert data["current_stage"] == "fundamental_analysis"
        assert data["progress_percentage"] == 50.0
        assert data["overall_confidence"] == 0.75

    @patch('src.api.research.get_db_session')
    def test_get_research_status_not_found(self, mock_db_session):
        """Test research status for non-existent project."""
        
        mock_db = AsyncMock()
        mock_db.get.return_value = None  # Project not found
        mock_db_session.return_value = mock_db
        
        response = client.get("/api/v1/research/non_existent/status")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @patch('src.api.research.get_db_session')
    @patch('src.api.research.ResearchWorkflowOrchestrator')
    def test_get_research_results_success(self, mock_orchestrator, mock_db_session):
        """Test successful research results retrieval."""
        
        # Mock database session and project
        mock_db = AsyncMock()
        mock_project = MagicMock()
        mock_project.workflow_id = "wf_test_123"
        mock_project.status.value = "completed"
        mock_project.query = "Test query"
        mock_project.investment_thesis = "Test thesis"
        mock_project.metadata = {
            "companies": [{"symbol": "AAPL", "name": "Apple Inc."}]
        }
        mock_project.created_at = datetime.now()
        mock_project.updated_at = datetime.now()
        mock_db.get.return_value = mock_project
        mock_db_session.return_value = mock_db
        
        # Mock workflow results
        mock_workflow = AsyncMock()
        mock_workflow.get_workflow_results.return_value = {
            "fundamental_analysis": {"test": "data"},
            "sentiment_analysis": {"sentiment": "positive"},
            "supply_chain_analysis": {"suppliers": []},
            "quantitative_analysis": {"signals": []},
            "risk_analysis": {"risks": []},
            "workflow_metadata": {"total_confidence": 0.82},
            "report_url": "https://docs.google.com/spreadsheets/test"
        }
        mock_orchestrator.return_value = mock_workflow
        
        response = client.get("/api/v1/research/test_project_123/results")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["query"] == "Test query"
        assert data["overall_confidence"] == 0.82
        assert "recommendation" in data
        assert "key_findings" in data
        assert "risks" in data
        assert "opportunities" in data

    @patch('src.api.research.get_db_session')
    def test_get_research_results_not_completed(self, mock_db_session):
        """Test research results for non-completed project."""
        
        mock_db = AsyncMock()
        mock_project = MagicMock()
        mock_project.status.value = "running"  # Not completed
        mock_db.get.return_value = mock_project
        mock_db_session.return_value = mock_db
        
        response = client.get("/api/v1/research/test_project_123/results")
        
        assert response.status_code == 400
        assert "not completed" in response.json()["detail"].lower()

    @patch('src.api.research.get_db_session')
    def test_list_research_projects(self, mock_db_session):
        """Test listing research projects."""
        
        mock_db = AsyncMock()
        # Mock query builder (simplified)
        mock_db.query.return_value.offset.return_value.limit.return_value = []
        mock_db_session.return_value = mock_db
        
        response = client.get("/api/v1/research/")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_research_projects_with_filters(self):
        """Test listing research projects with filters."""
        
        response = client.get("/api/v1/research/?status=completed&limit=10&offset=0")
        
        assert response.status_code == 200

    def test_list_research_projects_invalid_status(self):
        """Test listing with invalid status filter."""
        
        response = client.get("/api/v1/research/?status=invalid_status")
        
        assert response.status_code == 400
        assert "invalid status" in response.json()["detail"].lower()

    @patch('src.api.research.get_db_session')
    @patch('src.api.research.ResearchWorkflowOrchestrator')
    def test_cancel_research_project_running(self, mock_orchestrator, mock_db_session):
        """Test cancelling a running research project."""
        
        # Mock database session and project
        mock_db = AsyncMock()
        mock_project = MagicMock()
        mock_project.workflow_id = "wf_test_123"
        mock_project.status.value = "in_progress"
        mock_db.get.return_value = mock_project
        mock_db_session.return_value = mock_db
        
        # Mock workflow cancellation
        mock_workflow = AsyncMock()
        mock_workflow.cancel_workflow.return_value = True
        mock_orchestrator.return_value = mock_workflow
        
        response = client.delete("/api/v1/research/test_project_123")
        
        assert response.status_code == 200
        assert "cancelled successfully" in response.json()["message"]

    @patch('src.api.research.get_db_session')
    @patch('src.api.research.ResearchWorkflowOrchestrator')
    def test_restart_research_project(self, mock_orchestrator, mock_db_session):
        """Test restarting a failed research project."""
        
        # Mock database session and project
        mock_db = AsyncMock()
        mock_project = MagicMock()
        mock_project.status.value = "failed"
        mock_project.query = "Test query"
        mock_project.investment_thesis = "Test thesis"
        mock_project.metadata = {
            "companies": [{"symbol": "AAPL", "name": "Apple Inc."}],
            "time_horizon": 12,
            "risk_tolerance": "moderate"
        }
        mock_db.get.return_value = mock_project
        mock_db_session.return_value = mock_db
        
        # Mock workflow restart
        mock_workflow = AsyncMock()
        mock_workflow.start_research_workflow.return_value = "wf_new_456"
        mock_orchestrator.return_value = mock_workflow
        
        response = client.post("/api/v1/research/test_project_123/restart")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["workflow_id"] == "wf_new_456"
        assert data["status"] == "pending"

    @patch('src.api.research.get_db_session')
    def test_restart_research_project_invalid_status(self, mock_db_session):
        """Test restarting project with invalid status."""
        
        mock_db = AsyncMock()
        mock_project = MagicMock()
        mock_project.status.value = "completed"  # Can't restart completed
        mock_db.get.return_value = mock_project
        mock_db_session.return_value = mock_db
        
        response = client.post("/api/v1/research/test_project_123/restart")
        
        assert response.status_code == 400
        assert "only restart failed" in response.json()["detail"].lower()


class TestResearchAPIIntegration:
    """Integration tests for Research API."""

    @patch('src.api.research.get_db_session')
    @patch('src.api.research.ResearchWorkflowOrchestrator')
    def test_full_research_lifecycle(self, mock_orchestrator, mock_db_session):
        """Test complete research project lifecycle."""
        
        # Mock database session
        mock_db = AsyncMock()
        mock_db_session.return_value = mock_db
        
        # Mock workflow orchestrator
        mock_workflow = AsyncMock()
        mock_orchestrator.return_value = mock_workflow
        
        # 1. Start research
        research_request = {
            "query": "Integration test research",
            "companies": [{"symbol": "TEST", "name": "Test Corp"}]
        }
        
        mock_workflow.start_research_workflow.return_value = "wf_integration_test"
        
        start_response = client.post("/api/v1/research/", json=research_request)
        assert start_response.status_code == 200
        
        project_id = start_response.json()["project_id"]
        
        # 2. Check status (running)
        mock_project_running = MagicMock()
        mock_project_running.workflow_id = "wf_integration_test"
        mock_db.get.return_value = mock_project_running
        
        mock_workflow.get_workflow_status.return_value = {
            "status": "running",
            "current_stage": "fundamental_analysis",
            "progress_percentage": 60.0,
            "current_operation": "Analyzing fundamentals",
            "start_time": datetime.now().isoformat(),
            "agents_completed": ["research_director"],
            "errors": [],
            "overall_confidence": 0.7
        }
        
        status_response = client.get(f"/api/v1/research/{project_id}/status")
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "running"
        
        # 3. Check final results (completed)
        mock_project_completed = MagicMock()
        mock_project_completed.workflow_id = "wf_integration_test"
        mock_project_completed.status.value = "completed"
        mock_project_completed.query = research_request["query"]
        mock_project_completed.investment_thesis = ""
        mock_project_completed.metadata = {"companies": research_request["companies"]}
        mock_project_completed.created_at = datetime.now()
        mock_project_completed.updated_at = datetime.now()
        mock_db.get.return_value = mock_project_completed
        
        mock_workflow.get_workflow_results.return_value = {
            "fundamental_analysis": {"revenue_growth": 0.15},
            "sentiment_analysis": {"overall_sentiment": 0.6},
            "supply_chain_analysis": {"risk_score": 0.3},
            "quantitative_analysis": {"momentum": 0.7},
            "risk_analysis": {"max_drawdown": -0.12},
            "workflow_metadata": {"total_confidence": 0.82}
        }
        
        results_response = client.get(f"/api/v1/research/{project_id}/results")
        assert results_response.status_code == 200
        
        results_data = results_response.json()
        assert results_data["overall_confidence"] == 0.82
        assert "recommendation" in results_data

    def test_api_error_handling(self):
        """Test API error handling for various scenarios."""
        
        # 1. Missing required fields
        invalid_request = {"query": ""}  # Missing companies
        response = client.post("/api/v1/research/", json=invalid_request)
        assert response.status_code == 422
        
        # 2. Non-existent project
        response = client.get("/api/v1/research/non_existent_project/status")
        assert response.status_code == 404
        
        # 3. Invalid query parameters
        response = client.get("/api/v1/research/?status=invalid&limit=-1")
        assert response.status_code in [400, 422]

    def test_api_documentation_examples(self):
        """Test that API documentation examples are valid."""
        
        # Test example from ResearchRequest
        example_request = {
            "query": "Is Apple a good long-term investment given AI trends?",
            "investment_thesis": "Apple will benefit from AI integration across its ecosystem",
            "companies": [
                {
                    "symbol": "AAPL",
                    "name": "Apple Inc.",
                    "sector": "Technology"
                }
            ],
            "time_horizon": 24,
            "risk_tolerance": "moderate"
        }
        
        # Should validate without errors
        request_model = ResearchRequest(**example_request)
        assert request_model.query == example_request["query"]
        assert len(request_model.companies) == 1