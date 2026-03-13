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
