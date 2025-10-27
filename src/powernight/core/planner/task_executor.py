"""
PowerNight Task Executor

Executes stored tasks against the Powerwall using PyPowerwall commands.
"""

import logging
import threading
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from ..database.services import TaskService, TaskExecutionService
from ..powerwall import PowerwallConnector
from ..powerwall.exceptions import PowerwallError
from ..powerwall.commands import CommandType, CronCommand


class TaskExecutor:
    """
    Executes a stored task command against the Powerwall.

    Simplified executor with direct PyPowerwall API calls.
    """

    def __init__(self, task_id: str, task_name: str, command: CronCommand):
        """
        Initialize task executor.

        Args:
            task_id: ID of the task
            task_name: Name of the task
            command: CronCommand to execute
        """
        self.task_id = task_id
        self.task_name = task_name
        self.command = command
        self.task_service = TaskService()
        self.execution_service = TaskExecutionService()
        self.logger = logging.getLogger(__name__)
        self.powerwall_connector: Optional[PowerwallConnector] = None

    def __call__(self) -> Dict[str, Any]:
        """Make the executor callable for schedule library."""
        # For scheduled executions, create an execution record first
        try:
            execution = self.execution_service.create_execution(
                task_id=self.task_id,
                status='pending',
                execution_type='scheduled',  # Scheduled execution
                task_name=self.task_name,
                command=self.command.command_type.value,
                command_params=self.command.params
            )
            execution_id = execution['id']
            
            # Execute asynchronously to track the execution
            self.execute_async(execution_id)
            
            return {
                'success': True,
                'task_id': self.task_id,
                'execution_id': execution_id,
                'message': 'Scheduled task execution started'
            }
            
        except Exception as e:
            self.logger.error(f"Failed to start scheduled execution for task {self.task_id}: {e}")
            # Fallback to direct execution
            return self.execute()

    def execute_async(self, execution_id: str) -> None:
        """
        Execute the task command asynchronously with status tracking.

        Args:
            execution_id: ID of the execution record to update
        """
        try:
            # Update status to running
            self.execution_service.update_execution_status(execution_id, 'running')
            
            # Execute the command
            result = self._execute_command()
            
            # Extract and remove api_response from result to store separately
            api_response = result.pop('api_response', None)
            
            # Update status to success with result and API response
            self.execution_service.update_execution_status(
                execution_id, 
                'success', 
                result=result,
                api_response=api_response
            )
            
            # Update task status in database
            self.task_service.update_execution_status(
                self.task_id, status='success', error=None
            )
            
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Task {self.task_id} execution failed: {error_msg}")
            
            # Update execution status to error
            self.execution_service.update_execution_status(
                execution_id, 
                'error', 
                error_message=error_msg
            )
            
            # Update task status in database
            self.task_service.update_execution_status(
                self.task_id, status='error', error=error_msg
            )

    def execute(self) -> Dict[str, Any]:
        """
        Execute the task command against the Powerwall (synchronous).

        Returns:
            Dictionary with execution results

        Raises:
            PowerwallError: If execution fails
        """
        start_time = datetime.now(timezone.utc)
        
        try:
            result = self._execute_command()
            
            # Update task status in database
            self.task_service.update_execution_status(
                self.task_id, status='success', error=None
            )

            return {
                'success': True,
                'task_id': self.task_id,
                'message': result.get('message', 'Task executed successfully'),
                'execution_time': (datetime.now(timezone.utc) - start_time).total_seconds()
            }

        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Task {self.task_id} execution failed: {error_msg}")
            self.task_service.update_execution_status(
                self.task_id, status='error', error=error_msg
            )
            raise

    def _execute_command(self) -> Dict[str, Any]:
        """
        Execute the actual command against the Powerwall.

        Returns:
            Dictionary with execution results

        Raises:
            PowerwallError: If execution fails
        """
        self.logger.info(
            f"Executing task {self.task_id} ('{self.task_name}'): "
            f"command={self.command.command_type.value}, params={self.command.params}"
        )

        # Try to get PowerwallConnector from Flask app if not available
        if not self.powerwall_connector:
            try:
                from flask import current_app
                self.powerwall_connector = getattr(current_app, 'powerwall_connector', None)
            except Exception:
                pass

        if not self.powerwall_connector:
            raise PowerwallError("Powerwall connector not available")

        if not self.powerwall_connector.is_connected():
            raise PowerwallError("Powerwall is not connected or authenticated. Please login via the Settings page.")

        command_type = self.command.command_type
        params = self.command.params

        # --- Execute PyPowerwall Commands ---
        api_response = None
        
        if command_type == CommandType.MODE:
            api_response = self.powerwall_connector.set_mode(params['mode'])
            result_message = f"Set mode to '{params['mode']}'"

        elif command_type == CommandType.RESERVE:
            api_response = self.powerwall_connector.set_backup_reserve_percentage(params['reserve'])
            result_message = f"Set backup reserve to {params['reserve']}%"

        elif command_type == CommandType.GRID_CHARGING:
            api_response = self.powerwall_connector.set_grid_charging(params['enabled'])
            result_message = f"Set grid charging to {'enabled' if params['enabled'] else 'disabled'}"

        elif command_type == CommandType.GRID_EXPORT:
            api_response = self.powerwall_connector.set_export_mode(params['mode'])
            result_message = f"Set grid export to '{params['mode']}'"

        elif command_type == CommandType.CURRENT:
            soc = self.powerwall_connector.get_state_of_charge()
            if soc is not None:
                api_response = self.powerwall_connector.set_backup_reserve_percentage(soc)
                result_message = f"Set backup reserve to current charge level of {soc}%"
            else:
                raise PowerwallError("Could not retrieve current state of charge")

        else:
            raise PowerwallError(f"Unknown command type: {command_type.value}")

        # Sanitize API response for database storage
        sanitized_api_response = None
        if api_response is not None:
            try:
                # Use the PowerwallConnector's sanitization method
                sanitized_api_response = self.powerwall_connector._sanitize_api_response(api_response)
            except Exception as e:
                self.logger.warning(f"Failed to sanitize API response: {e}")
                # Fallback: convert to string representation
                sanitized_api_response = {"error": "Failed to sanitize response", "raw_type": str(type(api_response))}

        self.logger.info(f"Task {self.task_id} executed successfully: {result_message}")

        return {
            'success': True,
            'task_id': self.task_id,
            'message': result_message,
            'command': command_type.value,
            'params': params,
            'api_response': sanitized_api_response
        }


