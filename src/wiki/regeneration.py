"""
Wiki Regeneration Service (ADR-084).

Handles bulk wiki page regeneration:
- Auto-regenerate after bulk ingest
- On-demand bulk regeneration
- Full wiki rebuild
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..data.sqlite.wiki_repository import SQLiteWikiRepository
    from ..summarization.claude_client import ClaudeClient

from .synthesis import synthesize_wiki_page
from .models import SynthesisOptions

logger = logging.getLogger(__name__)

# Threshold for auto-regeneration after bulk ingest
BULK_INGEST_THRESHOLD = 3


class RegenerationScope(str, Enum):
    """Scope of regeneration job."""
    SELECTED = "selected"      # Specific pages/summaries
    DATE_RANGE = "date_range"  # Pages updated in date range
    FULL = "full"              # All pages


class RegenerationStatus(str, Enum):
    """Status of regeneration job."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class RegenerationJob:
    """A wiki regeneration job."""
    id: str
    guild_id: str
    scope: RegenerationScope
    status: RegenerationStatus
    summary_ids: Optional[List[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    page_count: int = 0
    processed_count: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None


@dataclass
class RegenerationResult:
    """Result of regeneration operation."""
    job_id: str
    pages_regenerated: int
    pages_failed: int
    duration_seconds: float
    errors: List[str]


class WikiRegenerationService:
    """
    Service for bulk wiki regeneration.

    Handles:
    - Creating and tracking regeneration jobs
    - Processing pages in batches
    - Auto-triggering after bulk ingest
    """

    def __init__(
        self,
        wiki_repo: "SQLiteWikiRepository",
        claude_client: Optional["ClaudeClient"] = None,
    ):
        self.wiki_repo = wiki_repo
        self.claude_client = claude_client

    async def create_job(
        self,
        guild_id: str,
        scope: RegenerationScope,
        summary_ids: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> RegenerationJob:
        """
        Create a regeneration job.

        Args:
            guild_id: Guild ID
            scope: Scope of regeneration
            summary_ids: For SELECTED scope, list of summary IDs
            start_date: For DATE_RANGE scope, start date
            end_date: For DATE_RANGE scope, end date
            created_by: User ID who created the job

        Returns:
            Created job
        """
        job_id = f"regen_{uuid.uuid4().hex[:12]}"

        # Calculate page count based on scope
        page_count = await self._estimate_page_count(
            guild_id, scope, summary_ids, start_date, end_date
        )

        job = RegenerationJob(
            id=job_id,
            guild_id=guild_id,
            scope=scope,
            status=RegenerationStatus.PENDING,
            summary_ids=summary_ids,
            start_date=start_date,
            end_date=end_date,
            page_count=page_count,
            created_by=created_by,
        )

        # Store in database
        await self._save_job(job)

        logger.info(f"Created regeneration job {job_id}: scope={scope}, pages={page_count}")

        return job

    async def process_job(self, job_id: str) -> RegenerationResult:
        """
        Process a regeneration job.

        Args:
            job_id: Job ID to process

        Returns:
            RegenerationResult with counts
        """
        import time
        start_time = time.time()

        job = await self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Update status to processing
        job.status = RegenerationStatus.PROCESSING
        job.started_at = datetime.utcnow()
        await self._save_job(job)

        pages_regenerated = 0
        pages_failed = 0
        errors = []

        try:
            # Get pages to regenerate based on scope
            pages = await self._get_pages_for_scope(job)

            for page in pages:
                try:
                    await self._regenerate_page(job.guild_id, page.path)
                    pages_regenerated += 1
                    job.processed_count = pages_regenerated
                    await self._save_job(job)
                except Exception as e:
                    pages_failed += 1
                    errors.append(f"{page.path}: {str(e)}")
                    logger.warning(f"Failed to regenerate {page.path}: {e}")

            # Mark completed
            job.status = RegenerationStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            await self._save_job(job)

        except Exception as e:
            job.status = RegenerationStatus.FAILED
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            await self._save_job(job)
            logger.exception(f"Regeneration job {job_id} failed: {e}")

        duration = time.time() - start_time

        return RegenerationResult(
            job_id=job_id,
            pages_regenerated=pages_regenerated,
            pages_failed=pages_failed,
            duration_seconds=duration,
            errors=errors,
        )

    async def get_job(self, job_id: str) -> Optional[RegenerationJob]:
        """Get a regeneration job by ID."""
        row = await self.wiki_repo.connection.fetch_one(
            "SELECT * FROM wiki_regeneration_jobs WHERE id = ?",
            (job_id,)
        )
        if not row:
            return None
        return self._row_to_job(row)

    async def get_active_job(self, guild_id: str) -> Optional[RegenerationJob]:
        """Get active (pending/processing) job for guild."""
        row = await self.wiki_repo.connection.fetch_one(
            """SELECT * FROM wiki_regeneration_jobs
               WHERE guild_id = ? AND status IN ('pending', 'processing')
               ORDER BY created_at DESC LIMIT 1""",
            (guild_id,)
        )
        if not row:
            return None
        return self._row_to_job(row)

    async def get_recent_jobs(
        self, guild_id: str, limit: int = 10
    ) -> List[RegenerationJob]:
        """Get recent regeneration jobs for guild."""
        rows = await self.wiki_repo.connection.fetch_all(
            """SELECT * FROM wiki_regeneration_jobs
               WHERE guild_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (guild_id, limit)
        )
        return [self._row_to_job(row) for row in rows]

    async def should_auto_regenerate(
        self, guild_id: str, ingested_count: int
    ) -> bool:
        """
        Check if auto-regeneration should be triggered.

        Returns True if:
        - Ingested count >= threshold
        - No active job already running
        """
        if ingested_count < BULK_INGEST_THRESHOLD:
            return False

        active = await self.get_active_job(guild_id)
        return active is None

    async def trigger_auto_regeneration(
        self, guild_id: str, summary_ids: List[str]
    ) -> Optional[RegenerationJob]:
        """
        Trigger auto-regeneration after bulk ingest.

        Args:
            guild_id: Guild ID
            summary_ids: IDs of summaries that were just ingested

        Returns:
            Created job or None if conditions not met
        """
        if not await self.should_auto_regenerate(guild_id, len(summary_ids)):
            return None

        logger.info(f"Auto-triggering wiki regeneration for {len(summary_ids)} summaries")

        job = await self.create_job(
            guild_id=guild_id,
            scope=RegenerationScope.SELECTED,
            summary_ids=summary_ids,
            created_by="system:auto-regenerate",
        )

        return job

    async def _estimate_page_count(
        self,
        guild_id: str,
        scope: RegenerationScope,
        summary_ids: Optional[List[str]],
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> int:
        """Estimate number of pages to regenerate."""
        if scope == RegenerationScope.FULL:
            row = await self.wiki_repo.connection.fetch_one(
                "SELECT COUNT(*) as count FROM wiki_pages WHERE guild_id = ?",
                (guild_id,)
            )
            return row["count"] if row else 0

        elif scope == RegenerationScope.SELECTED and summary_ids:
            # Count pages that reference these summaries
            placeholders = ",".join("?" * len(summary_ids))
            source_refs = [f"summary-{sid}" for sid in summary_ids]
            row = await self.wiki_repo.connection.fetch_one(
                f"""SELECT COUNT(DISTINCT id) as count FROM wiki_pages
                    WHERE guild_id = ? AND (
                        {" OR ".join(f"source_refs LIKE ?" for _ in source_refs)}
                    )""",
                (guild_id, *[f"%{ref}%" for ref in source_refs])
            )
            return row["count"] if row else 0

        elif scope == RegenerationScope.DATE_RANGE and start_date and end_date:
            row = await self.wiki_repo.connection.fetch_one(
                """SELECT COUNT(*) as count FROM wiki_pages
                   WHERE guild_id = ? AND updated_at >= ? AND updated_at <= ?""",
                (guild_id, start_date, end_date)
            )
            return row["count"] if row else 0

        return 0

    async def _get_pages_for_scope(self, job: RegenerationJob) -> List:
        """Get pages to regenerate based on job scope."""
        if job.scope == RegenerationScope.FULL:
            rows = await self.wiki_repo.connection.fetch_all(
                "SELECT * FROM wiki_pages WHERE guild_id = ?",
                (job.guild_id,)
            )

        elif job.scope == RegenerationScope.SELECTED and job.summary_ids:
            source_refs = [f"summary-{sid}" for sid in job.summary_ids]
            conditions = " OR ".join(f"source_refs LIKE ?" for _ in source_refs)
            rows = await self.wiki_repo.connection.fetch_all(
                f"""SELECT DISTINCT * FROM wiki_pages
                    WHERE guild_id = ? AND ({conditions})""",
                (job.guild_id, *[f"%{ref}%" for ref in source_refs])
            )

        elif job.scope == RegenerationScope.DATE_RANGE:
            rows = await self.wiki_repo.connection.fetch_all(
                """SELECT * FROM wiki_pages
                   WHERE guild_id = ? AND updated_at >= ? AND updated_at <= ?""",
                (job.guild_id, job.start_date, job.end_date)
            )
        else:
            rows = []

        # Convert to page objects
        return [self._row_to_page(row) for row in rows]

    async def _regenerate_page(self, guild_id: str, path: str) -> None:
        """Regenerate synthesis for a single page."""
        page = await self.wiki_repo.get_page(guild_id, path)
        if not page:
            return

        # Skip pages with no content
        if not page.content or len(page.content.strip()) < 50:
            logger.debug(f"Skipping {path}: insufficient content")
            return

        # Generate synthesis
        result = await synthesize_wiki_page(
            page_title=page.title,
            page_content=page.content,
            source_refs=page.source_refs,
            claude_client=self.claude_client,
            options=SynthesisOptions(model="auto"),
        )

        # Save synthesis
        await self.wiki_repo.save_synthesis(
            guild_id=guild_id,
            path=path,
            synthesis=result.synthesis,
            source_count=result.source_count,
            model=result.model_used,
        )

        logger.debug(f"Regenerated synthesis for {path}")

    async def _save_job(self, job: RegenerationJob) -> None:
        """Save job to database."""
        summary_ids_json = json.dumps(job.summary_ids) if job.summary_ids else None

        await self.wiki_repo.connection.execute(
            """INSERT OR REPLACE INTO wiki_regeneration_jobs
               (id, guild_id, scope, status, summary_ids, start_date, end_date,
                page_count, processed_count, started_at, completed_at,
                error_message, created_at, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), ?)""",
            (
                job.id, job.guild_id, job.scope.value if isinstance(job.scope, RegenerationScope) else job.scope,
                job.status.value if isinstance(job.status, RegenerationStatus) else job.status,
                summary_ids_json, job.start_date, job.end_date,
                job.page_count, job.processed_count,
                job.started_at.isoformat() if job.started_at else None,
                job.completed_at.isoformat() if job.completed_at else None,
                job.error_message,
                job.created_at.isoformat() if job.created_at else None,
                job.created_by,
            )
        )

    def _row_to_job(self, row) -> RegenerationJob:
        """Convert database row to RegenerationJob."""
        summary_ids = None
        if row["summary_ids"]:
            try:
                summary_ids = json.loads(row["summary_ids"])
            except json.JSONDecodeError:
                pass

        return RegenerationJob(
            id=row["id"],
            guild_id=row["guild_id"],
            scope=RegenerationScope(row["scope"]),
            status=RegenerationStatus(row["status"]),
            summary_ids=summary_ids,
            start_date=row["start_date"],
            end_date=row["end_date"],
            page_count=row["page_count"],
            processed_count=row["processed_count"],
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            error_message=row["error_message"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            created_by=row["created_by"],
        )

    def _row_to_page(self, row):
        """Convert database row to page-like object."""
        from dataclasses import dataclass

        @dataclass
        class PageStub:
            path: str
            title: str
            content: str
            source_refs: List[str]

        source_refs = []
        if row.get("source_refs"):
            try:
                source_refs = json.loads(row["source_refs"])
            except (json.JSONDecodeError, TypeError):
                pass

        return PageStub(
            path=row["path"],
            title=row.get("title", ""),
            content=row.get("content", ""),
            source_refs=source_refs,
        )
