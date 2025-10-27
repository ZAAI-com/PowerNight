"""
Tests for PowerNight scheduler functionality.
"""

import pytest
import threading
import time
import tempfile
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from powernight.core.scheduler import (
    ScheduleManager,
    PowerwallReserveJob,
    ScheduledJob,
    SchedulerError,
    JobExecutionError
)
from powernight.core.scheduler.manager import JobInfo, get_schedule_manager
from powernight.core.config import PowerNightConfig, create_default_config


class TestScheduledJob:
    """Test base ScheduledJob functionality."""

    def test_scheduled_job_creation(self):
        """Test creating a scheduled job."""

        class TestJob(ScheduledJob):
            def execute(self):
                return {"result": "success"}

        job = TestJob("Test Job", "A test job")
        assert job.name == "Test Job"
        assert job.description == "A test job"

    def test_scheduled_job_callable(self):
        """Test that scheduled job is callable."""

        class TestJob(ScheduledJob):
            def execute(self):
                return {"executed": True}

        job = TestJob("Test Job")
        result = job()
        assert result["executed"] is True


class TestPowerwallReserveJob:
    """Test PowerwallReserveJob functionality."""

    def test_powerwall_job_creation(self):
        """Test creating a Powerwall reserve job."""
        job = PowerwallReserveJob(target_percentage=40.0)
        assert job.target_percentage == 40.0
        assert "40.0%" in job.name
        assert "40.0%" in job.description

    def test_powerwall_job_invalid_percentage(self):
        """Test creating job with invalid percentage."""
        with pytest.raises(ValueError):
            PowerwallReserveJob(target_percentage=-10.0)

        with pytest.raises(ValueError):
            PowerwallReserveJob(target_percentage=150.0)

    def test_powerwall_job_custom_name_description(self):
        """Test job with custom name and description."""
        job = PowerwallReserveJob(
            target_percentage=25.0,
            name="Custom Job",
            description="Custom description"
        )
        assert job.name == "Custom Job"
        assert job.description == "Custom description"

    @patch('powernight.scheduler.jobs.get_config')
    def test_powerwall_job_dry_run(self, mock_get_config):
        """Test job execution in dry run mode."""
        # Setup mock config
        config = create_default_config()
        mock_get_config.return_value = config

        job = PowerwallReserveJob(target_percentage=30.0)
        result = job.execute()

        assert result['success'] is True
        assert result['dry_run'] is True
        assert result['target_percentage'] == 30.0

    @patch('powernight.scheduler.jobs.get_config')
    def test_powerwall_job_disabled_automation(self, mock_get_config):
        """Test job when automation is disabled."""
        config = create_default_config()
        config.automation.enabled = False
        mock_get_config.return_value = config

        job = PowerwallReserveJob(target_percentage=30.0)

        with pytest.raises(JobExecutionError):
            job.execute()


