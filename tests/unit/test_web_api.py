"""
Unit Tests for PowerNight Web API

Tests the consolidated API surface: schema validation, backup reserve
endpoints, status/health endpoints, and the consolidated GET/POST
/api/v1/config endpoints.

Uses the shared `app`/`client` fixtures from tests/conftest.py.
"""

import json

import pytest
import yaml
from unittest.mock import Mock, patch

from powernight.web.api.schemas import SchemaValidator, get_schema_validator


@pytest.fixture
def config_manager(config_file, monkeypatch):
    """Point the core ConfigManager singleton at a temp config file.

    API endpoints read configuration through the ConfigManager singleton
    (require_auth, get_config, save_config), so tests that hit those
    endpoints need the singleton loaded from a throwaway file.
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


class TestSchemaValidator:
    """Test suite for schema validation (backup_reserve schema only)."""

    def test_schema_registry_contains_only_backup_reserve(self):
        validator = get_schema_validator()
        assert list(validator.schemas.keys()) == ['backup_reserve']

    def test_backup_reserve_validation_success(self):
        validator = SchemaValidator()

        result = validator.validate_backup_reserve({
            'percentage': 75.5,
            'reason': 'Test change'
        })

        assert result.is_valid is True
        assert result.errors == []
        assert result.sanitized_data is not None
        assert result.sanitized_data['percentage'] == 75.5

    def test_backup_reserve_validation_invalid_percentage(self):
        validator = SchemaValidator()

        result = validator.validate_backup_reserve({'percentage': 150.0})

        assert result.is_valid is False
        assert len(result.errors) > 0
        assert any('percentage' in error for error in result.errors)

    def test_backup_reserve_validation_missing_percentage(self):
        validator = SchemaValidator()

        result = validator.validate_backup_reserve({'reason': 'No percentage'})

        assert result.is_valid is False
        assert any('percentage' in error for error in result.errors)

    def test_backup_reserve_validation_rejects_unknown_fields(self):
        validator = SchemaValidator()

        result = validator.validate_backup_reserve({
            'percentage': 50.0,
            'unexpected_field': 'nope'
        })

        assert result.is_valid is False
        assert any('unexpected_field' in error for error in result.errors)

    def test_backup_reserve_sanitization_trims_reason(self):
        validator = SchemaValidator()

        result = validator.validate_backup_reserve({
            'percentage': 50.0,
            'reason': '  Test change  '
        })

        assert result.is_valid is True
        assert result.sanitized_data['reason'] == 'Test change'

    def test_validation_result_to_dict(self):
        validator = SchemaValidator()

        result = validator.validate_backup_reserve({'percentage': -5})
        payload = result.to_dict()

        assert payload['is_valid'] is False
        assert payload['error_count'] == len(payload['errors'])
        assert 'warnings' in payload


class TestGetBackupReserveAPI:
    """Test suite for GET /api/v1/backup-reserve."""

    def test_get_backup_reserve_demo_mode_default(self, client, config_manager):
        """Without a profile header the endpoint returns demo data."""
        response = client.get('/api/v1/backup-reserve')

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['data']['demo_mode'] is True
        assert data['data']['backup_reserve_percentage'] == 20.0
        assert data['data']['powerwall_name'] == 'Demo Powerwall'

    def test_get_backup_reserve_success(self, client, config_manager):
        """Non-demo profile reads the real Powerwall connector."""
        with patch('powernight.web.api.api.get_powerwall_connector') as mock_connector:
            mock_powerwall = Mock()
            mock_powerwall.is_connected.return_value = True
            mock_powerwall.get_backup_reserve_percentage.return_value = 50.0
            mock_connector.return_value = mock_powerwall

            response = client.get('/api/v1/backup-reserve',
                                  headers={'X-Powerwall-Profile': 'real'})

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['data']['current_percentage'] == 50.0
        assert 'request_id' in data['data']
        assert 'connection_time_seconds' in data['data']

    def test_get_backup_reserve_with_diagnostics(self, client, config_manager):
        with patch('powernight.web.api.api.get_powerwall_connector') as mock_connector:
            mock_powerwall = Mock()
            mock_powerwall.is_connected.return_value = True
            mock_powerwall.get_backup_reserve_percentage.return_value = 75.0
            mock_powerwall.get_cache_stats.return_value = {'hits': 10, 'misses': 2}
            mock_connector.return_value = mock_powerwall

            response = client.get(
                '/api/v1/backup-reserve?include_diagnostics=true',
                headers={'X-Powerwall-Profile': 'real'})

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'diagnostics' in data['data']

    def test_get_backup_reserve_connection_error(self, client, config_manager):
        with patch('powernight.web.api.api.get_powerwall_connector') as mock_connector:
            mock_powerwall = Mock()
            mock_powerwall.is_connected.return_value = False
            mock_powerwall.test_connection.side_effect = Exception("Connection failed")
            mock_connector.return_value = mock_powerwall

            response = client.get('/api/v1/backup-reserve',
                                  headers={'X-Powerwall-Profile': 'real'})

        assert response.status_code == 502
        data = response.get_json()
        assert data['success'] is False
        assert 'Powerwall Communication Error' in data['error']


class TestSetBackupReserveAPI:
    """Test suite for POST /api/v1/backup-reserve."""

    JSON_HEADERS = {'Content-Type': 'application/json'}

    def test_set_backup_reserve_success(self, client, config_manager):
        reserve_data = {'percentage': 60.0, 'reason': 'Test change'}

        with patch('powernight.web.api.api.get_powerwall_connector') as mock_connector:
            mock_powerwall = Mock()
            mock_powerwall.is_connected.return_value = True
            mock_powerwall.set_backup_reserve_percentage.return_value = None
            mock_connector.return_value = mock_powerwall

            response = client.post('/api/v1/backup-reserve',
                                   data=json.dumps(reserve_data),
                                   headers=self.JSON_HEADERS)

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['data']['target_percentage'] == 60.0
        assert data['data']['actual_percentage'] == 60.0
        assert data['data']['change_applied'] is True
        assert 'metadata' in data
        mock_powerwall.set_backup_reserve_percentage.assert_called_once_with(
            60.0, reason='Test change')

    def test_set_backup_reserve_dry_run(self, client, config_manager):
        reserve_data = {'percentage': 80.0, 'reason': 'Dry run test'}

        response = client.post('/api/v1/backup-reserve?dry_run=true',
                               data=json.dumps(reserve_data),
                               headers=self.JSON_HEADERS)

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['dry_run'] is True
        assert data['target_percentage'] == 80.0

    def test_set_backup_reserve_validation_error(self, client, config_manager):
        reserve_data = {'percentage': 150.0}

        response = client.post('/api/v1/backup-reserve',
                               data=json.dumps(reserve_data),
                               headers=self.JSON_HEADERS)

        assert response.status_code == 422
        data = response.get_json()
        assert data['success'] is False
        assert 'validation' in data

    def test_set_backup_reserve_invalid_json(self, client, config_manager):
        response = client.post('/api/v1/backup-reserve',
                               data='not valid json',
                               headers=self.JSON_HEADERS)

        assert response.status_code == 422
        data = response.get_json()
        assert data['success'] is False
        assert 'Invalid JSON' in data['error']

    def test_set_backup_reserve_missing_content_type(self, client, config_manager):
        response = client.post('/api/v1/backup-reserve',
                               data=json.dumps({'percentage': 50.0}))

        assert response.status_code == 422
        data = response.get_json()
        assert data['success'] is False

    def test_set_backup_reserve_powerwall_error(self, client, config_manager):
        reserve_data = {'percentage': 30.0, 'reason': 'Test error scenario'}

        with patch('powernight.web.api.api.get_powerwall_connector') as mock_connector:
            mock_powerwall = Mock()
            mock_powerwall.is_connected.return_value = True
            mock_powerwall.set_backup_reserve_percentage.side_effect = Exception("Powerwall error")
            mock_connector.return_value = mock_powerwall

            response = client.post('/api/v1/backup-reserve',
                                   data=json.dumps(reserve_data),
                                   headers=self.JSON_HEADERS)

        assert response.status_code == 502
        data = response.get_json()
        assert data['success'] is False
        assert 'Powerwall Write Error' in data['error']


class TestConfigAPI:
    """Test suite for the consolidated GET/POST /api/v1/config endpoints."""

    JSON_HEADERS = {'Content-Type': 'application/json'}

    def test_get_config_success(self, client, config_manager):
        response = client.get('/api/v1/config')

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['data']['web']['port'] == 8080
        assert data['data']['automation']['enabled'] is False
        assert data['data']['powerwall']['configured'] is True

    def test_post_config_deep_merges_and_saves(self, client, config_manager, config_file):
        updates = {'automation': {'enabled': True}}

        response = client.post('/api/v1/config',
                               data=json.dumps(updates),
                               headers=self.JSON_HEADERS)

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

        # The merged config is persisted to the ConfigManager's loaded path
        with open(config_file) as f:
            saved = yaml.safe_load(f)
        assert saved['automation']['enabled'] is True
        # Deep merge preserved the untouched sections
        assert saved['powerwall']['tesla_email'] == 'test@example.com'
        assert saved['web_interface']['port'] == 8080

    def test_post_config_rejects_non_object_body(self, client, config_manager):
        response = client.post('/api/v1/config',
                               data='null',
                               headers=self.JSON_HEADERS)

        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False

    def test_post_config_rejects_invalid_json(self, client, config_manager):
        response = client.post('/api/v1/config',
                               data='not valid json',
                               headers=self.JSON_HEADERS)

        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False

    def test_post_config_validation_error(self, client, config_manager):
        updates = {'web_interface': {'port': 999999}}

        response = client.post('/api/v1/config',
                               data=json.dumps(updates),
                               headers=self.JSON_HEADERS)

        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert data['error'] == 'Validation failed'
        assert any('port' in detail for detail in data['details'])

    def test_post_config_invalid_schedule_entry(self, client, config_manager):
        updates = {'automation': {'schedule': [{'percentage': 50.0}]}}

        response = client.post('/api/v1/config',
                               data=json.dumps(updates),
                               headers=self.JSON_HEADERS)

        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False


class TestStatusAPI:
    """Test suite for GET /api/v1/status."""

    def test_status_success(self, client, config_manager, mock_planner):
        with patch('powernight.web.api.api.get_powerwall_connector') as mock_connector, \
             patch('powernight.web.api.api.get_planner', return_value=mock_planner):
            mock_powerwall = Mock()
            mock_powerwall.is_connected.return_value = False
            mock_connector.return_value = mock_powerwall

            response = client.get('/api/v1/status',
                                  headers={'X-Powerwall-Profile': 'demo'})

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['data']['system']['active_profile'] == 'demo'
        assert data['data']['powerwall']['name'] == 'Demo Powerwall'
        assert data['data']['configuration']['loaded'] is True
        assert data['data']['configuration']['automation_enabled'] is False


class TestHealthAPI:
    """Test suite for health endpoints."""

    def test_main_health_endpoint(self, client):
        response = client.get('/health')

        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'healthy'
        assert 'version' in data
        assert 'timestamp' in data

    def test_api_health_all_checks_passing(self, client, config_manager, mock_planner):
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
        assert data['checks'] == {
            'configuration': True,
            'powerwall': True,
            'scheduler': True
        }

    def test_api_health_degraded_when_powerwall_down(self, client, config_manager, mock_planner):
        mock_planner.get_status.return_value = {'is_running': True, 'task_count': 0}

        with patch('powernight.web.api.api.get_powerwall_connector') as mock_connector, \
             patch('powernight.web.api.api.get_planner', return_value=mock_planner):
            mock_powerwall = Mock()
            mock_powerwall.is_connected.return_value = False
            mock_connector.return_value = mock_powerwall

            response = client.get('/api/v1/health')

        assert response.status_code == 503
        data = response.get_json()
        assert data['status'] == 'degraded'
        assert data['checks']['configuration'] is True
        assert data['checks']['powerwall'] is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
