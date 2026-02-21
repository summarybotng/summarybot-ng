"""
Scope resolver utility for channel resolution.

ADR-011: Unified Scope Selection
Provides shared channel resolution logic for all summary types.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

import discord
from fastapi import HTTPException

from ..models import SummaryScope

logger = logging.getLogger(__name__)


@dataclass
class CategoryInfo:
    """Information about a Discord category."""
    id: str
    name: str
    channel_count: int
    channels: List[dict]  # List of {id, name} dicts


@dataclass
class ResolvedScope:
    """Result of scope resolution."""
    channels: List[discord.TextChannel]
    scope: SummaryScope
    category_info: Optional[CategoryInfo] = None
    channel_ids: Optional[List[str]] = None


async def resolve_channels_for_scope(
    guild: discord.Guild,
    scope: SummaryScope,
    channel_ids: Optional[List[str]] = None,
    category_id: Optional[str] = None,
    enabled_channels: Optional[List[str]] = None,
) -> ResolvedScope:
    """
    Resolve the list of channels based on scope.

    Args:
        guild: Discord guild object
        scope: The scope type (channel, category, guild)
        channel_ids: Explicit channel IDs (for CHANNEL scope)
        category_id: Category ID (for CATEGORY scope)
        enabled_channels: List of enabled channel IDs from config (for GUILD scope)

    Returns:
        ResolvedScope with list of text channels and metadata

    Raises:
        HTTPException: If required parameters are missing or invalid
    """
    if scope == SummaryScope.CHANNEL:
        return await _resolve_channel_scope(guild, channel_ids)
    elif scope == SummaryScope.CATEGORY:
        return await _resolve_category_scope(guild, category_id)
    elif scope == SummaryScope.GUILD:
        return await _resolve_guild_scope(guild, enabled_channels)
    else:
        raise HTTPException(400, f"Unknown scope: {scope}")


async def _resolve_channel_scope(
    guild: discord.Guild,
    channel_ids: Optional[List[str]],
) -> ResolvedScope:
    """Resolve CHANNEL scope - explicit channel list."""
    if not channel_ids:
        raise HTTPException(400, "channel_ids required for CHANNEL scope")

    channels = []
    invalid_ids = []

    for cid in channel_ids:
        channel = guild.get_channel(int(cid))
        if channel and isinstance(channel, discord.TextChannel):
            if channel.permissions_for(guild.me).read_message_history:
                channels.append(channel)
            else:
                logger.warning(f"No read_message_history permission for channel {cid}")
        else:
            invalid_ids.append(cid)

    if invalid_ids:
        logger.warning(f"Invalid channel IDs: {invalid_ids}")

    if not channels:
        raise HTTPException(400, "No valid accessible channels found")

    return ResolvedScope(
        channels=channels,
        scope=SummaryScope.CHANNEL,
        channel_ids=channel_ids,
    )


async def _resolve_category_scope(
    guild: discord.Guild,
    category_id: Optional[str],
) -> ResolvedScope:
    """Resolve CATEGORY scope - all channels in a category."""
    if not category_id:
        raise HTTPException(400, "category_id required for CATEGORY scope")

    category = guild.get_channel(int(category_id))
    if not category:
        raise HTTPException(404, f"Category not found: {category_id}")

    if not isinstance(category, discord.CategoryChannel):
        raise HTTPException(400, f"Channel {category_id} is not a category")

    # Get all text channels in the category that we can read
    channels = [
        ch for ch in category.text_channels
        if ch.permissions_for(guild.me).read_message_history
    ]

    if not channels:
        raise HTTPException(400, f"No accessible text channels in category '{category.name}'")

    category_info = CategoryInfo(
        id=str(category.id),
        name=category.name,
        channel_count=len(channels),
        channels=[{"id": str(ch.id), "name": ch.name} for ch in channels],
    )

    logger.info(f"Resolved category '{category.name}' to {len(channels)} channels")

    return ResolvedScope(
        channels=channels,
        scope=SummaryScope.CATEGORY,
        category_info=category_info,
        channel_ids=[str(ch.id) for ch in channels],
    )


async def _resolve_guild_scope(
    guild: discord.Guild,
    enabled_channels: Optional[List[str]] = None,
) -> ResolvedScope:
    """Resolve GUILD scope - all enabled/accessible channels in the server."""
    if enabled_channels:
        # Use enabled channels from config
        channels = []
        for cid in enabled_channels:
            channel = guild.get_channel(int(cid))
            if channel and isinstance(channel, discord.TextChannel):
                if channel.permissions_for(guild.me).read_message_history:
                    channels.append(channel)
    else:
        # Fall back to all accessible text channels
        channels = [
            ch for ch in guild.text_channels
            if ch.permissions_for(guild.me).read_message_history
        ]

    if not channels:
        raise HTTPException(400, "No accessible text channels in server")

    logger.info(f"Resolved guild scope to {len(channels)} channels")

    return ResolvedScope(
        channels=channels,
        scope=SummaryScope.GUILD,
        channel_ids=[str(ch.id) for ch in channels],
    )


async def get_category_info(guild: discord.Guild, category_id: str) -> CategoryInfo:
    """
    Get information about a category including its channels.

    Args:
        guild: Discord guild object
        category_id: Category ID

    Returns:
        CategoryInfo with channel details
    """
    category = guild.get_channel(int(category_id))
    if not category or not isinstance(category, discord.CategoryChannel):
        raise HTTPException(404, f"Category not found: {category_id}")

    channels = [
        ch for ch in category.text_channels
        if ch.permissions_for(guild.me).read_message_history
    ]

    return CategoryInfo(
        id=str(category.id),
        name=category.name,
        channel_count=len(channels),
        channels=[{"id": str(ch.id), "name": ch.name} for ch in channels],
    )


def get_scope_display_name(
    scope: SummaryScope,
    channel_names: Optional[List[str]] = None,
    category_name: Optional[str] = None,
    guild_name: Optional[str] = None,
) -> str:
    """
    Generate a human-readable display name for a scope.

    Args:
        scope: The scope type
        channel_names: List of channel names (for CHANNEL scope)
        category_name: Category name (for CATEGORY scope)
        guild_name: Guild name (for GUILD scope)

    Returns:
        Human-readable scope description
    """
    if scope == SummaryScope.CHANNEL:
        if channel_names:
            if len(channel_names) == 1:
                return f"#{channel_names[0]}"
            elif len(channel_names) <= 3:
                return ", ".join(f"#{n}" for n in channel_names)
            else:
                return f"{len(channel_names)} channels"
        return "Selected channels"
    elif scope == SummaryScope.CATEGORY:
        return f"Category: {category_name}" if category_name else "Category"
    elif scope == SummaryScope.GUILD:
        return f"Server: {guild_name}" if guild_name else "Entire server"
    return str(scope)
