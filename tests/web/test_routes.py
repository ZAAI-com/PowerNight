"""
Tests for PowerNight web routes.

Uses the shared `app`/`client` fixtures from tests/conftest.py which build the
real Flask app with a temp dist directory serving a minimal index.html.
"""

import pytest


@pytest.fixture(autouse=True)
def config_manager(config_file, monkeypatch):
    """Point the core ConfigManager singleton at a temp config file.

    API endpoints (require_auth, status, backup-reserve) read configuration
    through the ConfigManager singleton, not the Flask app config.
    """
    import powernight.core.config.manager as manager_module
    from powernight.core.config.manager import ConfigManager

    for var in (
        "TESLA_EMAIL",
        "TESLA_CLIENT_ID",
        "AUTOMATION_ENABLED",
        "POWERNIGHT_WEB_HOST",
        "POWERNIGHT_WEB_PORT",
        "POWERNIGHT_LOG_LEVEL",
    ):
        monkeypatch.delenv(var, raising=False)

    previous = ConfigManager._instance
    ConfigManager._instance = None
    # Reset the cached global too so get_config_manager() sees the new instance
    monkeypatch.setattr(manager_module, '_config_manager', None)
    manager = manager_module.get_config_manager()
    manager.load_config(config_file)
    yield manager
    ConfigManager._instance = previous


class TestPageRoutes:
    """Test SPA page routes (all serve index.html from the dist folder)."""

    def test_root_serves_spa(self, client):
        response = client.get('/')
        assert response.status_code == 200
        assert b'PowerNight test' in response.data

    def test_dashboard_page(self, client):
        response = client.get('/dashboard')
        assert response.status_code == 200
        assert b'PowerNight test' in response.data

    def test_scheduling_page(self, client):
        response = client.get('/scheduling')
        assert response.status_code == 200
        assert b'PowerNight test' in response.data

    def test_logs_page(self, client):
        response = client.get('/logs')
        assert response.status_code == 200
        assert b'PowerNight test' in response.data


class TestAPIRoutes:
    """Test API routes used by the SPA."""

    def test_status_endpoint(self, client):
        response = client.get('/api/v1/status')
        assert response.status_code == 200

        data = response.get_json()
        assert data['success'] is True
        assert 'data' in data
        assert 'system' in data['data']
        assert 'powerwall' in data['data']

    def test_backup_reserve_endpoint_demo_mode(self, client):
        """Without a profile header the endpoint defaults to demo mode."""
        response = client.get('/api/v1/backup-reserve')
        assert response.status_code == 200

        data = response.get_json()
        assert data['success'] is True
        assert data['data']['demo_mode'] is True
        assert data['data']['backup_reserve_percentage'] == 20.0

    def test_health_endpoint(self, client):
        response = client.get('/health')
        assert response.status_code == 200

        data = response.get_json()
        assert data['status'] == 'healthy'
        assert 'timestamp' in data


class TestErrorHandling:
    """Test error handling in routes."""

    def test_unknown_page_serves_spa(self, client):
        """Non-API routes are handled by the SPA catch-all, not 404."""
        response = client.get('/nonexistent-page')
        assert response.status_code == 200
        assert b'PowerNight test' in response.data

    def test_unknown_api_endpoint_returns_404(self, client):
        response = client.get('/api/v1/invalid-endpoint')
        assert response.status_code == 404


if __name__ == '__main__':
    pytest.main([__file__])
