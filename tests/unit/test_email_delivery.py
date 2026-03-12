"""
Tests for the email delivery service.

Tests core functionality of ADR-030: Email Delivery Destination.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.email_delivery import (
    EmailDeliveryService,
    EmailDeliveryResult,
    EmailContext,
    SMTPConfig,
    MAX_RECIPIENTS_PER_DESTINATION,
    MAX_EMAILS_PER_HOUR,
)
from src.models.summary import SummaryResult, SummarizationContext, Participant


@pytest.fixture
def smtp_config():
    """Create test SMTP configuration."""
    return SMTPConfig(
        host="smtp.test.local",
        port=587,
        username="testuser",
        password="testpass",
        use_tls=True,
        from_address="summarybot@test.local",
        from_name="Test SummaryBot",
        enabled=True,
    )


@pytest.fixture
def email_service(smtp_config):
    """Create email service with test config."""
    return EmailDeliveryService(smtp_config)


@pytest.fixture
def sample_summary():
    """Create a sample summary for testing."""
    return SummaryResult(
        id="test-summary-123",
        channel_id="123456789",
        guild_id="987654321",
        summary_text="This is a test summary of the conversation.",
        key_points=[
            "First key point discussed",
            "Second important topic",
            "Third notable item",
        ],
        action_items=[
            MagicMock(description="Complete the documentation", assignee="@alice"),
            MagicMock(description="Review the code changes", assignee="@bob"),
        ],
        participants=[
            Participant(
                user_id="1",
                display_name="Alice",
                message_count=15,
            ),
            Participant(
                user_id="2",
                display_name="Bob",
                message_count=10,
            ),
        ],
        message_count=50,
        start_time=datetime(2026, 3, 3, 9, 0),
        end_time=datetime(2026, 3, 3, 17, 0),
        context=SummarizationContext(
            channel_name="general",
            guild_name="Test Server",
            total_participants=10,
            time_span_hours=8.0,
        ),
    )


@pytest.fixture
def email_context():
    """Create sample email context."""
    return EmailContext(
        guild_name="Test Server",
        channel_names=["general", "development"],
        start_time=datetime(2026, 3, 3, 9, 0),
        end_time=datetime(2026, 3, 3, 17, 0),
        message_count=50,
        participant_count=10,
        schedule_name="Daily Digest",
    )


class TestSMTPConfig:
    """Tests for SMTPConfig."""

    def test_is_configured_when_valid(self, smtp_config):
        """Config is valid when all required fields are set."""
        assert smtp_config.is_configured() is True

    def test_is_configured_when_disabled(self, smtp_config):
        """Config is invalid when disabled."""
        smtp_config.enabled = False
        assert smtp_config.is_configured() is False

    def test_is_configured_when_no_host(self, smtp_config):
        """Config is invalid without host."""
        smtp_config.host = ""
        assert smtp_config.is_configured() is False

    def test_is_configured_when_no_from_address(self, smtp_config):
        """Config is invalid without from address."""
        smtp_config.from_address = ""
        assert smtp_config.is_configured() is False


class TestEmailValidation:
    """Tests for email validation."""

    def test_valid_email(self, email_service):
        """Valid email addresses pass validation."""
        assert email_service.validate_email("user@example.com") is True
        assert email_service.validate_email("user.name@example.co.uk") is True
        assert email_service.validate_email("user+tag@example.org") is True

    def test_invalid_email(self, email_service):
        """Invalid email addresses fail validation."""
        assert email_service.validate_email("") is False
        assert email_service.validate_email("notanemail") is False
        assert email_service.validate_email("@example.com") is False
        assert email_service.validate_email("user@") is False
        assert email_service.validate_email("user@.com") is False

    def test_parse_recipients_single(self, email_service):
        """Single recipient is parsed correctly."""
        result = email_service.parse_recipients("user@example.com")
        assert result == ["user@example.com"]

    def test_parse_recipients_multiple(self, email_service):
        """Multiple recipients are parsed correctly."""
        result = email_service.parse_recipients("a@test.com, b@test.com, c@test.com")
        assert result == ["a@test.com", "b@test.com", "c@test.com"]

    def test_parse_recipients_with_invalid(self, email_service):
        """Invalid recipients are filtered out."""
        result = email_service.parse_recipients("valid@test.com, invalid, also@valid.com")
        assert result == ["valid@test.com", "also@valid.com"]

    def test_parse_recipients_max_limit(self, email_service):
        """Recipients are limited to max count."""
        many_emails = ", ".join([f"user{i}@test.com" for i in range(20)])
        result = email_service.parse_recipients(many_emails)
        assert len(result) == MAX_RECIPIENTS_PER_DESTINATION

    def test_parse_recipients_empty(self, email_service):
        """Empty string returns empty list."""
        assert email_service.parse_recipients("") == []
        assert email_service.parse_recipients(None) == []


class TestEmailRendering:
    """Tests for email template rendering."""

    def test_render_html_fallback(self, email_service, sample_summary, email_context):
        """HTML fallback renders correctly."""
        html = email_service._render_html_fallback(sample_summary, email_context)

        assert "<!DOCTYPE html>" in html
        assert "general" in html or "development" in html
        assert "First key point discussed" in html
        assert "SummaryBot" in html

    def test_render_text_fallback(self, email_service, sample_summary, email_context):
        """Plain text fallback renders correctly."""
        text = email_service._render_text_fallback(sample_summary, email_context)

        assert "CHANNELS:" in text or "SUMMARY" in text
        assert "KEY POINTS" in text
        assert "First key point discussed" in text
        assert "SummaryBot" in text

    def test_render_html_with_template(self, email_service, sample_summary, email_context):
        """HTML renders with template (falls back if template not found)."""
        html = email_service.render_html(sample_summary, email_context)

        # Should have basic HTML structure
        assert "<html" in html
        assert "</html>" in html

    def test_render_plain_text_with_template(self, email_service, sample_summary, email_context):
        """Plain text renders with template (falls back if template not found)."""
        text = email_service.render_plain_text(sample_summary, email_context)

        # Should have summary content
        assert "SUMMARY" in text or "summary" in text.lower()

    def test_render_server_wide_context(self, email_service, sample_summary):
        """Server-wide summaries render correctly."""
        context = EmailContext(
            is_server_wide=True,
            message_count=100,
            participant_count=20,
        )
        html = email_service._render_html_fallback(sample_summary, context)
        assert "Server-wide" in html or "Server Summary" in html

    def test_render_category_context(self, email_service, sample_summary):
        """Category summaries render correctly."""
        context = EmailContext(
            category_name="Engineering",
            message_count=50,
            participant_count=10,
        )
        html = email_service._render_html_fallback(sample_summary, context)
        assert "Engineering" in html


class TestSubjectLine:
    """Tests for email subject line generation."""

    def test_subject_single_channel(self, email_service, sample_summary):
        """Subject for single channel summary."""
        context = EmailContext(channel_names=["general"])
        subject = email_service.build_subject(sample_summary, context)
        assert "#general" in subject
        assert "[SummaryBot]" in subject

    def test_subject_multiple_channels(self, email_service, sample_summary):
        """Subject for multi-channel summary."""
        context = EmailContext(channel_names=["general", "dev", "random"])
        subject = email_service.build_subject(sample_summary, context)
        assert "3 Channels" in subject

    def test_subject_server_wide(self, email_service, sample_summary):
        """Subject for server-wide summary."""
        context = EmailContext(is_server_wide=True)
        subject = email_service.build_subject(sample_summary, context)
        assert "Server Summary" in subject

    def test_subject_with_date(self, email_service, sample_summary):
        """Subject includes date when available."""
        context = EmailContext(
            channel_names=["general"],
            end_time=datetime(2026, 3, 3, 17, 0),
        )
        subject = email_service.build_subject(sample_summary, context)
        assert "Mar 03" in subject

    def test_custom_subject(self, email_service, sample_summary, email_context):
        """Custom subject overrides default."""
        custom = "My Custom Subject Line"
        subject = email_service.build_subject(sample_summary, email_context, custom)
        assert subject == custom


class TestRateLimiting:
    """Tests for rate limiting."""

    def test_rate_limit_not_exceeded(self, email_service):
        """Rate limit check passes when under limit."""
        assert email_service._check_rate_limit("guild123") is True

    def test_rate_limit_exceeded(self, email_service):
        """Rate limit check fails when over limit."""
        # Simulate hitting the limit
        email_service._send_count["guild123"] = MAX_EMAILS_PER_HOUR
        email_service._send_count_reset = datetime.utcnow()

        assert email_service._check_rate_limit("guild123") is False

    def test_rate_limit_resets_after_hour(self, email_service):
        """Rate limit resets after an hour."""
        email_service._send_count["guild123"] = MAX_EMAILS_PER_HOUR
        email_service._send_count_reset = datetime.utcnow() - timedelta(hours=2)

        # Should reset and allow
        assert email_service._check_rate_limit("guild123") is True
        assert email_service._send_count.get("guild123", 0) == 0

    def test_increment_send_count(self, email_service):
        """Send count increments correctly."""
        email_service._increment_send_count("guild123", 5)
        assert email_service._send_count["guild123"] == 5

        email_service._increment_send_count("guild123", 3)
        assert email_service._send_count["guild123"] == 8


class TestEmailDelivery:
    """Tests for email delivery."""

    def test_send_not_configured(self, sample_summary):
        """Sending fails when not configured."""
        service = EmailDeliveryService(SMTPConfig())
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            service.send_summary(sample_summary, ["test@example.com"])
        )

        assert result.success is False
        assert "not configured" in result.error.lower()

    def test_send_no_recipients(self, email_service, sample_summary):
        """Sending fails with no recipients."""
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            email_service.send_summary(sample_summary, [])
        )

        assert result.success is False
        assert "no valid recipients" in result.error.lower()

    def test_send_rate_limited(self, email_service, sample_summary):
        """Sending fails when rate limited."""
        email_service._send_count["guild123"] = MAX_EMAILS_PER_HOUR
        email_service._send_count_reset = datetime.utcnow()

        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            email_service.send_summary(
                sample_summary,
                ["test@example.com"],
                guild_id="guild123",
            )
        )

        assert result.success is False
        assert "rate limit" in result.error.lower()

    @pytest.mark.asyncio
    async def test_send_success(self, email_service, sample_summary, email_context):
        """Successful email delivery."""
        with patch("aiosmtplib.SMTP") as mock_smtp_class:
            mock_smtp = AsyncMock()
            mock_smtp_class.return_value.__aenter__.return_value = mock_smtp

            result = await email_service.send_summary(
                sample_summary,
                ["test@example.com"],
                context=email_context,
            )

            assert result.success is True
            assert "test@example.com" in result.recipients_sent

    @pytest.mark.asyncio
    async def test_send_partial_failure(self, email_service, sample_summary, email_context):
        """Partial delivery failure is handled."""
        with patch("aiosmtplib.SMTP") as mock_smtp_class:
            mock_smtp = AsyncMock()
            mock_smtp_class.return_value.__aenter__.return_value = mock_smtp

            # First recipient succeeds, second fails
            call_count = [0]

            async def mock_sendmail(from_addr, to_addr, msg):
                call_count[0] += 1
                if call_count[0] == 2:
                    raise Exception("Delivery failed")

            mock_smtp.sendmail = mock_sendmail

            result = await email_service.send_summary(
                sample_summary,
                ["success@test.com", "fail@test.com"],
                context=email_context,
            )

            assert result.success is True  # At least one succeeded
            assert len(result.recipients_sent) == 1
            assert len(result.recipients_failed) == 1


class TestHTMLEscaping:
    """Tests for HTML escaping."""

    def test_escape_html_special_chars(self, email_service):
        """Special HTML characters are escaped."""
        text = '<script>alert("xss")</script>'
        escaped = email_service._escape_html(text)

        assert "<script>" not in escaped
        assert "&lt;script&gt;" in escaped

    def test_escape_html_quotes(self, email_service):
        """Quote characters are escaped."""
        text = 'He said "hello" & \'goodbye\''
        escaped = email_service._escape_html(text)

        assert "&quot;" in escaped
        assert "&#39;" in escaped
        assert "&amp;" in escaped

    def test_escape_html_empty(self, email_service):
        """Empty string returns empty string."""
        assert email_service._escape_html("") == ""
        assert email_service._escape_html(None) == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
