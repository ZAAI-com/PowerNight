"""
Service Degradation Management

Provides graceful degradation functionality for Powerwall operations.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class ServiceState(Enum):
    """Service state enumeration."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass
class DegradationConfig:
    """Configuration for service degradation."""
    max_retries: int = 3
    retry_delay: float = 1.0
    degradation_threshold: int = 5
    recovery_threshold: int = 3


# Default degradation configuration for Powerwall
POWERWALL_DEGRADATION_CONFIG = DegradationConfig(
    max_retries=3,
    retry_delay=2.0,
    degradation_threshold=5,
    recovery_threshold=3
)


class DegradationManager:
    """Manages service degradation and recovery."""
    
    def __init__(self, name: str, config: DegradationConfig):
        self.name = name
        self.config = config
        self.state = ServiceState.HEALTHY
        self.failure_count = 0
        self.success_count = 0
        self._state_change_callbacks = []
    
    def add_state_change_callback(self, callback):
        """Add a callback for state change events."""
        self._state_change_callbacks.append(callback)
    
    def _notify_state_change(self, old_state: ServiceState, new_state: ServiceState):
        """Notify callbacks of state changes."""
        for callback in self._state_change_callbacks:
            try:
                callback(old_state, new_state)
            except Exception:
                pass  # Ignore callback errors
    
    def record_success(self):
        """Record a successful operation."""
        old_state = self.state
        self.success_count += 1
        if self.state == ServiceState.DEGRADED and self.success_count >= self.config.recovery_threshold:
            self.state = ServiceState.HEALTHY
            self.failure_count = 0
            self.success_count = 0
            self._notify_state_change(old_state, self.state)
    
    def record_failure(self):
        """Record a failed operation."""
        old_state = self.state
        self.failure_count += 1
        if self.failure_count >= self.config.degradation_threshold:
            self.state = ServiceState.DEGRADED
            self._notify_state_change(old_state, self.state)
        elif self.failure_count >= self.config.max_retries:
            self.state = ServiceState.FAILED
            self._notify_state_change(old_state, self.state)
    
    def should_retry(self) -> bool:
        """Check if operation should be retried."""
        return self.state != ServiceState.FAILED and self.failure_count < self.config.max_retries
    
    def get_retry_delay(self) -> float:
        """Get delay before retry."""
        return self.config.retry_delay
    
    def execute_with_degradation(self, operation=None, fallback=None, cache_key=None, **kwargs):
        """Execute a function with degradation management."""
        try:
            # Try primary operation first
            if operation:
                result = operation()
                self.record_success()
                return result
            else:
                raise ValueError("No operation provided")
        except Exception as e:
            self.record_failure()
            # Try fallback operation if available
            if fallback:
                try:
                    result = fallback()
                    self.record_success()
                    return result
                except Exception as fallback_error:
                    self.record_failure()
                    raise fallback_error
            else:
                raise e


# Global degradation manager registry
_degradation_managers = {}


def get_degradation_manager(name: str, config: Optional[DegradationConfig] = None) -> DegradationManager:
    """Get or create a degradation manager instance."""
    if name not in _degradation_managers:
        _degradation_managers[name] = DegradationManager(name, config or DegradationConfig())
    return _degradation_managers[name]
