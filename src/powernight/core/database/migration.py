"""
Database migration utilities for PowerNight.

Provides functions for initializing and migrating the database.
"""

import logging

from sqlalchemy import text

from .connection import get_database_manager, initialize_database
from .services import TaskPresetService

logger = logging.getLogger(__name__)


def drop_legacy_schedule_entries_table() -> bool:
    """
    Drop the legacy schedule_entries table if it exists.

    The schedule_entries table belonged to a removed legacy scheduling system;
    the current task system uses the tasks/task_executions/task_presets tables.

    Returns:
        True if the cleanup succeeded (or there was nothing to do)
    """
    try:
        initialize_database()
        db_manager = get_database_manager()
        with db_manager.get_session() as session:
            session.execute(text("DROP TABLE IF EXISTS schedule_entries"))
            session.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to drop legacy schedule_entries table: {e}")
        return False


def upgrade():
    """Run database migration."""
    run_migration()


def migrate_task_executions_table() -> bool:
    """
    Migrate task_executions table to add new logging columns.
    
    Returns:
        True if migration was successful, False otherwise
    """
    try:
        logger.info("Starting task_executions table migration")
        
        # Initialize database
        initialize_database()
        
        # Get database manager
        db_manager = get_database_manager()
        
        with db_manager.get_session() as session:
            # Check if new columns already exist
            result = session.execute(text("""
                SELECT COUNT(*) as count 
                FROM pragma_table_info('task_executions') 
                WHERE name IN ('execution_type', 'task_name', 'command', 'command_params', 'api_response')
            """))
            
            existing_columns = result.fetchone()[0]
            
            if existing_columns >= 5:
                logger.info("Task execution columns already exist, skipping migration")
                return True
            
            # Add new columns
            logger.info("Adding new columns to task_executions table")
            
            # Add execution_type column
            session.execute(text("""
                ALTER TABLE task_executions 
                ADD COLUMN execution_type VARCHAR(20) NOT NULL DEFAULT 'manual'
            """))
            
            # Add task_name column
            session.execute(text("""
                ALTER TABLE task_executions 
                ADD COLUMN task_name VARCHAR(255)
            """))
            
            # Add command column
            session.execute(text("""
                ALTER TABLE task_executions 
                ADD COLUMN command VARCHAR(50)
            """))
            
            # Add command_params column
            session.execute(text("""
                ALTER TABLE task_executions 
                ADD COLUMN command_params JSON
            """))
            
            # Add api_response column
            session.execute(text("""
                ALTER TABLE task_executions 
                ADD COLUMN api_response JSON
            """))
            
            session.commit()
            logger.info("Successfully added new columns to task_executions table")
            
            # Backfill existing records with available data
            logger.info("Backfilling existing task execution records")
            
            # Update existing records to set execution_type to 'scheduled' for records with task_id
            session.execute(text("""
                UPDATE task_executions 
                SET execution_type = 'scheduled' 
                WHERE task_id IS NOT NULL AND execution_type = 'manual'
            """))
            
            session.commit()
            logger.info("Successfully backfilled existing records")
            
        return True
        
    except Exception as e:
        logger.error(f"Task executions table migration failed: {e}")
        return False


BUILTIN_PRESETS = [
    {
        "name": "Night Charge to 100%",
        "command": "reserve",
        "command_params": {"reserve": 100},
        "default_time": "22:00",
        "sort_order": 1,
    },
    {
        "name": "Morning Low Reserve",
        "command": "reserve",
        "command_params": {"reserve": 20},
        "default_time": "06:00",
        "sort_order": 2,
    },
    {
        "name": "Enable Grid Charging",
        "command": "gridcharging",
        "command_params": {"enabled": True},
        "default_time": None,
        "sort_order": 3,
    },
    {
        "name": "Disable Grid Charging",
        "command": "gridcharging",
        "command_params": {"enabled": False},
        "default_time": None,
        "sort_order": 4,
    },
    {
        "name": "Self-Consumption Mode",
        "command": "mode",
        "command_params": {"mode": "self_consumption"},
        "default_time": None,
        "sort_order": 5,
    },
    {
        "name": "Backup Mode",
        "command": "mode",
        "command_params": {"mode": "backup"},
        "default_time": None,
        "sort_order": 6,
    },
    {
        "name": "Export PV Only",
        "command": "gridexport",
        "command_params": {"mode": "pv_only"},
        "default_time": None,
        "sort_order": 7,
    },
]


def ensure_preset_name_unique_index() -> bool:
    """
    Enforce uniqueness of task preset names at the database level.

    Deduplicates any historical duplicates first (keeping the oldest row per
    name), then creates a unique index. This makes preset seeding idempotent
    even across concurrent app starts.
    """
    try:
        initialize_database()
        db_manager = get_database_manager()
        with db_manager.get_session() as session:
            session.execute(text("""
                DELETE FROM task_presets
                WHERE rowid NOT IN (
                    SELECT MIN(rowid) FROM task_presets GROUP BY name
                )
            """))
            session.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_task_presets_name "
                "ON task_presets(name)"
            ))
            session.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to enforce preset name uniqueness: {e}")
        return False


def seed_builtin_presets() -> bool:
    """Seed built-in task presets if they don't already exist."""
    from sqlalchemy.exc import IntegrityError

    try:
        logger.info("Starting built-in preset seeding")
        initialize_database()

        preset_service = TaskPresetService()

        for preset_data in BUILTIN_PRESETS:
            try:
                if not preset_service.preset_exists_by_name(preset_data["name"]):
                    preset_service.create_preset(
                        is_builtin=True,
                        **preset_data
                    )
                    logger.info(f"Created built-in preset: {preset_data['name']}")
            except IntegrityError:
                # Another writer created it between check and insert; the
                # unique index makes this a no-op rather than a duplicate.
                logger.info(f"Preset already exists (concurrent seed): {preset_data['name']}")

        logger.info("Built-in preset seeding completed")
        return True
    except Exception as e:
        logger.error(f"Failed to seed built-in presets: {e}")
        return False


def run_migration() -> bool:
    """
    Run database migration.

    Creates/updates the schema, removes legacy artifacts, and seeds built-in
    task presets.

    Returns:
        True if migration was successful, False otherwise
    """
    # Create tables and run task executions table migration
    task_executions_success = migrate_task_executions_table()

    # Remove the legacy schedule_entries table
    legacy_cleanup_success = drop_legacy_schedule_entries_table()

    # Enforce preset-name uniqueness (dedupes historical duplicates first)
    unique_index_success = ensure_preset_name_unique_index()

    # Seed built-in task presets
    presets_success = seed_builtin_presets()

    return (task_executions_success and legacy_cleanup_success
            and unique_index_success and presets_success)