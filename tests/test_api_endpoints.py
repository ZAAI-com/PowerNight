"""
API endpoint tests for PowerNight application.

Covers the kept API surface: status, backup-reserve, config, test-connection,
and health. Uses the shared `app`/`client` fixtures from tests/conftest.py.
"""

import json

import pytest
import yaml
from unittest.mock import Mock, patch


@pytest.fixture(autouse=True)
def config_manager(config_file, monkeypatch):
    """Point the core ConfigManager singleton at a temp config file.

    API endpoints (require_auth, get_config, save_config) read configuration
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


JSON_HEADERS = {'Content-Type': 'application/json'}


class TestStatusAPI:
    """Test /api/v1/status endpoint."""

    def test_status_demo_profile(self, client, mock_planner):
        with patch('powernight.web.api.api.get_powerwall_connector') as mock_connector, \
             patch('powernight.web.api.api.get_planner', return_value=mock_planner):
            mock_powerwall = Mock()
            mock_powerwall.is_connected.return_value = False
            mock_connector.return_value = mock_powerwall

            response = client.get('/api/v1/status', headers={
                'X-Powerwall-Profile': 'demo',
            })

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'data' in data
        assert data['data']['system']['active_profile'] == 'demo'
        assert data['data']['powerwall']['name'] == 'Demo Powerwall'
        assert data['data']['powerwall']['backup_reserve_percentage'] == 20.0

    def test_status_gruber_eg_profile(self, client, mock_planner):
        with patch('powernight.web.api.api.get_powerwall_connector') as mock_connector, \
             patch('powernight.web.api.api.get_planner', return_value=mock_planner):
            mock_powerwall = Mock()
            mock_powerwall.is_connected.return_value = False
            mock_connector.return_value = mock_powerwall

            response = client.get('/api/v1/status', headers={
                'X-Powerwall-Profile': 'gruber-eg',
            })

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['data']['system']['active_profile'] == 'gruber-eg'
        assert data['data']['powerwall']['name'] == 'Gruber EG'
        assert data['data']['powerwall']['backup_reserve_percentage'] == 35.0

    def test_status_rejects_post(self, client):
        response = client.post('/api/v1/status')
        assert response.status_code == 405


class TestBackupReserveAPI:
    """Test /api/v1/backup-reserve endpoint."""

    def test_get_backup_reserve_demo(self, client):
        response = client.get('/api/v1/backup-reserve', headers={
            'X-Powerwall-Profile': 'demo',
        })

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['data']['backup_reserve_percentage'] == 20.0
        assert data['data']['powerwall_name'] == 'Demo Powerwall'
        assert data['data']['demo_mode'] is True

    def test_get_backup_reserve_gruber_eg(self, client):
        response = client.get('/api/v1/backup-reserve', headers={
            'X-Powerwall-Profile': 'gruber-eg',
        })

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['data']['backup_reserve_percentage'] == 35.0
        assert data['data']['powerwall_name'] == 'Gruber EG'
        assert data['data']['demo_mode'] is False

    def test_set_backup_reserve(self, client):
        with patch('powernight.web.api.api.get_powerwall_connector') as mock_connector:
            mock_powerwall = Mock()
            mock_powerwall.is_connected.return_value = True
            mock_powerwall.set_backup_reserve_percentage.return_value = None
            mock_connector.return_value = mock_powerwall

            response = client.post('/api/v1/backup-reserve',
                                   headers=JSON_HEADERS,
                                   data=json.dumps({'percentage': 25.0}))

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['data']['target_percentage'] == 25.0

    def test_set_backup_reserve_invalid_percentage(self, client):
        response = client.post('/api/v1/backup-reserve',
                               headers=JSON_HEADERS,
                               data=json.dumps({'percentage': 150.0}))

        assert response.status_code == 422
        data = response.get_json()
        assert data['success'] is False


class TestConfigAPI:
    """Test the consolidated /api/v1/config endpoints."""

    def test_get_config(self, client):
        response = client.get('/api/v1/config')

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'data' in data
        assert 'powerwall' in data['data']
        assert 'automation' in data['data']
        assert 'web' in data['data']

    def test_update_config(self, client, config_file):
        config_data = {
            'powerwall': {
                'timeout': 45.0,
            }
        }

        response = client.post('/api/v1/config',
                               headers=JSON_HEADERS,
                               data=json.dumps(config_data))

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

        with open(config_file) as f:
            saved = yaml.safe_load(f)
        assert saved['powerwall']['timeout'] == 45.0
        assert saved['powerwall']['tesla_email'] == 'test@example.com'

    def test_update_config_validation_error(self, client):
        config_data = {
            'powerwall': {
                'tesla_email': 'not-an-email',
            }
        }

        response = client.post('/api/v1/config',
                               headers=JSON_HEADERS,
                               data=json.dumps(config_data))

        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False


class TestTestConnectionAPI:
    """Test /api/v1/test-connection endpoint."""

    def test_test_connection_demo(self, client):
        response = client.post('/api/v1/test-connection',
                               headers={'X-Powerwall-Profile': 'demo',
                                        'Content-Type': 'application/json'},
                               data=json.dumps({'tesla_email': 'test@example.com'}))

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'message' in data
        assert data['demo_mode'] is True

    def test_test_connection_gruber_eg(self, client):
        response = client.post('/api/v1/test-connection',
                               headers={'X-Powerwall-Profile': 'gruber-eg',
                                        'Content-Type': 'application/json'},
                               data=json.dumps({'tesla_email': 'test@example.com'}))

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'message' in data

    def test_test_connection_missing_email(self, client):
        response = client.post('/api/v1/test-connection',
                               headers={'X-Powerwall-Profile': 'demo',
                                        'Content-Type': 'application/json'},
                               data=json.dumps({}))

        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False


class TestHealthAPI:
    """Test /api/v1/health endpoint."""

    def test_health_endpoint(self, client, mock_planner):
        mock_planner.get_status.return_value = {'is_running': True, 'task_count': 0}

        with patch('powernight.web.api.api.get_powerwall_connector') as mock_connector, \
             patch('powernight.web.api.api.get_planner', return_value=mock_planner):
            mock_powerwall = Mock()
            mock_powerwall.is_connected.return_value = True
            mock_connector.return_value = mock_powerwall

            response = client.get('/api/v1/health')

        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'healthy'
        assert 'checks' in data


class TestErrorHandling:
    """Test API error handling."""

    def test_missing_headers(self, client):
        """Backup reserve falls back to the demo profile without headers."""
        response = client.get('/api/v1/backup-reserve')

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

    def test_invalid_json(self, client):
        response = client.post('/api/v1/backup-reserve',
                               headers=JSON_HEADERS,
                               data='invalid json')

        assert response.status_code == 422
        data = response.get_json()
        assert data['success'] is False
        assert 'error' in data
