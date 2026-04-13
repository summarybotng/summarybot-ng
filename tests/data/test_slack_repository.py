"""
Unit tests for SQLiteSlackRepository.

Tests cover:
- Workspace CRUD operations
- Channel CRUD operations
- User cache operations
- Event deduplication
- Thread tracking
- File tracking

Following ADR-043 Slack workspace integration patterns.
"""

import pytest
import pytest_asyncio
import json
from datetime import datetime, timedelta
from typing import AsyncGenerator

from src.data.sqlite.connection import SQLiteConnection
from src.data.sqlite.slack_repository import SQLiteSlackRepository
from src.slack.models import (
    SlackWorkspace,
    SlackChannel,
    SlackUser,
    SlackScopeTier,
    SlackChannelType,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def slack_db() -> AsyncGenerator[SQLiteConnection, None]:
    """Create an in-memory SQLite database with Slack schema for testing."""
    connection = SQLiteConnection(":memory:", pool_size=1)
    await connection.connect()

    # Create Slack tables (from migrations 046, 047, 048)
    await _create_slack_schema(connection)

    yield connection

    await connection.disconnect()


async def _create_slack_schema(connection: SQLiteConnection) -> None:
    """Create Slack-specific database schema for testing."""
    # Migration 046: Slack workspaces, channels, users
    await connection.execute("""
        CREATE TABLE IF NOT EXISTS slack_workspaces (
            workspace_id TEXT PRIMARY KEY,
            workspace_name TEXT NOT NULL,
            workspace_domain TEXT,
            encrypted_bot_token TEXT NOT NULL,
            bot_user_id TEXT NOT NULL,
            installed_by_discord_user TEXT NOT NULL,
            installed_at TEXT NOT NULL DEFAULT (datetime('now')),
            scopes TEXT NOT NULL,
            scope_tier TEXT NOT NULL DEFAULT 'public',
            is_enterprise BOOLEAN DEFAULT FALSE,
            enterprise_id TEXT,
            enabled BOOLEAN DEFAULT TRUE,
            last_sync_at TEXT,
            metadata TEXT DEFAULT '{}',
            linked_guild_id TEXT,
            linked_at TEXT,
            CONSTRAINT slack_workspaces_scope_tier_check CHECK (
                scope_tier IN ('public', 'full')
            )
        )
    """)

    await connection.execute("""
        CREATE TABLE IF NOT EXISTS slack_channels (
            channel_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            channel_name TEXT NOT NULL,
            channel_type TEXT NOT NULL DEFAULT 'public_channel',
            is_shared BOOLEAN DEFAULT FALSE,
            is_archived BOOLEAN DEFAULT FALSE,
            is_sensitive BOOLEAN DEFAULT FALSE,
            auto_summarize BOOLEAN DEFAULT FALSE,
            summary_schedule TEXT,
            last_message_ts TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            topic TEXT,
            purpose TEXT,
            member_count INTEGER DEFAULT 0,
            FOREIGN KEY (workspace_id) REFERENCES slack_workspaces(workspace_id) ON DELETE CASCADE,
            CONSTRAINT slack_channels_type_check CHECK (
                channel_type IN ('public_channel', 'private_channel', 'im', 'mpim')
            )
        )
    """)

    await connection.execute("""
        CREATE TABLE IF NOT EXISTS slack_users (
            user_id TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            display_name TEXT NOT NULL,
            real_name TEXT,
            email TEXT,
            is_bot BOOLEAN DEFAULT FALSE,
            is_admin BOOLEAN DEFAULT FALSE,
            is_owner BOOLEAN DEFAULT FALSE,
            avatar_url TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
            timezone TEXT,
            status_text TEXT,
            status_emoji TEXT,
            PRIMARY KEY (workspace_id, user_id),
            FOREIGN KEY (workspace_id) REFERENCES slack_workspaces(workspace_id) ON DELETE CASCADE
        )
    """)

    # Migration 047: Slack events
    await connection.execute("""
        CREATE TABLE IF NOT EXISTS slack_event_log (
            event_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_subtype TEXT,
            channel_id TEXT,
            user_id TEXT,
            message_ts TEXT,
            thread_ts TEXT,
            received_at TEXT NOT NULL DEFAULT (datetime('now')),
            processed BOOLEAN DEFAULT FALSE,
            processed_at TEXT,
            error_message TEXT,
            raw_event TEXT,
            FOREIGN KEY (workspace_id) REFERENCES slack_workspaces(workspace_id) ON DELETE CASCADE
        )
    """)

    await connection.execute("""
        CREATE TABLE IF NOT EXISTS slack_app_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            triggered_by_user TEXT,
            occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
            metadata TEXT DEFAULT '{}',
            FOREIGN KEY (workspace_id) REFERENCES slack_workspaces(workspace_id) ON DELETE CASCADE,
            CONSTRAINT slack_app_events_type_check CHECK (
                event_type IN ('app_installed', 'app_uninstalled', 'tokens_revoked', 'scope_changed')
            )
        )
    """)

    # Migration 048: Slack threads and files
    await connection.execute("""
        CREATE TABLE IF NOT EXISTS slack_threads (
            thread_ts TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            reply_count INTEGER DEFAULT 0,
            reply_users_count INTEGER DEFAULT 0,
            latest_reply_ts TEXT,
            last_fetched_at TEXT,
            parent_user_id TEXT,
            parent_text TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (workspace_id, channel_id, thread_ts),
            FOREIGN KEY (workspace_id) REFERENCES slack_workspaces(workspace_id) ON DELETE CASCADE
        )
    """)

    await connection.execute("""
        CREATE TABLE IF NOT EXISTS slack_files (
            file_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            channel_id TEXT,
            user_id TEXT,
            filename TEXT NOT NULL,
            title TEXT,
            mimetype TEXT,
            filetype TEXT,
            size_bytes INTEGER,
            permalink TEXT,
            permalink_public TEXT,
            url_private TEXT,
            url_private_download TEXT,
            local_path TEXT,
            downloaded_at TEXT,
            expires_at TEXT,
            is_external BOOLEAN DEFAULT FALSE,
            is_public BOOLEAN DEFAULT FALSE,
            shares TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (workspace_id) REFERENCES slack_workspaces(workspace_id) ON DELETE CASCADE
        )
    """)

    await connection.execute("""
        CREATE TABLE IF NOT EXISTS slack_thread_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            thread_ts TEXT NOT NULL,
            message_ts TEXT NOT NULL,
            user_id TEXT,
            text TEXT,
            has_files BOOLEAN DEFAULT FALSE,
            fetched_at TEXT DEFAULT (datetime('now')),
            UNIQUE(workspace_id, channel_id, thread_ts, message_ts),
            FOREIGN KEY (workspace_id, channel_id, thread_ts)
                REFERENCES slack_threads(workspace_id, channel_id, thread_ts) ON DELETE CASCADE
        )
    """)

    # Create indexes for efficient querying
    await connection.execute("CREATE INDEX IF NOT EXISTS idx_slack_workspaces_guild ON slack_workspaces(linked_guild_id)")
    await connection.execute("CREATE INDEX IF NOT EXISTS idx_slack_workspaces_enabled ON slack_workspaces(enabled)")
    await connection.execute("CREATE INDEX IF NOT EXISTS idx_slack_channels_workspace ON slack_channels(workspace_id)")
    await connection.execute("CREATE INDEX IF NOT EXISTS idx_slack_users_workspace ON slack_users(workspace_id)")
    await connection.execute("CREATE INDEX IF NOT EXISTS idx_slack_events_workspace ON slack_event_log(workspace_id)")
    await connection.execute("CREATE INDEX IF NOT EXISTS idx_slack_threads_workspace ON slack_threads(workspace_id)")
    await connection.execute("CREATE INDEX IF NOT EXISTS idx_slack_files_workspace ON slack_files(workspace_id)")


@pytest_asyncio.fixture
async def slack_repository(slack_db: SQLiteConnection) -> SQLiteSlackRepository:
    """Create a Slack repository with in-memory database."""
    return SQLiteSlackRepository(slack_db)


@pytest.fixture
def sample_workspace() -> SlackWorkspace:
    """Create a sample Slack workspace for testing."""
    return SlackWorkspace(
        workspace_id="T12345ABC",
        workspace_name="Test Workspace",
        workspace_domain="test-workspace",
        encrypted_bot_token="encrypted_xoxb_token_here",
        bot_user_id="U12345BOT",
        installed_by_discord_user="123456789012345678",
        installed_at=datetime.utcnow(),
        scopes="channels:history,channels:read,users:read,team:read",
        scope_tier=SlackScopeTier.PUBLIC,
        is_enterprise=False,
        enterprise_id=None,
        enabled=True,
        last_sync_at=None,
        metadata={"install_version": "1.0"},
        linked_guild_id="987654321098765432",
        linked_at=datetime.utcnow(),
    )


@pytest.fixture
def sample_channel() -> SlackChannel:
    """Create a sample Slack channel for testing."""
    return SlackChannel(
        channel_id="C12345ABC",
        workspace_id="T12345ABC",
        channel_name="general",
        channel_type=SlackChannelType.PUBLIC,
        is_shared=False,
        is_archived=False,
        is_sensitive=False,
        auto_summarize=True,
        summary_schedule="0 9 * * 1-5",
        last_message_ts="1234567890.123456",
        created_at=datetime.utcnow(),
        topic="General discussion",
        purpose="A place for general chat",
        member_count=42,
    )


@pytest.fixture
def sample_user() -> SlackUser:
    """Create a sample Slack user for testing."""
    return SlackUser(
        user_id="U12345ABC",
        workspace_id="T12345ABC",
        display_name="testuser",
        real_name="Test User",
        email="test@example.com",
        is_bot=False,
        is_admin=False,
        is_owner=False,
        avatar_url="https://example.com/avatar.png",
        updated_at=datetime.utcnow(),
        timezone="America/New_York",
        status_text="Working from home",
        status_emoji=":house:",
    )


# =============================================================================
# Workspace CRUD Tests
# =============================================================================


@pytest.mark.asyncio
class TestWorkspaceCRUD:
    """Test workspace create, read, update, delete operations."""

    async def test_create_workspace_with_encrypted_token(
        self,
        slack_repository: SQLiteSlackRepository,
        sample_workspace: SlackWorkspace,
    ):
        """Test creating a workspace with encrypted token."""
        workspace_id = await slack_repository.save_workspace(sample_workspace)

        assert workspace_id == "T12345ABC"

        # Verify data was stored
        workspace = await slack_repository.get_workspace(workspace_id)
        assert workspace is not None
        assert workspace.workspace_id == "T12345ABC"
        assert workspace.workspace_name == "Test Workspace"
        assert workspace.encrypted_bot_token == "encrypted_xoxb_token_here"
        assert workspace.scope_tier == SlackScopeTier.PUBLIC

    async def test_get_workspace_by_id(
        self,
        slack_repository: SQLiteSlackRepository,
        sample_workspace: SlackWorkspace,
    ):
        """Test retrieving a workspace by ID."""
        await slack_repository.save_workspace(sample_workspace)

        workspace = await slack_repository.get_workspace("T12345ABC")

        assert workspace is not None
        assert workspace.workspace_id == "T12345ABC"
        assert workspace.bot_user_id == "U12345BOT"
        assert workspace.installed_by_discord_user == "123456789012345678"

    async def test_get_workspace_not_found(
        self,
        slack_repository: SQLiteSlackRepository,
    ):
        """Test retrieving a non-existent workspace returns None."""
        workspace = await slack_repository.get_workspace("T_NONEXISTENT")

        assert workspace is None

    async def test_get_workspace_by_guild(
        self,
        slack_repository: SQLiteSlackRepository,
        sample_workspace: SlackWorkspace,
    ):
        """Test retrieving workspace by linked guild ID."""
        await slack_repository.save_workspace(sample_workspace)

        workspace = await slack_repository.get_workspace_by_guild("987654321098765432")

        assert workspace is not None
        assert workspace.workspace_id == "T12345ABC"
        assert workspace.linked_guild_id == "987654321098765432"

    async def test_get_workspace_by_guild_disabled(
        self,
        slack_repository: SQLiteSlackRepository,
        sample_workspace: SlackWorkspace,
    ):
        """Test that disabled workspace is not returned by guild lookup."""
        sample_workspace.enabled = False
        await slack_repository.save_workspace(sample_workspace)

        workspace = await slack_repository.get_workspace_by_guild("987654321098765432")

        assert workspace is None

    async def test_list_workspaces_for_guild(
        self,
        slack_repository: SQLiteSlackRepository,
    ):
        """Test listing workspaces, optionally filtered by enabled status."""
        # Create multiple workspaces
        workspace1 = SlackWorkspace(
            workspace_id="T11111111",
            workspace_name="Workspace 1",
            encrypted_bot_token="token1",
            bot_user_id="U11111",
            installed_by_discord_user="user1",
            installed_at=datetime.utcnow() - timedelta(days=2),
            scopes="scope1",
            enabled=True,
        )
        workspace2 = SlackWorkspace(
            workspace_id="T22222222",
            workspace_name="Workspace 2",
            encrypted_bot_token="token2",
            bot_user_id="U22222",
            installed_by_discord_user="user2",
            installed_at=datetime.utcnow() - timedelta(days=1),
            scopes="scope2",
            enabled=True,
        )
        workspace3 = SlackWorkspace(
            workspace_id="T33333333",
            workspace_name="Workspace 3 (Disabled)",
            encrypted_bot_token="token3",
            bot_user_id="U33333",
            installed_by_discord_user="user3",
            installed_at=datetime.utcnow(),
            scopes="scope3",
            enabled=False,
        )

        await slack_repository.save_workspace(workspace1)
        await slack_repository.save_workspace(workspace2)
        await slack_repository.save_workspace(workspace3)

        # List enabled only (default)
        enabled_workspaces = await slack_repository.list_workspaces(enabled_only=True)
        assert len(enabled_workspaces) == 2
        assert all(w.enabled for w in enabled_workspaces)

        # List all
        all_workspaces = await slack_repository.list_workspaces(enabled_only=False)
        assert len(all_workspaces) == 3

    async def test_update_workspace_settings(
        self,
        slack_repository: SQLiteSlackRepository,
        sample_workspace: SlackWorkspace,
    ):
        """Test updating workspace settings via upsert."""
        await slack_repository.save_workspace(sample_workspace)

        # Update the workspace
        sample_workspace.workspace_name = "Updated Workspace Name"
        sample_workspace.scope_tier = SlackScopeTier.FULL
        sample_workspace.enabled = False

        await slack_repository.save_workspace(sample_workspace)

        # Verify update
        workspace = await slack_repository.get_workspace("T12345ABC")
        assert workspace.workspace_name == "Updated Workspace Name"
        assert workspace.scope_tier == SlackScopeTier.FULL
        assert workspace.enabled is False

    async def test_delete_workspace(
        self,
        slack_repository: SQLiteSlackRepository,
        sample_workspace: SlackWorkspace,
    ):
        """Test deleting a workspace."""
        await slack_repository.save_workspace(sample_workspace)

        # Verify exists
        assert await slack_repository.get_workspace("T12345ABC") is not None

        # Delete
        deleted = await slack_repository.delete_workspace("T12345ABC")
        assert deleted is True

        # Verify deleted
        assert await slack_repository.get_workspace("T12345ABC") is None

    async def test_delete_workspace_not_found(
        self,
        slack_repository: SQLiteSlackRepository,
    ):
        """Test deleting a non-existent workspace returns False."""
        deleted = await slack_repository.delete_workspace("T_NONEXISTENT")
        assert deleted is False

    async def test_delete_workspace_cascades_to_channels(
        self,
        slack_repository: SQLiteSlackRepository,
        sample_workspace: SlackWorkspace,
        sample_channel: SlackChannel,
    ):
        """Test that deleting a workspace cascades to its channels."""
        await slack_repository.save_workspace(sample_workspace)
        await slack_repository.save_channel(sample_channel)

        # Verify channel exists
        assert await slack_repository.get_channel("C12345ABC") is not None

        # Delete workspace
        await slack_repository.delete_workspace("T12345ABC")

        # Verify channel was cascade deleted
        assert await slack_repository.get_channel("C12345ABC") is None

    async def test_link_workspace_to_guild(
        self,
        slack_repository: SQLiteSlackRepository,
        sample_workspace: SlackWorkspace,
    ):
        """Test linking a workspace to a Discord guild."""
        sample_workspace.linked_guild_id = None
        sample_workspace.linked_at = None
        await slack_repository.save_workspace(sample_workspace)

        # Link to guild
        linked = await slack_repository.link_workspace_to_guild(
            "T12345ABC", "new_guild_123"
        )
        assert linked is True

        # Verify link
        workspace = await slack_repository.get_workspace("T12345ABC")
        assert workspace.linked_guild_id == "new_guild_123"
        assert workspace.linked_at is not None


# =============================================================================
# Channel CRUD Tests
# =============================================================================


@pytest.mark.asyncio
class TestChannelCRUD:
    """Test channel create, read, update, delete operations."""

    async def test_create_channel(
        self,
        slack_repository: SQLiteSlackRepository,
        sample_workspace: SlackWorkspace,
        sample_channel: SlackChannel,
    ):
        """Test creating a channel."""
        await slack_repository.save_workspace(sample_workspace)
        channel_id = await slack_repository.save_channel(sample_channel)

        assert channel_id == "C12345ABC"

        channel = await slack_repository.get_channel(channel_id)
        assert channel is not None
        assert channel.channel_name == "general"
        assert channel.channel_type == SlackChannelType.PUBLIC

    async def test_get_channels_for_workspace(
        self,
        slack_repository: SQLiteSlackRepository,
        sample_workspace: SlackWorkspace,
    ):
        """Test listing channels for a workspace."""
        await slack_repository.save_workspace(sample_workspace)

        # Create multiple channels
        channels = [
            SlackChannel(
                channel_id="C00000001",
                workspace_id="T12345ABC",
                channel_name="general",
                channel_type=SlackChannelType.PUBLIC,
                auto_summarize=True,
            ),
            SlackChannel(
                channel_id="C00000002",
                workspace_id="T12345ABC",
                channel_name="random",
                channel_type=SlackChannelType.PUBLIC,
                auto_summarize=False,
            ),
            SlackChannel(
                channel_id="C00000003",
                workspace_id="T12345ABC",
                channel_name="private-team",
                channel_type=SlackChannelType.PRIVATE,
                auto_summarize=True,
            ),
            SlackChannel(
                channel_id="C00000004",
                workspace_id="T12345ABC",
                channel_name="archived",
                channel_type=SlackChannelType.PUBLIC,
                is_archived=True,
            ),
        ]

        for ch in channels:
            await slack_repository.save_channel(ch)

        # List all non-archived
        all_channels = await slack_repository.list_channels("T12345ABC")
        assert len(all_channels) == 3  # Excludes archived

        # List with archived
        with_archived = await slack_repository.list_channels(
            "T12345ABC", include_archived=True
        )
        assert len(with_archived) == 4

        # Filter by type
        private_channels = await slack_repository.list_channels(
            "T12345ABC", channel_type=SlackChannelType.PRIVATE
        )
        assert len(private_channels) == 1
        assert private_channels[0].channel_name == "private-team"

        # Filter by auto_summarize
        auto_summarize_channels = await slack_repository.list_channels(
            "T12345ABC", auto_summarize_only=True
        )
        assert len(auto_summarize_channels) == 2

    async def test_update_channel_settings(
        self,
        slack_repository: SQLiteSlackRepository,
        sample_workspace: SlackWorkspace,
        sample_channel: SlackChannel,
    ):
        """Test updating channel settings (auto_summarize, is_sensitive)."""
        await slack_repository.save_workspace(sample_workspace)
        await slack_repository.save_channel(sample_channel)

        # Update settings
        sample_channel.auto_summarize = False
        sample_channel.is_sensitive = True
        sample_channel.summary_schedule = None

        await slack_repository.save_channel(sample_channel)

        channel = await slack_repository.get_channel("C12345ABC")
        assert channel.auto_summarize is False
        assert channel.is_sensitive is True
        assert channel.summary_schedule is None

    async def test_get_channel_by_id(
        self,
        slack_repository: SQLiteSlackRepository,
        sample_workspace: SlackWorkspace,
        sample_channel: SlackChannel,
    ):
        """Test retrieving a channel by ID."""
        await slack_repository.save_workspace(sample_workspace)
        await slack_repository.save_channel(sample_channel)

        channel = await slack_repository.get_channel("C12345ABC")

        assert channel is not None
        assert channel.channel_id == "C12345ABC"
        assert channel.workspace_id == "T12345ABC"
        assert channel.topic == "General discussion"
        assert channel.member_count == 42

    async def test_get_channel_not_found(
        self,
        slack_repository: SQLiteSlackRepository,
    ):
        """Test retrieving a non-existent channel returns None."""
        channel = await slack_repository.get_channel("C_NONEXISTENT")
        assert channel is None

    async def test_save_channels_batch(
        self,
        slack_repository: SQLiteSlackRepository,
        sample_workspace: SlackWorkspace,
    ):
        """Test batch saving multiple channels."""
        await slack_repository.save_workspace(sample_workspace)

        channels = [
            SlackChannel(
                channel_id=f"C{i:08d}",
                workspace_id="T12345ABC",
                channel_name=f"channel-{i}",
            )
            for i in range(10)
        ]

        count = await slack_repository.save_channels_batch(channels)
        assert count == 10

        all_channels = await slack_repository.list_channels("T12345ABC")
        assert len(all_channels) == 10

    async def test_save_channels_batch_empty(
        self,
        slack_repository: SQLiteSlackRepository,
    ):
        """Test batch saving empty list returns 0."""
        count = await slack_repository.save_channels_batch([])
        assert count == 0

    async def test_update_channel_last_message(
        self,
        slack_repository: SQLiteSlackRepository,
        sample_workspace: SlackWorkspace,
        sample_channel: SlackChannel,
    ):
        """Test updating a channel's last message timestamp."""
        await slack_repository.save_workspace(sample_workspace)
        await slack_repository.save_channel(sample_channel)

        # Update last message
        new_ts = "1234567999.999999"
        updated = await slack_repository.update_channel_last_message(
            "C12345ABC", new_ts
        )
        assert updated is True

        channel = await slack_repository.get_channel("C12345ABC")
        assert channel.last_message_ts == new_ts


# =============================================================================
# User Cache Tests
# =============================================================================


@pytest.mark.asyncio
class TestUserCache:
    """Test user cache operations."""

    async def test_store_user_info(
        self,
        slack_repository: SQLiteSlackRepository,
        sample_workspace: SlackWorkspace,
        sample_user: SlackUser,
    ):
        """Test storing user information."""
        await slack_repository.save_workspace(sample_workspace)
        user_id = await slack_repository.save_user(sample_user)

        assert user_id == "U12345ABC"

    async def test_get_user_by_id(
        self,
        slack_repository: SQLiteSlackRepository,
        sample_workspace: SlackWorkspace,
        sample_user: SlackUser,
    ):
        """Test retrieving a user by workspace and user ID."""
        await slack_repository.save_workspace(sample_workspace)
        await slack_repository.save_user(sample_user)

        user = await slack_repository.get_user("T12345ABC", "U12345ABC")

        assert user is not None
        assert user.user_id == "U12345ABC"
        assert user.display_name == "testuser"
        assert user.real_name == "Test User"
        assert user.email == "test@example.com"
        assert user.timezone == "America/New_York"

    async def test_get_user_not_found(
        self,
        slack_repository: SQLiteSlackRepository,
        sample_workspace: SlackWorkspace,
    ):
        """Test retrieving a non-existent user returns None."""
        await slack_repository.save_workspace(sample_workspace)

        user = await slack_repository.get_user("T12345ABC", "U_NONEXISTENT")
        assert user is None

    async def test_update_user_display_name(
        self,
        slack_repository: SQLiteSlackRepository,
        sample_workspace: SlackWorkspace,
        sample_user: SlackUser,
    ):
        """Test updating user display name."""
        await slack_repository.save_workspace(sample_workspace)
        await slack_repository.save_user(sample_user)

        # Update display name
        sample_user.display_name = "updated_username"
        sample_user.status_text = "On vacation"

        await slack_repository.save_user(sample_user)

        user = await slack_repository.get_user("T12345ABC", "U12345ABC")
        assert user.display_name == "updated_username"
        assert user.status_text == "On vacation"

    async def test_list_users(
        self,
        slack_repository: SQLiteSlackRepository,
        sample_workspace: SlackWorkspace,
    ):
        """Test listing users for a workspace."""
        await slack_repository.save_workspace(sample_workspace)

        # Create multiple users including bots
        users = [
            SlackUser(
                user_id="U00000001",
                workspace_id="T12345ABC",
                display_name="alice",
                is_bot=False,
            ),
            SlackUser(
                user_id="U00000002",
                workspace_id="T12345ABC",
                display_name="bob",
                is_bot=False,
            ),
            SlackUser(
                user_id="UBOT00001",
                workspace_id="T12345ABC",
                display_name="slackbot",
                is_bot=True,
            ),
        ]

        for u in users:
            await slack_repository.save_user(u)

        # List without bots (default)
        human_users = await slack_repository.list_users("T12345ABC")
        assert len(human_users) == 2
        assert all(not u.is_bot for u in human_users)

        # List including bots
        all_users = await slack_repository.list_users("T12345ABC", include_bots=True)
        assert len(all_users) == 3

    async def test_save_users_batch(
        self,
        slack_repository: SQLiteSlackRepository,
        sample_workspace: SlackWorkspace,
    ):
        """Test batch saving multiple users."""
        await slack_repository.save_workspace(sample_workspace)

        users = [
            SlackUser(
                user_id=f"U{i:08d}",
                workspace_id="T12345ABC",
                display_name=f"user-{i}",
            )
            for i in range(10)
        ]

        count = await slack_repository.save_users_batch(users)
        assert count == 10

        all_users = await slack_repository.list_users("T12345ABC")
        assert len(all_users) == 10


# =============================================================================
# Event Deduplication Tests
# =============================================================================


@pytest.mark.asyncio
class TestEventDedup:
    """Test event deduplication operations."""

    async def test_store_event_id(
        self,
        slack_repository: SQLiteSlackRepository,
        slack_db: SQLiteConnection,
        sample_workspace: SlackWorkspace,
    ):
        """Test storing an event ID for deduplication."""
        await slack_repository.save_workspace(sample_workspace)

        # Store event directly (repository doesn't have this method yet)
        await slack_db.execute(
            """
            INSERT INTO slack_event_log (event_id, workspace_id, event_type, received_at)
            VALUES (?, ?, ?, datetime('now'))
            """,
            ("evt_12345", "T12345ABC", "message"),
        )

        # Verify event was stored
        row = await slack_db.fetch_one(
            "SELECT * FROM slack_event_log WHERE event_id = ?", ("evt_12345",)
        )
        assert row is not None
        assert row["event_id"] == "evt_12345"
        assert row["workspace_id"] == "T12345ABC"

    async def test_check_event_exists(
        self,
        slack_repository: SQLiteSlackRepository,
        slack_db: SQLiteConnection,
        sample_workspace: SlackWorkspace,
    ):
        """Test checking if an event ID already exists."""
        await slack_repository.save_workspace(sample_workspace)

        # Store an event
        await slack_db.execute(
            """
            INSERT INTO slack_event_log (event_id, workspace_id, event_type, received_at)
            VALUES (?, ?, ?, datetime('now'))
            """,
            ("evt_exists", "T12345ABC", "message"),
        )

        # Check existing event
        row = await slack_db.fetch_one(
            "SELECT 1 FROM slack_event_log WHERE event_id = ?", ("evt_exists",)
        )
        assert row is not None

        # Check non-existing event
        row = await slack_db.fetch_one(
            "SELECT 1 FROM slack_event_log WHERE event_id = ?", ("evt_not_exists",)
        )
        assert row is None

    async def test_event_cleanup_old_events(
        self,
        slack_repository: SQLiteSlackRepository,
        slack_db: SQLiteConnection,
        sample_workspace: SlackWorkspace,
    ):
        """Test that old events can be cleaned up."""
        await slack_repository.save_workspace(sample_workspace)

        # Store an old event (8 days ago)
        old_time = (datetime.utcnow() - timedelta(days=8)).isoformat()
        await slack_db.execute(
            """
            INSERT INTO slack_event_log (event_id, workspace_id, event_type, received_at)
            VALUES (?, ?, ?, ?)
            """,
            ("evt_old", "T12345ABC", "message", old_time),
        )

        # Store a recent event
        await slack_db.execute(
            """
            INSERT INTO slack_event_log (event_id, workspace_id, event_type, received_at)
            VALUES (?, ?, ?, datetime('now'))
            """,
            ("evt_recent", "T12345ABC", "message"),
        )

        # Run cleanup (events older than 7 days)
        await slack_db.execute(
            "DELETE FROM slack_event_log WHERE received_at < datetime('now', '-7 days')"
        )

        # Verify old event was removed
        row = await slack_db.fetch_one(
            "SELECT * FROM slack_event_log WHERE event_id = ?", ("evt_old",)
        )
        assert row is None

        # Verify recent event still exists
        row = await slack_db.fetch_one(
            "SELECT * FROM slack_event_log WHERE event_id = ?", ("evt_recent",)
        )
        assert row is not None


# =============================================================================
# Thread Tracking Tests
# =============================================================================


@pytest.mark.asyncio
class TestThreadTracking:
    """Test thread tracking operations."""

    async def test_store_thread_metadata(
        self,
        slack_repository: SQLiteSlackRepository,
        slack_db: SQLiteConnection,
        sample_workspace: SlackWorkspace,
    ):
        """Test storing thread metadata."""
        await slack_repository.save_workspace(sample_workspace)

        # Store thread
        await slack_db.execute(
            """
            INSERT INTO slack_threads (
                thread_ts, channel_id, workspace_id, reply_count, reply_users_count,
                parent_user_id, parent_text, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            ("1234567890.123456", "C12345ABC", "T12345ABC", 5, 3, "U12345ABC", "Original message"),
        )

        # Verify thread was stored
        row = await slack_db.fetch_one(
            """
            SELECT * FROM slack_threads
            WHERE workspace_id = ? AND channel_id = ? AND thread_ts = ?
            """,
            ("T12345ABC", "C12345ABC", "1234567890.123456"),
        )
        assert row is not None
        assert row["reply_count"] == 5
        assert row["parent_text"] == "Original message"

    async def test_get_thread_by_ts(
        self,
        slack_repository: SQLiteSlackRepository,
        slack_db: SQLiteConnection,
        sample_workspace: SlackWorkspace,
    ):
        """Test retrieving a thread by timestamp."""
        await slack_repository.save_workspace(sample_workspace)

        # Store thread
        await slack_db.execute(
            """
            INSERT INTO slack_threads (
                thread_ts, channel_id, workspace_id, reply_count, latest_reply_ts
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            ("1234567890.123456", "C12345ABC", "T12345ABC", 10, "1234567999.999999"),
        )

        # Retrieve thread
        row = await slack_db.fetch_one(
            """
            SELECT * FROM slack_threads
            WHERE workspace_id = ? AND channel_id = ? AND thread_ts = ?
            """,
            ("T12345ABC", "C12345ABC", "1234567890.123456"),
        )

        assert row is not None
        assert row["reply_count"] == 10
        assert row["latest_reply_ts"] == "1234567999.999999"

    async def test_update_thread_reply_count(
        self,
        slack_repository: SQLiteSlackRepository,
        slack_db: SQLiteConnection,
        sample_workspace: SlackWorkspace,
    ):
        """Test updating thread reply count."""
        await slack_repository.save_workspace(sample_workspace)

        # Store thread
        await slack_db.execute(
            """
            INSERT INTO slack_threads (thread_ts, channel_id, workspace_id, reply_count)
            VALUES (?, ?, ?, ?)
            """,
            ("1234567890.123456", "C12345ABC", "T12345ABC", 5),
        )

        # Update reply count
        await slack_db.execute(
            """
            UPDATE slack_threads
            SET reply_count = ?, latest_reply_ts = ?, last_fetched_at = datetime('now')
            WHERE workspace_id = ? AND channel_id = ? AND thread_ts = ?
            """,
            (15, "1234567999.999999", "T12345ABC", "C12345ABC", "1234567890.123456"),
        )

        # Verify update
        row = await slack_db.fetch_one(
            """
            SELECT reply_count, latest_reply_ts FROM slack_threads
            WHERE workspace_id = ? AND channel_id = ? AND thread_ts = ?
            """,
            ("T12345ABC", "C12345ABC", "1234567890.123456"),
        )

        assert row["reply_count"] == 15
        assert row["latest_reply_ts"] == "1234567999.999999"


# =============================================================================
# File Tracking Tests
# =============================================================================


@pytest.mark.asyncio
class TestFileTracking:
    """Test file tracking operations."""

    async def test_store_file_metadata(
        self,
        slack_repository: SQLiteSlackRepository,
        slack_db: SQLiteConnection,
        sample_workspace: SlackWorkspace,
    ):
        """Test storing file metadata."""
        await slack_repository.save_workspace(sample_workspace)

        # Store file
        await slack_db.execute(
            """
            INSERT INTO slack_files (
                file_id, workspace_id, channel_id, user_id, filename, title,
                mimetype, filetype, size_bytes, permalink, expires_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                "F12345ABC",
                "T12345ABC",
                "C12345ABC",
                "U12345ABC",
                "document.pdf",
                "Important Document",
                "application/pdf",
                "pdf",
                1024000,
                "https://files.slack.com/files/F12345ABC",
                (datetime.utcnow() + timedelta(days=7)).isoformat(),
            ),
        )

        # Verify file was stored
        row = await slack_db.fetch_one(
            "SELECT * FROM slack_files WHERE file_id = ?", ("F12345ABC",)
        )
        assert row is not None
        assert row["filename"] == "document.pdf"
        assert row["mimetype"] == "application/pdf"
        assert row["size_bytes"] == 1024000

    async def test_get_file_by_id(
        self,
        slack_repository: SQLiteSlackRepository,
        slack_db: SQLiteConnection,
        sample_workspace: SlackWorkspace,
    ):
        """Test retrieving a file by ID."""
        await slack_repository.save_workspace(sample_workspace)

        # Store file
        await slack_db.execute(
            """
            INSERT INTO slack_files (file_id, workspace_id, filename, mimetype, size_bytes)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("F12345ABC", "T12345ABC", "image.png", "image/png", 512000),
        )

        # Retrieve file
        row = await slack_db.fetch_one(
            "SELECT * FROM slack_files WHERE file_id = ?", ("F12345ABC",)
        )

        assert row is not None
        assert row["file_id"] == "F12345ABC"
        assert row["filename"] == "image.png"
        assert row["mimetype"] == "image/png"

    async def test_check_file_expiration(
        self,
        slack_repository: SQLiteSlackRepository,
        slack_db: SQLiteConnection,
        sample_workspace: SlackWorkspace,
    ):
        """Test checking file expiration."""
        await slack_repository.save_workspace(sample_workspace)

        # Store expired file
        expired_time = (datetime.utcnow() - timedelta(days=1)).isoformat()
        await slack_db.execute(
            """
            INSERT INTO slack_files (file_id, workspace_id, filename, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            ("F_EXPIRED", "T12345ABC", "expired.pdf", expired_time),
        )

        # Store valid file
        valid_time = (datetime.utcnow() + timedelta(days=7)).isoformat()
        await slack_db.execute(
            """
            INSERT INTO slack_files (file_id, workspace_id, filename, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            ("F_VALID", "T12345ABC", "valid.pdf", valid_time),
        )

        # Query for expired files
        expired_files = await slack_db.fetch_all(
            """
            SELECT file_id FROM slack_files
            WHERE expires_at IS NOT NULL AND expires_at < datetime('now')
            """
        )

        assert len(expired_files) == 1
        assert expired_files[0]["file_id"] == "F_EXPIRED"

        # Query for valid files
        valid_files = await slack_db.fetch_all(
            """
            SELECT file_id FROM slack_files
            WHERE expires_at IS NULL OR expires_at >= datetime('now')
            """
        )

        assert len(valid_files) == 1
        assert valid_files[0]["file_id"] == "F_VALID"


# =============================================================================
# Edge Case Tests
# =============================================================================


@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and error handling."""

    async def test_workspace_with_empty_metadata(
        self,
        slack_repository: SQLiteSlackRepository,
    ):
        """Test workspace with empty metadata dict."""
        workspace = SlackWorkspace(
            workspace_id="T_EMPTY_META",
            workspace_name="Empty Metadata Workspace",
            encrypted_bot_token="token",
            bot_user_id="U12345",
            installed_by_discord_user="user123",
            scopes="scope1",
            metadata={},
        )

        await slack_repository.save_workspace(workspace)
        retrieved = await slack_repository.get_workspace("T_EMPTY_META")

        assert retrieved.metadata == {}

    async def test_workspace_with_complex_metadata(
        self,
        slack_repository: SQLiteSlackRepository,
    ):
        """Test workspace with complex nested metadata."""
        workspace = SlackWorkspace(
            workspace_id="T_COMPLEX_META",
            workspace_name="Complex Metadata Workspace",
            encrypted_bot_token="token",
            bot_user_id="U12345",
            installed_by_discord_user="user123",
            scopes="scope1",
            metadata={
                "install_version": "2.0",
                "features": ["feature1", "feature2"],
                "config": {"nested": {"deeply": "value"}},
            },
        )

        await slack_repository.save_workspace(workspace)
        retrieved = await slack_repository.get_workspace("T_COMPLEX_META")

        assert retrieved.metadata["features"] == ["feature1", "feature2"]
        assert retrieved.metadata["config"]["nested"]["deeply"] == "value"

    async def test_channel_with_all_types(
        self,
        slack_repository: SQLiteSlackRepository,
        sample_workspace: SlackWorkspace,
    ):
        """Test channels of all types."""
        await slack_repository.save_workspace(sample_workspace)

        channel_types = [
            (SlackChannelType.PUBLIC, "public"),
            (SlackChannelType.PRIVATE, "private"),
            (SlackChannelType.DM, "dm"),
            (SlackChannelType.MPIM, "mpim"),
        ]

        for i, (channel_type, name) in enumerate(channel_types):
            channel = SlackChannel(
                channel_id=f"C_TYPE_{i}",
                workspace_id="T12345ABC",
                channel_name=f"{name}-channel",
                channel_type=channel_type,
            )
            await slack_repository.save_channel(channel)

        # Verify each type
        for i, (channel_type, _) in enumerate(channel_types):
            channel = await slack_repository.get_channel(f"C_TYPE_{i}")
            assert channel.channel_type == channel_type

    async def test_user_with_null_optional_fields(
        self,
        slack_repository: SQLiteSlackRepository,
        sample_workspace: SlackWorkspace,
    ):
        """Test user with null optional fields."""
        await slack_repository.save_workspace(sample_workspace)

        user = SlackUser(
            user_id="U_MINIMAL",
            workspace_id="T12345ABC",
            display_name="minimal_user",
            # All optional fields are None/default
        )

        await slack_repository.save_user(user)
        retrieved = await slack_repository.get_user("T12345ABC", "U_MINIMAL")

        assert retrieved.real_name is None
        assert retrieved.email is None
        assert retrieved.avatar_url is None
        assert retrieved.timezone is None

    async def test_pagination(
        self,
        slack_repository: SQLiteSlackRepository,
        sample_workspace: SlackWorkspace,
    ):
        """Test pagination for list operations."""
        await slack_repository.save_workspace(sample_workspace)

        # Create 20 channels
        for i in range(20):
            channel = SlackChannel(
                channel_id=f"C{i:08d}",
                workspace_id="T12345ABC",
                channel_name=f"channel-{i:02d}",
            )
            await slack_repository.save_channel(channel)

        # Test pagination
        page1 = await slack_repository.list_channels(
            "T12345ABC", limit=10, offset=0
        )
        assert len(page1) == 10

        page2 = await slack_repository.list_channels(
            "T12345ABC", limit=10, offset=10
        )
        assert len(page2) == 10

        # Verify no overlap
        page1_ids = {c.channel_id for c in page1}
        page2_ids = {c.channel_id for c in page2}
        assert page1_ids.isdisjoint(page2_ids)

    async def test_workspace_scope_tiers(
        self,
        slack_repository: SQLiteSlackRepository,
    ):
        """Test different scope tiers."""
        # Public tier
        public_workspace = SlackWorkspace(
            workspace_id="T_PUBLIC",
            workspace_name="Public Workspace",
            encrypted_bot_token="token",
            bot_user_id="U12345",
            installed_by_discord_user="user123",
            scopes="channels:history,channels:read",
            scope_tier=SlackScopeTier.PUBLIC,
        )
        await slack_repository.save_workspace(public_workspace)

        # Full tier
        full_workspace = SlackWorkspace(
            workspace_id="T_FULL",
            workspace_name="Full Workspace",
            encrypted_bot_token="token",
            bot_user_id="U12345",
            installed_by_discord_user="user123",
            scopes="channels:history,channels:read,groups:history,groups:read",
            scope_tier=SlackScopeTier.FULL,
        )
        await slack_repository.save_workspace(full_workspace)

        public_retrieved = await slack_repository.get_workspace("T_PUBLIC")
        full_retrieved = await slack_repository.get_workspace("T_FULL")

        assert public_retrieved.scope_tier == SlackScopeTier.PUBLIC
        assert full_retrieved.scope_tier == SlackScopeTier.FULL
        assert not public_retrieved.can_access_private()
        assert full_retrieved.can_access_private()
