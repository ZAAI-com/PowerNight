"""
Tests for configuration backup and recovery functionality.
"""

import os
import json
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

from powernight.core.config.backup import (
    ConfigBackupManager,
    ConfigRecoveryManager
)
from powernight.core.config import (
    ConfigManager,
    ConfigurationError,
    create_default_config
)


class TestConfigBackupManager:
    """Test ConfigBackupManager functionality."""

    def setup_method(self):
        """Setup for each test."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.backup_manager = ConfigBackupManager(backup_dir=self.temp_dir / 'backups')

    def teardown_method(self):
        """Cleanup after each test."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_create_backup(self):
        """Test creating configuration backup."""
        # Create a test config file
        config_file = self.temp_dir / 'config.json'
        test_config = {'test': 'data'}

        with open(config_file, 'w') as f:
            json.dump(test_config, f)

        # Create backup
        backup_path = self.backup_manager.create_backup(config_file)

        assert backup_path is not None
        assert backup_path.exists()
        assert backup_path.parent == self.backup_manager.get_backup_dir(config_file)

        # Verify backup content
        with open(backup_path, 'r') as f:
            backup_data = json.load(f)
        assert backup_data == test_config

    def test_create_backup_nonexistent_file(self):
        """Test creating backup of nonexistent file."""
        nonexistent_file = self.temp_dir / 'nonexistent.json'
        backup_path = self.backup_manager.create_backup(nonexistent_file)
        assert backup_path is None

    def test_list_backups(self):
        """Test listing backup files."""
        config_file = self.temp_dir / 'config.json'

        with open(config_file, 'w') as f:
            json.dump({'test': 'data'}, f)

        # Create multiple backups
        backup1 = self.backup_manager.create_backup(config_file)
        backup2 = self.backup_manager.create_backup(config_file)

        backups = self.backup_manager.list_backups(config_file)
        assert len(backups) == 2

        # Should be sorted by modification time, newest first
        assert backups[0].stat().st_mtime >= backups[1].stat().st_mtime

    def test_restore_from_backup(self):
        """Test restoring configuration from backup."""
        config_file = self.temp_dir / 'config.json'
        original_data = {'original': 'data'}

        # Create original config
        with open(config_file, 'w') as f:
            json.dump(original_data, f)

        # Create backup
        backup_path = self.backup_manager.create_backup(config_file)

        # Modify original file
        modified_data = {'modified': 'data'}
        with open(config_file, 'w') as f:
            json.dump(modified_data, f)

        # Restore from backup
        success = self.backup_manager.restore_from_backup(config_file, backup_path)
        assert success

        # Verify restoration
        with open(config_file, 'r') as f:
            restored_data = json.load(f)
        assert restored_data == original_data

    def test_restore_from_most_recent_backup(self):
        """Test restoring from most recent backup."""
        config_file = self.temp_dir / 'config.json'

        # Create original config
        with open(config_file, 'w') as f:
            json.dump({'version': 1}, f)

        backup1 = self.backup_manager.create_backup(config_file)

        # Update config
        with open(config_file, 'w') as f:
            json.dump({'version': 2}, f)

        backup2 = self.backup_manager.create_backup(config_file)

        # Update config again
        with open(config_file, 'w') as f:
            json.dump({'version': 3}, f)

        # Restore without specifying backup (should use most recent)
        success = self.backup_manager.restore_from_backup(config_file)
        assert success

        # Should restore version 2 (most recent backup)
        with open(config_file, 'r') as f:
            restored_data = json.load(f)
        assert restored_data['version'] == 2

    def test_get_backup_info(self):
        """Test getting backup information."""
        config_file = self.temp_dir / 'config.json'

        with open(config_file, 'w') as f:
            json.dump({'test': 'data'}, f)

        # Create backup
        backup_path = self.backup_manager.create_backup(config_file)

        backup_info = self.backup_manager.get_backup_info(config_file)
        assert len(backup_info) == 1

        info = backup_info[0]
        assert info['path'] == backup_path
        assert info['size'] > 0
        assert 'created' in info
        assert 'age_days' in info

    def test_cleanup_old_backups(self):
        """Test cleaning up old backup files."""
        config_file = self.temp_dir / 'config.json'

        with open(config_file, 'w') as f:
            json.dump({'test': 'data'}, f)

        # Set max_backups to 2
        self.backup_manager.max_backups = 2

        # Create 4 backups
        for i in range(4):
            self.backup_manager.create_backup(config_file)

        # Should only keep 2 most recent
        backups = self.backup_manager.list_backups(config_file)
        assert len(backups) == 2

    def test_verify_backup(self):
        """Test backup verification."""
        config_file = self.temp_dir / 'config.json'
        valid_config = {
            'powerwall': {'ip_address': '192.168.1.100'},
            'automation': {'enabled': True, 'schedule': []}
        }

        # Create valid config and backup
        with open(config_file, 'w') as f:
            json.dump(valid_config, f)

        backup_path = self.backup_manager.create_backup(config_file)
        assert self.backup_manager.verify_backup(backup_path)

        # Create invalid backup
        invalid_backup = self.temp_dir / 'backups' / 'invalid_backup.json'
        invalid_backup.parent.mkdir(parents=True, exist_ok=True)

        with open(invalid_backup, 'w') as f:
            json.dump({'invalid': 'config'}, f)

        assert not self.backup_manager.verify_backup(invalid_backup)


