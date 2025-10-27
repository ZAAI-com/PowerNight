"""
PowerNight Powerwall Authentication Utilities

Enhanced authentication and credential management for Powerwall connections.
"""

import logging
import hashlib
import base64
from typing import Optional, Dict, Any
from dataclasses import dataclass
from pathlib import Path

from .exceptions import PowerwallAuthenticationError, PowerwallValidationError


@dataclass
class PowerwallCredentials:
    """Powerwall authentication credentials."""
    host: str
    password: str
    email: Optional[str] = None

    def __post_init__(self):
        if not self.host:
            raise PowerwallValidationError("host", self.host, "Host cannot be empty")
        if not self.password:
            raise PowerwallValidationError("password", "", "Password cannot be empty")

    @property
    def password_hash(self) -> str:
        """Get hashed password for secure storage."""
        return hashlib.sha256(self.password.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "host": self.host,
            "password_hash": self.password_hash,
            "email": self.email
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], tesla_email: str) -> "PowerwallCredentials":
        """Create from dictionary with password."""
        return cls(
            host=data["host"],
            password=tesla_email,
            email=data.get("email")
        )


class PowerwallAuthManager:
    """Manages Powerwall authentication and credential validation."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def validate_host(self, host: str) -> bool:
        """
        Validate Powerwall host format.

        Args:
            host: IP address or hostname

        Returns:
            True if valid

        Raises:
            PowerwallValidationError: If host format is invalid
        """
        if not host:
            raise PowerwallValidationError("host", host, "Host cannot be empty")

        # Basic IP address validation
        if self._is_valid_ip(host):
            return True

        # Basic hostname validation
        if self._is_valid_hostname(host):
            return True

        raise PowerwallValidationError("host", host, "Invalid IP address or hostname format")

    def _is_valid_ip(self, ip: str) -> bool:
        """Check if string is a valid IPv4 address."""
        try:
            parts = ip.split('.')
            if len(parts) != 4:
                return False

            for part in parts:
                if not part.isdigit():
                    return False
                num = int(part)
                if not 0 <= num <= 255:
                    return False

            return True
        except (ValueError, AttributeError):
            return False

    def _is_valid_hostname(self, hostname: str) -> bool:
        """Check if string is a valid hostname."""
        if not hostname:
            return False

        if len(hostname) > 253:
            return False

        # Simple hostname validation
        allowed_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-')
        return all(c in allowed_chars for c in hostname)

    def validate_password(self, password: str) -> bool:
        """
        Validate Powerwall password.

        Args:
            password: Password to validate

        Returns:
            True if valid

        Raises:
            PowerwallValidationError: If password is invalid
        """
        if not password:
            raise PowerwallValidationError("password", "", "Password cannot be empty")

        if len(password) < 8:
            raise PowerwallValidationError("password", "", "Password must be at least 8 characters")

        return True

    def create_credentials(self, host: str, tesla_email: str, email: Optional[str] = None) -> PowerwallCredentials:
        """
        Create validated Powerwall credentials.

        Args:
            host: Powerwall IP address or hostname
            tesla_email: Tesla account email
            email: Optional email address

        Returns:
            PowerwallCredentials object

        Raises:
            PowerwallValidationError: If credentials are invalid
        """
        # Validate inputs
        self.validate_host(host)
        self.validate_password(tesla_email)

        return PowerwallCredentials(
            host=host,
            password=tesla_email,
            email=email
        )

    def test_credentials(self, credentials: PowerwallCredentials) -> bool:
        """
        Test credentials against Powerwall device.

        Args:
            credentials: Credentials to test

        Returns:
            True if credentials are valid

        Raises:
            PowerwallAuthenticationError: If authentication fails
        """
        from .connector import PowerwallConnector

        try:
            # Create temporary connector for testing
            connector = PowerwallConnector(
                host=credentials.host,
                password=credentials.password,
                timeout=10.0
            )

            # Test connection
            success = connector.test_connection()
            connector.disconnect()

            if success:
                self.logger.info(f"Authentication successful for {credentials.host}")
                return True
            else:
                raise PowerwallAuthenticationError("Authentication test failed")

        except Exception as e:
            self.logger.error(f"Authentication failed for {credentials.host}: {e}")
            raise PowerwallAuthenticationError(f"Authentication failed: {e}")


class PowerwallDiscovery:
    """Discover Powerwall devices on the local network."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def scan_network(self, network_range: str = "192.168.1.0/24") -> list[str]:
        """
        Scan network for Powerwall devices.

        Args:
            network_range: Network range to scan (CIDR notation)

        Returns:
            List of potential Powerwall IP addresses

        Note:
            This is a basic implementation. In production, you might want
            to use more sophisticated discovery methods.
        """
        import socket
        import ipaddress
        from concurrent.futures import ThreadPoolExecutor, as_completed

        potential_hosts = []

        try:
            network = ipaddress.IPv4Network(network_range, strict=False)
            hosts_to_check = [str(ip) for ip in network.hosts()]

            # Tesla Powerwall typically runs on port 443 (HTTPS)
            def check_host(ip: str) -> Optional[str]:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2)
                    result = sock.connect_ex((ip, 443))
                    sock.close()

                    if result == 0:
                        return ip
                except Exception:
                    pass
                return None

            # Use threading for faster scanning
            with ThreadPoolExecutor(max_workers=50) as executor:
                future_to_ip = {executor.submit(check_host, ip): ip for ip in hosts_to_check}

                for future in as_completed(future_to_ip):
                    result = future.result()
                    if result:
                        potential_hosts.append(result)
                        self.logger.info(f"Found potential Powerwall at {result}")

        except Exception as e:
            self.logger.error(f"Network scan failed: {e}")

        return potential_hosts

    def verify_powerwall(self, host: str) -> bool:
        """
        Verify if host is actually a Powerwall device.

        Args:
            host: IP address to verify

        Returns:
            True if host appears to be a Powerwall
        """
        try:
            import requests

            # Try to access Powerwall API endpoint
            response = requests.get(
                f"https://{host}/api/status",
                timeout=5,
                verify=False  # Powerwall uses self-signed certificates
            )

            # Look for Powerwall-specific indicators in response
            if response.status_code in [200, 401, 403]:
                # These responses indicate a Powerwall API endpoint
                return True

        except Exception as e:
            self.logger.debug(f"Verification failed for {host}: {e}")

        return False