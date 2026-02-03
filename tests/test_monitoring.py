"""Tests for the monitoring system."""

import pytest
import time
import asyncio
from unittest.mock import Mock, patch, AsyncMock

from src.monitoring.metrics import (
    Counter, Gauge, Histogram, Summary,
    MetricsManager, get_metrics_manager,
    MetricSample
)
from src.monitoring.health import (
    HealthChecker, HealthStatus, ComponentHealth,
    DatabaseHealthCheck, RedisHealthCheck, 
    ExternalAPIHealthCheck, DiskSpaceHealthCheck, MemoryHealthCheck
)
from src.monitoring.middleware import MetricsMiddleware, HealthMiddleware


class TestCounter:
    """Test Counter metrics."""
    
    def test_counter_creation(self):
        """Test counter creation."""
        counter = Counter("test_counter", "Test counter", ["label1", "label2"])
        
        assert counter.name == "test_counter"
        assert counter.description == "Test counter"
        assert counter.labels == ["label1", "label2"]
    
    def test_counter_increment(self):
        """Test counter increment."""
        counter = Counter("test_counter", "Test counter", ["status"])
        
        counter.inc(label1="success")
        counter.inc(2.5, label1="success")
        counter.inc(label1="error")
        
        samples = counter.get_samples()
        assert len(samples) >= 1
        
        # Find samples by labels
        success_sample = next((s for s in samples if s.labels.get("label1") == "success"), None)
        error_sample = next((s for s in samples if s.labels.get("label1") == "error"), None)
        
        assert success_sample is not None
        assert success_sample.value == 3.5
        assert error_sample is not None
        assert error_sample.value == 1.0
    
    def test_counter_negative_increment_raises_error(self):
        """Test that negative increment raises error."""
        counter = Counter("test_counter", "Test counter")
        
        with pytest.raises(ValueError):
            counter.inc(-1)


class TestGauge:
    """Test Gauge metrics."""
    
    def test_gauge_creation(self):
        """Test gauge creation."""
        gauge = Gauge("test_gauge", "Test gauge", ["instance"])
        
        assert gauge.name == "test_gauge"
        assert gauge.description == "Test gauge"
        assert gauge.labels == ["instance"]
    
    def test_gauge_operations(self):
        """Test gauge set/inc/dec operations."""
        gauge = Gauge("test_gauge", "Test gauge", ["instance"])
        
        # Set value
        gauge.set(10.0, instance="server1")
        
        # Increment
        gauge.inc(5.0, instance="server1")
        
        # Decrement
        gauge.dec(2.0, instance="server1")
        
        samples = gauge.get_samples()
        sample = next(s for s in samples if s.labels.get("instance") == "server1")
        
        assert sample.value == 13.0  # 10 + 5 - 2


class TestHistogram:
    """Test Histogram metrics."""
    
    def test_histogram_creation(self):
        """Test histogram creation."""
        buckets = [0.1, 0.5, 1.0, 5.0, float('inf')]
        histogram = Histogram("test_histogram", "Test histogram", ["method"], buckets)
        
        assert histogram.name == "test_histogram"
        assert histogram.buckets == buckets
    
    def test_histogram_observe(self):
        """Test histogram observation."""
        histogram = Histogram("test_histogram", "Test histogram", ["method"])
        
        # Observe values
        histogram.observe(0.05, method="GET")
        histogram.observe(0.2, method="GET")
        histogram.observe(1.5, method="GET")
        
        samples = histogram.get_samples()
        
        # Check bucket samples
        bucket_samples = [s for s in samples if s.name.endswith("_bucket")]
        assert len(bucket_samples) > 0
        
        # Check count and sum samples
        count_samples = [s for s in samples if s.name.endswith("_count")]
        sum_samples = [s for s in samples if s.name.endswith("_sum")]
        
        assert len(count_samples) == 1
        assert len(sum_samples) == 1
        assert count_samples[0].value == 3
        assert sum_samples[0].value == pytest.approx(1.75)  # 0.05 + 0.2 + 1.5
    
    def test_histogram_time_context_manager(self):
        """Test histogram time context manager."""
        histogram = Histogram("test_histogram", "Test histogram", ["method"])
        
        with histogram.time(method="POST"):
            time.sleep(0.01)  # Sleep for a small amount
        
        samples = histogram.get_samples()
        count_samples = [s for s in samples if s.name.endswith("_count")]
        
        assert len(count_samples) == 1
        assert count_samples[0].value == 1


