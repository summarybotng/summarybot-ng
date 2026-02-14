"""
Message content cleaning and normalization.

Supports multi-source message handling per ADR-002/003.
"""

import re
import discord
from ..models.message import ProcessedMessage, MessageType, SourceType


class MessageCleaner:
    """Cleans and normalizes message content from Discord and WhatsApp."""

    def clean_message(self, message: discord.Message) -> ProcessedMessage:
        """Clean a Discord message into ProcessedMessage format."""
        return ProcessedMessage(
            id=str(message.id),
            author_name=message.author.display_name,
            author_id=str(message.author.id),
            content=self._clean_content(message.content or ""),
            timestamp=message.created_at,
            message_type=MessageType(message.type.value) if message.type.value < 22 else MessageType.DEFAULT,
            is_edited=message.edited_at is not None,
            is_pinned=message.pinned,
            channel_id=str(message.channel.id),
            channel_name=getattr(message.channel, 'name', None),
            source_type=SourceType.DISCORD,
        )

    def clean(self, message: ProcessedMessage) -> ProcessedMessage:
        """Clean a ProcessedMessage based on its source type (ADR-002).

        Args:
            message: ProcessedMessage to clean

        Returns:
            Cleaned ProcessedMessage
        """
        if message.source_type == SourceType.WHATSAPP:
            return self._clean_whatsapp(message)
        return self._clean_discord(message)

    def _clean_discord(self, message: ProcessedMessage) -> ProcessedMessage:
        """Clean Discord-specific content."""
        message.content = self._clean_content(message.content)
        return message

    def _clean_whatsapp(self, message: ProcessedMessage) -> ProcessedMessage:
        """Clean WhatsApp-specific formatting (ADR-002)."""
        text = message.content or ""

        # Normalize WhatsApp bold (*text*) to markdown bold (**text**)
        # Only match single asterisks that aren't already double
        text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'**\1**', text)

        # Normalize WhatsApp italic (_text_) to markdown italic (*text*)
        text = re.sub(r'(?<!_)_(?!_)(.+?)(?<!_)_(?!_)', r'*\1*', text)

        # Keep strikethrough as-is (~text~ is valid markdown)

        # Remove zero-width characters common in WhatsApp
        text = text.replace('\u200e', '')  # Left-to-right mark
        text = text.replace('\u200f', '')  # Right-to-left mark
        text = text.replace('\u200b', '')  # Zero-width space
        text = text.replace('\u200c', '')  # Zero-width non-joiner
        text = text.replace('\u200d', '')  # Zero-width joiner
        text = text.replace('\ufeff', '')  # BOM

        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        message.content = text
        return message

    def _clean_content(self, content: str) -> str:
        """Clean Discord message content."""
        if not content:
            return ""

        # Remove excessive whitespace
        content = re.sub(r'\s+', ' ', content).strip()

        # Keep mentions but make them readable
        content = re.sub(r'<@!?(\d+)>', r'@user', content)
        content = re.sub(r'<@&(\d+)>', r'@role', content)
        content = re.sub(r'<#(\d+)>', r'#channel', content)

        # Keep custom emojis but make them readable
        content = re.sub(r'<a?:[a-zA-Z0-9_]+:(\d+)>', r':emoji:', content)

        return content