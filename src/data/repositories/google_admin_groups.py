"""
Google Admin Groups repository for managing guild admin group mappings.

ADR-050: Google Workspace Admin Groups for Guild Access Control

This repository handles CRUD operations for the guild_google_admin_groups table,
which maps Discord guilds to Google Workspace admin group emails for SSO-based
access control.
"""

import logging
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime

from ..sqlite.connection import SQLiteConnection
from src.utils.time import utc_now_naive

logger = logging.getLogger(__name__)


class GoogleAdminGroupsRepository:
    """Repository for managing guild Google admin group mappings.

    This repository provides CRUD operations for the guild_google_admin_groups
    table, enabling Google Workspace group-based access control for Discord guilds.
    """

    def __init__(self, connection: SQLiteConnection):
        """Initialize the repository with a database connection.

        Args:
            connection: SQLite database connection instance
        """
        self.connection = connection

    async def get_admin_groups(self, guild_id: str) -> List[str]:
        """Get all admin group emails for a guild.

        Args:
            guild_id: Discord guild ID

        Returns:
            List of Google Workspace admin group email addresses
        """
        query = """
        SELECT google_group_email FROM guild_google_admin_groups
        WHERE guild_id = ?
        ORDER BY created_at ASC
        """

        try:
            rows = await self.connection.fetch_all(query, (guild_id,))
            return [row["google_group_email"] for row in rows]
        except Exception as e:
            logger.error(f"Failed to get admin groups for guild {guild_id}: {e}")
            raise

    async def add_admin_group(
        self,
        guild_id: str,
        google_group_email: str,
        created_by: str,
    ) -> bool:
        """Add an admin group email to a guild.

        Args:
            guild_id: Discord guild ID
            google_group_email: Google Workspace group email address
            created_by: User ID who added this mapping

        Returns:
            True if added successfully, False if already exists
        """
        # Normalize email to lowercase
        google_group_email = google_group_email.lower().strip()

        # Check if mapping already exists
        existing = await self._get_mapping(guild_id, google_group_email)
        if existing:
            logger.info(
                f"Admin group {google_group_email} already exists for guild {guild_id}"
            )
            return False

        entry_id = str(uuid.uuid4())
        created_at = utc_now_naive().isoformat()

        query = """
        INSERT INTO guild_google_admin_groups (id, guild_id, google_group_email, created_by, created_at)
        VALUES (?, ?, ?, ?, ?)
        """

        try:
            await self.connection.execute(
                query,
                (entry_id, guild_id, google_group_email, created_by, created_at),
            )
            logger.info(
                f"Added admin group {google_group_email} for guild {guild_id} by {created_by}"
            )
            return True
        except Exception as e:
            logger.error(
                f"Failed to add admin group {google_group_email} for guild {guild_id}: {e}"
            )
            raise

    async def remove_admin_group(self, guild_id: str, google_group_email: str) -> bool:
        """Remove an admin group email from a guild.

        Args:
            guild_id: Discord guild ID
            google_group_email: Google Workspace group email address to remove

        Returns:
            True if removed, False if not found
        """
        # Normalize email to lowercase
        google_group_email = google_group_email.lower().strip()

        query = """
        DELETE FROM guild_google_admin_groups
        WHERE guild_id = ? AND google_group_email = ?
        """

        try:
            cursor = await self.connection.execute(query, (guild_id, google_group_email))
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Removed admin group {google_group_email} from guild {guild_id}")
            else:
                logger.info(
                    f"Admin group {google_group_email} not found for guild {guild_id}"
                )
            return deleted
        except Exception as e:
            logger.error(
                f"Failed to remove admin group {google_group_email} from guild {guild_id}: {e}"
            )
            raise

    async def get_all_mappings(self) -> List[Dict[str, Any]]:
        """Get all guild-to-admin-group mappings for admin overview.

        Returns:
            List of mapping dictionaries containing id, guild_id, google_group_email,
            created_by, and created_at fields
        """
        query = """
        SELECT id, guild_id, google_group_email, created_by, created_at
        FROM guild_google_admin_groups
        ORDER BY guild_id ASC, created_at ASC
        """

        try:
            rows = await self.connection.fetch_all(query)
            return [
                {
                    "id": row["id"],
                    "guild_id": row["guild_id"],
                    "google_group_email": row["google_group_email"],
                    "created_by": row["created_by"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to get all admin group mappings: {e}")
            raise

    async def guild_has_admin_groups(self, guild_id: str) -> bool:
        """Check if a guild has any admin groups configured.

        Args:
            guild_id: Discord guild ID

        Returns:
            True if the guild has at least one admin group, False otherwise
        """
        query = """
        SELECT COUNT(*) as count FROM guild_google_admin_groups
        WHERE guild_id = ?
        """

        try:
            result = await self.connection.fetch_one(query, (guild_id,))
            return result["count"] > 0 if result else False
        except Exception as e:
            logger.error(
                f"Failed to check admin groups existence for guild {guild_id}: {e}"
            )
            raise

    async def get_guilds_for_group(self, google_group_email: str) -> List[str]:
        """Get all guild IDs that have a specific admin group configured.

        This is useful for determining which guilds a user has access to
        based on their Google group membership.

        Args:
            google_group_email: Google Workspace group email address

        Returns:
            List of Discord guild IDs
        """
        # Normalize email to lowercase
        google_group_email = google_group_email.lower().strip()

        query = """
        SELECT guild_id FROM guild_google_admin_groups
        WHERE google_group_email = ?
        ORDER BY created_at ASC
        """

        try:
            rows = await self.connection.fetch_all(query, (google_group_email,))
            return [row["guild_id"] for row in rows]
        except Exception as e:
            logger.error(f"Failed to get guilds for group {google_group_email}: {e}")
            raise

    async def _get_mapping(
        self, guild_id: str, google_group_email: str
    ) -> Optional[Dict[str, Any]]:
        """Get a specific guild-group mapping.

        Args:
            guild_id: Discord guild ID
            google_group_email: Google Workspace group email address

        Returns:
            Mapping dictionary if found, None otherwise
        """
        query = """
        SELECT id, guild_id, google_group_email, created_by, created_at
        FROM guild_google_admin_groups
        WHERE guild_id = ? AND google_group_email = ?
        """

        try:
            return await self.connection.fetch_one(query, (guild_id, google_group_email))
        except Exception as e:
            logger.error(
                f"Failed to get mapping for guild {guild_id}, group {google_group_email}: {e}"
            )
            raise
