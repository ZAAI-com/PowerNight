"""
PowerNight Planner

Lightweight daily task planner for executing Powerwall commands.
"""

import logging
import threading
import time
import schedule
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from ..database.services import TaskService, TaskExecutionService
from ..powerwall import PowerwallConnector
from ..config import get_config


class Planner:
    """
    Task planner for daily Powerwall automation.

    Features:
    - Loads tasks from database on startup
    - Executes tasks at specified times daily
    - Updates execution status in database
    - No complex retry logic, circuit breakers, or monitoring
    """

    _instance: Optional['Planner'] = None
    _lock = threading.Lock()

    def __new__(cls) -> 'Planner':
        """Singleton pattern implementation."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the planner."""
        if hasattr(self, '_initialized'):
            return

        self.logger = logging.getLogger(__name__)
        self._planner_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_running = False
        self._powerwall_connector: Optional[PowerwallConnector] = None
        self._registered_tasks: Dict[str, Any] = {}  # task_id -> schedule job
        self._task_service = TaskService()
        self._execution_service = TaskExecutionService()
        self._check_interval = 20.0  # Check every 20 seconds (reduced from 1 second for better performance)
        self._initialized = True

    def start(self, powerwall_connector: Optional[PowerwallConnector] = None) -> None:
        """
        Start the planner in a background thread.

        Args:
            powerwall_connector: Shared PowerwallConnector instance
        """
        with self._lock:
            if self._is_running:
                self.logger.warning("Planner is already running")
                return

            self._powerwall_connector = powerwall_connector

            # Bootstrap tasks from database
            self._bootstrap_tasks()

            # Log timezone configuration
            try:
                config = get_config()
                configured_tz = config.automation.timezone
                self.logger.info(f"Planner using timezone: {configured_tz}")
            except Exception as e:
                self.logger.warning(f"Could not determine configured timezone: {e}. Using system timezone.")

            # Clear stop event and start planner thread
            self._stop_event.clear()
            self._planner_thread = threading.Thread(
                target=self._run_loop,
                name="PowerNight-Planner",
                daemon=True
            )
            self._planner_thread.start()
            self._is_running = True

            self.logger.info(
                f"Planner started with {len(self._registered_tasks)} tasks"
            )

    def stop(self, timeout: float = 10.0) -> None:
        """
        Stop the planner and wait for thread to finish.

        Args:
            timeout: Maximum time to wait for thread to stop
        """
        with self._lock:
            if not self._is_running:
                self.logger.warning("Planner is not running")
                return

            # Signal stop and wait for thread
            self._stop_event.set()

            if self._planner_thread and self._planner_thread.is_alive():
                self._planner_thread.join(timeout)

                if self._planner_thread.is_alive():
                    self.logger.warning("Planner thread did not stop within timeout")
                else:
                    self.logger.info("Planner thread stopped successfully")

            self._is_running = False
            self._planner_thread = None

            self.logger.info("Simple Planner stopped")

    def is_running(self) -> bool:
        """Check if the planner is currently running."""
        return self._is_running

    def register_task(self, task_dict: Dict[str, Any]) -> None:
        """
        Register a task with the planner.

        Args:
            task_dict: Task dictionary with id, name, time, command, command_params, enabled
        """
        task_id = task_dict['id']
        task_name = task_dict['name']
        task_time = task_dict['time']

        if task_id in self._registered_tasks:
            self.logger.warning(f"Task {task_id} is already registered, unregistering first")
            self.unregister_task(task_id)

        # Import here to avoid circular imports
        from .task_executor import TaskExecutor
        from ..powerwall.commands import CronCommand, CommandType

        try:
            # Create command from task data
            command = CronCommand(
                command_type=CommandType(task_dict['command']),
                params=task_dict.get('command_params', {})
            )

            # Validate command
            validation = command.validate()
            if not validation.valid:
                self.logger.error(
                    f"Task {task_id} has invalid command: {validation.errors}"
                )
                return

            # Create executor
            executor = TaskExecutor(
                task_id=task_id,
                task_name=task_name,
                command=command
            )
            executor.powerwall_connector = self._powerwall_connector

            # Get configured timezone
            try:
                config = get_config()
                configured_tz = config.automation.timezone
            except Exception:
                configured_tz = None

            # Schedule daily execution at specified time with timezone
            if configured_tz:
                job = schedule.every().day.at(task_time, tz=configured_tz).do(executor)
                self.logger.info(
                    f"Registered task {task_id} ({task_name}) at {task_time} {configured_tz}"
                )
            else:
                job = schedule.every().day.at(task_time).do(executor)
                self.logger.info(
                    f"Registered task {task_id} ({task_name}) at {task_time} (system timezone)"
                )

            job.tag(task_id)

            # Track registration
            self._registered_tasks[task_id] = {
                'job': job,
                'executor': executor,
                'task_dict': task_dict
            }

        except Exception as e:
            self.logger.error(f"Failed to register task {task_id}: {e}")

    def unregister_task(self, task_id: str) -> None:
        """
        Unregister a task from the planner.

        Args:
            task_id: ID of task to unregister
        """
        if task_id not in self._registered_tasks:
            self.logger.warning(f"Task {task_id} is not registered")
            return

        try:
            # Remove from schedule library
            schedule.clear(task_id)

            # Remove from tracking
            del self._registered_tasks[task_id]

            self.logger.info(f"Unregistered task {task_id}")

        except Exception as e:
            self.logger.error(f"Failed to unregister task {task_id}: {e}")

    def execute_task_now(self, task_id: str) -> Dict[str, Any]:
        """
        Execute a task immediately (outside of schedule) - synchronous version.

        Args:
            task_id: ID of task to execute

        Returns:
            Execution result dictionary
        """
        if task_id in self._registered_tasks:
            # Execute registered task
            executor = self._registered_tasks[task_id]['executor']
            return executor.execute()
        else:
            # Load from database and execute
            from .task_executor import TaskExecutor
            from ..powerwall.commands import CronCommand, CommandType

            task_dict = self._task_service.get_task(task_id)

            # Create command
            command = CronCommand(
                command_type=CommandType(task_dict['command']),
                params=task_dict.get('command_params', {})
            )

            # Create executor
            executor = TaskExecutor(
                task_id=task_dict['id'],
                task_name=task_dict['name'],
                command=command
            )
            executor.powerwall_connector = self._powerwall_connector

            # Execute immediately
            return executor.execute()

    def execute_task_async(self, task_id: str) -> Dict[str, Any]:
        """
        Execute a task asynchronously in a background thread.

        Args:
            task_id: ID of task to execute

        Returns:
            Dictionary with execution_id and status
        """
        try:
            # Get task data first to include in execution record
            task_dict = self._task_service.get_task(task_id)
            
            # Create execution record with metadata
            execution = self._execution_service.create_execution(
                task_id=task_id,
                status='pending',
                execution_type='manual',  # Manual execution via API
                task_name=task_dict['name'],
                command=task_dict['command'],
                command_params=task_dict.get('command_params', {})
            )
            execution_id = execution['id']

            # Get or create executor
            if task_id in self._registered_tasks:
                executor = self._registered_tasks[task_id]['executor']
            else:
                # Load from database and create executor
                from .task_executor import TaskExecutor
                from ..powerwall.commands import CronCommand, CommandType

                # Create command
                command = CronCommand(
                    command_type=CommandType(task_dict['command']),
                    params=task_dict.get('command_params', {})
                )

                # Create executor
                executor = TaskExecutor(
                    task_id=task_dict['id'],
                    task_name=task_dict['name'],
                    command=command
                )
                executor.powerwall_connector = self._powerwall_connector

            # Launch background thread
            thread = threading.Thread(
                target=executor.execute_async,
                args=(execution_id,),
                name=f"TaskExecution-{task_id}-{execution_id}",
                daemon=True
            )
            thread.start()

            return {
                'execution_id': execution_id,
                'task_id': task_id,
                'status': 'pending',
                'message': 'Task execution started'
            }

        except Exception as e:
            self.logger.error(f"Failed to start async execution for task {task_id}: {e}")
            raise

    def get_registered_tasks(self) -> list:
        """
        Get list of registered task IDs.

        Returns:
            List of task IDs currently registered with planner
        """
        return list(self._registered_tasks.keys())

    def get_status(self) -> Dict[str, Any]:
        """
        Get planner status.

        Returns:
            Dictionary with planner status information
        """
        return {
            'is_running': self._is_running,
            'task_count': len(self._registered_tasks),
            'next_run': self._get_next_run_time()
        }

    def _bootstrap_tasks(self) -> None:
        """Bootstrap all enabled tasks from database."""
        try:
            self.logger.info("Bootstrapping tasks from database")

            # Get all enabled tasks
            enabled_tasks = self._task_service.list_tasks(enabled_only=True)

            # Register each task
            for task_dict in enabled_tasks:
                try:
                    self.register_task(task_dict)
                except Exception as e:
                    self.logger.error(
                        f"Failed to bootstrap task {task_dict['id']}: {e}"
                    )

            self.logger.info(
                f"Bootstrapped {len(enabled_tasks)} tasks from database"
            )

        except Exception as e:
            self.logger.error(f"Failed to bootstrap tasks: {e}")

    def _run_loop(self) -> None:
        """Main planner loop running in background thread."""
        self.logger.info("Planner thread started")

        try:
            while not self._stop_event.is_set():
                try:
                    # Run pending tasks
                    schedule.run_pending()

                    # Sleep for check interval
                    if self._stop_event.wait(self._check_interval):
                        break  # Stop event was set

                except Exception as e:
                    self.logger.error(f"Error in planner loop: {e}")
                    time.sleep(self._check_interval)

        except Exception as e:
            self.logger.critical(f"Critical error in planner thread: {e}")

        finally:
            self.logger.info("Planner thread ending")

    def reload_all_tasks(self) -> Dict[str, Any]:
        """
        Reload all tasks from database with current timezone configuration.
        
        This will unregister all current tasks and re-register them with the
        current timezone setting from the configuration.
        
        Returns:
            Dictionary with reload results
        """
        try:
            self.logger.info("Reloading all tasks with current timezone configuration")
            
            # Get current timezone for logging
            try:
                config = get_config()
                current_tz = config.automation.timezone
                self.logger.info(f"Reloading tasks with timezone: {current_tz}")
            except Exception as e:
                self.logger.warning(f"Could not determine current timezone: {e}")
                current_tz = "system timezone"
            
            # Clear all existing scheduled tasks
            schedule.clear()
            old_task_count = len(self._registered_tasks)
            self._registered_tasks.clear()
            
            # Re-bootstrap all tasks from database
            self._bootstrap_tasks()
            
            new_task_count = len(self._registered_tasks)
            
            self.logger.info(
                f"Task reload complete: {old_task_count} -> {new_task_count} tasks, "
                f"timezone: {current_tz}"
            )
            
            return {
                'success': True,
                'old_task_count': old_task_count,
                'new_task_count': new_task_count,
                'timezone': current_tz,
                'message': f'Reloaded {new_task_count} tasks with timezone: {current_tz}'
            }
            
        except Exception as e:
            self.logger.error(f"Failed to reload tasks: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f'Failed to reload tasks: {e}'
            }

    def _get_next_run_time(self) -> Optional[str]:
        """Get the next scheduled run time across all tasks."""
        try:
            next_run = schedule.next_run()
            return next_run.isoformat() if next_run else None
        except Exception:
            return None


# Global instance
_planner: Optional[Planner] = None


def get_planner() -> Planner:
    """Get the global planner instance."""
    global _planner
    if _planner is None:
        _planner = Planner()
    return _planner
