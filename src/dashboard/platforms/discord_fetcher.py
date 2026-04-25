"""
Discord Platform Fetcher (ADR-051).

Implements PlatformFetcher for Discord guilds.
"""

import logging
from typing import List, Optional, Callable, Dict
from datetime import datetime

import discord

from .base import PlatformFetcher
from .types import FetchResult, PlatformContext, ChannelInfo
from src.models.message import ProcessedMessage, MessageType, SourceType
from src.models.summary import SummaryOptions
from src.message_processing.processor import MessageProcessor

logger = logging.getLogger(__name__)


class DiscordFetcher(PlatformFetcher):
    """
    Discord implementation of PlatformFetcher.

    Handles message fetching, user resolution, and channel operations
    for Discord guilds using the existing MessageProcessor.
    """

    def __init__(self, guild: discord.Guild, bot: discord.Client):
        """Initialize Discord fetcher.

        Args:
            guild: Discord guild object
            bot: Discord bot client
        """
        self._guild = guild
        self._bot = bot
        self._processor = MessageProcessor(bot)

    @property
    def platform_name(self) -> str:
        return "discord"

    @property
    def platform_display_name(self) -> str:
        return "Discord"

    @property
    def server_id(self) -> str:
        return str(self._guild.id)

    @property
    def server_name(self) -> str:
        return self._guild.name

    async def fetch_messages(
        self,
        channel_ids: List[str],
        start_time: datetime,
        end_time: datetime,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> FetchResult:
        """
        Fetch messages from Discord channels.

        Uses the existing MessageProcessor for consistent message handling.
        """
        all_messages: List[ProcessedMessage] = []
        channel_names: Dict[str, str] = {}
        user_names: Dict[str, str] = {}
        errors: List[tuple] = []

        total_channels = len(channel_ids)

        for idx, channel_id in enumerate(channel_ids):
            try:
                channel = self._guild.get_channel(int(channel_id))
                if not channel:
                    # Try to fetch if not in cache
                    try:
                        channel = await self._bot.fetch_channel(int(channel_id))
                    except discord.NotFound:
                        errors.append((channel_id, "Channel not found"))
                        continue
                    except discord.Forbidden:
                        errors.append((channel_id, "No permission to access channel"))
                        continue

                if not isinstance(channel, discord.TextChannel):
                    errors.append((channel_id, "Not a text channel"))
                    continue

                channel_names[channel_id] = channel.name

                # Fetch and process messages
                raw_messages: List[discord.Message] = []
                async for message in channel.history(
                    after=start_time,
                    before=end_time,
                    limit=10000,  # High limit, we filter later
                    oldest_first=True,
                ):
                    raw_messages.append(message)
                    # Extract user names while we have the Message objects
                    user_names[str(message.author.id)] = message.author.display_name

                # Process through MessageProcessor
                options = SummaryOptions(min_messages=1)
                processed = await self._processor.process_messages(raw_messages, options)

                # Ensure source_type is set correctly
                for msg in processed:
                    msg.source_type = SourceType.DISCORD
                    msg.channel_name = channel.name

                all_messages.extend(processed)

                if progress_callback:
                    progress_callback(idx + 1, total_channels, f"Fetched #{channel.name}")

            except discord.Forbidden as e:
                error_msg = f"No permission to read channel: {str(e)}"
                logger.warning(f"Permission error for channel {channel_id}: {error_msg}")
                errors.append((channel_id, error_msg))

            except Exception as e:
                error_msg = str(e)
                logger.exception(f"Error fetching Discord channel {channel_id}")
                errors.append((channel_id, error_msg))

        return FetchResult(
            messages=all_messages,
            channel_names=channel_names,
            user_names=user_names,
            errors=errors,
        )

    async def resolve_channels(
        self,
        scope: str,
        channel_ids: Optional[List[str]] = None,
        category_id: Optional[str] = None,
    ) -> List[str]:
        """
        Resolve channel IDs based on scope.

        Supports channel, category, and guild scopes for Discord.
        """
        if scope == "channel":
            if not channel_ids:
                raise ValueError("channel_ids required for channel scope")
            # Validate channels exist
            valid_ids = []
            for cid in channel_ids:
                channel = self._guild.get_channel(int(cid))
                if channel and isinstance(channel, discord.TextChannel):
                    valid_ids.append(cid)
            return valid_ids

        elif scope == "category":
            if not category_id:
                raise ValueError("category_id required for category scope")

            category = self._guild.get_channel(int(category_id))
            if not category or not isinstance(category, discord.CategoryChannel):
                raise ValueError(f"Category {category_id} not found")

            return [
                str(ch.id)
                for ch in category.text_channels
                if isinstance(ch, discord.TextChannel)
            ]

        elif scope == "guild":
            # Get all text channels in the guild
            return [
                str(ch.id)
                for ch in self._guild.text_channels
                if isinstance(ch, discord.TextChannel)
            ]

        else:
            raise ValueError(f"Unknown scope: {scope}")

    async def get_channels(self) -> List[ChannelInfo]:
        """Get all accessible text channels in the guild."""
        channels = []

        for channel in self._guild.text_channels:
            # Check if bot can read the channel
            perms = channel.permissions_for(self._guild.me)
            is_accessible = perms.read_messages and perms.read_message_history

            channels.append(ChannelInfo(
                channel_id=str(channel.id),
                name=channel.name,
                channel_type="text",
                is_accessible=is_accessible,
                parent_id=str(channel.category_id) if channel.category_id else None,
            ))

        return channels

    async def get_context(
        self,
        channel_ids: List[str],
    ) -> PlatformContext:
        """Build summarization context."""
        channel_names: Dict[str, str] = {}

        for channel_id in channel_ids:
            channel = self._guild.get_channel(int(channel_id))
            if channel:
                channel_names[channel_id] = channel.name
            else:
                channel_names[channel_id] = channel_id

        primary_channel = channel_names.get(channel_ids[0], "unknown") if channel_ids else "unknown"

        return PlatformContext(
            platform_name=self.platform_display_name,
            server_name=self._guild.name,
            server_id=str(self._guild.id),
            primary_channel_name=primary_channel,
            channel_names=channel_names,
        )

    def get_archive_source_key(self) -> str:
        """Return archive key for this Discord guild."""
        return f"discord:{self._guild.id}"

    async def close(self) -> None:
        """Discord client is managed globally, nothing to close."""
        pass
