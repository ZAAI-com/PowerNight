"""
Web interface tests for PowerNight application.

The app serves a React SPA: every non-API route returns index.html from the
static (dist) folder. The shared `app` fixture from tests/conftest.py points
the static folder at a temp dist directory containing a minimal index.html.
"""

from pathlib import Path

import pytest


class TestPageRoutes:
    """Test SPA page routes."""

    def test_root_serves_index(self, client):
        response = client.get('/')
        assert response.status_code == 200
        assert b'PowerNight test' in response.data

    def test_spa_routes_serve_index(self, client):
        """All React Router routes are served by the catch-all."""
        for route in ('/dashboard', '/scheduling', '/settings', '/logs'):
            response = client.get(route)
            assert response.status_code == 200
            assert b'PowerNight test' in response.data

    def test_nested_spa_route_serves_index(self, client):
        response = client.get('/some/nested/route')
        assert response.status_code == 200
        assert b'PowerNight test' in response.data


class TestUtilityRoutes:
    """Test health, version, and favicon routes."""

    def test_health_route(self, client):
        response = client.get('/health')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'healthy'
        assert 'version' in data

    def test_version_route(self, client):
        response = client.get('/version')
        assert response.status_code == 200
        data = response.get_json()
        assert data['application'] == 'PowerNight'
        assert 'version' in data

    def test_favicon_returns_no_content(self, client):
        response = client.get('/favicon.ico')
        assert response.status_code == 204


class TestStaticAssets:
    """Test static asset serving from the dist/assets directory."""

    def test_asset_file_served(self, app, client):
        assets_dir = Path(app.static_folder) / 'assets'
        assets_dir.mkdir(exist_ok=True)
        (assets_dir / 'index-test.js').write_text('console.log("test");')
        (assets_dir / 'index-test.css').write_text('body { color: red; }')

        response = client.get('/assets/index-test.js')
        assert response.status_code == 200
        assert b'console.log' in response.data

        response = client.get('/assets/index-test.css')
        assert response.status_code == 200
        assert b'color: red' in response.data

    def test_missing_asset_returns_404(self, app, client):
        assets_dir = Path(app.static_folder) / 'assets'
        assets_dir.mkdir(exist_ok=True)

        response = client.get('/assets/does-not-exist.js')
        assert response.status_code == 404


class TestErrorHandling:
    """Test web interface error handling."""

    def test_unknown_api_endpoint_returns_404(self, client):
        response = client.get('/api/v1/invalid-endpoint')
        assert response.status_code == 404
        data = response.get_json()
        assert data['error'] == 'Not found'

    def test_unknown_api_path_not_served_as_spa(self, client):
        """API-prefixed paths must never fall through to index.html."""
        response = client.get('/api/does/not/exist')
        assert response.status_code == 404
        assert b'PowerNight test' not in response.data
