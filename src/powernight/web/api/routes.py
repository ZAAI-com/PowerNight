"""
PowerNight Main Routes

Main application routes for health checks and basic endpoints.
Serves the React SPA for all non-API routes.
"""

from flask import Blueprint, jsonify, current_app, send_from_directory
from datetime import datetime, timezone
import os


# Create main blueprint
main_blueprint = Blueprint('main', __name__)


@main_blueprint.route('/', methods=['GET'])
def index():
    """
    Application root endpoint - serve React SPA.
    """
    static_folder = current_app.static_folder
    return send_from_directory(static_folder, 'index.html')


@main_blueprint.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for container orchestration.

    Returns application health status.
    """
    try:
        # Basic health indicators
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'version': '1.0.0',
        }
        return jsonify(health_status), 200

    except Exception as e:
        current_app.logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'error': str(e)
        }), 503


@main_blueprint.route('/version', methods=['GET'])
def version_info():
    """
    Version information endpoint.

    Returns detailed version and build information.
    """
    return jsonify({
        'application': 'PowerNight',
        'version': '1.0.0',
        'build_date': '2025-10-18',
        'python_version': '3.13+',
        'dependencies': {
            'flask': 'Flask>=2.3.0',
            'pypowerwall': 'pypowerwall>=0.10.5',
            'schedule': 'schedule>=1.2.0'
        },
        'features': [
            'Tesla Powerwall automation',
            'Scheduled backup reserve changes',
            'React-based web UI',
            'REST API interface',
            'Error recovery and retry logic'
        ]
    })


@main_blueprint.route('/assets/<path:filename>')
def serve_assets(filename):
    """
    Serve React build assets.
    """
    static_folder = current_app.static_folder
    assets_dir = os.path.join(static_folder, 'assets')
    return send_from_directory(assets_dir, filename)




@main_blueprint.route('/favicon.ico', methods=['GET'])
def favicon():
    """
    Favicon endpoint to prevent 404 errors.
    """
    return '', 204


# Catch-all route for React SPA - serve index.html for all non-API routes
# This allows React Router to handle client-side routing
@main_blueprint.route('/<path:path>')
def spa_catchall(path):
    """
    Catch-all route for React SPA.
    Serves index.html for all routes not matched by API endpoints.
    React Router will handle client-side routing.
    """
    # Don't intercept API routes
    if path.startswith('api/'):
        return jsonify({'error': 'Not found'}), 404
    
    # Don't intercept specific static files that have their own routes
    if path in ['version-info.json', 'favicon.ico']:
        return jsonify({'error': 'Not found'}), 404

    # Serve React SPA for all other routes
    static_folder = current_app.static_folder
    return send_from_directory(static_folder, 'index.html')