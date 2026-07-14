"""
PowerNight Configuration Schema

Defines the configuration structure and validation rules for PowerNight.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import time, datetime

from .validators import (
    validate_percentage,
    validate_time_format,
    validate_timezone,
    validate_port_number,
    validate_positive_number,
    validate_non_negative_number,
    validate_log_level,
    validate_email_format,
    ValidationError,
    PercentageValidationError,
    TimeFormatValidationError
)


@dataclass
class PowerwallSettings:
    """Powerwall connection settings for cloud mode."""
    tesla_email: str
    powerwall_id: Optional[str] = None
    timeout: float = 30.0
    retry_attempts: int = 3
    verify_ssl: bool = True

    def validate(self) -> List[str]:
        """Validate powerwall settings."""
        errors = []

        # Validate Tesla email (required for cloud mode)
        try:
            validate_email_format(self.tesla_email)
        except ValidationError as e:
            errors.append(f"Tesla email: {e}")

        # Validate timeout
        try:
            validate_positive_number(self.timeout, "timeout")
        except ValidationError as e:
            errors.append(str(e))

        # Validate retry attempts
        try:
            validate_non_negative_number(self.retry_attempts, "retry_attempts")
        except ValidationError as e:
            errors.append(str(e))

        return errors


@dataclass
class ScheduleEntry:
    """Single schedule entry for backup reserve changes."""
    time: str  # Format: "HH:MM" (24-hour)
    percentage: float
    enabled: bool = True
    description: Optional[str] = None

    def validate(self) -> List[str]:
        """Validate schedule entry."""
        errors = []

        # Validate time format
        try:
            validate_time_format(self.time)
        except TimeFormatValidationError as e:
            errors.append(str(e))

        # Validate percentage
        try:
            validate_percentage(self.percentage)
        except PercentageValidationError as e:
            errors.append(str(e))

        return errors

    def get_time_object(self) -> time:
        """Get time as datetime.time object."""
        return datetime.strptime(self.time, "%H:%M").time()


@dataclass
class AutomationSettings:
    """Automation engine settings."""
    enabled: bool = True
    schedule: List[ScheduleEntry] = field(default_factory=list)
    timezone: str = "Europe/Berlin"  # Default timezone for scheduling
    check_interval: float = 60.0  # seconds

    def validate(self) -> List[str]:
        """Validate automation settings."""
        errors = []

        # Validate check interval
        try:
            validate_positive_number(self.check_interval, "check_interval")
        except ValidationError as e:
            errors.append(str(e))

        # Validate timezone
        try:
            validate_timezone(self.timezone)
        except ValidationError as e:
            errors.append(f"Timezone: {e}")

        # Validate schedule entries
        for i, entry in enumerate(self.schedule):
            entry_errors = entry.validate()
            for error in entry_errors:
                errors.append(f"Schedule entry {i}: {error}")

        # Check for duplicate times in enabled entries
        enabled_times = [entry.time for entry in self.schedule if entry.enabled]
        if len(enabled_times) != len(set(enabled_times)):
            errors.append("Duplicate schedule times found")

        return errors


@dataclass
class WebInterfaceSettings:
    """Web interface settings."""
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8020
    debug: bool = False
    auth_enabled: bool = True  # Secure by default: API requires a key/password
    auth_required: bool = False  # Keep for backward compatibility
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None
    cors_origins: List[str] = field(default_factory=lambda: ["*"])

    def __post_init__(self):
        """Post-initialization processing."""
        # Map auth_required to auth_enabled for backward compatibility
        if self.auth_required and not self.auth_enabled:
            self.auth_enabled = self.auth_required

    def validate(self) -> List[str]:
        """Validate web interface settings."""
        errors = []

        # Validate port number
        try:
            validate_port_number(self.port)
        except ValidationError as e:
            errors.append(str(e))

        # Validate authentication settings
        if self.auth_required:
            if not self.username:
                errors.append("Username required when auth is enabled")
            if not self.password:
                errors.append("Password required when auth is enabled")

        return errors


@dataclass
class LoggingSettings:
    """Logging configuration."""
    level: str = "INFO"
    file_path: Optional[str] = None
    file_enabled: bool = True
    max_file_size: str = "10MB"
    backup_count: int = 5
    console_output: bool = True
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    def validate(self) -> List[str]:
        """Validate logging settings."""
        errors = []

        # Validate log level
        try:
            validate_log_level(self.level)
        except ValidationError as e:
            errors.append(str(e))

        # Validate backup count
        try:
            validate_non_negative_number(self.backup_count, "backup_count")
        except ValidationError as e:
            errors.append(str(e))

        return errors


@dataclass
class MonitoringSettings:
    """Monitoring and health check settings."""
    enabled: bool = True
    health_check_interval: float = 300.0  # 5 minutes
    circuit_breaker_enabled: bool = True
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: float = 60.0
    data_cache_ttl: float = 30.0

    def validate(self) -> List[str]:
        """Validate monitoring settings."""
        errors = []

        # Validate health check interval
        try:
            validate_positive_number(self.health_check_interval, "health_check_interval")
        except ValidationError as e:
            errors.append(str(e))

        # Validate circuit breaker failure threshold
        try:
            validate_positive_number(self.circuit_breaker_failure_threshold, "circuit_breaker_failure_threshold")
        except ValidationError as e:
            errors.append(str(e))

        # Validate circuit breaker recovery timeout
        try:
            validate_positive_number(self.circuit_breaker_recovery_timeout, "circuit_breaker_recovery_timeout")
        except ValidationError as e:
            errors.append(str(e))

        # Validate data cache TTL
        try:
            validate_positive_number(self.data_cache_ttl, "data_cache_ttl")
        except ValidationError as e:
            errors.append(str(e))

        return errors


@dataclass
class PowerNightConfig:
    """Complete PowerNight configuration."""
    powerwall: PowerwallSettings
    automation: AutomationSettings = field(default_factory=AutomationSettings)
    web_interface: WebInterfaceSettings = field(default_factory=WebInterfaceSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    monitoring: MonitoringSettings = field(default_factory=MonitoringSettings)

    def validate(self) -> List[str]:
        """Validate entire configuration."""
        errors = []

        errors.extend(self.powerwall.validate())
        errors.extend(self.automation.validate())
        errors.extend(self.web_interface.validate())
        errors.extend(self.logging.validate())
        errors.extend(self.monitoring.validate())

        return errors

    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        return len(self.validate()) == 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'powerwall': {
                'tesla_email': self.powerwall.tesla_email,
                'powerwall_id': self.powerwall.powerwall_id,
                'timeout': self.powerwall.timeout,
                'retry_attempts': self.powerwall.retry_attempts,
                'verify_ssl': self.powerwall.verify_ssl
            },
            'automation': {
                'enabled': self.automation.enabled,
                'schedule': [
                    {
                        'time': entry.time,
                        'percentage': entry.percentage,
                        'enabled': entry.enabled,
                        'description': entry.description
                    }
                    for entry in self.automation.schedule
                ],
                'timezone': self.automation.timezone,
                'check_interval': self.automation.check_interval
            },
            'web_interface': {
                'enabled': self.web_interface.enabled,
                'host': self.web_interface.host,
                'port': self.web_interface.port,
                'debug': self.web_interface.debug,
                'auth_enabled': self.web_interface.auth_enabled,
                'auth_required': self.web_interface.auth_required,
                'username': self.web_interface.username,
                'password': self.web_interface.password,
                'api_key': self.web_interface.api_key,
                'cors_origins': self.web_interface.cors_origins
            },
            'logging': {
                'level': self.logging.level,
                'file_path': self.logging.file_path,
                'file_enabled': self.logging.file_enabled,
                'max_file_size': self.logging.max_file_size,
                'backup_count': self.logging.backup_count,
                'console_output': self.logging.console_output,
                'format': self.logging.format
            },
            'monitoring': {
                'enabled': self.monitoring.enabled,
                'health_check_interval': self.monitoring.health_check_interval,
                'circuit_breaker_enabled': self.monitoring.circuit_breaker_enabled,
                'circuit_breaker_failure_threshold': self.monitoring.circuit_breaker_failure_threshold,
                'circuit_breaker_recovery_timeout': self.monitoring.circuit_breaker_recovery_timeout,
                'data_cache_ttl': self.monitoring.data_cache_ttl
            }
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PowerNightConfig':
        """Create configuration from dictionary."""
        powerwall_data = data.get('powerwall', {})
        powerwall = PowerwallSettings(
            tesla_email=powerwall_data.get('tesla_email', 'user@example.com'),
            powerwall_id=powerwall_data.get('powerwall_id'),
            timeout=powerwall_data.get('timeout', 30.0),
            retry_attempts=powerwall_data.get('retry_attempts', 3),
            verify_ssl=powerwall_data.get('verify_ssl', True)
        )

        automation_data = data.get('automation', {})
        schedule_entries = []
        for i, entry_data in enumerate(automation_data.get('schedule', [])):
            missing = [key for key in ('time', 'percentage') if key not in entry_data]
            if missing:
                raise ValueError(
                    f"Schedule entry {i} is missing required key(s): {', '.join(missing)}. "
                    f"Each entry needs 'time' (HH:MM) and 'percentage' (0-100)."
                )
            schedule_entries.append(ScheduleEntry(
                time=entry_data['time'],
                percentage=entry_data['percentage'],
                enabled=entry_data.get('enabled', True),
                description=entry_data.get('description')
            ))

        automation = AutomationSettings(
            enabled=automation_data.get('enabled', True),
            schedule=schedule_entries,
            timezone=automation_data.get('timezone', 'UTC'),
            check_interval=automation_data.get('check_interval', 60.0)
        )

        web_data = data.get('web_interface', {})
        web_interface = WebInterfaceSettings(
            enabled=web_data.get('enabled', True),
            host=web_data.get('host', '0.0.0.0'),
            port=web_data.get('port', 8020),
            debug=web_data.get('debug', False),
            auth_enabled=web_data.get('auth_enabled', True),
            auth_required=web_data.get('auth_required', False),
            username=web_data.get('username'),
            password=web_data.get('password'),
            api_key=web_data.get('api_key'),
            cors_origins=web_data.get('cors_origins', ["*"])
        )

        logging_data = data.get('logging', {})
        logging_settings = LoggingSettings(
            level=logging_data.get('level', 'INFO'),
            file_path=logging_data.get('file_path', 'logs/powernight.log'),
            file_enabled=logging_data.get('file_enabled', True),
            max_file_size=logging_data.get('max_file_size', '10MB'),
            backup_count=logging_data.get('backup_count', 5),
            console_output=logging_data.get('console_output', True),
            format=logging_data.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )

        monitoring_data = data.get('monitoring', {})
        monitoring = MonitoringSettings(
            enabled=monitoring_data.get('enabled', True),
            health_check_interval=monitoring_data.get('health_check_interval', 300.0),
            circuit_breaker_enabled=monitoring_data.get('circuit_breaker_enabled', True),
            circuit_breaker_failure_threshold=monitoring_data.get('circuit_breaker_failure_threshold', 5),
            circuit_breaker_recovery_timeout=monitoring_data.get('circuit_breaker_recovery_timeout', 60.0),
            data_cache_ttl=monitoring_data.get('data_cache_ttl', 30.0)
        )

        return cls(
            powerwall=powerwall,
            automation=automation,
            web_interface=web_interface,
            logging=logging_settings,
            monitoring=monitoring
        )


def create_default_config() -> PowerNightConfig:
    """Create a default configuration with example values.

    Automation ships disabled: a generated example config must never be able
    to command a real Powerwall until the user reviews and enables it.
    """
    default_schedule = [
        ScheduleEntry(
            time="00:01",
            percentage=40.0,
            enabled=False,
            description="Example: set reserve to 40% at start of night"
        ),
        ScheduleEntry(
            time="04:58",
            percentage=0.0,
            enabled=False,
            description="Example: set reserve to 0% before sunrise"
        )
    ]

    return PowerNightConfig(
        powerwall=PowerwallSettings(
            tesla_email="user@example.com",
            timeout=30.0,
            retry_attempts=3,
            verify_ssl=True
        ),
        automation=AutomationSettings(
            enabled=False,
            schedule=default_schedule,
            timezone="Europe/Berlin",
            check_interval=60.0
        ),
        web_interface=WebInterfaceSettings(
            enabled=True,
            host="0.0.0.0",
            port=8020,
            debug=False,
            auth_required=False
        ),
        logging=LoggingSettings(
            level="INFO",
            file_path="logs/powernight.log",
            console_output=True
        ),
        monitoring=MonitoringSettings(
            enabled=True,
            health_check_interval=300.0,
            circuit_breaker_enabled=True,
            circuit_breaker_failure_threshold=5,
            circuit_breaker_recovery_timeout=60.0,
            data_cache_ttl=30.0
        )
    )
