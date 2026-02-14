"""
Backfill analysis and execution for retrospective summarization.

Phase 7: Backfill Analysis - Execution component
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .models import (
    ArchiveSource,
    PeriodInfo,
    SummaryStatistics,
    GenerationInfo,
    SummaryStatus,
    CostEntry,
)
from .scanner import ArchiveScanner, ScanResult, GapInfo
from .writer import SummaryWriter
from .locking import LockManager
from .cost_tracker import CostTracker

logger = logging.getLogger(__name__)


class BackfillStatus(Enum):
    """Status of a backfill job."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BackfillProgress:
    """Progress information for a backfill job."""
    total_periods: int
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    current_period: Optional[str] = None
    cost_usd: float = 0.0
    tokens_input: int = 0
    tokens_output: int = 0

    @property
    def percent_complete(self) -> float:
        if self.total_periods == 0:
            return 100.0
        return (self.completed + self.failed + self.skipped) / self.total_periods * 100


@dataclass
class BackfillJob:
    """A backfill job configuration."""
    job_id: str
    source: ArchiveSource
    dates: List[date]
    status: BackfillStatus = BackfillStatus.PENDING
    progress: BackfillProgress = field(default_factory=lambda: BackfillProgress(0))
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    max_cost_usd: Optional[float] = None
    dry_run: bool = False
    regenerate_existing: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "source_key": self.source.source_key,
            "status": self.status.value,
            "progress": {
                "total_periods": self.progress.total_periods,
                "completed": self.progress.completed,
                "failed": self.progress.failed,
                "skipped": self.progress.skipped,
                "current_period": self.progress.current_period,
                "percent_complete": self.progress.percent_complete,
                "cost_usd": self.progress.cost_usd,
            },
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


@dataclass
class BackfillReport:
    """Report of backfill potential for a source."""
    source: ArchiveSource
    scan_result: ScanResult
    backfill_dates: List[date]
    estimated_cost_usd: float
    estimated_tokens: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_key": self.source.source_key,
            "scan": self.scan_result.to_dict(),
            "backfill_dates": [d.isoformat() for d in self.backfill_dates],
            "estimated_cost_usd": round(self.estimated_cost_usd, 4),
            "estimated_tokens": self.estimated_tokens,
            "period_count": len(self.backfill_dates),
        }


# Type for message fetcher callback
MessageFetcher = Callable[[ArchiveSource, datetime, datetime], List[Dict[str, Any]]]
# Type for summarizer callback
Summarizer = Callable[[List[Dict[str, Any]], ArchiveSource], Dict[str, Any]]


