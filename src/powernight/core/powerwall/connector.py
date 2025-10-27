"""
PowerNight Powerwall Connector

Tesla Powerwall connection and communication management.
"""

import time
import json
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from dataclasses import dataclass
from abc import ABC, abstractmethod
from datetime import datetime

import pypowerwall
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    RetryError
)

from ...utils.logging import get_logger

from .exceptions import (
    PowerwallConnectionError,
    PowerwallAuthenticationError,
    PowerwallTimeoutError,
    PowerwallAPIError,
    PowerwallUnavailableError,
    PowerwallValidationError,
    PowerwallRateLimitError
)
from .data import PowerwallDataParser, PowerwallDataCache, PowerwallSystemInfo
from .reserve import (
    ReserveValidator,
    ReserveHistory,
    ReserveChangeRequest,
    ReserveChangeResult
)

# Use TYPE_CHECKING to avoid circular import with scheduler module
if TYPE_CHECKING:
    from ..scheduler.circuit_breaker import (
        CircuitBreaker,
        CircuitBreakerConfig,
        CircuitBreakerOpenException
    )
    from ..scheduler.degradation import (
        ServiceDegradationManager,
        DegradationConfig,
        ServiceState,
        DegradationLevel
    )
from .recovery import (
    HealthMonitor,
    ErrorRecoveryManager
)


@dataclass
class PowerwallStatus:
    """Powerwall status information."""
    backup_reserve_percentage: float
    battery_level: float
    is_charging: bool
    is_grid_connected: bool
    last_updated: float

    def __post_init__(self):
        self.last_updated = time.time()


@dataclass
class ConnectionConfig:
    """Powerwall connection configuration."""
    host: str
    password: str
    timeout: float = 30.0
    retry_attempts: int = 3
    retry_delay: float = 1.0
    max_retry_delay: float = 60.0
    rate_limit_delay: float = 1.0


