"""
PowerNight Configuration Validators

Advanced validation functions for configuration values.
"""

import re
from typing import Union
from datetime import datetime, time


class ValidationError(Exception):
    """Base validation error."""
    pass


class PercentageValidationError(ValidationError):
    """Percentage value validation error."""
    pass


class TimeFormatValidationError(ValidationError):
    """Time format validation error."""
    pass


def validate_percentage(value: Union[int, float]) -> float:
    """
    Validate percentage value (0-100).

    Args:
        value: Percentage value to validate

    Returns:
        Validated percentage as float

    Raises:
        PercentageValidationError: If percentage is invalid
    """
    if value is None:
        raise PercentageValidationError("Percentage cannot be None")

    try:
        percentage = float(value)
    except (ValueError, TypeError):
        raise PercentageValidationError(f"Percentage must be a number, got {type(value).__name__}")

    if not 0 <= percentage <= 100:
        raise PercentageValidationError(f"Percentage {percentage} must be between 0 and 100")

    return percentage


def validate_time_format(time_str: str) -> time:
    """
    Validate time format (HH:MM in 24-hour format).

    Args:
        time_str: Time string to validate

    Returns:
        Parsed time object

    Raises:
        TimeFormatValidationError: If time format is invalid
    """
    if not time_str or not isinstance(time_str, str):
        raise TimeFormatValidationError("Time string cannot be empty")

    time_str = time_str.strip()

    # Check basic format with regex
    if not re.match(r'^\d{1,2}:\d{2}$', time_str):
        raise TimeFormatValidationError(
            f"Invalid time format '{time_str}', expected HH:MM (24-hour format)"
        )

    try:
        time_obj = datetime.strptime(time_str, "%H:%M").time()
        return time_obj
    except ValueError as e:
        raise TimeFormatValidationError(
            f"Invalid time value '{time_str}': {e}"
        )


def validate_timezone(timezone_str: str) -> str:
    """
    Validate timezone string.

    Args:
        timezone_str: Timezone string to validate

    Returns:
        Validated timezone string

    Raises:
        ValidationError: If timezone is invalid
    """
    if not timezone_str or not isinstance(timezone_str, str):
        raise ValidationError("Timezone cannot be empty")

    timezone_str = timezone_str.strip()

    # Import here to avoid circular imports
    try:
        import pytz
        if timezone_str not in pytz.all_timezones:
            raise ValidationError(f"Invalid timezone: {timezone_str}")
    except ImportError:
        # If pytz is not available, do basic validation
        if not re.match(r'^[A-Za-z_/]+$', timezone_str):
            raise ValidationError(f"Invalid timezone format: {timezone_str}")

    return timezone_str


def validate_port_number(port: Union[int, str]) -> int:
    """
    Validate port number (1-65535).

    Args:
        port: Port number to validate

    Returns:
        Validated port number as int

    Raises:
        ValidationError: If port is invalid
    """
    try:
        port_num = int(port)
    except (ValueError, TypeError):
        raise ValidationError(f"Port must be a number, got {type(port).__name__}")

    if not 1 <= port_num <= 65535:
        raise ValidationError(f"Port {port_num} must be between 1 and 65535")

    return port_num


def validate_positive_number(value: Union[int, float], name: str = "value") -> float:
    """
    Validate positive number.

    Args:
        value: Number to validate
        name: Name of the value for error messages

    Returns:
        Validated number as float

    Raises:
        ValidationError: If number is not positive
    """
    if value is None:
        raise ValidationError(f"{name} cannot be None")

    try:
        number = float(value)
    except (ValueError, TypeError):
        raise ValidationError(f"{name} must be a number, got {type(value).__name__}")

    if number <= 0:
        raise ValidationError(f"{name} must be positive, got {number}")

    return number


def validate_non_negative_number(value: Union[int, float], name: str = "value") -> float:
    """
    Validate non-negative number.

    Args:
        value: Number to validate
        name: Name of the value for error messages

    Returns:
        Validated number as float

    Raises:
        ValidationError: If number is negative
    """
    if value is None:
        raise ValidationError(f"{name} cannot be None")

    try:
        number = float(value)
    except (ValueError, TypeError):
        raise ValidationError(f"{name} must be a number, got {type(value).__name__}")

    if number < 0:
        raise ValidationError(f"{name} cannot be negative, got {number}")

    return number


def validate_log_level(level: str) -> str:
    """
    Validate logging level.

    Args:
        level: Log level string to validate

    Returns:
        Validated log level (uppercase)

    Raises:
        ValidationError: If log level is invalid
    """
    if not level or not isinstance(level, str):
        raise ValidationError("Log level cannot be empty")

    level = level.strip().upper()
    valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

    if level not in valid_levels:
        raise ValidationError(f"Invalid log level '{level}', must be one of {valid_levels}")

    return level


def validate_email_format(email: str) -> str:
    """
    Validate email address format.

    Args:
        email: Email address to validate

    Returns:
        Validated email address

    Raises:
        ValidationError: If email format is invalid
    """
    if not email or not isinstance(email, str):
        raise ValidationError("Email address cannot be empty")

    email = email.strip().lower()

    # Basic email regex pattern
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

    if not re.match(pattern, email):
        raise ValidationError(f"Invalid email format: {email}")

    if len(email) > 254:
        raise ValidationError(f"Email address too long: {email}")

    return email


# Convenience function for validating complete configuration sections
