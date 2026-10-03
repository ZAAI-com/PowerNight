"""
Configuration management tests for PowerNight application.
Tests configuration loading, validation, updates, and persistence.
"""

import pytest
import tempfile
import os
from pathlib import Path

import yaml

from powernight.core.config import (
    PowerNightConfig, PowerwallSettings, AutomationSettings,
    WebInterfaceSettings, LoggingSettings, MonitoringSettings
)
from powernight.core.config.manager import ConfigManager
from powernight.core.config.validators import (
    validate_percentage, validate_time_format, validate_port_number,
    validate_log_level, validate_email_format
)


@pytest.fixture
def sample_config():
    """Create sample configuration for testing."""
    return PowerNightConfig(
        powerwall=PowerwallSettings(
            tesla_email="test@example.com",
            powerwall_id="TG0123456789AB"
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


@pytest.fixture
def config_dict():
    """Create sample configuration dictionary."""
    return {
        'powerwall': {
            'tesla_email': 'test@example.com',
            'powerwall_id': 'TG0123456789AB',
            'timeout': 30.0,
            'retry_attempts': 3,
            'verify_ssl': False
        },
        'automation': {
            'enabled': True
        },
        'web_interface': {
            'host': '0.0.0.0',
            'port': 5001,
            'debug': False
        },
        'logging': {
            'level': 'INFO',
            'file_path': 'logs/powernight.log'
        },
        'monitoring': {
            'enabled': True
        }
    }


class TestPowerNightConfig:
    """Test PowerNightConfig class."""

    def test_config_creation(self, sample_config):
        """Test configuration object creation."""
        assert sample_config.powerwall.tesla_email == "test@example.com"
        assert sample_config.powerwall.powerwall_id == "TG0123456789AB"
        assert sample_config.automation.enabled is True
        assert sample_config.web_interface.port == 5001
        assert sample_config.logging.level == "INFO"
        assert sample_config.monitoring.enabled is True

    def test_config_from_dict(self, config_dict):
        """Test configuration creation from dictionary."""
        config = PowerNightConfig.from_dict(config_dict)

        assert config.powerwall.tesla_email == "test@example.com"
        assert config.powerwall.powerwall_id == "TG0123456789AB"
        assert config.automation.enabled is True
        assert config.web_interface.port == 5001
        assert config.logging.level == "INFO"
        assert config.monitoring.enabled is True

    def test_config_to_dict(self, sample_config):
        """Test configuration conversion to dictionary."""
        config_dict = sample_config.to_dict()

        assert config_dict['powerwall']['tesla_email'] == "test@example.com"
        assert config_dict['powerwall']['powerwall_id'] == "TG0123456789AB"
        assert config_dict['automation']['enabled'] is True
        assert config_dict['web_interface']['port'] == 5001
        assert config_dict['logging']['level'] == "INFO"
        assert config_dict['monitoring']['enabled'] is True

        # Round-trip keys added for the web config API (auth is credential-driven)
        assert config_dict['web_interface']['auth_enabled'] is False
        assert config_dict['web_interface']['cors_origins'] == ["*"]
        assert config_dict['logging']['file_enabled'] is True

    def test_config_validation(self, sample_config):
        """Test configuration validation."""
        # Valid configuration produces no errors
        assert sample_config.validate() == []
        assert sample_config.is_valid()

        # Invalid Tesla email produces validation errors
        sample_config.powerwall.tesla_email = "invalid-email"
        errors = sample_config.validate()
        assert len(errors) > 0
        assert not sample_config.is_valid()

    def test_config_equality(self, sample_config):
        """Test configuration equality comparison."""
        config_copy = PowerNightConfig(
            powerwall=PowerwallSettings(
                tesla_email="test@example.com",
                powerwall_id="TG0123456789AB"
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

        assert sample_config == config_copy

        # Test inequality
        config_copy.powerwall.tesla_email = "different@example.com"
        assert sample_config != config_copy

    def test_from_dict_rejects_incomplete_schedule_entries(self):
        """Test that from_dict raises on schedule entries missing required keys."""
        with pytest.raises(ValueError):
            PowerNightConfig.from_dict({
                'automation': {'schedule': [{'time': '12:00'}]}
            })

        with pytest.raises(ValueError):
            PowerNightConfig.from_dict({
                'automation': {'schedule': [{'percentage': 40.0}]}
            })


class TestConfigManager:
    """Test ConfigManager class."""

    def setup_method(self):
        """Reset singleton state for each test."""
        ConfigManager._instance = None

    def teardown_method(self):
        """Reset singleton state after each test."""
        ConfigManager._instance = None

    def test_config_manager_is_singleton(self):
        """Test that ConfigManager is a singleton."""
        manager1 = ConfigManager()
        manager2 = ConfigManager()
        assert manager1 is manager2

    def test_load_config_from_file(self, config_dict):
        """Test loading configuration from file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_dict, f)
            config_path = f.name

        try:
            manager = ConfigManager()
            loaded_config = manager.load_config(config_path)

            assert loaded_config.powerwall.tesla_email == "test@example.com"
            assert loaded_config.automation.enabled is True
            assert loaded_config.web_interface.port == 5001
        finally:
            os.unlink(config_path)

    def test_save_config_to_file(self, sample_config):
        """Test saving configuration to file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = os.path.join(temp_dir, "config.yaml")

            manager = ConfigManager()
            manager.save_config(sample_config, config_path)

            # Verify file was created and contains data
            assert os.path.exists(config_path)
            with open(config_path, 'r') as f:
                content = f.read()
                assert 'powerwall' in content
                assert 'test@example.com' in content

    def test_config_backup_creation(self, sample_config):
        """Test configuration backup creation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = os.path.join(temp_dir, "config.yaml")
            manager = ConfigManager()

            # Save initial config
            manager.save_config(sample_config, config_path)

            # Create backup
            backup_path = manager.create_backup(config_path)

            assert backup_path is not None
            assert backup_path.exists()
            assert str(backup_path) != config_path

            # Verify backup contains same data
            backup_config = manager.load_config(backup_path)
            assert backup_config == sample_config

    def test_config_restore_from_backup(self, sample_config):
        """Test configuration restore from backup."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = os.path.join(temp_dir, "config.yaml")
            manager = ConfigManager()

            # Save initial config
            manager.save_config(sample_config, config_path)

            # Create backup
            backup_path = manager.create_backup(config_path)
            assert backup_path is not None

            # Modify config on disk
            modified_config = manager.load_config(config_path)
            modified_config.powerwall.tesla_email = "modified@example.com"
            manager.save_config(modified_config, config_path)

            # Restore from backup
            assert manager.restore_from_backup(backup_path, config_path)
            restored_config = manager.load_config(config_path)

            assert restored_config.powerwall.tesla_email == "test@example.com"
            assert restored_config == sample_config


class TestConfigValidators:
    """Test individual config validation functions."""

    def test_valid_percentage_validation(self):
        """Test validation of valid percentage."""
        result = validate_percentage(50.0)
        assert result == 50.0

    def test_invalid_percentage_validation(self):
        """Test validation of invalid percentage."""
        with pytest.raises(Exception):  # PercentageValidationError
            validate_percentage(150.0)

    def test_valid_time_format_validation(self):
        """Test validation of valid time format."""
        result = validate_time_format("15:30")
        assert result.hour == 15
        assert result.minute == 30

    def test_invalid_time_format_validation(self):
        """Test validation of invalid time format."""
        with pytest.raises(Exception):  # TimeFormatValidationError
            validate_time_format("25:00")

    def test_valid_port_validation(self):
        """Test validation of valid port."""
        result = validate_port_number(5001)
        assert result == 5001

    def test_invalid_port_validation(self):
        """Test validation of invalid port."""
        with pytest.raises(Exception):  # ValidationError
            validate_port_number(99999)

    def test_valid_log_level_validation(self):
        """Test validation of valid log level."""
        result = validate_log_level("INFO")
        assert result == "INFO"

    def test_invalid_log_level_validation(self):
        """Test validation of invalid log level."""
        with pytest.raises(Exception):  # ValidationError
            validate_log_level("INVALID")

    def test_valid_email_validation(self):
        """Test validation of valid email."""
        result = validate_email_format("test@example.com")
        assert result == "test@example.com"

    def test_invalid_email_validation(self):
        """Test validation of invalid email."""
        with pytest.raises(Exception):  # ValidationError
            validate_email_format("invalid-email")


class TestConfigurationIntegration:
    """Test configuration integration scenarios."""

    def setup_method(self):
        """Reset singleton state for each test."""
        ConfigManager._instance = None

    def teardown_method(self):
        """Reset singleton state after each test."""
        ConfigManager._instance = None

    def test_configuration_roundtrip(self, sample_config):
        """Test configuration save and load roundtrip."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = os.path.join(temp_dir, "config.yaml")

            manager = ConfigManager()

            # Save configuration
            manager.save_config(sample_config, config_path)

            # Load configuration
            loaded_config = manager.load_config(config_path)

            # Verify they are equal
            assert loaded_config == sample_config

    def test_configuration_merge(self, sample_config):
        """Test configuration merging."""
        # Create partial update
        update_dict = {
            'powerwall': {
                'tesla_email': 'updated@example.com'
            },
            'automation': {
                'enabled': False
            }
        }

        # Convert to dict, merge, and convert back
        config_dict = sample_config.to_dict()
        config_dict.update(update_dict)
        merged_config = PowerNightConfig.from_dict(config_dict)

        # Verify merge worked
        assert merged_config.powerwall.tesla_email == 'updated@example.com'
        assert merged_config.automation.enabled is False
        # Other fields should remain unchanged
        assert merged_config.web_interface.port == 5001
        assert merged_config.logging.level == "INFO"
