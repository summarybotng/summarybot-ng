"""
SQLite repository for Confluence settings and publication tracking (ADR-099).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any

from .connection import SQLiteConnection
from src.utils.time import utc_now_naive
from src.utils.encryption import encrypt_value, decrypt_value

logger = logging.getLogger(__name__)


@dataclass
class ConfluenceSettings:
    """Per-guild Confluence configuration."""
    guild_id: str
    enabled: bool = False
    base_url: str = ""  # e.g., https://company.atlassian.net
    space_key: str = ""  # e.g., TEAM
    parent_page_id: Optional[str] = None
    email: str = ""  # Service account email
    api_token: str = ""  # API token (stored encrypted)
    page_title_template: str = "{title}"
    configured_by: Optional[str] = None
    configured_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def is_configured(self) -> bool:
        """Check if Confluence is properly configured for this guild."""
        return bool(
            self.enabled
            and self.base_url
            and self.space_key
            and self.email
            and self.api_token
        )

    def to_dict(self, include_token: bool = False) -> Dict[str, Any]:
        """Convert to dictionary.

        Args:
            include_token: If False, excludes the API token for security
        """
        result = {
            "guild_id": self.guild_id,
            "enabled": self.enabled,
            "base_url": self.base_url,
            "space_key": self.space_key,
            "parent_page_id": self.parent_page_id,
            "email": self.email,
            "page_title_template": self.page_title_template,
            "configured_by": self.configured_by,
            "configured_at": self.configured_at.isoformat() if self.configured_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_configured": self.is_configured(),
        }
        if include_token:
            result["api_token"] = self.api_token
        return result


@dataclass
class ConfluencePublication:
    """Represents a summary published to Confluence."""
    id: str
    summary_id: str
    guild_id: str
    page_id: str
    page_url: str
    page_version: int = 1
    published_at: datetime = field(default_factory=utc_now_naive)
    published_by: str = ""
    last_updated_at: Optional[datetime] = None
    status: str = "published"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "summary_id": self.summary_id,
            "guild_id": self.guild_id,
            "page_id": self.page_id,
            "page_url": self.page_url,
            "page_version": self.page_version,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "published_by": self.published_by,
            "last_updated_at": self.last_updated_at.isoformat() if self.last_updated_at else None,
            "status": self.status,
        }


class SQLiteConfluenceRepository:
    """SQLite implementation of Confluence publication repository (ADR-099)."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    async def get_by_summary(self, summary_id: str) -> Optional[ConfluencePublication]:
        """Get publication record for a summary.

        Args:
            summary_id: Stored summary ID

        Returns:
            ConfluencePublication or None if not published
        """
        query = "SELECT * FROM confluence_publications WHERE summary_id = ?"
        row = await self.connection.fetch_one(query, (summary_id,))
        if not row:
            return None
        return self._row_to_publication(row)

    async def get_by_page_id(self, page_id: str) -> Optional[ConfluencePublication]:
        """Get publication record by Confluence page ID.

        Args:
            page_id: Confluence page ID

        Returns:
            ConfluencePublication or None if not found
        """
        query = "SELECT * FROM confluence_publications WHERE page_id = ?"
        row = await self.connection.fetch_one(query, (page_id,))
        if not row:
            return None
        return self._row_to_publication(row)

    async def get(self, publication_id: str) -> Optional[ConfluencePublication]:
        """Get publication by ID.

        Args:
            publication_id: Publication record ID

        Returns:
            ConfluencePublication or None if not found
        """
        query = "SELECT * FROM confluence_publications WHERE id = ?"
        row = await self.connection.fetch_one(query, (publication_id,))
        if not row:
            return None
        return self._row_to_publication(row)

    async def save(self, publication: ConfluencePublication) -> str:
        """Save a new publication record.

        Args:
            publication: ConfluencePublication to save

        Returns:
            Publication ID
        """
        query = """
        INSERT INTO confluence_publications (
            id, summary_id, guild_id, page_id, page_url,
            page_version, published_at, published_by, last_updated_at, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            publication.id,
            publication.summary_id,
            publication.guild_id,
            publication.page_id,
            publication.page_url,
            publication.page_version,
            publication.published_at.isoformat() if publication.published_at else utc_now_naive().isoformat(),
            publication.published_by,
            publication.last_updated_at.isoformat() if publication.last_updated_at else None,
            publication.status,
        )
        await self.connection.execute(query, params)
        logger.info(f"Saved Confluence publication: {publication.id} for summary {publication.summary_id}")
        return publication.id

    async def update_version(
        self,
        publication_id: str,
        new_version: int,
        page_url: Optional[str] = None,
    ) -> bool:
        """Update the page version after a republish.

        Args:
            publication_id: Publication record ID
            new_version: New Confluence page version
            page_url: Updated page URL (optional)

        Returns:
            True if updated, False if not found
        """
        now = utc_now_naive().isoformat()
        if page_url:
            query = """
            UPDATE confluence_publications
            SET page_version = ?, last_updated_at = ?, page_url = ?
            WHERE id = ?
            """
            params = (new_version, now, page_url, publication_id)
        else:
            query = """
            UPDATE confluence_publications
            SET page_version = ?, last_updated_at = ?
            WHERE id = ?
            """
            params = (new_version, now, publication_id)

        cursor = await self.connection.execute(query, params)
        updated = cursor.rowcount > 0
        if updated:
            logger.info(f"Updated Confluence publication {publication_id} to version {new_version}")
        return updated

    async def delete(self, publication_id: str) -> bool:
        """Delete a publication record.

        Args:
            publication_id: Publication record ID

        Returns:
            True if deleted, False if not found
        """
        query = "DELETE FROM confluence_publications WHERE id = ?"
        cursor = await self.connection.execute(query, (publication_id,))
        return cursor.rowcount > 0

    async def find_by_guild(
        self,
        guild_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ConfluencePublication]:
        """Find all publications for a guild.

        Args:
            guild_id: Discord guild ID
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of ConfluencePublication records
        """
        query = """
        SELECT * FROM confluence_publications
        WHERE guild_id = ?
        ORDER BY published_at DESC
        LIMIT ? OFFSET ?
        """
        rows = await self.connection.fetch_all(query, (guild_id, limit, offset))
        return [self._row_to_publication(row) for row in rows]

    def _row_to_publication(self, row: Dict[str, Any]) -> ConfluencePublication:
        """Convert database row to ConfluencePublication."""
        return ConfluencePublication(
            id=row["id"],
            summary_id=row["summary_id"],
            guild_id=row["guild_id"],
            page_id=row["page_id"],
            page_url=row["page_url"],
            page_version=row.get("page_version", 1),
            published_at=datetime.fromisoformat(row["published_at"]) if row.get("published_at") else utc_now_naive(),
            published_by=row.get("published_by", ""),
            last_updated_at=datetime.fromisoformat(row["last_updated_at"]) if row.get("last_updated_at") else None,
            status=row.get("status", "published"),
        )

    # ==========================================================================
    # Confluence Settings Methods (ADR-099)
    # ==========================================================================

    async def get_settings(self, guild_id: str) -> Optional[ConfluenceSettings]:
        """Get Confluence settings for a guild.

        Args:
            guild_id: Discord guild ID

        Returns:
            ConfluenceSettings or None if not configured
        """
        query = "SELECT * FROM confluence_settings WHERE guild_id = ?"
        row = await self.connection.fetch_one(query, (guild_id,))
        if not row:
            return None
        return self._row_to_settings(row)

    async def save_settings(self, settings: ConfluenceSettings) -> bool:
        """Save or update Confluence settings for a guild.

        Args:
            settings: ConfluenceSettings to save

        Returns:
            True if saved successfully
        """
        now = utc_now_naive().isoformat()

        # Encrypt the API token before storing
        encrypted_token = encrypt_value(settings.api_token) if settings.api_token else None

        query = """
        INSERT INTO confluence_settings (
            guild_id, enabled, base_url, space_key, parent_page_id,
            email, api_token_encrypted, page_title_template,
            configured_by, configured_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            enabled = excluded.enabled,
            base_url = excluded.base_url,
            space_key = excluded.space_key,
            parent_page_id = excluded.parent_page_id,
            email = excluded.email,
            api_token_encrypted = COALESCE(excluded.api_token_encrypted, api_token_encrypted),
            page_title_template = excluded.page_title_template,
            updated_at = excluded.updated_at
        """
        params = (
            settings.guild_id,
            1 if settings.enabled else 0,
            settings.base_url,
            settings.space_key,
            settings.parent_page_id,
            settings.email,
            encrypted_token,
            settings.page_title_template,
            settings.configured_by,
            settings.configured_at.isoformat() if settings.configured_at else now,
            now,
        )

        try:
            await self.connection.execute(query, params)
            logger.info(f"Saved Confluence settings for guild {settings.guild_id}")
            return True
        except Exception as e:
            logger.exception(f"Failed to save Confluence settings: {e}")
            return False

    async def delete_settings(self, guild_id: str) -> bool:
        """Delete Confluence settings for a guild.

        Args:
            guild_id: Discord guild ID

        Returns:
            True if deleted, False if not found
        """
        query = "DELETE FROM confluence_settings WHERE guild_id = ?"
        cursor = await self.connection.execute(query, (guild_id,))
        return cursor.rowcount > 0

    async def update_settings_partial(
        self,
        guild_id: str,
        enabled: Optional[bool] = None,
        base_url: Optional[str] = None,
        space_key: Optional[str] = None,
        parent_page_id: Optional[str] = None,
        email: Optional[str] = None,
        api_token: Optional[str] = None,
        page_title_template: Optional[str] = None,
    ) -> bool:
        """Partially update Confluence settings.

        Only updates provided fields.

        Args:
            guild_id: Discord guild ID
            Other args: Optional fields to update

        Returns:
            True if updated
        """
        updates = []
        params: List[Any] = []

        if enabled is not None:
            updates.append("enabled = ?")
            params.append(1 if enabled else 0)
        if base_url is not None:
            updates.append("base_url = ?")
            params.append(base_url)
        if space_key is not None:
            updates.append("space_key = ?")
            params.append(space_key)
        if parent_page_id is not None:
            updates.append("parent_page_id = ?")
            params.append(parent_page_id if parent_page_id else None)
        if email is not None:
            updates.append("email = ?")
            params.append(email)
        if api_token is not None:
            updates.append("api_token_encrypted = ?")
            params.append(encrypt_value(api_token) if api_token else None)
        if page_title_template is not None:
            updates.append("page_title_template = ?")
            params.append(page_title_template)

        if not updates:
            return True  # Nothing to update

        updates.append("updated_at = ?")
        params.append(utc_now_naive().isoformat())
        params.append(guild_id)

        query = f"UPDATE confluence_settings SET {', '.join(updates)} WHERE guild_id = ?"
        cursor = await self.connection.execute(query, tuple(params))
        return cursor.rowcount > 0

    def _row_to_settings(self, row: Dict[str, Any]) -> ConfluenceSettings:
        """Convert database row to ConfluenceSettings."""
        # Decrypt the API token
        api_token = decrypt_value(row.get("api_token_encrypted")) or ""

        return ConfluenceSettings(
            guild_id=row["guild_id"],
            enabled=bool(row.get("enabled", 0)),
            base_url=row.get("base_url", ""),
            space_key=row.get("space_key", ""),
            parent_page_id=row.get("parent_page_id"),
            email=row.get("email", ""),
            api_token=api_token,
            page_title_template=row.get("page_title_template", "{title}"),
            configured_by=row.get("configured_by"),
            configured_at=datetime.fromisoformat(row["configured_at"]) if row.get("configured_at") else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row.get("updated_at") else None,
        )


# Module-level repository accessor
_confluence_repo: Optional[SQLiteConfluenceRepository] = None


async def get_confluence_repository() -> Optional[SQLiteConfluenceRepository]:
    """Get the Confluence repository singleton.

    Returns:
        SQLiteConfluenceRepository or None if not initialized
    """
    global _confluence_repo
    if _confluence_repo is None:
        from .connection import get_connection
        conn = await get_connection()
        if conn:
            _confluence_repo = SQLiteConfluenceRepository(conn)
    return _confluence_repo
