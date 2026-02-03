"""Basic API tests."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from src.core.app import create_app
from src.core.config import settings


@pytest.fixture
def client():
    """Create test client."""
    # Mock database initialization for testing
    with patch('src.core.app.init_db', new=AsyncMock()), \
         patch('src.core.app.close_db', new=AsyncMock()):
        app = create_app()
        return TestClient(app)


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == settings.app.version
    assert data["environment"] == settings.app.environment


def test_cors_headers(client):
    """Test CORS headers are present."""
    response = client.get("/health")
    
    # Check that CORS middleware is working
    assert response.status_code == 200


def test_request_id_header(client):
    """Test request ID header is added."""
    response = client.get("/health")
    
    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0


def test_companies_endpoint_structure(client):
    """Test companies endpoint structure."""
    # This should return empty list initially
    response = client.get("/api/v1/companies/")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_research_projects_list(client):
    """Test research projects endpoint structure."""
    response = client.get("/api/v1/research/")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_agent_roles_endpoint(client):
    """Test agent roles endpoint."""
    response = client.get("/api/v1/agents/roles")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0  # Should have at least some agent roles
    
    # Check that expected agent roles are present
    expected_roles = [
        "research_director",
        "fundamental_analyst", 
        "supply_chain_analyst",
        "sentiment_analyst",
        "quantitative_analyst",
        "risk_analyst"
    ]
    
    for role in expected_roles:
        assert role in data


def test_invalid_endpoint(client):
    """Test invalid endpoint returns 404."""
    response = client.get("/api/v1/nonexistent")
    
    assert response.status_code == 404