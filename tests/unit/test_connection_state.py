"""The Tesla connection state shown in Settings must follow backend evidence only."""

import pytest

from powernight.core.auth.connection_state import classify_connection_state


pytestmark = pytest.mark.unit

NOW = 1_800_000_000.0
CREDENTIALS = {'email': 'owner@example.com', 'access_token': 'at', 'refresh_token': 'rt', 'expires_at': NOW + 3600}
ATTEMPTED = '2026-10-21T12:00:00+00:00'


@pytest.mark.parametrize('has_file, auth_data, connection, state, reason', [
    (False, None, {}, 'sign_in_required', 'no_credentials'),
    (True, None, {}, 'sign_in_required', 'credentials_unreadable'),
    (True, {'email': 'owner@example.com'}, {}, 'sign_in_required', 'credentials_unreadable'),
    (True, {**CREDENTIALS, 'email': None}, {}, 'sign_in_required', 'credentials_unreadable'),
    (True, CREDENTIALS, {'connected': True, 'auth_rejected': True}, 'connected', 'connected'),
    (True, CREDENTIALS, {'connected': False, 'auth_rejected': True, 'last_connection_attempt': ATTEMPTED,
                         'connection_error_code': 'circuit_breaker'},
     'sign_in_required', 'tesla_rejected_sign_in'),
    (True, {**CREDENTIALS, 'expires_at': NOW - 60}, {'connected': False, 'last_connection_attempt': ATTEMPTED,
                                                     'connection_error_code': 'no_response'},
     'sign_in_required', 'access_token_expired'),
    (True, {**CREDENTIALS, 'expires_at': '2020-01-01T00:00:00+00:00'},
     {'connected': False, 'last_connection_attempt': ATTEMPTED, 'connection_error_code': 'no_response'},
     'sign_in_required', 'access_token_expired'),
    # An expired token alone, before any failed attempt, is not evidence
    (True, {**CREDENTIALS, 'expires_at': NOW - 60}, {'connected': False}, 'checking', 'not_checked'),
    # Unknown expiry is never treated as expired
    (True, {**CREDENTIALS, 'expires_at': 'garbage'},
     {'connected': False, 'last_connection_attempt': ATTEMPTED, 'connection_error_code': 'connection'},
     'temporarily_unavailable', 'connection'),
    (True, CREDENTIALS, {'connected': False}, 'checking', 'not_checked'),
    (True, CREDENTIALS, {'connected': False, 'last_connection_attempt': ATTEMPTED,
                         'connection_error_code': 'no_response'},
     'temporarily_unavailable', 'no_response'),
    (True, CREDENTIALS, {'connected': False, 'last_connection_attempt': ATTEMPTED,
                         'connection_error_code': 'circuit_breaker'},
     'temporarily_unavailable', 'circuit_breaker'),
    (True, CREDENTIALS, {'connected': False, 'last_connection_attempt': ATTEMPTED,
                         'connection_error_code': 'tesla_rejected'},
     'temporarily_unavailable', 'tesla_rejected'),
])
def test_classification_rules(has_file, auth_data, connection, state, reason):
    assessment = classify_connection_state(
        has_auth_file=has_file, auth_data=auth_data, connection=connection, now=NOW
    )
    assert (assessment.state, assessment.reason) == (state, reason)
