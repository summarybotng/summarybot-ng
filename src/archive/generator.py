"""
Retrospective summary generator.

Generates summaries for arbitrary past time ranges with cost limits
and progress tracking. Implements ADR-006 Section 10.

Phase 5: Retrospective Generation
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, AsyncIterator

from .models import (
    SourceType,
    ArchiveSource,
    PeriodInfo,
    SummaryMetadata,
    SummaryStatistics,
    GenerationInfo,
    SummaryStatus,
    CostEntry,
)
from .sources import SourceRegistry
from .cost_tracker import CostTracker, PricingTable
from .locking import LockManager
from .writer import SummaryWriter, summary_exists
from .api_keys import ApiKeyResolver

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """Status of a generation job."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


@dataclass
class GenerationProgress:
    """Progress information for a generation job."""
    total_periods: int
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    current_period: Optional[str] = None
    estimated_remaining_seconds: Optional[int] = None

    @property
    def percent_complete(self) -> float:
        if self.total_periods == 0:
            return 100.0
        return (self.completed + self.failed + self.skipped) / self.total_periods * 100


@dataclass
class CostProgress:
    """Cost progress for a generation job."""
    cost_usd: float = 0.0
    tokens_input: int = 0
    tokens_output: int = 0
    max_cost_usd: Optional[float] = None
    budget_remaining_usd: Optional[float] = None

    @property
    def percent_of_max(self) -> Optional[float]:
        if self.max_cost_usd is None or self.max_cost_usd == 0:
            return None
        return self.cost_usd / self.max_cost_usd * 100


@dataclass
class GenerationJob:
    """A retrospective generation job."""
    job_id: str
    source: ArchiveSource
    date_range: tuple  # (start_date, end_date)
    granularity: str  # "daily", "weekly", "monthly"
    timezone: str
    status: JobStatus = JobStatus.QUEUED
    progress: GenerationProgress = field(default_factory=lambda: GenerationProgress(0))
    cost: CostProgress = field(default_factory=CostProgress)
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    pause_reason: Optional[str] = None
    error: Optional[str] = None

    # Options
    skip_existing: bool = True
    regenerate_outdated: bool = False
    regenerate_failed: bool = True
    max_cost_usd: Optional[float] = None
    dry_run: bool = False
    # Summary options
    summary_type: str = "detailed"  # brief, detailed, comprehensive
    perspective: str = "general"  # general, developer, marketing, product, etc.

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
            },
            "cost": {
                "cost_usd": self.cost.cost_usd,
                "tokens_input": self.cost.tokens_input,
                "tokens_output": self.cost.tokens_output,
                "max_cost_usd": self.cost.max_cost_usd,
                "percent_of_max": self.cost.percent_of_max,
            },
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "pause_reason": self.pause_reason,
            "error": self.error,
        }


