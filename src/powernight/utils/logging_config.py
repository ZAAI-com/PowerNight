"""
PowerNight Logging Configuration

Environment-specific logging configuration and setup utilities.
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional

from .logging import LogLevel, OperationType, PowerNightLogger, setup_logging


class LoggingConfig:
    """Configuration for PowerNight logging system."""

    def __init__(self):
        """Initialize logging configuration from environment variables."""
        self.log_level = self._get_log_level()
        self.log_dir = self._get_log_dir()
        self.enable_console = self._get_bool_env('LOG_ENABLE_CONSOLE', True)
        self.enable_file = self._get_bool_env('LOG_ENABLE_FILE', True)
        self.enable_json = self._get_bool_env('LOG_ENABLE_JSON', True)
        self.max_log_size = self._get_int_env('LOG_MAX_SIZE_MB', 50) * 1024 * 1024
        self.backup_count = self._get_int_env('LOG_BACKUP_COUNT', 10)
        self.console_level = self._get_log_level('LOG_CONSOLE_LEVEL', LogLevel.INFO)
        self.file_level = self._get_log_level('LOG_FILE_LEVEL', LogLevel.DEBUG)

    def _get_log_level(self, env_var: str = 'LOG_LEVEL', default: LogLevel = LogLevel.INFO) -> LogLevel:
        """Get log level from environment variable."""
        level_str = os.getenv(env_var, default.value).upper()
        try:
            return LogLevel(level_str)
        except ValueError:
            return default

    def _get_log_dir(self) -> Path:
        """Get log directory from environment or use default."""
        # Check for explicit log directory configuration
        log_dir_str = os.getenv('LOG_DIR') or os.getenv('POWERNIGHT_LOGS_PATH')
        if log_dir_str:
            return Path(log_dir_str)

        # Default paths based on environment
        if os.path.exists('/app'):
            # Docker environment
            return Path('/data/logs')
        elif os.getenv('POWERNIGHT_ENV') == 'development':
            # Development environment
            return Path('./logs')
        else:
            # Production environment
            return Path('/var/log/powernight')

    def _get_bool_env(self, env_var: str, default: bool) -> bool:
        """Get boolean value from environment variable."""
        value = os.getenv(env_var, str(default)).lower()
        return value in ('true', '1', 'yes', 'on', 'enabled')

    def _get_int_env(self, env_var: str, default: int) -> int:
        """Get integer value from environment variable."""
        try:
            return int(os.getenv(env_var, str(default)))
        except ValueError:
            return default

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'log_level': self.log_level.value,
            'log_dir': str(self.log_dir),
            'enable_console': self.enable_console,
            'enable_file': self.enable_file,
            'enable_json': self.enable_json,
            'max_log_size': self.max_log_size,
            'backup_count': self.backup_count,
            'console_level': self.console_level.value,
            'file_level': self.file_level.value
        }

    def setup_logger(self) -> PowerNightLogger:
        """Setup PowerNight logger with this configuration."""
        return setup_logging(
            log_dir=self.log_dir,
            log_level=self.log_level,
            enable_console=self.enable_console,
            enable_file=self.enable_file,
            enable_json=self.enable_json,
            max_log_size=self.max_log_size,
            backup_count=self.backup_count,
            console_level=self.console_level,
            file_level=self.file_level
        )


def configure_logging() -> PowerNightLogger:
    """Configure logging based on environment variables."""
    config = LoggingConfig()
    logger = config.setup_logger()

    # Log configuration details
    logger.log_system_event(
        operation=logger.OperationType.STARTUP,
        message="Logging configuration loaded",
        metadata=config.to_dict()
    )

    return logger


def get_docker_logging_config() -> Dict[str, Any]:
    """Get logging configuration optimized for Docker containers."""
    return {
        'log_dir': Path('/data/logs'),
        'log_level': LogLevel.INFO,
        'enable_console': True,
        'enable_file': True,
        'enable_json': True,
        'max_log_size': 50 * 1024 * 1024,  # 50MB
        'backup_count': 5,  # Less backups in container
        'console_level': LogLevel.INFO,
        'file_level': LogLevel.DEBUG
    }


def get_development_logging_config() -> Dict[str, Any]:
    """Get logging configuration optimized for development."""
    return {
        'log_dir': Path('./logs'),
        'log_level': LogLevel.DEBUG,
        'enable_console': True,
        'enable_file': True,
        'enable_json': True,
        'max_log_size': 10 * 1024 * 1024,  # 10MB
        'backup_count': 3,
        'console_level': LogLevel.DEBUG,
        'file_level': LogLevel.DEBUG
    }


def get_production_logging_config() -> Dict[str, Any]:
    """Get logging configuration optimized for production."""
    return {
        'log_dir': Path('/var/log/powernight'),
        'log_level': LogLevel.INFO,
        'enable_console': False,  # Minimize console output in production
        'enable_file': True,
        'enable_json': True,
        'max_log_size': 100 * 1024 * 1024,  # 100MB
        'backup_count': 20,
        'console_level': LogLevel.WARNING,
        'file_level': LogLevel.INFO
    }


# Environment detection and auto-configuration
def auto_configure_logging() -> PowerNightLogger:
    """Automatically configure logging based on detected environment."""
    env = os.getenv('POWERNIGHT_ENV', 'production').lower()

    if env == 'development':
        config = get_development_logging_config()
    elif os.path.exists('/app'):  # Docker environment
        config = get_docker_logging_config()
    else:
        config = get_production_logging_config()

    logger = setup_logging(**config)

    logger.log_system_event(
        operation=OperationType.STARTUP,
        message=f"Auto-configured logging for {env} environment",
        metadata={'environment': env, 'config': config}
    )

    return logger