class TestSummary:
    """Test Summary metrics."""
    
    def test_summary_creation(self):
        """Test summary creation."""
        quantiles = [0.5, 0.9, 0.99]
        summary = Summary("test_summary", "Test summary", ["endpoint"], quantiles)
        
        assert summary.name == "test_summary"
        assert summary.quantiles == quantiles
    
    def test_summary_observe(self):
        """Test summary observation."""
        summary = Summary("test_summary", "Test summary", ["endpoint"])
        
        # Observe many values to test quantile calculation
        values = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        for value in values:
            summary.observe(value, endpoint="api")
        
        samples = summary.get_samples()
        
        # Check quantile samples
        quantile_samples = [s for s in samples if "quantile" in s.labels]
        assert len(quantile_samples) > 0
        
        # Check count and sum samples
        count_samples = [s for s in samples if s.name.endswith("_count")]
        sum_samples = [s for s in samples if s.name.endswith("_sum")]
        
        assert len(count_samples) == 1
        assert len(sum_samples) == 1
        assert count_samples[0].value == 10
        assert sum_samples[0].value == pytest.approx(5.5)  # sum of 0.1 to 1.0


class TestMetricsManager:
    """Test MetricsManager."""
    
    def test_register_metrics(self):
        """Test registering different types of metrics."""
        manager = MetricsManager()
        
        counter = manager.register_counter("test_counter", "Test counter")
        gauge = manager.register_gauge("test_gauge", "Test gauge")
        histogram = manager.register_histogram("test_histogram", "Test histogram")
        summary = manager.register_summary("test_summary", "Test summary")
        
        assert isinstance(counter, Counter)
        assert isinstance(gauge, Gauge)
        assert isinstance(histogram, Histogram)
        assert isinstance(summary, Summary)
        
        # Test duplicate registration fails
        with pytest.raises(ValueError):
            manager.register_counter("test_counter", "Duplicate counter")
    
    def test_collect_metrics(self):
        """Test metrics collection."""
        manager = MetricsManager()
        
        counter = manager.register_counter("test_counter", "Test counter")
        gauge = manager.register_gauge("test_gauge", "Test gauge")
        
        counter.inc()
        gauge.set(42)
        
        samples = manager.collect_metrics()
        assert len(samples) >= 2
        
        counter_sample = next(s for s in samples if s.name == "test_counter")
        gauge_sample = next(s for s in samples if s.name == "test_gauge")
        
        assert counter_sample.value == 1
        assert gauge_sample.value == 42
    
    def test_prometheus_export(self):
        """Test Prometheus format export."""
        manager = MetricsManager()
        
        counter = manager.register_counter("http_requests", "HTTP requests", ["method"])
        counter.inc(method="GET")
        
        prometheus_output = manager.export_prometheus_format()
        
        assert "# HELP http_requests HTTP requests" in prometheus_output
        assert "http_requests{method=\"GET\"}" in prometheus_output


class TestHealthChecks:
    """Test health check system."""
    
    @pytest.mark.asyncio
    async def test_database_health_check(self):
        """Test database health check."""
        health_check = DatabaseHealthCheck()
        
        with patch('src.monitoring.health.get_async_session') as mock_session:
            mock_session.return_value.__aenter__ = AsyncMock()
            mock_session.return_value.__aexit__ = AsyncMock()
            
            # Mock successful database query
            mock_session.return_value.__aenter__.return_value.execute = AsyncMock()
            mock_session.return_value.__aenter__.return_value.execute.return_value.fetchone = AsyncMock()
            
            result = await health_check.check()
            
            assert result.name == "database"
            assert result.status == HealthStatus.HEALTHY
            assert "successful" in result.message.lower()
    
    @pytest.mark.asyncio
    async def test_redis_health_check(self):
        """Test Redis health check."""
        health_check = RedisHealthCheck()
        
        with patch('redis.asyncio.Redis.from_url') as mock_redis:
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance
            
            # Mock successful Redis operations
            mock_redis_instance.ping = AsyncMock()
            mock_redis_instance.set = AsyncMock()
            mock_redis_instance.get = AsyncMock(return_value=b"ok")
            mock_redis_instance.close = AsyncMock()
            
            result = await health_check.check()
            
            assert result.name == "redis"
            assert result.status == HealthStatus.HEALTHY
    
    @pytest.mark.asyncio
    async def test_external_api_health_check(self):
        """Test external API health check."""
        health_check = ExternalAPIHealthCheck("test_api", "https://api.example.com/status")
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            
            result = await health_check.check()
            
            assert result.name == "api_test_api"
            assert result.status == HealthStatus.HEALTHY
    
    @pytest.mark.asyncio
    async def test_disk_space_health_check(self):
        """Test disk space health check."""
        health_check = DiskSpaceHealthCheck(warning_threshold=0.8, critical_threshold=0.9)
        
        with patch('shutil.disk_usage') as mock_disk_usage:
            # Mock low disk usage (healthy)
            mock_disk_usage.return_value = (1000, 500, 500)  # total, used, free
            
            result = await health_check.check()
            
            assert result.name == "disk_space"
            assert result.status == HealthStatus.HEALTHY
            assert result.metadata["usage_percent"] == 50.0
    
    @pytest.mark.asyncio
    async def test_memory_health_check(self):
        """Test memory health check."""
        health_check = MemoryHealthCheck(warning_threshold=0.8, critical_threshold=0.9)
        
        with patch('psutil.virtual_memory') as mock_memory:
            # Mock memory info
            mock_memory.return_value.total = 8000000000
            mock_memory.return_value.available = 4000000000
            mock_memory.return_value.used = 4000000000
            mock_memory.return_value.percent = 50.0
            
            result = await health_check.check()
            
            assert result.name == "memory"
            assert result.status == HealthStatus.HEALTHY
    
    @pytest.mark.asyncio
    async def test_health_check_timeout(self):
        """Test health check timeout handling."""
        health_check = DatabaseHealthCheck(timeout=0.1)
        
        with patch('src.monitoring.health.get_async_session') as mock_session:
            # Mock slow database operation
            async def slow_operation():
                await asyncio.sleep(0.2)
                return Mock()
            
            mock_session.return_value.__aenter__ = AsyncMock(side_effect=slow_operation)
            
            result = await health_check.check()
            
            assert result.status == HealthStatus.UNHEALTHY
            assert "timed out" in result.message.lower()


