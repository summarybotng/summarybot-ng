"""
Tests for src/slack/dedup.py - Event deduplication.

Tests Slack event deduplication including TTL cache management,
concurrent event handling, and cleanup tasks.
"""

import pytest
import asyncio
import time
from unittest.mock import patch, AsyncMock

from src.slack.dedup import (
    DeduplicationEntry,
    SlackEventDeduplicator,
    get_deduplicator,
    initialize_deduplicator,
    shutdown_deduplicator,
    DEFAULT_TTL_SECONDS,
    _deduplicator,
)


class TestDeduplicationEntry:
    """Tests for DeduplicationEntry dataclass."""

    def test_should_create_entry_with_defaults(self):
        """Test entry creates with default values."""
        entry = DeduplicationEntry(event_id="Ev12345678")

        assert entry.event_id == "Ev12345678"
        assert entry.processed is False
        assert entry.processing_started is None
        assert entry.received_at > 0

    def test_should_store_event_id(self):
        """Test entry stores event ID."""
        entry = DeduplicationEntry(event_id="Ev_custom_id")

        assert entry.event_id == "Ev_custom_id"

    def test_should_record_received_time(self):
        """Test entry records received time."""
        before = time.time()
        entry = DeduplicationEntry(event_id="Ev12345678")
        after = time.time()

        assert before <= entry.received_at <= after


