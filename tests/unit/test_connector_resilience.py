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
    # Fresh degradation manager per test (module-level registry)
    import powernight.core.scheduler.degradation as degradation
    degradation._degradation_managers.clear()

    conn = PowerwallConnector(email='resilience@example.com')
    return conn


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
            with pytest.raises(Exception):
                breaker.call(failing)

        # Breaker should now refuse calls (open state)
        from powernight.core.scheduler.circuit_breaker import CircuitBreakerOpenException
        with pytest.raises(CircuitBreakerOpenException):
            breaker.call(lambda: 'ok')

        # After the recovery timeout, a successful call closes it again
        import time
        time.sleep(0.06)
        assert breaker.call(lambda: 'ok') == 'ok'