class PowerwallConnectorInterface(ABC):
    """Abstract interface for Powerwall connectors."""

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to Powerwall."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from Powerwall."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if connected to Powerwall."""
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """Test connection to Powerwall."""
        pass

    @abstractmethod
    def get_backup_reserve_percentage(self) -> float:
        """Get current backup reserve percentage."""
        pass

    @abstractmethod
    def set_backup_reserve_percentage(self, percentage: float) -> bool:
        """Set backup reserve percentage."""
        pass

    @abstractmethod
    def get_status(self) -> PowerwallStatus:
        """Get comprehensive Powerwall status."""
        pass


class PowerwallConnector(PowerwallConnectorInterface):
    """
    Tesla Powerwall connector using pypowerwall library in cloud mode.

    Provides reliable connection management, error handling, and retry logic
    for communicating with Tesla Powerwall devices exclusively through pypowerwall cloud mode.
    """

    def __init__(self, email: str, powerwall_id: Optional[str] = None, **kwargs) -> None:
        """
        Initialize Powerwall connector for cloud mode.

        Args:
            email: Tesla account email
            powerwall_id: Specific Powerwall ID to connect to (optional)
            **kwargs: Additional configuration options
        """
        from .cloud_connector import CloudConnectionConfig
        from ..auth.tesla_oauth import TeslaOAuthManager
        
        self.config = CloudConnectionConfig(email=email, powerwall_id=powerwall_id, **kwargs)
        self.logger = get_logger()
        # Use persistent data path from environment, fallback to data/tokens
        import os
        storage_path = os.environ.get('POWERNIGHT_DATA_PATH', 'data')
        self._oauth_manager = TeslaOAuthManager(storage_path=storage_path)
        self._powerwall: Optional[pypowerwall.Powerwall] = None
        self._connected = False
        self._last_status: Optional[PowerwallStatus] = None
        self._last_rate_limit = 0.0

        # Initialize data parser and cache
        self._data_parser = PowerwallDataParser()
        self._data_cache = PowerwallDataCache(ttl_seconds=kwargs.get('cache_ttl', 30.0))

        # Initialize reserve management
        self._reserve_validator = ReserveValidator()
        self._reserve_history = ReserveHistory(max_entries=kwargs.get('history_size', 1000))

        # Initialize circuit breaker with Powerwall-specific configuration
        # Late import to avoid circular dependency
        from ..scheduler.circuit_breaker import CircuitBreakerConfig, get_circuit_breaker

        circuit_config = CircuitBreakerConfig(
            failure_threshold=kwargs.get('failure_threshold', 3),
            recovery_timeout=kwargs.get('recovery_timeout', 60.0),
            success_threshold=kwargs.get('success_threshold', 2),
            timeout=kwargs.get('circuit_timeout', 30.0),
            failure_rate_threshold=kwargs.get('failure_rate_threshold', 0.6),
            window_size=kwargs.get('circuit_window_size', 50)
        )
        self._circuit_breaker = get_circuit_breaker(f"cloud_powerwall_{email}", circuit_config)

        # Set up health check function for the circuit breaker
        def health_check():
            """Simple health check for circuit breaker recovery."""
            try:
                # Try a simple vitals call
                if self._powerwall:
                    vitals = self._powerwall.vitals()
                    return vitals is not None
                return False
            except:
                return False

        self._circuit_breaker.set_health_check(health_check)

        # Initialize graceful degradation manager
        # Late import to avoid circular dependency
        from ..scheduler.degradation import get_degradation_manager, POWERWALL_DEGRADATION_CONFIG

        degradation_config = POWERWALL_DEGRADATION_CONFIG
        if 'degradation_config' in kwargs:
            degradation_config = kwargs['degradation_config']

        self._degradation_manager = get_degradation_manager(
            f"powerwall_{self.config.host}",
            degradation_config
        )

        # Set up degradation state change callback
        from ..scheduler.degradation import ServiceState

        def on_degradation_state_change(old_state: "ServiceState", new_state: "ServiceState"):
            self.logger.log_powerwall_operation(
                "degradation_state_change", True,
                metadata={
                    'host': self.config.host,
                    'old_state': old_state.value,
                    'new_state': new_state.value
                }
            )

        self._degradation_manager.add_state_change_callback(on_degradation_state_change)

        # Initialize health monitoring and recovery
        self._health_monitor = HealthMonitor(check_interval=kwargs.get('health_check_interval', 60.0))
        self._recovery_manager = ErrorRecoveryManager()

        # Validate configuration
        self._validate_config()

    def _sanitize_api_response(self, response: Any, max_size_bytes: int = 10485760) -> Dict[str, Any]:
        """
        Sanitize API response by removing sensitive data and limiting size.
        
        Args:
            response: The API response to sanitize
            max_size_bytes: Maximum size in bytes for the response
            
        Returns:
            Sanitized response as dictionary
        """
        def sanitize_value(key: str, value: Any) -> Any:
            """Sanitize individual values based on key name."""
            sensitive_keys = ['token', 'password', 'email', 'secret', 'key', 'auth', 'credential']
            key_lower = key.lower()
            
            if any(sensitive in key_lower for sensitive in sensitive_keys):
                if isinstance(value, str):
                    if '@' in value and 'email' in key_lower:  # Email address
                        parts = value.split('@')
                        if len(parts) == 2:
                            return f"{parts[0][:1]}***@{parts[1]}"
                    return "***REDACTED***"
                elif isinstance(value, (dict, list)):
                    return "***REDACTED***"
            return value

        def sanitize_recursive(obj: Any, path: str = "") -> Any:
            """Recursively sanitize nested objects."""
            if isinstance(obj, dict):
                sanitized = {}
                for k, v in obj.items():
                    current_path = f"{path}.{k}" if path else k
                    sanitized[k] = sanitize_recursive(sanitize_value(k, v), current_path)
                return sanitized
            elif isinstance(obj, list):
                return [sanitize_recursive(item, f"{path}[{i}]") for i, item in enumerate(obj)]
            elif hasattr(obj, 'isoformat'):  # Handle datetime objects
                return obj.isoformat()
            elif hasattr(obj, '__dict__'):  # Handle other objects with __dict__
                return str(obj)
            else:
                return obj

        try:
            # Convert response to dict if it's not already
            if hasattr(response, '__dict__'):
                response_dict = response.__dict__
            elif isinstance(response, (str, int, float, bool)):
                response_dict = {"value": response}
            else:
                response_dict = response

            # Sanitize the response
            sanitized = sanitize_recursive(response_dict)
            
            # Check size limit
            response_str = json.dumps(sanitized, default=str)
            if len(response_str.encode('utf-8')) > max_size_bytes:
                return {
                    "error": "Response too large",
                    "size_bytes": len(response_str.encode('utf-8')),
                    "max_size_bytes": max_size_bytes,
                    "truncated": True
                }
            
            return sanitized
            
        except Exception as e:
            return {
                "error": f"Failed to sanitize response: {str(e)}",
                "original_type": str(type(response))
            }

    def _log_api_response(self, operation: str, response: Any, success: bool = True, 
                         error_details: Optional[str] = None, **kwargs) -> None:
        """
        Log API response with full response data.
        
        Args:
            operation: Name of the operation
            response: The API response to log
            success: Whether the operation was successful
            error_details: Error details if operation failed
            **kwargs: Additional metadata
        """
        try:
            # Sanitize the response
            sanitized_response = self._sanitize_api_response(response)
            response_size = len(json.dumps(sanitized_response, default=str).encode('utf-8'))
            
            # Prepare metadata with full response
            metadata = {
                'operation': operation,
                'api_response': sanitized_response,
                'response_size_bytes': response_size,
                'host': self.config.host,
                **kwargs
            }
            
            # Log the operation with full response
            self.logger.log_powerwall_operation(
                operation=operation,
                success=success,
                error_details=error_details,
                metadata=metadata
            )
            
        except Exception as e:
            # Fallback to basic logging if response logging fails
            self.logger.log_powerwall_operation(
                operation=f"{operation}_response_log_failed",
                success=False,
                error_details=f"Failed to log response: {str(e)}",
                metadata={'host': self.config.host, **kwargs}
            )

    def _validate_config(self) -> None:
        """Validate connection configuration."""
        if not self.config.host:
            raise PowerwallValidationError("host", self.config.host, "Host cannot be empty")

        # For cloud mode, password is not required (uses OAuth)
        if self.config.host != "cloud" and not self.config.password:
            raise PowerwallValidationError("password", "", "Password cannot be empty")

        if self.config.timeout <= 0:
            raise PowerwallValidationError("timeout", self.config.timeout, "Timeout must be positive")

    def _validate_percentage(self, percentage: float) -> None:
        """Validate backup reserve percentage value."""
        if not isinstance(percentage, (int, float)):
            raise PowerwallValidationError("percentage", percentage, "Must be a number")

        if not 0 <= percentage <= 100:
            raise PowerwallValidationError("percentage", percentage, "Must be between 0 and 100")

    def _handle_rate_limit(self) -> None:
        """Handle API rate limiting."""
        current_time = time.time()
        time_since_last = current_time - self._last_rate_limit

        if time_since_last < self.config.rate_limit_delay:
            sleep_time = self.config.rate_limit_delay - time_since_last
            self.logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f}s")
            time.sleep(sleep_time)

        self._last_rate_limit = time.time()

    def connect(self) -> bool:
        """
        Establish connection to Powerwall via cloud with circuit breaker protection.

        Returns:
            True if connection successful, False otherwise

        Raises:
            PowerwallConnectionError: If unable to connect
            PowerwallAuthenticationError: If authentication fails
            CircuitBreakerOpenException: If circuit breaker is open
        """
        # Late import to avoid circular dependency
        from ..scheduler.circuit_breaker import CircuitBreakerOpenException
        def _connect_operation():
            start_time = time.time()

            self.logger.log_powerwall_operation(
                "cloud_connect_attempt", True,
                metadata={'email': self.config.email, 'powerwall_id': self.config.powerwall_id}
            )

            # Handle rate limiting
            self._handle_rate_limit()

            # Get valid access token
            access_token = self._oauth_manager.get_valid_access_token()
            if not access_token:
                raise PowerwallAuthenticationError("No valid access token available")

            # Initialize pypowerwall cloud connection
            self._powerwall = pypowerwall.Powerwall(
                email=self.config.email,
                cloudmode=True,
                authmode="token",
                authpath=str(self._oauth_manager.auth_storage.storage_path) + "/",
                timeout=self.config.timeout
            )

            # Test connection by getting basic info
            vitals = self._powerwall.vitals()
            if not vitals:
                raise PowerwallConnectionError("No response from Powerwall via cloud")

            self._connected = True
            duration_ms = (time.time() - start_time) * 1000

            # Log full vitals response
            self._log_api_response(
                "cloud_connect_success",
                vitals,
                success=True,
                duration_ms=duration_ms,
                email=self.config.email,
                powerwall_id=self.config.powerwall_id
            )
            return True

        try:
            # Execute connection through circuit breaker
            return self._circuit_breaker.call(_connect_operation)

        except Exception as circuit_error:
            # Late import to avoid circular dependency
            from ..scheduler.circuit_breaker import CircuitBreakerOpenException

            if isinstance(circuit_error, CircuitBreakerOpenException):
                self._connected = False
                self.logger.log_powerwall_operation(
                    "connect_circuit_open", False,
                    metadata={'host': self.config.host}
                )
                raise circuit_error
            else:
                raise circuit_error

        except pypowerwall.PyPowerwallError as e:
            self._connected = False

            if "authentication" in str(e).lower():
                self.logger.log_powerwall_operation(
                    "connect_auth_failed", False,
                    error_details=str(e),
                    metadata={'host': self.config.host}
                )
                raise PowerwallAuthenticationError(f"Authentication failed: {e}")
            else:
                self.logger.log_powerwall_operation(
                    "connect_failed", False,
                    error_details=str(e),
                    metadata={'host': self.config.host}
                )
                raise PowerwallConnectionError(self.config.host, f"Connection failed: {e}")

        except Exception as e:
            self._connected = False
            raise PowerwallConnectionError(self.config.host, f"Unexpected error: {e}")

    def disconnect(self) -> None:
        """Disconnect from Powerwall."""
        if self._powerwall:
            self.logger.info("Disconnecting from Powerwall")
            self._powerwall = None
            self._connected = False

    def is_connected(self) -> bool:
        """Check if connected to Powerwall."""
        # Can't test connection without powerwall object
        if not self._powerwall:
            self._connected = False
            return False

        try:
            # Always test connection with a simple API call (don't trust cached state)
            # This allows automatic recovery from transient failures
            self._handle_rate_limit()
            vitals = self._powerwall.vitals()
            if vitals is not None:
                self._connected = True  # Update state on success
                return True
            else:
                self._connected = False
                return False
        except Exception:
            self._connected = False
            return False

    def test_connection(self) -> bool:
        """
        Test connection to Powerwall.

        Returns:
            True if connection test successful

        Raises:
            PowerwallUnavailableError: If Powerwall is unavailable
        """
        if not self.is_connected():
            try:
                self.connect()
            except Exception as e:
                raise PowerwallUnavailableError(self.config.host, f"Connection test failed: {e}")

        try:
            # Test with a simple API call
            self._handle_rate_limit()
            vitals = self._powerwall.vitals()
            return vitals is not None

        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            raise PowerwallUnavailableError(self.config.host, f"Connection test failed: {e}")

    def get_backup_reserve_percentage(self) -> float:
        """
        Get current backup reserve percentage with graceful degradation.

        Returns:
            Current backup reserve percentage (0-100)

        Raises:
            PowerwallAPIError: If API call fails
            PowerwallUnavailableError: If Powerwall is unavailable and no fallback data
        """
        cache_key = "backup_reserve_percentage"

        def _primary_operation():
            """Primary operation to get backup reserve."""
            if not self.is_connected():
                self.connect()

            self._handle_rate_limit()

            # Get backup reserve from Powerwall through circuit breaker
            def _get_reserve_api_call():
                reserve = self._powerwall.get_reserve()
                percentage = self._data_parser.parse_reserve_percentage(reserve)
                self.logger.debug(f"Retrieved backup reserve: {percentage}%")
                
                # Log full reserve response
                self._log_api_response(
                    "get_backup_reserve_percentage",
                    reserve,
                    success=True,
                    percentage=percentage
                )
                
                return percentage

            return self._circuit_breaker.call(_get_reserve_api_call)

        def _fallback_operation():
            """Fallback operation using cached data or emergency values."""
            # Try degradation manager cache first
            cached_data = self._degradation_manager.get_cached_data(cache_key)
            if cached_data is not None:
                self.logger.log_powerwall_operation(
                    "get_reserve_fallback_cache", True,
                    metadata={
                        'host': self.config.host,
                        'value': cached_data,
                        'source': 'degradation_cache'
                    }
                )
                return cached_data

            # Try local data cache
            local_cached = self._data_cache.get(cache_key)
            if local_cached is not None:
                self.logger.log_powerwall_operation(
                    "get_reserve_fallback_local", True,
                    metadata={
                        'host': self.config.host,
                        'value': local_cached,
                        'source': 'local_cache'
                    }
                )
                return local_cached

            # Use emergency fallback data
            emergency_data = self._degradation_manager.get_emergency_fallback_data('backup_reserve_percentage')
            if emergency_data:
                percentage = emergency_data['value']
                self.logger.log_powerwall_operation(
                    "get_reserve_emergency_fallback", True,
                    metadata={
                        'host': self.config.host,
                        'value': percentage,
                        'source': 'emergency_config'
                    }
                )
                return percentage

            raise PowerwallUnavailableError(
                self.config.host,
                "No backup reserve data available from any source"
            )

        try:
            # Execute with graceful degradation
            result = self._degradation_manager.execute_with_degradation(
                operation=_primary_operation,
                fallback=_fallback_operation,
                cache_key=cache_key
            )

            # Cache in local cache as well for faster access
            self._data_cache.set(cache_key, result)
            return result

        except Exception as circuit_error:
            # Late import to avoid circular dependency
            from ..scheduler.circuit_breaker import CircuitBreakerOpenException

            if isinstance(circuit_error, CircuitBreakerOpenException):
                self.logger.log_powerwall_operation(
                    "get_reserve_circuit_open", False,
                    metadata={'host': self.config.host}
                )
                # Try fallback even when circuit breaker is open
                return _fallback_operation()
            else:
                raise circuit_error

        except Exception as e:
            # Final fallback attempt
            try:
                return _fallback_operation()
            except:
                raise PowerwallUnavailableError(self.config.host, f"Failed to get backup reserve: {e}")

    def set_backup_reserve_percentage(self, percentage: float, reason: Optional[str] = None) -> ReserveChangeResult:
        """
        Set backup reserve percentage - Fast mode (matches pypowerwall CLI).

        Directly calls pypowerwall set_reserve() with minimal overhead.
        No pre-read, no verification, no delays.

        Args:
            percentage: Backup reserve percentage (0-100)
            reason: Optional reason for the change

        Returns:
            ReserveChangeResult with operation details

        Raises:
            PowerwallValidationError: If percentage is invalid
            PowerwallAPIError: If API call fails
            PowerwallUnavailableError: If Powerwall is unavailable
        """
        start_time = time.time()

        # Validate percentage
        self._reserve_validator.validate_percentage(percentage)

        # Ensure connected
        if not self.is_connected():
            self.connect()

        def _set_reserve_operation():
            self._handle_rate_limit()

            self.logger.log_powerwall_operation(
                "reserve_change_attempt", True,
                metadata={
                    'target_percentage': percentage,
                    'reason': reason
                }
            )

            # JUST SET - NO VERIFICATION
            api_result = self._powerwall.set_reserve(percentage)

            if not api_result:
                raise PowerwallAPIError("Failed to set backup reserve percentage")

            # Log full set_reserve response
            self._log_api_response(
                "set_backup_reserve_percentage",
                api_result,
                success=True,
                target_percentage=percentage,
                reason=reason
            )

            # Create success result
            result = ReserveChangeResult(
                success=True,
                target_percentage=percentage,
                actual_percentage=percentage,  # Trust pypowerwall result
                duration_seconds=time.time() - start_time
            )

            # Add to history
            self._reserve_history.add_result(result)

            return result

        try:
            # Execute through circuit breaker
            return self._circuit_breaker.call(_set_reserve_operation)

        except Exception as circuit_error:
            # Late import to avoid circular dependency
            from ..scheduler.circuit_breaker import CircuitBreakerOpenException

            if isinstance(circuit_error, CircuitBreakerOpenException):
                error_result = ReserveChangeResult(
                    success=False,
                    target_percentage=percentage,
                    error_message="Circuit breaker is open - API temporarily unavailable",
                    duration_seconds=time.time() - start_time
                )
                self._reserve_history.add_result(error_result)
                self.logger.log_powerwall_operation(
                    "reserve_change_circuit_open", False,
                    duration_ms=(time.time() - start_time) * 1000,
                    metadata={'target_percentage': percentage}
                )
                raise circuit_error
            else:
                raise circuit_error

        except pypowerwall.PyPowerwallError as e:
            error_result = ReserveChangeResult(
                success=False,
                target_percentage=percentage,
                error_message=f"API error: {e}",
                duration_seconds=time.time() - start_time
            )
            self._reserve_history.add_result(error_result)
            raise PowerwallAPIError(f"API error setting backup reserve: {e}")

        except Exception as e:
            error_result = ReserveChangeResult(
                success=False,
                target_percentage=percentage,
                error_message=f"Unexpected error: {e}",
                duration_seconds=time.time() - start_time
            )
            self._reserve_history.add_result(error_result)
            raise PowerwallUnavailableError(self.config.host, f"Failed to set backup reserve: {e}")

    def get_status(self) -> PowerwallStatus:
        """
        Get comprehensive Powerwall status with graceful degradation.

        Returns:
            PowerwallStatus object with current status

        Raises:
            PowerwallAPIError: If API call fails
            PowerwallUnavailableError: If Powerwall is unavailable and no fallback data
        """
        cache_key = "powerwall_status"

        def _primary_operation():
            """Primary operation to get Powerwall status."""
            if not self.is_connected():
                self.connect()

            self._handle_rate_limit()

            # Get comprehensive status from Powerwall through circuit breaker
            def _get_status_api_call():
                vitals = self._powerwall.vitals()
                if not vitals:
                    raise PowerwallAPIError("Failed to retrieve Powerwall status")

                backup_reserve = self.get_backup_reserve_percentage()

                # Extract relevant information
                battery_level = float(vitals.get('battery', {}).get('percentage', 0))
                is_charging = vitals.get('battery', {}).get('charging', False)
                is_grid_connected = vitals.get('grid', {}).get('connected', False)

                status = PowerwallStatus(
                    backup_reserve_percentage=backup_reserve,
                    battery_level=battery_level,
                    is_charging=is_charging,
                    is_grid_connected=is_grid_connected,
                    last_updated=time.time()
                )

                # Log full vitals response
                self._log_api_response(
                    "get_status",
                    vitals,
                    success=True,
                    battery_level=battery_level,
                    is_charging=is_charging,
                    is_grid_connected=is_grid_connected,
                    backup_reserve=backup_reserve
                )

                self.logger.debug("Retrieved comprehensive Powerwall status")
                return status

            return self._circuit_breaker.call(_get_status_api_call)

        def _fallback_operation():
            """Fallback operation using cached status or emergency values."""
            # Try degradation manager cache first
            cached_status = self._degradation_manager.get_cached_data(cache_key)
            if cached_status is not None:
                # Update last_updated timestamp to indicate cached data
                cached_status.last_updated = time.time()
                self.logger.log_powerwall_operation(
                    "get_status_fallback_cache", True,
                    metadata={
                        'host': self.config.host,
                        'source': 'degradation_cache',
                        'backup_reserve': cached_status.backup_reserve_percentage
                    }
                )
                return cached_status

            # Try to use last known status
            if self._last_status:
                # Age the status but return it as fallback
                self._last_status.last_updated = time.time()
                self.logger.log_powerwall_operation(
                    "get_status_fallback_last", True,
                    metadata={
                        'host': self.config.host,
                        'source': 'last_status',
                        'backup_reserve': self._last_status.backup_reserve_percentage
                    }
                )
                return self._last_status

            # Use emergency fallback data
            emergency_data = self._degradation_manager.get_emergency_fallback_data('powerwall_status')
            if emergency_data:
                status = PowerwallStatus(
                    backup_reserve_percentage=emergency_data['backup_reserve_percentage'],
                    battery_level=emergency_data['battery_level'],
                    is_charging=emergency_data['is_charging'],
                    is_grid_connected=emergency_data['is_grid_connected'],
                    last_updated=emergency_data['last_updated']
                )
                self.logger.log_powerwall_operation(
                    "get_status_emergency_fallback", True,
                    metadata={
                        'host': self.config.host,
                        'source': 'emergency_config',
                        'backup_reserve': status.backup_reserve_percentage
                    }
                )
                return status

            raise PowerwallUnavailableError(
                self.config.host,
                "No status data available from any source"
            )

        try:
            # Execute with graceful degradation
            result = self._degradation_manager.execute_with_degradation(
                operation=_primary_operation,
                fallback=_fallback_operation,
                cache_key=cache_key
            )

            # Update last known status
            self._last_status = result
            return result

        except Exception as circuit_error:
            # Late import to avoid circular dependency
            from ..scheduler.circuit_breaker import CircuitBreakerOpenException

            if isinstance(circuit_error, CircuitBreakerOpenException):
                self.logger.log_powerwall_operation(
                    "get_status_circuit_open", False,
                    metadata={'host': self.config.host}
                )
                # Try fallback even when circuit breaker is open
                return _fallback_operation()
            else:
                raise circuit_error

        except Exception as e:
            # Final fallback attempt
            try:
                return _fallback_operation()
            except:
                raise PowerwallUnavailableError(self.config.host, f"Failed to get status: {e}")

    def get_last_status(self) -> Optional[PowerwallStatus]:
        """Get the last cached status."""
        return self._last_status

    def get_system_info(self) -> PowerwallSystemInfo:
        """
        Get comprehensive system information with enhanced data parsing.

        Returns:
            PowerwallSystemInfo object with detailed system data

        Raises:
            PowerwallAPIError: If API call fails
            PowerwallUnavailableError: If Powerwall is unavailable
        """
        # Check cache first
        cache_key = "system_info"
        cached_info = self._data_cache.get(cache_key)
        if cached_info is not None:
            return cached_info

        if not self.is_connected():
            self.connect()

        try:
            self._handle_rate_limit()

            # Get vitals and reserve data
            vitals = self._powerwall.vitals()
            reserve_percentage = self.get_backup_reserve_percentage()

            if not vitals:
                raise PowerwallAPIError("Failed to retrieve Powerwall vitals")

            # Parse comprehensive system information
            system_info = self._data_parser.parse_system_info(vitals, reserve_percentage)

            # Cache the result
            self._data_cache.set(cache_key, system_info)

            self.logger.debug("Retrieved comprehensive system information")
            return system_info

        except pypowerwall.PyPowerwallError as e:
            raise PowerwallAPIError(f"API error getting system info: {e}")

        except Exception as e:
            raise PowerwallUnavailableError(self.config.host, f"Failed to get system info: {e}")

    def clear_cache(self) -> None:
        """Clear the data cache."""
        self._data_cache.clear()
        self.logger.debug("Data cache cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self._data_cache.get_stats()

    def get_reserve_history_stats(self) -> Dict[str, Any]:
        """Get backup reserve change history statistics."""
        return self._reserve_history.get_stats()

    def get_recent_reserve_changes(self, hours: int = 24) -> List[ReserveChangeResult]:
        """Get recent backup reserve changes."""
        return self._reserve_history.get_recent_changes(hours)

    def suggest_optimal_reserve(self, time_of_day: Optional[datetime] = None) -> float:
        """
        Suggest optimal backup reserve percentage for current conditions.

        Args:
            time_of_day: Time to suggest for (defaults to now)

        Returns:
            Suggested backup reserve percentage
        """
        if time_of_day is None:
            time_of_day = datetime.now()

        # Get current battery level if possible
        battery_level = None
        try:
            status = self.get_status()
            battery_level = status.battery_level
        except Exception:
            pass

        return self._reserve_validator.suggest_optimal_percentage(time_of_day, battery_level)

    def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status including circuit breaker and degradation state."""
        try:
            health_check = self._health_monitor.check_health(self)
        except:
            health_check = {'overall_health': 'unknown', 'timestamp': datetime.now()}

        circuit_metrics = self._circuit_breaker.get_metrics()
        degradation_status = self._degradation_manager.get_status()

        try:
            recovery_stats = self._recovery_manager.get_recovery_stats()
        except:
            recovery_stats = {}

        # Determine overall system health based on all components
        overall_health = 'healthy'
        if (circuit_metrics['current_state'] == 'open' or
            degradation_status['current_state'] in ['offline', 'degraded']):
            overall_health = 'degraded'
        elif degradation_status['current_state'] == 'recovery':
            overall_health = 'recovering'

        return {
            'overall_health': overall_health,
            'health_check': health_check,
            'circuit_breaker': {
                'state': circuit_metrics['current_state'],
                'failure_count': circuit_metrics['failure_count'],
                'success_count': circuit_metrics['success_count'],
                'total_calls': circuit_metrics['total_calls'],
                'failure_rate': circuit_metrics['overall_failure_rate'],
                'recent_failure_rate': circuit_metrics['recent_failure_rate'],
                'time_since_last_failure': circuit_metrics['time_since_last_failure']
            },
            'degradation': {
                'service_state': degradation_status['current_state'],
                'degradation_level': degradation_status['degradation_level'],
                'time_in_state_seconds': degradation_status['time_in_state_seconds'],
                'recovery_attempts': degradation_status['recovery_attempts'],
                'cache_stats': degradation_status['cache_stats']
            },
            'recovery_stats': recovery_stats,
            'last_health_check': health_check['timestamp'].isoformat() if 'timestamp' in health_check else datetime.now().isoformat(),
            'host': self.config.host,
            'connected': self.is_connected()
        }

    def get_health_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get health summary for the last N hours."""
        return self._health_monitor.get_health_summary(hours)

    def reset_circuit_breaker(self) -> None:
        """Manually reset the circuit breaker."""
        self._circuit_breaker.reset()
        self.logger.log_powerwall_operation(
            "circuit_breaker_reset", True,
            metadata={'host': self.config.host}
        )

    def force_health_check(self) -> Dict[str, Any]:
        """Force an immediate health check."""
        return self._health_monitor.check_health(self)

    def attempt_recovery(self) -> bool:
        """Attempt to recover from degraded service state."""
        recovery_attempted = self._degradation_manager.attempt_recovery()

        self.logger.log_powerwall_operation(
            "recovery_attempt", recovery_attempted,
            metadata={
                'host': self.config.host,
                'current_state': self._degradation_manager.current_state.value
            }
        )

        return recovery_attempted

    def get_degradation_status(self) -> Dict[str, Any]:
        """Get detailed degradation service status."""
        return self._degradation_manager.get_status()

    def clear_degradation_cache(self) -> None:
        """Clear degradation cache to force fresh data retrieval."""
        self._degradation_manager.clear_cache()
        self.logger.log_powerwall_operation(
            "degradation_cache_cleared", True,
            metadata={'host': self.config.host}
        )

    # PyPowerwall Command Wrappers for Task Planner

    def set_mode(self, mode: str) -> bool:
        """
        Set Powerwall operating mode.

        Args:
            mode: Operating mode (self_consumption, backup, or autonomous)

        Returns:
            True if successful

        Raises:
            PowerwallAPIError: If API call fails
        """
        if not self.is_connected():
            self.connect()

        self._handle_rate_limit()

        try:
            result = self._powerwall.set_mode(mode)
            
            # Log full set_mode response
            self._log_api_response(
                "set_mode",
                result,
                success=True,
                mode=mode
            )
            
            return result
        except Exception as e:
            # Log error response
            self._log_api_response(
                "set_mode",
                {"error": str(e)},
                success=False,
                error_details=str(e),
                mode=mode
            )
            raise PowerwallAPIError(f"Failed to set mode: {e}")

    def set_grid_charging(self, enabled: bool) -> bool:
        """
        Enable or disable grid charging.

        Args:
            enabled: True to enable grid charging, False to disable

        Returns:
            True if successful

        Raises:
            PowerwallAPIError: If API call fails
        """
        if not self.is_connected():
            self.connect()

        self._handle_rate_limit()

        try:
            result = self._powerwall.grid_charging(enabled)
            
            # Log full grid_charging response
            self._log_api_response(
                "set_grid_charging",
                result,
                success=True,
                enabled=enabled
            )
            
            return result
        except Exception as e:
            # Log error response
            self._log_api_response(
                "set_grid_charging",
                {"error": str(e)},
                success=False,
                error_details=str(e),
                enabled=enabled
            )
            raise PowerwallAPIError(f"Failed to set grid charging: {e}")

    def set_export_mode(self, mode: str) -> bool:
        """
        Set grid export mode.

        Args:
            mode: Export mode (battery_ok, pv_only, or never)

        Returns:
            True if successful

        Raises:
            PowerwallAPIError: If API call fails
        """
        if not self.is_connected():
            self.connect()

        self._handle_rate_limit()

        try:
            result = self._powerwall.set_grid_export(mode)
            
            # Log full set_grid_export response
            self._log_api_response(
                "set_export_mode",
                result,
                success=True,
                mode=mode
            )
            
            return result
        except Exception as e:
            # Log error response
            self._log_api_response(
                "set_export_mode",
                {"error": str(e)},
                success=False,
                error_details=str(e),
                mode=mode
            )
            raise PowerwallAPIError(f"Failed to set export mode: {e}")

    def get_state_of_charge(self) -> Optional[float]:
        """
        Get current battery state of charge.

        Returns:
            Battery level as percentage (0-100), or None if unavailable

        Raises:
            PowerwallAPIError: If API call fails
        """
        if not self.is_connected():
            self.connect()

        self._handle_rate_limit()

        try:
            level = self._powerwall.level()
            
            # Log full level response
            self._log_api_response(
                "get_state_of_charge",
                level,
                success=True,
                level=level
            )
            
            return level
        except Exception as e:
            # Log error response
            self._log_api_response(
                "get_state_of_charge",
                {"error": str(e)},
                success=False,
                error_details=str(e)
            )
            raise PowerwallAPIError(f"Failed to get state of charge: {e}")

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()

    def __repr__(self) -> str:
        """String representation."""
        return f"PowerwallConnector(host={self.config.host}, connected={self.is_connected()})"