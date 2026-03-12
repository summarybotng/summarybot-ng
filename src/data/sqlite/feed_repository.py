"""
SQLite implementation of feed repository.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from ..base import FeedRepository
from ...models.feed import FeedConfig, FeedType
from .connection import SQLiteConnection
from src.utils.time import utc_now_naive

logger = logging.getLogger(__name__)


class SQLiteFeedRepository(FeedRepository):
    """SQLite implementation of feed repository."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    async def save_feed(self, feed: FeedConfig) -> str:
        """Save or update a feed configuration."""
        query = """
        INSERT OR REPLACE INTO feed_configs (
            id, guild_id, channel_id, feed_type, is_public, token,
            title, description, max_items, include_full_content,
            created_at, created_by, last_accessed, access_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            feed.id,
            feed.guild_id,
            feed.channel_id,
            feed.feed_type.value if isinstance(feed.feed_type, FeedType) else feed.feed_type,
            1 if feed.is_public else 0,
            feed.token,
            feed.title,
            feed.description,
            feed.max_items,
            1 if feed.include_full_content else 0,
            feed.created_at.isoformat(),
            feed.created_by,
            feed.last_accessed.isoformat() if feed.last_accessed else None,
            feed.access_count
        )

        await self.connection.execute(query, params)
        return feed.id

    async def get_feed(self, feed_id: str) -> Optional[FeedConfig]:
        """Retrieve a feed by its ID."""
        query = "SELECT * FROM feed_configs WHERE id = ?"
        row = await self.connection.fetch_one(query, (feed_id,))

        if not row:
            return None

        return self._row_to_feed(row)

    async def get_feed_by_token(self, token: str) -> Optional[FeedConfig]:
        """Retrieve a feed by its authentication token."""
        query = "SELECT * FROM feed_configs WHERE token = ?"
        row = await self.connection.fetch_one(query, (token,))

        if not row:
            return None

        return self._row_to_feed(row)

    async def get_feeds_by_guild(self, guild_id: str) -> List[FeedConfig]:
        """Get all feeds for a specific guild."""
        query = """
        SELECT * FROM feed_configs
        WHERE guild_id = ?
        ORDER BY created_at DESC
        """
        rows = await self.connection.fetch_all(query, (guild_id,))
        return [self._row_to_feed(row) for row in rows]

    async def delete_feed(self, feed_id: str) -> bool:
        """Delete a feed configuration."""
        query = "DELETE FROM feed_configs WHERE id = ?"
        cursor = await self.connection.execute(query, (feed_id,))
        return cursor.rowcount > 0

    async def update_access_stats(self, feed_id: str) -> None:
        """Update access statistics for a feed."""
        query = """
        UPDATE feed_configs
        SET last_accessed = ?, access_count = access_count + 1
        WHERE id = ?
        """
        await self.connection.execute(query, (utc_now_naive().isoformat(), feed_id))

    def _row_to_feed(self, row: Dict[str, Any]) -> FeedConfig:
        """Convert database row to FeedConfig object."""
        return FeedConfig(
            id=row['id'],
            guild_id=row['guild_id'],
            channel_id=row['channel_id'],
            feed_type=FeedType(row['feed_type']),
            is_public=bool(row['is_public']),
            token=row['token'],
            title=row['title'],
            description=row['description'],
            max_items=row['max_items'],
            include_full_content=bool(row['include_full_content']),
            created_at=datetime.fromisoformat(row['created_at']),
            created_by=row['created_by'],
            last_accessed=datetime.fromisoformat(row['last_accessed']) if row['last_accessed'] else None,
            access_count=row['access_count']
        )
