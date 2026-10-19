"""File settings must stay separate from runtime environment overrides."""

import json
import logging
from copy import deepcopy

import pytest
import yaml

from powernight.core.config.manager import ConfigManager
from powernight.core.config.schema import PowerNightConfig


@pytest.fixture
def manager(monkeypatch):
    monkeypatch.setattr(ConfigManager, '_instance', None)
    for name in (
        'POWERNIGHT_API_KEY', 'POWERNIGHT_AUTH_ENABLED', 'TESLA_EMAIL',
        'POWERNIGHT_POWERWALL_EMAIL', 'POWERNIGHT_WEB_PORT',
    ):
        monkeypatch.delenv(name, raising=False)
    result = ConfigManager()
    result.set_auto_recovery(False)
    return result


@pytest.mark.parametrize('suffix', ['yaml', 'json'])
@pytest.mark.parametrize('file_key', [None, 'file-owned-key'])
def test_repeated_saves_preserve_file_values_and_runtime_overrides(
    manager, tmp_path, monkeypatch, suffix, file_key
):
    data = {
        'powerwall': {'tesla_email': 'owner@example.com'},
        'web_interface': {'api_key': file_key, 'auth_enabled': False, 'port': 8020},
        'automation': {'timezone': 'UTC'},
    }
    path = tmp_path / f'config.{suffix}'
    path.write_text(yaml.safe_dump(data) if suffix == 'yaml' else json.dumps(data))
    monkeypatch.setenv('POWERNIGHT_API_KEY', 'runtime-only-secret')
    monkeypatch.setenv('TESLA_EMAIL', 'your-email@example.com')
    monkeypatch.setenv('POWERNIGHT_WEB_PORT', '8123')

    manager.load_config(path)
    for zone in ('Europe/Berlin', 'America/New_York'):
        config = manager.get_config()
        config.automation.timezone = zone
        manager.save_config(config)
        runtime = manager.get_config()
        assert runtime.web_interface.api_key == 'runtime-only-secret'
        assert runtime.web_interface.auth_enabled is True
        assert runtime.web_interface.port == 8123
        assert runtime.powerwall.tesla_email == 'your-email@example.com'

        saved = yaml.safe_load(path.read_text())
        assert saved['web_interface'] == data['web_interface']
        assert saved['powerwall'] == data['powerwall']
        assert saved['automation']['timezone'] == zone

    backups = list((tmp_path / '.backups').iterdir())
    assert len(backups) == 2
    for saved_path in [path, *backups]:
        assert 'runtime-only-secret' not in saved_path.read_text()
        assert 'your-email@example.com' not in saved_path.read_text()

    for name in ('POWERNIGHT_API_KEY', 'TESLA_EMAIL', 'POWERNIGHT_WEB_PORT'):
        monkeypatch.delenv(name)
    reloaded = manager.reload_config()
    assert reloaded.web_interface.api_key == file_key
    assert reloaded.web_interface.auth_enabled is bool(file_key)
    assert reloaded.powerwall.tesla_email == 'owner@example.com'
    assert reloaded.web_interface.port == 8020


def test_partial_config_replacement_persists_only_user_edits(manager, tmp_path, monkeypatch):
    path = tmp_path / 'config.yaml'
    path.write_text('powerwall:\n  tesla_email: owner@example.com\n')
    monkeypatch.setenv('POWERNIGHT_API_KEY', 'runtime-only-secret')
    config = manager.load_config(path)
    updates = config.to_dict()
    updates['powerwall']['timeout'] = 45
    updates['automation']['schedule'] = [{'time': '01:00', 'percentage': 0}]
    manager.save_config(PowerNightConfig.from_dict(updates))

    saved = yaml.safe_load(path.read_text())
    assert 'web_interface' not in saved
    assert saved['powerwall']['timeout'] == 45
    assert saved['automation']['schedule'][0]['percentage'] == 0
    assert manager.get_config().web_interface.api_key == 'runtime-only-secret'


def test_override_does_not_mutate_source_or_log_secret(manager, monkeypatch, caplog):
    source = {'web_interface': {'api_key': 'file-key'}}
    original = deepcopy(source)
    monkeypatch.setenv('POWERNIGHT_API_KEY', 'runtime-only-secret')
    with caplog.at_level(logging.DEBUG):
        overridden = manager._apply_env_overrides(source)
    assert source == original
    assert overridden['web_interface']['api_key'] == 'runtime-only-secret'
    assert 'runtime-only-secret' not in caplog.text


def test_create_default_preserves_loaded_persistence_state(manager, tmp_path, monkeypatch):
    path = tmp_path / 'config.yaml'
    path.write_text('powerwall:\n  tesla_email: owner@example.com\n')
    monkeypatch.setenv('POWERNIGHT_API_KEY', 'runtime-only-secret')
    manager.load_config(path)
    manager.create_default_config_file(tmp_path / 'defaults.yaml')
    config = manager.get_config()
    config.automation.timezone = 'Europe/Berlin'
    manager.save_config()
    assert 'runtime-only-secret' not in path.read_text()
    assert 'runtime-only-secret' not in (tmp_path / 'defaults.yaml').read_text()
    assert yaml.safe_load(path.read_text())['powerwall']['tesla_email'] == 'owner@example.com'
