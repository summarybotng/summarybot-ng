"""
Summary generation helpers (ADR-051).

Provides platform-agnostic helper functions for summary generation.
"""

import logging
from typing import List, Optional, Tuple, Callable
from datetime import datetime

from ..platforms import (
    get_platform_fetcher,
    detect_platform,
    PlatformFetcher,
    FetchResult,
    PlatformContext,
)
from src.models.message import ProcessedMessage
from src.models.summary import SummaryJob

logger = logging.getLogger(__name__)


async def fetch_messages_for_summary(
    guild_id: str,
    channel_ids: List[str],
    start_time: datetime,
    end_time: datetime,
    platform: str = "discord",
    job: Optional[SummaryJob] = None,
    job_repo=None,
) -> Tuple[List[ProcessedMessage], dict, dict, List[tuple]]:
    """
    Fetch messages for summary generation using platform-agnostic fetcher.

    Args:
        guild_id: Guild ID (used for Discord or Slack workspace lookup)
        channel_ids: List of channel IDs to fetch from
        start_time: Start of time range
        end_time: End of time range
        platform: Platform name ("discord" or "slack")
        job: Optional SummaryJob for progress updates
        job_repo: Optional job repository for persisting progress

    Returns:
        Tuple of (messages, channel_names, user_names, errors)

    Raises:
        ValueError: If platform is not available
    """
    fetcher = await get_platform_fetcher(platform, guild_id)
    if not fetcher:
        raise ValueError(f"Platform '{platform}' not available for guild {guild_id}")

    try:
        # Create progress callback
        async def progress_callback(current: int, total: int, message: str):
            if job:
                job.update_progress(current, total, message)
                if job_repo:
                    try:
                        await job_repo.update(job)
                    except Exception:
                        pass

        # Fetch messages
        result = await fetcher.fetch_messages(
            channel_ids=channel_ids,
            start_time=start_time,
            end_time=end_time,
            job_id=job.id if job else None,
            progress_callback=lambda c, t, m: progress_callback(c, t, m) if job else None,
        )

        return (
            result.messages,
            result.channel_names,
            result.user_names,
            result.errors,
        )

    finally:
        await fetcher.close()


async def resolve_channels_for_scope(
    guild_id: str,
    scope: str,
    channel_ids: Optional[List[str]] = None,
    category_id: Optional[str] = None,
    platform: str = "discord",
) -> List[str]:
    """
    Resolve channel IDs based on scope using platform-agnostic fetcher.

    Args:
        guild_id: Guild ID
        scope: "channel", "category", or "guild"/"workspace"
        channel_ids: Required for "channel" scope
        category_id: Required for "category" scope (Discord only)
        platform: Platform name

    Returns:
        List of resolved channel IDs

    Raises:
        ValueError: If platform unavailable or scope invalid
    """
    fetcher = await get_platform_fetcher(platform, guild_id)
    if not fetcher:
        raise ValueError(f"Platform '{platform}' not available for guild {guild_id}")

    try:
        return await fetcher.resolve_channels(
            scope=scope,
            channel_ids=channel_ids,
            category_id=category_id,
        )
    finally:
        await fetcher.close()


async def get_platform_context(
    guild_id: str,
    channel_ids: List[str],
    platform: str = "discord",
) -> PlatformContext:
    """
    Get platform context for summarization.

    Args:
        guild_id: Guild ID
        channel_ids: Channels being summarized
        platform: Platform name

    Returns:
        PlatformContext with server/channel names
    """
    fetcher = await get_platform_fetcher(platform, guild_id)
    if not fetcher:
        raise ValueError(f"Platform '{platform}' not available")

    try:
        return await fetcher.get_context(channel_ids)
    finally:
        await fetcher.close()


def get_archive_source_key(platform: str, server_id: str) -> str:
    """
    Generate archive source key for a platform/server.

    Args:
        platform: Platform name
        server_id: Server/workspace ID

    Returns:
        Key like "discord:123" or "slack:T123"
    """
    return f"{platform}:{server_id}"


async def fetch_messages_for_regeneration(
    guild_id: str,
    channel_ids: List[str],
    start_time: datetime,
    end_time: datetime,
    archive_source_key: Optional[str] = None,
    job: Optional[SummaryJob] = None,
    job_repo=None,
) -> Tuple[List[ProcessedMessage], dict, dict, List[tuple]]:
    """
    Fetch messages for summary regeneration, auto-detecting platform.

    Args:
        guild_id: Guild ID
        channel_ids: Channel IDs from stored summary
        start_time: Original start time
        end_time: Original end time
        archive_source_key: Optional key to detect platform
        job: Optional job for progress
        job_repo: Optional repository for persistence

    Returns:
        Tuple of (messages, channel_names, user_names, errors)
    """
    platform = detect_platform(archive_source_key)
    return await fetch_messages_for_summary(
        guild_id=guild_id,
        channel_ids=channel_ids,
        start_time=start_time,
        end_time=end_time,
        platform=platform,
        job=job,
        job_repo=job_repo,
    )
