"""
Slack event deduplication (ADR-043 Section 5.2).

Handles deduplication of Slack Events API messages to prevent
duplicate processing when Slack retries delivery.
"""

import asyncio
import logging
import time
from typing import Dict, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Default TTL for dedup entries (10 minutes)
DEFAULT_TTL_SECONDS = 60 * 10


@dataclass
class DeduplicationEntry:
    """Tracks a processed event for deduplication."""
    event_id: str
    received_at: float = field(default_factory=time.time)
    processed: bool = False
    processing_started: Optional[float] = None


class SlackEventDeduplicator:
    """In-memory event deduplication with TTL expiration.

    Slack may retry event delivery if we don't respond quickly enough.
    This deduplicator ensures each event is processed only once.

    For production, consider using Redis for distributed deduplication
    across multiple instances.
    """

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        """Initialize deduplicator.

        Args:
            ttl_seconds: Time-to-live for dedup entries
        """
        self.ttl_seconds = ttl_seconds
        self._events: Dict[str, DeduplicationEntry] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start_cleanup_task(self):
        """Start background cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup_task(self):
        """Stop background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def _cleanup_loop(self):
        """Periodically clean up expired entries."""
        while True:
            try:
                await asyncio.sleep(60)  # Run every minute
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in dedup cleanup: {e}")

    async def _cleanup_expired(self):
        """Remove entries older than TTL."""
        cutoff = time.time() - self.ttl_seconds
        async with self._lock:
            expired = [
                event_id for event_id, entry in self._events.items()
                if entry.received_at < cutoff
            ]
            for event_id in expired:
                del self._events[event_id]

            if expired:
                logger.debug(f"Cleaned up {len(expired)} expired dedup entries")

    async def should_process(self, event_id: str) -> bool:
        """Check if an event should be processed.

        Returns True if this is a new event or if the previous processing
        attempt appears to have failed (no completion within timeout).

        Args:
            event_id: Slack event ID (from event envelope)

        Returns:
            True if event should be processed, False if duplicate
        """
        async with self._lock:
            if event_id not in self._events:
                # New event
                self._events[event_id] = DeduplicationEntry(
                    event_id=event_id,
                    processing_started=time.time(),
                )
                return True

            entry = self._events[event_id]

            # Already processed successfully
            if entry.processed:
                logger.debug(f"Duplicate event {event_id} (already processed)")
                return False

            # Check if previous processing attempt timed out (30 seconds)
            if entry.processing_started:
                elapsed = time.time() - entry.processing_started
                if elapsed > 30:
                    # Previous attempt likely failed, allow retry
                    logger.warning(
                        f"Retrying event {event_id} after {elapsed:.1f}s "
                        "since previous attempt"
                    )
                    entry.processing_started = time.time()
                    return True

            # Still processing or recently attempted
            logger.debug(f"Duplicate event {event_id} (processing in progress)")
            return False

    async def mark_processed(self, event_id: str):
        """Mark an event as successfully processed.

        Args:
            event_id: Slack event ID
        """
        async with self._lock:
            if event_id in self._events:
                self._events[event_id].processed = True

    async def mark_failed(self, event_id: str):
        """Mark an event processing as failed.

        This allows the event to be retried on the next delivery.

        Args:
            event_id: Slack event ID
        """
        async with self._lock:
            if event_id in self._events:
                del self._events[event_id]

    async def get_stats(self) -> Dict[str, int]:
        """Get deduplication statistics.

        Returns:
            Dict with total, processed, and pending counts
        """
        async with self._lock:
            total = len(self._events)
            processed = sum(1 for e in self._events.values() if e.processed)
            return {
                "total_entries": total,
                "processed": processed,
                "pending": total - processed,
            }


# Global deduplicator instance
_deduplicator: Optional[SlackEventDeduplicator] = None


def get_deduplicator() -> SlackEventDeduplicator:
    """Get or create the global deduplicator instance."""
    global _deduplicator
    if _deduplicator is None:
        _deduplicator = SlackEventDeduplicator()
    return _deduplicator


async def initialize_deduplicator():
    """Initialize and start the global deduplicator."""
    dedup = get_deduplicator()
    await dedup.start_cleanup_task()
    return dedup


async def shutdown_deduplicator():
    """Shut down the global deduplicator."""
    global _deduplicator
    if _deduplicator:
        await _deduplicator.stop_cleanup_task()
        _deduplicator = None
