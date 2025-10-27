"""
PowerNight Flask Application Factory

Creates and configures the Flask application with blueprints and error handling.
"""

import os
import time
from typing import Optional, Dict, Any

from flask import request
from flask import Flask

from ..core.config import PowerNightConfig as Config
from ..core.powerwall import PowerwallConnector
from .api.routes import main_blueprint
from .api import api_blueprint
from .api.auth_api import auth_blueprint, init_auth_api
from .api.config_api import config_blueprint
from .api.logs_api import logs_blueprint
from .api.tasks_api import tasks_blueprint
from .middleware import configure_middleware


def create_app(
        config: Config,
        testing: bool = False,
        powerwall_connector: Optional[PowerwallConnector] = None
) -> Flask:
    """
    Create and configure the Flask application.
    """
    # Determine static folder path for React build output
    # In Docker: /app/dist
    # In development: project_root/dist
    static_folder = os.environ.get('POWERNIGHT_STATIC_PATH')

    if not static_folder or not os.path.exists(static_folder):
        # Calculate absolute path from this file's location
        # This file: src/powernight/web/app.py
        # Target: dist/ (at project root)
        web_dir = os.path.dirname(os.path.abspath(__file__))  # src/powernight/web
        powernight_dir = os.path.dirname(web_dir)              # src/powernight
        src_dir = os.path.dirname(powernight_dir)              # src
        project_root = os.path.dirname(src_dir)                # project root
        static_folder = os.path.join(project_root, 'dist')

    # Create Flask app
    # Note: template_folder is not needed since we're serving React SPA only
    # static_folder points to React build output (dist/)
    # static_url_path is left as default so static files work correctly
    app = Flask(
        __name__,
        static_folder=static_folder
    )

    # Store shared components on the app object
    app.powerwall_connector = powerwall_connector

    # Load configuration
    app.config.from_object(config)

    # Configure middleware
    configure_middleware(app)

    # Register blueprints
    # Main blueprint for serving React SPA (must be last for catch-all route)
    app.register_blueprint(api_blueprint, url_prefix='/api/v1')
    init_auth_api(app)  # Initialize OAuth manager before registering auth blueprint
    app.register_blueprint(config_blueprint)
    app.register_blueprint(logs_blueprint)  # logs_blueprint has its own /api/v1/logs prefix
    app.register_blueprint(tasks_blueprint)
    app.register_blueprint(main_blueprint)  # Must be last for catch-all route

    return app