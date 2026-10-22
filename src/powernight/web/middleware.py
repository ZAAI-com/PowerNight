"""
Flask middleware: CORS, security headers, and lightweight rate limiting.
"""

import threading
import time

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, Tuple

from flask import Flask, Response, request, jsonify
from flask.typing import ResponseReturnValue
from flask_cors import CORS


@dataclass(frozen=True)
class _RateLimitRule:
    """Requests matching ``prefix`` (and ``methods``, if set) share one bucket per client."""

    name: str
    prefix: str
    methods: Optional[FrozenSet[str]]
    max_requests: int
    window_seconds: float

    def matches(self, path: str, method: str) -> bool:
        return path.startswith(self.prefix) and (self.methods is None or method in self.methods)


# Paths that accept credentials or drive the OAuth flow get rate limited to
# slow down brute-force attempts. The first matching rule wins. Status reads
# get their own, looser bucket so polling a sign-in in progress cannot use
# up the budget for the steps that matter. Buckets are per client address,
# so behind a reverse proxy every client shares them.
_RATE_LIMIT_RULES: Tuple[_RateLimitRule, ...] = (
    _RateLimitRule('setup-status', '/api/auth/setup/status/', frozenset({'GET'}), 120, 60.0),
    _RateLimitRule('setup-helper', '/api/auth/setup/helper/', None, 30, 60.0),
    _RateLimitRule('setup', '/api/auth/setup/', None, 20, 60.0),
    _RateLimitRule('setup', '/api/auth/tesla/test-connection', None, 20, 60.0),
)


class _SlidingWindowRateLimiter:
    """Minimal in-memory per-client sliding window rate limiter."""

    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def allow(self, client_id: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            self._hits = {client: [t for t in hits if t > cutoff]
                          for client, hits in self._hits.items() if hits and hits[-1] > cutoff}
            hits = [t for t in self._hits.get(client_id, []) if t > cutoff]
            if len(hits) >= self.max_requests:
                self._hits[client_id] = hits
                return False
            hits.append(now)
            self._hits[client_id] = hits
            return True


def configure_middleware(app: Flask) -> None:
    """
    Configure Flask middleware: CORS, request logging, security headers,
    and rate limiting for authentication-adjacent endpoints.
    """
    # CORS: explicit allow-list only (Vite dev server), never a wildcard
    if app.config.get('DEBUG'):
        CORS(app, resources={r"/api/*": {"origins": ["http://localhost:3000"]}})

    rate_limiters: Dict[str, _SlidingWindowRateLimiter] = {}
    for rule in _RATE_LIMIT_RULES:
        rate_limiters.setdefault(
            rule.name, _SlidingWindowRateLimiter(rule.max_requests, rule.window_seconds)
        )

    @app.before_request
    def before_request() -> Optional[ResponseReturnValue]:
        """Log each request and enforce rate limits on sensitive paths."""
        app.logger.debug(f"Request: {request.method} {request.url}")

        rule = next(
            (rule for rule in _RATE_LIMIT_RULES if rule.matches(request.path, request.method)),
            None,
        )
        if rule is not None:
            client_id = request.remote_addr or 'unknown'
            if not rate_limiters[rule.name].allow(client_id):
                return jsonify({
                    'success': False,
                    'error': 'Too Many Requests',
                    'error_code': 'RATE_LIMITED',
                    'message': 'Rate limit exceeded; try again later'
                }), 429
        return None

    @app.after_request
    def after_request(response: Response) -> Response:
        """Log each response and attach security headers."""
        app.logger.debug(f"Response: {response.status_code}")

        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Referrer-Policy', 'same-origin')
        response.headers.setdefault(
            'Content-Security-Policy',
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self' https://auth.tesla.com"
        )
        # HSTS only makes sense when the request actually arrived over HTTPS
        # (directly or via a TLS-terminating reverse proxy)
        if request.is_secure or request.headers.get('X-Forwarded-Proto') == 'https':
            response.headers.setdefault(
                'Strict-Transport-Security', 'max-age=31536000; includeSubDomains'
            )
        return response

    @app.teardown_appcontext
    def teardown_appcontext(exception: Optional[BaseException] = None) -> None:
        """Clean up application context."""
        if exception:
            app.logger.error(f"App context teardown with exception: {exception}")
