"""
Slack message normalization for ingest processing (ADR-043).

Converts Slack messages into ProcessedMessage objects that the
existing summarization engine can process.
"""

import re
from typing import List, Optional, Dict, Any
from datetime import datetime

from ..models.message import (
    ProcessedMessage,
    AttachmentInfo,
    MessageReference,
    SourceType,
    MessageType,
    AttachmentType,
)
from .models import SlackMessage, SlackUser, SlackChannel


class SlackMessageProcessor:
    """Transform Slack messages into the internal ProcessedMessage format (ADR-043)."""

    # Slack message subtypes to skip (system/meta messages)
    SKIP_SUBTYPES = {
        "channel_join",
        "channel_leave",
        "channel_topic",
        "channel_purpose",
        "channel_name",
        "channel_archive",
        "channel_unarchive",
        "group_join",
        "group_leave",
        "group_topic",
        "group_purpose",
        "group_name",
        "group_archive",
        "group_unarchive",
        "pinned_item",
        "unpinned_item",
    }

    def __init__(self, users_cache: Optional[Dict[str, SlackUser]] = None):
        """Initialize Slack message processor.

        Args:
            users_cache: Optional dict mapping user_id to SlackUser for name resolution
        """
        self.users_cache = users_cache or {}

    def convert_batch(
        self,
        messages: List[SlackMessage],
        channel: SlackChannel,
    ) -> List[ProcessedMessage]:
        """Convert a batch of Slack messages to ProcessedMessages.

        Args:
            messages: List of SlackMessage objects
            channel: Channel context for the messages

        Returns:
            List of ProcessedMessage objects ready for summarization
        """
        processed = []

        for msg in messages:
            # Skip system messages
            if msg.subtype in self.SKIP_SUBTYPES:
                continue

            # Skip bot messages unless they have meaningful content
            if msg.subtype == "bot_message" and not msg.text.strip():
                continue

            converted = self.convert_message(msg, channel)
            if converted:
                processed.append(converted)

        # Build reply references
        msg_index = {m.id: m for m in processed}
        for orig, converted in zip(messages, processed):
            if orig.thread_ts and orig.thread_ts != orig.ts:
                # This is a reply to a thread
                if orig.thread_ts in msg_index:
                    ref_msg = msg_index[orig.thread_ts]
                    converted.references = [MessageReference(
                        message_id=ref_msg.id,
                        channel_id=channel.channel_id,
                        guild_id=None,
                        author_name=ref_msg.author_name,
                        content_preview=ref_msg.content[:100] if ref_msg.content else "",
                    )]
                    converted.reply_to_id = orig.thread_ts

        return processed

    def convert_message(
        self,
        msg: SlackMessage,
        channel: SlackChannel,
    ) -> Optional[ProcessedMessage]:
        """Convert a single Slack message to ProcessedMessage.

        Args:
            msg: SlackMessage to convert
            channel: Channel context

        Returns:
            ProcessedMessage or None if message should be skipped
        """
        # Resolve user name
        author_name = self._resolve_user_name(msg.user_id)

        # Clean and process content
        content = self._clean_slack_content(msg.text)

        # Convert attachments
        attachments = []
        for file in msg.files:
            att = self._convert_file(file)
            if att:
                attachments.append(att)

        # Also handle legacy Slack attachments
        for att_data in msg.attachments:
            att = self._convert_legacy_attachment(att_data)
            if att:
                attachments.append(att)

        return ProcessedMessage(
            id=msg.ts,
            author_id=msg.user_id,
            author_name=author_name,
            content=content,
            timestamp=msg.timestamp,
            source_type=SourceType.SLACK,
            message_type=self._map_message_type(msg),
            attachments=attachments,
            is_edited=msg.is_edited,
            is_pinned=False,
            channel_id=channel.channel_id,
            channel_name=channel.channel_name,
            is_forwarded=False,
            is_deleted=False,
            reply_to_id=msg.thread_ts if msg.is_thread_reply() else None,
            reactions_count=sum(len(r.get("users", [])) for r in msg.reactions),
        )

    def _resolve_user_name(self, user_id: str) -> str:
        """Resolve user ID to display name.

        Args:
            user_id: Slack user ID

        Returns:
            Display name or user ID if not found
        """
        if user_id in self.users_cache:
            return self.users_cache[user_id].display_name
        return user_id

    def _clean_slack_content(self, content: str) -> str:
        """Clean Slack-specific formatting from message content.

        Args:
            content: Raw Slack message text

        Returns:
            Cleaned text content
        """
        if not content:
            return ""

        # Replace user mentions <@U123ABC> with @user
        content = re.sub(r'<@([UW][A-Z0-9]+)>', lambda m: f"@{self._resolve_user_name(m.group(1))}", content)

        # Replace channel mentions <#C123ABC|channel-name> with #channel-name
        content = re.sub(r'<#[A-Z0-9]+\|([^>]+)>', r'#\1', content)
        content = re.sub(r'<#([A-Z0-9]+)>', r'#channel', content)

        # Replace special mentions
        content = content.replace("<!here>", "@here")
        content = content.replace("<!channel>", "@channel")
        content = content.replace("<!everyone>", "@everyone")

        # Replace custom emoji :emoji_name: (keep as is)
        # Already in standard format

        # Replace links <http://example.com|Display Text> with Display Text (http://example.com)
        content = re.sub(r'<(https?://[^|>]+)\|([^>]+)>', r'\2 (\1)', content)
        # Replace bare links <http://example.com>
        content = re.sub(r'<(https?://[^>]+)>', r'\1', content)

        # Clean up extra whitespace
        content = re.sub(r'\s+', ' ', content).strip()

        return content

    def _map_message_type(self, msg: SlackMessage) -> MessageType:
        """Map Slack message characteristics to MessageType.

        Args:
            msg: SlackMessage to analyze

        Returns:
            Appropriate MessageType enum value
        """
        if msg.files:
            # Check first file type
            file = msg.files[0]
            mimetype = file.get("mimetype", "")

            if mimetype.startswith("audio/"):
                return MessageType.SLACK_VOICE
            elif mimetype.startswith("image/") or mimetype.startswith("video/"):
                return MessageType.SLACK_MEDIA

            return MessageType.SLACK_FILE

        if msg.is_thread_reply():
            return MessageType.SLACK_THREAD_REPLY

        if msg.subtype == "bot_message":
            return MessageType.SLACK_BOT

        return MessageType.SLACK_TEXT

    def _convert_file(self, file: Dict[str, Any]) -> Optional[AttachmentInfo]:
        """Convert Slack file to AttachmentInfo.

        Args:
            file: Slack file dict from API

        Returns:
            AttachmentInfo or None
        """
        if not file:
            return None

        mimetype = file.get("mimetype", "application/octet-stream")

        return AttachmentInfo(
            id=file.get("id", ""),
            filename=file.get("name", "file"),
            size=file.get("size", 0),
            url=file.get("url_private", ""),
            proxy_url=file.get("url_private_download", ""),
            type=self._detect_type(mimetype),
            content_type=mimetype,
            description=file.get("title"),
        )

    def _convert_legacy_attachment(self, att: Dict[str, Any]) -> Optional[AttachmentInfo]:
        """Convert legacy Slack attachment to AttachmentInfo.

        Args:
            att: Slack attachment dict

        Returns:
            AttachmentInfo or None
        """
        # Legacy attachments are typically unfurled links, not files
        if not att.get("fallback"):
            return None

        # Create a pseudo-attachment for link previews
        return AttachmentInfo(
            id=att.get("id", ""),
            filename=att.get("title", "Link"),
            size=0,
            url=att.get("original_url", ""),
            proxy_url="",
            type=AttachmentType.DOCUMENT,
            content_type="text/html",
            description=att.get("text", att.get("fallback", "")),
        )

    def _detect_type(self, mime: str) -> AttachmentType:
        """Detect attachment type from MIME type.

        Args:
            mime: MIME type string

        Returns:
            AttachmentType enum value
        """
        if mime.startswith("image/"):
            return AttachmentType.IMAGE
        if mime.startswith("video/"):
            return AttachmentType.VIDEO
        if mime.startswith("audio/"):
            return AttachmentType.AUDIO
        return AttachmentType.DOCUMENT


