"""
Integration tests for PowerNight application.

Tests end-to-end behavior of the kept API surface (status, backup-reserve,
config, health) together with the SPA-serving web layer. Uses the shared
`app`/`client` fixtures from tests/conftest.py.
"""

import json
import time
from datetime import datetime, timezone

import pytest
import yaml
from unittest.mock import Mock, patch


@pytest.fixture(autouse=True)
def config_manager(config_file, monkeypatch):
    """Point the core ConfigManager singleton at a temp config file."""
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


class TestWebInterfaceIntegration:
    """Test web interface integration."""

    def test_web_interface_routes(self, client):
        """All web interface routes are accessible."""
        routes = [
            '/',
            '/dashboard',
            '/scheduling',
            '/logs',
            '/version',
            '/health',
        ]

        for route in routes:
            response = client.get(route)
            assert response.status_code == 200

    def test_spa_served_for_client_side_routes(self, client):
        """React Router routes get index.html so client routing can happen."""
        for route in ('/dashboard', '/scheduling', '/logs'):
            response = client.get(route)
            assert response.status_code == 200
            assert b'PowerNight test' in response.data


class TestAPIWebIntegration:
    """Test API and web interface integration."""

    def test_api_status_shape_for_frontend(self, client, mock_planner):
        """Status responses contain the fields the dashboard expects."""
        with patch('powernight.web.api.api.get_powerwall_connector') as mock_connector, \
             patch('powernight.web.api.api.get_planner', return_value=mock_planner):
            mock_powerwall = Mock()
            mock_powerwall.is_connected.return_value = False
            mock_connector.return_value = mock_powerwall

            response = client.get('/api/v1/status',
                                  headers={'X-Powerwall-Profile': 'demo'})

        assert response.status_code == 200
        data = response.get_json()
        assert 'data' in data
        assert 'powerwall' in data['data']
        assert 'backup_reserve_percentage' in data['data']['powerwall']
        assert 'connected' in data['data']['powerwall']
        assert 'scheduler' in data['data']
        assert 'configuration' in data['data']

    def test_api_headers_handling(self, client):
        """API correctly handles profile headers."""
        response = client.get('/api/v1/backup-reserve', headers={
            'X-Powerwall-Profile': 'demo',
            'X-Powerwall-Email': 'demo@example.com',
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['data']['demo_mode'] is True

        response = client.get('/api/v1/backup-reserve', headers={
            'X-Powerwall-Profile': 'gruber-eg',
            'X-Powerwall-Email': 'gruber@example.com',
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['data']['demo_mode'] is False
        assert data['data']['powerwall_name'] == 'Gruber EG'


class TestConfigurationIntegration:
    """Test configuration integration through the consolidated config API."""

    def test_configuration_loading(self, client):
        response = client.get('/api/v1/config')

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['data']['powerwall']['configured'] is True

    def test_configuration_update_round_trip(self, client, config_file):
        headers = {'Content-Type': 'application/json'}

        # Valid partial update is merged and persisted
        valid_update = {'automation': {'check_interval': 120.0}}
        response = client.post('/api/v1/config', headers=headers,
                               data=json.dumps(valid_update))
        assert response.status_code == 200

        with open(config_file) as f:
            saved = yaml.safe_load(f)
        assert saved['automation']['check_interval'] == 120.0
        assert saved['powerwall']['tesla_email'] == 'test@example.com'

        # Invalid update is rejected with 400
        invalid_update = {'powerwall': {'tesla_email': 'invalid-email'}}
        response = client.post('/api/v1/config', headers=headers,
                               data=json.dumps(invalid_update))
        assert response.status_code == 400


class TestErrorHandlingIntegration:
    """Test error handling integration."""

    def test_error_handling_consistency(self, client):
        # Unknown non-API routes are served by the SPA catch-all
        response = client.get('/nonexistent-route')
        assert response.status_code == 200

        # Method not allowed
        response = client.post('/api/v1/status')
        assert response.status_code == 405

        # Unknown API routes return JSON 404
        response = client.get('/api/v1/nonexistent')
        assert response.status_code == 404
        data = response.get_json()
        assert data['error'] == 'Not found'

    def test_graceful_degradation(self, client):
        """Application degrades gracefully with missing or unknown headers."""
        # Missing profile headers fall back to demo defaults
        response = client.get('/api/v1/backup-reserve')
        assert response.status_code == 200

        # Unknown profile headers hit the real connector path; a failing
        # connector yields a 502 instead of a crash
        with patch('powernight.web.api.api.get_powerwall_connector',
                   side_effect=Exception('no connector')):
            response = client.get('/api/v1/backup-reserve', headers={
                'X-Powerwall-Profile': 'invalid-profile',
            })
        assert response.status_code == 502
        data = response.get_json()
        assert data['success'] is False


class TestPerformanceIntegration:
    """Test performance integration."""

    def test_response_times(self, client):
        headers = {'X-Powerwall-Profile': 'demo'}

        for endpoint in ('/api/v1/backup-reserve', '/health', '/version'):
            start_time = time.time()
            response = client.get(endpoint, headers=headers)
            end_time = time.time()

            assert response.status_code == 200
            assert (end_time - start_time) < 1.0

    def test_concurrent_requests(self, client):
        import threading
        import queue

        headers = {'X-Powerwall-Profile': 'demo'}
        results = queue.Queue()

        def make_request():
            response = client.get('/api/v1/backup-reserve', headers=headers)
            results.put(response.status_code)

        threads = [threading.Thread(target=make_request) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        while not results.empty():
            assert results.get() == 200


class TestDataConsistencyIntegration:
    """Test data consistency across the application."""

    def test_data_consistency_across_profiles(self, client):
        profiles = [
            {'profile': 'demo', 'expected_name': 'Demo Powerwall'},
            {'profile': 'gruber-eg', 'expected_name': 'Gruber EG'},
        ]

        for profile_info in profiles:
            headers = {'X-Powerwall-Profile': profile_info['profile']}

            response = client.get('/api/v1/backup-reserve', headers=headers)
            assert response.status_code == 200
            data = response.get_json()
            assert data['data']['powerwall_name'] == profile_info['expected_name']

    def test_timestamp_consistency(self, client):
        response = client.get('/api/v1/backup-reserve',
                              headers={'X-Powerwall-Profile': 'demo'})
        assert response.status_code == 200
        data = response.get_json()

        timestamp_str = data['data']['timestamp']
        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        assert (now - timestamp).total_seconds() < 10
