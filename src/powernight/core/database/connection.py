"""
Database connection management for PowerNight.

Provides database connection, session management, and configuration.
"""

import os
from typing import Optional, Generator
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import SQLAlchemyError

from .models import Base
from .exceptions import DatabaseConnectionError, DatabaseError
from ..config.manager import get_config


class DatabaseManager:
    """Database connection and session manager."""
    
    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize database manager.
        
        Args:
            database_url: Database connection URL. If None, will use config.
        """
        self.database_url = database_url or self._get_database_url()
        self.engine = None
        self.SessionLocal = None
        self._initialized = False
    
    def _get_database_url(self) -> str:
        """Get database URL from configuration."""
        try:
            config = get_config()
            # Use environment variable for data path, fallback to default structure
            data_path = os.environ.get('POWERNIGHT_DATA_PATH', os.path.join(os.getcwd(), 'data'))
            db_path = os.path.join(data_path, 'powernight.db')
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            return f"sqlite:///{db_path}"
        except Exception as e:
            # Fallback to in-memory SQLite for development
            return "sqlite:///:memory:"
    
    def initialize(self) -> None:
        """Initialize database connection and create tables."""
        try:
            # Create engine
            if self.database_url.startswith("sqlite"):
                self.engine = create_engine(
                    self.database_url,
                    poolclass=StaticPool,
                    connect_args={"check_same_thread": False},
                    echo=False  # Set to True for SQL debugging
                )
            else:
                self.engine = create_engine(
                    self.database_url,
                    pool_size=10,
                    max_overflow=20,
                    echo=False
                )
            
            # Create session factory
            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )
            
            # Create tables
            Base.metadata.create_all(bind=self.engine)
            
            self._initialized = True
            
        except SQLAlchemyError as e:
            raise DatabaseConnectionError(f"Failed to initialize database: {e}")
        except Exception as e:
            raise DatabaseConnectionError(f"Unexpected error initializing database: {e}")
    
    def get_session(self) -> Session:
        """Get a new database session."""
        if not self._initialized:
            self.initialize()
        
        if not self.SessionLocal:
            raise DatabaseConnectionError("Database not initialized")
        
        return self.SessionLocal()
    
    @contextmanager
    def get_session_context(self) -> Generator[Session, None, None]:
        """Get a database session with automatic cleanup."""
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def test_connection(self) -> bool:
        """Test database connection."""
        try:
            with self.get_session_context() as session:
                session.execute(text("SELECT 1"))
                return True
        except Exception:
            return False
    
    def close(self) -> None:
        """Close database connections."""
        if self.engine:
            self.engine.dispose()
            self.engine = None
        self.SessionLocal = None
        self._initialized = False


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def get_database_manager() -> DatabaseManager:
    """Get the global database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
        _db_manager.initialize()
    return _db_manager


def get_db_session() -> Session:
    """Get a database session."""
    return get_database_manager().get_session()


@contextmanager
def get_db_session_context() -> Generator[Session, None, None]:
    """Get a database session with automatic cleanup."""
    with get_database_manager().get_session_context() as session:
        yield session


def initialize_database() -> None:
    """Initialize the database."""
    get_database_manager().initialize()


def close_database() -> None:
    """Close database connections."""
    global _db_manager
    if _db_manager:
        _db_manager.close()
        _db_manager = None
