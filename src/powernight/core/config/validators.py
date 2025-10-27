"""
PowerNight Configuration Validators

Advanced validation functions for configuration values.
"""

import re
import ipaddress
import socket
from typing import List, Optional, Union
from datetime import datetime, time
from urllib.parse import urlparse


class ValidationError(Exception):
    """Base validation error."""
    pass


class IPAddressValidationError(ValidationError):
    """IP address validation error."""
    pass


class PercentageValidationError(ValidationError):
    """Percentage value validation error."""
    pass


class TimeFormatValidationError(ValidationError):
    """Time format validation error."""
    pass


class ScheduleValidationError(ValidationError):
    """Schedule validation error."""
    pass


def validate_ipv4_address(address: str) -> str:
    """
    Validate IPv4 address.

    Args:
        address: IPv4 address string to validate

    Returns:
        Validated IPv4 address string

    Raises:
        IPAddressValidationError: If address is not a valid IPv4 address
    """
    if not address or not isinstance(address, str):
        raise IPAddressValidationError("IP address cannot be empty")

    address = address.strip()

    try:
        ipaddress.IPv4Address(address)
        return address
    except ipaddress.AddressValueError:
        raise IPAddressValidationError(f"Invalid IPv4 address: {address}")


def validate_tesla_email(tesla_email: str) -> str:
    """
    Validate Tesla email format.

    Args:
        tesla_email: Email string to validate

    Returns:
        Validated email string

    Raises:
        ValidationError: If email is invalid
    """
    if not tesla_email or not isinstance(tesla_email, str):
        raise ValidationError("Tesla email must be a non-empty string")

    tesla_email = tesla_email.strip()

    # Basic email validation
    import re
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, tesla_email):
        raise ValidationError(f"Invalid email format: {tesla_email}")

    return tesla_email


def validate_hostname_or_ip(address: str) -> str:
    """
    Validate hostname or IP address.

    Args:
        address: Hostname or IP address to validate

    Returns:
        Normalized address string

    Raises:
        IPAddressValidationError: If address is invalid
    """
    if not address or not isinstance(address, str):
        raise IPAddressValidationError("Address cannot be empty")

    address = address.strip()

    # Try IP address first
    try:
        return validate_ipv4_address(address)
    except IPAddressValidationError:
        pass

    # Try hostname validation
    if not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$', address):
        raise IPAddressValidationError(f"Invalid hostname format: {address}")

    if len(address) > 253:
        raise IPAddressValidationError(f"Hostname too long: {address}")

    return address


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


def validate_file_size_string(size_str: str) -> str:
    """
    Validate file size string (e.g., "10MB", "1GB").

    Args:
        size_str: File size string to validate

    Returns:
        Validated file size string

    Raises:
        ValidationError: If file size format is invalid
    """
    if not size_str or not isinstance(size_str, str):
        raise ValidationError("File size cannot be empty")

    size_str = size_str.strip().upper()

    # Pattern for size with unit
    pattern = r'^(\d+(?:\.\d+)?)(B|KB|MB|GB|TB)$'
    match = re.match(pattern, size_str)

    if not match:
        raise ValidationError(
            f"Invalid file size format '{size_str}', expected format like '10MB' or '1.5GB'"
        )

    size_value = float(match.group(1))
    if size_value <= 0:
        raise ValidationError(f"File size must be positive, got {size_value}")

    return size_str


def validate_schedule_entries(entries: List[dict]) -> List[str]:
    """
    Validate a list of schedule entries for conflicts and correctness.

    Args:
        entries: List of schedule entry dictionaries

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    if not isinstance(entries, list):
        errors.append("Schedule must be a list")
        return errors

    enabled_times = []

    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"Schedule entry {i}: must be a dictionary")
            continue

        # Validate required fields
        if 'time' not in entry:
            errors.append(f"Schedule entry {i}: missing 'time' field")
            continue

        if 'percentage' not in entry:
            errors.append(f"Schedule entry {i}: missing 'percentage' field")
            continue

        # Validate time format
        try:
            validate_time_format(entry['time'])
        except TimeFormatValidationError as e:
            errors.append(f"Schedule entry {i}: {e}")

        # Validate percentage
        try:
            validate_percentage(entry['percentage'])
        except PercentageValidationError as e:
            errors.append(f"Schedule entry {i}: {e}")

        # Track enabled times for duplicate checking
        enabled = entry.get('enabled', True)
        if enabled and 'time' in entry:
            enabled_times.append(entry['time'])

    # Check for duplicate times
    seen_times = set()
    for time_str in enabled_times:
        if time_str in seen_times:
            errors.append(f"Duplicate schedule time found: {time_str}")
        seen_times.add(time_str)

    return errors


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
def validate_powerwall_config(config: dict) -> List[str]:
    """Validate powerwall configuration section."""
    errors = []

    if 'tesla_email' not in config:
        errors.append("Tesla email is required")
    else:
        try:
            validate_tesla_email(config['tesla_email'])
        except ValidationError as e:
            errors.append(str(e))

    if 'email' in config and config['email']:
        try:
            validate_email_format(config['email'])
        except ValidationError as e:
            errors.append(f"Email: {e}")

    if 'timeout' in config:
        try:
            validate_positive_number(config['timeout'], "timeout")
        except ValidationError as e:
            errors.append(str(e))

    if 'retry_attempts' in config:
        try:
            validate_non_negative_number(config['retry_attempts'], "retry_attempts")
        except ValidationError as e:
            errors.append(str(e))

    return errors


def validate_config(config: dict) -> List[str]:
    """
    Validate the entire configuration dictionary.

    Args:
        config: The configuration dictionary to validate.

    Returns:
        A list of validation error messages. An empty list indicates a valid configuration.
    """
    errors = []

    if not isinstance(config, dict):
        errors.append("Configuration must be a dictionary.")
        return errors

    # Validate top-level sections
    required_sections = ['powerwall', 'automation', 'web_interface', 'logging']
    for section in required_sections:
        if section not in config:
            errors.append(f"Missing required configuration section: '{section}'")
    if errors:
        return errors

    # Validate powerwall section
    errors.extend(validate_powerwall_config(config['powerwall']))

    # Validate automation section
    if 'schedule' in config['automation']:
        errors.extend(validate_schedule_entries(config['automation']['schedule']))

    return errors