"""
Tesla OAuth authentication API endpoints.

Handles web-based OAuth flow, token management, and Powerwall discovery.
"""

from flask import Blueprint, request, jsonify, session, redirect, url_for
from datetime import datetime, timezone

from ...core.auth.tesla_oauth import TeslaOAuthManager
from ...utils.logging import get_logger, ComponentType, OperationType
from ...utils.timezone_utils import safe_format_datetime, format_datetime_for_display
from .decorators import require_auth


auth_blueprint = Blueprint('auth', __name__, url_prefix='/api/auth')
logger = get_logger()

# Global OAuth manager instance
oauth_manager: TeslaOAuthManager = None


def init_auth_api(app):
    """Initialize OAuth API with Flask app."""
    global oauth_manager
    # Use persistent data path from environment, fallback to local data directory
    import os
    storage_path = os.environ.get('POWERNIGHT_DATA_PATH', 'data')
    oauth_manager = TeslaOAuthManager(storage_path=storage_path)
    app.register_blueprint(auth_blueprint)


@auth_blueprint.route('/tesla/status', methods=['GET'])
def get_auth_status():
    """
    Get current Tesla authentication status.
    
    Returns:
        JSON response with authentication status
    """
    try:
        status = oauth_manager.get_auth_status()
        
        return jsonify({
            'success': True,
            'data': status,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
    except Exception as e:
        logger.log_error(ComponentType.WEB, "Failed to get auth status", e)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@auth_blueprint.route('/tesla/info', methods=['GET'])
def get_auth_info():
    """
    Get detailed Tesla authentication information for display on settings page.
    
    Returns:
        JSON response with detailed auth information (sensitive data masked)
    """
    try:
        # Get basic auth status
        status = oauth_manager.get_auth_status()
        
        if not status.get('authenticated'):
            return jsonify({
                'success': True,
                'data': {
                    'authenticated': False,
                    'message': 'No Tesla authentication found'
                },
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        
        # Get detailed auth data
        auth_data = oauth_manager.auth_storage.load_auth_data()
        storage_info = oauth_manager.auth_storage.get_storage_info()
        
        # Prepare response with masked sensitive data
        response_data = {
            'authenticated': True,
            'email': auth_data.get('email', 'Unknown'),
            'site_id': auth_data.get('site', {}).get('id') if auth_data.get('site') else None,
            'token_type': auth_data.get('token_type', 'Bearer'),
            'expires_at': safe_format_datetime(status.get('expires_at')),
            'expires_in_seconds': status.get('expires_in_seconds', 0),
            'token_expired': status.get('token_expired', True),
            'storage_path': storage_info.get('storage_path'),
            'file_size': storage_info.get('file_size'),
            'modified_at': safe_format_datetime(storage_info.get('modified_at')),
            # Mask sensitive tokens
            'access_token_masked': _mask_token(auth_data.get('access_token', '')),
            'refresh_token_masked': _mask_token(auth_data.get('refresh_token', ''))
        }
        
        return jsonify({
            'success': True,
            'data': response_data,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
    except Exception as e:
        logger.log_error(ComponentType.WEB, "Failed to get auth info", e)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


def _mask_token(token) -> str:
    """
    Mask sensitive token data for display.
    
    Args:
        token: Token to mask (string, float, or other type)
        
    Returns:
        Masked token string
    """
    # Convert to string first to handle different data types
    token_str = str(token) if token is not None else ''
    
    if not token_str or len(token_str) < 8:
        return '***'
    
    # Show first 4 and last 4 characters, mask the middle
    return f"{token_str[:4]}...{token_str[-4:]}"


# New Auth Setup Endpoints

@auth_blueprint.route('/setup/start', methods=['POST'])
def start_auth_setup():
    """
    Start Tesla OAuth setup flow.
    
    Body:
        {"email": "user@tesla.com"}
        
    Returns:
        JSON response with auth URL and session ID
    """
    try:
        data = request.get_json()
        if not data or 'email' not in data:
            return jsonify({
                'success': False,
                'error': 'Email is required',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 400
        
        email = data['email'].strip()
        if not email:
            return jsonify({
                'success': False,
                'error': 'Email cannot be empty',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 400
        
        # Clean up expired sessions
        oauth_manager.cleanup_expired_sessions()
        
        # Generate auth URL
        result = oauth_manager.generate_auth_url(email)
        
        return jsonify({
            'success': True,
            'auth_url': result['auth_url'],
            'session_id': result['session_id'],
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
    except Exception as e:
        logger.log_error(ComponentType.WEB, "Failed to start auth setup", e)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@auth_blueprint.route('/setup/callback', methods=['POST'])
def process_callback():
    """
    Process Tesla OAuth callback URL.
    
    Body:
        {
            "session_id": "session-id",
            "callback_url": "https://auth.tesla.com/void/callback?code=...&state=..."
        }
        
    Returns:
        JSON response with sites list
    """
    try:
        data = request.get_json()
        if not data or 'session_id' not in data or 'callback_url' not in data:
            return jsonify({
                'success': False,
                'error': 'Session ID and callback URL are required',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 400
        
        session_id = data['session_id']
        callback_url = data['callback_url']
        
        # Process callback URL
        result = oauth_manager.exchange_code_from_callback_url(session_id, callback_url)
        
        if result['success']:
            return jsonify({
                'success': True,
                'sites': result['sites'],
                'expires_at': safe_format_datetime(result.get('expires_at')),
                'timestamp': format_datetime_for_display(datetime.now(timezone.utc))
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Failed to process callback'),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 400
        
    except Exception as e:
        logger.log_error(ComponentType.WEB, "Failed to process callback", e)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@auth_blueprint.route('/setup/complete', methods=['POST'])
def complete_auth_setup():
    """
    Complete Tesla OAuth setup with site selection.
    
    Body:
        {
            "session_id": "session-id",
            "site_id": "selected-site-id"
        }
        
    Returns:
        JSON response with setup completion result
    """
    try:
        data = request.get_json()
        if not data or 'session_id' not in data or 'site_id' not in data:
            return jsonify({
                'success': False,
                'error': 'Session ID and site ID are required',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 400
        
        session_id = data['session_id']
        site_id = data['site_id']
        
        # Complete setup
        result = oauth_manager.complete_setup(session_id, site_id)
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': result['message'],
                'email': result['email'],
                'site': result['site'],
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Failed to complete setup'),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 400
        
    except Exception as e:
        logger.log_error(ComponentType.WEB, "Failed to complete auth setup", e)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@auth_blueprint.route('/setup/status/<session_id>', methods=['GET'])
def get_setup_status(session_id):
    """
    Get status of an auth setup session.
    
    Args:
        session_id: Session ID to check
        
    Returns:
        JSON response with session status
    """
    try:
        status = oauth_manager.get_session_status(session_id)
        
        return jsonify({
            'success': True,
            'data': status,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
    except Exception as e:
        logger.log_error(ComponentType.WEB, "Failed to get setup status", e)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500




@auth_blueprint.route('/tesla/refresh', methods=['POST'])
@require_auth
def refresh_access_token():
    """
    Refresh Tesla access token.
    
    Returns:
        JSON response with refresh result
    """
    try:
        success = oauth_manager.refresh_access_token()
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Token refreshed successfully',
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to refresh token',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 400
        
    except Exception as e:
        logger.log_error(ComponentType.WEB, "Token refresh error", e)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@auth_blueprint.route('/tesla/logout', methods=['POST'])
@require_auth
def logout():
    """
    Logout and revoke Tesla tokens.
    
    Returns:
        JSON response with logout result
    """
    try:
        success = oauth_manager.revoke_tokens()
        
        if success:
            # Clear any session data
            session.clear()
            
            return jsonify({
                'success': True,
                'message': 'Logged out successfully',
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to revoke tokens',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 400
        
    except Exception as e:
        logger.log_error(ComponentType.WEB, "Logout error", e)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@auth_blueprint.route('/tesla/powerwalls', methods=['GET'])
@require_auth
def get_powerwalls():
    """
    Test pypowerwall connection and get basic Powerwall info.
    
    Returns:
        JSON response with Powerwall connection test result
    """
    try:
        # Test pypowerwall connection using stored auth data
        result = oauth_manager.test_pypowerwall_connection("")
        
        if result['success']:
            return jsonify({
                'success': True,
                'data': {
                    'powerwalls': [result['powerwall']],
                    'count': 1,
                    'connection_type': 'pypowerwall_cloud'
                },
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Failed to connect to Powerwall'),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 500
        
    except Exception as e:
        logger.log_error(ComponentType.WEB, "Failed to test Powerwall connection", e)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@auth_blueprint.route('/tesla/test-connection', methods=['POST'])
@require_auth
def test_connection():
    """
    Test pypowerwall cloud mode connection.
    
    Returns:
        JSON response with connection test result
    """
    try:
        # Test pypowerwall connection using stored auth data
        result = oauth_manager.test_pypowerwall_connection("")
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': 'pypowerwall connection test successful',
                'data': {
                    'powerwalls_found': 1,
                    'api_accessible': True,
                    'connection_type': 'pypowerwall_cloud',
                    'powerwall_info': result['powerwall']
                },
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Connection test failed'),
                'data': {
                    'api_accessible': False,
                    'connection_type': 'pypowerwall_cloud'
                },
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 500
        
    except Exception as e:
        logger.log_error(ComponentType.WEB, "Connection test failed", e)
        return jsonify({
            'success': False,
            'error': str(e),
            'data': {
                'api_accessible': False,
                'connection_type': 'pypowerwall_cloud'
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@auth_blueprint.route('/site-details', methods=['GET'])
def get_site_details():
    """
    Get detailed information for the authenticated energy site using pypowerwall.

    Returns:
        JSON response with comprehensive site details from multiple pypowerwall methods
    """
    try:
        import pypowerwall

        # Get valid access token
        access_token = oauth_manager.get_valid_access_token()
        if not access_token:
            return jsonify({
                'success': False,
                'error': 'No valid authentication token available',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 401

        # Load auth data to get site info
        auth_data = oauth_manager.auth_storage.load_auth_data()
        if not auth_data or 'site' not in auth_data or auth_data['site'] is None:
            return jsonify({
                'success': False,
                'error': 'No site information available',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 404

        # Create pypowerwall Cloud instance using the same method as test_connection
        # This uses the stored auth data and authpath for proper authentication
        pw = pypowerwall.Powerwall(
            email=auth_data['email'],
            cloudmode=True,
            authmode="token",
            authpath=str(oauth_manager.auth_storage.storage_path) + "/",
            timeout=30
        )

        # Get comprehensive site data using multiple pypowerwall methods
        site_data = {}
        
        try:
            # Log pypowerwall instance info
            logger.log_system_event(OperationType.INFO, "pypowerwall_debug", metadata={
                "mode": pw.mode,
                "cloudmode": pw.cloudmode,
                "is_connected": pw.is_connected(),
                "version": pw.version(),
                "din": pw.din(),
                "site_name": pw.site_name(),
                "uptime": pw.uptime()
            })
            
            # Get basic status information
            try:
                status_data = pw.status()
                logger.log_system_event(OperationType.INFO, "pypowerwall_status", metadata={"data": status_data})
                if status_data:
                    site_data.update(status_data)
            except Exception as e:
                logger.log_error(ComponentType.WEB, f"pw.status() failed: {e}", e)
            
            # Get power information
            try:
                power_data = pw.power()
                logger.log_system_event(OperationType.INFO, "pypowerwall_power", metadata={"data": power_data})
                if power_data:
                    site_data.update(power_data)
            except Exception as e:
                logger.log_error(ComponentType.WEB, f"pw.power() failed: {e}", e)
            
            # Get battery level
            try:
                battery_level = pw.level()
                logger.log_system_event(OperationType.INFO, "pypowerwall_level", metadata={"data": battery_level})
                if battery_level is not None:
                    site_data['battery_level'] = battery_level
            except Exception as e:
                logger.log_error(ComponentType.WEB, f"pw.level() failed: {e}", e)
            
            # Get mode information (mode is a property, not a method)
            try:
                mode_data = pw.mode
                logger.log_system_event(OperationType.INFO, "pypowerwall_mode", metadata={"data": mode_data})
                if mode_data:
                    site_data['mode'] = mode_data
            except Exception as e:
                logger.log_error(ComponentType.WEB, f"pw.mode failed: {e}", e)
            
            # Get reserve percentage
            try:
                reserve = pw.get_reserve()
                logger.log_system_event(OperationType.INFO, "pypowerwall_get_reserve", metadata={"data": reserve})
                if reserve is not None:
                    site_data['reserve'] = reserve
            except Exception as e:
                logger.log_error(ComponentType.WEB, f"pw.get_reserve() failed: {e}", e)
            
            # Get grid charging status
            try:
                grid_charging = pw.get_grid_charging()
                logger.log_system_event(OperationType.INFO, "pypowerwall_get_grid_charging", metadata={"data": grid_charging})
                if grid_charging is not None:
                    site_data['grid_charging'] = grid_charging
            except Exception as e:
                logger.log_error(ComponentType.WEB, f"pw.get_grid_charging() failed: {e}", e)
            
            # Get grid export mode
            try:
                grid_export = pw.get_grid_export()
                logger.log_system_event(OperationType.INFO, "pypowerwall_get_grid_export", metadata={"data": grid_export})
                if grid_export is not None:
                    site_data['grid_export_mode'] = grid_export
            except Exception as e:
                logger.log_error(ComponentType.WEB, f"pw.get_grid_export() failed: {e}", e)
            
            # Additional pypowerwall API calls for comprehensive logging
            try:
                alerts_data = pw.alerts()
                logger.log_system_event(OperationType.INFO, "pypowerwall_alerts", metadata={"data": alerts_data})
            except Exception as e:
                logger.log_error(ComponentType.WEB, f"pw.alerts() failed: {e}", e)
            
            try:
                battery_data = pw.battery()
                logger.log_system_event(OperationType.INFO, "pypowerwall_battery", metadata={"data": battery_data})
            except Exception as e:
                logger.log_error(ComponentType.WEB, f"pw.battery() failed: {e}", e)
            
            try:
                grid_data = pw.grid()
                logger.log_system_event(OperationType.INFO, "pypowerwall_grid", metadata={"data": grid_data})
            except Exception as e:
                logger.log_error(ComponentType.WEB, f"pw.grid() failed: {e}", e)
            
            try:
                home_data = pw.home()
                logger.log_system_event(OperationType.INFO, "pypowerwall_home", metadata={"data": home_data})
            except Exception as e:
                logger.log_error(ComponentType.WEB, f"pw.home() failed: {e}", e)
            
            try:
                solar_data = pw.solar()
                logger.log_system_event(OperationType.INFO, "pypowerwall_solar", metadata={"data": solar_data})
            except Exception as e:
                logger.log_error(ComponentType.WEB, f"pw.solar() failed: {e}", e)
            
            try:
                load_data = pw.load()
                logger.log_system_event(OperationType.INFO, "pypowerwall_load", metadata={"data": load_data})
            except Exception as e:
                logger.log_error(ComponentType.WEB, f"pw.load() failed: {e}", e)
            
            try:
                site_data_raw = pw.site()
                logger.log_system_event(OperationType.INFO, "pypowerwall_site", metadata={"data": site_data_raw})
            except Exception as e:
                logger.log_error(ComponentType.WEB, f"pw.site() failed: {e}", e)
            
            try:
                vitals_data = pw.vitals()
                logger.log_system_event(OperationType.INFO, "pypowerwall_vitals", metadata={"data": vitals_data})
            except Exception as e:
                logger.log_error(ComponentType.WEB, f"pw.vitals() failed: {e}", e)
            
            try:
                system_status_data = pw.system_status()
                logger.log_system_event(OperationType.INFO, "pypowerwall_system_status", metadata={"data": system_status_data})
            except Exception as e:
                logger.log_error(ComponentType.WEB, f"pw.system_status() failed: {e}", e)
            
            try:
                grid_status_data = pw.grid_status()
                logger.log_system_event(OperationType.INFO, "pypowerwall_grid_status", metadata={"data": grid_status_data})
            except Exception as e:
                logger.log_error(ComponentType.WEB, f"pw.grid_status() failed: {e}", e)
            
            try:
                temps_data = pw.temps()
                logger.log_system_event(OperationType.INFO, "pypowerwall_temps", metadata={"data": temps_data})
            except Exception as e:
                logger.log_error(ComponentType.WEB, f"pw.temps() failed: {e}", e)
            
            try:
                strings_data = pw.strings()
                logger.log_system_event(OperationType.INFO, "pypowerwall_strings", metadata={"data": strings_data})
            except Exception as e:
                logger.log_error(ComponentType.WEB, f"pw.strings() failed: {e}", e)
            
            try:
                battery_blocks_data = pw.battery_blocks()
                logger.log_system_event(OperationType.INFO, "pypowerwall_battery_blocks", metadata={"data": battery_blocks_data})
            except Exception as e:
                logger.log_error(ComponentType.WEB, f"pw.battery_blocks() failed: {e}", e)
            
            try:
                get_mode_data = pw.get_mode()
                logger.log_system_event(OperationType.INFO, "pypowerwall_get_mode", metadata={"data": get_mode_data})
            except Exception as e:
                logger.log_error(ComponentType.WEB, f"pw.get_mode() failed: {e}", e)
            
            try:
                get_time_remaining_data = pw.get_time_remaining()
                logger.log_system_event(OperationType.INFO, "pypowerwall_get_time_remaining", metadata={"data": get_time_remaining_data})
            except Exception as e:
                logger.log_error(ComponentType.WEB, f"pw.get_time_remaining() failed: {e}", e)
            
            # Add site information from auth data
            site_data['site_name'] = auth_data['site'].get('name', 'Unknown')
            site_data['site_id'] = auth_data['site'].get('id', 'Unknown')
            
            # Add current timestamp
            site_data['timestamp'] = format_datetime_for_display(datetime.now(timezone.utc))
            
            return jsonify({
                'success': True,
                'data': site_data,
                'timestamp': format_datetime_for_display(datetime.now(timezone.utc))
            })
            
        except Exception as data_error:
            logger.log_error(ComponentType.WEB, "Failed to fetch specific site data", data_error)
            return jsonify({
                'success': False,
                'error': f'Failed to fetch site details: {str(data_error)}',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 500

    except Exception as e:
        logger.log_error(ComponentType.WEB, "Failed to fetch site details", e)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500
