"""
PowerNight Web API Validation

Request data validation functions and schemas.
"""

import re
from typing import Dict, List, Any, Optional
from datetime import datetime


def validate_config_data(data: Dict[str, Any]) -> List[str]:
    """
    Validate configuration data.

    Args:
        data: Configuration data to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    if not isinstance(data, dict):
        errors.append("Configuration data must be a dictionary")
        return errors

    # Validate powerwall configuration
    if 'powerwall' in data:
        powerwall_errors = _validate_powerwall_config(data['powerwall'])
        errors.extend([f"powerwall.{error}" for error in powerwall_errors])

    # Validate automation configuration
    if 'automation' in data:
        automation_errors = _validate_automation_config(data['automation'])
        errors.extend([f"automation.{error}" for error in automation_errors])

    # Validate web interface configuration (config schema section name is
    # 'web_interface')
    if 'web_interface' in data:
        web_errors = _validate_web_config(data['web_interface'])
        errors.extend([f"web_interface.{error}" for error in web_errors])

    # Validate logging configuration
    if 'logging' in data:
        logging_errors = _validate_logging_config(data['logging'])
        errors.extend([f"logging.{error}" for error in logging_errors])

    return errors


def validate_backup_reserve_data(data: Dict[str, Any]) -> List[str]:
    """
    Validate backup reserve data.

    Args:
        data: Backup reserve data to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    if not isinstance(data, dict):
        errors.append("Data must be a dictionary")
        return errors

    # Check required fields
    if 'percentage' not in data:
        errors.append("Missing required field: percentage")
        return errors

    # Validate percentage
    percentage = data['percentage']
    if not isinstance(percentage, (int, float)):
        errors.append("Percentage must be a number")
    elif not 0 <= percentage <= 100:
        errors.append("Percentage must be between 0 and 100")

    return errors


def _validate_powerwall_config(config: Dict[str, Any]) -> List[str]:
    """Validate Powerwall configuration section."""
    errors = []

    if not isinstance(config, dict):
        errors.append("Must be a dictionary")
        return errors

    # Validate IP address
    if 'tesla_email' in config:
        tesla_email = config['tesla_email']
        if not isinstance(tesla_email, str):
            errors.append("tesla_email must be a string")
        elif not _is_valid_email(tesla_email):
            errors.append("tesla_email must be a valid email address")

    # Validate email
    if 'email' in config:
        email = config['email']
        if not isinstance(email, str):
            errors.append("email must be a string")
        elif email and not _is_valid_email(email):
            errors.append("email must be a valid email address")

    # Validate password
    if 'password' in config:
        password = config['password']
        if not isinstance(password, str):
            errors.append("password must be a string")

    # Validate timeout
    if 'timeout' in config:
        timeout = config['timeout']
        if not isinstance(timeout, (int, float)):
            errors.append("timeout must be a number")
        elif timeout <= 0:
            errors.append("timeout must be positive")

    # Validate retry attempts
    if 'retry_attempts' in config:
        retry_attempts = config['retry_attempts']
        if not isinstance(retry_attempts, int):
            errors.append("retry_attempts must be an integer")
        elif retry_attempts < 0:
            errors.append("retry_attempts must be non-negative")

    # Validate verify_ssl
    if 'verify_ssl' in config:
        verify_ssl = config['verify_ssl']
        if not isinstance(verify_ssl, bool):
            errors.append("verify_ssl must be a boolean")

    return errors


def _validate_automation_config(config: Dict[str, Any]) -> List[str]:
    """Validate automation configuration section."""
    errors = []

    if not isinstance(config, dict):
        errors.append("Must be a dictionary")
        return errors

    # Validate enabled
    if 'enabled' in config:
        enabled = config['enabled']
        if not isinstance(enabled, bool):
            errors.append("enabled must be a boolean")

    # Validate check_interval
    if 'check_interval' in config:
        check_interval = config['check_interval']
        if not isinstance(check_interval, (int, float)):
            errors.append("check_interval must be a number")
        elif check_interval <= 0:
            errors.append("check_interval must be positive")

    # Validate schedule
    if 'schedule' in config:
        schedule = config['schedule']
        if not isinstance(schedule, list):
            errors.append("schedule must be a list")
        else:
            for i, entry in enumerate(schedule):
                entry_errors = _validate_schedule_entry(entry)
                errors.extend([f"schedule[{i}].{error}" for error in entry_errors])

    return errors


