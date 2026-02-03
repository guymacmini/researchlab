"""Performance and monitoring tests for ResearchLab."""

import pytest
import asyncio
import time
import json
import psutil
import threading
from unittest.mock import Mock, patch, AsyncMock
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from src.data.clients.rate_limiter import RateLimiter
from src.agents.base import AgentResult, AgentRole
from src.core.config import settings


class TestPerformanceBenchmarks:
    """Performance benchmarks for critical components."""
    
    def test_rate_limiter_performance(self):
        """Test rate limiter performance under load."""
        async def benchmark_rate_limiter():
            limiter = RateLimiter()
            await limiter.set_limit("perf_test", 1000, 60)  # 1000 requests per minute
            
            start_time = time.time()
            
            # Test 1000 sequential requests
            for i in range(1000):
                result = await limiter.check_and_consume("perf_test")
                assert result is True
            
            elapsed = time.time() - start_time
            
            # Should handle 1000 requests in reasonable time (< 1 second)
            assert elapsed < 1.0
            
            # Test requests per second
            rps = 1000 / elapsed
            assert rps > 500  # Should handle at least 500 RPS
            
            return elapsed, rps
        
        # Run async benchmark
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            elapsed, rps = loop.run_until_complete(benchmark_rate_limiter())
            print(f"Rate limiter: {elapsed:.3f}s for 1000 requests ({rps:.0f} RPS)")
        finally:
            loop.close()
    
    def test_concurrent_rate_limiting_performance(self):
        """Test rate limiter performance under concurrent load."""
        async def concurrent_benchmark():
            limiter = RateLimiter()
            await limiter.set_limit("concurrent_perf", 10000, 60)  # High limit
            
            start_time = time.time()
            
            # Create 100 concurrent batches of 10 requests each
            tasks = []
            for batch in range(100):
                batch_tasks = []
                for req in range(10):
                    batch_tasks.append(limiter.check_and_consume("concurrent_perf"))
                tasks.extend(batch_tasks)
            
            results = await asyncio.gather(*tasks)
            elapsed = time.time() - start_time
            
            # All should succeed
            assert all(results)
            
            # Should handle concurrent load efficiently
            assert elapsed < 5.0  # 1000 concurrent requests in < 5 seconds
            
            concurrent_rps = 1000 / elapsed
            return elapsed, concurrent_rps
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            elapsed, rps = loop.run_until_complete(concurrent_benchmark())
            print(f"Concurrent rate limiter: {elapsed:.3f}s for 1000 requests ({rps:.0f} RPS)")
        finally:
            loop.close()
    
    def test_agent_result_serialization_performance(self):
        """Test agent result serialization performance."""
        # Create various sized results
        test_cases = [
            ("small", {"metrics": list(range(10))}),
            ("medium", {"metrics": list(range(1000))}),
            ("large", {"metrics": list(range(10000))})
        ]
        
        for size_name, data in test_cases:
            result = AgentResult(
                agent=AgentRole.QUANTITATIVE_ANALYST,
                success=True,
                data=data,
                confidence=0.85,
                sources=[f"source_{i}" for i in range(len(data["metrics"]) // 10)],
                reasoning=f"Analysis of {len(data['metrics'])} data points"
            )
            
            # Test serialization
            start_time = time.time()
            serialized = json.dumps(result.dict())
            serialization_time = time.time() - start_time
            
            # Test deserialization  
            start_time = time.time()
            deserialized = json.loads(serialized)
            deserialization_time = time.time() - start_time
            
            print(f"{size_name.title()} result ({len(data['metrics'])} items):")
            print(f"  Serialization: {serialization_time:.4f}s")
            print(f"  Deserialization: {deserialization_time:.4f}s")
            print(f"  Size: {len(serialized):,} bytes")
            
            # Performance assertions
            if size_name == "small":
                assert serialization_time < 0.001
                assert deserialization_time < 0.001
            elif size_name == "medium":
                assert serialization_time < 0.01
                assert deserialization_time < 0.01
            else:  # large
                assert serialization_time < 0.1
                assert deserialization_time < 0.1
    
    def test_configuration_loading_performance(self):
        """Test configuration loading performance."""
        start_time = time.time()
        
        # Load configuration multiple times
        for _ in range(100):
            from src.core.config import Settings
            test_settings = Settings()
            
            # Access various configuration values
            _ = test_settings.app.app_name
            _ = test_settings.database.host
            _ = test_settings.api.finnhub_rate_limit
        
        elapsed = time.time() - start_time
        
        # Should load configuration quickly
        assert elapsed < 1.0  # 100 loads in < 1 second
        
        loads_per_second = 100 / elapsed
        print(f"Configuration loading: {elapsed:.3f}s for 100 loads ({loads_per_second:.0f} loads/s)")
    
    def test_memory_usage_agent_results(self):
        """Test memory usage of agent results."""
        import gc
        
        # Get initial memory usage
        gc.collect()
        initial_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        
        # Create many agent results
        results = []
        for i in range(1000):
            result = AgentResult(
                agent=AgentRole.FUNDAMENTAL_ANALYST,
                success=True,
                data={
                    "company_analysis": {
                        "financial_health": 0.85 + (i % 100) / 1000,
                        "growth_potential": 0.75 + (i % 100) / 1000,
                        "metrics": list(range(100))  # Some data
                    }
                },
                confidence=0.8 + (i % 20) / 100,
                sources=["10-K", "10-Q", "8-K", "Earnings"],
                reasoning=f"Analysis {i} completed with comprehensive review"
            )
            results.append(result)
        
        # Get memory after creating results
        gc.collect()
        final_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        
        memory_used = final_memory - initial_memory
        memory_per_result = memory_used / 1000
        
        print(f"Memory usage: {memory_used:.2f} MB for 1000 results ({memory_per_result:.3f} MB per result)")
        
        # Should not use excessive memory
        assert memory_per_result < 0.1  # Less than 100KB per result
        assert memory_used < 100  # Total less than 100MB


class TestPerformanceMonitoring:
    """Test performance monitoring capabilities."""
    
    def test_execution_time_tracking(self):
        """Test execution time tracking utility."""
        class ExecutionTimer:
            def __init__(self):
                self.start_time = None
                self.end_time = None
            
            def start(self):
                self.start_time = time.time()
            
            def stop(self):
                self.end_time = time.time()
            
            def elapsed(self):
                if self.start_time and self.end_time:
                    return self.end_time - self.start_time
                return None
        
        timer = ExecutionTimer()
        timer.start()
        
        # Simulate some work
        time.sleep(0.1)
        
        timer.stop()
        elapsed = timer.elapsed()
        
        assert elapsed is not None
        assert 0.09 < elapsed < 0.15  # Should be around 0.1 seconds
    
    def test_resource_usage_monitoring(self):
        """Test resource usage monitoring."""
        process = psutil.Process()
        
        # Get initial stats
        initial_cpu = process.cpu_percent()
        initial_memory = process.memory_info().rss
        
        # Do some work
        start_time = time.time()
        data = []
        for i in range(100000):
            data.append({"id": i, "value": i * 2})
        
        # Simulate processing
        processed = [item["value"] for item in data if item["id"] % 2 == 0]
        
        work_time = time.time() - start_time
        
        # Get final stats
        final_cpu = process.cpu_percent()
        final_memory = process.memory_info().rss
        
        memory_increase = (final_memory - initial_memory) / 1024 / 1024  # MB
        
        print(f"Work completed in {work_time:.3f}s")
        print(f"Memory increase: {memory_increase:.2f} MB")
        print(f"CPU usage: {final_cpu}%")
        
        # Reasonable performance expectations
        assert work_time < 1.0  # Should complete quickly
        assert memory_increase < 100  # Should not use excessive memory
    
    def test_concurrent_performance_monitoring(self):
        """Test performance under concurrent load."""
        def cpu_intensive_task(task_id):
            """Simulate CPU-intensive work."""
            result = 0
            for i in range(100000):
                result += i ** 2
            return result
        
        def io_intensive_task(task_id):
            """Simulate I/O-intensive work."""
            time.sleep(0.01)  # Simulate I/O wait
            return f"Task {task_id} completed"
        
        # Test CPU-bound concurrency
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=4) as executor:
            cpu_futures = [executor.submit(cpu_intensive_task, i) for i in range(8)]
            cpu_results = [f.result() for f in cpu_futures]
        
        cpu_time = time.time() - start_time
        
        # Test I/O-bound concurrency
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=4) as executor:
            io_futures = [executor.submit(io_intensive_task, i) for i in range(20)]
            io_results = [f.result() for f in io_futures]
        
        io_time = time.time() - start_time
        
        print(f"CPU-bound tasks: {cpu_time:.3f}s for 8 tasks")
        print(f"I/O-bound tasks: {io_time:.3f}s for 20 tasks")
        
        # Concurrency should provide benefits
        assert len(cpu_results) == 8
        assert len(io_results) == 20
        assert io_time < 0.3  # I/O tasks should benefit from concurrency
    
    def test_memory_leak_detection(self):
        """Test for memory leaks in repeated operations."""
        import gc
        
        def create_and_destroy_objects():
            """Create objects and let them go out of scope."""
            results = []
            for i in range(100):
                result = AgentResult(
                    agent=AgentRole.RISK_ANALYST,
                    success=True,
                    data={"risk_score": 0.5 + i / 1000},
                    confidence=0.8,
                    sources=["Risk model", "Historical data"],
                    reasoning=f"Risk analysis iteration {i}"
                )
                results.append(result)
            # Let results go out of scope
            return len(results)
        
        # Run multiple cycles
        memory_samples = []
        
        for cycle in range(10):
            gc.collect()  # Force garbage collection
            
            memory_before = psutil.Process().memory_info().rss / 1024 / 1024
            
            # Create and destroy objects
            count = create_and_destroy_objects()
            assert count == 100
            
            gc.collect()  # Force garbage collection
            
            memory_after = psutil.Process().memory_info().rss / 1024 / 1024
            memory_samples.append(memory_after)
        
        # Check for memory growth trend
        initial_memory = memory_samples[0]
        final_memory = memory_samples[-1]
        memory_growth = final_memory - initial_memory
        
        print(f"Memory samples: {memory_samples}")
        print(f"Memory growth over 10 cycles: {memory_growth:.2f} MB")
        
        # Should not have significant memory growth (< 10MB)
        assert memory_growth < 10