class TestScheduleManager:
    """Test ScheduleManager functionality."""

    def setup_method(self):
        """Setup for each test."""
        # Reset singleton
        ScheduleManager._instance = None

    def test_schedule_manager_singleton(self):
        """Test singleton pattern."""
        manager1 = ScheduleManager()
        manager2 = ScheduleManager()
        assert manager1 is manager2

    def test_schedule_manager_global_instance(self):
        """Test global instance function."""
        manager = get_schedule_manager()
        assert isinstance(manager, ScheduleManager)

        # Should return same instance
        manager2 = get_schedule_manager()
        assert manager is manager2

    @patch('powernight.scheduler.manager.get_config')
    def test_schedule_manager_initialization(self, mock_get_config):
        """Test manager initialization with config."""
        config = create_default_config()
        config.automation.check_interval = 5.0
        mock_get_config.return_value = config

        manager = ScheduleManager()
        assert manager._check_interval == 5.0
        assert manager._config is not None

    def test_add_job(self):
        """Test adding a job to the scheduler."""
        manager = ScheduleManager()

        def test_func():
            return "test"

        manager.add_job(
            job_id="test_job",
            name="Test Job",
            schedule_time="12:00",
            job_func=test_func,
            description="A test job"
        )

        assert "test_job" in manager._jobs
        job_info = manager._jobs["test_job"]
        assert job_info.name == "Test Job"
        assert job_info.schedule_time == "12:00"
        assert job_info.description == "A test job"

    def test_add_duplicate_job(self):
        """Test adding duplicate job raises error."""
        manager = ScheduleManager()

        def test_func():
            return "test"

        manager.add_job("test_job", "Test Job", "12:00", test_func)

        with pytest.raises(Exception):  # DuplicateJobError
            manager.add_job("test_job", "Another Job", "13:00", test_func)

    def test_add_job_invalid_time(self):
        """Test adding job with invalid time format."""
        manager = ScheduleManager()

        def test_func():
            return "test"

        with pytest.raises(Exception):  # ConfigurationError
            manager.add_job("test_job", "Test Job", "25:00", test_func)

        with pytest.raises(Exception):  # ConfigurationError
            manager.add_job("test_job", "Test Job", "12:70", test_func)

    def test_remove_job(self):
        """Test removing a job."""
        manager = ScheduleManager()

        def test_func():
            return "test"

        manager.add_job("test_job", "Test Job", "12:00", test_func)
        assert "test_job" in manager._jobs

        manager.remove_job("test_job")
        assert "test_job" not in manager._jobs

    def test_remove_nonexistent_job(self):
        """Test removing non-existent job raises error."""
        manager = ScheduleManager()

        with pytest.raises(Exception):  # JobNotFoundError
            manager.remove_job("nonexistent_job")

    def test_enable_disable_job(self):
        """Test enabling and disabling jobs."""
        manager = ScheduleManager()

        def test_func():
            return "test"

        manager.add_job("test_job", "Test Job", "12:00", test_func, enabled=True)

        job_info = manager.get_job_info("test_job")
        assert job_info.enabled is True

        manager.disable_job("test_job")
        assert job_info.enabled is False

        manager.enable_job("test_job")
        assert job_info.enabled is True

    def test_list_jobs(self):
        """Test listing all jobs."""
        manager = ScheduleManager()

        def test_func():
            return "test"

        manager.add_job("job1", "Job 1", "12:00", test_func)
        manager.add_job("job2", "Job 2", "13:00", test_func)

        jobs = manager.list_jobs()
        assert len(jobs) == 2
        job_names = [job.name for job in jobs]
        assert "Job 1" in job_names
        assert "Job 2" in job_names

    def test_get_status(self):
        """Test getting scheduler status."""
        manager = ScheduleManager()

        def test_func():
            return "test"

        manager.add_job("job1", "Job 1", "12:00", test_func, enabled=True)
        manager.add_job("job2", "Job 2", "13:00", test_func, enabled=False)

        status = manager.get_status()
        assert status['job_count'] == 2
        assert status['enabled_jobs'] == 1
        assert status['disabled_jobs'] == 1
        assert status['is_running'] is False

    def test_scheduler_lifecycle(self):
        """Test starting and stopping scheduler."""
        manager = ScheduleManager()

        assert not manager.is_running()

        manager.start()
        assert manager.is_running()

        manager.stop()
        assert not manager.is_running()

    def test_scheduler_restart(self):
        """Test restarting scheduler."""
        manager = ScheduleManager()

        def test_func():
            return "test"

        manager.add_job("test_job", "Test Job", "12:00", test_func)
        manager.start()

        assert manager.is_running()
        assert len(manager._jobs) >= 1

        manager.restart()

        assert manager.is_running()

    @patch('powernight.scheduler.manager.get_config')
    def test_setup_default_jobs(self, mock_get_config):
        """Test setting up default jobs from configuration."""
        config = create_default_config()
        # Add some schedule entries to test
        from powernight.config.schema import ScheduleEntry
        config.automation.schedule = [
            ScheduleEntry(time="00:01", percentage=40.0, description="Night reserve"),
            ScheduleEntry(time="04:58", percentage=0.0, description="Morning usage"),
            ScheduleEntry(time="12:00", percentage=20.0, enabled=False)  # Disabled
        ]
        mock_get_config.return_value = config

        manager = ScheduleManager()
        manager._setup_default_jobs()

        # Should have 2 jobs (third is disabled)
        assert len(manager._jobs) == 2

        # Check job details
        jobs = {job.schedule_time: job for job in manager.list_jobs()}
        assert "00:01" in jobs
        assert "04:58" in jobs
        assert "12:00" not in jobs  # Disabled job shouldn't be added

    def test_job_execution_tracking(self):
        """Test that job execution is tracked properly."""
        manager = ScheduleManager()

        execution_count = 0

        def test_func():
            nonlocal execution_count
            execution_count += 1
            return {"count": execution_count}

        manager.add_job("test_job", "Test Job", "12:00", test_func)
        job_info = manager.get_job_info("test_job")

        # Simulate job execution by calling the wrapped function
        wrapped_func = manager._wrap_job_function(job_info, test_func)

        # Execute multiple times
        wrapped_func()
        wrapped_func()

        assert job_info.run_count == 2
        assert job_info.error_count == 0
        assert job_info.last_success is not None

    def test_job_error_tracking(self):
        """Test that job errors are tracked properly."""
        manager = ScheduleManager()

        def failing_func():
            raise Exception("Test error")

        manager.add_job("test_job", "Test Job", "12:00", failing_func)
        job_info = manager.get_job_info("test_job")

        wrapped_func = manager._wrap_job_function(job_info, failing_func)

        # Execute and expect failure
        with pytest.raises(Exception):
            wrapped_func()

        assert job_info.run_count == 1
        assert job_info.error_count == 1
        assert job_info.last_error == "Test error"


