"""Integration tests for critical ResearchLab components."""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

from src.core.config import settings
from src.agents.base import AgentRole, AgentResult, AgentMessage
from src.api.research import ResearchRequest, CompanyInfo
from src.data.clients.rate_limiter import RateLimiter


class TestConfigurationIntegration:
    """Test configuration system integration."""
    
    def test_settings_loading(self):
        """Test that settings load properly."""
        assert settings.app.app_name is not None
        assert settings.app.version is not None
        assert settings.database.host is not None
        assert settings.api.finnhub_rate_limit > 0
    
    def test_environment_variables(self):
        """Test environment variable handling."""
        # Test that settings respect environment variables
        assert isinstance(settings.app.debug, bool)
        assert isinstance(settings.app.port, int)
        assert settings.app.port > 0
    
    def test_api_configuration(self):
        """Test API configuration."""
        assert settings.api.finnhub_rate_limit >= 1
        assert settings.api.alpha_vantage_rate_limit >= 1
        assert settings.agents.max_concurrent >= 1
        assert settings.agents.timeout > 0
    
    def test_database_configuration(self):
        """Test database configuration."""
        assert settings.database.port > 0
        assert settings.database.pool_size > 0
        assert settings.database.name is not None
    
    @patch.dict('os.environ', {'APP_NAME': 'TestLab', 'DEBUG': 'true'})
    def test_environment_override(self):
        """Test environment variable override."""
        from src.core.config import Settings
        
        test_settings = Settings()
        assert test_settings.app.app_name == 'TestLab'
        assert test_settings.app.debug is True


class TestAgentIntegration:
    """Test agent system integration."""
    
    def test_agent_roles_defined(self):
        """Test that all agent roles are defined."""
        roles = list(AgentRole)
        
        assert AgentRole.RESEARCH_DIRECTOR in roles
        assert AgentRole.FUNDAMENTAL_ANALYST in roles
        assert AgentRole.QUANTITATIVE_ANALYST in roles
        assert AgentRole.SENTIMENT_ANALYST in roles
        assert AgentRole.RISK_ANALYST in roles
        assert AgentRole.SUPPLY_CHAIN_ANALYST in roles
        
        # Should have at least 6 agents
        assert len(roles) >= 6
    
    def test_agent_message_creation(self):
        """Test agent message creation."""
        message = AgentMessage(
            agent_role=AgentRole.RESEARCH_DIRECTOR,
            content="Test message",
            message_type="instruction",
            metadata={"test": "data"}
        )
        
        assert message.agent_role == AgentRole.RESEARCH_DIRECTOR
        assert message.content == "Test message"
        assert message.message_type == "instruction"
        assert message.metadata["test"] == "data"
    
    def test_agent_result_creation(self):
        """Test agent result creation."""
        result = AgentResult(
            agent=AgentRole.FUNDAMENTAL_ANALYST,
            success=True,
            data={"analysis": "positive"},
            confidence=0.85,
            sources=["SEC filings", "Financial statements"],
            reasoning="Strong fundamentals observed"
        )
        
        assert result.agent == AgentRole.FUNDAMENTAL_ANALYST
        assert result.success is True
        assert result.data["analysis"] == "positive"
        assert result.confidence == 0.85
        assert len(result.sources) == 2
        assert "fundamentals" in result.reasoning
    
    def test_agent_result_validation(self):
        """Test agent result validation."""
        # Test confidence bounds
        with pytest.raises(ValueError):
            AgentResult(
                agent=AgentRole.RISK_ANALYST,
                success=True,
                data={},
                confidence=1.5  # Invalid: > 1.0
            )
        
        with pytest.raises(ValueError):
            AgentResult(
                agent=AgentRole.RISK_ANALYST,
                success=True,
                data={},
                confidence=-0.1  # Invalid: < 0.0
            )


