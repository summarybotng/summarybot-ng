"""
Unit tests for message_processing/extractor.py.

Tests MessageExtractor for extracting additional information from Discord messages.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock

from src.message_processing.extractor import MessageExtractor
from src.models.message import ProcessedMessage, SourceType, AttachmentInfo


class TestMessageExtractor:
    """Tests for MessageExtractor class."""

    @pytest.fixture
    def extractor(self):
        """Create a MessageExtractor instance."""
        return MessageExtractor()

    @pytest.fixture
    def create_processed_message(self):
        """Factory for creating ProcessedMessage objects."""
        def _create(content="Test message", attachments=None, code_blocks=None):
            return ProcessedMessage(
                id="msg123",
                author_name="Test User",
                author_id="123",
                content=content,
                timestamp=datetime.utcnow(),
                source_type=SourceType.DISCORD,
                attachments=attachments or [],
                code_blocks=code_blocks or [],
            )
        return _create

    @pytest.fixture
    def create_discord_message(self):
        """Factory for creating mock Discord messages."""
        def _create(
            content="Test message",
            attachments=None,
            embeds=None,
            reactions=None
        ):
            msg = MagicMock()
            msg.id = 123456
            msg.content = content
            msg.attachments = attachments or []
            msg.embeds = embeds or []
            msg.reactions = reactions or []
            return msg
        return _create

    def test_extract_attachments(self, extractor, create_processed_message, create_discord_message):
        """Extracting attachments from Discord message."""
        # Create mock attachment
        attachment = MagicMock()
        attachment.id = 1
        attachment.filename = "image.png"
        attachment.url = "https://cdn.discord.com/image.png"
        attachment.content_type = "image/png"
        attachment.size = 12345

        processed = create_processed_message(content="Check this out")
        original = create_discord_message(content="Check this out", attachments=[attachment])

        result = extractor.extract_information(processed, original)

        assert len(result.attachments) == 1
        assert result.attachments[0].filename == "image.png"

    def test_extract_no_attachments(self, extractor, create_processed_message, create_discord_message):
        """No attachments when none present."""
        processed = create_processed_message(content="No attachments here")
        original = create_discord_message(content="No attachments here")

        result = extractor.extract_information(processed, original)

        assert result.attachments == []

    def test_extract_embeds_count(self, extractor, create_processed_message, create_discord_message):
        """Counting embeds from Discord message."""
        embed1 = MagicMock()
        embed2 = MagicMock()

        processed = create_processed_message(content="Link preview")
        original = create_discord_message(content="Link preview", embeds=[embed1, embed2])

        result = extractor.extract_information(processed, original)

        assert result.embeds_count == 2

    def test_extract_reactions_count(self, extractor, create_processed_message, create_discord_message):
        """Counting reactions from Discord message."""
        reaction1 = MagicMock()
        reaction2 = MagicMock()
        reaction3 = MagicMock()

        processed = create_processed_message(content="Popular message")
        original = create_discord_message(content="Popular message", reactions=[reaction1, reaction2, reaction3])

        result = extractor.extract_information(processed, original)

        assert result.reactions_count == 3

    def test_extract_code_blocks(self, extractor, create_processed_message, create_discord_message):
        """Extracting code blocks from message content."""
        content = "Here's some code:\n```python\nprint('hello')\n```"

        processed = create_processed_message(content=content)
        original = create_discord_message(content=content)

        result = extractor.extract_information(processed, original)

        assert len(result.code_blocks) >= 1

    def test_extract_multiple_code_blocks(self, extractor, create_processed_message, create_discord_message):
        """Extracting multiple code blocks."""
        content = "```python\nx = 1\n```\nAnd also:\n```javascript\nconst y = 2;\n```"

        processed = create_processed_message(content=content)
        original = create_discord_message(content=content)

        result = extractor.extract_information(processed, original)

        assert len(result.code_blocks) >= 2

    def test_extract_all_information(self, extractor, create_processed_message, create_discord_message):
        """Extracting all types of information at once."""
        # Create attachment
        attachment = MagicMock()
        attachment.id = 1
        attachment.filename = "file.txt"
        attachment.url = "https://cdn.discord.com/file.txt"
        attachment.content_type = "text/plain"
        attachment.size = 100

        content = "Check this file:\n```\ncontents\n```"

        processed = create_processed_message(content=content)
        original = create_discord_message(
            content=content,
            attachments=[attachment],
            embeds=[MagicMock(), MagicMock()],
            reactions=[MagicMock()]
        )

        result = extractor.extract_information(processed, original)

        assert len(result.attachments) == 1
        assert result.embeds_count == 2
        assert result.reactions_count == 1
        assert len(result.code_blocks) >= 1

    def test_extract_preserves_original_data(self, extractor, create_processed_message, create_discord_message):
        """Extraction preserves original ProcessedMessage data."""
        processed = create_processed_message(
            content="Original content with lots of text here"
        )
        original_author = processed.author_name
        original_id = processed.id
        original_content = processed.content

        original = create_discord_message(content=processed.content)
        result = extractor.extract_information(processed, original)

        assert result.author_name == original_author
        assert result.id == original_id
        assert result.content == original_content
