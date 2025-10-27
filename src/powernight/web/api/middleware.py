"""
PowerNight Web Middleware

Enterprise-grade middleware for rate limiting, security, and monitoring.
"""

import time
import hashlib
import logging
from functools import wraps
from typing import Dict, Any, Optional, Callable, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from collections import defaultdict, deque
import threading

from flask import request, jsonify, current_app, g
from .errors import RateLimitError, APIError


@dataclass
class RateLimitRule:
    """Rate limiting rule configuration."""
    requests_per_window: int
    window_duration_seconds: int
    burst_allowance: int = 0
    block_duration_seconds: int = 300  # 5 minutes default

    def __post_init__(self):
        """Validate rule configuration."""
        if self.requests_per_window <= 0:
            raise ValueError("requests_per_window must be positive")
        if self.window_duration_seconds <= 0:
            raise ValueError("window_duration_seconds must be positive")
        if self.burst_allowance < 0:
            raise ValueError("burst_allowance cannot be negative")


@dataclass
class ClientMetrics:
    """Metrics for a specific client."""
    request_count: int = 0
    first_request_time: float = field(default_factory=time.time)
    last_request_time: float = field(default_factory=time.time)
    blocked_until: Optional[float] = None
    request_times: deque = field(default_factory=lambda: deque(maxlen=1000))
    burst_tokens: int = 0
    total_requests: int = 0
    total_blocked: int = 0

    def is_blocked(self) -> bool:
        """Check if client is currently blocked."""
        return (self.blocked_until is not None and
                time.time() < self.blocked_until)

    def reset_window(self, burst_allowance: int = 0):
        """Reset the rate limiting window."""
        self.request_count = 0
        self.first_request_time = time.time()
        self.burst_tokens = burst_allowance

    def add_request(self):
        """Record a new request."""
        now = time.time()
        self.request_count += 1
        self.total_requests += 1
        self.last_request_time = now
        self.request_times.append(now)

    def block_client(self, duration_seconds: int):
        """Block the client for specified duration."""
        self.blocked_until = time.time() + duration_seconds
        self.total_blocked += 1


