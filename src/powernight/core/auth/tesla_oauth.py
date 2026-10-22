"""
Tesla OAuth 2.0 authentication manager for pypowerwall compatibility.

Runs the browser sign-in (and the pypowerwall token import) as short-lived,
in-memory setup attempts: PKCE, callback validation, a single code exchange,
energy site discovery and finally saving the credentials in pypowerwall's
format. Pending tokens and the PKCE verifier never leave this process.
"""

import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
from pypowerwall import tesla_auth

from .setup_attempts import (
    AUTHORIZATION_URL_HINT,
    BUSY_STEPS,
    ENDED_STEPS,
    MISSING_CALLBACK_MESSAGE,
    SESSION_NOT_FOUND_MESSAGE,
    SETUP_CANCELLED_MESSAGE,
    SETUP_EXPIRED_MESSAGE,
    PendingTokens,
    SetupAttempt,
    SetupError,
    SetupErrorCode,
    SetupOutcome,
    SetupSource,
    SetupStep,
    SiteDiscoveryError,
    TokenResponseError,
    digest,
    extract_callback_params,
    is_valid_session_id,
    parse_callback_text,
)
from .token_storage import PyPowerwallAuthStorage
from ...utils.logging import get_logger
from ...utils.redaction import safe_error_detail


# Runs a credential write; the connector passes one that holds its session lock
CredentialCommitter = Callable[[Callable[[], None]], None]

EXCHANGE_REJECTED_MESSAGE = (
    'Tesla did not accept this sign-in result. It may have expired or been used already. '
    'Sign in to Tesla again and paste the new link.'
)
EXCHANGE_UNAVAILABLE_MESSAGE = (
    'PowerNight could not reach Tesla to finish signing in. '
    'Sign in to Tesla again and paste the new link.'
)
CODE_ALREADY_USED_MESSAGE = (
    'This sign-in result was already used. Sign in to Tesla again and paste the new link.'
)
TOO_MANY_EXCHANGES_MESSAGE = 'Tesla sign-in failed several times. Start the sign-in again.'
DISCOVERY_REJECTED_MESSAGE = (
    'Tesla rejected the new sign-in while listing your energy sites. Start the sign-in again.'
)
DISCOVERY_UNAVAILABLE_MESSAGE = (
    'PowerNight signed in to Tesla but could not load your energy sites. Try again in a moment.'
)
NO_ENERGY_SITES_MESSAGE = (
    'No Powerwall energy sites were found for this Tesla account. Check that you signed in '
    'with the account that owns the Powerwall, then try again.'
)
CREDENTIAL_WRITE_FAILED_MESSAGE = (
    'PowerNight could not save the new Tesla sign-in. Your previous sign-in was kept. Try again.'
)
IMPORT_REJECTED_MESSAGE = (
    "Tesla rejected the access token. Create a fresh one with "
    "'python -m pypowerwall authtoken' and paste it right away."
)
HANDOFF_INVALID_MESSAGE = (
    'This helper link is no longer valid. Start the Mac helper again from PowerNight Settings.'
)

_EXCHANGE_HTTP_STATUS = re.compile(r'\(HTTP (\d{3})\)')


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _run_now(write: Callable[[], None]) -> None:
    write()


class _DeadlinePassed(Exception):
    """The attempt expired before its credentials could be written."""


def classify_exchange_error(error: BaseException) -> Tuple[str, Optional[int], str]:
    """
    Map a code-exchange failure to (kind, HTTP status, safe message).

    pypowerwall puts Tesla's response body, and sometimes the whole token
    payload, into its exception text, so that text is never passed on.
    """
    if isinstance(error, TokenResponseError):
        return 'invalid_response', None, str(error)
    match = _EXCHANGE_HTTP_STATUS.search(str(error)) if isinstance(error, RuntimeError) else None
    if match:
        status = int(match.group(1))
        if status in (400, 401, 403):
            return 'rejected', status, EXCHANGE_REJECTED_MESSAGE
        return 'unavailable', status, EXCHANGE_UNAVAILABLE_MESSAGE
    if isinstance(error, RuntimeError) and 'No refresh_token' in str(error):
        return 'invalid_response', None, 'Tesla token exchange failed: no refresh token in the response'
    return 'unavailable', None, EXCHANGE_UNAVAILABLE_MESSAGE


