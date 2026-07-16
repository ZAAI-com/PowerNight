"""
PowerNight Central Logging Infrastructure

Comprehensive logging system for all PowerNight components including
web interface, Powerwall operations, configuration management, and scheduling.
"""

import json
import logging
import logging.handlers
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, List, Union
from dataclasses import dataclass, asdict
from enum import Enum

from .timezone_utils import safe_format_datetime


class LogLevel(Enum):
    """Log levels for PowerNight operations."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ComponentType(Enum):
    """PowerNight application components."""
    WEB = "web"
    POWERWALL = "powerwall"
    SCHEDULER = "scheduler"
    CONFIG = "config"
    SYSTEM = "system"
    API = "api"


class OperationType(Enum):
    """Types of operations that can be logged."""
    STARTUP = "startup"
    SHUTDOWN = "shutdown"
    CONFIG_LOAD = "config_load"
    CONFIG_SAVE = "config_save"
    POWERWALL_CONNECT = "powerwall_connect"
    POWERWALL_DISCONNECT = "powerwall_disconnect"
    RESERVE_CHANGE = "reserve_change"
    SCHEDULE_EXECUTE = "schedule_execute"
    API_REQUEST = "api_request"
    API_RESPONSE = "api_response"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class LogEntry:
    """Structured log entry for PowerNight operations."""
    timestamp: str
    component: ComponentType
    operation: OperationType
    level: LogLevel
    message: str
    duration_ms: Optional[float] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    error_details: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    api_response: Optional[Dict[str, Any]] = None
    response_size_bytes: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result['component'] = self.component.value
        result['operation'] = self.operation.value
        result['level'] = self.level.value
        # Format timestamp with timezone
        result['timestamp'] = safe_format_datetime(self.timestamp)
        return result

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


class PowerNightLogger:
    """
    Central logging system for PowerNight application.

    Provides structured logging with rotation, multiple output formats,
    and component-specific loggers for different parts of the application.
    """

    def __init__(self,
                 log_dir: Optional[Path] = None,
                 log_level: LogLevel = LogLevel.INFO,
                 enable_console: bool = True,
                 enable_file: bool = True,
                 enable_json: bool = True,
                 max_log_size: int = 50 * 1024 * 1024,  # 50MB
                 backup_count: int = 10,
                 console_level: LogLevel = LogLevel.INFO,
                 file_level: LogLevel = LogLevel.DEBUG):
        """
        Initialize the PowerNight logger.

        Args:
            log_dir: Directory for log files (defaults to /app/logs or ./logs)
            log_level: Minimum log level to process
            enable_console: Enable console logging
            enable_file: Enable file logging
            enable_json: Enable JSON structured logging
            max_log_size: Maximum size per log file in bytes
            backup_count: Number of backup log files to keep
            console_level: Log level for console output
            file_level: Log level for file output
        """
        # Set log directory - prefer Docker path, fallback to local
        if log_dir:
            self.log_dir = Path(log_dir)
        elif os.path.exists('/app'):
            self.log_dir = Path('/app/logs')
        else:
            self.log_dir = Path('./logs')

        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.log_level = log_level
        self.enable_console = enable_console
        self.enable_file = enable_file
        self.enable_json = enable_json
        self.max_log_size = max_log_size
        self.backup_count = backup_count
        self.console_level = console_level
        self.file_level = file_level

        self._lock = threading.Lock()
        self._loggers: Dict[str, logging.Logger] = {}

        # Setup main application logger
        self._setup_main_logger()

        # Setup component-specific loggers
        self._setup_component_loggers()

        # Log startup
        self.log_system_event(OperationType.STARTUP, "PowerNight logging system initialized")

    def _setup_main_logger(self) -> None:
        """Setup the main PowerNight logger."""
        self.main_logger = logging.getLogger("powernight")
        self.main_logger.setLevel(self._log_level_to_python(self.log_level))

        # Clear existing handlers
        self.main_logger.handlers.clear()
        self.main_logger.propagate = False

        # Console handler
        if self.enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(self._log_level_to_python(self.console_level))
            console_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(console_formatter)
            self.main_logger.addHandler(console_handler)

        # File handler with rotation
        if self.enable_file:
            file_handler = logging.handlers.RotatingFileHandler(
                self.log_dir / "powernight.log",
                maxBytes=self.max_log_size,
                backupCount=self.backup_count,
                encoding='utf-8'
            )
            file_handler.setLevel(self._log_level_to_python(self.file_level))
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s - '
                '[%(filename)s:%(lineno)d] - [%(funcName)s]'
            )
            file_handler.setFormatter(file_formatter)
            self.main_logger.addHandler(file_handler)

        # JSON handler for structured logging
        if self.enable_json:
            json_handler = logging.handlers.RotatingFileHandler(
                self.log_dir / "powernight.jsonl",
                maxBytes=self.max_log_size,
                backupCount=self.backup_count,
                encoding='utf-8'
            )
            json_handler.setLevel(self._log_level_to_python(self.file_level))
            json_handler.setFormatter(JSONFormatter())
            self.main_logger.addHandler(json_handler)

    def _setup_component_loggers(self) -> None:
        """Setup component-specific loggers."""
        components = [
            ("web", "powernight.web"),
            ("powerwall", "powernight.powerwall"),
            ("scheduler", "powernight.scheduler"),
            ("config", "powernight.config"),
            ("system", "powernight.system")
        ]

        for component_name, logger_name in components:
            logger = logging.getLogger(logger_name)
            logger.setLevel(self._log_level_to_python(self.log_level))
            logger.propagate = True  # Propagate to main logger
            self._loggers[component_name] = logger

    def apply_log_level(self, level) -> None:
        """
        Apply a new minimum log level to all PowerNight loggers and handlers.

        Called after configuration load so that config.logging.level (and the
        POWERNIGHT_LOG_LEVEL override) actually takes effect at runtime.

        Args:
            level: LogLevel enum member or level name string (e.g. "DEBUG")
        """
        if isinstance(level, str):
            try:
                level = LogLevel(level.upper())
            except ValueError:
                self.main_logger.warning(
                    f"Unknown log level '{level}', keeping {self.log_level.value}"
                )
                return

        with self._lock:
            self.log_level = level
            py_level = self._log_level_to_python(level)
            self.main_logger.setLevel(py_level)
            for handler in self.main_logger.handlers:
                handler.setLevel(py_level)
            for component_logger in self._loggers.values():
                component_logger.setLevel(py_level)

        self.main_logger.info(f"Log level set to {level.value}")

    def _log_level_to_python(self, level: LogLevel) -> int:
        """Convert LogLevel enum to Python logging level."""
        mapping = {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.WARNING: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
            LogLevel.CRITICAL: logging.CRITICAL
        }
        return mapping[level]

    def get_component_logger(self, component: ComponentType) -> logging.Logger:
        """Get logger for specific component."""
        return self._loggers.get(component.value, self.main_logger)

    def log_entry(self, entry: LogEntry) -> None:
        """
        Log a structured entry.

        Args:
            entry: LogEntry to log
        """
        logger = self.get_component_logger(entry.component)
        level = self._log_level_to_python(entry.level)

        # Create extra data for structured logging
        extra_data = {
            'component': entry.component.value,
            'operation': entry.operation.value,
            'duration_ms': entry.duration_ms,
            'user_id': entry.user_id,
            'session_id': entry.session_id,
            'request_id': entry.request_id,
            'error_details': entry.error_details,
            'metadata': entry.metadata,
            'api_response': entry.api_response,
            'response_size_bytes': entry.response_size_bytes
        }

        logger.log(level, entry.message, extra=extra_data)

    def sanitize_api_response(self, response: Any, max_size_bytes: int = 10485760) -> Dict[str, Any]:
        """
        Sanitize API response by removing sensitive data and limiting size.
        
        Args:
            response: The API response to sanitize
            max_size_bytes: Maximum size in bytes for the response
            
        Returns:
            Sanitized response as dictionary
        """
        def sanitize_value(key: str, value: Any) -> Any:
            """Sanitize individual values based on key name."""
            sensitive_keys = ['token', 'password', 'email', 'secret', 'key', 'auth', 'credential']
            key_lower = key.lower()
            
            if any(sensitive in key_lower for sensitive in sensitive_keys):
                if isinstance(value, str):
                    if '@' in value and 'email' in key_lower:  # Email address
                        parts = value.split('@')
                        if len(parts) == 2:
                            return f"{parts[0][:1]}***@{parts[1]}"
                    return "***REDACTED***"
                elif isinstance(value, (dict, list)):
                    return "***REDACTED***"
            return value

        def sanitize_recursive(obj: Any, path: str = "") -> Any:
            """Recursively sanitize nested objects."""
            if isinstance(obj, dict):
                sanitized = {}
                for k, v in obj.items():
                    current_path = f"{path}.{k}" if path else k
                    sanitized[k] = sanitize_recursive(sanitize_value(k, v), current_path)
                return sanitized
            elif isinstance(obj, list):
                return [sanitize_recursive(item, f"{path}[{i}]") for i, item in enumerate(obj)]
            else:
                return obj

        try:
            # Convert response to dict if it's not already
            if hasattr(response, '__dict__'):
                response_dict = response.__dict__
            elif isinstance(response, (str, int, float, bool)):
                response_dict = {"value": response}
            else:
                response_dict = response

            # Sanitize the response
            sanitized = sanitize_recursive(response_dict)
            
            # Check size limit
            response_str = json.dumps(sanitized, default=str)
            if len(response_str.encode('utf-8')) > max_size_bytes:
                return {
                    "error": "Response too large",
                    "size_bytes": len(response_str.encode('utf-8')),
                    "max_size_bytes": max_size_bytes,
                    "truncated": True
                }
            
            return sanitized
            
        except Exception as e:
            return {
                "error": f"Failed to sanitize response: {str(e)}",
                "original_type": str(type(response))
            }

    def log_operation(self,
                     component: ComponentType,
                     operation: OperationType,
                     message: str,
                     level: LogLevel = LogLevel.INFO,
                     duration_ms: Optional[float] = None,
                     error_details: Optional[str] = None,
                     metadata: Optional[Dict[str, Any]] = None,
                     api_response: Optional[Dict[str, Any]] = None,
                     response_size_bytes: Optional[int] = None,
                     **kwargs) -> None:
        """
        Log an operation with structured data.

        Args:
            component: Component performing the operation
            operation: Type of operation
            message: Log message
            level: Log level
            duration_ms: Operation duration in milliseconds
            error_details: Error details if applicable
            metadata: Additional metadata
            api_response: Full API response data
            response_size_bytes: Size of API response in bytes
            **kwargs: Additional fields for LogEntry
        """
        entry = LogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            component=component,
            operation=operation,
            level=level,
            message=message,
            duration_ms=duration_ms,
            error_details=error_details,
            metadata=metadata,
            api_response=api_response,
            response_size_bytes=response_size_bytes,
            **kwargs
        )
        self.log_entry(entry)

    def log_web_request(self, method: str, path: str, status_code: int,
                       duration_ms: float, user_id: Optional[str] = None,
                       session_id: Optional[str] = None,
                       request_id: Optional[str] = None) -> None:
        """Log web request."""
        level = LogLevel.WARNING if status_code >= 400 else LogLevel.INFO
        self.log_operation(
            ComponentType.WEB,
            OperationType.API_REQUEST,
            f"{method} {path} - {status_code}",
            level=level,
            duration_ms=duration_ms,
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            metadata={
                'method': method,
                'path': path,
                'status_code': status_code
            }
        )

    def log_powerwall_operation(self, operation: str, success: bool,
                              duration_ms: Optional[float] = None,
                              error_details: Optional[str] = None,
                              metadata: Optional[Dict[str, Any]] = None) -> None:
        """Log Powerwall operation."""
        level = LogLevel.INFO if success else LogLevel.ERROR
        op_type = OperationType.INFO if success else OperationType.ERROR

        self.log_operation(
            ComponentType.POWERWALL,
            op_type,
            f"Powerwall {operation}: {'success' if success else 'failed'}",
            level=level,
            duration_ms=duration_ms,
            error_details=error_details,
            metadata=metadata
        )

    def log_config_operation(self, operation: str, config_type: str,
                           success: bool, duration_ms: Optional[float] = None,
                           error_details: Optional[str] = None) -> None:
        """Log configuration operation."""
        level = LogLevel.INFO if success else LogLevel.ERROR
        op_type = OperationType.CONFIG_SAVE if 'save' in operation.lower() else OperationType.CONFIG_LOAD

        self.log_operation(
            ComponentType.CONFIG,
            op_type,
            f"Config {operation} ({config_type}): {'success' if success else 'failed'}",
            level=level,
            duration_ms=duration_ms,
            error_details=error_details,
            metadata={'config_type': config_type}
        )

    def log_schedule_operation(self, job_name: str, success: bool,
                             duration_ms: Optional[float] = None,
                             error_details: Optional[str] = None,
                             metadata: Optional[Dict[str, Any]] = None) -> None:
        """Log scheduled job execution."""
        level = LogLevel.INFO if success else LogLevel.ERROR
        op_type = OperationType.SCHEDULE_EXECUTE

        self.log_operation(
            ComponentType.SCHEDULER,
            op_type,
            f"Job {job_name}: {'completed' if success else 'failed'}",
            level=level,
            duration_ms=duration_ms,
            error_details=error_details,
            metadata=metadata
        )

    def log_system_event(self, operation: OperationType, message: str,
                        level: LogLevel = LogLevel.INFO,
                        metadata: Optional[Dict[str, Any]] = None) -> None:
        """Log system-level events."""
        self.log_operation(
            ComponentType.SYSTEM,
            operation,
            message,
            level=level,
            metadata=metadata
        )

    def log_error(self, component: ComponentType, message: str,
                 error: Exception, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Log error with exception details."""
        self.log_operation(
            component,
            OperationType.ERROR,
            f"Error: {message}",
            level=LogLevel.ERROR,
            error_details=f"{type(error).__name__}: {str(error)}",
            metadata=metadata
        )

    def get_recent_logs(self, limit: int = 100,
                       component: Optional[ComponentType] = None,
                       level: Optional[LogLevel] = None) -> List[LogEntry]:
        """
        Get recent log entries from JSON log file.

        Args:
            limit: Maximum number of entries to return
            component: Filter by component
            level: Filter by minimum log level

        Returns:
            List of recent LogEntry objects
        """
        entries = []
        json_log_file = self.log_dir / "powernight.jsonl"

        if not json_log_file.exists():
            return entries

        try:
            with open(json_log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Process lines in reverse order (most recent first)
            for line in reversed(lines[-limit*2:]):  # Read more to account for filtering
                try:
                    data = json.loads(line.strip())

                    # Skip if not our structured format
                    if 'component' not in data or 'operation' not in data:
                        continue

                    entry = LogEntry(
                        timestamp=data['timestamp'],
                        component=ComponentType(data['component']),
                        operation=OperationType(data['operation']),
                        level=LogLevel(data['level']),
                        message=data['message'],
                        duration_ms=data.get('duration_ms'),
                        user_id=data.get('user_id'),
                        session_id=data.get('session_id'),
                        request_id=data.get('request_id'),
                        error_details=data.get('error_details'),
                        metadata=data.get('metadata'),
                        api_response=data.get('api_response'),
                        response_size_bytes=data.get('response_size_bytes')
                    )

                    # Apply filters
                    if component and entry.component != component:
                        continue
                    if level and self._log_level_to_python(entry.level) < self._log_level_to_python(level):
                        continue

                    entries.append(entry)

                    if len(entries) >= limit:
                        break

                except (json.JSONDecodeError, KeyError, ValueError):
                    continue

        except Exception as e:
            self.main_logger.error(f"Failed to read recent logs: {e}")

        return entries

    def get_log_statistics(self) -> Dict[str, Any]:
        """Get logging statistics."""
        entries = self.get_recent_logs(limit=1000)

        stats = {
            'total_entries': len(entries),
            'by_component': {},
            'by_level': {},
            'by_operation': {},
            'error_rate': 0.0,
            'avg_duration_ms': 0.0
        }

        durations = []
        error_count = 0

        for entry in entries:
            # Count by component
            comp = entry.component.value
            stats['by_component'][comp] = stats['by_component'].get(comp, 0) + 1

            # Count by level
            level = entry.level.value
            stats['by_level'][level] = stats['by_level'].get(level, 0) + 1

            # Count by operation
            op = entry.operation.value
            stats['by_operation'][op] = stats['by_operation'].get(op, 0) + 1

            # Track errors
            if entry.level in [LogLevel.ERROR, LogLevel.CRITICAL]:
                error_count += 1

            # Track durations
            if entry.duration_ms:
                durations.append(entry.duration_ms)

        if len(entries) > 0:
            stats['error_rate'] = error_count / len(entries)

        if durations:
            stats['avg_duration_ms'] = sum(durations) / len(durations)

        return stats

    def shutdown(self) -> None:
        """Shutdown the logging system."""
        self.log_system_event(OperationType.SHUTDOWN, "PowerNight logging system shutting down")

        # Close all handlers
        for handler in self.main_logger.handlers:
            handler.close()
    
    # Standard logging methods for compatibility
    def debug(self, message: str, *args, **kwargs) -> None:
        """Log a debug message."""
        self.main_logger.debug(message, *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs) -> None:
        """Log an info message."""
        self.main_logger.info(message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs) -> None:
        """Log a warning message."""
        self.main_logger.warning(message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs) -> None:
        """Log an error message."""
        self.main_logger.error(message, *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs) -> None:
        """Log a critical message."""
        self.main_logger.critical(message, *args, **kwargs)


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""

    def format(self, record) -> str:
        """Format log record as JSON."""
        log_data = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }

        # Add extra fields from LogEntry if present
        extra_fields = [
            'component', 'operation', 'duration_ms', 'user_id',
            'session_id', 'request_id', 'error_details', 'metadata',
            'api_response', 'response_size_bytes'
        ]

        for field in extra_fields:
            if hasattr(record, field):
                log_data[field] = getattr(record, field)

        return json.dumps(log_data, default=self._json_serializer)

    def _json_serializer(self, obj):
        """Custom JSON serializer for non-serializable objects."""
        from pathlib import Path
        from datetime import datetime

        if isinstance(obj, Path):
            return str(obj)
        elif isinstance(obj, datetime):
            return obj.isoformat()
        else:
            return str(obj)


# Global logger instance
_powernight_logger: Optional[PowerNightLogger] = None


def get_logger() -> PowerNightLogger:
    """Get the global PowerNight logger instance."""
    global _powernight_logger
    if _powernight_logger is None:
        _powernight_logger = PowerNightLogger()
    return _powernight_logger


def setup_logging(log_dir: Optional[Path] = None,
                 log_level: LogLevel = LogLevel.INFO,
                 **kwargs) -> PowerNightLogger:
    """Setup and configure the global PowerNight logger."""
    global _powernight_logger
    _powernight_logger = PowerNightLogger(log_dir=log_dir, log_level=log_level, **kwargs)
    return _powernight_logger


def shutdown_logging() -> None:
    """Shutdown the global logging system."""
    global _powernight_logger
    if _powernight_logger:
        _powernight_logger.shutdown()
        _powernight_logger = None