"""
PowerNight Configuration Backup and Recovery

Handles automatic backup creation and recovery of configuration files.
"""

import os
import shutil
import logging
import time
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime, timedelta

from .exceptions import ConfigurationError, BackupError


class ConfigBackupManager:
    """
    Manages configuration file backups and recovery.

    Provides automatic backup creation before config changes,
    recovery from backups when configs are corrupted, and
    cleanup of old backup files.
    """

    def __init__(self, backup_dir: Optional[Path] = None, max_backups: int = 10) -> None:
        """
        Initialize backup manager.

        Args:
            backup_dir: Directory to store backups. If None, uses .backups in config dir
            max_backups: Maximum number of backup files to keep
        """
        self.logger = logging.getLogger(__name__)
        self.max_backups = max_backups
        self._backup_dir = backup_dir

    def get_backup_dir(self, config_path: Path) -> Path:
        """
        Get backup directory for a configuration file.

        Args:
            config_path: Path to configuration file

        Returns:
            Path to backup directory
        """
        if self._backup_dir:
            return self._backup_dir

        # Use .backups directory next to the config file
        return config_path.parent / '.backups'

    def create_backup(self, config_path: Path) -> Optional[Path]:
        """
        Create a backup of the configuration file.

        Args:
            config_path: Path to configuration file to backup

        Returns:
            Path to created backup file, or None if backup failed
        """
        if not config_path.exists():
            self.logger.warning(f"Cannot backup non-existent config file: {config_path}")
            return None

        try:
            backup_dir = self.get_backup_dir(config_path)
            backup_dir.mkdir(parents=True, exist_ok=True)

            # Create timestamped backup filename; microseconds plus a
            # collision counter so rapid consecutive saves never overwrite
            # an earlier backup
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            backup_name = f"{config_path.stem}_{timestamp}{config_path.suffix}"
            backup_path = backup_dir / backup_name
            counter = 1
            while backup_path.exists():
                backup_name = f"{config_path.stem}_{timestamp}_{counter}{config_path.suffix}"
                backup_path = backup_dir / backup_name
                counter += 1

            # Copy the configuration file
            shutil.copy2(config_path, backup_path)

            # Backups can contain credentials; keep them owner-only
            os.chmod(backup_path, 0o600)

            self.logger.info(f"Created configuration backup: {backup_path}")

            # Clean up old backups
            self._cleanup_old_backups(backup_dir, config_path.stem)

            return backup_path

        except Exception as e:
            self.logger.error(f"Failed to create backup of {config_path}: {e}")
            return None

    def list_backups(self, config_path: Path) -> List[Path]:
        """
        List available backup files for a configuration.

        Args:
            config_path: Path to configuration file

        Returns:
            List of backup file paths, sorted by modification time (newest first)
        """
        backup_dir = self.get_backup_dir(config_path)

        if not backup_dir.exists():
            return []

        # Find backup files matching the config file name
        config_stem = config_path.stem
        backup_pattern = f"{config_stem}_*{config_path.suffix}"

        backup_files = list(backup_dir.glob(backup_pattern))

        # Sort by modification time, newest first
        backup_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        return backup_files

    def restore_from_backup(self, config_path: Path, backup_path: Optional[Path] = None) -> bool:
        """
        Restore configuration from a backup file.

        Args:
            config_path: Path where to restore the configuration
            backup_path: Specific backup to restore. If None, uses most recent backup

        Returns:
            True if restore was successful, False otherwise
        """
        try:
            if backup_path is None:
                # Find most recent backup
                backups = self.list_backups(config_path)
                if not backups:
                    self.logger.error(f"No backups found for {config_path}")
                    return False
                backup_path = backups[0]

            if not backup_path.exists():
                self.logger.error(f"Backup file does not exist: {backup_path}")
                return False

            # Create parent directory if needed
            config_path.parent.mkdir(parents=True, exist_ok=True)

            # Restore the backup
            shutil.copy2(backup_path, config_path)

            self.logger.info(f"Restored configuration from backup: {backup_path} -> {config_path}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to restore backup {backup_path} to {config_path}: {e}")
            return False

    def get_backup_info(self, config_path: Path) -> List[Dict[str, Any]]:
        """
        Get information about available backups.

        Args:
            config_path: Path to configuration file

        Returns:
            List of backup information dictionaries
        """
        backups = self.list_backups(config_path)
        backup_info = []

        for backup_path in backups:
            try:
                stat = backup_path.stat()
                backup_info.append({
                    'path': backup_path,
                    'size': stat.st_size,
                    'created': datetime.fromtimestamp(stat.st_mtime),
                    'age_days': (datetime.now() - datetime.fromtimestamp(stat.st_mtime)).days
                })
            except Exception as e:
                self.logger.warning(f"Failed to get info for backup {backup_path}: {e}")

        return backup_info

    def cleanup_old_backups(self, config_path: Path, max_age_days: Optional[int] = None) -> int:
        """
        Clean up old backup files.

        Args:
            config_path: Configuration file path
            max_age_days: Maximum age in days. If None, only keeps max_backups files

        Returns:
            Number of backup files removed
        """
        backup_dir = self.get_backup_dir(config_path)
        return self._cleanup_old_backups(backup_dir, config_path.stem, max_age_days)

    def _cleanup_old_backups(self, backup_dir: Path, config_stem: str, max_age_days: Optional[int] = None) -> int:
        """
        Internal method to clean up old backup files.

        Args:
            backup_dir: Directory containing backups
            config_stem: Configuration file stem (name without extension)
            max_age_days: Maximum age in days for backups

        Returns:
            Number of files removed
        """
        removed_count = 0

        try:
            # Find all backup files for this config
            backup_pattern = f"{config_stem}_*"
            backup_files = list(backup_dir.glob(backup_pattern))

            # Sort by modification time, newest first
            backup_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            # Remove files beyond max_backups limit
            if len(backup_files) > self.max_backups:
                for backup_file in backup_files[self.max_backups:]:
                    try:
                        backup_file.unlink()
                        removed_count += 1
                        self.logger.debug(f"Removed old backup: {backup_file}")
                    except Exception as e:
                        self.logger.warning(f"Failed to remove backup {backup_file}: {e}")

            # Remove files older than max_age_days
            if max_age_days is not None:
                cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)

                for backup_file in backup_files:
                    try:
                        if backup_file.stat().st_mtime < cutoff_time:
                            backup_file.unlink()
                            removed_count += 1
                            self.logger.debug(f"Removed old backup: {backup_file}")
                    except Exception as e:
                        self.logger.warning(f"Failed to remove backup {backup_file}: {e}")

        except Exception as e:
            self.logger.error(f"Error during backup cleanup: {e}")

        if removed_count > 0:
            self.logger.info(f"Cleaned up {removed_count} old backup files")

        return removed_count

    def verify_backup(self, backup_path: Path) -> bool:
        """
        Verify that a backup file is valid and loadable.

        Args:
            backup_path: Path to backup file to verify

        Returns:
            True if backup is valid, False otherwise
        """
        try:
            from .manager import ConfigManager

            # Try to validate the backup file without loading it as current config
            manager = ConfigManager()
            errors = manager.validate_config_file(backup_path)

            if errors:
                self.logger.warning(f"Backup validation failed for {backup_path}: {errors}")
                return False

            return True

        except Exception as e:
            self.logger.error(f"Failed to verify backup {backup_path}: {e}")
            return False


