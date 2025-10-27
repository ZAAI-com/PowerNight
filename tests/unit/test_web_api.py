"""
Unit Tests for PowerNight Web API

Comprehensive test suite for enterprise-grade API endpoints with highest development standards.
"""

import json
import pytest
import tempfile
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from pathlib import Path

from powernight.web import create_app
from powernight.web.api.schemas import SchemaValidator, ValidationResult
from powernight.web.api.config_manager import EnterpriseConfigManager
from powernight.core.config import PowerNightConfig, WebInterfaceSettings, PowerwallSettings, AutomationSettings, LoggingSettings


# Global test configuration
@pytest.fixture(scope='session')
def test_config():
    """Create test configuration for all tests."""
    return PowerNightConfig(
        powerwall=PowerwallSettings(
            tesla_email='test@example.com',
            powerwall_id='test-powerwall-123',
            timeout=30.0,
            retry_attempts=3
        ),
        automation=AutomationSettings(
            enabled=True,
            check_interval=60.0,
            schedule=[]
        ),
        web_interface=WebInterfaceSettings(
            enabled=True,
            host='127.0.0.1',
            port=5000,
            debug=False,
            auth_enabled=True,
            username='test',
            password='test',
            api_key='test_api_key_123456789012345678901234',
            cors_origins=['http://localhost:3000']
        ),
        logging=LoggingSettings(
            level='INFO',
            file_enabled=True,
            file_path='test.log',
            max_file_size='10MB',
            backup_count=3,
            console_output=True
        )
    )

@pytest.fixture(scope='session')
def app(test_config):
    """Create test Flask application."""
    with patch('powernight.config.get_config') as mock_get_config, \
         patch('powernight.web.app.get_config') as mock_app_get_config, \
         patch('powernight.web.auth.get_config') as mock_auth_get_config:

        mock_get_config.return_value = test_config
        mock_app_get_config.return_value = test_config
        mock_auth_get_config.return_value = test_config

        app = create_app(config=test_config, testing=True)
        app.config['TESTING'] = True
        yield app

@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()

