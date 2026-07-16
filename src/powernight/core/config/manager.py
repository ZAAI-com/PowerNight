"""
PowerNight Configuration Manager

Handles loading, validation, and management of configuration files.
"""

import os
import json
import yaml
import logging
import threading
from typing import Optional, Dict, Any, List, Union
from pathlib import Path

from .schema import PowerNightConfig, create_default_config
from .exceptions import ConfigurationError


class ConfigManager:
    """
    Singleton configuration manager for PowerNight.

    Handles loading configuration from files, environment variable overrides,
    validation, and provides thread-safe access to configuration data.
    """

    _instance: Optional['ConfigManager'] = None
    _lock = threading.Lock()

    def __new__(cls) -> 'ConfigManager':
        """Singleton pattern implementation."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize configuration manager."""
        if hasattr(self, '_initialized'):
            return

        self.logger = logging.getLogger(__name__)
        self._config: Optional[PowerNightConfig] = None
        self._config_path: Optional[Path] = None
        self._file_lock = threading.RLock()
        self._backup_manager = None
        self._recovery_manager = None
        self._auto_backup = True
        self._auto_recovery = True
        self._initialized = True

    def _get_backup_manager(self):
        """Lazy initialization of backup manager to avoid circular imports."""
        if self._backup_manager is None:
            from .backup import ConfigBackupManager
            self._backup_manager = ConfigBackupManager()
        return self._backup_manager

    def _get_recovery_manager(self):
        """Lazy initialization of recovery manager to avoid circular imports."""
        if self._recovery_manager is None:
            from .backup import ConfigRecoveryManager
            self._recovery_manager = ConfigRecoveryManager()
        return self._recovery_manager

    def load_config(self, config_path: Optional[Union[str, Path]] = None) -> PowerNightConfig:
        """
        Load configuration from file with environment variable overrides.

        Args:
            config_path: Optional path to configuration file. If None, searches default locations.

        Returns:
            Validated PowerNightConfig object

        Raises:
            ConfigurationError: If configuration cannot be loaded or is invalid
        """
        with self._file_lock:
            if config_path is None:
                config_path = self._find_config_file()
            else:
                config_path = Path(config_path)

            self.logger.info(f"Loading configuration from {config_path}")

            try:
                # Load configuration from file
                config_data = self._load_config_file(config_path)

                # Apply environment variable overrides
                config_data = self._apply_env_overrides(config_data)

                # Validate and create configuration object
                config = PowerNightConfig.from_dict(config_data)
                validation_errors = config.validate()

                if validation_errors:
                    error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {error}" for error in validation_errors)
                    raise ConfigurationError(error_msg)

                self._config = config
                self._config_path = config_path
                self.logger.info("Configuration loaded and validated successfully")

                return config

            except Exception as e:
                self.logger.error(f"Failed to load configuration from {config_path}: {e}")

                # Attempt automatic recovery if enabled
                if self._auto_recovery:
                    self.logger.info("Attempting automatic configuration recovery")

                    recovered_path = self._get_recovery_manager().attempt_recovery(config_path, e)
                    if recovered_path:
                        self.logger.info("Configuration recovery successful, retrying load")
                        try:
                            # Recursively try to load the recovered configuration
                            return self.load_config(recovered_path)
                        except Exception as recovery_error:
                            self.logger.error(f"Failed to load recovered configuration: {recovery_error}")

                # If recovery failed or is disabled, raise the original error
                if isinstance(e, ConfigurationError):
                    raise
                raise ConfigurationError(f"Failed to load configuration: {e}")

    def save_config(self, config: Optional[PowerNightConfig] = None,
                   config_path: Optional[Union[str, Path]] = None) -> None:
        """
        Save configuration to file.

        Args:
            config: Configuration to save. If None, uses current configuration.
            config_path: Path to save configuration. If None, uses current path.

        Raises:
            ConfigurationError: If configuration cannot be saved
        """
        with self._file_lock:
            if config is None:
                config = self._config
            if config is None:
                raise ConfigurationError("No configuration to save")

            if config_path is None:
                config_path = self._config_path
            if config_path is None:
                raise ConfigurationError("No configuration path specified")

            config_path = Path(config_path)

            try:
                # Validate configuration before saving
                validation_errors = config.validate()
                if validation_errors:
                    error_msg = "Cannot save invalid configuration:\n" + "\n".join(f"  - {error}" for error in validation_errors)
                    raise ConfigurationError(error_msg)

                # Create backup before overwriting existing file
                if self._auto_backup and config_path.exists():
                    backup_path = self._get_backup_manager().create_backup(config_path)
                    if backup_path:
                        self.logger.debug(f"Created backup before saving: {backup_path}")

                # Create directory if it doesn't exist
                config_path.parent.mkdir(parents=True, exist_ok=True)

                # Save based on file extension
                config_dict = config.to_dict()

                if config_path.suffix.lower() == '.yaml' or config_path.suffix.lower() == '.yml':
                    with open(config_path, 'w') as f:
                        yaml.dump(config_dict, f, default_flow_style=False, indent=2)
                else:
                    with open(config_path, 'w') as f:
                        json.dump(config_dict, f, indent=2)

                # Keep the in-memory singleton in sync: everything that calls
                # get_config() (auth checks, scheduler, API reads) must see
                # the saved settings without a restart
                self._config = config
                self._config_path = config_path

                self.logger.info(f"Configuration saved to {config_path}")

            except Exception as e:
                if isinstance(e, ConfigurationError):
                    raise
                raise ConfigurationError(f"Failed to save configuration: {e}")

    def get_config(self) -> PowerNightConfig:
        """
        Get the current configuration.

        Returns:
            Current PowerNightConfig object

        Raises:
            ConfigurationError: If no configuration is loaded
        """
        if self._config is None:
            raise ConfigurationError("No configuration loaded. Call load_config() first.")
        return self._config

    def reload_config(self) -> PowerNightConfig:
        """
        Reload configuration from the current file path.

        Returns:
            Reloaded PowerNightConfig object

        Raises:
            ConfigurationError: If no previous configuration path or reload fails
        """
        if self._config_path is None:
            raise ConfigurationError("No configuration path available for reload")
        return self.load_config(self._config_path)

    def create_default_config_file(self, config_path: Union[str, Path]) -> None:
        """
        Create a default configuration file.

        Args:
            config_path: Path where to create the default configuration

        Raises:
            ConfigurationError: If file cannot be created
        """
        try:
            config_path = Path(config_path)
            default_config = create_default_config()

            # Temporarily set the config for saving
            old_config = self._config
            old_path = self._config_path

            self._config = default_config
            self._config_path = config_path

            try:
                self.save_config()
                self.logger.info(f"Default configuration created at {config_path}")
            finally:
                # Restore previous state
                self._config = old_config
                self._config_path = old_path

        except Exception as e:
            raise ConfigurationError(f"Failed to create default configuration: {e}")

    def validate_config_file(self, config_path: Union[str, Path]) -> List[str]:
        """
        Validate a configuration file without loading it as current config.

        Args:
            config_path: Path to configuration file to validate

        Returns:
            List of validation errors (empty if valid)
        """
        try:
            config_path = Path(config_path)
            config_data = self._load_config_file(config_path)
            config_data = self._apply_env_overrides(config_data)
            config = PowerNightConfig.from_dict(config_data)
            return config.validate()
        except Exception as e:
            return [f"Failed to load/parse configuration: {e}"]

    def _find_config_file(self) -> Path:
        """
        Find configuration file in default locations.

        Returns:
            Path to configuration file

        Raises:
            ConfigurationError: If no configuration file found
        """
        # Check environment variable first
        env_path = os.getenv('POWERNIGHT_CONFIG_PATH')
        if env_path:
            config_path = Path(env_path)
            if config_path.exists():
                return config_path
            else:
                self.logger.warning(f"Configuration path from environment variable does not exist: {env_path}")

        # Default search locations
        search_paths = [
            Path('./config.json'),
            Path('./config.yaml'),
            Path('./config/config.json'),
            Path('./config/config.yaml'),
            Path.home() / '.powernight' / 'config.json',
            Path.home() / '.powernight' / 'config.yaml'
        ]

        for path in search_paths:
            if path.exists():
                return path

        # No configuration file found, suggest creating one
        suggested_path = Path('./config.json')
        raise ConfigurationError(
            f"No configuration file found in default locations: {[str(p) for p in search_paths]}. "
            f"Create a configuration file or set POWERNIGHT_CONFIG_PATH environment variable. "
            f"You can create a default configuration with: powernight create-config {suggested_path}"
        )

    def _load_config_file(self, config_path: Path) -> Dict[str, Any]:
        """
        Load configuration data from file.

        Args:
            config_path: Path to configuration file

        Returns:
            Configuration dictionary

        Raises:
            ConfigurationError: If file cannot be loaded or parsed
        """
        if not config_path.exists():
            raise ConfigurationError(f"Configuration file not found: {config_path}")

        try:
            with open(config_path, 'r') as f:
                if config_path.suffix.lower() in ['.yaml', '.yml']:
                    return yaml.safe_load(f) or {}
                else:
                    return json.load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML in configuration file: {e}")
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON in configuration file: {e}")
        except Exception as e:
            raise ConfigurationError(f"Failed to read configuration file: {e}")

    def _apply_env_overrides(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply environment variable overrides to configuration.

        Args:
            config_data: Configuration dictionary

        Returns:
            Configuration dictionary with environment overrides applied
        """
        # Make a copy to avoid modifying the original
        config_data = config_data.copy()

        # Environment variable mappings
        env_mappings = {
            'POWERNIGHT_LOG_LEVEL': ('logging', 'level'),
            'POWERNIGHT_WEB_PORT': ('web_interface', 'port'),
            'POWERNIGHT_WEB_HOST': ('web_interface', 'host'),
            'POWERNIGHT_WEB_DEBUG': ('web_interface', 'debug'),
            'POWERNIGHT_AUTH_ENABLED': ('web_interface', 'auth_enabled'),
            'POWERNIGHT_API_KEY': ('web_interface', 'api_key'),
            'TESLA_EMAIL': ('powerwall', 'tesla_email'),
            'POWERNIGHT_POWERWALL_EMAIL': ('powerwall', 'tesla_email'),
            'POWERNIGHT_POWERWALL_TIMEOUT': ('powerwall', 'timeout'),
            'POWERNIGHT_AUTOMATION_ENABLED': ('automation', 'enabled'),
            'POWERNIGHT_AUTOMATION_INTERVAL': ('automation', 'check_interval'),
            'POWERNIGHT_MONITORING_ENABLED': ('monitoring', 'enabled'),
        }

        for env_var, (section, key) in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                # Ensure section exists
                if section not in config_data:
                    config_data[section] = {}

                # Convert value to appropriate type
                try:
                    # Try to convert to appropriate type based on key
                    if key in ['port', 'retry_attempts', 'backup_count', 'circuit_breaker_failure_threshold']:
                        config_data[section][key] = int(value)
                    elif key in ['timeout', 'check_interval', 'health_check_interval', 'circuit_breaker_recovery_timeout', 'data_cache_ttl']:
                        config_data[section][key] = float(value)
                    elif key in ['enabled', 'debug', 'verify_ssl', 'auth_enabled', 'auth_required', 'console_output', 'circuit_breaker_enabled']:
                        config_data[section][key] = value.lower() in ('true', '1', 'yes', 'on')
                    else:
                        config_data[section][key] = value

                    self.logger.debug(f"Applied environment override: {env_var} -> {section}.{key} = {config_data[section][key]}")
                except ValueError as e:
                    self.logger.warning(f"Invalid value for environment variable {env_var}: {value} ({e})")

        return config_data

    def set_auto_backup(self, enabled: bool) -> None:
        """Enable or disable automatic backup creation."""
        self._auto_backup = enabled
        self.logger.info(f"Automatic backup {'enabled' if enabled else 'disabled'}")

    def set_auto_recovery(self, enabled: bool) -> None:
        """Enable or disable automatic recovery from configuration errors."""
        self._auto_recovery = enabled
        self.logger.info(f"Automatic recovery {'enabled' if enabled else 'disabled'}")

    def create_backup(self, config_path: Optional[Union[str, Path]] = None) -> Optional[Path]:
        """
        Manually create a backup of the configuration file.

        Args:
            config_path: Path to configuration file. If None, uses current config path.

        Returns:
            Path to created backup file, or None if backup failed
        """
        if config_path is None:
            config_path = self._config_path
        if config_path is None:
            raise ConfigurationError("No configuration path available for backup")

        return self._get_backup_manager().create_backup(Path(config_path))

    def list_backups(self, config_path: Optional[Union[str, Path]] = None) -> List[Dict[str, Any]]:
        """
        List available backup files for the configuration.

        Args:
            config_path: Path to configuration file. If None, uses current config path.

        Returns:
            List of backup information dictionaries
        """
        if config_path is None:
            config_path = self._config_path
        if config_path is None:
            raise ConfigurationError("No configuration path available")

        return self._get_backup_manager().get_backup_info(Path(config_path))

    def restore_from_backup(self, backup_path: Optional[Union[str, Path]] = None,
                           config_path: Optional[Union[str, Path]] = None) -> bool:
        """
        Restore configuration from a backup file.

        Args:
            backup_path: Path to backup file. If None, uses most recent backup.
            config_path: Path where to restore the configuration. If None, uses current path.

        Returns:
            True if restore was successful, False otherwise
        """
        if config_path is None:
            config_path = self._config_path
        if config_path is None:
            raise ConfigurationError("No configuration path available for restore")

        backup_path = Path(backup_path) if backup_path else None
        success = self._get_backup_manager().restore_from_backup(Path(config_path), backup_path)

        if success:
            # Reload the restored configuration
            try:
                self.reload_config()
                self.logger.info("Configuration reloaded after restore")
            except Exception as e:
                self.logger.error(f"Failed to reload configuration after restore: {e}")

        return success

    def cleanup_old_backups(self, config_path: Optional[Union[str, Path]] = None,
                           max_age_days: Optional[int] = None) -> int:
        """
        Clean up old backup files.

        Args:
            config_path: Path to configuration file. If None, uses current config path.
            max_age_days: Maximum age in days for backups. If None, only keeps max_backups files.

        Returns:
            Number of backup files removed
        """
        if config_path is None:
            config_path = self._config_path
        if config_path is None:
            raise ConfigurationError("No configuration path available")

        return self._get_backup_manager().cleanup_old_backups(Path(config_path), max_age_days)

    def load_config_with_fallback(self, primary_path: Union[str, Path],
                                 fallback_paths: List[Union[str, Path]]) -> PowerNightConfig:
        """
        Load configuration with fallback paths.

        Tries to load configuration from primary path first, then fallback paths
        in order until one succeeds.

        Args:
            primary_path: Primary configuration file path
            fallback_paths: List of fallback configuration file paths

        Returns:
            Loaded PowerNightConfig object

        Raises:
            ConfigurationError: If no configuration could be loaded
        """
        all_paths = [Path(primary_path)] + [Path(p) for p in fallback_paths]
        errors = []

        for config_path in all_paths:
            try:
                self.logger.info(f"Attempting to load configuration from {config_path}")
                return self.load_config(config_path)
            except Exception as e:
                errors.append(f"{config_path}: {e}")
                self.logger.warning(f"Failed to load from {config_path}: {e}")

        # All paths failed
        error_msg = "Failed to load configuration from any path:\n" + "\n".join(f"  - {error}" for error in errors)
        raise ConfigurationError(error_msg)

    def get_config_status(self) -> Dict[str, Any]:
        """
        Get comprehensive status information about the configuration system.

        Returns:
            Dictionary with configuration status information
        """
        status = {
            'config_loaded': self._config is not None,
            'config_path': str(self._config_path) if self._config_path else None,
            'auto_backup_enabled': self._auto_backup,
            'auto_recovery_enabled': self._auto_recovery,
            'backup_count': 0,
            'last_backup': None,
            'validation_status': 'unknown'
        }

        # Get backup information
        if self._config_path:
            try:
                backup_info = self.list_backups()
                status['backup_count'] = len(backup_info)
                if backup_info:
                    status['last_backup'] = backup_info[0]['created'].isoformat()
            except Exception as e:
                self.logger.warning(f"Failed to get backup info: {e}")

        # Get validation status
        if self._config:
            try:
                validation_errors = self._config.validate()
                status['validation_status'] = 'valid' if not validation_errors else 'invalid'
                status['validation_errors'] = validation_errors
            except Exception as e:
                status['validation_status'] = 'error'
                status['validation_error'] = str(e)

        return status


# Global instance for easy access
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get the global configuration manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def get_config() -> PowerNightConfig:
    """Get the current configuration."""
    return get_config_manager().get_config()


def load_config(config_path: Optional[Union[str, Path]] = None) -> PowerNightConfig:
    """Load configuration from file."""
    return get_config_manager().load_config(config_path)


def save_config(config: Optional[PowerNightConfig] = None,
               config_path: Optional[Union[str, Path]] = None) -> None:
    """Save configuration to file."""
    get_config_manager().save_config(config, config_path)


def reload_config() -> PowerNightConfig:
    """Reload configuration from current file."""
    return get_config_manager().reload_config()


def create_default_config_file(config_path: Union[str, Path]) -> None:
    """Create a default configuration file."""
    get_config_manager().create_default_config_file(config_path)


def validate_config_file(config_path: Union[str, Path]) -> List[str]:
    """Validate a configuration file."""
    return get_config_manager().validate_config_file(config_path)