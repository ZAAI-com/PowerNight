"""
Database package for PowerNight.

Provides database models, connection management, and data access layers
for schedule management and settings persistence.
"""

from .connection import get_db_session, get_db_session_context
from .exceptions import DatabaseError, TaskNotFoundError, PresetNotFoundError, PresetNameConflictError, PresetProtectedError
from .models import Base, Task, TaskPreset
from . import migration as db_migration


__all__ = [
    'get_db_session',
    'get_db_session_context',
    'DatabaseError',
    'TaskNotFoundError',
    'PresetNotFoundError',
    'PresetNameConflictError',
    'PresetProtectedError',
    'Base',
    'Task',
    'TaskPreset',
    'db_migration'
]
