"""
Task definition classes for scheduled operations.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from enum import Enum

from ..models.task import ScheduledTask, TaskStatus, Destination
from ..models.summary import SummaryOptions
from src.utils.time import utc_now_naive


class TaskType(Enum):
    """Types of scheduled tasks."""
    SUMMARY = "summary"
    CLEANUP = "cleanup"
    EXPORT = "export"
    NOTIFICATION = "notification"


@dataclass
class SummaryTask:
    """Task for generating scheduled summaries."""

    scheduled_task: ScheduledTask
    channel_id: str  # Primary channel (backward compatibility)
    guild_id: str
    summary_options: SummaryOptions
    destinations: List[Destination] = field(default_factory=list)
    time_range_hours: int = 24  # How many hours back to summarize

    # Execution tracking
    status: TaskStatus = TaskStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0

    def get_all_channel_ids(self) -> List[str]:
        """Get all channels for this task (supports cross-channel summaries)."""
        return self.scheduled_task.get_all_channel_ids()

    def is_cross_channel(self) -> bool:
        """Check if this is a cross-channel summary."""
        return self.scheduled_task.is_cross_channel()

    def is_category_summary(self) -> bool:
        """Check if this is a category-based summary."""
        return self.scheduled_task.is_category_summary()

    def should_resolve_runtime(self) -> bool:
        """Check if category channels should be resolved at execution time."""
        return self.scheduled_task.should_resolve_runtime()

    def get_time_range(self) -> tuple[datetime, datetime]:
        """Get the time range for message fetching."""
        # Use timezone-aware datetimes to match Discord message timestamps
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=self.time_range_hours)
        return start_time, end_time

    def should_retry(self) -> bool:
        """Check if task should be retried after failure."""
        if self.status != TaskStatus.FAILED:
            return False

        max_retries = self.scheduled_task.max_failures
        return self.retry_count < max_retries

    def get_retry_delay(self) -> int:
        """Get delay in seconds before retry."""
        # Exponential backoff: 5min, 10min, 20min
        base_delay = self.scheduled_task.retry_delay_minutes
        return base_delay * 60 * (2 ** self.retry_count)

    def mark_started(self) -> None:
        """Mark task as started."""
        self.status = TaskStatus.RUNNING
        self.started_at = utc_now_naive()

    def mark_completed(self) -> None:
        """Mark task as completed successfully."""
        self.status = TaskStatus.COMPLETED
        self.completed_at = utc_now_naive()
        self.scheduled_task.mark_run_completed()

    def mark_failed(self, error: str) -> None:
        """Mark task as failed."""
        self.status = TaskStatus.FAILED
        self.completed_at = utc_now_naive()
        self.error_message = error
        self.retry_count += 1
        self.scheduled_task.mark_run_failed()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for persistence."""
        return {
            "type": TaskType.SUMMARY.value,
            "task_id": self.scheduled_task.id,
            "channel_id": self.channel_id,
            "guild_id": self.guild_id,
            "time_range_hours": self.time_range_hours,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "destinations": [
                {
                    "type": dest.type.value,
                    "target": dest.target,
                    "format": dest.format,
                    "enabled": dest.enabled
                }
                for dest in self.destinations
            ],
            "summary_options": {
                "summary_length": self.summary_options.summary_length.value,
                "claude_model": self.summary_options.summarization_model,
                "temperature": self.summary_options.temperature,
                "max_tokens": self.summary_options.max_tokens,
                "include_bots": self.summary_options.include_bots,
                "include_attachments": self.summary_options.include_attachments,
                "min_messages": self.summary_options.min_messages,
            }
        }

    def get_execution_summary(self) -> str:
        """Get human-readable execution summary."""
        if self.status == TaskStatus.PENDING:
            return f"⏳ Pending - Scheduled for channel {self.channel_id}"

        if self.status == TaskStatus.RUNNING:
            elapsed = (utc_now_naive() - self.started_at).total_seconds() if self.started_at else 0
            return f"🔄 Running for {elapsed:.1f}s"

        if self.status == TaskStatus.COMPLETED:
            duration = (self.completed_at - self.started_at).total_seconds() if self.started_at and self.completed_at else 0
            return f"✅ Completed in {duration:.1f}s - Delivered to {len(self.destinations)} destination(s)"

        if self.status == TaskStatus.FAILED:
            return f"❌ Failed (attempt {self.retry_count}): {self.error_message}"

        return f"Unknown status: {self.status.value}"


