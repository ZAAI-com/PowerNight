"""
Timezone utilities for PowerNight.

This module provides timezone-aware datetime formatting functions that convert
UTC timestamps from the database to the user's configured timezone for display.
"""

import pytz
from datetime import datetime, timezone
from typing import Optional, Union


def get_configured_timezone() -> str:
    """
    Get the user's configured timezone from the application config.
    
    Returns:
        str: Timezone string (e.g., 'Europe/Berlin')
    """
    try:
        # Import here to avoid circular dependency
        from ..core.config import get_config
        config = get_config()
        return config.automation.timezone
    except Exception:
        # Fallback to UTC if config is not available
        return 'UTC'


def convert_utc_to_timezone(utc_datetime: Union[datetime, str], target_timezone: Optional[str] = None) -> datetime:
    """
    Convert a UTC datetime to the specified timezone.
    
    Args:
        utc_datetime: UTC datetime object or ISO string
        target_timezone: Target timezone string. If None, uses configured timezone.
        
    Returns:
        datetime: Datetime object in the target timezone
        
    Raises:
        ValueError: If timezone is invalid or datetime parsing fails
    """
    if target_timezone is None:
        target_timezone = get_configured_timezone()
    
    # Parse string to datetime if needed
    if isinstance(utc_datetime, str):
        # Handle ISO format strings
        if utc_datetime.endswith('Z'):
            utc_datetime = utc_datetime.replace('Z', '+00:00')
        utc_datetime = datetime.fromisoformat(utc_datetime)
    
    # Ensure datetime is timezone-aware and in UTC
    if utc_datetime.tzinfo is None:
        utc_datetime = utc_datetime.replace(tzinfo=timezone.utc)
    elif utc_datetime.tzinfo != timezone.utc:
        utc_datetime = utc_datetime.astimezone(timezone.utc)
    
    # Convert to target timezone
    try:
        target_tz = pytz.timezone(target_timezone)
        return utc_datetime.astimezone(target_tz)
    except pytz.exceptions.UnknownTimeZoneError:
        raise ValueError(f"Invalid timezone: {target_timezone}")


def format_datetime_for_display(utc_datetime: Union[datetime, str], target_timezone: Optional[str] = None) -> str:
    """
    Format a UTC datetime to the standard display format in the specified timezone.
    
    Format: "yyyy-MM-dd HH:mm:ss"
    
    Args:
        utc_datetime: UTC datetime object or ISO string
        target_timezone: Target timezone string. If None, uses configured timezone.
        
    Returns:
        str: Formatted datetime string (e.g., "2025-10-19 14:35:42")
        
    Raises:
        ValueError: If timezone is invalid or datetime parsing fails
    """
    try:
        local_datetime = convert_utc_to_timezone(utc_datetime, target_timezone)
        return local_datetime.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        # Return a safe fallback for invalid dates
        return 'Invalid Date'


def format_datetime_with_timezone(utc_datetime: Union[datetime, str], target_timezone: Optional[str] = None) -> str:
    """
    Format a UTC datetime with timezone abbreviation for display.
    
    Format: "yyyy-MM-dd HH:mm:ss (TZ)"
    
    Args:
        utc_datetime: UTC datetime object or ISO string
        target_timezone: Target timezone string. If None, uses configured timezone.
        
    Returns:
        str: Formatted datetime string with timezone (e.g., "2025-10-19 14:35:42 (CET)")
    """
    try:
        local_datetime = convert_utc_to_timezone(utc_datetime, target_timezone)
        timezone_abbr = local_datetime.strftime('%Z')
        formatted_date = local_datetime.strftime('%Y-%m-%d %H:%M:%S')
        return f"{formatted_date} ({timezone_abbr})"
    except Exception as e:
        return 'Invalid Date'


def get_current_time_in_timezone(target_timezone: Optional[str] = None) -> str:
    """
    Get the current time in the specified timezone.
    
    Args:
        target_timezone: Target timezone string. If None, uses configured timezone.
        
    Returns:
        str: Current time formatted as "yyyy-MM-dd HH:mm:ss"
    """
    utc_now = datetime.now(timezone.utc)
    return format_datetime_for_display(utc_now, target_timezone)


def get_current_time_with_timezone(target_timezone: Optional[str] = None) -> str:
    """
    Get the current time in the specified timezone with timezone abbreviation.
    
    Args:
        target_timezone: Target timezone string. If None, uses configured timezone.
        
    Returns:
        str: Current time formatted as "yyyy-MM-dd HH:mm:ss (TZ)"
    """
    utc_now = datetime.now(timezone.utc)
    return format_datetime_with_timezone(utc_now, target_timezone)


def safe_format_datetime(utc_datetime: Union[datetime, str, None], target_timezone: Optional[str] = None) -> str:
    """
    Safely format a datetime, handling None values and invalid dates gracefully.
    
    Args:
        utc_datetime: UTC datetime object, ISO string, or None
        target_timezone: Target timezone string. If None, uses configured timezone.
        
    Returns:
        str: Formatted datetime string or 'Never' for None values
    """
    if utc_datetime is None:
        return 'Never'
    
    try:
        return format_datetime_for_display(utc_datetime, target_timezone)
    except Exception:
        return 'Invalid Date'
