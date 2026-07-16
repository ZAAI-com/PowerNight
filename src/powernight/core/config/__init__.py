"""
PowerNight Configuration Module

Configuration management and schema definitions.
"""

from .manager import ConfigManager, get_config_manager, get_config, load_config
from .schema import (
    PowerNightConfig,
    PowerwallSettings,
    AutomationSettings,
    WebInterfaceSettings,
    LoggingSettings,
    MonitoringSettings,
    ScheduleEntry,
    create_default_config
)
from .exceptions import ConfigurationError

__all__ = [
    'ConfigManager',
    'get_config_manager',
    'get_config',
    'load_config',
    'PowerNightConfig',
    'PowerwallSettings',
    'AutomationSettings',
    'WebInterfaceSettings',
    'LoggingSettings',
    'MonitoringSettings',
    'ScheduleEntry',
    'create_default_config',
    'ConfigurationError'
]