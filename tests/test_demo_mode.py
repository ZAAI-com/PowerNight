"""
Demo mode functionality tests for PowerNight application.
Tests demo mode behavior, simulated data, and demo-specific features.
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


class TestDemoModeDetection:
    """Test demo mode detection logic."""
    
    def test_demo_mode_detection_by_profile(self, client, mock_config):
        """Test demo mode detection by profile ID."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'demo',
            }
            
            response = client.get('/api/v1/backup-reserve', headers=headers)
            assert response.status_code == 200
            data = response.get_json()
            assert data['data']['demo_mode'] is True
            assert 'Demo mode - using simulated data' in data['data']['message']
    
    def test_demo_mode_detection_by_ip(self, client, mock_config):
        """Test demo mode detection by IP address."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'test-profile',
            }
            
            response = client.get('/api/v1/backup-reserve', headers=headers)
            assert response.status_code == 200
            data = response.get_json()
            assert data['data']['demo_mode'] is True
    
    def test_non_demo_mode_detection(self, client, mock_config):
        """Test non-demo mode detection."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'gruber-eg',
            }
            
            response = client.get('/api/v1/backup-reserve', headers=headers)
            assert response.status_code == 200
            data = response.get_json()
            assert data['data']['demo_mode'] is False
            assert 'Simulated data for Gruber EG' in data['data']['message']


class TestDemoModeData:
    """Test demo mode data generation."""
    
    def test_demo_backup_reserve_data(self, client, mock_config):
        """Test demo backup reserve data."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'demo',
            }
            
            response = client.get('/api/v1/backup-reserve', headers=headers)
            assert response.status_code == 200
            data = response.get_json()
            
            assert data['data']['backup_reserve_percentage'] == 20.0
            assert data['data']['connected'] is False
            assert data['data']['powerwall_name'] == 'Demo Powerwall'
            assert data['data']['profile_id'] == 'demo'
    
    def test_demo_schedules_data(self, client, mock_config):
        """Test demo schedules data."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'demo',
            }
            
            response = client.get('/api/v1/schedules', headers=headers)
            assert response.status_code == 200
            data = response.get_json()
            
            assert len(data['data']) >= 2  # At least 2 default schedules
            assert data['demo_mode'] is True
            assert data['powerwall_name'] == 'Demo Powerwall'
            
            # Check for specific demo schedules
            schedule_names = [s['name'] for s in data['data']]
            assert any('Night Reserve (40% at 00:01)' in name for name in schedule_names)
            assert any('Morning Discharge (0% at 04:58)' in name for name in schedule_names)
    
    def test_demo_activity_data(self, client, mock_config):
        """Test demo activity data."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'demo',
            }
            
            response = client.get('/api/v1/activity', headers=headers)
            assert response.status_code == 200
            data = response.get_json()
            
            assert isinstance(data['data'], list)
            assert len(data['data']) > 0
            assert data['demo_mode'] is True
            assert data['powerwall_name'] == 'Demo Powerwall'
            
            # Check activity structure
            for activity in data['data']:
                assert 'id' in activity
                assert 'timestamp' in activity
                assert 'type' in activity
                assert 'message' in activity
                assert 'level' in activity
    
    def test_demo_automation_status_data(self, client, mock_config):
        """Test demo automation status data."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'demo',
            }
            
            response = client.get('/api/v1/automation/status', headers=headers)
            assert response.status_code == 200
            data = response.get_json()
            
            assert 'data' in data
            assert 'enabled' in data['data']
            assert 'total_jobs' in data['data']
            assert 'enabled_jobs' in data['data']
            assert data['powerwall_name'] == 'Demo Powerwall'


class TestDemoModeOperations:
    """Test demo mode operations."""
    
    def test_demo_schedule_creation(self, client, mock_config):
        """Test creating schedules in demo mode."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'demo',
                'Content-Type': 'application/json'
            }
            
            schedule_data = {
                'name': 'Demo Test Schedule',
                'time': '15:30',
                'reserve_percentage': 25,
                'days': ['monday', 'wednesday', 'friday']
            }
            
            response = client.post('/api/v1/schedules', headers=headers, data=json.dumps(schedule_data))
            assert response.status_code == 200
            data = response.get_json()
            
            assert data['success'] is True
            assert data['data']['name'] == 'Demo Test Schedule'
            assert data['data']['time'] == '15:30'
            assert data['data']['reserve_percentage'] == 25
            assert data['data']['days'] == ['monday', 'wednesday', 'friday']
            assert data['demo_mode'] is True
    
    def test_demo_schedule_update(self, client, mock_config):
        """Test updating schedules in demo mode."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'demo',
                'Content-Type': 'application/json'
            }
            
            schedule_data = {
                'name': 'Updated Demo Schedule',
                'time': '16:00',
                'reserve_percentage': 35,
                'days': ['tuesday', 'thursday']
            }
            
            response = client.put('/api/v1/schedules/schedule_1', headers=headers, data=json.dumps(schedule_data))
            assert response.status_code == 200
            data = response.get_json()
            
            assert data['success'] is True
            assert data['data']['name'] == 'Updated Demo Schedule'
            assert data['data']['time'] == '16:00'
            assert data['data']['reserve_percentage'] == 35
            assert data['data']['days'] == ['tuesday', 'thursday']
    
    def test_demo_schedule_deletion(self, client, mock_config):
        """Test deleting schedules in demo mode."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'demo',
            }
            
            response = client.delete('/api/v1/schedules/schedule_1', headers=headers)
            assert response.status_code == 200
            data = response.get_json()
            
            assert data['success'] is True
            assert 'deleted successfully (demo mode)' in data['message']
    
    def test_demo_automation_toggle(self, client, mock_config):
        """Test toggling automation in demo mode."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'demo',
                'Content-Type': 'application/json'
            }
            
            # Toggle off
            response = client.post('/api/v1/automation/toggle', 
                                 headers=headers, 
                                 data=json.dumps({'enabled': False}))
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert data['data']['enabled'] is False
            
            # Toggle on
            response = client.post('/api/v1/automation/toggle', 
                                 headers=headers, 
                                 data=json.dumps({'enabled': True}))
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert data['data']['enabled'] is True


