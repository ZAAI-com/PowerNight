"""
Database services for PowerNight.

Data access services for tasks, task executions, and task presets.
"""

from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from .models import Task, TaskExecution, TaskPreset
from .exceptions import DatabaseError, TaskNotFoundError, PresetNotFoundError
from .connection import get_db_session_context


class TaskService:
    """Service for managing task entries."""
    
    def __init__(self, session: Optional[Session] = None):
        self.session = session
    
    def _get_session(self) -> Session:
        """Get database session."""
        if self.session:
            return self.session
        return get_db_session_context()
    
    def create_task(
        self,
        name: str,
        time: str,
        command: str,
        command_params: Optional[Dict[str, Any]] = None,
        enabled: bool = True
    ) -> Dict[str, Any]:
        """
        Create a new task entry.

        Args:
            name: Task name
            time: Time in HH:MM format
            command: Command type (mode, reserve, current, gridcharging, gridexport)
            command_params: Optional parameters for the command
            enabled: Whether task is enabled

        Returns:
            Dictionary representation of created task
        """
        try:
            with self._get_session() as session:
                task = Task(
                    name=name,
                    time=time,
                    command=command,
                    command_params=command_params or {},
                    enabled=enabled
                )

                session.add(task)
                session.commit()
                session.refresh(task)  # Refresh to get database-generated values

                # Return dictionary representation within session context
                return task.to_dict()

        except Exception as e:
            raise DatabaseError(f"Failed to create task: {e}")
    
    def get_task(self, task_id: str) -> Dict[str, Any]:
        """
        Get a task by ID.
        
        Args:
            task_id: Task ID
        
        Returns:
            Dictionary representation of the task
            
        Raises:
            TaskNotFoundError: If task not found
        """
        try:
            with self._get_session() as session:
                task = session.query(Task).filter(
                    Task.id == task_id
                ).first()
                
                if not task:
                    raise TaskNotFoundError(f"Task {task_id} not found")
                
                # Return dictionary representation within session context
                return task.to_dict()
                
        except TaskNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to get task: {e}")
    
    def list_tasks(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """
        List all task entries.

        Args:
            enabled_only: Only return enabled tasks

        Returns:
            List of task dictionaries
        """
        try:
            with self._get_session() as session:
                query = session.query(Task)

                if enabled_only:
                    query = query.filter(Task.enabled == True)

                tasks = query.order_by(Task.time).all()

                # Return dictionary representations within session context
                return [t.to_dict() for t in tasks]

        except Exception as e:
            raise DatabaseError(f"Failed to list tasks: {e}")
    
    def update_task(
        self,
        task_id: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Update a task entry.

        Args:
            task_id: Task ID
            **kwargs: Fields to update

        Returns:
            Dictionary representation of updated task

        Raises:
            TaskNotFoundError: If task not found
        """
        try:
            with self._get_session() as session:
                task = session.query(Task).filter(
                    Task.id == task_id
                ).first()

                if not task:
                    raise TaskNotFoundError(f"Task {task_id} not found")

                # Update allowed fields
                allowed_fields = {
                    'name', 'time', 'command', 'command_params',
                    'enabled', 'last_execution',
                    'last_status', 'last_error', 'execution_count'
                }

                for field, value in kwargs.items():
                    if field in allowed_fields and hasattr(task, field):
                        setattr(task, field, value)

                task.updated_at = datetime.now(timezone.utc)
                session.commit()
                session.refresh(task)  # Refresh to get updated values

                # Return dictionary representation within session context
                return task.to_dict()

        except TaskNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to update task: {e}")
    
    def delete_task(self, task_id: str) -> bool:
        """
        Delete a task entry.
        
        Args:
            task_id: Task ID
        
        Returns:
            True if deleted successfully
            
        Raises:
            TaskNotFoundError: If task not found
        """
        try:
            with self._get_session() as session:
                task = session.query(Task).filter(
                    Task.id == task_id
                ).first()
                
                if not task:
                    raise TaskNotFoundError(f"Task {task_id} not found")
                
                session.delete(task)
                session.commit()
                
                return True
                
        except TaskNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to delete task: {e}")
    
    def get_enabled_tasks(self) -> List[Dict[str, Any]]:
        """
        Get all enabled task entries.
        
        Returns:
            List of enabled task dictionaries
        """
        return self.list_tasks(enabled_only=True)
    
    def update_execution_status(
        self,
        task_id: str,
        status: str,
        error: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update task execution status.

        Args:
            task_id: Task ID
            status: Execution status (success, error, pending)
            error: Optional error message

        Returns:
            Dictionary representation of updated task
        """
        try:
            with self._get_session() as session:
                task = session.query(Task).filter(
                    Task.id == task_id
                ).first()

                if not task:
                    raise TaskNotFoundError(f"Task {task_id} not found")

                # Update execution fields
                task.last_execution = datetime.now(timezone.utc)
                task.last_status = status
                task.last_error = error
                task.execution_count = (task.execution_count or 0) + 1
                task.updated_at = datetime.now(timezone.utc)

                session.commit()
                session.refresh(task)  # Refresh to get updated values

                # Return dictionary representation within session context
                return task.to_dict()

        except TaskNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to update task execution status: {e}")


class TaskExecutionService:
    """Service for managing task execution records."""
    
    def __init__(self, session: Optional[Session] = None):
        self.session = session
    
    def _get_session(self) -> Session:
        """Get database session."""
        if self.session:
            return self.session
        return get_db_session_context()
    
    def create_execution(
        self,
        task_id: str,
        status: str = 'pending',
        execution_type: str = 'manual',
        task_name: Optional[str] = None,
        command: Optional[str] = None,
        command_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new task execution record.

        Args:
            task_id: ID of the task being executed
            status: Initial execution status (default: 'pending')
            execution_type: Type of execution ('scheduled' or 'manual')
            task_name: Name of the task at execution time
            command: Command type being executed
            command_params: Command parameters

        Returns:
            Dictionary representation of created execution
        """
        try:
            with self._get_session() as session:
                execution = TaskExecution(
                    task_id=task_id,
                    status=status,
                    execution_type=execution_type,
                    task_name=task_name,
                    command=command,
                    command_params=command_params
                )

                session.add(execution)
                session.commit()
                session.refresh(execution)  # Refresh to get database-generated values

                # Return dictionary representation within session context
                return execution.to_dict()

        except Exception as e:
            raise DatabaseError(f"Failed to create task execution: {e}")
    
    def get_execution(self, execution_id: str) -> Dict[str, Any]:
        """
        Get a task execution by ID.
        
        Args:
            execution_id: Execution ID
        
        Returns:
            Dictionary representation of the execution
            
        Raises:
            DatabaseError: If execution not found
        """
        try:
            with self._get_session() as session:
                execution = session.query(TaskExecution).filter(
                    TaskExecution.id == execution_id
                ).first()
                
                if not execution:
                    raise DatabaseError(f"Task execution {execution_id} not found")
                
                # Return dictionary representation within session context
                return execution.to_dict()
                
        except DatabaseError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to get task execution: {e}")
    
    def update_execution_status(
        self,
        execution_id: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        api_response: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Update task execution status.

        Args:
            execution_id: Execution ID
            status: New execution status (pending, running, success, error)
            result: Optional execution result data
            error_message: Optional error message
            api_response: Optional full API response data

        Returns:
            Dictionary representation of updated execution
        """
        try:
            with self._get_session() as session:
                execution = session.query(TaskExecution).filter(
                    TaskExecution.id == execution_id
                ).first()

                if not execution:
                    raise DatabaseError(f"Task execution {execution_id} not found")

                # Update execution fields
                execution.status = status
                execution.updated_at = datetime.now(timezone.utc)
                
                if result is not None:
                    execution.result = result
                
                if error_message is not None:
                    execution.error_message = error_message
                
                if api_response is not None:
                    execution.api_response = api_response
                
                # Set completion time if status is success or error
                if status in ('success', 'error'):
                    execution.completed_at = datetime.now(timezone.utc)

                session.commit()
                session.refresh(execution)  # Refresh to get updated values

                # Return dictionary representation within session context
                return execution.to_dict()

        except DatabaseError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to update task execution status: {e}")
    
    def list_executions(
        self,
        task_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List task executions.

        Args:
            task_id: Optional task ID to filter by
            limit: Maximum number of executions to return

        Returns:
            List of execution dictionaries
        """
        try:
            with self._get_session() as session:
                query = session.query(TaskExecution)

                if task_id:
                    query = query.filter(TaskExecution.task_id == task_id)

                executions = query.order_by(TaskExecution.started_at.desc()).limit(limit).all()

                # Return dictionary representations within session context
                return [e.to_dict() for e in executions]

        except Exception as e:
            raise DatabaseError(f"Failed to list task executions: {e}")
    
    def cleanup_old_executions(
        self,
        days_to_keep: int = 7,
        max_per_task: int = 100
    ) -> int:
        """
        Clean up old task execution records.

        Args:
            days_to_keep: Number of days to keep executions
            max_per_task: Maximum executions to keep per task

        Returns:
            Number of executions deleted
        """
        try:
            with self._get_session() as session:
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
                
                # Delete old executions
                old_executions = session.query(TaskExecution).filter(
                    TaskExecution.created_at < cutoff_date
                ).all()
                
                deleted_count = len(old_executions)
                for execution in old_executions:
                    session.delete(execution)
                
                # For each task, keep only the most recent executions
                task_ids = session.query(TaskExecution.task_id).distinct().all()
                for (task_id,) in task_ids:
                    # Get executions for this task, ordered by most recent
                    task_executions = session.query(TaskExecution).filter(
                        TaskExecution.task_id == task_id
                    ).order_by(TaskExecution.started_at.desc()).all()
                    
                    # Delete excess executions
                    if len(task_executions) > max_per_task:
                        for execution in task_executions[max_per_task:]:
                            session.delete(execution)
                            deleted_count += 1
                
                session.commit()
                return deleted_count

        except Exception as e:
            raise DatabaseError(f"Failed to cleanup old executions: {e}")
    
    def get_execution_logs(
        self,
        limit: int = 100,
        offset: int = 0,
        task_name_filter: Optional[str] = None,
        execution_type_filter: Optional[str] = None,
        status_filter: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get paginated task execution logs with filtering.

        Args:
            limit: Maximum number of logs to return
            offset: Number of logs to skip
            task_name_filter: Filter by task name (partial match)
            execution_type_filter: Filter by execution type ('scheduled' or 'manual')
            status_filter: Filter by status ('pending', 'running', 'success', 'error')
            start_date: Filter logs after this date
            end_date: Filter logs before this date

        Returns:
            Dictionary with logs and pagination info
        """
        try:
            with self._get_session() as session:
                query = session.query(TaskExecution)

                # Apply filters
                if task_name_filter:
                    query = query.filter(TaskExecution.task_name.ilike(f'%{task_name_filter}%'))
                
                if execution_type_filter:
                    query = query.filter(TaskExecution.execution_type == execution_type_filter)
                
                if status_filter:
                    query = query.filter(TaskExecution.status == status_filter)
                
                if start_date:
                    query = query.filter(TaskExecution.started_at >= start_date)
                
                if end_date:
                    query = query.filter(TaskExecution.started_at <= end_date)

                # Get total count
                total_count = query.count()

                # Get paginated results
                executions = query.order_by(TaskExecution.started_at.desc()).offset(offset).limit(limit).all()

                # Convert to dictionaries
                logs = [e.to_dict() for e in executions]

                return {
                    'logs': logs,
                    'total': total_count,
                    'limit': limit,
                    'offset': offset,
                    'has_more': offset + limit < total_count
                }

        except Exception as e:
            raise DatabaseError(f"Failed to get execution logs: {e}")


class TaskPresetService:
    """Service for managing task presets."""

    def __init__(self, session: Optional[Session] = None):
        self.session = session

    def _get_session(self) -> Session:
        """Get database session."""
        if self.session:
            return self.session
        return get_db_session_context()

    def create_preset(
        self,
        name: str,
        command: str,
        command_params: Optional[Dict[str, Any]] = None,
        default_time: Optional[str] = None,
        is_builtin: bool = False,
        sort_order: int = 0
    ) -> Dict[str, Any]:
        """Create a new task preset."""
        try:
            with self._get_session() as session:
                preset = TaskPreset(
                    name=name,
                    command=command,
                    command_params=command_params or {},
                    default_time=default_time,
                    is_builtin=is_builtin,
                    sort_order=sort_order
                )
                session.add(preset)
                session.commit()
                session.refresh(preset)
                return preset.to_dict()
        except Exception as e:
            raise DatabaseError(f"Failed to create preset: {e}")

    def list_presets(self) -> List[Dict[str, Any]]:
        """List all presets, ordered by sort_order then name."""
        try:
            with self._get_session() as session:
                presets = session.query(TaskPreset).order_by(
                    TaskPreset.sort_order, TaskPreset.name
                ).all()
                return [p.to_dict() for p in presets]
        except Exception as e:
            raise DatabaseError(f"Failed to list presets: {e}")

    def get_preset(self, preset_id: str) -> Dict[str, Any]:
        """Get a preset by ID."""
        try:
            with self._get_session() as session:
                preset = session.query(TaskPreset).filter(
                    TaskPreset.id == preset_id
                ).first()
                if not preset:
                    raise PresetNotFoundError(f"Preset {preset_id} not found")
                return preset.to_dict()
        except PresetNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to get preset: {e}")

    def delete_preset(self, preset_id: str) -> bool:
        """Delete a user preset. Built-in presets cannot be deleted."""
        try:
            with self._get_session() as session:
                preset = session.query(TaskPreset).filter(
                    TaskPreset.id == preset_id
                ).first()
                if not preset:
                    raise PresetNotFoundError(f"Preset {preset_id} not found")
                if preset.is_builtin:
                    raise DatabaseError("Built-in presets cannot be deleted")
                session.delete(preset)
                session.commit()
                return True
        except (PresetNotFoundError, DatabaseError):
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to delete preset: {e}")

    def preset_exists_by_name(self, name: str) -> bool:
        """Check if a preset with the given name already exists."""
        try:
            with self._get_session() as session:
                count = session.query(TaskPreset).filter(
                    TaskPreset.name == name
                ).count()
                return count > 0
        except Exception:
            return False
