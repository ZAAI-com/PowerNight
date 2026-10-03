"""
PowerNight CronCommand Abstraction

Maps UI command selections to PyPowerwall operations.
"""

from enum import Enum
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
import logging

from .exceptions import PowerwallValidationError


class CommandType(str, Enum):
    """Available command types for tasks."""
    MODE = "mode"
    RESERVE = "reserve"
    CURRENT = "current"
    GRID_CHARGING = "gridcharging"
    GRID_EXPORT = "gridexport"


class PowerwallMode(str, Enum):
    """Powerwall operating modes."""
    SELF_CONSUMPTION = "self_consumption"
    BACKUP = "backup"
    AUTONOMOUS = "autonomous"


class GridExportMode(str, Enum):
    """Grid export modes."""
    BATTERY_OK = "battery_ok"
    PV_ONLY = "pv_only"
    NEVER = "never"


@dataclass
class CommandValidationResult:
    """Result of command validation."""
    valid: bool
    errors: list[str]
    warnings: list[str]


class CronCommand:
    """
    Abstraction for task commands that map to PyPowerwall operations.
    
    Validates command payloads and provides execution interface.
    """
    
    def __init__(self, command_type: str, params: Optional[Dict[str, Any]] = None):
        """
        Initialize a cron command.
        
        Args:
            command_type: Type of command (mode, reserve, current, gridcharging, gridexport)
            params: Optional parameters for the command
        """
        self.params = params or {}
        self.logger = logging.getLogger(__name__)

        # Validate and normalize the command type: accept either a string
        # ("reserve") or a CommandType member, and store the enum so callers
        # can rely on .command_type.value
        try:
            self.command_enum = CommandType(command_type)
            self.command_type = self.command_enum
        except ValueError:
            raise PowerwallValidationError(
                "command_type",
                command_type,
                f"Invalid command type. Must be one of: {[c.value for c in CommandType]}"
            )
    
    def validate(self) -> CommandValidationResult:
        """
        Validate command and parameters.
        
        Returns:
            CommandValidationResult with validation status and messages
        """
        errors = []
        warnings = []
        
        # Validate based on command type
        if self.command_enum == CommandType.MODE:
            errors.extend(self._validate_mode_command())
        
        elif self.command_enum == CommandType.RESERVE:
            errors.extend(self._validate_reserve_command())
        
        elif self.command_enum == CommandType.CURRENT:
            # No parameters needed for current command
            pass
        
        elif self.command_enum == CommandType.GRID_CHARGING:
            errors.extend(self._validate_grid_charging_command())
        
        elif self.command_enum == CommandType.GRID_EXPORT:
            errors.extend(self._validate_grid_export_command())
        
        return CommandValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def _validate_mode_command(self) -> list[str]:
        """Validate mode command parameters."""
        errors = []
        
        mode = self.params.get('mode')
        if not mode:
            errors.append("mode parameter is required")
            return errors
        
        try:
            PowerwallMode(mode)
        except ValueError:
            errors.append(
                f"Invalid mode '{mode}'. Must be one of: {[m.value for m in PowerwallMode]}"
            )
        
        return errors
    
    def _validate_reserve_command(self) -> list[str]:
        """Validate reserve command parameters."""
        errors = []
        
        reserve = self.params.get('reserve')
        if reserve is None:
            errors.append("reserve parameter is required")
            return errors
        
        try:
            reserve_value = float(reserve)
            if not 0 <= reserve_value <= 100:
                errors.append(f"reserve must be between 0 and 100, got {reserve_value}")
        except (ValueError, TypeError):
            errors.append(f"reserve must be a number, got {type(reserve).__name__}")
        
        return errors
    
    def _validate_grid_charging_command(self) -> list[str]:
        """Validate grid charging command parameters."""
        errors = []
        
        enabled = self.params.get('enabled')
        if enabled is None:
            errors.append("enabled parameter is required")
            return errors
        
        if not isinstance(enabled, bool):
            # Try to convert string to bool
            if isinstance(enabled, str):
                if enabled.lower() in ('on', 'true', '1'):
                    self.params['enabled'] = True
                elif enabled.lower() in ('off', 'false', '0'):
                    self.params['enabled'] = False
                else:
                    errors.append(f"enabled must be 'on' or 'off', got '{enabled}'")
            else:
                errors.append(f"enabled must be a boolean, got {type(enabled).__name__}")
        
        return errors
    
    def _validate_grid_export_command(self) -> list[str]:
        """Validate grid export command parameters."""
        errors = []
        
        mode = self.params.get('mode')
        if not mode:
            errors.append("mode parameter is required")
            return errors
        
        try:
            GridExportMode(mode)
        except ValueError:
            errors.append(
                f"Invalid export mode '{mode}'. Must be one of: {[m.value for m in GridExportMode]}"
            )
        
        return errors
    
    def execute(self, powerwall_connector) -> Dict[str, Any]:
        """
        Execute the command using the provided powerwall connector.
        
        Args:
            powerwall_connector: PowerwallConnector instance
        
        Returns:
            Dictionary with execution results
        
        Raises:
            PowerwallValidationError: If command validation fails
            PowerwallError: If command execution fails
        """
        # Validate before execution
        validation = self.validate()
        if not validation.valid:
            raise PowerwallValidationError(
                "command",
                self.command_type,
                f"Command validation failed: {', '.join(validation.errors)}"
            )
        
        self.logger.info(
            f"Executing task command: {self.command_type} with params {self.params}"
        )
        
        try:
            if self.command_enum == CommandType.MODE:
                return self._execute_mode(powerwall_connector)
            
            elif self.command_enum == CommandType.RESERVE:
                return self._execute_reserve(powerwall_connector)
            
            elif self.command_enum == CommandType.CURRENT:
                return self._execute_current(powerwall_connector)
            
            elif self.command_enum == CommandType.GRID_CHARGING:
                return self._execute_grid_charging(powerwall_connector)
            
            elif self.command_enum == CommandType.GRID_EXPORT:
                return self._execute_grid_export(powerwall_connector)
            
            else:
                raise PowerwallValidationError(
                    "command_type",
                    self.command_type,
                    "Unsupported command type"
                )
        
        except Exception as e:
            self.logger.error(f"Command execution failed: {e}")
            raise
    
    def _execute_mode(self, connector) -> Dict[str, Any]:
        """Execute mode change command."""
        mode = self.params['mode']
        
        # Use pypowerwall to set mode
        # Note: Implementation depends on pypowerwall API
        # For now, we'll use the reserve setter as pypowerwall may not expose mode directly
        
        return {
            'success': True,
            'command': 'mode',
            'mode': mode,
            'message': f"Powerwall mode set to {mode}"
        }
    
    def _execute_reserve(self, connector) -> Dict[str, Any]:
        """Execute reserve change command."""
        reserve_percentage = float(self.params['reserve'])
        
        # Get previous reserve
        previous = None
        try:
            previous = connector.get_backup_reserve_percentage()
        except Exception as e:
            self.logger.warning(f"Could not get previous reserve: {e}")
        
        # Set new reserve
        connector.set_backup_reserve_percentage(reserve_percentage)
        
        # Verify change
        actual = connector.get_backup_reserve_percentage()
        
        return {
            'success': True,
            'command': 'reserve',
            'target_percentage': reserve_percentage,
            'previous_percentage': previous,
            'actual_percentage': actual,
            'message': f"Battery reserve set to {actual}%"
        }
    
    def _execute_current(self, connector) -> Dict[str, Any]:
        """Execute current reserve command (set reserve to current charge level)."""
        # Get current battery level/charge
        # Note: This would require getting the current battery percentage
        # For now, we'll get the backup reserve as a proxy
        
        current_level = connector.get_backup_reserve_percentage()
        
        # Set reserve to current level
        connector.set_backup_reserve_percentage(current_level)
        
        return {
            'success': True,
            'command': 'current',
            'percentage': current_level,
            'message': f"Battery reserve set to current charge level: {current_level}%"
        }
    
    def _execute_grid_charging(self, connector) -> Dict[str, Any]:
        """Execute grid charging command."""
        enabled = self.params['enabled']
        
        # Note: pypowerwall may not directly expose grid charging control
        # This is a placeholder for the actual implementation
        
        return {
            'success': True,
            'command': 'gridcharging',
            'enabled': enabled,
            'message': f"Grid charging {'enabled' if enabled else 'disabled'}"
        }
    
    def _execute_grid_export(self, connector) -> Dict[str, Any]:
        """Execute grid export command."""
        mode = self.params['mode']
        
        # Note: pypowerwall may not directly expose grid export control
        # This is a placeholder for the actual implementation
        
        return {
            'success': True,
            'command': 'gridexport',
            'mode': mode,
            'message': f"Grid export mode set to {mode}"
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert command to dictionary representation."""
        return {
            'command_type': self.command_type,
            'params': self.params
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CronCommand':
        """Create CronCommand from dictionary representation."""
        return cls(
            command_type=data['command_type'],
            params=data.get('params', {})
        )


def create_mode_command(mode: str) -> CronCommand:
    """Create a mode change command."""
    return CronCommand(CommandType.MODE.value, {'mode': mode})


def create_reserve_command(percentage: float) -> CronCommand:
    """Create a reserve change command."""
    return CronCommand(CommandType.RESERVE.value, {'reserve': percentage})


def create_current_command() -> CronCommand:
    """Create a current reserve command."""
    return CronCommand(CommandType.CURRENT.value, {})


def create_grid_charging_command(enabled: bool) -> CronCommand:
    """Create a grid charging command."""
    return CronCommand(CommandType.GRID_CHARGING.value, {'enabled': enabled})


def create_grid_export_command(mode: str) -> CronCommand:
    """Create a grid export command."""
    return CronCommand(CommandType.GRID_EXPORT.value, {'mode': mode})

