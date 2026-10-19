"""
PowerNight - Tesla Powerwall Backup Reserve Automation

A comprehensive Docker container application that controls the backup reserve percentage
of a Tesla Powerwall 2 during nighttime hours for Synology DSM deployment.

Features:
- Automated backup reserve scheduling
- Real-time monitoring and health checks
- Web-based management interface
- Enterprise-grade reliability features
- Multi-channel notifications
- Comprehensive logging and metrics
"""

__version__ = "2.0.0"
__author__ = "PowerNight Team"
__email__ = "powernight@zaai.com"
__description__ = "Tesla Powerwall Backup Reserve Automation"

# Core imports
from .core.powerwall import PowerwallConnector
from .core.config import ConfigManager
from .core.planner import Planner
from .web import create_app

# Utility imports
from .utils.logging import get_logger, ComponentType, OperationType, LogLevel
from .utils.exceptions import PowerNightError

__all__ = [
    # Core components
    "PowerwallConnector",
    "ConfigManager",
    "Planner",
    "create_app",

    # Utilities
    "get_logger",
    "ComponentType",
    "OperationType",
    "LogLevel",
    "PowerNightError",

    # Metadata
    "__version__",
    "__author__",
    "__email__",
    "__description__",
]