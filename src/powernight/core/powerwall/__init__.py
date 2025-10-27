"""
Tesla Powerwall Connection Module

Handles communication with Tesla Powerwall devices using pypowerwall library.
"""

from .connector import PowerwallConnector
from .exceptions import (
    PowerwallError,
    PowerwallConnectionError,
    PowerwallAuthenticationError,
    PowerwallTimeoutError,
)
from .commands import (
    CronCommand,
    CommandType,
    PowerwallMode,
    GridExportMode,
    create_mode_command,
    create_reserve_command,
    create_current_command,
    create_grid_charging_command,
    create_grid_export_command,
)

# --- Singleton instance ---
_powerwall_connector_instance: PowerwallConnector | None = None


def initialize_powerwall_connector(config) -> PowerwallConnector:
    """
    Create and configure the singleton PowerwallConnector instance.
    Should be called once at application startup.
    """
    global _powerwall_connector_instance
    if _powerwall_connector_instance is None:
        try:
            # Try to get authenticated Tesla credentials first
            from ..auth.tesla_oauth import TeslaOAuthManager
            import os
            
            storage_path = os.environ.get('POWERNIGHT_DATA_PATH', 'data')
            oauth_manager = TeslaOAuthManager(storage_path=storage_path)
            
            # Use authenticated credentials if available, otherwise fall back to config
            email = config.powerwall.tesla_email
            powerwall_id = config.powerwall.powerwall_id
            
            if oauth_manager.auth_storage.has_auth_data():
                try:
                    auth_data = oauth_manager.auth_storage.load_auth_data()
                    if auth_data.get('email'):
                        email = auth_data['email']
                        print(f"Using authenticated Tesla email: {email}")
                    if auth_data.get('site', {}).get('id'):
                        powerwall_id = str(auth_data['site']['id'])
                        print(f"Using authenticated Powerwall site ID: {powerwall_id}")
                except Exception as e:
                    print(f"Warning: Could not load authenticated credentials, using config values: {e}")
            
            _powerwall_connector_instance = PowerwallConnector(
                email=email,
                powerwall_id=powerwall_id,
                timeout=config.powerwall.timeout,
                retry_attempts=config.powerwall.retry_attempts,
                rate_limit_delay=1.0
            )
        except Exception as e:
            raise PowerwallError(f"Failed to initialize PowerwallConnector: {e}")
    return _powerwall_connector_instance


def get_powerwall_connector() -> PowerwallConnector:
    """
    Get the singleton PowerwallConnector instance.

    Returns:
        PowerwallConnector instance

    Raises:
        PowerwallError: If configuration is invalid or connector cannot be created
    """
    if _powerwall_connector_instance is None:
        raise PowerwallError("PowerwallConnector has not been initialized. Please call initialize_powerwall_connector() at startup.")

    return _powerwall_connector_instance


__all__ = [
    "PowerwallConnector",
    "initialize_powerwall_connector",
    "get_powerwall_connector",
    "PowerwallError",
    "PowerwallConnectionError",
    "PowerwallAuthenticationError",
    "PowerwallTimeoutError",
    "CronCommand",
    "CommandType",
    "PowerwallMode",
    "GridExportMode",
    "create_mode_command",
    "create_reserve_command",
    "create_current_command",
    "create_grid_charging_command",
    "create_grid_export_command",
]