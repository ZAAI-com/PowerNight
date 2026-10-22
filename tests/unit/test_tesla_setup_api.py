"""
HTTP contract of the Tesla setup endpoints used by the Settings wizard.

Runs the real TeslaOAuthManager (with a fake clock) behind the real Flask
app; only Tesla and the shared connector are mocked.
"""

import urllib.parse
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from powernight.core.auth.setup_attempts import SiteDiscoveryError
from powernight.core.auth.tesla_oauth import TeslaOAuthManager


pytestmark = pytest.mark.unit

EMAIL = 'owner@example.com'
SITES = [
    {'id': 111222, 'name': 'Home', 'type': 'battery', 'resource_type': 'battery', 'state': 'online'},
    {'id': 333444, 'name': 'Cabin', 'type': 'battery', 'resource_type': 'battery', 'state': 'online'},
]
TOKENS = {
    'access_token': 'eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJvd25lciJ9.bmV3LWFjY2Vzcy10b2tlbg',
    'refresh_token': 'new-refresh-token-value',
    'expires_in': 28800,
}
EXCHANGE = 'powernight.core.auth.tesla_oauth.tesla_auth._exchange_code'


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


@pytest.fixture
def data_path(tmp_path, monkeypatch):
    path = tmp_path / 'data'
    monkeypatch.setenv('POWERNIGHT_DATA_PATH', str(path))
    return path


@pytest.fixture
def app(data_path, app_config, mock_powerwall_connector, temp_dir, monkeypatch):
    from powernight.web.app import create_app

    static_dir = temp_dir / 'dist'
    static_dir.mkdir(exist_ok=True)
    (static_dir / 'index.html').write_text('<html></html>')
    monkeypatch.setenv('POWERNIGHT_STATIC_PATH', str(static_dir))
    return create_app(app_config, testing=True, powerwall_connector=mock_powerwall_connector)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture(autouse=True)
def manager(app, app_config, data_path, clock, monkeypatch, mock_powerwall_connector):
    from powernight.web.api import auth, auth_api

    monkeypatch.setattr(auth, 'get_config', lambda: app_config)
    monkeypatch.setattr(auth_api, 'get_config', lambda: app_config)
    manager = TeslaOAuthManager(storage_path=str(data_path), clock=clock, expiry_timers=False)
    monkeypatch.setattr(auth_api, 'oauth_manager', manager)
    mock_powerwall_connector.replace_credentials.side_effect = lambda write: write()
    mock_powerwall_connector.get_connection_status.return_value = {
        'connected': True,
        'connection_status': 'connected',
        'last_connection_attempt': '2026-10-21T12:00:00+00:00',
        'connection_error': None,
        'connection_error_code': None,
        'auth_rejected': False,
    }
    return manager


def start(client):
    response = client.post('/api/auth/setup/start', json={'email': EMAIL})
    assert response.status_code == 200
    query = urllib.parse.parse_qs(urllib.parse.urlparse(response.json['auth_url']).query)
    return response.json['session_id'], query['state'][0]


def callback(state, code='code-1'):
    return f'tesla://auth/callback?code={code}&state={state}'


def sign_in(client, manager, sites=SITES):
    session_id, state = start(client)
    with patch(EXCHANGE, return_value=dict(TOKENS)), \
            patch.object(manager, 'get_energy_sites', return_value=list(sites)):
        response = client.post('/api/auth/setup/callback', json={
            'session_id': session_id, 'callback_url': callback(state),
        })
    assert response.status_code == 200
    return session_id


def store_old_credentials(manager, data_path):
    manager.auth_storage.store_auth_data(
        'old@example.com', {'access_token': 'old-access', 'refresh_token': 'old-refresh'}, {'id': 1}
    )
    return {name: (data_path / name).read_bytes() for name in ('.pypowerwall.auth', '.pypowerwall.site')}


class TestStart:
    def test_start_returns_attempt_with_setup_expiry(self, client):
        response = client.post('/api/auth/setup/start', json={'email': ' owner@example.com '})

        assert response.status_code == 200
        assert response.headers['Cache-Control'] == 'no-store'
        body = response.json
        assert body['auth_url'].startswith('https://auth.tesla.com/oauth2/v3/authorize?')
        assert body['setup_expires_at'] == '2026-10-21T12:10:00+00:00'
        assert body['setup']['step'] == 'awaiting_callback'
        assert body['setup']['email'] == EMAIL
        assert body['setup']['setup_expires_in_seconds'] == 600

    @pytest.mark.parametrize('payload, message', [
        ({}, 'Email is required'),
        ({'email': '   '}, 'Email cannot be empty'),
    ])
    def test_start_requires_an_email(self, client, payload, message):
        response = client.post('/api/auth/setup/start', json=payload)
        assert response.status_code == 400
        assert response.json['error'] == message
        assert response.json['error_code'] == 'INVALID_INPUT'


