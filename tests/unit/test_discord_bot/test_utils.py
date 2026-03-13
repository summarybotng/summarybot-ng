"""
Unit tests for discord_bot.utils module.
"""

import pytest
from datetime import datetime
import discord

from src.discord_bot.utils import (
    create_embed,
    create_error_embed,
    create_success_embed,
    create_info_embed,
    format_timestamp,
    truncate_text,
    format_code_block,
    format_list,
    parse_channel_mention,
    parse_user_mention,
    parse_role_mention,
    create_progress_bar,
    format_file_size,
    split_message
)


class TestEmbedCreation:
    """Tests for embed creation utilities."""

    def test_create_embed_basic(self):
        """Test basic embed creation."""
        embed = create_embed(title="Test Title", description="Test Description")

        assert isinstance(embed, discord.Embed)
        assert embed.title == "Test Title"
        assert embed.description == "Test Description"
        assert embed.color.value == 0x4A90E2

    def test_create_embed_with_fields(self):
        """Test embed creation with fields."""
        fields = [
            {"name": "Field 1", "value": "Value 1", "inline": True},
            {"name": "Field 2", "value": "Value 2", "inline": False}
        ]

        embed = create_embed(title="Test", fields=fields)

        assert len(embed.fields) == 2
        assert embed.fields[0].name == "Field 1"
        assert embed.fields[0].value == "Value 1"
        assert embed.fields[0].inline == True
        assert embed.fields[1].inline == False

    def test_create_embed_with_footer(self):
        """Test embed creation with footer."""
        embed = create_embed(title="Test", footer="Test Footer")

        assert embed.footer.text == "Test Footer"

    def test_create_embed_with_timestamp(self):
        """Test embed creation with timestamp."""
        now = datetime.utcnow()
        embed = create_embed(title="Test", timestamp=now)

        # discord.py may attach UTC tzinfo to naive datetimes
        assert embed.timestamp.replace(tzinfo=None) == now

    def test_create_error_embed(self):
        """Test error embed creation."""
        embed = create_error_embed(
            title="Error",
            description="Something went wrong",
            error_code="TEST_ERROR"
        )

        assert "❌" in embed.title
        assert embed.color.value == 0xE74C3C
        assert any("TEST_ERROR" in field.value for field in embed.fields)

    def test_create_success_embed(self):
        """Test success embed creation."""
        embed = create_success_embed(
            title="Success",
            description="Operation completed"
        )

        assert "✅" in embed.title
        assert embed.color.value == 0x2ECC71

    def test_create_info_embed(self):
        """Test info embed creation."""
        embed = create_info_embed(
            title="Information",
            description="Here's some info"
        )

        assert "ℹ️" in embed.title
        assert embed.color.value == 0x3498DB


class TestTextFormatting:
    """Tests for text formatting utilities."""

    def test_format_timestamp(self):
        """Test timestamp formatting."""
        dt = datetime(2024, 1, 1, 12, 30, 0)
        formatted = format_timestamp(dt, style="f")

        assert formatted.startswith("<t:")
        assert formatted.endswith(":f>")
        assert str(int(dt.timestamp())) in formatted

    def test_truncate_text_no_truncation(self):
        """Test truncate_text when text is within limit."""
        text = "Short text"
        result = truncate_text(text, max_length=50)

        assert result == text

    def test_truncate_text_with_truncation(self):
        """Test truncate_text when text exceeds limit."""
        text = "This is a very long text that needs to be truncated"
        result = truncate_text(text, max_length=20)

        assert len(result) == 20
        assert result.endswith("...")
        assert len(result) <= 20

    def test_format_code_block(self):
        """Test code block formatting."""
        code = "print('Hello, World!')"
        result = format_code_block(code, language="python")

        assert result.startswith("```python\n")
        assert result.endswith("\n```")
        assert code in result

    def test_format_list(self):
        """Test list formatting."""
        items = ["Item 1", "Item 2", "Item 3"]
        result = format_list(items)

        assert "• Item 1" in result
        assert "• Item 2" in result
        assert "• Item 3" in result
        assert result.count("\n") == 2


