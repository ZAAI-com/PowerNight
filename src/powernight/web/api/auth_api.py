"""
Tesla OAuth authentication API endpoints.

Handles web-based OAuth flow, token management, and Powerwall discovery.
"""

import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from flask import Blueprint, Flask, Response, current_app, request, jsonify, session
from flask.typing import ResponseReturnValue
from datetime import datetime, timezone

from ...core.auth.connection_state import classify_connection_state
from ...core.auth.setup_attempts import SetupError
from ...core.auth.tesla_oauth import TeslaOAuthManager
from ...core.config import get_config
from ...utils.logging import get_logger, ComponentType, OperationType
from ...utils.redaction import safe_error_detail
from ...utils.timezone_utils import safe_format_datetime, format_datetime_for_display
from .decorators import require_auth, get_current_user


auth_blueprint = Blueprint('auth', __name__, url_prefix='/api/auth')
logger = get_logger()

# Global OAuth manager instance
oauth_manager: TeslaOAuthManager = None  # type: ignore[assignment]  # set by init_auth_api() at startup


def init_auth_api(app: Flask) -> None:
    """Initialize OAuth API with Flask app."""
    global oauth_manager
    # Use persistent data path from environment, fallback to local data directory
    import os
    storage_path = os.environ.get('POWERNIGHT_DATA_PATH', 'data')
    oauth_manager = TeslaOAuthManager(storage_path=storage_path)
    app.register_blueprint(auth_blueprint)


def _shared_connector() -> Any:
    """Return the application's long-lived Powerwall connector, when available."""
    return getattr(current_app, 'powerwall_connector', None)


def _raw_connection_status() -> Dict[str, Any]:
    """The connector's cached connection state, without any network call."""
    connector = _shared_connector()
    status = None
    if connector is not None and hasattr(connector, 'get_connection_status'):
        status = connector.get_connection_status()
    return status if isinstance(status, dict) else {}


def _shared_connection_status() -> Dict[str, Any]:
    """Return a JSON-safe snapshot of live Tesla connection state."""
    status = _raw_connection_status()
    return {
        'connected': bool(status.get('connected')),
        'connection_status': status.get('connection_status', 'unknown'),
        'last_connection_attempt': status.get('last_connection_attempt'),
        'connection_error': status.get('connection_error'),
        'connection_error_code': status.get('connection_error_code'),
    }


def _connection_state_payload() -> Dict[str, Any]:
    """Connection snapshot plus the evidence-based state the UI shows."""
    status = _raw_connection_status()
    storage = oauth_manager.auth_storage
    assessment = classify_connection_state(
        has_auth_file=storage.has_auth_data(),
        auth_data=storage.load_auth_data(),
        connection=status,
        now=time.time(),
    )
    return {
        **_shared_connection_status(),
        'connection_state': assessment.state,
        'connection_state_reason': assessment.reason,
    }


@contextmanager
def _shared_cloud_session() -> Iterator[Any]:
    """Use the shared connector's live pypowerwall session under its lock."""
    connector = _shared_connector()
    if connector is None:
        raise RuntimeError('Powerwall connector is not available')
    with connector.cloud_session() as pw:
        yield pw


def _connect_shared_connector(force: bool = False) -> Dict[str, Any]:
    """Connect the shared connector used by the scheduler and manual commands."""
    connector = _shared_connector()
    if connector is None:
        raise RuntimeError('Powerwall connector is not available')
    if force:
        connector.disconnect()
    connector.ensure_connected()
    return _shared_connection_status()


@auth_blueprint.route('/tesla/status', methods=['GET'])
@require_auth
def get_auth_status() -> ResponseReturnValue:
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
            'error': 'Internal server error',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@auth_blueprint.route('/tesla/info', methods=['GET'])
