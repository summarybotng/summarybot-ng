"""
Pytest fixtures for Slack integration tests.

Provides reusable fixtures for testing Slack modules including
mock workspaces, channels, users, messages, and API responses.
"""

import os
import pytest
import pytest_asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from cryptography.fernet import Fernet

# Set up encryption key for tests
_TEST_ENCRYPTION_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def setup_test_encryption_key(monkeypatch):
    """Ensure encryption key is set for all tests."""
    monkeypatch.setenv("ENCRYPTION_KEY", _TEST_ENCRYPTION_KEY)
    # Reset the cipher singleton
    import src.utils.encryption as enc
    enc._cipher = None
    yield
    enc._cipher = None


@pytest.fixture
def slack_workspace():
    """Create a test SlackWorkspace."""
    from src.slack.models import SlackWorkspace, SlackScopeTier
    from src.slack.token_store import SecureSlackTokenStore

    # Encrypt a test token (fake token for testing only)
    test_token = "xoxb-fake-token-for-testing-only-not-real"
    encrypted_token = SecureSlackTokenStore.encrypt_token(test_token)

    return SlackWorkspace(
        workspace_id="T12345678",
        workspace_name="Test Workspace",
        workspace_domain="test-workspace",
        encrypted_bot_token=encrypted_token,
        bot_user_id="U87654321",
        installed_by_discord_user="123456789012345678",
        installed_at=datetime(2024, 1, 15, 12, 0, 0),
        scopes="channels:history,channels:read,users:read,team:read,reactions:read",
        scope_tier=SlackScopeTier.PUBLIC,
        is_enterprise=False,
        enabled=True,
    )


@pytest.fixture
def slack_workspace_full_scopes():
    """Create a test SlackWorkspace with full scopes."""
    from src.slack.models import SlackWorkspace, SlackScopeTier
    from src.slack.token_store import SecureSlackTokenStore

    test_token = "xoxb-fake-full-scope-token-testing-only"
    encrypted_token = SecureSlackTokenStore.encrypt_token(test_token)

    return SlackWorkspace(
        workspace_id="T12345679",
        workspace_name="Full Scope Workspace",
        workspace_domain="full-scope",
        encrypted_bot_token=encrypted_token,
        bot_user_id="U87654322",
        installed_by_discord_user="123456789012345679",
        installed_at=datetime(2024, 1, 15, 12, 0, 0),
        scopes="channels:history,channels:read,users:read,team:read,reactions:read,groups:history,groups:read,im:history,im:read,mpim:history,mpim:read,files:read",
        scope_tier=SlackScopeTier.FULL,
        is_enterprise=False,
        enabled=True,
    )


@pytest.fixture
def slack_channel():
    """Create a test SlackChannel."""
    from src.slack.models import SlackChannel, SlackChannelType

    return SlackChannel(
        channel_id="C12345678",
        workspace_id="T12345678",
        channel_name="general",
        channel_type=SlackChannelType.PUBLIC,
        is_shared=False,
        is_archived=False,
        is_sensitive=False,
        auto_summarize=False,
        member_count=50,
        topic="General discussion",
        purpose="A place for general chat",
    )


@pytest.fixture
def slack_private_channel():
    """Create a test private SlackChannel."""
    from src.slack.models import SlackChannel, SlackChannelType

    return SlackChannel(
        channel_id="G12345678",
        workspace_id="T12345678",
        channel_name="private-channel",
        channel_type=SlackChannelType.PRIVATE,
        is_shared=False,
        is_archived=False,
        is_sensitive=True,
        auto_summarize=False,
        member_count=10,
    )


@pytest.fixture
def slack_user():
    """Create a test SlackUser."""
    from src.slack.models import SlackUser

    return SlackUser(
        user_id="U11111111",
        workspace_id="T12345678",
        display_name="testuser",
        real_name="Test User",
        email="testuser@example.com",
        is_bot=False,
        is_admin=False,
        is_owner=False,
        timezone="America/Los_Angeles",
    )


