"""
Classify the Tesla connection for the UI from backend evidence only.

"Sign-in required" is reserved for evidence that the stored sign-in itself is
missing or was rejected. Any other failure is reported as temporarily
unavailable, so a network blip never asks the user to sign in again.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Mapping, Optional


ConnectionState = Literal['connected', 'sign_in_required', 'temporarily_unavailable', 'checking']


@dataclass(frozen=True)
class ConnectionAssessment:
    state: ConnectionState
    reason: str


def _expiry_timestamp(value: Any) -> Optional[float]:
    """Stored access-token expiry as a UNIX timestamp, or None when unknown."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
        except ValueError:
            return None
    return None


def classify_connection_state(*, has_auth_file: bool, auth_data: Optional[Mapping[str, Any]],
                              connection: Mapping[str, Any], now: float) -> ConnectionAssessment:
    """
    Rules, first match wins:

    1. No auth file: sign-in required.
    2. Auth file unreadable, or without email or tokens: sign-in required.
    3. Live session connected: connected.
    4. Tesla rejected the stored sign-in (typed error or pypowerwall's own
       rejection log line, kept through circuit-breaker opens): sign-in required.
    5. A connection attempt failed and the stored access token has explicitly
       expired. Tesla rejects refreshed tokens on a new session, so a new
       session needs a fresh sign-in (the ~8 hour limitation): sign-in required.
    6. No connection attempt yet: checking.
    7. Anything else: temporarily unavailable.
    """
    if not has_auth_file:
        return ConnectionAssessment('sign_in_required', 'no_credentials')
    if not auth_data or not auth_data.get('email') or not (
        auth_data.get('access_token') or auth_data.get('refresh_token')
    ):
        return ConnectionAssessment('sign_in_required', 'credentials_unreadable')
    if connection.get('connected'):
        return ConnectionAssessment('connected', 'connected')
    if connection.get('auth_rejected'):
        return ConnectionAssessment('sign_in_required', 'tesla_rejected_sign_in')

    attempted = bool(connection.get('last_connection_attempt'))
    expires_at = _expiry_timestamp(auth_data.get('expires_at'))
    if attempted and expires_at is not None and expires_at <= now:
        return ConnectionAssessment('sign_in_required', 'access_token_expired')
    if not attempted:
        return ConnectionAssessment('checking', 'not_checked')
    return ConnectionAssessment(
        'temporarily_unavailable', str(connection.get('connection_error_code') or 'connection')
    )
