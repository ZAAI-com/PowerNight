"""
PowerNight Backup Reserve Management

Advanced backup reserve percentage management and validation.
"""

import logging
import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

from .exceptions import PowerwallValidationError, PowerwallAPIError


@dataclass
class ReserveChangeRequest:
    """Request to change backup reserve percentage."""
    target_percentage: float
    current_percentage: Optional[float] = None
    reason: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    max_wait_time: float = 300.0  # 5 minutes
    tolerance: float = 0.5  # Acceptable difference in %

    def __post_init__(self):
        if not 0 <= self.target_percentage <= 100:
            raise PowerwallValidationError(
                "target_percentage",
                self.target_percentage,
                "Must be between 0 and 100"
            )

        if self.max_wait_time <= 0:
            raise PowerwallValidationError(
                "max_wait_time",
                self.max_wait_time,
                "Must be positive"
            )


@dataclass
class ReserveChangeResult:
    """Result of a backup reserve change operation."""
    success: bool
    target_percentage: float
    actual_percentage: Optional[float] = None
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class ReserveValidator:
    """Validates backup reserve percentage changes."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def validate_percentage(self, percentage: float) -> bool:
        """
        Validate backup reserve percentage.

        Args:
            percentage: Percentage to validate (0-100)

        Returns:
            True if valid

        Raises:
            PowerwallValidationError: If percentage is invalid
        """
        if not isinstance(percentage, (int, float)):
            raise PowerwallValidationError(
                "percentage",
                percentage,
                "Must be a number"
            )

        if not 0 <= percentage <= 100:
            raise PowerwallValidationError(
                "percentage",
                percentage,
                "Must be between 0 and 100"
            )

        return True

    def validate_change_request(self, request: ReserveChangeRequest) -> bool:
        """
        Validate a reserve change request.

        Args:
            request: Change request to validate

        Returns:
            True if valid

        Raises:
            PowerwallValidationError: If request is invalid
        """
        # Validate target percentage
        self.validate_percentage(request.target_percentage)

        # Validate current percentage if provided
        if request.current_percentage is not None:
            self.validate_percentage(request.current_percentage)

        # Check if change is necessary
        if (request.current_percentage is not None and
            abs(request.target_percentage - request.current_percentage) < request.tolerance):
            self.logger.info(
                f"Change not necessary: current {request.current_percentage}% "
                f"is within tolerance of target {request.target_percentage}%"
            )

        # Validate scheduled time
        if request.scheduled_time and request.scheduled_time < datetime.now():
            raise PowerwallValidationError(
                "scheduled_time",
                request.scheduled_time,
                "Cannot schedule changes in the past"
            )

        return True

    def get_safe_percentage_range(self, current_percentage: float) -> tuple[float, float]:
        """
        Get safe percentage range for changes from current value.

        Args:
            current_percentage: Current backup reserve percentage

        Returns:
            Tuple of (min_safe, max_safe) percentages
        """
        # Generally safe to set reserve between 0-100%
        # But avoid extreme changes if battery is very low
        min_safe = 0.0
        max_safe = 100.0

        # If current is very low, suggest minimum reserve
        if current_percentage < 5:
            min_safe = 5.0

        return min_safe, max_safe

    def suggest_optimal_percentage(self,
                                 time_of_day: datetime,
                                 battery_level: Optional[float] = None) -> float:
        """
        Suggest optimal backup reserve percentage based on conditions.

        Args:
            time_of_day: Current time
            battery_level: Current battery level (optional)

        Returns:
            Suggested backup reserve percentage
        """
        hour = time_of_day.hour

        # Night hours (0:00 - 5:00): Higher reserve for backup
        if 0 <= hour < 5:
            suggested = 40.0
        # Early morning (5:00 - 8:00): Lower reserve to use stored energy
        elif 5 <= hour < 8:
            suggested = 0.0
        # Day hours (8:00 - 18:00): Moderate reserve
        elif 8 <= hour < 18:
            suggested = 20.0
        # Evening hours (18:00 - 24:00): Higher reserve for night
        else:
            suggested = 30.0

        # Adjust based on battery level if available
        if battery_level is not None:
            if battery_level < 20:
                # Low battery: increase reserve
                suggested = min(suggested + 10, 100)
            elif battery_level > 90:
                # High battery: can afford lower reserve
                suggested = max(suggested - 10, 0)

        return suggested


class ReserveScheduler:
    """Manages scheduled backup reserve changes."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self._scheduled_changes: List[ReserveChangeRequest] = []

    def add_scheduled_change(self, request: ReserveChangeRequest) -> None:
        """
        Add a scheduled reserve change.

        Args:
            request: Change request with scheduled_time set
        """
        if not request.scheduled_time:
            raise PowerwallValidationError(
                "scheduled_time",
                None,
                "Scheduled time is required"
            )

        # Validate the request
        validator = ReserveValidator()
        validator.validate_change_request(request)

        # Add to schedule
        self._scheduled_changes.append(request)
        self._scheduled_changes.sort(key=lambda x: x.scheduled_time)

        self.logger.info(
            f"Scheduled reserve change to {request.target_percentage}% "
            f"at {request.scheduled_time}"
        )

    def get_pending_changes(self, before_time: Optional[datetime] = None) -> List[ReserveChangeRequest]:
        """
        Get pending scheduled changes.

        Args:
            before_time: Only return changes scheduled before this time

        Returns:
            List of pending change requests
        """
        if before_time is None:
            before_time = datetime.now()

        return [
            change for change in self._scheduled_changes
            if change.scheduled_time <= before_time
        ]

    def remove_completed_change(self, request: ReserveChangeRequest) -> None:
        """Remove a completed change from the schedule."""
        if request in self._scheduled_changes:
            self._scheduled_changes.remove(request)

    def clear_schedule(self) -> None:
        """Clear all scheduled changes."""
        self._scheduled_changes.clear()
        self.logger.info("Cleared all scheduled reserve changes")

    def get_next_change(self) -> Optional[ReserveChangeRequest]:
        """Get the next scheduled change."""
        if not self._scheduled_changes:
            return None

        return self._scheduled_changes[0]


