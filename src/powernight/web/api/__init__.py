"""
PowerNight Web API Module

REST API endpoints for configuration, control, and monitoring.
"""

from .api import api_blueprint

__all__ = [
    "api_blueprint",
]
