"""
PowerNight Powerwall Exception Classes

Custom exception classes for different Powerwall error scenarios.
"""

from typing import Optional


class PowerwallError(Exception):
    """Base exception class for all Powerwall-related errors."""

    def __init__(self, message: str, error_code: Optional[str] = None) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class PowerwallConnectionError(PowerwallError):
    """Exception raised when unable to connect to Powerwall device."""

    def __init__(self, email: str, message: str = "Failed to connect to Powerwall") -> None:
        super().__init__(f"{message} for {email}")
        self.email = email


class PowerwallAuthenticationError(PowerwallError):
    """Exception raised when authentication with Powerwall fails."""

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message)


class PowerwallTimeoutError(PowerwallError):
    """Exception raised when Powerwall operations timeout."""

    def __init__(self, operation: str, timeout: float) -> None:
        super().__init__(f"Operation '{operation}' timed out after {timeout}s")
        self.operation = operation
        self.timeout = timeout


class PowerwallAPIError(PowerwallError):
    """Exception raised when Powerwall API returns an error."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class PowerwallUnavailableError(PowerwallError):
    """Exception raised when Powerwall device is unavailable or unreachable."""

    def __init__(self, email: str, message: str = "Powerwall device unavailable") -> None:
        super().__init__(f"{message} for {email}")
        self.email = email


class PowerwallValidationError(PowerwallError):
    """Exception raised when input validation fails."""

    def __init__(self, parameter: str, value: any, message: str = "") -> None:
        full_message = f"Invalid value for {parameter}: {value}"
        if message:
            full_message += f" - {message}"
        super().__init__(full_message)
        self.parameter = parameter
        self.value = value


class PowerwallRateLimitError(PowerwallError):
    """Exception raised when API rate limits are exceeded."""

    def __init__(self, retry_after: Optional[float] = None) -> None:
        message = "API rate limit exceeded"
        if retry_after:
            message += f", retry after {retry_after}s"
        super().__init__(message)
        self.retry_after = retry_after