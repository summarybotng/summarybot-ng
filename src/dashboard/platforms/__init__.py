"""
Platform Message Fetcher Abstraction (ADR-051).

Factory functions and exports for platform-agnostic message fetching.
"""

from typing import Optional

from .base import PlatformFetcher
from .types import FetchResult, PlatformContext, ChannelInfo, UserInfo
from .discord_fetcher import DiscordFetcher
from .slack_fetcher import SlackFetcher


async def get_platform_fetcher(
    platform: str,
    guild_id: str,
) -> Optional[PlatformFetcher]:
    """
    Factory to create appropriate platform fetcher.

    Args:
        platform: "discord" or "slack"
        guild_id: Discord guild ID (used for both Discord and Slack workspace linking)

    Returns:
        PlatformFetcher instance or None if platform unavailable
    """
    if platform == "slack":
        from src.data.repositories import get_slack_repository
        slack_repo = await get_slack_repository()
        workspace = await slack_repo.get_workspace_by_guild(guild_id)
        if workspace and workspace.enabled:
            return SlackFetcher(workspace)
        return None

    elif platform == "discord":
        from src.discord_bot import get_discord_bot
        import discord

        bot = get_discord_bot()
        if not bot or not bot.client:
            return None

        guild = bot.client.get_guild(int(guild_id))
        if not guild:
            try:
                guild = await bot.client.fetch_guild(int(guild_id))
            except (discord.NotFound, discord.Forbidden):
                return None

        return DiscordFetcher(guild, bot.client)

    return None


def detect_platform(archive_source_key: Optional[str]) -> str:
    """
    Detect platform from archive source key.

    Args:
        archive_source_key: Key like "slack:T123" or "discord:123456"

    Returns:
        Platform name: "slack", "discord", or "discord" as default
    """
    if archive_source_key:
        if archive_source_key.startswith("slack:"):
            return "slack"
        elif archive_source_key.startswith("whatsapp:"):
            return "whatsapp"
    return "discord"


async def get_fetcher_for_summary(
    guild_id: str,
    archive_source_key: Optional[str] = None,
    explicit_platform: Optional[str] = None,
) -> Optional[PlatformFetcher]:
    """
    Get a platform fetcher based on summary context.

    Args:
        guild_id: Guild ID for Discord or linked workspace lookup
        archive_source_key: Optional archive source key to detect platform
        explicit_platform: Optional explicit platform override

    Returns:
        PlatformFetcher or None if unavailable
    """
    platform = explicit_platform or detect_platform(archive_source_key)
    return await get_platform_fetcher(platform, guild_id)


__all__ = [
    # Base classes
    "PlatformFetcher",
    "FetchResult",
    "PlatformContext",
    "ChannelInfo",
    "UserInfo",
    # Implementations
    "DiscordFetcher",
    "SlackFetcher",
    # Factory functions
    "get_platform_fetcher",
    "get_fetcher_for_summary",
    "detect_platform",
]