class RateLimiter:
    """
    Enterprise-grade rate limiter with sliding window and burst handling.

    Features:
    - Multiple rate limiting algorithms (sliding window, token bucket)
    - Per-endpoint and global rate limits
    - Burst allowance for legitimate traffic spikes
    - Automatic client blocking for abuse
    - Detailed metrics and monitoring
    """

    def __init__(self):
        """Initialize rate limiter."""
        self.logger = logging.getLogger(__name__)
        self._clients: Dict[str, ClientMetrics] = {}
        self._rules: Dict[str, RateLimitRule] = {}
        self._lock = threading.RLock()

        # Default rules
        self._setup_default_rules()

        # Cleanup task
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # 5 minutes

    def _setup_default_rules(self):
        """Setup default rate limiting rules."""
        self._rules = {
            'global': RateLimitRule(
                requests_per_window=100,
                window_duration_seconds=60,
                burst_allowance=20,
                block_duration_seconds=300
            ),
            'config': RateLimitRule(
                requests_per_window=10,
                window_duration_seconds=60,
                burst_allowance=2,
                block_duration_seconds=600
            ),
            'backup-reserve': RateLimitRule(
                requests_per_window=20,
                window_duration_seconds=60,
                burst_allowance=5,
                block_duration_seconds=300
            ),
            'auth': RateLimitRule(
                requests_per_window=5,
                window_duration_seconds=300,  # 5 minutes
                burst_allowance=0,
                block_duration_seconds=900  # 15 minutes
            )
        }

    def add_rule(self, endpoint: str, rule: RateLimitRule):
        """Add or update a rate limiting rule."""
        with self._lock:
            self._rules[endpoint] = rule
            self.logger.info(f"Added rate limit rule for {endpoint}: {rule}")

    def check_rate_limit(self, client_id: str, endpoint: str = 'global') -> Tuple[bool, Dict[str, Any]]:
        """
        Check if request should be rate limited.

        Args:
            client_id: Unique identifier for the client
            endpoint: Endpoint being accessed

        Returns:
            Tuple of (allowed, metadata)
        """
        with self._lock:
            # Cleanup old entries periodically
            self._periodic_cleanup()

            # Get or create client metrics
            if client_id not in self._clients:
                self._clients[client_id] = ClientMetrics()

            client = self._clients[client_id]

            # Check if client is currently blocked
            if client.is_blocked():
                metadata = {
                    'rate_limited': True,
                    'reason': 'Client blocked',
                    'blocked_until': client.blocked_until,
                    'retry_after': int(client.blocked_until - time.time())
                }
                return False, metadata

            # Get applicable rule
            rule = self._rules.get(endpoint, self._rules['global'])

            # Check sliding window
            now = time.time()
            window_start = now - rule.window_duration_seconds

            # Clean old requests from window
            while client.request_times and client.request_times[0] < window_start:
                client.request_times.popleft()

            current_requests = len(client.request_times)

            # Check if within limits (including burst)
            effective_limit = rule.requests_per_window + client.burst_tokens

            if current_requests >= effective_limit:
                # Rate limit exceeded
                client.block_client(rule.block_duration_seconds)

                metadata = {
                    'rate_limited': True,
                    'reason': 'Rate limit exceeded',
                    'rule': {
                        'endpoint': endpoint,
                        'requests_per_window': rule.requests_per_window,
                        'window_duration': rule.window_duration_seconds
                    },
                    'current_requests': current_requests,
                    'limit': effective_limit,
                    'blocked_until': client.blocked_until,
                    'retry_after': rule.block_duration_seconds
                }

                self.logger.warning(
                    f"Rate limit exceeded for {client_id} on {endpoint}: "
                    f"{current_requests}/{effective_limit} requests"
                )

                return False, metadata

            # Allow request and record it
            client.add_request()

            # Update burst tokens (regenerate over time)
            if client.burst_tokens < rule.burst_allowance:
                time_since_last = now - client.last_request_time
                tokens_to_add = int(time_since_last / (rule.window_duration_seconds / rule.burst_allowance))
                client.burst_tokens = min(
                    rule.burst_allowance,
                    client.burst_tokens + tokens_to_add
                )

            # Use burst token if needed
            if current_requests > rule.requests_per_window and client.burst_tokens > 0:
                client.burst_tokens -= 1

            metadata = {
                'rate_limited': False,
                'requests_remaining': max(0, effective_limit - current_requests - 1),
                'window_reset': window_start + rule.window_duration_seconds,
                'burst_tokens': client.burst_tokens,
                'total_requests': client.total_requests
            }

            return True, metadata

    def get_client_stats(self, client_id: str) -> Dict[str, Any]:
        """Get statistics for a specific client."""
        with self._lock:
            if client_id not in self._clients:
                return {'error': 'Client not found'}

            client = self._clients[client_id]

            return {
                'client_id': client_id,
                'total_requests': client.total_requests,
                'total_blocked': client.total_blocked,
                'current_window_requests': client.request_count,
                'last_request': client.last_request_time,
                'is_blocked': client.is_blocked(),
                'blocked_until': client.blocked_until,
                'burst_tokens': client.burst_tokens,
                'request_rate_per_minute': len([
                    t for t in client.request_times
                    if t > time.time() - 60
                ])
            }

    def get_global_stats(self) -> Dict[str, Any]:
        """Get global rate limiter statistics."""
        with self._lock:
            total_clients = len(self._clients)
            blocked_clients = sum(1 for c in self._clients.values() if c.is_blocked())
            total_requests = sum(c.total_requests for c in self._clients.values())
            total_blocked = sum(c.total_blocked for c in self._clients.values())

            return {
                'total_clients': total_clients,
                'blocked_clients': blocked_clients,
                'total_requests': total_requests,
                'total_blocked_requests': total_blocked,
                'rules_configured': len(self._rules),
                'rules': {
                    name: {
                        'requests_per_window': rule.requests_per_window,
                        'window_duration_seconds': rule.window_duration_seconds,
                        'burst_allowance': rule.burst_allowance
                    }
                    for name, rule in self._rules.items()
                }
            }

    def _periodic_cleanup(self):
        """Clean up old client entries."""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return

        # Remove clients that haven't made requests in the last hour
        # and are not currently blocked
        cutoff_time = now - 3600
        clients_to_remove = []

        for client_id, client in self._clients.items():
            if (client.last_request_time < cutoff_time and
                not client.is_blocked()):
                clients_to_remove.append(client_id)

        for client_id in clients_to_remove:
            del self._clients[client_id]

        if clients_to_remove:
            self.logger.info(f"Cleaned up {len(clients_to_remove)} inactive clients")

        self._last_cleanup = now

    def reset_client(self, client_id: str):
        """Reset rate limiting for a specific client."""
        with self._lock:
            if client_id in self._clients:
                del self._clients[client_id]
                self.logger.info(f"Reset rate limiting for client {client_id}")


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def rate_limit(endpoint: str = 'global'):
    """
    Decorator for rate limiting API endpoints.

    Args:
        endpoint: Endpoint name for specific rate limiting rules
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get client identifier
            client_id = _get_client_identifier()

            # Check rate limit
            rate_limiter = get_rate_limiter()
            allowed, metadata = rate_limiter.check_rate_limit(client_id, endpoint)

            if not allowed:
                # Rate limited
                response = jsonify({
                    'success': False,
                    'error': 'Rate Limit Exceeded',
                    'message': metadata.get('reason', 'Too many requests'),
                    'retry_after': metadata.get('retry_after', 300),
                    'limit_info': metadata,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
                response.status_code = 429
                response.headers['Retry-After'] = str(metadata.get('retry_after', 300))
                response.headers['X-RateLimit-Limit'] = str(
                    metadata.get('rule', {}).get('requests_per_window', 'unknown')
                )
                response.headers['X-RateLimit-Remaining'] = '0'

                return response

            # Add rate limit headers to successful response
            g.rate_limit_metadata = metadata

            # Call the original function
            response = f(*args, **kwargs)

            # Add rate limit headers if response is a Flask response
            if hasattr(response, 'headers'):
                response.headers['X-RateLimit-Limit'] = str(
                    metadata.get('rule', {}).get('requests_per_window', 'unknown')
                )
                response.headers['X-RateLimit-Remaining'] = str(
                    metadata.get('requests_remaining', 0)
                )
                if 'window_reset' in metadata:
                    response.headers['X-RateLimit-Reset'] = str(int(metadata['window_reset']))

            return response

        return decorated_function
    return decorator


def _get_client_identifier() -> str:
    """
    Get unique identifier for rate limiting.

    Uses multiple factors to create a unique but privacy-respecting identifier.
    """
    # Start with IP address
    client_ip = request.remote_addr or 'unknown'

    # Add user agent hash for better uniqueness
    user_agent = request.headers.get('User-Agent', '')
    user_agent_hash = hashlib.md5(user_agent.encode()).hexdigest()[:8]

    # Add authentication info if available
    auth_user = getattr(g, 'current_user', None)
    if auth_user:
        return f"user:{auth_user}:{client_ip}"

    # Check for API key
    api_key = request.headers.get('X-API-Key')
    if api_key:
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:12]
        return f"api:{api_key_hash}:{client_ip}"

    # Default to IP + user agent hash
    return f"ip:{client_ip}:{user_agent_hash}"


class SecurityMiddleware:
    """
    Enterprise security middleware for additional protection.

    Features:
    - Request validation and sanitization
    - Suspicious pattern detection
    - Security headers enforcement
    - Request/response logging for security audit
    """

    def __init__(self):
        """Initialize security middleware."""
        self.logger = logging.getLogger(__name__)
        self._suspicious_patterns = [
            # SQL injection patterns
            r'(\b(union|select|insert|update|delete|drop|exec|script)\b)',
            # XSS patterns
            r'(<script|javascript:|on\w+\s*=)',
            # Path traversal
            r'(\.\./|\.\.\\)',
            # Command injection
            r'(;|\||&|\$\(|\`)',
        ]

        # Compile patterns for better performance
        import re
        self._compiled_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self._suspicious_patterns
        ]

    def validate_request(self, request_data: Any) -> Tuple[bool, Optional[str]]:
        """
        Validate request for suspicious content.

        Args:
            request_data: Request data to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if request_data is None:
            return True, None

        # Convert to string for pattern matching
        if isinstance(request_data, dict):
            data_str = str(request_data)
        elif isinstance(request_data, (list, tuple)):
            data_str = str(request_data)
        else:
            data_str = str(request_data)

        # Check for suspicious patterns
        for pattern in self._compiled_patterns:
            if pattern.search(data_str):
                return False, f"Suspicious pattern detected: {pattern.pattern}"

        # Check for extremely long inputs (potential DoS)
        if len(data_str) > 100000:  # 100KB limit
            return False, "Request data too large"

        return True, None

    def add_security_headers(self, response):
        """Add security headers to response."""
        security_headers = {
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'X-XSS-Protection': '1; mode=block',
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
            'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'",
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Permissions-Policy': 'geolocation=(), microphone=(), camera=()'
        }

        for header, value in security_headers.items():
            if header not in response.headers:
                response.headers[header] = value

        return response

    def log_security_event(self, event_type: str, details: Dict[str, Any]):
        """Log security-related events."""
        security_log = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'event_type': event_type,
            'client_ip': request.remote_addr,
            'user_agent': request.headers.get('User-Agent'),
            'endpoint': request.endpoint,
            'method': request.method,
            'details': details
        }

        self.logger.warning(f"Security event: {event_type}", extra={'security_event': security_log})


