"""
SQLite implementation of configuration repository.
"""

import json
import logging
from typing import List, Optional, Dict, Any

from ..base import ConfigRepository
from ...config.settings import GuildConfig, PermissionSettings, SummaryOptions, SummaryLength
from ...utils.encryption import encrypt_value, decrypt_value
from .connection import SQLiteConnection

logger = logging.getLogger(__name__)


class SQLiteConfigRepository(ConfigRepository):
    """SQLite implementation of configuration repository."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    async def save_guild_config(self, config: GuildConfig) -> None:
        """Save or update a guild configuration."""
        query = """
        INSERT OR REPLACE INTO guild_configs (
            guild_id, enabled_channels, excluded_channels,
            default_summary_options, permission_settings,
            webhook_enabled, webhook_secret
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            config.guild_id,
            json.dumps(config.enabled_channels),
            json.dumps(config.excluded_channels),
            json.dumps(config.default_summary_options.to_dict()),
            json.dumps(config.permission_settings.to_dict()),
            config.webhook_enabled,
            encrypt_value(config.webhook_secret)
        )

        await self.connection.execute(query, params)

    async def get_guild_config(self, guild_id: str) -> Optional[GuildConfig]:
        """Retrieve configuration for a specific guild."""
        query = "SELECT * FROM guild_configs WHERE guild_id = ?"
        row = await self.connection.fetch_one(query, (guild_id,))

        if not row:
            return None

        return self._row_to_guild_config(row)

    async def delete_guild_config(self, guild_id: str) -> bool:
        """Delete a guild configuration."""
        query = "DELETE FROM guild_configs WHERE guild_id = ?"
        cursor = await self.connection.execute(query, (guild_id,))
        return cursor.rowcount > 0

    async def get_all_guild_configs(self) -> List[GuildConfig]:
        """Retrieve all guild configurations."""
        query = "SELECT * FROM guild_configs"
        rows = await self.connection.fetch_all(query)
        return [self._row_to_guild_config(row) for row in rows]

    def _row_to_guild_config(self, row: Dict[str, Any]) -> GuildConfig:
        """Convert database row to GuildConfig object."""
        options_data = json.loads(row['default_summary_options'])
        permission_data = json.loads(row['permission_settings'])

        # Convert summary options
        options_data['summary_length'] = SummaryLength(options_data['summary_length'])

        # Handle legacy field name: claude_model -> summarization_model
        if 'claude_model' in options_data:
            options_data['summarization_model'] = options_data.pop('claude_model')

        # Filter out unknown fields (e.g., deprecated 'perspective' field)
        from dataclasses import fields as dataclass_fields
        valid_fields = {f.name for f in dataclass_fields(SummaryOptions)}
        options_data = {k: v for k, v in options_data.items() if k in valid_fields}

        summary_options = SummaryOptions(**options_data)

        # Convert permission settings
        permission_settings = PermissionSettings(**permission_data)

        return GuildConfig(
            guild_id=row['guild_id'],
            enabled_channels=json.loads(row['enabled_channels']),
            excluded_channels=json.loads(row['excluded_channels']),
            default_summary_options=summary_options,
            permission_settings=permission_settings,
            webhook_enabled=bool(row['webhook_enabled']),
            webhook_secret=decrypt_value(row['webhook_secret'])
        )

    # ADR-046: Channel sensitivity configuration (Phase 2)

    async def get_sensitive_channels(self, guild_id: str) -> List[str]:
        """Get list of sensitive channel IDs for a guild.

        ADR-046: Returns channel IDs that are marked as sensitive.
        These channels require admin access to view summaries.

        Args:
            guild_id: Discord guild ID

        Returns:
            List of sensitive channel IDs
        """
        query = "SELECT sensitive_channels FROM guild_configs WHERE guild_id = ?"
        row = await self.connection.fetch_one(query, (guild_id,))

        if not row or not row.get('sensitive_channels'):
            return []

        try:
            return json.loads(row['sensitive_channels'])
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Invalid sensitive_channels JSON for guild {guild_id}")
            return []

    async def set_sensitive_channels(self, guild_id: str, channel_ids: List[str]) -> None:
        """Set sensitive channel IDs for a guild.

        ADR-046: Mark channels as sensitive so their summaries require admin access.

        Args:
            guild_id: Discord guild ID
            channel_ids: List of channel IDs to mark as sensitive
        """
        query = """
        UPDATE guild_configs
        SET sensitive_channels = ?
        WHERE guild_id = ?
        """
        await self.connection.execute(query, (json.dumps(channel_ids), guild_id))
        logger.info(f"Updated sensitive channels for guild {guild_id}: {len(channel_ids)} channels")

    async def get_channel_sensitivity_config(self, guild_id: str) -> Dict[str, Any]:
        """Get full sensitivity config including auto_mark setting.

        ADR-046: Returns complete sensitivity configuration for a guild.

        Args:
            guild_id: Discord guild ID

        Returns:
            Dict with sensitive_channels, sensitive_categories, and auto_mark_private_sensitive
        """
        query = """
        SELECT sensitive_channels, sensitive_categories, auto_mark_private_sensitive
        FROM guild_configs
        WHERE guild_id = ?
        """
        row = await self.connection.fetch_one(query, (guild_id,))

        if not row:
            return {
                "sensitive_channels": [],
                "sensitive_categories": [],
                "auto_mark_private_sensitive": True,
            }

        def safe_json_load(value: Any, default: List) -> List:
            """Safely parse JSON, returning default on failure."""
            if not value:
                return default
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return default

        return {
            "sensitive_channels": safe_json_load(row.get('sensitive_channels'), []),
            "sensitive_categories": safe_json_load(row.get('sensitive_categories'), []),
            "auto_mark_private_sensitive": bool(row.get('auto_mark_private_sensitive', True)),
        }

    async def set_channel_sensitivity_config(
        self,
        guild_id: str,
        sensitive_channels: Optional[List[str]] = None,
        sensitive_categories: Optional[List[str]] = None,
        auto_mark_private_sensitive: Optional[bool] = None,
    ) -> None:
        """Set full sensitivity config for a guild.

        ADR-046: Update sensitivity configuration. Only updates provided fields.

        Args:
            guild_id: Discord guild ID
            sensitive_channels: List of sensitive channel IDs (optional)
            sensitive_categories: List of sensitive category IDs (optional)
            auto_mark_private_sensitive: Whether to auto-mark private channels (optional)
        """
        updates = []
        params: List[Any] = []

        if sensitive_channels is not None:
            updates.append("sensitive_channels = ?")
            params.append(json.dumps(sensitive_channels))

        if sensitive_categories is not None:
            updates.append("sensitive_categories = ?")
            params.append(json.dumps(sensitive_categories))

        if auto_mark_private_sensitive is not None:
            updates.append("auto_mark_private_sensitive = ?")
            params.append(auto_mark_private_sensitive)

        if not updates:
            return

        params.append(guild_id)
        query = f"UPDATE guild_configs SET {', '.join(updates)} WHERE guild_id = ?"
        await self.connection.execute(query, tuple(params))
        logger.info(f"Updated sensitivity config for guild {guild_id}")

    async def is_channel_sensitive(self, guild_id: str, channel_id: str) -> bool:
        """Check if a specific channel is marked as sensitive.

        ADR-046: Quick check for channel sensitivity.

        Args:
            guild_id: Discord guild ID
            channel_id: Channel ID to check

        Returns:
            True if channel is in the sensitive list
        """
        sensitive_channels = await self.get_sensitive_channels(guild_id)
        return channel_id in sensitive_channels

    async def add_sensitive_channel(self, guild_id: str, channel_id: str) -> None:
        """Add a channel to the sensitive list.

        ADR-046: Mark a single channel as sensitive.

        Args:
            guild_id: Discord guild ID
            channel_id: Channel ID to add
        """
        current = await self.get_sensitive_channels(guild_id)
        if channel_id not in current:
            current.append(channel_id)
            await self.set_sensitive_channels(guild_id, current)

    async def remove_sensitive_channel(self, guild_id: str, channel_id: str) -> None:
        """Remove a channel from the sensitive list.

        ADR-046: Unmark a channel as sensitive.

        Args:
            guild_id: Discord guild ID
            channel_id: Channel ID to remove
        """
        current = await self.get_sensitive_channels(guild_id)
        if channel_id in current:
            current.remove(channel_id)
            await self.set_sensitive_channels(guild_id, current)
