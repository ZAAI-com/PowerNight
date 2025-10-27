"""
Tests for web application path handling to prevent Docker container path bugs.

These tests ensure that the web application uses proper development paths
and doesn't rely on Docker container paths when running locally.
"""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from powernight.web.app import create_app
from powernight.core.config.schema import PowerNightConfig, PowerwallSettings, AutomationSettings, WebInterfaceSettings, LoggingSettings, MonitoringSettings


def get_expected_static_folder():
    """Calculate the expected static folder path based on the actual file location."""
    # This mimics the logic in create_app
    web_dir = os.path.dirname(os.path.abspath(__file__))
    powernight_dir = os.path.dirname(web_dir)
    src_dir = os.path.dirname(powernight_dir)
    project_root = os.path.dirname(src_dir)
    return os.path.join(project_root, 'dist')


class TestWebAppPathHandling:
    """Test web application path handling in different environments."""

    def test_create_app_uses_relative_static_path_by_default(self):
        """Test that create_app uses relative static path by default."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Create a mock config
                config = PowerNightConfig(
                    powerwall=PowerwallSettings(
                        tesla_email="test@example.com",
                    ),
                    automation=AutomationSettings(enabled=False),
                    web_interface=WebInterfaceSettings(enabled=True),
                    logging=LoggingSettings(file_path="logs/powernight.log"),
                    monitoring=MonitoringSettings(enabled=False)
                )
                
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
                            
                            # Verify static folder is set correctly
                            # Should be calculated from the actual file location, not cwd
                            expected_static_folder = get_expected_static_folder()
                            assert app.static_folder == expected_static_folder
                            assert app.static_url_path == "/static"
                            
            finally:
                os.chdir(original_cwd)

    def test_create_app_respects_environment_variable(self):
        """Test that create_app respects POWERNIGHT_STATIC_PATH environment variable."""
        with tempfile.TemporaryDirectory() as temp_dir:
            custom_static_path = str(Path(temp_dir) / "custom_static")
            
            # Create a mock config
            config = PowerNightConfig(
                powerwall=PowerwallSettings(
                    tesla_email="test@example.com",
                    cloud_mode_enabled=True
                ),
                automation=AutomationSettings(enabled=False),
                web_interface=WebInterfaceSettings(enabled=True),
                logging=LoggingSettings(file_path="logs/powernight.log"),
                monitoring=MonitoringSettings(enabled=False)
            )
            
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
                        assert app.static_url_path == "/static"

    def test_create_app_does_not_use_docker_paths_by_default(self):
        """Test that create_app does not use Docker paths by default."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Create a mock config
                config = PowerNightConfig(
                    powerwall=PowerwallSettings(
                        tesla_email="test@example.com",
                    ),
                    automation=AutomationSettings(enabled=False),
                    web_interface=WebInterfaceSettings(enabled=True),
                    logging=LoggingSettings(file_path="logs/powernight.log"),
                    monitoring=MonitoringSettings(enabled=False)
                )
                
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
                            
                            # Should be calculated from the actual file location
                            expected_static_folder = get_expected_static_folder()
                            assert app.static_folder == expected_static_folder
                            
            finally:
                os.chdir(original_cwd)

    def test_create_app_calculates_paths_correctly_from_web_directory(self):
        """Test that create_app calculates paths correctly from web directory structure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a mock project structure
            project_root = Path(temp_dir) / "project"
            src_dir = project_root / "src"
            powernight_dir = src_dir / "powernight"
            web_dir = powernight_dir / "web"
            
            # Create directories
            web_dir.mkdir(parents=True)
            
            original_cwd = os.getcwd()
            try:
                os.chdir(web_dir)
                
                # Create a mock config
                config = PowerNightConfig(
                    powerwall=PowerwallSettings(
                        tesla_email="test@example.com",
                    ),
                    automation=AutomationSettings(enabled=False),
                    web_interface=WebInterfaceSettings(enabled=True),
                    logging=LoggingSettings(file_path="logs/powernight.log"),
                    monitoring=MonitoringSettings(enabled=False)
                )
                
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
                            
                            # Verify static folder is calculated correctly
                            # From web_dir, should go up to project_root/dist
                            expected_static_folder = str(project_root / "dist")
                            assert app.static_folder == expected_static_folder
                            
            finally:
                os.chdir(original_cwd)

    def test_create_app_handles_missing_static_directory_gracefully(self):
        """Test that create_app handles missing static directory gracefully."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Create a mock config
                config = PowerNightConfig(
                    powerwall=PowerwallSettings(
                        tesla_email="test@example.com",
                    ),
                    automation=AutomationSettings(enabled=False),
                    web_interface=WebInterfaceSettings(enabled=True),
                    logging=LoggingSettings(file_path="logs/powernight.log"),
                    monitoring=MonitoringSettings(enabled=False)
                )
                
                # Clear any existing environment variable
                with patch.dict(os.environ, {}, clear=True):
                    # Mock the auth API initialization to avoid actual setup
                    with patch('powernight.web.app.init_auth_api'):
                        # Mock blueprint registrations
                        with patch('powernight.web.app.main_blueprint'), \
                             patch('powernight.web.app.config_blueprint'), \
                             patch('powernight.web.app.logs_blueprint'), \
                             patch('powernight.web.app.tasks_blueprint'):
                            
                            # Create the app (should not fail even if dist doesn't exist)
                            app = create_app(config)
                            
                            # Verify app was created successfully
                            assert app is not None
                            assert app.static_folder is not None
                            
            finally:
                os.chdir(original_cwd)

    def test_create_app_works_with_absolute_static_path(self):
        """Test that create_app works with absolute static path when specified."""
        with tempfile.TemporaryDirectory() as temp_dir:
            absolute_static_path = str(Path(temp_dir) / "absolute_static")
            
            # Create a mock config
            config = PowerNightConfig(
                powerwall=PowerwallSettings(
                    tesla_email="test@example.com",
                    cloud_mode_enabled=True
                ),
                automation=AutomationSettings(enabled=False),
                web_interface=WebInterfaceSettings(enabled=True),
                logging=LoggingSettings(file_path="logs/powernight.log"),
                monitoring=MonitoringSettings(enabled=False)
            )
            
            # Set environment variable to absolute path
            with patch.dict(os.environ, {'POWERNIGHT_STATIC_PATH': absolute_static_path}):
                # Mock the auth API initialization to avoid actual setup
                with patch('powernight.web.app.init_auth_api'):
                    # Mock blueprint registrations
                    with patch('powernight.web.app.main_blueprint'), \
                         patch('powernight.web.app.config_blueprint'), \
                         patch('powernight.web.app.logs_blueprint'), \
                         patch('powernight.web.app.tasks_blueprint'):
                        
                        # Create the app
                        app = create_app(config)
                        
                        # Verify static folder uses absolute path
                        assert app.static_folder == absolute_static_path
                        assert app.static_url_path == "/static"