# Global security middleware instance
_security_middleware: Optional[SecurityMiddleware] = None


def get_security_middleware() -> SecurityMiddleware:
    """Get the global security middleware instance."""
    global _security_middleware
    if _security_middleware is None:
        _security_middleware = SecurityMiddleware()
    return _security_middleware


def secure_endpoint(validate_input: bool = True):
    """
    Decorator for adding security validation to endpoints.

    Args:
        validate_input: Whether to validate request input for suspicious patterns
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            security = get_security_middleware()

            # Validate input if requested
            if validate_input and request.is_json:
                try:
                    request_data = request.get_json()
                    is_valid, error_msg = security.validate_request(request_data)

                    if not is_valid:
                        security.log_security_event('suspicious_input', {
                            'error': error_msg,
                            'data_sample': str(request_data)[:500]  # Log sample for analysis
                        })

                        return jsonify({
                            'success': False,
                            'error': 'Invalid Request',
                            'message': 'Request contains invalid or suspicious content',
                            'timestamp': datetime.now(timezone.utc).isoformat()
                        }), 400

                except Exception as e:
                    security.log_security_event('validation_error', {
                        'error': str(e)
                    })

            # Call the original function
            response = f(*args, **kwargs)

            # Add security headers
            if hasattr(response, 'headers'):
                response = security.add_security_headers(response)

            return response

        return decorated_function
    return decorator


def performance_monitor():
    """Decorator for monitoring endpoint performance."""
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            start_time = time.time()

            try:
                # Call the original function
                result = f(*args, **kwargs)

                # Record successful execution
                execution_time = time.time() - start_time

                if execution_time > 5.0:  # Log slow requests
                    current_app.logger.warning(
                        f"Slow request detected: {request.endpoint} took {execution_time:.2f}s"
                    )

                # Add performance headers
                if hasattr(result, 'headers'):
                    result.headers['X-Response-Time'] = f"{execution_time:.3f}s"

                return result

            except Exception as e:
                execution_time = time.time() - start_time
                current_app.logger.error(
                    f"Request failed: {request.endpoint} failed after {execution_time:.2f}s: {e}"
                )
                raise

        return decorated_function
    return decorator