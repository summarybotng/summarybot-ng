"""
SQLite repository for content coverage tracking (ADR-072).
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple
from .connection import SQLiteConnection

logger = logging.getLogger(__name__)


@dataclass
class ChannelCoverage:
    """Coverage status for a single channel."""
    id: str
    guild_id: str
    channel_id: str
    channel_name: Optional[str]
    platform: str

    # Content boundaries
    content_start: Optional[datetime]
    content_end: Optional[datetime]
    estimated_messages: int

    # Coverage boundaries
    covered_start: Optional[datetime]
    covered_end: Optional[datetime]
    summary_count: int

    # Metrics
    coverage_percent: float
    gap_count: int
    covered_days: int
    total_days: int

    # Timestamps
    last_summary_at: Optional[datetime]
    last_computed_at: datetime


@dataclass
class CoverageGap:
    """A gap in coverage that needs backfill."""
    id: str
    guild_id: str
    channel_id: str
    channel_name: Optional[str]
    platform: str

    # Gap boundaries
    gap_start: datetime
    gap_end: datetime
    gap_days: int

    # Status
    status: str  # pending, scheduled, running, complete, failed, skipped
    priority: int

    # Tracking
    job_id: Optional[str]
    summary_id: Optional[str]
    error_message: Optional[str]

    # Timestamps
    scheduled_for: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime


@dataclass
class BackfillSchedule:
    """Backfill schedule configuration for a guild."""
    id: str
    guild_id: str
    platform: str

    # Config
    channels: List[str]  # Empty = all channels
    priority_mode: str  # oldest_first, newest_first, largest_gaps
    rate_limit: int  # Summaries per hour

    # Status
    enabled: bool
    paused: bool

    # Progress
    total_gaps: int
    completed_gaps: int
    failed_gaps: int

    # Timestamps
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


@dataclass
class CoverageReport:
    """Full coverage report for a guild."""
    guild_id: str
    platform: str
    channels: List[ChannelCoverage]
    total_coverage_percent: float
    total_gaps: int
    total_channels: int
    covered_channels: int
    computed_at: datetime


class SQLiteCoverageRepository:
    """Repository for content coverage tracking."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    def _format_datetime(self, dt: Optional[datetime]) -> Optional[str]:
        if not dt:
            return None
        return dt.isoformat()

    # =========================================================================
    # Channel Coverage
    # =========================================================================

    async def get_coverage(self, guild_id: str, platform: str = "discord") -> List[ChannelCoverage]:
        """Get coverage for all channels in a guild."""
        rows = await self.connection.fetch_all(
            """
            SELECT id, guild_id, channel_id, channel_name, platform,
                   content_start, content_end, estimated_messages,
                   covered_start, covered_end, summary_count,
                   coverage_percent, gap_count, covered_days, total_days,
                   last_summary_at, last_computed_at
            FROM content_coverage
            WHERE guild_id = ? AND platform = ?
            ORDER BY channel_name
            """,
            (guild_id, platform),
        )

        return [
            ChannelCoverage(
                id=row["id"],
                guild_id=row["guild_id"],
                channel_id=row["channel_id"],
                channel_name=row["channel_name"],
                platform=row["platform"],
                content_start=self._parse_datetime(row["content_start"]),
                content_end=self._parse_datetime(row["content_end"]),
                estimated_messages=row["estimated_messages"] or 0,
                covered_start=self._parse_datetime(row["covered_start"]),
                covered_end=self._parse_datetime(row["covered_end"]),
                summary_count=row["summary_count"] or 0,
                coverage_percent=row["coverage_percent"] or 0,
                gap_count=row["gap_count"] or 0,
                covered_days=row["covered_days"] or 0,
                total_days=row["total_days"] or 0,
                last_summary_at=self._parse_datetime(row["last_summary_at"]),
                last_computed_at=self._parse_datetime(row["last_computed_at"]) or datetime.utcnow(),
            )
            for row in rows
        ]

    async def upsert_coverage(self, coverage: ChannelCoverage) -> None:
        """Insert or update channel coverage."""
        await self.connection.execute(
            """
            INSERT INTO content_coverage (
                id, guild_id, channel_id, channel_name, platform,
                content_start, content_end, estimated_messages,
                covered_start, covered_end, summary_count,
                coverage_percent, gap_count, covered_days, total_days,
                last_summary_at, last_computed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, channel_id, platform) DO UPDATE SET
                channel_name = excluded.channel_name,
                content_start = excluded.content_start,
                content_end = excluded.content_end,
                estimated_messages = excluded.estimated_messages,
                covered_start = excluded.covered_start,
                covered_end = excluded.covered_end,
                summary_count = excluded.summary_count,
                coverage_percent = excluded.coverage_percent,
                gap_count = excluded.gap_count,
                covered_days = excluded.covered_days,
                total_days = excluded.total_days,
                last_summary_at = excluded.last_summary_at,
                last_computed_at = excluded.last_computed_at
            """,
            (
                coverage.id,
                coverage.guild_id,
                coverage.channel_id,
                coverage.channel_name,
                coverage.platform,
                self._format_datetime(coverage.content_start),
                self._format_datetime(coverage.content_end),
                coverage.estimated_messages,
                self._format_datetime(coverage.covered_start),
                self._format_datetime(coverage.covered_end),
                coverage.summary_count,
                coverage.coverage_percent,
                coverage.gap_count,
                coverage.covered_days,
                coverage.total_days,
                self._format_datetime(coverage.last_summary_at),
                self._format_datetime(coverage.last_computed_at),
            ),
        )

    # =========================================================================
    # Coverage Gaps
    # =========================================================================

    async def get_gaps(
        self,
        guild_id: str,
        platform: str = "discord",
        status: Optional[str] = None,
        channel_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[CoverageGap], int]:
        """Get coverage gaps with optional filtering."""
        conditions = ["guild_id = ?", "platform = ?"]
        params: list = [guild_id, platform]

        if status:
            conditions.append("status = ?")
            params.append(status)

        if channel_id:
            conditions.append("channel_id = ?")
            params.append(channel_id)

        where_clause = " AND ".join(conditions)

        # Get total count
        row = await self.connection.fetch_one(
            f"SELECT COUNT(*) as count FROM coverage_gaps WHERE {where_clause}",
            tuple(params),
        )
        total = row["count"] if row else 0

        # Get gaps
        params.extend([limit, offset])
        rows = await self.connection.fetch_all(
            f"""
            SELECT id, guild_id, channel_id, channel_name, platform,
                   gap_start, gap_end, gap_days, status, priority,
                   job_id, summary_id, error_message,
                   scheduled_for, started_at, completed_at, created_at
            FROM coverage_gaps
            WHERE {where_clause}
            ORDER BY priority DESC, gap_start ASC
            LIMIT ? OFFSET ?
            """,
            tuple(params),
        )

        gaps = [
            CoverageGap(
                id=row["id"],
                guild_id=row["guild_id"],
                channel_id=row["channel_id"],
                channel_name=row["channel_name"],
                platform=row["platform"],
                gap_start=self._parse_datetime(row["gap_start"]) or datetime.utcnow(),
                gap_end=self._parse_datetime(row["gap_end"]) or datetime.utcnow(),
                gap_days=row["gap_days"] or 0,
                status=row["status"],
                priority=row["priority"] or 0,
                job_id=row["job_id"],
                summary_id=row["summary_id"],
                error_message=row["error_message"],
                scheduled_for=self._parse_datetime(row["scheduled_for"]),
                started_at=self._parse_datetime(row["started_at"]),
                completed_at=self._parse_datetime(row["completed_at"]),
                created_at=self._parse_datetime(row["created_at"]) or datetime.utcnow(),
            )
            for row in rows
        ]

        return gaps, total

    async def create_gap(self, gap: CoverageGap) -> None:
        """Create a new coverage gap."""
        await self.connection.execute(
            """
            INSERT INTO coverage_gaps (
                id, guild_id, channel_id, channel_name, platform,
                gap_start, gap_end, gap_days, status, priority,
                job_id, summary_id, error_message,
                scheduled_for, started_at, completed_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                gap.id,
                gap.guild_id,
                gap.channel_id,
                gap.channel_name,
                gap.platform,
                self._format_datetime(gap.gap_start),
                self._format_datetime(gap.gap_end),
                gap.gap_days,
                gap.status,
                gap.priority,
                gap.job_id,
                gap.summary_id,
                gap.error_message,
                self._format_datetime(gap.scheduled_for),
                self._format_datetime(gap.started_at),
                self._format_datetime(gap.completed_at),
                self._format_datetime(gap.created_at),
            ),
        )

    async def update_gap_status(
        self,
        gap_id: str,
        status: str,
        summary_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update gap status."""
        now = datetime.utcnow().isoformat()

        if status == "running":
            await self.connection.execute(
                "UPDATE coverage_gaps SET status = ?, started_at = ? WHERE id = ?",
                (status, now, gap_id),
            )
        elif status in ("complete", "skipped"):
            await self.connection.execute(
                "UPDATE coverage_gaps SET status = ?, summary_id = ?, completed_at = ? WHERE id = ?",
                (status, summary_id, now, gap_id),
            )
        elif status == "failed":
            await self.connection.execute(
                "UPDATE coverage_gaps SET status = ?, error_message = ?, completed_at = ? WHERE id = ?",
                (status, error_message, now, gap_id),
            )
        else:
            await self.connection.execute(
                "UPDATE coverage_gaps SET status = ? WHERE id = ?",
                (status, gap_id),
            )

    async def delete_gaps_for_guild(self, guild_id: str, platform: str = "discord") -> int:
        """Delete all gaps for a guild (for recomputation)."""
        cursor = await self.connection.execute(
            "DELETE FROM coverage_gaps WHERE guild_id = ? AND platform = ? AND status = 'pending'",
            (guild_id, platform),
        )
        return cursor.rowcount

    async def get_pending_gaps(
        self,
        guild_id: str,
        platform: str = "discord",
        limit: int = 10,
    ) -> List[CoverageGap]:
        """Get next gaps to process for backfill."""
        gaps, _ = await self.get_gaps(
            guild_id=guild_id,
            platform=platform,
            status="pending",
            limit=limit,
        )
        return gaps

    # =========================================================================
    # Backfill Schedules
    # =========================================================================

    async def get_backfill_schedule(
        self,
        guild_id: str,
        platform: str = "discord",
    ) -> Optional[BackfillSchedule]:
        """Get backfill schedule for a guild."""
        row = await self.connection.fetch_one(
            """
            SELECT id, guild_id, platform, channels, priority_mode, rate_limit,
                   enabled, paused, total_gaps, completed_gaps, failed_gaps,
                   last_run_at, next_run_at, created_at, updated_at
            FROM backfill_schedules
            WHERE guild_id = ? AND platform = ?
            """,
            (guild_id, platform),
        )

        if not row:
            return None

        channels = []
        if row["channels"]:
            try:
                channels = json.loads(row["channels"])
            except json.JSONDecodeError:
                pass

        return BackfillSchedule(
            id=row["id"],
            guild_id=row["guild_id"],
            platform=row["platform"],
            channels=channels,
            priority_mode=row["priority_mode"],
            rate_limit=row["rate_limit"],
            enabled=bool(row["enabled"]),
            paused=bool(row["paused"]),
            total_gaps=row["total_gaps"] or 0,
            completed_gaps=row["completed_gaps"] or 0,
            failed_gaps=row["failed_gaps"] or 0,
            last_run_at=self._parse_datetime(row["last_run_at"]),
            next_run_at=self._parse_datetime(row["next_run_at"]),
            created_at=self._parse_datetime(row["created_at"]) or datetime.utcnow(),
            updated_at=self._parse_datetime(row["updated_at"]) or datetime.utcnow(),
        )

    async def upsert_backfill_schedule(self, schedule: BackfillSchedule) -> None:
        """Create or update backfill schedule."""
        channels_json = json.dumps(schedule.channels) if schedule.channels else None

        await self.connection.execute(
            """
            INSERT INTO backfill_schedules (
                id, guild_id, platform, channels, priority_mode, rate_limit,
                enabled, paused, total_gaps, completed_gaps, failed_gaps,
                last_run_at, next_run_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, platform) DO UPDATE SET
                channels = excluded.channels,
                priority_mode = excluded.priority_mode,
                rate_limit = excluded.rate_limit,
                enabled = excluded.enabled,
                paused = excluded.paused,
                total_gaps = excluded.total_gaps,
                completed_gaps = excluded.completed_gaps,
                failed_gaps = excluded.failed_gaps,
                last_run_at = excluded.last_run_at,
                next_run_at = excluded.next_run_at,
                updated_at = excluded.updated_at
            """,
            (
                schedule.id,
                schedule.guild_id,
                schedule.platform,
                channels_json,
                schedule.priority_mode,
                schedule.rate_limit,
                schedule.enabled,
                schedule.paused,
                schedule.total_gaps,
                schedule.completed_gaps,
                schedule.failed_gaps,
                self._format_datetime(schedule.last_run_at),
                self._format_datetime(schedule.next_run_at),
                self._format_datetime(schedule.created_at),
                self._format_datetime(schedule.updated_at),
            ),
        )

    async def update_backfill_progress(
        self,
        guild_id: str,
        platform: str,
        completed_increment: int = 0,
        failed_increment: int = 0,
    ) -> None:
        """Update backfill progress counters."""
        await self.connection.execute(
            """
            UPDATE backfill_schedules
            SET completed_gaps = completed_gaps + ?,
                failed_gaps = failed_gaps + ?,
                last_run_at = datetime('now'),
                updated_at = datetime('now')
            WHERE guild_id = ? AND platform = ?
            """,
            (completed_increment, failed_increment, guild_id, platform),
        )

    async def delete_backfill_schedule(self, guild_id: str, platform: str = "discord") -> None:
        """Delete backfill schedule."""
        await self.connection.execute(
            "DELETE FROM backfill_schedules WHERE guild_id = ? AND platform = ?",
            (guild_id, platform),
        )

    # =========================================================================
    # Summary Helpers
    # =========================================================================

    async def get_coverage_summary(self, guild_id: str, platform: str = "discord") -> dict:
        """Get summary statistics for coverage."""
        coverage = await self.get_coverage(guild_id, platform)

        if not coverage:
            return {
                "total_channels": 0,
                "covered_channels": 0,
                "total_coverage_percent": 0,
                "total_gaps": 0,
                "total_summaries": 0,
            }

        total_channels = len(coverage)
        covered_channels = sum(1 for c in coverage if c.coverage_percent > 0)
        total_gaps = sum(c.gap_count for c in coverage)
        total_summaries = sum(c.summary_count for c in coverage)

        # Weighted average by total days
        total_days_sum = sum(c.total_days for c in coverage)
        if total_days_sum > 0:
            weighted_coverage = sum(c.coverage_percent * c.total_days for c in coverage) / total_days_sum
        else:
            weighted_coverage = 0

        return {
            "total_channels": total_channels,
            "covered_channels": covered_channels,
            "total_coverage_percent": round(weighted_coverage, 1),
            "total_gaps": total_gaps,
            "total_summaries": total_summaries,
        }
