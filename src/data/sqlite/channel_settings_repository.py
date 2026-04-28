"""
SQLite Channel Settings Repository (ADR-073)

Persistent storage for channel enable/disable state, locked channel detection,
and audit trail for locked channel overrides.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from .connection import SQLiteConnection

logger = logging.getLogger(__name__)


@dataclass
class ChannelSettings:
    """Channel settings for summarization control."""
    guild_id: str
    channel_id: str
    platform: str = "discord"
    enabled: bool = True
    is_locked: bool = False
    locked_override: bool = False
    locked_override_by: Optional[str] = None
    locked_override_at: Optional[datetime] = None
    wiki_visible: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SQLiteChannelSettingsRepository:
    """Repository for channel settings."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    async def get_settings(
        self,
        guild_id: str,
        channel_id: str,
        platform: str = "discord",
    ) -> Optional[ChannelSettings]:
        """Get settings for a specific channel."""
        query = """
            SELECT guild_id, channel_id, platform, enabled, is_locked,
                   locked_override, locked_override_by, locked_override_at,
                   wiki_visible, created_at, updated_at
            FROM channel_settings
            WHERE guild_id = ? AND channel_id = ? AND platform = ?
        """
        rows = await self.connection.fetch_all(query, (guild_id, channel_id, platform))
        if not rows:
            return None
        return self._row_to_settings(rows[0])

    async def get_guild_settings(
        self,
        guild_id: str,
        platform: str = "discord",
    ) -> List[ChannelSettings]:
        """Get all channel settings for a guild."""
        query = """
            SELECT guild_id, channel_id, platform, enabled, is_locked,
                   locked_override, locked_override_by, locked_override_at,
                   wiki_visible, created_at, updated_at
            FROM channel_settings
            WHERE guild_id = ? AND platform = ?
            ORDER BY channel_id
        """
        try:
            rows = await self.connection.fetch_all(query, (guild_id, platform))
            return [self._row_to_settings(row) for row in rows]
        except Exception as e:
            # Table might not exist yet (migration not run)
            logger.warning(f"Failed to get channel settings: {e}")
            return []

    async def get_enabled_channel_ids(
        self,
        guild_id: str,
        platform: str = "discord",
    ) -> List[str]:
        """Get list of explicitly enabled channel IDs."""
        query = """
            SELECT channel_id
            FROM channel_settings
            WHERE guild_id = ? AND platform = ? AND enabled = 1
        """
        rows = await self.connection.fetch_all(query, (guild_id, platform))
        return [row[0] for row in rows]

    async def get_disabled_channel_ids(
        self,
        guild_id: str,
        platform: str = "discord",
    ) -> List[str]:
        """Get list of explicitly disabled channel IDs."""
        query = """
            SELECT channel_id
            FROM channel_settings
            WHERE guild_id = ? AND platform = ? AND enabled = 0
        """
        rows = await self.connection.fetch_all(query, (guild_id, platform))
        return [row[0] for row in rows]

    async def get_locked_channel_ids(
        self,
        guild_id: str,
        platform: str = "discord",
    ) -> List[str]:
        """Get list of locked channel IDs."""
        query = """
            SELECT channel_id
            FROM channel_settings
            WHERE guild_id = ? AND platform = ? AND is_locked = 1
        """
        rows = await self.connection.fetch_all(query, (guild_id, platform))
        return [row[0] for row in rows]

    async def upsert_settings(self, settings: ChannelSettings) -> None:
        """Create or update channel settings."""
        now = datetime.utcnow().isoformat()
        query = """
            INSERT INTO channel_settings
                (guild_id, channel_id, platform, enabled, is_locked,
                 locked_override, locked_override_by, locked_override_at,
                 wiki_visible, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (guild_id, channel_id, platform) DO UPDATE SET
                enabled = excluded.enabled,
                is_locked = excluded.is_locked,
                locked_override = excluded.locked_override,
                locked_override_by = excluded.locked_override_by,
                locked_override_at = excluded.locked_override_at,
                wiki_visible = excluded.wiki_visible,
                updated_at = excluded.updated_at
        """
        params = (
            settings.guild_id,
            settings.channel_id,
            settings.platform,
            settings.enabled,
            settings.is_locked,
            settings.locked_override,
            settings.locked_override_by,
            settings.locked_override_at.isoformat() if settings.locked_override_at else None,
            settings.wiki_visible,
            settings.created_at.isoformat() if settings.created_at else now,
            now,
        )
        await self.connection.execute(query, params)

    async def bulk_upsert_settings(self, settings_list: List[ChannelSettings]) -> None:
        """Bulk create or update channel settings."""
        if not settings_list:
            return
        now = datetime.utcnow().isoformat()
        query = """
            INSERT INTO channel_settings
                (guild_id, channel_id, platform, enabled, is_locked,
                 locked_override, locked_override_by, locked_override_at,
                 wiki_visible, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (guild_id, channel_id, platform) DO UPDATE SET
                enabled = excluded.enabled,
                is_locked = excluded.is_locked,
                locked_override = excluded.locked_override,
                locked_override_by = excluded.locked_override_by,
                locked_override_at = excluded.locked_override_at,
                wiki_visible = excluded.wiki_visible,
                updated_at = excluded.updated_at
        """
        params_list = [
            (
                s.guild_id,
                s.channel_id,
                s.platform,
                s.enabled,
                s.is_locked,
                s.locked_override,
                s.locked_override_by,
                s.locked_override_at.isoformat() if s.locked_override_at else None,
                s.wiki_visible,
                s.created_at.isoformat() if s.created_at else now,
                now,
            )
            for s in settings_list
        ]
        try:
            await self.connection.executemany(query, params_list)
        except Exception as e:
            # Table might not exist yet (migration not run)
            logger.warning(f"Failed to save channel settings: {e}")

    async def set_enabled(
        self,
        guild_id: str,
        channel_id: str,
        enabled: bool,
        platform: str = "discord",
    ) -> None:
        """Set enabled state for a channel."""
        now = datetime.utcnow().isoformat()
        query = """
            INSERT INTO channel_settings (guild_id, channel_id, platform, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (guild_id, channel_id, platform) DO UPDATE SET
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
        """
        await self.connection.execute(query, (guild_id, channel_id, platform, enabled, now, now))

    async def set_locked_override(
        self,
        guild_id: str,
        channel_id: str,
        override: bool,
        override_by: str,
        platform: str = "discord",
    ) -> None:
        """Set locked channel override (enables summarization on locked channel)."""
        now = datetime.utcnow()
        query = """
            UPDATE channel_settings
            SET locked_override = ?,
                locked_override_by = ?,
                locked_override_at = ?,
                enabled = ?,
                updated_at = ?
            WHERE guild_id = ? AND channel_id = ? AND platform = ?
        """
        params = (
            override,
            override_by if override else None,
            now.isoformat() if override else None,
            override,  # Enable if override, disable if removing override
            now.isoformat(),
            guild_id,
            channel_id,
            platform,
        )
        await self.connection.execute(query, params)

    async def delete_settings(
        self,
        guild_id: str,
        channel_id: str,
        platform: str = "discord",
    ) -> None:
        """Delete channel settings."""
        query = """
            DELETE FROM channel_settings
            WHERE guild_id = ? AND channel_id = ? AND platform = ?
        """
        await self.connection.execute(query, (guild_id, channel_id, platform))

    def _row_to_settings(self, row) -> ChannelSettings:
        """Convert database row to ChannelSettings."""
        return ChannelSettings(
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            platform=row["platform"],
            enabled=bool(row["enabled"]),
            is_locked=bool(row["is_locked"]),
            locked_override=bool(row["locked_override"]),
            locked_override_by=row["locked_override_by"],
            locked_override_at=datetime.fromisoformat(row["locked_override_at"]) if row["locked_override_at"] else None,
            wiki_visible=bool(row["wiki_visible"]),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )
