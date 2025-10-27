"""
PowerNight Powerwall Data Operations

Enhanced data retrieval and parsing for Powerwall information.
"""

import logging
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from datetime import datetime

from .exceptions import PowerwallAPIError, PowerwallValidationError


@dataclass
class PowerwallReserveInfo:
    """Detailed backup reserve information."""
    current_percentage: float
    target_percentage: Optional[float]
    last_changed: Optional[datetime]
    is_adjusting: bool = False

    def __post_init__(self):
        if not 0 <= self.current_percentage <= 100:
            raise PowerwallValidationError(
                "current_percentage",
                self.current_percentage,
                "Must be between 0 and 100"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        if self.last_changed:
            data['last_changed'] = self.last_changed.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PowerwallReserveInfo":
        """Create from dictionary."""
        if 'last_changed' in data and data['last_changed']:
            data['last_changed'] = datetime.fromisoformat(data['last_changed'])
        return cls(**data)


@dataclass
class PowerwallBatteryInfo:
    """Detailed battery information."""
    percentage: float
    capacity_kwh: Optional[float]
    energy_remaining_kwh: Optional[float]
    power_kw: Optional[float]
    is_charging: bool
    is_discharging: bool
    temperature_celsius: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class PowerwallGridInfo:
    """Grid connection information."""
    is_connected: bool
    power_kw: Optional[float]
    frequency_hz: Optional[float]
    voltage_v: Optional[float]
    is_importing: bool
    is_exporting: bool

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class PowerwallSystemInfo:
    """Complete Powerwall system information."""
    reserve_info: PowerwallReserveInfo
    battery_info: PowerwallBatteryInfo
    grid_info: PowerwallGridInfo
    timestamp: datetime
    system_version: Optional[str] = None
    serial_number: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'reserve_info': self.reserve_info.to_dict(),
            'battery_info': self.battery_info.to_dict(),
            'grid_info': self.grid_info.to_dict(),
            'timestamp': self.timestamp.isoformat(),
            'system_version': self.system_version,
            'serial_number': self.serial_number
        }


