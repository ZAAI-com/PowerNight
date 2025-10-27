"""
PowerNight Configuration Management API

Enterprise-grade configuration management with backup, rollback, and audit capabilities.
"""

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import threading

from ...core.config import get_config_manager, ConfigManager, get_config
from .schemas import SchemaValidator, ConfigurationChangeRequest, ValidationResult


@dataclass
class ConfigurationBackup:
    """Represents a configuration backup."""
    backup_id: str
    timestamp: datetime
    user_id: str
    reason: str
    config_data: Dict[str, Any]
    file_path: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            'backup_id': self.backup_id,
            'timestamp': self.timestamp.isoformat(),
            'user_id': self.user_id,
            'reason': self.reason,
            'file_path': str(self.file_path) if self.file_path else None,
            'size_bytes': len(json.dumps(self.config_data)) if self.config_data else 0
        }


@dataclass
class ConfigurationDiff:
    """Represents differences between two configurations."""
    added: Dict[str, Any] = field(default_factory=dict)
    removed: Dict[str, Any] = field(default_factory=dict)
    changed: Dict[str, Any] = field(default_factory=dict)

    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return bool(self.added or self.removed or self.changed)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            'has_changes': self.has_changes(),
            'changes': {
                'added': self.added,
                'removed': self.removed,
                'changed': self.changed
            },
            'change_count': len(self.added) + len(self.removed) + len(self.changed)
        }


