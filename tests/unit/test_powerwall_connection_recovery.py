"""Regression coverage for Tesla cloud connection recovery."""

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pypowerwall.cloud.exceptions import (
    PyPowerwallCloudNoTeslaAuthFile,
    PyPowerwallCloudTeslaNotConnected,
)

from powernight.core.powerwall.connector import PowerwallConnector
from powernight.core.powerwall.exceptions import PowerwallAuthenticationError, PowerwallConnectionError
from powernight.core.scheduler.circuit_breaker import CircuitBreakerOpenException


@pytest.mark.parametrize('operation', ['connect', 'is_connected'])
def test_cached_status_remains_responsive_during_network_request(tmp_path, monkeypatch, operation):
    monkeypatch.setenv('POWERNIGHT_DATA_PATH', str(tmp_path))
    connector = make_connector(tmp_path)
    powerwall = MagicMock()
    connector._powerwall = powerwall
    entered = threading.Event()
    release = threading.Event()

    def slow_vitals():
        entered.set()
        assert release.wait(3)
        return {'online': True}

    powerwall.vitals.side_effect = slow_vitals
    with patch('powernight.core.powerwall.connector.pypowerwall.Powerwall', return_value=powerwall):
        with ThreadPoolExecutor(max_workers=2) as workers:
            request = workers.submit(getattr(connector, operation))
            try:
                assert entered.wait(2)
                status = workers.submit(connector.get_connection_status).result(timeout=0.5)
                assert status['connected'] is False
            finally:
                release.set()
            assert request.result(timeout=2) is True
    assert connector.get_connection_status()['connected'] is True


@pytest.mark.parametrize(('operation', 'args', 'client_method'), [
    ('set_mode', ('self_consumption',), 'set_mode'),
    ('set_grid_charging', (True,), 'grid_charging'),
    ('set_export_mode', ('pv_only',), 'set_grid_export'),
    ('set_backup_reserve_percentage', (40,), 'set_reserve'),
    ('get_state_of_charge', (), 'level'),
])
def test_reconnect_waits_for_inflight_command(tmp_path, monkeypatch, operation, args, client_method):
    monkeypatch.setenv('POWERNIGHT_DATA_PATH', str(tmp_path))
    connector = make_connector(tmp_path)
    powerwall = MagicMock()
    connector._powerwall = powerwall
    connector.ensure_connected = MagicMock(return_value=True)
    entered = threading.Event()
    release = threading.Event()
    reconnect_started = threading.Event()
    disconnected = threading.Event()

    def rate_limit():
        entered.set()
        assert release.wait(3)

    def reconnect():
        reconnect_started.set()
        connector.disconnect()
        disconnected.set()
        connector.connect()

    connector._handle_rate_limit = rate_limit
    replacement = MagicMock()
    replacement.vitals.return_value = {'online': True}
    with patch('powernight.core.powerwall.connector.pypowerwall.Powerwall', return_value=replacement):
        with ThreadPoolExecutor(max_workers=2) as workers:
            command = workers.submit(getattr(connector, operation), *args)
            try:
                assert entered.wait(2)
                connection = workers.submit(reconnect)
                assert reconnect_started.wait(2)
                assert not disconnected.wait(0.1)
                assert connector._powerwall is powerwall
            finally:
                release.set()
            command.result(timeout=2)
            connection.result(timeout=2)
    getattr(powerwall, client_method).assert_called_once_with(*args)
    assert connector._powerwall is replacement


def make_connector(tmp_path, auth_data=None):
    connector = PowerwallConnector(email='stale@example.com', rate_limit_delay=0)
    connector._oauth_manager = MagicMock()
    connector._oauth_manager.auth_storage.storage_path = Path(tmp_path)
    connector._oauth_manager.auth_storage.load_auth_data.return_value = auth_data or {
        'email': 'owner@example.com',
        'site': {'id': 123456},
    }
    connector._oauth_manager.has_credentials.return_value = True
    connector._circuit_breaker = MagicMock()
    connector._circuit_breaker.call.side_effect = lambda operation: operation()
    return connector


