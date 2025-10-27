"""
PowerNight Performance Monitoring and Metrics

Enterprise-grade performance monitoring with metrics collection, alerting, and reporting.
"""

import time
import threading
import json
import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from functools import wraps
from collections import defaultdict, deque
import statistics
import psutil
import os

from flask import request, g, current_app


@dataclass
class MetricPoint:
    """A single metric data point."""
    timestamp: datetime
    value: float
    labels: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'value': self.value,
            'labels': self.labels
        }


@dataclass
class RequestMetrics:
    """Metrics for a single HTTP request."""
    method: str
    endpoint: str
    status_code: int
    duration_ms: float
    timestamp: datetime
    user_agent: str = ""
    tesla_email: str = ""
    request_size: int = 0
    response_size: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class SystemMetrics:
    """System-level performance metrics."""
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_available_mb: float
    disk_usage_percent: float
    network_sent_mb: float
    network_recv_mb: float
    process_count: int
    uptime_seconds: float
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'cpu_percent': self.cpu_percent,
            'memory_percent': self.memory_percent,
            'memory_used_mb': self.memory_used_mb,
            'memory_available_mb': self.memory_available_mb,
            'disk_usage_percent': self.disk_usage_percent,
            'network_sent_mb': self.network_sent_mb,
            'network_recv_mb': self.network_recv_mb,
            'process_count': self.process_count,
            'uptime_seconds': self.uptime_seconds,
            'timestamp': self.timestamp.isoformat()
        }


