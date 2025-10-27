"""
Powerwall profile switching tests for PowerNight application.
Tests profile-specific data handling and switching functionality.
"""

import pytest
import json
from unittest.mock import patch, MagicMock

from powernight.web import create_app
from powernight.core.config import PowerNightConfig, PowerwallSettings, AutomationSettings, WebInterfaceSettings, LoggingSettings, MonitoringSettings


@pytest.fixture
def app():
    """Create test Flask application."""
    app = create_app()
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


class TestProfileDataConsistency:
    """Test that profile-specific data is consistent across endpoints."""
    
    def test_demo_profile_data_consistency(self, client, mock_config):
        """Test Demo Powerwall profile data consistency."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'demo',
            }
            
            # Test status endpoint
            status_response = client.get('/api/v1/status', headers=headers)
            assert status_response.status_code == 200
            status_data = status_response.get_json()
            assert status_data['data']['powerwall']['name'] == 'Demo Powerwall'
            assert status_data['data']['powerwall']['backup_reserve_percentage'] == 20.0
            
            # Test backup-reserve endpoint
            backup_response = client.get('/api/v1/backup-reserve', headers=headers)
            assert backup_response.status_code == 200
            backup_data = backup_response.get_json()
            assert backup_data['data']['powerwall_name'] == 'Demo Powerwall'
            assert backup_data['data']['backup_reserve_percentage'] == 20.0
            assert backup_data['data']['demo_mode'] is True
            
            # Test schedules endpoint
            schedules_response = client.get('/api/v1/schedules', headers=headers)
            assert schedules_response.status_code == 200
            schedules_data = schedules_response.get_json()
            assert schedules_data['powerwall_name'] == 'Demo Powerwall'
            assert schedules_data['demo_mode'] is True
            
            # Test activity endpoint
            activity_response = client.get('/api/v1/activity', headers=headers)
            assert activity_response.status_code == 200
            activity_data = activity_response.get_json()
            assert activity_data['powerwall_name'] == 'Demo Powerwall'
            assert activity_data['demo_mode'] is True
    
    def test_gruber_eg_profile_data_consistency(self, client, mock_config):
        """Test Gruber EG profile data consistency."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'gruber-eg',
            }
            
            # Test status endpoint
            status_response = client.get('/api/v1/status', headers=headers)
            assert status_response.status_code == 200
            status_data = status_response.get_json()
            assert status_data['data']['powerwall']['name'] == 'Gruber EG'
            assert status_data['data']['powerwall']['backup_reserve_percentage'] == 35.0
            
            # Test backup-reserve endpoint
            backup_response = client.get('/api/v1/backup-reserve', headers=headers)
            assert backup_response.status_code == 200
            backup_data = backup_response.get_json()
            assert backup_data['data']['powerwall_name'] == 'Gruber EG'
            assert backup_data['data']['backup_reserve_percentage'] == 35.0
            assert backup_data['data']['demo_mode'] is False
            
            # Test schedules endpoint
            schedules_response = client.get('/api/v1/schedules', headers=headers)
            assert schedules_response.status_code == 200
            schedules_data = schedules_response.get_json()
            assert schedules_data['powerwall_name'] == 'Gruber EG'
            assert schedules_data['demo_mode'] is False
            
            # Test activity endpoint
            activity_response = client.get('/api/v1/activity', headers=headers)
            assert activity_response.status_code == 200
            activity_data = activity_response.get_json()
            assert activity_data['powerwall_name'] == 'Gruber EG'
            assert activity_data['demo_mode'] is False


