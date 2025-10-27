"""
Simplified tests for web application path handling to prevent Docker container path bugs.

These tests focus on the key behaviors we want to ensure:
1. No Docker paths are used by default
2. Environment variables are respected when paths exist
3. Fallback to calculated paths works correctly
"""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from powernight.web.app import create_app
from powernight.core.config.schema import PowerNightConfig, PowerwallSettings, AutomationSettings, WebInterfaceSettings, LoggingSettings, MonitoringSettings


def create_test_config():
    """Create a test configuration."""
    return PowerNightConfig(
        powerwall=PowerwallSettings(
            tesla_email="test@example.com"
        ),
        automation=AutomationSettings(enabled=False),
        web_interface=WebInterfaceSettings(enabled=True),
        logging=LoggingSettings(file_path="logs/powernight.log"),
        monitoring=MonitoringSettings(enabled=False)
    )


class TestWebAppPathHandling:
    """Test web application path handling in different environments."""

    def test_create_app_does_not_use_docker_paths_by_default(self):
        """Test that create_app does not use Docker paths by default."""
        config = create_test_config()
        
        # Clear any existing environment variable
        with patch.dict(os.environ, {}, clear=True):
            # Mock the auth API initialization to avoid actual setup
            with patch('powernight.web.app.init_auth_api'):
                # Mock blueprint registrations
                with patch('powernight.web.app.main_blueprint'), \
                     patch('powernight.web.app.config_blueprint'), \
                     patch('powernight.web.app.logs_blueprint'), \
                     patch('powernight.web.app.tasks_blueprint'):
                    
                    # Create the app
                    app = create_app(config)
                    
                    # Verify static folder is NOT a Docker path
                    assert app.static_folder != "/app/dist"
                    assert not app.static_folder.startswith("/app/")
                    
                    # Should be a valid path
                    assert app.static_folder is not None
                    assert app.static_url_path == "/static"

    def test_create_app_respects_environment_variable_when_path_exists(self):
        """Test that create_app respects POWERNIGHT_STATIC_PATH when the path exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create the directory so it exists
            custom_static_path = str(Path(temp_dir) / "custom_static")
            Path(custom_static_path).mkdir()
            
            config = create_test_config()
            
            # Set environment variable
            with patch.dict(os.environ, {'POWERNIGHT_STATIC_PATH': custom_static_path}):
                # Mock the auth API initialization to avoid actual setup
                with patch('powernight.web.app.init_auth_api'):
                    # Mock blueprint registrations
                    with patch('powernight.web.app.main_blueprint'), \
                         patch('powernight.web.app.config_blueprint'), \
                         patch('powernight.web.app.logs_blueprint'), \
                         patch('powernight.web.app.tasks_blueprint'):
                        
                        # Create the app
                        app = create_app(config)
                        
                        # Verify static folder uses environment variable
                        assert app.static_folder == custom_static_path

    def test_create_app_falls_back_when_environment_path_does_not_exist(self):
        """Test that create_app falls back to calculated path when environment path doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Don't create the directory so it doesn't exist
            nonexistent_path = str(Path(temp_dir) / "nonexistent" / "static")
            
            config = create_test_config()
            
            # Set environment variable to nonexistent path
            with patch.dict(os.environ, {'POWERNIGHT_STATIC_PATH': nonexistent_path}):
                # Mock the auth API initialization to avoid actual setup
                with patch('powernight.web.app.init_auth_api'):
                    # Mock blueprint registrations
                    with patch('powernight.web.app.main_blueprint'), \
                         patch('powernight.web.app.config_blueprint'), \
                         patch('powernight.web.app.logs_blueprint'), \
                         patch('powernight.web.app.tasks_blueprint'):
                        
                        # Create the app
                        app = create_app(config)
                        
                        # Should fall back to calculated path (not the nonexistent one)
                        assert app.static_folder != nonexistent_path
                        assert app.static_folder is not None
                        assert not app.static_folder.startswith("/app/")

    def test_create_app_handles_empty_environment_variable(self):
        """Test that create_app handles empty environment variable gracefully."""
        config = create_test_config()
        
        # Set empty environment variable
        with patch.dict(os.environ, {'POWERNIGHT_STATIC_PATH': ''}):
            # Mock the auth API initialization to avoid actual setup
            with patch('powernight.web.app.init_auth_api'):
                # Mock blueprint registrations
                with patch('powernight.web.app.main_blueprint'), \
                     patch('powernight.web.app.config_blueprint'), \
                     patch('powernight.web.app.logs_blueprint'), \
                     patch('powernight.web.app.tasks_blueprint'):
                    
                    # Create the app
                    app = create_app(config)
                    
                    # Should fall back to calculated path
                    assert app.static_folder is not None
                    assert not app.static_folder.startswith("/app/")

    def test_create_app_works_with_relative_paths_in_config(self):
        """Test that create_app works with relative paths in configuration."""
        config = create_test_config()
        
        # Verify the config uses relative paths
        assert config.logging.file_path == "logs/powernight.log"
        assert not config.logging.file_path.startswith("/app/")
        
        # Clear any existing environment variable
        with patch.dict(os.environ, {}, clear=True):
            # Mock the auth API initialization to avoid actual setup
            with patch('powernight.web.app.init_auth_api'):
                # Mock blueprint registrations
                with patch('powernight.web.app.main_blueprint'), \
                     patch('powernight.web.app.config_blueprint'), \
                     patch('powernight.web.app.logs_blueprint'), \
                     patch('powernight.web.app.tasks_blueprint'):
                    
                    # Create the app
                    app = create_app(config)
                    
                    # Should work successfully
                    assert app is not None
                    assert app.static_folder is not None
                    assert app.static_url_path == "/static"
                    assert app.template_folder == "templates"

    def test_create_app_initializes_all_components_correctly(self):
        """Test that create_app initializes all components correctly."""
        config = create_test_config()
        
        # Clear any existing environment variable
        with patch.dict(os.environ, {}, clear=True):
            # Mock the auth API initialization to avoid actual setup
            with patch('powernight.web.app.init_auth_api') as mock_init_auth:
                # Mock blueprint registrations
                with patch('powernight.web.app.main_blueprint'), \
                     patch('powernight.web.app.config_blueprint'), \
                     patch('powernight.web.app.logs_blueprint'), \
                     patch('powernight.web.app.tasks_blueprint'):
                    
                    # Create the app
                    app = create_app(config)
                    
                    # Verify all components were initialized
                    assert app is not None
                    assert app.static_folder is not None
                    assert app.static_url_path == "/static"
                    assert app.template_folder == "templates"
                    
                    # Verify auth API was initialized
                    mock_init_auth.assert_called_once_with(app)

    def test_create_app_uses_consistent_paths_across_calls(self):
        """Test that create_app uses consistent paths across multiple calls."""
        config = create_test_config()
        
        # Clear any existing environment variable
        with patch.dict(os.environ, {}, clear=True):
            # Mock the auth API initialization to avoid actual setup
            with patch('powernight.web.app.init_auth_api'):
                # Mock blueprint registrations
                with patch('powernight.web.app.main_blueprint'), \
                     patch('powernight.web.app.config_blueprint'), \
                     patch('powernight.web.app.logs_blueprint'), \
                     patch('powernight.web.app.tasks_blueprint'):
                    
                    # Create multiple apps
                    app1 = create_app(config)
                    app2 = create_app(config)
                    
                    # Should use same paths each time
                    assert app1.static_folder == app2.static_folder
                    assert app1.static_url_path == app2.static_url_path
                    assert app1.template_folder == app2.template_folder
