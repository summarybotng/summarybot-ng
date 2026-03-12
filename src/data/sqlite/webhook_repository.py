"""
SQLite implementation of webhook repository.
"""

import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from ..base import WebhookRepository
from .connection import SQLiteConnection
from src.utils.time import utc_now_naive

logger = logging.getLogger(__name__)


class SQLiteWebhookRepository(WebhookRepository):
    """SQLite implementation of webhook repository."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    async def save_webhook(self, webhook: Dict[str, Any]) -> str:
        """Save or update a webhook."""
        query = """
        INSERT OR REPLACE INTO webhooks (
            id, guild_id, name, url, type, headers, enabled,
            last_delivery, last_status, created_by, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            webhook['id'],
            webhook['guild_id'],
            webhook['name'],
            webhook['url'],
            webhook.get('type', 'generic'),
            json.dumps(webhook.get('headers', {})),
            1 if webhook.get('enabled', True) else 0,
            webhook.get('last_delivery').isoformat() if webhook.get('last_delivery') else None,
            webhook.get('last_status'),
            webhook['created_by'],
            webhook['created_at'].isoformat() if isinstance(webhook['created_at'], datetime) else webhook['created_at'],
        )

        await self.connection.execute(query, params)
        return webhook['id']

    async def get_webhook(self, webhook_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a webhook by its ID."""
        query = "SELECT * FROM webhooks WHERE id = ?"
        row = await self.connection.fetch_one(query, (webhook_id,))

        if not row:
            return None

        return self._row_to_webhook(row)

    async def get_webhooks_by_guild(self, guild_id: str) -> List[Dict[str, Any]]:
        """Get all webhooks for a specific guild."""
        query = """
        SELECT * FROM webhooks
        WHERE guild_id = ?
        ORDER BY created_at DESC
        """
        rows = await self.connection.fetch_all(query, (guild_id,))
        return [self._row_to_webhook(row) for row in rows]

    async def delete_webhook(self, webhook_id: str) -> bool:
        """Delete a webhook."""
        query = "DELETE FROM webhooks WHERE id = ?"
        cursor = await self.connection.execute(query, (webhook_id,))
        return cursor.rowcount > 0

    async def update_delivery_status(
        self,
        webhook_id: str,
        status: str,
        delivery_time: Optional[datetime] = None
    ) -> None:
        """Update delivery status for a webhook."""
        delivery_time = delivery_time or utc_now_naive()
        query = """
        UPDATE webhooks
        SET last_delivery = ?, last_status = ?
        WHERE id = ?
        """
        await self.connection.execute(query, (delivery_time.isoformat(), status, webhook_id))

    def _row_to_webhook(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert database row to webhook dictionary."""
        return {
            'id': row['id'],
            'guild_id': row['guild_id'],
            'name': row['name'],
            'url': row['url'],
            'type': row['type'],
            'headers': json.loads(row['headers']),
            'enabled': bool(row['enabled']),
            'last_delivery': datetime.fromisoformat(row['last_delivery']) if row['last_delivery'] else None,
            'last_status': row['last_status'],
            'created_by': row['created_by'],
            'created_at': datetime.fromisoformat(row['created_at']),
        }
