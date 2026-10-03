"""
Unit tests for configuration corruption recovery.

Verifies the recovery contract of ConfigManager + ConfigRecoveryManager:
- a corrupt config with no backups raises ConfigurationError and the
  user's file is never overwritten (no fabricated defaults)
- a corrupt config with a valid backup is restored from that backup,
  preserving the original values
"""

import pytest
import yaml

from powernight.core.config.exceptions import ConfigurationError
from powernight.core.config.manager import ConfigManager
import powernight.core.config.manager as manager_module


ORIGINAL_EMAIL = "real.owner@powernight-test.io"

VALID_CONFIG = {
    "powerwall": {"tesla_email": ORIGINAL_EMAIL},
    "automation": {"enabled": False, "schedule": []},
    "web_interface": {"enabled": True, "host": "0.0.0.0", "port": 8080},
    "logging": {"level": "INFO", "file_path": "logs/powernight.log"},
    "monitoring": {"enabled": False},
}

CORRUPT_YAML = "powerwall: [unclosed\n  ::: definitely not yaml {{{\n"

# Env vars that ConfigManager._apply_env_overrides consults; cleared so the
# host environment cannot leak into assertions.
OVERRIDE_ENV_VARS = [
    "POWERNIGHT_LOG_LEVEL",
    "POWERNIGHT_WEB_PORT",
    "POWERNIGHT_WEB_HOST",
    "POWERNIGHT_WEB_DEBUG",
    "POWERNIGHT_POWERWALL_EMAIL",
    "POWERNIGHT_POWERWALL_TIMEOUT",
    "POWERNIGHT_AUTOMATION_ENABLED",
    "POWERNIGHT_AUTOMATION_INTERVAL",
    "POWERNIGHT_MONITORING_ENABLED",
]


@pytest.fixture
def reset_singleton(monkeypatch):
    """Reset the ConfigManager singleton before and after each test."""
    for var in OVERRIDE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    def _reset():
        ConfigManager._instance = None
        manager_module._config_manager = None

    _reset()
    yield _reset
    _reset()


def test_corrupt_config_without_backups_raises_and_preserves_file(tmp_path, reset_singleton):
    """A corrupt config with no backups must fail loudly and stay untouched."""
    config_path = tmp_path / "config.yaml"
    corrupt_bytes = CORRUPT_YAML.encode()
    config_path.write_bytes(corrupt_bytes)

    manager = ConfigManager()
    with pytest.raises(ConfigurationError):
        manager.load_config(config_path)

    # The user's file must be byte-identical: recovery must never overwrite
    # it with fabricated defaults.
    assert config_path.read_bytes() == corrupt_bytes

    # And no backup or replacement artifacts may have been created.
    backup_dir = tmp_path / ".backups"
    assert not backup_dir.exists() or not any(backup_dir.iterdir())


def test_corrupt_config_recovers_from_valid_backup(tmp_path, reset_singleton):
    """A corrupt config with a valid backup is restored from that backup."""
    config_path = tmp_path / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(VALID_CONFIG, f)

    manager = ConfigManager()
    loaded = manager.load_config(config_path)
    assert loaded.powerwall.tesla_email == ORIGINAL_EMAIL

    # save_config with auto-backup enabled snapshots the existing file
    # into .backups/ before rewriting it.
    manager.save_config()
    backups = manager.list_backups(config_path)
    assert backups, "expected save_config to create a backup of the config"

    # Corrupt the live config file.
    config_path.write_text(CORRUPT_YAML)

    # A fresh manager (new process simulation) must recover via the backup.
    reset_singleton()
    recovered_manager = ConfigManager()
    recovered = recovered_manager.load_config(config_path)

    # Recovery must restore the user's real settings, not fabricate defaults.
    assert recovered.powerwall.tesla_email == ORIGINAL_EMAIL
    assert recovered.powerwall.tesla_email != "user@example.com"

    # The file on disk must be valid again and carry the original values.
    on_disk = yaml.safe_load(config_path.read_text())
    assert on_disk["powerwall"]["tesla_email"] == ORIGINAL_EMAIL