@dataclass
class CleanupTask:
    """Task for cleaning up old summaries and data."""

    task_id: str
    guild_id: Optional[str] = None  # None = all guilds
    retention_days: int = 90
    delete_summaries: bool = True
    delete_logs: bool = True
    delete_cached_data: bool = True

    # Execution tracking
    status: TaskStatus = TaskStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    items_deleted: int = 0
    error_message: Optional[str] = None

    def get_cutoff_date(self) -> datetime:
        """Get the cutoff date for deletion."""
        return utc_now_naive() - timedelta(days=self.retention_days)

    def mark_started(self) -> None:
        """Mark task as started."""
        self.status = TaskStatus.RUNNING
        self.started_at = utc_now_naive()

    def mark_completed(self, items_deleted: int) -> None:
        """Mark task as completed successfully."""
        self.status = TaskStatus.COMPLETED
        self.completed_at = utc_now_naive()
        self.items_deleted = items_deleted

    def mark_failed(self, error: str) -> None:
        """Mark task as failed."""
        self.status = TaskStatus.FAILED
        self.completed_at = utc_now_naive()
        self.error_message = error

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for persistence."""
        return {
            "type": TaskType.CLEANUP.value,
            "task_id": self.task_id,
            "guild_id": self.guild_id,
            "retention_days": self.retention_days,
            "delete_summaries": self.delete_summaries,
            "delete_logs": self.delete_logs,
            "delete_cached_data": self.delete_cached_data,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "items_deleted": self.items_deleted,
            "error_message": self.error_message
        }

    def get_execution_summary(self) -> str:
        """Get human-readable execution summary."""
        if self.status == TaskStatus.PENDING:
            scope = f"guild {self.guild_id}" if self.guild_id else "all guilds"
            return f"⏳ Pending - Will clean data older than {self.retention_days} days in {scope}"

        if self.status == TaskStatus.RUNNING:
            elapsed = (utc_now_naive() - self.started_at).total_seconds() if self.started_at else 0
            return f"🔄 Running cleanup for {elapsed:.1f}s"

        if self.status == TaskStatus.COMPLETED:
            duration = (self.completed_at - self.started_at).total_seconds() if self.started_at and self.completed_at else 0
            return f"✅ Completed in {duration:.1f}s - Deleted {self.items_deleted} items"

        if self.status == TaskStatus.FAILED:
            return f"❌ Failed: {self.error_message}"

        return f"Unknown status: {self.status.value}"


@dataclass
class TaskMetadata:
    """Metadata for task execution tracking."""

    task_id: str
    task_type: TaskType
    created_at: datetime
    last_executed: Optional[datetime] = None
    next_execution: Optional[datetime] = None
    execution_count: int = 0
    failure_count: int = 0
    average_duration_seconds: float = 0.0

    def update_execution(self, duration_seconds: float, failed: bool = False) -> None:
        """Update execution statistics."""
        self.last_executed = utc_now_naive()
        self.execution_count += 1

        if failed:
            self.failure_count += 1
        else:
            # Update running average duration
            self.average_duration_seconds = (
                (self.average_duration_seconds * (self.execution_count - 1) + duration_seconds)
                / self.execution_count
            )

    def get_success_rate(self) -> float:
        """Get task success rate as percentage."""
        if self.execution_count == 0:
            return 0.0

        success_count = self.execution_count - self.failure_count
        return (success_count / self.execution_count) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "created_at": self.created_at.isoformat(),
            "last_executed": self.last_executed.isoformat() if self.last_executed else None,
            "next_execution": self.next_execution.isoformat() if self.next_execution else None,
            "execution_count": self.execution_count,
            "failure_count": self.failure_count,
            "average_duration_seconds": self.average_duration_seconds,
            "success_rate": self.get_success_rate()
        }
