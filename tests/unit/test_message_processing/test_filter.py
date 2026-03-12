"""
Unit tests for message_processing/filter.py.

Tests MessageFilter for Discord and WhatsApp message filtering.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock
import discord

from src.message_processing.filter import MessageFilter
from src.models.message import ProcessedMessage, SourceType
from src.models.summary import SummaryOptions


class TestMessageFilterDiscord:
    """Tests for MessageFilter with Discord messages."""

    @pytest.fixture
    def filter(self):
        """Create a MessageFilter instance."""
        return MessageFilter()

    @pytest.fixture
    def default_options(self):
        """Create default SummaryOptions."""
        return SummaryOptions(
            include_bots=False,
            excluded_users=[],
            min_messages=1
        )

    @pytest.fixture
    def mock_discord_message(self):
        """Create a mock Discord message."""
        def _create_message(
            content="Test message",
            author_id=123456,
            is_bot=False,
            message_type=discord.MessageType.default,
            has_attachments=False,
            created_at=None
        ):
            message = MagicMock(spec=discord.Message)
            message.content = content
            message.author.id = author_id
            message.author.bot = is_bot
            message.type = message_type
            message.attachments = [MagicMock()] if has_attachments else []
            message.created_at = created_at or datetime.utcnow()
            return message
        return _create_message

    def test_filter_messages_basic(self, filter, default_options, mock_discord_message):
        """Basic filtering keeps valid messages."""
        messages = [
            mock_discord_message(content="Message 1"),
            mock_discord_message(content="Message 2"),
        ]

        filtered = filter.filter_messages(messages, default_options)

        assert len(filtered) == 2

    def test_filter_messages_excludes_bots(self, filter, default_options, mock_discord_message):
        """Bot messages are excluded by default."""
        messages = [
            mock_discord_message(content="Human message", is_bot=False),
            mock_discord_message(content="Bot message", is_bot=True),
        ]

        filtered = filter.filter_messages(messages, default_options)

        assert len(filtered) == 1
        assert filtered[0].content == "Human message"

    def test_filter_messages_includes_bots_when_enabled(
        self, filter, mock_discord_message
    ):
        """Bot messages included when option is True."""
        options = SummaryOptions(include_bots=True)
        messages = [
            mock_discord_message(content="Human message", is_bot=False),
            mock_discord_message(content="Bot message", is_bot=True),
        ]

        filtered = filter.filter_messages(messages, options)

        assert len(filtered) == 2

    def test_filter_messages_excludes_system_messages(
        self, filter, default_options, mock_discord_message
    ):
        """System messages are excluded."""
        messages = [
            mock_discord_message(content="Normal", message_type=discord.MessageType.default),
            mock_discord_message(content="Join", message_type=discord.MessageType.new_member),
        ]

        filtered = filter.filter_messages(messages, default_options)

        assert len(filtered) == 1

    def test_filter_messages_keeps_reply_messages(
        self, filter, default_options, mock_discord_message
    ):
        """Reply messages are kept."""
        messages = [
            mock_discord_message(content="Normal", message_type=discord.MessageType.default),
            mock_discord_message(content="Reply", message_type=discord.MessageType.reply),
        ]

        filtered = filter.filter_messages(messages, default_options)

        assert len(filtered) == 2

    def test_filter_messages_excludes_empty_messages(
        self, filter, default_options, mock_discord_message
    ):
        """Empty messages without attachments are excluded."""
        messages = [
            mock_discord_message(content="Has content"),
            mock_discord_message(content="", has_attachments=False),
            mock_discord_message(content=None, has_attachments=False),
        ]

        filtered = filter.filter_messages(messages, default_options)

        assert len(filtered) == 1

    def test_filter_messages_keeps_empty_with_attachments(
        self, filter, default_options, mock_discord_message
    ):
        """Empty messages with attachments are kept."""
        messages = [
            mock_discord_message(content="", has_attachments=True),
        ]

        filtered = filter.filter_messages(messages, default_options)

        assert len(filtered) == 1

    def test_filter_messages_excludes_specific_users(
        self, filter, mock_discord_message
    ):
        """Messages from excluded users are filtered."""
        options = SummaryOptions(excluded_users=["123456"])
        messages = [
            mock_discord_message(content="Excluded", author_id=123456),
            mock_discord_message(content="Included", author_id=789012),
        ]

        filtered = filter.filter_messages(messages, options)

        assert len(filtered) == 1
        assert filtered[0].content == "Included"

    def test_filter_messages_sorted_by_timestamp(
        self, filter, default_options, mock_discord_message
    ):
        """Filtered messages are sorted chronologically."""
        now = datetime.utcnow()
        messages = [
            mock_discord_message(content="Third", created_at=now + timedelta(hours=2)),
            mock_discord_message(content="First", created_at=now),
            mock_discord_message(content="Second", created_at=now + timedelta(hours=1)),
        ]

        filtered = filter.filter_messages(messages, default_options)

        assert [m.content for m in filtered] == ["First", "Second", "Third"]


class TestMessageFilterProcessed:
    """Tests for MessageFilter with ProcessedMessage objects."""

    @pytest.fixture
    def filter(self):
        """Create a MessageFilter instance."""
        return MessageFilter()

    @pytest.fixture
    def default_options(self):
        """Create default SummaryOptions."""
        return SummaryOptions(excluded_users=[], min_messages=1)

    @pytest.fixture
    def create_processed_message(self):
        """Factory for creating ProcessedMessage objects."""
        def _create(
            content="Test message",
            author_id="123",
            source_type=SourceType.DISCORD,
            channel_id="channel123",
            timestamp=None,
            attachments=None,
            is_deleted=False,
            is_forwarded=False
        ):
            msg = ProcessedMessage(
                id="msg123",
                author_name="Test User",
                author_id=author_id,
                content=content,
                timestamp=timestamp or datetime.utcnow(),
                source_type=source_type,
                channel_id=channel_id,
                attachments=attachments or [],
            )
            msg.is_deleted = is_deleted
            msg.is_forwarded = is_forwarded
            return msg
        return _create

    def test_filter_processed_messages_basic(
        self, filter, default_options, create_processed_message
    ):
        """Basic filtering for processed messages."""
        messages = [
            create_processed_message(content="Message 1"),
            create_processed_message(content="Message 2"),
        ]

        filtered = filter.filter_processed_messages(messages, default_options)

        assert len(filtered) == 2

    def test_filter_processed_messages_discord(
        self, filter, default_options, create_processed_message
    ):
        """Discord messages filtered correctly."""
        messages = [
            create_processed_message(content="Has content"),
            create_processed_message(content="", attachments=[]),  # Empty, no attachments
        ]

        filtered = filter.filter_processed_messages(messages, default_options)

        assert len(filtered) == 1

    def test_filter_processed_messages_excludes_users(
        self, filter, create_processed_message
    ):
        """Excluded users are filtered from processed messages."""
        options = SummaryOptions(excluded_users=["user123"])
        messages = [
            create_processed_message(content="Keep", author_id="user456"),
            create_processed_message(content="Exclude", author_id="user123"),
        ]

        filtered = filter.filter_processed_messages(messages, options)

        assert len(filtered) == 1
        assert filtered[0].content == "Keep"

    def test_filter_processed_messages_sorted(
        self, filter, default_options, create_processed_message
    ):
        """Processed messages are sorted by timestamp."""
        now = datetime.utcnow()
        messages = [
            create_processed_message(content="Third", timestamp=now + timedelta(hours=2)),
            create_processed_message(content="First", timestamp=now),
            create_processed_message(content="Second", timestamp=now + timedelta(hours=1)),
        ]

        filtered = filter.filter_processed_messages(messages, default_options)

        assert [m.content for m in filtered] == ["First", "Second", "Third"]


class TestMessageFilterWhatsApp:
    """Tests for MessageFilter with WhatsApp messages."""

    @pytest.fixture
    def filter(self):
        """Create a MessageFilter instance."""
        return MessageFilter()

    @pytest.fixture
    def default_options(self):
        """Create default SummaryOptions."""
        return SummaryOptions(excluded_users=[], min_messages=1)

    @pytest.fixture
    def create_whatsapp_message(self):
        """Factory for creating WhatsApp ProcessedMessage objects."""
        def _create(
            content="Test message",
            author_id="123",
            channel_id="group123",
            is_deleted=False,
            is_forwarded=False,
            has_attachments=False
        ):
            msg = ProcessedMessage(
                id="msg123",
                author_name="Test User",
                author_id=author_id,
                content=content,
                timestamp=datetime.utcnow(),
                source_type=SourceType.WHATSAPP,
                channel_id=channel_id,
                attachments=[MagicMock()] if has_attachments else [],
            )
            msg.is_deleted = is_deleted
            msg.is_forwarded = is_forwarded
            return msg
        return _create

    def test_whatsapp_excludes_deleted_messages(
        self, filter, default_options, create_whatsapp_message
    ):
        """Deleted WhatsApp messages are excluded."""
        messages = [
            create_whatsapp_message(content="Visible"),
            create_whatsapp_message(content="Deleted", is_deleted=True),
        ]

        filtered = filter.filter_processed_messages(messages, default_options)

        assert len(filtered) == 1
        assert filtered[0].content == "Visible"

    def test_whatsapp_excludes_status_broadcast(
        self, filter, default_options, create_whatsapp_message
    ):
        """WhatsApp status broadcast messages are excluded."""
        messages = [
            create_whatsapp_message(content="Normal", channel_id="group123"),
            create_whatsapp_message(content="Status", channel_id="status@broadcast"),
        ]

        filtered = filter.filter_processed_messages(messages, default_options)

        assert len(filtered) == 1
        assert filtered[0].content == "Normal"

    def test_whatsapp_excludes_empty_messages(
        self, filter, default_options, create_whatsapp_message
    ):
        """Empty WhatsApp messages without attachments are excluded."""
        messages = [
            create_whatsapp_message(content="Has content"),
            create_whatsapp_message(content="", has_attachments=False),
        ]

        filtered = filter.filter_processed_messages(messages, default_options)

        assert len(filtered) == 1

    def test_whatsapp_keeps_empty_with_attachments(
        self, filter, default_options, create_whatsapp_message
    ):
        """Empty WhatsApp messages with attachments are kept."""
        messages = [
            create_whatsapp_message(content="", has_attachments=True),
        ]

        filtered = filter.filter_processed_messages(messages, default_options)

        assert len(filtered) == 1

    def test_whatsapp_excludes_users(
        self, filter, create_whatsapp_message
    ):
        """Excluded users are filtered from WhatsApp messages."""
        options = SummaryOptions(excluded_users=["blocked_user"])
        messages = [
            create_whatsapp_message(content="Keep", author_id="normal_user"),
            create_whatsapp_message(content="Block", author_id="blocked_user"),
        ]

        filtered = filter.filter_processed_messages(messages, options)

        assert len(filtered) == 1
        assert filtered[0].content == "Keep"