class PowerwallDataParser:
    """Parse and validate Powerwall API responses."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def parse_reserve_percentage(self, raw_data: Any) -> float:
        """
        Parse backup reserve percentage from API response.

        Args:
            raw_data: Raw API response data

        Returns:
            Parsed backup reserve percentage

        Raises:
            PowerwallAPIError: If data cannot be parsed
            PowerwallValidationError: If percentage is invalid
        """
        try:
            if raw_data is None:
                raise PowerwallAPIError("No reserve data received from Powerwall")

            # Handle different response formats
            if isinstance(raw_data, (int, float)):
                percentage = float(raw_data)
            elif isinstance(raw_data, dict):
                # Try common field names
                for field in ['percentage', 'reserve', 'backup_reserve', 'value']:
                    if field in raw_data:
                        percentage = float(raw_data[field])
                        break
                else:
                    raise PowerwallAPIError(f"Cannot find reserve percentage in response: {raw_data}")
            else:
                raise PowerwallAPIError(f"Unexpected reserve data format: {type(raw_data)}")

            # Validate percentage range
            if not 0 <= percentage <= 100:
                raise PowerwallValidationError(
                    "percentage",
                    percentage,
                    "Reserve percentage must be between 0 and 100"
                )

            self.logger.debug(f"Parsed reserve percentage: {percentage}%")
            return percentage

        except (ValueError, TypeError) as e:
            raise PowerwallAPIError(f"Failed to parse reserve percentage: {e}")

    def parse_battery_info(self, vitals_data: Dict[str, Any]) -> PowerwallBatteryInfo:
        """
        Parse battery information from vitals data.

        Args:
            vitals_data: Powerwall vitals response

        Returns:
            PowerwallBatteryInfo object
        """
        try:
            battery_data = vitals_data.get('battery', {})

            return PowerwallBatteryInfo(
                percentage=float(battery_data.get('percentage', 0)),
                capacity_kwh=self._safe_float(battery_data.get('capacity_kwh')),
                energy_remaining_kwh=self._safe_float(battery_data.get('energy_remaining_kwh')),
                power_kw=self._safe_float(battery_data.get('power_kw')),
                is_charging=bool(battery_data.get('charging', False)),
                is_discharging=bool(battery_data.get('discharging', False)),
                temperature_celsius=self._safe_float(battery_data.get('temperature_celsius'))
            )

        except Exception as e:
            raise PowerwallAPIError(f"Failed to parse battery info: {e}")

    def parse_grid_info(self, vitals_data: Dict[str, Any]) -> PowerwallGridInfo:
        """
        Parse grid information from vitals data.

        Args:
            vitals_data: Powerwall vitals response

        Returns:
            PowerwallGridInfo object
        """
        try:
            grid_data = vitals_data.get('grid', {})

            power_kw = self._safe_float(grid_data.get('power_kw'))

            return PowerwallGridInfo(
                is_connected=bool(grid_data.get('connected', False)),
                power_kw=power_kw,
                frequency_hz=self._safe_float(grid_data.get('frequency_hz')),
                voltage_v=self._safe_float(grid_data.get('voltage_v')),
                is_importing=power_kw > 0 if power_kw is not None else False,
                is_exporting=power_kw < 0 if power_kw is not None else False
            )

        except Exception as e:
            raise PowerwallAPIError(f"Failed to parse grid info: {e}")

    def parse_system_info(self, vitals_data: Dict[str, Any], reserve_percentage: float) -> PowerwallSystemInfo:
        """
        Parse complete system information.

        Args:
            vitals_data: Powerwall vitals response
            reserve_percentage: Current backup reserve percentage

        Returns:
            PowerwallSystemInfo object
        """
        try:
            reserve_info = PowerwallReserveInfo(
                current_percentage=reserve_percentage,
                target_percentage=None,  # Would need additional API call
                last_changed=None,       # Would need historical data
                is_adjusting=False       # Could be determined by monitoring changes
            )

            battery_info = self.parse_battery_info(vitals_data)
            grid_info = self.parse_grid_info(vitals_data)

            return PowerwallSystemInfo(
                reserve_info=reserve_info,
                battery_info=battery_info,
                grid_info=grid_info,
                timestamp=datetime.now(),
                system_version=vitals_data.get('version'),
                serial_number=vitals_data.get('serial_number')
            )

        except Exception as e:
            raise PowerwallAPIError(f"Failed to parse system info: {e}")

    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float, returning None if conversion fails."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


class PowerwallDataCache:
    """Cache for Powerwall data to reduce API calls."""

    def __init__(self, ttl_seconds: float = 30.0) -> None:
        """
        Initialize data cache.

        Args:
            ttl_seconds: Time-to-live for cached data in seconds
        """
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger(__name__)

    def get(self, key: str) -> Optional[Any]:
        """
        Get cached data if not expired.

        Args:
            key: Cache key

        Returns:
            Cached data or None if expired/missing
        """
        if key not in self._cache:
            return None

        entry = self._cache[key]
        age = time.time() - entry['timestamp']

        if age > self.ttl_seconds:
            del self._cache[key]
            self.logger.debug(f"Cache entry '{key}' expired after {age:.1f}s")
            return None

        self.logger.debug(f"Cache hit for '{key}' (age: {age:.1f}s)")
        return entry['data']

    def set(self, key: str, data: Any) -> None:
        """
        Store data in cache.

        Args:
            key: Cache key
            data: Data to cache
        """
        self._cache[key] = {
            'data': data,
            'timestamp': time.time()
        }
        self.logger.debug(f"Cached data for '{key}'")

    def clear(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
        self.logger.debug("Cache cleared")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        current_time = time.time()
        valid_entries = 0
        expired_entries = 0

        for entry in self._cache.values():
            age = current_time - entry['timestamp']
            if age <= self.ttl_seconds:
                valid_entries += 1
            else:
                expired_entries += 1

        return {
            'total_entries': len(self._cache),
            'valid_entries': valid_entries,
            'expired_entries': expired_entries,
            'ttl_seconds': self.ttl_seconds
        }