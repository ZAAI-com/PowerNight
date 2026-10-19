"""
Resilience regression tests for the Powerwall connector.

The fallback paths run exactly when the Powerwall is unreachable, so they
must never raise AttributeError or otherwise crash: they serve cached data
(stale if necessary) or raise a clean PowerwallUnavailableError.
"""

from unittest.mock import MagicMock, patch

import pytest

from powernight.core.powerwall.connector import PowerwallConnector, PowerwallStatus
from powernight.core.powerwall.exceptions import PowerwallUnavailableError


@pytest.fixture
def connector(tmp_path, monkeypatch):
    """A connector with isolated storage and neutralized degradation state."""
    monkeypatch.setenv('POWERNIGHT_DATA_PATH', str(tmp_path))
    import powernight.core.scheduler.circuit_breaker as circuit_breaker
    circuit_breaker._circuit_breakers.clear()
    # Fresh degradation manager per test (module-level registry)
    import powernight.core.scheduler.degradation as degradation
    degradation._degradation_managers.clear()

    conn = PowerwallConnector(email='resilience@example.com')
    try:
        yield conn
    finally:
        degradation._degradation_managers.clear()
        circuit_breaker._circuit_breakers.clear()


@pytest.mark.unit
class TestReserveFallback:

    def test_reserve_falls_back_to_stale_cache(self, connector):
        """When the API raises, a previously cached value is served even if
        the TTL has expired."""
        connector._data_cache.set('backup_reserve_percentage', 42.0)
        # Expire the entry
        connector._data_cache._cache['backup_reserve_percentage']['timestamp'] -= 3600

        with patch.object(connector, 'is_connected', return_value=True):
            with patch.object(connector, '_handle_rate_limit'):
                connector._powerwall = MagicMock()
                connector._powerwall.get_reserve.side_effect = RuntimeError('cloud down')

                result = connector.get_backup_reserve_percentage()

        assert result == 42.0

    def test_reserve_raises_clean_error_with_no_cache(self, connector):
        """With no cached data at all, a clean PowerwallUnavailableError is
        raised: never AttributeError."""
        with patch.object(connector, 'is_connected', return_value=True):
            with patch.object(connector, '_handle_rate_limit'):
                connector._powerwall = MagicMock()
                connector._powerwall.get_reserve.side_effect = RuntimeError('cloud down')

                with pytest.raises(PowerwallUnavailableError):
                    connector.get_backup_reserve_percentage()


@pytest.mark.unit
class TestStatusFallback:

    def test_status_falls_back_to_last_known_status(self, connector):
        """When the API raises, the last in-memory status is served."""
        last = PowerwallStatus(
            backup_reserve_percentage=33.0,
            battery_level=80.0,
            is_charging=False,
            is_grid_connected=True,
            last_updated=0.0,
        )
        connector._last_status = last

        with patch.object(connector, 'is_connected', return_value=True):
            with patch.object(connector, '_handle_rate_limit'):
                connector._powerwall = MagicMock()
                connector._powerwall.vitals.side_effect = RuntimeError('cloud down')

                result = connector.get_status()

        assert result.backup_reserve_percentage == 33.0

    def test_status_raises_clean_error_with_no_fallback_data(self, connector):
        with patch.object(connector, 'is_connected', return_value=True):
            with patch.object(connector, '_handle_rate_limit'):
                connector._powerwall = MagicMock()
                connector._powerwall.vitals.side_effect = RuntimeError('cloud down')

                with pytest.raises(PowerwallUnavailableError):
                    connector.get_status()