class TestMentionParsing:
    """Tests for mention parsing utilities."""

    def test_parse_channel_mention_valid(self):
        """Test parsing valid channel mention."""
        mention = "<#123456789>"
        result = parse_channel_mention(mention)

        assert result == 123456789

    def test_parse_channel_mention_invalid(self):
        """Test parsing invalid channel mention."""
        result = parse_channel_mention("not a mention")

        assert result is None

    def test_parse_user_mention_valid(self):
        """Test parsing valid user mention."""
        mention = "<@123456789>"
        result = parse_user_mention(mention)

        assert result == 123456789

    def test_parse_user_mention_with_exclamation(self):
        """Test parsing user mention with exclamation."""
        mention = "<@!123456789>"
        result = parse_user_mention(mention)

        assert result == 123456789

    def test_parse_user_mention_invalid(self):
        """Test parsing invalid user mention."""
        result = parse_user_mention("not a mention")

        assert result is None

    def test_parse_role_mention_valid(self):
        """Test parsing valid role mention."""
        mention = "<@&123456789>"
        result = parse_role_mention(mention)

        assert result == 123456789

    def test_parse_role_mention_invalid(self):
        """Test parsing invalid role mention."""
        result = parse_role_mention("not a mention")

        assert result is None


class TestProgressBar:
    """Tests for progress bar creation."""

    def test_create_progress_bar_empty(self):
        """Test progress bar at 0%."""
        result = create_progress_bar(0, 100)

        assert "░" in result
        assert "0%" in result

    def test_create_progress_bar_half(self):
        """Test progress bar at 50%."""
        result = create_progress_bar(50, 100, length=10)

        assert "50%" in result
        assert "█" in result
        assert "░" in result

    def test_create_progress_bar_full(self):
        """Test progress bar at 100%."""
        result = create_progress_bar(100, 100)

        assert "100%" in result
        assert "█" in result

    def test_create_progress_bar_zero_total(self):
        """Test progress bar with zero total."""
        result = create_progress_bar(0, 0, length=10)

        assert result.count("░") == 10


class TestFileSizeFormatting:
    """Tests for file size formatting."""

    def test_format_file_size_bytes(self):
        """Test formatting bytes."""
        result = format_file_size(500)

        assert "500.0 B" in result

    def test_format_file_size_kilobytes(self):
        """Test formatting kilobytes."""
        result = format_file_size(1024)

        assert "1.0 KB" in result

    def test_format_file_size_megabytes(self):
        """Test formatting megabytes."""
        result = format_file_size(1024 * 1024)

        assert "1.0 MB" in result

    def test_format_file_size_gigabytes(self):
        """Test formatting gigabytes."""
        result = format_file_size(1024 * 1024 * 1024)

        assert "1.0 GB" in result


class TestMessageSplitting:
    """Tests for message splitting utility."""

    def test_split_message_short(self):
        """Test splitting a short message."""
        text = "Short message"
        result = split_message(text)

        assert len(result) == 1
        assert result[0] == text

    def test_split_message_long(self):
        """Test splitting a long message."""
        text = "A" * 3000
        result = split_message(text, max_length=2000)

        assert len(result) == 2
        assert len(result[0]) <= 2000
        assert len(result[1]) <= 2000

    def test_split_message_with_newlines(self):
        """Test splitting message respecting newlines."""
        lines = ["Line " + str(i) for i in range(100)]
        text = "\n".join(lines)

        result = split_message(text, max_length=500)

        assert len(result) > 1
        for part in result:
            assert len(part) <= 500

    def test_split_message_exact_length(self):
        """Test splitting message at exact max length."""
        text = "A" * 2000
        result = split_message(text, max_length=2000)

        assert len(result) == 1
        assert result[0] == text
