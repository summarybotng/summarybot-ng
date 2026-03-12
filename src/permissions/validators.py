"""
Permission validation logic for Summary Bot NG.

This module provides validators for different types of permission checks,
including Discord permissions, webhook access, and command-specific validations.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import discord
import logging

from src.utils.time import utc_now_naive
from ..exceptions.discord_errors import (
    DiscordPermissionError,
    BotPermissionError,
    ChannelAccessError
)
from ..exceptions.base import ErrorContext, create_error_context

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a permission validation check."""

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)

    def add_error(self, error: str) -> None:
        """Add an error to the validation result."""
        self.errors.append(error)
        self.is_valid = False

    def add_warning(self, warning: str) -> None:
        """Add a warning to the validation result."""
        self.warnings.append(warning)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "context": self.context
        }

    def get_error_message(self) -> str:
        """Get formatted error message."""
        if not self.errors:
            return ""
        return "\n".join(f"- {error}" for error in self.errors)

    @classmethod
    def success(cls, **context) -> 'ValidationResult':
        """Create a successful validation result."""
        return cls(is_valid=True, context=context)

    @classmethod
    def failure(cls, error: str, **context) -> 'ValidationResult':
        """Create a failed validation result."""
        return cls(is_valid=False, errors=[error], context=context)


class PermissionValidator:
    """
    Validates permissions for various bot operations.

    This class provides validation methods for different types of permission
    checks, including Discord-native permissions and bot-specific permissions.
    """

    def __init__(self):
        """Initialize the permission validator."""
        logger.debug("PermissionValidator initialized")

    def validate_summarize_permission(
        self,
        user: discord.Member,
        channel: discord.TextChannel
    ) -> ValidationResult:
        """
        Validate that a user has permission to request summaries in a channel.

        Checks:
        1. User can read messages in the channel
        2. User can read message history
        3. Channel is accessible

        Args:
            user: Discord member requesting the summary
            channel: Target channel for summarization

        Returns:
            ValidationResult with validation status and any errors
        """
        result = ValidationResult(is_valid=True)

        try:
            # Get user's permissions in the channel
            permissions = channel.permissions_for(user)

            # Check required permissions
            if not permissions.read_messages:
                result.add_error(
                    f"You don't have permission to read messages in {channel.mention}"
                )

            if not permissions.read_message_history:
                result.add_error(
                    f"You don't have permission to read message history in {channel.mention}"
                )

            # Add context
            result.context = {
                "user_id": str(user.id),
                "channel_id": str(channel.id),
                "guild_id": str(channel.guild.id),
                "permissions": {
                    "read_messages": permissions.read_messages,
                    "read_message_history": permissions.read_message_history
                }
            }

            if result.is_valid:
                logger.debug(
                    f"User {user.id} has valid permissions for channel {channel.id}"
                )
            else:
                logger.info(
                    f"User {user.id} lacks permissions for channel {channel.id}: "
                    f"{result.get_error_message()}"
                )

            return result

        except Exception as e:
            logger.error(f"Error validating summarize permission: {e}")
            return ValidationResult.failure(
                f"Error validating permissions: {str(e)}",
                user_id=str(user.id),
                channel_id=str(channel.id)
            )

    def validate_bot_permissions(
        self,
        bot_member: discord.Member,
        channel: discord.TextChannel,
        operation: str = "summarize"
    ) -> ValidationResult:
        """
        Validate that the bot has required permissions in a channel.

        Args:
            bot_member: Discord member object for the bot
            channel: Target channel
            operation: Operation type (e.g., "summarize", "manage")

        Returns:
            ValidationResult with validation status and any errors
        """
        result = ValidationResult(is_valid=True)

        try:
            permissions = channel.permissions_for(bot_member)

            # Required permissions for summarization
            required_perms = {
                "read_messages": permissions.read_messages,
                "read_message_history": permissions.read_message_history,
                "send_messages": permissions.send_messages,
                "embed_links": permissions.embed_links
            }

            # Check each required permission
            for perm_name, has_perm in required_perms.items():
                if not has_perm:
                    result.add_error(
                        f"Bot lacks required permission: {perm_name.replace('_', ' ').title()}"
                    )

            # Add context
            result.context = {
                "bot_id": str(bot_member.id),
                "channel_id": str(channel.id),
                "guild_id": str(channel.guild.id),
                "operation": operation,
                "permissions": required_perms
            }

            if not result.is_valid:
                logger.warning(
                    f"Bot lacks permissions in channel {channel.id}: "
                    f"{result.get_error_message()}"
                )

            return result

        except Exception as e:
            logger.error(f"Error validating bot permissions: {e}")
            return ValidationResult.failure(
                f"Error validating bot permissions: {str(e)}",
                channel_id=str(channel.id)
            )

    def validate_webhook_access(
        self,
        api_key: Optional[str],
        guild_id: str,
        expected_secret: Optional[str]
    ) -> ValidationResult:
        """
        Validate webhook API access credentials.

        Args:
            api_key: Provided API key/secret
            guild_id: Target guild ID
            expected_secret: Expected secret from configuration

        Returns:
            ValidationResult with validation status and any errors
        """
        result = ValidationResult(is_valid=True)

        # Check if API key is provided
        if not api_key:
            result.add_error("API key is required for webhook access")

        # Check if secret is configured
        if not expected_secret:
            result.add_error(
                f"Webhook access is not configured for guild {guild_id}"
            )

        # Validate the secret matches
        elif api_key != expected_secret:
            result.add_error("Invalid API key")
            logger.warning(
                f"Invalid webhook access attempt for guild {guild_id}"
            )

        result.context = {
            "guild_id": guild_id,
            "authenticated": result.is_valid
        }

        return result

    def validate_channel_accessibility(
        self,
        channel: discord.TextChannel,
        bot_member: discord.Member
    ) -> ValidationResult:
        """
        Validate that a channel is accessible and usable.

        Args:
            channel: Channel to validate
            bot_member: Bot's member object

        Returns:
            ValidationResult with validation status and any errors
        """
        result = ValidationResult(is_valid=True)

        try:
            # Check if channel exists
            if not channel:
                return ValidationResult.failure("Channel not found")

            # Check if it's a text channel
            if not isinstance(channel, discord.TextChannel):
                result.add_error(
                    "Channel must be a text channel (not voice, category, etc.)"
                )

            # Check if channel is NSFW when it shouldn't be
            if hasattr(channel, 'is_nsfw') and channel.is_nsfw():
                result.add_warning("Channel is marked as NSFW")

            # Check bot's view permissions
            permissions = channel.permissions_for(bot_member)
            if not permissions.view_channel:
                result.add_error("Bot cannot view this channel")

            result.context = {
                "channel_id": str(channel.id),
                "channel_name": channel.name,
                "guild_id": str(channel.guild.id),
                "is_nsfw": getattr(channel, 'is_nsfw', lambda: False)(),
                "bot_can_view": permissions.view_channel if permissions else False
            }

            return result

        except Exception as e:
            logger.error(f"Error validating channel accessibility: {e}")
            return ValidationResult.failure(
                f"Error validating channel: {str(e)}"
            )

    def validate_time_range(
        self,
        start_time: Any,
        end_time: Any,
        max_days: int = 90
    ) -> ValidationResult:
        """
        Validate that a time range is valid for message fetching.

        Args:
            start_time: Start time for message range
            end_time: End time for message range
            max_days: Maximum allowed days in the past

        Returns:
            ValidationResult with validation status and any errors
        """
        from datetime import datetime, timedelta

        result = ValidationResult(is_valid=True)

        try:
            # Validate time types
            if not isinstance(start_time, datetime) or not isinstance(end_time, datetime):
                result.add_error("Start and end times must be datetime objects")
                return result

            # Check if start is before end
            if start_time >= end_time:
                result.add_error("Start time must be before end time")

            # Check if range is too old
            now = utc_now_naive()
            days_old = (now - start_time).days

            if days_old > max_days:
                result.add_error(
                    f"Time range is too old ({days_old} days). "
                    f"Maximum allowed is {max_days} days."
                )

            # Check if range is in the future
            if start_time > now:
                result.add_error("Start time cannot be in the future")

            if end_time > now:
                result.add_warning("End time is in the future, using current time")

            # Calculate range duration
            duration = (end_time - start_time).total_seconds() / 3600  # hours

            result.context = {
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_hours": duration,
                "days_old": days_old
            }

            return result

        except Exception as e:
            logger.error(f"Error validating time range: {e}")
            return ValidationResult.failure(
                f"Error validating time range: {str(e)}"
            )

    def validate_user_rate_limit(
        self,
        user_id: str,
        action: str,
        limit: int = 10,
        window_seconds: int = 60
    ) -> ValidationResult:
        """
        Validate that a user hasn't exceeded rate limits.

        Note: This is a placeholder. Actual implementation would require
        a rate limiting backend (Redis, etc.)

        Args:
            user_id: User to check
            action: Action being rate limited
            limit: Maximum actions allowed
            window_seconds: Time window in seconds

        Returns:
            ValidationResult with validation status
        """
        result = ValidationResult(is_valid=True)

        # Placeholder - would implement with Redis or similar
        result.context = {
            "user_id": user_id,
            "action": action,
            "limit": limit,
            "window_seconds": window_seconds,
            "note": "Rate limiting not yet implemented"
        }

        return result
