"""
Cloud-based Powerwall connector using pypowerwall cloud mode.

Provides connection to Tesla Powerwalls exclusively through pypowerwall library.
"""

import time
from typing import Optional, Dict, Any, List
from abc import ABC, abstractmethod

import pypowerwall

from .connector import PowerwallStatus
from .data import PowerwallDataParser, PowerwallDataCache
from .reserve import ReserveValidator, ReserveHistory
from .exceptions import (
    PowerwallError,
    PowerwallConnectionError,
    PowerwallAuthenticationError,
    PowerwallTimeoutError,
)
from ...utils.logging import get_logger
from ..auth.tesla_oauth import TeslaOAuthManager


class CloudConnectionConfig:
    """Configuration for cloud-based Powerwall connection."""
    
    def __init__(self, email: str, powerwall_id: Optional[str] = None, **kwargs):
        """
        Initialize cloud connection configuration.
        
        Args:
            email: Tesla account email
            powerwall_id: Specific Powerwall ID to connect to (optional)
            **kwargs: Additional configuration options
        """
        self.email = email
        self.powerwall_id = powerwall_id
        self.host = "cloud"  # Cloud connection doesn't use a specific host
        self.password = None  # Cloud connection uses OAuth, not password
        self.timeout = kwargs.get('timeout', 30.0)
        self.retry_attempts = kwargs.get('retry_attempts', 3)
        self.rate_limit_delay = kwargs.get('rate_limit_delay', 1.0)
        self.cache_ttl = kwargs.get('cache_ttl', 30.0)
        self.history_size = kwargs.get('history_size', 1000)


