"""
Tests for configuration validation functions.
"""

import pytest
from datetime import time

from powernight.core.config.validators import (
    ValidationError,
    PercentageValidationError,
    TimeFormatValidationError,
    validate_percentage,
    validate_time_format,
    validate_timezone,
    validate_port_number,
    validate_positive_number,
    validate_non_negative_number,
    validate_log_level,
    validate_email_format
)


class TestPercentageValidation:
    """Test percentage validation."""

    def test_valid_percentages(self):
        """Test valid percentage values."""
        valid_percentages = [0, 0.0, 50, 50.5, 100, 100.0]

        for percentage in valid_percentages:
            result = validate_percentage(percentage)
            assert result == float(percentage)

    def test_invalid_percentages(self):
        """Test invalid percentage values."""
        invalid_percentages = [-1, 101, -0.1, 100.1, "not_a_number", None]

        for percentage in invalid_percentages:
            with pytest.raises(PercentageValidationError):
                validate_percentage(percentage)


class TestTimeFormatValidation:
    """Test time format validation."""

    def test_valid_time_formats(self):
        """Test valid time formats."""
        valid_times = [
            ("00:00", time(0, 0)),
            ("12:30", time(12, 30)),
            ("23:59", time(23, 59)),
            ("9:15", time(9, 15))
        ]

        for time_str, expected_time in valid_times:
            result = validate_time_format(time_str)
            assert result == expected_time

    def test_invalid_time_formats(self):
        """Test invalid time formats."""
        invalid_times = [
            "",
            "24:00",
            "12:60",
            "12",
            "12:30:45",
            "not_a_time",
            "25:30"
        ]

        for time_str in invalid_times:
            with pytest.raises(TimeFormatValidationError):
                validate_time_format(time_str)


class TestTimezoneValidation:
    """Test timezone validation."""

    def test_valid_timezones(self):
        """Test valid timezone strings."""
        valid_timezones = [
            "UTC",
            "America/Los_Angeles",
            "Europe/London",
            "Asia/Tokyo"
        ]

        for tz in valid_timezones:
            result = validate_timezone(tz)
            assert result == tz

    def test_invalid_timezones(self):
        """Test invalid timezone strings."""
        invalid_timezones = [
            "",
            "Invalid/Timezone",
            "123",
            None
        ]

        for tz in invalid_timezones:
            with pytest.raises(ValidationError):
                validate_timezone(tz)


class TestPortNumberValidation:
    """Test port number validation."""

    def test_valid_port_numbers(self):
        """Test valid port numbers."""
        valid_ports = [1, 80, 443, 5000, 8080, 65535, "5000"]

        for port in valid_ports:
            result = validate_port_number(port)
            assert result == int(port)

    def test_invalid_port_numbers(self):
        """Test invalid port numbers."""
        invalid_ports = [0, -1, 65536, 100000, "not_a_number", None]

        for port in invalid_ports:
            with pytest.raises(ValidationError):
                validate_port_number(port)


class TestNumberValidation:
    """Test number validation functions."""

    def test_positive_numbers(self):
        """Test positive number validation."""
        valid_numbers = [1, 1.0, 0.1, 100, 999.99]

        for number in valid_numbers:
            result = validate_positive_number(number)
            assert result == float(number)

    def test_invalid_positive_numbers(self):
        """Test invalid positive numbers."""
        invalid_numbers = [0, -1, -0.1, "not_a_number", None]

        for number in invalid_numbers:
            with pytest.raises(ValidationError):
                validate_positive_number(number)

    def test_non_negative_numbers(self):
        """Test non-negative number validation."""
        valid_numbers = [0, 0.0, 1, 1.0, 100, 999.99]

        for number in valid_numbers:
            result = validate_non_negative_number(number)
            assert result == float(number)

    def test_invalid_non_negative_numbers(self):
        """Test invalid non-negative numbers."""
        invalid_numbers = [-1, -0.1, "not_a_number", None]

        for number in invalid_numbers:
            with pytest.raises(ValidationError):
                validate_non_negative_number(number)


class TestLogLevelValidation:
    """Test log level validation."""

    def test_valid_log_levels(self):
        """Test valid log levels."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        valid_levels_lower = ["debug", "info", "warning", "error", "critical"]

        for level in valid_levels + valid_levels_lower:
            result = validate_log_level(level)
            assert result == level.upper()

    def test_invalid_log_levels(self):
        """Test invalid log levels."""
        invalid_levels = ["", "INVALID", "TRACE", None]

        for level in invalid_levels:
            with pytest.raises(ValidationError):
                validate_log_level(level)


class TestEmailValidation:
    """Test email validation."""

    def test_valid_emails(self):
        """Test valid email addresses."""
        valid_emails = [
            "test@example.com",
            "user.name@domain.co.uk",
            "user+tag@example.org",
            "123@example.com"
        ]

        for email in valid_emails:
            result = validate_email_format(email)
            assert result == email.lower()

    def test_invalid_emails(self):
        """Test invalid email addresses."""
        invalid_emails = [
            "",
            "not_an_email",
            "@example.com",
            "user@",
            "user@domain",
            "a" * 250 + "@example.com",  # Too long
            None
        ]

        for email in invalid_emails:
            with pytest.raises(ValidationError):
                validate_email_format(email)