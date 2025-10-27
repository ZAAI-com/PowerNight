"""
Integration tests for application startup path handling.

These tests ensure that the full application startup process uses proper
development paths and doesn't rely on Docker container paths when running locally.
"""

import os
import tempfile
import pytest
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

from powernight.app import PowerNightApp
from powernight.core.config import load_config


class TestApplicationStartupPaths:
    """Test application startup path handling in different environments."""

    def test_application_initializes_with_relative_paths(self):
        """Test that application initializes successfully with relative paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create config file with relative paths
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text("""
powerwall:
  tesla_email: test@example.com
automation:
  enabled: false
  schedule: []
web_interface:
  enabled: true
  host: 0.0.0.0
  port: 8080
logging:
  level: INFO
  file_path: logs/powernight.log
monitoring:
  enabled: false
""")
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Mock database migration to avoid actual database operations
                with patch('powernight.app.db_migration.upgrade'):
                    # Mock Powerwall connector initialization
                    with patch('powernight.app.initialize_powerwall_connector') as mock_powerwall:
                        mock_powerwall.return_value = MagicMock()
                        
                        # Mock planner to avoid actual scheduling
                        with patch('powernight.app.get_planner') as mock_planner:
                            mock_planner_instance = MagicMock()
                            mock_planner.return_value = mock_planner_instance
                            
                            # Create and initialize application
                            app = PowerNightApp()
                            success = app.initialize(str(config_path))
                            
                            # Verify initialization was successful
                            assert success
                            
                            # Verify config was loaded with relative paths
                            config = app.config_manager.get_config()
                            assert config.logging.file_path == "logs/powernight.log"
                            assert not config.logging.file_path.startswith("/app/")
                            
            finally:
                os.chdir(original_cwd)

    def test_application_does_not_use_docker_paths_by_default(self):
        """Test that application does not use Docker paths by default."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create config file
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text("""
powerwall:
  tesla_email: test@example.com
automation:
  enabled: false
  schedule: []
web_interface:
  enabled: true
  host: 0.0.0.0
  port: 8080
logging:
  level: INFO
  file_path: logs/powernight.log
monitoring:
  enabled: false
""")
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Clear any existing environment variables
                with patch.dict(os.environ, {}, clear=True):
                    # Mock database migration to avoid actual database operations
                    with patch('powernight.app.db_migration.upgrade'):
                        # Mock Powerwall connector initialization
                        with patch('powernight.app.initialize_powerwall_connector') as mock_powerwall:
                            mock_powerwall.return_value = MagicMock()
                            
                            # Mock planner to avoid actual scheduling
                            with patch('powernight.app.get_planner') as mock_planner:
                                mock_planner_instance = MagicMock()
                                mock_planner.return_value = mock_planner_instance
                                
                                # Create and initialize application
                                app = PowerNightApp()
                                success = app.initialize(str(config_path))
                                
                                # Verify initialization was successful
                                assert success
                                
                                # Verify no Docker paths were used
                                config = app.config_manager.get_config()
                                assert config.logging.file_path != "/app/logs/powernight.log"
                                assert not config.logging.file_path.startswith("/app/")
                                
            finally:
                os.chdir(original_cwd)

    def test_application_web_interface_starts_with_relative_paths(self):
        """Test that web interface starts successfully with relative paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create config file
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text("""
powerwall:
  tesla_email: test@example.com
automation:
  enabled: false
  schedule: []
web_interface:
  enabled: true
  host: 0.0.0.0
  port: 8080
logging:
  level: INFO
  file_path: logs/powernight.log
monitoring:
  enabled: false
""")
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Mock database migration to avoid actual database operations
                with patch('powernight.app.db_migration.upgrade'):
                    # Mock Powerwall connector initialization
                    with patch('powernight.app.initialize_powerwall_connector') as mock_powerwall:
                        mock_powerwall.return_value = MagicMock()
                        
                        # Mock planner to avoid actual scheduling
                        with patch('powernight.app.get_planner') as mock_planner:
                            mock_planner_instance = MagicMock()
                            mock_planner.return_value = mock_planner_instance
                            
                            # Mock Flask app creation to avoid actual web server
                            with patch('powernight.app.create_app') as mock_create_app:
                                mock_flask_app = MagicMock()
                                mock_create_app.return_value = mock_flask_app
                                
                                # Create and initialize application
                                app = PowerNightApp()
                                success = app.initialize(str(config_path))
                                
                                # Verify initialization was successful
                                assert success
                                
                                # Start web interface
                                web_success = app.start_web_interface()
                                
                                # Verify web interface started successfully
                                assert web_success
                                
                                # Verify Flask app was created
                                mock_create_app.assert_called_once()
                                
            finally:
                os.chdir(original_cwd)

    def test_application_handles_missing_directories_gracefully(self):
        """Test that application handles missing directories gracefully."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create config file
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text("""
powerwall:
  tesla_email: test@example.com
automation:
  enabled: false
  schedule: []
web_interface:
  enabled: true
  host: 0.0.0.0
  port: 8080
logging:
  level: INFO
  file_path: logs/powernight.log
monitoring:
  enabled: false
""")
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Don't create logs directory - should be handled gracefully
                
                # Mock database migration to avoid actual database operations
                with patch('powernight.app.db_migration.upgrade'):
                    # Mock Powerwall connector initialization
                    with patch('powernight.app.initialize_powerwall_connector') as mock_powerwall:
                        mock_powerwall.return_value = MagicMock()
                        
                        # Mock planner to avoid actual scheduling
                        with patch('powernight.app.get_planner') as mock_planner:
                            mock_planner_instance = MagicMock()
                            mock_planner.return_value = mock_planner_instance
                            
                            # Create and initialize application
                            app = PowerNightApp()
                            success = app.initialize(str(config_path))
                            
                            # Should still initialize successfully
                            assert success
                            
            finally:
                os.chdir(original_cwd)

    def test_application_works_in_different_working_directories(self):
        """Test that application works correctly in different working directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create subdirectory
            subdir = Path(temp_dir) / "subdir"
            subdir.mkdir()
            
            # Create config file in subdirectory
            config_path = subdir / "config.yaml"
            config_path.write_text("""