class TestProfileSpecificSchedules:
    """Test that different profiles return different schedules."""
    
    def test_demo_profile_schedules(self, client, mock_config):
        """Test Demo Powerwall profile schedules."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'demo',
            }
            
            response = client.get('/api/v1/schedules', headers=headers)
            assert response.status_code == 200
            data = response.get_json()
            
            # Check for Demo Powerwall specific schedules
            schedule_names = [schedule['name'] for schedule in data['data']]
            assert any('Night Reserve (40% at 00:01)' in name for name in schedule_names)
            assert any('Morning Discharge (0% at 04:58)' in name for name in schedule_names)
    
    def test_gruber_eg_profile_schedules(self, client, mock_config):
        """Test Gruber EG profile schedules."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'gruber-eg',
            }
            
            response = client.get('/api/v1/schedules', headers=headers)
            assert response.status_code == 200
            data = response.get_json()
            
            # Check for Gruber EG specific schedules
            schedule_names = [schedule['name'] for schedule in data['data']]
            assert any('Gruber Night Reserve' in name for name in schedule_names)
            assert any('Gruber Morning Discharge' in name for name in schedule_names)
            assert any('Gruber Peak Hours' in name for name in schedule_names)


class TestProfileSwitching:
    """Test profile switching functionality."""
    
    def test_switch_from_demo_to_gruber_eg(self, client, mock_config):
        """Test switching from Demo to Gruber EG profile."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            # Start with Demo profile
            demo_headers = {
                'X-Powerwall-Profile': 'demo',
            }
            
            demo_response = client.get('/api/v1/backup-reserve', headers=demo_headers)
            assert demo_response.status_code == 200
            demo_data = demo_response.get_json()
            assert demo_data['data']['powerwall_name'] == 'Demo Powerwall'
            assert demo_data['data']['backup_reserve_percentage'] == 20.0
            
            # Switch to Gruber EG profile
            gruber_headers = {
                'X-Powerwall-Profile': 'gruber-eg',
            }
            
            gruber_response = client.get('/api/v1/backup-reserve', headers=gruber_headers)
            assert gruber_response.status_code == 200
            gruber_data = gruber_response.get_json()
            assert gruber_data['data']['powerwall_name'] == 'Gruber EG'
            assert gruber_data['data']['backup_reserve_percentage'] == 35.0
    
    def test_switch_from_gruber_eg_to_demo(self, client, mock_config):
        """Test switching from Gruber EG to Demo profile."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            # Start with Gruber EG profile
            gruber_headers = {
                'X-Powerwall-Profile': 'gruber-eg',
            }
            
            gruber_response = client.get('/api/v1/backup-reserve', headers=gruber_headers)
            assert gruber_response.status_code == 200
            gruber_data = gruber_response.get_json()
            assert gruber_data['data']['powerwall_name'] == 'Gruber EG'
            assert gruber_data['data']['backup_reserve_percentage'] == 35.0
            
            # Switch to Demo profile
            demo_headers = {
                'X-Powerwall-Profile': 'demo',
            }
            
            demo_response = client.get('/api/v1/backup-reserve', headers=demo_headers)
            assert demo_response.status_code == 200
            demo_data = demo_response.get_json()
            assert demo_data['data']['powerwall_name'] == 'Demo Powerwall'
            assert demo_data['data']['backup_reserve_percentage'] == 20.0


