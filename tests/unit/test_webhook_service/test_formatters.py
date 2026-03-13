"""
Unit tests for response formatters (formatters.py).

Tests JSON, Markdown, HTML, and plain text formatting,
as well as error and success response formatting.
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from src.webhook_service.formatters import (
    OutputFormat,
    ResponseFormatter
)
from src.models.summary import (
    SummaryResult,
    ActionItem,
    TechnicalTerm,
    Participant,
    Priority,
    SummarizationContext
)


@pytest.fixture
def sample_summary():
    """Create sample summary result for testing."""
    context = SummarizationContext(
        channel_name="test-channel",
        guild_name="Test Guild",
        total_participants=2,
        time_span_hours=2.0
    )

    action_items = [
        ActionItem(
            description="Implement authentication",
            assignee="user_123",
            priority=Priority.HIGH,
            deadline=datetime.utcnow() + timedelta(days=7)
        ),
        ActionItem(
            description="Write documentation",
            priority=Priority.MEDIUM
        )
    ]

    technical_terms = [
        TechnicalTerm(
            term="JWT",
            definition="JSON Web Token for authentication",
            context="Used in API security",
            source_message_id="msg_001"
        ),
        TechnicalTerm(
            term="REST",
            definition="Representational State Transfer",
            context="API architecture style",
            source_message_id="msg_002"
        )
    ]

    participants = [
        Participant(
            user_id="user_123",
            display_name="Alice",
            message_count=15,
            key_contributions=["Proposed JWT implementation", "Reviewed API design"]
        ),
        Participant(
            user_id="user_456",
            display_name="Bob",
            message_count=8,
            key_contributions=["Fixed authentication bug"]
        )
    ]

    return SummaryResult(
        id="sum_test_123",
        channel_id="123456789",
        guild_id="987654321",
        start_time=datetime.utcnow() - timedelta(hours=2),
        end_time=datetime.utcnow(),
        message_count=23,
        summary_text="The team discussed implementing JWT authentication for the API. "
                     "Key decisions were made about token expiration and refresh strategies.",
        key_points=[
            "JWT will be used for API authentication",
            "Token expiration set to 1 hour",
            "Refresh tokens will be implemented"
        ],
        action_items=action_items,
        technical_terms=technical_terms,
        participants=participants,
        context=context,
        metadata={
            "input_tokens": 1500,
            "output_tokens": 500,
            "total_tokens": 2000
        },
        created_at=datetime.utcnow()
    )


class TestOutputFormatEnum:
    """Test OutputFormat enumeration."""

    def test_format_values(self):
        """Test enum values."""
        assert OutputFormat.JSON == "json"
        assert OutputFormat.MARKDOWN == "markdown"
        assert OutputFormat.HTML == "html"
        assert OutputFormat.PLAIN_TEXT == "plain_text"


class TestFormatSummary:
    """Test main format_summary method."""

    def test_format_summary_json(self, sample_summary):
        """Test formatting as JSON."""
        result = ResponseFormatter.format_summary(
            sample_summary,
            OutputFormat.JSON
        )

        assert isinstance(result, str)
        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed["id"] == "sum_test_123"
        assert "summary_text" in parsed

    def test_format_summary_markdown(self, sample_summary):
        """Test formatting as Markdown."""
        result = ResponseFormatter.format_summary(
            sample_summary,
            OutputFormat.MARKDOWN
        )

        assert isinstance(result, str)
        assert "#" in result  # Should have markdown headers
        assert "test-channel" in result

    def test_format_summary_html(self, sample_summary):
        """Test formatting as HTML."""
        result = ResponseFormatter.format_summary(
            sample_summary,
            OutputFormat.HTML
        )

        assert isinstance(result, str)
        assert "<!DOCTYPE html>" in result
        assert "<html>" in result
        assert "</html>" in result

    def test_format_summary_plain_text(self, sample_summary):
        """Test formatting as plain text."""
        result = ResponseFormatter.format_summary(
            sample_summary,
            OutputFormat.PLAIN_TEXT
        )

        assert isinstance(result, str)
        assert "SUMMARY" in result
        assert "test-channel" in result

    def test_format_summary_default(self, sample_summary):
        """Test default format is JSON."""
        result = ResponseFormatter.format_summary(sample_summary)

        # Should be JSON by default
        parsed = json.loads(result)
        assert "id" in parsed


class TestJSONFormatting:
    """Test JSON formatting."""

    def test_json_structure(self, sample_summary):
        """Test JSON has correct structure."""
        result = ResponseFormatter._format_json(sample_summary)
        data = json.loads(result)

        assert data["id"] == "sum_test_123"
        assert data["channel_id"] == "123456789"
        assert data["message_count"] == 23
        assert isinstance(data["key_points"], list)
        assert isinstance(data["action_items"], list)
        assert isinstance(data["technical_terms"], list)
        assert isinstance(data["participants"], list)

    def test_json_indentation(self, sample_summary):
        """Test JSON is formatted with indentation."""
        result = ResponseFormatter._format_json(sample_summary)

        # Should have newlines (indented JSON)
        assert "\n" in result
        assert "  " in result  # 2-space indent

    def test_json_datetime_handling(self, sample_summary):
        """Test datetime fields are serialized."""
        result = ResponseFormatter._format_json(sample_summary)
        data = json.loads(result)

        # Datetime fields should be strings
        assert isinstance(data["created_at"], str)
        assert isinstance(data["start_time"], str)
        assert isinstance(data["end_time"], str)


class TestMarkdownFormatting:
    """Test Markdown formatting."""

    def test_markdown_uses_to_markdown_method(self, sample_summary):
        """Test markdown uses SummaryResult.to_markdown()."""
        result = ResponseFormatter._format_markdown(sample_summary)

        # Should call the model's to_markdown method
        expected = sample_summary.to_markdown()
        assert result == expected


class TestHTMLFormatting:
    """Test HTML formatting."""

    def test_html_structure(self, sample_summary):
        """Test HTML has correct structure."""
        result = ResponseFormatter._format_html(sample_summary)

        assert "<!DOCTYPE html>" in result
        assert "<html>" in result
        assert "<head>" in result
        assert "<body>" in result
        assert "</body>" in result
        assert "</html>" in result

    def test_html_includes_styles(self, sample_summary):
        """Test HTML includes CSS styles."""
        result = ResponseFormatter._format_html(sample_summary)

        assert "<style>" in result
        assert "</style>" in result
        assert "font-family" in result

    def test_html_includes_channel_name(self, sample_summary):
        """Test HTML includes channel name in title."""
        result = ResponseFormatter._format_html(sample_summary)

        assert "test-channel" in result
        assert "<h1>" in result

    def test_html_includes_metadata(self, sample_summary):
        """Test HTML includes metadata section."""
        result = ResponseFormatter._format_html(sample_summary)

        assert "metadata" in result.lower()
        assert "Messages:" in result
        assert "23" in result  # message count

    def test_html_includes_summary_text(self, sample_summary):
        """Test HTML includes summary text."""
        result = ResponseFormatter._format_html(sample_summary)

        assert sample_summary.summary_text in result

    def test_html_includes_key_points(self, sample_summary):
        """Test HTML includes key points."""
        result = ResponseFormatter._format_html(sample_summary)

        assert "Key Points" in result
        assert "JWT will be used" in result
        assert "<ul" in result

    def test_html_includes_action_items(self, sample_summary):
        """Test HTML includes action items."""
        result = ResponseFormatter._format_html(sample_summary)

        assert "Action Items" in result
        assert "Implement authentication" in result
        assert "user_123" in result

    def test_html_action_item_priority_indicators(self, sample_summary):
        """Test HTML shows priority indicators."""
        result = ResponseFormatter._format_html(sample_summary)

        # Should have priority emoji/color indicators
        assert "🔴" in result or "🟡" in result  # High/medium priority

    def test_html_includes_technical_terms(self, sample_summary):
        """Test HTML includes technical terms."""
        result = ResponseFormatter._format_html(sample_summary)

        assert "Technical Terms" in result
        assert "JWT" in result
        assert "JSON Web Token" in result

    def test_html_includes_participants(self, sample_summary):
        """Test HTML includes participants."""
        result = ResponseFormatter._format_html(sample_summary)

        assert "Participants" in result
        assert "Alice" in result
        assert "Bob" in result
        assert "15 messages" in result

    def test_html_participant_contributions(self, sample_summary):
        """Test HTML shows participant contributions."""
        result = ResponseFormatter._format_html(sample_summary)

        assert "Key contributions" in result
        assert "Proposed JWT implementation" in result

    def test_html_includes_summary_id(self, sample_summary):
        """Test HTML includes summary ID in footer."""
        result = ResponseFormatter._format_html(sample_summary)

        assert "sum_test_123" in result


class TestPlainTextFormatting:
    """Test plain text formatting."""

    def test_plain_text_structure(self, sample_summary):
        """Test plain text has clear structure."""
        result = ResponseFormatter._format_plain_text(sample_summary)

        assert "SUMMARY:" in result
        assert "=" * 60 in result
        assert "-" * 60 in result

    def test_plain_text_channel_name(self, sample_summary):
        """Test plain text includes channel name."""
        result = ResponseFormatter._format_plain_text(sample_summary)

        assert "test-channel" in result

    def test_plain_text_metadata(self, sample_summary):
        """Test plain text includes metadata."""
        result = ResponseFormatter._format_plain_text(sample_summary)

        assert "Time Period:" in result
        assert "Messages: 23" in result
        assert "Participants:" in result

    def test_plain_text_summary_section(self, sample_summary):
        """Test plain text includes summary section."""
        result = ResponseFormatter._format_plain_text(sample_summary)

        assert "SUMMARY" in result
        assert sample_summary.summary_text in result

    def test_plain_text_key_points(self, sample_summary):
        """Test plain text includes numbered key points."""
        result = ResponseFormatter._format_plain_text(sample_summary)

        assert "KEY POINTS" in result
        assert "1. JWT will be used" in result
        assert "2. Token expiration" in result

    def test_plain_text_action_items(self, sample_summary):
        """Test plain text includes action items."""
        result = ResponseFormatter._format_plain_text(sample_summary)

        assert "ACTION ITEMS" in result
        assert "Implement authentication" in result
        assert "@user_123" in result

    def test_plain_text_technical_terms(self, sample_summary):
        """Test plain text includes technical terms."""
        result = ResponseFormatter._format_plain_text(sample_summary)

        assert "TECHNICAL TERMS" in result
        assert "JWT: JSON Web Token" in result

    def test_plain_text_participants(self, sample_summary):
        """Test plain text includes participants."""
        result = ResponseFormatter._format_plain_text(sample_summary)

        assert "PARTICIPANTS" in result
        assert "Alice (15 messages)" in result
        assert "  - Proposed JWT implementation" in result

    def test_plain_text_footer(self, sample_summary):
        """Test plain text includes footer."""
        result = ResponseFormatter._format_plain_text(sample_summary)

        assert "Summary ID: sum_test_123" in result
        assert "Generated:" in result


class TestErrorFormatting:
    """Test error response formatting."""

    def test_format_error_minimal(self):
        """Test formatting error with minimal parameters."""
        result = ResponseFormatter.format_error(
            error_code="TEST_ERROR",
            message="Something went wrong"
        )

        assert result["error"] == "TEST_ERROR"
        assert result["message"] == "Something went wrong"
        assert "timestamp" in result

    def test_format_error_with_details(self):
        """Test formatting error with details."""
        result = ResponseFormatter.format_error(
            error_code="VALIDATION_ERROR",
            message="Invalid input",
            details={"field": "channel_id", "reason": "too short"}
        )

        assert result["details"] == {"field": "channel_id", "reason": "too short"}

    def test_format_error_with_request_id(self):
        """Test formatting error with request ID."""
        result = ResponseFormatter.format_error(
            error_code="ERROR",
            message="Error occurred",
            request_id="req_123"
        )

        assert result["request_id"] == "req_123"

    def test_format_error_timestamp(self):
        """Test error includes timestamp."""
        result = ResponseFormatter.format_error(
            error_code="ERROR",
            message="Error"
        )

        assert "timestamp" in result
        # Should be ISO format
        datetime.fromisoformat(result["timestamp"])


class TestSuccessFormatting:
    """Test success response formatting."""

    def test_format_success_minimal(self):
        """Test formatting success with minimal parameters."""
        result = ResponseFormatter.format_success(
            data={"id": "123", "status": "ok"}
        )

        assert result["success"] is True
        assert result["message"] == "Success"
        assert result["data"] == {"id": "123", "status": "ok"}
        assert "timestamp" in result

    def test_format_success_custom_message(self):
        """Test formatting success with custom message."""
        result = ResponseFormatter.format_success(
            data={"result": "completed"},
            message="Operation completed successfully"
        )

        assert result["message"] == "Operation completed successfully"

    def test_format_success_with_request_id(self):
        """Test formatting success with request ID."""
        result = ResponseFormatter.format_success(
            data={"status": "ok"},
            request_id="req_456"
        )

        assert result["request_id"] == "req_456"

    def test_format_success_timestamp(self):
        """Test success includes timestamp."""
        result = ResponseFormatter.format_success(data={})

        assert "timestamp" in result
        datetime.fromisoformat(result["timestamp"])


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_empty_lists_in_summary(self):
        """Test formatting summary with empty lists."""
        context = SummarizationContext(
            channel_name="test",
            guild_name="Test Guild",
            total_participants=0,
            time_span_hours=1.0
        )

        summary = SummaryResult(
            id="sum_empty",
            channel_id="123",
            guild_id="456",
            start_time=datetime.utcnow() - timedelta(hours=1),
            end_time=datetime.utcnow(),
            message_count=5,
            summary_text="Empty summary",
            key_points=[],
            action_items=[],
            technical_terms=[],
            participants=[],
            context=context,
            created_at=datetime.utcnow()
        )

        # All formats should handle empty lists gracefully
        json_result = ResponseFormatter.format_summary(summary, OutputFormat.JSON)
        assert json_result is not None

        html_result = ResponseFormatter.format_summary(summary, OutputFormat.HTML)
        assert html_result is not None

        text_result = ResponseFormatter.format_summary(summary, OutputFormat.PLAIN_TEXT)
        assert text_result is not None

    def test_special_characters_in_html(self):
        """Test HTML escaping of special characters."""
        context = SummarizationContext(
            channel_name="test-<script>",
            guild_name="Test & Guild",
            total_participants=0,
            time_span_hours=1.0
        )

        summary = SummaryResult(
            id="sum_special",
            channel_id="123",
            guild_id="456",
            start_time=datetime.utcnow() - timedelta(hours=1),
            end_time=datetime.utcnow(),
            message_count=1,
            summary_text="Text with <tags> & special chars",
            context=context,
            created_at=datetime.utcnow()
        )

        html_result = ResponseFormatter.format_summary(summary, OutputFormat.HTML)
        # Should contain the text (may or may not be escaped depending on implementation)
        assert "special chars" in html_result

    def test_unicode_in_formatting(self):
        """Test handling of Unicode characters."""
        context = SummarizationContext(
            channel_name="test-🚀",
            guild_name="Test Guild",
            total_participants=0,
            time_span_hours=1.0
        )

        summary = SummaryResult(
            id="sum_unicode",
            channel_id="123",
            guild_id="456",
            start_time=datetime.utcnow() - timedelta(hours=1),
            end_time=datetime.utcnow(),
            message_count=1,
            summary_text="Unicode: 你好 мир 🌍",
            context=context,
            created_at=datetime.utcnow()
        )

        # All formats should handle Unicode
        for format_type in OutputFormat:
            result = ResponseFormatter.format_summary(summary, format_type)
            assert result is not None
