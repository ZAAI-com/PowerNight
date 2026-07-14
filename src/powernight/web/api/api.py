"""
PowerNight API Blueprint

REST API endpoints for configuration, control, and monitoring.
"""

from flask import Blueprint, jsonify, request, current_app
from datetime import datetime, timezone
import logging
import os

from ... import __version__
from ...core.config import get_config
from ...core.powerwall import get_powerwall_connector
from ...core.planner import get_planner
from ...utils.timezone_utils import format_datetime_for_display
from .auth import require_auth, get_current_user
from .errors import APIError, ValidationError, PowerwallError
from .schemas import get_schema_validator
from .monitoring import get_metrics_collector, performance_monitor


# Create API blueprint
api_blueprint = Blueprint('api', __name__)


@api_blueprint.route('/version-info.json', methods=['GET'])
def serve_version_info():
    """
    Serve version information JSON file generated during build.

    Tries to serve from dist/ (production) first, then falls back to
    project root (development) if not found.

    Returns:
        JSON file with version information or error message with 404 status
    """
    import json

    logger = logging.getLogger(__name__)
    static_folder = current_app.static_folder

    # Try production path first (dist/version-info.json)
    version_file_path = os.path.join(static_folder, 'version-info.json') if static_folder else None

    logger.debug(f"Looking for version-info.json in static_folder: {static_folder}")
    logger.debug(f"Full path: {version_file_path}")

    if version_file_path and os.path.exists(version_file_path):
        logger.info(f"Serving version-info.json from: {static_folder}")
        try:
            # Read and validate JSON before serving
            with open(version_file_path, 'r') as f:
                version_data = json.load(f)
            return jsonify(version_data), 200
        except Exception as e:
            logger.error(f"Error reading version-info.json: {e}")
            return jsonify({
                'error': 'Failed to read version information',
                'details': str(e)
            }), 500

    # Fallback to project root for development
    # This file: src/powernight/web/api/api.py
    # Target: version-info.json (at project root)
    api_dir = os.path.dirname(os.path.abspath(__file__))       # src/powernight/web/api
    web_dir = os.path.dirname(api_dir)                         # src/powernight/web
    powernight_dir = os.path.dirname(web_dir)                  # src/powernight
    src_dir = os.path.dirname(powernight_dir)                  # src
    project_root = os.path.dirname(src_dir)                    # project root
    fallback_path = os.path.join(project_root, 'version-info.json')

    logger.debug(f"Trying fallback path: {fallback_path}")
    logger.debug(f"Fallback file exists: {os.path.exists(fallback_path)}")

    if os.path.exists(fallback_path):
        logger.info(f"Serving version-info.json from project root: {fallback_path}")
        try:
            with open(fallback_path, 'r') as f:
                version_data = json.load(f)
            return jsonify(version_data), 200
        except Exception as e:
            logger.error(f"Error reading fallback version-info.json: {e}")
            return jsonify({
                'error': 'Failed to read version information',
                'details': str(e)
            }), 500

    # File not found in either location
    logger.warning("version-info.json not found in any expected location")
    return jsonify({
        'error': 'Version information not available',
        'message': 'Run ./build.sh to generate version-info.json',
        'searched_paths': [
            version_file_path if version_file_path else 'N/A (static_folder not set)',
            fallback_path
        ]
    }), 404




