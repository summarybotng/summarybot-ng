"""
SQLite implementation of Slack repository (ADR-043).
"""

import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from ..base import DatabaseConnection
from ...slack.models import (
    SlackWorkspace, SlackChannel, SlackUser,
    SlackScopeTier, SlackChannelType,
)
from .connection import SQLiteConnection

logger = logging.getLogger(__name__)


class SQLiteSlackRepository:
    """SQLite implementation of Slack repository (ADR-043)."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    # =========================================================================
    # Workspace Operations
    # =========================================================================

    async def save_workspace(self, workspace: SlackWorkspace) -> str:
        """Save or update a Slack workspace.

        Args:
            workspace: SlackWorkspace to save

        Returns:
            Workspace ID
        """
        query = """
        INSERT INTO slack_workspaces (
            workspace_id, workspace_name, workspace_domain, encrypted_bot_token,
            bot_user_id, installed_by_discord_user, installed_at, scopes,
            scope_tier, is_enterprise, enterprise_id, enabled, last_sync_at,
            metadata, linked_guild_id, linked_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(workspace_id) DO UPDATE SET
            workspace_name = excluded.workspace_name,
            workspace_domain = excluded.workspace_domain,
            encrypted_bot_token = excluded.encrypted_bot_token,
            bot_user_id = excluded.bot_user_id,
            scopes = excluded.scopes,
            scope_tier = excluded.scope_tier,
            is_enterprise = excluded.is_enterprise,
            enterprise_id = excluded.enterprise_id,
            enabled = excluded.enabled,
            last_sync_at = excluded.last_sync_at,
            metadata = excluded.metadata,
            linked_guild_id = excluded.linked_guild_id,
            linked_at = excluded.linked_at
        """

        params = (
            workspace.workspace_id,
            workspace.workspace_name,
            workspace.workspace_domain,
            workspace.encrypted_bot_token,
            workspace.bot_user_id,
            workspace.installed_by_discord_user,
            workspace.installed_at.isoformat() if workspace.installed_at else None,
            workspace.scopes,
            workspace.scope_tier.value,
            workspace.is_enterprise,
            workspace.enterprise_id,
            workspace.enabled,
            workspace.last_sync_at.isoformat() if workspace.last_sync_at else None,
            json.dumps(workspace.metadata),
            workspace.linked_guild_id,
            workspace.linked_at.isoformat() if workspace.linked_at else None,
        )

        await self.connection.execute(query, params)
        return workspace.workspace_id

    async def get_workspace(self, workspace_id: str) -> Optional[SlackWorkspace]:
        """Get a workspace by ID.

        Args:
            workspace_id: Slack workspace ID

        Returns:
            SlackWorkspace if found, None otherwise
        """
        query = "SELECT * FROM slack_workspaces WHERE workspace_id = ?"
        row = await self.connection.fetch_one(query, (workspace_id,))

        if not row:
            return None

        return self._row_to_workspace(row)

    async def get_workspace_by_guild(self, guild_id: str) -> Optional[SlackWorkspace]:
        """Get workspace linked to a Discord guild.

        Args:
            guild_id: Discord guild ID

        Returns:
            SlackWorkspace if found, None otherwise
        """
        query = "SELECT * FROM slack_workspaces WHERE linked_guild_id = ? AND enabled = TRUE"
        row = await self.connection.fetch_one(query, (guild_id,))

        if not row:
            return None

        return self._row_to_workspace(row)

    async def list_workspaces(
        self,
        enabled_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> List[SlackWorkspace]:
        """List all workspaces.

        Args:
            enabled_only: Only return enabled workspaces
            limit: Max workspaces to return
            offset: Pagination offset

        Returns:
            List of SlackWorkspace objects
        """
        where = "WHERE enabled = TRUE" if enabled_only else ""
        query = f"""
        SELECT * FROM slack_workspaces
        {where}
        ORDER BY installed_at DESC
        LIMIT ? OFFSET ?
        """

        rows = await self.connection.fetch_all(query, (limit, offset))
        return [self._row_to_workspace(row) for row in rows]

    async def delete_workspace(self, workspace_id: str) -> bool:
        """Delete a workspace (cascades to channels and users).

        Args:
            workspace_id: Slack workspace ID

        Returns:
            True if deleted, False if not found
        """
        query = "DELETE FROM slack_workspaces WHERE workspace_id = ?"
        cursor = await self.connection.execute(query, (workspace_id,))
        return cursor.rowcount > 0

    async def link_workspace_to_guild(
        self,
        workspace_id: str,
        guild_id: str,
    ) -> bool:
        """Link a Slack workspace to a Discord guild.

        Args:
            workspace_id: Slack workspace ID
            guild_id: Discord guild ID

        Returns:
            True if updated, False if workspace not found
        """
        query = """
        UPDATE slack_workspaces
        SET linked_guild_id = ?, linked_at = datetime('now')
        WHERE workspace_id = ?
        """
        cursor = await self.connection.execute(query, (guild_id, workspace_id))
        return cursor.rowcount > 0

    # =========================================================================
    # Channel Operations
    # =========================================================================

    async def save_channel(self, channel: SlackChannel) -> str:
        """Save or update a Slack channel.

        Args:
            channel: SlackChannel to save

        Returns:
            Channel ID
        """
        query = """
        INSERT INTO slack_channels (
            channel_id, workspace_id, channel_name, channel_type, is_shared,
            is_archived, is_sensitive, auto_summarize, summary_schedule,
            last_message_ts, created_at, topic, purpose, member_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(channel_id) DO UPDATE SET
            channel_name = excluded.channel_name,
            channel_type = excluded.channel_type,
            is_shared = excluded.is_shared,
            is_archived = excluded.is_archived,
            is_sensitive = excluded.is_sensitive,
            auto_summarize = excluded.auto_summarize,
            summary_schedule = excluded.summary_schedule,
            last_message_ts = excluded.last_message_ts,
            topic = excluded.topic,
            purpose = excluded.purpose,
            member_count = excluded.member_count
        """

        params = (
            channel.channel_id,
            channel.workspace_id,
            channel.channel_name,
            channel.channel_type.value,
            channel.is_shared,
            channel.is_archived,
            channel.is_sensitive,
            channel.auto_summarize,
            channel.summary_schedule,
            channel.last_message_ts,
            channel.created_at.isoformat() if channel.created_at else None,
            channel.topic,
            channel.purpose,
            channel.member_count,
        )

        await self.connection.execute(query, params)
        return channel.channel_id

    async def save_channels_batch(self, channels: List[SlackChannel]) -> int:
        """Save multiple channels efficiently.

        Args:
            channels: List of SlackChannel objects

        Returns:
            Number of channels saved
        """
        if not channels:
            return 0

        query = """
        INSERT INTO slack_channels (
            channel_id, workspace_id, channel_name, channel_type, is_shared,
            is_archived, is_sensitive, auto_summarize, summary_schedule,
            last_message_ts, created_at, topic, purpose, member_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(channel_id) DO UPDATE SET
            channel_name = excluded.channel_name,
            channel_type = excluded.channel_type,
            is_shared = excluded.is_shared,
            is_archived = excluded.is_archived,
            topic = excluded.topic,
            purpose = excluded.purpose,
            member_count = excluded.member_count
        """

        params_list = [
            (
                ch.channel_id,
                ch.workspace_id,
                ch.channel_name,
                ch.channel_type.value,
                ch.is_shared,
                ch.is_archived,
                ch.is_sensitive,
                ch.auto_summarize,
                ch.summary_schedule,
                ch.last_message_ts,
                ch.created_at.isoformat() if ch.created_at else None,
                ch.topic,
                ch.purpose,
                ch.member_count,
            )
            for ch in channels
        ]

        await self.connection.executemany(query, params_list)
        return len(channels)

    async def get_channel(self, channel_id: str) -> Optional[SlackChannel]:
        """Get a channel by ID.

        Args:
            channel_id: Slack channel ID

        Returns:
            SlackChannel if found, None otherwise
        """
        query = "SELECT * FROM slack_channels WHERE channel_id = ?"
        row = await self.connection.fetch_one(query, (channel_id,))

        if not row:
            return None

        return self._row_to_channel(row)

    async def list_channels(
        self,
        workspace_id: str,
        channel_type: Optional[SlackChannelType] = None,
        auto_summarize_only: bool = False,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[SlackChannel]:
        """List channels for a workspace.

        Args:
            workspace_id: Slack workspace ID
            channel_type: Filter by channel type
            auto_summarize_only: Only return channels with auto_summarize enabled
            include_archived: Include archived channels
            limit: Max channels to return
            offset: Pagination offset

        Returns:
            List of SlackChannel objects
        """
        conditions = ["workspace_id = ?"]
        params: List[Any] = [workspace_id]

        if channel_type:
            conditions.append("channel_type = ?")
            params.append(channel_type.value)

        if auto_summarize_only:
            conditions.append("auto_summarize = TRUE")

        if not include_archived:
            conditions.append("is_archived = FALSE")

        where_clause = " AND ".join(conditions)

        query = f"""
        SELECT * FROM slack_channels
        WHERE {where_clause}
        ORDER BY channel_name ASC
        LIMIT ? OFFSET ?
        """

        params.extend([limit, offset])
        rows = await self.connection.fetch_all(query, tuple(params))
        return [self._row_to_channel(row) for row in rows]

    async def update_channel_last_message(
        self,
        channel_id: str,
        message_ts: str,
    ) -> bool:
        """Update a channel's last message timestamp.

        Args:
            channel_id: Slack channel ID
            message_ts: Slack message timestamp

        Returns:
            True if updated, False if not found
        """
        query = """
        UPDATE slack_channels
        SET last_message_ts = ?
        WHERE channel_id = ?
        """
        cursor = await self.connection.execute(query, (message_ts, channel_id))
        return cursor.rowcount > 0

    # =========================================================================
    # User Operations
    # =========================================================================

    async def save_user(self, user: SlackUser) -> str:
        """Save or update a Slack user.

        Args:
            user: SlackUser to save

        Returns:
            User ID
        """
        query = """
        INSERT INTO slack_users (
            user_id, workspace_id, display_name, real_name, email, is_bot,
            is_admin, is_owner, avatar_url, updated_at, timezone,
            status_text, status_emoji
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(workspace_id, user_id) DO UPDATE SET
            display_name = excluded.display_name,
            real_name = excluded.real_name,
            email = excluded.email,
            is_bot = excluded.is_bot,
            is_admin = excluded.is_admin,
            is_owner = excluded.is_owner,
            avatar_url = excluded.avatar_url,
            updated_at = excluded.updated_at,
            timezone = excluded.timezone,
            status_text = excluded.status_text,
            status_emoji = excluded.status_emoji
        """

        params = (
            user.user_id,
            user.workspace_id,
            user.display_name,
            user.real_name,
            user.email,
            user.is_bot,
            user.is_admin,
            user.is_owner,
            user.avatar_url,
            user.updated_at.isoformat() if user.updated_at else None,
            user.timezone,
            user.status_text,
            user.status_emoji,
        )

        await self.connection.execute(query, params)
        return user.user_id

    async def save_users_batch(self, users: List[SlackUser]) -> int:
        """Save multiple users efficiently.

        Args:
            users: List of SlackUser objects

        Returns:
            Number of users saved
        """
        if not users:
            return 0

        query = """
        INSERT INTO slack_users (
            user_id, workspace_id, display_name, real_name, email, is_bot,
            is_admin, is_owner, avatar_url, updated_at, timezone,
            status_text, status_emoji
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(workspace_id, user_id) DO UPDATE SET
            display_name = excluded.display_name,
            real_name = excluded.real_name,
            is_bot = excluded.is_bot,
            is_admin = excluded.is_admin,
            is_owner = excluded.is_owner,
            avatar_url = excluded.avatar_url,
            updated_at = excluded.updated_at
        """

        params_list = [
            (
                u.user_id,
                u.workspace_id,
                u.display_name,
                u.real_name,
                u.email,
                u.is_bot,
                u.is_admin,
                u.is_owner,
                u.avatar_url,
                u.updated_at.isoformat() if u.updated_at else None,
                u.timezone,
                u.status_text,
                u.status_emoji,
            )
            for u in users
        ]

        await self.connection.executemany(query, params_list)
        return len(users)

    async def get_user(
        self,
        workspace_id: str,
        user_id: str,
    ) -> Optional[SlackUser]:
        """Get a user by workspace and user ID.

        Args:
            workspace_id: Slack workspace ID
            user_id: Slack user ID

        Returns:
            SlackUser if found, None otherwise
        """
        query = "SELECT * FROM slack_users WHERE workspace_id = ? AND user_id = ?"
        row = await self.connection.fetch_one(query, (workspace_id, user_id))

        if not row:
            return None

        return self._row_to_user(row)

    async def list_users(
        self,
        workspace_id: str,
        include_bots: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> List[SlackUser]:
        """List users for a workspace.

        Args:
            workspace_id: Slack workspace ID
            include_bots: Include bot users
            limit: Max users to return
            offset: Pagination offset

        Returns:
            List of SlackUser objects
        """
        conditions = ["workspace_id = ?"]
        params: List[Any] = [workspace_id]

        if not include_bots:
            conditions.append("is_bot = FALSE")

        where_clause = " AND ".join(conditions)

        query = f"""
        SELECT * FROM slack_users
        WHERE {where_clause}
        ORDER BY display_name ASC
        LIMIT ? OFFSET ?
        """

        params.extend([limit, offset])
        rows = await self.connection.fetch_all(query, tuple(params))
        return [self._row_to_user(row) for row in rows]

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _row_to_workspace(self, row: Dict[str, Any]) -> SlackWorkspace:
        """Convert database row to SlackWorkspace."""
        return SlackWorkspace(
            workspace_id=row["workspace_id"],
            workspace_name=row["workspace_name"],
            workspace_domain=row.get("workspace_domain"),
            encrypted_bot_token=row["encrypted_bot_token"],
            bot_user_id=row["bot_user_id"],
            installed_by_discord_user=row["installed_by_discord_user"],
            installed_at=datetime.fromisoformat(row["installed_at"]) if row.get("installed_at") else None,
            scopes=row.get("scopes", ""),
            scope_tier=SlackScopeTier(row.get("scope_tier", "public")),
            is_enterprise=bool(row.get("is_enterprise")),
            enterprise_id=row.get("enterprise_id"),
            enabled=bool(row.get("enabled", True)),
            last_sync_at=datetime.fromisoformat(row["last_sync_at"]) if row.get("last_sync_at") else None,
            metadata=json.loads(row.get("metadata") or "{}"),
            linked_guild_id=row.get("linked_guild_id"),
            linked_at=datetime.fromisoformat(row["linked_at"]) if row.get("linked_at") else None,
        )

    def _row_to_channel(self, row: Dict[str, Any]) -> SlackChannel:
        """Convert database row to SlackChannel."""
        return SlackChannel(
            channel_id=row["channel_id"],
            workspace_id=row["workspace_id"],
            channel_name=row["channel_name"],
            channel_type=SlackChannelType(row.get("channel_type", "public_channel")),
            is_shared=bool(row.get("is_shared")),
            is_archived=bool(row.get("is_archived")),
            is_sensitive=bool(row.get("is_sensitive")),
            auto_summarize=bool(row.get("auto_summarize")),
            summary_schedule=row.get("summary_schedule"),
            last_message_ts=row.get("last_message_ts"),
            created_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else None,
            topic=row.get("topic"),
            purpose=row.get("purpose"),
            member_count=row.get("member_count", 0),
        )

    def _row_to_user(self, row: Dict[str, Any]) -> SlackUser:
        """Convert database row to SlackUser."""
        return SlackUser(
            user_id=row["user_id"],
            workspace_id=row["workspace_id"],
            display_name=row["display_name"],
            real_name=row.get("real_name"),
            email=row.get("email"),
            is_bot=bool(row.get("is_bot")),
            is_admin=bool(row.get("is_admin")),
            is_owner=bool(row.get("is_owner")),
            avatar_url=row.get("avatar_url"),
            updated_at=datetime.fromisoformat(row["updated_at"]) if row.get("updated_at") else None,
            timezone=row.get("timezone"),
            status_text=row.get("status_text"),
            status_emoji=row.get("status_emoji"),
        )
