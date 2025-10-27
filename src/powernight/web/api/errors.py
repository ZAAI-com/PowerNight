"""
PowerNight Web API Errors

Custom exception classes for web API error handling.
"""

from typing import Optional, Dict, Any


class APIError(Exception):
    """Base API error class."""

    def __init__(self, message: str, status_code: int = 500, details: Optional[Dict[str, Any]] = None):
        """
        Initialize API error.

        Args:
            message: Error message
            status_code: HTTP status code
            details: Optional additional error details
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class ValidationError(APIError):
    """Validation error for request data."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """
        Initialize validation error.

        Args:
            message: Error message
            details: Optional validation error details
        """
        super().__init__(message, status_code=422, details=details)


class AuthenticationError(APIError):
    """Authentication error."""

    def __init__(self, message: str = "Authentication required"):
        """
        Initialize authentication error.

        Args:
            message: Error message
        """
        super().__init__(message, status_code=401)


class AuthorizationError(APIError):
    """Authorization error."""

    def __init__(self, message: str = "Access denied"):
        """
        Initialize authorization error.

        Args:
            message: Error message
        """
        super().__init__(message, status_code=403)


class PowerwallError(APIError):
    """Powerwall communication error."""

    def __init__(self, message: str, status_code: int = 502):
        """
        Initialize Powerwall error.

        Args:
            message: Error message
            status_code: HTTP status code (default 502 Bad Gateway)
        """
        super().__init__(message, status_code=status_code)


class ConfigurationError(APIError):
    """Configuration error."""

    def __init__(self, message: str):
        """
        Initialize configuration error.

        Args:
            message: Error message
        """
        super().__init__(message, status_code=500)


class RateLimitError(APIError):
    """Rate limit exceeded error."""

    def __init__(self, message: str = "Rate limit exceeded"):
        """
        Initialize rate limit error.

        Args:
            message: Error message
        """
        super().__init__(message, status_code=429)