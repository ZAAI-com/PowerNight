"""
PowerNight Configuration Exceptions

Exception classes for configuration-related errors.
"""


class ConfigurationError(Exception):
    """Exception raised for configuration-related errors."""
    pass


class ValidationError(Exception):
    """Exception raised for configuration validation errors."""
    pass


class BackupError(Exception):
    """Exception raised for backup/recovery operation errors."""
    pass