@require_auth
def get_auth_info() -> ResponseReturnValue:
    """
    Get detailed Tesla authentication information for display on settings page.
    
    Returns:
        JSON response with detailed auth information (sensitive data masked)
    """
    try:
        # Get basic auth status
        status = oauth_manager.get_auth_status()
        connection_status = _connection_state_payload()
        
        if not status.get('authenticated'):
            return jsonify({
                'success': True,
                'data': {
                    'authenticated': False,
                    'message': 'No Tesla authentication found',
                    **connection_status,
                },
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        
        # Get detailed auth data
        auth_data = oauth_manager.auth_storage.load_auth_data() or {}
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
        response_data.update(connection_status)
        
        return jsonify({
            'success': True,
            'data': response_data,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
    except Exception as e:
        logger.log_error(ComponentType.WEB, "Failed to get auth info", e)
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


def _mask_token(token: Optional[str]) -> str:
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


# Setup endpoints: browser sign-in, token import, the Mac helper handoff

def _setup_allowed() -> bool:
    """
    Decide whether an OAuth setup request may proceed.

    First-time setup must be possible on a fresh install (no credentials
    exist yet), but once Tesla tokens exist, or when web auth is enabled,
    setup endpoints must not be open to the network:
    - Authenticated requests are always allowed.
    - Web auth disabled: allowed (the whole UI is open by configuration).
    - Otherwise: only when no Tesla tokens exist yet AND the request comes
      from loopback (first-time bootstrap on the host itself).
    """
    try:
        config = get_config()
        if not config.web_interface.auth_enabled:
            return True
        if get_current_user():
            return True
        has_tokens = oauth_manager.auth_storage.has_auth_data()
        is_loopback = request.remote_addr in ('127.0.0.1', '::1')
        return not has_tokens and is_loopback
    except Exception:
        return False


def _setup_denied_response() -> ResponseReturnValue:
    """Standard 401 response for blocked setup requests (app auth, not Tesla)."""
    return jsonify({
        'success': False,
        'error': 'Authentication required',
        'error_code': 'APP_AUTH_REQUIRED',
        'message': 'Tesla setup requires authentication once the app is configured',
        'timestamp': datetime.now(timezone.utc).isoformat()
    }), 401


def _setup_json(body: Dict[str, Any], status: int = 200) -> Response:
    """JSON for setup endpoints: never cached, never 401 for Tesla-side failures."""
    response = jsonify({**body, 'timestamp': datetime.now(timezone.utc).isoformat()})
    # A 401 makes the web UI drop its PowerNight API key; Tesla problems must not
    response.status_code = 400 if status == 401 else status
    response.headers['Cache-Control'] = 'no-store'
    return response


def _setup_error_response(error: SetupError) -> Response:
    body: Dict[str, Any] = {'success': False, 'error_code': str(error.code), 'error': error.message}
    if error.progress is not None:
        body['setup'] = error.progress
    return _setup_json(body, error.http_status)


def _invalid_setup_input(message: str) -> Response:
    return _setup_json({'success': False, 'error_code': 'INVALID_INPUT', 'error': message}, 400)


def _setup_internal_error(message: str, error: Exception) -> Response:
    """Log without exception text from pypowerwall or Tesla (it can hold tokens)."""
    logger.error(f"{message} ({safe_error_detail(error)})")
    return _setup_json({'success': False, 'error_code': 'INTERNAL_ERROR', 'error': 'Internal server error'}, 500)


def _request_json() -> Dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@auth_blueprint.route('/setup/start', methods=['POST'])
def start_auth_setup() -> ResponseReturnValue:
    """
    Start Tesla OAuth setup flow.
    
    Body:
        {"email": "user@tesla.com"}
        
    Returns:
        JSON response with auth URL, session ID and the attempt's progress
    """
    if not _setup_allowed():
        return _setup_denied_response()
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or 'email' not in data:
            return _invalid_setup_input('Email is required')

        email = str(data.get('email') or '').strip()
        if not email:
            return _invalid_setup_input('Email cannot be empty')
        if len(email) > 254:
            return _invalid_setup_input('Email is too long')

        oauth_manager.cleanup_expired_sessions()
        setup = oauth_manager.start_setup(email)

        return _setup_json({
            'success': True,
            'auth_url': setup['auth_url'],
            'session_id': setup['session_id'],
            'setup_expires_at': setup['setup_expires_at'],
            'setup': setup,
        })

    except Exception as e:
        return _setup_internal_error("Failed to start auth setup", e)


@auth_blueprint.route('/setup/callback', methods=['POST'])
def process_callback() -> ResponseReturnValue:
    """
    Process Tesla OAuth callback URL.
    
    Body:
        {
            "session_id": "session-id",
            "callback_url": "tesla://auth/callback?code=...&state=..."
        }
        
    Returns:
        JSON response with sites list; 202 while another request for the
        same attempt is still talking to Tesla
    """
    if not _setup_allowed():
        return _setup_denied_response()
    try:
        data = _request_json()
        session_id = data.get('session_id')
        callback_url = data.get('callback_url')
        if not session_id or not isinstance(callback_url, str) or not callback_url.strip():
            return _invalid_setup_input('Session ID and callback URL are required')

        try:
            outcome = oauth_manager.submit_callback(str(session_id), callback_url)
        except SetupError as error:
            return _setup_error_response(error)

        progress = outcome.progress
        if outcome.http_status == 202:
            return _setup_json({'success': True, 'in_progress': True, 'setup': progress}, 202)
        return _setup_json({
            'success': True,
            'sites': progress['sites'] or [],
            'expires_at': safe_format_datetime(progress['token_expires_at']),
            'setup_expires_at': progress['setup_expires_at'],
            'duplicate': outcome.duplicate,
            'setup': progress,
        })

    except Exception as e:
        return _setup_internal_error("Failed to process callback", e)


@auth_blueprint.route('/setup/tokens', methods=['POST'])
def import_tokens() -> ResponseReturnValue:
    """
    Start Tesla setup from tokens created by ``python -m pypowerwall authtoken``.

    Body:
        {
            "email": "user@tesla.com",
            "refresh_token": "...",
            "access_token": "..."
        }

    Returns:
        JSON response with session ID and sites list
    """
    if not _setup_allowed():
        return _setup_denied_response()
    try:
        data = _request_json()
        email = str(data.get('email') or '').strip()
        if not email:
            return _invalid_setup_input('Email is required')

        oauth_manager.cleanup_expired_sessions()
        result = oauth_manager.import_tokens(
            email, str(data.get('refresh_token') or ''), str(data.get('access_token') or '')
        )

        if result.get('success'):
            body: Dict[str, Any] = {
                'success': True,
                'session_id': result['session_id'],
                'sites': result.get('sites') or [],
                'expires_at': safe_format_datetime(result.get('expires_at')),
                'setup_expires_at': result.get('setup_expires_at'),
            }
            if result.get('setup') is not None:
                body['setup'] = result['setup']
            return _setup_json(body, int(result.get('http_status', 200)))

        body = {
            'success': False,
            'error': result.get('error', 'Failed to import tokens'),
            'error_code': result.get('error_code', 'INVALID_INPUT'),
        }
        for key in ('session_id', 'setup'):
            if result.get(key) is not None:
                body[key] = result[key]
        return _setup_json(body, int(result.get('http_status', 400)))

    except Exception as e:
        return _setup_internal_error("Failed to import Tesla tokens", e)


@auth_blueprint.route('/setup/sites', methods=['POST'])
def retry_site_discovery() -> ResponseReturnValue:
    """
    List energy sites again for a signed-in attempt, without a new code exchange.

    Body:
        {"session_id": "session-id"}
    """
    if not _setup_allowed():
        return _setup_denied_response()
    try:
        session_id = _request_json().get('session_id')
        if not session_id:
            return _invalid_setup_input('Session ID is required')
        try:
            outcome = oauth_manager.retry_site_discovery(str(session_id))
        except SetupError as error:
            return _setup_error_response(error)

        progress = outcome.progress
        if outcome.http_status == 202:
            return _setup_json({'success': True, 'in_progress': True, 'setup': progress}, 202)
        return _setup_json({'success': True, 'sites': progress['sites'] or [], 'setup': progress})

    except Exception as e:
        return _setup_internal_error("Failed to retry Tesla site discovery", e)


@auth_blueprint.route('/setup/complete', methods=['POST'])
def complete_auth_setup() -> ResponseReturnValue:
    """
    Complete Tesla OAuth setup with site selection.

    Existing credentials and the live connection stay untouched until the
    new ones are validated and saved; the connector then swaps its session.
    
    Body:
        {
            "session_id": "session-id",
            "site_id": "selected-site-id"
        }
        
    Returns:
        JSON response with setup completion result
    """
    if not _setup_allowed():
        return _setup_denied_response()
    try:
        data = _request_json()
        if not data.get('session_id') or data.get('site_id') in (None, ''):
            return _invalid_setup_input('Session ID and site ID are required')

        connector = _shared_connector()
        commit = getattr(connector, 'replace_credentials', None) if connector is not None else None
        result = oauth_manager.complete_setup(
            str(data['session_id']), data['site_id'], commit=commit if callable(commit) else None
        )

        if not result.get('success'):
            body: Dict[str, Any] = {
                'success': False,
                'error': result.get('error', 'Failed to complete setup'),
                'error_code': result.get('error_code'),
                'credentials_saved': False,
            }
            if result.get('setup') is not None:
                body['setup'] = result['setup']
            return _setup_json(body, int(result.get('http_status', 400)))

        if result.get('in_progress'):
            return _setup_json({'success': True, 'in_progress': True, 'setup': result.get('setup')}, 202)

        duplicate = bool(result.get('duplicate'))
        if not duplicate:
            try:
                _connect_shared_connector()
            except Exception as connection_error:
                logger.error(
                    "Tesla credentials saved but shared connector failed "
                    f"({safe_error_detail(connection_error)})"
                )
                connection = _connection_state_payload()
                return _setup_json({
                    'success': False,
                    'credentials_saved': True,
                    'connected': False,
                    'connection_status': 'disconnected',
                    'connection_error': connection.get('connection_error') or (
                        'Tesla cloud connection failed. Check Settings and the container logs.'
                    ),
                    'connection_error_code': connection.get('connection_error_code'),
                    'connection_state': connection.get('connection_state'),
                    'connection_state_reason': connection.get('connection_state_reason'),
                    'message': 'Tesla credentials were saved, but the live connection failed.',
                    'email': result.get('email'),
                    'site': result.get('site'),
                    'setup': result.get('setup'),
                }, 502)

        return _setup_json({
            'success': True,
            'message': result.get('message'),
            'email': result.get('email'),
            'site': result.get('site'),
            'credentials_saved': True,
            'duplicate': duplicate,
            **_connection_state_payload(),
            'setup': result.get('setup'),
        })

    except Exception as e:
        return _setup_internal_error("Failed to complete auth setup", e)


@auth_blueprint.route('/setup/cancel', methods=['POST'])
def cancel_auth_setup() -> ResponseReturnValue:
    """
    Cancel one pending sign-in attempt. Stored credentials are not touched.

    Body:
        {"session_id": "session-id"}
    """
    if not _setup_allowed():
        return _setup_denied_response()
    try:
        session_id = _request_json().get('session_id')
        if not session_id:
            return _invalid_setup_input('Session ID is required')
        try:
            outcome = oauth_manager.cancel_setup(str(session_id))
        except SetupError as error:
            return _setup_error_response(error)
        return _setup_json({'success': True, 'already_ended': outcome.duplicate, 'setup': outcome.progress})

    except Exception as e:
        return _setup_internal_error("Failed to cancel auth setup", e)


@auth_blueprint.route('/setup/status/<session_id>', methods=['GET'])
def get_setup_status(session_id: str) -> ResponseReturnValue:
    """
    Get resumable progress of an auth setup attempt.
    
    Args:
        session_id: Session ID to check
        
    Returns:
        JSON response with the attempt's progress. Unknown attempts (for
        example after a restart) report exists=false with SETUP_NOT_FOUND.
    """
    if not _setup_allowed():
        return _setup_denied_response()
    try:
        return _setup_json({'success': True, 'data': oauth_manager.get_session_status(session_id)})

    except Exception as e:
        return _setup_internal_error("Failed to get setup status", e)


# Experimental Mac helper. The helper authenticates with a short-lived
# handoff bound to one attempt, never with the app API key, and never
# learns the session ID or any Tesla token.

HANDOFF_HEADER = 'X-PowerNight-Handoff'


def _helper_error_response(error: SetupError) -> Response:
    body: Dict[str, Any] = {'success': False, 'error_code': str(error.code), 'error': error.message}
    if error.progress is not None:
        body['step'] = error.progress.get('step')
    return _setup_json(body, error.http_status)


@auth_blueprint.route('/setup/handoff', methods=['POST'])
def create_helper_handoff() -> ResponseReturnValue:
    """
    Create a Mac helper handoff for an attempt that is waiting for sign-in.

    Body:
        {"session_id": "session-id"}
    """
    if not _setup_allowed():
        return _setup_denied_response()
    try:
        session_id = _request_json().get('session_id')
        if not session_id:
            return _invalid_setup_input('Session ID is required')
        try:
            handoff = oauth_manager.create_handoff(str(session_id))
        except SetupError as error:
            return _setup_error_response(error)
        return _setup_json({'success': True, **handoff})

    except Exception as e:
        return _setup_internal_error("Failed to create Mac helper handoff", e)


@auth_blueprint.route('/setup/helper/authorization', methods=['GET'])
def helper_authorization() -> ResponseReturnValue:
    """Give the Mac helper the Tesla sign-in URL for its attempt."""
    try:
        try:
            data = oauth_manager.helper_authorization(request.headers.get(HANDOFF_HEADER))
        except SetupError as error:
            return _helper_error_response(error)
        return _setup_json({'success': True, **data})

    except Exception as e:
        return _setup_internal_error("Failed to serve Mac helper authorization", e)


@auth_blueprint.route('/setup/helper/callback', methods=['POST'])
def helper_callback() -> ResponseReturnValue:
    """
    Accept the tesla://auth/callback the Mac helper captured.

    Body:
        {"callback_url": "tesla://auth/callback?code=...&state=..."}
    """
    try:
        callback_url = _request_json().get('callback_url')
        if not isinstance(callback_url, str) or not callback_url.strip():
            return _invalid_setup_input('Callback URL is required')
        try:
            outcome = oauth_manager.helper_submit_callback(
                request.headers.get(HANDOFF_HEADER), callback_url
            )
        except SetupError as error:
            return _helper_error_response(error)
        progress = outcome.progress
        return _setup_json({
            'success': True,
            'step': progress['step'],
            'error_code': progress['error_code'],
            'error': progress['error'],
        }, outcome.http_status)

    except Exception as e:
        return _setup_internal_error("Failed to process Mac helper callback", e)


@auth_blueprint.route('/tesla/logout', methods=['POST'])
@require_auth
def logout() -> ResponseReturnValue:
    """
    Logout and revoke Tesla tokens.
    
    Returns:
        JSON response with logout result
    """
    try:
        success = oauth_manager.revoke_tokens()
        
        if success:
            connector = _shared_connector()
            if connector is not None:
                connector.disconnect()
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
            'error': 'Internal server error',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@auth_blueprint.route('/tesla/powerwalls', methods=['GET'])
@require_auth
def get_powerwalls() -> ResponseReturnValue:
    """
    Test pypowerwall connection and get basic Powerwall info.
    
    Returns:
        JSON response with Powerwall connection test result
    """
    try:
        # A missing Tesla login is an expected state on a fresh install,
        # not a server error
        if not oauth_manager.auth_storage.has_auth_data():
            return jsonify({
                'success': False,
                'error': 'No Tesla authentication configured',
                'code': 'TESLA_AUTH_REQUIRED',
                'connection_state': 'sign_in_required',
                'message': 'Connect or reconnect your Tesla account in Settings.',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 503

        # Reuse the shared session: a new one would need a fresh Tesla login
        try:
            with _shared_cloud_session() as pw:
                result = oauth_manager.describe_powerwall(pw)
        except Exception as connection_error:
            result = {'success': False, 'error': _shared_connection_status().get('connection_error')
                      or f'Tesla cloud connection failed ({type(connection_error).__name__})'}

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
                'connection_state': _connection_state_payload().get('connection_state'),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 502
        
    except Exception as e:
        logger.log_error(ComponentType.WEB, "Failed to test Powerwall connection", e)
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


@auth_blueprint.route('/tesla/test-connection', methods=['POST'])
@require_auth
def test_connection() -> ResponseReturnValue:
    """
    Test pypowerwall cloud mode connection.
    
    Returns:
        JSON response with connection test result
    """
    try:
        if not oauth_manager.auth_storage.has_auth_data():
            return jsonify({
                'success': False,
                'error': 'No Tesla authentication configured',
                'code': 'TESLA_AUTH_REQUIRED',
                'connection_state': 'sign_in_required',
                'message': 'Connect or reconnect your Tesla account in Settings.',
                'data': {
                    'api_accessible': False,
                    'connection_type': 'pypowerwall_cloud',
                    **_connection_state_payload(),
                },
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 503

        # Do not force a reconnect: dropping a healthy session would need a
        # fresh Tesla login token to start a new one
        _connect_shared_connector()
        connection_status = _connection_state_payload()
        return jsonify({
            'success': True,
            'message': 'Tesla cloud connection successful',
            'data': {
                'api_accessible': True,
                'connection_type': 'pypowerwall_cloud',
                **connection_status,
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
    except Exception as e:
        logger.log_error(ComponentType.WEB, "Connection test failed", e)
        connection_status = _connection_state_payload()
        return jsonify({
            'success': False,
            'error': connection_status.get('connection_error') or (
                'Tesla cloud connection failed. Check Settings and the container logs.'
            ),
            'data': {
                'api_accessible': False,
                'connection_type': 'pypowerwall_cloud',
                **connection_status,
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 502


def _site_details_response(pw: Any, auth_data: Dict[str, Any]) -> ResponseReturnValue:
    """Collect site details from a live pypowerwall session."""
    # Get comprehensive site data using multiple pypowerwall methods
    site_data: Dict[str, Any] = {}
    
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


@auth_blueprint.route('/site-details', methods=['GET'])
@require_auth
def get_site_details() -> ResponseReturnValue:
    """
    Get detailed information for the authenticated energy site using pypowerwall.

    Returns:
        JSON response with comprehensive site details from multiple pypowerwall methods
    """
    try:
        if not oauth_manager.has_credentials():
            return jsonify({
                'success': False,
                'error': 'No valid authentication token available',
                'code': 'TESLA_AUTH_REQUIRED',
                'connection_state': 'sign_in_required',
                'message': 'Connect or reconnect your Tesla account in Settings.',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 503

        # Load auth data to get site info
        auth_data = oauth_manager.auth_storage.load_auth_data()
        if not auth_data or 'site' not in auth_data or auth_data['site'] is None:
            return jsonify({
                'success': False,
                'error': 'No site information available',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 404

        # Reuse the shared session (a new one would need a fresh Tesla login)
        # and hold it for the whole request so scheduled commands never run
        # on the same client concurrently. The helper handles its own errors,
        # so anything caught here comes from acquiring the session.
        try:
            with _shared_cloud_session() as pw:
                return _site_details_response(pw, auth_data)
        except Exception as connection_error:
            logger.log_error(ComponentType.WEB, "Tesla cloud session unavailable for site details", connection_error)
            connection = _connection_state_payload()
            return jsonify({
                'success': False,
                'error': connection.get('connection_error')
                or 'Tesla cloud connection failed. Check Settings and the container logs.',
                'connection_state': connection.get('connection_state'),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 502

    except Exception as e:
        logger.log_error(ComponentType.WEB, "Failed to fetch site details", e)
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500