@api_blueprint.route('/test-connection', methods=['POST'])
@require_auth
def test_powerwall_connection():
    """
    Test Powerwall connection with provided credentials.
    
    Request Body:
        {
            "tesla_email": "user@example.com",
            "email": "user@example.com",  # Optional for Tesla auth
            "password": "password",
            "timeout": 30,
            "verify_ssl": false
        }
    
    Returns:
        JSON response with connection test result
    """
    try:
        data = request.get_json() or {}
        
        # Validate required fields
        if not data.get('tesla_email'):
            return jsonify({
                'success': False,
                'error': 'Missing Tesla email',
                'message': 'Tesla email is required for connection test',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 400
        
        # Get profile information from headers
        profile_id = request.headers.get('X-Powerwall-Profile', 'demo')
        
        # Check if this is demo mode (cloud mode only)
        is_demo_mode = profile_id == 'demo'
        is_gruber_eg = profile_id == 'gruber-eg'
        
        if is_demo_mode or is_gruber_eg:
            # Simulate connection test for demo mode
            powerwall_name = "Demo Powerwall" if is_demo_mode else "Gruber EG"
            
            # Simulate connection test for cloud mode
            test_email = data.get('tesla_email', 'user@example.com')
            
            return jsonify({
                'success': True,
                'data': {
                    'connected': True,
                    'tesla_email': test_email,
                    'powerwall_name': powerwall_name,
                    'response_time': '45ms',
                    'firmware_version': '23.12.1',
                    'serial_number': 'TG0123456789AB',
                    'status': 'online',
                    'connection_type': 'cloud'
                },
                'message': f'Successfully connected to {powerwall_name} via cloud',
                'demo_mode': is_demo_mode,
                'profile_id': profile_id,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        
        # For real Powerwall connections (not implemented yet)
        return jsonify({
            'success': False,
            'error': 'Not Implemented',
            'message': 'Real Powerwall connection testing not implemented yet',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 501
        
    except Exception as e:
        current_app.logger.error(f"Error testing Powerwall connection: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': 'Connection test failed',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500



# Backup reserve control endpoints
@api_blueprint.route('/backup-reserve', methods=['GET'])
@require_auth
def get_backup_reserve():
    """
    Get current Powerwall backup reserve percentage with enhanced monitoring.

    Query Parameters:
        include_history (bool): Include recent change history
        include_diagnostics (bool): Include Powerwall diagnostics

    Returns:
        JSON response with current backup reserve percentage and metadata
    """
    try:
        include_history = request.args.get('include_history', 'false').lower() == 'true'
        include_diagnostics = request.args.get('include_diagnostics', 'false').lower() == 'true'

        # Get profile information from headers
        profile_id = request.headers.get('X-Powerwall-Profile', 'demo')
                # Check if we're in demo mode (cloud mode only)
        config = get_config()
        
        # Check if this is the Gruber EG Powerwall first
        is_gruber_eg = profile_id == 'gruber-eg'
        
        # Check if we're in demo mode (cloud mode only, but not Gruber EG)
        is_demo_mode = profile_id == 'demo' and not is_gruber_eg
        
        if is_demo_mode or is_gruber_eg:
            # Return demo data instead of trying to connect
            backup_reserve = 20.0 if is_demo_mode else 35.0  # Different values for different Powerwalls
            powerwall_name = "Demo Powerwall" if is_demo_mode else "Gruber EG"
            
            return jsonify({
                'success': True,
                'data': {
                    'backup_reserve_percentage': backup_reserve,
                    'connected': False,
                    'demo_mode': is_demo_mode,
                    'message': f'Demo mode - using simulated data for {powerwall_name}' if is_demo_mode else f'Simulated data for {powerwall_name}',
                    'profile_id': profile_id,
                    'powerwall_name': powerwall_name,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            })

        # Get Powerwall connector
        powerwall = get_powerwall_connector()

        # Enhanced connection testing
        connection_start = datetime.now()
        is_connected = powerwall.is_connected()

        if not is_connected:
            current_app.logger.info("Powerwall not connected, attempting connection...")
            powerwall.test_connection()
            is_connected = powerwall.is_connected()

        connection_time = (datetime.now() - connection_start).total_seconds()

        # Get current backup reserve percentage
        current_percentage = powerwall.get_backup_reserve_percentage()

        response_data = {
            'current_percentage': current_percentage,
            'timestamp': format_datetime_for_display(datetime.now(timezone.utc)),
            'powerwall_connected': is_connected,
            'connection_time_seconds': round(connection_time, 3),
            'request_id': f"reserve_get_{int(datetime.now().timestamp())}",
            'user_id': get_current_user() or 'anonymous'
        }

        # Add diagnostics if requested
        if include_diagnostics:
            try:
                response_data['diagnostics'] = {
                    'cache_stats': powerwall.get_cache_stats() if hasattr(powerwall, 'get_cache_stats') else None,
                    'last_error': None  # Could be enhanced with error tracking
                }
            except Exception as diag_error:
                response_data['diagnostics'] = {
                    'error': f"Failed to get diagnostics: {diag_error}"
                }

        # Add change history if requested
        if include_history:
            # This could be enhanced with actual history tracking
            response_data['recent_changes'] = {
                'note': 'History tracking not yet implemented',
                'last_manual_change': None,
                'last_scheduled_change': None
            }

        return jsonify({
            'success': True,
            'data': response_data
        })

    except Exception as e:
        current_app.logger.error(f"Failed to get backup reserve: {e}")
        return jsonify({
            'success': False,
            'error': 'Powerwall Communication Error',
            'message': 'Failed to retrieve backup reserve percentage',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'request_id': f"reserve_get_error_{int(datetime.now().timestamp())}"
        }), 502


@api_blueprint.route('/backup-reserve', methods=['POST'])
@require_auth
def set_backup_reserve():
    """
    Set Powerwall backup reserve percentage with enterprise-grade validation and audit.

    Request Body:
        {
            "percentage": 0-100,
            "reason": "Optional reason for change",
            "force": false
        }

    Query Parameters:
        dry_run (bool): Validate request without applying changes

    Returns:
        JSON response with operation result and detailed metadata
    """
    try:
        # Check if we're in demo mode (demo IP address)
        config = get_config()
        is_demo_mode = config.powerwall.tesla_email in ['demo@example.com', 'user@example.com']
        
        if is_demo_mode:
            # Return demo response instead of trying to connect
            try:
                data = request.get_json() or {}
                percentage = data.get('percentage', 0)
                reason = data.get('reason', 'Demo mode change')
                
                return jsonify({
                    'success': True,
                    'data': {
                        'backup_reserve_percentage': percentage,
                        'connected': False,
                        'demo_mode': True,
                        'message': f'Demo mode - simulated change to {percentage}%',
                        'reason': reason,
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': 'Invalid request',
                    'message': str(e),
                    'demo_mode': True,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })

        # Parse request parameters
        dry_run = request.args.get('dry_run', 'false').lower() == 'true'

        # Validate request data
        if not request.is_json:
            raise ValidationError("Request must contain JSON data with Content-Type: application/json")

        try:
            data = request.get_json()
        except Exception:
            return jsonify({
                'success': False,
                'error': 'Invalid JSON',
                'message': 'Request body must contain valid JSON',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 422
        if not data:
            raise ValidationError("Request body cannot be empty")

        # Use enterprise validation
        validator = get_schema_validator()
        validation_result = validator.validate_backup_reserve(data)

        if not validation_result.is_valid:
            return jsonify({
                'success': False,
                'error': 'Validation Error',
                'validation': validation_result.to_dict(),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 422

        # Extract validated data
        sanitized_data = validation_result.sanitized_data
        target_percentage = sanitized_data['percentage']
        reason = sanitized_data.get('reason', 'Manual API change')
        force_change = sanitized_data.get('force', False)

        # Get request metadata
        user_id = get_current_user() or 'anonymous'
        client_ip = request.remote_addr
        user_agent = request.headers.get('User-Agent', 'Unknown')
        request_id = f"reserve_set_{int(datetime.now().timestamp())}"

        # Start operation timing
        operation_start = datetime.now()

        if dry_run:
            return jsonify({
                'success': True,
                'dry_run': True,
                'validation': validation_result.to_dict(),
                'target_percentage': target_percentage,
                'request_metadata': {
                    'request_id': request_id,
                    'user_id': user_id,
                    'client_ip': client_ip,
                    'reason': reason
                },
                'timestamp': datetime.now(timezone.utc).isoformat()
            })

        # Get Powerwall connector with enhanced error handling
        try:
            powerwall = get_powerwall_connector()
        except Exception as e:
            current_app.logger.error(f"Failed to get Powerwall connector: {e}")
            return jsonify({
                'success': False,
                'error': 'Powerwall Configuration Error',
                'message': 'Failed to connect to Powerwall',
                'request_id': request_id,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 502

        # Test connection if needed
        is_connected = powerwall.is_connected()

        if not is_connected:
            current_app.logger.info("Powerwall not connected, attempting connection...")
            try:
                powerwall.test_connection()
                is_connected = powerwall.is_connected()
            except Exception as e:
                if not force_change:
                    return jsonify({
                        'success': False,
                        'error': 'Powerwall Connection Error',
                        'message': f'Cannot connect to Powerwall: {e}. Use force=true to override.',
                        'request_id': request_id,
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }), 502

        # Set backup reserve percentage (fast mode - no verification)
        try:
            current_app.logger.info(f"Setting backup reserve to {target_percentage}%")
            result = powerwall.set_backup_reserve_percentage(target_percentage, reason=reason)
        except Exception as e:
            current_app.logger.error(f"Failed to set backup reserve: {e}")
            return jsonify({
                'success': False,
                'error': 'Powerwall Write Error',
                'message': 'Failed to set backup reserve',
                'request_id': request_id,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 502

        total_operation_time = (datetime.now() - operation_start).total_seconds()

        # Log the operation
        current_app.logger.info(
            f"Backup reserve set to {target_percentage}% "
            f"(user: {user_id}, reason: {reason}, duration: {total_operation_time:.2f}s)"
        )

        # Prepare response
        response_data = {
            'success': True,
            'data': {
                'target_percentage': target_percentage,
                'actual_percentage': target_percentage,  # Trust result
                'change_applied': True,
                'timestamp': format_datetime_for_display(datetime.now(timezone.utc))
            },
            'metadata': {
                'request_id': request_id,
                'user_id': user_id,
                'client_ip': client_ip,
                'reason': reason,
                'operation_time_seconds': round(total_operation_time, 3)
            },
            'timestamp': format_datetime_for_display(datetime.now(timezone.utc))
        }

        return jsonify(response_data), 200

    except ValidationError as e:
        current_app.logger.warning(f"Backup reserve validation failed: {e}")
        return jsonify({
            'success': False,
            'error': 'Validation Error',
            'message': str(e),
            'details': getattr(e, 'details', {}),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 422

    except Exception as e:
        current_app.logger.error(f"Backup reserve operation failed: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Backup reserve operation failed: {e}',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


# Status and monitoring endpoints
@api_blueprint.route('/status', methods=['GET'])
@require_auth
def get_system_status():
    """
    Get comprehensive system status.

    Returns:
        JSON response with system status information
    """
    try:
        # Get profile information from headers
        profile_id = request.headers.get('X-Powerwall-Profile', 'demo')
        powerwall_email = request.headers.get('X-Powerwall-Email')
        
        # Check if this is the Gruber EG Powerwall
        is_gruber_eg = profile_id == 'gruber-eg'
        powerwall_name = "Demo Powerwall" if profile_id == 'demo' else "Gruber EG" if is_gruber_eg else "Unknown"
        
        # Determine backup reserve percentage based on profile
        backup_reserve = None
        if profile_id == 'demo':
            backup_reserve = 20.0
        elif is_gruber_eg:
            backup_reserve = 35.0
        
        status_data = {
            'timestamp': format_datetime_for_display(datetime.now(timezone.utc)),
            'system': {
                'healthy': True,
                'version': __version__,
                'active_profile': profile_id
            },
            'powerwall': {
                'connected': False,
                'backup_reserve_percentage': backup_reserve,
                'last_communication': None,
                'error': None,
                'profile_id': profile_id,
                'tesla_email': powerwall_email,
                'email': powerwall_email,
                'name': powerwall_name
            },
            'scheduler': {
                'running': False,
                'job_count': 0,
                'next_run': None,
                'last_execution': None
            },
            'configuration': {
                'loaded': True,
                'automation_enabled': False
            }
        }

        # Get Powerwall status
        try:
            config = get_config()
            status_data['configuration'].update({
                'automation_enabled': config.automation.enabled
            })

            if config.powerwall.tesla_email:
                powerwall = get_powerwall_connector()

                try:
                    is_connected = powerwall.is_connected()
                    status_data['powerwall']['connected'] = is_connected

                    if is_connected:
                        backup_percentage = powerwall.get_backup_reserve_percentage()
                        status_data['powerwall']['backup_reserve_percentage'] = backup_percentage
                        status_data['powerwall']['last_communication'] = datetime.now(timezone.utc).isoformat()

                except Exception as e:
                    status_data['powerwall']['error'] = str(e)
                    status_data['system']['healthy'] = False

        except Exception as e:
            status_data['configuration']['loaded'] = False
            status_data['configuration']['error'] = str(e)
            status_data['system']['healthy'] = False

        # Get planner status
        try:
            planner = get_planner()
            planner_status = planner.get_status()

            status_data['scheduler'].update({
                'running': planner_status['is_running'],
                'job_count': planner_status['task_count'],
                'next_run': planner_status.get('next_run'),
                'enabled_jobs': planner_status.get('task_count', 0),
                'disabled_jobs': 0
            })

        except Exception as e:
            status_data['scheduler']['error'] = str(e)

        return jsonify({
            'success': True,
            'data': status_data
        })

    except Exception as e:
        current_app.logger.error(f"Failed to get system status: {e}")
        raise APIError("Failed to retrieve system status", status_code=500)


# Logs endpoint moved to logs_blueprint (/api/v1/logs)
# This placeholder was causing conflicts with the real implementation


# Performance monitoring and metrics endpoints
@api_blueprint.route('/metrics', methods=['GET'])
@require_auth
@performance_monitor('api.metrics.get')
def get_metrics():
    """
    Get application performance metrics and analytics.

    Query Parameters:
        time_window (int): Time window in hours for metrics (default: 1, max: 24)
        format (str): Export format ('json', 'prometheus')
        include_system (bool): Include system metrics
        include_requests (bool): Include request analytics

    Returns:
        JSON response with metrics data or Prometheus format
    """
    try:
        # Parse query parameters
        time_window_hours = min(int(request.args.get('time_window', 1)), 24)
        export_format = request.args.get('format', 'json').lower()
        include_system = request.args.get('include_system', 'true').lower() == 'true'
        include_requests = request.args.get('include_requests', 'true').lower() == 'true'

        from datetime import timedelta
        time_window = timedelta(hours=time_window_hours)

        # Get metrics collector
        collector = get_metrics_collector()

        if export_format == 'prometheus':
            # Return Prometheus format
            prometheus_data = collector.export_metrics('prometheus', time_window)
            return prometheus_data, 200, {'Content-Type': 'text/plain; version=0.0.4; charset=utf-8'}

        # JSON format response
        response_data = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'time_window_hours': time_window_hours,
            'metrics_summary': {}
        }

        # System metrics
        if include_system:
            try:
                current_system = collector.collect_system_metrics()
                response_data['current_system'] = current_system.to_dict()

                # System metrics summaries
                system_summaries = {}
                for metric in ['system_cpu_percent', 'system_memory_percent', 'system_disk_percent']:
                    summary = collector.get_metrics_summary(metric, time_window)
                    if 'error' not in summary:
                        system_summaries[metric] = summary

                response_data['system_metrics_summary'] = system_summaries

            except Exception as e:
                response_data['system_metrics_error'] = str(e)

        # Request analytics
        if include_requests:
            try:
                request_analytics = collector.get_request_analytics(time_window)
                response_data['request_analytics'] = request_analytics
            except Exception as e:
                response_data['request_analytics_error'] = str(e)

        # Performance metrics summaries
        performance_summaries = {}
        for metric in ['function_duration_ms', 'http_requests_total', 'http_request_duration_ms']:
            summary = collector.get_metrics_summary(metric, time_window)
            if 'error' not in summary:
                performance_summaries[metric] = summary

        response_data['performance_summary'] = performance_summaries

        # Current alerts
        response_data['current_alerts'] = collector.get_current_alerts()

        return jsonify({
            'success': True,
            'data': response_data
        })

    except Exception as e:
        current_app.logger.error(f"Failed to get metrics: {e}")
        raise APIError("Failed to retrieve metrics", status_code=500)



@api_blueprint.route('/health', methods=['GET'])
@performance_monitor('api.health.check')
def health_check():
    """
    Lightweight health check endpoint for monitoring systems.

    Returns:
        JSON response with basic health status
    """
    try:
        # Quick health checks
        health_data = {
            'status': 'healthy',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'version': __version__,
            'uptime_seconds': 0
        }

        # Calculate uptime
        try:
            collector = get_metrics_collector()
            if hasattr(collector, 'start_time'):
                uptime = (datetime.now() - collector.start_time).total_seconds()
                health_data['uptime_seconds'] = round(uptime, 2)
        except Exception:
            pass

        # Basic system checks
        checks = {
            'configuration': False,
            'powerwall': False,
            'scheduler': False
        }

        # Configuration check
        try:
            config = get_config()
            checks['configuration'] = True
        except Exception:
            health_data['status'] = 'degraded'

        # Powerwall check (quick)
        try:
            if checks['configuration']:
                powerwall = get_powerwall_connector()
                checks['powerwall'] = powerwall.is_connected()
        except Exception:
            pass

        # Planner check
        try:
            planner = get_planner()
            planner_status = planner.get_status()
            checks['scheduler'] = planner_status.get('is_running', False)
        except Exception:
            pass

        health_data['checks'] = checks

        # Determine overall status
        if not any(checks.values()):
            health_data['status'] = 'unhealthy'
        elif not all(checks.values()):
            health_data['status'] = 'degraded'

        status_code = 200 if health_data['status'] == 'healthy' else 503

        return jsonify(health_data), status_code

    except Exception as e:
        current_app.logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': 'Internal server error',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 503



# Error handlers for this blueprint
@api_blueprint.errorhandler(ValidationError)
def handle_validation_error(error):
    """Handle validation errors."""
    response_data = {
        'success': False,
        'error': 'Validation Error',
        'message': str(error),
        'timestamp': datetime.now(timezone.utc).isoformat()
    }

    if hasattr(error, 'details') and error.details:
        response_data['details'] = error.details

    return jsonify(response_data), error.status_code


@api_blueprint.errorhandler(PowerwallError)
def handle_powerwall_error(error):
    """Handle Powerwall-related errors."""
    return jsonify({
        'success': False,
        'error': 'Powerwall Error',
        'message': str(error),
        'timestamp': datetime.now(timezone.utc).isoformat()
    }), error.status_code


@api_blueprint.errorhandler(APIError)
def handle_api_error(error):
    """Handle general API errors."""
    return jsonify({
        'success': False,
        'error': 'API Error',
        'message': str(error),
        'timestamp': datetime.now(timezone.utc).isoformat()
    }), error.status_code