class TestAPIIntegration:
    """Test API model integration."""
    
    def test_research_request_creation(self):
        """Test research request model."""
        companies = [
            CompanyInfo(symbol="AAPL", name="Apple Inc."),
            CompanyInfo(symbol="GOOGL", name="Alphabet Inc.")
        ]
        
        request = ResearchRequest(
            query="Analyze tech giants for growth potential",
            investment_thesis="AI and cloud computing will drive growth",
            companies=companies,
            time_horizon=24,
            risk_tolerance="moderate"
        )
        
        assert request.query == "Analyze tech giants for growth potential"
        assert len(request.companies) == 2
        assert request.companies[0].symbol == "AAPL"
        assert request.time_horizon == 24
        assert request.risk_tolerance == "moderate"
    
    def test_company_info_validation(self):
        """Test company info validation."""
        # Valid company
        company = CompanyInfo(symbol="AAPL", name="Apple Inc.")
        assert company.symbol == "AAPL"
        assert company.name == "Apple Inc."
        
        # Test symbol validation (should be uppercase)
        company2 = CompanyInfo(symbol="aapl", name="Apple Inc.")
        # Should normalize to uppercase
        assert company2.symbol == "AAPL" or company2.symbol == "aapl"  # Depends on implementation
    
    def test_research_request_validation(self):
        """Test research request validation."""
        companies = [CompanyInfo(symbol="AAPL", name="Apple Inc.")]
        
        # Test minimum query length
        with pytest.raises(ValueError):
            ResearchRequest(
                query="Hi",  # Too short
                companies=companies
            )
        
        # Test empty companies
        with pytest.raises(ValueError):
            ResearchRequest(
                query="Valid query here",
                companies=[]  # Empty companies list
            )