class TestHealthChecker:
    """Test HealthChecker orchestration."""
    
    @pytest.mark.asyncio
    async def test_health_checker_multiple_checks(self):
        """Test health checker with multiple checks."""
        checker = HealthChecker()
        
        # Clear default checks and add test checks
        checker.checks.clear()
        
        # Add mock checks
        check1 = Mock()
        check1.name = "test1"
        check1.check = AsyncMock(return_value=ComponentHealth(
            name="test1", status=HealthStatus.HEALTHY, message="OK"
        ))
        
        check2 = Mock()
        check2.name = "test2"
        check2.check = AsyncMock(return_value=ComponentHealth(
            name="test2", status=HealthStatus.DEGRADED, message="Slow"
        ))
        
        checker.add_check(check1)
        checker.add_check(check2)
        
        result = await checker.check_health()
        
        assert result.overall_status == HealthStatus.DEGRADED  # One degraded component
        assert len(result.components) == 2
    
    @pytest.mark.asyncio
    async def test_health_checker_component_filter(self):
        """Test health checker with component filtering."""
        checker = HealthChecker()
        
        # Clear default checks and add test checks
        checker.checks.clear()
        
        check1 = Mock()
        check1.name = "database"
        check1.check = AsyncMock(return_value=ComponentHealth(
            name="database", status=HealthStatus.HEALTHY, message="OK"
        ))
        
        check2 = Mock()
        check2.name = "redis"
        check2.check = AsyncMock(return_value=ComponentHealth(
            name="redis", status=HealthStatus.HEALTHY, message="OK"
        ))
        
        checker.add_check(check1)
        checker.add_check(check2)
        
        # Check only database
        result = await checker.check_health(["database"])
        
        assert len(result.components) == 1
        assert result.components[0].name == "database"


class TestMiddleware:
    """Test monitoring middleware."""
    
    @pytest.mark.asyncio
    async def test_metrics_middleware(self):
        """Test metrics middleware."""
        # This would require more complex FastAPI testing setup
        # For now, test the core functionality
        
        with patch('src.monitoring.middleware.get_metrics_manager') as mock_manager:
            mock_metrics = Mock()
            mock_manager.return_value = mock_metrics
            
            middleware = MetricsMiddleware(Mock())
            
            # Mock request and response
            request = Mock()
            request.method = "GET"
            request.url.path = "/api/test"
            
            response = Mock()
            response.status_code = 200
            
            async def call_next(req):
                return response
            
            result = await middleware.dispatch(request, call_next)
            
            assert result == response
    
    def test_middleware_setup_function(self):
        """Test middleware setup function."""
        from src.monitoring.middleware import setup_monitoring_middleware
        
        app = Mock()
        app.add_middleware = Mock()
        
        setup_monitoring_middleware(app)
        
        # Should add both middleware types
        assert app.add_middleware.call_count == 2