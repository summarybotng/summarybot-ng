"""
Slack Platform Fetcher (ADR-051).

Implements PlatformFetcher for Slack workspaces.
"""

import logging
from typing import List, Optional, Callable, Dict, Set
from datetime import datetime

from .base import PlatformFetcher
from .types import FetchResult, PlatformContext, ChannelInfo
from src.models.message import ProcessedMessage, MessageType, SourceType
from src.slack.models import SlackWorkspace, SlackChannelType
from src.slack.client import SlackClient, SlackAPIError

logger = logging.getLogger(__name__)


class SlackFetcher(PlatformFetcher):
    """
    Slack implementation of PlatformFetcher.

    Handles message fetching, user resolution, and channel operations
    for Slack workspaces.
    """

    def __init__(self, workspace: SlackWorkspace):
        """Initialize Slack fetcher.

        Args:
            workspace: SlackWorkspace with encrypted token
        """
        self._workspace = workspace
        self._client: Optional[SlackClient] = None
        self._user_cache: Dict[str, str] = {}  # user_id -> display_name

    @property
    def platform_name(self) -> str:
        return "slack"

    @property
    def platform_display_name(self) -> str:
        return "Slack"

    @property
    def server_id(self) -> str:
        return self._workspace.workspace_id

    @property
    def server_name(self) -> str:
        return self._workspace.workspace_name

    async def _get_client(self) -> SlackClient:
        """Get or create Slack client."""
        if self._client is None:
            self._client = SlackClient(self._workspace)
        return self._client

    async def fetch_messages(
        self,
        channel_ids: List[str],
        start_time: datetime,
        end_time: datetime,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> FetchResult:
        """
        Fetch messages from Slack channels.

        Handles pagination, auto-join for public channels, and user resolution.
        """
        client = await self._get_client()
        messages: List[ProcessedMessage] = []
        channel_names: Dict[str, str] = {}
        errors: List[tuple] = []
        user_ids_seen: Set[str] = set()

        # Convert to Slack timestamps
        oldest_ts = str(start_time.timestamp())
        latest_ts = str(end_time.timestamp())

        total_channels = len(channel_ids)

        for idx, channel_id in enumerate(channel_ids):
            try:
                # Get channel info for name
                try:
                    channel_info = await client.get_channel_info(channel_id)
                    channel_names[channel_id] = channel_info.channel_name
                except SlackAPIError as e:
                    logger.warning(f"Could not get channel info for {channel_id}: {e.error}")
                    channel_names[channel_id] = channel_id

                # Fetch messages with pagination and auto-join
                channel_messages = await self._fetch_channel_messages(
                    client=client,
                    channel_id=channel_id,
                    channel_name=channel_names[channel_id],
                    oldest_ts=oldest_ts,
                    latest_ts=latest_ts,
                    user_ids_seen=user_ids_seen,
                )
                messages.extend(channel_messages)

                if progress_callback:
                    progress_callback(idx + 1, total_channels, f"Fetched #{channel_names[channel_id]}")

            except SlackAPIError as e:
                error_msg = f"Slack API error: {e.error}"
                logger.error(f"Failed to fetch channel {channel_id}: {error_msg}")
                errors.append((channel_id, error_msg))
            except Exception as e:
                error_msg = str(e)
                logger.exception(f"Unexpected error fetching channel {channel_id}")
                errors.append((channel_id, error_msg))

        # Batch resolve user names
        user_names = await self._resolve_user_names(client, user_ids_seen)

        # Update message author names
        for msg in messages:
            if msg.author_id in user_names:
                msg.author_name = user_names[msg.author_id]

        return FetchResult(
            messages=messages,
            channel_names=channel_names,
            user_names=user_names,
            errors=errors,
        )

    async def _fetch_channel_messages(
        self,
        client: SlackClient,
        channel_id: str,
        channel_name: str,
        oldest_ts: str,
        latest_ts: str,
        user_ids_seen: Set[str],
    ) -> List[ProcessedMessage]:
        """Fetch messages from a single channel with auto-join."""
        messages: List[ProcessedMessage] = []
        cursor = None

        while True:
            try:
                data = await client.get_channel_history(
                    channel_id=channel_id,
                    oldest=oldest_ts,
                    latest=latest_ts,
                    limit=200,
                    cursor=cursor,
                )
            except SlackAPIError as e:
                if e.error == "not_in_channel":
                    # Try to join and retry
                    if await client.join_channel(channel_id):
                        logger.info(f"Auto-joined channel {channel_id}")
                        data = await client.get_channel_history(
                            channel_id=channel_id,
                            oldest=oldest_ts,
                            latest=latest_ts,
                            limit=200,
                            cursor=cursor,
                        )
                    else:
                        raise SlackAPIError("cannot_join", f"Cannot access channel {channel_id}")
                else:
                    raise

            # Process messages
            for msg in data.get("messages", []):
                # Skip bot messages and system messages
                subtype = msg.get("subtype")
                if subtype in ("bot_message", "channel_join", "channel_leave", "channel_topic", "channel_purpose"):
                    continue

                user_id = msg.get("user", msg.get("bot_id", "unknown"))
                user_ids_seen.add(user_id)

                # Convert to ProcessedMessage
                processed = self._convert_message(msg, channel_id, channel_name)
                messages.append(processed)

            # Handle pagination
            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        return messages

    def _convert_message(
        self,
        msg: Dict,
        channel_id: str,
        channel_name: str,
    ) -> ProcessedMessage:
        """Convert Slack message to ProcessedMessage."""
        ts = msg.get("ts", "")
        user_id = msg.get("user", msg.get("bot_id", "unknown"))
        text = msg.get("text", "")

        # Parse timestamp to datetime
        try:
            timestamp = datetime.fromtimestamp(float(ts))
        except (ValueError, TypeError):
            timestamp = datetime.utcnow()

        # Determine message type
        msg_type = MessageType.SLACK_MESSAGE
        if msg.get("thread_ts") and msg.get("thread_ts") != ts:
            msg_type = MessageType.SLACK_THREAD_REPLY

        return ProcessedMessage(
            id=ts,
            author_id=user_id,
            author_name=user_id,  # Will be resolved later
            content=text,
            timestamp=timestamp,
            channel_id=channel_id,
            channel_name=channel_name,
            message_type=msg_type,
            source_type=SourceType.SLACK,
            thread_id=msg.get("thread_ts"),
            reply_count=msg.get("reply_count", 0),
            reactions=[r.get("name", "") for r in msg.get("reactions", [])],
            attachments=[a.get("fallback", "") for a in msg.get("attachments", [])],
            has_attachments=bool(msg.get("files")),
            metadata={
                "workspace_id": self._workspace.workspace_id,
                "edited": msg.get("edited") is not None,
            },
        )

    async def _resolve_user_names(
        self,
        client: SlackClient,
        user_ids: Set[str],
    ) -> Dict[str, str]:
        """Batch resolve user IDs to display names."""
        user_names: Dict[str, str] = {}

        for user_id in user_ids:
            if user_id in self._user_cache:
                user_names[user_id] = self._user_cache[user_id]
                continue

            if user_id in ("unknown", ""):
                continue

            try:
                user_info = await client.get_user_info(user_id)
                display_name = user_info.display_name or user_info.real_name or user_id
                user_names[user_id] = display_name
                self._user_cache[user_id] = display_name
            except SlackAPIError as e:
                logger.warning(f"Could not resolve user {user_id}: {e.error}")
                user_names[user_id] = user_id

        return user_names

    async def resolve_channels(
        self,
        scope: str,
        channel_ids: Optional[List[str]] = None,
        category_id: Optional[str] = None,
    ) -> List[str]:
        """
        Resolve channel IDs based on scope.

        Slack doesn't have categories, so only "channel" and "workspace" scopes are supported.
        """
        if scope == "channel":
            if not channel_ids:
                raise ValueError("channel_ids required for channel scope")
            return channel_ids

        elif scope in ("guild", "workspace"):
            # Get all accessible channels
            client = await self._get_client()
            channels = await client.get_all_channels(include_private=False)
            return [c.channel_id for c in channels if not c.is_archived]

        elif scope == "category":
            raise ValueError("Slack does not support category scope")

        else:
            raise ValueError(f"Unknown scope: {scope}")

    async def get_channels(self) -> List[ChannelInfo]:
        """Get all accessible channels in the workspace."""
        client = await self._get_client()
        slack_channels = await client.get_all_channels(
            include_private=self._workspace.can_access_private()
        )

        return [
            ChannelInfo(
                channel_id=c.channel_id,
                name=c.channel_name,
                channel_type=self._map_channel_type(c.channel_type),
                is_accessible=not c.is_archived,
            )
            for c in slack_channels
        ]

    def _map_channel_type(self, slack_type: SlackChannelType) -> str:
        """Map Slack channel type to generic type."""
        if slack_type == SlackChannelType.PUBLIC:
            return "public"
        elif slack_type == SlackChannelType.PRIVATE:
            return "private"
        elif slack_type == SlackChannelType.DM:
            return "dm"
        elif slack_type == SlackChannelType.MPIM:
            return "group_dm"
        else:
            return "text"

    async def get_context(
        self,
        channel_ids: List[str],
    ) -> PlatformContext:
        """Build summarization context."""
        client = await self._get_client()
        channel_names: Dict[str, str] = {}

        for channel_id in channel_ids:
            try:
                info = await client.get_channel_info(channel_id)
                channel_names[channel_id] = info.channel_name
            except SlackAPIError:
                channel_names[channel_id] = channel_id

        primary_channel = channel_names.get(channel_ids[0], channel_ids[0]) if channel_ids else "unknown"

        return PlatformContext(
            platform_name=self.platform_display_name,
            server_name=self._workspace.workspace_name,
            server_id=self._workspace.workspace_id,
            primary_channel_name=primary_channel,
            channel_names=channel_names,
        )

    def get_archive_source_key(self) -> str:
        """Return archive key for this Slack workspace."""
        return f"slack:{self._workspace.workspace_id}"

    async def close(self) -> None:
        """Close Slack client."""
        if self._client:
            await self._client.close()
            self._client = None