class TestSchedulerIntegration:
    """Integration tests for scheduler functionality."""

    def setup_method(self):
        """Setup for each test."""
        ScheduleManager._instance = None

    @patch('powernight.scheduler.jobs.get_config')
    @patch('powernight.scheduler.manager.get_config')
    def test_full_integration(self, mock_manager_config, mock_jobs_config):
        """Test full integration with configuration and jobs."""
        # Setup configuration
        config = create_default_config()
        config.automation.enabled = True

        from powernight.config.schema import ScheduleEntry
        config.automation.schedule = [
            ScheduleEntry(time="00:01", percentage=40.0, description="Night reserve")
        ]

        mock_manager_config.return_value = config
        mock_jobs_config.return_value = config

        # Create and start scheduler
        manager = ScheduleManager()
        manager.start()

        try:
            # Verify job was created
            jobs = manager.list_jobs()
            assert len(jobs) >= 1

            # Find the reserve change job
            reserve_job = None
            for job in jobs:
                if "00:01" in job.schedule_time:
                    reserve_job = job
                    break

            assert reserve_job is not None
            assert reserve_job.schedule_time == "00:01"

            # Get status
            status = manager.get_status()
            assert status['is_running'] is True
            assert status['job_count'] >= 1

        finally:
            manager.stop()

    def test_scheduler_thread_safety(self):
        """Test scheduler thread safety."""
        manager = ScheduleManager()

        def test_func():
            time.sleep(0.1)
            return "done"

        results = []
        errors = []

        def add_job_worker(job_id):
            try:
                manager.add_job(f"job_{job_id}", f"Job {job_id}", "12:00", test_func)
                results.append(job_id)
            except Exception as e:
                errors.append(e)

        # Start multiple threads adding jobs
        threads = []
        for i in range(10):
            thread = threading.Thread(target=add_job_worker, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Should have some successful additions (first one) and some errors (duplicates)
        assert len(results) >= 1
        assert len(manager._jobs) >= 1