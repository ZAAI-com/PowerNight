"""
Integration tests for PowerNight application.
Tests end-to-end functionality, API integration, and system behavior.
"""

import pytest
import json
import time
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

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


class TestWebInterfaceIntegration:
    """Test web interface integration."""
    
    def test_web_interface_routes(self, client):
        """Test all web interface routes are accessible."""
        routes = [
            '/',
            '/dashboard',
            '/scheduling',
            '/logs',
            '/version'
        ]
        
        for route in routes:
            response = client.get(route)
            assert response.status_code in [200, 302]  # 302 for redirects
    
    def test_web_interface_static_files(self, client):
        """Test static files are served correctly."""
        static_files = [
            '/static/css/app.css',
            '/static/css/dashboard.css',
            '/static/css/scheduling.css',
            '/static/js/api.js',
            '/static/js/selector.js',
            '/static/js/dashboard-page.js',
            '/static/js/scheduling-page.js',
            '/static/js/logs-page.js',
            '/static/js/validation.js',
            '/static/js/ui.js'
        ]
        
        for file_path in static_files:
            response = client.get(file_path)
            assert response.status_code == 200
            assert response.content_type.startswith('text/') or response.content_type.startswith('application/')
    
    def test_web_interface_templates(self, client):
        """Test templates render correctly."""
        with patch('powernight.web.api.get_config') as mock_get_config:
            mock_config = PowerNightConfig(
                powerwall=PowerwallSettings(ip_address="10.0.0.30"),
                automation=AutomationSettings(enabled=True),
                web_interface=WebInterfaceSettings(host="0.0.0.0", port=5001),
                logging=LoggingSettings(level="INFO"),
                monitoring=MonitoringSettings(enabled=True)
            )
            mock_get_config.return_value = mock_config
            
            # Test dashboard template
            response = client.get('/dashboard')
            assert response.status_code == 200
            assert b'PowerNight Dashboard' in response.data
            
            # Test scheduling template
            response = client.get('/scheduling')
            assert response.status_code == 200
            assert b'PowerNight Scheduling' in response.data
            
            
            # Test logs template
            response = client.get('/logs')
            assert response.status_code == 200
            assert b'PowerNight Logs' in response.data


class TestAPIWebIntegration:
    """Test API and web interface integration."""
    
    def test_api_web_consistency(self, client, mock_config):
        """Test API responses are consistent with web interface expectations."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'demo',
            }
            
            # Test that API responses contain expected fields for web interface
            response = client.get('/api/v1/status', headers=headers)
            assert response.status_code == 200
            data = response.get_json()
            
            # Check required fields for web interface
            assert 'data' in data
            assert 'powerwall' in data['data']
            assert 'backup_reserve_percentage' in data['data']['powerwall']
            assert 'connected' in data['data']['powerwall']
            assert 'status' in data['data']['powerwall']
    
    def test_api_headers_handling(self, client, mock_config):
        """Test API correctly handles profile headers."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            # Test with demo profile
            headers = {
                'X-Powerwall-Profile': 'demo',
                'X-Powerwall-Email': 'demo@example.com'
            }
            
            response = client.get('/api/v1/backup-reserve', headers=headers)
            assert response.status_code == 200
            data = response.get_json()
            assert data['data']['demo_mode'] is True
            
            # Test with Gruber EG profile
            headers = {
                'X-Powerwall-Profile': 'gruber-eg',
                'X-Powerwall-Email': 'gruber@example.com'
            }
            
            response = client.get('/api/v1/backup-reserve', headers=headers)
            assert response.status_code == 200
            data = response.get_json()
            assert data['data']['demo_mode'] is False
            assert data['data']['powerwall_name'] == 'Gruber EG'


