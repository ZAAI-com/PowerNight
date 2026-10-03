"""
PowerNight Flask Application Factory

Creates and configures the Flask application with blueprints and error handling.
"""

import os
from typing import Optional

from flask import Flask

from ..core.config import PowerNightConfig as Config
from ..core.powerwall import PowerwallConnector
from .api.routes import main_blueprint
from .api import api_blueprint
from .api.auth_api import init_auth_api
from .api.config_api import config_blueprint
from .api.logs_api import logs_blueprint
from .api.tasks_api import tasks_blueprint
from .middleware import configure_middleware


def _load_or_create_secret() -> str:
    """Load the persisted Flask secret, generating it on first run."""
    import secrets

    data_path = os.environ.get('POWERNIGHT_DATA_PATH', 'data')
    secret_file = os.path.join(data_path, '.flask_secret')
    try:
        if os.path.exists(secret_file):
            with open(secret_file) as f:
                value = f.read().strip()
            if value:
                return value
        value = secrets.token_hex(32)
        os.makedirs(data_path, exist_ok=True)
        with open(secret_file, 'w') as f:
            f.write(value)
        os.chmod(secret_file, 0o600)
        return value
    except OSError:
        # Fall back to an ephemeral secret rather than refusing to start;
        # sessions will not survive restarts in this case
        return secrets.token_hex(32)


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
    app.testing = testing

    # Session/signing secret: env var wins; otherwise persist a generated
    # secret under the data path so sessions survive restarts
    app.secret_key = os.environ.get('FLASK_SECRET_KEY') or _load_or_create_secret()

    # Load configuration
    app.config.from_object(config)

    # Configure middleware
    configure_middleware(app)

    # Authentication failures must be 401s on every blueprint, not 500s
    from .api.errors import AuthenticationError, AuthorizationError

    @app.errorhandler(AuthenticationError)
    def handle_authentication_error(error):
        return {
            'success': False,
            'error': 'Authentication required',
            'message': str(error)
        }, 401

    @app.errorhandler(AuthorizationError)
    def handle_authorization_error(error):
        return {
            'success': False,
            'error': 'Forbidden',
            'message': str(error)
        }, 403

    # Register blueprints
    # Main blueprint for serving React SPA (must be last for catch-all route)
    app.register_blueprint(api_blueprint, url_prefix='/api/v1')
    init_auth_api(app)  # Initialize OAuth manager before registering auth blueprint
    app.register_blueprint(config_blueprint)
    app.register_blueprint(logs_blueprint)  # logs_blueprint has its own /api/v1/logs prefix
    app.register_blueprint(tasks_blueprint)
    app.register_blueprint(main_blueprint)  # Must be last for catch-all route

    return app