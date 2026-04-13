"""
Tests for src/slack/normalizer.py - Message conversion to ProcessedMessage.

Tests Slack message normalization including content cleaning,
user resolution, attachment handling, and thread reconstruction.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from src.slack.normalizer import SlackMessageProcessor, SlackThreadReconstructor
from src.slack.models import SlackMessage, SlackChannel, SlackUser, SlackChannelType
from src.models.message import (
    ProcessedMessage,
    SourceType,
    MessageType,
    AttachmentType,
)


class TestSlackMessageProcessor:
    """Tests for SlackMessageProcessor class."""

    @pytest.fixture
    def processor(self, users_cache):
        """Create a processor with user cache."""
        return SlackMessageProcessor(users_cache=users_cache)

    @pytest.fixture
    def processor_no_cache(self):
        """Create a processor without user cache."""
        return SlackMessageProcessor()

    def test_should_convert_simple_message(
        self, processor, slack_message, slack_channel
    ):
        """Test converting a simple text message."""
        result = processor.convert_message(slack_message, slack_channel)

        assert result is not None
        assert isinstance(result, ProcessedMessage)
        assert result.id == slack_message.ts
        assert result.content == "Hello, this is a test message!"
        assert result.source_type == SourceType.SLACK
        assert result.message_type == MessageType.SLACK_TEXT

    def test_should_resolve_user_name_from_cache(
        self, processor, slack_message, slack_channel
    ):
        """Test user name is resolved from cache."""
        result = processor.convert_message(slack_message, slack_channel)

        assert result.author_name == "testuser"

    def test_should_use_user_id_when_not_in_cache(
        self, processor_no_cache, slack_message, slack_channel
    ):
        """Test user ID is used when not in cache."""
        result = processor_no_cache.convert_message(slack_message, slack_channel)

        assert result.author_name == "U11111111"

    def test_should_set_channel_context(
        self, processor, slack_message, slack_channel
    ):
        """Test channel info is set on message."""
        result = processor.convert_message(slack_message, slack_channel)

        assert result.channel_id == "C12345678"
        assert result.channel_name == "general"

    def test_should_convert_thread_reply(
        self, processor, slack_thread_reply, slack_channel
    ):
        """Test converting a thread reply message."""
        result = processor.convert_message(slack_thread_reply, slack_channel)

        assert result.message_type == MessageType.SLACK_THREAD_REPLY
        assert result.reply_to_id == "1705312800.000001"

    def test_should_convert_bot_message(
        self, processor, slack_bot_message, slack_channel
    ):
        """Test converting a bot message."""
        result = processor.convert_message(slack_bot_message, slack_channel)

        assert result.message_type == MessageType.SLACK_BOT

    def test_should_convert_message_with_file(
        self, processor, slack_message_with_file, slack_channel
    ):
        """Test converting a message with file attachment."""
        result = processor.convert_message(slack_message_with_file, slack_channel)

        assert result.message_type == MessageType.SLACK_FILE
        assert len(result.attachments) == 1
        assert result.attachments[0].filename == "document.pdf"
        assert result.attachments[0].type == AttachmentType.DOCUMENT

    def test_should_convert_batch_of_messages(self, processor, slack_channel):
        """Test batch conversion of messages."""
        messages = [
            SlackMessage(
                ts=f"1705312800.00000{i}",
                channel_id="C12345678",
                workspace_id="T12345678",
                user_id="U11111111",
                text=f"Message {i}",
            )
            for i in range(5)
        ]

        results = processor.convert_batch(messages, slack_channel)

        assert len(results) == 5
        assert all(isinstance(r, ProcessedMessage) for r in results)

    def test_should_skip_system_messages_in_batch(self, processor, slack_channel):
        """Test system messages are skipped in batch."""
        messages = [
            SlackMessage(
                ts="1705312800.000001",
                channel_id="C12345678",
                workspace_id="T12345678",
                user_id="U11111111",
                text="Regular message",
                subtype=None,
            ),
            SlackMessage(
                ts="1705312800.000002",
                channel_id="C12345678",
                workspace_id="T12345678",
                user_id="U11111111",
                text="joined the channel",
                subtype="channel_join",
            ),
        ]

        results = processor.convert_batch(messages, slack_channel)

        assert len(results) == 1
        assert results[0].content == "Regular message"

    def test_should_count_reactions(
        self, processor, slack_thread_parent, slack_channel
    ):
        """Test reaction count is calculated."""
        result = processor.convert_message(slack_thread_parent, slack_channel)

        # slack_thread_parent has reactions with 2 users
        assert result.reactions_count == 2


class TestSlackContentCleaning:
    """Tests for Slack content cleaning."""

    @pytest.fixture
    def processor(self):
        """Create processor with mock user cache."""
        mock_user = MagicMock()
        mock_user.display_name = "johndoe"
        return SlackMessageProcessor(users_cache={"U12345678": mock_user})

    def test_should_clean_user_mentions(self, processor):
        """Test user mentions are cleaned."""
        content = "Hey <@U12345678>, check this out"
        result = processor._clean_slack_content(content)

        assert result == "Hey @johndoe, check this out"

    def test_should_clean_channel_mentions_with_name(self, processor):
        """Test channel mentions with name are cleaned."""
        content = "See <#C12345678|general> for details"
        result = processor._clean_slack_content(content)

        assert result == "See #general for details"

    def test_should_clean_channel_mentions_without_name(self, processor):
        """Test channel mentions without name are cleaned."""
        content = "See <#C12345678> for details"
        result = processor._clean_slack_content(content)

        assert result == "See #channel for details"

    def test_should_clean_special_mentions(self, processor):
        """Test special mentions are cleaned."""
        content = "<!here> and <!channel> and <!everyone>"
        result = processor._clean_slack_content(content)

        assert "@here" in result
        assert "@channel" in result
        assert "@everyone" in result

    def test_should_clean_links_with_display_text(self, processor):
        """Test links with display text are cleaned."""
        content = "Check <https://example.com|this link>"
        result = processor._clean_slack_content(content)

        assert result == "Check this link (https://example.com)"

    def test_should_clean_bare_links(self, processor):
        """Test bare links are cleaned."""
        content = "Visit <https://example.com>"
        result = processor._clean_slack_content(content)

        assert result == "Visit https://example.com"

    def test_should_handle_empty_content(self, processor):
        """Test empty content is handled."""
        assert processor._clean_slack_content("") == ""
        assert processor._clean_slack_content(None) == ""

    def test_should_clean_extra_whitespace(self, processor):
        """Test extra whitespace is normalized."""
        content = "Hello    world\n\ntest"
        result = processor._clean_slack_content(content)

        assert result == "Hello world test"


class TestMessageTypeMapping:
    """Tests for message type mapping."""

    @pytest.fixture
    def processor(self):
        return SlackMessageProcessor()

    def test_should_map_text_message(self, processor):
        """Test plain text maps to SLACK_TEXT."""
        msg = SlackMessage(
            ts="1705312800.000001",
            channel_id="C12345678",
            workspace_id="T12345678",
            user_id="U11111111",
            text="Hello",
        )
        result = processor._map_message_type(msg)

        assert result == MessageType.SLACK_TEXT

    def test_should_map_image_file(self, processor):
        """Test image file maps to SLACK_MEDIA."""
        msg = SlackMessage(
            ts="1705312800.000001",
            channel_id="C12345678",
            workspace_id="T12345678",
            user_id="U11111111",
            text="",
            files=[{"mimetype": "image/png"}],
        )
        result = processor._map_message_type(msg)

        assert result == MessageType.SLACK_MEDIA

    def test_should_map_video_file(self, processor):
        """Test video file maps to SLACK_MEDIA."""
        msg = SlackMessage(
            ts="1705312800.000001",
            channel_id="C12345678",
            workspace_id="T12345678",
            user_id="U11111111",
            text="",
            files=[{"mimetype": "video/mp4"}],
        )
        result = processor._map_message_type(msg)

        assert result == MessageType.SLACK_MEDIA

    def test_should_map_audio_file(self, processor):
        """Test audio file maps to SLACK_VOICE."""
        msg = SlackMessage(
            ts="1705312800.000001",
            channel_id="C12345678",
            workspace_id="T12345678",
            user_id="U11111111",
            text="",
            files=[{"mimetype": "audio/mp3"}],
        )
        result = processor._map_message_type(msg)

        assert result == MessageType.SLACK_VOICE

    def test_should_map_document_file(self, processor):
        """Test document file maps to SLACK_FILE."""
        msg = SlackMessage(
            ts="1705312800.000001",
            channel_id="C12345678",
            workspace_id="T12345678",
            user_id="U11111111",
            text="",
            files=[{"mimetype": "application/pdf"}],
        )
        result = processor._map_message_type(msg)

        assert result == MessageType.SLACK_FILE

    def test_should_map_bot_message(self, processor):
        """Test bot message maps to SLACK_BOT."""
        msg = SlackMessage(
            ts="1705312800.000001",
            channel_id="C12345678",
            workspace_id="T12345678",
            user_id="B11111111",
            text="Bot says hello",
            subtype="bot_message",
        )
        result = processor._map_message_type(msg)

        assert result == MessageType.SLACK_BOT


class TestAttachmentConversion:
    """Tests for attachment conversion."""

    @pytest.fixture
    def processor(self):
        return SlackMessageProcessor()

    def test_should_convert_file_to_attachment(self, processor):
        """Test file dict converts to AttachmentInfo."""
        file = {
            "id": "F12345678",
            "name": "image.png",
            "mimetype": "image/png",
            "size": 1024,
            "url_private": "https://files.slack.com/image.png",
            "url_private_download": "https://files.slack.com/download/image.png",
            "title": "My Image",
        }

        result = processor._convert_file(file)

        assert result is not None
        assert result.id == "F12345678"
        assert result.filename == "image.png"
        assert result.size == 1024
        assert result.type == AttachmentType.IMAGE
        assert result.content_type == "image/png"

    def test_should_detect_video_type(self, processor):
        """Test video MIME type is detected."""
        result = processor._detect_type("video/mp4")
        assert result == AttachmentType.VIDEO

    def test_should_detect_audio_type(self, processor):
        """Test audio MIME type is detected."""
        result = processor._detect_type("audio/mpeg")
        assert result == AttachmentType.AUDIO

    def test_should_default_to_document(self, processor):
        """Test unknown MIME defaults to document."""
        result = processor._detect_type("application/octet-stream")
        assert result == AttachmentType.DOCUMENT

    def test_should_handle_empty_file(self, processor):
        """Test empty file returns None."""
        result = processor._convert_file(None)
        assert result is None

        result = processor._convert_file({})
        assert result is None

    def test_should_convert_legacy_attachment(self, processor):
        """Test legacy Slack attachment converts."""
        attachment = {
            "id": "att123",
            "fallback": "Link preview",
            "title": "Article Title",
            "text": "Article description",
            "original_url": "https://example.com/article",
        }

        result = processor._convert_legacy_attachment(attachment)

        assert result is not None
        assert result.filename == "Article Title"
        assert result.type == AttachmentType.DOCUMENT

    def test_should_skip_legacy_attachment_without_fallback(self, processor):
        """Test legacy attachment without fallback is skipped."""
        attachment = {
            "id": "att123",
            "title": "No fallback",
        }

        result = processor._convert_legacy_attachment(attachment)
        assert result is None


class TestSlackThreadReconstructor:
    """Tests for SlackThreadReconstructor class."""

    @pytest.fixture
    def reconstructor(self):
        return SlackThreadReconstructor(time_gap_minutes=10)

    def test_should_group_explicit_threads(self, reconstructor):
        """Test explicit thread grouping by reply_to_id."""
        messages = [
            ProcessedMessage(
                id="1705312800.000001",
                author_name="user1",
                author_id="U1",
                content="Thread parent",
                timestamp=datetime(2024, 1, 15, 12, 0, 0),
            ),
            ProcessedMessage(
                id="1705312900.000001",
                author_name="user2",
                author_id="U2",
                content="Reply 1",
                timestamp=datetime(2024, 1, 15, 12, 1, 0),
                reply_to_id="1705312800.000001",
            ),
            ProcessedMessage(
                id="1705313000.000001",
                author_name="user3",
                author_id="U3",
                content="Reply 2",
                timestamp=datetime(2024, 1, 15, 12, 2, 0),
                reply_to_id="1705312800.000001",
            ),
        ]

        threads = reconstructor.reconstruct(messages)

        # Should have one thread with parent and 2 replies
        assert len(threads) == 1
        assert len(threads[0]) == 3

    def test_should_group_orphans_by_time_proximity(self, reconstructor):
        """Test orphan messages grouped by time proximity."""
        messages = [
            ProcessedMessage(
                id="1",
                author_name="user1",
                author_id="U1",
                content="Message 1",
                timestamp=datetime(2024, 1, 15, 12, 0, 0),
            ),
            ProcessedMessage(
                id="2",
                author_name="user2",
                author_id="U2",
                content="Message 2",
                timestamp=datetime(2024, 1, 15, 12, 5, 0),  # 5 min later
            ),
            ProcessedMessage(
                id="3",
                author_name="user3",
                author_id="U3",
                content="Message 3",
                timestamp=datetime(2024, 1, 15, 13, 0, 0),  # 1 hour later
            ),
        ]

        threads = reconstructor.reconstruct(messages)

        # Messages 1 and 2 should be grouped (within 10 min)
        # Message 3 should be separate (1 hour gap)
        assert len(threads) == 2

    def test_should_sort_threads_by_timestamp(self, reconstructor):
        """Test messages in threads are sorted by timestamp."""
        messages = [
            ProcessedMessage(
                id="3",
                author_name="user3",
                author_id="U3",
                content="Third",
                timestamp=datetime(2024, 1, 15, 12, 10, 0),
                reply_to_id="1",
            ),
            ProcessedMessage(
                id="1",
                author_name="user1",
                author_id="U1",
                content="First",
                timestamp=datetime(2024, 1, 15, 12, 0, 0),
            ),
            ProcessedMessage(
                id="2",
                author_name="user2",
                author_id="U2",
                content="Second",
                timestamp=datetime(2024, 1, 15, 12, 5, 0),
                reply_to_id="1",
            ),
        ]

        threads = reconstructor.reconstruct(messages)

        # Should be sorted: First, Second, Third
        thread = threads[0]
        assert thread[0].content == "First"
        assert thread[1].content == "Second"
        assert thread[2].content == "Third"

    def test_should_handle_empty_messages(self, reconstructor):
        """Test empty message list returns empty result."""
        threads = reconstructor.reconstruct([])
        assert threads == []

    def test_should_respect_time_gap_setting(self):
        """Test custom time gap is respected."""
        reconstructor = SlackThreadReconstructor(time_gap_minutes=5)

        messages = [
            ProcessedMessage(
                id="1",
                author_name="user1",
                author_id="U1",
                content="Message 1",
                timestamp=datetime(2024, 1, 15, 12, 0, 0),
            ),
            ProcessedMessage(
                id="2",
                author_name="user2",
                author_id="U2",
                content="Message 2",
                timestamp=datetime(2024, 1, 15, 12, 7, 0),  # 7 min later
            ),
        ]

        threads = reconstructor.reconstruct(messages)

        # With 5 min gap, messages should be separate threads
        assert len(threads) == 2
