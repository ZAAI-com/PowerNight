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


def test_flask_secret_persists_and_empty_file_does_not_overwrite_winner(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv('POWERNIGHT_DATA_PATH', str(tmp_path))
    secret = _load_or_create_secret()
    assert _load_or_create_secret() == secret
    path = tmp_path / '.flask_secret'
    assert mode(path) == 0o600
    path.write_text('')
    assert _load_or_create_secret()
    assert path.read_text() == ''
    assert 'sessions will not survive restarts' in caplog.text
