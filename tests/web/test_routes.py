"""
Tests for PowerNight web routes
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from flask import Flask

# Import the application
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from powernight.web.app import create_app


@pytest.fixture
def app():
    """Create test application instance."""
    app = create_app(testing=True)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


class TestPageRoutes:
    """Test page routes for the new multi-page interface."""

    def test_root_redirect(self, client):
        """Test that root redirects to dashboard."""
        response = client.get('/')
        assert response.status_code == 302
        assert '/dashboard' in response.location

    def test_dashboard_page(self, client):
        """Test dashboard page loads correctly."""
        response = client.get('/dashboard')
        assert response.status_code == 200
        assert b'Dashboard' in response.data
        assert b'Powerwall Status' in response.data
        assert b'Backup Reserve' in response.data

    def test_scheduling_page(self, client):
        """Test scheduling page loads correctly."""
        response = client.get('/scheduling')
        assert response.status_code == 200
        assert b'Scheduling' in response.data
        assert b'Automation Status' in response.data
        assert b'Schedule Management' in response.data


    def test_logs_page(self, client):
        """Test logs page loads correctly."""
        response = client.get('/logs')
        assert response.status_code == 200
        assert b'Logs' in response.data
        assert b'System Logs' in response.data
        assert b'Log Filters' in response.data

    def test_old_interface_redirect(self, client):
        """Test that old static interface redirects to dashboard."""
        response = client.get('/static/index.html')
        assert response.status_code == 302
        assert '/dashboard' in response.location


class TestAPIRoutes:
    """Test API routes used by the new interface."""

    @patch('powernight.web.api.api.get_config')
    def test_status_endpoint(self, mock_get_config, client):
        """Test status endpoint returns valid data."""
        # Mock configuration
        mock_config = MagicMock()
        mock_config.powerwall.ip_address = '192.168.1.100'
        mock_get_config.return_value = mock_config

        response = client.get('/api/v1/status')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert 'success' in data
        assert 'data' in data
        assert 'system' in data['data']
        assert 'powerwall' in data['data']

    @patch('powernight.web.api.api.get_config')
    def test_backup_reserve_endpoint_demo_mode(self, mock_get_config, client):
        """Test backup reserve endpoint in demo mode."""
        # Mock configuration for demo mode
        mock_config = MagicMock()
        mock_config.powerwall.ip_address = '192.168.1.100'  # Demo IP
        mock_get_config.return_value = mock_config

        response = client.get('/api/v1/backup-reserve')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'demo_mode' in data['data']
        assert data['data']['demo_mode'] is True

    def test_health_endpoint(self, client):
        """Test health endpoint."""
        response = client.get('/health')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert 'status' in data
        assert 'timestamp' in data


class TestTemplateRendering:
    """Test template rendering and content."""

    def test_base_template_includes_navigation(self, client):
        """Test that base template includes navigation."""
        response = client.get('/dashboard')
        assert b'navbar' in response.data
        assert b'Dashboard' in response.data
        assert b'Scheduling' in response.data
        assert b'Settings' in response.data
        assert b'Logs' in response.data

    def test_powerwall_selector_included(self, client):
        """Test that Powerwall selector is included in all pages."""
        pages = ['/dashboard', '/scheduling', '/logs']
        
        for page in pages:
            response = client.get(page)
            assert b'powerwall-selector' in response.data
            assert b'Demo Powerwall' in response.data

    def test_css_and_js_assets_included(self, client):
        """Test that CSS and JS assets are included."""
        response = client.get('/dashboard')
        
        # Check CSS files
        assert b'app.css' in response.data
        assert b'styles.css' in response.data
        
        # Check JS files
        assert b'selector.js' in response.data
        assert b'dashboard-page.js' in response.data
        assert b'api.js' in response.data


class TestErrorHandling:
    """Test error handling in routes."""

    def test_404_for_nonexistent_page(self, client):
        """Test 404 for non-existent page."""
        response = client.get('/nonexistent-page')
        assert response.status_code == 404

    def test_api_error_handling(self, client):
        """Test API error handling."""
        # Test with invalid endpoint
        response = client.get('/api/v1/invalid-endpoint')
        assert response.status_code == 404


if __name__ == '__main__':
    pytest.main([__file__])
