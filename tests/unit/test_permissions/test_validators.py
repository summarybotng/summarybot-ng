"""
Unit tests for permissions/validators.py.

Tests ValidationResult and PermissionValidator.
"""

import pytest
from unittest.mock import MagicMock, PropertyMock
from datetime import datetime, timedelta

from src.permissions.validators import (
    ValidationResult,
    PermissionValidator
)


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_create_valid_result(self):
        """Create a valid result."""
        result = ValidationResult(is_valid=True)
        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []
        assert result.context == {}

    def test_create_invalid_result(self):
        """Create an invalid result with errors."""
        result = ValidationResult(is_valid=False, errors=["Error 1"])
        assert result.is_valid is False
        assert "Error 1" in result.errors

    def test_add_error(self):
        """Adding an error makes result invalid."""
        result = ValidationResult(is_valid=True)
        result.add_error("Something went wrong")

        assert result.is_valid is False
        assert "Something went wrong" in result.errors

    def test_add_warning(self):
        """Adding a warning doesn't affect validity."""
        result = ValidationResult(is_valid=True)
        result.add_warning("This is a warning")

        assert result.is_valid is True
        assert "This is a warning" in result.warnings

    def test_add_multiple_errors(self):
        """Can add multiple errors."""
        result = ValidationResult(is_valid=True)
        result.add_error("Error 1")
        result.add_error("Error 2")

        assert len(result.errors) == 2
        assert result.is_valid is False

    def test_to_dict(self):
        """to_dict serializes all fields."""
        result = ValidationResult(
            is_valid=True,
            errors=["error1"],
            warnings=["warning1"],
            context={"key": "value"}
        )

        d = result.to_dict()

        assert d["is_valid"] is True
        assert d["errors"] == ["error1"]
        assert d["warnings"] == ["warning1"]
        assert d["context"]["key"] == "value"

    def test_get_error_message_empty(self):
        """get_error_message with no errors returns empty string."""
        result = ValidationResult(is_valid=True)
        assert result.get_error_message() == ""

    def test_get_error_message_with_errors(self):
        """get_error_message formats errors correctly."""
        result = ValidationResult(
            is_valid=False,
            errors=["Error 1", "Error 2"]
        )

        message = result.get_error_message()

        assert "- Error 1" in message
        assert "- Error 2" in message

    def test_success_factory_method(self):
        """success() creates valid result with context."""
        result = ValidationResult.success(user_id="123", action="test")

        assert result.is_valid is True
        assert result.errors == []
        assert result.context["user_id"] == "123"
        assert result.context["action"] == "test"

    def test_failure_factory_method(self):
        """failure() creates invalid result with error and context."""
        result = ValidationResult.failure(
            "Something failed",
            user_id="123"
        )

        assert result.is_valid is False
        assert "Something failed" in result.errors
        assert result.context["user_id"] == "123"


