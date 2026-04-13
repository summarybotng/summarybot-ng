"""
Tests for src/slack/models.py - Slack dataclasses, enums, and serialization.

Tests SlackWorkspace, SlackChannel, SlackUser, SlackMessage dataclasses
and their methods including serialization and helper functions.
"""

import pytest
from datetime import datetime
from src.slack.models import (
    SlackScopeTier,
    SlackChannelType,
    SlackWorkspace,
    SlackChannel,
    SlackUser,
    SlackMessage,
    SLACK_SCOPES_PUBLIC,
    SLACK_SCOPES_FULL,
)


class TestSlackScopeTier:
    """Tests for SlackScopeTier enum."""

    def test_public_tier_value(self):
        """Test PUBLIC tier has correct value."""
        assert SlackScopeTier.PUBLIC.value == "public"

    def test_full_tier_value(self):
        """Test FULL tier has correct value."""
        assert SlackScopeTier.FULL.value == "full"

    def test_scope_tier_is_string_enum(self):
        """Test that SlackScopeTier is a string enum."""
        assert isinstance(SlackScopeTier.PUBLIC, str)
        assert SlackScopeTier.PUBLIC == "public"


class TestSlackChannelType:
    """Tests for SlackChannelType enum."""

    def test_public_channel_type(self):
        """Test PUBLIC channel type value."""
        assert SlackChannelType.PUBLIC.value == "public_channel"

    def test_private_channel_type(self):
        """Test PRIVATE channel type value."""
        assert SlackChannelType.PRIVATE.value == "private_channel"

    def test_dm_channel_type(self):
        """Test DM channel type value."""
        assert SlackChannelType.DM.value == "im"

    def test_mpim_channel_type(self):
        """Test MPIM channel type value."""
        assert SlackChannelType.MPIM.value == "mpim"


class TestSlackWorkspace:
    """Tests for SlackWorkspace dataclass."""

    def test_should_create_workspace_with_required_fields(self):
        """Test creating workspace with minimal required fields."""
        workspace = SlackWorkspace(
            workspace_id="T12345678",
            workspace_name="Test Workspace",
        )

        assert workspace.workspace_id == "T12345678"
        assert workspace.workspace_name == "Test Workspace"
        assert workspace.enabled is True
        assert workspace.scope_tier == SlackScopeTier.PUBLIC

    def test_should_check_scope_when_workspace_has_scope(self):
        """Test has_scope returns True when scope is present."""
        workspace = SlackWorkspace(
            workspace_id="T12345678",
            workspace_name="Test",
            scopes="channels:history,channels:read,users:read",
        )

        assert workspace.has_scope("channels:history") is True
        assert workspace.has_scope("channels:read") is True
        assert workspace.has_scope("users:read") is True

    def test_should_check_scope_when_workspace_missing_scope(self):
        """Test has_scope returns False when scope is missing."""
        workspace = SlackWorkspace(
            workspace_id="T12345678",
            workspace_name="Test",
            scopes="channels:history,channels:read",
        )

        assert workspace.has_scope("groups:history") is False
        assert workspace.has_scope("files:read") is False

    def test_should_detect_private_access_with_full_tier(self):
        """Test can_access_private returns True for FULL tier."""
        workspace = SlackWorkspace(
            workspace_id="T12345678",
            workspace_name="Test",
            scope_tier=SlackScopeTier.FULL,
        )

        assert workspace.can_access_private() is True

    def test_should_deny_private_access_with_public_tier(self):
        """Test can_access_private returns False for PUBLIC tier."""
        workspace = SlackWorkspace(
            workspace_id="T12345678",
            workspace_name="Test",
            scope_tier=SlackScopeTier.PUBLIC,
        )

        assert workspace.can_access_private() is False

    def test_should_serialize_to_dict_without_sensitive_data(self, slack_workspace):
        """Test to_dict excludes encrypted token."""
        result = slack_workspace.to_dict()

        assert "workspace_id" in result
        assert "workspace_name" in result
        assert "encrypted_bot_token" not in result
        assert result["scope_tier"] == "public"

    def test_should_serialize_datetime_fields_as_iso(self, slack_workspace):
        """Test datetime fields are serialized as ISO format."""
        result = slack_workspace.to_dict()

        assert result["installed_at"] is not None
        assert "T" in result["installed_at"]  # ISO format includes T separator

    def test_should_handle_none_datetime_in_serialization(self):
        """Test to_dict handles None datetime fields."""
        workspace = SlackWorkspace(
            workspace_id="T12345678",
            workspace_name="Test",
            last_sync_at=None,
            linked_at=None,
        )
        result = workspace.to_dict()

        assert result["last_sync_at"] is None
        assert result["linked_at"] is None


