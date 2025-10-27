"""
Demo cloud Powerwall connector for testing and demonstration.

Simulates cloud-based Powerwall behavior without requiring Tesla authentication.
"""

import time
import random
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from .cloud_connector import CloudPowerwallConnectorInterface, CloudConnectionConfig
from .connector import PowerwallStatus
from .exceptions import PowerwallError
from ...utils.logging import get_logger


class DemoCloudPowerwallConnector(CloudPowerwallConnectorInterface):
    """
    Demo cloud Powerwall connector for testing.
    
    Simulates multiple Powerwalls with realistic data patterns.
    """
    
    def __init__(self, config: CloudConnectionConfig) -> None:
        """Initialize demo cloud connector."""
        self.config = config
        self.logger = get_logger()
        self._connected = False
        self._current_powerwall_id = config.powerwall_id or "demo_powerwall_1"
        
        # Demo Powerwall data
        self._demo_powerwalls = [
            {
                'id': 'demo_powerwall_1',
                'serial_number': 'T1234567890',
                'site_id': 'demo_site_1',
                'display_name': 'Demo Powerwall 1',
                'energy_site_id': 'demo_energy_site_1',
                'resource_type': 'battery',
                'state': 'online',
                'components': {'battery': True, 'solar': True, 'grid': True}
            },
            {
                'id': 'demo_powerwall_2',
                'serial_number': 'T0987654321',
                'site_id': 'demo_site_2',
                'display_name': 'Demo Powerwall 2',
                'energy_site_id': 'demo_energy_site_2',
                'resource_type': 'battery',
                'state': 'online',
                'components': {'battery': True, 'solar': False, 'grid': True}
            }
        ]
        
        # Demo status data
        self._demo_status = {
            'battery_level': 85.0,
            'backup_reserve_percentage': 20.0,
            'solar_power': 2500.0,
            'grid_power': -500.0,
            'home_power': 2000.0,
            'battery_power': -1000.0,
            'connected': True,
            'demo_mode': True
        }
    
    def connect(self) -> bool:
        """Simulate cloud connection."""
        self.logger.info("Demo cloud Powerwall connection established")
        self._connected = True
        return True
    
    def disconnect(self) -> None:
        """Simulate disconnection."""
        self.logger.info("Demo cloud Powerwall disconnected")
        self._connected = False
    
    def is_connected(self) -> bool:
        """Check demo connection status."""
        return self._connected
    
    def get_status(self) -> PowerwallStatus:
        """Get demo Powerwall status with realistic variations."""
        if not self._connected:
            raise PowerwallError("Not connected to demo Powerwall")
        
        # Add some realistic variation to demo data
        variation = random.uniform(0.95, 1.05)
        
        # Create status data with only the parameters that PowerwallStatus accepts
        status_data = {
            'battery_level': max(0, min(100, self._demo_status['battery_level'] * variation)),
            'backup_reserve_percentage': self._demo_status['backup_reserve_percentage'],
            'is_charging': self._demo_status['battery_power'] < 0,  # Negative power means charging
            'is_grid_connected': True,
            'last_updated': time.time()
        }
        
        return PowerwallStatus(**status_data)
    
    def get_powerwalls(self) -> List[Dict[str, Any]]:
        """Get demo Powerwalls list."""
        return self._demo_powerwalls.copy()
    
    def switch_powerwall(self, powerwall_id: str) -> bool:
        """Switch to different demo Powerwall."""
        if any(pw['id'] == powerwall_id for pw in self._demo_powerwalls):
            self._current_powerwall_id = powerwall_id
            self.logger.info(f"Switched to demo Powerwall: {powerwall_id}")
            return True
        return False
    
    def set_backup_reserve(self, percentage: float) -> bool:
        """Simulate setting backup reserve."""
        if not self._connected:
            raise PowerwallError("Not connected to demo Powerwall")
        
        if 0 <= percentage <= 100:
            self._demo_status['backup_reserve_percentage'] = percentage
            self.logger.info(f"Demo backup reserve set to {percentage}%")
            return True
        return False
    
    def get_connection_info(self) -> Dict[str, Any]:
        """Get demo connection info."""
        return {
            'connection_type': 'cloud_demo',
            'email': 'demo@example.com',
            'powerwall_id': self._current_powerwall_id,
            'connected': self._connected,
            'demo_mode': True,
            'available_powerwalls': len(self._demo_powerwalls)
        }