@pytest.fixture
def slack_bot_user():
    """Create a test SlackUser that is a bot."""
    from src.slack.models import SlackUser

    return SlackUser(
        user_id="B22222222",
        workspace_id="T12345678",
        display_name="TestBot",
        real_name="Test Bot",
        is_bot=True,
        is_admin=False,
        is_owner=False,
    )


@pytest.fixture
def slack_message():
    """Create a test SlackMessage."""
    from src.slack.models import SlackMessage

    return SlackMessage(
        ts="1705312800.123456",
        channel_id="C12345678",
        workspace_id="T12345678",
        user_id="U11111111",
        text="Hello, this is a test message!",
        thread_ts=None,
        reply_count=0,
        reply_users_count=0,
        reactions=[],
        attachments=[],
        files=[],
        is_edited=False,
        subtype=None,
    )


@pytest.fixture
def slack_thread_parent():
    """Create a test SlackMessage that is a thread parent."""
    from src.slack.models import SlackMessage

    return SlackMessage(
        ts="1705312800.000001",
        channel_id="C12345678",
        workspace_id="T12345678",
        user_id="U11111111",
        text="This is a thread parent message",
        thread_ts="1705312800.000001",  # thread_ts = ts for parent
        reply_count=5,
        reply_users_count=3,
        reactions=[{"name": "thumbsup", "users": ["U22222222", "U33333333"]}],
        attachments=[],
        files=[],
        is_edited=False,
        subtype=None,
    )


@pytest.fixture
def slack_thread_reply():
    """Create a test SlackMessage that is a thread reply."""
    from src.slack.models import SlackMessage

    return SlackMessage(
        ts="1705312900.000001",
        channel_id="C12345678",
        workspace_id="T12345678",
        user_id="U22222222",
        text="This is a reply in the thread",
        thread_ts="1705312800.000001",  # Points to parent
        reply_count=0,
        reply_users_count=0,
        reactions=[],
        attachments=[],
        files=[],
        is_edited=False,
        subtype=None,
    )


@pytest.fixture
def slack_message_with_file():
    """Create a test SlackMessage with a file attachment."""
    from src.slack.models import SlackMessage

    return SlackMessage(
        ts="1705313000.000001",
        channel_id="C12345678",
        workspace_id="T12345678",
        user_id="U11111111",
        text="Here is a file",
        thread_ts=None,
        reply_count=0,
        reply_users_count=0,
        reactions=[],
        attachments=[],
        files=[
            {
                "id": "F12345678",
                "name": "document.pdf",
                "mimetype": "application/pdf",
                "size": 1024000,
                "url_private": "https://files.slack.com/files-pri/T12345678-F12345678/document.pdf",
                "url_private_download": "https://files.slack.com/files-pri/T12345678-F12345678/download/document.pdf",
                "title": "Important Document",
            }
        ],
        is_edited=False,
        subtype="file_share",
    )


@pytest.fixture
def slack_bot_message():
    """Create a test SlackMessage from a bot."""
    from src.slack.models import SlackMessage

    return SlackMessage(
        ts="1705313100.000001",
        channel_id="C12345678",
        workspace_id="T12345678",
        user_id="B22222222",
        text="This is an automated bot message",
        thread_ts=None,
        reply_count=0,
        reply_users_count=0,
        reactions=[],
        attachments=[],
        files=[],
        is_edited=False,
        subtype="bot_message",
    )


