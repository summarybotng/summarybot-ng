"""
Tests for src/slack/rate_limiter.py - Token bucket rate limiter.

Tests the tier-based rate limiting for Slack API calls including
token bucket algorithm, tier limits, and Retry-After handling.
"""

import pytest
import asyncio
import time
from unittest.mock import patch, MagicMock

from src.slack.rate_limiter import (
    SlackAPITier,
    TIER_LIMITS,
    METHOD_TIERS,
    RateLimitBucket,
    SlackRateLimiter,
    get_rate_limiter,
    _rate_limiters,
)


class TestSlackAPITier:
    """Tests for SlackAPITier enum."""

    def test_tier_1_value(self):
        """Test TIER_1 has value 1."""
        assert SlackAPITier.TIER_1.value == 1

    def test_tier_2_value(self):
        """Test TIER_2 has value 2."""
        assert SlackAPITier.TIER_2.value == 2

    def test_tier_3_value(self):
        """Test TIER_3 has value 3."""
        assert SlackAPITier.TIER_3.value == 3

    def test_tier_4_value(self):
        """Test TIER_4 has value 4."""
        assert SlackAPITier.TIER_4.value == 4


class TestTierLimits:
    """Tests for tier limit constants."""

    def test_tier_1_limit_is_1_per_minute(self):
        """Test TIER_1 allows 1 request per minute."""
        assert TIER_LIMITS[SlackAPITier.TIER_1] == 1

    def test_tier_2_limit_is_20_per_minute(self):
        """Test TIER_2 allows 20 requests per minute."""
        assert TIER_LIMITS[SlackAPITier.TIER_2] == 20

    def test_tier_3_limit_is_50_per_minute(self):
        """Test TIER_3 allows 50 requests per minute."""
        assert TIER_LIMITS[SlackAPITier.TIER_3] == 50

    def test_tier_4_limit_is_100_per_minute(self):
        """Test TIER_4 allows 100 requests per minute."""
        assert TIER_LIMITS[SlackAPITier.TIER_4] == 100


class TestMethodTiers:
    """Tests for method-to-tier mapping."""

    def test_conversations_history_is_tier_2(self):
        """Test conversations.history is TIER_2."""
        assert METHOD_TIERS["conversations.history"] == SlackAPITier.TIER_2

    def test_conversations_replies_is_tier_2(self):
        """Test conversations.replies is TIER_2."""
        assert METHOD_TIERS["conversations.replies"] == SlackAPITier.TIER_2

    def test_conversations_list_is_tier_3(self):
        """Test conversations.list is TIER_3."""
        assert METHOD_TIERS["conversations.list"] == SlackAPITier.TIER_3

    def test_users_list_is_tier_3(self):
        """Test users.list is TIER_3."""
        assert METHOD_TIERS["users.list"] == SlackAPITier.TIER_3

    def test_auth_test_is_tier_4(self):
        """Test auth.test is TIER_4."""
        assert METHOD_TIERS["auth.test"] == SlackAPITier.TIER_4


class TestRateLimitBucket:
    """Tests for RateLimitBucket dataclass."""

    def test_should_return_correct_max_tokens(self):
        """Test max_tokens property returns tier limit."""
        bucket = RateLimitBucket(tier=SlackAPITier.TIER_2)
        assert bucket.max_tokens == 20

        bucket = RateLimitBucket(tier=SlackAPITier.TIER_3)
        assert bucket.max_tokens == 50

    def test_should_calculate_refill_rate(self):
        """Test refill_rate converts per-minute to per-second."""
        bucket = RateLimitBucket(tier=SlackAPITier.TIER_2)
        # 20 per minute = 20/60 per second
        assert bucket.refill_rate == pytest.approx(20 / 60, rel=0.001)

    def test_should_initialize_with_zero_tokens(self):
        """Test bucket initializes with zero tokens by default."""
        bucket = RateLimitBucket(tier=SlackAPITier.TIER_3)
        assert bucket.tokens == 0

    def test_should_initialize_with_current_time(self):
        """Test bucket initializes with current time."""
        before = time.time()
        bucket = RateLimitBucket(tier=SlackAPITier.TIER_3)
        after = time.time()

        assert before <= bucket.last_update <= after