@pytest.mark.unit
class TestCircuitBreakerTransitions:

    def test_breaker_opens_after_failures_and_recovers(self):
        from powernight.core.scheduler.circuit_breaker import (
            CircuitBreaker, CircuitBreakerConfig
        )

        config = CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=0.05,
            success_threshold=1,
        )
        breaker = CircuitBreaker('test-breaker', config)

        def failing():
            raise RuntimeError('boom')

        for _ in range(2):
            with pytest.raises(RuntimeError):
                breaker.call(failing)

        # Breaker should now refuse calls (open state)
        from powernight.core.scheduler.circuit_breaker import CircuitBreakerOpenException
        with pytest.raises(CircuitBreakerOpenException):
            breaker.call(lambda: 'ok')

        # After the recovery timeout, a successful call closes it again
        import time
        time.sleep(0.06)
        assert breaker.call(lambda: 'ok') == 'ok'


def test_successful_status_finishes_without_reentering_breaker(connector):
    """Use the real non-reentrant breaker; a nested call must fail boundedly."""
    import threading
    connector.ensure_connected = MagicMock(return_value=True)
    connector._handle_rate_limit = MagicMock()
    connector._powerwall = MagicMock()
    connector._powerwall.vitals.return_value = {
        'battery': {'percentage': 81, 'charging': True}, 'grid': {'connected': True},
    }
    connector._powerwall.get_reserve.return_value = 45
    results = []
    worker = threading.Thread(target=lambda: results.append(connector.get_status()), daemon=True)
    worker.start()
    worker.join(timeout=1)
    assert not worker.is_alive(), 'get_status deadlocked inside the circuit breaker'
    assert results[0].backup_reserve_percentage == 45
    assert results[0].battery_level == 81
    assert connector._data_cache.get('powerwall_status') is results[0]
    assert connector._data_cache.get('backup_reserve_percentage') == 45
    connector._powerwall.vitals.assert_called_once()
    connector._powerwall.get_reserve.assert_called_once()


@pytest.mark.parametrize(('method', 'cache_key', 'value', 'client_method'), [
    ('get_backup_reserve_percentage', 'backup_reserve_percentage', 42.0, 'get_reserve'),
    ('get_status', 'powerwall_status', PowerwallStatus(33, 80, False, True, 123), 'vitals'),
])
def test_repeated_outage_fallback_never_renews_cache_age(
        connector, method, cache_key, value, client_method):
    connector.ensure_connected = MagicMock(return_value=True)
    connector._handle_rate_limit = MagicMock()
    connector._powerwall = MagicMock()
    getattr(connector._powerwall, client_method).side_effect = RuntimeError('offline')
    connector._data_cache.set(cache_key, value)
    entry = connector._data_cache._cache[cache_key]
    entry['timestamp'] -= 3600
    original_timestamp = entry['timestamp']
    for _ in range(4):
        assert getattr(connector, method)() == value
        assert connector._data_cache.get(cache_key) is None
        assert connector._data_cache._cache[cache_key]['timestamp'] == original_timestamp
    getattr(connector._powerwall, client_method).assert_called()


@pytest.mark.parametrize('reserve', [0.0, 42.0])
@pytest.mark.parametrize('expired', [False, True])
def test_status_keeps_fresh_vitals_when_only_reserve_fails(connector, reserve, expired):
    connector.ensure_connected = MagicMock(return_value=True)
    connector._handle_rate_limit = MagicMock()
    connector._powerwall = MagicMock()
    connector._powerwall.vitals.return_value = {
        'battery': {'percentage': 81, 'charging': True}, 'grid': {'connected': True},
    }
    connector._powerwall.get_reserve.side_effect = RuntimeError('reserve unavailable')
    connector._data_cache.set('backup_reserve_percentage', reserve)
    entry = connector._data_cache._cache['backup_reserve_percentage']
    if expired:
        entry['timestamp'] -= 3600
    original_timestamp = entry['timestamp']
    for _ in range(2):
        result = connector.get_status()
        assert result.backup_reserve_percentage == reserve
        assert result.battery_level == 81
        assert connector._data_cache.get('powerwall_status') is None
        assert connector._data_cache._cache['backup_reserve_percentage']['timestamp'] == original_timestamp
