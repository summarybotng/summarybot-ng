"""
Unit tests for command handler utilities.

Tests cover:
- Time period parsing functions
- Embed formatters
- Error message builders
- Response pagination
- Text truncation
- Progress bar creation
"""

import pytest
from datetime import datetime, timedelta
import discord

from src.command_handlers.utils import (
    format_error_response,
    format_success_response,
    format_info_response,
    validate_time_range,
    parse_time_string,
    format_duration,
    truncate_text,
    extract_channel_id,
    create_progress_bar
)
from src.exceptions import UserError


class TestEmbedFormatters:
    """Test embed formatting functions."""

    def test_format_error_response(self):
        """Test error response formatting."""
        embed = format_error_response("Test error message", "TEST_ERROR")

        assert isinstance(embed, discord.Embed)
        assert "Error" in embed.title
        assert embed.description == "Test error message"
        assert embed.color == discord.Colour(0xFF0000)  # Red
        assert "TEST_ERROR" in embed.footer.text

    def test_format_error_response_default_code(self):
        """Test error response with default error code."""
        embed = format_error_response("Error occurred")

        assert isinstance(embed, discord.Embed)
        assert "ERROR" in embed.footer.text

    def test_format_success_response(self):
        """Test success response formatting."""
        embed = format_success_response(
            title="Operation Complete",
            description="Successfully completed the operation"
        )

        assert isinstance(embed, discord.Embed)
        assert "Operation Complete" in embed.title
        assert embed.description == "Successfully completed the operation"
        assert embed.color == discord.Colour(0x00FF00)  # Green

    def test_format_success_response_with_fields(self):
        """Test success response with fields."""
        fields = {
            "Field 1": "Value 1",
            "Field 2": "Value 2",
            "Field 3": "Value 3"
        }

        embed = format_success_response(
            title="Success",
            description="Test",
            fields=fields
        )

        assert len(embed.fields) == 3
        assert embed.fields[0].name == "Field 1"
        assert embed.fields[0].value == "Value 1"
        assert embed.fields[0].inline is False

    def test_format_info_response(self):
        """Test info response formatting."""
        embed = format_info_response(
            title="Information",
            description="Here is some information"
        )

        assert isinstance(embed, discord.Embed)
        assert "Information" in embed.title
        assert embed.description == "Here is some information"
        assert embed.color == discord.Colour(0x4A90E2)  # Blue

    def test_format_info_response_with_fields(self):
        """Test info response with fields."""
        fields = {"Status": "Active", "Count": "42"}

        embed = format_info_response(
            title="Info",
            description="Details",
            fields=fields
        )

        assert len(embed.fields) == 2


class TestTimeValidation:
    """Test time validation functions."""

    def test_validate_time_range_valid(self):
        """Test validating valid time range."""
        start = datetime.utcnow() - timedelta(hours=2)
        end = datetime.utcnow()

        # Should not raise
        validate_time_range(start, end)

    def test_validate_time_range_start_after_end(self):
        """Test validating when start is after end."""
        start = datetime.utcnow()
        end = datetime.utcnow() - timedelta(hours=1)

        with pytest.raises(UserError) as exc_info:
            validate_time_range(start, end)

        assert "Start time must be before end time" in str(exc_info.value.user_message)

    def test_validate_time_range_too_large(self):
        """Test validating time range that's too large."""
        start = datetime.utcnow() - timedelta(hours=200)  # 200 hours
        end = datetime.utcnow()

        with pytest.raises(UserError) as exc_info:
            validate_time_range(start, end, max_hours=168)  # Max 1 week

        assert "cannot exceed" in str(exc_info.value.user_message)

    def test_validate_time_range_custom_max(self):
        """Test validating with custom max hours."""
        start = datetime.utcnow() - timedelta(hours=50)
        end = datetime.utcnow()

        # Should fail with 24 hour max
        with pytest.raises(UserError):
            validate_time_range(start, end, max_hours=24)

        # Should pass with 72 hour max
        validate_time_range(start, end, max_hours=72)

    def test_validate_time_range_future_end(self):
        """Test validating when end time is in the future."""
        start = datetime.utcnow() - timedelta(hours=1)
        end = datetime.utcnow() + timedelta(hours=1)  # Future

        with pytest.raises(UserError) as exc_info:
            validate_time_range(start, end)

        assert "future" in str(exc_info.value.user_message).lower()


