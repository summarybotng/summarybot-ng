"""
Retrospective summary generator.

Generates summaries for arbitrary past time ranges with cost limits
and progress tracking. Implements ADR-006 Section 10.

Extended by ADR-008: Unified Summary Experience to save archive
summaries to the database alongside real-time summaries.

Phase 5: Retrospective Generation
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, AsyncIterator, TYPE_CHECKING

from src.utils.time import utc_now_naive
from src.logging.error_tracker import get_error_tracker
from src.models.error_log import ErrorType, ErrorSeverity
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
from .writer import SummaryWriter, summary_exists, summary_exists_in_db
from .api_keys import ApiKeyResolver

# ADR-008: Import for database storage
if TYPE_CHECKING:
    from ..data.base import StoredSummaryRepository

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """Status of a generation job."""
    # Note: Use PENDING (not QUEUED) to match SummaryJob model in database
    PENDING = "pending"
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
    status: JobStatus = JobStatus.PENDING
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
    force_regenerate: bool = False  # ADR-019: Delete existing and regenerate
    max_cost_usd: Optional[float] = None
    dry_run: bool = False
    # Summary options
    summary_type: str = "detailed"  # brief, detailed, comprehensive
    perspective: str = "general"  # general, developer, marketing, product, etc.
    # Weekly options
    schedule_days: Optional[List[int]] = None  # For weekly: which days to generate (0=Sun, 6=Sat)
    lookback_hours: Optional[int] = None  # How many hours to look back for each summary
    # ADR-096: Per-channel mode for weekly summaries
    per_channel: bool = False  # Generate one summary per channel instead of guild-wide
    min_channel_messages: int = 5  # Skip channels with fewer messages

    # Results
    summary_ids: List[str] = field(default_factory=list)  # IDs of created summaries

    def to_dict(self) -> Dict[str, Any]:
        start_date, end_date = self.date_range
        return {
            "job_id": self.job_id,
            "source_key": self.source.source_key,
            "status": self.status.value,
            "progress": {
                "total": self.progress.total_periods,
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
            # Job criteria for display
            "date_range": {
                "start": start_date.isoformat() if hasattr(start_date, 'isoformat') else str(start_date),
                "end": end_date.isoformat() if hasattr(end_date, 'isoformat') else str(end_date),
            },
            "granularity": self.granularity,
            "summary_type": self.summary_type,
            "perspective": self.perspective,
            "server_name": self.source.server_name,
            # Timestamps
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "pause_reason": self.pause_reason,
            "error": self.error,
            # Results
            "summary_ids": self.summary_ids,
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
        stored_summary_repository: Optional['StoredSummaryRepository'] = None,
        summary_job_repository: Optional[Any] = None,  # ADR-013
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
            stored_summary_repository: ADR-008 - Repository for saving to database
            summary_job_repository: ADR-013 - Repository for persistent job tracking
        """
        self.archive_root = archive_root
        self.summarization_service = summarization_service
        self.source_registry = source_registry
        self.cost_tracker = cost_tracker
        self.api_key_resolver = api_key_resolver
        self.lock_manager = lock_manager or LockManager()
        self.writer = SummaryWriter(archive_root)
        self.max_concurrent = max_concurrent
        self.stored_summary_repository = stored_summary_repository
        self.summary_job_repository = summary_job_repository  # ADR-013

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
        force_regenerate: bool = False,
        max_cost_usd: Optional[float] = None,
        dry_run: bool = False,
        summary_type: str = "detailed",
        perspective: str = "general",
        schedule_days: Optional[List[int]] = None,
        lookback_hours: Optional[int] = None,
        per_channel: bool = False,
        min_channel_messages: int = 5,
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
            schedule_days: For weekly granularity - which days to generate (0=Sun, 6=Sat)
            lookback_hours: How many hours to look back for each summary
            per_channel: ADR-096 - Generate one summary per channel instead of guild-wide
            min_channel_messages: Skip channels with fewer than this many messages

        Returns:
            Created job
        """
        job_id = f"job_{uuid.uuid4().hex[:12]}"

        # Calculate periods
        logger.info(
            f"Creating job {job_id}: start_date={start_date} (type={type(start_date).__name__}), "
            f"end_date={end_date} (type={type(end_date).__name__}), granularity={granularity}"
        )
        periods = list(self._generate_periods(start_date, end_date, granularity, schedule_days))
        logger.info(f"Job {job_id}: calculated {len(periods)} periods")

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
            force_regenerate=force_regenerate,
            max_cost_usd=max_cost_usd,
            dry_run=dry_run,
            summary_type=summary_type,
            perspective=perspective,
            schedule_days=schedule_days,
            lookback_hours=lookback_hours,
            per_channel=per_channel,
            min_channel_messages=min_channel_messages,
        )

        if max_cost_usd:
            job.cost.max_cost_usd = max_cost_usd

        self._jobs[job_id] = job
        logger.info(f"Created job {job_id} for {source.source_key}: {len(periods)} periods")

        # ADR-013: Persist job to database
        await self._persist_job(job)

        return job

    async def _persist_job(self, job: 'GenerationJob') -> None:
        """ADR-013: Save job to database for persistence across restarts."""
        if not self.summary_job_repository:
            return

        try:
            from ..models.summary_job import SummaryJob, JobType, JobStatus as DBJobStatus

            # Convert internal job to database model
            start_date, end_date = job.date_range

            # Build progress message with breakdown
            parts = []
            if job.progress.completed > 0:
                parts.append(f"{job.progress.completed} generated")
            if job.progress.skipped > 0:
                parts.append(f"{job.progress.skipped} skipped (already exist)")
            if job.progress.failed > 0:
                parts.append(f"{job.progress.failed} failed")
            progress_message = ", ".join(parts) if parts else "Starting..."

            db_job = SummaryJob(
                id=job.job_id,
                guild_id=job.source.server_id,
                job_type=JobType.RETROSPECTIVE,
                status=DBJobStatus(job.status.value),
                scope="guild",
                date_range_start=start_date,
                date_range_end=end_date,
                granularity=job.granularity,
                summary_type=job.summary_type,
                perspective=job.perspective,
                force_regenerate=job.force_regenerate,
                progress_current=job.progress.completed + job.progress.failed + job.progress.skipped,
                progress_total=job.progress.total_periods,
                progress_message=progress_message,
                current_period=job.progress.current_period,
                cost_usd=job.cost.cost_usd,
                tokens_input=job.cost.tokens_input,
                tokens_output=job.cost.tokens_output,
                summary_ids=job.summary_ids,  # Track created summaries
                error=job.error,
                pause_reason=job.pause_reason,
                created_at=job.created_at,
                started_at=job.started_at,
                completed_at=job.completed_at,
                source_key=job.source.source_key,
                server_name=job.source.server_name,
            )

            # Check if job exists
            existing = await self.summary_job_repository.get(job.job_id)
            if existing:
                await self.summary_job_repository.update(db_job)
            else:
                await self.summary_job_repository.save(db_job)

        except Exception as e:
            logger.warning(f"Failed to persist job {job.job_id} to database: {e}")

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
        job.started_at = utc_now_naive()
        await self._persist_job(job)  # ADR-013

        try:
            start_date, end_date = job.date_range
            periods = list(self._generate_periods(start_date, end_date, job.granularity, job.schedule_days))

            logger.info(f"Job {job_id}: per_channel={job.per_channel}, granularity={job.granularity}, periods={len(periods)}")

            # ADR-096: Per-channel mode - get channel list for iteration
            if job.per_channel:
                channels = await self._get_channels_for_job(job, message_fetcher)
                logger.info(f"Per-channel mode: {len(channels)} channels × {len(periods)} periods")
            else:
                channels = [None]  # Single iteration for guild-wide mode

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

                # ADR-096: Iterate over channels (or single None for guild-wide)
                for channel_info in channels:
                    if job.status in (JobStatus.CANCELLED, JobStatus.PAUSED):
                        break

                    # Create period-specific source for per-channel mode
                    if channel_info:
                        channel_id, channel_name = channel_info
                        period_source = ArchiveSource(
                            source_type=job.source.source_type,
                            server_id=job.source.server_id,
                            server_name=job.source.server_name,
                            channel_id=channel_id,
                            channel_name=channel_name,
                        )
                        job.progress.current_period = f"{period_start.isoformat()} #{channel_name}"
                    else:
                        period_source = job.source
                        job.progress.current_period = period_start.isoformat()

                    try:
                        result = await self._generate_period(
                            job=job,
                            period_start=period_start,
                            period_end=period_end,
                            message_fetcher=message_fetcher,
                            source_override=period_source if channel_info else None,
                        )

                        if result == "completed":
                            job.progress.completed += 1
                        elif result == "skipped":
                            job.progress.skipped += 1
                        elif result == "failed":
                            job.progress.failed += 1

                    except Exception as e:
                        logger.error(f"Error generating {period_start} {channel_info}: {e}")
                        job.progress.failed += 1

                    # Progress callback
                    if progress_callback:
                        await progress_callback(job)

                    # ADR-013: Persist progress periodically (every 5 periods)
                    if (job.progress.completed + job.progress.skipped + job.progress.failed) % 5 == 0:
                        await self._persist_job(job)

            # Mark complete if not paused/cancelled
            if job.status == JobStatus.RUNNING:
                job.status = JobStatus.COMPLETED
                job.completed_at = utc_now_naive()

                # Trigger sync if configured
                await self._trigger_sync(job)

            # ADR-013: Persist final state
            await self._persist_job(job)

        except Exception as e:
            job.status = JobStatus.FAILED
            job.error = str(e)
            job.completed_at = utc_now_naive()
            logger.error(f"Job {job_id} failed: {e}")
            await self._persist_job(job)  # ADR-013

        return job

    async def _get_channels_for_job(
        self,
        job: GenerationJob,
        message_fetcher: Callable,
    ) -> List[tuple]:
        """
        ADR-096: Get list of channels for per-channel mode.

        Returns list of (channel_id, channel_name) tuples.
        """
        import discord

        # Get channel info from Discord bot
        guild = None
        bot = None  # Initialize before try block so it's accessible in fallback
        channel_map = {}  # id -> channel object
        try:
            from src.dashboard.routes import get_discord_bot
            bot = get_discord_bot()
            logger.info(f"Channel lookup: bot={bot is not None}, bot.is_ready={bot.is_ready() if bot else 'N/A'}")
            if bot:
                guild = bot.get_guild(int(job.source.server_id))
                logger.info(f"Channel lookup: guild={guild.name if guild else 'NOT FOUND'} for server_id={job.source.server_id}")
                if guild:
                    # Include all text-based channels: text, news/announcement, forum, voice text, stage
                    # ADR-096 fix: Include all channel types that can have text messages
                    for ch in guild.channels:
                        # Check for common text channel types + any channel with name attribute
                        # This catches: TextChannel, NewsChannel (announcements), ForumChannel, VoiceChannel, StageChannel
                        if hasattr(ch, 'name') and hasattr(ch, 'id') and not isinstance(ch, discord.CategoryChannel):
                            channel_map[str(ch.id)] = ch
                    logger.info(f"Channel lookup: cached {len(channel_map)} channels from guild")
        except Exception as e:
            logger.warning(f"Failed to get channels from bot: {e}")

        # If source has explicit channel_ids, use those with looked-up names
        # ADR-096 fix: Use bot.get_or_fetch_channel() to fetch from API if not in cache
        if job.source.channel_ids:
            result = []
            for cid in job.source.channel_ids:
                if cid in channel_map:
                    # Found in cache
                    result.append((cid, channel_map[cid].name))
                else:
                    # Not in cache - try API fetch via bot's helper method
                    channel_name = f"channel-{cid[-4:]}"  # fallback
                    logger.info(f"Channel {cid} not in cache ({len(channel_map)} cached), attempting API fetch...")
                    try:
                        if bot and bot.is_ready():
                            channel = await bot.get_or_fetch_channel(int(cid))
                            if channel and hasattr(channel, 'name'):
                                channel_name = channel.name
                                logger.info(f"Fetched channel name via API: {cid} -> {channel_name}")
                            else:
                                logger.warning(f"Channel {cid} fetch returned: {type(channel).__name__ if channel else 'None'}")
                        else:
                            logger.warning(f"Bot not available/ready for channel fetch: {cid} (bot={bot is not None}, ready={bot.is_ready() if bot else 'N/A'})")
                    except Exception as e:
                        logger.warning(f"Failed to fetch channel {cid}: {type(e).__name__}: {e}")
                    result.append((cid, channel_name))
            return result

        # Otherwise, return all readable channels from bot (using channel_map which includes all types)
        if guild and channel_map:
            return [
                (str(ch.id), ch.name)
                for ch in channel_map.values()
                if hasattr(ch, 'permissions_for') and ch.permissions_for(guild.me).read_message_history
            ]

        return []

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
        source_override: Optional[ArchiveSource] = None,
    ) -> str:
        """Generate summary for a single period.

        Args:
            job: The generation job
            period_start: Start date of the period
            period_end: End date of the period
            message_fetcher: Callable to fetch messages
            source_override: ADR-096 - Override source for per-channel mode
        """
        # ADR-096: Use override source for per-channel mode
        source = source_override or job.source
        logger.info(f"Processing period {period_start} for {source.source_key} (skip_existing={job.skip_existing}, force_regenerate={job.force_regenerate})")

        # Track whether we should force lock acquisition (when DB says summary doesn't exist)
        force_lock_acquire = False

        # ADR-019: force_regenerate deletes existing and regenerates
        if job.force_regenerate:
            await self._delete_existing(source, period_start)
            force_lock_acquire = True  # After deletion, force lock acquisition
        # ADR-019: Check database for existing summary (not disk)
        elif job.skip_existing:
            exists = await summary_exists_in_db(source, period_start)
            logger.info(f"Period {period_start}: summary_exists_in_db returned {exists}")
            if exists:
                return "skipped"
            else:
                # Database says it doesn't exist, so any disk files are stale
                # Force lock acquisition to override "complete" status on disk
                force_lock_acquire = True

        # Create period info with UTC timezone-aware datetimes
        from datetime import timezone as tz

        # Determine lookback hours:
        # 1. Use job.lookback_hours if explicitly set
        # 2. Default based on granularity: 24h for daily, 168h for weekly, 720h for monthly
        if job.lookback_hours:
            duration_hours = job.lookback_hours
        elif job.granularity == "daily":
            duration_hours = 24
        elif job.granularity == "weekly":
            duration_hours = 168
        else:
            duration_hours = 720

        # Calculate actual time range for message fetching
        # End time is end of period_end day
        end_time = datetime.combine(period_end, datetime.max.time().replace(microsecond=0), tzinfo=tz.utc)
        # Start time: look back duration_hours from end_time
        # This is critical for weekly summaries where period_start == period_end
        start_time = end_time - timedelta(hours=duration_hours)

        logger.info(f"Period {period_start}: fetching {duration_hours}h from {start_time} to {end_time}")

        period = PeriodInfo(
            start=start_time,
            end=end_time,
            timezone=job.timezone,
            duration_hours=duration_hours,
        )

        # Acquire lock
        meta_path = self._get_meta_path(source, period_start)
        logger.info(f"Period {period_start}: attempting lock at {meta_path} (force={force_lock_acquire})")
        lock_job_id = await self.lock_manager.acquire_lock(meta_path, job.job_id, force_acquire=force_lock_acquire)
        if not lock_job_id:
            logger.info(f"Period {period_start}: FAILED to acquire lock - skipping")
            return "skipped"
        logger.info(f"Period {period_start}: lock acquired, proceeding")

        try:
            # Dry run - just estimate
            if job.dry_run:
                estimate = self.cost_tracker.estimate_backfill_cost(
                    source.source_key, 1
                )
                job.cost.cost_usd += estimate.estimated_cost_usd
                return "completed"

            # Fetch messages
            messages = await message_fetcher(
                source,
                period.start,
                period.end,
            )

            # ADR-096: Skip channels with too few messages in per-channel mode
            if not messages or (source_override and len(messages) < job.min_channel_messages):
                if source_override:
                    logger.info(f"Period {period_start}: skipping {source.channel_name} ({len(messages) if messages else 0} messages < {job.min_channel_messages})")
                    return "skipped"
                # No messages - write incomplete marker
                self.writer.write_incomplete_marker(
                    source=source,
                    period=period,
                    reason_code="NO_MESSAGES",
                    reason_message="No messages found in this period",
                    backfill_eligible=False,
                )
                await self.lock_manager.release_lock(meta_path, SummaryStatus.INCOMPLETE)
                return "completed"

            # Get API key for this source
            manifest = self.source_registry.get_manifest(source.source_key)
            resolved_key = await self.api_key_resolver.get_key_for_source(
                source.source_key,
                manifest.to_dict() if manifest else None,
            )

            # Pre-emptive budget check: estimate cost BEFORE making API call
            # This prevents exceeding budget by checking if estimated cost fits
            if job.max_cost_usd:
                # Estimate cost based on message count (avg ~10 tokens per message)
                estimated_tokens = len(messages) * 10 + 500  # +500 for prompt overhead
                estimated_cost, _ = self.cost_tracker.pricing.calculate_cost(
                    model="anthropic/claude-3-haiku",  # Use cheapest model for estimate
                    tokens_input=estimated_tokens,
                    tokens_output=int(estimated_tokens * 0.2),
                )
                remaining_budget = job.max_cost_usd - job.cost.cost_usd
                if estimated_cost > remaining_budget:
                    logger.warning(
                        f"Budget enforcement: estimated ${estimated_cost:.4f} > remaining ${remaining_budget:.4f}. "
                        f"Pausing job {job.job_id} before API call."
                    )
                    job.status = JobStatus.PAUSED
                    job.pause_reason = "budget_exceeded"
                    await self.lock_manager.release_lock(meta_path, SummaryStatus.INCOMPLETE)
                    return "skipped"

            # Generate summary
            # ADR-014: Pass guild_id for jump link generation in references
            start_time = utc_now_naive()
            summary_result = await self.summarization_service.generate_summary(
                messages=messages,
                api_key=resolved_key.key,
                summary_type=job.summary_type,
                perspective=job.perspective,
                guild_id=source.server_id or "",
            )
            duration = (utc_now_naive() - start_time).total_seconds()

            # Calculate cost
            cost, pricing_version = self.cost_tracker.pricing.calculate_cost(
                model=summary_result.model,
                tokens_input=summary_result.tokens_input,
                tokens_output=summary_result.tokens_output,
            )

            # Record cost
            cost_entry = CostEntry(
                source_key=source.source_key,
                summary_id=f"sum_{uuid.uuid4().hex[:12]}",
                timestamp=utc_now_naive(),
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
                options={
                    "summary_type": job.summary_type,
                    "perspective": job.perspective,
                },
                duration_seconds=duration,
                tokens_input=summary_result.tokens_input,
                tokens_output=summary_result.tokens_output,
                cost_usd=cost,
                pricing_version=pricing_version,
                api_key_used=resolved_key.api_key_used,
            )

            # Generate summary ID
            summary_id = f"sum_{uuid.uuid4().hex[:12]}"

            self.writer.write_summary(
                source=source,
                period=period,
                content=summary_result.content,
                statistics=statistics,
                generation=generation,
                is_backfill=True,
                backfill_reason="historical_archive",
                summary_id=summary_id,
            )

            # ADR-008: Save to database for unified access
            if self.stored_summary_repository:
                await self._save_to_database(
                    job=job,
                    period=period,
                    summary_result=summary_result,
                    statistics=statistics,
                    generation=generation,
                    summary_id=summary_id,
                    source_override=source,
                )

            # Track created summary ID for job reporting
            job.summary_ids.append(summary_id)

            await self.lock_manager.release_lock(meta_path, SummaryStatus.COMPLETE)
            return "completed"

        except Exception as e:
            logger.error(f"Error generating summary for {period_start}: {e}")
            await self.lock_manager.release_lock(meta_path, SummaryStatus.INCOMPLETE)

            # Log to error tracker for dashboard visibility
            try:
                tracker = get_error_tracker()
                await tracker.capture_error(
                    error=e,
                    error_type=ErrorType.SUMMARIZATION_ERROR,
                    severity=ErrorSeverity.ERROR,
                    guild_id=source.server_id,
                    operation=f"Archive retrospective: {period_start}",
                    details={
                        "job_id": job.job_id,
                        "period": str(period_start),
                        "source_key": source.source_key,
                        "granularity": job.granularity,
                        "channel_id": source.channel_id,
                    },
                )
            except Exception as track_err:
                logger.warning(f"Failed to track error: {track_err}")

            return "failed"

    async def _save_to_database(
        self,
        job: GenerationJob,
        period: PeriodInfo,
        summary_result: Any,  # SummaryResult from summarization service
        statistics: SummaryStatistics,
        generation: GenerationInfo,
        summary_id: str,
        source_override: Optional[ArchiveSource] = None,
    ) -> None:
        """
        ADR-008: Save archive summary to database for unified access.

        This enables archive summaries to appear in the Summaries page
        alongside real-time summaries, with consistent features like
        Push to Channel and View Generation Details.

        ADR-026: For non-Discord sources (WhatsApp, Slack, etc.), store
        summaries under the PRIMARY_GUILD_ID so they appear in the main
        guild's summaries view. The original source is preserved in
        archive_source_key for attribution.
        """
        from ..models.stored_summary import StoredSummary, SummarySource
        from ..models.summary import SummaryResult
        import os

        # ADR-096: Use override source for per-channel mode
        source = source_override or job.source

        try:
            # ADR-026: Determine guild_id for storage
            # - Discord: use server_id directly (it's the guild_id)
            # - Slack: use server_id (which is the linked Discord guild_id from workspace)
            # - WhatsApp/other: use PRIMARY_GUILD_ID to appear in main guild view
            if source.source_type in (SourceType.DISCORD, SourceType.SLACK):
                storage_guild_id = source.server_id or ""
            else:
                storage_guild_id = os.environ.get("PRIMARY_GUILD_ID", source.server_id or "")
            # Build a SummaryResult object if we have raw content
            if hasattr(summary_result, 'to_summary_result'):
                db_summary_result = summary_result.to_summary_result()
            elif isinstance(summary_result, SummaryResult):
                db_summary_result = summary_result
            else:
                # Create minimal SummaryResult from available data
                # ADR-004: Preserve reference_index for grounded citations
                # ADR-016: Preserve source_content for regeneration fallback
                db_summary_result = SummaryResult(
                    id=summary_id,
                    guild_id=storage_guild_id,  # ADR-026: Use storage_guild_id
                    channel_id=source.channel_id or "",
                    start_time=period.start,
                    end_time=period.end,
                    message_count=statistics.message_count,
                    summary_text=summary_result.content if hasattr(summary_result, 'content') else str(summary_result),
                    key_points=getattr(summary_result, 'key_points', []),
                    action_items=getattr(summary_result, 'action_items', []),
                    participants=getattr(summary_result, 'participants', []),
                    technical_terms=getattr(summary_result, 'technical_terms', []),
                    # ADR-004: Copy reference_index for grounded citations display
                    reference_index=getattr(summary_result, 'reference_index', []),
                    # ADR-016: Copy source_content for regeneration fallback
                    source_content=getattr(summary_result, 'source_content', None),
                    prompt_system=getattr(summary_result, 'prompt_system', None),
                    prompt_user=getattr(summary_result, 'prompt_user', None),
                    metadata={
                        "summary_type": job.summary_type,
                        "perspective": job.perspective,
                        "model": generation.model,
                        "prompt_version": generation.prompt_version,
                        "prompt_checksum": generation.prompt_checksum,
                        "tokens_input": generation.tokens_input,
                        "tokens_output": generation.tokens_output,
                        "cost_usd": generation.cost_usd,
                        "duration_seconds": generation.duration_seconds,
                        # ADR-004: Track grounding status
                        "grounded": len(getattr(summary_result, 'reference_index', [])) > 0,
                        # ADR-024: Preserve generation_attempts for retry tracking
                        **({"generation_attempts": getattr(summary_result, 'metadata', {}).get('generation_attempts')}
                           if getattr(summary_result, 'metadata', {}).get('generation_attempts') else {}),
                    },
                )

            # ADR-017: Build source_channel_ids from all available channel info
            source_channel_ids = []
            if source.channel_ids:
                # Multiple channels (GUILD/CATEGORY scope)
                source_channel_ids = source.channel_ids
            elif source.channel_id:
                # Single channel (CHANNEL scope)
                source_channel_ids = [source.channel_id]

            # Create StoredSummary with archive source
            # ADR-026: Use storage_guild_id so WhatsApp summaries appear under primary guild
            stored = StoredSummary(
                id=summary_id,
                guild_id=storage_guild_id,
                source_channel_ids=source_channel_ids,
                summary_result=db_summary_result,
                title=f"{source.channel_name or source.server_name} - {period.start.strftime('%Y-%m-%d')}",
                # ADR-008: Archive-specific metadata
                source=SummarySource.ARCHIVE,
                archive_period=period.start.strftime('%Y-%m-%d'),
                archive_granularity=job.granularity,
                archive_source_key=source.source_key,
            )

            await self.stored_summary_repository.save(stored)
            logger.debug(f"Saved archive summary to database: {summary_id}")

        except Exception as e:
            # Log but don't fail the job - file was already written
            logger.warning(f"Failed to save archive summary to database: {e}")

    def _generate_periods(
        self,
        start_date: date,
        end_date: date,
        granularity: str,
        schedule_days: Optional[List[int]] = None,
    ) -> AsyncIterator[tuple]:
        """Generate period tuples for the date range.

        Args:
            start_date: Start date of the range
            end_date: End date of the range
            granularity: "daily", "weekly", or "monthly"
            schedule_days: For weekly granularity - which days to generate (0=Sun, 6=Sat in JS format)
        """
        current = start_date

        while current <= end_date:
            if granularity == "daily":
                period_end = current
                yield (current, period_end)
                current += timedelta(days=1)

            elif granularity == "weekly":
                # If schedule_days is specified, yield each matching day in range
                # schedule_days uses 0=Sun, 6=Sat format (JavaScript style)
                if schedule_days:
                    # Convert Python weekday to JS weekday format
                    # Python: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
                    # JS: 0=Sun, 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat
                    js_weekday = (current.weekday() + 1) % 7
                    if js_weekday in schedule_days:
                        yield (current, current)
                    current += timedelta(days=1)
                else:
                    # Original behavior: Monday to Sunday periods
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

    async def _delete_existing(self, source: ArchiveSource, target_date: date) -> None:
        """
        ADR-019: Delete existing summary from both database and disk.

        Called when force_regenerate is True to ensure clean regeneration.
        """
        from .writer import delete_summary_file

        # Delete from database - match on source_key to only delete for this specific source
        try:
            if self.stored_summary_repository:
                # Use direct query to match on archive_source_key
                query = """
                SELECT id FROM stored_summaries
                WHERE guild_id = ?
                  AND archive_period = ?
                  AND archive_source_key = ?
                """
                rows = await self.stored_summary_repository.connection.fetch_all(
                    query,
                    (source.server_id, target_date.isoformat(), source.source_key)
                )
                for row in rows:
                    await self.stored_summary_repository.delete(row['id'])
                    logger.info(f"Deleted existing summary from DB: {row['id']}")
        except Exception as e:
            logger.warning(f"Failed to delete from DB: {e}")

        # Delete from disk
        if delete_summary_file(self.archive_root, source, target_date):
            logger.info(f"Deleted existing summary file for {target_date}")

    def get_job(self, job_id: str) -> Optional[GenerationJob]:
        """Get a job by ID (checks memory first, then database)."""
        # Check in-memory first
        if job_id in self._jobs:
            return self._jobs[job_id]
        return None

    async def get_job_from_db(self, job_id: str) -> Optional[Dict[str, Any]]:
        """ADR-013: Get job from database (for jobs from previous sessions)."""
        if not self.summary_job_repository:
            return None
        try:
            db_job = await self.summary_job_repository.get(job_id)
            if db_job:
                return db_job.to_dict()
        except Exception as e:
            logger.warning(f"Failed to get job {job_id} from database: {e}")
        return None

    async def restore_job_from_db(self, job_id: str) -> Optional[GenerationJob]:
        """Restore a GenerationJob from database after server restart.

        This allows resuming jobs that were paused when the server restarted.
        """
        if not self.summary_job_repository:
            logger.warning("Cannot restore job: no summary_job_repository")
            return None

        try:
            db_job = await self.summary_job_repository.get(job_id)
            if not db_job:
                return None

            # Only restore retrospective jobs
            if db_job.job_type.value != "retrospective":
                logger.warning(f"Cannot restore non-retrospective job: {db_job.job_type}")
                return None

            # Reconstruct ArchiveSource
            source = ArchiveSource(
                source_type=SourceType.DISCORD,  # TODO: support other types
                server_id=db_job.guild_id,
                server_name=db_job.server_name or db_job.guild_id,
                channel_id=db_job.channel_ids[0] if db_job.channel_ids else None,
            )

            # Create GenerationJob with restored state
            job = GenerationJob(
                job_id=job_id,
                source=source,
                date_range=(db_job.date_range_start, db_job.date_range_end),
                granularity=db_job.granularity or "daily",
                timezone=db_job.metadata.get("timezone", "UTC") if db_job.metadata else "UTC",
                status=JobStatus.PAUSED,  # Keep as paused until explicitly resumed
                progress=GenerationProgress(
                    total_periods=db_job.progress_total,
                    completed=db_job.progress_current,
                ),
                cost=CostProgress(
                    cost_usd=db_job.cost_usd,
                    tokens_input=db_job.tokens_input,
                    tokens_output=db_job.tokens_output,
                ),
                summary_type=db_job.summary_type,
                perspective=db_job.perspective,
                force_regenerate=db_job.force_regenerate,
                pause_reason=db_job.pause_reason,
                summary_ids=db_job.summary_ids or [],
            )

            # Add to in-memory jobs
            self._jobs[job_id] = job
            logger.info(f"Restored job {job_id} from database (progress: {job.progress.completed}/{job.progress.total_periods})")

            return job

        except Exception as e:
            logger.error(f"Failed to restore job {job_id} from database: {e}")
            return None

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

        if job.status in (JobStatus.RUNNING, JobStatus.PENDING, JobStatus.PAUSED):
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
