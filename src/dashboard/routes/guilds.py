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
from . import get_discord_bot, get_config_manager, get_config_repository, get_summary_repository, get_task_repository, get_webhook_repository, get_feed_repository, get_channel_settings_repository, get_audit_repository
from ...data.base import SearchCriteria

logger = logging.getLogger(__name__)

router = APIRouter()


def _is_channel_locked(channel, guild) -> bool:
    """
    Check if a channel is "locked down" (restricted access).

    A channel is considered locked if @everyone lacks:
    - VIEW_CHANNEL permission, or
    - READ_MESSAGE_HISTORY permission

    Per ADR-073, locked channels should be disabled by default.
    """
    try:
        everyone_role = guild.default_role
        overwrites = channel.overwrites_for(everyone_role)

        # Check for explicit denies
        if overwrites.view_channel is False:
            return True
        if overwrites.read_message_history is False:
            return True

        # Also check category-level restrictions
        if channel.category:
            cat_overwrites = channel.category.overwrites_for(everyone_role)
            if cat_overwrites.view_channel is False:
                return True
            if cat_overwrites.read_message_history is False:
                return True

        return False
    except Exception as e:
        logger.warning(f"Error checking channel lock status: {e}")
        return False


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
    user_guilds = user.get("guilds", [])
    for guild_id in user_guilds:
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
                summary_count = await stored_repo.count_by_guild(guild_id=guild_id)
                if summary_count > 0:
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

    # Get enabled channels from guild_config (legacy) and channel_settings (new ADR-073)
    enabled_channels_legacy = set(guild_config.enabled_channels if guild_config else [])
    excluded_channels = guild_config.excluded_channels if guild_config else []

    # Get channel settings from ADR-073 table
    channel_settings_repo = await get_channel_settings_repository()
    channel_settings_map = {}
    if channel_settings_repo:
        settings_list = await channel_settings_repo.get_guild_settings(guild_id)
        channel_settings_map = {s.channel_id: s for s in settings_list}

    # Build channel list
    channels = []
    categories = {}
    settings_to_save = []  # New settings to persist

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
        channel_id_str = str(channel.id)
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

        # Check locked status
        is_locked = _is_channel_locked(channel, guild)

        # Determine enabled state from channel_settings or fallback to legacy
        settings = channel_settings_map.get(channel_id_str)
        if settings:
            # Use persistent channel settings
            enabled = settings.enabled
            locked_override = settings.locked_override
        else:
            # Fallback to legacy enabled_channels, but locked channels default to disabled
            if is_locked:
                enabled = False  # Locked channels disabled by default (ADR-073)
                locked_override = False
            else:
                enabled = channel_id_str in enabled_channels_legacy
                locked_override = False

            # Create initial settings record for new channels
            from ...data.sqlite.channel_settings_repository import ChannelSettings
            settings_to_save.append(ChannelSettings(
                guild_id=guild_id,
                channel_id=channel_id_str,
                platform="discord",
                enabled=enabled,
                is_locked=is_locked,
                locked_override=False,
                wiki_visible=not is_locked,  # Locked channels not wiki-visible by default
            ))

        channels.append(
            ChannelResponse(
                id=channel_id_str,
                name=channel.name,
                type="text",
                category=category_name,
                enabled=enabled,
                is_locked=is_locked,
                locked_override=locked_override,
            )
        )

    # Persist new channel settings
    if settings_to_save and channel_settings_repo:
        await channel_settings_repo.bulk_upsert_settings(settings_to_save)

    # Build category list
    category_list = [
        CategoryResponse(
            id=cat["id"],
            name=cat["name"],
            channel_count=cat["channel_count"],
        )
        for cat in categories.values()
    ]

    # Build config response - use the actual enabled channels from channel list
    enabled_channel_ids = [c.id for c in channels if c.enabled]
    default_opts = guild_config.default_summary_options if guild_config else None
    config_response = GuildConfigResponse(
        enabled_channels=enabled_channel_ids,
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
        import asyncio
        from ...models.stored_summary import SummarySource
        week_ago = utc_now_naive() - timedelta(days=7)

        # Use count queries instead of fetching all objects
        count_results = await asyncio.gather(
            stored_repo.count_by_guild(guild_id=guild_id),
            stored_repo.count_by_guild(guild_id=guild_id, created_after=week_ago),
            stored_repo.find_by_guild(guild_id=guild_id, limit=1, sort_by="created_at", sort_order="desc"),
        )
        total_summaries = count_results[0]
        summaries_this_week = count_results[1]
        recent = count_results[2]
        if recent:
            last_summary_at = recent[0].created_at

        # Count by source type if there are summaries
        if total_summaries > 0:
            source_counts = await asyncio.gather(
                stored_repo.count_by_guild(guild_id=guild_id, source=SummarySource.REALTIME.value),
                stored_repo.count_by_guild(guild_id=guild_id, source=SummarySource.ARCHIVE.value),
                stored_repo.count_by_guild(guild_id=guild_id, source=SummarySource.SCHEDULED.value),
                stored_repo.count_by_guild(guild_id=guild_id, source=SummarySource.MANUAL.value),
            )
            realtime_count = source_counts[0]
            archive_count = source_counts[1]
            scheduled_count = source_counts[2]
            manual_count = source_counts[3]

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

        # Also persist to channel_settings table (ADR-073)
        channel_settings_repo = await get_channel_settings_repository()
        if channel_settings_repo:
            # Get current settings to check for locked channel overrides
            current_settings = await channel_settings_repo.get_guild_settings(guild_id)
            settings_by_id = {s.channel_id: s for s in current_settings}

            enabled_set = set(body.enabled_channels)
            from ...data.sqlite.channel_settings_repository import ChannelSettings
            settings_to_save = []
            locked_overrides = []

            for channel_id in enabled_set:
                existing = settings_by_id.get(channel_id)
                if existing:
                    # Check if enabling a locked channel (requires audit)
                    if existing.is_locked and not existing.locked_override:
                        locked_overrides.append(channel_id)
                        settings_to_save.append(ChannelSettings(
                            guild_id=guild_id,
                            channel_id=channel_id,
                            platform="discord",
                            enabled=True,
                            is_locked=True,
                            locked_override=True,
                            locked_override_by=user.get("id"),
                            locked_override_at=datetime.utcnow(),
                            wiki_visible=existing.wiki_visible,
                        ))
                    elif existing.enabled != True:
                        existing.enabled = True
                        settings_to_save.append(existing)
                else:
                    # New channel being enabled
                    settings_to_save.append(ChannelSettings(
                        guild_id=guild_id,
                        channel_id=channel_id,
                        platform="discord",
                        enabled=True,
                    ))

            # Handle disabled channels
            for channel_id, existing in settings_by_id.items():
                if channel_id not in enabled_set and existing.enabled:
                    existing.enabled = False
                    # Clear override if disabling a locked channel
                    if existing.is_locked:
                        existing.locked_override = False
                        existing.locked_override_by = None
                        existing.locked_override_at = None
                    settings_to_save.append(existing)

            if settings_to_save:
                await channel_settings_repo.bulk_upsert_settings(settings_to_save)

            # Log audit events for locked channel overrides
            if locked_overrides:
                audit_repo = await get_audit_repository()
                if audit_repo:
                    from ...models.audit_log import AuditLog, AuditEventCategory, AuditSeverity
                    import secrets
                    for channel_id in locked_overrides:
                        audit_entry = AuditLog(
                            id=secrets.token_hex(16),
                            event_type="LOCKED_CHANNEL_ENABLED",
                            category=AuditEventCategory.SETTINGS,
                            severity=AuditSeverity.WARNING,
                            user_id=user.get("id"),
                            user_name=user.get("username"),
                            guild_id=guild_id,
                            resource_type="channel",
                            resource_id=channel_id,
                            action="enable_locked_channel",
                            details={"warning": "Summarization enabled on locked/private channel"},
                            success=True,
                            timestamp=datetime.utcnow(),
                        )
                        await audit_repo.save(audit_entry)
                        logger.warning(f"Locked channel {channel_id} enabled for summarization by {user.get('username')} in guild {guild_id}")

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