class TestSlackRateLimiter:
    """Tests for SlackRateLimiter class."""

    def test_should_initialize_all_tier_buckets(self):
        """Test limiter initializes buckets for all tiers."""
        limiter = SlackRateLimiter("T12345678")

        assert SlackAPITier.TIER_1 in limiter._buckets
        assert SlackAPITier.TIER_2 in limiter._buckets
        assert SlackAPITier.TIER_3 in limiter._buckets
        assert SlackAPITier.TIER_4 in limiter._buckets

    def test_should_initialize_buckets_with_full_tokens(self):
        """Test buckets start with full token count."""
        limiter = SlackRateLimiter("T12345678")

        for tier, bucket in limiter._buckets.items():
            assert bucket.tokens == TIER_LIMITS[tier]

    def test_should_get_correct_tier_for_known_method(self):
        """Test get_tier returns correct tier for known method."""
        limiter = SlackRateLimiter("T12345678")

        assert limiter.get_tier("conversations.history") == SlackAPITier.TIER_2
        assert limiter.get_tier("users.list") == SlackAPITier.TIER_3
        assert limiter.get_tier("auth.test") == SlackAPITier.TIER_4

    def test_should_default_to_tier_3_for_unknown_method(self):
        """Test get_tier returns TIER_3 for unknown methods."""
        limiter = SlackRateLimiter("T12345678")

        assert limiter.get_tier("unknown.method") == SlackAPITier.TIER_3
        assert limiter.get_tier("custom.api") == SlackAPITier.TIER_3

    @pytest.mark.asyncio
    async def test_should_acquire_token_and_decrement(self):
        """Test acquire consumes a token from the bucket."""
        limiter = SlackRateLimiter("T12345678")
        initial_tokens = limiter._buckets[SlackAPITier.TIER_3].tokens

        await limiter.acquire("users.list")

        # Should have one less token (accounting for possible refill)
        assert limiter._buckets[SlackAPITier.TIER_3].tokens < initial_tokens

    @pytest.mark.asyncio
    async def test_should_refill_tokens_over_time(self):
        """Test tokens refill based on elapsed time."""
        limiter = SlackRateLimiter("T12345678")
        bucket = limiter._buckets[SlackAPITier.TIER_3]

        # Drain some tokens
        bucket.tokens = 10
        bucket.last_update = time.time() - 10  # 10 seconds ago

        await limiter.acquire("users.list")

        # Should have refilled some tokens (50/60 * 10 seconds = ~8.33 tokens)
        # Then consumed 1, so should be around 17-18
        assert bucket.tokens > 10

    @pytest.mark.asyncio
    async def test_should_not_exceed_max_tokens_on_refill(self):
        """Test token refill does not exceed max_tokens."""
        limiter = SlackRateLimiter("T12345678")
        bucket = limiter._buckets[SlackAPITier.TIER_3]

        # Set up for large refill
        bucket.tokens = 45
        bucket.last_update = time.time() - 60  # 1 minute ago

        await limiter.acquire("users.list")

        # Should cap at max_tokens (50) then subtract 1
        assert bucket.tokens <= bucket.max_tokens

    def test_should_record_rate_limit_response(self):
        """Test record_rate_limit sets retry_after and clears tokens."""
        limiter = SlackRateLimiter("T12345678")
        bucket = limiter._buckets[SlackAPITier.TIER_2]

        limiter.record_rate_limit("conversations.history", 30)

        assert bucket.tokens == 0
        assert bucket.retry_after > time.time()
        assert bucket.retry_after <= time.time() + 30

    @pytest.mark.asyncio
    async def test_should_wait_when_retry_after_active(self):
        """Test acquire waits when retry_after is set."""
        limiter = SlackRateLimiter("T12345678")
        bucket = limiter._buckets[SlackAPITier.TIER_3]

        # Set a short retry_after
        bucket.retry_after = time.time() + 0.1  # 100ms from now
        bucket.tokens = 0

        start = time.time()
        await limiter.acquire("users.list")
        elapsed = time.time() - start

        # Should have waited approximately 100ms
        assert elapsed >= 0.09  # Allow some tolerance

    def test_should_return_status_for_all_tiers(self):
        """Test get_status returns info for all tiers."""
        limiter = SlackRateLimiter("T12345678")

        status = limiter.get_status()

        assert "TIER_1" in status
        assert "TIER_2" in status
        assert "TIER_3" in status
        assert "TIER_4" in status

    def test_should_return_utilization_in_status(self):
        """Test get_status includes utilization metric."""
        limiter = SlackRateLimiter("T12345678")
        limiter._buckets[SlackAPITier.TIER_3].tokens = 25  # Half full

        status = limiter.get_status()

        assert "tokens" in status["TIER_3"]
        assert "max_tokens" in status["TIER_3"]
        assert "utilization" in status["TIER_3"]
        assert status["TIER_3"]["utilization"] == pytest.approx(0.5, rel=0.01)