class TestPermissionValidator:
    """Tests for PermissionValidator class."""

    @pytest.fixture
    def validator(self):
        """Create a fresh PermissionValidator instance."""
        return PermissionValidator()

    @pytest.fixture
    def mock_channel(self):
        """Create a mock Discord text channel."""
        import discord
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 987654321
        channel.name = "test-channel"
        channel.mention = "<#987654321>"
        channel.guild.id = 123456789
        channel.is_nsfw.return_value = False
        return channel

    @pytest.fixture
    def mock_member(self, mock_channel):
        """Create a mock Discord member with permissions."""
        member = MagicMock()
        member.id = 111111111

        # Create permissions mock
        permissions = MagicMock()
        permissions.read_messages = True
        permissions.read_message_history = True
        permissions.send_messages = True
        permissions.embed_links = True
        permissions.view_channel = True

        mock_channel.permissions_for.return_value = permissions

        return member

    def test_validate_summarize_permission_success(
        self, validator, mock_member, mock_channel
    ):
        """Valid permissions return successful result."""
        result = validator.validate_summarize_permission(mock_member, mock_channel)

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert result.context["user_id"] == str(mock_member.id)
        assert result.context["channel_id"] == str(mock_channel.id)

    def test_validate_summarize_permission_no_read_messages(
        self, validator, mock_member, mock_channel
    ):
        """Missing read_messages permission fails."""
        permissions = mock_channel.permissions_for.return_value
        permissions.read_messages = False

        result = validator.validate_summarize_permission(mock_member, mock_channel)

        assert result.is_valid is False
        assert any("read messages" in e.lower() for e in result.errors)

    def test_validate_summarize_permission_no_read_history(
        self, validator, mock_member, mock_channel
    ):
        """Missing read_message_history permission fails."""
        permissions = mock_channel.permissions_for.return_value
        permissions.read_message_history = False

        result = validator.validate_summarize_permission(mock_member, mock_channel)

        assert result.is_valid is False
        assert any("message history" in e.lower() for e in result.errors)

    def test_validate_summarize_permission_both_missing(
        self, validator, mock_member, mock_channel
    ):
        """Multiple missing permissions result in multiple errors."""
        permissions = mock_channel.permissions_for.return_value
        permissions.read_messages = False
        permissions.read_message_history = False

        result = validator.validate_summarize_permission(mock_member, mock_channel)

        assert result.is_valid is False
        assert len(result.errors) == 2

    def test_validate_bot_permissions_success(
        self, validator, mock_member, mock_channel
    ):
        """Bot with all required permissions passes."""
        result = validator.validate_bot_permissions(mock_member, mock_channel)

        assert result.is_valid is True
        assert result.context["operation"] == "summarize"

    def test_validate_bot_permissions_missing_send_messages(
        self, validator, mock_member, mock_channel
    ):
        """Bot without send_messages fails."""
        permissions = mock_channel.permissions_for.return_value
        permissions.send_messages = False

        result = validator.validate_bot_permissions(mock_member, mock_channel)

        assert result.is_valid is False
        assert any("send messages" in e.lower() for e in result.errors)

    def test_validate_bot_permissions_missing_embed_links(
        self, validator, mock_member, mock_channel
    ):
        """Bot without embed_links fails."""
        permissions = mock_channel.permissions_for.return_value
        permissions.embed_links = False

        result = validator.validate_bot_permissions(mock_member, mock_channel)

        assert result.is_valid is False
        assert any("embed links" in e.lower() for e in result.errors)

    def test_validate_webhook_access_success(self, validator):
        """Valid API key passes webhook validation."""
        result = validator.validate_webhook_access(
            api_key="secret123",
            guild_id="guild123",
            expected_secret="secret123"
        )

        assert result.is_valid is True
        assert result.context["authenticated"] is True

    def test_validate_webhook_access_no_api_key(self, validator):
        """Missing API key fails."""
        result = validator.validate_webhook_access(
            api_key=None,
            guild_id="guild123",
            expected_secret="secret123"
        )

        assert result.is_valid is False
        assert any("api key" in e.lower() for e in result.errors)

    def test_validate_webhook_access_no_expected_secret(self, validator):
        """No configured secret fails."""
        result = validator.validate_webhook_access(
            api_key="secret123",
            guild_id="guild123",
            expected_secret=None
        )

        assert result.is_valid is False
        assert any("not configured" in e.lower() for e in result.errors)

    def test_validate_webhook_access_wrong_key(self, validator):
        """Wrong API key fails."""
        result = validator.validate_webhook_access(
            api_key="wrong_key",
            guild_id="guild123",
            expected_secret="secret123"
        )

        assert result.is_valid is False
        assert any("invalid" in e.lower() for e in result.errors)

    def test_validate_channel_accessibility_success(
        self, validator, mock_member, mock_channel
    ):
        """Accessible channel passes validation."""
        result = validator.validate_channel_accessibility(mock_channel, mock_member)

        assert result.is_valid is True
        assert result.context["channel_name"] == mock_channel.name

    def test_validate_channel_accessibility_no_channel(
        self, validator, mock_member
    ):
        """None channel fails."""
        result = validator.validate_channel_accessibility(None, mock_member)

        assert result.is_valid is False
        assert any("not found" in e.lower() for e in result.errors)

    def test_validate_channel_accessibility_not_visible(
        self, validator, mock_member, mock_channel
    ):
        """Channel bot can't view fails."""
        permissions = mock_channel.permissions_for.return_value
        permissions.view_channel = False

        result = validator.validate_channel_accessibility(mock_channel, mock_member)

        assert result.is_valid is False
        assert any("cannot view" in e.lower() for e in result.errors)

    def test_validate_channel_accessibility_nsfw_warning(
        self, validator, mock_member, mock_channel
    ):
        """NSFW channel adds warning but passes."""
        mock_channel.is_nsfw.return_value = True

        result = validator.validate_channel_accessibility(mock_channel, mock_member)

        assert result.is_valid is True
        assert len(result.warnings) > 0
        assert any("nsfw" in w.lower() for w in result.warnings)

    def test_validate_time_range_success(self, validator):
        """Valid time range passes."""
        now = datetime.utcnow()
        start = now - timedelta(hours=24)
        end = now

        result = validator.validate_time_range(start, end)

        assert result.is_valid is True
        assert "duration_hours" in result.context

    def test_validate_time_range_invalid_types(self, validator):
        """Non-datetime types fail."""
        result = validator.validate_time_range("2024-01-01", "2024-01-02")

        assert result.is_valid is False
        assert any("datetime" in e.lower() for e in result.errors)

    def test_validate_time_range_start_after_end(self, validator):
        """Start after end fails."""
        now = datetime.utcnow()
        start = now
        end = now - timedelta(hours=24)

        result = validator.validate_time_range(start, end)

        assert result.is_valid is False
        assert any("before" in e.lower() for e in result.errors)

    def test_validate_time_range_too_old(self, validator):
        """Time range exceeding max_days fails."""
        now = datetime.utcnow()
        start = now - timedelta(days=100)
        end = now

        result = validator.validate_time_range(start, end, max_days=90)

        assert result.is_valid is False
        assert any("too old" in e.lower() for e in result.errors)

    def test_validate_time_range_future_start(self, validator):
        """Future start time fails."""
        now = datetime.utcnow()
        start = now + timedelta(hours=1)
        end = now + timedelta(hours=2)

        result = validator.validate_time_range(start, end)

        assert result.is_valid is False
        assert any("future" in e.lower() for e in result.errors)

    def test_validate_time_range_future_end_warning(self, validator):
        """Future end time adds warning but passes."""
        now = datetime.utcnow()
        start = now - timedelta(hours=24)
        end = now + timedelta(hours=1)

        result = validator.validate_time_range(start, end)

        # Should still be valid but with warning
        assert len(result.warnings) > 0
        assert any("future" in w.lower() for w in result.warnings)

    def test_validate_user_rate_limit_placeholder(self, validator):
        """Rate limit validation returns valid (placeholder)."""
        result = validator.validate_user_rate_limit(
            user_id="123",
            action="summarize",
            limit=10,
            window_seconds=60
        )

        assert result.is_valid is True
        assert result.context["note"] == "Rate limiting not yet implemented"