class TestConfigRecoveryManager:
    """Test ConfigRecoveryManager functionality."""

    def setup_method(self):
        """Setup for each test."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.recovery_manager = ConfigRecoveryManager()

    def teardown_method(self):
        """Cleanup after each test."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_attempt_recovery_with_backup(self):
        """Test recovery from backup."""
        config_file = self.temp_dir / 'config.json'
        valid_config = {
            'powerwall': {'ip_address': '192.168.1.100'},
            'automation': {'enabled': True, 'schedule': []}
        }

        # Create valid config and backup
        with open(config_file, 'w') as f:
            json.dump(valid_config, f)

        backup_path = self.recovery_manager.backup_manager.create_backup(config_file)

        # Corrupt the config file
        with open(config_file, 'w') as f:
            f.write("invalid json {")

        # Attempt recovery
        error = Exception("Test error")
        recovered_path = self.recovery_manager.attempt_recovery(config_file, error)

        assert recovered_path == config_file
        assert config_file.exists()

        # Verify recovery worked
        with open(config_file, 'r') as f:
            recovered_data = json.load(f)
        assert recovered_data == valid_config

    def test_attempt_recovery_create_default(self):
        """Test recovery by creating default config."""
        config_file = self.temp_dir / 'config.json'

        # Attempt recovery with no existing file
        error = Exception("Test error")
        recovered_path = self.recovery_manager.attempt_recovery(config_file, error)

        assert recovered_path == config_file
        assert config_file.exists()

        # Verify default config was created
        with open(config_file, 'r') as f:
            config_data = json.load(f)
        assert 'powerwall' in config_data
        assert 'automation' in config_data


class TestEnhancedConfigManager:
    """Test enhanced ConfigManager with backup/recovery functionality."""

    def setup_method(self):
        """Setup for each test."""
        ConfigManager._instance = None
        self.temp_dir = Path(tempfile.mkdtemp())

    def teardown_method(self):
        """Cleanup after each test."""
        ConfigManager._instance = None
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_auto_backup_on_save(self):
        """Test automatic backup creation when saving config."""
        config_file = self.temp_dir / 'config.json'

        # Create initial config
        default_config = create_default_config()

        with open(config_file, 'w') as f:
            json.dump(default_config.to_dict(), f)

        manager = ConfigManager()
        manager.load_config(config_file)

        # Modify and save config
        config = manager.get_config()
        config.powerwall.ip_address = "192.168.1.200"
        manager.save_config(config, config_file)

        # Check that backup was created
        backups = manager.list_backups()
        assert len(backups) >= 1

    def test_auto_recovery_on_load_error(self):
        """Test automatic recovery when config loading fails."""
        config_file = self.temp_dir / 'config.json'

        # Create valid config first
        default_config = create_default_config()
        with open(config_file, 'w') as f:
            json.dump(default_config.to_dict(), f)

        manager = ConfigManager()

        # Create backup
        manager.create_backup(config_file)

        # Corrupt the config file
        with open(config_file, 'w') as f:
            f.write("invalid json {")

        # Loading should trigger auto-recovery
        config = manager.load_config(config_file)
        assert config is not None
        assert config.powerwall.ip_address  # Should have valid config

    def test_load_config_with_fallback(self):
        """Test loading config with fallback paths."""
        primary_path = self.temp_dir / 'primary.json'
        fallback_path = self.temp_dir / 'fallback.json'

        # Create only fallback config
        default_config = create_default_config()
        with open(fallback_path, 'w') as f:
            json.dump(default_config.to_dict(), f)

        manager = ConfigManager()
        config = manager.load_config_with_fallback(primary_path, [fallback_path])

        assert config is not None
        assert manager._config_path == fallback_path

    def test_load_config_with_fallback_all_fail(self):
        """Test fallback loading when all paths fail."""
        primary_path = self.temp_dir / 'primary.json'
        fallback_path = self.temp_dir / 'fallback.json'

        manager = ConfigManager()

        with pytest.raises(ConfigurationError) as exc_info:
            manager.load_config_with_fallback(primary_path, [fallback_path])

        assert "Failed to load configuration from any path" in str(exc_info.value)

    def test_config_status(self):
        """Test getting configuration status."""
        manager = ConfigManager()

        # Status without loaded config
        status = manager.get_config_status()
        assert not status['config_loaded']
        assert status['config_path'] is None

        # Load config and check status
        config_file = self.temp_dir / 'config.json'
        default_config = create_default_config()

        with open(config_file, 'w') as f:
            json.dump(default_config.to_dict(), f)

        manager.load_config(config_file)
        status = manager.get_config_status()

        assert status['config_loaded']
        assert status['config_path'] == str(config_file)
        assert status['validation_status'] == 'valid'

    def test_set_auto_backup_recovery(self):
        """Test enabling/disabling auto backup and recovery."""
        manager = ConfigManager()

        # Test setting auto backup
        manager.set_auto_backup(False)
        assert not manager._auto_backup

        manager.set_auto_backup(True)
        assert manager._auto_backup

        # Test setting auto recovery
        manager.set_auto_recovery(False)
        assert not manager._auto_recovery

        manager.set_auto_recovery(True)
        assert manager._auto_recovery

    def test_restore_from_backup(self):
        """Test manual restore from backup."""
        config_file = self.temp_dir / 'config.json'

        # Create config
        original_config = create_default_config()
        original_config.powerwall.ip_address = "192.168.1.100"

        with open(config_file, 'w') as f:
            json.dump(original_config.to_dict(), f)

        manager = ConfigManager()
        manager.load_config(config_file)

        # Create backup
        backup_path = manager.create_backup()
        assert backup_path is not None

        # Modify config
        modified_config = create_default_config()
        modified_config.powerwall.ip_address = "192.168.1.200"
        manager.save_config(modified_config)

        # Restore from backup
        success = manager.restore_from_backup(backup_path)
        assert success

        # Verify restoration
        reloaded_config = manager.get_config()
        assert reloaded_config.powerwall.ip_address == "192.168.1.100"