"""
Guild routes for dashboard API.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import discord
from fastapi import APIRouter, Depends, HTTPException, Path

from ..auth import get_current_user
from src.utils.time import utc_now_naive
from ..models import (
    GuildsResponse,
    GuildListItem,
    GuildDetailResponse,
    ChannelResponse,
    CategoryResponse,
    GuildConfigResponse,
    GuildStatsResponse,
    SummaryOptionsResponse,
    ConfigUpdateRequest,
    ChannelSyncResponse,
    ConfigStatus,
    ErrorResponse,
)
from . import get_discord_bot, get_config_manager, get_config_repository, get_summary_repository, get_task_repository, get_webhook_repository, get_feed_repository
from ...data.base import SearchCriteria

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_guild_or_404(guild_id: str):
    """Get guild from bot or raise 404."""
    bot = get_discord_bot()
    if not bot or not bot.client:
        raise HTTPException(
            status_code=503,
            detail={"code": "BOT_UNAVAILABLE", "message": "Discord bot not available"},
        )

    guild = bot.client.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Guild not found"},
        )

    return guild


def _check_guild_access(guild_id: str, user: dict):
    """Check user has access to guild."""
    if guild_id not in user.get("guilds", []):
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "You don't have permission to manage this guild"},
        )


@router.get(
    "/debug",
    summary="Debug endpoint",
    include_in_schema=False,
)
async def debug_guilds(user: dict = Depends(get_current_user)):
    """Simple debug endpoint to test router."""
    return {"status": "ok", "user_guilds_count": len(user.get("guilds", []))}


@router.get(
    "",
    response_model=GuildsResponse,
    summary="List manageable guilds",
    description="Get all guilds the user can manage.",
)
async def list_guilds(user: dict = Depends(get_current_user)):
    """List guilds user can manage."""
    # Wrap entire function in try/except to catch any errors and return useful response
    try:
        bot = get_discord_bot()
        config_repo = await get_config_repository()
        config_manager = get_config_manager()
        # Use stored_summary_repository which includes both realtime and archive summaries
        from . import get_stored_summary_repository
        stored_repo = await get_stored_summary_repository()

        # Get repositories for counts
        task_repo = await get_task_repository()
        webhook_repo = await get_webhook_repository()
        feed_repo = await get_feed_repository()
    except Exception as e:
        logger.error(f"Failed to initialize repositories for list_guilds: {e}", exc_info=True)
        # Return empty list rather than 500 error
        return GuildsResponse(guilds=[])

    guild_items = []
    for guild_id in user.get("guilds", []):
        try:
            guild = bot.client.get_guild(int(guild_id)) if bot and bot.client else None
            if not guild:
                continue

            # Get config status - check database first, then in-memory
            config_status = ConfigStatus.NEEDS_SETUP
            guild_config = None

            if config_repo:
                guild_config = await config_repo.get_guild_config(guild_id)

            if not guild_config and config_manager:
                current_config = config_manager.get_current_config()
                if current_config:
                    guild_config = current_config.guild_configs.get(guild_id)

            if guild_config and guild_config.enabled_channels:
                config_status = ConfigStatus.CONFIGURED

            # Get actual summary count and last summary from stored summaries
            # This includes both realtime and archive summaries
            summary_count = 0
            last_summary_at = None
            if stored_repo:
                all_summaries = await stored_repo.find_by_guild(guild_id=guild_id, limit=10000)
                summary_count = len(all_summaries)
                if summary_count > 0:
                    # Get most recent by created_at
                    recent = await stored_repo.find_by_guild(
                        guild_id=guild_id,
                        limit=1,
                        sort_by="created_at",
                        sort_order="desc",
                    )
                    if recent:
                        last_summary_at = recent[0].created_at

            # Get schedule count (active schedules only)
            schedule_count = 0
            if task_repo:
                try:
                    tasks = await task_repo.get_tasks_by_guild(guild_id)
                    schedule_count = len([t for t in tasks if t.is_active])
                except Exception as e:
                    logger.warning(f"Failed to get schedules for guild {guild_id}: {e}")

            # Get webhook count
            webhook_count = 0
            if webhook_repo:
                try:
                    webhooks = await webhook_repo.get_webhooks_by_guild(guild_id)
                    webhook_count = len(webhooks)
                except Exception as e:
                    logger.warning(f"Failed to get webhooks for guild {guild_id}: {e}")

            # Get feed count
            feed_count = 0
            if feed_repo:
                try:
                    feeds = await feed_repo.get_feeds_by_guild(guild_id)
                    feed_count = len(feeds)
                except Exception as e:
                    logger.warning(f"Failed to get feeds for guild {guild_id}: {e}")

            guild_items.append(
                GuildListItem(
                    id=str(guild.id),
                    name=guild.name,
                    icon_url=str(guild.icon.url) if guild.icon else None,
                    member_count=guild.member_count or 0,
                    summary_count=summary_count,
                    last_summary_at=last_summary_at,
                    config_status=config_status,
                    schedule_count=schedule_count,
                    webhook_count=webhook_count,
                    feed_count=feed_count,
                )
            )
        except Exception as e:
            logger.error(f"Failed to process guild {guild_id}: {e}", exc_info=True)
            continue

    return GuildsResponse(guilds=guild_items)


@router.get(
    "/{guild_id}",
    response_model=GuildDetailResponse,
    summary="Get guild details",
    description="Get detailed information about a guild including channels and configuration.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Guild not found"},
    },
)
async def get_guild(
    guild_id: str = Path(..., description="Discord guild ID"),
    user: dict = Depends(get_current_user),
):
    """Get guild details."""
    _check_guild_access(guild_id, user)
    guild = _get_guild_or_404(guild_id)

    # Get guild config from database first, then in-memory
    config_repo = await get_config_repository()
    config_manager = get_config_manager()

    guild_config = None
    if config_repo:
        guild_config = await config_repo.get_guild_config(guild_id)

    if not guild_config and config_manager:
        current_config = config_manager.get_current_config()
        if current_config:
            guild_config = current_config.guild_configs.get(guild_id)

    enabled_channels = guild_config.enabled_channels if guild_config else []
    excluded_channels = guild_config.excluded_channels if guild_config else []

    # Build channel list
    channels = []
    categories = {}

    # Get text channels - always fetch from Discord API to ensure fresh data
    text_channels = list(guild.text_channels)
    logger.info(f"Guild {guild_id} has {len(text_channels)} cached text channels")

    if len(text_channels) == 0:
        # Channels not in cache, fetch them from Discord API
        logger.warning(f"No text channels in cache for guild {guild_id}, fetching from Discord API")
        try:
            fetched_channels = await guild.fetch_channels()
            text_channels = [ch for ch in fetched_channels if isinstance(ch, discord.TextChannel)]
            logger.info(f"Fetched {len(text_channels)} text channels for guild {guild_id}")
        except Exception as e:
            logger.error(f"Failed to fetch channels for guild {guild_id}: {e}")
            text_channels = []

    for channel in text_channels:
        category_name = channel.category.name if channel.category else None
        category_id = str(channel.category.id) if channel.category else None

        # Track categories
        if category_id and category_id not in categories:
            categories[category_id] = {
                "id": category_id,
                "name": category_name,
                "channel_count": 0,
            }
        if category_id:
            categories[category_id]["channel_count"] += 1

        channels.append(
            ChannelResponse(
                id=str(channel.id),
                name=channel.name,
                type="text",
                category=category_name,
                enabled=str(channel.id) in enabled_channels,
            )
        )

    # Build category list
    category_list = [
        CategoryResponse(
            id=cat["id"],
            name=cat["name"],
            channel_count=cat["channel_count"],
        )
        for cat in categories.values()
    ]

    # Build config response
    default_opts = guild_config.default_summary_options if guild_config else None
    config_response = GuildConfigResponse(
        enabled_channels=enabled_channels,
        excluded_channels=excluded_channels,
        default_options=SummaryOptionsResponse(
            summary_length=default_opts.summary_length.value if default_opts else "detailed",
            perspective="general",
            include_action_items=default_opts.extract_action_items if default_opts else True,
            include_technical_terms=default_opts.extract_technical_terms if default_opts else True,
        ),
    )

    # Get actual stats from database
    # Use stored_summary_repository which includes both realtime and archive summaries
    from . import get_stored_summary_repository
    stored_repo = await get_stored_summary_repository()
    task_repo = await get_task_repository()

    total_summaries = 0
    summaries_this_week = 0
    active_schedules = 0
    last_summary_at = None

    # Breakdown by source type
    realtime_count = 0
    archive_count = 0
    scheduled_count = 0
    manual_count = 0

    if stored_repo:
        # Get total count of all summaries (realtime + archive)
        all_summaries = await stored_repo.find_by_guild(guild_id=guild_id, limit=10000)
        total_summaries = len(all_summaries)

        # Count by source type
        from ...models.stored_summary import SummarySource
        for s in all_summaries:
            if s.source == SummarySource.ARCHIVE:
                archive_count += 1
            elif s.source == SummarySource.SCHEDULED:
                scheduled_count += 1
            elif s.source == SummarySource.MANUAL:
                manual_count += 1
            else:  # REALTIME or others
                realtime_count += 1

        # Get summaries this week
        week_ago = utc_now_naive() - timedelta(days=7)
        week_summaries = await stored_repo.find_by_guild(
            guild_id=guild_id,
            created_after=week_ago,
            limit=10000,
        )
        summaries_this_week = len(week_summaries)

        # Get last summary
        recent = await stored_repo.find_by_guild(
            guild_id=guild_id,
            limit=1,
            sort_by="created_at",
            sort_order="desc",
        )
        if recent:
            last_summary_at = recent[0].created_at

    if task_repo:
        tasks = await task_repo.get_tasks_by_guild(guild_id)
        active_schedules = len([t for t in tasks if t.is_active])

    stats = GuildStatsResponse(
        total_summaries=total_summaries,
        summaries_this_week=summaries_this_week,
        active_schedules=active_schedules,
        last_summary_at=last_summary_at,
        realtime_count=realtime_count,
        archive_count=archive_count,
        scheduled_count=scheduled_count,
        manual_count=manual_count,
    )

    return GuildDetailResponse(
        id=str(guild.id),
        name=guild.name,
        icon_url=str(guild.icon.url) if guild.icon else None,
        member_count=guild.member_count or 0,
        channels=channels,
        categories=category_list,
        config=config_response,
        stats=stats,
    )


@router.patch(
    "/{guild_id}/config",
    response_model=GuildConfigResponse,
    summary="Update guild configuration",
    description="Update channel settings and default options for a guild.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Guild not found"},
    },
)
async def update_config(
    body: ConfigUpdateRequest,
    guild_id: str = Path(..., description="Discord guild ID"),
    user: dict = Depends(get_current_user),
):
    """Update guild configuration."""
    _check_guild_access(guild_id, user)
    _get_guild_or_404(guild_id)  # Verify guild exists

    from ...config.settings import GuildConfig, SummaryLength

    # Get config repository (database-backed) and config manager (in-memory)
    config_repo = await get_config_repository()
    config_manager = get_config_manager()

    # Try to get existing guild config from database first, then in-memory
    guild_config = None
    if config_repo:
        guild_config = await config_repo.get_guild_config(guild_id)

    if not guild_config and config_manager:
        current_config = config_manager.get_current_config()
        if current_config:
            guild_config = current_config.get_guild_config(guild_id)

    # Create new config if none exists
    if not guild_config:
        guild_config = GuildConfig(guild_id=guild_id)

    # Update fields
    if body.enabled_channels is not None:
        guild_config.enabled_channels = body.enabled_channels

    if body.excluded_channels is not None:
        guild_config.excluded_channels = body.excluded_channels

    if body.default_options is not None:
        guild_config.default_summary_options.summary_length = SummaryLength(body.default_options.summary_length)
        guild_config.default_summary_options.extract_action_items = body.default_options.include_action_items
        guild_config.default_summary_options.extract_technical_terms = body.default_options.include_technical_terms

    # Save to database (primary storage)
    if config_repo:
        await config_repo.save_guild_config(guild_config)
        logger.info(f"Saved guild config for {guild_id} to database")
    else:
        logger.warning(f"No config repository available, config not persisted for {guild_id}")

    # Also update in-memory config if available (for immediate effect)
    if config_manager:
        current_config = config_manager.get_current_config()
        if current_config:
            current_config.guild_configs[guild_id] = guild_config

    # Return updated config
    return GuildConfigResponse(
        enabled_channels=guild_config.enabled_channels,
        excluded_channels=guild_config.excluded_channels,
        default_options=SummaryOptionsResponse(
            summary_length=guild_config.default_summary_options.summary_length.value,
            perspective="general",
            include_action_items=guild_config.default_summary_options.extract_action_items,
            include_technical_terms=guild_config.default_summary_options.extract_technical_terms,
        ),
    )


@router.post(
    "/{guild_id}/channels/sync",
    response_model=ChannelSyncResponse,
    summary="Sync channels from Discord",
    description="Refresh the channel list from Discord.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Guild not found"},
    },
)
async def sync_channels(
    guild_id: str = Path(..., description="Discord guild ID"),
    user: dict = Depends(get_current_user),
):
    """Sync channels from Discord."""
    _check_guild_access(guild_id, user)
    guild = _get_guild_or_404(guild_id)

    # Get config from database first, then in-memory
    config_repo = await get_config_repository()
    config_manager = get_config_manager()

    guild_config = None
    if config_repo:
        guild_config = await config_repo.get_guild_config(guild_id)

    if not guild_config and config_manager:
        current_config = config_manager.get_current_config()
        if current_config:
            guild_config = current_config.guild_configs.get(guild_id)

    enabled_channels = set(guild_config.enabled_channels if guild_config else [])

    # Build current channel list - always fetch to ensure fresh data
    try:
        fetched_channels = await guild.fetch_channels()
        text_channels = [ch for ch in fetched_channels if isinstance(ch, discord.TextChannel)]
        logger.info(f"Sync: Fetched {len(text_channels)} text channels for guild {guild_id}")
    except Exception as e:
        logger.error(f"Sync: Failed to fetch channels for guild {guild_id}: {e}")
        text_channels = list(guild.text_channels)

    current_channels = {str(c.id) for c in text_channels}

    # Calculate changes
    # Channels that were enabled but no longer exist
    removed = enabled_channels - current_channels

    # Update enabled channels to remove non-existent ones
    if guild_config and removed:
        guild_config.enabled_channels = [c for c in guild_config.enabled_channels if c not in removed]
        # Save to database
        if config_repo:
            await config_repo.save_guild_config(guild_config)
        # Update in-memory
        if config_manager:
            current_config = config_manager.get_current_config()
            if current_config:
                current_config.guild_configs[guild_id] = guild_config

    # Build channel response
    channels = []
    for channel in text_channels:
        category_name = channel.category.name if channel.category else None
        channels.append(
            ChannelResponse(
                id=str(channel.id),
                name=channel.name,
                type="text",
                category=category_name,
                enabled=str(channel.id) in enabled_channels,
            )
        )

    return ChannelSyncResponse(
        success=True,
        channels_added=0,  # Discord API always has current channels
        channels_removed=len(removed),
        channels=channels,
    )
