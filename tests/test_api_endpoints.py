"""
Comprehensive API endpoint tests for PowerNight application.
Tests all API endpoints with proper authentication and profile handling.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from powernight.web import create_app
from powernight.core.config import PowerNightConfig, PowerwallSettings, AutomationSettings, WebInterfaceSettings, LoggingSettings, MonitoringSettings, create_dummy_config


@pytest.fixture
def app():
    """Create test Flask application."""
    config = create_dummy_config()
    app = create_app(config, testing=True)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def mock_config():
    """Create mock configuration."""
    return PowerNightConfig(
        powerwall=PowerwallSettings(
            email="test@example.com",
            password="test123",
            verify_ssl=False
        ),
        automation=AutomationSettings(
            enabled=True,
        ),
        web_interface=WebInterfaceSettings(
            host="0.0.0.0",
            port=5001,
            debug=False
        ),
        logging=LoggingSettings(
            level="INFO",
            file_path="logs/powernight.log"
        ),
        monitoring=MonitoringSettings(
            enabled=True,
            health_check_interval=300.0
        )
    )


class TestStatusAPI:
    """Test /api/v1/status endpoint."""
    
    def test_status_demo_profile(self, client, mock_config):
        """Test status endpoint with demo profile."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
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
    
    def test_status_gruber_eg_profile(self, client, mock_config):
        """Test status endpoint with Gruber EG profile."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            response = client.get('/api/v1/status', headers={
                'X-Powerwall-Profile': 'gruber-eg',
            })
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert data['data']['system']['active_profile'] == 'gruber-eg'
            assert data['data']['powerwall']['name'] == 'Gruber EG'
            assert data['data']['powerwall']['backup_reserve_percentage'] == 35.0


class TestBackupReserveAPI:
    """Test /api/v1/backup-reserve endpoint."""
    
    def test_get_backup_reserve_demo(self, client, mock_config):
        """Test GET backup reserve for demo profile."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            response = client.get('/api/v1/backup-reserve', headers={
                'X-Powerwall-Profile': 'demo',
            })
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert data['data']['backup_reserve_percentage'] == 20.0
            assert data['data']['powerwall_name'] == 'Demo Powerwall'
            assert data['data']['demo_mode'] is True
    
    def test_get_backup_reserve_gruber_eg(self, client, mock_config):
        """Test GET backup reserve for Gruber EG profile."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            response = client.get('/api/v1/backup-reserve', headers={
                'X-Powerwall-Profile': 'gruber-eg',
            })
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert data['data']['backup_reserve_percentage'] == 35.0
            assert data['data']['powerwall_name'] == 'Gruber EG'
            assert data['data']['demo_mode'] is False
    
    def test_set_backup_reserve_demo(self, client, mock_config):
        """Test POST backup reserve for demo profile."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            response = client.post('/api/v1/backup-reserve', 
                headers={
                    'X-Powerwall-Profile': 'demo',
                        'Content-Type': 'application/json'
                },
                data=json.dumps({'backup_reserve_percentage': 25.0})
            )
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert 'message' in data