class CloudPowerwallConnectorInterface(ABC):
    """Interface for cloud-based Powerwall connectors."""
    
    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to Powerwall via cloud."""
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
    def get_status(self) -> PowerwallStatus:
        """Get comprehensive Powerwall status."""
        pass
    
    @abstractmethod
    def get_powerwalls(self) -> List[Dict[str, Any]]:
        """Get list of available Powerwalls."""
        pass
    
    @abstractmethod
    def switch_powerwall(self, powerwall_id: str) -> bool:
        """Switch to a different Powerwall."""
        pass


class CloudPowerwallConnector(CloudPowerwallConnectorInterface):
    """
    Cloud-based Tesla Powerwall connector using pypowerwall library.
    
    Provides reliable connection management, error handling, and retry logic
    for communicating with Tesla Powerwall devices exclusively through pypowerwall cloud mode.
    """
    
    def __init__(self, config: CloudConnectionConfig, oauth_manager: Optional[TeslaOAuthManager] = None) -> None:
        """
        Initialize cloud Powerwall connector.
        
        Args:
            config: Cloud connection configuration
            oauth_manager: Tesla OAuth manager for authentication (optional, will create if not provided)
        """
        self.config = config
        self.oauth_manager = oauth_manager or TeslaOAuthManager()
        self.logger = get_logger()
        self._powerwall: Optional[pypowerwall.Powerwall] = None
        self._connected = False
        self._last_status: Optional[PowerwallStatus] = None
        self._current_powerwall_id: Optional[str] = None
        
        # Initialize data parser and cache
        self._data_parser = PowerwallDataParser()
        self._data_cache = PowerwallDataCache(ttl_seconds=config.cache_ttl)
        
        # Initialize reserve management
        self._reserve_validator = ReserveValidator()
        self._reserve_history = ReserveHistory(max_entries=config.history_size)
        
        # Initialize circuit breaker
        from ..scheduler.circuit_breaker import CircuitBreakerConfig, get_circuit_breaker
        
        circuit_config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=60.0,
            success_threshold=2,
            timeout=config.timeout,
            failure_rate_threshold=0.6,
            window_size=50
        )
        self._circuit_breaker = get_circuit_breaker(f"cloud_powerwall_{config.email}", circuit_config)
    
    def connect(self) -> bool:
        """
        Establish connection to Powerwall via cloud with circuit breaker protection.
        
        Returns:
            True if connection successful, False otherwise
            
        Raises:
            PowerwallConnectionError: If unable to connect
            PowerwallAuthenticationError: If authentication fails
        """
        def _connect_operation():
            start_time = time.time()
            
            self.logger.log_powerwall_operation(
                "cloud_connect_attempt", True,
                metadata={'email': self.config.email, 'powerwall_id': self.config.powerwall_id}
            )
            
            # Check if auth data exists
            if not self.oauth_manager.auth_storage.has_auth_data():
                raise PowerwallAuthenticationError("No authentication data found. Please complete Tesla OAuth setup first.")
            
            # Initialize pypowerwall cloud connection using stored auth data
            self._powerwall = pypowerwall.Powerwall(
                email=self.config.email,
                cloudmode=True,
                authmode="token",
                authpath=str(self.oauth_manager.auth_storage.storage_path) + "/",
                timeout=self.config.timeout
            )
            
            # Test connection by getting basic info
            try:
                vitals = self._powerwall.vitals()
                if not vitals:
                    raise PowerwallConnectionError("No response from Powerwall via cloud")
                
                self._connected = True
                self._current_powerwall_id = self.config.powerwall_id
                
                duration_ms = (time.time() - start_time) * 1000
                
                self.logger.log_powerwall_operation(
                    "cloud_connect_success", True,
                    duration_ms=duration_ms,
                    metadata={
                        'email': self.config.email,
                        'powerwall_id': self._current_powerwall_id,
                        'has_vitals': bool(vitals)
                    }
                )
                return True
                
            except Exception as e:
                raise PowerwallConnectionError(f"Cloud connection test failed: {e}")
        
        try:
            # Execute connection through circuit breaker
            return self._circuit_breaker.execute(_connect_operation)
            
        except Exception as e:
            self.logger.log_powerwall_operation(
                "cloud_connect_failure", False,
                metadata={'error': str(e), 'email': self.config.email}
            )
            raise
    
    def disconnect(self) -> None:
        """Disconnect from Powerwall."""
        try:
            if self._powerwall:
                # pypowerwall doesn't have explicit disconnect, just clear reference
                self._powerwall = None
            
            self._connected = False
            self._current_powerwall_id = None
            
            self.logger.log_powerwall_operation(
                "cloud_disconnect", True,
                metadata={'email': self.config.email}
            )
            
        except Exception as e:
            self.logger.error(f"Error during cloud disconnect: {e}")
    
    def is_connected(self) -> bool:
        """Check if connected to Powerwall via cloud."""
        # Can't test connection without powerwall object
        if not self._powerwall:
            self._connected = False
            return False

        try:
            # Always test connection with a simple API call (don't trust cached state)
            # This allows automatic recovery from transient failures
            self._powerwall.vitals()
            self._connected = True  # Update state on success
            return True
        except Exception:
            self._connected = False
            return False
    
    def get_status(self) -> PowerwallStatus:
        """
        Get comprehensive Powerwall status via cloud.
        
        Returns:
            PowerwallStatus object with current status
            
        Raises:
            PowerwallConnectionError: If not connected or API call fails
        """
        if not self.is_connected():
            raise PowerwallConnectionError("Not connected to Powerwall")
        
        def _get_status_operation():
            try:
                # Get vitals data
                vitals = self._powerwall.vitals()
                if not vitals:
                    raise PowerwallConnectionError("No vitals data received")
                
                # Get system status
                system_status = self._powerwall.status()
                
                # Get power data
                power_data = self._powerwall.power()
                
                # Parse and combine data
                status_data = {
                    'vitals': vitals,
                    'system_status': system_status,
                    'power_data': power_data,
                    'timestamp': time.time(),
                    'connection_type': 'cloud',
                    'powerwall_id': self._current_powerwall_id
                }
                
                # Parse using existing data parser
                powerwall_status = self._data_parser.parse_status(status_data)
                
                # Cache the result
                self._data_cache.cache_status(powerwall_status)
                self._last_status = powerwall_status
                
                return powerwall_status
                
            except Exception as e:
                self.logger.error(f"Failed to get Powerwall status: {e}")
                raise PowerwallConnectionError(f"Status retrieval failed: {e}")
        
        try:
            return self._circuit_breaker.execute(_get_status_operation)
        except Exception as e:
            self.logger.log_powerwall_operation(
                "get_status_failure", False,
                metadata={'error': str(e), 'email': self.config.email}
            )
            raise
    
    def get_powerwalls(self) -> List[Dict[str, Any]]:
        """
        Test pypowerwall connection and get basic Powerwall info.
        
        Returns:
            List containing single Powerwall information dictionary
        """
        try:
            result = self.oauth_manager.test_pypowerwall_connection("")
            if result['success']:
                return [result['powerwall']]
            else:
                raise PowerwallError(f"Failed to connect to Powerwall: {result.get('error')}")
        except Exception as e:
            self.logger.error(f"Failed to get Powerwall info: {e}")
            raise PowerwallError(f"Failed to get Powerwall: {e}")
    
    def switch_powerwall(self, powerwall_id: str) -> bool:
        """
        Switch to a different Powerwall.
        
        Args:
            powerwall_id: ID of the Powerwall to switch to
            
        Returns:
            True if switch successful, False otherwise
        """
        try:
            # Update configuration
            self.config.powerwall_id = powerwall_id
            
            # Disconnect current connection
            self.disconnect()
            
            # Reconnect with new Powerwall ID
            success = self.connect()
            
            if success:
                self.logger.log_powerwall_operation(
                    "switch_powerwall_success", True,
                    metadata={
                        'email': self.config.email,
                        'new_powerwall_id': powerwall_id
                    }
                )
            else:
                self.logger.log_powerwall_operation(
                    "switch_powerwall_failure", False,
                    metadata={
                        'email': self.config.email,
                        'powerwall_id': powerwall_id
                    }
                )
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to switch Powerwall: {e}")
            return False
    
    def set_backup_reserve(self, percentage: float) -> bool:
        """
        Set backup reserve percentage via cloud.
        
        Args:
            percentage: Backup reserve percentage (0-100)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_connected():
            raise PowerwallConnectionError("Not connected to Powerwall")
        
        # Validate percentage
        if not self._reserve_validator.validate_percentage(percentage):
            raise ValueError(f"Invalid backup reserve percentage: {percentage}")
        
        def _set_reserve_operation():
            try:
                # Use pypowerwall to set backup reserve
                result = self._powerwall.setbackup(percentage)
                
                if result:
                    # Record in history
                    self._reserve_history.add_entry(percentage, time.time())
                    
                    self.logger.log_powerwall_operation(
                        "set_backup_reserve_success", True,
                        metadata={
                            'percentage': percentage,
                            'email': self.config.email,
                            'powerwall_id': self._current_powerwall_id
                        }
                    )
                    return True
                else:
                    self.logger.log_powerwall_operation(
                        "set_backup_reserve_failure", False,
                        metadata={
                            'percentage': percentage,
                            'email': self.config.email,
                            'powerwall_id': self._current_powerwall_id
                        }
                    )
                    return False
                    
            except Exception as e:
                self.logger.error(f"Failed to set backup reserve: {e}")
                raise PowerwallError(f"Backup reserve setting failed: {e}")
        
        try:
            return self._circuit_breaker.execute(_set_reserve_operation)
        except Exception as e:
            self.logger.log_powerwall_operation(
                "set_backup_reserve_failure", False,
                metadata={'error': str(e), 'percentage': percentage}
            )
            raise
    
    def get_connection_info(self) -> Dict[str, Any]:
        """
        Get connection information.
        
        Returns:
            Dictionary with connection details
        """
        return {
            'connection_type': 'cloud',
            'email': self.config.email,
            'powerwall_id': self._current_powerwall_id,
            'connected': self._connected,
            'oauth_status': self.oauth_manager.get_auth_status(),
            'last_status_time': self._last_status.timestamp if self._last_status else None
        }