def test_connect_reloads_credentials_and_uses_cloud_only_selected_site(tmp_path):
    connector = make_connector(tmp_path)
    powerwall = MagicMock()
    powerwall.vitals.return_value = {'site': 'online'}

    with patch(
        'powernight.core.powerwall.connector.pypowerwall.Powerwall',
        return_value=powerwall,
    ) as powerwall_class:
        assert connector.connect() is True

    connector._oauth_manager.auth_storage.load_auth_data.assert_called_once()
    assert connector.config.email == 'owner@example.com'
    assert connector.config.powerwall_id == '123456'
    powerwall_class.assert_called_once_with(
        email='owner@example.com',
        cloudmode=True,
        authmode='token',
        authpath=f'{tmp_path}/',
        timeout=30.0,
        siteid=123456,
        failover=False,
    )


def test_each_connection_attempt_reloads_selected_site(tmp_path):
    connector = make_connector(tmp_path)
    connector._oauth_manager.auth_storage.load_auth_data.side_effect = [
        {'email': 'first@example.com', 'site': {'id': 100}},
        {'email': 'second@example.com', 'site': {'id': 200}},
    ]
    powerwall = MagicMock()
    powerwall.vitals.return_value = {'site': 'online'}

    with patch(
        'powernight.core.powerwall.connector.pypowerwall.Powerwall',
        return_value=powerwall,
    ) as powerwall_class:
        connector.connect()
        connector.disconnect()
        connector.connect()

    assert powerwall_class.call_args_list[0].kwargs['siteid'] == 100
    assert powerwall_class.call_args_list[1].kwargs['siteid'] == 200
    assert powerwall_class.call_args_list[1].kwargs['email'] == 'second@example.com'


def test_concurrent_ensure_connected_builds_one_session(tmp_path):
    connector = make_connector(tmp_path)
    powerwall = MagicMock()
    powerwall.vitals.return_value = {'site': 'online'}
    barrier = threading.Barrier(8)
    results = []

    def connect():
        barrier.wait()
        results.append(connector.ensure_connected())

    with patch(
        'powernight.core.powerwall.connector.pypowerwall.Powerwall',
        return_value=powerwall,
    ) as powerwall_class:
        threads = [threading.Thread(target=connect) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)

    assert results == [True] * 8
    powerwall_class.assert_called_once()


@pytest.mark.parametrize(
    ('error', 'expected_code', 'expected_exception'),
    [
        (PyPowerwallCloudNoTeslaAuthFile('missing auth'), 'authentication', PowerwallAuthenticationError),
        (PyPowerwallCloudTeslaNotConnected('Tesla session unavailable'), 'tesla_rejected', PowerwallConnectionError),
        (RuntimeError('network down'), 'connection', PowerwallConnectionError),
    ],
)
def test_connection_failures_are_categorized(tmp_path, error, expected_code, expected_exception):
    connector = make_connector(tmp_path)
    connector._circuit_breaker.call.side_effect = error

    with pytest.raises(expected_exception):
        connector.connect()

    status = connector.get_connection_status()
    assert status['connected'] is False
    assert status['connection_status'] == 'disconnected'
    assert status['connection_error_code'] == expected_code
    assert status['connection_error']
    assert status['last_connection_attempt']


def test_circuit_breaker_failure_remains_distinguishable(tmp_path):
    connector = make_connector(tmp_path)
    connector._circuit_breaker.call.side_effect = CircuitBreakerOpenException('open')

    with pytest.raises(CircuitBreakerOpenException):
        connector.connect()

    assert connector.get_connection_status()['connection_error_code'] == 'circuit_breaker'


def test_generic_failure_is_wrapped_without_leaking_token(tmp_path):
    connector = make_connector(tmp_path)
    connector._circuit_breaker.call.side_effect = RuntimeError(
        'authorization: Bearer secret-token-value'
    )

    with patch.object(connector.logger, 'log_powerwall_operation') as log_operation:
        with pytest.raises(PowerwallConnectionError):
            connector.connect()

    failure_log = log_operation.call_args.kwargs['error_details']
    assert 'secret-token-value' not in failure_log
    assert '***REDACTED***' in failure_log


