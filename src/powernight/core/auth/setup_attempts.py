"""
In-memory Tesla sign-in attempts: steps, stable error codes and callback parsing.

An attempt holds the PKCE verifier and, after the code exchange, the pending
Tesla tokens until the user picks an energy site. Secrets never leave the
server: ``TeslaOAuthManager`` serializes attempts for the browser only through
its progress view, which omits every field marked secret here.
"""

import hashlib
import re
import threading
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Dict, FrozenSet, List, Literal, Optional, Set


class SetupErrorCode(StrEnum):
    """Stable, machine-readable reasons a setup request failed."""

    INVALID_INPUT = 'INVALID_INPUT'
    STATE_MISMATCH = 'STATE_MISMATCH'
    SETUP_NOT_FOUND = 'SETUP_NOT_FOUND'
    SETUP_EXPIRED = 'SETUP_EXPIRED'
    SETUP_CANCELLED = 'SETUP_CANCELLED'
    WRONG_STEP = 'WRONG_STEP'
    TESLA_DENIED = 'TESLA_DENIED'
    EXCHANGE_FAILED = 'EXCHANGE_FAILED'
    SITE_DISCOVERY_UNAVAILABLE = 'SITE_DISCOVERY_UNAVAILABLE'
    NO_ENERGY_SITES = 'NO_ENERGY_SITES'
    INVALID_SITE = 'INVALID_SITE'
    CREDENTIAL_WRITE_FAILED = 'CREDENTIAL_WRITE_FAILED'
    HANDOFF_INVALID = 'HANDOFF_INVALID'
    INTERNAL_ERROR = 'INTERNAL_ERROR'


SetupStep = Literal[
    'awaiting_callback', 'exchanging', 'discovering_sites', 'selecting_site',
    'completing', 'complete', 'failed', 'cancelled', 'expired',
]
SetupSource = Literal['browser', 'token_import']
HelperState = Literal['none', 'pending', 'opened', 'submitted']

# Steps after which the attempt can no longer change or write credentials
ENDED_STEPS: FrozenSet[str] = frozenset({'failed', 'cancelled', 'expired'})
# Steps a background request is working on; duplicates get the current progress
BUSY_STEPS: FrozenSet[str] = frozenset({'exchanging', 'discovering_sites', 'completing'})

AUTHORIZATION_URL_HINT = (
    'This is the sign-in page, not the returned login result. The embedded redirect '
    'address does not contain your authorization code.'
)
MISSING_CALLBACK_MESSAGE = (
    'Missing authorization code or state parameter. Paste the tesla://auth/callback '
    'link that contains "code=" and "state=".'
)
SESSION_NOT_FOUND_MESSAGE = (
    'This sign-in session is no longer available. PowerNight may have restarted. '
    'Start the sign-in again.'
)
SETUP_EXPIRED_MESSAGE = 'This sign-in attempt expired after 10 minutes. Start the sign-in again.'
SETUP_CANCELLED_MESSAGE = 'This sign-in attempt was cancelled.'

MAX_CALLBACK_TEXT = 8192
_SESSION_ID = re.compile(r'^[A-Za-z0-9_-]{20,128}$')
# Value characters stop at separators, whitespace, quotes (including the
# curly quotes some consoles print) and angle brackets
_VALUE = r'[^&#\s\'"“”‘’<>]+'
_CALLBACK_SEGMENT = re.compile(r'tesla://auth/callback(\?[^\s\'"“”‘’<>]*)')
_PARAM = re.compile(rf'[?&#](code|state|error)=({_VALUE})')
_AUTHORIZE_URL = re.compile(r'auth\.tesla\.(?:com|cn)/oauth2/v3/authorize', re.IGNORECASE)
_SAFE_ERROR = re.compile(r'^[A-Za-z0-9_.-]{1,64}$')


def is_valid_session_id(session_id: Any) -> bool:
    """Return True for strings shaped like the IDs this server issues."""
    return isinstance(session_id, str) and bool(_SESSION_ID.match(session_id))


def digest(value: str) -> str:
    """One-way fingerprint for codes, states and handoff tokens."""
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class ParsedCallback:
    """What a pasted text turned out to be."""

    kind: Literal['callback', 'authorization_url', 'tesla_error', 'unknown']
    code: Optional[str] = field(default=None, repr=False)
    state: Optional[str] = field(default=None, repr=False)
    error: Optional[str] = None


