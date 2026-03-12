"""
Unit tests for message_processing/cleaner.py.

Tests MessageCleaner for content normalization and cleaning.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock
import discord

from src.message_processing.cleaner import MessageCleaner
from src.models.message import ProcessedMessage, SourceType


class TestMessageCleanerDiscord:
    """Tests for MessageCleaner with Discord messages."""

    @pytest.fixture
    def cleaner(self):
        """Create a MessageCleaner instance."""
        return MessageCleaner()

    @pytest.fixture
    def mock_discord_message(self):
        """Create a mock Discord message."""
        def _create(
            content="Test message",
            author_name="TestUser",
            author_id=123456,
            message_id=789012,
            channel_id=111222,
            channel_name="test-channel",
            is_edited=False,
            is_pinned=False,
            message_type=discord.MessageType.default
        ):
            message = MagicMock(spec=discord.Message)
            message.id = message_id
            message.content = content
            message.author.display_name = author_name
            message.author.id = author_id
            message.created_at = datetime.utcnow()
            message.edited_at = datetime.utcnow() if is_edited else None
            message.pinned = is_pinned
            message.channel.id = channel_id
            message.channel.name = channel_name
            message.type = message_type
            return message
        return _create

    def test_clean_message_basic(self, cleaner, mock_discord_message):
        """Basic message cleaning produces ProcessedMessage."""
        msg = mock_discord_message(content="Hello world")

        result = cleaner.clean_message(msg)

        assert isinstance(result, ProcessedMessage)
        assert result.content == "Hello world"
        assert result.source_type == SourceType.DISCORD

    def test_clean_message_preserves_metadata(self, cleaner, mock_discord_message):
        """Message metadata is preserved."""
        msg = mock_discord_message(
            content="Test",
            author_name="Alice",
            author_id=12345,
            channel_name="general"
        )

        result = cleaner.clean_message(msg)

        assert result.author_name == "Alice"
        assert result.author_id == "12345"
        assert result.channel_name == "general"

    def test_clean_message_edited_flag(self, cleaner, mock_discord_message):
        """Edited flag is set correctly."""
        unedited = mock_discord_message(content="Original", is_edited=False)
        edited = mock_discord_message(content="Edited", is_edited=True)

        assert cleaner.clean_message(unedited).is_edited is False
        assert cleaner.clean_message(edited).is_edited is True

    def test_clean_message_pinned_flag(self, cleaner, mock_discord_message):
        """Pinned flag is set correctly."""
        unpinned = mock_discord_message(content="Normal", is_pinned=False)
        pinned = mock_discord_message(content="Important", is_pinned=True)

        assert cleaner.clean_message(unpinned).is_pinned is False
        assert cleaner.clean_message(pinned).is_pinned is True


class TestContentCleaning:
    """Tests for content cleaning/normalization."""

    @pytest.fixture
    def cleaner(self):
        """Create a MessageCleaner instance."""
        return MessageCleaner()

    def test_clean_content_whitespace(self, cleaner):
        """Excessive whitespace is normalized."""
        result = cleaner._clean_content("Hello   world\n\ntest")
        assert result == "Hello world test"

    def test_clean_content_user_mentions(self, cleaner):
        """User mentions are normalized."""
        result = cleaner._clean_content("Hey <@123456789> check this")
        assert result == "Hey @user check this"

        # Also with ! format
        result = cleaner._clean_content("Hey <@!987654321>")
        assert result == "Hey @user"

    def test_clean_content_role_mentions(self, cleaner):
        """Role mentions are normalized."""
        result = cleaner._clean_content("Attention <@&111222333>!")
        assert result == "Attention @role!"

    def test_clean_content_channel_mentions(self, cleaner):
        """Channel mentions are normalized."""
        result = cleaner._clean_content("See <#444555666> for details")
        assert result == "See #channel for details"

    def test_clean_content_custom_emojis(self, cleaner):
        """Custom emojis are normalized."""
        # Static emoji
        result = cleaner._clean_content("Nice <:thumbsup:123456>")
        assert result == "Nice :emoji:"

        # Animated emoji
        result = cleaner._clean_content("Party <a:partyparrot:789012>")
        assert result == "Party :emoji:"

    def test_clean_content_empty(self, cleaner):
        """Empty content returns empty string."""
        assert cleaner._clean_content("") == ""
        assert cleaner._clean_content(None) == ""

    def test_clean_content_strips_whitespace(self, cleaner):
        """Leading and trailing whitespace is stripped."""
        result = cleaner._clean_content("  Hello world  ")
        assert result == "Hello world"


class TestWhatsAppCleaning:
    """Tests for WhatsApp-specific content cleaning."""

    @pytest.fixture
    def cleaner(self):
        """Create a MessageCleaner instance."""
        return MessageCleaner()

    @pytest.fixture
    def create_whatsapp_message(self):
        """Factory for creating WhatsApp ProcessedMessage."""
        def _create(content):
            return ProcessedMessage(
                id="msg123",
                author_name="Test User",
                author_id="123",
                content=content,
                timestamp=datetime.utcnow(),
                source_type=SourceType.WHATSAPP,
            )
        return _create

    def test_whatsapp_bold_conversion(self, cleaner, create_whatsapp_message):
        """WhatsApp *bold* is converted to markdown **bold**."""
        msg = create_whatsapp_message("This is *bold* text")
        result = cleaner._clean_whatsapp(msg)
        assert result.content == "This is **bold** text"

    def test_whatsapp_italic_conversion(self, cleaner, create_whatsapp_message):
        """WhatsApp _italic_ is converted to markdown *italic*."""
        msg = create_whatsapp_message("This is _italic_ text")
        result = cleaner._clean_whatsapp(msg)
        assert result.content == "This is *italic* text"

    def test_whatsapp_strikethrough_preserved(self, cleaner, create_whatsapp_message):
        """WhatsApp ~strikethrough~ is preserved."""
        msg = create_whatsapp_message("This is ~strikethrough~ text")
        result = cleaner._clean_whatsapp(msg)
        assert "~strikethrough~" in result.content

    def test_whatsapp_zero_width_characters_removed(
        self, cleaner, create_whatsapp_message
    ):
        """Zero-width characters are removed."""
        # Zero-width chars between words without spaces merge the words
        msg = create_whatsapp_message("Hello\u200bworld\u200etest\ufeff")
        result = cleaner._clean_whatsapp(msg)
        assert result.content == "Helloworldtest"

        # With proper spaces, words are preserved
        msg = create_whatsapp_message("Hello\u200b world\u200e test\ufeff")
        result = cleaner._clean_whatsapp(msg)
        assert result.content == "Hello world test"

    def test_whatsapp_excessive_whitespace(self, cleaner, create_whatsapp_message):
        """Excessive whitespace is normalized."""
        msg = create_whatsapp_message("Hello   world\n\ntest")
        result = cleaner._clean_whatsapp(msg)
        assert result.content == "Hello world test"

    def test_whatsapp_empty_content(self, cleaner, create_whatsapp_message):
        """Empty content is handled."""
        msg = create_whatsapp_message("")
        result = cleaner._clean_whatsapp(msg)
        assert result.content == ""

        msg = create_whatsapp_message(None)
        result = cleaner._clean_whatsapp(msg)
        assert result.content == ""


class TestCleanMethod:
    """Tests for the main clean() method that routes by source type."""

    @pytest.fixture
    def cleaner(self):
        """Create a MessageCleaner instance."""
        return MessageCleaner()

    def test_clean_routes_discord(self, cleaner):
        """Discord messages are routed to Discord cleaner."""
        msg = ProcessedMessage(
            id="msg123",
            author_name="User",
            author_id="123",
            content="<@123456> hello",
            timestamp=datetime.utcnow(),
            source_type=SourceType.DISCORD,
        )

        result = cleaner.clean(msg)

        # Discord cleaner normalizes mentions
        assert "@user" in result.content

    def test_clean_routes_whatsapp(self, cleaner):
        """WhatsApp messages are routed to WhatsApp cleaner."""
        msg = ProcessedMessage(
            id="msg123",
            author_name="User",
            author_id="123",
            content="*bold* and _italic_",
            timestamp=datetime.utcnow(),
            source_type=SourceType.WHATSAPP,
        )

        result = cleaner.clean(msg)

        # WhatsApp cleaner converts formatting
        assert "**bold**" in result.content
        assert "*italic*" in result.content
