"""
Summary Job model for unified job tracking.

ADR-013: Unified Job Tracking
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional
import json
from src.utils.time import utc_now_naive


class JobType(Enum):
    """Type of summary generation job."""
    MANUAL = "manual"           # Generate button in UI
    SCHEDULED = "scheduled"     # Scheduled task
    RETROSPECTIVE = "retrospective"  # Archive backfill
    REGENERATE = "regenerate"   # Regenerate existing summary


class JobStatus(Enum):
    """Status of a summary generation job."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


@dataclass
class SummaryJob:
    """
    Unified job tracking for all summary generation types.

    Replaces:
    - _generation_tasks dict in summaries.py
    - _jobs dict in generator.py
    - Task scheduler internal state
    """
    id: str
    guild_id: str
    job_type: JobType
    status: JobStatus = JobStatus.PENDING

    # Job configuration
    scope: Optional[str] = None  # 'channel', 'category', 'guild'
    channel_ids: List[str] = field(default_factory=list)
    category_id: Optional[str] = None
    schedule_id: Optional[str] = None

    # Time range for summary
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None

    # Retrospective-specific
    date_range_start: Optional[date] = None
    date_range_end: Optional[date] = None
    granularity: Optional[str] = None  # 'daily', 'weekly', 'monthly'
    summary_type: str = "detailed"
    perspective: str = "general"
    force_regenerate: bool = False

    # Progress tracking
    progress_current: int = 0
    progress_total: int = 1
    progress_message: Optional[str] = None
    current_period: Optional[str] = None

    # Cost tracking
    cost_usd: float = 0.0
    tokens_input: int = 0
    tokens_output: int = 0

    # Results
    summary_id: Optional[str] = None
    summary_ids: List[str] = field(default_factory=list)
    error: Optional[str] = None
    pause_reason: Optional[str] = None

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Metadata
    created_by: Optional[str] = None
    source_key: Optional[str] = None
    server_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def percent_complete(self) -> float:
        """Calculate completion percentage."""
        if self.progress_total == 0:
            return 100.0 if self.status == JobStatus.COMPLETED else 0.0
        return (self.progress_current / self.progress_total) * 100

    @property
    def is_active(self) -> bool:
        """Check if job is still running."""
        return self.status in (JobStatus.PENDING, JobStatus.RUNNING)

    @property
    def can_cancel(self) -> bool:
        """Check if job can be cancelled."""
        return self.status in (JobStatus.PENDING, JobStatus.RUNNING, JobStatus.PAUSED)

    @property
    def can_retry(self) -> bool:
        """Check if job can be retried."""
        return self.status == JobStatus.FAILED

    def start(self) -> None:
        """Mark job as started."""
        self.status = JobStatus.RUNNING
        self.started_at = utc_now_naive()

    def complete(self, summary_id: Optional[str] = None) -> None:
        """Mark job as completed."""
        self.status = JobStatus.COMPLETED
        self.completed_at = utc_now_naive()
        if summary_id:
            self.summary_id = summary_id

    def fail(self, error: str) -> None:
        """Mark job as failed."""
        self.status = JobStatus.FAILED
        self.completed_at = utc_now_naive()
        self.error = error

    def cancel(self) -> None:
        """Mark job as cancelled."""
        self.status = JobStatus.CANCELLED
        self.completed_at = utc_now_naive()

    def pause(self, reason: str = "user_requested") -> None:
        """Mark job as paused."""
        self.status = JobStatus.PAUSED
        self.pause_reason = reason

    def resume(self) -> None:
        """Resume a paused job."""
        self.status = JobStatus.RUNNING
        self.pause_reason = None

    def update_progress(
        self,
        current: int,
        total: Optional[int] = None,
        message: Optional[str] = None,
        current_period: Optional[str] = None,
    ) -> None:
        """Update progress tracking."""
        self.progress_current = current
        if total is not None:
            self.progress_total = total
        if message is not None:
            self.progress_message = message
        if current_period is not None:
            self.current_period = current_period

    def add_cost(self, cost_usd: float, tokens_in: int, tokens_out: int) -> None:
        """Add cost and token usage."""
        self.cost_usd += cost_usd
        self.tokens_input += tokens_in
        self.tokens_output += tokens_out

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "job_id": self.id,
            "guild_id": self.guild_id,
            "job_type": self.job_type.value,
            "status": self.status.value,
            "scope": self.scope,
            "channel_ids": self.channel_ids,
            "category_id": self.category_id,
            "schedule_id": self.schedule_id,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "date_range": {
                "start": self.date_range_start.isoformat() if self.date_range_start else None,
                "end": self.date_range_end.isoformat() if self.date_range_end else None,
            } if self.date_range_start or self.date_range_end else None,
            "granularity": self.granularity,
            "summary_type": self.summary_type,
            "perspective": self.perspective,
            "progress": {
                "current": self.progress_current,
                "total": self.progress_total,
                "percent": self.percent_complete,
                "message": self.progress_message,
                "current_period": self.current_period,
            },
            "cost": {
                "cost_usd": self.cost_usd,
                "tokens_input": self.tokens_input,
                "tokens_output": self.tokens_output,
            },
            "summary_id": self.summary_id,
            "summary_ids": self.summary_ids if self.summary_ids else None,
            "error": self.error,
            "pause_reason": self.pause_reason,
            "source_key": self.source_key,
            "server_name": self.server_name,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SummaryJob":
        """Create from dictionary (database row)."""
        # Parse channel_ids from JSON
        channel_ids = data.get("channel_ids")
        if isinstance(channel_ids, str):
            channel_ids = json.loads(channel_ids) if channel_ids else []

        # Parse summary_ids from JSON
        summary_ids = data.get("summary_ids")
        if isinstance(summary_ids, str):
            summary_ids = json.loads(summary_ids) if summary_ids else []

        # Parse metadata from JSON
        metadata = data.get("metadata")
        if isinstance(metadata, str):
            metadata = json.loads(metadata) if metadata else {}

        # Parse timestamps
        def parse_dt(val):
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            return datetime.fromisoformat(val.replace("Z", "+00:00"))

        def parse_date(val):
            if val is None:
                return None
            if isinstance(val, date):
                return val
            if isinstance(val, str):
                return date.fromisoformat(val)
            return val

        return cls(
            id=data["id"],
            guild_id=data["guild_id"],
            job_type=JobType(data["job_type"]),
            status=JobStatus(data.get("status", "pending")),
            scope=data.get("scope"),
            channel_ids=channel_ids or [],
            category_id=data.get("category_id"),
            schedule_id=data.get("schedule_id"),
            period_start=parse_dt(data.get("period_start")),
            period_end=parse_dt(data.get("period_end")),
            date_range_start=parse_date(data.get("date_range_start")),
            date_range_end=parse_date(data.get("date_range_end")),
            granularity=data.get("granularity"),
            summary_type=data.get("summary_type", "detailed"),
            perspective=data.get("perspective", "general"),
            force_regenerate=bool(data.get("force_regenerate", False)),
            progress_current=data.get("progress_current", 0),
            progress_total=data.get("progress_total", 1),
            progress_message=data.get("progress_message"),
            current_period=data.get("current_period"),
            cost_usd=data.get("cost_usd", 0.0),
            tokens_input=data.get("tokens_input", 0),
            tokens_output=data.get("tokens_output", 0),
            summary_id=data.get("summary_id"),
            summary_ids=summary_ids or [],
            error=data.get("error"),
            pause_reason=data.get("pause_reason"),
            created_at=parse_dt(data.get("created_at")) or utc_now_naive(),
            started_at=parse_dt(data.get("started_at")),
            completed_at=parse_dt(data.get("completed_at")),
            created_by=data.get("created_by"),
            source_key=data.get("source_key"),
            server_name=data.get("server_name"),
            metadata=metadata or {},
        )
