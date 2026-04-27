"""
Platform Message Fetcher Abstraction (ADR-051).

Factory functions and exports for platform-agnostic message fetching.
"""

from enum import Enum
from typing import Optional, Union

from .base import PlatformFetcher
from .types import FetchResult, PlatformContext, ChannelInfo, UserInfo
from .discord_fetcher import DiscordFetcher
from .slack_fetcher import SlackFetcher


class Platform(str, Enum):
    """
    Known messaging platforms (P1: Type-safe platform enum).

    Using str, Enum for backward compatibility with string comparisons.

    Note: Only DISCORD and SLACK have fetchers for scheduled summaries.
    WHATSAPP is used for archive display (detect_platform) only - it returns
    None from get_platform_fetcher since no WhatsAppFetcher exists.
    """
    DISCORD = "discord"
    SLACK = "slack"
    WHATSAPP = "whatsapp"  # Archive display only - no fetcher for schedules

    @classmethod
    def from_string(cls, value: str) -> "Platform":
        """
        Convert string to Platform enum, case-insensitive.

        Args:
            value: Platform string like "discord", "slack", "Discord"

        Returns:
            Platform enum value

        Raises:
            ValueError: If platform is not supported
        """
        normalized = value.lower().strip()
        try:
            return cls(normalized)
        except ValueError:
            valid_platforms = ", ".join(p.value for p in cls)
            raise ValueError(f"Unsupported platform '{value}'. Valid: {valid_platforms}")

    def __str__(self) -> str:
        """Return the string value for backward compatibility."""
        return self.value


class UnauthorizedAccessError(Exception):
    """
    Raised when a user attempts to access a workspace they don't have permission for.

    P0: Security - Authorization verification for workspace access.
    """
    def __init__(self, guild_id: str, user_id: Optional[str] = None):
        self.guild_id = guild_id
        self.user_id = user_id
        message = f"User does not have access to workspace {guild_id}"
        if user_id:
            message = f"User {user_id} does not have access to workspace {guild_id}"
        super().__init__(message)


def _verify_user_authorization(guild_id: str, user: Optional[dict]) -> None:
    """
    Verify that a user has access to the specified guild/workspace.

    P0: Security - User authorization check before returning platform fetcher.

    Args:
        guild_id: The guild/workspace ID to verify access for
        user: User dict from auth system with 'guilds' list, or None for system calls

    Raises:
        UnauthorizedAccessError: If user doesn't have access to the guild

    Note:
        When user is None (e.g., scheduled tasks, background jobs), authorization
        is skipped. This allows the scheduler to operate without user context.
    """
    if user is None:
        # System/scheduler calls without user context - allowed
        return

    user_guilds = user.get("guilds", [])
    if guild_id not in user_guilds:
        user_id = user.get("sub") or user.get("user_id")
        raise UnauthorizedAccessError(guild_id, user_id)


async def get_platform_fetcher(
    platform: Union[str, Platform],
    guild_id: str,
    user: Optional[dict] = None,
) -> Optional[PlatformFetcher]:
    """
    Factory to create appropriate platform fetcher.

    P0: Security - Verifies user authorization before returning fetcher.
    P1: Type safety - Accepts Platform enum or string for backward compatibility.

    Args:
        platform: Platform enum or string ("discord", "slack")
        guild_id: Discord guild ID (used for both Discord and Slack workspace linking)
        user: Optional user dict from auth system for authorization verification.
              If None, authorization is skipped (for scheduler/system calls).

    Returns:
        PlatformFetcher instance or None if platform unavailable

    Raises:
        UnauthorizedAccessError: If user is provided but lacks access to guild
        ValueError: If platform string is not a valid Platform
    """
    # P0: Verify user has access to this workspace before proceeding
    _verify_user_authorization(guild_id, user)

    # P1: Normalize platform to enum for type safety
    if isinstance(platform, str):
        try:
            platform = Platform.from_string(platform)
        except ValueError:
            # Unknown platform - return None for backward compatibility
            return None

    if platform == Platform.SLACK:
        from src.data.repositories import get_slack_repository
        slack_repo = await get_slack_repository()
        workspace = await slack_repo.get_workspace_by_guild(guild_id)
        if workspace and workspace.enabled:
            return SlackFetcher(workspace)
        return None

    elif platform == Platform.DISCORD:
        from src.dashboard.routes import get_discord_bot
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


def detect_platform(archive_source_key: Optional[str]) -> Platform:
    """
    Detect platform from archive source key.

    P1: Now returns Platform enum for type safety.

    Args:
        archive_source_key: Key like "slack:T123" or "discord:123456"

    Returns:
        Platform enum: Platform.SLACK, Platform.DISCORD, or Platform.DISCORD as default
    """
    if archive_source_key:
        if archive_source_key.startswith("slack:"):
            return Platform.SLACK
        elif archive_source_key.startswith("whatsapp:"):
            return Platform.WHATSAPP
    return Platform.DISCORD


async def get_fetcher_for_summary(
    guild_id: str,
    archive_source_key: Optional[str] = None,
    explicit_platform: Optional[Union[str, Platform]] = None,
    user: Optional[dict] = None,
) -> Optional[PlatformFetcher]:
    """
    Get a platform fetcher based on summary context.

    P0: Security - Verifies user authorization before returning fetcher.
    P1: Type safety - Accepts Platform enum or string for backward compatibility.

    Args:
        guild_id: Guild ID for Discord or linked workspace lookup
        archive_source_key: Optional archive source key to detect platform
        explicit_platform: Optional explicit platform override (enum or string)
        user: Optional user dict from auth system for authorization verification.
              If None, authorization is skipped (for scheduler/system calls).

    Returns:
        PlatformFetcher or None if unavailable

    Raises:
        UnauthorizedAccessError: If user is provided but lacks access to guild
    """
    # P1: Normalize explicit_platform to enum if provided as string
    platform: Platform
    if explicit_platform is not None:
        if isinstance(explicit_platform, str):
            platform = Platform.from_string(explicit_platform)
        else:
            platform = explicit_platform
    else:
        platform = detect_platform(archive_source_key)

    return await get_platform_fetcher(platform, guild_id, user)


__all__ = [
    # P1: Platform enum for type safety
    "Platform",
    # P0: Authorization error
    "UnauthorizedAccessError",
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
