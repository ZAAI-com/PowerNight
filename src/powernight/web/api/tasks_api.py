"""
PowerNight Tasks API Blueprint

REST API endpoints for task management in the Planner.
"""

from flask import Blueprint, jsonify, request, current_app
from datetime import datetime, timezone
from typing import Dict, Any

from ...core.database.services import TaskService, TaskExecutionService, TaskPresetService
from ...core.database.exceptions import DatabaseError, TaskNotFoundError, PresetNotFoundError
from ...core.planner import get_task_manager
from ...core.powerwall.commands import CronCommand, CommandType
from ...core.powerwall.exceptions import PowerwallError
from .auth import require_auth
from .errors import APIError, ValidationError


# Create tasks blueprint
tasks_blueprint = Blueprint('tasks', __name__, url_prefix='/api/v1/tasks')

# Initialize services - we'll create them per request to avoid session issues
def get_task_service() -> TaskService:
    """Get a task service instance."""
    return TaskService()


@tasks_blueprint.route('', methods=['GET'])
@require_auth
def list_tasks():
    """
    Get all tasks.

    Query Parameters:
        enabled_only (bool): Only return enabled tasks

    Returns:
        JSON response with list of tasks
    """
    try:
        enabled_only = request.args.get('enabled_only', 'false').lower() == 'true'

        task_service = get_task_service()
        tasks = task_service.list_tasks(enabled_only=enabled_only)

        return jsonify({
            'success': True,
            'data': {
                'tasks': tasks,
                'total': len(tasks)
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        current_app.logger.error(f"Failed to list tasks: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Failed to list tasks: {e}',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@tasks_blueprint.route('/<task_id>', methods=['GET'])
@require_auth
def get_task(task_id: str):
    """
    Get a specific task.

    Args:
        task_id: ID of the task

    Returns:
        JSON response with task details
    """
    try:
        task_service = get_task_service()
        task_data = task_service.get_task(task_id)

        # Get registration status
        task_manager = get_task_manager()
        is_registered = task_manager.is_registered(task_id)

        # Add registration status to the dictionary
        task_data['is_registered'] = is_registered

        return jsonify({
            'success': True,
            'data': task_data,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    except TaskNotFoundError as e:
        return jsonify({
            'success': False,
            'error': 'Not Found',
            'message': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 404

    except Exception as e:
        current_app.logger.error(f"Failed to get task: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Failed to get task: {e}',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@tasks_blueprint.route('', methods=['POST'])
@require_auth
def create_task():
    """
    Create a new task.

    Request Body:
        {
            "name": "Daily reserve change",
            "time": "14:15",
            "command": "reserve",
            "command_params": {"reserve": 40},
            "enabled": true
        }

    Returns:
        JSON response with created task
    """
    try:
        if not request.is_json:
            raise ValidationError("Request must contain JSON data")

        data = request.get_json()

        # Validate required fields
        required_fields = ['name', 'time', 'command']
        for field in required_fields:
            if field not in data:
                raise ValidationError(f"Missing required field: {field}")

        # Validate command type
        try:
            CommandType(data['command'])
        except ValueError:
            raise ValidationError(
                f"Invalid command type. Must be one of: {[c.value for c in CommandType]}"
            )

        # Validate time format
        time = data['time']
        try:
            hour, minute = time.split(':')
            if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
                raise ValueError("Invalid time range")
        except (ValueError, IndexError):
            raise ValidationError("Invalid time format. Must be HH:MM")

        # Validate command parameters
        command_params = data.get('command_params', {})
        command = CronCommand(data['command'], command_params)
        validation = command.validate()

        if not validation.valid:
            raise ValidationError(f"Invalid command parameters: {', '.join(validation.errors)}")

        # Create task
        task_service = get_task_service()
        task_data = task_service.create_task(
            name=data['name'],
            time=time,
            command=data['command'],
            command_params=command_params,
            enabled=data.get('enabled', True)
        )

        # Register with planner if enabled
        if task_data['enabled']:
            try:
                task_manager = get_task_manager()
                task_manager.register_task(task_data)
            except Exception as reg_error:
                current_app.logger.error(f"Failed to register task: {reg_error}")
                # Continue - task is created but not scheduled

        return jsonify({
            'success': True,
            'data': task_data,
            'message': 'Task created successfully',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 201

    except ValidationError as e:
        return jsonify({
            'success': False,
            'error': 'Validation Error',
            'message': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 422

    except Exception as e:
        current_app.logger.error(f"Failed to create task: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Failed to create task: {e}',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@tasks_blueprint.route('/<task_id>', methods=['PUT', 'PATCH'])
@require_auth
def update_task(task_id: str):
    """
    Update a task.

    Args:
        task_id: ID of the task

    Request Body:
        {
            "name": "Updated name",
            "time": "15:00",
            "command_params": {"reserve": 50},
            "enabled": true
        }

    Returns:
        JSON response with updated task
    """
    try:
        if not request.is_json:
            raise ValidationError("Request must contain JSON data")

        data = request.get_json()

        # Get existing task to validate against
        task_service = get_task_service()
        existing_task_data = task_service.get_task(task_id)

        # Validate time format if provided
        if 'time' in data:
            time = data['time']
            try:
                hour, minute = time.split(':')
                if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
                    raise ValueError("Invalid time range")
            except (ValueError, IndexError):
                raise ValidationError("Invalid time format. Must be HH:MM")

        # Validate command parameters if provided
        if 'command_params' in data:
            command = CronCommand(
                existing_task_data['command'],
                data['command_params']
            )
            validation = command.validate()

            if not validation.valid:
                raise ValidationError(
                    f"Invalid command parameters: {', '.join(validation.errors)}"
                )

        # Update task
        updated_task_data = task_service.update_task(
            task_id,
            **data
        )

        # Update in planner
        try:
            task_manager = get_task_manager()
            task_manager.update_task(updated_task_data)
        except Exception as update_error:
            current_app.logger.error(f"Failed to update task in planner: {update_error}")

        return jsonify({
            'success': True,
            'data': updated_task_data,
            'message': 'Task updated successfully',
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    except TaskNotFoundError as e:
        return jsonify({
            'success': False,
            'error': 'Not Found',
            'message': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 404

    except ValidationError as e:
        return jsonify({
            'success': False,
            'error': 'Validation Error',
            'message': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 422

    except Exception as e:
        current_app.logger.error(f"Failed to update task: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Failed to update task: {e}',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@tasks_blueprint.route('/<task_id>', methods=['DELETE'])
@require_auth
def delete_task(task_id: str):
    """
    Delete a task.

    Args:
        task_id: ID of the task

    Returns:
        JSON response confirming deletion
    """
    try:
        # Unregister from planner first
        try:
            task_manager = get_task_manager()
            task_manager.unregister_task(task_id)
        except Exception as unreg_error:
            current_app.logger.warning(f"Failed to unregister task: {unreg_error}")

        # Delete from database
        task_service = get_task_service()
        task_service.delete_task(task_id)

        return jsonify({
            'success': True,
            'message': 'Task deleted successfully',
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    except TaskNotFoundError as e:
        return jsonify({
            'success': False,
            'error': 'Not Found',
            'message': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 404

    except Exception as e:
        current_app.logger.error(f"Failed to delete task: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Failed to delete task: {e}',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@tasks_blueprint.route('/<task_id>/toggle', methods=['POST'])
@require_auth
def toggle_task(task_id: str):
    """
    Toggle a task's enabled status.

    Args:
        task_id: ID of the task

    Returns:
        JSON response with updated task
    """
    try:
        task_service = get_task_service()
        task_manager = get_task_manager()

        # Get current task data as a dictionary
        current_task_data = task_service.get_task(task_id)

        # Toggle enabled status
        new_enabled = not current_task_data['enabled']

        if new_enabled:
            task_manager.enable_task(task_id)
        else:
            task_manager.disable_task(task_id)

        # Get updated task data as dictionary
        updated_task = task_service.get_task(task_id)

        return jsonify({
            'success': True,
            'data': updated_task,
            'message': f"Task {'enabled' if new_enabled else 'disabled'}",
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    except TaskNotFoundError as e:
        return jsonify({
            'success': False,
            'error': 'Not Found',
            'message': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 404

    except Exception as e:
        current_app.logger.error(f"Failed to toggle task: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Failed to toggle task: {e}',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@tasks_blueprint.route('/<task_id>/execute', methods=['POST'])
@require_auth
def execute_task(task_id: str):
    """
    Execute a task asynchronously.

    Args:
        task_id: ID of the task

    Returns:
        JSON response with execution_id and status
    """
    try:
        # Get PowerwallConnector from Flask app
        powerwall_connector = getattr(current_app, 'powerwall_connector', None)
        if powerwall_connector is None:
            return jsonify({
                'success': False,
                'error': 'Service Unavailable',
                'message': 'Powerwall connector is not available; complete Tesla authentication first',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 503
        task_manager = get_task_manager(powerwall_connector)
        result = task_manager.execute_task_async(task_id)

        return jsonify({
            'success': True,
            'data': result,
            'message': 'Task execution started',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 201

    except TaskNotFoundError as e:
        return jsonify({
            'success': False,
            'error': 'Not Found',
            'message': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 404

    except Exception as e:
        error_msg = str(e)
        current_app.logger.error(f"Failed to start task execution: {error_msg}")

        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Failed to start task execution: {error_msg}',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@tasks_blueprint.route('/<task_id>/executions/<execution_id>', methods=['GET'])
@require_auth
def get_task_execution(task_id: str, execution_id: str):
    """
    Get execution status by ID.

    Args:
        task_id: ID of the task
        execution_id: ID of the execution

    Returns:
        JSON response with execution status
    """
    try:
        execution_service = TaskExecutionService()
        execution = execution_service.get_execution(execution_id)

        # Verify the execution belongs to the task
        if execution['task_id'] != task_id:
            return jsonify({
                'success': False,
                'error': 'Not Found',
                'message': f'Execution {execution_id} not found for task {task_id}',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 404

        return jsonify({
            'success': True,
            'data': execution,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    except DatabaseError as e:
        return jsonify({
            'success': False,
            'error': 'Not Found',
            'message': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 404

    except Exception as e:
        current_app.logger.error(f"Failed to get task execution: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Failed to get task execution: {e}',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@tasks_blueprint.route('/<task_id>/executions', methods=['GET'])
@require_auth
def list_task_executions(task_id: str):
    """
    List recent executions for a task.

    Args:
        task_id: ID of the task

    Query Parameters:
        limit (int): Maximum number of executions to return (default: 10)

    Returns:
        JSON response with list of executions
    """
    try:
        limit = request.args.get('limit', 10, type=int)
        limit = min(limit, 100)  # Cap at 100

        execution_service = TaskExecutionService()
        executions = execution_service.list_executions(task_id=task_id, limit=limit)

        return jsonify({
            'success': True,
            'data': {
                'executions': executions,
                'total': len(executions)
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        current_app.logger.error(f"Failed to list task executions: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Failed to list task executions: {e}',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@tasks_blueprint.route('/commands', methods=['GET'])
@require_auth
def list_available_commands():
    """
    Get list of available command types and their parameters.

    Returns:
        JSON response with command definitions
    """
    try:
        from ...core.powerwall.commands import (
            CommandType,
            PowerwallMode,
            GridExportMode
        )

        commands = {
            'mode': {
                'description': 'Set Powerwall operating mode',
                'params': {
                    'mode': {
                        'type': 'string',
                        'required': True,
                        'options': [m.value for m in PowerwallMode]
                    }
                }
            },
            'reserve': {
                'description': 'Set backup reserve level',
                'params': {
                    'reserve': {
                        'type': 'number',
                        'required': True,
                        'min': 0,
                        'max': 100,
                        'unit': 'percent'
                    }
                }
            },
            'current': {
                'description': 'Set reserve to current charge level',
                'params': {}
            },
            'gridcharging': {
                'description': 'Enable or disable grid charging',
                'params': {
                    'enabled': {
                        'type': 'boolean',
                        'required': True
                    }
                }
            },
            'gridexport': {
                'description': 'Set grid export mode',
                'params': {
                    'mode': {
                        'type': 'string',
                        'required': True,
                        'options': [m.value for m in GridExportMode]
                    }
                }
            }
        }

        return jsonify({
            'success': True,
            'data': {
                'commands': commands
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        current_app.logger.error(f"Failed to list commands: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Failed to list commands: {e}',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@tasks_blueprint.route('/reload', methods=['POST'])
@require_auth
def reload_all_tasks():
    """
    Reload all tasks with current timezone configuration.
    
    This will unregister all current tasks and re-register them with the
    current timezone setting from the configuration.
    
    Returns:
        JSON response with reload results
    """
    try:
        # Get PowerwallConnector from Flask app
        powerwall_connector = getattr(current_app, 'powerwall_connector', None)
        task_manager = get_task_manager(powerwall_connector)
        
        result = task_manager.reload_all_tasks()
        
        if result['success']:
            return jsonify({
                'success': True,
                'data': result,
                'message': result['message'],
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Reload Failed',
                'message': result['message'],
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 500

    except Exception as e:
        current_app.logger.error(f"Failed to reload tasks: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Failed to reload tasks: {e}',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@tasks_blueprint.route('/presets', methods=['GET'])
@require_auth
def list_presets():
    """Get all task presets (built-in and user-defined)."""
    try:
        preset_service = TaskPresetService()
        presets = preset_service.list_presets()

        return jsonify({
            'success': True,
            'data': {
                'presets': presets,
                'total': len(presets)
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        current_app.logger.error(f"Failed to list presets: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Failed to list presets: {e}',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@tasks_blueprint.route('/presets', methods=['POST'])
@require_auth
def create_preset():
    """Create a new user-defined task preset."""
    try:
        if not request.is_json:
            raise ValidationError("Request must contain JSON data")

        data = request.get_json()

        # Validate required fields
        if not data.get('name', '').strip():
            raise ValidationError("Preset name is required")
        if not data.get('command'):
            raise ValidationError("Command is required")

        # Validate command type
        try:
            CommandType(data['command'])
        except ValueError:
            raise ValidationError(
                f"Invalid command type. Must be one of: {[c.value for c in CommandType]}"
            )

        # Validate command parameters if provided
        command_params = data.get('command_params', {})
        if command_params:
            command = CronCommand(data['command'], command_params)
            validation = command.validate()
            if not validation.valid:
                raise ValidationError(f"Invalid command parameters: {', '.join(validation.errors)}")

        # Validate default_time format if provided
        default_time = data.get('default_time')
        if default_time:
            try:
                hour, minute = default_time.split(':')
                if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
                    raise ValueError("Invalid time range")
            except (ValueError, IndexError):
                raise ValidationError("Invalid time format. Must be HH:MM")

        preset_service = TaskPresetService()
        preset_data = preset_service.create_preset(
            name=data['name'].strip(),
            command=data['command'],
            command_params=command_params,
            default_time=default_time,
            is_builtin=False,
            sort_order=100
        )

        return jsonify({
            'success': True,
            'data': preset_data,
            'message': 'Preset created successfully',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 201

    except ValidationError as e:
        return jsonify({
            'success': False,
            'error': 'Validation Error',
            'message': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 422

    except Exception as e:
        current_app.logger.error(f"Failed to create preset: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Failed to create preset: {e}',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@tasks_blueprint.route('/presets/<preset_id>', methods=['DELETE'])
@require_auth
def delete_preset(preset_id: str):
    """Delete a user-defined preset. Built-in presets cannot be deleted."""
    try:
        preset_service = TaskPresetService()
        preset_service.delete_preset(preset_id)

        return jsonify({
            'success': True,
            'message': 'Preset deleted successfully',
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    except PresetNotFoundError as e:
        return jsonify({
            'success': False,
            'error': 'Not Found',
            'message': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 404

    except DatabaseError as e:
        if "Built-in" in str(e):
            return jsonify({
                'success': False,
                'error': 'Forbidden',
                'message': str(e),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 403
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500

    except Exception as e:
        current_app.logger.error(f"Failed to delete preset: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Failed to delete preset: {e}',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


# Backwards compatibility: Keep old cronjobs endpoint accessible
cronjobs_blueprint = tasks_blueprint
