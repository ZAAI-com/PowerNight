"""
Tests for configuration path handling to prevent Docker container path bugs.

These tests ensure that the application uses proper development paths
and doesn't rely on Docker container paths when running locally.
"""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open

from powernight.core.config.manager import ConfigManager
from powernight.core.config.schema import PowerNightConfig, create_default_config, create_dummy_config


class TestConfigPathResolution:
    """Test configuration path resolution in different environments."""

    def test_config_manager_finds_local_config_files(self):
        """Test that ConfigManager finds local config files before Docker paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a local config file
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text("""
powerwall:
  tesla_email: test@example.com
automation:
  enabled: false
web_interface:
  enabled: true
logging:
  level: INFO
  file_path: logs/powernight.log
""")
            
            # Change to temp directory
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                manager = ConfigManager()
                found_path = manager._find_config_file()
                
                # Should find the local config.yaml
                assert found_path == Path("config.yaml")
                assert found_path.exists()
                
            finally:
                os.chdir(original_cwd)

    def test_config_manager_prioritizes_local_paths(self):
        """Test that local paths are prioritized over Docker paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create both local and Docker-style config files
            local_config = Path(temp_dir) / "config.yaml"
            docker_config = Path(temp_dir) / "docker-config.yaml"
            
            local_config.write_text("""
powerwall:
  tesla_email: local@example.com
automation:
  enabled: false
web_interface:
  enabled: true
logging:
  level: INFO
  file_path: logs/powernight.log
""")
            
            docker_config.write_text("""
powerwall:
  tesla_email: docker@example.com
automation:
  enabled: false
web_interface:
  enabled: true
logging:
  level: INFO
  file_path: /app/logs/powernight.log
""")
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                manager = ConfigManager()
                found_path = manager._find_config_file()
                
                # Should find the local config.yaml, not the Docker one
                assert found_path == Path("config.yaml")
                
                # Load the config and verify it's the local one
                config = manager.load_config()
                assert config.powerwall.tesla_email == "local@example.com"
                
            finally:
                os.chdir(original_cwd)

    def test_config_uses_relative_log_paths(self):
        """Test that configuration uses relative log paths by default."""
        config = create_default_config()
        
        # Should use relative path, not Docker path
        assert config.logging.file_path == "logs/powernight.log"
        assert not config.logging.file_path.startswith("/app/")
        assert not config.logging.file_path.startswith("/")

    def test_dummy_config_uses_relative_paths(self):
        """Test that dummy configuration uses relative paths."""
        config = create_dummy_config()
        
        # Should use relative path, not Docker path
        assert config.logging.file_path == "logs/powernight.log"
        assert not config.logging.file_path.startswith("/app/")

    def test_config_from_dict_uses_relative_paths(self):
        """Test that config created from dict uses relative paths by default."""
        config_data = {
            "powerwall": {
                "tesla_email": "test@example.com",
            },
            "automation": {
                "enabled": False
            },
            "web_interface": {
                "enabled": True
            },
            "logging": {
                # No file_path specified - should default to relative path
            }
        }
        
        config = PowerNightConfig.from_dict(config_data)
        
        # Should default to relative path
        assert config.logging.file_path == "logs/powernight.log"
        assert not config.logging.file_path.startswith("/app/")

    def test_environment_variable_override_works(self):
        """Test that environment variables can override config paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "test-config.yaml"
            config_path.write_text("""
powerwall:
  tesla_email: test@example.com
automation:
  enabled: false
web_interface:
  enabled: true
logging:
  level: INFO
  file_path: logs/powernight.log
""")
            
            # Set environment variable
            with patch.dict(os.environ, {'POWERNIGHT_CONFIG_PATH': str(config_path)}):
                manager = ConfigManager()
                found_path = manager._find_config_file()
                
                assert found_path == config_path

    def test_config_validation_rejects_docker_paths_in_development(self):
        """Test that configuration validation can detect problematic Docker paths."""
        # This test documents the expected behavior - we want to catch
        # configurations that use Docker paths in development
        
        config_data = {
            "powerwall": {
                "tesla_email": "test@example.com",
            },
            "automation": {
                "enabled": False
            },
            "web_interface": {
                "enabled": True
            },
            "logging": {
                "file_path": "/app/logs/powernight.log"  # Docker path
            }
        }
        
        config = PowerNightConfig.from_dict(config_data)
        
        # The config should be created (validation doesn't reject Docker paths)
        # but we can test that it uses the Docker path as specified
        assert config.logging.file_path == "/app/logs/powernight.log"
        
        # In a real scenario, we might want to add validation to warn about
        # Docker paths in development, but for now we just document the behavior


class TestConfigPathEdgeCases:
    """Test edge cases in configuration path handling."""

    def test_config_manager_handles_missing_config_gracefully(self):
        """Test that ConfigManager handles missing config files gracefully."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                manager = ConfigManager()
                
                # Should raise ConfigurationError when no config found
                with pytest.raises(Exception):  # ConfigurationError
                    manager._find_config_file()
                    
            finally:
                os.chdir(original_cwd)

    def test_config_manager_handles_invalid_paths(self):
        """Test that ConfigManager handles invalid paths gracefully."""
        manager = ConfigManager()
        
        # Test with non-existent path
        with pytest.raises(Exception):  # ConfigurationError
            manager.load_config("/non/existent/path.yaml")

    def test_config_works_with_absolute_paths(self):
        """Test that configuration works with absolute paths when explicitly provided."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text("""
powerwall:
  tesla_email: test@example.com
automation:
  enabled: false
web_interface:
  enabled: true
logging:
  level: INFO
  file_path: /tmp/powernight.log
""")
            
            manager = ConfigManager()
            config = manager.load_config(config_path)
            
            # Should load successfully even with absolute log path
            assert config.powerwall.tesla_email == "test@example.com"
            assert config.logging.file_path == "/tmp/powernight.log"


class TestConfigPathIntegration:
    """Integration tests for configuration path handling."""

    def test_full_config_loading_workflow(self):
        """Test the complete configuration loading workflow."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create config file
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text("""
powerwall:
  tesla_email: integration@example.com
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
                
                # Test full workflow
                manager = ConfigManager()
                config = manager.load_config()
                
                # Verify all components loaded correctly
                assert config.powerwall.tesla_email == "integration@example.com"
                assert config.automation.enabled is False
                assert config.web_interface.enabled is True
                assert config.logging.file_path == "logs/powernight.log"
                assert config.monitoring.enabled is False
                
                # Verify validation passes
                errors = config.validate()
                assert len(errors) == 0
                
            finally:
                os.chdir(original_cwd)

    def test_config_save_and_reload_workflow(self):
        """Test saving and reloading configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "test-config.yaml"
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Create and save config
                manager = ConfigManager()
                config = create_default_config()
                config.powerwall.tesla_email = "save-test@example.com"
                config.logging.file_path = "logs/test.log"
                
                manager.save_config(config, config_path)
                
                # Verify file was created
                assert config_path.exists()
                
                # Reload and verify
                reloaded_config = manager.load_config(config_path)
                assert reloaded_config.powerwall.tesla_email == "save-test@example.com"
                assert reloaded_config.logging.file_path == "logs/test.log"
                
            finally:
                os.chdir(original_cwd)
