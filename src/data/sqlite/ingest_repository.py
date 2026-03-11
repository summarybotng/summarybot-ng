"""
SQLite implementation of ingest repository (ADR-002).
"""

import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from ..base import IngestRepository
from ...models.ingest import IngestDocument, IngestBatch, ChannelType
from ...models.message import (
    ProcessedMessage, SourceType, MessageType,
    AttachmentInfo, AttachmentType
)
from .connection import SQLiteConnection

logger = logging.getLogger(__name__)


class SQLiteIngestRepository(IngestRepository):
    """SQLite implementation of ingest repository (ADR-002)."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    async def store_batch(
        self,
        batch_id: str,
        document: IngestDocument,
        processed_messages: List[ProcessedMessage],
    ) -> str:
        """Store an ingest batch with its processed messages."""
        # Store the batch record
        batch_query = """
        INSERT INTO ingest_batches (
            id, source_type, channel_id, channel_name, channel_type,
            message_count, time_range_start, time_range_end, raw_payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        batch_params = (
            batch_id,
            document.source_type if isinstance(document.source_type, str) else document.source_type.value,
            document.channel_id,
            document.channel_name,
            document.channel_type if isinstance(document.channel_type, str) else document.channel_type.value,
            document.total_message_count,
            document.time_range_start.isoformat(),
            document.time_range_end.isoformat(),
            document.model_dump_json(),
        )

        await self.connection.execute(batch_query, batch_params)

        # Store individual messages
        msg_query = """
        INSERT INTO ingest_messages (
            id, batch_id, source_type, channel_id, sender_id, sender_name,
            timestamp, content, has_attachments, attachments_json,
            reply_to_id, is_forwarded, is_edited, is_deleted, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        # PERF-002: Use executemany for batch inserts (10-100x faster)
        msg_params_list = []
        for msg in processed_messages:
            attachments_json = json.dumps([
                {
                    'filename': a.filename,
                    'size': a.size,
                    'type': a.type.value if a.type else None,
                    'content_type': a.content_type,
                }
                for a in msg.attachments
            ])

            msg_params = (
                msg.id,
                batch_id,
                msg.source_type.value if isinstance(msg.source_type, SourceType) else msg.source_type,
                msg.channel_id,
                msg.author_id,
                msg.author_name,
                msg.timestamp.isoformat(),
                msg.content,
                1 if msg.attachments else 0,
                attachments_json,
                msg.reply_to_id,
                1 if msg.is_forwarded else 0,
                1 if msg.is_edited else 0,
                1 if msg.is_deleted else 0,
                json.dumps({'phone_number': msg.phone_number}) if msg.phone_number else '{}',
            )
            msg_params_list.append(msg_params)

        # Batch insert all messages at once
        if msg_params_list:
            await self.connection.executemany(msg_query, msg_params_list)

        # Update channel stats
        await self._update_channel_stats(document)

        return batch_id

    async def _update_channel_stats(self, document: IngestDocument) -> None:
        """Update channel statistics after ingesting messages."""
        source_type = document.source_type if isinstance(document.source_type, str) else document.source_type.value
        channel_type = document.channel_type if isinstance(document.channel_type, str) else document.channel_type.value

        # Upsert channel stats
        query = """
        INSERT INTO channel_stats (
            source_type, channel_id, channel_name, channel_type,
            message_count, participant_count, first_message_at, last_message_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(source_type, channel_id) DO UPDATE SET
            channel_name = COALESCE(excluded.channel_name, channel_name),
            message_count = message_count + excluded.message_count,
            participant_count = MAX(participant_count, excluded.participant_count),
            first_message_at = MIN(COALESCE(first_message_at, excluded.first_message_at), excluded.first_message_at),
            last_message_at = MAX(COALESCE(last_message_at, excluded.last_message_at), excluded.last_message_at),
            updated_at = datetime('now')
        """

        params = (
            source_type,
            document.channel_id,
            document.channel_name,
            channel_type,
            document.total_message_count,
            len(document.participants),
            document.time_range_start.isoformat(),
            document.time_range_end.isoformat(),
        )

        await self.connection.execute(query, params)

    async def get_batch(self, batch_id: str) -> Optional[IngestBatch]:
        """Retrieve an ingest batch by ID."""
        query = "SELECT * FROM ingest_batches WHERE id = ?"
        row = await self.connection.fetch_one(query, (batch_id,))

        if not row:
            return None

        return IngestBatch(
            id=row['id'],
            source_type=SourceType(row['source_type']),
            channel_id=row['channel_id'],
            channel_name=row['channel_name'],
            channel_type=ChannelType(row['channel_type']),
            message_count=row['message_count'],
            time_range_start=datetime.fromisoformat(row['time_range_start']),
            time_range_end=datetime.fromisoformat(row['time_range_end']),
            raw_payload=row['raw_payload'],
            processed=bool(row['processed']),
            document_id=row['document_id'],
            created_at=datetime.fromisoformat(row['created_at']),
        )

    async def get_messages(
        self,
        source_type: str,
        channel_id: str,
        time_from: Optional[datetime] = None,
        time_to: Optional[datetime] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> List[ProcessedMessage]:
        """Get processed messages for a channel."""
        conditions = ["source_type = ?", "channel_id = ?"]
        params: List[Any] = [source_type, channel_id]

        if time_from:
            conditions.append("timestamp >= ?")
            params.append(time_from.isoformat())

        if time_to:
            conditions.append("timestamp <= ?")
            params.append(time_to.isoformat())

        where_clause = " AND ".join(conditions)

        query = f"""
        SELECT * FROM ingest_messages
        WHERE {where_clause}
        ORDER BY timestamp ASC
        LIMIT ? OFFSET ?
        """

        params.extend([limit, offset])

        rows = await self.connection.fetch_all(query, tuple(params))
        return [self._row_to_processed_message(row) for row in rows]

    def _row_to_processed_message(self, row: Dict[str, Any]) -> ProcessedMessage:
        """Convert database row to ProcessedMessage."""
        # Parse attachments
        attachments = []
        if row.get('attachments_json'):
            att_data = json.loads(row['attachments_json'])
            for att in att_data:
                attachments.append(AttachmentInfo(
                    id=att.get('filename', ''),
                    filename=att.get('filename', ''),
                    size=att.get('size', 0),
                    url='',
                    proxy_url='',
                    type=AttachmentType(att['type']) if att.get('type') else AttachmentType.UNKNOWN,
                    content_type=att.get('content_type'),
                ))

        # Parse metadata
        metadata = json.loads(row.get('metadata') or '{}')

        return ProcessedMessage(
            id=row['id'],
            author_id=row['sender_id'],
            author_name=row['sender_name'],
            content=row['content'] or '',
            timestamp=datetime.fromisoformat(row['timestamp']),
            source_type=SourceType(row['source_type']),
            message_type=MessageType.WHATSAPP_TEXT,  # Default for ingested messages
            attachments=attachments,
            channel_id=row['channel_id'],
            is_forwarded=bool(row['is_forwarded']),
            is_edited=bool(row['is_edited']),
            is_deleted=bool(row['is_deleted']),
            reply_to_id=row['reply_to_id'],
            phone_number=metadata.get('phone_number'),
        )

    async def list_channels(
        self,
        source_type: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List channels with ingested messages."""
        query = """
        SELECT * FROM channel_stats
        WHERE source_type = ?
        ORDER BY last_message_at DESC
        LIMIT ? OFFSET ?
        """

        rows = await self.connection.fetch_all(query, (source_type, limit, offset))

        return [
            {
                'chat_id': row['channel_id'],
                'chat_name': row['channel_name'] or row['channel_id'],
                'chat_type': row['channel_type'],
                'message_count': row['message_count'],
                'participant_count': row['participant_count'],
                'first_message_at': datetime.fromisoformat(row['first_message_at']) if row['first_message_at'] else None,
                'last_message_at': datetime.fromisoformat(row['last_message_at']) if row['last_message_at'] else None,
            }
            for row in rows
        ]

    async def count_channels(self, source_type: str) -> int:
        """Count channels with ingested messages."""
        query = "SELECT COUNT(*) as count FROM channel_stats WHERE source_type = ?"
        row = await self.connection.fetch_one(query, (source_type,))
        return row['count'] if row else 0

    async def get_channel_stats(
        self,
        source_type: str,
        channel_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get statistics for a specific channel."""
        query = """
        SELECT * FROM channel_stats
        WHERE source_type = ? AND channel_id = ?
        """

        row = await self.connection.fetch_one(query, (source_type, channel_id))

        if not row:
            return None

        return {
            'chat_id': row['channel_id'],
            'chat_name': row['channel_name'] or row['channel_id'],
            'chat_type': row['channel_type'],
            'message_count': row['message_count'],
            'participant_count': row['participant_count'],
            'first_message_at': datetime.fromisoformat(row['first_message_at']) if row['first_message_at'] else None,
            'last_message_at': datetime.fromisoformat(row['last_message_at']) if row['last_message_at'] else None,
        }

    async def delete_batch(self, batch_id: str) -> bool:
        """Delete an ingest batch and its messages."""
        # Messages are deleted via CASCADE
        query = "DELETE FROM ingest_batches WHERE id = ?"
        cursor = await self.connection.execute(query, (batch_id,))
        return cursor.rowcount > 0
