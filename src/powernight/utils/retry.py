"""
PowerNight Retry Mechanisms

Comprehensive retry handling with exponential backoff for robustness.
"""

import asyncio
import functools
import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional, Type, Union, List
from datetime import datetime, timedelta

from .logging import get_logger, ComponentType, OperationType, LogLevel


class RetryStrategy(Enum):
    """Retry strategy types."""
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    FIXED_DELAY = "fixed_delay"
    LINEAR_BACKOFF = "linear_backoff"
    IMMEDIATE = "immediate"


class FailureType(Enum):
    """Types of failures that can trigger retries."""
    NETWORK_ERROR = "network_error"
    AUTHENTICATION_ERROR = "authentication_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    TIMEOUT_ERROR = "timeout_error"
    API_ERROR = "api_error"
    SYSTEM_ERROR = "system_error"
    TEMPORARY_ERROR = "temporary_error"


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    base_delay: float = 1.0  # Initial delay in seconds
    max_delay: float = 60.0  # Maximum delay in seconds
    multiplier: float = 2.0  # Backoff multiplier
    jitter: bool = True  # Add random jitter to delays
    jitter_range: tuple = (0.1, 0.1)  # Jitter range as (min, max) fraction
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF

    # Failure-specific configurations
    retryable_exceptions: List[Type[Exception]] = None
    non_retryable_exceptions: List[Type[Exception]] = None

    # Custom conditions
    retry_condition: Optional[Callable[[Exception], bool]] = None

    def __post_init__(self):
        """Initialize default exception lists."""
        if self.retryable_exceptions is None:
            self.retryable_exceptions = [
                ConnectionError,
                TimeoutError,
                OSError,
            ]

        if self.non_retryable_exceptions is None:
            self.non_retryable_exceptions = [
                ValueError,
                TypeError,
                AttributeError,
            ]


@dataclass
class RetryAttempt:
    """Information about a single retry attempt."""
    attempt_number: int
    delay: float
    exception: Optional[Exception]
    timestamp: datetime
    duration_ms: Optional[float] = None
    success: bool = False


