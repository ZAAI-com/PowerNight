"""Preset conflicts are normal errors, not leaked database exceptions."""

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from powernight.core.config.schema import create_default_config
from powernight.core.database import migration, services
from powernight.core.database.exceptions import DatabaseError, PresetNameConflictError
from powernight.core.database.models import TaskPreset


@pytest.fixture
def service(monkeypatch):
    engine = create_engine('sqlite:///:memory:')
    TaskPreset.__table__.create(engine)

    @contextmanager
    def session_context():
        with Session(engine) as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    monkeypatch.setattr(services, 'get_db_session_context', session_context)
    yield services.TaskPresetService()
    engine.dispose()


@pytest.fixture
def preset_client(service, monkeypatch):
    from powernight.web.api import auth, tasks_api

    monkeypatch.setattr(auth, 'get_config', create_default_config)
    app = Flask(__name__)
    app.register_blueprint(tasks_api.tasks_blueprint)
    return app.test_client()


def test_duplicate_name_is_a_typed_conflict_and_does_not_poison_session(service):
    service.create_preset('Night', 'reserve', {'reserve': 40})
    with pytest.raises(PresetNameConflictError, match='name already exists') as caught:
        service.create_preset('Night', 'reserve', {'reserve': 60})
    assert 'INSERT' not in str(caught.value)
    assert service.create_preset('Morning', 'reserve', {'reserve': 20})['name'] == 'Morning'
    assert len(service.list_presets()) == 2


def test_other_integrity_errors_are_not_reported_as_name_conflicts(service):
    with pytest.raises(DatabaseError) as caught:
        service.create_preset(None, 'reserve')
    assert not isinstance(caught.value, PresetNameConflictError)
    assert str(caught.value) == 'Failed to create preset'


def test_duplicate_preset_api_returns_friendly_conflict(preset_client):
    payload = {'name': 'Night', 'command': 'reserve', 'command_params': {'reserve': 40}}
    assert preset_client.post('/api/v1/tasks/presets', json=payload).status_code == 201
    response = preset_client.post('/api/v1/tasks/presets', json=payload)
    assert response.status_code == 409
    assert response.json['error'] == 'Conflict'
    assert response.json['message'] == 'A preset with this name already exists'
    assert 'INSERT' not in response.get_data(as_text=True)
    assert 'sqlalchemy' not in response.get_data(as_text=True)


def test_preset_api_hides_unexpected_database_errors(preset_client, monkeypatch):
    monkeypatch.setattr(services.TaskPresetService, 'create_preset', MagicMock(
        side_effect=DatabaseError('SELECT private database details')
    ))
    response = preset_client.post('/api/v1/tasks/presets', json={
        'name': 'Night', 'command': 'reserve', 'command_params': {'reserve': 40},
    })
    assert response.status_code == 500
    assert response.json['message'] == 'Failed to create preset'
    assert 'private database details' not in response.get_data(as_text=True)


def test_builtin_seeding_tolerates_concurrent_name_conflicts(monkeypatch):
    service = MagicMock()
    service.preset_exists_by_name.return_value = False
    service.create_preset.side_effect = PresetNameConflictError('Already exists')
    monkeypatch.setattr(migration, 'initialize_database', lambda: None)
    monkeypatch.setattr(migration, 'TaskPresetService', lambda: service)
    assert migration.seed_builtin_presets() is True
    assert service.create_preset.call_count == len(migration.BUILTIN_PRESETS)