class EnterpriseConfigManager:
    """
    Enterprise-grade configuration manager with advanced features.

    Features:
    - Automatic configuration backups
    - Configuration validation and sanitization
    - Audit logging for all changes
    - Rollback capabilities
    - Configuration diff analysis
    - Thread-safe operations
    """

    def __init__(self, base_config_manager: Optional[ConfigManager] = None):
        """
        Initialize enterprise config manager.

        Args:
            base_config_manager: Base configuration manager to wrap
        """
        self.base_manager = base_config_manager or get_config_manager()
        self.validator = SchemaValidator()
        self.logger = logging.getLogger(__name__)

        # Thread safety
        self._lock = threading.RLock()

        # Backup configuration
        self.backup_dir = Path(".config_backups")
        self.max_backups = 50
        self.backup_dir.mkdir(exist_ok=True)

        # Audit configuration
        self.audit_log_path = Path(".audit.jsonl")

    def get_configuration(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """
        Get current configuration with optional sensitive data filtering.

        Args:
            include_sensitive: Whether to include sensitive fields

        Returns:
            Configuration dictionary
        """
        with self._lock:
            try:
                config = get_config()
                config_dict = self._config_to_dict(config)

                if not include_sensitive:
                    config_dict = self._filter_sensitive_data(config_dict)

                return {
                    'success': True,
                    'data': config_dict,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'version': self._get_config_version()
                }

            except Exception as e:
                self.logger.error(f"Failed to get configuration: {e}")
                return {
                    'success': False,
                    'error': f"Failed to retrieve configuration: {e}",
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }

    def update_configuration(self,
                           updates: Dict[str, Any],
                           user_id: str,
                           client_ip: str,
                           user_agent: str,
                           dry_run: bool = False) -> Dict[str, Any]:
        """
        Update configuration with enterprise-grade validation and backup.

        Args:
            updates: Configuration updates to apply
            user_id: ID of user making the change
            client_ip: Client IP address
            user_agent: Client user agent
            dry_run: Whether to perform validation only

        Returns:
            Update result with detailed feedback
        """
        with self._lock:
            change_request = ConfigurationChangeRequest(
                user_id=user_id,
                client_ip=client_ip,
                user_agent=user_agent,
                timestamp=datetime.now(timezone.utc),
                changes=updates,
                validation_result=ValidationResult(is_valid=False)
            )

            try:
                # Step 1: Validate the update request
                validation_result = self.validator.validate_config_update(updates)
                change_request.validation_result = validation_result

                if not validation_result.is_valid:
                    self._log_audit_event(change_request, 'validation_failed')
                    return {
                        'success': False,
                        'validation': validation_result.to_dict(),
                        'change_id': change_request.change_id,
                        'timestamp': change_request.timestamp.isoformat()
                    }

                # Step 2: Get current configuration for backup and diff
                current_config = self._config_to_dict(get_config())

                # Step 3: Calculate configuration diff
                config_diff = self._calculate_diff(
                    current_config,
                    validation_result.sanitized_data
                )

                if dry_run:
                    self._log_audit_event(change_request, 'dry_run_validation')
                    return {
                        'success': True,
                        'dry_run': True,
                        'validation': validation_result.to_dict(),
                        'diff': config_diff.to_dict(),
                        'change_id': change_request.change_id,
                        'timestamp': change_request.timestamp.isoformat()
                    }

                # Step 4: Create backup before making changes
                backup = self._create_backup(
                    current_config,
                    user_id,
                    f"Pre-update backup for change {change_request.change_id}"
                )

                # Step 5: Apply the configuration updates
                merged_config = self._merge_configurations(
                    current_config,
                    validation_result.sanitized_data
                )

                # Step 6: Convert merged config to PowerNightConfig object and save
                from ...core.config.schema import PowerNightConfig
                config_obj = PowerNightConfig.from_dict(merged_config)
                self.base_manager.save_config(config_obj)

                # Step 7: Log successful change
                self._log_audit_event(change_request, 'configuration_updated')

                # Step 8: Cleanup old backups
                self._cleanup_old_backups()

                return {
                    'success': True,
                    'validation': validation_result.to_dict(),
                    'diff': config_diff.to_dict(),
                    'backup': backup.to_dict(),
                    'change_id': change_request.change_id,
                    'timestamp': change_request.timestamp.isoformat(),
                    'message': 'Configuration updated successfully'
                }

            except Exception as e:
                self.logger.error(f"Configuration update failed: {e}")
                change_request.validation_result.errors.append(str(e))
                self._log_audit_event(change_request, 'update_failed')

                return {
                    'success': False,
                    'error': f"Configuration update failed: {e}",
                    'change_id': change_request.change_id,
                    'timestamp': change_request.timestamp.isoformat()
                }

    def rollback_configuration(self,
                             backup_id: str,
                             user_id: str,
                             client_ip: str,
                             reason: str = "Manual rollback") -> Dict[str, Any]:
        """
        Rollback configuration to a previous backup.

        Args:
            backup_id: ID of backup to restore
            user_id: ID of user performing rollback
            client_ip: Client IP address
            reason: Reason for rollback

        Returns:
            Rollback result
        """
        with self._lock:
            try:
                # Find the backup
                backup = self._find_backup(backup_id)
                if not backup:
                    return {
                        'success': False,
                        'error': f'Backup {backup_id} not found',
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }

                # Create backup of current state before rollback
                current_config = self._config_to_dict(get_config())
                pre_rollback_backup = self._create_backup(
                    current_config,
                    user_id,
                    f"Pre-rollback backup (rolling back to {backup_id})"
                )

                # Apply the backup configuration
                self.base_manager.save_config(backup.config_data)

                # Log rollback event
                self._log_audit_event_simple(
                    user_id=user_id,
                    client_ip=client_ip,
                    action='configuration_rollback',
                    details={
                        'backup_id': backup_id,
                        'reason': reason,
                        'pre_rollback_backup': pre_rollback_backup.backup_id
                    }
                )

                return {
                    'success': True,
                    'message': f'Configuration rolled back to backup {backup_id}',
                    'backup_restored': backup.to_dict(),
                    'pre_rollback_backup': pre_rollback_backup.to_dict(),
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }

            except Exception as e:
                self.logger.error(f"Configuration rollback failed: {e}")
                return {
                    'success': False,
                    'error': f'Rollback failed: {e}',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }

    def get_configuration_history(self, limit: int = 20) -> Dict[str, Any]:
        """
        Get configuration change history.

        Args:
            limit: Maximum number of history entries to return

        Returns:
            Configuration history
        """
        try:
            backups = self._list_backups(limit)
            audit_entries = self._get_recent_audit_entries(limit)

            return {
                'success': True,
                'data': {
                    'backups': [backup.to_dict() for backup in backups],
                    'audit_entries': audit_entries,
                    'total_backups': len(backups)
                },
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            self.logger.error(f"Failed to get configuration history: {e}")
            return {
                'success': False,
                'error': f'Failed to retrieve history: {e}',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

    def validate_configuration_only(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate configuration without applying changes.

        Args:
            config_data: Configuration data to validate

        Returns:
            Validation result
        """
        try:
            validation_result = self.validator.validate_config_update(config_data)

            return {
                'success': True,
                'validation': validation_result.to_dict(),
                'sanitized_data': validation_result.sanitized_data if validation_result.is_valid else None,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            self.logger.error(f"Configuration validation failed: {e}")
            return {
                'success': False,
                'error': f'Validation failed: {e}',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

    def _config_to_dict(self, config) -> Dict[str, Any]:
        """Convert configuration object to dictionary."""
        return {
            'powerwall': {
                'tesla_email': config.powerwall.tesla_email,
                'powerwall_id': config.powerwall.powerwall_id,
                'timeout': config.powerwall.timeout,
                'retry_attempts': config.powerwall.retry_attempts,
                'verify_ssl': config.powerwall.verify_ssl
            },
            'automation': {
                'enabled': config.automation.enabled,
                'check_interval': config.automation.check_interval,
                'schedule': [
                    {
                        'time': entry.time,
                        'percentage': entry.percentage,
                        'enabled': entry.enabled,
                        'description': entry.description
                    }
                    for entry in config.automation.schedule
                ]
            },
            'web_interface': {
                'enabled': config.web_interface.enabled,
                'host': config.web_interface.host,
                'port': config.web_interface.port,
                'debug': config.web_interface.debug,
                'auth_enabled': config.web_interface.auth_enabled,
                'username': config.web_interface.username,
                'password': config.web_interface.password,
                'api_key': config.web_interface.api_key,
                'cors_origins': config.web_interface.cors_origins
            },
            'logging': {
                'level': config.logging.level,
                'file_enabled': config.logging.file_enabled,
                'file_path': config.logging.file_path,
                'max_file_size': config.logging.max_file_size,
                'backup_count': config.logging.backup_count,
                'console_output': config.logging.console_output
            }
        }

    def _filter_sensitive_data(self, config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive data from configuration."""
        filtered = config_dict.copy()

        # Filter sensitive fields
        sensitive_fields = {
            'powerwall': ['email', 'password'],
            'web_interface': ['password', 'api_key']
        }

        for section, fields in sensitive_fields.items():
            if section in filtered:
                for field in fields:
                    if field in filtered[section]:
                        filtered[section][field] = "***REDACTED***" if filtered[section][field] else None

        return filtered

    def _create_backup(self,
                      config_data: Dict[str, Any],
                      user_id: str,
                      reason: str) -> ConfigurationBackup:
        """Create a configuration backup."""
        backup_id = f"backup_{int(datetime.now().timestamp())}_{user_id}"
        timestamp = datetime.now(timezone.utc)

        backup = ConfigurationBackup(
            backup_id=backup_id,
            timestamp=timestamp,
            user_id=user_id,
            reason=reason,
            config_data=config_data
        )

        # Save backup to file
        backup_file = self.backup_dir / f"{backup_id}.json"
        with open(backup_file, 'w') as f:
            json.dump({
                'metadata': backup.to_dict(),
                'config_data': config_data
            }, f, indent=2, default=str)

        backup.file_path = backup_file
        self.logger.info(f"Created configuration backup: {backup_id}")

        return backup

    def _find_backup(self, backup_id: str) -> Optional[ConfigurationBackup]:
        """Find a backup by ID."""
        backup_file = self.backup_dir / f"{backup_id}.json"
        if not backup_file.exists():
            return None

        try:
            with open(backup_file, 'r') as f:
                backup_data = json.load(f)

            metadata = backup_data['metadata']
            return ConfigurationBackup(
                backup_id=metadata['backup_id'],
                timestamp=datetime.fromisoformat(metadata['timestamp']),
                user_id=metadata['user_id'],
                reason=metadata['reason'],
                config_data=backup_data['config_data'],
                file_path=backup_file
            )

        except Exception as e:
            self.logger.error(f"Failed to load backup {backup_id}: {e}")
            return None

    def _list_backups(self, limit: int = 20) -> List[ConfigurationBackup]:
        """List available backups."""
        backups = []

        for backup_file in sorted(self.backup_dir.glob("backup_*.json"), reverse=True):
            if len(backups) >= limit:
                break

            backup = self._find_backup(backup_file.stem)
            if backup:
                backups.append(backup)

        return backups

    def _cleanup_old_backups(self) -> None:
        """Remove old backups beyond the retention limit."""
        backups = sorted(self.backup_dir.glob("backup_*.json"))

        if len(backups) > self.max_backups:
            for backup_file in backups[:-self.max_backups]:
                try:
                    backup_file.unlink()
                    self.logger.info(f"Removed old backup: {backup_file.name}")
                except Exception as e:
                    self.logger.error(f"Failed to remove backup {backup_file.name}: {e}")

    def _calculate_diff(self,
                       current: Dict[str, Any],
                       new: Dict[str, Any]) -> ConfigurationDiff:
        """Calculate differences between configurations."""
        diff = ConfigurationDiff()

        # Simple implementation - can be enhanced for nested diff
        for section, values in new.items():
            if section not in current:
                diff.added[section] = values
            elif current[section] != values:
                diff.changed[section] = {
                    'old': current[section],
                    'new': values
                }

        for section in current:
            if section not in new:
                diff.removed[section] = current[section]

        return diff

    def _merge_configurations(self,
                            current: Dict[str, Any],
                            updates: Dict[str, Any]) -> Dict[str, Any]:
        """Merge configuration updates with current configuration."""
        merged = current.copy()

        for section, values in updates.items():
            if section in merged:
                if isinstance(values, dict) and isinstance(merged[section], dict):
                    merged[section].update(values)
                else:
                    merged[section] = values
            else:
                merged[section] = values

        return merged

    def _log_audit_event(self, change_request: ConfigurationChangeRequest, action: str) -> None:
        """Log audit event for configuration change."""
        audit_entry = {
            'timestamp': change_request.timestamp.isoformat(),
            'action': action,
            'change_request': change_request.to_audit_log()
        }

        try:
            with open(self.audit_log_path, 'a') as f:
                f.write(json.dumps(audit_entry, default=str) + '\n')
        except Exception as e:
            self.logger.error(f"Failed to write audit log: {e}")

    def _log_audit_event_simple(self,
                               user_id: str,
                               client_ip: str,
                               action: str,
                               details: Dict[str, Any]) -> None:
        """Log simple audit event."""
        audit_entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'action': action,
            'user_id': user_id,
            'client_ip': client_ip,
            'details': details
        }

        try:
            with open(self.audit_log_path, 'a') as f:
                f.write(json.dumps(audit_entry, default=str) + '\n')
        except Exception as e:
            self.logger.error(f"Failed to write audit log: {e}")

    def _get_recent_audit_entries(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent audit log entries."""
        if not self.audit_log_path.exists():
            return []

        entries = []
        try:
            with open(self.audit_log_path, 'r') as f:
                lines = f.readlines()

            # Get the last 'limit' lines
            for line in lines[-limit:]:
                try:
                    entry = json.loads(line.strip())
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue

        except Exception as e:
            self.logger.error(f"Failed to read audit log: {e}")

        return list(reversed(entries))  # Most recent first

    def _get_config_version(self) -> str:
        """Get configuration version identifier."""
        return f"v{int(datetime.now().timestamp())}"


# Global enterprise config manager instance
_enterprise_config_manager: Optional[EnterpriseConfigManager] = None


def get_enterprise_config_manager() -> EnterpriseConfigManager:
    """Get the global enterprise configuration manager instance."""
    global _enterprise_config_manager
    if _enterprise_config_manager is None:
        _enterprise_config_manager = EnterpriseConfigManager()
    return _enterprise_config_manager