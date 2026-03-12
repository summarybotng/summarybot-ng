"""
Unit tests for message_processing/validator.py.

Tests MessageValidator for message quality validation.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.message_processing.validator import MessageValidator
from src.models.message import ProcessedMessage, SourceType


class TestMessageValidator:
    """Tests for MessageValidator class."""

    @pytest.fixture
    def validator(self):
        """Create a MessageValidator instance."""
        return MessageValidator()

    @pytest.fixture
    def create_message(self):
        """Factory for creating ProcessedMessage objects."""
        def _create(
            content="Test message",
            attachments=None,
            references=None,
            mentions=None
        ):
            return ProcessedMessage(
                id="msg123",
                author_name="Test User",
                author_id="123",
                content=content,
                timestamp=datetime.utcnow(),
                source_type=SourceType.DISCORD,
                attachments=attachments or [],
                references=references or [],
                mentions=mentions or [],
            )
        return _create

    def test_is_valid_message_with_content(self, validator, create_message):
        """Message with content is valid."""
        msg = create_message(content="This is a valid message with content")
        assert validator.is_valid_message(msg) is True

    def test_is_valid_message_empty_content(self, validator, create_message):
        """Message with empty content but no attachments is invalid."""
        msg = create_message(content="")
        # has_substantial_content should return False for empty
        assert validator.is_valid_message(msg) is False

    def test_is_valid_message_with_attachments(self, validator, create_message):
        """Message with attachments is valid even without text."""
        msg = create_message(content="", attachments=[{"type": "image", "url": "http://example.com"}])
        assert validator.is_valid_message(msg) is True

    def test_is_valid_message_whitespace_only(self, validator, create_message):
        """Message with only whitespace is invalid."""
        msg = create_message(content="   ")
        assert validator.is_valid_message(msg) is False

    def test_is_valid_message_short_content(self, validator, create_message):
        """Very short content (<10 chars) or few words is invalid per has_substantial_content.

        Requirements:
        - At least 10 characters
        - At least 3 words with >2 characters each
        """
        # Too few characters
        msg = create_message(content="Hi")
        assert validator.is_valid_message(msg) is False

        # 10+ chars but only 2 words - still invalid
        msg = create_message(content="Hello there")
        assert validator.is_valid_message(msg) is False

        # 10+ chars with 3+ significant words - valid
        msg = create_message(content="Hello there friend")
        assert validator.is_valid_message(msg) is True

    def test_is_valid_message_long_content(self, validator, create_message):
        """Long content is valid."""
        msg = create_message(content="This is a long message " * 100)
        assert validator.is_valid_message(msg) is True

    def test_is_valid_message_special_characters(self, validator, create_message):
        """Message with special characters is valid."""
        msg = create_message(content="Hello! 👋 How are you?")
        assert validator.is_valid_message(msg) is True

    def test_is_valid_message_unicode(self, validator, create_message):
        """Message with unicode is valid if substantial (>=10 chars + 3 words)."""
        # Unicode without spaces has few "words" so needs mixed content
        # to satisfy the word count requirement
        msg = create_message(content="こんにちは hello world friend")
        assert validator.is_valid_message(msg) is True

    def test_is_valid_message_markdown(self, validator, create_message):
        """Message with markdown formatting is valid."""
        msg = create_message(content="**bold** and *italic*")
        assert validator.is_valid_message(msg) is True

    def test_is_valid_message_code_block(self, validator, create_message):
        """Message with code block is valid."""
        msg = create_message(content="```python\nprint('hello')\n```")
        assert validator.is_valid_message(msg) is True

    def test_is_valid_message_links(self, validator, create_message):
        """Message with links is valid."""
        msg = create_message(content="Check this out: https://example.com")
        assert validator.is_valid_message(msg) is True
