"""
Flask middleware: CORS, security headers, and lightweight rate limiting.
"""

import threading
import time

from flask import Flask, request, jsonify
from flask_cors import CORS


# Paths that accept credentials or drive the OAuth flow get rate limited to
# slow down brute-force attempts. Prefix match.
_RATE_LIMITED_PREFIXES = (
    '/api/auth/setup/',
    '/api/auth/tesla/test-connection',
)
_RATE_LIMIT_MAX_REQUESTS = 20
_RATE_LIMIT_WINDOW_SECONDS = 60.0


class _SlidingWindowRateLimiter:
    """Minimal in-memory per-client sliding window rate limiter."""

    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits = {}
        self._lock = threading.Lock()

    def allow(self, client_id: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
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

    rate_limiter = _SlidingWindowRateLimiter(
        _RATE_LIMIT_MAX_REQUESTS, _RATE_LIMIT_WINDOW_SECONDS
    )

    @app.before_request
    def before_request():
        """Log each request and enforce rate limits on sensitive paths."""
        app.logger.debug(f"Request: {request.method} {request.url}")

        if request.path.startswith(_RATE_LIMITED_PREFIXES):
            client_id = request.remote_addr or 'unknown'
            if not rate_limiter.allow(client_id):
                return jsonify({
                    'success': False,
                    'error': 'Too Many Requests',
                    'message': 'Rate limit exceeded; try again later'
                }), 429

    @app.after_request
    def after_request(response):
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
    def teardown_appcontext(exception=None):
        """Clean up application context."""
        if exception:
            app.logger.error(f"App context teardown with exception: {exception}")