class TestProfileSwitchingIntegration:
    """Test profile switching integration."""
    
    def test_profile_switching_consistency(self, client, mock_config):
        """Test profile switching maintains consistency across all endpoints."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            # Test demo profile
            demo_headers = {
                'X-Powerwall-Profile': 'demo',
            }
            
            # Test Gruber EG profile
            gruber_headers = {
                'X-Powerwall-Profile': 'gruber-eg',
            }
            
            endpoints = [
                '/api/v1/status',
                '/api/v1/backup-reserve',
                '/api/v1/schedules',
                '/api/v1/activity',
                '/api/v1/automation/status'
            ]
            
            for endpoint in endpoints:
                # Test demo profile
                response = client.get(endpoint, headers=demo_headers)
                assert response.status_code == 200
                demo_data = response.get_json()
                
                # Test Gruber EG profile
                response = client.get(endpoint, headers=gruber_headers)
                assert response.status_code == 200
                gruber_data = response.get_json()
                
                # Verify different profiles return different data
                if 'powerwall_name' in demo_data:
                    assert demo_data['powerwall_name'] == 'Demo Powerwall'
                if 'powerwall_name' in gruber_data:
                    assert gruber_data['powerwall_name'] == 'Gruber EG'
    
    def test_profile_switching_schedules(self, client, mock_config):
        """Test profile switching affects schedules correctly."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            # Test demo profile schedules
            demo_headers = {
                'X-Powerwall-Profile': 'demo',
            }
            
            response = client.get('/api/v1/schedules', headers=demo_headers)
            assert response.status_code == 200
            demo_data = response.get_json()
            
            # Test Gruber EG profile schedules
            gruber_headers = {
                'X-Powerwall-Profile': 'gruber-eg',
            }
            
            response = client.get('/api/v1/schedules', headers=gruber_headers)
            assert response.status_code == 200
            gruber_data = response.get_json()
            
            # Verify different profiles have different schedules
            demo_schedules = demo_data['data']
            gruber_schedules = gruber_data['data']
            
            # Both should have schedules but with different names
            assert len(demo_schedules) > 0
            assert len(gruber_schedules) > 0
            
            # Check for profile-specific schedule names
            demo_names = [s['name'] for s in demo_schedules]
            gruber_names = [s['name'] for s in gruber_schedules]
            
            assert any('Demo' in name for name in demo_names)
            assert any('Gruber' in name for name in gruber_names)


class TestConfigurationIntegration:
    """Test configuration integration."""
    
    def test_configuration_loading(self, client):
        """Test configuration is loaded correctly."""
        with patch('powernight.web.api.get_config') as mock_get_config:
            mock_config = PowerNightConfig(
                powerwall=PowerwallSettings(ip_address="10.0.0.30"),
                automation=AutomationSettings(enabled=True),
                web_interface=WebInterfaceSettings(host="0.0.0.0", port=5001),
                logging=LoggingSettings(level="INFO"),
                monitoring=MonitoringSettings(enabled=True)
            )
            mock_get_config.return_value = mock_config
            
            response = client.get('/api/v1/status')
            assert response.status_code == 200
            mock_get_config.assert_called()
    
    def test_configuration_validation(self, client, mock_config):
        """Test configuration validation works correctly."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {'Content-Type': 'application/json'}
            
            # Test valid configuration update
            valid_config = {
                'powerwall': {
                    'ip_address': '192.168.1.100',
                    'email': 'test@example.com',
                    'password': 'newpassword'
                }
            }
            
            response = client.put('/api/v1/config', headers=headers, data=json.dumps(valid_config))
            assert response.status_code == 200
            
            # Test invalid configuration update
            invalid_config = {
                'powerwall': {
                    'ip_address': 'invalid-ip',
                    'email': 'invalid-email'
                }
            }
            
            response = client.put('/api/v1/config', headers=headers, data=json.dumps(invalid_config))
            assert response.status_code == 400


class TestErrorHandlingIntegration:
    """Test error handling integration."""
    
    def test_error_handling_consistency(self, client):
        """Test error handling is consistent across the application."""
        # Test 404 errors
        response = client.get('/nonexistent-route')
        assert response.status_code == 404
        
        # Test 405 errors (method not allowed)
        response = client.post('/api/v1/status')
        assert response.status_code == 405
        
        # Test 400 errors (bad request)
        response = client.post('/api/v1/schedules', 
                             headers={'Content-Type': 'application/json'},
                             data='invalid json')
        assert response.status_code == 400
    
    def test_error_response_format(self, client):
        """Test error responses have consistent format."""
        response = client.get('/api/v1/nonexistent')
        assert response.status_code == 404
        
        data = response.get_json()
        assert 'error' in data
        assert 'message' in data
    
    def test_graceful_degradation(self, client, mock_config):
        """Test application degrades gracefully when components fail."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            # Test with missing profile headers (should fallback to defaults)
            response = client.get('/api/v1/backup-reserve')
            assert response.status_code == 200
            
            # Test with invalid profile headers
            headers = {
                'X-Powerwall-Profile': 'invalid-profile',
                'X-Powerwall-IP': 'invalid-ip'
            }
            response = client.get('/api/v1/backup-reserve', headers=headers)
            assert response.status_code == 200