@pytest.fixture
def slack_signing_secret():
    """Return a test signing secret."""
    return "test_signing_secret_1234567890"


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx.AsyncClient."""
    client = AsyncMock()
    client.aclose = AsyncMock()
    return client


@pytest.fixture
def users_cache(slack_user, slack_bot_user):
    """Create a users cache for testing normalizer."""
    return {
        slack_user.user_id: slack_user,
        slack_bot_user.user_id: slack_bot_user,
    }


@pytest.fixture
def slack_api_response_channels():
    """Create a mock Slack API response for conversations.list."""
    return {
        "ok": True,
        "channels": [
            {
                "id": "C12345678",
                "name": "general",
                "is_private": False,
                "is_archived": False,
                "is_shared": False,
                "num_members": 50,
                "topic": {"value": "General discussion"},
                "purpose": {"value": "A place for general chat"},
            },
            {
                "id": "C23456789",
                "name": "random",
                "is_private": False,
                "is_archived": False,
                "is_shared": False,
                "num_members": 45,
                "topic": {"value": "Random topics"},
                "purpose": {"value": "For random discussions"},
            },
        ],
        "response_metadata": {"next_cursor": ""},
    }


@pytest.fixture
def slack_api_response_history():
    """Create a mock Slack API response for conversations.history."""
    return {
        "ok": True,
        "messages": [
            {
                "ts": "1705312800.000001",
                "user": "U11111111",
                "text": "Hello everyone!",
                "type": "message",
            },
            {
                "ts": "1705312900.000001",
                "user": "U22222222",
                "text": "Hi there!",
                "type": "message",
            },
            {
                "ts": "1705313000.000001",
                "user": "U11111111",
                "text": "How's everyone doing?",
                "type": "message",
                "thread_ts": "1705313000.000001",
                "reply_count": 3,
                "reply_users_count": 2,
            },
        ],
        "response_metadata": {"next_cursor": ""},
        "has_more": False,
    }


@pytest.fixture
def slack_api_response_replies():
    """Create a mock Slack API response for conversations.replies."""
    return {
        "ok": True,
        "messages": [
            {
                "ts": "1705313000.000001",
                "user": "U11111111",
                "text": "How's everyone doing?",
                "type": "message",
                "thread_ts": "1705313000.000001",
                "reply_count": 3,
                "reply_users_count": 2,
            },
            {
                "ts": "1705313100.000001",
                "user": "U22222222",
                "text": "Doing great!",
                "type": "message",
                "thread_ts": "1705313000.000001",
            },
            {
                "ts": "1705313200.000001",
                "user": "U33333333",
                "text": "All good here",
                "type": "message",
                "thread_ts": "1705313000.000001",
            },
        ],
        "response_metadata": {"next_cursor": ""},
        "has_more": False,
    }


@pytest.fixture
def slack_api_response_users():
    """Create a mock Slack API response for users.list."""
    return {
        "ok": True,
        "members": [
            {
                "id": "U11111111",
                "deleted": False,
                "is_bot": False,
                "is_admin": False,
                "is_owner": False,
                "tz": "America/Los_Angeles",
                "profile": {
                    "display_name": "testuser",
                    "real_name": "Test User",
                    "email": "testuser@example.com",
                    "image_72": "https://example.com/avatar.png",
                    "status_text": "Working",
                    "status_emoji": ":computer:",
                },
            },
            {
                "id": "U22222222",
                "deleted": False,
                "is_bot": False,
                "is_admin": True,
                "is_owner": False,
                "tz": "America/New_York",
                "profile": {
                    "display_name": "admin",
                    "real_name": "Admin User",
                    "email": "admin@example.com",
                    "image_72": "https://example.com/admin_avatar.png",
                },
            },
        ],
        "response_metadata": {"next_cursor": ""},
    }


@pytest.fixture
def slack_event_callback_payload():
    """Create a test Slack event callback payload."""
    return {
        "type": "event_callback",
        "event_id": "Ev12345678",
        "team_id": "T12345678",
        "event": {
            "type": "message",
            "channel": "C12345678",
            "user": "U11111111",
            "text": "Hello from event!",
            "ts": "1705312800.000001",
        },
    }


@pytest.fixture
def slack_url_verification_payload():
    """Create a test Slack URL verification payload."""
    return {
        "type": "url_verification",
        "challenge": "test_challenge_12345",
    }
