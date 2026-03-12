"""
Guild prompt configuration repository for external prompt hosting.

This module provides CRUD operations for guild-specific prompt configurations
including repository settings, authentication, and sync status tracking.
"""

import logging
from typing import Optional, List
from datetime import datetime
from cryptography.fernet import Fernet
import json

from .models import GuildPromptConfig
from ..data.sqlite import SQLiteConnection
from src.utils.time import utc_now_naive

logger = logging.getLogger(__name__)


class GuildPromptConfigStore:
    """Repository for managing guild prompt configurations."""

    def __init__(self, connection: SQLiteConnection, encryption_key: Optional[bytes] = None):
        """
        Initialize guild config store.

        Args:
            connection: Database connection
            encryption_key: Fernet encryption key for private repo tokens.
                          If None, generates a new key (not recommended for production).
        """
        self.connection = connection

        # Initialize encryption for private repo tokens
        if encryption_key:
            self.cipher = Fernet(encryption_key)
        else:
            # Generate new key (warning: tokens won't persist across restarts)
            logger.warning("No encryption key provided - generating ephemeral key")
            self.cipher = Fernet(Fernet.generate_key())

    async def get_config(self, guild_id: str) -> Optional[GuildPromptConfig]:
        """
        Get prompt configuration for a guild.

        Args:
            guild_id: Discord guild ID

        Returns:
            Guild configuration or None if not found
        """
        query = "SELECT * FROM guild_prompt_configs WHERE guild_id = ?"
        row = await self.connection.fetch_one(query, (guild_id,))

        if not row:
            return None

        # Decrypt auth token if present
        auth_token = None
        if row['auth_token']:
            try:
                auth_token = self._decrypt_token(row['auth_token'])
            except Exception as e:
                logger.error(f"Failed to decrypt auth token for guild {guild_id}: {e}")

        # Parse validation errors if present
        validation_errors = None
        if row['validation_errors']:
            try:
                validation_errors = json.loads(row['validation_errors'])
            except Exception as e:
                logger.error(f"Failed to parse validation errors for guild {guild_id}: {e}")

        return GuildPromptConfig(
            guild_id=row['guild_id'],
            repo_url=row['repo_url'],
            branch=row['branch'] or 'main',
            enabled=bool(row['enabled']),
            auth_token=auth_token,
            last_sync=datetime.fromisoformat(row['last_sync']) if row['last_sync'] else None,
            last_sync_status=row['last_sync_status'] or 'never',
            validation_errors=validation_errors,
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else utc_now_naive(),
            updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else utc_now_naive()
        )

    async def set_config(self, config: GuildPromptConfig) -> None:
        """
        Save or update guild prompt configuration.

        Args:
            config: Guild configuration to save
        """
        # Encrypt auth token if present
        encrypted_token = None
        if config.auth_token:
            encrypted_token = self._encrypt_token(config.auth_token)

        # Serialize validation errors if present
        validation_errors_json = None
        if config.validation_errors:
            validation_errors_json = json.dumps(config.validation_errors)

        query = """
        INSERT INTO guild_prompt_configs (
            guild_id, repo_url, branch, enabled, auth_token,
            last_sync, last_sync_status, validation_errors,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            repo_url = excluded.repo_url,
            branch = excluded.branch,
            enabled = excluded.enabled,
            auth_token = excluded.auth_token,
            last_sync = excluded.last_sync,
            last_sync_status = excluded.last_sync_status,
            validation_errors = excluded.validation_errors,
            updated_at = excluded.updated_at
        """

        params = (
            config.guild_id,
            config.repo_url,
            config.branch,
            1 if config.enabled else 0,
            encrypted_token,
            config.last_sync.isoformat() if config.last_sync else None,
            config.last_sync_status,
            validation_errors_json,
            config.created_at.isoformat() if config.created_at else utc_now_naive().isoformat(),
            utc_now_naive().isoformat()  # Always update updated_at
        )

        await self.connection.execute(query, params)
        logger.info(f"Saved prompt config for guild {config.guild_id}: {config.repo_url}")

    async def delete_config(self, guild_id: str) -> bool:
        """
        Delete guild prompt configuration.

        Args:
            guild_id: Discord guild ID

        Returns:
            True if config was deleted, False if not found
        """
        query = "DELETE FROM guild_prompt_configs WHERE guild_id = ?"
        cursor = await self.connection.execute(query, (guild_id,))

        deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"Deleted prompt config for guild {guild_id}")

        return deleted

    async def update_sync_status(
        self,
        guild_id: str,
        status: str,
        validation_errors: Optional[List[str]] = None
    ) -> None:
        """
        Update sync status for a guild.

        Args:
            guild_id: Discord guild ID
            status: Sync status (success, failed, rate_limited, etc.)
            validation_errors: Optional list of validation errors
        """
        validation_errors_json = None
        if validation_errors:
            validation_errors_json = json.dumps(validation_errors)

        query = """
        UPDATE guild_prompt_configs
        SET last_sync = ?,
            last_sync_status = ?,
            validation_errors = ?,
            updated_at = ?
        WHERE guild_id = ?
        """

        params = (
            utc_now_naive().isoformat(),
            status,
            validation_errors_json,
            utc_now_naive().isoformat(),
            guild_id
        )

        await self.connection.execute(query, params)
        logger.info(f"Updated sync status for guild {guild_id}: {status}")

    async def get_all_enabled_configs(self) -> List[GuildPromptConfig]:
        """
        Get all enabled guild configurations.

        Returns:
            List of enabled guild configurations
        """
        query = "SELECT * FROM guild_prompt_configs WHERE enabled = 1"
        rows = await self.connection.fetch_all(query)

        configs = []
        for row in rows:
            try:
                # Decrypt auth token if present
                auth_token = None
                if row['auth_token']:
                    auth_token = self._decrypt_token(row['auth_token'])

                # Parse validation errors if present
                validation_errors = None
                if row['validation_errors']:
                    validation_errors = json.loads(row['validation_errors'])

                config = GuildPromptConfig(
                    guild_id=row['guild_id'],
                    repo_url=row['repo_url'],
                    branch=row['branch'] or 'main',
                    enabled=bool(row['enabled']),
                    auth_token=auth_token,
                    last_sync=datetime.fromisoformat(row['last_sync']) if row['last_sync'] else None,
                    last_sync_status=row['last_sync_status'] or 'never',
                    validation_errors=validation_errors,
                    created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else utc_now_naive(),
                    updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else utc_now_naive()
                )
                configs.append(config)
            except Exception as e:
                logger.error(f"Failed to parse config for guild {row['guild_id']}: {e}")

        return configs

    def _encrypt_token(self, token: str) -> str:
        """
        Encrypt authentication token using Fernet.

        Args:
            token: Plain text token

        Returns:
            Encrypted token (base64 encoded)
        """
        return self.cipher.encrypt(token.encode()).decode()

    def _decrypt_token(self, encrypted_token: str) -> str:
        """
        Decrypt authentication token.

        Args:
            encrypted_token: Encrypted token (base64 encoded)

        Returns:
            Plain text token
        """
        return self.cipher.decrypt(encrypted_token.encode()).decode()

    @property
    def has_custom_prompts(self) -> bool:
        """
        Check if any guilds have custom prompts configured.

        Returns:
            True if at least one guild has custom prompts enabled
        """
        query = "SELECT COUNT(*) as count FROM guild_prompt_configs WHERE enabled = 1 AND repo_url IS NOT NULL"
        row = self.connection.fetch_one(query)
        return row and row['count'] > 0