class TestCallback:
    def test_callback_returns_sites_and_progress(self, client, manager):
        session_id, state = start(client)
        with patch(EXCHANGE, return_value=dict(TOKENS)), \
                patch.object(manager, 'get_energy_sites', return_value=SITES):
            response = client.post('/api/auth/setup/callback', json={
                'session_id': session_id,
                'callback_url': f"Failed to launch '{callback(state)}' because the scheme does not have a registered handler.",
            })

        assert response.status_code == 200
        assert response.json['sites'] == SITES
        assert response.json['setup']['step'] == 'selecting_site'
        assert response.json['setup']['auth_url'] is None

    def test_pasted_sign_in_page_gets_the_hint(self, client):
        session_id, _ = start(client)
        status = client.get(f'/api/auth/setup/status/{session_id}').json['data']
        response = client.post('/api/auth/setup/callback', json={
            'session_id': session_id, 'callback_url': status['auth_url'],
        })
        assert response.status_code == 400
        assert response.json['error_code'] == 'INVALID_INPUT'
        assert response.json['error'].startswith('This is the sign-in page, not the returned login result.')

    def test_state_mismatch_is_rejected(self, client):
        session_id, _ = start(client)
        response = client.post('/api/auth/setup/callback', json={
            'session_id': session_id, 'callback_url': callback('other-attempt'),
        })
        assert response.status_code == 400
        assert response.json['error_code'] == 'STATE_MISMATCH'

    def test_unknown_session_is_404(self, client):
        response = client.post('/api/auth/setup/callback', json={
            'session_id': 'unknown-session-id-0123456789', 'callback_url': callback('x'),
        })
        assert response.status_code == 404
        assert response.json['error_code'] == 'SETUP_NOT_FOUND'
        assert 'session' in response.json['error'].lower()

    def test_expired_attempt_is_410(self, client, clock):
        session_id, state = start(client)
        clock.advance(minutes=10)
        response = client.post('/api/auth/setup/callback', json={
            'session_id': session_id, 'callback_url': callback(state),
        })
        assert response.status_code == 410
        assert response.json['error_code'] == 'SETUP_EXPIRED'

    def test_unavailable_site_discovery_is_502_and_retryable(self, client, manager):
        session_id, state = start(client)
        with patch(EXCHANGE, return_value=dict(TOKENS)) as exchange, \
                patch.object(manager, 'get_energy_sites',
                             side_effect=[SiteDiscoveryError(rejected=False, status=503), SITES]):
            first = client.post('/api/auth/setup/callback', json={
                'session_id': session_id, 'callback_url': callback(state),
            })
            retry = client.post('/api/auth/setup/sites', json={'session_id': session_id})

        assert first.status_code == 502
        assert first.json['error_code'] == 'SITE_DISCOVERY_UNAVAILABLE'
        assert retry.status_code == 200
        assert retry.json['sites'] == SITES
        assert exchange.call_count == 1

    def test_sites_retry_before_sign_in_is_409(self, client):
        session_id, _ = start(client)
        response = client.post('/api/auth/setup/sites', json={'session_id': session_id})
        assert response.status_code == 409
        assert response.json['error_code'] == 'WRONG_STEP'


class TestNever401ForTesla:
    def test_tesla_401_during_exchange_is_not_an_app_401(self, client):
        session_id, state = start(client)
        with patch(EXCHANGE, side_effect=RuntimeError('Token exchange failed (HTTP 401): unauthorized')):
            response = client.post('/api/auth/setup/callback', json={
                'session_id': session_id, 'callback_url': callback(state),
            })
        assert response.status_code == 400
        assert response.json['error_code'] == 'EXCHANGE_FAILED'

    def test_tesla_401_during_discovery_is_not_an_app_401(self, client, manager):
        session_id, state = start(client)
        with patch(EXCHANGE, return_value=dict(TOKENS)), \
                patch.object(manager, 'get_energy_sites',
                             side_effect=SiteDiscoveryError(rejected=True, status=401)):
            response = client.post('/api/auth/setup/callback', json={
                'session_id': session_id, 'callback_url': callback(state),
            })
        assert response.status_code == 400
        assert response.json['error_code'] == 'TESLA_DENIED'

    def test_rejected_imported_token_is_not_an_app_401(self, client, manager):
        with patch.object(manager, 'get_energy_sites',
                          side_effect=SiteDiscoveryError(rejected=True, status=401)):
            response = client.post('/api/auth/setup/tokens', json={
                'email': EMAIL, 'refresh_token': 'rt', 'access_token': TOKENS['access_token'],
            })
        assert response.status_code == 400
        assert response.json['error_code'] == 'TESLA_DENIED'


