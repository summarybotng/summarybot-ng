"""
Tests for src/slack/thread_handler.py - Thread fetching logic.

Tests thread expansion heuristics, reply fetching,
and thread information tracking.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.slack.thread_handler import (
    ThreadInfo,
    ThreadReplies,
    SlackThreadHandler,
    MIN_REPLIES_FOR_EXPANSION,
    MAX_THREAD_AGE_DAYS,
    MAX_THREADS_PER_BATCH,
)
from src.slack.models import SlackMessage, SlackChannel
from src.slack.client import SlackClient, SlackAPIError


class TestThreadInfo:
    """Tests for ThreadInfo dataclass."""

    def test_should_create_thread_info(self):
        """Test creating ThreadInfo with required fields."""
        info = ThreadInfo(
            thread_ts="1705312800.000001",
            channel_id="C12345678",
            workspace_id="T12345678",
        )

        assert info.thread_ts == "1705312800.000001"
        assert info.channel_id == "C12345678"
        assert info.workspace_id == "T12345678"
        assert info.reply_count == 0
        assert info.is_active is True

    def test_should_store_parent_info(self):
        """Test ThreadInfo stores parent message info."""
        info = ThreadInfo(
            thread_ts="1705312800.000001",
            channel_id="C12345678",
            workspace_id="T12345678",
            parent_user_id="U11111111",
            parent_text="This is the thread parent",
        )

        assert info.parent_user_id == "U11111111"
        assert info.parent_text == "This is the thread parent"


class TestThreadReplies:
    """Tests for ThreadReplies dataclass."""

    def test_should_create_thread_replies(self):
        """Test creating ThreadReplies with info."""
        info = ThreadInfo(
            thread_ts="1705312800.000001",
            channel_id="C12345678",
            workspace_id="T12345678",
        )

        replies = ThreadReplies(info=info)

        assert replies.info is info
        assert replies.parent_message is None
        assert replies.replies == []


class TestSlackThreadHandler:
    """Tests for SlackThreadHandler class."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock SlackClient."""
        client = AsyncMock(spec=SlackClient)
        client.workspace_id = "T12345678"
        return client

    @pytest.fixture
    def handler(self, mock_client):
        """Create a thread handler with mock client."""
        return SlackThreadHandler(client=mock_client)

    def test_should_expand_thread_with_many_replies(self, handler, slack_thread_parent):
        """Test thread with 5+ replies should be expanded."""
        # slack_thread_parent has reply_count=5
        assert handler.should_expand_thread(slack_thread_parent) is True

    def test_should_not_expand_thread_with_few_replies(self, handler):
        """Test thread with few replies should not be expanded."""
        msg = SlackMessage(
            ts="1705312800.000001",
            channel_id="C12345678",
            workspace_id="T12345678",
            user_id="U11111111",
            text="Thread parent",
            thread_ts="1705312800.000001",
            reply_count=2,  # Less than MIN_REPLIES_FOR_EXPANSION
        )

        assert handler.should_expand_thread(msg) is False

    def test_should_not_expand_non_thread_message(self, handler, slack_message):
        """Test regular message should not be expanded."""
        assert handler.should_expand_thread(slack_message) is False

    def test_should_not_expand_thread_reply(self, handler, slack_thread_reply):
        """Test thread reply should not be expanded."""
        assert handler.should_expand_thread(slack_thread_reply) is False

    def test_should_expand_thread_with_files(self, handler, slack_message_with_file):
        """Test thread with files should be expanded."""
        # Make it a thread parent with files
        slack_message_with_file.thread_ts = slack_message_with_file.ts
        slack_message_with_file.reply_count = 1

        assert handler.should_expand_thread(slack_message_with_file) is True

    def test_should_expand_recent_thread_with_some_activity(self, handler):
        """Test recent thread with 2+ replies should be expanded."""
        # Create a recent thread (within MAX_THREAD_AGE_DAYS)
        recent_ts = str(int(datetime.utcnow().timestamp()))
        msg = SlackMessage(
            ts=recent_ts,
            channel_id="C12345678",
            workspace_id="T12345678",
            user_id="U11111111",
            text="Recent thread",
            thread_ts=recent_ts,
            reply_count=2,
        )

        assert handler.should_expand_thread(msg) is True

    def test_should_use_custom_min_replies(self, mock_client):
        """Test custom min_replies is respected."""
        handler = SlackThreadHandler(client=mock_client, min_replies=10)

        msg = SlackMessage(
            ts="1705312800.000001",
            channel_id="C12345678",
            workspace_id="T12345678",
            user_id="U11111111",
            text="Thread parent",
            thread_ts="1705312800.000001",
            reply_count=7,  # Less than custom 10
        )

        assert handler.should_expand_thread(msg) is False


