"""
PowerNight API Schemas

JSON schema definitions for API request/response validation using enterprise standards.
"""

from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
import jsonschema
from jsonschema import validate, ValidationError as JsonSchemaValidationError


# JSON Schema definitions for enterprise-grade validation

BACKUP_RESERVE_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["percentage"],
    "additionalProperties": False,
    "properties": {
        "percentage": {
            "type": "number",
            "minimum": 0,
            "maximum": 100,
            "multipleOf": 0.1,
            "description": "Backup reserve percentage (0-100)"
        },
        "reason": {
            "type": "string",
            "maxLength": 255,
            "pattern": r"^[a-zA-Z0-9\s\-_.,!?()]+$",
            "description": "Optional reason for the change"
        },
        "force": {
            "type": "boolean",
            "default": False,
            "description": "Force change even if Powerwall is unreachable"
        }
    }
}


@dataclass
class ValidationResult:
    """Result of validation operation."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    sanitized_data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            'is_valid': self.is_valid,
            'errors': self.errors,
            'warnings': self.warnings,
            'error_count': len(self.errors),
            'warning_count': len(self.warnings)
        }


@dataclass
class ConfigurationChangeRequest:
    """Represents a configuration change request with metadata."""
    user_id: str
    client_ip: str
    user_agent: str
    timestamp: datetime
    changes: Dict[str, Any]
    validation_result: ValidationResult
    change_id: str = field(default_factory=lambda: f"cfg_{int(datetime.now().timestamp())}")

    def to_audit_log(self) -> Dict[str, Any]:
        """Convert to audit log entry."""
        return {
            'change_id': self.change_id,
            'timestamp': self.timestamp.isoformat(),
            'user_id': self.user_id,
            'client_ip': self.client_ip,
            'user_agent': self.user_agent,
            'changes': self.changes,
            'validation_result': self.validation_result.to_dict(),
            'change_count': len(self._flatten_changes(self.changes))
        }

    def _flatten_changes(self, data: Dict[str, Any], prefix: str = '') -> List[str]:
        """Flatten nested changes for audit logging."""
        changes = []
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                changes.extend(self._flatten_changes(value, full_key))
            else:
                changes.append(full_key)
        return changes


class SchemaValidator:
    """Enterprise-grade JSON schema validator with security features."""

    def __init__(self):
        """Initialize validator with schema registry."""
        self.schemas = {
            'backup_reserve': BACKUP_RESERVE_SCHEMA
        }

        # Create validator instances for each schema
        self.validators = {
            name: jsonschema.Draft7Validator(schema)
            for name, schema in self.schemas.items()
        }


    def validate_backup_reserve(self, data: Dict[str, Any]) -> ValidationResult:
        """
        Validate backup reserve data.

        Args:
            data: Backup reserve data to validate

        Returns:
            ValidationResult with detailed feedback
        """
        result = ValidationResult(is_valid=True)

        try:
            # JSON Schema validation
            validator = self.validators['backup_reserve']
            errors = list(validator.iter_errors(data))

            if errors:
                result.is_valid = False
                for error in errors:
                    path = '.'.join(str(p) for p in error.absolute_path) if error.absolute_path else 'root'
                    result.errors.append(f"{path}: {error.message}")
            else:
                result.sanitized_data = self._sanitize_backup_reserve_data(data)

        except Exception as e:
            result.is_valid = False
            result.errors.append(f"Validation error: {str(e)}")

        return result

    def _validate_business_rules(self, data: Dict[str, Any]) -> List[str]:
        """Validate business logic rules."""
        errors = []

        # Check for duplicate schedule times
        if 'automation' in data and 'schedule' in data['automation']:
            schedule = data['automation']['schedule']
            if isinstance(schedule, list):
                enabled_times = [
                    entry.get('time') for entry in schedule
                    if isinstance(entry, dict) and entry.get('enabled', True) and 'time' in entry
                ]

                if len(enabled_times) != len(set(enabled_times)):
                    errors.append("automation.schedule: Duplicate schedule times found for enabled entries")

        # Validate authentication configuration consistency
        if 'web_interface' in data:
            web_config = data['web_interface']
            if isinstance(web_config, dict):
                auth_enabled = web_config.get('auth_enabled', False)
                username = web_config.get('username')
                password = web_config.get('password')
                api_key = web_config.get('api_key')

                if auth_enabled and not (username and password) and not api_key:
                    errors.append("web_interface: Authentication enabled but no credentials provided")

        return errors

    def _validate_security_rules(self, data: Dict[str, Any]) -> List[str]:
        """Validate security-related rules and generate warnings."""
        warnings = []

        # Check for insecure configurations
        if 'web_interface' in data:
            web_config = data['web_interface']
            if isinstance(web_config, dict):
                # Warn about debug mode in production
                if web_config.get('debug', False):
                    warnings.append("web_interface.debug: Debug mode enabled - not recommended for production")

                # Warn about disabled SSL verification
                if 'verify_ssl' in data.get('powerwall', {}) and not data['powerwall']['verify_ssl']:
                    warnings.append("powerwall.verify_ssl: SSL verification disabled - security risk")

                # Warn about weak CORS settings
                cors_origins = web_config.get('cors_origins', [])
                if '*' in cors_origins and len(cors_origins) == 1:
                    warnings.append("web_interface.cors_origins: Wildcard CORS origin (*) - potential security risk")

        return warnings

    def _sanitize_config_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize and normalize configuration data."""
        sanitized = {}

        for section_name, section_data in data.items():
            if not isinstance(section_data, dict):
                continue

            sanitized[section_name] = {}

            for key, value in section_data.items():
                # Sanitize string values
                if isinstance(value, str):
                    # Trim whitespace
                    value = value.strip()

                    # Normalize email addresses
                    if key == 'email':
                        value = value.lower()

                    # Normalize IP addresses
                    elif key in ['tesla_email', 'powerwall_id']:
                        if value == 'localhost':
                            value = '127.0.0.1'

                # Sanitize schedule array
                elif key == 'schedule' and isinstance(value, list):
                    sanitized_schedule = []
                    for entry in value:
                        if isinstance(entry, dict):
                            sanitized_entry = {}
                            for entry_key, entry_value in entry.items():
                                if entry_key == 'time' and isinstance(entry_value, str):
                                    # Normalize time format
                                    time_parts = entry_value.split(':')
                                    if len(time_parts) == 2:
                                        hour = int(time_parts[0])
                                        minute = int(time_parts[1])
                                        sanitized_entry[entry_key] = f"{hour:02d}:{minute:02d}"
                                else:
                                    sanitized_entry[entry_key] = entry_value
                            sanitized_schedule.append(sanitized_entry)
                    value = sanitized_schedule

                sanitized[section_name][key] = value

        return sanitized

    def _sanitize_backup_reserve_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize backup reserve data."""
        sanitized = {}

        for key, value in data.items():
            if key == 'percentage':
                # Round to 1 decimal place
                sanitized[key] = round(float(value), 1)
            elif key == 'reason' and isinstance(value, str):
                # Sanitize reason text
                sanitized[key] = value.strip()[:255]
            else:
                sanitized[key] = value

        return sanitized


# Global validator instance
_validator = SchemaValidator()


def get_schema_validator() -> SchemaValidator:
    """Get the global schema validator instance."""
    return _validator