class TestSlackEventDeduplicator:
    """Tests for SlackEventDeduplicator class."""

    @pytest.fixture
    def deduplicator(self):
        """Create a fresh deduplicator for each test."""
        return SlackEventDeduplicator(ttl_seconds=60)

    @pytest.mark.asyncio
    async def test_should_process_new_event(self, deduplicator):
        """Test new events should be processed."""
        result = await deduplicator.should_process("Ev_new_event")

        assert result is True

    @pytest.mark.asyncio
    async def test_should_reject_duplicate_event(self, deduplicator):
        """Test duplicate events are rejected."""
        # First call creates the entry
        await deduplicator.should_process("Ev_duplicate")

        # Mark as processed
        await deduplicator.mark_processed("Ev_duplicate")

        # Second call should reject
        result = await deduplicator.should_process("Ev_duplicate")

        assert result is False

    @pytest.mark.asyncio
    async def test_should_track_processing_state(self, deduplicator):
        """Test event transitions from processing to processed."""
        event_id = "Ev_track_state"

        await deduplicator.should_process(event_id)

        # Should be in processing state
        assert event_id in deduplicator._events
        assert deduplicator._events[event_id].processed is False
        assert deduplicator._events[event_id].processing_started is not None

    @pytest.mark.asyncio
    async def test_should_mark_event_as_processed(self, deduplicator):
        """Test mark_processed updates event state."""
        event_id = "Ev_mark_processed"

        await deduplicator.should_process(event_id)
        await deduplicator.mark_processed(event_id)

        assert deduplicator._events[event_id].processed is True

    @pytest.mark.asyncio
    async def test_should_handle_mark_processed_for_unknown_event(self, deduplicator):
        """Test mark_processed ignores unknown events."""
        # Should not raise
        await deduplicator.mark_processed("Ev_unknown")

        assert "Ev_unknown" not in deduplicator._events

    @pytest.mark.asyncio
    async def test_should_remove_event_on_mark_failed(self, deduplicator):
        """Test mark_failed removes event from tracking."""
        event_id = "Ev_mark_failed"

        await deduplicator.should_process(event_id)
        await deduplicator.mark_failed(event_id)

        assert event_id not in deduplicator._events

    @pytest.mark.asyncio
    async def test_should_allow_retry_after_failure(self, deduplicator):
        """Test event can be retried after mark_failed."""
        event_id = "Ev_retry_after_fail"

        await deduplicator.should_process(event_id)
        await deduplicator.mark_failed(event_id)

        # Should be able to process again
        result = await deduplicator.should_process(event_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_should_reject_event_in_progress(self, deduplicator):
        """Test rejects event that is still being processed."""
        event_id = "Ev_in_progress"

        # First call starts processing
        await deduplicator.should_process(event_id)

        # Immediate second call should be rejected (still processing)
        result = await deduplicator.should_process(event_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_should_allow_retry_after_processing_timeout(self, deduplicator):
        """Test allows retry when previous processing timed out."""
        event_id = "Ev_timeout_retry"

        await deduplicator.should_process(event_id)

        # Simulate timeout by backdating processing_started
        deduplicator._events[event_id].processing_started = time.time() - 35  # > 30s timeout

        # Should allow retry
        result = await deduplicator.should_process(event_id)

        assert result is True

    @pytest.mark.asyncio
    async def test_should_return_stats(self, deduplicator):
        """Test get_stats returns correct counts."""
        # Add some events
        await deduplicator.should_process("Ev1")
        await deduplicator.should_process("Ev2")
        await deduplicator.mark_processed("Ev1")

        stats = await deduplicator.get_stats()

        assert stats["total_entries"] == 2
        assert stats["processed"] == 1
        assert stats["pending"] == 1


class TestDeduplicatorCleanup:
    """Tests for deduplicator cleanup functionality."""

    @pytest.mark.asyncio
    async def test_should_cleanup_expired_entries(self):
        """Test expired entries are removed during cleanup."""
        deduplicator = SlackEventDeduplicator(ttl_seconds=1)

        await deduplicator.should_process("Ev_expire")
        await deduplicator.mark_processed("Ev_expire")

        # Backdate the entry
        deduplicator._events["Ev_expire"].received_at = time.time() - 10

        # Run cleanup
        await deduplicator._cleanup_expired()

        assert "Ev_expire" not in deduplicator._events

    @pytest.mark.asyncio
    async def test_should_keep_recent_entries(self):
        """Test recent entries are kept during cleanup."""
        deduplicator = SlackEventDeduplicator(ttl_seconds=60)

        await deduplicator.should_process("Ev_recent")
        await deduplicator.mark_processed("Ev_recent")

        # Run cleanup
        await deduplicator._cleanup_expired()

        assert "Ev_recent" in deduplicator._events

    @pytest.mark.asyncio
    async def test_should_start_and_stop_cleanup_task(self):
        """Test cleanup task can be started and stopped."""
        deduplicator = SlackEventDeduplicator()

        await deduplicator.start_cleanup_task()
        assert deduplicator._cleanup_task is not None

        await deduplicator.stop_cleanup_task()
        assert deduplicator._cleanup_task is None

    @pytest.mark.asyncio
    async def test_should_handle_stop_without_start(self):
        """Test stop_cleanup_task is safe when task not started."""
        deduplicator = SlackEventDeduplicator()

        # Should not raise
        await deduplicator.stop_cleanup_task()


class TestDeduplicatorConcurrency:
    """Tests for concurrent access to deduplicator."""

    @pytest.mark.asyncio
    async def test_should_handle_concurrent_should_process_calls(self):
        """Test concurrent calls for same event only process once."""
        deduplicator = SlackEventDeduplicator()
        event_id = "Ev_concurrent"
        results = []

        async def try_process():
            result = await deduplicator.should_process(event_id)
            results.append(result)

        # Make concurrent calls
        await asyncio.gather(*[try_process() for _ in range(10)])

        # Only one should return True
        assert results.count(True) == 1
        assert results.count(False) == 9

    @pytest.mark.asyncio
    async def test_should_handle_concurrent_different_events(self):
        """Test concurrent calls for different events all process."""
        deduplicator = SlackEventDeduplicator()

        async def process_event(event_id):
            return await deduplicator.should_process(event_id)

        # Process 10 different events concurrently
        results = await asyncio.gather(
            *[process_event(f"Ev_{i}") for i in range(10)]
        )

        # All should return True
        assert all(results)
        assert len(deduplicator._events) == 10


class TestGlobalDeduplicator:
    """Tests for global deduplicator functions."""

    @pytest.fixture(autouse=True)
    def reset_global_deduplicator(self):
        """Reset global deduplicator before each test."""
        import src.slack.dedup as dedup_module
        dedup_module._deduplicator = None
        yield
        dedup_module._deduplicator = None

    def test_should_create_global_deduplicator(self):
        """Test get_deduplicator creates instance."""
        dedup = get_deduplicator()

        assert dedup is not None
        assert isinstance(dedup, SlackEventDeduplicator)

    def test_should_return_same_instance(self):
        """Test get_deduplicator returns same instance."""
        dedup1 = get_deduplicator()
        dedup2 = get_deduplicator()

        assert dedup1 is dedup2

    @pytest.mark.asyncio
    async def test_should_initialize_with_cleanup_task(self):
        """Test initialize_deduplicator starts cleanup task."""
        dedup = await initialize_deduplicator()

        assert dedup._cleanup_task is not None

        # Cleanup
        await dedup.stop_cleanup_task()

    @pytest.mark.asyncio
    async def test_should_shutdown_deduplicator(self):
        """Test shutdown_deduplicator stops and clears instance."""
        import src.slack.dedup as dedup_module

        await initialize_deduplicator()
        await shutdown_deduplicator()

        assert dedup_module._deduplicator is None


class TestDeduplicatorTTL:
    """Tests for TTL functionality."""

    def test_should_use_default_ttl(self):
        """Test default TTL is 10 minutes."""
        deduplicator = SlackEventDeduplicator()

        assert deduplicator.ttl_seconds == DEFAULT_TTL_SECONDS
        assert deduplicator.ttl_seconds == 60 * 10

    def test_should_accept_custom_ttl(self):
        """Test custom TTL can be specified."""
        deduplicator = SlackEventDeduplicator(ttl_seconds=30)

        assert deduplicator.ttl_seconds == 30

    @pytest.mark.asyncio
    async def test_should_expire_based_on_ttl(self):
        """Test entries expire based on TTL."""
        deduplicator = SlackEventDeduplicator(ttl_seconds=5)

        await deduplicator.should_process("Ev_ttl_test")

        # Backdate entry to be older than TTL
        deduplicator._events["Ev_ttl_test"].received_at = time.time() - 10

        await deduplicator._cleanup_expired()

        assert "Ev_ttl_test" not in deduplicator._events
