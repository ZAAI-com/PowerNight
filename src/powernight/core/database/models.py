"""
Database models for PowerNight.

Simplified models for Tesla Powerwall integration without multi-profile complexity.
"""

from datetime import datetime
from typing import Dict, Any, Optional
from uuid import uuid4

from sqlalchemy import (
    String, Integer, Boolean, DateTime, Text,
    ForeignKey, JSON
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func

from ...utils.timezone_utils import safe_format_datetime

class Base(DeclarativeBase):
    """Declarative base for PowerNight models."""


class Task(Base):
    """Task model for persistent task scheduling."""

    __tablename__ = 'tasks'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    time: Mapped[str] = mapped_column(String(8), nullable=False)  # HH:MM format for daily execution
    command: Mapped[str] = mapped_column(String(50), nullable=False)  # mode, reserve, current, gridcharging, gridexport
    command_params: Mapped[Any] = mapped_column(JSON, nullable=True)  # Parameters for the command
    enabled: Mapped[Optional[bool]] = mapped_column(Boolean, default=True)
    last_execution: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # success, error, pending
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    execution_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary."""
        return {
            'id': str(self.id),
            'name': self.name,
            'time': self.time,
            'command': self.command,
            'command_params': self.command_params,
            'enabled': self.enabled,
            'last_execution': safe_format_datetime(self.last_execution),
            'last_status': self.last_status,
            'last_error': self.last_error,
            'execution_count': self.execution_count or 0,
            'created_at': safe_format_datetime(self.created_at),
            'updated_at': safe_format_datetime(self.updated_at),
        }


class TaskPreset(Base):
    """Task preset model for reusable task templates."""

    __tablename__ = 'task_presets'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    command: Mapped[str] = mapped_column(String(50), nullable=False)
    command_params: Mapped[Any] = mapped_column(JSON, nullable=True)
    default_time: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)  # Optional HH:MM
    is_builtin: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    sort_order: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    def to_dict(self) -> Dict[str, Any]:
        """Convert task preset to dictionary."""
        return {
            'id': str(self.id),
            'name': self.name,
            'command': self.command,
            'command_params': self.command_params,
            'default_time': self.default_time,
            'is_builtin': self.is_builtin,
            'sort_order': self.sort_order,
            'created_at': safe_format_datetime(self.created_at),
            'updated_at': safe_format_datetime(self.updated_at),
        }


class TaskExecution(Base):
    """Task execution model for tracking async task execution status."""

    __tablename__ = 'task_executions'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey('tasks.id'), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='pending')  # pending, running, success, error
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[Any] = mapped_column(JSON, nullable=True)  # Execution result data
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # New fields for enhanced logging
    execution_type: Mapped[str] = mapped_column(String(20), nullable=False, default='manual')  # scheduled, manual
    task_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Task name at execution time
    command: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Command type executed
    command_params: Mapped[Any] = mapped_column(JSON, nullable=True)  # Command parameters
    api_response: Mapped[Any] = mapped_column(JSON, nullable=True)  # Full PyPowerwall API response
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task execution to dictionary."""
        return {
            'id': str(self.id),
            'task_id': str(self.task_id),
            'status': self.status,
            'started_at': safe_format_datetime(self.started_at),
            'completed_at': safe_format_datetime(self.completed_at),
            'result': self.result,
            'error_message': self.error_message,
            'execution_type': self.execution_type,
            'task_name': self.task_name,
            'command': self.command,
            'command_params': self.command_params,
            'api_response': self.api_response,
            'created_at': safe_format_datetime(self.created_at),
            'updated_at': safe_format_datetime(self.updated_at),
        }