def _validate_schedule_entry(entry: Dict[str, Any]) -> List[str]:
    """Validate a single schedule entry."""
    errors = []

    if not isinstance(entry, dict):
        errors.append("Must be a dictionary")
        return errors

    # Validate time
    if 'time' not in entry:
        errors.append("Missing required field: time")
    else:
        time_str = entry['time']
        if not isinstance(time_str, str):
            errors.append("time must be a string")
        elif not _is_valid_time_format(time_str):
            errors.append("time must be in HH:MM format")

    # Validate percentage
    if 'percentage' not in entry:
        errors.append("Missing required field: percentage")
    else:
        percentage = entry['percentage']
        if not isinstance(percentage, (int, float)):
            errors.append("percentage must be a number")
        elif not 0 <= percentage <= 100:
            errors.append("percentage must be between 0 and 100")

    # Validate enabled
    if 'enabled' in entry:
        enabled = entry['enabled']
        if not isinstance(enabled, bool):
            errors.append("enabled must be a boolean")

    # Validate description
    if 'description' in entry:
        description = entry['description']
        if not isinstance(description, str):
            errors.append("description must be a string")

    return errors


def _validate_web_config(config: Dict[str, Any]) -> List[str]:
    """Validate web configuration section."""
    errors = []

    if not isinstance(config, dict):
        errors.append("Must be a dictionary")
        return errors

    # Validate host
    if 'host' in config:
        host = config['host']
        if not isinstance(host, str):
            errors.append("host must be a string")

    # Validate port
    if 'port' in config:
        port = config['port']
        if not isinstance(port, int):
            errors.append("port must be an integer")
        elif not 1 <= port <= 65535:
            errors.append("port must be between 1 and 65535")

    # Validate debug
    if 'debug' in config:
        debug = config['debug']
        if not isinstance(debug, bool):
            errors.append("debug must be a boolean")

    # Validate cors_origins
    if 'cors_origins' in config:
        cors_origins = config['cors_origins']
        if not isinstance(cors_origins, list):
            errors.append("cors_origins must be a list")
        else:
            for i, origin in enumerate(cors_origins):
                if not isinstance(origin, str):
                    errors.append(f"cors_origins[{i}] must be a string")

    return errors


def _validate_logging_config(config: Dict[str, Any]) -> List[str]:
    """Validate logging configuration section."""
    errors = []

    if not isinstance(config, dict):
        errors.append("Must be a dictionary")
        return errors

    # Validate level
    if 'level' in config:
        level = config['level']
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if not isinstance(level, str):
            errors.append("level must be a string")
        elif level.upper() not in valid_levels:
            errors.append(f"level must be one of: {', '.join(valid_levels)}")

    # Validate file_enabled
    if 'file_enabled' in config:
        file_enabled = config['file_enabled']
        if not isinstance(file_enabled, bool):
            errors.append("file_enabled must be a boolean")

    # Validate max_file_size
    if 'max_file_size' in config:
        max_file_size = config['max_file_size']
        if not isinstance(max_file_size, int):
            errors.append("max_file_size must be an integer")
        elif max_file_size <= 0:
            errors.append("max_file_size must be positive")

    # Validate backup_count
    if 'backup_count' in config:
        backup_count = config['backup_count']
        if not isinstance(backup_count, int):
            errors.append("backup_count must be an integer")
        elif backup_count < 0:
            errors.append("backup_count must be non-negative")

    return errors


def _is_valid_email(email: str) -> bool:
    """Check if string is a valid email address."""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def _is_valid_time_format(time_str: str) -> bool:
    """Check if string is in valid HH:MM format."""
    try:
        datetime.strptime(time_str, '%H:%M')
        return True
    except ValueError:
        return False