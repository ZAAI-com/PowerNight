"""
Thread-safety regression tests for the planner and database layers.

Covers:
- Scheduled task execution must not block the scheduler loop
- get_database_manager() must be a thread-safe singleton
"""

import threading
import time
from unittest.mock import patch, MagicMock

import pytest


@pytest.mark.unit
class TestScheduledExecutionDoesNotBlock:
    """TaskExecutor.__call__ runs from schedule.run_pending() in the planner
    thread and must return immediately even when the command is slow."""

    def test_call_returns_quickly_while_command_runs(self):
        from powernight.core.planner.task_executor import TaskExecutor
        from powernight.core.powerwall.commands import CronCommand

        command = CronCommand(command_type='reserve', params={'reserve': 50})
        executor = TaskExecutor('task-1', 'Slow task', command)

        command_started = threading.Event()
        release_command = threading.Event()

        def slow_command():
            command_started.set()
            release_command.wait(timeout=10)
            return {'success': True}

        executor.execution_service = MagicMock()
        executor.execution_service.create_execution.return_value = {'id': 'exec-1'}
        executor.task_service = MagicMock()

        with patch.object(executor, '_execute_command', side_effect=slow_command):
            start = time.monotonic()
            result = executor()
            elapsed = time.monotonic() - start

        try:
            assert elapsed < 0.5, (
                f"__call__ blocked for {elapsed:.2f}s; scheduled execution "
                "must run in a background thread"
            )
            assert result['success'] is True
            assert result['execution_id'] == 'exec-1'
            assert command_started.wait(timeout=5), "background execution never started"
        finally:
            release_command.set()

    def test_call_reports_failure_when_execution_record_fails(self):
        from powernight.core.planner.task_executor import TaskExecutor
        from powernight.core.powerwall.commands import CronCommand

        command = CronCommand(command_type='reserve', params={'reserve': 50})
        executor = TaskExecutor('task-2', 'Broken task', command)

        executor.execution_service = MagicMock()
        executor.execution_service.create_execution.side_effect = RuntimeError('db down')
        executor.task_service = MagicMock()

        with patch.object(executor, '_execute_command') as mock_exec:
            result = executor()

        assert result['success'] is False
        mock_exec.assert_not_called()


@pytest.mark.unit
class TestExecuteCommandReconnect:
    """_execute_command() must attempt a reconnect when the shared connector
    reports disconnected, so scheduled tasks self-heal after a boot-time
    connect() failure instead of failing forever with a valid token on disk."""

    def _reserve_executor(self, task_id):
        from powernight.core.planner.task_executor import TaskExecutor
        from powernight.core.powerwall.commands import CronCommand

        command = CronCommand(command_type='reserve', params={'reserve': 50})
        return TaskExecutor(task_id, 'Reserve task', command)

    def test_reconnects_when_disconnected_then_executes(self):
        """Disconnected on first check -> connect() -> connected -> command runs."""
        executor = self._reserve_executor('task-reconnect')

        connector = MagicMock()
        # is_connected(): False before reconnect, True after connect() succeeds.
        connector.is_connected.side_effect = [False, True]
        connector.set_backup_reserve_percentage.return_value = {'ok': True}
        connector._sanitize_api_response.return_value = {'ok': True}
        executor.powerwall_connector = connector

        result = executor._execute_command()

        connector.connect.assert_called_once()
        connector.set_backup_reserve_percentage.assert_called_once_with(50)
        assert result['success'] is True

    def test_raises_friendly_error_when_reconnect_auth_fails(self):
        """connect() raising an auth error surfaces the login-prompt message and
        does not dispatch the command."""
        from powernight.core.powerwall.exceptions import (
            PowerwallError,
            PowerwallAuthenticationError,
        )

        executor = self._reserve_executor('task-authfail')

        connector = MagicMock()
        connector.is_connected.return_value = False
        connector.connect.side_effect = PowerwallAuthenticationError(
            "No valid access token available"
        )
        executor.powerwall_connector = connector

        with pytest.raises(PowerwallError, match="Please login via the Settings page"):
            executor._execute_command()

        connector.set_backup_reserve_percentage.assert_not_called()

    def test_wraps_circuit_breaker_open_as_friendly_error(self):
        """CircuitBreakerOpenException is NOT a PowerwallError; the broad except
        must still surface the friendly message rather than leak it raw."""
        from powernight.core.powerwall.exceptions import PowerwallError
        from powernight.core.scheduler.circuit_breaker import (
            CircuitBreakerOpenException,
        )

        executor = self._reserve_executor('task-cbopen')

        connector = MagicMock()
        connector.is_connected.return_value = False
        connector.connect.side_effect = CircuitBreakerOpenException("circuit open")
        executor.powerwall_connector = connector

        with pytest.raises(PowerwallError, match="Please login via the Settings page"):
            executor._execute_command()

        connector.set_backup_reserve_percentage.assert_not_called()


@pytest.mark.unit
class TestDatabaseManagerThreadSafety:
    """get_database_manager() must create exactly one instance under
    concurrent first access."""

    def test_concurrent_first_access_creates_single_instance(self, tmp_path, monkeypatch):
        import powernight.core.database.connection as connection

        monkeypatch.setenv('POWERNIGHT_DATA_PATH', str(tmp_path))
        # Reset the module singleton
        connection.close_database()

        results = []
        barrier = threading.Barrier(20)

        def grab():
            barrier.wait()
            results.append(connection.get_database_manager())

        threads = [threading.Thread(target=grab) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(results) == 20
        assert len({id(m) for m in results}) == 1, (
            "get_database_manager() returned more than one instance under "
            "concurrent access"
        )

        connection.close_database()