class TeslaOAuthManager:
    """
    Manages Tesla OAuth 2.0 authentication flow for pypowerwall cloud mode.

    Implements the same OAuth flow as pypowerwall's terminal setup process,
    including PKCE, callback URL handling, and site selection.
    """

    # Tesla OAuth endpoints
    AUTHORIZATION_URL = "https://auth.tesla.com/oauth2/v3/authorize"
    TOKEN_URL = "https://auth.tesla.com/oauth2/v3/token"
    REVOKE_URL = "https://auth.tesla.com/oauth2/v3/revoke"
    PRODUCTS_URL = "https://owner-api.teslamotors.com/api/1/products"

    # OAuth scopes matching pypowerwall
    SCOPES = [
        "openid",
        "email",
        "offline_access"
    ]

    # Client ID matching pypowerwall
    CLIENT_ID = "ownerapi"

    # Tesla only accepts the native-app redirect for the ownerapi client. A
    # browser cannot open tesla://, so the user copies the URL it was sent to.
    REDIRECT_URI = tesla_auth.REDIRECT_URI

    # Code-exchange access tokens are valid for about 8 hours
    DEFAULT_ACCESS_TOKEN_LIFETIME = 28800

    # Setup attempts: lifetime, how many may run at once, how long ended ones
    # are remembered (without secrets) so status can explain what happened
    SETUP_TTL = timedelta(minutes=10)
    MAX_LIVE_ATTEMPTS = 20
    TOMBSTONE_TTL = timedelta(hours=1)
    MAX_TOMBSTONES = 200
    MAX_EXCHANGE_ATTEMPTS = 3

    def __init__(self, storage_path: Optional[str] = None, *,
                 clock: Callable[[], datetime] = _utcnow,
                 expiry_timers: bool = True) -> None:
        """
        Initialize Tesla OAuth manager.

        Args:
            storage_path: Path to store pypowerwall auth files. If None, uses environment variable or default.
            clock: Source of the current UTC time (tests pass a fake clock)
            expiry_timers: Wipe attempt secrets on a timer once they expire
        """
        self.logger = get_logger()
        self.auth_storage = PyPowerwallAuthStorage(storage_path)
        self._clock = clock
        self._expiry_timers = expiry_timers
        # Lock order: registry, then attempt. The connector's session lock may
        # be held while taking an attempt lock, never the other way round.
        self._registry_lock = threading.Lock()
        self._attempts: Dict[str, SetupAttempt] = {}
        self._handoffs: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Attempt registry
    # ------------------------------------------------------------------

    def _new_attempt(self, email: str, source: SetupSource, step: SetupStep) -> SetupAttempt:
        now = self._clock()
        return SetupAttempt(
            id=secrets.token_urlsafe(32),
            email=email,
            source=source,
            created_at=now,
            expires_at=now + self.SETUP_TTL,
            step=step,
        )

    def _register(self, attempt: SetupAttempt) -> None:
        """Add an attempt, ending the oldest live one when too many are open."""
        with self._registry_lock:
            self._prune_locked()
            live = [a for a in self._attempts.values()
                    if a.ended_at is None and a.step != 'completing']
            if len(live) >= self.MAX_LIVE_ATTEMPTS:
                oldest = min(live, key=lambda a: a.created_at)
                with oldest.lock:
                    if oldest.ended_at is None and oldest.step != 'completing':
                        self._end(oldest, 'cancelled', SetupErrorCode.SETUP_CANCELLED,
                                  'This sign-in attempt was replaced by a newer one.')
            self._attempts[attempt.id] = attempt
        self._schedule_expiry(attempt)

    def _prune_locked(self) -> int:
        """Expire overdue attempts and forget old ended ones. Registry lock held."""
        now = self._clock()
        expired = 0
        for attempt in list(self._attempts.values()):
            if attempt.ended_at is None and now >= attempt.expires_at:
                with attempt.lock:
                    if self._enforce_deadline(attempt):
                        expired += 1
        ended = sorted(
            (a for a in self._attempts.values() if a.ended_at is not None),
            key=lambda a: a.ended_at or now,
        )
        overflow = max(0, len(ended) - self.MAX_TOMBSTONES)
        for index, attempt in enumerate(ended):
            if index < overflow or (attempt.ended_at and now - attempt.ended_at > self.TOMBSTONE_TTL):
                del self._attempts[attempt.id]
        for token_digest, attempt_id in list(self._handoffs.items()):
            owner = self._attempts.get(attempt_id)
            if owner is None or owner.handoff_digest != token_digest:
                del self._handoffs[token_digest]
        return expired

    def _schedule_expiry(self, attempt: SetupAttempt) -> None:
        if not self._expiry_timers:
            return
        delay = max(0.0, (attempt.expires_at - self._clock()).total_seconds()) + 1.0
        timer = threading.Timer(delay, self._expire, args=(attempt.id,))
        timer.daemon = True
        with attempt.lock:
            attempt.timer = timer
        timer.start()

    def _expire(self, session_id: str) -> None:
        with self._registry_lock:
            attempt = self._attempts.get(session_id)
        if attempt is not None:
            with attempt.lock:
                self._enforce_deadline(attempt)

    def _get(self, session_id: Any) -> SetupAttempt:
        if is_valid_session_id(session_id):
            with self._registry_lock:
                attempt = self._attempts.get(session_id)
            if attempt is not None:
                return attempt
        raise SetupError(SetupErrorCode.SETUP_NOT_FOUND, SESSION_NOT_FOUND_MESSAGE, 404)

    # ------------------------------------------------------------------
    # Attempt state helpers (attempt lock held)
    # ------------------------------------------------------------------

    def _enforce_deadline(self, attempt: SetupAttempt) -> bool:
        """Expire the attempt once its ten minutes are up. Returns True if it did."""
        if (attempt.ended_at is None and attempt.step != 'completing'
                and self._clock() >= attempt.expires_at):
            self._end(attempt, 'expired', SetupErrorCode.SETUP_EXPIRED, SETUP_EXPIRED_MESSAGE)
            return True
        return False

    def _end(self, attempt: SetupAttempt, step: SetupStep,
             code: Optional[SetupErrorCode], message: Optional[str]) -> None:
        attempt.step = step
        attempt.error_code = code
        attempt.error = message
        attempt.ended_at = self._clock()
        attempt.wipe_secrets()
        if attempt.timer is not None:
            attempt.timer.cancel()
            attempt.timer = None

    def _ended_error(self, attempt: SetupAttempt) -> SetupError:
        default_code = {
            'expired': SetupErrorCode.SETUP_EXPIRED,
            'cancelled': SetupErrorCode.SETUP_CANCELLED,
        }.get(attempt.step, SetupErrorCode.EXCHANGE_FAILED)
        default_message = {
            'expired': SETUP_EXPIRED_MESSAGE,
            'cancelled': SETUP_CANCELLED_MESSAGE,
        }.get(attempt.step, TOO_MANY_EXCHANGES_MESSAGE)
        return SetupError(attempt.error_code or default_code, attempt.error or default_message,
                          410, self._progress(attempt))

    def _stale_error(self, attempt: SetupAttempt) -> SetupError:
        """The attempt moved on while a request was talking to Tesla."""
        if attempt.step in ENDED_STEPS:
            return self._ended_error(attempt)
        return SetupError(
            SetupErrorCode.WRONG_STEP,
            'This sign-in attempt changed while PowerNight was talking to Tesla. Check its status.',
            409, self._progress(attempt),
        )

    @staticmethod
    def _state_matches(attempt: SetupAttempt, state: str) -> bool:
        return attempt.state_digest is not None and hmac.compare_digest(
            attempt.state_digest, digest(state)
        )

    def _progress(self, attempt: SetupAttempt) -> Dict[str, Any]:
        """The only view of an attempt that leaves the server: no tokens, verifier or state."""
        now = self._clock()
        remaining = 0 if attempt.ended_at else int((attempt.expires_at - now).total_seconds())
        return {
            'session_id': attempt.id,
            'step': attempt.step,
            'source': attempt.source,
            'email': attempt.email,
            'created_at': attempt.created_at.isoformat(),
            'setup_expires_at': attempt.expires_at.isoformat(),
            'setup_expires_in_seconds': max(0, remaining),
            'auth_url': attempt.auth_url if attempt.step == 'awaiting_callback' else None,
            'token_expires_at': attempt.token_expires_at,
            'sites': [dict(site) for site in attempt.sites] if attempt.sites is not None else None,
            'selected_site_id': attempt.selected_site_id,
            'error_code': str(attempt.error_code) if attempt.error_code else None,
            'error': attempt.error,
            'credentials_saved': attempt.step == 'complete',
            'helper_state': attempt.helper_state,
        }

    # ------------------------------------------------------------------
    # Browser sign-in
    # ------------------------------------------------------------------

    def _build_auth_url(self, email: str, state: str, code_verifier: str) -> str:
        params = {
            'response_type': 'code',
            'client_id': self.CLIENT_ID,
            'redirect_uri': self.REDIRECT_URI,
            'scope': ' '.join(self.SCOPES),
            'state': state,
            'code_challenge': self._generate_code_challenge(code_verifier),
            'code_challenge_method': 'S256',
            'login_hint': email,
        }
        return f"{self.AUTHORIZATION_URL}?{urllib.parse.urlencode(params)}"

    def start_setup(self, email: str) -> Dict[str, Any]:
        """Start a browser sign-in attempt and return its progress (incl. auth_url)."""
        attempt = self._new_attempt(email, 'browser', 'awaiting_callback')
        code_verifier = secrets.token_urlsafe(32)  # 43 chars, matching pypowerwall
        state = secrets.token_urlsafe(32)
        attempt.code_verifier = code_verifier
        attempt.state_digest = digest(state)
        attempt.auth_url = self._build_auth_url(email, state, code_verifier)
        self._register(attempt)
        self.logger.info(f"Generated Tesla authorization URL for {email}")
        with attempt.lock:
            return self._progress(attempt)

    def generate_auth_url(self, email: str) -> Dict[str, str]:
        """
        Generate Tesla authorization URL for pypowerwall-compatible OAuth flow.

        Args:
            email: Tesla account email

        Returns:
            Dictionary containing auth_url and session_id
        """
        progress = self.start_setup(email)
        return {'auth_url': progress['auth_url'], 'session_id': progress['session_id']}

    def submit_callback(self, session_id: str, text: str) -> SetupOutcome:
        """
        Validate a pasted callback and exchange its code exactly once.

        The attempt lock only guards state changes; the Tesla requests run
        without it, so a duplicate submission gets the current progress (202)
        instead of waiting for the first one.

        Raises:
            SetupError: With a stable code, HTTP status and the current progress
        """
        parsed = parse_callback_text(text)
        attempt = self._get(session_id)
        with attempt.lock:
            self._enforce_deadline(attempt)
            if attempt.step in ENDED_STEPS:
                raise self._ended_error(attempt)
            if parsed.kind == 'authorization_url':
                raise SetupError(SetupErrorCode.INVALID_INPUT, AUTHORIZATION_URL_HINT, 400,
                                 self._progress(attempt))
            if parsed.kind == 'unknown':
                raise SetupError(SetupErrorCode.INVALID_INPUT, MISSING_CALLBACK_MESSAGE, 400,
                                 self._progress(attempt))
            if parsed.state is not None and not self._state_matches(attempt, parsed.state):
                raise SetupError(
                    SetupErrorCode.STATE_MISMATCH,
                    'Invalid state parameter: this link belongs to a different sign-in attempt. '
                    'Open Tesla sign-in again from this page.',
                    400, self._progress(attempt),
                )
            if attempt.step in BUSY_STEPS:
                return SetupOutcome(self._progress(attempt), 202, duplicate=True)
            if attempt.step != 'awaiting_callback':
                return SetupOutcome(self._progress(attempt), 200, duplicate=True)
            if parsed.kind == 'tesla_error':
                raise SetupError(
                    SetupErrorCode.TESLA_DENIED,
                    f'OAuth error: {parsed.error}. Tesla sign-in was not completed. '
                    'Open Tesla sign-in and try again.',
                    400, self._progress(attempt),
                )
            code = parsed.code or ''
            code_digest = digest(code)
            if code_digest in attempt.failed_code_digests:
                raise SetupError(SetupErrorCode.EXCHANGE_FAILED, CODE_ALREADY_USED_MESSAGE, 400,
                                 self._progress(attempt))
            code_verifier = attempt.code_verifier
            if code_verifier is None:
                raise SetupError(SetupErrorCode.INTERNAL_ERROR,
                                 'This sign-in attempt cannot continue. Start the sign-in again.',
                                 500, self._progress(attempt))
            attempt.step = 'exchanging'
            attempt.claimed_code_digest = code_digest
            attempt.exchange_attempts += 1
            attempt.error_code = None
            attempt.error = None

        try:
            token_data = self._exchange_code_for_tokens(code, code_verifier)
        except Exception as error:
            kind, status, message = classify_exchange_error(error)
            self.logger.warning(
                f"Tesla code exchange failed: {kind} ({type(error).__name__}"
                f"{f', HTTP {status}' if status else ''})"
            )
            with attempt.lock:
                self._enforce_deadline(attempt)
                if attempt.step != 'exchanging' or attempt.claimed_code_digest != code_digest:
                    raise self._stale_error(attempt)
                attempt.failed_code_digests.add(code_digest)
                attempt.claimed_code_digest = None
                if attempt.exchange_attempts >= self.MAX_EXCHANGE_ATTEMPTS:
                    self._end(attempt, 'failed', SetupErrorCode.EXCHANGE_FAILED, TOO_MANY_EXCHANGES_MESSAGE)
                    raise self._ended_error(attempt)
                attempt.step = 'awaiting_callback'
                attempt.error_code = SetupErrorCode.EXCHANGE_FAILED
                attempt.error = message
                raise SetupError(SetupErrorCode.EXCHANGE_FAILED, message,
                                 400 if kind == 'rejected' else 502, self._progress(attempt))

        with attempt.lock:
            self._enforce_deadline(attempt)
            if attempt.step != 'exchanging' or attempt.claimed_code_digest != code_digest:
                raise self._stale_error(attempt)
            attempt.tokens = PendingTokens(
                access_token=token_data['access_token'],
                refresh_token=token_data.get('refresh_token'),
                expires_at=token_data['expires_at'],
                scope=token_data.get('scope') or 'openid email offline_access',
            )
            attempt.token_expires_at = token_data['expires_at']
            attempt.code_verifier = None
            attempt.claimed_code_digest = None
            attempt.step = 'discovering_sites'
            access_token = attempt.tokens.access_token
        self.logger.info(f"Exchanged Tesla authorization code for {attempt.email}")
        return self._discover_sites(attempt, access_token)

    def _discover_sites(self, attempt: SetupAttempt, access_token: str) -> SetupOutcome:
        """List energy sites for pending tokens, outside the attempt lock."""
        failure: Optional[SiteDiscoveryError] = None
        sites: List[Dict[str, Any]] = []
        try:
            sites = self.get_energy_sites(access_token)
        except SiteDiscoveryError as error:
            failure = error
        except Exception as error:
            self.logger.warning(f"Tesla energy site discovery failed ({type(error).__name__})")
            failure = SiteDiscoveryError(rejected=False)

        with attempt.lock:
            self._enforce_deadline(attempt)
            if attempt.step != 'discovering_sites':
                raise self._stale_error(attempt)
            if failure is not None and failure.rejected:
                self._end(attempt, 'failed', SetupErrorCode.TESLA_DENIED, DISCOVERY_REJECTED_MESSAGE)
                raise SetupError(SetupErrorCode.TESLA_DENIED, DISCOVERY_REJECTED_MESSAGE, 400,
                                 self._progress(attempt))
            attempt.step = 'selecting_site'
            if failure is not None:
                attempt.error_code = SetupErrorCode.SITE_DISCOVERY_UNAVAILABLE
                attempt.error = DISCOVERY_UNAVAILABLE_MESSAGE
                raise SetupError(SetupErrorCode.SITE_DISCOVERY_UNAVAILABLE,
                                 DISCOVERY_UNAVAILABLE_MESSAGE, 502, self._progress(attempt))
            attempt.sites = sites
            if sites:
                attempt.error_code = None
                attempt.error = None
            else:
                attempt.error_code = SetupErrorCode.NO_ENERGY_SITES
                attempt.error = NO_ENERGY_SITES_MESSAGE
            return SetupOutcome(self._progress(attempt), 200)

    def retry_site_discovery(self, session_id: str) -> SetupOutcome:
        """List energy sites again with the pending tokens, without a new exchange."""
        attempt = self._get(session_id)
        with attempt.lock:
            self._enforce_deadline(attempt)
            if attempt.step in ENDED_STEPS:
                raise self._ended_error(attempt)
            if attempt.step in ('exchanging', 'discovering_sites'):
                return SetupOutcome(self._progress(attempt), 202, duplicate=True)
            if attempt.step != 'selecting_site' or attempt.tokens is None:
                raise SetupError(SetupErrorCode.WRONG_STEP,
                                 'Energy sites can only be refreshed after signing in to Tesla.',
                                 409, self._progress(attempt))
            attempt.step = 'discovering_sites'
            access_token = attempt.tokens.access_token
        return self._discover_sites(attempt, access_token)

    def exchange_code_from_callback_url(self, session_id: str, callback_url: str) -> Dict[str, Any]:
        """
        Exchange authorization code from callback URL for tokens.

        Args:
            session_id: Session ID for this auth flow
            callback_url: The tesla://auth/callback URL, or any pasted text
                containing it (e.g. a browser console line)

        Returns:
            Dictionary with token exchange result and sites
        """
        try:
            outcome = self.submit_callback(session_id, callback_url)
        except SetupError as error:
            return {'success': False, 'error': error.message, 'error_code': str(error.code)}
        progress = outcome.progress
        return {
            'success': True,
            'in_progress': outcome.http_status == 202,
            'sites': progress['sites'] or [],
            'expires_at': progress['token_expires_at'],
            'setup_expires_at': progress['setup_expires_at'],
        }

    @staticmethod
    def _parse_callback_params(text: str) -> Dict[str, str]:
        """Extract code, state and error from a pasted callback URL or log line."""
        return extract_callback_params(text or '')

    # ------------------------------------------------------------------
    # Token import (python -m pypowerwall authtoken)
    # ------------------------------------------------------------------

    def import_tokens(self, email: str, refresh_token: str, access_token: str) -> Dict[str, Any]:
        """
        Start a setup session from tokens created by ``python -m pypowerwall authtoken``.

        Tesla only accepts access tokens from a fresh native login, so this is
        the fallback when the browser flow cannot capture the tesla:// redirect.

        Returns:
            Dictionary with session_id and sites on success; ``http_status``
            tells the API how to answer
        """
        refresh_token = (refresh_token or '').strip()
        access_token = (access_token or '').strip()
        if not refresh_token or not access_token:
            return self._import_failure(SetupErrorCode.INVALID_INPUT,
                                        "Both the refresh token and the access token are required", 400)

        expires_at = self._access_token_expiry(access_token)
        if expires_at <= self._clock():
            return self._import_failure(
                SetupErrorCode.INVALID_INPUT,
                "This access token has expired. Run 'python -m pypowerwall authtoken' again.", 400,
            )

        failure: Optional[SiteDiscoveryError] = None
        sites: List[Dict[str, Any]] = []
        try:
            sites = self.get_energy_sites(access_token)
        except SiteDiscoveryError as error:
            failure = error
        except Exception as error:
            self.logger.warning(f"Tesla energy site discovery failed ({type(error).__name__})")
            failure = SiteDiscoveryError(rejected=False)
        if failure is not None and failure.rejected:
            return self._import_failure(SetupErrorCode.TESLA_DENIED, IMPORT_REJECTED_MESSAGE, 400)

        attempt = self._new_attempt(email, 'token_import', 'selecting_site')
        attempt.tokens = PendingTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at.isoformat(),
        )
        attempt.token_expires_at = expires_at.isoformat()
        if failure is not None:
            attempt.error_code = SetupErrorCode.SITE_DISCOVERY_UNAVAILABLE
            attempt.error = DISCOVERY_UNAVAILABLE_MESSAGE
        else:
            attempt.sites = sites
            if not sites:
                attempt.error_code = SetupErrorCode.NO_ENERGY_SITES
                attempt.error = NO_ENERGY_SITES_MESSAGE
        self._register(attempt)
        self.logger.info(f"Imported Tesla tokens for {email}")
        with attempt.lock:
            progress = self._progress(attempt)
        if failure is not None:
            return {
                'success': False,
                'error': DISCOVERY_UNAVAILABLE_MESSAGE,
                'error_code': str(SetupErrorCode.SITE_DISCOVERY_UNAVAILABLE),
                'http_status': 502,
                'session_id': attempt.id,
                'setup': progress,
            }
        return {
            'success': True,
            'http_status': 200,
            'session_id': attempt.id,
            'sites': progress['sites'],
            'expires_at': expires_at.isoformat(),
            'setup_expires_at': progress['setup_expires_at'],
            'setup': progress,
        }

    def _import_failure(self, code: SetupErrorCode, message: str, http_status: int) -> Dict[str, Any]:
        self.logger.error(f"Failed to import Tesla tokens: {code}")
        return {'success': False, 'error': message, 'error_code': str(code), 'http_status': http_status}

    def _access_token_expiry(self, access_token: str) -> datetime:
        """Read the exp claim of a Tesla JWT access token (no signature check)."""
        try:
            payload = access_token.split('.')[1]
            claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
            return datetime.fromtimestamp(int(claims['exp']), timezone.utc)
        except (IndexError, KeyError, TypeError, ValueError):
            return self._clock() + timedelta(seconds=self.DEFAULT_ACCESS_TOKEN_LIFETIME)

    def _generate_code_challenge(self, code_verifier: str) -> str:
        """Generate PKCE code challenge from verifier."""
        digest_bytes = hashlib.sha256(code_verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest_bytes).decode().rstrip('=')

    def get_energy_sites(self, access_token: str) -> List[Dict[str, Any]]:
        """
        Get Tesla Energy sites for the authenticated user.

        Args:
            access_token: Valid Tesla access token

        Returns:
            List of energy sites

        Raises:
            SiteDiscoveryError: Tesla refused the token (``rejected``) or was
                unreachable. Response bodies are never included.
        """
        headers = {
            'Authorization': f'Bearer {access_token}',
            'User-Agent': 'PowerNight/1.0'
        }
        try:
            response = requests.get(self.PRODUCTS_URL, headers=headers, timeout=30)
        except requests.RequestException as error:
            self.logger.warning(f"Failed to get energy sites ({type(error).__name__})")
            raise SiteDiscoveryError(rejected=False) from None

        if response.status_code != 200:
            self.logger.warning(f"Failed to get energy sites: HTTP {response.status_code}")
            raise SiteDiscoveryError(rejected=response.status_code in (401, 403),
                                     status=response.status_code)
        try:
            data = response.json()
        except ValueError:
            self.logger.warning("Failed to get energy sites: response was not JSON")
            raise SiteDiscoveryError(rejected=False, status=response.status_code) from None

        products = data.get('response', []) if isinstance(data, dict) else []

        # Filter for energy products (Powerwalls)
        energy_sites = []
        for product in products if isinstance(products, list) else []:
            if isinstance(product, dict) and product.get('resource_type') == 'battery':
                energy_sites.append({
                    'id': product.get('energy_site_id'),
                    'name': product.get('site_name', 'Unknown Site'),
                    'type': 'battery',
                    'resource_type': product.get('resource_type'),
                    'state': product.get('state', 'unknown')
                })

        self.logger.info(f"Found {len(energy_sites)} energy sites")
        return energy_sites

    def _exchange_code_for_tokens(self, code: str, code_verifier: str) -> Dict[str, Any]:
        """Exchange authorization code for access and refresh tokens.

        Delegates to pypowerwall, which speaks HTTP/2 with the TLS settings
        Tesla's token endpoint now requires and uses the tesla:// redirect.
        """
        token_response = tesla_auth._exchange_code(code, code_verifier)
        # pypowerwall only checks for a refresh token; reject anything else
        # unusable here with a clear message instead of a KeyError/TypeError
        if not isinstance(token_response, dict) or not token_response.get('access_token'):
            raise TokenResponseError("Tesla token exchange failed: no access token in the response")

        # Calculate expiration time
        expires_in = token_response.get('expires_in', self.DEFAULT_ACCESS_TOKEN_LIFETIME)
        if isinstance(expires_in, bool) or not isinstance(expires_in, (int, float)) or expires_in <= 0:
            raise TokenResponseError("Tesla token exchange failed: invalid token lifetime in the response")
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        return {
            'access_token': token_response['access_token'],
            'refresh_token': token_response.get('refresh_token'),
            'id_token': token_response.get('id_token'),
            'token_type': token_response.get('token_type', 'Bearer'),
            'expires_in': expires_in,
            'expires_at': expires_at.isoformat(),
            'scope': token_response.get('scope', '')
        }

    # ------------------------------------------------------------------
    # Completion and cancellation
    # ------------------------------------------------------------------

    @staticmethod
    def _failure(error: SetupError) -> Dict[str, Any]:
        return {
            'success': False,
            'error': error.message,
            'error_code': str(error.code),
            'http_status': error.http_status,
            'setup': error.progress,
        }

    def complete_setup(self, session_id: str, site_id: Any,
                       commit: Optional[CredentialCommitter] = None) -> Dict[str, Any]:
        """
        Complete the auth setup by storing tokens and site selection.

        Existing credentials are only replaced here, after Tesla accepted the
        new tokens and the chosen site is one Tesla listed for them.

        Args:
            session_id: Session ID for this auth flow
            site_id: Selected site ID
            commit: Runs the credential write; the shared connector passes one
                that swaps its live session under its lock

        Returns:
            Dictionary with setup completion result; ``duplicate`` means an
            earlier identical request already did the work
        """
        try:
            attempt = self._get(session_id)
        except SetupError as error:
            return self._failure(error)
        site_key = str(site_id).strip() if site_id is not None else ''

        with attempt.lock:
            self._enforce_deadline(attempt)
            if attempt.step in ENDED_STEPS:
                return self._failure(self._ended_error(attempt))
            if attempt.step in ('complete', 'completing'):
                if attempt.selected_site_id != site_key:
                    return self._failure(SetupError(
                        SetupErrorCode.WRONG_STEP,
                        'This sign-in is already being saved with a different energy site.',
                        409, self._progress(attempt),
                    ))
                if attempt.step == 'completing':
                    return {'success': True, 'in_progress': True, 'duplicate': True,
                            'http_status': 202, 'setup': self._progress(attempt)}
                return {**(attempt.result or {}), 'duplicate': True, 'http_status': 200,
                        'setup': self._progress(attempt)}
            if attempt.step != 'selecting_site' or attempt.tokens is None:
                return self._failure(SetupError(
                    SetupErrorCode.WRONG_STEP,
                    'Finish signing in to Tesla before choosing an energy site.',
                    409, self._progress(attempt),
                ))
            if attempt.sites is None:
                return self._failure(SetupError(
                    SetupErrorCode.SITE_DISCOVERY_UNAVAILABLE,
                    'Your energy sites have not loaded yet. Retry finding sites first.',
                    409, self._progress(attempt),
                ))
            selected_site = next(
                (dict(site) for site in attempt.sites if str(site.get('id')) == site_key), None
            )
            if selected_site is None:
                return self._failure(SetupError(SetupErrorCode.INVALID_SITE, 'Invalid site selection',
                                                400, self._progress(attempt)))
            attempt.step = 'completing'
            attempt.selected_site_id = site_key
            attempt.error_code = None
            attempt.error = None
            email = attempt.email
            tokens = attempt.tokens

        def write() -> None:
            with attempt.lock:
                if self._clock() >= attempt.expires_at:
                    raise _DeadlinePassed()
                self.auth_storage.replace_auth_data(
                    email=email, tokens=tokens.as_storage_dict(), site=selected_site
                )

        try:
            (commit or _run_now)(write)
        except _DeadlinePassed:
            with attempt.lock:
                self._end(attempt, 'expired', SetupErrorCode.SETUP_EXPIRED, SETUP_EXPIRED_MESSAGE)
                return self._failure(self._ended_error(attempt))
        except Exception as error:
            self.logger.error(f"Failed to save Tesla credentials ({safe_error_detail(error)})")
            with attempt.lock:
                attempt.step = 'selecting_site'
                attempt.selected_site_id = None
                attempt.error_code = SetupErrorCode.CREDENTIAL_WRITE_FAILED
                attempt.error = CREDENTIAL_WRITE_FAILED_MESSAGE
                return self._failure(SetupError(SetupErrorCode.CREDENTIAL_WRITE_FAILED,
                                                CREDENTIAL_WRITE_FAILED_MESSAGE, 500,
                                                self._progress(attempt)))

        with attempt.lock:
            result = {
                'success': True,
                'message': 'Setup complete. Auth file created.',
                'email': email,
                'site': selected_site,
                'credentials_saved': True,
            }
            attempt.result = result
            self._end(attempt, 'complete', None, None)
            self.logger.info(f"Auth setup completed for {email} with site {selected_site.get('name')}")
            return {**result, 'duplicate': False, 'http_status': 200, 'setup': self._progress(attempt)}

    def cancel_setup(self, session_id: str) -> SetupOutcome:
        """Invalidate one pending attempt; other attempts and stored credentials stay."""
        attempt = self._get(session_id)
        with attempt.lock:
            self._enforce_deadline(attempt)
            if attempt.step in ENDED_STEPS:
                return SetupOutcome(self._progress(attempt), 200, duplicate=True)
            if attempt.step in ('completing', 'complete'):
                raise SetupError(SetupErrorCode.WRONG_STEP,
                                 'This sign-in has already been saved and can no longer be cancelled.',
                                 409, self._progress(attempt))
            self._end(attempt, 'cancelled', SetupErrorCode.SETUP_CANCELLED, SETUP_CANCELLED_MESSAGE)
            self.logger.info("Tesla sign-in attempt cancelled")
            return SetupOutcome(self._progress(attempt), 200)

    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """
        Get status of an auth setup attempt.

        Args:
            session_id: Session ID to check

        Returns:
            ``exists`` plus the attempt's progress; ended or unknown attempts
            report ``exists: False`` with a stable ``error_code``
        """
        try:
            attempt = self._get(session_id)
        except SetupError as error:
            return {'exists': False, 'step': None, 'error_code': str(error.code), 'error': error.message}
        with attempt.lock:
            self._enforce_deadline(attempt)
            return {'exists': attempt.step not in ENDED_STEPS, **self._progress(attempt)}

    def sweep_expired(self) -> int:
        """Expire overdue attempts and forget old ended ones; returns how many expired."""
        with self._registry_lock:
            expired = self._prune_locked()
        if expired:
            self.logger.info(f"Expired {expired} Tesla sign-in attempts")
        return expired

    def cleanup_expired_sessions(self) -> None:
        """Clean up expired auth sessions."""
        self.sweep_expired()

    # ------------------------------------------------------------------
    # Mac helper handoff (experimental)
    # ------------------------------------------------------------------

    def create_handoff(self, session_id: str) -> Dict[str, Any]:
        """
        Mint a single-use helper handoff for one attempt awaiting sign-in.

        Only its hash is kept. Minting again replaces the previous handoff,
        and it ends with the attempt.
        """
        attempt = self._get(session_id)
        handoff = secrets.token_urlsafe(32)
        handoff_digest = digest(handoff)
        with attempt.lock:
            self._enforce_deadline(attempt)
            if attempt.step in ENDED_STEPS:
                raise self._ended_error(attempt)
            if attempt.step != 'awaiting_callback' or attempt.source != 'browser':
                raise SetupError(SetupErrorCode.WRONG_STEP,
                                 'The Mac helper can only be started before you sign in to Tesla.',
                                 409, self._progress(attempt))
            previous = attempt.handoff_digest
            attempt.handoff_digest = handoff_digest
            attempt.helper_state = 'pending'
            expires_at = attempt.expires_at.isoformat()
            progress = self._progress(attempt)
        with self._registry_lock:
            if previous:
                self._handoffs.pop(previous, None)
            self._handoffs[handoff_digest] = attempt.id
        return {'handoff': handoff, 'handoff_expires_at': expires_at, 'setup': progress}

    def _attempt_for_handoff(self, handoff: Any) -> Tuple[SetupAttempt, str]:
        invalid = SetupError(SetupErrorCode.HANDOFF_INVALID, HANDOFF_INVALID_MESSAGE, 403)
        if not isinstance(handoff, str) or not 20 <= len(handoff) <= 128:
            raise invalid
        handoff_digest = digest(handoff)
        with self._registry_lock:
            attempt_id = self._handoffs.get(handoff_digest)
            attempt = self._attempts.get(attempt_id) if attempt_id else None
        if attempt is None:
            raise invalid
        return attempt, handoff_digest

    def _check_handoff(self, attempt: SetupAttempt, handoff_digest: str) -> None:
        """Attempt lock held."""
        self._enforce_deadline(attempt)
        if attempt.step in ENDED_STEPS:
            raise self._ended_error(attempt)
        if attempt.handoff_digest is None or not hmac.compare_digest(attempt.handoff_digest, handoff_digest):
            raise SetupError(SetupErrorCode.HANDOFF_INVALID, HANDOFF_INVALID_MESSAGE, 403)

    def helper_authorization(self, handoff: Any) -> Dict[str, Any]:
        """Give the Mac helper the Tesla sign-in URL for its attempt."""
        attempt, handoff_digest = self._attempt_for_handoff(handoff)
        with attempt.lock:
            self._check_handoff(attempt, handoff_digest)
            if attempt.step != 'awaiting_callback':
                raise SetupError(SetupErrorCode.WRONG_STEP,
                                 'This sign-in is already past the Tesla sign-in step.', 409)
            attempt.helper_state = 'opened'
            progress = self._progress(attempt)
        return {
            'auth_url': progress['auth_url'],
            'email': progress['email'],
            'setup_expires_at': progress['setup_expires_at'],
            'setup_expires_in_seconds': progress['setup_expires_in_seconds'],
        }

    def helper_submit_callback(self, handoff: Any, text: str) -> SetupOutcome:
        """Submit the callback the Mac helper captured; consumes the handoff once used."""
        attempt, handoff_digest = self._attempt_for_handoff(handoff)
        with attempt.lock:
            self._check_handoff(attempt, handoff_digest)
        try:
            return self.submit_callback(attempt.id, text)
        finally:
            with attempt.lock:
                if attempt.step != 'awaiting_callback':
                    attempt.handoff_digest = None
                    if attempt.step not in ENDED_STEPS:
                        attempt.helper_state = 'submitted'

    # ------------------------------------------------------------------
    # Stored credentials
    # ------------------------------------------------------------------

    def has_credentials(self) -> bool:
        """Return True when a Tesla login is stored.

        PowerNight never refreshes tokens itself: Tesla's owner API rejects
        access tokens minted by a refresh on a new session (HTTP 403), so the
        token lifecycle is left to pypowerwall's long-lived cloud session.
        """
        auth_data = self.auth_storage.load_auth_data()
        return bool(auth_data and (auth_data.get('refresh_token') or auth_data.get('access_token')))

    def describe_powerwall(self, pw: Any) -> Dict[str, Any]:
        """
        Summarize the Powerwall reachable through an existing pypowerwall session.

        Args:
            pw: Connected pypowerwall cloud session (the shared connector's)

        Returns:
            Dictionary with connection test result and basic Powerwall info
        """
        try:
            auth_data = self.auth_storage.load_auth_data()
            if not auth_data:
                raise Exception("No authentication data found. Please complete setup first.")

            # Test basic connectivity by getting site info
            site_info = pw.site()
            if site_info is None:
                raise Exception("No site information available")

            # Get basic Powerwall info
            battery_level = pw.level()

            # Create a simplified Powerwall info structure
            site_id = (auth_data.get('site') or {}).get('id', 'unknown')
            powerwall_info = {
                'id': site_id,
                'serial_number': site_id,
                'site_id': site_id,
                'display_name': f"Powerwall ({auth_data['email']})",
                'energy_site_id': site_id,
                'resource_type': 'battery',
                'state': 'online' if battery_level is not None else 'unknown',
                'components': {
                    'battery': True,
                    'solar': 'solar' in str(site_info).lower(),
                    'grid': True
                },
                'battery_level': battery_level,
                'connection_test': True
            }

            self.logger.info(f"Successfully tested pypowerwall connection for {auth_data['email']}")
            return {
                'success': True,
                'powerwall': powerwall_info,
                'connection_type': 'pypowerwall_cloud'
            }

        except Exception as e:
            self.logger.error(f"Failed to test pypowerwall connection: {e}")
            return {
                'success': False,
                'error': str(e),
                'connection_type': 'pypowerwall_cloud'
            }

    def revoke_tokens(self) -> bool:
        """
        Revoke all stored tokens.

        Returns:
            True if revocation successful, False otherwise
        """
        try:
            auth_data = self.auth_storage.load_auth_data()
            if not auth_data:
                return True

            # Best-effort revocation: signing out must still clear local
            # credentials when Tesla is unreachable or rejects the request
            if auth_data.get('access_token'):
                try:
                    requests.post(
                        self.REVOKE_URL,
                        data={
                            'token': auth_data['access_token'],
                            'token_type_hint': 'access_token'
                        },
                        headers={
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'User-Agent': 'PowerNight/1.0'
                        },
                        timeout=30
                    )
                except requests.RequestException as error:
                    self.logger.warning(f"Tesla token revocation failed: {error}")

            # Clear stored auth data
            self.auth_storage.clear_auth_data()

            self.logger.info("Tokens revoked and auth data cleared")
            return True

        except Exception as e:
            self.logger.error(f"Failed to revoke tokens: {e}")
            return False

    def get_auth_status(self) -> Dict[str, Any]:
        """
        Get current authentication status.

        Returns:
            Dictionary with authentication status information
        """
        auth_data = self.auth_storage.load_auth_data()

        status = {
            'authenticated': bool(auth_data),
            'has_auth_data': self.auth_storage.has_auth_data(),
            'token_expired': self.auth_storage.is_token_expired(auth_data) if auth_data else True,
            'storage_info': self.auth_storage.get_storage_info()
        }

        if auth_data:
            try:
                expires_at_value = auth_data['expires_at']
                # Handle both unix timestamp (float/int) and ISO string formats
                if isinstance(expires_at_value, (int, float)):
                    expires_at = datetime.fromtimestamp(expires_at_value, timezone.utc)
                else:
                    expires_at = datetime.fromisoformat(str(expires_at_value).replace('Z', '+00:00'))

                status['expires_at'] = expires_at.isoformat()
                status['expires_in_seconds'] = int((expires_at - datetime.now(timezone.utc)).total_seconds())
                status['email'] = auth_data.get('email')
                status['site_name'] = auth_data.get('site_name')
                status['site_id'] = auth_data.get('site', {}).get('id') if auth_data.get('site') else None
            except (ValueError, KeyError, TypeError):
                status['expires_at'] = None
                status['expires_in_seconds'] = 0

        return status