class TestFetchThreadReplies:
    """Tests for fetching thread replies."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock SlackClient."""
        client = AsyncMock(spec=SlackClient)
        client.workspace_id = "T12345678"
        return client

    @pytest.fixture
    def handler(self, mock_client):
        """Create a thread handler with mock client."""
        return SlackThreadHandler(client=mock_client)

    @pytest.mark.asyncio
    async def test_should_fetch_thread_replies(
        self, handler, mock_client, slack_api_response_replies
    ):
        """Test fetching replies for a thread."""
        mock_client.get_thread_replies.return_value = slack_api_response_replies
        mock_client.parse_message.side_effect = lambda msg, ch: SlackMessage(
            ts=msg["ts"],
            channel_id=ch,
            workspace_id="T12345678",
            user_id=msg.get("user", ""),
            text=msg.get("text", ""),
            thread_ts=msg.get("thread_ts"),
        )

        result = await handler.fetch_thread_replies("C12345678", "1705313000.000001")

        assert isinstance(result, ThreadReplies)
        assert result.info.thread_ts == "1705313000.000001"
        assert result.info.channel_id == "C12345678"
        assert result.parent_message is not None
        assert len(result.replies) == 2  # Two replies, one parent

    @pytest.mark.asyncio
    async def test_should_handle_pagination(self, handler, mock_client):
        """Test pagination is handled for large threads."""
        # First page with cursor
        page1 = {
            "ok": True,
            "messages": [
                {"ts": "1705313000.000001", "user": "U1", "text": "Parent", "thread_ts": "1705313000.000001"},
                {"ts": "1705313100.000001", "user": "U2", "text": "Reply 1", "thread_ts": "1705313000.000001"},
            ],
            "response_metadata": {"next_cursor": "page2_cursor"},
        }
        # Second page (last)
        page2 = {
            "ok": True,
            "messages": [
                {"ts": "1705313200.000001", "user": "U3", "text": "Reply 2", "thread_ts": "1705313000.000001"},
            ],
            "response_metadata": {"next_cursor": ""},
        }

        mock_client.get_thread_replies.side_effect = [page1, page2]
        mock_client.parse_message.side_effect = lambda msg, ch: SlackMessage(
            ts=msg["ts"],
            channel_id=ch,
            workspace_id="T12345678",
            user_id=msg.get("user", ""),
            text=msg.get("text", ""),
            thread_ts=msg.get("thread_ts"),
        )

        result = await handler.fetch_thread_replies("C12345678", "1705313000.000001")

        assert len(result.replies) == 2
        assert mock_client.get_thread_replies.call_count == 2

    @pytest.mark.asyncio
    async def test_should_handle_api_error(self, handler, mock_client):
        """Test API errors are handled gracefully."""
        mock_client.get_thread_replies.side_effect = SlackAPIError("channel_not_found", "Channel not found")

        result = await handler.fetch_thread_replies("C_invalid", "1705313000.000001")

        # Should return empty replies on error
        assert len(result.replies) == 0
        assert result.parent_message is None


class TestExpandThreadsInMessages:
    """Tests for expanding threads in message batches."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock SlackClient."""
        client = AsyncMock(spec=SlackClient)
        client.workspace_id = "T12345678"
        return client

    @pytest.fixture
    def handler(self, mock_client):
        """Create a thread handler with mock client."""
        return SlackThreadHandler(client=mock_client)

    @pytest.mark.asyncio
    async def test_should_expand_eligible_threads(self, handler, mock_client):
        """Test eligible threads are expanded."""
        messages = [
            SlackMessage(
                ts="1705312800.000001",
                channel_id="C12345678",
                workspace_id="T12345678",
                user_id="U11111111",
                text="Thread 1",
                thread_ts="1705312800.000001",
                reply_count=10,  # Eligible
            ),
            SlackMessage(
                ts="1705312900.000001",
                channel_id="C12345678",
                workspace_id="T12345678",
                user_id="U22222222",
                text="Regular message",
            ),
        ]

        mock_client.get_thread_replies.return_value = {
            "ok": True,
            "messages": [
                {"ts": "1705312800.000001", "user": "U1", "text": "Parent", "thread_ts": "1705312800.000001"},
            ],
            "response_metadata": {},
        }
        mock_client.parse_message.side_effect = lambda msg, ch: SlackMessage(
            ts=msg["ts"],
            channel_id=ch,
            workspace_id="T12345678",
            user_id=msg.get("user", ""),
            text=msg.get("text", ""),
            thread_ts=msg.get("thread_ts"),
        )

        result = await handler.expand_threads_in_messages(messages, "C12345678")

        assert "1705312800.000001" in result
        assert mock_client.get_thread_replies.called

    @pytest.mark.asyncio
    async def test_should_respect_max_threads_limit(self, handler, mock_client):
        """Test max_threads limit is respected."""
        messages = [
            SlackMessage(
                ts=f"17053128{i:02d}.000001",
                channel_id="C12345678",
                workspace_id="T12345678",
                user_id="U11111111",
                text=f"Thread {i}",
                thread_ts=f"17053128{i:02d}.000001",
                reply_count=10,
            )
            for i in range(20)  # More than MAX_THREADS_PER_BATCH
        ]

        mock_client.get_thread_replies.return_value = {
            "ok": True,
            "messages": [],
            "response_metadata": {},
        }
        mock_client.parse_message.side_effect = lambda msg, ch: SlackMessage(
            ts=msg["ts"],
            channel_id=ch,
            workspace_id="T12345678",
            user_id=msg.get("user", ""),
            text=msg.get("text", ""),
            thread_ts=msg.get("thread_ts"),
        )

        result = await handler.expand_threads_in_messages(messages, "C12345678", max_threads=5)

        assert len(result) <= 5


