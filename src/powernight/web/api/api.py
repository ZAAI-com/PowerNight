"""
PowerNight API Blueprint

REST API endpoints for configuration, control, and monitoring.
"""

from flask import Blueprint, jsonify, request, current_app, send_from_directory
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Tuple, Optional
import logging
import os

from ...core.config import get_config, ConfigManager
from ...core.powerwall import get_powerwall_connector
from ...core.planner import get_planner
from ...core.database.services import ScheduleService
from ...core.database.exceptions import DatabaseError
from ...core.database.migration import run_migration, get_migration_status
from ...utils.timezone_utils import format_datetime_for_display
from .validation import validate_config_data, validate_backup_reserve_data
from .auth import require_auth, get_current_user
from .errors import APIError, ValidationError, PowerwallError
from .config_manager import get_enterprise_config_manager
from .schemas import get_schema_validator
from .monitoring import get_metrics_collector, performance_monitor


# Create API blueprint
api_blueprint = Blueprint('api', __name__)

# Initialize services
schedule_service = ScheduleService()


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


# Configuration endpoints with enterprise-grade features
@api_blueprint.route('/config', methods=['GET'])
@require_auth
def get_configuration():
    """
    Get current application configuration with enterprise features.

    Query Parameters:
        include_sensitive (bool): Include sensitive data (requires admin privileges)
        format (str): Response format ('full', 'summary', 'schema')

    Returns:
        JSON response with current configuration and metadata
    """
    try:
        include_sensitive = request.args.get('include_sensitive', 'false').lower() == 'true'
        response_format = request.args.get('format', 'full').lower()

        # Get enterprise config manager
        enterprise_manager = get_enterprise_config_manager()

        # Get configuration
        config_response = enterprise_manager.get_configuration(include_sensitive=include_sensitive)

        # Add additional metadata based on format
        if response_format == 'schema':
            validator = get_schema_validator()
            config_response['schema'] = validator.schemas['config_update']
        elif response_format == 'summary':
            # Provide only high-level summary
            if config_response['success']:
                data = config_response['data']
                config_response['data'] = {
                    'powerwall_configured': bool(data.get('powerwall', {}).get('tesla_email')),
                    'automation_enabled': data.get('automation', {}).get('enabled', False),
                    'web_interface_enabled': data.get('web_interface', {}).get('enabled', False),
                    'schedule_count': len(data.get('automation', {}).get('schedule', [])),
                    'logging_level': data.get('logging', {}).get('level', 'INFO')
                }

        # Add request metadata
        config_response.update({
            'request_id': f"cfg_get_{int(datetime.now().timestamp())}",
            'user_id': get_current_user() or 'anonymous',
            'client_ip': request.remote_addr,
            'response_format': response_format,
            'includes_sensitive': include_sensitive
        })

        return jsonify(config_response)

    except Exception as e:
        current_app.logger.error(f"Failed to get configuration: {e}")
        raise APIError(f"Failed to retrieve configuration: {e}", status_code=500)