def test_connect_never_refreshes_tokens_itself(tmp_path):
    connector = make_connector(tmp_path)
    connector._oauth_manager.has_credentials.return_value = False

    with pytest.raises(PowerwallAuthenticationError):
        connector.connect()

    assert not connector._oauth_manager.refresh_access_token.called
    assert connector.get_connection_status()['connection_error_code'] == 'authentication'


def test_cloud_session_reuses_live_session(tmp_path):
    connector = make_connector(tmp_path)
    live = MagicMock()
    connector._powerwall = live
    live.vitals.return_value = {'ok': True}

    with patch.object(connector, 'connect') as connect:
        with connector.cloud_session() as pw:
            assert pw is live
    connect.assert_not_called()


def test_cloud_session_holds_connection_lock_for_whole_block(tmp_path):
    connector = make_connector(tmp_path)
    connector._powerwall = MagicMock()
    connector._powerwall.vitals.return_value = {'ok': True}
    acquired_elsewhere = []

    def try_lock():
        got = connector._connection_lock.acquire(timeout=0.2)
        acquired_elsewhere.append(got)
        if got:
            connector._connection_lock.release()

    with connector.cloud_session():
        other = threading.Thread(target=try_lock)
        other.start()
        other.join()
    assert acquired_elsewhere == [False]

    # Released afterwards, so scheduled commands can proceed
    try_lock()
    assert acquired_elsewhere == [False, True]


def test_cloud_session_fails_clearly_without_a_session(tmp_path):
    connector = make_connector(tmp_path)
    with patch.object(connector, 'ensure_connected', return_value=False):
        with pytest.raises(PowerwallConnectionError):
            with connector.cloud_session():
                pass


# --- Reconnect without signing out -------------------------------------------

def test_replace_credentials_waits_for_inflight_session_use(tmp_path):
    connector = make_connector(tmp_path)
    old_session = MagicMock()
    connector._powerwall = old_session
    entered, release = threading.Event(), threading.Event()
    written = []

    def hold_session():
        with connector.cloud_session():
            entered.set()
            assert release.wait(3)

    connector.is_connected = MagicMock(return_value=True)
    holder = threading.Thread(target=hold_session)
    holder.start()
    assert entered.wait(3)
    swapper = threading.Thread(target=lambda: connector.replace_credentials(lambda: written.append(1)))
    swapper.start()
    swapper.join(0.3)
    assert written == []  # still waiting for the in-flight request
    release.set()
    holder.join(3)
    swapper.join(3)

    assert written == [1]
    assert connector._powerwall is None


def test_failed_credential_write_keeps_the_live_session(tmp_path):
    connector = make_connector(tmp_path)
    session = MagicMock()
    connector._powerwall = session
    connector._connected = True
    connector._last_connection_attempt = '2026-10-21T12:00:00+00:00'

    def failing_write():
        raise OSError('disk full')

    with pytest.raises(OSError):
        connector.replace_credentials(failing_write)

    assert connector._powerwall is session
    assert connector.get_connection_status()['connected'] is True
    connector._circuit_breaker.reset.assert_not_called()


def test_replacing_credentials_retires_the_old_session_and_resets_state(tmp_path):
    connector = make_connector(tmp_path)
    old_session = MagicMock()
    connector._powerwall = old_session
    connector._record_connection_failure(PowerwallAuthenticationError('Tesla rejected the saved sign-in'))
    assert connector.get_connection_status()['auth_rejected'] is True

    connector.replace_credentials(lambda: None)

    status = connector.get_connection_status()
    assert connector._powerwall is None
    assert status['connection_status'] == 'unknown'
    assert status['connection_error_code'] is None
    assert status['auth_rejected'] is False
    connector._circuit_breaker.reset.assert_called_once()
    old_session.client.tesla.close.assert_called_once()
    # The retired session is never used again (it would rewrite the auth file)
    new_session = MagicMock()
    new_session.vitals.return_value = {'site': 'online'}
    with patch('powernight.core.powerwall.connector.pypowerwall.Powerwall', return_value=new_session):
        with connector.cloud_session() as session:
            assert session is new_session
    old_session.vitals.assert_not_called()


