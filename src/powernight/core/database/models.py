"""
Database models for PowerNight.

Simplified models for Tesla Powerwall integration without multi-profile complexity.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import uuid4, UUID
import json

from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Text, 
    ForeignKey, UniqueConstraint, Index, JSON
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Session
# from sqlalchemy.dialects.postgresql import UUID as PostgresUUID, INET
from sqlalchemy.sql import func

from ...utils.timezone_utils import safe_format_datetime

Base = declarative_base()


class ScheduleEntry(Base):
    """Schedule entry model for time-based automation."""
    
    __tablename__ = 'schedule_entries'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    time = Column(String(8), nullable=False)  # HH:MM format
    backup_reserve_percentage = Column(Integer, nullable=False)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert schedule entry to dictionary."""
        return {
            'id': str(self.id),
            'name': self.name,
            'description': self.description,
            'time': self.time,
            'backup_reserve_percentage': self.backup_reserve_percentage,
            'enabled': self.enabled,
            'created_at': safe_format_datetime(self.created_at),
            'updated_at': safe_format_datetime(self.updated_at),
        }


class Task(Base):
    """Task model for persistent task scheduling."""

    __tablename__ = 'tasks'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name = Column(String(255), nullable=False)
    time = Column(String(8), nullable=False)  # HH:MM format for daily execution
    command = Column(String(50), nullable=False)  # mode, reserve, current, gridcharging, gridexport
    command_params = Column(JSON, nullable=True)  # Parameters for the command
    enabled = Column(Boolean, default=True)
    last_execution = Column(DateTime(timezone=True), nullable=True)
    last_status = Column(String(50), nullable=True)  # success, error, pending
    last_error = Column(Text, nullable=True)
    execution_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    
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


class TaskExecution(Base):
    """Task execution model for tracking async task execution status."""

    __tablename__ = 'task_executions'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id = Column(String(36), ForeignKey('tasks.id'), nullable=False)
    status = Column(String(20), nullable=False, default='pending')  # pending, running, success, error
    started_at = Column(DateTime(timezone=True), default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    result = Column(JSON, nullable=True)  # Execution result data
    error_message = Column(Text, nullable=True)
    # New fields for enhanced logging
    execution_type = Column(String(20), nullable=False, default='manual')  # scheduled, manual
    task_name = Column(String(255), nullable=True)  # Task name at execution time
    command = Column(String(50), nullable=True)  # Command type executed
    command_params = Column(JSON, nullable=True)  # Command parameters
    api_response = Column(JSON, nullable=True)  # Full PyPowerwall API response
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    
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