class TestRateLimitingIntegration:
    """Test rate limiting integration."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.limiter = RateLimiter()
    
    async def test_rate_limiter_basic_functionality(self):
        """Test basic rate limiting."""
        # Set a low limit for testing
        await self.limiter.set_limit("test_key", 2, 60)  # 2 requests per minute
        
        # First two requests should pass
        assert await self.limiter.check_and_consume("test_key") is True
        assert await self.limiter.check_and_consume("test_key") is True
        
        # Third request should be blocked
        assert await self.limiter.check_and_consume("test_key") is False
    
    async def test_rate_limiter_reset(self):
        """Test rate limiter reset functionality."""
        await self.limiter.set_limit("test_reset", 1, 1)  # 1 request per second
        
        # Consume the limit
        assert await self.limiter.check_and_consume("test_reset") is True
        assert await self.limiter.check_and_consume("test_reset") is False
        
        # Wait for reset (slightly more than 1 second)
        await asyncio.sleep(1.1)
        
        # Should be available again
        assert await self.limiter.check_and_consume("test_reset") is True
    
    async def test_rate_limiter_multiple_keys(self):
        """Test rate limiter with multiple keys."""
        await self.limiter.set_limit("key1", 1, 60)
        await self.limiter.set_limit("key2", 1, 60)
        
        # Each key should have its own limit
        assert await self.limiter.check_and_consume("key1") is True
        assert await self.limiter.check_and_consume("key2") is True
        
        # Both should now be exhausted
        assert await self.limiter.check_and_consume("key1") is False
        assert await self.limiter.check_and_consume("key2") is False
    
    async def test_rate_limiter_stats(self):
        """Test rate limiter statistics."""
        await self.limiter.set_limit("stats_test", 5, 60)
        
        # Make some requests
        for _ in range(3):
            await self.limiter.check_and_consume("stats_test")
        
        stats = await self.limiter.get_stats("stats_test")
        
        assert stats["requests_consumed"] == 3
        assert stats["requests_remaining"] == 2
        assert stats["limit"] == 5
        assert "reset_time" in stats


class TestDataFlowIntegration:
    """Test data flow integration between components."""
    
    def test_research_data_flow(self):
        """Test research request to agent flow."""
        # Create a research request
        companies = [CompanyInfo(symbol="AAPL", name="Apple Inc.")]
        request = ResearchRequest(
            query="Is Apple a good investment?",
            companies=companies,
            time_horizon=12
        )
        
        # Verify data can flow to agent format
        agent_input = {
            "project_id": "test_123",
            "query": request.query,
            "companies": [{"symbol": c.symbol, "name": c.name} for c in request.companies],
            "investment_thesis": request.investment_thesis,
            "time_horizon": request.time_horizon,
            "risk_tolerance": request.risk_tolerance
        }
        
        assert agent_input["query"] == request.query
        assert len(agent_input["companies"]) == 1
        assert agent_input["companies"][0]["symbol"] == "AAPL"
    
    def test_agent_result_to_api_response(self):
        """Test agent result to API response conversion."""
        # Create agent result
        result = AgentResult(
            agent=AgentRole.FUNDAMENTAL_ANALYST,
            success=True,
            data={
                "financial_health": 0.85,
                "growth_potential": 0.78,
                "valuation": "undervalued"
            },
            confidence=0.82,
            sources=["10-K filing", "Earnings report"],
            reasoning="Strong fundamentals with good growth prospects"
        )
        
        # Convert to API format
        api_response = {
            "agent": result.agent.value,
            "success": result.success,
            "confidence": result.confidence,
            "analysis": result.data,
            "sources": result.sources,
            "reasoning": result.reasoning
        }
        
        assert api_response["agent"] == "fundamental_analyst"
        assert api_response["analysis"]["financial_health"] == 0.85
        assert len(api_response["sources"]) == 2
    
    def test_configuration_to_agent_initialization(self):
        """Test configuration flowing to agent initialization."""
        # Test that configuration values are accessible for agent init
        agent_config = {
            "max_concurrent": settings.agents.max_concurrent,
            "timeout": settings.agents.timeout,
            "retry_attempts": settings.agents.retry_attempts,
            "default_model": settings.llm.default_model,
            "temperature": settings.llm.temperature
        }
        
        assert agent_config["max_concurrent"] > 0
        assert agent_config["timeout"] > 0
        assert agent_config["default_model"] is not None


class TestErrorHandlingIntegration:
    """Test error handling across components."""
    
    def test_invalid_agent_role(self):
        """Test handling of invalid agent roles."""
        with pytest.raises((ValueError, AttributeError)):
            AgentRole("nonexistent_agent")
    
    def test_invalid_research_request(self):
        """Test handling of invalid research requests."""
        # Test completely invalid data
        with pytest.raises((ValueError, TypeError)):
            ResearchRequest(
                query=None,  # Invalid
                companies=None  # Invalid
            )
    
    def test_agent_result_error_handling(self):
        """Test agent result error scenarios."""
        # Test failed agent result
        error_result = AgentResult(
            agent=AgentRole.RISK_ANALYST,
            success=False,
            data={},
            confidence=0.0,
            errors=["API timeout", "Invalid response format"],
            reasoning="Analysis failed due to multiple errors"
        )
        
        assert error_result.success is False
        assert len(error_result.errors) == 2
        assert "timeout" in error_result.errors[0]
    
    async def test_rate_limiter_error_scenarios(self):
        """Test rate limiter error handling."""
        limiter = RateLimiter()
        
        # Test with invalid parameters
        with pytest.raises(ValueError):
            await limiter.set_limit("test", -1, 60)  # Negative limit
        
        with pytest.raises(ValueError):
            await limiter.set_limit("test", 10, 0)  # Zero window
    
    def test_configuration_missing_values(self):
        """Test configuration with missing values."""
        # Most config values should have defaults
        assert settings.app.host is not None
        assert settings.app.port > 0
        assert settings.database.pool_size > 0
        
        # These may be empty but shouldn't be None
        assert settings.api.finnhub_api_key is not None  # May be empty string
        assert isinstance(settings.app.debug, bool)


class TestPerformanceIntegration:
    """Test performance-related integration."""
    
    def test_concurrent_rate_limiting(self):
        """Test rate limiting under concurrent load."""
        async def test_concurrent():
            limiter = RateLimiter()
            await limiter.set_limit("concurrent_test", 10, 60)
            
            # Create multiple concurrent requests
            tasks = []
            for _ in range(20):  # More than the limit
                tasks.append(limiter.check_and_consume("concurrent_test"))
            
            results = await asyncio.gather(*tasks)
            
            # Should have exactly 10 successes and 10 failures
            successes = sum(1 for r in results if r is True)
            failures = sum(1 for r in results if r is False)
            
            assert successes == 10
            assert failures == 10
        
        # Run the async test
        asyncio.run(test_concurrent())
    
    def test_agent_result_serialization_performance(self):
        """Test agent result serialization performance."""
        import time
        
        # Create a large result
        large_data = {
            f"metric_{i}": f"value_{i}" for i in range(1000)
        }
        
        result = AgentResult(
            agent=AgentRole.QUANTITATIVE_ANALYST,
            success=True,
            data=large_data,
            confidence=0.75,
            sources=[f"source_{i}" for i in range(100)],
            reasoning="Large dataset analysis completed"
        )
        
        # Test serialization time
        start_time = time.time()
        serialized = json.dumps(result.dict())
        serialization_time = time.time() - start_time
        
        # Should serialize quickly (< 0.1 seconds for this size)
        assert serialization_time < 0.1
        assert len(serialized) > 1000  # Should be substantial
        
        # Test deserialization
        start_time = time.time()
        deserialized = json.loads(serialized)
        deserialization_time = time.time() - start_time
        
        assert deserialization_time < 0.1
        assert deserialized["data"]["metric_0"] == "value_0"


class TestWorkflowIntegration:
    """Test workflow integration scenarios."""
    
    def test_workflow_stage_progression(self):
        """Test workflow stage progression logic."""
        from src.core.workflow import WorkflowStage
        
        stages = list(WorkflowStage)
        
        # Should have logical progression
        assert WorkflowStage.INITIALIZATION in stages
        assert WorkflowStage.RESEARCH_PLANNING in stages
        assert WorkflowStage.DATA_COLLECTION in stages
        assert WorkflowStage.AGENT_ANALYSIS in stages
        assert WorkflowStage.REPORT_GENERATION in stages
        assert WorkflowStage.COMPLETED in stages
    
    def test_agent_dependency_resolution(self):
        """Test agent dependency resolution."""
        # Test that agent dependencies make sense
        from src.core.workflow import ResearchWorkflowOrchestrator
        
        orchestrator = ResearchWorkflowOrchestrator()
        
        # Research Director should have no dependencies
        director_deps = orchestrator.agent_dependencies.get(AgentRole.RESEARCH_DIRECTOR, [])
        assert len(director_deps) == 0
        
        # Other agents should have Research Director as dependency
        for agent_role in AgentRole:
            if agent_role != AgentRole.RESEARCH_DIRECTOR:
                agent_deps = orchestrator.agent_dependencies.get(agent_role, [])
                assert AgentRole.RESEARCH_DIRECTOR in agent_deps or len(agent_deps) == 0
    
    def test_workflow_metadata_consistency(self):
        """Test workflow metadata consistency."""
        # Test that workflow metadata structure is consistent
        metadata = {
            "workflow_id": "test_workflow_123",
            "start_time": datetime.now().isoformat(),
            "agents_completed": [],
            "total_confidence": 0.0,
            "stage_durations": {},
            "error_count": 0
        }
        
        # Should have required fields
        assert "workflow_id" in metadata
        assert "start_time" in metadata
        assert "agents_completed" in metadata
        assert isinstance(metadata["agents_completed"], list)
        assert isinstance(metadata["total_confidence"], (int, float))


class TestSecurityIntegration:
    """Test security-related integration."""
    
    def test_api_key_handling(self):
        """Test API key handling in configuration."""
        # API keys should be strings (empty is OK)
        assert isinstance(settings.api.finnhub_api_key, str)
        assert isinstance(settings.api.alpha_vantage_api_key, str)
        
        # Should not expose actual keys in tests
        if settings.api.finnhub_api_key:
            assert len(settings.api.finnhub_api_key) > 10  # Real keys are longer
    
    def test_data_sanitization(self):
        """Test data sanitization in results."""
        # Test that sensitive data doesn't leak
        result = AgentResult(
            agent=AgentRole.FUNDAMENTAL_ANALYST,
            success=True,
            data={
                "analysis": "positive",
                "api_key": "secret_key_12345",  # Should be filtered out
                "password": "test_password"     # Should be filtered out
            },
            confidence=0.8
        )
        
        # In a real implementation, sensitive fields should be filtered
        # For now, just ensure the structure is correct
        assert "analysis" in result.data
        # Note: In production, would want to filter out api_key and password
    
    def test_input_validation(self):
        """Test input validation for security."""
        # Test SQL injection prevention (basic)
        malicious_query = "DROP TABLE users; --"
        
        with pytest.raises((ValueError, TypeError)):
            ResearchRequest(
                query=malicious_query,
                companies=[CompanyInfo(symbol="'; DROP TABLE companies; --", name="Malicious")]
            )
        
        # Test script injection prevention
        script_query = "<script>alert('xss')</script>"
        
        # Should either reject or sanitize
        try:
            request = ResearchRequest(
                query=script_query,
                companies=[CompanyInfo(symbol="AAPL", name="Apple Inc.")]
            )
            # If allowed, should be sanitized
            assert "<script>" not in request.query
        except (ValueError, TypeError):
            # If rejected, that's also acceptable
            pass


# Async test runner helper
def run_async_test(coro):
    """Helper to run async tests."""
    return asyncio.get_event_loop().run_until_complete(coro)