def test_email_digits_are_not_mistaken_for_an_http_status(tmp_path):
    connector = make_connector(tmp_path)
    connector.config.email = 'jo403@example.com'
    connector._circuit_breaker.call.side_effect = PowerwallConnectionError(
        'jo403@example.com', 'No response from Powerwall via cloud'
    )

    with pytest.raises(PowerwallConnectionError):
        connector.connect()

    status = connector.get_connection_status()
    assert status['connection_error_code'] == 'no_response'
    assert status['auth_rejected'] is False


def test_auth_rejection_survives_circuit_breaker_opening(tmp_path):
    connector = make_connector(tmp_path)
    connector._circuit_breaker.call.side_effect = PowerwallAuthenticationError('Tesla rejected the saved sign-in')
    with pytest.raises(PowerwallAuthenticationError):
        connector.connect()

    connector._circuit_breaker.call.side_effect = CircuitBreakerOpenException('open')
    with pytest.raises(CircuitBreakerOpenException):
        connector.connect()

    status = connector.get_connection_status()
    assert status['connection_error_code'] == 'circuit_breaker'
    assert status['auth_rejected'] is True


def test_pypowerwall_rejection_log_line_is_evidence_of_sign_in_problem(tmp_path):
    import logging
    from powernight.core.powerwall.connector import PYPOWERWALL_CLOUD_LOGGER

    connector = make_connector(tmp_path)
    session = MagicMock()
    session.vitals.return_value = None

    def build_session(**kwargs):
        logging.getLogger(PYPOWERWALL_CLOUD_LOGGER).error('Access token rejected (403 Forbidden).')
        return session

    with patch('powernight.core.powerwall.connector.pypowerwall.Powerwall', side_effect=build_session):
        with pytest.raises(PowerwallAuthenticationError):
            connector.connect()

    status = connector.get_connection_status()
    assert status['connection_error_code'] == 'authentication'
    assert status['auth_rejected'] is True


def test_empty_vitals_without_rejection_stay_a_connection_problem(tmp_path):
    connector = make_connector(tmp_path)
    session = MagicMock()
    session.vitals.return_value = None
    with patch('powernight.core.powerwall.connector.pypowerwall.Powerwall', return_value=session):
        with pytest.raises(PowerwallConnectionError):
            connector.connect()
    assert connector.get_connection_status()['auth_rejected'] is False


def test_pypowerwall_still_logs_the_rejection_markers():
    """Canary: if pypowerwall rewords these, sign-in evidence silently disappears."""
    import inspect
    import pypowerwall.cloud.pypowerwall_cloud as cloud
    from powernight.core.powerwall.connector import PYPOWERWALL_AUTH_MARKERS, PYPOWERWALL_CLOUD_LOGGER

    source = inspect.getsource(cloud)
    assert cloud.__name__ == PYPOWERWALL_CLOUD_LOGGER
    for marker in PYPOWERWALL_AUTH_MARKERS:
        assert marker in source, marker


def test_circuit_breaker_reset_closes_it():
    from powernight.core.scheduler.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

    breaker = CircuitBreaker('reset-test', CircuitBreakerConfig(failure_threshold=1))
    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError('down')))
    assert breaker.state == 'OPEN'

    breaker.reset()

    assert breaker.state == 'CLOSED'
    assert breaker.call(lambda: 'ok') == 'ok'


def test_missing_credentials_are_not_a_tesla_rejection(tmp_path):
    connector = make_connector(tmp_path)
    connector._oauth_manager.has_credentials.return_value = False

    with pytest.raises(PowerwallAuthenticationError):
        connector.connect()

    status = connector.get_connection_status()
    assert status['connection_error_code'] == 'authentication'
    assert status['auth_rejected'] is False
