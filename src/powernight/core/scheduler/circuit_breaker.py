"""
Circuit Breaker Implementation

Provides circuit breaker functionality for Powerwall operations.
"""

from typing import Optional, Callable, Any
from dataclasses import dataclass
import time
import threading


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 3
    recovery_timeout: float = 60.0
    success_threshold: int = 2
    timeout: float = 30.0
    failure_rate_threshold: float = 0.6
    window_size: int = 50


class CircuitBreakerOpenException(Exception):
    """Exception raised when circuit breaker is open."""
    pass


class CircuitBreaker:
    """Simple circuit breaker implementation."""
    
    def __init__(self, name: str, config: CircuitBreakerConfig):
        self.name = name
        self.config = config
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.health_check: Optional[Callable] = None
        self._lock = threading.Lock()
    
    def set_health_check(self, health_check: Callable):
        """Set health check function."""
        self.health_check = health_check
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        with self._lock:
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.config.recovery_timeout:
                    self.state = "HALF_OPEN"
                    self.success_count = 0
                else:
                    raise CircuitBreakerOpenException(f"Circuit breaker {self.name} is OPEN")
            
            try:
                result = func(*args, **kwargs)
                self._on_success()
                return result
            except Exception as e:
                self._on_failure()
                raise e
    
    def _on_success(self):
        """Handle successful operation."""
        if self.state == "HALF_OPEN":
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = "CLOSED"
                self.failure_count = 0
        else:
            self.failure_count = max(0, self.failure_count - 1)
    
    def _on_failure(self):
        """Handle failed operation."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.config.failure_threshold:
            self.state = "OPEN"


# Global circuit breaker registry
_circuit_breakers = {}
_breaker_lock = threading.Lock()


def get_circuit_breaker(name: str, config: CircuitBreakerConfig) -> CircuitBreaker:
    """Get or create a circuit breaker instance."""
    with _breaker_lock:
        if name not in _circuit_breakers:
            _circuit_breakers[name] = CircuitBreaker(name, config)
        return _circuit_breakers[name]