powerwall:
  tesla_email: test@example.com
automation:
  enabled: false
  schedule: []
web_interface:
  enabled: true
  host: 0.0.0.0
  port: 8080
logging:
  level: INFO
  file_path: logs/powernight.log
monitoring:
  enabled: false
""")
            
            original_cwd = os.getcwd()
            try:
                # Test in subdirectory
                os.chdir(subdir)
                
                # Mock database migration to avoid actual database operations
                with patch('powernight.app.db_migration.upgrade'):
                    # Mock Powerwall connector initialization
                    with patch('powernight.app.initialize_powerwall_connector') as mock_powerwall:
                        mock_powerwall.return_value = MagicMock()
                        
                        # Mock planner to avoid actual scheduling
                        with patch('powernight.app.get_planner') as mock_planner:
                            mock_planner_instance = MagicMock()
                            mock_planner.return_value = mock_planner_instance
                            
                            # Create and initialize application
                            app = PowerNightApp()
                            success = app.initialize(str(config_path))
                            
                            # Should initialize successfully
                            assert success
                            
                            # Verify config was loaded correctly
                            config = app.config_manager.get_config()
                            assert config.logging.file_path == "logs/powernight.log"
                            
            finally:
                os.chdir(original_cwd)


class TestApplicationStartupPathEdgeCases:
    """Test edge cases in application startup path handling."""

    def test_application_handles_environment_variable_overrides(self):
        """Test that application handles environment variable overrides correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create config file
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text("""
powerwall:
  tesla_email: test@example.com
automation:
  enabled: false
  schedule: []
web_interface:
  enabled: true
  host: 0.0.0.0
  port: 8080
logging:
  level: INFO
  file_path: logs/powernight.log
monitoring:
  enabled: false
""")
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Set environment variables
                with patch.dict(os.environ, {
                    'POWERNIGHT_DATA_PATH': str(Path(temp_dir) / "custom_data"),
                    'POWERNIGHT_STATIC_PATH': str(Path(temp_dir) / "custom_static")
                }):
                    # Mock database migration to avoid actual database operations
                    with patch('powernight.app.db_migration.upgrade'):
                        # Mock Powerwall connector initialization
                        with patch('powernight.app.initialize_powerwall_connector') as mock_powerwall:
                            mock_powerwall.return_value = MagicMock()
                            
                            # Mock planner to avoid actual scheduling
                            with patch('powernight.app.get_planner') as mock_planner:
                                mock_planner_instance = MagicMock()
                                mock_planner.return_value = mock_planner_instance
                                
                                # Create and initialize application
                                app = PowerNightApp()
                                success = app.initialize(str(config_path))
                                
                                # Should initialize successfully
                                assert success
                                
            finally:
                os.chdir(original_cwd)

    def test_application_handles_invalid_config_paths(self):
        """Test that application handles invalid config paths gracefully."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Mock database migration to avoid actual database operations
                with patch('powernight.app.db_migration.upgrade'):
                    # Mock Powerwall connector initialization
                    with patch('powernight.app.initialize_powerwall_connector') as mock_powerwall:
                        mock_powerwall.return_value = MagicMock()
                        
                        # Mock planner to avoid actual scheduling
                        with patch('powernight.app.get_planner') as mock_planner:
                            mock_planner_instance = MagicMock()
                            mock_planner.return_value = mock_planner_instance
                            
                            # Create application
                            app = PowerNightApp()
                            
                            # Try to initialize with non-existent config
                            success = app.initialize("/non/existent/config.yaml")
                            
                            # Should fail gracefully
                            assert not success
                            
            finally:
                os.chdir(original_cwd)

    def test_application_handles_missing_required_directories(self):
        """Test that application handles missing required directories gracefully."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create config file
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text("""
powerwall:
  tesla_email: test@example.com
automation:
  enabled: false
  schedule: []
web_interface:
  enabled: true
  host: 0.0.0.0
  port: 8080
logging:
  level: INFO
  file_path: logs/powernight.log
monitoring:
  enabled: false
""")
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Mock database migration to avoid actual database operations
                with patch('powernight.app.db_migration.upgrade'):
                    # Mock Powerwall connector initialization
                    with patch('powernight.app.initialize_powerwall_connector') as mock_powerwall:
                        mock_powerwall.return_value = MagicMock()
                        
                        # Mock planner to avoid actual scheduling
                        with patch('powernight.app.get_planner') as mock_planner:
                            mock_planner_instance = MagicMock()
                            mock_planner.return_value = mock_planner_instance
                            
                            # Create and initialize application
                            app = PowerNightApp()
                            success = app.initialize(str(config_path))
                            
                            # Should initialize successfully even without directories
                            assert success
                            
            finally:
                os.chdir(original_cwd)


