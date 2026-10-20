"""Tests for truthful Tesla authentication and connection API reporting."""

from unittest.mock import Mock

import pytest


@pytest.fixture(autouse=True)
def configured_auth(monkeypatch, app_config):
    from powernight.web.api import auth, auth_api

    monkeypatch.setattr(auth, 'get_config', lambda: app_config)
    monkeypatch.setattr(auth_api, 'get_config', lambda: app_config)


@pytest.mark.unit
def test_auth_info_separates_valid_token_from_disconnected_session(
    client, mock_powerwall_connector, monkeypatch
):
    from powernight.web.api import auth_api

    monkeypatch.setattr(auth_api.oauth_manager, 'get_auth_status', lambda: {
        'authenticated': True,
        'expires_at': None,
        'expires_in_seconds': 3600,
        'token_expired': False,
    })
    monkeypatch.setattr(auth_api.oauth_manager.auth_storage, 'load_auth_data', lambda: {
        'email': 'owner@example.com',
        'site': {'id': 123},
        'access_token': 'access-token',
        'refresh_token': 'refresh-token',
    })
    monkeypatch.setattr(auth_api.oauth_manager.auth_storage, 'get_storage_info', lambda: {})
    mock_powerwall_connector.get_connection_status.return_value = {
        'connected': False,
        'connection_status': 'disconnected',
        'last_connection_attempt': '2026-10-03T12:00:00+00:00',
        'connection_error': 'Tesla cloud is unreachable. Check container networking and try again.',
    }

    response = client.get('/api/auth/tesla/info')

    assert response.status_code == 200
    assert response.json['data']['authenticated'] is True
    assert response.json['data']['token_expired'] is False
    assert response.json['data']['connected'] is False
    assert response.json['data']['connection_status'] == 'disconnected'


@pytest.mark.unit
def test_connection_test_uses_shared_connector_and_returns_502(
    client, mock_powerwall_connector, monkeypatch
):
    from powernight.web.api import auth_api

    monkeypatch.setattr(auth_api.oauth_manager.auth_storage, 'has_auth_data', lambda: True)
    mock_powerwall_connector.ensure_connected.side_effect = RuntimeError('upstream unavailable')
    mock_powerwall_connector.get_connection_status.return_value = {
        'connected': False,
        'connection_status': 'disconnected',
        'last_connection_attempt': '2026-10-03T12:00:00+00:00',
        'connection_error': 'Tesla cloud is unreachable. Check container networking and try again.',
    }

    response = client.post('/api/auth/tesla/test-connection')

    assert response.status_code == 502
    assert response.json['data']['connected'] is False
    assert response.json['error'].startswith('Tesla cloud is unreachable')
    # Retrying must not drop a healthy session (a new one needs a fresh login)
    mock_powerwall_connector.disconnect.assert_not_called()
    mock_powerwall_connector.ensure_connected.assert_called_once()


@pytest.mark.unit
def test_oauth_completion_reconnects_shared_connector(
    client, mock_powerwall_connector, monkeypatch
):
    from powernight.web.api import auth_api

    result = {
        'success': True,
        'message': 'Setup complete.',
        'email': 'owner@example.com',
        'site': {'id': 123, 'name': 'Home'},
        'credentials_saved': True,
    }
    monkeypatch.setattr(auth_api.oauth_manager, 'complete_setup', Mock(return_value=result))
    mock_powerwall_connector.get_connection_status.return_value = {
        'connected': True,
        'connection_status': 'connected',
        'last_connection_attempt': '2026-10-03T12:00:00+00:00',
        'connection_error': None,
    }

    response = client.post('/api/auth/setup/complete', json={
        'session_id': 'session-1',
        'site_id': '123',
    })

    assert response.status_code == 200
    assert response.json['credentials_saved'] is True
    assert response.json['connected'] is True
    mock_powerwall_connector.ensure_connected.assert_called_once()


@pytest.mark.unit
def test_oauth_completion_keeps_credentials_when_live_connection_fails(
    client, mock_powerwall_connector, monkeypatch
):
    from powernight.web.api import auth_api

    result = {
        'success': True,
        'message': 'Setup complete.',
        'email': 'owner@example.com',
        'site': {'id': 123, 'name': 'Home'},
        'credentials_saved': True,
    }
    monkeypatch.setattr(auth_api.oauth_manager, 'complete_setup', Mock(return_value=result))
    mock_powerwall_connector.ensure_connected.side_effect = RuntimeError('network down')
    mock_powerwall_connector.get_connection_status.return_value = {
        'connected': False,
        'connection_status': 'disconnected',
        'last_connection_attempt': '2026-10-03T12:00:00+00:00',
        'connection_error': 'Tesla cloud is unreachable. Check container networking and try again.',
    }

    response = client.post('/api/auth/setup/complete', json={
        'session_id': 'session-1',
        'site_id': '123',
    })

    assert response.status_code == 502
    assert response.json['credentials_saved'] is True
    assert response.json['connected'] is False
    assert response.json['connection_error'].startswith('Tesla cloud is unreachable')


@pytest.mark.unit
def test_token_import_returns_setup_session(client, monkeypatch):
    from powernight.web.api import auth_api

    monkeypatch.setattr(auth_api.oauth_manager.auth_storage, 'has_auth_data', lambda: False)
    import_tokens = Mock(return_value={
        'success': True,
        'session_id': 'session-1',
        'sites': [{'id': 123, 'name': 'Home'}],
        'expires_at': None,
    })
    monkeypatch.setattr(auth_api.oauth_manager, 'import_tokens', import_tokens)

    response = client.post('/api/auth/setup/tokens', json={
        'email': ' owner@example.com ',
        'refresh_token': 'rt',
        'access_token': 'at',
    })

    assert response.status_code == 200
    assert response.json['session_id'] == 'session-1'
    assert response.json['sites'] == [{'id': 123, 'name': 'Home'}]
    import_tokens.assert_called_once_with('owner@example.com', 'rt', 'at')


@pytest.mark.unit
def test_token_import_requires_email(client, monkeypatch):
    from powernight.web.api import auth_api

    monkeypatch.setattr(auth_api.oauth_manager.auth_storage, 'has_auth_data', lambda: False)
    response = client.post('/api/auth/setup/tokens', json={'refresh_token': 'rt', 'access_token': 'at'})

    assert response.status_code == 400
    assert response.json['error'] == 'Email is required'


@pytest.mark.unit
def test_sign_out_clears_tokens_and_disconnects(client, mock_powerwall_connector, monkeypatch):
    from powernight.web.api import auth_api

    monkeypatch.setattr(auth_api.oauth_manager, 'revoke_tokens', Mock(return_value=True))

    response = client.post('/api/auth/tesla/logout')

    assert response.status_code == 200
    assert response.json['success'] is True
    mock_powerwall_connector.disconnect.assert_called_once()