class TestTimeStringParsing:
    """Test time string parsing functions."""

    def test_parse_time_string_hours(self):
        """Test parsing hour-based time strings."""
        now = datetime.utcnow()

        result = parse_time_string("1h")
        assert (now - result).total_seconds() < 3605  # ~1 hour ago

        result = parse_time_string("24h")
        assert (now - result).total_seconds() < 86500  # ~24 hours ago

    def test_parse_time_string_hours_variations(self):
        """Test parsing hour strings with different formats."""
        now = datetime.utcnow()

        for format_str in ["2h", "2 hours", "2hour"]:
            result = parse_time_string(format_str)
            delta = (now - result).total_seconds()
            assert 7100 < delta < 7300  # ~2 hours

    def test_parse_time_string_minutes(self):
        """Test parsing minute-based time strings."""
        now = datetime.utcnow()

        result = parse_time_string("30m")
        assert (now - result).total_seconds() < 1850  # ~30 minutes ago

        result = parse_time_string("5 minutes")
        assert (now - result).total_seconds() < 350  # ~5 minutes ago

    def test_parse_time_string_days(self):
        """Test parsing day-based time strings."""
        now = datetime.utcnow()

        result = parse_time_string("1d")
        assert (now - result).total_seconds() < 86500  # ~1 day ago

        result = parse_time_string("7 days")
        delta = (now - result).total_seconds()
        assert 604700 < delta < 605000  # ~7 days

    def test_parse_time_string_weeks(self):
        """Test parsing week-based time strings."""
        now = datetime.utcnow()

        result = parse_time_string("1w")
        delta = (now - result).total_seconds()
        assert 604700 < delta < 605000  # ~1 week

    def test_parse_time_string_ago_format(self):
        """Test parsing 'X ago' format."""
        now = datetime.utcnow()

        result = parse_time_string("2 hours ago")
        delta = (now - result).total_seconds()
        assert 7100 < delta < 7300  # ~2 hours

        result = parse_time_string("30 minutes ago")
        assert (now - result).total_seconds() < 1850

    def test_parse_time_string_keywords(self):
        """Test parsing keyword time strings."""
        now = datetime.utcnow()

        result = parse_time_string("yesterday")
        delta = (now - result).total_seconds()
        assert 86300 < delta < 86500  # ~24 hours

        result = parse_time_string("last week")
        delta = (now - result).total_seconds()
        assert 604700 < delta < 605000  # ~1 week

        result = parse_time_string("today")
        assert result.hour == 0
        assert result.minute == 0

    def test_parse_time_string_iso_format(self):
        """Test parsing ISO format time strings."""
        iso_str = "2024-01-15T10:30:00"
        result = parse_time_string(iso_str)

        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30

    def test_parse_time_string_invalid(self):
        """Test parsing invalid time strings."""
        with pytest.raises(UserError) as exc_info:
            parse_time_string("invalid time string")

        assert "Could not understand time format" in str(exc_info.value.user_message)


class TestDurationFormatting:
    """Test duration formatting functions."""

    def test_format_duration_seconds(self):
        """Test formatting durations under 60 seconds."""
        assert format_duration(30) == "30s"
        assert format_duration(45.7) == "45s"
        assert format_duration(1) == "1s"

    def test_format_duration_minutes(self):
        """Test formatting durations in minutes."""
        assert format_duration(60) == "1m"
        assert format_duration(90) == "1m 30s"
        assert format_duration(300) == "5m"
        assert format_duration(3540) == "59m"

    def test_format_duration_hours(self):
        """Test formatting durations in hours."""
        assert format_duration(3600) == "1h"
        assert format_duration(5400) == "1h 30m"
        assert format_duration(7200) == "2h"
        assert format_duration(7260) == "2h 1m"

    def test_format_duration_days(self):
        """Test formatting durations in days."""
        assert format_duration(86400) == "1d"
        assert format_duration(90000) == "1d 1h"
        assert format_duration(172800) == "2d"
        assert format_duration(176400) == "2d 1h"

    def test_format_duration_mixed(self):
        """Test formatting various mixed durations."""
        # 1 day, 2 hours, 30 minutes, 45 seconds
        total_seconds = 86400 + 7200 + 1800 + 45
        result = format_duration(total_seconds)
        assert "1d" in result
        assert "2h" in result


class TestTextTruncation:
    """Test text truncation functions."""

    def test_truncate_text_under_limit(self):
        """Test truncating text that's already under limit."""
        text = "This is a short text"
        result = truncate_text(text, max_length=100)

        assert result == text

    def test_truncate_text_over_limit(self):
        """Test truncating text that exceeds limit."""
        text = "A" * 2000
        result = truncate_text(text, max_length=1024)

        assert len(result) == 1024
        assert result.endswith("...")

    def test_truncate_text_custom_suffix(self):
        """Test truncating with custom suffix."""
        text = "A" * 2000
        result = truncate_text(text, max_length=100, suffix=" [truncated]")

        assert len(result) == 100
        assert result.endswith(" [truncated]")

    def test_truncate_text_exactly_at_limit(self):
        """Test truncating text exactly at limit."""
        text = "A" * 1024
        result = truncate_text(text, max_length=1024)

        assert result == text
        assert not result.endswith("...")

    def test_truncate_text_discord_field_limit(self):
        """Test truncating for Discord field limit."""
        text = "A" * 2000

        # Discord field value limit is 1024
        result = truncate_text(text)

        assert len(result) <= 1024


