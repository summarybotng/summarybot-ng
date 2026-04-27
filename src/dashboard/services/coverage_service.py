"""
Content Coverage Service (ADR-072)

Computes and tracks what percentage of server content has been summarized.
"""

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Tuple


def _make_naive(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert timezone-aware datetime to naive (UTC) for comparison."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt

from ...data.repositories import get_coverage_repository, get_stored_summary_repository
from ...data.sqlite.coverage_repository import (
    ChannelCoverage,
    CoverageGap,
    BackfillSchedule,
    SQLiteCoverageRepository,
)

logger = logging.getLogger(__name__)


@dataclass
class ChannelInventory:
    """Inventory of content in a channel."""
    channel_id: str
    channel_name: str
    earliest_message: Optional[datetime]
    latest_message: Optional[datetime]
    estimated_messages: int
    accessible: bool


@dataclass
class GuildInventory:
    """Inventory of content in a guild."""
    guild_id: str
    platform: str
    channels: List[ChannelInventory]
    earliest_content: Optional[datetime]
    latest_content: Optional[datetime]
    inventory_date: datetime


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
    total_summaries: int
    earliest_content: Optional[datetime]
    latest_content: Optional[datetime]
    computed_at: datetime


class CoverageService:
    """Service for computing and managing content coverage."""

    def __init__(self):
        self._repo: Optional[SQLiteCoverageRepository] = None

    async def _get_repo(self) -> SQLiteCoverageRepository:
        if not self._repo:
            self._repo = await get_coverage_repository()
        return self._repo

    async def get_discord_inventory(
        self,
        guild_id: str,
        bot_client,
    ) -> GuildInventory:
        """Get content inventory from Discord."""
        import discord

        guild = bot_client.get_guild(int(guild_id))
        if not guild:
            try:
                guild = await bot_client.fetch_guild(int(guild_id))
            except (discord.NotFound, discord.Forbidden):
                return GuildInventory(
                    guild_id=guild_id,
                    platform="discord",
                    channels=[],
                    earliest_content=None,
                    latest_content=None,
                    inventory_date=datetime.utcnow(),
                )

        channels = []
        earliest_overall = None
        latest_overall = None

        for channel in guild.text_channels:
            # Check if we can access
            permissions = channel.permissions_for(guild.me)
            if not permissions.read_message_history:
                channels.append(ChannelInventory(
                    channel_id=str(channel.id),
                    channel_name=channel.name,
                    earliest_message=None,
                    latest_message=None,
                    estimated_messages=0,
                    accessible=False,
                ))
                continue

            # Get latest message (fast)
            latest_msg = None
            try:
                async for msg in channel.history(limit=1):
                    latest_msg = msg
            except discord.Forbidden:
                channels.append(ChannelInventory(
                    channel_id=str(channel.id),
                    channel_name=channel.name,
                    earliest_message=None,
                    latest_message=None,
                    estimated_messages=0,
                    accessible=False,
                ))
                continue

            # Get earliest message (slower - sample approach)
            earliest_msg = None
            try:
                async for msg in channel.history(limit=1, oldest_first=True):
                    earliest_msg = msg
            except discord.Forbidden:
                pass

            earliest = earliest_msg.created_at if earliest_msg else None
            latest = latest_msg.created_at if latest_msg else None

            # Estimate message count based on time range and typical activity
            estimated = 0
            if earliest and latest:
                days = (latest - earliest).days + 1
                estimated = days * 50  # Rough estimate: 50 messages/day

            channels.append(ChannelInventory(
                channel_id=str(channel.id),
                channel_name=channel.name,
                earliest_message=earliest,
                latest_message=latest,
                estimated_messages=estimated,
                accessible=True,
            ))

            if earliest:
                if not earliest_overall or earliest < earliest_overall:
                    earliest_overall = earliest
            if latest:
                if not latest_overall or latest > latest_overall:
                    latest_overall = latest

        return GuildInventory(
            guild_id=guild_id,
            platform="discord",
            channels=channels,
            earliest_content=earliest_overall,
            latest_content=latest_overall,
            inventory_date=datetime.utcnow(),
        )

    async def compute_coverage(
        self,
        guild_id: str,
        platform: str = "discord",
        inventory: Optional[GuildInventory] = None,
    ) -> CoverageReport:
        """Compute coverage for a guild based on existing summaries."""
        repo = await self._get_repo()
        stored_repo = await get_stored_summary_repository()

        # Get all summaries for this guild
        summaries = await stored_repo.find_by_guild(guild_id, limit=10000)

        # Track unique summaries with valid time ranges for the total count
        unique_summary_ids_with_time: set = set()

        # Build a map of channel -> summary ranges
        channel_summaries: dict = {}
        for summary in summaries:
            for channel_id in (summary.source_channel_ids or []):
                if channel_id not in channel_summaries:
                    channel_summaries[channel_id] = []
                # Access start_time/end_time from the nested summary_result (normalize to naive)
                if summary.summary_result and summary.summary_result.start_time and summary.summary_result.end_time:
                    start = _make_naive(summary.summary_result.start_time)
                    end = _make_naive(summary.summary_result.end_time)
                    channel_summaries[channel_id].append((start, end))
                    unique_summary_ids_with_time.add(summary.id)

        # Get channel info from inventory or existing coverage
        if inventory:
            channel_info = {c.channel_id: c for c in inventory.channels}
        else:
            existing_coverage = await repo.get_coverage(guild_id, platform)
            channel_info = {c.channel_id: c for c in existing_coverage}

        # Compute coverage for each channel
        coverage_results = []
        all_gaps = []
        now = datetime.utcnow()

        # Process channels with summaries
        for channel_id, ranges in channel_summaries.items():
            info = channel_info.get(channel_id)
            channel_name = info.channel_name if info else None

            # Sort ranges by start time
            ranges.sort(key=lambda r: r[0])

            # Merge overlapping ranges
            merged = []
            for start, end in ranges:
                if merged and start <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], end))
                else:
                    merged.append((start, end))

            # Compute coverage metrics
            covered_start = merged[0][0] if merged else None
            covered_end = merged[-1][1] if merged else None

            # Determine content boundaries
            if info and hasattr(info, 'earliest_message') and info.earliest_message:
                content_start = info.earliest_message
            elif info and hasattr(info, 'content_start') and info.content_start:
                content_start = info.content_start
            else:
                content_start = covered_start

            if info and hasattr(info, 'latest_message') and info.latest_message:
                content_end = info.latest_message
            elif info and hasattr(info, 'content_end') and info.content_end:
                content_end = info.content_end
            else:
                content_end = covered_end or now

            # Calculate days
            if content_start and content_end:
                total_days = (content_end - content_start).days + 1
            else:
                total_days = 0

            covered_days = sum((end - start).days + 1 for start, end in merged)
            coverage_pct = (covered_days / total_days * 100) if total_days > 0 else 0

            # Find gaps
            gaps = []
            if content_start and merged:
                # Gap before first summary
                if merged[0][0] > content_start:
                    gaps.append((content_start, merged[0][0] - timedelta(days=1)))

                # Gaps between summaries
                for i in range(len(merged) - 1):
                    gap_start = merged[i][1] + timedelta(days=1)
                    gap_end = merged[i + 1][0] - timedelta(days=1)
                    if gap_end > gap_start:
                        gaps.append((gap_start, gap_end))

                # Gap after last summary
                if content_end and merged[-1][1] < content_end:
                    gaps.append((merged[-1][1] + timedelta(days=1), content_end))

            # Create gap records
            for gap_start, gap_end in gaps:
                gap_days = (gap_end - gap_start).days + 1
                if gap_days > 0:
                    all_gaps.append(CoverageGap(
                        id=secrets.token_hex(8),
                        guild_id=guild_id,
                        channel_id=channel_id,
                        channel_name=channel_name,
                        platform=platform,
                        gap_start=gap_start,
                        gap_end=gap_end,
                        gap_days=gap_days,
                        status="pending",
                        priority=gap_days,  # Larger gaps get higher priority
                        job_id=None,
                        summary_id=None,
                        error_message=None,
                        scheduled_for=None,
                        started_at=None,
                        completed_at=None,
                        created_at=now,
                    ))

            coverage = ChannelCoverage(
                id=secrets.token_hex(8),
                guild_id=guild_id,
                channel_id=channel_id,
                channel_name=channel_name,
                platform=platform,
                content_start=content_start,
                content_end=content_end,
                estimated_messages=info.estimated_messages if info and hasattr(info, 'estimated_messages') else 0,
                covered_start=covered_start,
                covered_end=covered_end,
                summary_count=len(ranges),
                coverage_percent=round(coverage_pct, 1),
                gap_count=len(gaps),
                covered_days=covered_days,
                total_days=total_days,
                last_summary_at=covered_end,
                last_computed_at=now,
            )
            coverage_results.append(coverage)

            # Save to database
            await repo.upsert_coverage(coverage)

        # Add channels from inventory that have no summaries
        if inventory:
            for inv_channel in inventory.channels:
                if inv_channel.channel_id not in channel_summaries and inv_channel.accessible:
                    if inv_channel.earliest_message and inv_channel.latest_message:
                        total_days = (inv_channel.latest_message - inv_channel.earliest_message).days + 1

                        # The entire channel is a gap
                        all_gaps.append(CoverageGap(
                            id=secrets.token_hex(8),
                            guild_id=guild_id,
                            channel_id=inv_channel.channel_id,
                            channel_name=inv_channel.channel_name,
                            platform=platform,
                            gap_start=inv_channel.earliest_message,
                            gap_end=inv_channel.latest_message,
                            gap_days=total_days,
                            status="pending",
                            priority=total_days,
                            job_id=None,
                            summary_id=None,
                            error_message=None,
                            scheduled_for=None,
                            started_at=None,
                            completed_at=None,
                            created_at=now,
                        ))

                        coverage = ChannelCoverage(
                            id=secrets.token_hex(8),
                            guild_id=guild_id,
                            channel_id=inv_channel.channel_id,
                            channel_name=inv_channel.channel_name,
                            platform=platform,
                            content_start=inv_channel.earliest_message,
                            content_end=inv_channel.latest_message,
                            estimated_messages=inv_channel.estimated_messages,
                            covered_start=None,
                            covered_end=None,
                            summary_count=0,
                            coverage_percent=0,
                            gap_count=1,
                            covered_days=0,
                            total_days=total_days,
                            last_summary_at=None,
                            last_computed_at=now,
                        )
                        coverage_results.append(coverage)
                        await repo.upsert_coverage(coverage)

        # Clear old gaps and save new ones
        await repo.delete_gaps_for_guild(guild_id, platform)
        for gap in all_gaps:
            await repo.create_gap(gap)

        # Compute totals
        total_channels = len(coverage_results)
        covered_channels = sum(1 for c in coverage_results if c.coverage_percent > 0)
        # Use unique summary count, not sum of per-channel counts (a summary covering 10 channels should count as 1)
        total_summaries = len(unique_summary_ids_with_time)
        total_days_sum = sum(c.total_days for c in coverage_results)

        if total_days_sum > 0:
            total_coverage = sum(c.coverage_percent * c.total_days for c in coverage_results) / total_days_sum
        else:
            total_coverage = 0

        # Normalize datetimes to naive for comparison (some may be timezone-aware)
        earliest = min((_make_naive(c.content_start) for c in coverage_results if c.content_start), default=None)
        latest = max((_make_naive(c.content_end) for c in coverage_results if c.content_end), default=None)

        return CoverageReport(
            guild_id=guild_id,
            platform=platform,
            channels=coverage_results,
            total_coverage_percent=round(total_coverage, 1),
            total_gaps=len(all_gaps),
            total_channels=total_channels,
            covered_channels=covered_channels,
            total_summaries=total_summaries,
            earliest_content=earliest,
            latest_content=latest,
            computed_at=now,
        )

    async def get_coverage_report(
        self,
        guild_id: str,
        platform: str = "discord",
    ) -> Optional[CoverageReport]:
        """Get existing coverage report from database."""
        repo = await self._get_repo()
        coverage = await repo.get_coverage(guild_id, platform)

        if not coverage:
            return None

        summary = await repo.get_coverage_summary(guild_id, platform)

        # Normalize datetimes to naive for comparison
        earliest = min((_make_naive(c.content_start) for c in coverage if c.content_start), default=None)
        latest = max((_make_naive(c.content_end) for c in coverage if c.content_end), default=None)
        last_computed = max((_make_naive(c.last_computed_at) for c in coverage if c.last_computed_at), default=datetime.utcnow())

        return CoverageReport(
            guild_id=guild_id,
            platform=platform,
            channels=coverage,
            total_coverage_percent=summary["total_coverage_percent"],
            total_gaps=summary["total_gaps"],
            total_channels=summary["total_channels"],
            covered_channels=summary["covered_channels"],
            total_summaries=summary["total_summaries"],
            earliest_content=earliest,
            latest_content=latest,
            computed_at=last_computed,
        )

    async def get_gaps(
        self,
        guild_id: str,
        platform: str = "discord",
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[CoverageGap], int]:
        """Get coverage gaps."""
        repo = await self._get_repo()
        return await repo.get_gaps(guild_id, platform, status=status, limit=limit, offset=offset)

    async def start_backfill(
        self,
        guild_id: str,
        platform: str = "discord",
        channels: Optional[List[str]] = None,
        priority_mode: str = "oldest_first",
        rate_limit: int = 10,
    ) -> BackfillSchedule:
        """Start or update a backfill schedule."""
        repo = await self._get_repo()
        now = datetime.utcnow()

        # Get existing gaps count
        _, total_gaps = await repo.get_gaps(guild_id, platform, status="pending")

        schedule = BackfillSchedule(
            id=secrets.token_hex(8),
            guild_id=guild_id,
            platform=platform,
            channels=channels or [],
            priority_mode=priority_mode,
            rate_limit=rate_limit,
            enabled=True,
            paused=False,
            total_gaps=total_gaps,
            completed_gaps=0,
            failed_gaps=0,
            last_run_at=None,
            next_run_at=now,
            created_at=now,
            updated_at=now,
        )

        await repo.upsert_backfill_schedule(schedule)
        return schedule

    async def get_backfill_status(
        self,
        guild_id: str,
        platform: str = "discord",
    ) -> Optional[BackfillSchedule]:
        """Get backfill schedule status."""
        repo = await self._get_repo()
        return await repo.get_backfill_schedule(guild_id, platform)

    async def pause_backfill(self, guild_id: str, platform: str = "discord") -> None:
        """Pause backfill."""
        repo = await self._get_repo()
        schedule = await repo.get_backfill_schedule(guild_id, platform)
        if schedule:
            schedule.paused = True
            schedule.updated_at = datetime.utcnow()
            await repo.upsert_backfill_schedule(schedule)

    async def resume_backfill(self, guild_id: str, platform: str = "discord") -> None:
        """Resume backfill."""
        repo = await self._get_repo()
        schedule = await repo.get_backfill_schedule(guild_id, platform)
        if schedule:
            schedule.paused = False
            schedule.next_run_at = datetime.utcnow()
            schedule.updated_at = datetime.utcnow()
            await repo.upsert_backfill_schedule(schedule)

    async def cancel_backfill(self, guild_id: str, platform: str = "discord") -> None:
        """Cancel backfill."""
        repo = await self._get_repo()
        await repo.delete_backfill_schedule(guild_id, platform)


# Singleton instance
_coverage_service: Optional[CoverageService] = None


def get_coverage_service() -> CoverageService:
    """Get the coverage service singleton."""
    global _coverage_service
    if _coverage_service is None:
        _coverage_service = CoverageService()
    return _coverage_service
