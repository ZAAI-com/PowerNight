"""
Database package for PowerNight.

Provides database models, connection management, and data access layers
for schedule management and settings persistence.
"""

from .connection import get_db_session, get_db_session_context
from .exceptions import DatabaseError, ScheduleNotFoundError, TaskNotFoundError
from .models import Base, ScheduleEntry, Task
from . import migration as db_migration


__all__ = [
    'get_db_session',
    'get_db_session_context',
    'DatabaseError',
    'ScheduleNotFoundError',
    'TaskNotFoundError',
    'Base',
    'ScheduleEntry',
    'Task',
    'db_migration'
]
