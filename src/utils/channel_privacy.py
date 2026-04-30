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


def determine_private_content(
    source_channel_ids: List[str],
    references: List[Dict],
    locked_channel_ids: set,
) -> bool:
    """
    Determine if a summary contains actual content from locked channels (ADR-074).

    Uses refined logic that checks actual content, not just scope:
    1. Check grounded references (most accurate)
    2. Check single-channel scope (certain)
    3. Default to False for multi-channel without references

    Args:
        source_channel_ids: List of channel IDs that were in scope
        references: List of reference dicts from summary_result.references OR
                   summary_result.reference_index (both fields are checked)
        locked_channel_ids: Set of channel IDs that are locked/private

    Returns:
        True if the summary contains actual content from locked channels
    """
    # Priority 1: Check references (most accurate)
    # Note: References may be in 'references' or 'reference_index' field
    if references:
        for ref in references:
            ref_channel_id = ref.get("channel_id")
            if ref_channel_id and ref_channel_id in locked_channel_ids:
                logger.debug(
                    f"Found private content via reference from channel {ref_channel_id}"
                )
                return True
        # Has references but none from locked channels
        return False

    # Priority 2: Single-channel scope (certain)
    if len(source_channel_ids) == 1:
        is_locked = source_channel_ids[0] in locked_channel_ids
        if is_locked:
            logger.debug(
                f"Single-channel summary from locked channel {source_channel_ids[0]}"
            )
        return is_locked

    # Priority 3: Multi-channel without references - cannot determine
    # Default to False to reduce false positives (ADR-074 decision)
    return False


def get_references_from_summary(summary_data: Dict) -> List[Dict]:
    """
    Extract references from summary data, checking both possible field names.

    Args:
        summary_data: The summary_result dict

    Returns:
        List of reference dicts, or empty list if none found
    """
    if not summary_data:
        return []
    # Check both field names - 'references' and 'reference_index'
    return summary_data.get("references") or summary_data.get("reference_index") or []


def get_private_channel_sources(
    references: List[Dict],
    locked_channel_ids: set,
) -> List[str]:
    """
    Get the list of locked channel IDs that contributed content to a summary.

    Args:
        references: List of reference dicts (from summary_result.references)
        locked_channel_ids: Set of channel IDs that are locked/private

    Returns:
        List of locked channel IDs that have references in the summary
    """
    private_sources = set()
    for ref in references or []:
        ref_channel_id = ref.get("channel_id")
        if ref_channel_id and ref_channel_id in locked_channel_ids:
            private_sources.add(ref_channel_id)
    return list(private_sources)


def group_channels_by_privacy(
    channel_ids: List[str],
    locked_channel_ids: set,
) -> Dict[str, List[str]]:
    """
    Group channel IDs into public and private sets (ADR-075).

    Args:
        channel_ids: List of all channel IDs in scope
        locked_channel_ids: Set of channel IDs that are locked/private

    Returns:
        Dict with 'public' and 'private' keys, each containing a list of channel IDs
    """
    public_channels = []
    private_channels = []

    for channel_id in channel_ids:
        if channel_id in locked_channel_ids:
            private_channels.append(channel_id)
        else:
            public_channels.append(channel_id)

    return {
        "public": public_channels,
        "private": private_channels,
    }