class TestPerformanceIntegration:
    """Test performance integration."""
    
    def test_response_times(self, client, mock_config):
        """Test API response times are reasonable."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'demo',
            }
            
            endpoints = [
                '/api/v1/status',
                '/api/v1/backup-reserve',
                '/api/v1/schedules',
                '/api/v1/activity'
            ]
            
            for endpoint in endpoints:
                start_time = time.time()
                response = client.get(endpoint, headers=headers)
                end_time = time.time()
                
                assert response.status_code == 200
                assert (end_time - start_time) < 1.0  # Should respond within 1 second
    
    def test_concurrent_requests(self, client, mock_config):
        """Test application handles concurrent requests."""
        import threading
        import queue
        
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'demo',
            }
            
            results = queue.Queue()
            
            def make_request():
                response = client.get('/api/v1/status', headers=headers)
                results.put(response.status_code)
            
            # Create multiple threads
            threads = []
            for _ in range(5):
                thread = threading.Thread(target=make_request)
                threads.append(thread)
                thread.start()
            
            # Wait for all threads to complete
            for thread in threads:
                thread.join()
            
            # Check all requests succeeded
            while not results.empty():
                status_code = results.get()
                assert status_code == 200


class TestDataConsistencyIntegration:
    """Test data consistency across the application."""
    
    def test_data_consistency_across_profiles(self, client, mock_config):
        """Test data is consistent across different profiles."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            profiles = [
                {'profile': 'demo', 'ip': '10.0.0.30', 'expected_name': 'Demo Powerwall'},
                {'profile': 'gruber-eg', 'ip': '10.0.0.30', 'expected_name': 'Gruber EG'}
            ]
            
            for profile_info in profiles:
                headers = {
                    'X-Powerwall-Profile': profile_info['profile'],
                    'X-Powerwall-IP': profile_info['ip']
                }
                
                # Test backup reserve consistency
                response = client.get('/api/v1/backup-reserve', headers=headers)
                assert response.status_code == 200
                data = response.get_json()
                assert data['data']['powerwall_name'] == profile_info['expected_name']
                
                # Test schedules consistency
                response = client.get('/api/v1/schedules', headers=headers)
                assert response.status_code == 200
                data = response.get_json()
                assert data['powerwall_name'] == profile_info['expected_name']
    
    def test_timestamp_consistency(self, client, mock_config):
        """Test timestamps are consistent and recent."""
        with patch('powernight.web.api.get_config', return_value=mock_config):
            headers = {
                'X-Powerwall-Profile': 'demo',
            }
            
            response = client.get('/api/v1/backup-reserve', headers=headers)
            assert response.status_code == 200
            data = response.get_json()
            
            if 'timestamp' in data:
                timestamp = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                time_diff = (now - timestamp).total_seconds()
                assert time_diff < 10  # Timestamp should be within last 10 seconds