class ReserveHistory:
    """Tracks history of backup reserve changes."""

    def __init__(self, max_entries: int = 1000) -> None:
        self.max_entries = max_entries
        self._history: List[ReserveChangeResult] = []
        self.logger = logging.getLogger(__name__)

    def add_result(self, result: ReserveChangeResult) -> None:
        """Add a change result to history."""
        self._history.append(result)

        # Limit history size
        if len(self._history) > self.max_entries:
            self._history = self._history[-self.max_entries:]

        self.logger.debug(f"Added reserve change result to history: {result}")

    def get_recent_changes(self, hours: int = 24) -> List[ReserveChangeResult]:
        """
        Get reserve changes from the last N hours.

        Args:
            hours: Number of hours to look back

        Returns:
            List of recent change results
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)

        return [
            result for result in self._history
            if result.timestamp and result.timestamp >= cutoff_time
        ]

    def get_success_rate(self, hours: int = 24) -> float:
        """
        Get success rate of reserve changes in the last N hours.

        Args:
            hours: Number of hours to analyze

        Returns:
            Success rate as percentage (0-100)
        """
        recent_changes = self.get_recent_changes(hours)

        if not recent_changes:
            return 100.0  # No changes means 100% success rate

        successful = sum(1 for change in recent_changes if change.success)
        return (successful / len(recent_changes)) * 100

    def get_average_duration(self, hours: int = 24) -> Optional[float]:
        """
        Get average duration of reserve changes in the last N hours.

        Args:
            hours: Number of hours to analyze

        Returns:
            Average duration in seconds, or None if no data
        """
        recent_changes = self.get_recent_changes(hours)

        durations = [
            change.duration_seconds for change in recent_changes
            if change.success and change.duration_seconds is not None
        ]

        if not durations:
            return None

        return sum(durations) / len(durations)

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive history statistics."""
        total_changes = len(self._history)
        successful_changes = sum(1 for change in self._history if change.success)

        recent_24h = self.get_recent_changes(24)
        recent_success_rate = self.get_success_rate(24)
        avg_duration = self.get_average_duration(24)

        return {
            'total_changes': total_changes,
            'successful_changes': successful_changes,
            'overall_success_rate': (successful_changes / total_changes * 100) if total_changes > 0 else 100.0,
            'recent_24h_changes': len(recent_24h),
            'recent_24h_success_rate': recent_success_rate,
            'average_duration_seconds': avg_duration,
            'oldest_entry': self._history[0].timestamp if self._history else None,
            'newest_entry': self._history[-1].timestamp if self._history else None
        }