class TestDemoModeSimulation:
    """Test demo mode simulation features."""
    
    def test_demo_connection_test(self, client, mock_config):
        """Test connection test in demo mode."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'demo',
                'Content-Type': 'application/json'
            }
            
            response = client.post('/api/v1/test-connection', 
                                 headers=headers, 
                                 data=json.dumps({}))
            assert response.status_code == 200
            data = response.get_json()
            
            assert data['success'] is True
            assert 'message' in data
            # Should simulate success for demo IP
            assert 'success' in data['message'].lower() or 'connected' in data['message'].lower()
    
    def test_demo_backup_reserve_set(self, client, mock_config):
        """Test setting backup reserve in demo mode."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'demo',
                'Content-Type': 'application/json'
            }
            
            response = client.post('/api/v1/backup-reserve', 
                                 headers=headers, 
                                 data=json.dumps({'backup_reserve_percentage': 30.0}))
            assert response.status_code == 200
            data = response.get_json()
            
            assert data['success'] is True
            assert 'message' in data
            # Should simulate success in demo mode
            assert 'success' in data['message'].lower() or 'updated' in data['message'].lower()


class TestDemoModeConsistency:
    """Test demo mode data consistency."""
    
    def test_demo_mode_consistency_across_endpoints(self, client, mock_config):
        """Test that demo mode is consistent across all endpoints."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'demo',
            }
            
            endpoints = [
                '/api/v1/status',
                '/api/v1/backup-reserve',
                '/api/v1/schedules',
                '/api/v1/activity',
                '/api/v1/automation/status'
            ]
            
            for endpoint in endpoints:
                response = client.get(endpoint, headers=headers)
                assert response.status_code == 200
                data = response.get_json()
                
                # All endpoints should indicate demo mode
                if 'data' in data and isinstance(data['data'], dict):
                    if 'demo_mode' in data['data']:
                        assert data['data']['demo_mode'] is True
                
                # All endpoints should have consistent profile info
                if 'powerwall_name' in data:
                    assert data['powerwall_name'] == 'Demo Powerwall'
                if 'profile_id' in data:
                    assert data['profile_id'] == 'demo'
    
    def test_demo_mode_timestamp_consistency(self, client, mock_config):
        """Test that demo mode timestamps are consistent."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'demo',
            }
            
            # Get multiple responses and check timestamps are recent
            response1 = client.get('/api/v1/backup-reserve', headers=headers)
            response2 = client.get('/api/v1/schedules', headers=headers)
            
            data1 = response1.get_json()
            data2 = response2.get_json()
            
            # Check timestamps are present and recent
            if 'timestamp' in data1:
                timestamp1 = datetime.fromisoformat(data1['timestamp'].replace('Z', '+00:00'))
                assert (datetime.now(timezone.utc) - timestamp1).total_seconds() < 10
            
            if 'timestamp' in data2:
                timestamp2 = datetime.fromisoformat(data2['timestamp'].replace('Z', '+00:00'))
                assert (datetime.now(timezone.utc) - timestamp2).total_seconds() < 10


class TestDemoModeErrorHandling:
    """Test demo mode error handling."""
    
    def test_demo_mode_invalid_requests(self, client, mock_config):
        """Test demo mode handles invalid requests gracefully."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'demo',
                'Content-Type': 'application/json'
            }
            
            # Test invalid JSON
            response = client.post('/api/v1/schedules', headers=headers, data='invalid json')
            assert response.status_code == 400
            
            # Test missing required fields
            response = client.post('/api/v1/schedules', headers=headers, data=json.dumps({}))
            assert response.status_code == 200  # Demo mode should handle gracefully
            
            # Test invalid schedule ID
            response = client.put('/api/v1/schedules/invalid-id', headers=headers, data=json.dumps({'name': 'Test'}))
            assert response.status_code == 200  # Demo mode should handle gracefully
