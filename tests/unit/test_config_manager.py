"""
Tests for ConfigManager functionality.
"""

import os
import json
import yaml
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open

from powernight.core.config import (
    ConfigManager,
    ConfigurationError,
    PowerNightConfig,
    get_config_manager,
    get_config,
    load_config,
    create_default_config
)


class TestConfigManager:
    """Test ConfigManager class."""

    def setup_method(self):
        """Reset singleton state for each test."""
        ConfigManager._instance = None

    def test_singleton_pattern(self):
        """Test that ConfigManager follows singleton pattern."""
        manager1 = ConfigManager()
        manager2 = ConfigManager()
        assert manager1 is manager2

    def test_global_instance_functions(self):
        """Test global instance access functions."""
        manager = get_config_manager()
        assert isinstance(manager, ConfigManager)

        # Should return same instance
        manager2 = get_config_manager()
        assert manager is manager2

    def test_load_json_config(self):
        """Test loading JSON configuration."""
        config_data = {
            "powerwall": {
                "ip_address": "192.168.1.100",
                "timeout": 30.0
            },
            "automation": {
                "enabled": True,
                "schedule": [
                    {
                        "time": "00:01",
                        "percentage": 40.0,
                        "enabled": True
                    }
                ]
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            manager = ConfigManager()
            config = manager.load_config(config_path)

            assert isinstance(config, PowerNightConfig)
            assert config.powerwall.ip_address == "192.168.1.100"
            assert config.powerwall.timeout == 30.0
            assert config.automation.enabled is True
            assert len(config.automation.schedule) == 1
            assert config.automation.schedule[0].time == "00:01"
            assert config.automation.schedule[0].percentage == 40.0

        finally:
            os.unlink(config_path)

    def test_load_yaml_config(self):
        """Test loading YAML configuration."""
        config_data = {
            "powerwall": {
                "ip_address": "192.168.1.100",
                "timeout": 30.0
            },
            "automation": {
                "enabled": True,
                "schedule": [
                    {
                        "time": "00:01",
                        "percentage": 40.0,
                        "enabled": True
                    }
                ]
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            manager = ConfigManager()
            config = manager.load_config(config_path)

            assert isinstance(config, PowerNightConfig)
            assert config.powerwall.ip_address == "192.168.1.100"
            assert config.automation.enabled is True

        finally:
            os.unlink(config_path)

    def test_environment_variable_overrides(self):
        """Test environment variable overrides."""
        config_data = {
            "powerwall": {
                "ip_address": "192.168.1.100",
                "timeout": 30.0
            },
            "web_interface": {
                "port": 5000
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            with patch.dict(os.environ, {
                'POWERNIGHT_POWERWALL_IP': '192.168.1.200',
                'POWERNIGHT_WEB_PORT': '8080',
                'POWERNIGHT_LOG_LEVEL': 'DEBUG'
            }):
                manager = ConfigManager()
                config = manager.load_config(config_path)

                assert config.powerwall.ip_address == "192.168.1.200"
                assert config.web_interface.port == 8080
                assert config.logging.level == "DEBUG"

        finally:
            os.unlink(config_path)

    def test_save_json_config(self):
        """Test saving configuration to JSON."""
        config = create_default_config()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_path = f.name

        try:
            manager = ConfigManager()
            manager._config = config
            manager.save_config(config, config_path)

            # Verify file was created and is valid JSON
            assert Path(config_path).exists()

            with open(config_path, 'r') as f:
                saved_data = json.load(f)

            assert saved_data['powerwall']['ip_address'] == config.powerwall.ip_address
            assert saved_data['automation']['enabled'] == config.automation.enabled

        finally:
            if Path(config_path).exists():
                os.unlink(config_path)

    def test_save_yaml_config(self):
        """Test saving configuration to YAML."""
        config = create_default_config()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            config_path = f.name

        try:
            manager = ConfigManager()
            manager._config = config
            manager.save_config(config, config_path)

            # Verify file was created and is valid YAML
            assert Path(config_path).exists()

            with open(config_path, 'r') as f:
                saved_data = yaml.safe_load(f)

            assert saved_data['powerwall']['ip_address'] == config.powerwall.ip_address
            assert saved_data['automation']['enabled'] == config.automation.enabled

        finally:
            if Path(config_path).exists():
                os.unlink(config_path)

    def test_validation_errors(self):
        """Test configuration validation errors."""
        invalid_config_data = {
            "powerwall": {
                "ip_address": "",  # Invalid: empty IP
                "timeout": -5.0     # Invalid: negative timeout
            },
            "automation": {
                "schedule": [
                    {
                        "time": "25:00",  # Invalid: bad time format
                        "percentage": 150.0  # Invalid: percentage > 100
                    }
                ]
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(invalid_config_data, f)
            config_path = f.name

        try:
            manager = ConfigManager()

            with pytest.raises(ConfigurationError) as exc_info:
                manager.load_config(config_path)

            error_msg = str(exc_info.value)
            assert "validation failed" in error_msg.lower()

        finally:
            os.unlink(config_path)

    def test_missing_config_file(self):
        """Test handling of missing configuration file."""
        manager = ConfigManager()

        with pytest.raises(ConfigurationError) as exc_info:
            manager.load_config("/nonexistent/config.json")

        assert "not found" in str(exc_info.value).lower()

    def test_invalid_json_file(self):
        """Test handling of invalid JSON file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{ invalid json }")
            config_path = f.name

        try:
            manager = ConfigManager()

            with pytest.raises(ConfigurationError) as exc_info:
                manager.load_config(config_path)

            assert "invalid json" in str(exc_info.value).lower()

        finally:
            os.unlink(config_path)

    def test_invalid_yaml_file(self):
        """Test handling of invalid YAML file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("invalid: yaml: content: [")
            config_path = f.name

        try:
            manager = ConfigManager()

            with pytest.raises(ConfigurationError) as exc_info:
                manager.load_config(config_path)

            assert "invalid yaml" in str(exc_info.value).lower()

        finally:
            os.unlink(config_path)

    def test_get_config_without_loading(self):
        """Test getting config without loading first."""
        manager = ConfigManager()

        with pytest.raises(ConfigurationError) as exc_info:
            manager.get_config()

        assert "no configuration loaded" in str(exc_info.value).lower()

    def test_create_default_config_file(self):
        """Test creating default configuration file."""
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            config_path = f.name

        # Remove the file so we can test creation
        os.unlink(config_path)

        try:
            manager = ConfigManager()
            manager.create_default_config_file(config_path)

            # Verify file was created
            assert Path(config_path).exists()

            # Verify it's valid JSON
            with open(config_path, 'r') as f:
                config_data = json.load(f)

            assert 'powerwall' in config_data
            assert 'automation' in config_data

        finally:
            if Path(config_path).exists():
                os.unlink(config_path)

    def test_validate_config_file(self):
        """Test validating configuration file."""
        # Valid config
        valid_config = {
            "powerwall": {
                "ip_address": "192.168.1.100"
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(valid_config, f)
            valid_path = f.name

        # Invalid config
        invalid_config = {
            "powerwall": {
                "ip_address": ""  # Empty IP
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(invalid_config, f)
            invalid_path = f.name

        try:
            manager = ConfigManager()

            # Valid config should return no errors
            errors = manager.validate_config_file(valid_path)
            assert len(errors) == 0

            # Invalid config should return errors
            errors = manager.validate_config_file(invalid_path)
            assert len(errors) > 0

        finally:
            os.unlink(valid_path)
            os.unlink(invalid_path)

    def test_reload_config(self):
        """Test reloading configuration."""
        config_data = {
            "powerwall": {
                "ip_address": "192.168.1.100"
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            manager = ConfigManager()

            # Load initial config
            config1 = manager.load_config(config_path)
            assert config1.powerwall.ip_address == "192.168.1.100"

            # Modify file
            config_data['powerwall']['ip_address'] = "192.168.1.200"
            with open(config_path, 'w') as f:
                json.dump(config_data, f)

            # Reload config
            config2 = manager.reload_config()
            assert config2.powerwall.ip_address == "192.168.1.200"

        finally:
            os.unlink(config_path)

    @patch.dict(os.environ, {'POWERNIGHT_CONFIG_PATH': '/custom/config.json'})
    def test_find_config_with_env_var(self):
        """Test finding config file with environment variable."""
        manager = ConfigManager()

        # Should look for environment variable path first
        with pytest.raises(ConfigurationError) as exc_info:
            manager._find_config_file()

        # Should mention the environment variable path
        assert "/custom/config.json" in str(exc_info.value) or "environment variable does not exist" in str(exc_info.value)

    def test_thread_safety(self):
        """Test thread safety of singleton pattern."""
        import threading

        instances = []

        def create_instance():
            instances.append(ConfigManager())

        threads = [threading.Thread(target=create_instance) for _ in range(10)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # All instances should be the same
        for instance in instances:
            assert instance is instances[0]