class SlackThreadReconstructor:
    """Reconstruct conversation threads from Slack thread_ts chains."""

    def __init__(self, time_gap_minutes: int = 10):
        """Initialize thread reconstructor.

        Args:
            time_gap_minutes: Max time gap for implicit thread grouping
        """
        self.time_gap_minutes = time_gap_minutes

    def reconstruct(self, messages: List[ProcessedMessage]) -> List[List[ProcessedMessage]]:
        """Reconstruct threads from messages.

        Slack has explicit thread_ts for thread grouping.

        Args:
            messages: List of processed messages

        Returns:
            List of thread groups (each thread is a list of messages)
        """
        threads: Dict[str, List[ProcessedMessage]] = {}
        orphans: List[ProcessedMessage] = []

        for msg in messages:
            if msg.reply_to_id:
                # Part of a thread
                if msg.reply_to_id not in threads:
                    threads[msg.reply_to_id] = []
                threads[msg.reply_to_id].append(msg)
            else:
                # Not a thread reply, could be thread parent or standalone
                orphans.append(msg)

        # Add orphans that are thread parents to their threads
        for msg in orphans:
            if msg.id in threads:
                # This is a thread parent, prepend it
                threads[msg.id].insert(0, msg)

        # Collect all threads
        result = list(threads.values())

        # Group remaining orphans by time proximity
        remaining_orphans = [m for m in orphans if m.id not in threads]
        if remaining_orphans:
            implicit_threads = self._group_by_time_proximity(remaining_orphans)
            result.extend(implicit_threads)

        # Sort each thread by timestamp
        for thread in result:
            thread.sort(key=lambda m: m.timestamp)

        return result

    def _group_by_time_proximity(
        self,
        messages: List[ProcessedMessage],
    ) -> List[List[ProcessedMessage]]:
        """Group messages by time proximity into implicit threads."""
        if not messages:
            return []

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