class BackfillManager:
    """
    Manages backfill analysis and execution.

    Coordinates gap detection, cost estimation, and summary generation
    for retrospective backfill.
    """

    def __init__(
        self,
        archive_root: Path,
        cost_tracker: CostTracker,
        message_fetcher: Optional[MessageFetcher] = None,
        summarizer: Optional[Summarizer] = None,
    ):
        """
        Initialize backfill manager.

        Args:
            archive_root: Root path of the archive
            cost_tracker: Cost tracker for estimates and recording
            message_fetcher: Callback to fetch messages for a period
            summarizer: Callback to generate summary from messages
        """
        self.archive_root = archive_root
        self.cost_tracker = cost_tracker
        self.message_fetcher = message_fetcher
        self.summarizer = summarizer
        self.scanner = ArchiveScanner(archive_root)
        self.writer = SummaryWriter(archive_root)
        self.lock_manager = LockManager()
        self._jobs: Dict[str, BackfillJob] = {}
        self._cancelled: set = set()

    def analyze_backfill(
        self,
        source: ArchiveSource,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        include_outdated: bool = False,
        current_prompt_version: Optional[str] = None,
        model: str = "anthropic/claude-3-haiku",
    ) -> BackfillReport:
        """
        Analyze backfill potential for a source.

        Args:
            source: Source to analyze
            start_date: Start of analysis range
            end_date: End of analysis range
            include_outdated: Include outdated summaries
            current_prompt_version: Current prompt version
            model: Model for cost estimation

        Returns:
            Backfill report with dates and cost estimate
        """
        # Scan the source
        scan_result = self.scanner.scan_source(
            source,
            start_date=start_date,
            end_date=end_date,
            current_prompt_version=current_prompt_version if include_outdated else None,
        )

        # Get backfill candidates
        backfill_dates = self.scanner.get_backfill_candidates(
            source,
            include_failed=True,
            include_outdated=include_outdated,
            current_prompt_version=current_prompt_version,
        )

        # Filter by date range
        if start_date:
            backfill_dates = [d for d in backfill_dates if d >= start_date]
        if end_date:
            backfill_dates = [d for d in backfill_dates if d <= end_date]

        # Estimate cost
        estimate = self.cost_tracker.estimate_backfill_cost(
            source_key=source.source_key,
            periods=len(backfill_dates),
            model=model,
        )

        return BackfillReport(
            source=source,
            scan_result=scan_result,
            backfill_dates=backfill_dates,
            estimated_cost_usd=estimate.estimated_cost_usd,
            estimated_tokens=estimate.avg_tokens_per_summary * len(backfill_dates),
        )

    async def create_backfill_job(
        self,
        source: ArchiveSource,
        dates: Optional[List[date]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        max_cost_usd: Optional[float] = None,
        dry_run: bool = False,
        regenerate_existing: bool = False,
    ) -> BackfillJob:
        """
        Create a new backfill job.

        Args:
            source: Source to backfill
            dates: Specific dates to backfill (optional)
            start_date: Start of range (used if dates not provided)
            end_date: End of range (used if dates not provided)
            max_cost_usd: Maximum cost limit
            dry_run: If True, only estimate without generating
            regenerate_existing: If True, regenerate existing summaries

        Returns:
            Created backfill job
        """
        job_id = f"bf_{uuid.uuid4().hex[:12]}"

        # Determine dates to backfill
        if dates:
            backfill_dates = sorted(dates)
        else:
            backfill_dates = self.scanner.get_backfill_candidates(
                source,
                include_failed=True,
                include_outdated=regenerate_existing,
            )
            if start_date:
                backfill_dates = [d for d in backfill_dates if d >= start_date]
            if end_date:
                backfill_dates = [d for d in backfill_dates if d <= end_date]

        job = BackfillJob(
            job_id=job_id,
            source=source,
            dates=backfill_dates,
            progress=BackfillProgress(total_periods=len(backfill_dates)),
            max_cost_usd=max_cost_usd,
            dry_run=dry_run,
            regenerate_existing=regenerate_existing,
        )

        self._jobs[job_id] = job
        logger.info(f"Created backfill job {job_id} with {len(backfill_dates)} periods")

        return job

    async def run_backfill_job(
        self,
        job_id: str,
        timezone: str = "UTC",
        prompt_version: str = "1.0.0",
        prompt_checksum: str = "sha256:unknown",
        model: str = "anthropic/claude-3-haiku",
    ) -> BackfillJob:
        """
        Execute a backfill job.

        Args:
            job_id: Job ID to execute
            timezone: Timezone for periods
            prompt_version: Prompt version for metadata
            prompt_checksum: Prompt checksum for metadata
            model: Model to use

        Returns:
            Updated job with results
        """
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        if not self.message_fetcher or not self.summarizer:
            raise ValueError("Message fetcher and summarizer must be configured")

        job.status = BackfillStatus.RUNNING
        job.started_at = datetime.utcnow()

        try:
            for target_date in job.dates:
                # Check for cancellation
                if job_id in self._cancelled:
                    job.status = BackfillStatus.CANCELLED
                    break

                # Check cost limit
                if job.max_cost_usd and job.progress.cost_usd >= job.max_cost_usd:
                    job.status = BackfillStatus.PAUSED
                    job.error = "Cost limit reached"
                    break

                job.progress.current_period = target_date.isoformat()

                try:
                    await self._backfill_date(
                        job=job,
                        target_date=target_date,
                        timezone=timezone,
                        prompt_version=prompt_version,
                        prompt_checksum=prompt_checksum,
                        model=model,
                    )
                    job.progress.completed += 1

                except Exception as e:
                    logger.error(f"Failed to backfill {target_date}: {e}")
                    job.progress.failed += 1

                # Small delay between generations
                await asyncio.sleep(0.5)

            if job.status == BackfillStatus.RUNNING:
                job.status = BackfillStatus.COMPLETED

        except Exception as e:
            job.status = BackfillStatus.FAILED
            job.error = str(e)
            logger.error(f"Backfill job {job_id} failed: {e}")

        finally:
            job.completed_at = datetime.utcnow()
            job.progress.current_period = None

        return job

    async def _backfill_date(
        self,
        job: BackfillJob,
        target_date: date,
        timezone: str,
        prompt_version: str,
        prompt_checksum: str,
        model: str,
    ) -> None:
        """Backfill a single date."""
        source = job.source

        # Create period for the day
        import pytz
        tz = pytz.timezone(timezone)
        start_dt = tz.localize(datetime.combine(target_date, datetime.min.time()))
        end_dt = tz.localize(datetime.combine(target_date, datetime.max.time().replace(microsecond=0)))

        period = PeriodInfo(
            start=start_dt,
            end=end_dt,
            timezone=timezone,
            duration_hours=24,
        )

        # Acquire lock
        meta_path = source.get_archive_path(self.archive_root) / str(target_date.year) / f"{target_date.month:02d}" / f"{target_date.isoformat()}_daily.meta.json"
        lock_job_id = await self.lock_manager.acquire_lock(meta_path, job.job_id)

        if not lock_job_id and not job.regenerate_existing:
            job.progress.skipped += 1
            return

        try:
            # Fetch messages
            start_time = datetime.now()
            messages = await asyncio.get_event_loop().run_in_executor(
                None,
                self.message_fetcher,
                source,
                start_dt,
                end_dt,
            )

            if not messages:
                # Write incomplete marker
                self.writer.write_incomplete_marker(
                    source=source,
                    period=period,
                    reason_code="NO_MESSAGES",
                    reason_message="No messages found in this period",
                    backfill_eligible=False,
                )
                return

            # Generate summary
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                self.summarizer,
                messages,
                source,
            )

            duration = (datetime.now() - start_time).total_seconds()

            # Calculate cost
            tokens_in = result.get("tokens_input", 0)
            tokens_out = result.get("tokens_output", 0)
            cost, pricing_version = self.cost_tracker.pricing.calculate_cost(
                model, tokens_in, tokens_out
            )

            # Update progress
            job.progress.cost_usd += cost
            job.progress.tokens_input += tokens_in
            job.progress.tokens_output += tokens_out

            # Create generation info
            generation = GenerationInfo(
                prompt_version=prompt_version,
                prompt_checksum=prompt_checksum,
                model=model,
                options=result.get("options", {}),
                duration_seconds=duration,
                tokens_input=tokens_in,
                tokens_output=tokens_out,
                cost_usd=cost,
                pricing_version=pricing_version,
                api_key_used="default",
            )

            # Create statistics
            stats = SummaryStatistics(
                message_count=len(messages),
                participant_count=len(set(m.get("author_id") for m in messages)),
            )

            # Write summary
            self.writer.write_summary(
                source=source,
                period=period,
                content=result.get("content", ""),
                statistics=stats,
                generation=generation,
                is_backfill=True,
                backfill_reason="historical_archive",
            )

            # Record cost
            self.cost_tracker.record_cost(CostEntry(
                source_key=source.source_key,
                summary_id=f"sum_{target_date.isoformat()}",
                timestamp=datetime.utcnow(),
                model=model,
                tokens_input=tokens_in,
                tokens_output=tokens_out,
                cost_usd=cost,
                pricing_version=pricing_version,
            ))

        finally:
            await self.lock_manager.release_lock(meta_path, SummaryStatus.COMPLETE)

    def get_job(self, job_id: str) -> Optional[BackfillJob]:
        """Get a backfill job by ID."""
        return self._jobs.get(job_id)

    def list_jobs(self) -> List[BackfillJob]:
        """List all backfill jobs."""
        return list(self._jobs.values())

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running backfill job."""
        if job_id in self._jobs:
            self._cancelled.add(job_id)
            return True
        return False