class TestApplicationStartupPathIntegration:
    """Integration tests for application startup path handling."""

    def test_full_application_startup_workflow(self):
        """Test the complete application startup workflow."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create config file
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text("""
powerwall:
  tesla_email: test@example.com
automation:
  enabled: false
  schedule: []
web_interface:
  enabled: true
  host: 0.0.0.0
  port: 8080
logging:
  level: INFO
  file_path: logs/powernight.log
monitoring:
  enabled: false
""")
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Mock database migration to avoid actual database operations
                with patch('powernight.app.db_migration.upgrade'):
                    # Mock Powerwall connector initialization
                    with patch('powernight.app.initialize_powerwall_connector') as mock_powerwall:
                        mock_powerwall.return_value = MagicMock()
                        
                        # Mock planner to avoid actual scheduling
                        with patch('powernight.app.get_planner') as mock_planner:
                            mock_planner_instance = MagicMock()
                            mock_planner.return_value = mock_planner_instance
                            
                            # Mock Flask app creation to avoid actual web server
                            with patch('powernight.app.create_app') as mock_create_app:
                                mock_flask_app = MagicMock()
                                mock_create_app.return_value = mock_flask_app
                                
                                # Create and run application
                                app = PowerNightApp()
                                
                                # Test full workflow
                                success = app.initialize(str(config_path))
                                assert success
                                
                                planner_success = app.start_planner()
                                assert planner_success
                                
                                web_success = app.start_web_interface()
                                assert web_success
                                
                                # Verify all components were initialized
                                assert app.powerwall_connector is not None
                                assert app.flask_app is not None
                                assert app.planner is not None
                                
                                # Verify config uses relative paths
                                config = app.config_manager.get_config()
                                assert config.logging.file_path == "logs/powernight.log"
                                assert not config.logging.file_path.startswith("/app/")
                                
            finally:
                os.chdir(original_cwd)

    def test_application_startup_path_consistency(self):
        """Test that application startup uses consistent paths across components."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create config file
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text("""
powerwall:
  tesla_email: test@example.com
automation:
  enabled: false
  schedule: []
web_interface:
  enabled: true
  host: 0.0.0.0
  port: 8080
logging:
  level: INFO
  file_path: logs/powernight.log
monitoring:
  enabled: false
""")
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Mock database migration to avoid actual database operations
                with patch('powernight.app.db_migration.upgrade'):
                    # Mock Powerwall connector initialization
                    with patch('powernight.app.initialize_powerwall_connector') as mock_powerwall:
                        mock_powerwall.return_value = MagicMock()
                        
                        # Mock planner to avoid actual scheduling
                        with patch('powernight.app.get_planner') as mock_planner:
                            mock_planner_instance = MagicMock()
                            mock_planner.return_value = mock_planner_instance
                            
                            # Mock Flask app creation to avoid actual web server
                            with patch('powernight.app.create_app') as mock_create_app:
                                mock_flask_app = MagicMock()
                                mock_create_app.return_value = mock_flask_app
                                
                                # Create and initialize application
                                app = PowerNightApp()
                                success = app.initialize(str(config_path))
                                
                                # Verify initialization was successful
                                assert success
                                
                                # Verify all components use consistent paths
                                config = app.config_manager.get_config()
                                
                                # All paths should be relative, not Docker paths
                                assert config.logging.file_path == "logs/powernight.log"
                                assert not config.logging.file_path.startswith("/app/")
                                
                                # Start web interface to trigger create_app
                                web_success = app.start_web_interface()
                                assert web_success
                                
                                # Verify Flask app was created with correct paths
                                mock_create_app.assert_called_once()
                                call_args = mock_create_app.call_args
                                # Check that the config passed to create_app has relative paths
                                if call_args and call_args[0]:
                                    flask_config = call_args[0][0]  # First positional argument
                                    assert flask_config.logging.file_path == "logs/powernight.log"
                                    assert not flask_config.logging.file_path.startswith("/app/")
                                else:
                                    # If no positional args, check keyword args
                                    assert 'config' in call_args[1]
                                    flask_config = call_args[1]['config']
                                    assert flask_config.logging.file_path == "logs/powernight.log"
                                    assert not flask_config.logging.file_path.startswith("/app/")
                                
            finally:
                os.chdir(original_cwd)