class TestSlackChannel:
    """Tests for SlackChannel dataclass."""

    def test_should_create_channel_with_defaults(self):
        """Test creating channel with default values."""
        channel = SlackChannel(
            channel_id="C12345678",
            workspace_id="T12345678",
            channel_name="general",
        )

        assert channel.channel_type == SlackChannelType.PUBLIC
        assert channel.is_shared is False
        assert channel.is_archived is False
        assert channel.is_sensitive is False
        assert channel.auto_summarize is False

    def test_should_serialize_channel_to_dict(self, slack_channel):
        """Test channel serialization to dict."""
        result = slack_channel.to_dict()

        assert result["channel_id"] == "C12345678"
        assert result["channel_name"] == "general"
        assert result["channel_type"] == "public_channel"
        assert result["is_shared"] is False
        assert result["member_count"] == 50

    def test_should_serialize_private_channel_type(self, slack_private_channel):
        """Test private channel type serialization."""
        result = slack_private_channel.to_dict()

        assert result["channel_type"] == "private_channel"
        assert result["is_sensitive"] is True


class TestSlackUser:
    """Tests for SlackUser dataclass."""

    def test_should_create_user_with_defaults(self):
        """Test creating user with default values."""
        user = SlackUser(
            user_id="U12345678",
            workspace_id="T12345678",
            display_name="testuser",
        )

        assert user.is_bot is False
        assert user.is_admin is False
        assert user.is_owner is False

    def test_should_serialize_user_to_dict(self, slack_user):
        """Test user serialization to dict."""
        result = slack_user.to_dict()

        assert result["user_id"] == "U11111111"
        assert result["display_name"] == "testuser"
        assert result["real_name"] == "Test User"
        assert result["is_bot"] is False
        # Email should not be in to_dict (privacy)
        assert "email" not in result

    def test_should_serialize_bot_user(self, slack_bot_user):
        """Test bot user serialization."""
        result = slack_bot_user.to_dict()

        assert result["is_bot"] is True
        assert result["display_name"] == "TestBot"


class TestSlackMessage:
    """Tests for SlackMessage dataclass."""

    def test_should_create_message_with_defaults(self):
        """Test creating message with default values."""
        msg = SlackMessage(
            ts="1705312800.000001",
            channel_id="C12345678",
            workspace_id="T12345678",
            user_id="U11111111",
            text="Hello world",
        )

        assert msg.thread_ts is None
        assert msg.reply_count == 0
        assert msg.reactions == []
        assert msg.is_edited is False

    def test_should_parse_timestamp_to_datetime(self, slack_message):
        """Test timestamp property converts to datetime."""
        timestamp = slack_message.timestamp

        assert isinstance(timestamp, datetime)
        # Timestamp 1705312800 = 2024-01-15 08:00:00 UTC
        assert timestamp.year == 2024
        assert timestamp.month == 1

    def test_should_identify_thread_parent(self, slack_thread_parent):
        """Test is_thread_parent returns True for parent messages."""
        assert slack_thread_parent.is_thread_parent() is True

    def test_should_identify_thread_reply(self, slack_thread_reply):
        """Test is_thread_reply returns True for reply messages."""
        assert slack_thread_reply.is_thread_reply() is True

    def test_should_identify_non_thread_message(self, slack_message):
        """Test regular message is not thread parent or reply."""
        assert slack_message.is_thread_parent() is False
        assert slack_message.is_thread_reply() is False

    def test_should_identify_thread_parent_with_replies(self):
        """Test message with reply_count > 0 is thread parent."""
        msg = SlackMessage(
            ts="1705312800.000001",
            channel_id="C12345678",
            workspace_id="T12345678",
            user_id="U11111111",
            text="Thread starter",
            reply_count=3,
        )

        assert msg.is_thread_parent() is True


class TestSlackScopes:
    """Tests for OAuth scope constants."""

    def test_public_scopes_include_required(self):
        """Test PUBLIC scopes include required permissions."""
        assert "channels:history" in SLACK_SCOPES_PUBLIC
        assert "channels:read" in SLACK_SCOPES_PUBLIC
        assert "users:read" in SLACK_SCOPES_PUBLIC
        assert "team:read" in SLACK_SCOPES_PUBLIC

    def test_full_scopes_include_public(self):
        """Test FULL scopes include all PUBLIC scopes."""
        for scope in SLACK_SCOPES_PUBLIC:
            assert scope in SLACK_SCOPES_FULL

    def test_full_scopes_include_private(self):
        """Test FULL scopes include private channel access."""
        assert "groups:history" in SLACK_SCOPES_FULL
        assert "groups:read" in SLACK_SCOPES_FULL
        assert "im:history" in SLACK_SCOPES_FULL
        assert "files:read" in SLACK_SCOPES_FULL

    def test_public_scopes_exclude_private(self):
        """Test PUBLIC scopes do not include private access."""
        assert "groups:history" not in SLACK_SCOPES_PUBLIC
        assert "im:history" not in SLACK_SCOPES_PUBLIC