class MetricsCollector:
    """Enterprise metrics collector with time-series storage."""

    def __init__(self, max_data_points: int = 10000):
        """Initialize metrics collector."""
        self.max_data_points = max_data_points
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_data_points))
        self.request_metrics: deque = deque(maxlen=max_data_points)
        self.system_metrics: deque = deque(maxlen=1000)  # Smaller buffer for system metrics
        self.alerts: List[Dict[str, Any]] = []
        self.start_time = datetime.now()
        self.logger = logging.getLogger(__name__)

        # Threading for background collection
        self.collection_thread = None
        self.stop_collection = threading.Event()

        # System monitoring baseline
        self._network_baseline = None
        self._setup_network_baseline()

    def _setup_network_baseline(self) -> None:
        """Setup network monitoring baseline."""
        try:
            net_io = psutil.net_io_counters()
            self._network_baseline = {
                'bytes_sent': net_io.bytes_sent,
                'bytes_recv': net_io.bytes_recv,
                'timestamp': time.time()
            }
        except Exception:
            self._network_baseline = None

    def start_background_collection(self, interval: float = 30.0) -> None:
        """Start background system metrics collection."""
        if self.collection_thread and self.collection_thread.is_alive():
            return

        def collect_system_metrics():
            while not self.stop_collection.wait(interval):
                try:
                    self.collect_system_metrics()
                except Exception as e:
                    self.logger.error(f"Error collecting system metrics: {e}")

        self.collection_thread = threading.Thread(target=collect_system_metrics, daemon=True)
        self.collection_thread.start()
        self.logger.info("Started background metrics collection")

    def stop_background_collection(self) -> None:
        """Stop background metrics collection."""
        if self.collection_thread:
            self.stop_collection.set()
            self.collection_thread.join(timeout=5)
            self.logger.info("Stopped background metrics collection")

    def record_metric(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Record a custom metric."""
        point = MetricPoint(
            timestamp=datetime.now(),
            value=value,
            labels=labels or {}
        )
        self.metrics[name].append(point)

    def record_request(self, method: str, endpoint: str, status_code: int,
                      duration_ms: float, **kwargs) -> None:
        """Record HTTP request metrics."""
        metrics = RequestMetrics(
            method=method,
            endpoint=endpoint,
            status_code=status_code,
            duration_ms=duration_ms,
            timestamp=datetime.now(),
            **kwargs
        )
        self.request_metrics.append(metrics)

        # Update derived metrics
        self.record_metric(f"http_requests_total", 1, {
            'method': method,
            'endpoint': endpoint,
            'status': str(status_code)
        })
        self.record_metric(f"http_request_duration_ms", duration_ms, {
            'method': method,
            'endpoint': endpoint
        })

    def collect_system_metrics(self) -> SystemMetrics:
        """Collect current system metrics."""
        try:
            # CPU and Memory
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()

            # Disk usage
            disk = psutil.disk_usage('/')
            disk_usage_percent = (disk.used / disk.total) * 100

            # Network (delta since baseline)
            network_sent_mb = 0
            network_recv_mb = 0
            if self._network_baseline:
                try:
                    net_io = psutil.net_io_counters()
                    network_sent_mb = (net_io.bytes_sent - self._network_baseline['bytes_sent']) / (1024 * 1024)
                    network_recv_mb = (net_io.bytes_recv - self._network_baseline['bytes_recv']) / (1024 * 1024)
                except Exception:
                    pass

            # Process count
            process_count = len(psutil.pids())

            # Uptime
            uptime_seconds = (datetime.now() - self.start_time).total_seconds()

            metrics = SystemMetrics(
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_used_mb=memory.used / (1024 * 1024),
                memory_available_mb=memory.available / (1024 * 1024),
                disk_usage_percent=disk_usage_percent,
                network_sent_mb=network_sent_mb,
                network_recv_mb=network_recv_mb,
                process_count=process_count,
                uptime_seconds=uptime_seconds,
                timestamp=datetime.now()
            )

            self.system_metrics.append(metrics)

            # Record individual metrics for alerting
            self.record_metric("system_cpu_percent", cpu_percent)
            self.record_metric("system_memory_percent", memory.percent)
            self.record_metric("system_disk_percent", disk_usage_percent)

            # Check for alerts
            self._check_system_alerts(metrics)

            return metrics

        except Exception as e:
            self.logger.error(f"Error collecting system metrics: {e}")
            raise

    def _check_system_alerts(self, metrics: SystemMetrics) -> None:
        """Check system metrics for alert conditions."""
        alerts = []

        # CPU alerts
        if metrics.cpu_percent > 90:
            alerts.append({
                'type': 'cpu_high',
                'severity': 'critical',
                'message': f'CPU usage is {metrics.cpu_percent:.1f}%',
                'value': metrics.cpu_percent,
                'threshold': 90
            })
        elif metrics.cpu_percent > 75:
            alerts.append({
                'type': 'cpu_high',
                'severity': 'warning',
                'message': f'CPU usage is {metrics.cpu_percent:.1f}%',
                'value': metrics.cpu_percent,
                'threshold': 75
            })

        # Memory alerts
        if metrics.memory_percent > 95:
            alerts.append({
                'type': 'memory_high',
                'severity': 'critical',
                'message': f'Memory usage is {metrics.memory_percent:.1f}%',
                'value': metrics.memory_percent,
                'threshold': 95
            })
        elif metrics.memory_percent > 80:
            alerts.append({
                'type': 'memory_high',
                'severity': 'warning',
                'message': f'Memory usage is {metrics.memory_percent:.1f}%',
                'value': metrics.memory_percent,
                'threshold': 80
            })

        # Disk alerts
        if metrics.disk_usage_percent > 95:
            alerts.append({
                'type': 'disk_full',
                'severity': 'critical',
                'message': f'Disk usage is {metrics.disk_usage_percent:.1f}%',
                'value': metrics.disk_usage_percent,
                'threshold': 95
            })
        elif metrics.disk_usage_percent > 85:
            alerts.append({
                'type': 'disk_full',
                'severity': 'warning',
                'message': f'Disk usage is {metrics.disk_usage_percent:.1f}%',
                'value': metrics.disk_usage_percent,
                'threshold': 85
            })

        # Add timestamp to alerts and store
        for alert in alerts:
            alert['timestamp'] = datetime.now().isoformat()
            self.alerts.append(alert)

        # Keep only recent alerts (last 24 hours)
        cutoff_time = datetime.now() - timedelta(hours=24)
        self.alerts = [
            alert for alert in self.alerts
            if datetime.fromisoformat(alert['timestamp']) > cutoff_time
        ]

    def get_metrics_summary(self, metric_name: str, time_window: Optional[timedelta] = None) -> Dict[str, Any]:
        """Get statistical summary for a metric."""
        if metric_name not in self.metrics:
            return {'error': f'Metric {metric_name} not found'}

        metrics_data = self.metrics[metric_name]

        # Filter by time window if specified
        if time_window:
            cutoff_time = datetime.now() - time_window
            metrics_data = [m for m in metrics_data if m.timestamp > cutoff_time]

        if not metrics_data:
            return {'error': 'No data points found'}

        values = [m.value for m in metrics_data]

        return {
            'count': len(values),
            'min': min(values),
            'max': max(values),
            'mean': statistics.mean(values),
            'median': statistics.median(values),
            'std_dev': statistics.stdev(values) if len(values) > 1 else 0,
            'percentile_95': statistics.quantiles(values, n=20)[18] if len(values) > 1 else values[0],
            'percentile_99': statistics.quantiles(values, n=100)[98] if len(values) > 1 else values[0],
            'first_timestamp': metrics_data[0].timestamp.isoformat(),
            'last_timestamp': metrics_data[-1].timestamp.isoformat()
        }

    def get_request_analytics(self, time_window: Optional[timedelta] = None) -> Dict[str, Any]:
        """Get HTTP request analytics."""
        requests_data = list(self.request_metrics)

        # Filter by time window if specified
        if time_window:
            cutoff_time = datetime.now() - time_window
            requests_data = [r for r in requests_data if r.timestamp > cutoff_time]

        if not requests_data:
            return {'error': 'No request data found'}

        # Calculate various analytics
        total_requests = len(requests_data)

        # Status code distribution
        status_codes = defaultdict(int)
        for req in requests_data:
            status_codes[req.status_code] += 1

        # Endpoint popularity
        endpoints = defaultdict(int)
        for req in requests_data:
            endpoints[req.endpoint] += 1

        # Response time statistics
        durations = [req.duration_ms for req in requests_data]

        # Error rate
        error_requests = sum(1 for req in requests_data if req.status_code >= 400)
        error_rate = (error_requests / total_requests) * 100 if total_requests > 0 else 0

        # Requests per minute (approximate)
        if requests_data:
            time_span = (requests_data[-1].timestamp - requests_data[0].timestamp).total_seconds() / 60
            rpm = total_requests / time_span if time_span > 0 else 0
        else:
            rpm = 0

        return {
            'total_requests': total_requests,
            'error_rate_percent': round(error_rate, 2),
            'requests_per_minute': round(rpm, 2),
            'status_codes': dict(status_codes),
            'top_endpoints': dict(sorted(endpoints.items(), key=lambda x: x[1], reverse=True)[:10]),
            'response_time_stats': {
                'min_ms': min(durations),
                'max_ms': max(durations),
                'mean_ms': round(statistics.mean(durations), 2),
                'median_ms': round(statistics.median(durations), 2),
                'p95_ms': round(statistics.quantiles(durations, n=20)[18] if len(durations) > 1 else durations[0], 2),
                'p99_ms': round(statistics.quantiles(durations, n=100)[98] if len(durations) > 1 else durations[0], 2)
            }
        }

    def get_current_alerts(self) -> List[Dict[str, Any]]:
        """Get current active alerts."""
        # Return alerts from the last hour
        cutoff_time = datetime.now() - timedelta(hours=1)
        recent_alerts = [
            alert for alert in self.alerts
            if datetime.fromisoformat(alert['timestamp']) > cutoff_time
        ]

        # Group by type and return only the most recent of each type
        alert_types = {}
        for alert in recent_alerts:
            alert_type = alert['type']
            if alert_type not in alert_types or alert['timestamp'] > alert_types[alert_type]['timestamp']:
                alert_types[alert_type] = alert

        return list(alert_types.values())

    def export_metrics(self, format: str = 'json', time_window: Optional[timedelta] = None) -> str:
        """Export metrics in specified format."""
        if format.lower() == 'json':
            return self._export_json(time_window)
        elif format.lower() == 'prometheus':
            return self._export_prometheus(time_window)
        else:
            raise ValueError(f"Unsupported export format: {format}")

    def _export_json(self, time_window: Optional[timedelta] = None) -> str:
        """Export metrics as JSON."""
        cutoff_time = datetime.now() - time_window if time_window else None

        export_data = {
            'export_timestamp': datetime.now().isoformat(),
            'time_window_hours': time_window.total_seconds() / 3600 if time_window else None,
            'metrics': {},
            'request_metrics': [],
            'system_metrics': [],
            'alerts': self.get_current_alerts()
        }

        # Export custom metrics
        for name, points in self.metrics.items():
            filtered_points = [
                p for p in points
                if not cutoff_time or p.timestamp > cutoff_time
            ]
            export_data['metrics'][name] = [p.to_dict() for p in filtered_points]

        # Export request metrics
        filtered_requests = [
            r for r in self.request_metrics
            if not cutoff_time or r.timestamp > cutoff_time
        ]
        export_data['request_metrics'] = [r.to_dict() for r in filtered_requests]

        # Export system metrics
        filtered_system = [
            s for s in self.system_metrics
            if not cutoff_time or s.timestamp > cutoff_time
        ]
        export_data['system_metrics'] = [s.to_dict() for s in filtered_system]

        return json.dumps(export_data, indent=2)

    def _export_prometheus(self, time_window: Optional[timedelta] = None) -> str:
        """Export metrics in Prometheus format."""
        lines = []

        # Add metadata
        lines.append(f"# HELP powernight_metrics PowerNight application metrics")
        lines.append(f"# TYPE powernight_metrics counter")

        # Export latest values for each metric
        for name, points in self.metrics.items():
            if points:
                latest_point = points[-1]
                # Prometheus metric names should use underscores
                prom_name = name.replace('-', '_').replace('.', '_')

                # Add labels if present
                labels = ''
                if latest_point.labels:
                    label_pairs = [f'{k}="{v}"' for k, v in latest_point.labels.items()]
                    labels = '{' + ','.join(label_pairs) + '}'

                lines.append(f"powernight_{prom_name}{labels} {latest_point.value}")

        return '\n'.join(lines)


# Global metrics collector instance
_metrics_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    return _metrics_collector


def performance_monitor(metric_name: Optional[str] = None):
    """Decorator for monitoring function performance."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            metric_key = metric_name or f"{func.__module__}.{func.__name__}"

            try:
                result = func(*args, **kwargs)
                success = True
            except Exception as e:
                success = False
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000

                # Record performance metric
                collector = get_metrics_collector()
                collector.record_metric(
                    f"function_duration_ms",
                    duration_ms,
                    {
                        'function': metric_key,
                        'success': str(success)
                    }
                )

            return result
        return wrapper
    return decorator


def setup_request_monitoring(app):
    """Setup Flask request monitoring middleware."""

    @app.before_request
    def before_request():
        """Record request start time."""
        g.start_time = time.time()

    @app.after_request
    def after_request(response):
        """Record request metrics after completion."""
        if hasattr(g, 'start_time'):
            duration_ms = (time.time() - g.start_time) * 1000

            collector = get_metrics_collector()
            collector.record_request(
                method=request.method,
                endpoint=request.endpoint or 'unknown',
                status_code=response.status_code,
                duration_ms=duration_ms,
                user_agent=request.headers.get('User-Agent', ''),
                tesla_email=getattr(request, 'tesla_email', '') or '',
                request_size=len(request.get_data()),
                response_size=response.content_length or 0
            )

        return response

    return app