class RetrospectiveGenerator:
    """
    Generates retrospective summaries for past time ranges.

    Handles batch generation with cost limits, progress tracking,
    and pause/resume capability.
    """

    def __init__(
        self,
        archive_root: Path,
        summarization_service: Any,  # SummarizationService
        source_registry: SourceRegistry,
        cost_tracker: CostTracker,
        api_key_resolver: ApiKeyResolver,
        lock_manager: Optional[LockManager] = None,
        max_concurrent: int = 3,
    ):
        """
        Initialize retrospective generator.

        Args:
            archive_root: Root path of the archive
            summarization_service: Service for generating summaries
            source_registry: Source registry
            cost_tracker: Cost tracker
            api_key_resolver: API key resolver
            lock_manager: Lock manager (created if not provided)
            max_concurrent: Maximum concurrent generations
        """
        self.archive_root = archive_root
        self.summarization_service = summarization_service
        self.source_registry = source_registry
        self.cost_tracker = cost_tracker
        self.api_key_resolver = api_key_resolver
        self.lock_manager = lock_manager or LockManager()
        self.writer = SummaryWriter(archive_root)
        self.max_concurrent = max_concurrent

        self._jobs: Dict[str, GenerationJob] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def create_job(
        self,
        source: ArchiveSource,
        start_date: date,
        end_date: date,
        granularity: str = "daily",
        timezone: str = "UTC",
        skip_existing: bool = True,
        regenerate_outdated: bool = False,
        regenerate_failed: bool = True,
        max_cost_usd: Optional[float] = None,
        dry_run: bool = False,
        summary_type: str = "detailed",
        perspective: str = "general",
    ) -> GenerationJob:
        """
        Create a new generation job.

        Args:
            source: Source to generate for
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)
            granularity: "daily", "weekly", or "monthly"
            timezone: Timezone for summaries
            skip_existing: Skip if summary already exists
            regenerate_outdated: Regenerate if prompt changed
            regenerate_failed: Retry failed summaries
            max_cost_usd: Maximum cost limit
            dry_run: Estimate cost without generating
            summary_type: Type of summary (brief, detailed, comprehensive)
            perspective: Perspective/audience (general, developer, etc.)

        Returns:
            Created job
        """
        job_id = f"job_{uuid.uuid4().hex[:12]}"

        # Calculate periods
        periods = list(self._generate_periods(start_date, end_date, granularity))

        job = GenerationJob(
            job_id=job_id,
            source=source,
            date_range=(start_date, end_date),
            granularity=granularity,
            timezone=timezone,
            progress=GenerationProgress(total_periods=len(periods)),
            skip_existing=skip_existing,
            regenerate_outdated=regenerate_outdated,
            regenerate_failed=regenerate_failed,
            max_cost_usd=max_cost_usd,
            dry_run=dry_run,
            summary_type=summary_type,
            perspective=perspective,
        )

        if max_cost_usd:
            job.cost.max_cost_usd = max_cost_usd

        self._jobs[job_id] = job
        logger.info(f"Created job {job_id} for {source.source_key}: {len(periods)} periods")

        return job

    async def run_job(
        self,
        job_id: str,
        message_fetcher: Callable,
        progress_callback: Optional[Callable] = None,
    ) -> GenerationJob:
        """
        Run a generation job.

        Args:
            job_id: Job ID to run
            message_fetcher: Async callable to fetch messages for a period
            progress_callback: Optional callback for progress updates

        Returns:
            Completed job
        """
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()

        try:
            start_date, end_date = job.date_range
            periods = list(self._generate_periods(start_date, end_date, job.granularity))

            for period_start, period_end in periods:
                # Check for cancellation/pause
                if job.status == JobStatus.CANCELLED:
                    break
                if job.status == JobStatus.PAUSED:
                    break

                # Check cost limit
                if job.max_cost_usd and job.cost.cost_usd >= job.max_cost_usd:
                    job.status = JobStatus.PAUSED
                    job.pause_reason = "budget_exceeded"
                    logger.warning(f"Job {job_id} paused: budget exceeded")
                    break

                job.progress.current_period = period_start.isoformat()

                try:
                    result = await self._generate_period(
                        job=job,
                        period_start=period_start,
                        period_end=period_end,
                        message_fetcher=message_fetcher,
                    )

                    if result == "completed":
                        job.progress.completed += 1
                    elif result == "skipped":
                        job.progress.skipped += 1
                    elif result == "failed":
                        job.progress.failed += 1

                except Exception as e:
                    logger.error(f"Error generating {period_start}: {e}")
                    job.progress.failed += 1

                # Progress callback
                if progress_callback:
                    await progress_callback(job)

            # Mark complete if not paused/cancelled
            if job.status == JobStatus.RUNNING:
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.utcnow()

                # Trigger sync if configured
                await self._trigger_sync(job)

        except Exception as e:
            job.status = JobStatus.FAILED
            job.error = str(e)
            logger.error(f"Job {job_id} failed: {e}")

        return job

    async def _trigger_sync(self, job: GenerationJob) -> None:
        """Trigger Google Drive sync after job completion."""
        try:
            from .sync import get_sync_service

            sync_service = get_sync_service(self.archive_root)
            if not sync_service.is_enabled():
                logger.debug("Sync not enabled, skipping")
                return

            if not sync_service.config.sync_on_generation:
                logger.debug("Sync on generation disabled, skipping")
                return

            # Get source path
            source_path = job.source.get_archive_path(self.archive_root).parent

            logger.info(f"Triggering sync for {job.source.source_key}")
            result = await sync_service.sync_source(
                source_key=job.source.source_key,
                source_path=source_path,
                server_name=job.source.server_name,
            )
            logger.info(
                f"Sync completed: status={result.status.value}, "
                f"files={result.files_synced}"
            )

        except Exception as e:
            # Don't fail the job if sync fails
            logger.warning(f"Sync failed for {job.source.source_key}: {e}")

    async def _generate_period(
        self,
        job: GenerationJob,
        period_start: date,
        period_end: date,
        message_fetcher: Callable,
    ) -> str:
        """Generate summary for a single period."""

        # Check if summary exists
        if job.skip_existing and summary_exists(self.archive_root, job.source, period_start):
            logger.debug(f"Skipping existing: {period_start}")
            return "skipped"

        # Create period info with UTC timezone-aware datetimes
        from datetime import timezone as tz
        period = PeriodInfo(
            start=datetime.combine(period_start, datetime.min.time(), tzinfo=tz.utc),
            end=datetime.combine(period_end, datetime.max.time().replace(microsecond=0), tzinfo=tz.utc),
            timezone=job.timezone,
            duration_hours=24 if job.granularity == "daily" else 168 if job.granularity == "weekly" else 720,
        )

        # Acquire lock
        meta_path = self._get_meta_path(job.source, period_start)
        lock_job_id = await self.lock_manager.acquire_lock(meta_path, job.job_id)
        if not lock_job_id:
            logger.debug(f"Could not acquire lock for {period_start}")
            return "skipped"

        try:
            # Dry run - just estimate
            if job.dry_run:
                estimate = self.cost_tracker.estimate_backfill_cost(
                    job.source.source_key, 1
                )
                job.cost.cost_usd += estimate.estimated_cost_usd
                return "completed"

            # Fetch messages
            messages = await message_fetcher(
                job.source,
                period.start,
                period.end,
            )

            if not messages:
                # No messages - write incomplete marker
                self.writer.write_incomplete_marker(
                    source=job.source,
                    period=period,
                    reason_code="NO_MESSAGES",
                    reason_message="No messages found in this period",
                    backfill_eligible=False,
                )
                await self.lock_manager.release_lock(meta_path, SummaryStatus.INCOMPLETE)
                return "completed"

            # Get API key for this source
            manifest = self.source_registry.get_manifest(job.source.source_key)
            resolved_key = await self.api_key_resolver.get_key_for_source(
                job.source.source_key,
                manifest.to_dict() if manifest else None,
            )

            # Generate summary
            start_time = datetime.utcnow()
            summary_result = await self.summarization_service.generate_summary(
                messages=messages,
                api_key=resolved_key.key,
                summary_type=job.summary_type,
                perspective=job.perspective,
            )
            duration = (datetime.utcnow() - start_time).total_seconds()

            # Calculate cost
            cost, pricing_version = self.cost_tracker.pricing.calculate_cost(
                model=summary_result.model,
                tokens_input=summary_result.tokens_input,
                tokens_output=summary_result.tokens_output,
            )

            # Record cost
            cost_entry = CostEntry(
                source_key=job.source.source_key,
                summary_id=f"sum_{uuid.uuid4().hex[:12]}",
                timestamp=datetime.utcnow(),
                model=summary_result.model,
                tokens_input=summary_result.tokens_input,
                tokens_output=summary_result.tokens_output,
                cost_usd=cost,
                pricing_version=pricing_version,
                api_key_source=resolved_key.source,
            )
            self.cost_tracker.record_cost(cost_entry)

            # Update job cost
            job.cost.cost_usd += cost
            job.cost.tokens_input += summary_result.tokens_input
            job.cost.tokens_output += summary_result.tokens_output

            # Write summary
            statistics = SummaryStatistics(
                message_count=len(messages),
                participant_count=len(set(m.get("author_id") for m in messages)),
                word_count=sum(len(m.get("content", "").split()) for m in messages),
            )

            generation = GenerationInfo(
                prompt_version=summary_result.prompt_version,
                prompt_checksum=summary_result.prompt_checksum,
                model=summary_result.model,
                options={},
                duration_seconds=duration,
                tokens_input=summary_result.tokens_input,
                tokens_output=summary_result.tokens_output,
                cost_usd=cost,
                pricing_version=pricing_version,
                api_key_used=resolved_key.api_key_used,
            )

            self.writer.write_summary(
                source=job.source,
                period=period,
                content=summary_result.content,
                statistics=statistics,
                generation=generation,
                is_backfill=True,
                backfill_reason="historical_archive",
            )

            await self.lock_manager.release_lock(meta_path, SummaryStatus.COMPLETE)
            return "completed"

        except Exception as e:
            logger.error(f"Error generating summary for {period_start}: {e}")
            await self.lock_manager.release_lock(meta_path, SummaryStatus.INCOMPLETE)
            return "failed"

    def _generate_periods(
        self,
        start_date: date,
        end_date: date,
        granularity: str,
    ) -> AsyncIterator[tuple]:
        """Generate period tuples for the date range."""
        current = start_date

        while current <= end_date:
            if granularity == "daily":
                period_end = current
                yield (current, period_end)
                current += timedelta(days=1)

            elif granularity == "weekly":
                # Start on Monday
                days_until_sunday = 6 - current.weekday()
                period_end = min(current + timedelta(days=days_until_sunday), end_date)
                yield (current, period_end)
                current = period_end + timedelta(days=1)

            elif granularity == "monthly":
                # End of month
                if current.month == 12:
                    next_month = date(current.year + 1, 1, 1)
                else:
                    next_month = date(current.year, current.month + 1, 1)
                period_end = min(next_month - timedelta(days=1), end_date)
                yield (current, period_end)
                current = next_month

            else:
                raise ValueError(f"Unknown granularity: {granularity}")

    def _get_meta_path(self, source: ArchiveSource, target_date: date) -> Path:
        """Get metadata path for a date."""
        summary_dir = source.get_archive_path(self.archive_root)
        return summary_dir / str(target_date.year) / f"{target_date.month:02d}" / f"{target_date.isoformat()}_daily.meta.json"

    def get_job(self, job_id: str) -> Optional[GenerationJob]:
        """Get a job by ID."""
        return self._jobs.get(job_id)

    def list_jobs(self, status: Optional[JobStatus] = None) -> List[GenerationJob]:
        """List jobs, optionally filtered by status."""
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status == status]
        return jobs

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job."""
        job = self._jobs.get(job_id)
        if not job:
            return False

        if job.status in (JobStatus.RUNNING, JobStatus.QUEUED, JobStatus.PAUSED):
            job.status = JobStatus.CANCELLED
            logger.info(f"Cancelled job {job_id}")
            return True

        return False

    async def pause_job(self, job_id: str, reason: str = "user_requested") -> bool:
        """Pause a running job."""
        job = self._jobs.get(job_id)
        if not job:
            return False

        if job.status == JobStatus.RUNNING:
            job.status = JobStatus.PAUSED
            job.pause_reason = reason
            logger.info(f"Paused job {job_id}: {reason}")
            return True

        return False

    async def resume_job(
        self,
        job_id: str,
        message_fetcher: Callable,
        progress_callback: Optional[Callable] = None,
    ) -> Optional[GenerationJob]:
        """Resume a paused job."""
        job = self._jobs.get(job_id)
        if not job or job.status != JobStatus.PAUSED:
            return None

        job.pause_reason = None
        return await self.run_job(job_id, message_fetcher, progress_callback)