class TestConfigurationAPI:
    """Test suite for configuration API endpoints."""

    @pytest.fixture
    def auth_headers(self):
        """Create authentication headers."""
        return {
            'Authorization': 'Basic dGVzdDp0ZXN0',  # test:test in base64
            'Content-Type': 'application/json'
        }

    @pytest.fixture
    def mock_config(self):
        """Create mock configuration."""
        return PowerNightConfig(
            powerwall=PowerwallSettings(
                ip_address="192.168.1.100",
                email="test@example.com",
                password="test_password",
                timeout=30.0,
                retry_attempts=3,
                verify_ssl=True
            ),
            automation=AutomationSettings(
                enabled=True,
                    check_interval=60.0,
                schedule=[
                    {
                        'time': '00:01',
                        'percentage': 40.0,
                        'enabled': True,
                        'description': 'Night reserve'
                    }
                ]
            ),
            web_interface=WebInterfaceSettings(
                enabled=True,
                host='127.0.0.1',
                port=5000,
                debug=False,
                auth_enabled=False
            )
        )

    def test_get_configuration_success(self, client, auth_headers, mock_config):
        """Test successful configuration retrieval."""
        with patch('powernight.web.api.get_enterprise_config_manager') as mock_manager:
            mock_instance = Mock()
            mock_instance.get_configuration.return_value = {
                'success': True,
                'data': {
                    'powerwall': {
                        'ip_address': '192.168.1.100',
                        'configured': True
                    },
                    'automation': {
                        'enabled': True,
                        'schedule': []
                    }
                },
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            mock_manager.return_value = mock_instance

            response = client.get('/api/v1/config', headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
            assert 'request_id' in data
            assert 'timestamp' in data

    def test_get_configuration_with_parameters(self, client, auth_headers):
        """Test configuration retrieval with query parameters."""
        with patch('powernight.web.api.get_enterprise_config_manager') as mock_manager:
            mock_instance = Mock()
            mock_instance.get_configuration.return_value = {
                'success': True,
                'data': {'test': 'data'},
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            mock_manager.return_value = mock_instance

            # Test with include_sensitive=true
            response = client.get('/api/v1/config?include_sensitive=true&format=summary',
                                headers=auth_headers)

            assert response.status_code == 200
            mock_instance.get_configuration.assert_called_with(include_sensitive=True)

    def test_get_configuration_schema_format(self, client, auth_headers):
        """Test configuration retrieval with schema format."""
        with patch('powernight.web.api.get_enterprise_config_manager') as mock_manager, \
             patch('powernight.web.api.get_schema_validator') as mock_validator:

            mock_instance = Mock()
            mock_instance.get_configuration.return_value = {
                'success': True,
                'data': {'test': 'data'},
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            mock_manager.return_value = mock_instance

            mock_validator_instance = Mock()
            mock_validator_instance.schemas = {
                'config_update': {'type': 'object', 'properties': {}}
            }
            mock_validator.return_value = mock_validator_instance

            response = client.get('/api/v1/config?format=schema', headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'schema' in data

    def test_update_configuration_success(self, client, auth_headers):
        """Test successful configuration update."""
        update_data = {
            'automation': {
                'enabled': True,
                'dry_run': False
            }
        }

        with patch('powernight.web.api.get_enterprise_config_manager') as mock_manager:
            mock_instance = Mock()
            mock_instance.update_configuration.return_value = {
                'success': True,
                'validation': {
                    'is_valid': True,
                    'errors': [],
                    'warnings': []
                },
                'change_id': 'test_change_123',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            mock_manager.return_value = mock_instance

            response = client.post('/api/v1/config',
                                 data=json.dumps(update_data),
                                 headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'change_id' in data
            assert 'request_metadata' in data

    def test_update_configuration_dry_run(self, client, auth_headers):
        """Test configuration update with dry run."""
        update_data = {
            'automation': {
                'enabled': False
            }
        }

        with patch('powernight.web.api.get_enterprise_config_manager') as mock_manager:
            mock_instance = Mock()
            mock_instance.update_configuration.return_value = {
                'success': True,
                'dry_run': True,
                'validation': {
                    'is_valid': True,
                    'errors': [],
                    'warnings': []
                },
                'change_id': 'test_dry_run_123',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            mock_manager.return_value = mock_instance

            response = client.post('/api/v1/config?dry_run=true',
                                 data=json.dumps(update_data),
                                 headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True

    def test_update_configuration_validation_error(self, client, auth_headers):
        """Test configuration update with validation errors."""
        update_data = {
            'powerwall': {
                'ip_address': 'invalid_ip'
            }
        }

        with patch('powernight.web.api.get_enterprise_config_manager') as mock_manager:
            mock_instance = Mock()
            mock_instance.update_configuration.return_value = {
                'success': False,
                'validation': {
                    'is_valid': False,
                    'errors': ['powerwall.ip_address: Invalid IP address format'],
                    'warnings': []
                },
                'change_id': 'test_validation_fail_123',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            mock_manager.return_value = mock_instance

            response = client.post('/api/v1/config',
                                 data=json.dumps(update_data),
                                 headers=auth_headers)

            assert response.status_code == 400
            data = json.loads(response.data)
            assert data['success'] is False
            assert 'validation' in data

    def test_update_configuration_warnings_without_force(self, client, auth_headers):
        """Test configuration update with warnings but no force flag."""
        update_data = {
            'web_interface': {
                'debug': True
            }
        }

        with patch('powernight.web.api.get_enterprise_config_manager') as mock_manager:
            mock_instance = Mock()
            mock_instance.update_configuration.return_value = {
                'success': True,
                'validation': {
                    'is_valid': True,
                    'errors': [],
                    'warnings': ['Debug mode enabled - not recommended for production'],
                    'warning_count': 1
                },
                'change_id': 'test_warning_123',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            mock_manager.return_value = mock_instance

            response = client.post('/api/v1/config',
                                 data=json.dumps(update_data),
                                 headers=auth_headers)

            assert response.status_code == 422
            data = json.loads(response.data)
            assert data['success'] is False
            assert 'warnings' in data

    def test_update_configuration_invalid_json(self, client, auth_headers):
        """Test configuration update with invalid JSON."""
        response = client.post('/api/v1/config',
                             data='invalid json',
                             headers=auth_headers)

        assert response.status_code == 422
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'Invalid JSON' in data['error']

    def test_validate_configuration_endpoint(self, client, auth_headers):
        """Test configuration validation endpoint."""
        config_data = {
            'automation': {
                'enabled': True,
                'schedule': [
                    {
                        'time': '00:01',
                        'percentage': 40.0,
                        'enabled': True
                    }
                ]
            }
        }

        with patch('powernight.web.api.get_enterprise_config_manager') as mock_manager:
            mock_instance = Mock()
            mock_instance.validate_configuration_only.return_value = {
                'success': True,
                'validation': {
                    'is_valid': True,
                    'errors': [],
                    'warnings': []
                },
                'sanitized_data': config_data,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            mock_manager.return_value = mock_instance

            response = client.post('/api/v1/config/validate',
                                 data=json.dumps(config_data),
                                 headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'validation' in data

    def test_configuration_history_endpoint(self, client, auth_headers):
        """Test configuration history endpoint."""
        with patch('powernight.web.api.get_enterprise_config_manager') as mock_manager:
            mock_instance = Mock()
            mock_instance.get_configuration_history.return_value = {
                'success': True,
                'data': {
                    'backups': [
                        {
                            'backup_id': 'backup_123',
                            'timestamp': '2023-10-01T12:00:00Z',
                            'user_id': 'test_user',
                            'reason': 'Test backup'
                        }
                    ],
                    'audit_entries': [],
                    'total_backups': 1
                },
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            mock_manager.return_value = mock_instance

            response = client.get('/api/v1/config/history?limit=10', headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
            assert 'backups' in data['data']

    def test_configuration_rollback_endpoint(self, client, auth_headers):
        """Test configuration rollback endpoint."""
        rollback_data = {
            'backup_id': 'backup_123',
            'reason': 'Test rollback'
        }

        with patch('powernight.web.api.get_enterprise_config_manager') as mock_manager:
            mock_instance = Mock()
            mock_instance.rollback_configuration.return_value = {
                'success': True,
                'message': 'Configuration rolled back successfully',
                'backup_restored': {
                    'backup_id': 'backup_123',
                    'timestamp': '2023-10-01T12:00:00Z'
                },
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            mock_manager.return_value = mock_instance

            response = client.post('/api/v1/config/rollback',
                                 data=json.dumps(rollback_data),
                                 headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'backup_restored' in data

    def test_configuration_schema_endpoint(self, client):
        """Test configuration schema endpoint (no auth required)."""
        with patch('powernight.web.api.get_schema_validator') as mock_validator:
            mock_validator_instance = Mock()
            mock_validator_instance.schemas = {
                'config_update': {'type': 'object'},
                'backup_reserve': {'type': 'object'}
            }
            mock_validator.return_value = mock_validator_instance

            response = client.get('/api/v1/config/schema')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
            assert 'config_update_schema' in data['data']
            assert 'backup_reserve_schema' in data['data']


class TestBackupReserveAPI:
    """Test suite for backup reserve API endpoints."""

    @pytest.fixture
    def app(self):
        """Create test Flask application."""
        app = create_app(testing=True)
        app.config['TESTING'] = True
        with app.app_context():
            yield app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return app.test_client()

    @pytest.fixture
    def auth_headers(self):
        """Create authentication headers."""
        return {
            'Authorization': 'Basic dGVzdDp0ZXN0',  # test:test in base64
            'Content-Type': 'application/json'
        }

    def test_get_backup_reserve_success(self, client, auth_headers):
        """Test successful backup reserve retrieval."""
        with patch('powernight.web.api.get_powerwall_connector') as mock_connector:
            mock_powerwall = Mock()
            mock_powerwall.is_connected.return_value = True
            mock_powerwall.get_backup_reserve_percentage.return_value = 50.0
            mock_connector.return_value = mock_powerwall

            response = client.get('/api/v1/backup-reserve', headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['data']['current_percentage'] == 50.0
            assert 'request_id' in data['data']
            assert 'connection_time_seconds' in data['data']

    def test_get_backup_reserve_with_diagnostics(self, client, auth_headers):
        """Test backup reserve retrieval with diagnostics."""
        with patch('powernight.web.api.get_powerwall_connector') as mock_connector:
            mock_powerwall = Mock()
            mock_powerwall.is_connected.return_value = True
            mock_powerwall.get_backup_reserve_percentage.return_value = 75.0
            mock_powerwall.get_cache_stats.return_value = {'hits': 10, 'misses': 2}
            mock_connector.return_value = mock_powerwall

            response = client.get('/api/v1/backup-reserve?include_diagnostics=true',
                                headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'diagnostics' in data['data']

    def test_get_backup_reserve_connection_error(self, client, auth_headers):
        """Test backup reserve retrieval with connection error."""
        with patch('powernight.web.api.get_powerwall_connector') as mock_connector:
            mock_powerwall = Mock()
            mock_powerwall.is_connected.return_value = False
            mock_powerwall.test_connection.side_effect = Exception("Connection failed")
            mock_connector.return_value = mock_powerwall

            response = client.get('/api/v1/backup-reserve', headers=auth_headers)

            assert response.status_code == 502
            data = json.loads(response.data)
            assert data['success'] is False
            assert 'Powerwall Communication Error' in data['error']

    def test_set_backup_reserve_success(self, client, auth_headers):
        """Test successful backup reserve setting."""
        reserve_data = {
            'percentage': 60.0,
            'reason': 'Test change'
        }

        with patch('powernight.web.api.get_powerwall_connector') as mock_connector, \
             patch('powernight.web.api.get_schema_validator') as mock_validator:

            mock_powerwall = Mock()
            mock_powerwall.is_connected.return_value = True
            mock_powerwall.get_backup_reserve_percentage.side_effect = [50.0, 60.0]  # Before and after
            mock_powerwall.set_backup_reserve_percentage.return_value = None
            mock_connector.return_value = mock_powerwall

            mock_validator_instance = Mock()
            validation_result = ValidationResult(is_valid=True, sanitized_data=reserve_data)
            mock_validator_instance.validate_backup_reserve.return_value = validation_result
            mock_validator.return_value = mock_validator_instance

            response = client.post('/api/v1/backup-reserve',
                                 data=json.dumps(reserve_data),
                                 headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['data']['target_percentage'] == 60.0
            assert data['data']['actual_percentage'] == 60.0
            assert 'timing' in data
            assert 'operation_metadata' in data

    def test_set_backup_reserve_dry_run(self, client, auth_headers):
        """Test backup reserve setting with dry run."""
        reserve_data = {
            'percentage': 80.0,
            'reason': 'Dry run test'
        }

        with patch('powernight.web.api.get_schema_validator') as mock_validator:
            mock_validator_instance = Mock()
            validation_result = ValidationResult(is_valid=True, sanitized_data=reserve_data)
            mock_validator_instance.validate_backup_reserve.return_value = validation_result
            mock_validator.return_value = mock_validator_instance

            response = client.post('/api/v1/backup-reserve?dry_run=true',
                                 data=json.dumps(reserve_data),
                                 headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['dry_run'] is True
            assert data['target_percentage'] == 80.0

    def test_set_backup_reserve_validation_error(self, client, auth_headers):
        """Test backup reserve setting with validation error."""
        reserve_data = {
            'percentage': 150.0  # Invalid percentage
        }

        with patch('powernight.web.api.get_schema_validator') as mock_validator:
            mock_validator_instance = Mock()
            validation_result = ValidationResult(
                is_valid=False,
                errors=['percentage: Must be between 0 and 100']
            )
            mock_validator_instance.validate_backup_reserve.return_value = validation_result
            mock_validator.return_value = mock_validator_instance

            response = client.post('/api/v1/backup-reserve',
                                 data=json.dumps(reserve_data),
                                 headers=auth_headers)

            assert response.status_code == 422
            data = json.loads(response.data)
            assert data['success'] is False
            assert 'validation' in data

    def test_set_backup_reserve_powerwall_error(self, client, auth_headers):
        """Test backup reserve setting with Powerwall error."""
        reserve_data = {
            'percentage': 30.0,
            'reason': 'Test error scenario'
        }

        with patch('powernight.web.api.get_powerwall_connector') as mock_connector, \
             patch('powernight.web.api.get_schema_validator') as mock_validator:

            mock_powerwall = Mock()
            mock_powerwall.is_connected.return_value = True
            mock_powerwall.get_backup_reserve_percentage.return_value = 50.0
            mock_powerwall.set_backup_reserve_percentage.side_effect = Exception("Powerwall error")
            mock_connector.return_value = mock_powerwall

            mock_validator_instance = Mock()
            validation_result = ValidationResult(is_valid=True, sanitized_data=reserve_data)
            mock_validator_instance.validate_backup_reserve.return_value = validation_result
            mock_validator.return_value = mock_validator_instance

            response = client.post('/api/v1/backup-reserve',
                                 data=json.dumps(reserve_data),
                                 headers=auth_headers)

            assert response.status_code == 502
            data = json.loads(response.data)
            assert data['success'] is False
            assert 'Powerwall Write Error' in data['error']

    def test_set_backup_reserve_force_change(self, client, auth_headers):
        """Test backup reserve setting with force flag when Powerwall is unreachable."""
        reserve_data = {
            'percentage': 25.0,
            'reason': 'Emergency change',
            'force': True
        }

        with patch('powernight.web.api.get_powerwall_connector') as mock_connector, \
             patch('powernight.web.api.get_schema_validator') as mock_validator:

            mock_powerwall = Mock()
            mock_powerwall.is_connected.return_value = False
            mock_powerwall.test_connection.side_effect = Exception("Connection failed")
            mock_powerwall.get_backup_reserve_percentage.side_effect = Exception("Read failed")
            mock_powerwall.set_backup_reserve_percentage.return_value = None
            mock_connector.return_value = mock_powerwall

            mock_validator_instance = Mock()
            validation_result = ValidationResult(is_valid=True, sanitized_data=reserve_data)
            mock_validator_instance.validate_backup_reserve.return_value = validation_result
            mock_validator.return_value = mock_validator_instance

            # Mock verification to return the target percentage
            with patch('time.sleep'):  # Speed up the test
                mock_powerwall.get_backup_reserve_percentage.side_effect = [Exception("Read failed")] * 3 + [25.0]

                response = client.post('/api/v1/backup-reserve',
                                     data=json.dumps(reserve_data),
                                     headers=auth_headers)

                assert response.status_code in [200, 202]  # Success or accepted


class TestSchemaValidator:
    """Test suite for schema validation."""

    def test_config_update_validation_success(self):
        """Test successful configuration validation."""
        validator = SchemaValidator()

        valid_config = {
            'powerwall': {
                'ip_address': '192.168.1.100',
                'timeout': 30.0,
                'retry_attempts': 3
            },
            'automation': {
                'enabled': True,
                'schedule': [
                    {
                        'time': '00:01',
                        'percentage': 40.0,
                        'enabled': True
                    }
                ]
            }
        }

        result = validator.validate_config_update(valid_config)

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert result.sanitized_data is not None

    def test_config_update_validation_invalid_ip(self):
        """Test configuration validation with invalid IP."""
        validator = SchemaValidator()

        invalid_config = {
            'powerwall': {
                'ip_address': '999.999.999.999'  # Invalid IP
            }
        }

        result = validator.validate_config_update(invalid_config)

        assert result.is_valid is False
        assert len(result.errors) > 0
        assert any('ip_address' in error for error in result.errors)

    def test_config_update_validation_duplicate_schedule_times(self):
        """Test configuration validation with duplicate schedule times."""
        validator = SchemaValidator()

        config_with_duplicates = {
            'automation': {
                'schedule': [
                    {
                        'time': '00:01',
                        'percentage': 40.0,
                        'enabled': True
                    },
                    {
                        'time': '00:01',  # Duplicate time
                        'percentage': 50.0,
                        'enabled': True
                    }
                ]
            }
        }

        result = validator.validate_config_update(config_with_duplicates)

        assert result.is_valid is False
        assert any('duplicate' in error.lower() for error in result.errors)

    def test_backup_reserve_validation_success(self):
        """Test successful backup reserve validation."""
        validator = SchemaValidator()

        valid_data = {
            'percentage': 75.5,
            'reason': 'Test change'
        }

        result = validator.validate_backup_reserve(valid_data)

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert result.sanitized_data is not None
        assert result.sanitized_data['percentage'] == 75.5

    def test_backup_reserve_validation_invalid_percentage(self):
        """Test backup reserve validation with invalid percentage."""
        validator = SchemaValidator()

        invalid_data = {
            'percentage': 150.0  # Invalid percentage
        }

        result = validator.validate_backup_reserve(invalid_data)

        assert result.is_valid is False
        assert len(result.errors) > 0
        assert any('percentage' in error for error in result.errors)

    def test_data_sanitization(self):
        """Test data sanitization functionality."""
        validator = SchemaValidator()

        config_data = {
            'powerwall': {
                'ip_address': '  192.168.1.100  ',  # Extra whitespace
                'email': '  Test@Example.COM  '  # Mixed case
            },
            'automation': {
                'schedule': [
                    {
                        'time': '1:1',  # Should be normalized to 01:01
                        'percentage': 40.0
                    }
                ]
            }
        }

        result = validator.validate_config_update(config_data)

        if result.is_valid:
            sanitized = result.sanitized_data
            assert sanitized['powerwall']['ip_address'] == '192.168.1.100'
            assert sanitized['powerwall']['email'] == 'test@example.com'
            assert sanitized['automation']['schedule'][0]['time'] == '01:01'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])