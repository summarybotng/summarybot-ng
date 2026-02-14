"""
Message filtering logic.

Supports multi-source message handling per ADR-002/003.
"""

from typing import List, Union
import discord
from ..models.summary import SummaryOptions
from ..models.message import ProcessedMessage, SourceType


class MessageFilter:
    """Filters messages from Discord and WhatsApp based on summarization options."""

    def filter_messages(self,
                       messages: List[discord.Message],
                       options: SummaryOptions) -> List[discord.Message]:
        """Filter Discord messages based on options."""
        filtered = []

        for message in messages:
            if self._should_include_message(message, options):
                filtered.append(message)

        # Sort by timestamp to maintain chronological order
        filtered.sort(key=lambda m: m.created_at)
        return filtered

    def filter_processed_messages(
        self,
        messages: List[ProcessedMessage],
        options: SummaryOptions,
    ) -> List[ProcessedMessage]:
        """Filter ProcessedMessages based on source type and options (ADR-002).

        Args:
            messages: List of ProcessedMessage objects
            options: Summary options including source_type

        Returns:
            Filtered list of messages
        """
        filtered = []

        for message in messages:
            if self._should_include_processed(message, options):
                filtered.append(message)

        # Sort by timestamp
        filtered.sort(key=lambda m: m.timestamp)
        return filtered

    def _should_include_processed(
        self,
        message: ProcessedMessage,
        options: SummaryOptions,
    ) -> bool:
        """Check if a ProcessedMessage should be included (ADR-002)."""
        if message.source_type == SourceType.WHATSAPP:
            return self._should_include_whatsapp(message, options)
        return self._should_include_discord_processed(message, options)

    def _should_include_discord_processed(
        self,
        message: ProcessedMessage,
        options: SummaryOptions,
    ) -> bool:
        """Check if a Discord ProcessedMessage should be included."""
        # Skip empty messages without attachments
        if not message.content and not message.attachments:
            return False

        # Skip messages from excluded users
        if message.author_id in options.excluded_users:
            return False

        return True

    def _should_include_whatsapp(
        self,
        message: ProcessedMessage,
        options: SummaryOptions,
    ) -> bool:
        """Check if a WhatsApp message should be included (ADR-002)."""
        # Skip deleted messages
        if getattr(message, 'is_deleted', False):
            return False

        # Skip status broadcast messages
        if message.channel_id and 'status@broadcast' in message.channel_id:
            return False

        # Skip empty messages without attachments
        if not message.content and not message.attachments:
            return False

        # Skip forwarded messages if not included
        if getattr(message, 'is_forwarded', False) and not getattr(options, 'include_forwarded', True):
            return False

        # Skip messages from excluded users
        if message.author_id in options.excluded_users:
            return False

        return True

    def _should_include_message(self,
                               message: discord.Message,
                               options: SummaryOptions) -> bool:
        """Check if Discord message should be included."""
        # Skip bot messages unless explicitly included
        if message.author.bot and not options.include_bots:
            return False

        # Skip system messages
        if message.type not in [discord.MessageType.default, discord.MessageType.reply]:
            return False

        # Skip empty messages without attachments
        if not message.content and not message.attachments:
            return False

        # Skip messages from excluded users
        if str(message.author.id) in options.excluded_users:
            return False

        return True