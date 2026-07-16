"""
PowerNight Logs API

REST API endpoints for task execution log management and viewing.
"""

import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from flask import Blueprint, request, jsonify, current_app

from ...utils.logging import get_logger, ComponentType, OperationType, LogLevel
from ...core.database.services import TaskExecutionService
from ...core.database.exceptions import DatabaseError
from .auth import require_auth

# Create blueprint
logs_blueprint = Blueprint('logs', __name__, url_prefix='/api/v1/logs')


# Task Execution Logs Endpoints

@logs_blueprint.route('/executions', methods=['GET'])
@require_auth
def get_task_execution_logs():
    """
    Get task execution logs with filtering and pagination.

    Query Parameters:
    - limit: Maximum number of logs to return (default: 100, max: 1000)
    - offset: Number of logs to skip (default: 0)
    - task_name: Filter by task name (partial match)
    - execution_type: Filter by execution type (scheduled, manual)
    - status: Filter by status (pending, running, success, error)
    - start_date: Filter logs after this timestamp (ISO format)
    - end_date: Filter logs before this timestamp (ISO format)
    """
    start_time = time.time()

    try:
        # Parse query parameters
        limit = min(int(request.args.get('limit', 100)), 1000)
        offset = int(request.args.get('offset', 0))
        task_name_filter = request.args.get('task_name', '').strip()
        execution_type_filter = request.args.get('execution_type')
        status_filter = request.args.get('status')
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')

        # Parse date filters
        start_date = None
        end_date = None

        if start_date_str:
            try:
                start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
            except ValueError:
                return jsonify({'error': 'Invalid start_date format. Use ISO format.'}), 400

        if end_date_str:
            try:
                end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
            except ValueError:
                return jsonify({'error': 'Invalid end_date format. Use ISO format.'}), 400

        # Get execution service
        execution_service = TaskExecutionService()

        # Get logs with filters
        result = execution_service.get_execution_logs(
            limit=limit,
            offset=offset,
            task_name_filter=task_name_filter if task_name_filter else None,
            execution_type_filter=execution_type_filter,
            status_filter=status_filter,
            start_date=start_date,
            end_date=end_date
        )

        duration_ms = (time.time() - start_time) * 1000

        # Log the API request
        logger = get_logger()
        logger.log_web_request(
            method='GET',
            path='/api/logs/executions',
            status_code=200,
            duration_ms=duration_ms
        )

        return jsonify({
            'success': True,
            'data': result,
            'filters': {
                'task_name': task_name_filter if task_name_filter else None,
                'execution_type': execution_type_filter,
                'status': status_filter,
                'start_date': start_date_str,
                'end_date': end_date_str,
                'limit': limit,
                'offset': offset
            },
            'response_time_ms': duration_ms,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        logger = get_logger()
        logger.log_error(
            ComponentType.WEB,
            "Failed to retrieve task execution logs",
            e,
            metadata={'endpoint': '/api/logs/executions'}
        )

        return jsonify({
            'success': False,
            'error': 'Failed to retrieve task execution logs',
            'message': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500