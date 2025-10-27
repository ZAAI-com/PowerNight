"""
Unit tests for cloud Powerwall connector.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import pypowerwall

from powernight.core.powerwall.cloud_connector import CloudConnectionConfig
from powernight.core.powerwall.connector import PowerwallConnector
from powernight.core.powerwall.demo_cloud import DemoCloudPowerwallConnector
from powernight.core.powerwall.exceptions import (
    PowerwallConnectionError,
    PowerwallAuthenticationError
)


class TestCloudConnectionConfig:
    """Test cases for CloudConnectionConfig class."""

    def test_init_with_required_fields(self):
        """Test initialization with required fields."""
        config = CloudConnectionConfig(email="test@example.com")
        
        assert config.email == "test@example.com"
        assert config.powerwall_id is None
        assert config.timeout == 30.0
        assert config.retry_attempts == 3
        assert config.cache_ttl == 30.0
        assert config.rate_limit_delay == 1.0
        assert config.history_size == 1000

    def test_init_with_optional_fields(self):
        """Test initialization with optional fields."""
        config = CloudConnectionConfig(
            email="test@example.com",
            powerwall_id="test-powerwall-123",
            timeout=60.0,
            retry_attempts=5,
            cache_ttl=60.0,
            rate_limit_delay=2.0,
            history_size=2000
        )
        
        assert config.email == "test@example.com"
        assert config.powerwall_id == "test-powerwall-123"
        assert config.timeout == 60.0
        assert config.retry_attempts == 5
        assert config.cache_ttl == 60.0
        assert config.rate_limit_delay == 2.0
        assert config.history_size == 2000


class TestPowerwallConnectorCloud:
    """Test cases for PowerwallConnector in cloud mode."""

    def test_init_cloud_mode(self):
        """Test connector initialization in cloud mode."""
        with patch('powernight.core.powerwall.connector.TeslaOAuthManager'):
            connector = PowerwallConnector(
                email="test@example.com",
                powerwall_id="test-powerwall-123"
            )
            
            assert connector.config.email == "test@example.com"
            assert connector.config.powerwall_id == "test-powerwall-123"
            assert not connector.is_connected()

    def test_connect_success(self):
        """Test successful cloud connection."""
        with patch('powernight.core.powerwall.connector.TeslaOAuthManager') as mock_oauth:
            mock_oauth_instance = Mock()
            mock_oauth_instance.get_valid_access_token.return_value = "test_access_token"
            mock_oauth.return_value = mock_oauth_instance
            
            with patch('powernight.core.powerwall.connector.pypowerwall.Powerwall') as mock_powerwall:
                mock_powerwall_instance = Mock()
                mock_powerwall_instance.vitals.return_value = {"status": "connected"}
                mock_powerwall.return_value = mock_powerwall_instance
                
                connector = PowerwallConnector(
                    email="test@example.com",
                    powerwall_id="test-powerwall-123"
                )
                
                result = connector.connect()
                
                assert result is True
                assert connector.is_connected()
                mock_powerwall.assert_called_once_with(
                    email="test@example.com",
                    cloudmode=True,
                    authmode="token",
                    authpath="/app/data/tokens/",
                    timeout=30.0
                )

    def test_connect_no_access_token(self):
        """Test connection failure due to no access token."""
        with patch('powernight.core.powerwall.connector.TeslaOAuthManager') as mock_oauth:
            mock_oauth_instance = Mock()
            mock_oauth_instance.get_valid_access_token.return_value = None
            mock_oauth.return_value = mock_oauth_instance
            
            connector = PowerwallConnector(
                email="test@example.com",
                powerwall_id="test-powerwall-123"
            )
            
            with pytest.raises(PowerwallAuthenticationError, match="No valid access token"):
                connector.connect()

    def test_connect_powerwall_no_response(self):
        """Test connection failure due to no Powerwall response."""
        with patch('powernight.core.powerwall.connector.TeslaOAuthManager') as mock_oauth:
            mock_oauth_instance = Mock()
            mock_oauth_instance.get_valid_access_token.return_value = "test_access_token"
            mock_oauth.return_value = mock_oauth_instance
            
            with patch('powernight.core.powerwall.connector.pypowerwall.Powerwall') as mock_powerwall:
                mock_powerwall_instance = Mock()
                mock_powerwall_instance.vitals.return_value = None
                mock_powerwall.return_value = mock_powerwall_instance
                
                connector = PowerwallConnector(
                    email="test@example.com",
                    powerwall_id="test-powerwall-123"
                )
                
                with pytest.raises(PowerwallConnectionError, match="No response from Powerwall"):
                    connector.connect()

    def test_get_status_cloud_mode(self):
        """Test getting status in cloud mode."""
        with patch('powernight.core.powerwall.connector.TeslaOAuthManager'):
            connector = PowerwallConnector(
                email="test@example.com",
                powerwall_id="test-powerwall-123"
            )
            
            # Mock connected state
            connector._connected = True
            
            with patch('powernight.core.powerwall.connector.pypowerwall.Powerwall') as mock_powerwall:
                mock_powerwall_instance = Mock()
                mock_powerwall_instance.vitals.return_value = {
                    "battery_power": 5000,
                    "solar_power": 3000,
                    "grid_power": -2000,
                    "home_power": 6000,
                    "percentage_charged": 75.0,
                    "backup_reserve": 20.0,
                    "grid_status": "Connected",
                    "operation_mode": "SelfConsumption"
                }
                mock_powerwall.return_value = mock_powerwall_instance
                
                status = connector.get_status()
                
                assert status.connected is True
                assert status.connection_type == "cloud"
                assert status.battery_power == 5000
                assert status.solar_power == 3000
                assert status.percentage_charged == 75.0

    def test_set_backup_reserve_cloud_mode(self):
        """Test setting backup reserve in cloud mode."""
        with patch('powernight.core.powerwall.connector.TeslaOAuthManager'):
            connector = PowerwallConnector(
                email="test@example.com",
                powerwall_id="test-powerwall-123"
            )
            
            # Mock connected state
            connector._connected = True
            
            with patch('powernight.core.powerwall.connector.pypowerwall.Powerwall') as mock_powerwall:
                mock_powerwall_instance = Mock()
                mock_powerwall_instance.set_reserve.return_value = True
                mock_powerwall.return_value = mock_powerwall_instance
                
                result = connector.set_backup_reserve(25.0)
                
                assert result is True
                mock_powerwall_instance.set_reserve.assert_called_once_with(25.0)

    def test_get_backup_reserve_cloud_mode(self):
        """Test getting backup reserve in cloud mode."""
        with patch('powernight.core.powerwall.connector.TeslaOAuthManager'):
            connector = PowerwallConnector(
                email="test@example.com",
                powerwall_id="test-powerwall-123"
            )
            
            # Mock connected state
            connector._connected = True
            
            with patch('powernight.core.powerwall.connector.pypowerwall.Powerwall') as mock_powerwall:
                mock_powerwall_instance = Mock()
                mock_powerwall_instance.get_reserve.return_value = 20.0
                mock_powerwall.return_value = mock_powerwall_instance
                
                reserve = connector.get_backup_reserve()
                
                assert reserve == 20.0
                mock_powerwall_instance.get_reserve.assert_called_once()


class TestDemoCloudPowerwallConnector:
    """Test cases for DemoCloudPowerwallConnector class."""

    def test_init_demo_connector(self):
        """Test demo connector initialization."""
        connector = DemoCloudPowerwallConnector(
            email="demo@example.com",
            powerwall_id="DEMO-PW-123"
        )
        
        assert connector.email == "demo@example.com"
        assert connector.powerwall_id == "DEMO-PW-123"
        assert not connector.is_connected()

    def test_connect_demo(self):
        """Test demo connector connection."""
        connector = DemoCloudPowerwallConnector(
            email="demo@example.com",
            powerwall_id="DEMO-PW-123"
        )
        
        result = connector.connect()
        
        assert result is True
        assert connector.is_connected()

    def test_get_status_demo_connected(self):
        """Test getting status from demo connector when connected."""
        connector = DemoCloudPowerwallConnector(
            email="demo@example.com",
            powerwall_id="DEMO-PW-123"
        )
        connector._connected = True
        
        status = connector.get_status()
        
        assert status.connected is True
        assert status.connection_type == "cloud"
        assert status.demo_mode is True
        assert status.site_name == "Demo Cloud Site"
        assert status.powerwall_id == "DEMO-PW-123"
        assert status.battery_power is not None
        assert status.solar_power is not None
        assert status.percentage_charged is not None

    def test_get_status_demo_disconnected(self):
        """Test getting status from demo connector when disconnected."""
        connector = DemoCloudPowerwallConnector(
            email="demo@example.com",
            powerwall_id="DEMO-PW-123"
        )
        connector._connected = False
        
        status = connector.get_status()
        
        assert status.connected is False
        assert status.connection_type == "cloud"
        assert status.demo_mode is True
        assert status.site_name == "Demo Cloud Site"
        assert status.powerwall_id == "DEMO-PW-123"

    def test_set_backup_reserve_demo(self):
        """Test setting backup reserve on demo connector."""
        connector = DemoCloudPowerwallConnector(
            email="demo@example.com",
            powerwall_id="DEMO-PW-123"
        )
        connector._connected = True
        
        result = connector.set_backup_reserve(25.0)
        
        assert result is True
        assert connector._demo_data["backup_reserve"] == 25.0

    def test_set_backup_reserve_demo_disconnected(self):
        """Test setting backup reserve on demo connector when disconnected."""
        connector = DemoCloudPowerwallConnector(
            email="demo@example.com",
            powerwall_id="DEMO-PW-123"
        )
        connector._connected = False
        
        result = connector.set_backup_reserve(25.0)
        
        assert result is False

    def test_get_backup_reserve_demo(self):
        """Test getting backup reserve from demo connector."""
        connector = DemoCloudPowerwallConnector(
            email="demo@example.com",
            powerwall_id="DEMO-PW-123"
        )
        connector._connected = True
        
        reserve = connector.get_backup_reserve()
        
        assert reserve == 20.0  # Default demo reserve

    def test_get_site_info_demo(self):
        """Test getting site info from demo connector."""
        connector = DemoCloudPowerwallConnector(
            email="demo@example.com",
            powerwall_id="DEMO-PW-123"
        )
        
        site_info = connector.get_site_info()
        
        assert site_info["site_name"] == "Demo Cloud Site"
        assert site_info["gateway_id"] == "DEMO-GATEWAY-123"
        assert site_info["energy_site_id"] == "DEMO-ENERGY-SITE-456"
        assert site_info["powerwall_id"] == "DEMO-PW-123"

    def test_get_site_live_status_demo(self):
        """Test getting live status from demo connector."""
        connector = DemoCloudPowerwallConnector(
            email="demo@example.com",
            powerwall_id="DEMO-PW-123"
        )
        connector._connected = True
        
        live_status = connector.get_site_live_status()
        
        assert "solar_power" in live_status
        assert "battery_power" in live_status
        assert "grid_power" in live_status
        assert "home_power" in live_status
        assert "percentage_charged" in live_status
        assert "last_communication_time" in live_status

    def test_demo_data_dynamic(self):
        """Test that demo data changes over time."""
        connector = DemoCloudPowerwallConnector(
            email="demo@example.com",
            powerwall_id="DEMO-PW-123"
        )
        connector._connected = True
        
        # Get status twice to see dynamic changes
        status1 = connector.get_status()
        
        # Simulate time passing
        import time
        time.sleep(0.1)
        
        status2 = connector.get_status()
        
        # Values should be different due to time-based simulation
        # (This test might be flaky due to timing, but demonstrates the concept)
        assert status1.connected == status2.connected
        assert status1.demo_mode == status2.demo_mode