class TestScalabilityMetrics:
    """Test scalability characteristics."""
    
    def test_linear_scaling_rate_limiter(self):
        """Test rate limiter scales linearly."""
        async def test_scaling():
            limiter = RateLimiter()
            
            # Test different load levels
            load_levels = [100, 200, 500, 1000]
            times = []
            
            for load in load_levels:
                await limiter.set_limit(f"scale_test_{load}", load, 60)
                
                start_time = time.time()
                
                tasks = []
                for i in range(load):
                    tasks.append(limiter.check_and_consume(f"scale_test_{load}"))
                
                results = await asyncio.gather(*tasks)
                elapsed = time.time() - start_time
                times.append(elapsed)
                
                # All requests should succeed
                assert all(results)
            
            # Calculate scaling coefficient
            # Time should scale roughly linearly with load
            for i in range(1, len(load_levels)):
                load_ratio = load_levels[i] / load_levels[i-1]
                time_ratio = times[i] / times[i-1]
                
                # Time ratio should be close to load ratio (linear scaling)
                # Allow some variance due to setup costs
                assert time_ratio < load_ratio * 2  # Not more than 2x worse than linear
            
            return load_levels, times
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loads, times = loop.run_until_complete(test_scaling())
            for load, time_taken in zip(loads, times):
                rps = load / time_taken
                print(f"Load {load}: {time_taken:.3f}s ({rps:.0f} RPS)")
        finally:
            loop.close()
    
    def test_data_structure_scaling(self):
        """Test data structure performance at different scales."""
        # Test dictionary access scaling
        scales = [100, 1000, 10000, 100000]
        
        for scale in scales:
            # Create large dictionary
            large_dict = {f"key_{i}": f"value_{i}" for i in range(scale)}
            
            # Time random access
            import random
            keys_to_test = [f"key_{random.randint(0, scale-1)}" for _ in range(1000)]
            
            start_time = time.time()
            for key in keys_to_test:
                _ = large_dict.get(key)
            elapsed = time.time() - start_time
            
            access_time_per_lookup = elapsed / 1000
            
            print(f"Dict scale {scale}: {access_time_per_lookup:.6f}s per lookup")
            
            # Dictionary access should be O(1) - constant time
            assert access_time_per_lookup < 0.001  # Less than 1ms per lookup
    
    def test_concurrent_connection_scaling(self):
        """Test handling multiple concurrent connections."""
        async def simulate_concurrent_clients():
            # Simulate multiple clients making requests
            client_count = 50
            requests_per_client = 10
            
            async def simulate_client(client_id):
                """Simulate a single client making multiple requests."""
                results = []
                for request in range(requests_per_client):
                    # Simulate request processing time
                    await asyncio.sleep(0.001)  # 1ms processing time
                    
                    result = {
                        "client_id": client_id,
                        "request_id": request,
                        "timestamp": time.time(),
                        "status": "completed"
                    }
                    results.append(result)
                
                return results
            
            start_time = time.time()
            
            # Create tasks for all clients
            client_tasks = []
            for client_id in range(client_count):
                task = simulate_client(client_id)
                client_tasks.append(task)
            
            # Wait for all clients to complete
            all_results = await asyncio.gather(*client_tasks)
            
            elapsed = time.time() - start_time
            
            # Flatten results
            total_requests = sum(len(client_results) for client_results in all_results)
            
            requests_per_second = total_requests / elapsed
            
            print(f"Concurrent clients: {client_count}")
            print(f"Total requests: {total_requests}")
            print(f"Total time: {elapsed:.3f}s")
            print(f"Requests per second: {requests_per_second:.0f}")
            
            # Should handle concurrent load efficiently
            assert total_requests == client_count * requests_per_client
            assert requests_per_second > 1000  # Should handle at least 1000 RPS
            
            return requests_per_second
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            rps = loop.run_until_complete(simulate_concurrent_clients())
            assert rps > 0
        finally:
            loop.close()