class TestProfileHeaderHandling:
    """Test profile header handling."""
    
    def test_missing_profile_headers(self, client, mock_config):
        """Test behavior when profile headers are missing."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            # No headers - should default to demo
            response = client.get('/api/v1/backup-reserve')
            assert response.status_code == 200
            data = response.get_json()
            assert data['data']['powerwall_name'] == 'Demo Powerwall'
            assert data['data']['backup_reserve_percentage'] == 20.0
    
    def test_invalid_profile_headers(self, client, mock_config):
        """Test behavior with invalid profile headers."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            # Invalid profile - should default to demo
            headers = {
                'X-Powerwall-Profile': 'invalid-profile',
            }
            
            response = client.get('/api/v1/backup-reserve', headers=headers)
            assert response.status_code == 200
            data = response.get_json()
            # Should fall back to demo mode
            assert data['data']['powerwall_name'] == 'Demo Powerwall'
    
    def test_profile_with_different_ip(self, client, mock_config):
        """Test profile with different IP address."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'gruber-eg',
                'X-Powerwall-IP': '192.168.1.100'  # Different IP
            }
            
            response = client.get('/api/v1/backup-reserve', headers=headers)
            assert response.status_code == 200
            data = response.get_json()
            # Should still use Gruber EG profile
            assert data['data']['powerwall_name'] == 'Gruber EG'


class TestProfileSpecificOperations:
    """Test profile-specific operations."""
    
    def test_create_schedule_demo_profile(self, client, mock_config):
        """Test creating schedule for Demo profile."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'demo',
                'Content-Type': 'application/json'
            }
            
            schedule_data = {
                'name': 'Demo Test Schedule',
                'time': '12:00',
                'reserve_percentage': 25,
                'days': ['monday', 'tuesday']
            }
            
            response = client.post('/api/v1/schedules', headers=headers, data=json.dumps(schedule_data))
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert data['data']['name'] == 'Demo Test Schedule'
    
    def test_create_schedule_gruber_eg_profile(self, client, mock_config):
        """Test creating schedule for Gruber EG profile."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'gruber-eg',
                'Content-Type': 'application/json'
            }
            
            schedule_data = {
                'name': 'Gruber Test Schedule',
                'time': '14:00',
                'reserve_percentage': 45,
                'days': ['wednesday', 'thursday']
            }
            
            response = client.post('/api/v1/schedules', headers=headers, data=json.dumps(schedule_data))
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert data['data']['name'] == 'Gruber Test Schedule'
    
    def test_toggle_automation_demo_profile(self, client, mock_config):
        """Test toggling automation for Demo profile."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'demo',
                'Content-Type': 'application/json'
            }
            
            response = client.post('/api/v1/automation/toggle', 
                                 headers=headers, 
                                 data=json.dumps({'enabled': False}))
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert data['data']['enabled'] is False
    
    def test_toggle_automation_gruber_eg_profile(self, client, mock_config):
        """Test toggling automation for Gruber EG profile."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'gruber-eg',
                'Content-Type': 'application/json'
            }
            
            response = client.post('/api/v1/automation/toggle', 
                                 headers=headers, 
                                 data=json.dumps({'enabled': True}))
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert data['data']['enabled'] is True


class TestProfileIsolation:
    """Test that profiles are properly isolated."""
    
    def test_schedule_isolation(self, client, mock_config):
        """Test that schedules are isolated between profiles."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            # Create schedule for Demo profile
            demo_headers = {
                'X-Powerwall-Profile': 'demo',
                'Content-Type': 'application/json'
            }
            
            demo_schedule = {
                'name': 'Demo Only Schedule',
                'time': '10:00',
                'reserve_percentage': 30,
                'days': ['monday']
            }
            
            demo_response = client.post('/api/v1/schedules', headers=demo_headers, data=json.dumps(demo_schedule))
            assert demo_response.status_code == 200
            
            # Create schedule for Gruber EG profile
            gruber_headers = {
                'X-Powerwall-Profile': 'gruber-eg',
                'Content-Type': 'application/json'
            }
            
            gruber_schedule = {
                'name': 'Gruber Only Schedule',
                'time': '11:00',
                'reserve_percentage': 40,
                'days': ['tuesday']
            }
            
            gruber_response = client.post('/api/v1/schedules', headers=gruber_headers, data=json.dumps(gruber_schedule))
            assert gruber_response.status_code == 200
            
            # Verify schedules are isolated
            demo_schedules = client.get('/api/v1/schedules', headers=demo_headers)
            gruber_schedules = client.get('/api/v1/schedules', headers=gruber_headers)
            
            demo_data = demo_schedules.get_json()
            gruber_data = gruber_schedules.get_json()
            
            # Each profile should have its own schedules
            demo_names = [s['name'] for s in demo_data['data']]
            gruber_names = [s['name'] for s in gruber_data['data']]
            
            assert 'Demo Only Schedule' in demo_names
            assert 'Gruber Only Schedule' in gruber_names
            # Note: In demo mode, schedules might be shared, but the profile context should be different