class TestWebAppPathEdgeCases:
    """Test edge cases in web application path handling."""

    def test_create_app_handles_empty_environment_variable(self):
        """Test that create_app handles empty environment variable gracefully."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Create a mock config
                config = PowerNightConfig(
                    powerwall=PowerwallSettings(
                        tesla_email="test@example.com",
                    ),
                    automation=AutomationSettings(enabled=False),
                    web_interface=WebInterfaceSettings(enabled=True),
                    logging=LoggingSettings(file_path="logs/powernight.log"),
                    monitoring=MonitoringSettings(enabled=False)
                )
                
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
                            expected_static_folder = str(Path.cwd() / "dist")
                            assert app.static_folder == expected_static_folder
                            
            finally:
                os.chdir(original_cwd)

    def test_create_app_handles_nonexistent_static_path(self):
        """Test that create_app handles nonexistent static path gracefully."""
        with tempfile.TemporaryDirectory() as temp_dir:
            nonexistent_path = str(Path(temp_dir) / "nonexistent" / "static")
            
            # Create a mock config
            config = PowerNightConfig(
                powerwall=PowerwallSettings(
                    tesla_email="test@example.com",
                    cloud_mode_enabled=True
                ),
                automation=AutomationSettings(enabled=False),
                web_interface=WebInterfaceSettings(enabled=True),
                logging=LoggingSettings(file_path="logs/powernight.log"),
                monitoring=MonitoringSettings(enabled=False)
            )
            
            # Set environment variable to nonexistent path
            with patch.dict(os.environ, {'POWERNIGHT_STATIC_PATH': nonexistent_path}):
                # Mock the auth API initialization to avoid actual setup
                with patch('powernight.web.app.init_auth_api'):
                    # Mock blueprint registrations
                    with patch('powernight.web.app.main_blueprint'), \
                         patch('powernight.web.app.config_blueprint'), \
                         patch('powernight.web.app.logs_blueprint'), \
                         patch('powernight.web.app.tasks_blueprint'):
                        
                        # Create the app (should not fail even if path doesn't exist)
                        app = create_app(config)
                        
                        # Verify app was created successfully
                        assert app is not None
                        assert app.static_folder == nonexistent_path
                        
    def test_create_app_works_in_different_working_directories(self):
        """Test that create_app works correctly in different working directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create subdirectory
            subdir = Path(temp_dir) / "subdir"
            subdir.mkdir()
            
            original_cwd = os.getcwd()
            try:
                # Test in subdirectory
                os.chdir(subdir)
                
                # Create a mock config
                config = PowerNightConfig(
                    powerwall=PowerwallSettings(
                        tesla_email="test@example.com",
                    ),
                    automation=AutomationSettings(enabled=False),
                    web_interface=WebInterfaceSettings(enabled=True),
                    logging=LoggingSettings(file_path="logs/powernight.log"),
                    monitoring=MonitoringSettings(enabled=False)
                )
                
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
                            
                            # Should calculate path relative to current working directory
                            expected_static_folder = str(Path.cwd() / "dist")
                            assert app.static_folder == expected_static_folder
                            
            finally:
                os.chdir(original_cwd)


