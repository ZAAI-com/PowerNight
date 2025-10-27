from flask import Flask, request
from flask_cors import CORS
from ..core.config import PowerNightConfig


def configure_middleware(app: Flask) -> None:
    """
    Configure Flask middleware, including CORS and request/response handling.
    """
    # Enable CORS for frontend development
    if app.config.get('DEBUG'):
        CORS(app, resources={r"/api/*": {"origins": "*"}})

    @app.before_request
    def before_request():
        """Log each request."""
        app.logger.debug(f"Request: {request.method} {request.url}")

    @app.after_request
    def after_request(response):
        """Log each response."""
        app.logger.debug(f"Response: {response.status_code}")
        return response

    @app.teardown_appcontext
    def teardown_appcontext(exception=None):
        """Clean up application context."""
        if exception:
            app.logger.error(f"App context teardown with exception: {exception}")