class TestComplete:
    def test_complete_swaps_credentials_then_reconnects(self, client, manager, data_path,
                                                        mock_powerwall_connector):
        session_id = sign_in(client, manager)
        response = client.post('/api/auth/setup/complete', json={
            'session_id': session_id, 'site_id': '333444',
        })

        assert response.status_code == 200
        assert response.json['credentials_saved'] is True
        assert response.json['connected'] is True
        assert response.json['connection_state'] == 'connected'
        assert response.json['site']['id'] == 333444
        mock_powerwall_connector.replace_credentials.assert_called_once()
        mock_powerwall_connector.ensure_connected.assert_called_once()
        mock_powerwall_connector.disconnect.assert_not_called()
        assert (data_path / '.pypowerwall.site').read_text() == '333444'

    def test_duplicate_completion_replays_without_reconnecting(self, client, manager,
                                                               mock_powerwall_connector):
        session_id = sign_in(client, manager)
        payload = {'session_id': session_id, 'site_id': '111222'}
        client.post('/api/auth/setup/complete', json=payload)
        replay = client.post('/api/auth/setup/complete', json=payload)

        assert replay.status_code == 200
        assert replay.json['duplicate'] is True
        mock_powerwall_connector.replace_credentials.assert_called_once()
        mock_powerwall_connector.ensure_connected.assert_called_once()

    def test_failed_write_is_500_without_reconnect(self, client, manager, data_path,
                                                   mock_powerwall_connector):
        before = store_old_credentials(manager, data_path)
        session_id = sign_in(client, manager)
        mock_powerwall_connector.replace_credentials.side_effect = OSError('disk full')

        response = client.post('/api/auth/setup/complete', json={
            'session_id': session_id, 'site_id': '111222',
        })

        assert response.status_code == 500
        assert response.json['error_code'] == 'CREDENTIAL_WRITE_FAILED'
        assert response.json['credentials_saved'] is False
        mock_powerwall_connector.ensure_connected.assert_not_called()
        assert {name: (data_path / name).read_bytes() for name in before} == before

    def test_unknown_site_is_400(self, client, manager):
        session_id = sign_in(client, manager)
        response = client.post('/api/auth/setup/complete', json={
            'session_id': session_id, 'site_id': '999',
        })
        assert response.status_code == 400
        assert response.json['error_code'] == 'INVALID_SITE'


class TestFailedReconnectKeepsCredentials:
    """Reconnecting must leave the stored sign-in untouched until a new one is saved."""

    def _assert_unchanged(self, before, data_path, connector):
        assert {name: (data_path / name).read_bytes() for name in before} == before
        connector.replace_credentials.assert_not_called()

    def test_exchange_failure(self, client, manager, data_path, mock_powerwall_connector):
        before = store_old_credentials(manager, data_path)
        session_id, state = start(client)
        with patch(EXCHANGE, side_effect=RuntimeError('Token exchange failed (HTTP 400): bad')):
            client.post('/api/auth/setup/callback', json={'session_id': session_id, 'callback_url': callback(state)})
        self._assert_unchanged(before, data_path, mock_powerwall_connector)

    def test_discovery_failure(self, client, manager, data_path, mock_powerwall_connector):
        before = store_old_credentials(manager, data_path)
        session_id, state = start(client)
        with patch(EXCHANGE, return_value=dict(TOKENS)), \
                patch.object(manager, 'get_energy_sites', side_effect=SiteDiscoveryError(True, 403)):
            client.post('/api/auth/setup/callback', json={'session_id': session_id, 'callback_url': callback(state)})
        self._assert_unchanged(before, data_path, mock_powerwall_connector)

    def test_cancel(self, client, manager, data_path, mock_powerwall_connector):
        before = store_old_credentials(manager, data_path)
        session_id = sign_in(client, manager)
        assert client.post('/api/auth/setup/cancel', json={'session_id': session_id}).status_code == 200
        response = client.post('/api/auth/setup/complete', json={'session_id': session_id, 'site_id': '111222'})
        assert response.status_code == 410
        self._assert_unchanged(before, data_path, mock_powerwall_connector)

    def test_expiry(self, client, manager, data_path, clock, mock_powerwall_connector):
        before = store_old_credentials(manager, data_path)
        session_id = sign_in(client, manager)
        clock.advance(minutes=11)
        response = client.post('/api/auth/setup/complete', json={'session_id': session_id, 'site_id': '111222'})
        assert response.status_code == 410
        self._assert_unchanged(before, data_path, mock_powerwall_connector)


