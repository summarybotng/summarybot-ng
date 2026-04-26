"""
Wiki Backfill Executor (ADR-068).

Processes existing summaries that haven't been ingested into the wiki,
with rate limiting, priority yielding, and resource monitoring.
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Any

from ..models.summary_job import SummaryJob, JobType, JobStatus
from ..models.stored_summary import StoredSummary
from ..data.sqlite.wiki_repository import SQLiteWikiRepository
from ..data.sqlite.stored_summary_repository import SQLiteStoredSummaryRepository
from ..data.sqlite.summary_job_repository import SQLiteSummaryJobRepository
from ..utils.time import utc_now_naive

logger = logging.getLogger(__name__)


@dataclass
class BackfillConfig:
    """Configuration for wiki backfill."""
    mode: str = "unprocessed"  # unprocessed, all, date_range
    batch_size: int = 10
    delay_between_batches: float = 1.0
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    # Adaptive rate control
    enable_priority_yielding: bool = True
    enable_resource_monitoring: bool = True
    cpu_threshold: float = 80.0
    memory_threshold: float = 85.0


@dataclass
class BackfillProgress:
    """Progress tracking for wiki backfill."""
    total_summaries: int = 0
    processed: int = 0
    ingested: int = 0
    skipped: int = 0
    failed: int = 0
    current_summary_id: Optional[str] = None
    current_summary_title: Optional[str] = None
    errors: List[dict] = field(default_factory=list)


class WikiBackfillExecutor:
    """Executes wiki backfill jobs with rate limiting and monitoring."""

    def __init__(
        self,
        wiki_repo: SQLiteWikiRepository,
        stored_summary_repo: SQLiteStoredSummaryRepository,
        job_repo: SQLiteSummaryJobRepository,
    ):
        self.wiki_repo = wiki_repo
        self.stored_summary_repo = stored_summary_repo
        self.job_repo = job_repo
        self._cancelled = False

    async def execute(self, job: SummaryJob) -> None:
        """Execute the wiki backfill job."""
        try:
            config = self._parse_config(job)
            progress = BackfillProgress()

            # Get summaries to process
            summaries = await self._get_summaries(job.guild_id, config)
            progress.total_summaries = len(summaries)

            if not summaries:
                job.update_progress(0, total=0, message="No summaries to process")
                job.complete()
                await self.job_repo.update(job)
                return

            job.start()
            job.update_progress(0, total=len(summaries), message="Starting backfill...")
            await self.job_repo.update(job)

            # Process in batches
            batch_num = 0
            for i in range(0, len(summaries), config.batch_size):
                batch = summaries[i:i + config.batch_size]
                batch_num += 1

                # Check for cancellation
                refreshed_job = await self.job_repo.get(job.id)
                if refreshed_job and refreshed_job.status == JobStatus.CANCELLED:
                    logger.info(f"Wiki backfill {job.id} cancelled")
                    return

                # Priority yielding - wait for real-time jobs
                if config.enable_priority_yielding:
                    await self._wait_for_priority(job)

                # Resource monitoring
                if config.enable_resource_monitoring:
                    await self._wait_for_resources(job, config)

                # Process batch
                for summary in batch:
                    progress.current_summary_id = summary.id
                    progress.current_summary_title = summary.title

                    try:
                        await self._process_summary(summary, config)
                        progress.ingested += 1
                    except Exception as e:
                        progress.failed += 1
                        progress.errors.append({
                            "summary_id": summary.id,
                            "summary_title": summary.title,
                            "error": str(e),
                            "timestamp": utc_now_naive().isoformat(),
                        })
                        logger.warning(f"Failed to ingest summary {summary.id}: {e}")

                    progress.processed += 1

                # Update job progress
                total_batches = (len(summaries) + config.batch_size - 1) // config.batch_size
                job.update_progress(
                    current=progress.processed,
                    total=progress.total_summaries,
                    message=f"Batch {batch_num}/{total_batches}: {progress.ingested} ingested, {progress.failed} failed",
                )
                job.metadata["errors"] = progress.errors[-10:]  # Keep last 10 errors
                job.metadata["stats"] = {
                    "ingested": progress.ingested,
                    "skipped": progress.skipped,
                    "failed": progress.failed,
                }
                await self.job_repo.update(job)

                # Delay between batches (with adaptive adjustment)
                delay = await self._get_adaptive_delay(config)
                await asyncio.sleep(delay)

            # Complete the job
            job.update_progress(
                current=progress.total_summaries,
                total=progress.total_summaries,
                message=f"Completed: {progress.ingested} ingested, {progress.failed} failed, {progress.skipped} skipped",
            )
            job.complete()
            await self.job_repo.update(job)

            logger.info(
                f"Wiki backfill {job.id} completed: "
                f"{progress.ingested} ingested, {progress.failed} failed"
            )

        except Exception as e:
            logger.exception(f"Wiki backfill {job.id} failed: {e}")
            job.fail(str(e))
            await self.job_repo.update(job)

    def _parse_config(self, job: SummaryJob) -> BackfillConfig:
        """Parse job metadata into config."""
        meta = job.metadata or {}
        return BackfillConfig(
            mode=meta.get("mode", "unprocessed"),
            batch_size=meta.get("batch_size", 10),
            delay_between_batches=meta.get("delay", 1.0),
            date_from=datetime.fromisoformat(meta["date_from"]) if meta.get("date_from") else None,
            date_to=datetime.fromisoformat(meta["date_to"]) if meta.get("date_to") else None,
            enable_priority_yielding=meta.get("enable_priority_yielding", True),
            enable_resource_monitoring=meta.get("enable_resource_monitoring", True),
            cpu_threshold=meta.get("cpu_threshold", 80.0),
            memory_threshold=meta.get("memory_threshold", 85.0),
        )

    async def _get_summaries(
        self,
        guild_id: str,
        config: BackfillConfig,
    ) -> List[StoredSummary]:
        """Get summaries to process based on config mode."""
        if config.mode == "unprocessed":
            return await self.stored_summary_repo.find_not_wiki_ingested(
                guild_id=guild_id,
                limit=1000,  # Cap at 1000 for safety
            )
        elif config.mode == "date_range":
            return await self.stored_summary_repo.find_by_guild(
                guild_id=guild_id,
                created_after=config.date_from,
                created_before=config.date_to,
                limit=1000,
            )
        elif config.mode == "all":
            return await self.stored_summary_repo.find_by_guild(
                guild_id=guild_id,
                limit=1000,
            )
        else:
            return []

    async def _process_summary(
        self,
        summary: StoredSummary,
        config: BackfillConfig,
    ) -> None:
        """Process a single summary into the wiki."""
        from .agents import WikiIngestAgent

        result = summary.summary_result
        if not result:
            logger.debug(f"No summary result for {summary.id}, skipping")
            return

        agent = WikiIngestAgent(self.wiki_repo)

        # Extract platform from archive_source_key or default to discord
        platform = "discord"
        if summary.archive_source_key:
            parts = summary.archive_source_key.split(":")
            if parts:
                platform = parts[0]

        await agent.ingest_summary(
            guild_id=summary.guild_id,
            summary_id=summary.id,
            summary_text=result.summary_text or "",
            key_points=result.key_points or [],
            action_items=[a.description for a in (result.action_items or [])],
            participants=[p.display_name for p in (result.participants or [])],
            technical_terms=[t.term for t in (result.technical_terms or [])],
            channel_name=summary.title or "Unknown",
            timestamp=summary.created_at,
            platform=platform,
        )

        # Mark as ingested
        await self.stored_summary_repo.mark_wiki_ingested(summary.id)

    async def _wait_for_priority(self, job: SummaryJob) -> None:
        """Wait for higher-priority jobs to complete (priority yielding)."""
        while True:
            # Check for real-time summary jobs
            active_count = await self.job_repo.count_active_by_types(
                [JobType.MANUAL, JobType.SCHEDULED],
                guild_id=job.guild_id,
            )

            if active_count == 0:
                return

            job.update_progress(
                job.progress_current,
                message=f"Paused: waiting for {active_count} real-time job(s)",
            )
            await self.job_repo.update(job)
            await asyncio.sleep(5)

    async def _wait_for_resources(
        self,
        job: SummaryJob,
        config: BackfillConfig,
    ) -> None:
        """Wait for system resources to be available."""
        try:
            import psutil

            while True:
                cpu = psutil.cpu_percent(interval=0.5)
                memory = psutil.virtual_memory().percent

                if cpu < config.cpu_threshold and memory < config.memory_threshold:
                    return

                reason = []
                if cpu >= config.cpu_threshold:
                    reason.append(f"CPU {cpu:.0f}%")
                if memory >= config.memory_threshold:
                    reason.append(f"Memory {memory:.0f}%")

                job.update_progress(
                    job.progress_current,
                    message=f"Paused: {', '.join(reason)}",
                )
                await self.job_repo.update(job)
                await asyncio.sleep(10)

        except ImportError:
            # psutil not available, skip resource monitoring
            pass

    async def _get_adaptive_delay(self, config: BackfillConfig) -> float:
        """Get adaptive delay based on system load."""
        try:
            import psutil

            cpu = psutil.cpu_percent()

            if cpu < 30:
                return max(0.5, config.delay_between_batches * 0.5)
            elif cpu < 50:
                return config.delay_between_batches
            elif cpu < 70:
                return config.delay_between_batches * 2
            else:
                return min(10.0, config.delay_between_batches * 5)

        except ImportError:
            return config.delay_between_batches


def generate_backfill_job_id() -> str:
    """Generate a unique job ID for wiki backfill."""
    import uuid
    return f"wiki-backfill-{uuid.uuid4().hex[:12]}"