class TestSchedulesAPI:
    """Test /api/v1/schedules endpoint."""
    
    def test_get_schedules_demo(self, client, mock_config):
        """Test GET schedules for demo profile."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            response = client.get('/api/v1/schedules', headers={
                'X-Powerwall-Profile': 'demo',
            })
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert 'data' in data
            assert len(data['data']) >= 2  # At least 2 default schedules
            assert data['powerwall_name'] == 'Demo Powerwall'
            assert data['demo_mode'] is True
    
    def test_get_schedules_gruber_eg(self, client, mock_config):
        """Test GET schedules for Gruber EG profile."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            response = client.get('/api/v1/schedules', headers={
                'X-Powerwall-Profile': 'gruber-eg',
            })
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert 'data' in data
            assert len(data['data']) >= 2  # At least 2 default schedules
            assert data['powerwall_name'] == 'Gruber EG'
            assert data['demo_mode'] is False
    
    def test_create_schedule_demo(self, client, mock_config):
        """Test POST create schedule for demo profile."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            schedule_data = {
                'name': 'Test Schedule',
                'time': '14:30',
                'reserve_percentage': 30,
                'days': ['monday', 'tuesday', 'wednesday']
            }
            
            response = client.post('/api/v1/schedules',
                headers={
                    'X-Powerwall-Profile': 'demo',
                        'Content-Type': 'application/json'
                },
                data=json.dumps(schedule_data)
            )
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert 'data' in data
            assert data['data']['name'] == 'Test Schedule'
    
    def test_update_schedule_demo(self, client, mock_config):
        """Test PUT update schedule for demo profile."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            schedule_data = {
                'name': 'Updated Schedule',
                'time': '15:00',
                'reserve_percentage': 40,
                'days': ['monday', 'tuesday', 'wednesday', 'thursday']
            }
            
            response = client.put('/api/v1/schedules/schedule_1',
                headers={
                    'X-Powerwall-Profile': 'demo',
                        'Content-Type': 'application/json'
                },
                data=json.dumps(schedule_data)
            )
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert 'data' in data
            assert data['data']['name'] == 'Updated Schedule'
    
    def test_delete_schedule_demo(self, client, mock_config):
        """Test DELETE schedule for demo profile."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            response = client.delete('/api/v1/schedules/schedule_1',
                headers={
                    'X-Powerwall-Profile': 'demo',
                    }
            )
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True


class TestAutomationAPI:
    """Test /api/v1/automation endpoints."""
    
    def test_get_automation_status_demo(self, client, mock_config):
        """Test GET automation status for demo profile."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            response = client.get('/api/v1/automation/status', headers={
                'X-Powerwall-Profile': 'demo',
            })
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert 'data' in data
            assert 'enabled' in data['data']
            assert data['powerwall_name'] == 'Demo Powerwall'
    
    def test_toggle_automation_demo(self, client, mock_config):
        """Test POST toggle automation for demo profile."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            response = client.post('/api/v1/automation/toggle',
                headers={
                    'X-Powerwall-Profile': 'demo',
                        'Content-Type': 'application/json'
                },
                data=json.dumps({'enabled': False})
            )
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert 'data' in data
            assert data['data']['enabled'] is False


class TestActivityAPI:
    """Test /api/v1/activity endpoint."""
    
    def test_get_activity_demo(self, client, mock_config):
        """Test GET activity for demo profile."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            response = client.get('/api/v1/activity', headers={
                'X-Powerwall-Profile': 'demo',
            })
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert 'data' in data
            assert isinstance(data['data'], list)
            assert data['powerwall_name'] == 'Demo Powerwall'
            assert data['demo_mode'] is True
    
    def test_get_activity_gruber_eg(self, client, mock_config):
        """Test GET activity for Gruber EG profile."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            response = client.get('/api/v1/activity', headers={
                'X-Powerwall-Profile': 'gruber-eg',
            })
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert 'data' in data
            assert isinstance(data['data'], list)
            assert data['powerwall_name'] == 'Gruber EG'
            assert data['demo_mode'] is False


class TestConfigAPI:
    """Test /api/v1/config endpoint."""
    
    def test_get_config(self, client, mock_config):
        """Test GET configuration."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            response = client.get('/api/v1/config')
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert 'data' in data
            assert 'powerwall' in data['data']
            assert 'automation' in data['data']
    
    def test_update_config(self, client, mock_config):
        """Test POST update configuration."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            with patch('powernight.web.api.config_manager.EnterpriseConfigManager.update_configuration') as mock_update:
                mock_update.return_value = {'success': True}
                
                config_data = {
                    'powerwall': {
                        'ip_address': '10.0.0.31',
                        'email': 'test@example.com',
                        'password': 'newpassword'
                    }
                }
                
                response = client.post('/api/v1/config',
                    headers={'Content-Type': 'application/json'},
                    data=json.dumps(config_data)
                )
                
                assert response.status_code == 200
                data = response.get_json()
                assert data['success'] is True


class TestTestConnectionAPI:
    """Test /api/v1/test-connection endpoint."""
    
    def test_test_connection_demo(self, client, mock_config):
        """Test connection test for demo profile."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            response = client.post('/api/v1/test-connection',
                headers={
                    'X-Powerwall-Profile': 'demo',
                        'Content-Type': 'application/json'
                },
                data=json.dumps({'ip_address': '10.0.0.30'})
            )
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert 'message' in data
    
    def test_test_connection_gruber_eg(self, client, mock_config):
        """Test connection test for Gruber EG profile."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            response = client.post('/api/v1/test-connection',
                headers={
                    'X-Powerwall-Profile': 'gruber-eg',
                        'Content-Type': 'application/json'
                },
                data=json.dumps({'ip_address': '10.0.0.30'})
            )
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert 'message' in data


class TestHealthAPI:
    """Test /api/v1/health endpoint."""
    
    def test_health_endpoint(self, client):
        """Test health endpoint."""
        response = client.get('/api/v1/health')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'status' in data
        assert data['status'] == 'healthy'


class TestErrorHandling:
    """Test API error handling."""
    
    def test_missing_headers(self, client, mock_config):
        """Test API calls without profile headers."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            response = client.get('/api/v1/backup-reserve')
            
            # Should still work with default profile
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
    
    def test_invalid_json(self, client, mock_config):
        """Test API calls with invalid JSON."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            response = client.post('/api/v1/backup-reserve',
                headers={
                    'X-Powerwall-Profile': 'demo',
                        'Content-Type': 'application/json'
                },
                data='invalid json'
            )
            
            assert response.status_code == 400
            data = response.get_json()
            assert data['success'] is False
            assert 'error' in data