class TaskManager:
    """
    Manages the lifecycle of tasks in the planner.

    Provides convenience methods for task operations using the SimplePlanner.
    """

    def __init__(self, powerwall_connector: Optional[PowerwallConnector] = None):
        """Initialize task manager."""
        self.logger = logging.getLogger(__name__)
        self.task_service = TaskService()
        self._powerwall_connector = powerwall_connector

        # Import here to avoid circular imports
        from .planner import get_planner
        self.planner = get_planner()

    def register_task(self, task_data: Dict[str, Any]) -> None:
        """
        Register a task with the planner.

        Args:
            task_data: Task dictionary with id, name, time, command, command_params, enabled
        """
        self.planner.register_task(task_data)

    def unregister_task(self, task_id: str) -> None:
        """
        Unregister a task from the planner.

        Args:
            task_id: ID of task to unregister
        """
        self.planner.unregister_task(task_id)

    def update_task(self, task_data: Dict[str, Any]) -> None:
        """
        Update a registered task.

        Args:
            task_data: Updated task dictionary
        """
        # Unregister old version
        self.unregister_task(task_data['id'])

        # Register new version if enabled
        if task_data.get('enabled', False):
            self.register_task(task_data)

        self.logger.info(f"Updated task {task_data['id']}")

    def enable_task(self, task_id: str) -> None:
        """
        Enable a task.

        Args:
            task_id: ID of task to enable
        """
        try:
            # Update database
            task = self.task_service.update_task(
                task_id,
                enabled=True
            )

            # Register with planner
            self.register_task(task)

            self.logger.info(f"Enabled task {task_id}")

        except Exception as e:
            self.logger.error(f"Failed to enable task {task_id}: {e}")
            raise

    def disable_task(self, task_id: str) -> None:
        """
        Disable a task.

        Args:
            task_id: ID of task to disable
        """
        try:
            # Update database
            self.task_service.update_task(
                task_id,
                enabled=False
            )

            # Unregister from planner
            self.unregister_task(task_id)

            self.logger.info(f"Disabled task {task_id}")

        except Exception as e:
            self.logger.error(f"Failed to disable task {task_id}: {e}")
            raise

    def execute_task_now(self, task_id: str) -> Dict[str, Any]:
        """
        Execute a task immediately (outside of schedule) - synchronous.

        Args:
            task_id: ID of task to execute

        Returns:
            Execution result dictionary
        """
        return self.planner.execute_task_now(task_id)

    def execute_task_async(self, task_id: str) -> Dict[str, Any]:
        """
        Execute a task asynchronously in a background thread.

        Args:
            task_id: ID of task to execute

        Returns:
            Dictionary with execution_id and status
        """
        return self.planner.execute_task_async(task_id)

    def get_registered_tasks(self) -> list:
        """
        Get list of registered task IDs.

        Returns:
            List of task IDs currently registered with planner
        """
        return self.planner.get_registered_tasks()

    def is_registered(self, task_id: str) -> bool:
        """
        Check if a task is registered with the planner.

        Args:
            task_id: ID of task to check

        Returns:
            True if registered, False otherwise
        """
        return task_id in self.get_registered_tasks()

    def reload_all_tasks(self) -> Dict[str, Any]:
        """
        Reload all tasks with current timezone configuration.
        
        This will unregister all current tasks and re-register them with the
        current timezone setting from the configuration.
        
        Returns:
            Dictionary with reload results
        """
        return self.planner.reload_all_tasks()


# Global instance
_task_manager: Optional[TaskManager] = None


def get_task_manager(powerwall_connector: Optional[PowerwallConnector] = None) -> TaskManager:
    """Get the global task manager instance."""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager(powerwall_connector)
    # Always update the connector in case the app was re-initialized
    _task_manager._powerwall_connector = powerwall_connector
    # Also update the planner's PowerwallConnector
    if powerwall_connector:
        _task_manager.planner._powerwall_connector = powerwall_connector
    return _task_manager


# Backwards compatibility aliases (will be removed later)
# Backwards compatibility aliases (deprecated)
# These are kept for backwards compatibility but should not be used in new code
CronJobExecutor = TaskExecutor
CronJobManager = TaskManager
get_cronjob_manager = get_task_manager
