"""
WhatsApp Platform Fetcher (ADR-051 + ADR-081).

Implements PlatformFetcher for WhatsApp imported chats.
Reads messages from ingest_messages table populated by WhatsApp imports.
"""

import logging
from typing import List, Optional, Callable, Dict
from datetime import datetime

from .base import PlatformFetcher
from .types import FetchResult, PlatformContext, ChannelInfo
from src.models.message import ProcessedMessage, MessageType, SourceType

logger = logging.getLogger(__name__)


class WhatsAppFetcher(PlatformFetcher):
    """
    WhatsApp implementation of PlatformFetcher.

    Fetches messages from imported WhatsApp chats stored in ingest_messages.
    Uses guild_id to scope chats and chat_id as channel equivalent.
    """

    def __init__(self, guild_id: str, db_connection):
        """Initialize WhatsApp fetcher.

        Args:
            guild_id: Discord guild ID that owns the WhatsApp imports
            db_connection: Database connection for queries
        """
        self._guild_id = guild_id
        self._db = db_connection
        self._chat_names: Dict[str, str] = {}

    @property
    def platform_name(self) -> str:
        return "whatsapp"

    @property
    def platform_display_name(self) -> str:
        return "WhatsApp"

    @property
    def server_id(self) -> str:
        return self._guild_id

    @property
    def server_name(self) -> str:
        return "WhatsApp Imports"

    async def fetch_messages(
        self,
        channel_ids: List[str],
        start_time: datetime,
        end_time: datetime,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> FetchResult:
        """
        Fetch messages from WhatsApp imported chats.

        Args:
            channel_ids: List of WhatsApp chat_ids to fetch from
            start_time: Start of time range (UTC)
            end_time: End of time range (UTC)
            job_id: Optional job ID for tracking
            progress_callback: Optional progress callback

        Returns:
            FetchResult with messages and metadata
        """
        messages: List[ProcessedMessage] = []
        channel_names: Dict[str, str] = {}
        errors: List[tuple] = []
        user_names: Dict[str, str] = {}

        total_channels = len(channel_ids)
        start_iso = start_time.isoformat()
        end_iso = end_time.isoformat()

        for idx, chat_id in enumerate(channel_ids):
            try:
                # Get chat name from whatsapp_imports
                chat_name = await self._get_chat_name(chat_id)
                channel_names[chat_id] = chat_name

                if progress_callback:
                    await progress_callback(
                        idx, total_channels,
                        f"Fetching {chat_name}"
                    )

                # Query messages from ingest_messages
                # Messages are linked via batch_id -> whatsapp_imports.id
                # And channel_id = chat_id
                rows = await self._db.fetch_all(
                    """
                    SELECT
                        m.id,
                        m.sender_id,
                        m.sender_name,
                        m.timestamp,
                        m.content,
                        m.has_attachments,
                        m.reply_to_id
                    FROM ingest_messages m
                    JOIN whatsapp_imports wi ON m.batch_id = wi.id
                    WHERE wi.guild_id = ?
                      AND m.channel_id = ?
                      AND m.timestamp >= ?
                      AND m.timestamp <= ?
                      AND m.content IS NOT NULL
                      AND m.content != ''
                    ORDER BY m.timestamp ASC
                    """,
                    (self._guild_id, chat_id, start_iso, end_iso)
                )

                logger.info(f"[{job_id}] Fetched {len(rows)} messages from WhatsApp chat {chat_name}")

                for row in rows:
                    # Track user names
                    sender_id = row["sender_id"]
                    sender_name = row["sender_name"]
                    if sender_id and sender_name:
                        user_names[sender_id] = sender_name

                    # Parse timestamp
                    timestamp_str = row["timestamp"]
                    try:
                        if "T" in timestamp_str:
                            msg_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                        else:
                            msg_time = datetime.fromisoformat(timestamp_str)
                        # Make naive for consistency
                        if msg_time.tzinfo:
                            msg_time = msg_time.replace(tzinfo=None)
                    except (ValueError, TypeError):
                        continue

                    # Create ProcessedMessage
                    msg = ProcessedMessage(
                        id=row["id"],
                        channel_id=chat_id,
                        author_id=sender_id or "unknown",
                        author_name=sender_name or "Unknown",
                        content=row["content"] or "",
                        timestamp=msg_time,
                        message_type=MessageType.WHATSAPP_TEXT,
                        source_type=SourceType.WHATSAPP,
                        reply_to_id=row["reply_to_id"],
                        has_attachments=bool(row["has_attachments"]),
                    )
                    messages.append(msg)

            except Exception as e:
                logger.error(f"[{job_id}] Error fetching WhatsApp chat {chat_id}: {e}")
                errors.append((chat_id, str(e)))

        if progress_callback:
            await progress_callback(total_channels, total_channels, "Fetch complete")

        return FetchResult(
            messages=messages,
            channel_names=channel_names,
            user_names=user_names,
            errors=errors,
        )

    async def _get_chat_name(self, chat_id: str) -> str:
        """Get chat display name from whatsapp_imports."""
        if chat_id in self._chat_names:
            return self._chat_names[chat_id]

        row = await self._db.fetch_one(
            """
            SELECT chat_name FROM whatsapp_imports
            WHERE guild_id = ? AND chat_id = ?
            ORDER BY imported_at DESC
            LIMIT 1
            """,
            (self._guild_id, chat_id)
        )

        name = row["chat_name"] if row else chat_id
        self._chat_names[chat_id] = name
        return name

    async def resolve_channels(
        self,
        scope: str,
        channel_ids: Optional[List[str]] = None,
        category_id: Optional[str] = None,
    ) -> List[str]:
        """
        Resolve WhatsApp chat IDs based on scope.

        For WhatsApp:
        - "channel" scope: Use provided chat_ids
        - "guild" scope: Return all chats with imports in this guild
        """
        if scope == "channel" and channel_ids:
            return channel_ids

        # Get all chat_ids that have imports for this guild
        rows = await self._db.fetch_all(
            """
            SELECT DISTINCT chat_id FROM whatsapp_imports
            WHERE guild_id = ? AND status = 'completed'
            """,
            (self._guild_id,)
        )

        return [row["chat_id"] for row in rows]

    async def get_channels(self) -> List[ChannelInfo]:
        """Get all WhatsApp chats available for this guild."""
        rows = await self._db.fetch_all(
            """
            SELECT
                chat_id,
                chat_name,
                SUM(message_count) as total_messages
            FROM whatsapp_imports
            WHERE guild_id = ? AND status = 'completed'
            GROUP BY chat_id, chat_name
            ORDER BY chat_name
            """,
            (self._guild_id,)
        )

        return [
            ChannelInfo(
                channel_id=row["chat_id"],
                name=row["chat_name"] or row["chat_id"],
                channel_type="whatsapp_chat",
                is_accessible=True,
            )
            for row in rows
        ]

    async def get_context(
        self,
        channel_ids: List[str],
    ) -> PlatformContext:
        """Build summarization context for WhatsApp chats."""
        channel_names = {}
        for chat_id in channel_ids:
            channel_names[chat_id] = await self._get_chat_name(chat_id)

        primary_name = channel_names.get(channel_ids[0], "WhatsApp Chat") if channel_ids else "WhatsApp"

        return PlatformContext(
            platform_name="WhatsApp",
            server_name="WhatsApp Imports",
            server_id=self._guild_id,
            primary_channel_name=primary_name,
            channel_names=channel_names,
        )

    def get_archive_source_key(self) -> str:
        """Return archive key for WhatsApp imports."""
        return f"whatsapp:{self._guild_id}"

    async def close(self) -> None:
        """No cleanup needed for WhatsApp fetcher."""
        pass