class TestChannelIdExtraction:
    """Test channel ID extraction functions."""

    def test_extract_channel_id_from_mention(self):
        """Test extracting ID from channel mention."""
        channel_id = extract_channel_id("<#123456789>")

        assert channel_id == "123456789"

    def test_extract_channel_id_from_plain_id(self):
        """Test extracting ID from plain ID string."""
        channel_id = extract_channel_id("987654321")

        assert channel_id == "987654321"

    def test_extract_channel_id_invalid_mention(self):
        """Test extracting ID from invalid mention."""
        result = extract_channel_id("<#invalid>")

        assert result is None

    def test_extract_channel_id_malformed_input(self):
        """Test extracting ID from malformed input."""
        assert extract_channel_id("not a channel") is None
        assert extract_channel_id("") is None
        assert extract_channel_id("<123456>") is None  # Missing #


class TestProgressBar:
    """Test progress bar creation."""

    def test_create_progress_bar_empty(self):
        """Test creating empty progress bar."""
        bar = create_progress_bar(0, 100)

        assert bar == "[░░░░░░░░░░] 0%"

    def test_create_progress_bar_full(self):
        """Test creating full progress bar."""
        bar = create_progress_bar(100, 100)

        assert bar == "[██████████] 100%"

    def test_create_progress_bar_half(self):
        """Test creating half-full progress bar."""
        bar = create_progress_bar(50, 100)

        assert "[█████" in bar
        assert "50%" in bar

    def test_create_progress_bar_custom_length(self):
        """Test creating progress bar with custom length."""
        bar = create_progress_bar(50, 100, length=20)

        # Should have 20 characters between brackets
        content = bar[bar.index('[') + 1:bar.index(']')]
        assert len(content) == 20

    def test_create_progress_bar_partial_progress(self):
        """Test creating progress bar with various percentages."""
        bar25 = create_progress_bar(25, 100, length=10)
        bar75 = create_progress_bar(75, 100, length=10)

        assert "25%" in bar25
        assert "75%" in bar75

    def test_create_progress_bar_zero_total(self):
        """Test creating progress bar with zero total."""
        bar = create_progress_bar(0, 0)

        assert "0%" in bar

    def test_create_progress_bar_over_100_percent(self):
        """Test creating progress bar when current exceeds total."""
        bar = create_progress_bar(150, 100)

        # Should cap at 100%
        assert "100%" in bar

    def test_create_progress_bar_small_values(self):
        """Test creating progress bar with small values."""
        bar = create_progress_bar(1, 10)

        assert "10%" in bar

    def test_create_progress_bar_large_values(self):
        """Test creating progress bar with large values."""
        bar = create_progress_bar(5000, 10000)

        assert "50%" in bar


class TestIntegrationScenarios:
    """Test integration scenarios using multiple utilities."""

    def test_parse_and_validate_time_range(self):
        """Test parsing and validating a time range."""
        start_str = "2 hours ago"
        end_str = "1 hour ago"

        start = parse_time_string(start_str)
        end = parse_time_string(end_str)

        # Should not raise
        validate_time_range(start, end, max_hours=24)

    def test_format_duration_from_time_range(self):
        """Test formatting duration from parsed time range."""
        start_str = "2 hours ago"
        end_str = "1 hour ago"

        start = parse_time_string(start_str)
        end = parse_time_string(end_str)

        duration_seconds = (end - start).total_seconds()
        formatted = format_duration(duration_seconds)

        # Should be approximately 1 hour
        assert "59m" in formatted or "1h" in formatted or "60m" in formatted

    def test_error_response_with_truncated_message(self):
        """Test creating error response with truncated message."""
        long_error = "Error: " + "A" * 2000

        truncated = truncate_text(long_error, max_length=1024)
        embed = format_error_response(truncated, "LONG_ERROR")

        assert len(embed.description) <= 1024
        assert isinstance(embed, discord.Embed)

    def test_success_response_with_formatted_duration(self):
        """Test creating success response with formatted duration."""
        duration = 7325  # 2h 2m 5s
        formatted_duration = format_duration(duration)

        embed = format_success_response(
            title="Task Complete",
            description="Task completed successfully",
            fields={"Duration": formatted_duration}
        )

        assert len(embed.fields) == 1
        assert "2h" in embed.fields[0].value
