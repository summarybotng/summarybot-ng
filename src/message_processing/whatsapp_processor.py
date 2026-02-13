"""
WhatsApp message processing for ingest data (ADR-002).

Converts IngestMessage objects from the WhatsApp Push Agent into ProcessedMessage
objects that the existing summarization engine can process.
"""

from typing import List, Dict, Optional
from datetime import datetime

from ..models.message import (
    ProcessedMessage,
    AttachmentInfo,
    MessageReference,
    SourceType,
    MessageType,
    AttachmentType,
)
from ..models.ingest import IngestMessage, IngestDocument, IngestAttachment


class WhatsAppMessageProcessor:
    """Transform WhatsApp ingest data into the internal ProcessedMessage format."""

    def convert_batch(self, doc: IngestDocument) -> List[ProcessedMessage]:
        """Convert an entire IngestDocument batch to ProcessedMessages.

        Args:
            doc: The ingest document containing WhatsApp messages

        Returns:
            List of ProcessedMessage objects ready for summarization
        """
        messages = [self.convert_message(msg, doc.channel_name) for msg in doc.messages]

        # Build reply references by linking reply_to_ids
        msg_index = {m.id: m for m in messages}

        for orig, converted in zip(doc.messages, messages):
            if orig.reply_to_id and orig.reply_to_id in msg_index:
                ref_msg = msg_index[orig.reply_to_id]
                converted.references = [MessageReference(
                    message_id=ref_msg.id,
                    channel_id=doc.channel_id,
                    guild_id=None,  # WhatsApp doesn't have guilds
                    author_name=ref_msg.author_name,
                    content_preview=ref_msg.content[:100] if ref_msg.content else "",
                )]
                converted.reply_to_id = orig.reply_to_id

        return messages

    def convert_message(
        self,
        msg: IngestMessage,
        channel_name: Optional[str] = None
    ) -> ProcessedMessage:
        """Convert a single IngestMessage to ProcessedMessage.

        Args:
            msg: The ingest message to convert
            channel_name: Optional channel/chat name for context

        Returns:
            ProcessedMessage ready for the summarization pipeline
        """
        return ProcessedMessage(
            id=msg.id,
            author_id=msg.sender.id,
            author_name=msg.sender.display_name,
            content=msg.content,
            timestamp=msg.timestamp,
            source_type=SourceType.WHATSAPP,
            message_type=self._map_message_type(msg),
            attachments=[self._convert_attachment(a) for a in msg.attachments],
            is_edited=msg.is_edited,
            is_pinned=False,  # WhatsApp doesn't have pinned messages in the same way
            channel_id=msg.channel_id,
            channel_name=channel_name,
            is_forwarded=msg.is_forwarded,
            is_deleted=msg.is_deleted,
            reply_to_id=msg.reply_to_id,
            phone_number=msg.sender.phone_number,
        )

    def _map_message_type(self, msg: IngestMessage) -> MessageType:
        """Map WhatsApp message characteristics to MessageType.

        Args:
            msg: The ingest message

        Returns:
            Appropriate MessageType enum value
        """
        if msg.is_forwarded:
            return MessageType.WHATSAPP_FORWARDED

        if msg.attachments:
            mime = msg.attachments[0].mime_type
            if mime.startswith('audio/'):
                return MessageType.WHATSAPP_VOICE
            return MessageType.WHATSAPP_MEDIA

        # Check metadata for special types
        metadata = msg.metadata or {}
        if metadata.get('type') == 'location':
            return MessageType.WHATSAPP_LOCATION
        if metadata.get('type') == 'contact':
            return MessageType.WHATSAPP_CONTACT
        if metadata.get('type') == 'poll':
            return MessageType.WHATSAPP_POLL

        return MessageType.WHATSAPP_TEXT

    def _convert_attachment(self, att: IngestAttachment) -> AttachmentInfo:
        """Convert an IngestAttachment to AttachmentInfo.

        Args:
            att: The ingest attachment

        Returns:
            AttachmentInfo object
        """
        return AttachmentInfo(
            id=att.filename,  # WhatsApp doesn't have attachment IDs, use filename
            filename=att.filename,
            size=att.size_bytes,
            url=att.url or "",
            proxy_url=att.url or "",  # WhatsApp doesn't have proxy URLs
            type=self._detect_type(att.mime_type),
            content_type=att.mime_type,
            description=att.caption,
        )

    def _detect_type(self, mime: str) -> AttachmentType:
        """Detect attachment type from MIME type.

        Args:
            mime: MIME type string

        Returns:
            AttachmentType enum value
        """
        if mime.startswith('image/'):
            return AttachmentType.IMAGE
        if mime.startswith('video/'):
            return AttachmentType.VIDEO
        if mime.startswith('audio/'):
            return AttachmentType.AUDIO
        return AttachmentType.DOCUMENT


class ThreadReconstructor:
    """Reconstruct conversation threads from WhatsApp reply-to chains (ADR-002)."""

    def __init__(self, time_gap_minutes: int = 5):
        """Initialize thread reconstructor.

        Args:
            time_gap_minutes: Max time gap for implicit thread grouping
        """
        self.time_gap_minutes = time_gap_minutes

    def reconstruct(self, messages: List[ProcessedMessage]) -> List[List[ProcessedMessage]]:
        """Reconstruct threads from messages with reply chains.

        Args:
            messages: List of processed messages

        Returns:
            List of thread groups (each thread is a list of messages)
        """
        threads: Dict[str, List[ProcessedMessage]] = {}
        orphans: List[ProcessedMessage] = []

        # First pass: group by reply chains
        for msg in messages:
            if msg.reply_to_id:
                root = self._find_root(msg.reply_to_id, messages)
                if root not in threads:
                    threads[root] = []
                threads[root].append(msg)
            else:
                orphans.append(msg)

        # Second pass: group orphans by time proximity
        implicit_threads = self._group_by_time_proximity(orphans)

        # Combine explicit and implicit threads
        result = list(threads.values())
        result.extend(implicit_threads)

        # Sort each thread by timestamp
        for thread in result:
            thread.sort(key=lambda m: m.timestamp)

        return result

    def _find_root(self, reply_to_id: str, messages: List[ProcessedMessage]) -> str:
        """Find the root message ID of a reply chain.

        Args:
            reply_to_id: The ID being replied to
            messages: All messages to search

        Returns:
            Root message ID
        """
        msg_map = {m.id: m for m in messages}
        current_id = reply_to_id

        # Follow reply chain up to root
        visited = set()
        while current_id in msg_map and current_id not in visited:
            visited.add(current_id)
            msg = msg_map[current_id]
            if msg.reply_to_id and msg.reply_to_id in msg_map:
                current_id = msg.reply_to_id
            else:
                break

        return current_id

    def _group_by_time_proximity(
        self,
        messages: List[ProcessedMessage]
    ) -> List[List[ProcessedMessage]]:
        """Group messages by time proximity into implicit threads.

        Args:
            messages: Messages without explicit reply chains

        Returns:
            List of implicit thread groups
        """
        if not messages:
            return []

        # Sort by timestamp
        sorted_msgs = sorted(messages, key=lambda m: m.timestamp)
        groups: List[List[ProcessedMessage]] = []
        current_group: List[ProcessedMessage] = [sorted_msgs[0]]

        for msg in sorted_msgs[1:]:
            prev_msg = current_group[-1]
            gap = (msg.timestamp - prev_msg.timestamp).total_seconds() / 60

            if gap <= self.time_gap_minutes:
                current_group.append(msg)
            else:
                groups.append(current_group)
                current_group = [msg]

        if current_group:
            groups.append(current_group)

        return groups
