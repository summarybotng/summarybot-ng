"""
SQLite implementation of summary job repository (ADR-013).
"""

import json
import logging
from typing import List, Optional
from datetime import datetime

from ..base import SummaryJobRepository
from ...models.summary_job import SummaryJob, JobType, JobStatus
from .connection import SQLiteConnection

logger = logging.getLogger(__name__)


class SQLiteSummaryJobRepository(SummaryJobRepository):
    """SQLite implementation of summary job repository (ADR-013)."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    async def save(self, job: SummaryJob) -> str:
        """Save a job to the database."""
        query = """
        INSERT INTO summary_jobs (
            id, guild_id, job_type, status, scope, channel_ids, category_id,
            schedule_id, period_start, period_end, date_range_start, date_range_end,
            granularity, summary_type, perspective, force_regenerate,
            progress_current, progress_total, progress_message, current_period,
            cost_usd, tokens_input, tokens_output, summary_id, summary_ids,
            error, pause_reason, created_at, started_at, completed_at,
            created_by, source_key, server_name, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            job.id,
            job.guild_id,
            job.job_type.value,
            job.status.value,
            job.scope,
            json.dumps(job.channel_ids) if job.channel_ids else None,
            job.category_id,
            job.schedule_id,
            job.period_start.isoformat() if job.period_start else None,
            job.period_end.isoformat() if job.period_end else None,
            job.date_range_start.isoformat() if job.date_range_start else None,
            job.date_range_end.isoformat() if job.date_range_end else None,
            job.granularity,
            job.summary_type,
            job.perspective,
            1 if job.force_regenerate else 0,
            job.progress_current,
            job.progress_total,
            job.progress_message,
            job.current_period,
            job.cost_usd,
            job.tokens_input,
            job.tokens_output,
            job.summary_id,
            json.dumps(job.summary_ids) if job.summary_ids else None,
            job.error,
            job.pause_reason,
            job.created_at.isoformat(),
            job.started_at.isoformat() if job.started_at else None,
            job.completed_at.isoformat() if job.completed_at else None,
            job.created_by,
            job.source_key,
            job.server_name,
            json.dumps(job.metadata) if job.metadata else None,
        )

        await self.connection.execute(query, params)
        return job.id

    async def get(self, job_id: str) -> Optional[SummaryJob]:
        """Get a job by ID."""
        query = "SELECT * FROM summary_jobs WHERE id = ?"
        row = await self.connection.fetch_one(query, (job_id,))
        if not row:
            return None
        return SummaryJob.from_dict(dict(row))

    async def update(self, job: SummaryJob) -> bool:
        """Update an existing job."""
        query = """
        UPDATE summary_jobs SET
            status = ?,
            progress_current = ?,
            progress_total = ?,
            progress_message = ?,
            current_period = ?,
            cost_usd = ?,
            tokens_input = ?,
            tokens_output = ?,
            summary_id = ?,
            summary_ids = ?,
            error = ?,
            pause_reason = ?,
            started_at = ?,
            completed_at = ?
        WHERE id = ?
        """

        params = (
            job.status.value,
            job.progress_current,
            job.progress_total,
            job.progress_message,
            job.current_period,
            job.cost_usd,
            job.tokens_input,
            job.tokens_output,
            job.summary_id,
            json.dumps(job.summary_ids) if job.summary_ids else None,
            job.error,
            job.pause_reason,
            job.started_at.isoformat() if job.started_at else None,
            job.completed_at.isoformat() if job.completed_at else None,
            job.id,
        )

        cursor = await self.connection.execute(query, params)
        return cursor.rowcount > 0

    async def find_by_guild(
        self,
        guild_id: str,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[SummaryJob]:
        """Find jobs for a guild with optional filters."""
        conditions = ["guild_id = ?"]
        params = [guild_id]

        if status:
            conditions.append("status = ?")
            params.append(status)

        if job_type:
            conditions.append("job_type = ?")
            params.append(job_type)

        query = f"""
        SELECT * FROM summary_jobs
        WHERE {' AND '.join(conditions)}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        rows = await self.connection.fetch_all(query, tuple(params))
        return [SummaryJob.from_dict(dict(row)) for row in rows]

    async def find_active(self, guild_id: Optional[str] = None) -> List[SummaryJob]:
        """Find all active (pending/running) jobs."""
        if guild_id:
            query = """
            SELECT * FROM summary_jobs
            WHERE guild_id = ? AND status IN ('pending', 'running', 'paused')
            ORDER BY created_at DESC
            """
            rows = await self.connection.fetch_all(query, (guild_id,))
        else:
            query = """
            SELECT * FROM summary_jobs
            WHERE status IN ('pending', 'running', 'paused')
            ORDER BY created_at DESC
            """
            rows = await self.connection.fetch_all(query, ())

        return [SummaryJob.from_dict(dict(row)) for row in rows]

    async def delete(self, job_id: str) -> bool:
        """Delete a job by ID."""
        query = "DELETE FROM summary_jobs WHERE id = ?"
        cursor = await self.connection.execute(query, (job_id,))
        return cursor.rowcount > 0

    async def cleanup_old(self, days: int = 7) -> int:
        """Delete jobs older than specified days."""
        query = """
        DELETE FROM summary_jobs
        WHERE completed_at IS NOT NULL
        AND completed_at < datetime('now', '-' || ? || ' days')
        """
        cursor = await self.connection.execute(query, (days,))
        return cursor.rowcount

    async def count_by_guild(
        self,
        guild_id: str,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
    ) -> int:
        """Count jobs for a guild."""
        conditions = ["guild_id = ?"]
        params = [guild_id]

        if status:
            conditions.append("status = ?")
            params.append(status)

        if job_type:
            conditions.append("job_type = ?")
            params.append(job_type)

        query = f"""
        SELECT COUNT(*) as count FROM summary_jobs
        WHERE {' AND '.join(conditions)}
        """

        row = await self.connection.fetch_one(query, tuple(params))
        return row['count'] if row else 0

    async def mark_interrupted_jobs(self, reason: str = "server_restart") -> int:
        """
        Mark all RUNNING jobs as PAUSED due to server restart.

        ADR-013: Startup recovery - when the server restarts, any jobs that were
        RUNNING are marked as PAUSED so users can see they were interrupted and
        can choose to resume them.

        Args:
            reason: The pause reason to set (default: 'server_restart')

        Returns:
            Number of jobs that were marked as paused
        """
        query = """
        UPDATE summary_jobs
        SET status = 'paused', pause_reason = ?
        WHERE status = 'running'
        """
        cursor = await self.connection.execute(query, (reason,))
        return cursor.rowcount

    # ADR-068: Wiki backfill support

    async def find_active_by_type(
        self,
        guild_id: str,
        job_type: JobType,
    ) -> Optional[SummaryJob]:
        """Find an active job of a specific type for a guild."""
        query = """
        SELECT * FROM summary_jobs
        WHERE guild_id = ? AND job_type = ? AND status IN ('pending', 'running', 'paused')
        ORDER BY created_at DESC
        LIMIT 1
        """
        row = await self.connection.fetch_one(query, (guild_id, job_type.value))
        if not row:
            return None
        return SummaryJob.from_dict(dict(row))

    async def count_active_by_types(
        self,
        job_types: List[JobType],
        guild_id: Optional[str] = None,
    ) -> int:
        """Count active jobs of specific types (for priority yielding)."""
        type_values = [t.value for t in job_types]
        placeholders = ",".join("?" for _ in type_values)

        if guild_id:
            query = f"""
            SELECT COUNT(*) as count FROM summary_jobs
            WHERE guild_id = ? AND job_type IN ({placeholders})
            AND status IN ('pending', 'running')
            """
            params = [guild_id] + type_values
        else:
            query = f"""
            SELECT COUNT(*) as count FROM summary_jobs
            WHERE job_type IN ({placeholders})
            AND status IN ('pending', 'running')
            """
            params = type_values

        row = await self.connection.fetch_one(query, tuple(params))
        return row['count'] if row else 0

    async def find_by_category(
        self,
        guild_id: str,
        category: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[SummaryJob]:
        """Find jobs by category (ADR-068)."""
        from ...models.summary_job import JobCategory, JOB_TYPE_CATEGORY

        # Get job types for this category
        try:
            cat_enum = JobCategory(category)
        except ValueError:
            return []

        job_types = [jt.value for jt, cat in JOB_TYPE_CATEGORY.items() if cat == cat_enum]
        if not job_types:
            return []

        placeholders = ",".join("?" for _ in job_types)
        query = f"""
        SELECT * FROM summary_jobs
        WHERE guild_id = ? AND job_type IN ({placeholders})
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """
        params = [guild_id] + job_types + [limit, offset]

        rows = await self.connection.fetch_all(query, tuple(params))
        return [SummaryJob.from_dict(dict(row)) for row in rows]