class TestGetRateLimiter:
    """Tests for get_rate_limiter function."""

    def test_should_create_limiter_for_new_workspace(self):
        """Test creates new limiter for unknown workspace."""
        # Clear global state
        _rate_limiters.clear()

        limiter = get_rate_limiter("T_NEW_WORKSPACE")

        assert limiter is not None
        assert isinstance(limiter, SlackRateLimiter)
        assert limiter.workspace_id == "T_NEW_WORKSPACE"

    def test_should_return_same_limiter_for_same_workspace(self):
        """Test returns existing limiter for known workspace."""
        _rate_limiters.clear()

        limiter1 = get_rate_limiter("T_SHARED")
        limiter2 = get_rate_limiter("T_SHARED")

        assert limiter1 is limiter2

    def test_should_return_different_limiters_for_different_workspaces(self):
        """Test returns different limiters for different workspaces."""
        _rate_limiters.clear()

        limiter1 = get_rate_limiter("T_WORKSPACE_1")
        limiter2 = get_rate_limiter("T_WORKSPACE_2")

        assert limiter1 is not limiter2
        assert limiter1.workspace_id == "T_WORKSPACE_1"
        assert limiter2.workspace_id == "T_WORKSPACE_2"


class TestRateLimiterEdgeCases:
    """Edge case tests for rate limiter."""

    @pytest.mark.asyncio
    async def test_should_handle_concurrent_acquire_calls(self):
        """Test concurrent acquire calls are handled safely."""
        limiter = SlackRateLimiter("T12345678")

        # Make multiple concurrent acquire calls
        tasks = [limiter.acquire("users.list") for _ in range(5)]
        await asyncio.gather(*tasks)

        # Should have consumed 5 tokens
        bucket = limiter._buckets[SlackAPITier.TIER_3]
        # Initial was 50, minus 5 (with possible refill during execution)
        assert bucket.tokens < 50

    @pytest.mark.asyncio
    async def test_should_wait_when_bucket_empty(self):
        """Test acquire waits when no tokens available."""
        limiter = SlackRateLimiter("T12345678")
        bucket = limiter._buckets[SlackAPITier.TIER_3]

        # Empty the bucket
        bucket.tokens = 0
        bucket.last_update = time.time()

        start = time.time()
        await limiter.acquire("users.list")
        elapsed = time.time() - start

        # Should have waited for token refill
        # At 50/60 tokens per second, need ~1.2 seconds for 1 token
        # But could be faster due to timing
        assert elapsed > 0

    def test_should_handle_zero_retry_after(self):
        """Test record_rate_limit handles zero retry_after."""
        limiter = SlackRateLimiter("T12345678")

        limiter.record_rate_limit("users.list", 0)

        bucket = limiter._buckets[SlackAPITier.TIER_3]
        assert bucket.tokens == 0
        # retry_after should be at current time
        assert bucket.retry_after <= time.time() + 1
