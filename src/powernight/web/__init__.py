"""
Web Interface Module

Flask-based web interface for configuration and monitoring.
"""

from .app import create_app
from .api import api_blueprint
from .api.routes import main_blueprint

__all__ = [
    "create_app",
    "api_blueprint",
    "main_blueprint",
]