class TestPerformanceRegression:
    """Test for performance regressions."""
    
    def test_baseline_performance_metrics(self):
        """Establish baseline performance metrics."""
        metrics = {}
        
        # Test 1: Simple object creation
        start_time = time.time()
        results = []
        for i in range(1000):
            result = AgentResult(
                agent=AgentRole.FUNDAMENTAL_ANALYST,
                success=True,
                data={"metric": i},
                confidence=0.8
            )
            results.append(result)
        
        metrics['object_creation_1000'] = time.time() - start_time
        
        # Test 2: JSON serialization
        start_time = time.time()
        for result in results[:100]:  # Serialize first 100
            json.dumps(result.dict())
        
        metrics['json_serialization_100'] = time.time() - start_time
        
        # Test 3: Configuration access
        start_time = time.time()
        for _ in range(1000):
            _ = settings.app.app_name
            _ = settings.database.host
            _ = settings.api.finnhub_rate_limit
        
        metrics['config_access_1000'] = time.time() - start_time
        
        # Print baseline metrics
        for test_name, time_taken in metrics.items():
            print(f"Baseline {test_name}: {time_taken:.4f}s")
        
        # Store expected performance ranges
        expected_ranges = {
            'object_creation_1000': (0.0, 0.5),      # Should be very fast
            'json_serialization_100': (0.0, 0.1),    # Should be quick
            'config_access_1000': (0.0, 0.1)         # Should be very quick
        }
        
        # Check against expected ranges
        for test_name, time_taken in metrics.items():
            min_time, max_time = expected_ranges[test_name]
            assert min_time <= time_taken <= max_time, \
                f"{test_name} took {time_taken:.4f}s, expected {min_time}-{max_time}s"
        
        return metrics
    
    def test_memory_footprint_regression(self):
        """Test memory footprint doesn't regress."""
        import gc
        
        gc.collect()
        initial_memory = psutil.Process().memory_info().rss / 1024 / 1024
        
        # Create typical workload
        results = []
        for i in range(500):
            result = AgentResult(
                agent=AgentRole.QUANTITATIVE_ANALYST,
                success=True,
                data={
                    "analysis": f"Result {i}",
                    "metrics": list(range(50)),  # Some data
                    "score": 0.8 + (i % 20) / 100
                },
                confidence=0.75 + (i % 25) / 100,
                sources=["Data source A", "Data source B"],
                reasoning=f"Detailed analysis for iteration {i}"
            )
            results.append(result)
        
        gc.collect()
        peak_memory = psutil.Process().memory_info().rss / 1024 / 1024
        
        memory_used = peak_memory - initial_memory
        memory_per_result = memory_used / 500
        
        print(f"Memory footprint test:")
        print(f"  Initial memory: {initial_memory:.2f} MB")
        print(f"  Peak memory: {peak_memory:.2f} MB")
        print(f"  Memory used: {memory_used:.2f} MB")
        print(f"  Memory per result: {memory_per_result:.3f} MB")
        
        # Set regression thresholds
        assert memory_used < 50, f"Memory usage {memory_used:.2f} MB exceeds limit of 50 MB"
        assert memory_per_result < 0.1, f"Memory per result {memory_per_result:.3f} MB exceeds limit"


# Performance test utilities
class PerformanceTimer:
    """Utility class for performance timing."""
    
    def __init__(self, name="Operation"):
        self.name = name
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        elapsed = self.end_time - self.start_time
        print(f"{self.name}: {elapsed:.4f}s")
    
    def elapsed(self):
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None


# Test helper for async performance tests
async def async_performance_test(test_func, iterations=100):
    """Helper for running async performance tests."""
    times = []
    
    for _ in range(iterations):
        start_time = time.time()
        await test_func()
        elapsed = time.time() - start_time
        times.append(elapsed)
    
    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)
    
    return {
        "average": avg_time,
        "minimum": min_time,
        "maximum": max_time,
        "iterations": iterations
    }