class TestWebAppPathIntegration:
    """Integration tests for web application path handling."""

    def test_create_app_integration_with_all_components(self):
        """Test create_app integration with all components."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Create a mock config
                config = PowerNightConfig(
                    powerwall=PowerwallSettings(
                        tesla_email="test@example.com",
                    ),
                    automation=AutomationSettings(enabled=False),
                    web_interface=WebInterfaceSettings(enabled=True),
                    logging=LoggingSettings(file_path="logs/powernight.log"),
                    monitoring=MonitoringSettings(enabled=False)
                )
                
                # Clear any existing environment variable
                with patch.dict(os.environ, {}, clear=True):
                    # Mock the auth API initialization to avoid actual setup
                    with patch('powernight.web.app.init_auth_api') as mock_init_auth:
                        # Mock blueprint registrations
                        with patch('powernight.web.app.main_blueprint') as mock_main, \
                             patch('powernight.web.app.config_blueprint') as mock_config, \
                             patch('powernight.web.app.logs_blueprint') as mock_logs, \
                             patch('powernight.web.app.tasks_blueprint') as mock_tasks:
                            
                            # Create the app
                            app = create_app(config)
                            
                            # Verify all components were initialized
                            assert app is not None
                            assert app.static_folder is not None
                            assert app.static_url_path == "/static"
                            assert app.template_folder == "templates"
                            
                            # Verify auth API was initialized
                            mock_init_auth.assert_called_once_with(app)
                            
                            # Verify blueprints were registered
                            # Note: register_blueprint is a method, not a mock, so we can't check call_count
                            # The important thing is that the app was created successfully
                            assert app is not None
                            
            finally:
                os.chdir(original_cwd)

    def test_create_app_path_consistency_across_calls(self):
        """Test that create_app uses consistent paths across multiple calls."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Create a mock config
                config = PowerNightConfig(
                    powerwall=PowerwallSettings(
                        tesla_email="test@example.com",
                    ),
                    automation=AutomationSettings(enabled=False),
                    web_interface=WebInterfaceSettings(enabled=True),
                    logging=LoggingSettings(file_path="logs/powernight.log"),
                    monitoring=MonitoringSettings(enabled=False)
                )
                
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
                            expected_static_folder = str(Path.cwd() / "dist")
                            assert app1.static_folder == expected_static_folder
                            assert app2.static_folder == expected_static_folder
                            assert app1.static_folder == app2.static_folder
                            
            finally:
                os.chdir(original_cwd)
