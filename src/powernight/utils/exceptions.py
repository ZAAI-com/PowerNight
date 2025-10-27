"""
PowerNight Common Exceptions

Common exception classes used across the PowerNight application.
"""


class PowerNightError(Exception):
    """Base exception class for all PowerNight errors."""
    pass


class ConfigurationError(PowerNightError):
    """Exception raised for configuration-related errors."""
    pass


class ValidationError(PowerNightError):
    """Exception raised for validation errors."""
    pass
