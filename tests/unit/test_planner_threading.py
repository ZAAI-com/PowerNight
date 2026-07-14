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