class RetryHandler:
    """
    Comprehensive retry handler with multiple strategies and detailed logging.
    """

    def __init__(self, config: RetryConfig = None):
        """
        Initialize retry handler.

        Args:
            config: Retry configuration
        """
        self.config = config or RetryConfig()
        self.logger = get_logger()
        self.attempt_history: List[RetryAttempt] = []

    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for given attempt number.

        Args:
            attempt: Current attempt number (1-based)

        Returns:
            Delay in seconds
        """
        if self.config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = self.config.base_delay * (self.config.multiplier ** (attempt - 1))
        elif self.config.strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = self.config.base_delay * attempt
        elif self.config.strategy == RetryStrategy.FIXED_DELAY:
            delay = self.config.base_delay
        else:  # IMMEDIATE
            delay = 0.0

        # Apply maximum delay limit
        delay = min(delay, self.config.max_delay)

        # Add jitter if enabled
        if self.config.jitter and delay > 0:
            jitter_min, jitter_max = self.config.jitter_range
            jitter = random.uniform(-jitter_min * delay, jitter_max * delay)
            delay = max(0.1, delay + jitter)  # Ensure minimum delay

        return delay

    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """
        Determine if an operation should be retried.

        Args:
            exception: Exception that occurred
            attempt: Current attempt number

        Returns:
            True if should retry, False otherwise
        """
        # Check attempt limit
        if attempt >= self.config.max_attempts:
            return False

        # Check custom retry condition first
        if self.config.retry_condition:
            return self.config.retry_condition(exception)

        # Check non-retryable exceptions
        if any(isinstance(exception, exc_type) for exc_type in self.config.non_retryable_exceptions):
            return False

        # Check retryable exceptions
        return any(isinstance(exception, exc_type) for exc_type in self.config.retryable_exceptions)

    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with retry logic.

        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            Last exception if all retries exhausted
        """
        self.attempt_history.clear()
        last_exception = None

        for attempt in range(1, self.config.max_attempts + 1):
            start_time = time.time()

            try:
                self.logger.log_operation(
                    ComponentType.SYSTEM,
                    OperationType.INFO,
                    f"Executing function {func.__name__} (attempt {attempt}/{self.config.max_attempts})",
                    metadata={
                        'function': func.__name__,
                        'attempt': attempt,
                        'max_attempts': self.config.max_attempts
                    }
                )

                # Execute the function
                result = func(*args, **kwargs)

                # Record successful attempt
                duration_ms = (time.time() - start_time) * 1000
                attempt_info = RetryAttempt(
                    attempt_number=attempt,
                    delay=0.0,
                    exception=None,
                    timestamp=datetime.now(),
                    duration_ms=duration_ms,
                    success=True
                )
                self.attempt_history.append(attempt_info)

                self.logger.log_operation(
                    ComponentType.SYSTEM,
                    OperationType.INFO,
                    f"Function {func.__name__} succeeded on attempt {attempt}",
                    duration_ms=duration_ms,
                    metadata={
                        'function': func.__name__,
                        'attempt': attempt,
                        'total_attempts': len(self.attempt_history)
                    }
                )

                return result

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                last_exception = e

                # Check if we should retry
                should_retry = self.should_retry(e, attempt)

                if should_retry and attempt < self.config.max_attempts:
                    delay = self.calculate_delay(attempt + 1)

                    # Record failed attempt
                    attempt_info = RetryAttempt(
                        attempt_number=attempt,
                        delay=delay,
                        exception=e,
                        timestamp=datetime.now(),
                        duration_ms=duration_ms,
                        success=False
                    )
                    self.attempt_history.append(attempt_info)

                    self.logger.log_operation(
                        ComponentType.SYSTEM,
                        OperationType.WARNING,
                        f"Function {func.__name__} failed on attempt {attempt}, retrying in {delay:.2f}s",
                        duration_ms=duration_ms,
                        error_details=str(e),
                        metadata={
                            'function': func.__name__,
                            'attempt': attempt,
                            'delay': delay,
                            'exception_type': type(e).__name__
                        }
                    )

                    # Wait before retry
                    time.sleep(delay)
                else:
                    # Record final failed attempt
                    attempt_info = RetryAttempt(
                        attempt_number=attempt,
                        delay=0.0,
                        exception=e,
                        timestamp=datetime.now(),
                        duration_ms=duration_ms,
                        success=False
                    )
                    self.attempt_history.append(attempt_info)

                    # Log final failure
                    self.logger.log_operation(
                        ComponentType.SYSTEM,
                        OperationType.ERROR,
                        f"Function {func.__name__} failed permanently after {attempt} attempts",
                        duration_ms=duration_ms,
                        error_details=str(e),
                        metadata={
                            'function': func.__name__,
                            'total_attempts': attempt,
                            'exception_type': type(e).__name__,
                            'should_retry': should_retry
                        }
                    )
                    break

        # Re-raise the last exception
        raise last_exception

    async def execute_async(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute async function with retry logic.

        Args:
            func: Async function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            Last exception if all retries exhausted
        """
        self.attempt_history.clear()
        last_exception = None

        for attempt in range(1, self.config.max_attempts + 1):
            start_time = time.time()

            try:
                self.logger.log_operation(
                    ComponentType.SYSTEM,
                    OperationType.INFO,
                    f"Executing async function {func.__name__} (attempt {attempt}/{self.config.max_attempts})",
                    metadata={
                        'function': func.__name__,
                        'attempt': attempt,
                        'max_attempts': self.config.max_attempts
                    }
                )

                # Execute the async function
                result = await func(*args, **kwargs)

                # Record successful attempt
                duration_ms = (time.time() - start_time) * 1000
                attempt_info = RetryAttempt(
                    attempt_number=attempt,
                    delay=0.0,
                    exception=None,
                    timestamp=datetime.now(),
                    duration_ms=duration_ms,
                    success=True
                )
                self.attempt_history.append(attempt_info)

                self.logger.log_operation(
                    ComponentType.SYSTEM,
                    OperationType.INFO,
                    f"Async function {func.__name__} succeeded on attempt {attempt}",
                    duration_ms=duration_ms,
                    metadata={
                        'function': func.__name__,
                        'attempt': attempt,
                        'total_attempts': len(self.attempt_history)
                    }
                )

                return result

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                last_exception = e

                # Check if we should retry
                should_retry = self.should_retry(e, attempt)

                if should_retry and attempt < self.config.max_attempts:
                    delay = self.calculate_delay(attempt + 1)

                    # Record failed attempt
                    attempt_info = RetryAttempt(
                        attempt_number=attempt,
                        delay=delay,
                        exception=e,
                        timestamp=datetime.now(),
                        duration_ms=duration_ms,
                        success=False
                    )
                    self.attempt_history.append(attempt_info)

                    self.logger.log_operation(
                        ComponentType.SYSTEM,
                        OperationType.WARNING,
                        f"Async function {func.__name__} failed on attempt {attempt}, retrying in {delay:.2f}s",
                        duration_ms=duration_ms,
                        error_details=str(e),
                        metadata={
                            'function': func.__name__,
                            'attempt': attempt,
                            'delay': delay,
                            'exception_type': type(e).__name__
                        }
                    )

                    # Async wait before retry
                    await asyncio.sleep(delay)
                else:
                    # Record final failed attempt
                    attempt_info = RetryAttempt(
                        attempt_number=attempt,
                        delay=0.0,
                        exception=e,
                        timestamp=datetime.now(),
                        duration_ms=duration_ms,
                        success=False
                    )
                    self.attempt_history.append(attempt_info)

                    # Log final failure
                    self.logger.log_operation(
                        ComponentType.SYSTEM,
                        OperationType.ERROR,
                        f"Async function {func.__name__} failed permanently after {attempt} attempts",
                        duration_ms=duration_ms,
                        error_details=str(e),
                        metadata={
                            'function': func.__name__,
                            'total_attempts': attempt,
                            'exception_type': type(e).__name__,
                            'should_retry': should_retry
                        }
                    )
                    break

        # Re-raise the last exception
        raise last_exception

    def get_attempt_statistics(self) -> dict:
        """Get statistics about retry attempts."""
        if not self.attempt_history:
            return {}

        total_attempts = len(self.attempt_history)
        successful_attempts = sum(1 for attempt in self.attempt_history if attempt.success)
        failed_attempts = total_attempts - successful_attempts

        total_delay = sum(attempt.delay for attempt in self.attempt_history)
        avg_duration = sum(attempt.duration_ms or 0 for attempt in self.attempt_history) / total_attempts

        return {
            'total_attempts': total_attempts,
            'successful_attempts': successful_attempts,
            'failed_attempts': failed_attempts,
            'success_rate': successful_attempts / total_attempts if total_attempts > 0 else 0,
            'total_delay_seconds': total_delay,
            'average_duration_ms': avg_duration,
            'first_attempt': self.attempt_history[0].timestamp.isoformat(),
            'last_attempt': self.attempt_history[-1].timestamp.isoformat()
        }


def retry(config: RetryConfig = None):
    """
    Decorator for automatic retry with exponential backoff.

    Args:
        config: Retry configuration

    Example:
        @retry(RetryConfig(max_attempts=3, base_delay=1.0))
        def unreliable_function():
            # Function that might fail
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            handler = RetryHandler(config)
            return handler.execute(func, *args, **kwargs)
        return wrapper
    return decorator


def async_retry(config: RetryConfig = None):
    """
    Decorator for automatic retry with exponential backoff for async functions.

    Args:
        config: Retry configuration

    Example:
        @async_retry(RetryConfig(max_attempts=3, base_delay=1.0))
        async def unreliable_async_function():
            # Async function that might fail
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            handler = RetryHandler(config)
            return await handler.execute_async(func, *args, **kwargs)
        return wrapper
    return decorator


# Pre-configured retry configurations for common scenarios
POWERWALL_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    base_delay=2.0,
    max_delay=30.0,
    multiplier=2.0,
    jitter=True,
    strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
    retryable_exceptions=[
        ConnectionError,
        TimeoutError,
        OSError,
    ]
)

NETWORK_RETRY_CONFIG = RetryConfig(
    max_attempts=5,
    base_delay=1.0,
    max_delay=60.0,
    multiplier=2.0,
    jitter=True,
    strategy=RetryStrategy.EXPONENTIAL_BACKOFF
)

QUICK_RETRY_CONFIG = RetryConfig(
    max_attempts=2,
    base_delay=0.5,
    max_delay=5.0,
    multiplier=2.0,
    jitter=False,
    strategy=RetryStrategy.EXPONENTIAL_BACKOFF
)


# Global retry handler instances
_default_handler = RetryHandler()
_powerwall_handler = RetryHandler(POWERWALL_RETRY_CONFIG)
_network_handler = RetryHandler(NETWORK_RETRY_CONFIG)


def execute_with_retry(func: Callable, *args, config: RetryConfig = None, **kwargs) -> Any:
    """
    Execute function with retry logic using default or custom configuration.

    Args:
        func: Function to execute
        config: Optional retry configuration
        *args: Function arguments
        **kwargs: Function keyword arguments

    Returns:
        Function result
    """
    handler = RetryHandler(config) if config else _default_handler
    return handler.execute(func, *args, **kwargs)


async def execute_async_with_retry(func: Callable, *args, config: RetryConfig = None, **kwargs) -> Any:
    """
    Execute async function with retry logic using default or custom configuration.

    Args:
        func: Async function to execute
        config: Optional retry configuration
        *args: Function arguments
        **kwargs: Function keyword arguments

    Returns:
        Function result
    """
    handler = RetryHandler(config) if config else _default_handler
    return await handler.execute_async(func, *args, **kwargs)