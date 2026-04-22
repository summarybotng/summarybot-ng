"""
Channel privacy detection utilities (ADR-046).

Detects channels that are not visible to @everyone role.
"""

import discord
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)


async def detect_private_channels(guild: discord.Guild) -> List[str]:
    """Detect channels that are not visible to @everyone.

    Args:
        guild: Discord guild object

    Returns:
        List of channel IDs that are private (not visible to @everyone)
    """
    everyone_role = guild.default_role
    private_channels = []

    for channel in guild.channels:
        if isinstance(channel, discord.TextChannel):
            perms = channel.permissions_for(everyone_role)
            if not perms.view_channel:
                private_channels.append(str(channel.id))

    return private_channels


async def check_channels_privacy(
    guild: discord.Guild,
    channel_ids: List[str]
) -> List[Dict]:
    """Check if specific channels are private.

    Args:
        guild: Discord guild object
        channel_ids: List of channel IDs to check

    Returns:
        List of warning dicts for private channels
    """
    everyone_role = guild.default_role
    warnings = []

    for channel_id in channel_ids:
        channel = guild.get_channel(int(channel_id))
        if channel and isinstance(channel, discord.TextChannel):
            perms = channel.permissions_for(everyone_role)
            if not perms.view_channel:
                warnings.append({
                    "channel_id": channel_id,
                    "channel_name": channel.name,
                    "warning": "This channel is not visible to @everyone. "
                              "Summaries will be visible to all dashboard users."
                })

    return warnings


def is_channel_in_sensitive_category(
    channel: discord.TextChannel,
    sensitive_categories: List[str]
) -> bool:
    """Check if a channel's category is marked as sensitive.

    Args:
        channel: Discord text channel
        sensitive_categories: List of sensitive category IDs

    Returns:
        True if channel's category is in the sensitive list
    """
    if channel.category_id:
        return str(channel.category_id) in sensitive_categories
    return False
