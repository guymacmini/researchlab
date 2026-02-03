"""Prometheus-style metrics collection for ResearchLab."""

import time
from typing import Dict, List, Optional, Any
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
import threading
from contextlib import contextmanager

import structlog

logger = structlog.get_logger()


class MetricType(Enum):
    """Types of metrics."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class MetricSample:
    """A single metric sample."""
    name: str
    labels: Dict[str, str]
    value: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class HistogramBucket:
    """Histogram bucket with upper bound and count."""
    le: float  # less than or equal to
    count: int = 0


class Counter:
    """Prometheus-style counter metric."""
    
    def __init__(self, name: str, description: str, labels: Optional[List[str]] = None):
        self.name = name
        self.description = description
        self.labels = labels or []
        self._values: Dict[tuple, float] = defaultdict(float)
        self._lock = threading.Lock()
    
    def inc(self, amount: float = 1.0, **labels) -> None:
        """Increment counter by amount."""
        if amount < 0:
            raise ValueError("Counter can only increase")
        
        label_values = tuple(labels.get(label, "") for label in self.labels)
        
        with self._lock:
            self._values[label_values] += amount
    
    def get_samples(self) -> List[MetricSample]:
        """Get current metric samples."""
        samples = []
        
        with self._lock:
            for label_values, value in self._values.items():
                label_dict = dict(zip(self.labels, label_values))
                samples.append(MetricSample(
                    name=self.name,
                    labels=label_dict,
                    value=value
                ))
        
        return samples


class Gauge:
    """Prometheus-style gauge metric."""
    
    def __init__(self, name: str, description: str, labels: Optional[List[str]] = None):
        self.name = name
        self.description = description
        self.labels = labels or []
        self._values: Dict[tuple, float] = defaultdict(float)
        self._lock = threading.Lock()
    
    def set(self, value: float, **labels) -> None:
        """Set gauge to value."""
        label_values = tuple(labels.get(label, "") for label in self.labels)
        
        with self._lock:
            self._values[label_values] = value
    
    def inc(self, amount: float = 1.0, **labels) -> None:
        """Increment gauge by amount."""
        label_values = tuple(labels.get(label, "") for label in self.labels)
        
        with self._lock:
            self._values[label_values] += amount
    
    def dec(self, amount: float = 1.0, **labels) -> None:
        """Decrement gauge by amount."""
        self.inc(-amount, **labels)
    
    def get_samples(self) -> List[MetricSample]:
        """Get current metric samples."""
        samples = []
        
        with self._lock:
            for label_values, value in self._values.items():
                label_dict = dict(zip(self.labels, label_values))
                samples.append(MetricSample(
                    name=self.name,
                    labels=label_dict,
                    value=value
                ))
        
        return samples


class Histogram:
    """Prometheus-style histogram metric."""
    
    DEFAULT_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0, float('inf')]
    
    def __init__(self, name: str, description: str, labels: Optional[List[str]] = None, 
                 buckets: Optional[List[float]] = None):
        self.name = name
        self.description = description
        self.labels = labels or []
        self.buckets = sorted(buckets or self.DEFAULT_BUCKETS)
        
        # Ensure +Inf bucket exists
        if self.buckets[-1] != float('inf'):
            self.buckets.append(float('inf'))
        
        self._buckets: Dict[tuple, List[HistogramBucket]] = defaultdict(
            lambda: [HistogramBucket(le=b) for b in self.buckets]
        )
        self._counts: Dict[tuple, int] = defaultdict(int)
        self._sums: Dict[tuple, float] = defaultdict(float)
        self._lock = threading.Lock()
    
    def observe(self, value: float, **labels) -> None:
        """Observe a value."""
        label_values = tuple(labels.get(label, "") for label in self.labels)
        
        with self._lock:
            # Update count and sum
            self._counts[label_values] += 1
            self._sums[label_values] += value
            
            # Update buckets
            buckets = self._buckets[label_values]
            for bucket in buckets:
                if value <= bucket.le:
                    bucket.count += 1
    
    @contextmanager
    def time(self, **labels):
        """Time a block of code."""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.observe(duration, **labels)
    
    def get_samples(self) -> List[MetricSample]:
        """Get current metric samples."""
        samples = []
        
        with self._lock:
            for label_values, buckets in self._buckets.items():
                label_dict = dict(zip(self.labels, label_values))
                
                # Bucket samples
                for bucket in buckets:
                    bucket_labels = {**label_dict, "le": str(bucket.le)}
                    samples.append(MetricSample(
                        name=f"{self.name}_bucket",
                        labels=bucket_labels,
                        value=bucket.count
                    ))
                
                # Count sample
                samples.append(MetricSample(
                    name=f"{self.name}_count",
                    labels=label_dict,
                    value=self._counts[label_values]
                ))
                
                # Sum sample
                samples.append(MetricSample(
                    name=f"{self.name}_sum",
                    labels=label_dict,
                    value=self._sums[label_values]
                ))
        
        return samples


class Summary:
    """Prometheus-style summary metric with quantiles."""
    
    def __init__(self, name: str, description: str, labels: Optional[List[str]] = None,
                 quantiles: Optional[List[float]] = None, max_age: float = 600, 
                 ageing_buckets: int = 5):
        self.name = name
        self.description = description
        self.labels = labels or []
        self.quantiles = quantiles or [0.5, 0.9, 0.95, 0.99]
        self.max_age = max_age
        self.ageing_buckets = ageing_buckets
        
        # Time-decaying reservoir for each label combination
        self._reservoirs: Dict[tuple, deque] = defaultdict(deque)
        self._counts: Dict[tuple, int] = defaultdict(int)
        self._sums: Dict[tuple, float] = defaultdict(float)
        self._lock = threading.Lock()
    
    def observe(self, value: float, **labels) -> None:
        """Observe a value."""
        label_values = tuple(labels.get(label, "") for label in self.labels)
        current_time = time.time()
        
        with self._lock:
            # Update count and sum
            self._counts[label_values] += 1
            self._sums[label_values] += value
            
            # Add to reservoir
            reservoir = self._reservoirs[label_values]
            reservoir.append((value, current_time))
            
            # Remove old samples
            cutoff_time = current_time - self.max_age
            while reservoir and reservoir[0][1] < cutoff_time:
                reservoir.popleft()
    
    def _calculate_quantiles(self, label_values: tuple) -> Dict[float, float]:
        """Calculate quantiles for given label combination."""
        reservoir = self._reservoirs[label_values]
        if not reservoir:
            return {q: 0.0 for q in self.quantiles}
        
        # Extract values and sort
        values = sorted(value for value, _ in reservoir)
        n = len(values)
        
        quantile_values = {}
        for quantile in self.quantiles:
            if quantile == 0.0:
                quantile_values[quantile] = values[0]
            elif quantile == 1.0:
                quantile_values[quantile] = values[-1]
            else:
                index = (n - 1) * quantile
                lower_index = int(index)
                upper_index = min(lower_index + 1, n - 1)
                weight = index - lower_index
                
                quantile_values[quantile] = (
                    values[lower_index] * (1 - weight) + 
                    values[upper_index] * weight
                )
        
        return quantile_values
    
    def get_samples(self) -> List[MetricSample]:
        """Get current metric samples."""
        samples = []
        
        with self._lock:
            for label_values in self._reservoirs.keys():
                label_dict = dict(zip(self.labels, label_values))
                
                # Quantile samples
                quantile_values = self._calculate_quantiles(label_values)
                for quantile, value in quantile_values.items():
                    quantile_labels = {**label_dict, "quantile": str(quantile)}
                    samples.append(MetricSample(
                        name=self.name,
                        labels=quantile_labels,
                        value=value
                    ))
                
                # Count sample
                samples.append(MetricSample(
                    name=f"{self.name}_count",
                    labels=label_dict,
                    value=self._counts[label_values]
                ))
                
                # Sum sample
                samples.append(MetricSample(
                    name=f"{self.name}_sum",
                    labels=label_dict,
                    value=self._sums[label_values]
                ))
        
        return samples


class MetricsManager:
    """Central metrics manager for ResearchLab."""
    
    def __init__(self):
        self._metrics: Dict[str, Any] = {}
        self._lock = threading.Lock()
        
        logger.info("Metrics manager initialized")
    
    def register_counter(self, name: str, description: str, 
                        labels: Optional[List[str]] = None) -> Counter:
        """Register a counter metric."""
        with self._lock:
            if name in self._metrics:
                raise ValueError(f"Metric {name} already registered")
            
            counter = Counter(name, description, labels)
            self._metrics[name] = counter
            logger.debug("Registered counter metric", name=name)
            return counter
    
    def register_gauge(self, name: str, description: str,
                      labels: Optional[List[str]] = None) -> Gauge:
        """Register a gauge metric."""
        with self._lock:
            if name in self._metrics:
                raise ValueError(f"Metric {name} already registered")
            
            gauge = Gauge(name, description, labels)
            self._metrics[name] = gauge
            logger.debug("Registered gauge metric", name=name)
            return gauge
    
    def register_histogram(self, name: str, description: str,
                          labels: Optional[List[str]] = None,
                          buckets: Optional[List[float]] = None) -> Histogram:
        """Register a histogram metric."""
        with self._lock:
            if name in self._metrics:
                raise ValueError(f"Metric {name} already registered")
            
            histogram = Histogram(name, description, labels, buckets)
            self._metrics[name] = histogram
            logger.debug("Registered histogram metric", name=name)
            return histogram
    
    def register_summary(self, name: str, description: str,
                        labels: Optional[List[str]] = None,
                        quantiles: Optional[List[float]] = None) -> Summary:
        """Register a summary metric."""
        with self._lock:
            if name in self._metrics:
                raise ValueError(f"Metric {name} already registered")
            
            summary = Summary(name, description, labels, quantiles)
            self._metrics[name] = summary
            logger.debug("Registered summary metric", name=name)
            return summary
    
    def get_metric(self, name: str) -> Optional[Any]:
        """Get a metric by name."""
        with self._lock:
            return self._metrics.get(name)
    
    def collect_metrics(self) -> List[MetricSample]:
        """Collect all metric samples."""
        samples = []
        
        with self._lock:
            for metric in self._metrics.values():
                samples.extend(metric.get_samples())
        
        return samples
    
    def export_prometheus_format(self) -> str:
        """Export metrics in Prometheus format."""
        samples = self.collect_metrics()
        lines = []
        
        # Group samples by metric name for help text
        metric_descriptions = {}
        with self._lock:
            for metric in self._metrics.values():
                metric_descriptions[metric.name] = metric.description
        
        for name, description in metric_descriptions.items():
            lines.append(f"# HELP {name} {description}")
            lines.append(f"# TYPE {name} counter")  # Simplified type detection
        
        # Add samples
        for sample in samples:
            if sample.labels:
                label_str = ",".join(f'{k}="{v}"' for k, v in sample.labels.items())
                lines.append(f"{sample.name}{{{label_str}}} {sample.value} {int(sample.timestamp * 1000)}")
            else:
                lines.append(f"{sample.name} {sample.value} {int(sample.timestamp * 1000)}")
        
        return "\n".join(lines) + "\n"


# Global metrics manager instance
_metrics_manager: Optional[MetricsManager] = None
_manager_lock = threading.Lock()


def get_metrics_manager() -> MetricsManager:
    """Get the global metrics manager instance."""
    global _metrics_manager
    
    with _manager_lock:
        if _metrics_manager is None:
            _metrics_manager = MetricsManager()
        
        return _metrics_manager


# Pre-registered application metrics
metrics_manager = get_metrics_manager()

# HTTP request metrics
request_duration = metrics_manager.register_histogram(
    name="http_request_duration_seconds",
    description="Duration of HTTP requests in seconds",
    labels=["method", "endpoint", "status_code"]
)

request_counter = metrics_manager.register_counter(
    name="http_requests_total",
    description="Total number of HTTP requests",
    labels=["method", "endpoint", "status_code"]
)

# Database metrics
database_operations = metrics_manager.register_histogram(
    name="database_operation_duration_seconds",
    description="Duration of database operations in seconds",
    labels=["operation", "table"]
)

# Agent metrics
agent_executions = metrics_manager.register_histogram(
    name="agent_execution_duration_seconds",
    description="Duration of agent executions in seconds",
    labels=["agent_type", "status"]
)

# External API metrics
api_calls_counter = metrics_manager.register_counter(
    name="external_api_calls_total",
    description="Total number of external API calls",
    labels=["api_name", "endpoint", "status"]
)

# Error metrics
error_counter = metrics_manager.register_counter(
    name="errors_total",
    description="Total number of errors",
    labels=["component", "error_type"]
)

# Workflow metrics
workflow_duration = metrics_manager.register_histogram(
    name="workflow_duration_seconds",
    description="Duration of research workflows in seconds",
    labels=["workflow_type", "status"]
)

# Data processing metrics
data_processing_duration = metrics_manager.register_histogram(
    name="data_processing_duration_seconds",
    description="Duration of data processing operations in seconds",
    labels=["operation", "source"]
)