class ConfigRecoveryManager:
    """
    Handles automatic recovery from configuration errors.

    Provides strategies for recovering from corrupted configs,
    missing files, and validation errors.
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.backup_manager = ConfigBackupManager()

    def attempt_recovery(self, config_path: Path, error: Exception) -> Optional[Path]:
        """
        Attempt to recover from a configuration error.

        Args:
            config_path: Path to the problematic configuration file
            error: The error that occurred

        Returns:
            Path to recovered configuration, or None if recovery failed
        """
        self.logger.info(f"Attempting recovery for configuration error: {error}")

        # Strategy 1: Try to restore from most recent backup
        if self._try_restore_from_backup(config_path):
            return config_path

        # Strategy 2: Try to restore from an older backup that validates
        if self._try_restore_from_valid_backup(config_path):
            return config_path

        # No fabricated defaults: recovery only ever restores verified backups.
        # Overwriting the user's config with example values could silently
        # enable automation against a real Powerwall.
        self.logger.error(
            "Configuration recovery failed: no valid backup available. "
            f"Fix or restore {config_path} manually (see 'powernight-cli validate-config')."
        )
        return None

    def _try_restore_from_backup(self, config_path: Path) -> bool:
        """Try to restore from the most recent backup."""
        try:
            backups = self.backup_manager.list_backups(config_path)
            if not backups:
                self.logger.info("No backups available for restore")
                return False

            most_recent = backups[0]
            self.logger.info(f"Attempting restore from most recent backup: {most_recent}")

            if self.backup_manager.restore_from_backup(config_path, most_recent):
                # Verify the restored config
                if self.backup_manager.verify_backup(config_path):
                    self.logger.info("Successfully restored from most recent backup")
                    return True
                else:
                    self.logger.warning("Restored backup failed validation")

        except Exception as e:
            self.logger.error(f"Failed to restore from backup: {e}")

        return False

    def _try_restore_from_valid_backup(self, config_path: Path) -> bool:
        """Try to restore from the first valid backup found."""
        try:
            backups = self.backup_manager.list_backups(config_path)

            for backup_path in backups:
                self.logger.info(f"Checking backup: {backup_path}")

                if self.backup_manager.verify_backup(backup_path):
                    self.logger.info(f"Found valid backup: {backup_path}")

                    if self.backup_manager.restore_from_backup(config_path, backup_path):
                        self.logger.info("Successfully restored from valid backup")
                        return True

        except Exception as e:
            self.logger.error(f"Failed to find valid backup: {e}")

        return False

