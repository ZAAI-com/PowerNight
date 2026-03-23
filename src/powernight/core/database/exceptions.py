"""
Database exceptions for PowerNight.

Defines custom exceptions for database operations and schedule management.
"""


class DatabaseError(Exception):
    """Base exception for database-related errors."""
    pass


class ScheduleNotFoundError(DatabaseError):
    """Raised when a requested schedule is not found."""
    pass


class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails."""
    pass


class DatabaseMigrationError(DatabaseError):
    """Raised when database migration fails."""
    pass


class TaskNotFoundError(DatabaseError):
    """Raised when a requested task is not found."""
    pass


class PresetNotFoundError(DatabaseError):
    """Raised when a requested preset is not found."""
    pass