class TestGetActiveThreads:
    """Tests for getting active threads."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock SlackClient."""
        client = AsyncMock(spec=SlackClient)
        client.workspace_id = "T12345678"
        return client

    @pytest.fixture
    def handler(self, mock_client):
        """Create a thread handler with mock client."""
        return SlackThreadHandler(client=mock_client)

    @pytest.mark.asyncio
    async def test_should_get_active_threads(self, handler, mock_client, slack_api_response_history):
        """Test getting active threads from channel."""
        mock_client.get_channel_history.return_value = slack_api_response_history
        mock_client.parse_message.side_effect = lambda msg, ch: SlackMessage(
            ts=msg["ts"],
            channel_id=ch,
            workspace_id="T12345678",
            user_id=msg.get("user", ""),
            text=msg.get("text", ""),
            thread_ts=msg.get("thread_ts"),
            reply_count=msg.get("reply_count", 0),
            reply_users_count=msg.get("reply_users_count", 0),
        )

        result = await handler.get_active_threads("C12345678")

        assert len(result) > 0
        assert all(isinstance(t, ThreadInfo) for t in result)

    @pytest.mark.asyncio
    async def test_should_handle_channel_history_error(self, handler, mock_client):
        """Test API error is handled gracefully."""
        mock_client.get_channel_history.side_effect = SlackAPIError("channel_not_found", "")

        result = await handler.get_active_threads("C_invalid")

        assert result == []

    @pytest.mark.asyncio
    async def test_should_respect_limit(self, handler, mock_client):
        """Test limit parameter is respected."""
        # Create many thread messages
        messages = [
            {"ts": f"170531280{i}.000001", "user": "U1", "text": f"Thread {i}",
             "thread_ts": f"170531280{i}.000001", "reply_count": 5}
            for i in range(30)
        ]

        mock_client.get_channel_history.return_value = {
            "ok": True,
            "messages": messages,
        }
        mock_client.parse_message.side_effect = lambda msg, ch: SlackMessage(
            ts=msg["ts"],
            channel_id=ch,
            workspace_id="T12345678",
            user_id=msg.get("user", ""),
            text=msg.get("text", ""),
            thread_ts=msg.get("thread_ts"),
            reply_count=msg.get("reply_count", 0),
        )

        result = await handler.get_active_threads("C12345678", limit=10)

        assert len(result) <= 10

    @pytest.mark.asyncio
    async def test_should_deduplicate_threads(self, handler, mock_client):
        """Test duplicate thread_ts values are deduplicated."""
        # Messages that reference the same thread
        messages = [
            {"ts": "1705312800.000001", "user": "U1", "text": "Parent", "thread_ts": "1705312800.000001", "reply_count": 3},
            {"ts": "1705312900.000001", "user": "U2", "text": "Reply", "thread_ts": "1705312800.000001"},
            {"ts": "1705313000.000001", "user": "U3", "text": "Another reply", "thread_ts": "1705312800.000001"},
        ]

        mock_client.get_channel_history.return_value = {
            "ok": True,
            "messages": messages,
        }
        mock_client.parse_message.side_effect = lambda msg, ch: SlackMessage(
            ts=msg["ts"],
            channel_id=ch,
            workspace_id="T12345678",
            user_id=msg.get("user", ""),
            text=msg.get("text", ""),
            thread_ts=msg.get("thread_ts"),
            reply_count=msg.get("reply_count", 0),
        )

        result = await handler.get_active_threads("C12345678")

        # Should only have one thread (deduplicated)
        thread_ts_values = [t.thread_ts for t in result]
        assert len(thread_ts_values) == len(set(thread_ts_values))
