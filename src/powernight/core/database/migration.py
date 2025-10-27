"""
Database migration utilities for PowerNight.

Provides functions for initializing the database and creating default data.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from sqlalchemy import text

from .connection import get_database_manager, initialize_database
from .models import ScheduleEntry, TaskExecution
from .services import ScheduleService
from .exceptions import DatabaseError

logger = logging.getLogger(__name__)


def initialize_default_data() -> bool:
    """
    Initialize default data for the simplified PowerNight application.
    
    This function creates default schedule entries and initializes the database.
    
    Returns:
        True if initialization was successful, False otherwise
    """
    try:
        logger.info("Starting database initialization")
        
        # Initialize database
        initialize_database()
        
        # Get services
        schedule_service = ScheduleService()
        
        # Check if schedules already exist in database
        existing_schedules = schedule_service.list_schedules()
        if existing_schedules:
            logger.info(f"Found {len(existing_schedules)} existing schedules in database, skipping initialization")
            return True
        
        # Create default schedules
        try:
            # Default schedule: 40% at 0:01 (night)
            schedule_service.create_schedule(
                name="Night Reserve",
                time="00:01",
                backup_reserve_percentage=40,
                description="Set backup reserve to 40% at night",
                enabled=True
            )
            logger.info("Created default night schedule")
            
            # Default schedule: 0% at 4:58 (morning)
            schedule_service.create_schedule(
                name="Morning Reserve",
                time="04:58",
                backup_reserve_percentage=0,
                description="Set backup reserve to 0% in the morning",
                enabled=True
            )
            logger.info("Created default morning schedule")
            
        except Exception as e:
            logger.error(f"Failed to create default schedules: {e}")
            return False
        
        logger.info("Database initialization completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
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


def run_migration() -> bool:
    """
    Run database migration.
    
    This function runs both the default data initialization and the task executions migration.
    
    Returns:
        True if migration was successful, False otherwise
    """
    # Run default data initialization
    default_data_success = initialize_default_data()
    
    # Run task executions table migration
    task_executions_success = migrate_task_executions_table()
    
    return default_data_success and task_executions_success


def get_migration_status() -> Dict[str, Any]:
    """
    Get the current migration status.
    
    Returns:
        Dictionary containing migration status information
    """
    try:
        # Initialize database
        initialize_database()
        
        # Get schedule service
        schedule_service = ScheduleService()
        
        # Count existing schedules
        schedules = schedule_service.list_schedules()
        
        return {
            "status": "completed",
            "schedules_count": len(schedules),
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get migration status: {e}")
        return {
            "status": "error",
            "error": str(e),
            "last_updated": datetime.now(timezone.utc).isoformat()
        }