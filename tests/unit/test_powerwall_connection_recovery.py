"""Regression coverage for Tesla cloud connection recovery."""

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pypowerwall.cloud.exceptions import (
    PyPowerwallCloudNoTeslaAuthFile,
    PyPowerwallCloudTeslaNotConnected,
)

from powernight.core.powerwall.connector import PowerwallConnector
from powernight.core.powerwall.exceptions import PowerwallConnectionError
from powernight.core.scheduler.circuit_breaker import CircuitBreakerOpenException


def make_connector(tmp_path, auth_data=None):
    connector = PowerwallConnector(email='stale@example.com', rate_limit_delay=0)
    connector._oauth_manager = MagicMock()
    connector._oauth_manager.auth_storage.storage_path = Path(tmp_path)
    connector._oauth_manager.auth_storage.load_auth_data.return_value = auth_data or {
        'email': 'owner@example.com',
        'site': {'id': 123456},
    }
    connector._oauth_manager.get_valid_access_token.return_value = 'valid-access-token'
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
    ('error', 'expected_code'),
    [
        (PyPowerwallCloudNoTeslaAuthFile('missing auth'), 'authentication'),
        (PyPowerwallCloudTeslaNotConnected('Tesla session unavailable'), 'pypowerwall'),
        (RuntimeError('network down'), 'connection'),
    ],
)
def test_connection_failures_are_categorized(tmp_path, error, expected_code):
    connector = make_connector(tmp_path)
    connector._circuit_breaker.call.side_effect = error

    with pytest.raises(Exception):
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
