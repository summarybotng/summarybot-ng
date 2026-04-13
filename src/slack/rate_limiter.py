"""
Tier-based rate limiter for Slack API (ADR-043 Section 4.2).

Slack API uses tiered rate limits per method. This module provides
a rate limiter that respects these tiers and handles Retry-After headers.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class SlackAPITier(Enum):
    """Slack API rate limit tiers.

    See: https://api.slack.com/docs/rate-limits
    """
    TIER_1 = 1  # 1 req/min (rarely used)
    TIER_2 = 2  # 20 req/min (conversations.history)
    TIER_3 = 3  # 50 req/min (most methods)
    TIER_4 = 4  # 100+ req/min (auth.test)


# Rate limits per tier (requests per minute)
TIER_LIMITS = {
    SlackAPITier.TIER_1: 1,
    SlackAPITier.TIER_2: 20,
    SlackAPITier.TIER_3: 50,
    SlackAPITier.TIER_4: 100,
}

# Map Slack API methods to their tiers
# Reference: https://api.slack.com/methods
METHOD_TIERS: Dict[str, SlackAPITier] = {
    # Tier 2 - Careful with these
    "conversations.history": SlackAPITier.TIER_2,
    "conversations.replies": SlackAPITier.TIER_2,
    "conversations.members": SlackAPITier.TIER_2,
    "files.list": SlackAPITier.TIER_2,
    "search.messages": SlackAPITier.TIER_2,

    # Tier 3 - Most methods
    "conversations.list": SlackAPITier.TIER_3,
    "conversations.info": SlackAPITier.TIER_3,
    "users.list": SlackAPITier.TIER_3,
    "users.info": SlackAPITier.TIER_3,
    "team.info": SlackAPITier.TIER_3,
    "reactions.list": SlackAPITier.TIER_3,
    "chat.postMessage": SlackAPITier.TIER_3,

    # Tier 4 - High throughput
    "auth.test": SlackAPITier.TIER_4,
}


@dataclass
class RateLimitBucket:
    """Tracks rate limit state for a specific tier."""
    tier: SlackAPITier
    tokens: float = field(default=0)
    last_update: float = field(default_factory=time.time)
    retry_after: float = 0  # Seconds until rate limit clears

    @property
    def max_tokens(self) -> int:
        """Maximum tokens (requests) for this tier."""
        return TIER_LIMITS.get(self.tier, 50)

    @property
    def refill_rate(self) -> float:
        """Tokens refilled per second."""
        return self.max_tokens / 60.0  # Convert from per-minute to per-second


class SlackRateLimiter:
    """Rate limiter for Slack API calls (ADR-043).

    Implements token bucket algorithm with per-tier tracking.
    Respects Retry-After headers from 429 responses.
    """

    def __init__(self, workspace_id: str):
        """Initialize rate limiter for a workspace.

        Args:
            workspace_id: Slack workspace ID for logging
        """
        self.workspace_id = workspace_id
        self._buckets: Dict[SlackAPITier, RateLimitBucket] = {}
        self._lock = asyncio.Lock()

        # Initialize all tier buckets
        for tier in SlackAPITier:
            self._buckets[tier] = RateLimitBucket(
                tier=tier,
                tokens=TIER_LIMITS[tier],  # Start full
            )

    def get_tier(self, method: str) -> SlackAPITier:
        """Get the rate limit tier for an API method.

        Args:
            method: Slack API method name (e.g., "conversations.history")

        Returns:
            The tier for this method (defaults to TIER_3)
        """
        return METHOD_TIERS.get(method, SlackAPITier.TIER_3)

    async def acquire(self, method: str) -> None:
        """Acquire permission to make an API call.

        Blocks until the rate limit allows the request.

        Args:
            method: Slack API method being called
        """
        tier = self.get_tier(method)

        async with self._lock:
            bucket = self._buckets[tier]

            # Refill tokens based on time passed
            now = time.time()
            elapsed = now - bucket.last_update
            bucket.tokens = min(
                bucket.max_tokens,
                bucket.tokens + (elapsed * bucket.refill_rate)
            )
            bucket.last_update = now

            # Check for active retry-after
            if bucket.retry_after > now:
                wait_time = bucket.retry_after - now
                logger.warning(
                    f"Slack rate limit active for {self.workspace_id}, "
                    f"tier={tier.name}, waiting {wait_time:.1f}s"
                )
                await asyncio.sleep(wait_time)
                bucket.retry_after = 0
                bucket.tokens = bucket.max_tokens  # Reset after retry-after

            # Wait if no tokens available
            if bucket.tokens < 1:
                wait_time = (1 - bucket.tokens) / bucket.refill_rate
                logger.debug(
                    f"Rate limit bucket empty for {self.workspace_id}, "
                    f"tier={tier.name}, waiting {wait_time:.1f}s"
                )
                await asyncio.sleep(wait_time)
                bucket.tokens = 1  # Will be decremented below

            # Consume a token
            bucket.tokens -= 1

    def record_rate_limit(self, method: str, retry_after: int) -> None:
        """Record a rate limit response from Slack.

        Call this when receiving a 429 response.

        Args:
            method: Slack API method that was rate limited
            retry_after: Seconds from Retry-After header
        """
        tier = self.get_tier(method)
        bucket = self._buckets[tier]
        bucket.retry_after = time.time() + retry_after
        bucket.tokens = 0

        logger.warning(
            f"Slack API rate limited: workspace={self.workspace_id}, "
            f"method={method}, tier={tier.name}, retry_after={retry_after}s"
        )

    def get_status(self) -> Dict[str, Dict[str, float]]:
        """Get current rate limit status for all tiers.

        Returns:
            Dict mapping tier names to their current state
        """
        return {
            tier.name: {
                "tokens": bucket.tokens,
                "max_tokens": bucket.max_tokens,
                "utilization": 1 - (bucket.tokens / bucket.max_tokens),
            }
            for tier, bucket in self._buckets.items()
        }


# Global rate limiters per workspace
_rate_limiters: Dict[str, SlackRateLimiter] = {}


def get_rate_limiter(workspace_id: str) -> SlackRateLimiter:
    """Get or create rate limiter for a workspace.

    Args:
        workspace_id: Slack workspace ID

    Returns:
        Rate limiter instance for the workspace
    """
    if workspace_id not in _rate_limiters:
        _rate_limiters[workspace_id] = SlackRateLimiter(workspace_id)
    return _rate_limiters[workspace_id]
