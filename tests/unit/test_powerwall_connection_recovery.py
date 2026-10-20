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
        assert connector.cloud_session() is live
    connect.assert_not_called()
