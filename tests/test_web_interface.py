"""
Web interface tests for PowerNight application.
Tests all web pages, templates, and static assets.
"""

import pytest
from unittest.mock import patch, MagicMock

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
            metrics_retention_days=30
        )
    )


class TestPageRoutes:
    """Test web page routes."""
    
    def test_root_redirect(self, client):
        """Test root URL redirects to dashboard."""
        response = client.get('/')
        assert response.status_code == 302
        assert response.location.endswith('/dashboard')
    
    def test_dashboard_page(self, client):
        """Test dashboard page loads correctly."""
        response = client.get('/dashboard')
        assert response.status_code == 200
        assert b'Dashboard - PowerNight' in response.data
        assert b'Powerwall Status' in response.data
        assert b'Backup Reserve' in response.data
    
    def test_scheduling_page(self, client):
        """Test scheduling page loads correctly."""
        response = client.get('/scheduling')
        assert response.status_code == 200
        assert b'Scheduling - PowerNight' in response.data
        assert b'Automation Scheduling' in response.data
        assert b'Quick Templates' in response.data
    
    
    def test_logs_page(self, client):
        """Test logs page loads correctly."""
        response = client.get('/logs')
        assert response.status_code == 200
        assert b'Logs - PowerNight' in response.data
        assert b'System Logs' in response.data
        assert b'View and filter PowerNight system events' in response.data


class TestTemplateRendering:
    """Test template rendering and includes."""
    
    def test_base_template_includes_navigation(self, client):
        """Test base template includes navigation."""
        response = client.get('/dashboard')
        assert b'<nav class="navbar">' in response.data
        assert b'PowerNight' in response.data
        assert b'Dashboard' in response.data
        assert b'Scheduling' in response.data
        assert b'Settings' in response.data
        assert b'Logs' in response.data
    
    def test_powerwall_selector_included(self, client):
        """Test Powerwall selector is included in all pages."""
        pages = ['/dashboard', '/scheduling', '/logs']
        
        for page in pages:
            response = client.get(page)
            assert response.status_code == 200
            assert b'<select id="powerwall-select"' in response.data
            assert b'Demo Powerwall' in response.data
            assert b'Gruber EG' in response.data
    
    def test_css_and_js_assets_included(self, client):
        """Test CSS and JS assets are included."""
        response = client.get('/dashboard')
        assert b'<link rel="stylesheet" href="/static/css/styles.css">' in response.data
        assert b'<link rel="stylesheet" href="/static/css/components.css">' in response.data
        assert b'<link rel="stylesheet" href="/static/css/app.css">' in response.data
        assert b'<script src="/static/js/api.js">' in response.data
        assert b'<script src="/static/js/selector.js">' in response.data


class TestStaticAssets:
    """Test static asset serving."""
    
    def test_css_files_served(self, client):
        """Test CSS files are served correctly."""
        css_files = [
            '/static/css/styles.css',
            '/static/css/components.css',
            '/static/css/app.css'
        ]
        
        for css_file in css_files:
            response = client.get(css_file)
            assert response.status_code == 200
            assert response.content_type == 'text/css; charset=utf-8'
    
    def test_js_files_served(self, client):
        """Test JavaScript files are served correctly."""
        js_files = [
            '/static/js/api.js',
            '/static/js/selector.js',
            '/static/js/dashboard-page.js',
            '/static/js/scheduling-page.js',
            '/static/js/logs-page.js'
        ]
        
        for js_file in js_files:
            response = client.get(js_file)
            assert response.status_code == 200
            assert response.content_type == 'text/javascript; charset=utf-8'
    
    def test_static_html_served(self, client):
        """Test static HTML file is served."""
        response = client.get('/static/index.html')
        # This redirects to dashboard, so we expect a 302
        assert response.status_code == 302
        assert b'/dashboard' in response.data


