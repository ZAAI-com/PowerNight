"""
Unit tests for Powerwall connection module.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import pypowerwall

from powernight.core.powerwall.connector import PowerwallConnector, PowerwallStatus
from powernight.core.powerwall.auth import PowerwallAuthManager, PowerwallCredentials
from powernight.core.powerwall.exceptions import (
    PowerwallConnectionError,
    PowerwallAuthenticationError,
    PowerwallValidationError,
    PowerwallUnavailableError
)


class TestPowerwallConnector:
    """Test cases for PowerwallConnector class."""

    def test_init_valid_config(self):
        """Test connector initialization with valid configuration."""
        connector = PowerwallConnector(email="test@example.com", powerwall_id="test-123")
        assert connector.config.email == "test@example.com"
        assert connector.config.powerwall_id == "test-123"
        assert not connector.is_connected()

    def test_init_invalid_email(self):
        """Test connector initialization with invalid email."""
        with pytest.raises(PowerwallValidationError):
            PowerwallConnector(email="", powerwall_id="test-123")

    def test_init_invalid_email_format(self):
        """Test connector initialization with invalid email format."""
        with pytest.raises(PowerwallValidationError):
            PowerwallConnector(email="invalid-email", powerwall_id="test-123")

    def test_validate_percentage_valid(self):
        """Test percentage validation with valid values."""
        connector = PowerwallConnector(email="test@example.com", powerwall_id="test-123")

        # Test valid percentages
        connector._validate_percentage(0)
        connector._validate_percentage(50)
        connector._validate_percentage(100)
        connector._validate_percentage(0.5)

    def test_validate_percentage_invalid(self):
        """Test percentage validation with invalid values."""
        connector = PowerwallConnector(email="test@example.com", powerwall_id="test-123")

        # Test invalid percentages
        with pytest.raises(PowerwallValidationError):
            connector._validate_percentage(-1)

        with pytest.raises(PowerwallValidationError):
            connector._validate_percentage(101)

        with pytest.raises(PowerwallValidationError):
            connector._validate_percentage("invalid")

    @patch('pypowerwall.Powerwall')
    def test_connect_success(self, mock_powerwall):
        """Test successful connection to Powerwall."""
        # Mock successful connection
        mock_instance = Mock()
        mock_instance.vitals.return_value = {"battery": {"percentage": 85}}
        mock_powerwall.return_value = mock_instance

        connector = PowerwallConnector(email="test@example.com", powerwall_id="test-123")
        result = connector.connect()

        assert result is True
        assert connector.is_connected()
        mock_powerwall.assert_called_once()

    @patch('pypowerwall.Powerwall')
    def test_connect_authentication_error(self, mock_powerwall):
        """Test connection with authentication error."""
        # Mock authentication failure
        mock_powerwall.side_effect = pypowerwall.PyPowerwallError("authentication failed")

        connector = PowerwallConnector(email="test@example.com", powerwall_id="test-123")

        with pytest.raises(PowerwallAuthenticationError):
            connector.connect()

    @patch('pypowerwall.Powerwall')
    def test_connect_connection_error(self, mock_powerwall):
        """Test connection with general connection error."""
        # Mock connection failure
        mock_powerwall.side_effect = pypowerwall.PyPowerwallError("connection failed")

        connector = PowerwallConnector(email="test@example.com", powerwall_id="test-123")

        with pytest.raises(PowerwallConnectionError):
            connector.connect()

    @patch('pypowerwall.Powerwall')
    def test_get_backup_reserve_success(self, mock_powerwall):
        """Test getting backup reserve percentage."""
        # Mock successful API call
        mock_instance = Mock()
        mock_instance.vitals.return_value = {"battery": {"percentage": 85}}
        mock_instance.get_reserve.return_value = 40.0
        mock_powerwall.return_value = mock_instance

        connector = PowerwallConnector(email="test@example.com", powerwall_id="test-123")
        connector.connect()

        reserve = connector.get_backup_reserve_percentage()
        assert reserve == 40.0

    @patch('pypowerwall.Powerwall')
    def test_set_backup_reserve_success(self, mock_powerwall):
        """Test setting backup reserve percentage."""
        # Mock successful API calls
        mock_instance = Mock()
        mock_instance.vitals.return_value = {"battery": {"percentage": 85}}
        mock_instance.set_reserve.return_value = True
        mock_instance.get_reserve.return_value = 50.0
        mock_powerwall.return_value = mock_instance

        connector = PowerwallConnector(email="test@example.com", powerwall_id="test-123")
        connector.connect()

        result = connector.set_backup_reserve_percentage(50.0)
        assert result is True

    def test_context_manager(self):
        """Test connector as context manager."""
        with patch('pypowerwall.Powerwall') as mock_powerwall:
            mock_instance = Mock()
            mock_instance.vitals.return_value = {"battery": {"percentage": 85}}
            mock_powerwall.return_value = mock_instance

            with PowerwallConnector(host="192.168.1.100", password="test123") as connector:
                assert connector.is_connected()

            # Should be disconnected after exiting context
            assert not connector.is_connected()


class TestPowerwallAuthManager:
    """Test cases for PowerwallAuthManager class."""

    def test_validate_host_valid_ip(self):
        """Test host validation with valid IP addresses."""
        auth_manager = PowerwallAuthManager()

        assert auth_manager.validate_host("192.168.1.100")
        assert auth_manager.validate_host("10.0.0.1")
        assert auth_manager.validate_host("172.16.254.1")

    def test_validate_host_invalid_ip(self):
        """Test host validation with invalid IP addresses."""
        auth_manager = PowerwallAuthManager()

        with pytest.raises(PowerwallValidationError):
            auth_manager.validate_host("256.256.256.256")

        with pytest.raises(PowerwallValidationError):
            auth_manager.validate_host("192.168.1")

        with pytest.raises(PowerwallValidationError):
            auth_manager.validate_host("")

    def test_validate_host_valid_hostname(self):
        """Test host validation with valid hostnames."""
        auth_manager = PowerwallAuthManager()

        assert auth_manager.validate_host("powerwall.local")
        assert auth_manager.validate_host("tesla-powerwall")

    def test_validate_password_valid(self):
        """Test password validation with valid passwords."""
        auth_manager = PowerwallAuthManager()

        assert auth_manager.validate_password("password123")
        assert auth_manager.validate_password("mysecretpw")

    def test_validate_password_invalid(self):
        """Test password validation with invalid passwords."""
        auth_manager = PowerwallAuthManager()

        with pytest.raises(PowerwallValidationError):
            auth_manager.validate_password("")

        with pytest.raises(PowerwallValidationError):
            auth_manager.validate_password("short")

    def test_create_credentials_valid(self):
        """Test creating valid credentials."""
        auth_manager = PowerwallAuthManager()

        credentials = auth_manager.create_credentials(
            host="192.168.1.100",
            password="password123",
            email="user@example.com"
        )

        assert credentials.host == "192.168.1.100"
        assert credentials.password == "password123"
        assert credentials.email == "user@example.com"

    def test_create_credentials_invalid(self):
        """Test creating credentials with invalid data."""
        auth_manager = PowerwallAuthManager()

        with pytest.raises(PowerwallValidationError):
            auth_manager.create_credentials(host="", password="password123")


class TestPowerwallCredentials:
    """Test cases for PowerwallCredentials class."""

    def test_init_valid(self):
        """Test credentials initialization with valid data."""
        credentials = PowerwallCredentials(
            host="192.168.1.100",
            password="password123",
            email="user@example.com"
        )

        assert credentials.host == "192.168.1.100"
        assert credentials.password == "password123"
        assert credentials.email == "user@example.com"

    def test_init_invalid_host(self):
        """Test credentials initialization with invalid host."""
        with pytest.raises(PowerwallValidationError):
            PowerwallCredentials(host="", password="password123")

    def test_init_invalid_password(self):
        """Test credentials initialization with invalid password."""
        with pytest.raises(PowerwallValidationError):
            PowerwallCredentials(host="192.168.1.100", password="")

    def test_password_hash(self):
        """Test password hashing functionality."""
        credentials = PowerwallCredentials(
            host="192.168.1.100",
            password="password123"
        )

        hash1 = credentials.password_hash
        hash2 = credentials.password_hash

        # Hash should be consistent
        assert hash1 == hash2

        # Hash should be different from original password
        assert hash1 != "password123"

    def test_to_dict(self):
        """Test converting credentials to dictionary."""
        credentials = PowerwallCredentials(
            host="192.168.1.100",
            password="password123",
            email="user@example.com"
        )

        data = credentials.to_dict()

        assert data["host"] == "192.168.1.100"
        assert data["email"] == "user@example.com"
        assert "password_hash" in data
        assert "password" not in data  # Should not include plain password

    def test_from_dict(self):
        """Test creating credentials from dictionary."""
        data = {
            "host": "192.168.1.100",
            "password_hash": "some_hash",
            "email": "user@example.com"
        }

        credentials = PowerwallCredentials.from_dict(data, "password123")

        assert credentials.host == "192.168.1.100"
        assert credentials.password == "password123"
        assert credentials.email == "user@example.com"