def _params(text: str) -> Dict[str, str]:
    """Collect code/state/error, letting the last occurrence of each win."""
    params: Dict[str, str] = {}
    for name, value in _PARAM.findall(text):
        params[name] = urllib.parse.unquote(value)
    return params


def extract_callback_params(text: str) -> Dict[str, str]:
    """Return code/state/error from the last tesla:// callback in ``text``."""
    segments = _CALLBACK_SEGMENT.findall(text)
    return _params(segments[-1] if segments else text)


def _is_authorization_url(text: str) -> bool:
    if _CALLBACK_SEGMENT.search(text):
        return False
    return bool(_AUTHORIZE_URL.search(text)) or (
        'code_challenge=' in text and not re.search(r'[?&#]code=', text)
    )


def parse_callback_text(text: Any) -> ParsedCallback:
    """
    Classify pasted text: a tesla://auth/callback result (bare, or inside a
    console or Network line), Tesla's sign-in page URL, a Tesla error, or noise.
    """
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_CALLBACK_TEXT:
        return ParsedCallback('unknown')
    if _is_authorization_url(text):
        return ParsedCallback('authorization_url')

    params = extract_callback_params(text)

    if params.get('error'):
        error = params['error'] if _SAFE_ERROR.match(params['error']) else 'unknown_error'
        return ParsedCallback('tesla_error', state=params.get('state'), error=error)
    if params.get('code') and params.get('state'):
        return ParsedCallback('callback', code=params['code'], state=params['state'])
    return ParsedCallback('unknown')


@dataclass(repr=False)
class PendingTokens:
    """Tokens from a fresh Tesla sign-in, held until the site is chosen."""

    access_token: str
    refresh_token: Optional[str]
    expires_at: str
    token_type: str = 'Bearer'
    scope: str = 'openid email offline_access'

    def __repr__(self) -> str:
        return 'PendingTokens(<redacted>)'

    def as_storage_dict(self) -> Dict[str, Any]:
        return {
            'access_token': self.access_token,
            'refresh_token': self.refresh_token,
            'expires_at': self.expires_at,
            'token_type': self.token_type,
            'scope': self.scope,
        }


@dataclass
class SetupAttempt:
    """One sign-in attempt. Guard every read and write with ``lock``."""

    id: str
    email: str
    source: SetupSource
    created_at: datetime
    expires_at: datetime
    step: SetupStep
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)
    # Fingerprint of the OAuth state, kept to recognize duplicate callbacks
    state_digest: Optional[str] = field(default=None, repr=False)
    # Secrets: never serialized, wiped when the attempt ends
    code_verifier: Optional[str] = field(default=None, repr=False)
    tokens: Optional[PendingTokens] = field(default=None, repr=False)
    handoff_digest: Optional[str] = field(default=None, repr=False)
    # Only shown while awaiting the callback; it carries the state value
    auth_url: Optional[str] = field(default=None, repr=False)
    claimed_code_digest: Optional[str] = field(default=None, repr=False)
    failed_code_digests: Set[str] = field(default_factory=set, repr=False)
    exchange_attempts: int = 0
    token_expires_at: Optional[str] = None
    sites: Optional[List[Dict[str, Any]]] = None
    selected_site_id: Optional[str] = None
    error_code: Optional[SetupErrorCode] = None
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    helper_state: HelperState = 'none'
    ended_at: Optional[datetime] = None
    timer: Optional[threading.Timer] = field(default=None, repr=False, compare=False)

    def wipe_secrets(self) -> None:
        self.code_verifier = None
        self.tokens = None
        self.handoff_digest = None
        self.auth_url = None


class SetupError(Exception):
    """A setup request failed with a stable code and a user-facing message."""

    def __init__(self, code: SetupErrorCode, message: str, http_status: int,
                 progress: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.progress = progress


@dataclass(frozen=True)
class SetupOutcome:
    """Progress after a setup request. ``duplicate`` means nothing new ran."""

    progress: Dict[str, Any]
    http_status: int = 200
    duplicate: bool = False


class SiteDiscoveryError(Exception):
    """Listing energy sites failed; ``rejected`` means Tesla refused the token."""

    def __init__(self, rejected: bool, status: Optional[int] = None) -> None:
        super().__init__(
            f'Tesla energy site discovery failed (HTTP {status})' if status
            else 'Tesla energy site discovery failed'
        )
        self.rejected = rejected
        self.status = status


class TokenResponseError(ValueError):
    """Tesla answered the code exchange with an unusable token response."""
