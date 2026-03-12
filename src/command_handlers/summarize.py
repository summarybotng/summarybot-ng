"""
Summarization command handlers for Discord slash commands.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Optional, List
import discord

from .base import BaseCommandHandler
from src.utils.time import utc_now_naive
from .utils import (
    parse_time_string,
    validate_time_range,
    format_duration,
    format_error_response,
    format_success_response
)
from ..models.summary import SummaryOptions, SummaryLength, SummarizationContext
from ..models.message import ProcessedMessage
from ..message_processing import MessageFetcher, MessageFilter, MessageCleaner
from ..exceptions import (
    UserError,
    InsufficientContentError,
    ChannelAccessError,
    create_error_context
)

logger = logging.getLogger(__name__)


def resolve_category_channels(
    category: discord.CategoryChannel,
    excluded_channel_ids: Optional[List[str]] = None
) -> List[discord.TextChannel]:
    """Resolve a category to its text channels, applying exclusions.

    Args:
        category: Discord category channel
        excluded_channel_ids: List of channel IDs to exclude

    Returns:
        List of text channels in the category
    """
    excluded = set(excluded_channel_ids or [])
    channels = [
        ch for ch in category.text_channels
        if str(ch.id) not in excluded
    ]
    return channels


def parse_exclude_channels(exclude_string: Optional[str]) -> List[str]:
    """Parse excluded channels from comma-separated mentions or IDs.

    Args:
        exclude_string: Comma-separated channel mentions (#channel) or IDs

    Returns:
        List of channel IDs
    """
    if not exclude_string:
        return []

    # Extract channel IDs from mentions (<#123>) or raw IDs
    channel_pattern = r'<#(\d+)>|(\d{17,20})'
    matches = re.findall(channel_pattern, exclude_string)
    return [mention_id or raw_id for mention_id, raw_id in matches]


class SummarizeCommandHandler(BaseCommandHandler):
    """Handler for summarization commands."""

    def __init__(self, summarization_engine, permission_manager=None,
                 message_fetcher: Optional[MessageFetcher] = None,
                 message_filter: Optional[MessageFilter] = None,
                 message_cleaner: Optional[MessageCleaner] = None,
                 command_logger=None,
                 config_manager=None):
        """
        Initialize summarize command handler.

        Args:
            summarization_engine: SummarizationEngine instance
            permission_manager: PermissionManager instance (optional)
            message_fetcher: MessageFetcher instance
            message_filter: MessageFilter instance
            message_cleaner: MessageCleaner instance
            command_logger: CommandLogger instance for audit logging (optional)
            config_manager: ConfigManager instance for guild configuration (optional)
        """
        super().__init__(summarization_engine, permission_manager, command_logger=command_logger)

        self.message_fetcher = message_fetcher
        self.message_filter = message_filter
        self.message_cleaner = message_cleaner
        self.config_manager = config_manager

        # Override rate limits for summarization (more restrictive)
        self.max_requests_per_minute = 3
        self.rate_limit_window = 60

    async def _execute_command(self, interaction: discord.Interaction, **kwargs) -> None:
        """
        Execute summarization command.
        Routes to appropriate handler based on command options.
        """
        # This is a placeholder - actual routing happens in handle_* methods
        pass

    async def handle_summarize_interaction(
        self,
        interaction: discord.Interaction,
        messages: Optional[int] = None,
        hours: Optional[int] = None,
        minutes: Optional[int] = None,
        length: Optional[str] = "detailed",
        perspective: Optional[str] = "general",
        channel: Optional[discord.TextChannel] = None,
        category: Optional[discord.CategoryChannel] = None,
        mode: Optional[str] = "combined",
        exclude_channels: Optional[str] = None
    ) -> None:
        """
        Handle /summarize slash command interaction.

        This is the main entry point from Discord slash commands.

        Args:
            interaction: Discord interaction
            messages: Number of messages to summarize (overrides time-based)
            hours: Hours of messages to look back
            minutes: Minutes of messages to look back
            length: Summary length (brief, detailed, comprehensive)
            perspective: Perspective/audience (general, developer, marketing, etc.)
            channel: Target channel to summarize (optional, defaults to current channel)
            category: Target category to summarize (mutually exclusive with channel)
            mode: For category: "combined" or "individual" mode
            exclude_channels: Comma-separated channel IDs or mentions to exclude
        """
        try:
            # Route to category handler if category is specified
            if category:
                excluded_channel_ids = parse_exclude_channels(exclude_channels)

                if mode == "individual":
                    await self.handle_category_individual_summary(
                        interaction,
                        category=category,
                        excluded_channel_ids=excluded_channel_ids,
                        messages=messages,
                        hours=hours,
                        minutes=minutes,
                        length=length,
                        perspective=perspective
                    )
                else:  # combined mode
                    await self.handle_category_combined_summary(
                        interaction,
                        category=category,
                        excluded_channel_ids=excluded_channel_ids,
                        messages=messages,
                        hours=hours,
                        minutes=minutes,
                        length=length,
                        perspective=perspective
                    )
                return
            # Determine target channel
            target_channel = channel or interaction.channel

            # Cross-channel permission check
            # NOTE: Interaction is already deferred by commands.py, so we must use followup.send()
            if channel and channel.id != interaction.channel.id:
                # User is requesting cross-channel summary
                if not self.config_manager:
                    await interaction.followup.send(
                        "❌ Configuration manager not available.",
                        ephemeral=True
                    )
                    return

                # Get guild config from bot config
                bot_config = self.config_manager.get_current_config()
                if not bot_config:
                    await interaction.followup.send(
                        "❌ Configuration not loaded.",
                        ephemeral=True
                    )
                    return

                guild_config = bot_config.get_guild_config(str(interaction.guild_id))

                if not guild_config.cross_channel_summary_role_name:
                    # Feature not configured
                    await interaction.followup.send(
                        "❌ Cross-channel summaries are not enabled on this server.",
                        ephemeral=True
                    )
                    return

                # Check if user has required role
                user_member = interaction.guild.get_member(interaction.user.id)
                has_cross_channel_role = any(
                    role.name == guild_config.cross_channel_summary_role_name
                    for role in user_member.roles
                )

                if not has_cross_channel_role:
                    await interaction.followup.send(
                        f"❌ You need the **{guild_config.cross_channel_summary_role_name}** "
                        f"role to summarize other channels.",
                        ephemeral=True
                    )
                    return

                # Check Discord read permissions for user
                if not channel.permissions_for(user_member).read_message_history:
                    await interaction.followup.send(
                        f"❌ You don't have permission to read message history in {channel.mention}.",
                        ephemeral=True
                    )
                    return

                # Also check bot has permissions
                bot_member = interaction.guild.me
                if not channel.permissions_for(bot_member).read_message_history:
                    await interaction.followup.send(
                        f"❌ I don't have permission to read message history in {channel.mention}.",
                        ephemeral=True
                    )
                    return

            # Default to 100 messages or 24 hours
            if messages:
                # Message count mode
                await self.handle_quick_summary(
                    interaction,
                    channel=target_channel,
                    message_count=messages,
                    length=length,
                    perspective=perspective
                )
            elif hours or minutes:
                # Time-based mode
                total_hours = (hours or 0) + (minutes or 0) / 60
                await self.handle_summarize(
                    interaction,
                    channel=target_channel,
                    hours=int(total_hours) if total_hours > 0 else 24,
                    length=length,
                    perspective=perspective,
                    include_bots=False
                )
            else:
                # Default: last 100 messages
                await self.handle_quick_summary(
                    interaction,
                    channel=target_channel,
                    message_count=100,
                    length=length,
                    perspective=perspective
                )

        except Exception as e:
            logger.error(f"Error in handle_summarize_interaction: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    f"❌ Failed to create summary: {str(e)}",
                    ephemeral=True
                )
            except Exception as followup_error:
                # SEC-005: Log the error instead of silently swallowing
                logger.warning(f"Failed to send error followup: {followup_error}")

    async def fetch_messages(self, channel: discord.TextChannel, limit: int = 100) -> list[discord.Message]:
        """
        Fetch messages from a Discord channel.

        This is a convenience method for fetching messages with a simple limit.
        For time-based fetching, use _fetch_and_process_messages instead.

        Args:
            channel: Discord text channel to fetch from
            limit: Maximum number of messages to fetch

        Returns:
            List of Discord messages

        Raises:
            ChannelAccessError: If the bot lacks permissions to read messages
        """
        try:
            messages = []
            async for message in channel.history(limit=limit):
                messages.append(message)
            return messages
        except discord.errors.Forbidden as e:
            raise ChannelAccessError(
                channel_id=str(channel.id),
                reason=f"I don't have permission to read messages in {channel.mention}. Please ensure I have 'Read Message History' permission."
            ) from e

    async def fetch_recent_messages(self, channel: discord.TextChannel, time_delta: timedelta) -> list[discord.Message]:
        """
        Fetch recent messages from a channel within a time window.

        Args:
            channel: Discord text channel to fetch from
            time_delta: Time window to fetch messages from (e.g., timedelta(hours=1))

        Returns:
            List of Discord messages within the time window

        Raises:
            ChannelAccessError: If the bot lacks permissions to read messages
        """
        try:
            now = utc_now_naive()
            after_time = now - time_delta

            messages = []
            async for message in channel.history(limit=1000, after=after_time):
                messages.append(message)

            return messages
        except discord.errors.Forbidden as e:
            raise ChannelAccessError(
                channel_id=str(channel.id),
                reason=f"I don't have permission to read messages in {channel.mention}. Please ensure I have 'Read Message History' permission."
            ) from e

    async def handle_summarize(self,
                              interaction: discord.Interaction,
                              channel: Optional[discord.TextChannel] = None,
                              hours: int = 24,
                              length: str = "detailed",
                              perspective: str = "general",
                              include_bots: bool = False,
                              start_time: Optional[str] = None,
                              end_time: Optional[str] = None) -> None:
        """
        Handle the /summarize command for full customizable summaries.

        Args:
            interaction: Discord interaction object
            channel: Target channel (defaults to current channel)
            hours: Number of hours to look back (if start_time not specified)
            length: Summary length (brief/detailed/comprehensive)
            perspective: Perspective/audience (general, developer, marketing, etc.)
            include_bots: Whether to include bot messages
            start_time: Custom start time string
            end_time: Custom end time string
        """
        await self.defer_response(interaction)

        try:
            # Check permissions
            if self.permission_manager:
                # Check command permission
                has_permission = await self.permission_manager.check_command_permission(
                    user_id=str(interaction.user.id),
                    command="summarize",
                    guild_id=str(interaction.guild_id) if interaction.guild else None
                )

                if not has_permission:
                    error_msg = "You don't have permission to use this command."
                    await interaction.followup.send(content=error_msg, ephemeral=True)
                    return

            # Determine target channel
            target_channel = channel or interaction.channel

            # Check channel access permission
            if self.permission_manager and target_channel:
                has_access = await self.permission_manager.check_channel_access(
                    user_id=str(interaction.user.id),
                    channel_id=str(target_channel.id),
                    guild_id=str(interaction.guild_id) if interaction.guild else None
                )

                if not has_access:
                    error_msg = f"You don't have access to {target_channel.mention}."
                    await interaction.followup.send(content=error_msg, ephemeral=True)
                    return
            if not isinstance(target_channel, discord.TextChannel):
                raise UserError(
                    message=f"Invalid channel type: {type(target_channel)}",
                    error_code="INVALID_CHANNEL",
                    user_message="Summaries can only be created for text channels."
                )

            # Check channel access
            if not target_channel.permissions_for(interaction.guild.me).read_message_history:
                raise ChannelAccessError(
                    channel_id=str(target_channel.id),
                    reason=f"I don't have permission to read messages in {target_channel.mention}."
                )

            # Parse time range
            now = utc_now_naive()

            if start_time:
                parsed_start = parse_time_string(start_time)
            else:
                parsed_start = now - timedelta(hours=hours)

            if end_time:
                parsed_end = parse_time_string(end_time)
            else:
                parsed_end = now

            # Validate time range
            validate_time_range(parsed_start, parsed_end, max_hours=168)  # 1 week max

            # Parse summary length
            try:
                summary_length = SummaryLength(length.lower())
            except ValueError:
                raise UserError(
                    message=f"Invalid summary length: {length}",
                    error_code="INVALID_LENGTH",
                    user_message=f"Invalid summary length. Choose from: brief, detailed, comprehensive."
                )

            # Create summary options
            summary_options = SummaryOptions(
                summary_length=summary_length,
                perspective=perspective,
                include_bots=include_bots,
                include_attachments=True,
                min_messages=5
            )

            # Send status update
            status_embed = discord.Embed(
                title="🔄 Generating Summary",
                description=f"Analyzing messages in {target_channel.mention}...",
                color=0x4A90E2,
                timestamp=utc_now_naive()
            )
            status_embed.add_field(
                name="Time Range",
                value=f"{parsed_start.strftime('%Y-%m-%d %H:%M')} to {parsed_end.strftime('%Y-%m-%d %H:%M')}",
                inline=False
            )
            await interaction.followup.send(embed=status_embed)

            # Fetch messages first (for testability)
            raw_messages = await self.fetch_messages(target_channel, limit=10000)

            # Filter messages by time range
            time_filtered_messages = [
                msg for msg in raw_messages
                if parsed_start <= msg.created_at <= parsed_end
            ]

            # Then process them
            processed_messages = await self._process_messages(
                time_filtered_messages,
                summary_options
            )

            if len(processed_messages) < summary_options.min_messages:
                raise InsufficientContentError(
                    message_count=len(processed_messages),
                    min_required=summary_options.min_messages
                )

            # Create summarization context
            context = SummarizationContext(
                channel_name=target_channel.name,
                guild_name=interaction.guild.name,
                total_participants=len(set(msg.author_id for msg in processed_messages)),
                time_span_hours=(parsed_end - parsed_start).total_seconds() / 3600
            )

            # Generate summary
            summary_result = await self.summarization_engine.summarize_messages(
                messages=processed_messages,
                options=summary_options,
                context=context,
                channel_id=str(target_channel.id),
                guild_id=str(interaction.guild_id)
            )

            # Send summary as embed
            summary_embed_dict = summary_result.to_embed_dict()
            summary_embed = discord.Embed.from_dict(summary_embed_dict)

            await interaction.followup.send(embed=summary_embed)

            # Log success
            logger.info(
                f"Summary generated - Guild: {interaction.guild_id}, "
                f"Channel: {target_channel.id}, Messages: {len(processed_messages)}, "
                f"User: {interaction.user.id}"
            )

        except (UserError, InsufficientContentError, ChannelAccessError) as e:
            logger.warning(f"Summarization failed: {e.to_log_string()}")
            await self.send_error_response(interaction, e)

        except Exception as e:
            logger.exception(f"Unexpected error in summarize command: {e}")
            error = UserError(
                message=str(e),
                error_code="SUMMARIZE_FAILED",
                user_message="Failed to generate summary. Please try again later."
            )
            await self.send_error_response(interaction, error)

    async def handle_quick_summary(self,
                                  interaction: discord.Interaction,
                                  minutes: int = 60,
                                  channel: Optional[discord.TextChannel] = None,
                                  message_count: Optional[int] = None,
                                  length: str = "detailed",
                                  perspective: str = "general") -> None:
        """
        Handle quick summary command for recent messages.

        Args:
            interaction: Discord interaction object
            minutes: Number of minutes to look back (default: 60)
            channel: Target channel (defaults to interaction.channel)
            message_count: Number of messages to summarize (overrides time-based)
            length: Summary length (brief, detailed, comprehensive)
            perspective: Perspective/audience (general, developer, marketing, etc.)
        """
        await self.defer_response(interaction)

        try:
            # Determine target channel
            target_channel = channel or interaction.channel

            # Fetch messages based on mode
            if message_count:
                # Message count mode
                raw_messages = await self.fetch_messages(target_channel, limit=message_count)
            else:
                # Time-based mode
                # Validate minutes
                if minutes < 5 or minutes > 1440:  # 5 min to 24 hours
                    raise UserError(
                        message=f"Invalid minutes: {minutes}",
                        error_code="INVALID_DURATION",
                        user_message="Minutes must be between 5 and 1440 (24 hours)."
                    )

                # Fetch recent messages using the dedicated method
                time_delta = timedelta(minutes=minutes)
                raw_messages = await self.fetch_recent_messages(target_channel, time_delta)

            # Process messages
            # Convert length string to enum
            summary_length_enum = SummaryLength(length)
            summary_options = SummaryOptions(
                summary_length=summary_length_enum,
                perspective=perspective,
                include_bots=False
            )
            processed_messages = await self._process_messages(raw_messages, summary_options)

            if len(processed_messages) < summary_options.min_messages:
                raise InsufficientContentError(
                    message_count=len(processed_messages),
                    min_required=summary_options.min_messages
                )

            # Create summarization context
            time_span = minutes / 60 if not message_count else 0
            context = SummarizationContext(
                channel_name=target_channel.name,
                guild_name=interaction.guild.name,
                total_participants=len(set(msg.author_id for msg in processed_messages)),
                time_span_hours=time_span
            )

            # Generate summary
            summary_result = await self.summarization_engine.summarize_messages(
                messages=processed_messages,
                options=summary_options,
                context=context,
                channel_id=str(target_channel.id),
                guild_id=str(interaction.guild_id)
            )

            # Send summary as embed
            summary_embed_dict = summary_result.to_embed_dict()
            summary_embed = discord.Embed.from_dict(summary_embed_dict)

            await interaction.followup.send(embed=summary_embed)

        except Exception as e:
            logger.exception(f"Quick summary failed: {e}")
            await self.send_error_response(interaction, e)

    async def handle_scheduled_summary(self,
                                      interaction: discord.Interaction,
                                      channel: discord.TextChannel,
                                      schedule: str,
                                      length: str = "detailed") -> None:
        """
        Handle scheduled summary setup command.

        Args:
            interaction: Discord interaction object
            channel: Target channel for summaries
            schedule: Schedule specification (e.g., "daily", "weekly")
            length: Summary length
        """
        # This is a placeholder - actual scheduling happens in schedule.py
        embed = discord.Embed(
            title="ℹ️ Scheduled Summaries",
            description="Scheduled summary feature is coming soon!",
            color=0x4A90E2
        )

        embed.add_field(
            name="Requested Schedule",
            value=f"Channel: {channel.mention}\nSchedule: {schedule}\nLength: {length}",
            inline=False
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _process_messages(self,
                               raw_messages: List[discord.Message],
                               options: SummaryOptions) -> List[ProcessedMessage]:
        """
        Process raw Discord messages into ProcessedMessages.

        Args:
            raw_messages: List of raw Discord messages
            options: Summary options for filtering

        Returns:
            List of processed messages
        """
        if not raw_messages:
            return []

        # Filter messages
        if self.message_filter:
            self.message_filter.options = options
            filtered_messages = self.message_filter.filter_messages(raw_messages)
        else:
            # Basic filtering
            filtered_messages = [
                msg for msg in raw_messages
                if not msg.author.bot or options.include_bots
            ]

        # Clean and process messages
        processed_messages = []

        for message in filtered_messages:
            if self.message_cleaner:
                processed = self.message_cleaner.clean_message(message)
            else:
                # Basic processing
                processed = ProcessedMessage(
                    id=str(message.id),
                    author_name=message.author.display_name,
                    author_id=str(message.author.id),
                    content=message.content,
                    timestamp=message.created_at,
                    attachments=[],
                    references=[],
                    mentions=[]
                )

            # Only include messages with substantial content
            if processed.has_substantial_content():
                processed_messages.append(processed)

        return processed_messages

    async def _fetch_and_process_messages(self,
                                         channel: discord.TextChannel,
                                         start_time: datetime,
                                         end_time: datetime,
                                         options: SummaryOptions) -> List[ProcessedMessage]:
        """
        Fetch and process messages from a channel.

        Args:
            channel: Discord text channel
            start_time: Start of time range
            end_time: End of time range
            options: Summary options

        Returns:
            List of processed messages
        """
        # Fetch messages from Discord
        if self.message_fetcher:
            raw_messages = await self.message_fetcher.fetch_messages(
                channel_id=str(channel.id),
                start_time=start_time,
                end_time=end_time,
                limit=10000
            )
        else:
            # Fallback: fetch directly from channel
            raw_messages = []
            async for message in channel.history(
                limit=10000,
                after=start_time,
                before=end_time,
                oldest_first=True
            ):
                raw_messages.append(message)

        return await self._process_messages(raw_messages, options)

    async def handle_category_combined_summary(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        excluded_channel_ids: List[str],
        messages: Optional[int] = None,
        hours: Optional[int] = None,
        minutes: Optional[int] = None,
        length: str = "detailed",
        perspective: str = "general"
    ) -> None:
        """Handle category summary in combined mode (one summary for all channels).

        Args:
            interaction: Discord interaction
            category: Discord category to summarize
            excluded_channel_ids: List of channel IDs to exclude
            messages: Number of messages to summarize
            hours: Hours of messages to look back
            minutes: Minutes of messages to look back
            length: Summary length
            perspective: Summary perspective
        """
        try:
            # Permission check - reuse cross_channel_summary_role_name
            if self.config_manager:
                bot_config = self.config_manager.get_current_config()
                if bot_config:
                    guild_config = bot_config.get_guild_config(str(interaction.guild_id))
                    required_role = guild_config.cross_channel_summary_role_name

                    if required_role:
                        user_member = interaction.guild.get_member(interaction.user.id)
                        has_role = any(role.name == required_role for role in user_member.roles)

                        if not has_role:
                            await interaction.followup.send(
                                f"❌ You need the **{required_role}** role to summarize categories.",
                                ephemeral=True
                            )
                            return

            # Resolve category to channels
            channels = resolve_category_channels(category, excluded_channel_ids)

            if not channels:
                await interaction.followup.send(
                    f"❌ No accessible text channels found in category '{category.name}'.",
                    ephemeral=True
                )
                return

            logger.info(f"Category combined summary: {category.name} with {len(channels)} channels")

            # Fetch messages from all channels
            all_messages = []

            for ch in channels:
                try:
                    if messages:
                        raw_messages = await self.fetch_messages(ch, limit=messages)
                    elif hours or minutes:
                        total_hours = (hours or 0) + (minutes or 0) / 60
                        time_delta = timedelta(hours=total_hours if total_hours > 0 else 24)
                        raw_messages = await self.fetch_recent_messages(ch, time_delta)
                    else:
                        raw_messages = await self.fetch_messages(ch, limit=100)

                    all_messages.extend(raw_messages)
                except Exception as e:
                    logger.warning(f"Failed to fetch messages from #{ch.name}: {e}")
                    continue

            # Sort messages chronologically
            all_messages.sort(key=lambda m: m.created_at)

            # Process messages
            summary_length_enum = SummaryLength(length)
            summary_options = SummaryOptions(
                summary_length=summary_length_enum,
                perspective=perspective,
                include_bots=False
            )
            processed_messages = await self._process_messages(all_messages, summary_options)

            if len(processed_messages) < summary_options.min_messages:
                raise InsufficientContentError(
                    message_count=len(processed_messages),
                    min_required=summary_options.min_messages
                )

            # Create summarization context
            channel_names = ", ".join([f"#{ch.name}" for ch in channels])
            time_span = (hours or 0) + (minutes or 0) / 60 if not messages else 0
            context = SummarizationContext(
                channel_name=f"Category: {category.name} ({channel_names})",
                guild_name=interaction.guild.name,
                total_participants=len(set(msg.author_id for msg in processed_messages)),
                time_span_hours=time_span
            )

            # Generate summary
            summary_result = await self.summarization_engine.summarize_messages(
                messages=processed_messages,
                options=summary_options,
                context=context,
                channel_id=str(category.id),
                guild_id=str(interaction.guild_id)
            )

            # Send summary as embed
            summary_embed_dict = summary_result.to_embed_dict()
            summary_embed = discord.Embed.from_dict(summary_embed_dict)

            await interaction.followup.send(embed=summary_embed)

            logger.info(f"Category combined summary completed for {category.name}")

        except Exception as e:
            logger.exception(f"Category combined summary failed: {e}")
            await self.send_error_response(interaction, e)

    async def handle_category_individual_summary(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        excluded_channel_ids: List[str],
        messages: Optional[int] = None,
        hours: Optional[int] = None,
        minutes: Optional[int] = None,
        length: str = "detailed",
        perspective: str = "general"
    ) -> None:
        """Handle category summary in individual mode (separate summaries per channel).

        Args:
            interaction: Discord interaction
            category: Discord category to summarize
            excluded_channel_ids: List of channel IDs to exclude
            messages: Number of messages to summarize
            hours: Hours of messages to look back
            minutes: Minutes of messages to look back
            length: Summary length
            perspective: Summary perspective
        """
        try:
            # Permission check
            if self.config_manager:
                bot_config = self.config_manager.get_current_config()
                if bot_config:
                    guild_config = bot_config.get_guild_config(str(interaction.guild_id))
                    required_role = guild_config.cross_channel_summary_role_name

                    if required_role:
                        user_member = interaction.guild.get_member(interaction.user.id)
                        has_role = any(role.name == required_role for role in user_member.roles)

                        if not has_role:
                            await interaction.followup.send(
                                f"❌ You need the **{required_role}** role to summarize categories.",
                                ephemeral=True
                            )
                            return

            # Resolve category to channels
            channels = resolve_category_channels(category, excluded_channel_ids)

            if not channels:
                await interaction.followup.send(
                    f"❌ No accessible text channels found in category '{category.name}'.",
                    ephemeral=True
                )
                return

            logger.info(f"Category individual summary: {category.name} with {len(channels)} channels")

            # Ask user where to post summaries
            from discord import ui

            class SummaryDestinationView(ui.View):
                def __init__(self):
                    super().__init__(timeout=30)
                    self.destination = None

                @ui.button(label="Post to Each Channel", style=discord.ButtonStyle.primary, custom_id="each_channel")
                async def each_channel(self, interaction: discord.Interaction, button: ui.Button):
                    self.destination = "each"
                    await interaction.response.edit_message(
                        content=f"✅ Will post individual summaries to each channel in **{category.name}**",
                        view=None
                    )
                    self.stop()

                @ui.button(label="Post All Here", style=discord.ButtonStyle.secondary, custom_id="current_channel")
                async def current_channel(self, interaction: discord.Interaction, button: ui.Button):
                    self.destination = "current"
                    await interaction.response.edit_message(
                        content=f"✅ Will post all summaries here",
                        view=None
                    )
                    self.stop()

            # Ask for destination preference
            view = SummaryDestinationView()
            await interaction.followup.send(
                f"📝 Generating individual summaries for {len(channels)} channels in **{category.name}**\n\n"
                f"Where should I post the summaries?",
                view=view
            )

            # Wait for user response
            await view.wait()

            if view.destination is None:
                await interaction.followup.send("❌ Timed out waiting for response. Please try again.")
                return

            post_destination = view.destination

            # Send processing status
            await interaction.followup.send(
                f"🔄 Generating summaries..."
            )

            # Generate summaries for each channel
            results = []
            for ch in channels:
                try:
                    # Fetch messages from this channel
                    if messages:
                        raw_messages = await self.fetch_messages(ch, limit=messages)
                    elif hours or minutes:
                        total_hours = (hours or 0) + (minutes or 0) / 60
                        time_delta = timedelta(hours=total_hours if total_hours > 0 else 24)
                        raw_messages = await self.fetch_recent_messages(ch, time_delta)
                    else:
                        raw_messages = await self.fetch_messages(ch, limit=100)

                    # Process messages
                    summary_length_enum = SummaryLength(length)
                    summary_options = SummaryOptions(
                        summary_length=summary_length_enum,
                        perspective=perspective,
                        include_bots=False
                    )
                    processed_messages = await self._process_messages(raw_messages, summary_options)

                    if len(processed_messages) < summary_options.min_messages:
                        logger.warning(f"#{ch.name}: insufficient messages ({len(processed_messages)} < {summary_options.min_messages})")
                        results.append({"channel": ch, "success": False, "error": "Insufficient messages"})
                        continue

                    # Create summarization context
                    time_span = (hours or 0) + (minutes or 0) / 60 if not messages else 0
                    context = SummarizationContext(
                        channel_name=ch.name,
                        guild_name=interaction.guild.name,
                        total_participants=len(set(msg.author_id for msg in processed_messages)),
                        time_span_hours=time_span
                    )

                    # Generate summary
                    summary_result = await self.summarization_engine.summarize_messages(
                        messages=processed_messages,
                        options=summary_options,
                        context=context,
                        channel_id=str(ch.id),
                        guild_id=str(interaction.guild_id)
                    )

                    results.append({"channel": ch, "summary": summary_result, "success": True})

                except Exception as e:
                    logger.error(f"Failed to summarize #{ch.name}: {e}")
                    results.append({"channel": ch, "success": False, "error": str(e)})

            # Send consolidated response
            success_count = sum(1 for r in results if r["success"])

            await interaction.followup.send(
                f"✅ Generated {success_count}/{len(channels)} summaries for category **{category.name}**"
            )

            # Post summaries based on user preference
            if post_destination == "each":
                # Post individual summaries to their respective channels
                for result in results:
                    if result["success"]:
                        ch = result["channel"]
                        summary = result["summary"]
                        embed_dict = summary.to_embed_dict()
                        embed = discord.Embed.from_dict(embed_dict)

                        try:
                            await ch.send(embed=embed)
                        except Exception as e:
                            logger.error(f"Failed to post summary to #{ch.name}: {e}")

                logger.info(f"Category individual summary completed for {category.name}: {success_count}/{len(channels)} posted to respective channels")
            else:
                # Post all summaries to the current channel
                for result in results:
                    if result["success"]:
                        ch = result["channel"]
                        summary = result["summary"]
                        embed_dict = summary.to_embed_dict()
                        embed = discord.Embed.from_dict(embed_dict)

                        # Add channel name to title
                        embed["title"] = f"#{ch.name}: {embed.get('title', 'Summary')}"

                        try:
                            await interaction.followup.send(embed=embed)
                        except Exception as e:
                            logger.error(f"Failed to post summary for #{ch.name}: {e}")

                logger.info(f"Category individual summary completed for {category.name}: {success_count}/{len(channels)} posted to invocation channel")

        except Exception as e:
            logger.exception(f"Category individual summary failed: {e}")
            await self.send_error_response(interaction, e)

    async def estimate_summary_cost(self,
                                   interaction: discord.Interaction,
                                   channel: Optional[discord.TextChannel] = None,
                                   hours: int = 24) -> None:
        """
        Estimate cost for generating a summary.

        Args:
            interaction: Discord interaction object
            channel: Target channel
            hours: Hours to look back
        """
        await self.defer_response(interaction, ephemeral=True)

        try:
            target_channel = channel or interaction.channel
            end_time = utc_now_naive()
            start_time = end_time - timedelta(hours=hours)

            # Fetch messages to estimate
            options = SummaryOptions()
            processed_messages = await self._fetch_and_process_messages(
                target_channel,
                start_time,
                end_time,
                options
            )

            # Get cost estimate
            cost_estimate = await self.summarization_engine.estimate_cost(
                messages=processed_messages,
                options=options
            )

            # Create response embed
            embed = discord.Embed(
                title="💰 Summary Cost Estimate",
                description=f"Estimated cost for summarizing {target_channel.mention}",
                color=0x4A90E2,
                timestamp=utc_now_naive()
            )

            embed.add_field(
                name="Messages",
                value=str(cost_estimate.message_count),
                inline=True
            )

            embed.add_field(
                name="Estimated Cost",
                value=f"${cost_estimate.estimated_cost_usd:.4f} USD",
                inline=True
            )

            embed.add_field(
                name="Input Tokens",
                value=f"{cost_estimate.input_tokens:,}",
                inline=True
            )

            embed.add_field(
                name="Output Tokens",
                value=f"{cost_estimate.output_tokens:,}",
                inline=True
            )

            embed.add_field(
                name="Model",
                value=cost_estimate.model,
                inline=True
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception(f"Cost estimation failed: {e}")
            await self.send_error_response(interaction, e)
