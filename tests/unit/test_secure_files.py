"""Credential files must never be published partially or with public permissions."""
import json
import os
from pathlib import Path
import stat
from unittest.mock import patch

import pytest

from powernight.utils.secure_files import protect_directory, write_private_file
from powernight.core.auth.token_storage import PyPowerwallAuthStorage
from powernight.core.config.backup import ConfigBackupManager
from powernight.web.app import _load_or_create_secret


def mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_private_publish_and_exclusive_winner(tmp_path):
    path = tmp_path / 'secret'
    real_replace = os.replace

    def inspect_publication(source, destination):
        assert mode(Path(source)) == 0o600
        assert Path(source).read_text() == 'credential'
        real_replace(source, destination)

    with patch('os.replace', side_effect=inspect_publication):
        write_private_file(path, 'credential')
    assert not write_private_file(path, 'losing credential', exclusive=True)
    assert path.read_text() == 'credential'
    assert mode(path) == 0o600
    assert list(tmp_path.iterdir()) == [path]


def test_permission_failure_keeps_original_and_cleans_tempfile(tmp_path):
    path = tmp_path / 'secret'
    path.write_text('original')
    with patch('os.fchmod', side_effect=PermissionError('denied')):
        with pytest.raises(PermissionError):
            write_private_file(path, 'replacement')
    assert path.read_text() == 'original'
    assert list(tmp_path.iterdir()) == [path]


def test_directory_protection_fails_closed(tmp_path):
    directory = tmp_path / 'auth'
    with patch('os.chmod', side_effect=PermissionError('denied')):
        with pytest.raises(PermissionError):
            PyPowerwallAuthStorage(directory)
    protect_directory(directory)
    assert mode(directory) == 0o700


def test_auth_files_remain_plain_json_but_private(tmp_path):
    storage = PyPowerwallAuthStorage(tmp_path / 'auth')
    storage.store_auth_data('test@example.com', {'access_token': 'test-token'}, {'id': 123})
    auth = storage.storage_path / '.pypowerwall.auth'
    assert json.loads(auth.read_text())['test@example.com']['sso']['access_token'] == 'test-token'
    assert mode(auth) == mode(storage.storage_path / '.pypowerwall.site') == 0o600


def test_backups_harden_older_files_and_restore_privately(tmp_path):
    config = tmp_path / 'config.yaml'
    config.write_text('api_key: example-only')
    directory = tmp_path / '.backups'
    directory.mkdir()
    old = directory / 'config_old.yaml'
    old.write_text('api_key: old-example')
    old.chmod(0o644)
    backup = ConfigBackupManager().create_backup(config)
    assert backup is not None
    assert mode(backup) == mode(old) == 0o600
    assert mode(directory) == 0o700
    assert ConfigBackupManager().restore_from_backup(config, backup)
    assert mode(config) == 0o600


def test_backup_retries_exclusive_publication_collision(tmp_path):
    config = tmp_path / 'config.yaml'
    config.write_text('value: original')
    with patch('powernight.core.config.backup.write_private_file', side_effect=[False, True]) as write:
        result = ConfigBackupManager().create_backup(config)
    assert write.call_count == 2
    assert result == write.call_args.args[0]
    assert result.name.endswith('_1.yaml')


def test_flask_secret_persists_and_repairs_empty_file(tmp_path, monkeypatch):
    monkeypatch.setenv('POWERNIGHT_DATA_PATH', str(tmp_path))
    secret = _load_or_create_secret()
    assert _load_or_create_secret() == secret
    path = tmp_path / '.flask_secret'
    assert mode(path) == 0o600
    path.write_text('')
    repaired = _load_or_create_secret()
    assert repaired and repaired != secret
    assert path.read_text() == repaired
    assert _load_or_create_secret() == repaired
    assert mode(path) == 0o600


def test_concurrent_empty_secret_repair_shares_one_key(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setenv('POWERNIGHT_DATA_PATH', str(tmp_path))
    path = tmp_path / '.flask_secret'
    path.touch()
    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(lambda _: _load_or_create_secret(), range(8)))
    assert len(set(values)) == 1
    assert path.read_text() == values[0]


def test_secret_write_failure_warns_and_uses_ephemeral_key(tmp_path, monkeypatch, caplog):
    import logging
    monkeypatch.setenv('POWERNIGHT_DATA_PATH', str(tmp_path))
    logger = logging.getLogger('powernight.web.app')
    monkeypatch.setattr(logger, 'handlers', [*logger.handlers, caplog.handler])
    with patch('powernight.web.app.write_private_file', side_effect=PermissionError('denied')):
        assert _load_or_create_secret()
    assert not (tmp_path / '.flask_secret').exists()
    assert 'sessions will not survive restarts' in caplog.text


def test_backup_links_are_not_listed_or_restored(tmp_path):
    config = tmp_path / 'config.yaml'
    config.write_text('original')
    manager = ConfigBackupManager()
    directory = manager.get_backup_dir(config)
    directory.mkdir()
    external = tmp_path / 'other.yaml'
    external.write_text('untrusted')
    link = directory / 'config_link.yaml'
    link.symlink_to(external)
    assert manager.list_backups(config) == []
    assert not manager.restore_from_backup(config, link)
    assert not manager.restore_from_backup(config)
    assert config.read_text() == 'original'
    assert external.read_text() == 'untrusted'


def test_restore_preserves_config_symlink(tmp_path):
    target = tmp_path / 'actual.yaml'
    target.write_text('original')
    config = tmp_path / 'config.yaml'
    config.symlink_to(target)
    manager = ConfigBackupManager()
    backup = manager.create_backup(config)
    target.write_text('changed')
    assert manager.restore_from_backup(config, backup)
    assert config.is_symlink()
    assert target.read_text() == 'original'
    assert mode(target) == 0o600


def test_existing_backup_permissions_fail_closed(tmp_path):
    config = tmp_path / 'config.yaml'
    config.write_text('credential')
    directory = tmp_path / '.backups'
    directory.mkdir()
    old = directory / 'config_old.yaml'
    old.write_text('old credential')
    real_chmod = os.chmod

    def deny_old_backup(path, mode):
        if path == old:
            raise PermissionError('denied')
        real_chmod(path, mode)

    manager = ConfigBackupManager()
    with patch('os.chmod', side_effect=deny_old_backup):
        with pytest.raises(PermissionError):
            manager.list_backups(config)
        assert manager.create_backup(config) is None
    assert list(directory.iterdir()) == [old]
