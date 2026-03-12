"""
Base command handler with common functionality for all command handlers.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import discord
from abc import ABC, abstractmethod

from src.utils.time import utc_now_naive
from ..exceptions import (
    SummaryBotException,
    UserError,
    create_error_context
)
from ..logging import CommandLogger, log_command, CommandType

logger = logging.getLogger(__name__)


class RateLimitTracker:
    """Simple in-memory rate limit tracker."""

    def __init__(self):
        self._user_requests: Dict[str, list] = {}

    def check_rate_limit(self, user_id: str, max_requests: int = 5,
                        window_seconds: int = 60) -> tuple[bool, Optional[int]]:
        """
        Check if user is within rate limit.

        Args:
            user_id: Discord user ID
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            Tuple of (is_allowed, seconds_until_reset)
        """
        now = utc_now_naive()

        # Clean up old entries
        if user_id in self._user_requests:
            cutoff = now - timedelta(seconds=window_seconds)
            self._user_requests[user_id] = [
                ts for ts in self._user_requests[user_id] if ts > cutoff
            ]
        else:
            self._user_requests[user_id] = []

        # Check if under limit
        if len(self._user_requests[user_id]) >= max_requests:
            oldest = min(self._user_requests[user_id])
            reset_time = int((oldest + timedelta(seconds=window_seconds) - now).total_seconds())
            return False, reset_time

        # Add current request
        self._user_requests[user_id].append(now)
        return True, None

    def clear_user_limit(self, user_id: str):
        """Clear rate limit for a specific user."""
        if user_id in self._user_requests:
            del self._user_requests[user_id]


class BaseCommandHandler(ABC):
    """Base class for all command handlers."""

    def __init__(self,
                 summarization_engine,
                 permission_manager=None,
                 rate_limit_enabled: bool = True,
                 command_logger: Optional[CommandLogger] = None):
        """
        Initialize base command handler.

        Args:
            summarization_engine: SummarizationEngine instance
            permission_manager: PermissionManager instance (optional)
            rate_limit_enabled: Whether to enable rate limiting
            command_logger: CommandLogger instance for audit logging (optional)
        """
        self.summarization_engine = summarization_engine
        self.permission_manager = permission_manager
        self.rate_limit_enabled = rate_limit_enabled
        self.command_logger = command_logger
        self.rate_limiter = RateLimitTracker()
        self._deferred_interactions: set = set()  # Track deferred interactions

        # Default rate limits (can be overridden by subclasses)
        self.max_requests_per_minute = 5
        self.rate_limit_window = 60

    @log_command(CommandType.SLASH_COMMAND)
    async def handle_command(self, interaction: discord.Interaction, **kwargs) -> None:
        """
        Main command handler with error handling and rate limiting.

        Args:
            interaction: Discord interaction object
            **kwargs: Command-specific arguments
        """
        try:
            # Check rate limit
            if self.rate_limit_enabled:
                allowed, reset_time = self.rate_limiter.check_rate_limit(
                    str(interaction.user.id),
                    self.max_requests_per_minute,
                    self.rate_limit_window
                )

                if not allowed:
                    await self.send_rate_limit_response(interaction, reset_time)
                    return

            # Check permissions if permission manager is available
            if self.permission_manager:
                has_permission = await self._check_permissions(interaction)
                if not has_permission:
                    await self.send_permission_error(interaction)
                    return

            # Execute the command
            await self._execute_command(interaction, **kwargs)

        except SummaryBotException as e:
            logger.error(f"Command error: {e.to_log_string()}")
            await self.send_error_response(interaction, e)

        except Exception as e:
            logger.exception(f"Unexpected error in command handler: {e}")

            error = SummaryBotException(
                message=f"Unexpected error: {str(e)}",
                error_code="COMMAND_ERROR",
                context=create_error_context(
                    user_id=str(interaction.user.id),
                    guild_id=str(interaction.guild_id) if interaction.guild else None,
                    channel_id=str(interaction.channel_id),
                    command=interaction.command.name if interaction.command else "unknown"
                ),
                user_message="An unexpected error occurred while processing your command.",
                retryable=True,
                cause=e
            )

            await self.send_error_response(interaction, error)

    @abstractmethod
    async def _execute_command(self, interaction: discord.Interaction, **kwargs) -> None:
        """
        Execute the specific command logic.
        Must be implemented by subclasses.

        Args:
            interaction: Discord interaction object
            **kwargs: Command-specific arguments
        """
        pass

    async def _check_permissions(self, interaction: discord.Interaction) -> bool:
        """
        Check if user has permission to execute command.

        Args:
            interaction: Discord interaction object

        Returns:
            True if user has permission
        """
        if not self.permission_manager:
            return True

        try:
            command_name = interaction.command.name if interaction.command else "unknown"

            return await self.permission_manager.check_command_permission(
                user_id=str(interaction.user.id),
                command=command_name,
                guild_id=str(interaction.guild_id) if interaction.guild else None
            )
        except Exception as e:
            logger.error(f"Permission check failed: {e}")
            # Fail open - allow command if permission check fails
            return True

    async def defer_response(self, interaction: discord.Interaction,
                           ephemeral: bool = False) -> None:
        """
        Defer response for long-running commands.

        Args:
            interaction: Discord interaction object
            ephemeral: Whether response should be ephemeral (only visible to user)
        """
        try:
            import inspect
            # Handle both sync and async is_done() for testing flexibility
            is_done_result = interaction.response.is_done()
            if inspect.iscoroutine(is_done_result):
                is_done = await is_done_result
            else:
                is_done = is_done_result

            if not is_done:
                await interaction.response.defer(ephemeral=ephemeral)
                self._deferred_interactions.add(id(interaction))  # Track that we deferred
                logger.debug(f"Deferred response for command: {interaction.command.name if interaction.command else 'unknown'}")
        except Exception as e:
            logger.warning(f"Failed to defer response: {e}")

    async def send_error_response(self, interaction: discord.Interaction,
                                 error: Exception) -> None:
        """
        Send error response to user.

        Args:
            interaction: Discord interaction object
            error: Exception that occurred
        """
        # Convert to SummaryBotException if needed
        if isinstance(error, SummaryBotException):
            bot_error = error
        else:
            bot_error = SummaryBotException(
                message=str(error),
                error_code="UNKNOWN_ERROR",
                user_message="An error occurred while processing your request.",
                retryable=False
            )

        # Create error embed
        embed = discord.Embed(
            title="❌ Error",
            description=bot_error.get_user_response(),
            color=0xFF0000,  # Red
            timestamp=utc_now_naive()
        )

        # Add error code footer
        embed.set_footer(text=f"Error Code: {bot_error.error_code}")

        # Add retry hint if retryable
        if bot_error.retryable:
            embed.add_field(
                name="💡 Tip",
                value="This error is temporary. Please try again in a moment.",
                inline=False
            )

        try:
            import inspect
            # Handle both sync and async is_done() for testing flexibility
            is_done_result = interaction.response.is_done()
            if inspect.iscoroutine(is_done_result):
                is_done = await is_done_result
            else:
                is_done = is_done_result

            # Check if we deferred this interaction OR if Discord says response is done
            if id(interaction) in self._deferred_interactions or is_done:
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to send error response: {e}")
        finally:
            # Clean up tracking
            self._deferred_interactions.discard(id(interaction))

    async def send_success_response(self, interaction: discord.Interaction,
                                   title: str, description: str,
                                   embed: Optional[discord.Embed] = None,
                                   ephemeral: bool = False) -> None:
        """
        Send success response to user.

        Args:
            interaction: Discord interaction object
            title: Response title
            description: Response description
            embed: Optional custom embed
            ephemeral: Whether response should be ephemeral
        """
        if not embed:
            embed = discord.Embed(
                title=f"✅ {title}",
                description=description,
                color=0x00FF00,  # Green
                timestamp=utc_now_naive()
            )

        try:
            import inspect
            # Handle both sync and async is_done() for testing flexibility
            is_done_result = interaction.response.is_done()
            if inspect.iscoroutine(is_done_result):
                is_done = await is_done_result
            else:
                is_done = is_done_result

            # Check if we deferred this interaction OR if Discord says response is done
            if id(interaction) in self._deferred_interactions or is_done:
                await interaction.followup.send(embed=embed, ephemeral=ephemeral)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
        except Exception as e:
            logger.error(f"Failed to send success response: {e}")
        finally:
            # Clean up tracking
            self._deferred_interactions.discard(id(interaction))

    async def send_rate_limit_response(self, interaction: discord.Interaction,
                                      reset_seconds: int) -> None:
        """
        Send rate limit error response.

        Args:
            interaction: Discord interaction object
            reset_seconds: Seconds until rate limit resets
        """
        embed = discord.Embed(
            title="⏱️ Rate Limit Exceeded",
            description=f"You're sending commands too quickly. Please wait {reset_seconds} seconds before trying again.",
            color=0xFFA500,  # Orange
            timestamp=utc_now_naive()
        )

        embed.add_field(
            name="Rate Limit",
            value=f"{self.max_requests_per_minute} requests per {self.rate_limit_window} seconds",
            inline=False
        )

        try:
            import inspect
            # Handle both sync and async is_done() for testing flexibility
            is_done_result = interaction.response.is_done()
            if inspect.iscoroutine(is_done_result):
                is_done = await is_done_result
            else:
                is_done = is_done_result

            if is_done:
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to send rate limit response: {e}")

    async def send_permission_error(self, interaction: discord.Interaction) -> None:
        """
        Send permission error response.

        Args:
            interaction: Discord interaction object
        """
        embed = discord.Embed(
            title="🔒 Permission Denied",
            description="You don't have permission to use this command.",
            color=0xFF0000,  # Red
            timestamp=utc_now_naive()
        )

        embed.add_field(
            name="Need Help?",
            value="Contact a server administrator if you believe this is an error.",
            inline=False
        )

        try:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to send permission error: {e}")
