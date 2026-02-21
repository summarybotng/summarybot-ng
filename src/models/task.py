"""
Task and scheduling models.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from enum import Enum

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore

from .base import BaseModel, generate_id
from .summary import SummaryOptions


def _get_timezone(tz_name: str) -> Any:
    """Get a timezone object from name, with fallback to UTC."""
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return timezone.utc


def _localize_time(dt: datetime, tz_name: str) -> datetime:
    """Create a timezone-aware datetime in the specified timezone."""
    tz = _get_timezone(tz_name)
    if dt.tzinfo is None:
        # Naive datetime - treat as local time in the target timezone
        return dt.replace(tzinfo=tz)
    else:
        # Already timezone-aware - convert to target timezone
        return dt.astimezone(tz)


def _to_utc(dt: datetime) -> datetime:
    """Convert a timezone-aware datetime to UTC."""
    if dt.tzinfo is None:
        # Assume UTC if naive
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SCHEDULED = "scheduled"


class TaskType(Enum):
    """Type of task."""
    SUMMARY = "summary"
    CLEANUP = "cleanup"
    MAINTENANCE = "maintenance"
    BACKUP = "backup"


class ScheduleType(Enum):
    """Types of scheduling."""
    ONCE = "once"
    FIFTEEN_MINUTES = "fifteen-minutes"  # Every 15 minutes
    HOURLY = "hourly"  # Every hour
    EVERY_4_HOURS = "every-4-hours"  # Every 4 hours
    DAILY = "daily"
    WEEKLY = "weekly"
    HALF_WEEKLY = "half-weekly"  # Specific days of the week
    MONTHLY = "monthly"
    CUSTOM = "custom"


class DestinationType(Enum):
    """Types of delivery destinations."""
    DISCORD_CHANNEL = "discord_channel"
    WEBHOOK = "webhook"
    EMAIL = "email"
    FILE = "file"
    DASHBOARD = "dashboard"  # ADR-005: Store in dashboard for viewing/manual push


@dataclass
class Destination(BaseModel):
    """Delivery destination for scheduled summaries."""
    type: DestinationType
    target: str  # Channel ID, webhook URL, email address, file path, or "default" for dashboard
    format: str = "embed"  # embed, markdown, json
    enabled: bool = True
    # ADR-005: Dashboard-specific options
    auto_archive_days: Optional[int] = None  # Auto-archive after N days
    notify_on_delivery: bool = False  # Send notification when summary is ready

    def to_display_string(self) -> str:
        """Get human-readable destination string."""
        type_names = {
            DestinationType.DISCORD_CHANNEL: "Discord Channel",
            DestinationType.WEBHOOK: "Webhook",
            DestinationType.EMAIL: "Email",
            DestinationType.FILE: "File",
            DestinationType.DASHBOARD: "Dashboard"
        }

        status = "✅" if self.enabled else "❌"
        type_name = type_names.get(self.type, self.type.value)
        if self.type == DestinationType.DASHBOARD:
            return f"{status} {type_name} ({self.format})"
        return f"{status} {type_name}: {self.target} ({self.format})"


@dataclass
class ScheduledTask(BaseModel):
    """A scheduled summarization task."""
    id: str = field(default_factory=generate_id)
    name: str = ""
    channel_id: str = ""  # Primary channel (backward compatibility)
    channel_ids: List[str] = field(default_factory=list)  # Multiple channels for cross-channel summaries
    guild_id: str = ""
    task_type: TaskType = TaskType.SUMMARY
    schedule_type: ScheduleType = ScheduleType.DAILY
    schedule_time: Optional[str] = None  # Time in HH:MM format
    schedule_days: List[int] = field(default_factory=list)  # Days of week (0=Monday)
    cron_expression: Optional[str] = None  # For custom scheduling
    destinations: List[Destination] = field(default_factory=list)
    summary_options: SummaryOptions = field(default_factory=SummaryOptions)
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: str = ""  # User ID who created the task
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    failure_count: int = 0
    max_failures: int = 3
    retry_delay_minutes: int = 5

    # Timezone support
    timezone: str = "UTC"  # Timezone for schedule times (e.g., "America/New_York")

    # Category support
    category_id: Optional[str] = None  # Discord category ID for category-based summaries
    excluded_channel_ids: List[str] = field(default_factory=list)  # Channels to exclude from category
    category_mode: str = "combined"  # "combined" (one summary) or "individual" (per-channel summaries)
    resolve_category_at_runtime: bool = False  # Resolve category channels at execution time vs creation time
    
    def calculate_next_run(self, from_time: Optional[datetime] = None) -> Optional[datetime]:
        """Calculate the next run time for this task.

        The schedule_time is interpreted in the task's timezone, and the
        returned next_run is always in UTC for consistent storage/comparison.
        """
        if not self.is_active:
            return None

        # Get current time in UTC
        utc_now = from_time or datetime.now(timezone.utc)
        if utc_now.tzinfo is None:
            utc_now = utc_now.replace(tzinfo=timezone.utc)

        # Convert to task's timezone for schedule calculations
        task_tz = _get_timezone(self.timezone)
        local_now = utc_now.astimezone(task_tz)

        if self.schedule_type == ScheduleType.ONCE:
            # One-time tasks don't have a next run after completion
            return None if self.last_run else utc_now

        if self.schedule_type == ScheduleType.DAILY:
            # Build the next run time in the task's timezone
            next_run_local = local_now.replace(second=0, microsecond=0)

            if self.schedule_time:
                try:
                    hour, minute = map(int, self.schedule_time.split(':'))
                    next_run_local = next_run_local.replace(hour=hour, minute=minute)

                    # If the time has passed today (in local timezone), schedule for tomorrow
                    if next_run_local <= local_now:
                        next_run_local += timedelta(days=1)
                except ValueError:
                    # Invalid time format, use current time + 1 day
                    next_run_local += timedelta(days=1)
            else:
                # No specific time, run daily at the same time as now
                next_run_local += timedelta(days=1)

            # Convert back to UTC for storage
            return _to_utc(next_run_local)

        if self.schedule_type == ScheduleType.WEEKLY:
            next_run_local = local_now.replace(second=0, microsecond=0)

            if self.schedule_time:
                try:
                    hour, minute = map(int, self.schedule_time.split(':'))
                    next_run_local = next_run_local.replace(hour=hour, minute=minute)
                except ValueError:
                    pass

            # Find next scheduled day
            current_weekday = local_now.weekday()  # 0=Monday
            scheduled_days = self.schedule_days or [current_weekday]

            days_ahead = None
            for day in sorted(scheduled_days):
                if day > current_weekday or (day == current_weekday and next_run_local > local_now):
                    days_ahead = day - current_weekday
                    break

            if days_ahead is None:
                # Next occurrence is next week
                days_ahead = (7 - current_weekday) + min(scheduled_days)

            next_run_local += timedelta(days=days_ahead)
            return _to_utc(next_run_local)
        
        if self.schedule_type == ScheduleType.MONTHLY:
            # Simple monthly scheduling - same day of month
            # Use local time for calculations
            next_run_local = local_now.replace(second=0, microsecond=0, day=1)

            if self.schedule_time:
                try:
                    hour, minute = map(int, self.schedule_time.split(':'))
                    next_run_local = next_run_local.replace(hour=hour, minute=minute)
                except ValueError:
                    pass

            # Try to use the same day of month as the original creation
            target_day = self.created_at.day

            # Add one month
            if next_run_local.month == 12:
                next_run_local = next_run_local.replace(year=next_run_local.year + 1, month=1)
            else:
                next_run_local = next_run_local.replace(month=next_run_local.month + 1)

            # Adjust for day of month
            try:
                next_run_local = next_run_local.replace(day=target_day)
            except ValueError:
                # Day doesn't exist in this month (e.g., Feb 31)
                # Use last day of month
                if next_run_local.month == 12:
                    next_run_local = next_run_local.replace(year=next_run_local.year + 1, month=1, day=1) - timedelta(days=1)
                else:
                    next_run_local = next_run_local.replace(month=next_run_local.month + 1, day=1) - timedelta(days=1)

            return _to_utc(next_run_local)
        
        # CUSTOM type would use cron_expression (not implemented here)
        return None
    
    def should_run_now(self, current_time: Optional[datetime] = None) -> bool:
        """Check if task should run now."""
        if not self.is_active:
            return False

        if not self.next_run:
            self.next_run = self.calculate_next_run(current_time)

        if not self.next_run:
            return False

        current_time = current_time or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        next_run = self.next_run
        if next_run.tzinfo is None:
            next_run = next_run.replace(tzinfo=timezone.utc)

        return current_time >= next_run
    
    def mark_run_started(self) -> None:
        """Mark that a run has started."""
        self.last_run = datetime.utcnow()
        self.run_count += 1
    
    def mark_run_completed(self) -> None:
        """Mark that a run completed successfully."""
        self.next_run = self.calculate_next_run()
        self.failure_count = 0  # Reset failure count on success
    
    def mark_run_failed(self) -> None:
        """Mark that a run failed."""
        self.failure_count += 1

        # Disable task if too many failures
        if self.failure_count >= self.max_failures:
            self.is_active = False
        else:
            # Schedule retry
            retry_time = datetime.utcnow() + timedelta(minutes=self.retry_delay_minutes)
            self.next_run = retry_time

    def get_all_channel_ids(self) -> List[str]:
        """Get all channels for this task (supports both single and multi-channel)."""
        if self.channel_ids:
            return self.channel_ids
        elif self.channel_id:
            return [self.channel_id]
        else:
            return []

    def is_cross_channel(self) -> bool:
        """Check if this is a cross-channel summary task."""
        return len(self.get_all_channel_ids()) > 1

    def is_category_summary(self) -> bool:
        """Check if this is a category-based summary."""
        return self.category_id is not None

    def should_resolve_runtime(self) -> bool:
        """Check if category channels should be resolved at execution time."""
        return self.is_category_summary() and self.resolve_category_at_runtime

    def get_filtered_channel_ids(self, all_channel_ids: List[str]) -> List[str]:
        """Get channel IDs with exclusions applied.

        Args:
            all_channel_ids: Full list of channel IDs

        Returns:
            Filtered list of channel IDs with exclusions removed
        """
        return [cid for cid in all_channel_ids if cid not in self.excluded_channel_ids]
    
    def get_schedule_description(self) -> str:
        """Get human-readable schedule description."""
        if self.schedule_type == ScheduleType.ONCE:
            return "One time"
        
        if self.schedule_type == ScheduleType.DAILY:
            time_part = f" at {self.schedule_time}" if self.schedule_time else ""
            return f"Daily{time_part}"
        
        if self.schedule_type == ScheduleType.WEEKLY:
            day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            if self.schedule_days:
                days = ", ".join([day_names[d] for d in sorted(self.schedule_days)])
            else:
                days = "Weekly"
            time_part = f" at {self.schedule_time}" if self.schedule_time else ""
            return f"{days}{time_part}"

        if self.schedule_type == ScheduleType.HALF_WEEKLY:
            day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            if self.schedule_days:
                days = ", ".join([day_names[d] for d in sorted(self.schedule_days)])
                time_part = f" at {self.schedule_time}" if self.schedule_time else ""
                return f"{days}{time_part}"
            else:
                return "Half-weekly (days not specified)"

        if self.schedule_type == ScheduleType.MONTHLY:
            day_part = f" on day {self.created_at.day}"
            time_part = f" at {self.schedule_time}" if self.schedule_time else ""
            return f"Monthly{day_part}{time_part}"
        
        if self.schedule_type == ScheduleType.CUSTOM:
            return f"Custom: {self.cron_expression}"
        
        return "Unknown schedule"
    
    def to_status_dict(self) -> Dict[str, Any]:
        """Get status information for display."""
        return {
            "id": self.id,
            "name": self.name,
            "schedule": self.get_schedule_description(),
            "is_active": self.is_active,
            "run_count": self.run_count,
            "failure_count": self.failure_count,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "destinations": [dest.to_display_string() for dest in self.destinations],
            "created_at": self.created_at,
            "created_by": self.created_by
        }


@dataclass
class SummaryTask(ScheduledTask):
    """Convenience class for summary tasks (alias for ScheduledTask with SUMMARY type)."""

    def __post_init__(self):
        """Ensure task type is set to SUMMARY."""
        self.task_type = TaskType.SUMMARY


@dataclass
class TaskResult(BaseModel):
    """Result of a task execution."""
    task_id: str
    execution_id: str = field(default_factory=generate_id)
    status: TaskStatus = TaskStatus.PENDING
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    summary_id: Optional[str] = None
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    delivery_results: List[Dict[str, Any]] = field(default_factory=list)
    execution_time_seconds: Optional[float] = None
    
    def mark_completed(self, summary_id: str) -> None:
        """Mark task as completed successfully."""
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.summary_id = summary_id
        self.execution_time_seconds = (self.completed_at - self.started_at).total_seconds()
    
    def mark_failed(self, error: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Mark task as failed."""
        self.status = TaskStatus.FAILED
        self.completed_at = datetime.utcnow()
        self.error_message = error
        self.error_details = details
        self.execution_time_seconds = (self.completed_at - self.started_at).total_seconds()
    
    def add_delivery_result(self, destination_type: str, target: str, success: bool, 
                          message: Optional[str] = None) -> None:
        """Add a delivery result."""
        self.delivery_results.append({
            "destination_type": destination_type,
            "target": target,
            "success": success,
            "message": message,
            "timestamp": datetime.utcnow()
        })
    
    def get_summary_text(self) -> str:
        """Get summary text for the execution result."""
        if self.status == TaskStatus.COMPLETED:
            success_count = sum(1 for result in self.delivery_results if result["success"])
            total_deliveries = len(self.delivery_results)
            return f"✅ Completed in {self.execution_time_seconds:.1f}s, {success_count}/{total_deliveries} deliveries successful"
        
        if self.status == TaskStatus.FAILED:
            return f"❌ Failed after {self.execution_time_seconds:.1f}s: {self.error_message}"
        
        if self.status == TaskStatus.RUNNING:
            elapsed = (datetime.utcnow() - self.started_at).total_seconds()
            return f"🔄 Running for {elapsed:.1f}s"
        
        return f"⏳ {self.status.value.title()}"