"""
PowerNight Web API Authentication

Authentication and authorization functions for the web API.
"""

import base64
import hmac
import os
from functools import wraps
from typing import Optional
from flask import request, current_app

from .errors import AuthenticationError, AuthorizationError
from ...core.config import get_config


def require_auth(f):
    """
    Decorator to require authentication for API endpoints.

    Supports multiple authentication methods:
    - API Key via X-API-Key header
    - HTTP Basic Authentication
    - Optional authentication (can be disabled in config)
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            config = get_config()

            # Check if authentication is disabled (visible in logs so an
            # open deployment is a deliberate choice, not a surprise)
            if not config.web_interface.auth_enabled:
                _warn_auth_disabled_once()
                return f(*args, **kwargs)

            # Try different authentication methods
            auth_result = (
                _check_api_key_auth() or
                _check_bearer_auth() or
                _check_basic_auth() or
                _check_no_auth_required()
            )

            if not auth_result:
                current_app.logger.warning(
                    f"Authentication failed for {request.remote_addr} - {request.method} {request.path}"
                )
                raise AuthenticationError("Authentication required")

            return f(*args, **kwargs)

        except AuthenticationError:
            raise
        except Exception as e:
            current_app.logger.error(f"Authentication error: {e}")
            raise AuthenticationError("Authentication failed")

    return decorated_function


def _check_api_key_auth() -> bool:
    """
    Check API key authentication via X-API-Key header.

    Returns:
        True if authenticated successfully, False otherwise
    """
    try:
        config = get_config()

        # Get API key from header
        provided_key = request.headers.get('X-API-Key')
        if not provided_key:
            return False

        # Get configured API key
        configured_key = config.web_interface.api_key
        if not configured_key:
            return False

        # Compare keys (constant-time comparison to prevent timing attacks)
        return _constant_time_compare(provided_key, configured_key)

    except Exception:
        return False


def _check_bearer_auth() -> bool:
    """
    Check Bearer token authentication via Authorization header.

    Returns:
        True if authenticated successfully, False otherwise
    """
    try:
        config = get_config()

        # Get authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return False

        # Extract token
        token = auth_header[7:]  # Remove 'Bearer ' prefix
        if not token:
            return False

        # Get configured API key
        configured_key = config.web_interface.api_key
        if not configured_key:
            return False

        # Compare token with API key (constant-time comparison)
        return _constant_time_compare(token, configured_key)

    except Exception:
        return False


def _check_basic_auth() -> bool:
    """
    Check HTTP Basic Authentication.

    Returns:
        True if authenticated successfully, False otherwise
    """
    try:
        config = get_config()

        # Get authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Basic '):
            return False

        # Decode credentials
        try:
            credentials = base64.b64decode(auth_header[6:]).decode('utf-8')
            username, password = credentials.split(':', 1)
        except (ValueError, UnicodeDecodeError):
            return False

        # Get configured credentials
        configured_username = config.web_interface.username
        configured_password = config.web_interface.password

        if not configured_username or not configured_password:
            return False

        # Compare credentials
        return (
            _constant_time_compare(username, configured_username) and
            _constant_time_compare(password, configured_password)
        )

    except Exception:
        return False


_auth_disabled_warned = False


def _warn_auth_disabled_once() -> None:
    """Log a single warning when requests are served with auth disabled."""
    global _auth_disabled_warned
    if not _auth_disabled_warned:
        _auth_disabled_warned = True
        current_app.logger.warning(
            "Web authentication is DISABLED (web_interface.auth_enabled=false); "
            "every API endpoint is open to anyone who can reach this port"
        )


def _check_no_auth_required() -> bool:
    """
    Check if no authentication is required for this endpoint.

    Returns:
        True if no authentication is required, False otherwise
    """
    try:
        config = get_config()

        # Liveness probes only; anything with system detail requires auth
        public_endpoints = [
            '/health',         # Health check is always public
            '/version'         # Version info is always public
        ]

        return request.path in public_endpoints or not config.web_interface.auth_enabled

    except Exception:
        return False


def _constant_time_compare(a: str, b: str) -> bool:
    """
    Compare two strings in constant time to prevent timing attacks.

    Args:
        a: First string
        b: Second string

    Returns:
        True if strings are equal, False otherwise
    """
    return hmac.compare_digest(a.encode('utf-8'), b.encode('utf-8'))


def generate_api_key(length: int = 32) -> str:
    """
    Generate a random API key.

    Args:
        length: Length of the API key in bytes

    Returns:
        Base64-encoded API key
    """
    key_bytes = os.urandom(length)
    return base64.b64encode(key_bytes).decode('utf-8')


def get_current_user() -> Optional[str]:
    """
    Get the current authenticated user.

    Returns:
        Username of current user, or None if not authenticated
    """
    try:
        # Check API key authentication
        api_key = request.headers.get('X-API-Key')
        if api_key:
            config = get_config()
            if config.web_interface.api_key and _constant_time_compare(api_key, config.web_interface.api_key):
                return 'api_user'

        # Check Bearer token authentication
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header[7:]
            if token:
                config = get_config()
                if config.web_interface.api_key and _constant_time_compare(token, config.web_interface.api_key):
                    return 'api_user'

        # Check basic authentication
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Basic '):
            try:
                credentials = base64.b64decode(auth_header[6:]).decode('utf-8')
                username, password = credentials.split(':', 1)

                config = get_config()
                if (config.web_interface.username and config.web_interface.password and
                    _constant_time_compare(username, config.web_interface.username) and
                    _constant_time_compare(password, config.web_interface.password)):
                    return username

            except (ValueError, UnicodeDecodeError):
                pass

        return None

    except Exception:
        return None


def require_role(role: str):
    """
    Decorator to require specific role for API endpoints.

    Args:
        role: Required role (currently only 'admin' is supported)
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            current_user = get_current_user()
            if not current_user:
                raise AuthenticationError("Authentication required")

            # For now, all authenticated users have admin role
            # This can be extended later for more granular permissions
            if role == 'admin' and current_user:
                return f(*args, **kwargs)

            raise AuthorizationError(f"Role '{role}' required")

        return decorated_function
    return decorator