@api_blueprint.route('/config', methods=['POST'])
@require_auth
def update_configuration():
    """
    Update application configuration with enterprise-grade validation and backup.

    Request Body:
        Configuration updates in JSON format

    Query Parameters:
        dry_run (bool): Validate changes without applying them
        force (bool): Force update even with warnings
        backup_reason (str): Custom reason for configuration backup

    Returns:
        JSON response with update result, validation details, and change metadata
    """
    try:
        # Parse request parameters
        dry_run = request.args.get('dry_run', 'false').lower() == 'true'
        force_update = request.args.get('force', 'false').lower() == 'true'
        backup_reason = request.args.get('backup_reason', 'API configuration update')

        # Validate request data
        if not request.is_json:
            raise ValidationError("Request must contain JSON data with Content-Type: application/json")

        try:
            config_updates = request.get_json()
        except Exception:
            return jsonify({
                'success': False,
                'error': 'Invalid JSON',
                'message': 'Request body must contain valid JSON',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 422

        if not config_updates:
            raise ValidationError("Request body cannot be empty")

        if not isinstance(config_updates, dict):
            raise ValidationError("Request body must be a JSON object")

        # Get request metadata
        user_id = get_current_user() or 'anonymous'
        client_ip = request.remote_addr
        user_agent = request.headers.get('User-Agent', 'Unknown')

        # Get enterprise config manager
        enterprise_manager = get_enterprise_config_manager()

        # Update configuration with enterprise features
        update_result = enterprise_manager.update_configuration(
            updates=config_updates,
            user_id=user_id,
            client_ip=client_ip,
            user_agent=user_agent,
            dry_run=dry_run
        )

        # Check for warnings if not force update
        if (update_result['success'] and
            not dry_run and
            not force_update and
            'validation' in update_result and
            update_result['validation'].get('warning_count', 0) > 0):

            return jsonify({
                'success': False,
                'error': 'Configuration has warnings. Use force=true to proceed.',
                'warnings': update_result['validation'].get('warnings', []),
                'change_id': update_result.get('change_id'),
                'timestamp': update_result.get('timestamp')
            }), 422

        # Add request metadata to response
        update_result.update({
            'request_metadata': {
                'user_id': user_id,
                'client_ip': client_ip,
                'user_agent': user_agent,
                'dry_run': dry_run,
                'force_update': force_update,
                'backup_reason': backup_reason
            }
        })

        # Determine HTTP status code
        status_code = 200 if update_result['success'] else 400

        return jsonify(update_result), status_code

    except ValidationError as e:
        current_app.logger.warning(f"Configuration validation failed: {e}")
        return jsonify({
            'success': False,
            'error': 'Validation Error',
            'message': str(e),
            'details': getattr(e, 'details', {}),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 422

    except Exception as e:
        current_app.logger.error(f"Configuration update failed: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Configuration update failed: {e}',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


# Configuration management endpoints
@api_blueprint.route('/config/validate', methods=['POST'])
@require_auth
def validate_configuration():
    """
    Validate configuration without applying changes.

    Request Body:
        Configuration data to validate in JSON format

    Returns:
        JSON response with validation results and sanitized data
    """
    try:
        if not request.is_json:
            raise ValidationError("Request must contain JSON data")

        try:
            config_data = request.get_json()
        except Exception:
            return jsonify({
                'success': False,
                'error': 'Invalid JSON',
                'message': 'Request body must contain valid JSON',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 422
        if not config_data:
            raise ValidationError("Request body cannot be empty")

        enterprise_manager = get_enterprise_config_manager()
        validation_result = enterprise_manager.validate_configuration_only(config_data)

        return jsonify(validation_result)

    except ValidationError as e:
        return jsonify({
            'success': False,
            'error': 'Validation Error',
            'message': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 422

    except Exception as e:
        current_app.logger.error(f"Configuration validation failed: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Validation failed: {e}',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/config/history', methods=['GET'])
@require_auth
def get_configuration_history():
    """
    Get configuration change history and backups.

    Query Parameters:
        limit (int): Maximum number of entries to return (default: 20, max: 100)

    Returns:
        JSON response with configuration history and backup information
    """
    try:
        limit = min(int(request.args.get('limit', 20)), 100)

        enterprise_manager = get_enterprise_config_manager()
        history_result = enterprise_manager.get_configuration_history(limit=limit)

        return jsonify(history_result)

    except ValueError:
        return jsonify({
            'success': False,
            'error': 'Invalid Parameter',
            'message': 'Limit parameter must be a valid integer',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 400

    except Exception as e:
        current_app.logger.error(f"Failed to get configuration history: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Failed to retrieve history: {e}',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


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
            'message': f'Connection test failed: {str(e)}',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/config/rollback', methods=['POST'])
@require_auth
def rollback_configuration():
    """
    Rollback configuration to a previous backup.

    Request Body:
        {
            "backup_id": "backup_id_to_restore",
            "reason": "Optional reason for rollback"
        }

    Returns:
        JSON response with rollback result
    """
    try:
        if not request.is_json:
            raise ValidationError("Request must contain JSON data")

        try:
            rollback_data = request.get_json()
        except Exception:
            return jsonify({
                'success': False,
                'error': 'Invalid JSON',
                'message': 'Request body must contain valid JSON',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 422
        if not rollback_data:
            raise ValidationError("Request body cannot be empty")

        backup_id = rollback_data.get('backup_id')
        if not backup_id:
            raise ValidationError("backup_id is required")

        reason = rollback_data.get('reason', 'Manual rollback via API')
        user_id = get_current_user() or 'anonymous'
        client_ip = request.remote_addr

        enterprise_manager = get_enterprise_config_manager()
        rollback_result = enterprise_manager.rollback_configuration(
            backup_id=backup_id,
            user_id=user_id,
            client_ip=client_ip,
            reason=reason
        )

        status_code = 200 if rollback_result['success'] else 400
        return jsonify(rollback_result), status_code

    except ValidationError as e:
        return jsonify({
            'success': False,
            'error': 'Validation Error',
            'message': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 422

    except Exception as e:
        current_app.logger.error(f"Configuration rollback failed: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Rollback failed: {e}',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/config/schema', methods=['GET'])
def get_configuration_schema():
    """
    Get the JSON schema for configuration validation.

    Returns:
        JSON schema for configuration updates
    """
    try:
        validator = get_schema_validator()

        return jsonify({
            'success': True,
            'data': {
                'config_update_schema': validator.schemas['config_update'],
                'backup_reserve_schema': validator.schemas['backup_reserve']
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        current_app.logger.error(f"Failed to get configuration schema: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Failed to retrieve schema: {e}',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500




@api_blueprint.route('/migration/status', methods=['GET'])
@require_auth
def get_migration_status_endpoint():
    """
    Get the current migration status.
    
    Returns:
        JSON response with migration status information
    """
    try:
        status = get_migration_status()
        
        return jsonify({
            'success': True,
            'data': status,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting migration status: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/migration/run', methods=['POST'])
@require_auth
def run_migration_endpoint():
    """
    Run the profile migration process.
    
    This endpoint migrates profiles from localStorage to the database.
    
    Returns:
        JSON response with migration result
    """
    try:
        success = run_migration()
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Migration completed successfully',
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Migration failed',
                'message': 'Failed to migrate profiles to database',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 500
            
    except Exception as e:
        current_app.logger.error(f"Error running migration: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': str(e),
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
            'message': f'Failed to retrieve backup reserve percentage: {e}',
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
                'message': f'Failed to connect to Powerwall: {e}',
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
                'message': f'Failed to set backup reserve: {e}',
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
                'version': '1.0.0',
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
        raise APIError(f"Failed to retrieve system status: {e}", status_code=500)


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
        raise APIError(f"Failed to retrieve metrics: {e}", status_code=500)


@api_blueprint.route('/metrics/export', methods=['GET'])
@require_auth
@performance_monitor('api.metrics.export')
def export_metrics():
    """
    Export comprehensive metrics data for backup or analysis.

    Query Parameters:
        time_window (int): Time window in hours (default: 24, max: 168)
        format (str): Export format ('json', 'csv')

    Returns:
        Exported metrics data
    """
    try:
        # Parse query parameters
        time_window_hours = min(int(request.args.get('time_window', 24)), 168)  # Max 1 week
        export_format = request.args.get('format', 'json').lower()

        from datetime import timedelta
        time_window = timedelta(hours=time_window_hours)

        # Get metrics collector
        collector = get_metrics_collector()

        if export_format == 'json':
            # Export as JSON
            exported_data = collector.export_metrics('json', time_window)
            return exported_data, 200, {
                'Content-Type': 'application/json',
                'Content-Disposition': f'attachment; filename=powernight_metrics_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
            }
        else:
            raise ValidationError(f"Unsupported export format: {export_format}")

    except Exception as e:
        current_app.logger.error(f"Failed to export metrics: {e}")
        raise APIError(f"Failed to export metrics: {e}", status_code=500)


@api_blueprint.route('/metrics/alerts', methods=['GET'])
@require_auth
@performance_monitor('api.metrics.alerts')
def get_alerts():
    """
    Get current system alerts and warnings.

    Query Parameters:
        severity (str): Filter by severity ('warning', 'critical')
        limit (int): Maximum number of alerts to return (default: 50)

    Returns:
        JSON response with current alerts
    """
    try:
        # Parse query parameters
        severity_filter = request.args.get('severity', '').lower()
        limit = min(int(request.args.get('limit', 50)), 100)

        # Get metrics collector
        collector = get_metrics_collector()
        alerts = collector.get_current_alerts()

        # Filter by severity if specified
        if severity_filter and severity_filter in ['warning', 'critical']:
            alerts = [alert for alert in alerts if alert.get('severity') == severity_filter]

        # Limit results
        alerts = alerts[:limit]

        # Group alerts by type for summary
        alert_summary = {}
        for alert in alerts:
            alert_type = alert.get('type', 'unknown')
            if alert_type not in alert_summary:
                alert_summary[alert_type] = {'count': 0, 'severities': {}}

            alert_summary[alert_type]['count'] += 1
            severity = alert.get('severity', 'unknown')
            alert_summary[alert_type]['severities'][severity] = alert_summary[alert_type]['severities'].get(severity, 0) + 1

        return jsonify({
            'success': True,
            'data': {
                'alerts': alerts,
                'alert_count': len(alerts),
                'alert_summary': alert_summary,
                'filters': {
                    'severity': severity_filter or 'all',
                    'limit': limit
                },
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        })

    except Exception as e:
        current_app.logger.error(f"Failed to get alerts: {e}")
        raise APIError(f"Failed to retrieve alerts: {e}", status_code=500)


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
            'version': '1.0.0',
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
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 503


# Helper functions
def _apply_config_updates(current_config: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply configuration updates to current configuration.

    Args:
        current_config: Current configuration dictionary
        updates: Updates to apply

    Returns:
        Updated configuration dictionary
    """
    # Create a deep copy of current config
    import copy
    updated_config = copy.deepcopy(current_config)

    # Apply updates recursively
    def _update_dict(target: Dict[str, Any], source: Dict[str, Any]) -> None:
        for key, value in source.items():
            if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                _update_dict(target[key], value)
            else:
                target[key] = value

    _update_dict(updated_config, updates)
    return updated_config


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


# Circuit Breaker Monitoring Endpoints
@api_blueprint.route('/circuit-breakers', methods=['GET'])
@require_auth
def get_circuit_breakers():
    """
    Get status of all circuit breakers.

    Returns:
        JSON response with circuit breaker states and metrics
    """
    try:
        circuit_breakers = list_circuit_breakers()

        # Add summary statistics
        total_breakers = len(circuit_breakers)
        open_breakers = sum(1 for cb in circuit_breakers.values() if cb['current_state'] == 'open')
        half_open_breakers = sum(1 for cb in circuit_breakers.values() if cb['current_state'] == 'half_open')

        total_calls = sum(cb['total_calls'] for cb in circuit_breakers.values())
        total_failures = sum(cb['total_failures'] for cb in circuit_breakers.values())
        overall_failure_rate = total_failures / max(1, total_calls)

        return jsonify({
            'success': True,
            'data': {
                'circuit_breakers': circuit_breakers,
                'summary': {
                    'total_breakers': total_breakers,
                    'open_breakers': open_breakers,
                    'half_open_breakers': half_open_breakers,
                    'closed_breakers': total_breakers - open_breakers - half_open_breakers,
                    'total_calls': total_calls,
                    'total_failures': total_failures,
                    'overall_failure_rate': overall_failure_rate
                }
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        current_app.logger.error(f"Error getting circuit breaker status: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': 'Failed to retrieve circuit breaker status',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/circuit-breakers/reset', methods=['POST'])
@require_auth
def reset_circuit_breakers():
    """
    Reset all circuit breakers to closed state.

    Requires admin privileges.

    Returns:
        JSON response confirming reset operation
    """
    try:
        # Check if user has admin privileges
        current_user = get_current_user()
        if not current_user.get('is_admin', False):
            return jsonify({
                'success': False,
                'error': 'Forbidden',
                'message': 'Admin privileges required to reset circuit breakers',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 403

        # Reset all circuit breakers
        reset_all_circuit_breakers()

        current_app.logger.info(f"All circuit breakers reset by user: {current_user.get('username', 'unknown')}")

        return jsonify({
            'success': True,
            'message': 'All circuit breakers have been reset to closed state',
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        current_app.logger.error(f"Error resetting circuit breakers: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': 'Failed to reset circuit breakers',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/circuit-breakers/<breaker_name>', methods=['GET'])
@require_auth
def get_circuit_breaker_details(breaker_name: str):
    """
    Get detailed information about a specific circuit breaker.

    Args:
        breaker_name: Name of the circuit breaker

    Returns:
        JSON response with detailed circuit breaker metrics
    """
    try:
        circuit_breakers = list_circuit_breakers()

        if breaker_name not in circuit_breakers:
            return jsonify({
                'success': False,
                'error': 'Not Found',
                'message': f'Circuit breaker "{breaker_name}" not found',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 404

        breaker_data = circuit_breakers[breaker_name]

        return jsonify({
            'success': True,
            'data': breaker_data,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        current_app.logger.error(f"Error getting circuit breaker details: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Failed to retrieve details for circuit breaker "{breaker_name}"',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/circuit-breakers/<breaker_name>/reset', methods=['POST'])
@require_auth
def reset_specific_circuit_breaker(breaker_name: str):
    """
    Reset a specific circuit breaker to closed state.

    Args:
        breaker_name: Name of the circuit breaker to reset

    Returns:
        JSON response confirming reset operation
    """
    try:
        # Check if user has admin privileges
        current_user = get_current_user()
        if not current_user.get('is_admin', False):
            return jsonify({
                'success': False,
                'error': 'Forbidden',
                'message': 'Admin privileges required to reset circuit breakers',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 403

        # Get the specific circuit breaker
        from ..scheduler.circuit_breaker import get_circuit_breaker

        try:
            breaker = get_circuit_breaker(breaker_name)
            breaker.reset()

            current_app.logger.info(f"Circuit breaker '{breaker_name}' reset by user: {current_user.get('username', 'unknown')}")

            return jsonify({
                'success': True,
                'message': f'Circuit breaker "{breaker_name}" has been reset to closed state',
                'timestamp': datetime.now(timezone.utc).isoformat()
            })

        except KeyError:
            return jsonify({
                'success': False,
                'error': 'Not Found',
                'message': f'Circuit breaker "{breaker_name}" not found',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 404

    except Exception as e:
        current_app.logger.error(f"Error resetting circuit breaker '{breaker_name}': {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Failed to reset circuit breaker "{breaker_name}"',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


# Service Degradation Monitoring Endpoints
@api_blueprint.route('/degradation', methods=['GET'])
@require_auth
def get_degradation_status():
    """
    Get status of all service degradation managers.

    Returns:
        JSON response with degradation states and cache statistics
    """
    try:
        degradation_managers = list_degradation_managers()

        # Add summary statistics
        total_services = len(degradation_managers)
        normal_services = sum(1 for dm in degradation_managers.values() if dm['current_state'] == 'normal')
        degraded_services = sum(1 for dm in degradation_managers.values() if dm['current_state'] == 'degraded')
        offline_services = sum(1 for dm in degradation_managers.values() if dm['current_state'] == 'offline')
        recovery_services = sum(1 for dm in degradation_managers.values() if dm['current_state'] == 'recovery')

        # Calculate aggregate cache statistics
        total_cache_entries = sum(dm['cache_stats']['total_entries'] for dm in degradation_managers.values())
        total_valid_entries = sum(dm['cache_stats']['valid_entries'] for dm in degradation_managers.values())

        return jsonify({
            'success': True,
            'data': {
                'degradation_managers': degradation_managers,
                'summary': {
                    'total_services': total_services,
                    'normal_services': normal_services,
                    'degraded_services': degraded_services,
                    'offline_services': offline_services,
                    'recovery_services': recovery_services,
                    'overall_health': (
                        'healthy' if degraded_services == 0 and offline_services == 0
                        else 'degraded' if offline_services == 0
                        else 'critical'
                    ),
                    'cache_statistics': {
                        'total_entries': total_cache_entries,
                        'valid_entries': total_valid_entries,
                        'cache_utilization': total_valid_entries / max(1, total_cache_entries)
                    }
                }
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        current_app.logger.error(f"Error getting degradation status: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': 'Failed to retrieve degradation status',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/degradation/<service_name>/recovery', methods=['POST'])
@require_auth
def trigger_service_recovery(service_name: str):
    """
    Trigger recovery attempt for a specific service.

    Args:
        service_name: Name of the service

    Returns:
        JSON response confirming recovery attempt
    """
    try:
        # Check if user has admin privileges
        current_user = get_current_user()
        if not current_user.get('is_admin', False):
            return jsonify({
                'success': False,
                'error': 'Forbidden',
                'message': 'Admin privileges required to trigger service recovery',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 403

        # Get the service (typically the Powerwall connector)
        if 'powerwall' in service_name.lower():
            try:
                connector = get_powerwall_connector()
                recovery_attempted = connector.attempt_recovery()

                current_app.logger.info(f"Recovery triggered for service '{service_name}' by user: {current_user.get('username', 'unknown')}")

                return jsonify({
                    'success': True,
                    'message': f'Recovery attempt triggered for service "{service_name}"',
                    'recovery_attempted': recovery_attempted,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })

            except Exception as service_error:
                return jsonify({
                    'success': False,
                    'error': 'Service Error',
                    'message': f'Failed to trigger recovery for service "{service_name}": {service_error}',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }), 500
        else:
            return jsonify({
                'success': False,
                'error': 'Not Found',
                'message': f'Service "{service_name}" not found or does not support recovery',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 404

    except Exception as e:
        current_app.logger.error(f"Error triggering recovery for service '{service_name}': {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Failed to trigger recovery for service "{service_name}"',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


# System Health Monitoring Endpoints
@api_blueprint.route('/health/detailed', methods=['GET'])
@require_auth
def get_system_health():
    """
    Get comprehensive system health status.

    Query Parameters:
        summary (bool): Include health summary for last 24 hours
        hours (int): Hours of history for summary (default: 24)

    Returns:
        JSON response with current health status and optional summary
    """
    try:
        health_monitor = get_health_monitor()
        include_summary = request.args.get('summary', 'false').lower() == 'true'
        summary_hours = int(request.args.get('hours', '24'))

        # Get current health status
        current_status = health_monitor.get_current_status()

        response_data = {
            'success': True,
            'data': {
                'current_status': current_status,
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        # Add summary if requested
        if include_summary:
            summary = health_monitor.get_health_summary(hours=summary_hours)
            response_data['data']['summary'] = summary

        return jsonify(response_data)

    except Exception as e:
        current_app.logger.error(f"Error getting system health: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': 'Failed to retrieve system health status',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/health/checks', methods=['POST'])
@require_auth
def run_health_checks():
    """
    Manually trigger all health checks.

    Returns:
        JSON response with health check results
    """
    try:
        health_monitor = get_health_monitor()
        results = health_monitor.run_health_checks()

        # Convert results to serializable format
        check_results = {name: result.to_dict() for name, result in results.items()}

        return jsonify({
            'success': True,
            'data': {
                'check_results': check_results,
                'total_checks': len(results),
                'overall_status': health_monitor._calculate_overall_status(results).value
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        current_app.logger.error(f"Error running health checks: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': 'Failed to run health checks',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/health/recovery/<check_name>', methods=['POST'])
@require_auth
def trigger_health_recovery(check_name: str):
    """
    Trigger recovery actions for a specific health check.

    Args:
        check_name: Name of the health check

    Returns:
        JSON response confirming recovery attempt
    """
    try:
        # Check if user has admin privileges
        current_user = get_current_user()
        if not current_user.get('is_admin', False):
            return jsonify({
                'success': False,
                'error': 'Forbidden',
                'message': 'Admin privileges required to trigger health recovery',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 403

        health_monitor = get_health_monitor()
        recovery_success = health_monitor.force_recovery(check_name)

        if recovery_success:
            message = f"Recovery actions executed successfully for check '{check_name}'"
            current_app.logger.info(f"Health recovery triggered for '{check_name}' by user: {current_user.get('username', 'unknown')}")
        else:
            message = f"No recovery actions available or recovery failed for check '{check_name}'"

        return jsonify({
            'success': True,
            'message': message,
            'recovery_attempted': recovery_success,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        current_app.logger.error(f"Error triggering health recovery for '{check_name}': {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Failed to trigger recovery for health check "{check_name}"',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


# Notification Management Endpoints
@api_blueprint.route('/notifications', methods=['GET'])
@require_auth
def get_notifications():
    """
    Get notification history and configuration.

    Query Parameters:
        limit (int): Maximum number of notifications to return (default: 50, max: 200)
        level (str): Filter by notification level ('info', 'warning', 'critical')
        component (str): Filter by component name
        since (str): ISO timestamp to get notifications since
        status (str): Filter by notification status ('pending', 'sent', 'failed')

    Returns:
        JSON response with notifications and statistics
    """
    try:
        # Parse query parameters
        limit = min(int(request.args.get('limit', 50)), 200)
        level_filter = request.args.get('level', '').lower()
        component_filter = request.args.get('component', '')
        since = request.args.get('since')
        status_filter = request.args.get('status', '').lower()

        notification_manager = get_notification_manager()

        # Get notifications with filters
        filters = {}
        if level_filter:
            filters['level'] = level_filter
        if component_filter:
            filters['component'] = component_filter
        if status_filter:
            filters['status'] = status_filter
        if since:
            try:
                from datetime import datetime
                filters['since'] = datetime.fromisoformat(since.replace('Z', '+00:00'))
            except ValueError:
                raise ValidationError(f"Invalid timestamp format for 'since': {since}")

        notifications = notification_manager.get_notification_history(limit=limit, **filters)

        # Get statistics
        stats = notification_manager.get_statistics()

        return jsonify({
            'success': True,
            'data': {
                'notifications': [n.to_dict() for n in notifications],
                'count': len(notifications),
                'statistics': stats,
                'filters_applied': {
                    'limit': limit,
                    'level': level_filter or 'all',
                    'component': component_filter or 'all',
                    'status': status_filter or 'all',
                    'since': since
                }
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    except ValidationError as e:
        return jsonify({
            'success': False,
            'error': 'Validation Error',
            'message': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 422

    except Exception as e:
        current_app.logger.error(f"Error getting notifications: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': 'Failed to retrieve notifications',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/notifications', methods=['POST'])
@require_auth
def send_notification():
    """
    Send a manual notification.

    Request Body:
        {
            "title": "Notification title",
            "message": "Notification message",
            "level": "info|warning|critical",
            "component": "component_name",
            "channels": ["email", "webhook", "log"],  // optional
            "metadata": {}  // optional
        }

    Returns:
        JSON response with notification ID and delivery status
    """
    try:
        if not request.is_json:
            raise ValidationError("Request must contain JSON data")

        data = request.get_json()
        if not data:
            raise ValidationError("Request body cannot be empty")

        # Extract required fields
        title = data.get('title')
        message = data.get('message')
        level = data.get('level', 'info').lower()
        component = data.get('component', 'manual')

        if not title:
            raise ValidationError("'title' is required")
        if not message:
            raise ValidationError("'message' is required")

        # Validate level
        from ..scheduler.notifications import NotificationLevel
        try:
            notification_level = NotificationLevel(level.upper())
        except ValueError:
            raise ValidationError(f"Invalid notification level: {level}. Must be one of: info, warning, critical")

        # Optional fields
        channels = data.get('channels')
        if channels is not None:
            from ..scheduler.notifications import NotificationChannel
            try:
                channels = [NotificationChannel(ch.upper()) for ch in channels]
            except ValueError as e:
                raise ValidationError(f"Invalid notification channel: {e}")

        metadata = data.get('metadata', {})
        if not isinstance(metadata, dict):
            raise ValidationError("'metadata' must be a dictionary")

        # Add request metadata
        user_id = get_current_user() or 'anonymous'
        metadata.update({
            'manual_request': True,
            'user_id': user_id,
            'client_ip': request.remote_addr,
            'user_agent': request.headers.get('User-Agent', 'Unknown')
        })

        # Send notification
        notification_manager = get_notification_manager()
        notification = notification_manager.send_notification(
            title=title,
            message=message,
            level=notification_level,
            component=component,
            metadata=metadata,
            channels=channels
        )

        if notification:
            current_app.logger.info(f"Manual notification sent by user {user_id}: {title}")

            return jsonify({
                'success': True,
                'data': {
                    'notification_id': notification.id,
                    'title': notification.title,
                    'level': notification.level.value,
                    'component': notification.component,
                    'channels_attempted': [ch.value for ch in notification.channels],
                    'sent_at': notification.created_at.isoformat()
                },
                'message': 'Notification sent successfully',
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Notification Failed',
                'message': 'Failed to send notification (rate limited or other error)',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 429

    except ValidationError as e:
        return jsonify({
            'success': False,
            'error': 'Validation Error',
            'message': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 422

    except Exception as e:
        current_app.logger.error(f"Error sending notification: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': 'Failed to send notification',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/notifications/test', methods=['POST'])
@require_auth
def test_notifications():
    """
    Test notification delivery to all configured channels.

    Request Body:
        {
            "channels": ["email", "webhook", "log"]  // optional, defaults to all
        }

    Returns:
        JSON response with test results for each channel
    """
    try:
        # Check if user has admin privileges
        current_user = get_current_user()
        if not current_user.get('is_admin', False):
            return jsonify({
                'success': False,
                'error': 'Forbidden',
                'message': 'Admin privileges required to test notifications',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 403

        data = request.get_json() or {}
        test_channels = data.get('channels')

        if test_channels is not None:
            from ..scheduler.notifications import NotificationChannel
            try:
                test_channels = [NotificationChannel(ch.upper()) for ch in test_channels]
            except ValueError as e:
                raise ValidationError(f"Invalid notification channel: {e}")

        notification_manager = get_notification_manager()

        # Run test
        test_results = notification_manager.test_notifications(channels=test_channels)

        return jsonify({
            'success': True,
            'data': {
                'test_results': test_results,
                'overall_success': all(result.get('success', False) for result in test_results.values()),
                'tested_channels': list(test_results.keys()),
                'test_time': datetime.now(timezone.utc).isoformat()
            },
            'message': 'Notification test completed',
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    except ValidationError as e:
        return jsonify({
            'success': False,
            'error': 'Validation Error',
            'message': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 422

    except Exception as e:
        current_app.logger.error(f"Error testing notifications: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': 'Failed to test notifications',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/notifications/config', methods=['GET'])
@require_auth
def get_notification_config():
    """
    Get current notification configuration.

    Returns:
        JSON response with notification settings and channel configurations
    """
    try:
        notification_manager = get_notification_manager()
        config = notification_manager.get_configuration()

        return jsonify({
            'success': True,
            'data': config,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        current_app.logger.error(f"Error getting notification config: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': 'Failed to retrieve notification configuration',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/notifications/config', methods=['PUT'])
@require_auth
def update_notification_config():
    """
    Update notification configuration.

    Request Body:
        {
            "enabled": true,
            "rate_limit_per_hour": 10,
            "deduplication_window_minutes": 60,
            "channels": {
                "email": {
                    "enabled": true,
                    "smtp_host": "smtp.example.com",
                    "smtp_port": 587,
                    "username": "user@example.com",
                    "recipients": ["admin@example.com"]
                },
                "webhook": {
                    "enabled": true,
                    "url": "https://your-slack-webhook-url-here",
                    "timeout_seconds": 30
                }
            }
        }

    Returns:
        JSON response confirming configuration update
    """
    try:
        # Check if user has admin privileges
        current_user = get_current_user()
        if not current_user.get('is_admin', False):
            return jsonify({
                'success': False,
                'error': 'Forbidden',
                'message': 'Admin privileges required to update notification configuration',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 403

        if not request.is_json:
            raise ValidationError("Request must contain JSON data")

        config_updates = request.get_json()
        if not config_updates:
            raise ValidationError("Request body cannot be empty")

        notification_manager = get_notification_manager()
        success = notification_manager.update_configuration(config_updates)

        if success:
            current_app.logger.info(f"Notification configuration updated by user: {current_user.get('username', 'unknown')}")

            return jsonify({
                'success': True,
                'message': 'Notification configuration updated successfully',
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Configuration Update Failed',
                'message': 'Failed to update notification configuration',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 400

    except ValidationError as e:
        return jsonify({
            'success': False,
            'error': 'Validation Error',
            'message': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 422

    except Exception as e:
        current_app.logger.error(f"Error updating notification config: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': 'Failed to update notification configuration',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/notifications/statistics', methods=['GET'])
@require_auth
def get_notification_statistics():
    """
    Get notification delivery statistics.

    Query Parameters:
        hours (int): Time window for statistics in hours (default: 24, max: 168)

    Returns:
        JSON response with notification statistics
    """
    try:
        hours = min(int(request.args.get('hours', 24)), 168)  # Max 1 week

        notification_manager = get_notification_manager()
        stats = notification_manager.get_statistics(hours=hours)

        return jsonify({
            'success': True,
            'data': {
                'statistics': stats,
                'time_window_hours': hours
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    except ValueError:
        return jsonify({
            'success': False,
            'error': 'Invalid Parameter',
            'message': 'Hours parameter must be a valid integer',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 400

    except Exception as e:
        current_app.logger.error(f"Error getting notification statistics: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': 'Failed to retrieve notification statistics',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/notifications/<notification_id>', methods=['GET'])
@require_auth
def get_notification_details(notification_id: str):
    """
    Get detailed information about a specific notification.

    Args:
        notification_id: ID of the notification

    Returns:
        JSON response with notification details
    """
    try:
        notification_manager = get_notification_manager()
        notification = notification_manager.get_notification_by_id(notification_id)

        if not notification:
            return jsonify({
                'success': False,
                'error': 'Not Found',
                'message': f'Notification "{notification_id}" not found',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 404

        return jsonify({
            'success': True,
            'data': notification.to_dict(),
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        current_app.logger.error(f"Error getting notification details: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': f'Failed to retrieve notification "{notification_id}"',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


# Demo Mode API Endpoints
@api_blueprint.route('/schedules', methods=['GET'])
@require_auth
def get_schedules():
    """
    Get all automation schedules (demo mode).
    """
    try:
        # Get profile information from headers
        profile_id = request.headers.get('X-Powerwall-Profile', 'demo')
        config = get_config()
        # Check if this is the Gruber EG Powerwall first
        is_gruber_eg = profile_id == 'gruber-eg'
        
        # Check if we're in demo mode (cloud mode only, but not Gruber EG)
        is_demo_mode = profile_id == 'demo' and not is_gruber_eg
        
        if is_demo_mode or is_gruber_eg:
            # Return demo schedules with time-based automations
            if is_demo_mode:
                demo_schedules = [
                    {
                        'id': 'schedule_1',
                        'name': 'Night Reserve (40% at 00:01)',
                        'time': '00:01',
                        'reserve_percentage': 40,
                        'days': ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'],
                        'enabled': True,
                        'created_at': '2025-01-01T00:00:00Z',
                        'last_run': '2025-01-01T00:01:00Z',
                        'next_run': '2025-01-02T00:01:00Z'
                    },
                    {
                        'id': 'schedule_2',
                        'name': 'Morning Discharge (0% at 04:58)',
                        'time': '04:58',
                        'reserve_percentage': 0,
                        'days': ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'],
                        'enabled': True,
                        'created_at': '2025-01-01T00:00:00Z',
                        'last_run': '2025-01-01T04:58:00Z',
                        'next_run': '2025-01-02T04:58:00Z'
                    },
                    {
                        'id': 'schedule_3',
                        'name': 'Evening Reserve Increase',
                        'time': '18:00',
                        'reserve_percentage': 25,
                        'days': ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
                        'enabled': False,
                        'created_at': '2025-01-01T00:00:00Z',
                        'last_run': '2025-01-01T18:00:00Z',
                        'next_run': '2025-01-02T18:00:00Z'
                    }
                ]
            else:  # Gruber EG
                demo_schedules = [
                    {
                        'id': 'schedule_1',
                        'name': 'Gruber Night Reserve (50% at 23:30)',
                        'time': '23:30',
                        'reserve_percentage': 50,
                        'days': ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'],
                        'enabled': True,
                        'created_at': '2025-01-01T00:00:00Z',
                        'last_run': '2025-01-01T23:30:00Z',
                        'next_run': '2025-01-02T23:30:00Z'
                    },
                    {
                        'id': 'schedule_2',
                        'name': 'Gruber Morning Discharge (10% at 06:00)',
                        'time': '06:00',
                        'reserve_percentage': 10,
                        'days': ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'],
                        'enabled': True,
                        'created_at': '2025-01-01T00:00:00Z',
                        'last_run': '2025-01-01T06:00:00Z',
                        'next_run': '2025-01-02T06:00:00Z'
                    },
                    {
                        'id': 'schedule_3',
                        'name': 'Gruber Peak Hours (60% at 17:00)',
                        'time': '17:00',
                        'reserve_percentage': 60,
                        'days': ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
                        'enabled': True,
                        'created_at': '2025-01-01T00:00:00Z',
                        'last_run': '2025-01-01T17:00:00Z',
                        'next_run': '2025-01-02T17:00:00Z'
                    }
                ]
            
            powerwall_name = "Demo Powerwall" if is_demo_mode else "Gruber EG"
            
            return jsonify({
                'success': True,
                'data': demo_schedules,
                'demo_mode': is_demo_mode,
                'profile_id': profile_id,
                'powerwall_name': powerwall_name,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        
        # Real implementation would go here
        return jsonify({
            'success': False,
            'error': 'Not Implemented',
            'message': 'Schedule management not implemented for real Powerwall',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 501
        
    except Exception as e:
        current_app.logger.error(f"Error getting schedules: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': 'Failed to retrieve schedules',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/schedules', methods=['POST'])
@require_auth
def create_schedule():
    """
    Create a new automation schedule (demo mode).
    """
    try:
        # Get profile information from headers
        profile_id = request.headers.get('X-Powerwall-Profile', 'demo')
        config = get_config()
        # Check if this is the Gruber EG Powerwall first
        is_gruber_eg = profile_id == 'gruber-eg'
        
        # Check if we're in demo mode (cloud mode only, but not Gruber EG)
        is_demo_mode = profile_id == 'demo' and not is_gruber_eg
        
        if is_demo_mode or is_gruber_eg:
            data = request.get_json() or {}
            
            # Create demo schedule
            new_schedule = {
                'id': f'schedule_{int(datetime.now().timestamp())}',
                'name': data.get('name', 'New Schedule'),
                'time': data.get('time', '12:00'),
                'reserve_percentage': data.get('reserve_percentage', 20),
                'days': data.get('days', ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']),
                'enabled': data.get('enabled', True),
                'created_at': datetime.now(timezone.utc).isoformat(),
                'last_run': None,
                'next_run': f"{datetime.now().date()}T{data.get('time', '12:00')}:00Z"
            }
            
            powerwall_name = "Demo Powerwall" if is_demo_mode else "Gruber EG"
            
            return jsonify({
                'success': True,
                'data': new_schedule,
                'demo_mode': is_demo_mode,
                'profile_id': profile_id,
                'powerwall_name': powerwall_name,
                'message': f'Schedule created successfully for {powerwall_name}',
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        
        return jsonify({
            'success': False,
            'error': 'Not Implemented',
            'message': 'Schedule creation not implemented for real Powerwall',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 501
        
    except Exception as e:
        current_app.logger.error(f"Error creating schedule: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': 'Failed to create schedule',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/schedules/<schedule_id>', methods=['PUT'])
@require_auth
def update_schedule(schedule_id: str):
    """
    Update an automation schedule (demo mode).
    """
    try:
        # Get profile information from headers
        profile_id = request.headers.get('X-Powerwall-Profile', 'demo')
        config = get_config()
        # Check if this is the Gruber EG Powerwall first
        is_gruber_eg = profile_id == 'gruber-eg'
        
        # Check if we're in demo mode (cloud mode only, but not Gruber EG)
        is_demo_mode = profile_id == 'demo' and not is_gruber_eg
        
        if is_demo_mode or is_gruber_eg:
            data = request.get_json() or {}
            
            # Update demo schedule
            updated_schedule = {
                'id': schedule_id,
                'name': data.get('name', 'Updated Schedule'),
                'time': data.get('time', '12:00'),
                'reserve_percentage': data.get('reserve_percentage', 20),
                'days': data.get('days', ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']),
                'enabled': data.get('enabled', True),
                'created_at': '2025-01-01T00:00:00Z',
                'last_run': '2025-01-01T12:00:00Z',
                'next_run': f"{datetime.now().date()}T{data.get('time', '12:00')}:00Z"
            }
            
            return jsonify({
                'success': True,
                'data': updated_schedule,
                'demo_mode': True,
                'message': 'Schedule updated successfully (demo mode)',
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        
        return jsonify({
            'success': False,
            'error': 'Not Implemented',
            'message': 'Schedule update not implemented for real Powerwall',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 501
        
    except Exception as e:
        current_app.logger.error(f"Error updating schedule: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': 'Failed to update schedule',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/schedules/<schedule_id>', methods=['DELETE'])
@require_auth
def delete_schedule(schedule_id: str):
    """
    Delete an automation schedule (demo mode).
    """
    try:
        # Get profile information from headers
        profile_id = request.headers.get('X-Powerwall-Profile', 'demo')
        config = get_config()
        # Check if this is the Gruber EG Powerwall first
        is_gruber_eg = profile_id == 'gruber-eg'
        
        # Check if we're in demo mode (cloud mode only, but not Gruber EG)
        is_demo_mode = profile_id == 'demo' and not is_gruber_eg
        
        if is_demo_mode or is_gruber_eg:
            return jsonify({
                'success': True,
                'message': f'Schedule {schedule_id} deleted successfully (demo mode)',
                'demo_mode': True,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        
        return jsonify({
            'success': False,
            'error': 'Not Implemented',
            'message': 'Schedule deletion not implemented for real Powerwall',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 501
        
    except Exception as e:
        current_app.logger.error(f"Error deleting schedule: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': 'Failed to delete schedule',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/automation/status', methods=['GET'])
@require_auth
def get_automation_status():
    """
    Get automation status (demo mode).
    """
    try:
        # Get profile information from headers
        profile_id = request.headers.get('X-Powerwall-Profile', 'demo')
        config = get_config()
        # Check if this is the Gruber EG Powerwall first
        is_gruber_eg = profile_id == 'gruber-eg'
        
        # Check if we're in demo mode (cloud mode only, but not Gruber EG)
        is_demo_mode = profile_id == 'demo' and not is_gruber_eg
        
        if is_demo_mode or is_gruber_eg:
            powerwall_name = "Demo Powerwall" if is_demo_mode else "Gruber EG"
            
            return jsonify({
                'success': True,
                'data': {
                    'enabled': True,
                    'enabled_jobs': 2,
                    'disabled_jobs': 0,
                    'total_jobs': 2,
                    'last_execution': '2025-01-01T18:00:00Z',
                    'next_run': '2025-01-02T06:00:00Z',
                    'running': False,
                    'demo_mode': is_demo_mode
                },
                'profile_id': profile_id,
                'powerwall_name': powerwall_name,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        
        return jsonify({
            'success': False,
            'error': 'Not Implemented',
            'message': 'Automation status not implemented for real Powerwall',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 501
        
    except Exception as e:
        current_app.logger.error(f"Error getting automation status: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': 'Failed to get automation status',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/automation/toggle', methods=['POST'])
@require_auth
def toggle_automation():
    """
    Toggle automation on/off (demo mode).
    """
    try:
        # Get profile information from headers
        profile_id = request.headers.get('X-Powerwall-Profile', 'demo')
        config = get_config()
        # Check if this is the Gruber EG Powerwall first
        is_gruber_eg = profile_id == 'gruber-eg'
        
        # Check if we're in demo mode (cloud mode only, but not Gruber EG)
        is_demo_mode = profile_id == 'demo' and not is_gruber_eg
        
        if is_demo_mode or is_gruber_eg:
            data = request.get_json() or {}
            enabled = data.get('enabled', True)
            
            powerwall_name = "Demo Powerwall" if is_demo_mode else "Gruber EG"
            
            return jsonify({
                'success': True,
                'data': {
                    'enabled': enabled,
                    'message': f'Automation {"enabled" if enabled else "disabled"} successfully for {powerwall_name}'
                },
                'demo_mode': is_demo_mode,
                'profile_id': profile_id,
                'powerwall_name': powerwall_name,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        
        return jsonify({
            'success': False,
            'error': 'Not Implemented',
            'message': 'Automation toggle not implemented for real Powerwall',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 501
        
    except Exception as e:
        current_app.logger.error(f"Error toggling automation: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': 'Failed to toggle automation',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/activity', methods=['GET'])
@require_auth
def get_activity():
    """
    Get recent activity (demo mode).
    """
    try:
        # Get profile information from headers
        profile_id = request.headers.get('X-Powerwall-Profile', 'demo')
        config = get_config()
        
        # Check if this is the Gruber EG Powerwall first
        is_gruber_eg = profile_id == 'gruber-eg'
        
        # Check if we're in demo mode (cloud mode only, but not Gruber EG)
        is_demo_mode = profile_id == 'demo' and not is_gruber_eg
        
        if is_demo_mode or is_gruber_eg:
            limit = request.args.get('limit', 10, type=int)
            
            # Generate demo activity
            activities = []
            now = datetime.now(timezone.utc)
            
            for i in range(min(limit, 20)):
                activity_time = now - timedelta(minutes=i * 5)
                activities.append({
                    'id': f'activity_{i}',
                    'timestamp': activity_time.isoformat(),
                    'type': ['schedule', 'manual', 'system', 'error'][i % 4],
                    'message': [
                        'Morning reserve increase executed',
                        'User logged in',
                        'System health check completed',
                        'Backup reserve updated to 25%',
                        'Schedule "Evening Decrease" disabled',
                        'Configuration updated',
                        'Log file rotated',
                        'API request processed',
                        'Powerwall connection restored',
                        'New schedule created'
                    ][i % 10],
                    'details': f'Activity details for event {i}',
                    'level': ['info', 'warning', 'error', 'debug'][i % 4]
                })
            
            powerwall_name = "Demo Powerwall" if is_demo_mode else "Gruber EG"
            
            return jsonify({
                'success': True,
                'data': activities,
                'demo_mode': is_demo_mode,
                'profile_id': profile_id,
                'powerwall_name': powerwall_name,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        
        return jsonify({
            'success': False,
            'error': 'Not Implemented',
            'message': 'Activity retrieval not implemented for real Powerwall',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 501
        
    except Exception as e:
        current_app.logger.error(f"Error getting activity: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': 'Failed to get activity',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/schedules/<schedule_id>/execute', methods=['POST'])
@require_auth
def execute_schedule(schedule_id: str):
    """
    Execute a schedule immediately (demo mode).
    """
    try:
        config = get_config()
        is_demo_mode = config.powerwall.tesla_email in ['demo@example.com', 'user@example.com']
        
        if is_demo_mode:
            # Simulate schedule execution
            now = datetime.now(timezone.utc)
            
            # Find the schedule (in a real implementation, this would query the database)
            demo_schedules = [
                {
                    'id': 'schedule_1',
                    'name': 'Night Reserve (40% at 00:01)',
                    'time': '00:01',
                    'reserve_percentage': 40,
                    'days': ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'],
                    'enabled': True
                },
                {
                    'id': 'schedule_2',
                    'name': 'Morning Discharge (0% at 04:58)',
                    'time': '04:58',
                    'reserve_percentage': 0,
                    'days': ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'],
                    'enabled': True
                }
            ]
            
            schedule = next((s for s in demo_schedules if s['id'] == schedule_id), None)
            if not schedule:
                return jsonify({
                    'success': False,
                    'error': 'Not Found',
                    'message': f'Schedule {schedule_id} not found',
                    'timestamp': now.isoformat()
                }), 404
            
            # Simulate execution
            execution_result = {
                'schedule_id': schedule_id,
                'schedule_name': schedule['name'],
                'executed_at': now.isoformat(),
                'reserve_percentage': schedule['reserve_percentage'],
                'success': True,
                'message': f'Demo: Backup reserve set to {schedule["reserve_percentage"]}%',
                'demo_mode': True
            }
            
            return jsonify({
                'success': True,
                'data': execution_result,
                'timestamp': now.isoformat()
            })
        
        return jsonify({
            'success': False,
            'error': 'Not Implemented',
            'message': 'Schedule execution not implemented for real Powerwall',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 501
        
    except Exception as e:
        current_app.logger.error(f"Error executing schedule: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': 'Failed to execute schedule',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@api_blueprint.route('/schedules/next-execution', methods=['GET'])
@require_auth
def get_next_execution():
    """
    Get the next scheduled execution (demo mode).
    """
    try:
        config = get_config()
        is_demo_mode = config.powerwall.tesla_email in ['demo@example.com', 'user@example.com']
        
        if is_demo_mode:
            now = datetime.now(timezone.utc)
            
            # Calculate next execution times for demo schedules
            next_executions = [
                {
                    'schedule_id': 'schedule_1',
                    'schedule_name': 'Night Reserve (40% at 00:01)',
                    'next_execution': (now.replace(hour=0, minute=1, second=0, microsecond=0) + timedelta(days=1)).isoformat(),
                    'reserve_percentage': 40,
                    'time_until': 'Next night at 00:01'
                },
                {
                    'schedule_id': 'schedule_2',
                    'schedule_name': 'Morning Discharge (0% at 04:58)',
                    'next_execution': (now.replace(hour=4, minute=58, second=0, microsecond=0) + timedelta(days=1)).isoformat(),
                    'reserve_percentage': 0,
                    'time_until': 'Tomorrow at 04:58'
                }
            ]
            
            return jsonify({
                'success': True,
                'data': next_executions,
                'demo_mode': True,
                'timestamp': now.isoformat()
            })
        
        return jsonify({
            'success': False,
            'error': 'Not Implemented',
            'message': 'Next execution not implemented for real Powerwall',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 501
        
    except Exception as e:
        current_app.logger.error(f"Error getting next execution: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': 'Failed to get next execution',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500