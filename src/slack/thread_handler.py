"""
Slack thread handling (ADR-043 Section 6.1).

Manages fetching and tracking of thread replies for summarization.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from .client import SlackClient, SlackAPIError
from .models import SlackWorkspace, SlackChannel, SlackMessage

logger = logging.getLogger(__name__)

# Thread expansion heuristics (ADR-043 Section 6.1)
MIN_REPLIES_FOR_EXPANSION = 5  # Threads with 5+ replies
MAX_THREAD_AGE_DAYS = 7  # Don't expand old threads
MAX_THREADS_PER_BATCH = 10  # Rate limit consideration


@dataclass
class ThreadInfo:
    """Information about a Slack thread."""
    thread_ts: str
    channel_id: str
    workspace_id: str
    reply_count: int = 0
    reply_users_count: int = 0
    latest_reply_ts: Optional[str] = None
    last_fetched_at: Optional[datetime] = None
    parent_user_id: Optional[str] = None
    parent_text: Optional[str] = None
    is_active: bool = True


@dataclass
class ThreadReplies:
    """Thread with its replies."""
    info: ThreadInfo
    parent_message: Optional[SlackMessage] = None
    replies: List[SlackMessage] = field(default_factory=list)


class SlackThreadHandler:
    """Handles thread expansion and reply fetching (ADR-043).

    Implements heuristics for deciding which threads to expand:
    - Threads with 5+ replies
    - Threads with recent activity
    - Threads containing file attachments
    """

    def __init__(
        self,
        client: SlackClient,
        min_replies: int = MIN_REPLIES_FOR_EXPANSION,
        max_age_days: int = MAX_THREAD_AGE_DAYS,
    ):
        """Initialize thread handler.

        Args:
            client: Slack API client
            min_replies: Minimum replies for thread expansion
            max_age_days: Maximum thread age for expansion
        """
        self.client = client
        self.min_replies = min_replies
        self.max_age_days = max_age_days

    def should_expand_thread(self, message: SlackMessage) -> bool:
        """Determine if a thread should be expanded.

        Args:
            message: Parent message to evaluate

        Returns:
            True if thread should be expanded
        """
        # Not a thread parent
        if not message.is_thread_parent():
            return False

        # Check reply count
        if message.reply_count >= self.min_replies:
            return True

        # Check if thread has files (important content)
        if message.files:
            return True

        # Check for recent activity (within max_age_days)
        try:
            thread_time = datetime.fromtimestamp(float(message.ts.split(".")[0]))
            if datetime.utcnow() - thread_time < timedelta(days=self.max_age_days):
                # Recent thread with some activity
                if message.reply_count >= 2:
                    return True
        except (ValueError, TypeError):
            pass

        return False

    async def fetch_thread_replies(
        self,
        channel_id: str,
        thread_ts: str,
        limit: int = 100,
    ) -> ThreadReplies:
        """Fetch all replies in a thread.

        Args:
            channel_id: Channel containing the thread
            thread_ts: Thread parent timestamp
            limit: Max replies per page

        Returns:
            ThreadReplies with parent and reply messages
        """
        all_messages = []
        cursor = None
        parent_message = None

        while True:
            try:
                data = await self.client.get_thread_replies(
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                    limit=limit,
                    cursor=cursor,
                )

                messages = data.get("messages", [])
                for msg_data in messages:
                    msg = self.client.parse_message(msg_data, channel_id)

                    # First message is the parent
                    if msg.ts == thread_ts:
                        parent_message = msg
                    else:
                        all_messages.append(msg)

                # Handle pagination
                cursor = data.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break

            except SlackAPIError as e:
                logger.error(f"Failed to fetch thread replies: {e}")
                break

        # Build thread info
        info = ThreadInfo(
            thread_ts=thread_ts,
            channel_id=channel_id,
            workspace_id=self.client.workspace_id,
            reply_count=len(all_messages),
            reply_users_count=len(set(m.user_id for m in all_messages)),
            latest_reply_ts=all_messages[-1].ts if all_messages else None,
            last_fetched_at=datetime.utcnow(),
            parent_user_id=parent_message.user_id if parent_message else None,
            parent_text=parent_message.text[:500] if parent_message else None,
        )

        return ThreadReplies(
            info=info,
            parent_message=parent_message,
            replies=all_messages,
        )

    async def expand_threads_in_messages(
        self,
        messages: List[SlackMessage],
        channel_id: str,
        max_threads: int = MAX_THREADS_PER_BATCH,
    ) -> Dict[str, ThreadReplies]:
        """Expand threads found in a list of messages.

        Args:
            messages: Messages to scan for threads
            channel_id: Channel ID
            max_threads: Maximum threads to expand (rate limit consideration)

        Returns:
            Dict mapping thread_ts to ThreadReplies
        """
        threads_to_expand = []

        for msg in messages:
            if self.should_expand_thread(msg):
                threads_to_expand.append(msg.ts)

            if len(threads_to_expand) >= max_threads:
                break

        # Fetch replies for each thread
        expanded = {}
        for thread_ts in threads_to_expand:
            try:
                replies = await self.fetch_thread_replies(channel_id, thread_ts)
                expanded[thread_ts] = replies
                logger.debug(
                    f"Expanded thread {thread_ts}: {len(replies.replies)} replies"
                )
            except Exception as e:
                logger.error(f"Failed to expand thread {thread_ts}: {e}")

        return expanded

    async def get_active_threads(
        self,
        channel_id: str,
        since_ts: Optional[str] = None,
        limit: int = 20,
    ) -> List[ThreadInfo]:
        """Get threads with recent activity in a channel.

        Args:
            channel_id: Channel to scan
            since_ts: Only threads with activity after this timestamp
            limit: Maximum threads to return

        Returns:
            List of active ThreadInfo objects
        """
        # Fetch recent messages
        try:
            data = await self.client.get_channel_history(
                channel_id=channel_id,
                oldest=since_ts,
                limit=200,  # Fetch more to find threads
            )
        except SlackAPIError as e:
            logger.error(f"Failed to get channel history: {e}")
            return []

        active_threads = []
        seen_threads = set()

        for msg_data in data.get("messages", []):
            msg = self.client.parse_message(msg_data, channel_id)

            # Check if this is a thread parent
            if msg.is_thread_parent() and msg.ts not in seen_threads:
                seen_threads.add(msg.ts)
                active_threads.append(ThreadInfo(
                    thread_ts=msg.ts,
                    channel_id=channel_id,
                    workspace_id=self.client.workspace_id,
                    reply_count=msg.reply_count,
                    reply_users_count=msg.reply_users_count,
                    parent_user_id=msg.user_id,
                    parent_text=msg.text[:500] if msg.text else None,
                    is_active=True,
                ))

            # Also check for thread replies pointing to parent
            if msg.is_thread_reply() and msg.thread_ts not in seen_threads:
                seen_threads.add(msg.thread_ts)
                # We don't have full info, create minimal entry
                active_threads.append(ThreadInfo(
                    thread_ts=msg.thread_ts,
                    channel_id=channel_id,
                    workspace_id=self.client.workspace_id,
                    is_active=True,
                ))

            if len(active_threads) >= limit:
                break

        return active_threads