class TestCancelAndStatus:
    def test_cancel_contract(self, client, manager):
        session_id, _ = start(client)
        first = client.post('/api/auth/setup/cancel', json={'session_id': session_id})
        again = client.post('/api/auth/setup/cancel', json={'session_id': session_id})
        unknown = client.post('/api/auth/setup/cancel', json={'session_id': 'unknown-session-id-0123456789'})

        assert first.status_code == 200 and first.json['setup']['step'] == 'cancelled'
        assert again.status_code == 200 and again.json['already_ended'] is True
        assert unknown.status_code == 404

    def test_cancel_after_completion_is_409(self, client, manager):
        session_id = sign_in(client, manager)
        client.post('/api/auth/setup/complete', json={'session_id': session_id, 'site_id': '111222'})
        response = client.post('/api/auth/setup/cancel', json={'session_id': session_id})
        assert response.status_code == 409

    def test_status_for_unknown_session_explains_a_restart(self, client):
        response = client.get('/api/auth/setup/status/unknown-session-id-0123456789')
        assert response.status_code == 200
        assert response.json['data']['exists'] is False
        assert response.json['data']['error_code'] == 'SETUP_NOT_FOUND'

    def test_responses_never_contain_tokens(self, client, manager):
        session_id, state = start(client)
        bodies = []
        with patch(EXCHANGE, return_value=dict(TOKENS)), \
                patch.object(manager, 'get_energy_sites', return_value=SITES):
            bodies.append(client.post('/api/auth/setup/callback', json={
                'session_id': session_id, 'callback_url': callback(state),
            }).get_data(as_text=True))
        bodies.append(client.get(f'/api/auth/setup/status/{session_id}').get_data(as_text=True))
        bodies.append(client.post('/api/auth/setup/complete', json={
            'session_id': session_id, 'site_id': '111222',
        }).get_data(as_text=True))
        bodies.append(client.get(f'/api/auth/setup/status/{session_id}').get_data(as_text=True))

        for body in bodies:
            for secret in (TOKENS['access_token'], TOKENS['refresh_token'], state, 'code_verifier'):
                assert secret not in body


class TestConnectionState:
    def test_info_reports_temporarily_unavailable_for_network_failures(self, client, manager,
                                                                      mock_powerwall_connector):
        manager.auth_storage.store_auth_data(
            EMAIL, {'access_token': 'at', 'refresh_token': 'rt',
                    'expires_at': (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()},
            {'id': 1},
        )
        mock_powerwall_connector.get_connection_status.return_value = {
            'connected': False,
            'connection_status': 'disconnected',
            'last_connection_attempt': '2026-10-21T12:00:00+00:00',
            'connection_error': 'Tesla cloud is unreachable.',
            'connection_error_code': 'no_response',
            'auth_rejected': False,
        }

        data = client.get('/api/auth/tesla/info').json['data']

        assert data['connection_state'] == 'temporarily_unavailable'
        assert data['connection_state_reason'] == 'no_response'
        assert data['connection_error_code'] == 'no_response'

    def test_info_without_credentials_requires_sign_in(self, client):
        data = client.get('/api/auth/tesla/info').json['data']
        assert data['authenticated'] is False
        assert data['connection_state'] == 'sign_in_required'


class TestHelperEndpoints:
    def test_helper_flow_uses_only_the_handoff(self, client, manager):
        session_id, state = start(client)
        handoff = client.post('/api/auth/setup/handoff', json={'session_id': session_id}).json['handoff']

        missing = client.get('/api/auth/setup/helper/authorization')
        authorization = client.get('/api/auth/setup/helper/authorization',
                                   headers={'X-PowerNight-Handoff': handoff})
        with patch(EXCHANGE, return_value=dict(TOKENS)), \
                patch.object(manager, 'get_energy_sites', return_value=SITES):
            submitted = client.post('/api/auth/setup/helper/callback',
                                    headers={'X-PowerNight-Handoff': handoff},
                                    json={'callback_url': callback(state)})
        replay = client.post('/api/auth/setup/helper/callback',
                             headers={'X-PowerNight-Handoff': handoff},
                             json={'callback_url': callback(state)})

        assert missing.status_code == 403
        assert authorization.status_code == 200
        assert authorization.json['auth_url'].startswith('https://auth.tesla.com/')
        assert submitted.status_code == 200
        assert submitted.json['step'] == 'selecting_site'
        assert replay.status_code == 403
        for response in (authorization, submitted, replay):
            text = response.get_data(as_text=True)
            assert session_id not in text
            assert TOKENS['access_token'] not in text
        status = client.get(f'/api/auth/setup/status/{session_id}').json['data']
        assert status['helper_state'] == 'submitted'
        assert status['sites'] == SITES
