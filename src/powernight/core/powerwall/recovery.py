"""
PowerNight Error Recovery and Circuit Breaker

Advanced error recovery, circuit breaker pattern, and health monitoring.
"""

import logging
import time
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from .exceptions import (
    PowerwallError,
    PowerwallConnectionError,
    PowerwallAuthenticationError,
    PowerwallTimeoutError,
    PowerwallUnavailableError
)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class ErrorMetrics:
    """Error tracking metrics."""
    total_requests: int = 0
    failed_requests: int = 0
    consecutive_failures: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate as percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.failed_requests / self.total_requests) * 100

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        return 100.0 - self.failure_rate


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5           # Failures before opening circuit
    recovery_timeout: float = 60.0       # Seconds before trying half-open
    success_threshold: int = 3           # Successes needed to close circuit
    request_timeout: float = 30.0        # Individual request timeout
    failure_rate_threshold: float = 50.0 # Failure rate % to open circuit


class CircuitBreaker:
    """
    Circuit breaker pattern implementation for Powerwall operations.

    Prevents cascading failures by monitoring error rates and temporarily
    stopping requests to failing services.
    """

    def __init__(self, config: Optional[CircuitBreakerConfig] = None) -> None:
        """Initialize circuit breaker."""
        self.config = config or CircuitBreakerConfig()
        self.logger = logging.getLogger(__name__)

        self.state = CircuitState.CLOSED
        self.metrics = ErrorMetrics()
        self._state_changed_at = time.time()
        self._half_open_successes = 0

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            PowerwallUnavailableError: If circuit is open
            Original exception: If function fails
        """
        # Check if circuit is open
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._transition_to_half_open()
            else:
                raise PowerwallUnavailableError(
                    "circuit_breaker",
                    f"Circuit breaker is OPEN (failure rate: {self.metrics.failure_rate:.1f}%)"
                )

        # Check if we're in half-open and have enough attempts
        if (self.state == CircuitState.HALF_OPEN and
            self._half_open_successes >= self.config.success_threshold):
            self._transition_to_closed()

        # Execute the function
        start_time = time.time()
        self.metrics.total_requests += 1

        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result

        except Exception as e:
            self._record_failure(e)
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        return time.time() - self._state_changed_at >= self.config.recovery_timeout

    def _transition_to_half_open(self) -> None:
        """Transition to half-open state."""
        self.state = CircuitState.HALF_OPEN
        self._state_changed_at = time.time()
        self._half_open_successes = 0
        self.logger.info("Circuit breaker transitioning to HALF_OPEN")

    def _transition_to_closed(self) -> None:
        """Transition to closed state."""
        self.state = CircuitState.CLOSED
        self._state_changed_at = time.time()
        self.metrics.consecutive_failures = 0
        self.logger.info("Circuit breaker transitioning to CLOSED")

    def _transition_to_open(self) -> None:
        """Transition to open state."""
        self.state = CircuitState.OPEN
        self._state_changed_at = time.time()
        self.logger.warning(
            f"Circuit breaker transitioning to OPEN "
            f"(consecutive failures: {self.metrics.consecutive_failures}, "
            f"failure rate: {self.metrics.failure_rate:.1f}%)"
        )

    def _record_success(self) -> None:
        """Record a successful operation."""
        self.metrics.consecutive_failures = 0
        self.metrics.last_success_time = datetime.now()

        if self.state == CircuitState.HALF_OPEN:
            self._half_open_successes += 1

    def _record_failure(self, exception: Exception) -> None:
        """Record a failed operation."""
        self.metrics.failed_requests += 1
        self.metrics.consecutive_failures += 1
        self.metrics.last_failure_time = datetime.now()

        self.logger.warning(f"Circuit breaker recorded failure: {exception}")

        # Check if we should open the circuit
        should_open = (
            self.metrics.consecutive_failures >= self.config.failure_threshold or
            self.metrics.failure_rate >= self.config.failure_rate_threshold
        )

        if should_open and self.state != CircuitState.OPEN:
            self._transition_to_open()

    def get_status(self) -> Dict[str, Any]:
        """Get circuit breaker status information."""
        return {
            'state': self.state.value,
            'metrics': {
                'total_requests': self.metrics.total_requests,
                'failed_requests': self.metrics.failed_requests,
                'consecutive_failures': self.metrics.consecutive_failures,
                'failure_rate': round(self.metrics.failure_rate, 2),
                'success_rate': round(self.metrics.success_rate, 2),
                'last_failure_time': self.metrics.last_failure_time.isoformat() if self.metrics.last_failure_time else None,
                'last_success_time': self.metrics.last_success_time.isoformat() if self.metrics.last_success_time else None
            },
            'config': {
                'failure_threshold': self.config.failure_threshold,
                'recovery_timeout': self.config.recovery_timeout,
                'success_threshold': self.config.success_threshold,
                'failure_rate_threshold': self.config.failure_rate_threshold
            },
            'state_changed_at': datetime.fromtimestamp(self._state_changed_at).isoformat(),
            'half_open_successes': self._half_open_successes
        }

    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        self.state = CircuitState.CLOSED
        self.metrics = ErrorMetrics()
        self._state_changed_at = time.time()
        self._half_open_successes = 0
        self.logger.info("Circuit breaker manually reset")


class HealthMonitor:
    """Monitor Powerwall connection health and perform recovery actions."""

    def __init__(self, check_interval: float = 60.0) -> None:
        """
        Initialize health monitor.

        Args:
            check_interval: Seconds between health checks
        """
        self.check_interval = check_interval
        self.logger = logging.getLogger(__name__)
        self._last_check = 0.0
        self._health_history: List[Dict[str, Any]] = []
        self._max_history = 100

    def check_health(self, connector) -> Dict[str, Any]:
        """
        Perform health check on Powerwall connector.

        Args:
            connector: PowerwallConnector instance

        Returns:
            Health check results
        """
        start_time = time.time()
        health_info = {
            'timestamp': datetime.now(),
            'check_duration': 0.0,
            'connection_status': 'unknown',
            'api_status': 'unknown',
            'data_freshness': 'unknown',
            'overall_health': 'unknown',
            'issues': []
        }

        try:
            # Test basic connection
            if connector.is_connected():
                health_info['connection_status'] = 'connected'
            else:
                health_info['connection_status'] = 'disconnected'
                health_info['issues'].append('Not connected to Powerwall')

            # Test API functionality
            try:
                connector.test_connection()
                health_info['api_status'] = 'responsive'
            except Exception as e:
                health_info['api_status'] = 'error'
                health_info['issues'].append(f'API test failed: {e}')

            # Check data freshness (cache age)
            try:
                cache_stats = connector.get_cache_stats()
                if cache_stats['valid_entries'] > 0:
                    health_info['data_freshness'] = 'fresh'
                else:
                    health_info['data_freshness'] = 'stale'
                    health_info['issues'].append('No fresh cached data')
            except Exception as e:
                health_info['data_freshness'] = 'error'
                health_info['issues'].append(f'Cache check failed: {e}')

            # Determine overall health
            if not health_info['issues']:
                health_info['overall_health'] = 'healthy'
            elif health_info['connection_status'] == 'connected':
                health_info['overall_health'] = 'degraded'
            else:
                health_info['overall_health'] = 'unhealthy'

        except Exception as e:
            health_info['overall_health'] = 'error'
            health_info['issues'].append(f'Health check failed: {e}')
            self.logger.error(f"Health check error: {e}")

        finally:
            health_info['check_duration'] = time.time() - start_time
            self._last_check = time.time()

        # Add to history
        self._health_history.append(health_info)
        if len(self._health_history) > self._max_history:
            self._health_history = self._health_history[-self._max_history:]

        return health_info

    def should_check(self) -> bool:
        """Check if it's time for a health check."""
        return time.time() - self._last_check >= self.check_interval

    def get_health_summary(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get health summary for the last N hours.

        Args:
            hours: Number of hours to analyze

        Returns:
            Health summary statistics
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_checks = [
            check for check in self._health_history
            if check['timestamp'] >= cutoff_time
        ]

        if not recent_checks:
            return {
                'total_checks': 0,
                'healthy_checks': 0,
                'degraded_checks': 0,
                'unhealthy_checks': 0,
                'health_percentage': 0.0,
                'average_response_time': 0.0,
                'common_issues': []
            }

        healthy = sum(1 for check in recent_checks if check['overall_health'] == 'healthy')
        degraded = sum(1 for check in recent_checks if check['overall_health'] == 'degraded')
        unhealthy = sum(1 for check in recent_checks if check['overall_health'] in ['unhealthy', 'error'])

        # Collect all issues
        all_issues = []
        for check in recent_checks:
            all_issues.extend(check['issues'])

        # Find most common issues
        issue_counts = {}
        for issue in all_issues:
            issue_counts[issue] = issue_counts.get(issue, 0) + 1

        common_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        # Calculate average response time
        response_times = [check['check_duration'] for check in recent_checks]
        avg_response_time = sum(response_times) / len(response_times)

        return {
            'total_checks': len(recent_checks),
            'healthy_checks': healthy,
            'degraded_checks': degraded,
            'unhealthy_checks': unhealthy,
            'health_percentage': (healthy / len(recent_checks)) * 100,
            'average_response_time': round(avg_response_time, 3),
            'common_issues': [{'issue': issue, 'count': count} for issue, count in common_issues]
        }


class ErrorRecoveryManager:
    """Manages automatic error recovery strategies."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self._recovery_attempts = {}

    def attempt_recovery(self, connector, error: Exception) -> bool:
        """
        Attempt to recover from an error.

        Args:
            connector: PowerwallConnector instance
            error: The error that occurred

        Returns:
            True if recovery was attempted
        """
        error_type = type(error).__name__

        # Track recovery attempts
        if error_type not in self._recovery_attempts:
            self._recovery_attempts[error_type] = {'count': 0, 'last_attempt': None}

        self._recovery_attempts[error_type]['count'] += 1
        self._recovery_attempts[error_type]['last_attempt'] = datetime.now()

        self.logger.info(f"Attempting recovery for {error_type}: {error}")

        try:
            if isinstance(error, PowerwallConnectionError):
                return self._recover_connection_error(connector, error)
            elif isinstance(error, PowerwallAuthenticationError):
                return self._recover_auth_error(connector, error)
            elif isinstance(error, PowerwallTimeoutError):
                return self._recover_timeout_error(connector, error)
            elif isinstance(error, PowerwallUnavailableError):
                return self._recover_unavailable_error(connector, error)
            else:
                return self._recover_generic_error(connector, error)

        except Exception as recovery_error:
            self.logger.error(f"Recovery attempt failed: {recovery_error}")
            return False

    def _recover_connection_error(self, connector, error: PowerwallConnectionError) -> bool:
        """Recover from connection errors."""
        self.logger.info("Attempting connection recovery")

        # Clear cache and disconnect
        connector.clear_cache()
        connector.disconnect()

        # Wait a moment and retry connection
        time.sleep(2)

        try:
            connector.connect()
            self.logger.info("Connection recovery successful")
            return True
        except Exception:
            self.logger.warning("Connection recovery failed")
            return False

    def _recover_auth_error(self, connector, error: PowerwallAuthenticationError) -> bool:
        """Recover from authentication errors."""
        self.logger.info("Attempting authentication recovery")

        # Disconnect and clear any cached auth state
        connector.disconnect()
        connector.clear_cache()

        # Authentication errors usually require manual intervention
        self.logger.warning("Authentication error requires manual intervention")
        return False

    def _recover_timeout_error(self, connector, error: PowerwallTimeoutError) -> bool:
        """Recover from timeout errors."""
        self.logger.info("Attempting timeout recovery")

        # Clear cache to ensure fresh requests
        connector.clear_cache()

        # Timeouts often resolve themselves
        time.sleep(1)
        return True

    def _recover_unavailable_error(self, connector, error: PowerwallUnavailableError) -> bool:
        """Recover from unavailable errors."""
        self.logger.info("Attempting unavailable recovery")

        # Clear state and wait
        connector.clear_cache()
        connector.disconnect()
        time.sleep(5)

        return True

    def _recover_generic_error(self, connector, error: Exception) -> bool:
        """Recover from generic errors."""
        self.logger.info(f"Attempting generic recovery for {type(error).__name__}")

        # Basic recovery: clear cache
        connector.clear_cache()
        time.sleep(1)

        return True

    def get_recovery_stats(self) -> Dict[str, Any]:
        """Get recovery attempt statistics."""
        return {
            'recovery_attempts': dict(self._recovery_attempts),
            'total_attempts': sum(stats['count'] for stats in self._recovery_attempts.values()),
            'error_types': list(self._recovery_attempts.keys())
        }