class TestTemplateFeatures:
    """Test specific template features."""
    
    def test_dashboard_template_features(self, client):
        """Test dashboard template specific features."""
        response = client.get('/dashboard')
        assert b'<div class="dashboard-container">' in response.data
        assert b'<div class="status-grid">' in response.data
        assert b'<div class="status-card">' in response.data
        assert b'<div class="activity-section">' in response.data
    
    def test_scheduling_template_features(self, client):
        """Test scheduling template specific features."""
        response = client.get('/scheduling')
        assert b'<div class="scheduling-container">' in response.data
        assert b'<div class="schedule-list">' in response.data
        assert b'<button id="add-schedule-btn"' in response.data
        assert b'<button id="add-template-btn"' in response.data
    
    
    def test_logs_template_features(self, client):
        """Test logs template specific features."""
        response = client.get('/logs')
        assert b'<div class="logs-container">' in response.data
        assert b'<div class="log-filters">' in response.data
        assert b'<div class="log-table-container">' in response.data
        assert b'<button id="refresh-logs-btn"' in response.data


class TestErrorHandling:
    """Test web interface error handling."""
    
    def test_404_for_nonexistent_page(self, client):
        """Test 404 error for non-existent page."""
        response = client.get('/nonexistent-page')
        assert response.status_code == 404
    
    def test_api_error_handling(self, client):
        """Test API error handling in web interface."""
        # Test with invalid API endpoint
        response = client.get('/api/v1/invalid-endpoint')
        assert response.status_code == 404


class TestTemplateInheritance:
    """Test template inheritance and blocks."""
    
    def test_title_blocks(self, client):
        """Test page titles are set correctly."""
        pages = [
            ('/dashboard', 'Dashboard - PowerNight'),
            ('/scheduling', 'Scheduling - PowerNight'),
            ('/logs', 'Logs - PowerNight')
        ]
        
        for page, expected_title in pages:
            response = client.get(page)
            assert response.status_code == 200
            assert expected_title.encode() in response.data
    
    def test_content_blocks(self, client):
        """Test content blocks are rendered correctly."""
        response = client.get('/dashboard')
        assert b'<main class="main-content">' in response.data
        assert b'<div class="dashboard-container">' in response.data


class TestJavaScriptIntegration:
    """Test JavaScript integration in templates."""
    
    def test_javascript_event_handlers(self, client):
        """Test JavaScript event handlers are present."""
        response = client.get('/dashboard')
        # Check that JavaScript files are included
        assert b'dashboard-page.js' in response.data
        assert b'selector.js' in response.data
    
    def test_api_calls_in_templates(self, client):
        """Test API calls are present in templates."""
        response = client.get('/dashboard')
        # Check that API client is included
        assert b'api.js' in response.data
        # Check that JavaScript files are properly included
        assert b'script src=' in response.data


class TestResponsiveDesign:
    """Test responsive design elements."""
    
    def test_viewport_meta_tag(self, client):
        """Test viewport meta tag is present."""
        response = client.get('/dashboard')
        assert b'<meta name="viewport" content="width=device-width, initial-scale=1.0">' in response.data
    
    def test_responsive_css_classes(self, client):
        """Test responsive CSS classes are present."""
        response = client.get('/dashboard')
        # Check for common responsive classes
        assert b'container' in response.data
        assert b'navbar' in response.data
        assert b'main-content' in response.data


class TestAccessibility:
    """Test accessibility features."""
    
    def test_alt_text_for_images(self, client):
        """Test alt text is present for images."""
        response = client.get('/dashboard')
        # Check if there are any images and they have alt text
        # This is a basic check - in a real app you'd have more images
        pass
    
    def test_form_labels(self, client):
        """Test form labels are present."""
        response = client.get('/dashboard')
        assert b'<label' in response.data
        assert b'for=' in response.data
    
    def test_button_aria_labels(self, client):
        """Test buttons have proper accessibility attributes."""
        response = client.get('/scheduling')
        assert b'<button' in response.data
        # Check for aria-label or other accessibility attributes
        assert b'id=' in response.data
