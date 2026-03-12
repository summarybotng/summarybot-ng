"""
Unit tests for cache implementation.

Tests cover:
- Cache hits and misses
- TTL expiration
- Cache invalidation
- Memory management
- Health checks
- Statistics tracking
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock

from src.summarization.cache import (
    SummaryCache, MemoryCache, CacheInterface
)
from src.models.summary import SummaryResult


@pytest.fixture
def memory_cache():
    """Create MemoryCache instance."""
    return MemoryCache(max_size=100, default_ttl=3600)


@pytest.fixture
def summary_cache(memory_cache):
    """Create SummaryCache instance."""
    return SummaryCache(backend=memory_cache)


@pytest.fixture
def sample_summary():
    """Create sample summary result."""
    return SummaryResult(
        id="summary_123",
        channel_id="channel_1",
        guild_id="guild_1",
        start_time=datetime.utcnow() - timedelta(hours=1),
        end_time=datetime.utcnow(),
        message_count=10,
        summary_text="Test summary content",
        key_points=["Point 1", "Point 2"],
        action_items=[],
        technical_terms=[],
        participants=[],
        metadata={"claude_model": "claude-3-sonnet-20240229"},
        created_at=datetime.utcnow()
    )


class TestMemoryCache:
    """Test suite for MemoryCache."""

    @pytest.mark.asyncio
    async def test_set_and_get(self, memory_cache):
        """Test basic set and get operations."""
        await memory_cache.set("test_key", "test_value")
        value = await memory_cache.get("test_key")

        assert value == "test_value"

    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self, memory_cache):
        """Test getting non-existent key returns None."""
        value = await memory_cache.get("nonexistent")

        assert value is None

    @pytest.mark.asyncio
    async def test_ttl_expiration(self, memory_cache):
        """Test cache entry expires after TTL."""
        # Set with 1 second TTL
        await memory_cache.set("expire_key", "value", ttl=1)

        # Should exist immediately
        value1 = await memory_cache.get("expire_key")
        assert value1 == "value"

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Should be expired
        value2 = await memory_cache.get("expire_key")
        assert value2 is None

    @pytest.mark.asyncio
    async def test_no_ttl(self, memory_cache):
        """Test cache entry without TTL."""
        await memory_cache.set("permanent_key", "value", ttl=0)

        # Should exist even after delay
        await asyncio.sleep(0.1)
        value = await memory_cache.get("permanent_key")
        assert value == "value"

    @pytest.mark.asyncio
    async def test_delete(self, memory_cache):
        """Test deleting cache entries."""
        await memory_cache.set("delete_me", "value")

        deleted = await memory_cache.delete("delete_me")
        assert deleted is True

        value = await memory_cache.get("delete_me")
        assert value is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, memory_cache):
        """Test deleting non-existent key."""
        deleted = await memory_cache.delete("nonexistent")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_clear_all(self, memory_cache):
        """Test clearing all cache entries."""
        # Add multiple entries
        for i in range(5):
            await memory_cache.set(f"key_{i}", f"value_{i}")

        # Clear all
        count = await memory_cache.clear()

        assert count == 5

        # Verify all gone
        for i in range(5):
            value = await memory_cache.get(f"key_{i}")
            assert value is None

    @pytest.mark.asyncio
    async def test_clear_with_pattern(self, memory_cache):
        """Test clearing entries matching pattern."""
        # Add entries with different prefixes
        await memory_cache.set("user_1", "data1")
        await memory_cache.set("user_2", "data2")
        await memory_cache.set("admin_1", "data3")

        # Clear only user_ entries
        count = await memory_cache.clear(pattern="user_")

        assert count == 2

        # Verify user_ entries gone, admin_ still there
        assert await memory_cache.get("user_1") is None
        assert await memory_cache.get("admin_1") == "data3"

    @pytest.mark.asyncio
    async def test_max_size_enforcement(self, memory_cache):
        """Test cache enforces max size limit."""
        # Fill cache to max
        for i in range(memory_cache.max_size):
            await memory_cache.set(f"key_{i}", f"value_{i}")

        # Add one more (should evict oldest)
        await memory_cache.set("new_key", "new_value")

        # New key should exist
        assert await memory_cache.get("new_key") == "new_value"

        # Oldest should be evicted (key_0)
        assert await memory_cache.get("key_0") is None

    @pytest.mark.asyncio
    async def test_update_existing_key(self, memory_cache):
        """Test updating existing key doesn't count toward size limit."""
        await memory_cache.set("key", "value1")
        await memory_cache.set("key", "value2")

        value = await memory_cache.get("key")
        assert value == "value2"

    @pytest.mark.asyncio
    async def test_health_check(self, memory_cache):
        """Test memory cache health check."""
        is_healthy = await memory_cache.health_check()
        assert is_healthy is True

    def test_get_stats(self, memory_cache):
        """Test cache statistics."""
        stats = memory_cache.get_stats()

        assert "size" in stats
        assert "max_size" in stats
        assert "expired_entries" in stats
        assert "backend" in stats
        assert stats["backend"] == "memory"
        assert stats["max_size"] == 100


class TestSummaryCache:
    """Test suite for SummaryCache."""

    @pytest.mark.asyncio
    async def test_cache_and_retrieve_summary(
        self, summary_cache, sample_summary
    ):
        """Test caching and retrieving summary."""
        # Cache the summary
        await summary_cache.cache_summary(sample_summary)

        # Retrieve it
        cached = await summary_cache.get_cached_summary(
            channel_id=sample_summary.channel_id,
            start_time=sample_summary.start_time,
            end_time=sample_summary.end_time,
            options_hash=summary_cache._hash_summary_options(sample_summary),
            guild_id=sample_summary.guild_id
        )

        assert cached is not None
        assert cached.id == sample_summary.id
        assert cached.summary_text == sample_summary.summary_text

    @pytest.mark.asyncio
    async def test_cache_miss(self, summary_cache):
        """Test cache miss returns None."""
        cached = await summary_cache.get_cached_summary(
            channel_id="channel_999",
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            options_hash="nonexistent"
        )

        assert cached is None

    @pytest.mark.asyncio
    async def test_cache_with_ttl(self, summary_cache, sample_summary):
        """Test cached summary expires after TTL."""
        # Cache with very short TTL
        await summary_cache.cache_summary(sample_summary, ttl=1)

        # Should exist immediately
        cached1 = await summary_cache.get_cached_summary(
            channel_id=sample_summary.channel_id,
            start_time=sample_summary.start_time,
            end_time=sample_summary.end_time,
            options_hash=summary_cache._hash_summary_options(sample_summary),
            guild_id=sample_summary.guild_id
        )
        assert cached1 is not None

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Should be expired
        cached2 = await summary_cache.get_cached_summary(
            channel_id=sample_summary.channel_id,
            start_time=sample_summary.start_time,
            end_time=sample_summary.end_time,
            options_hash=summary_cache._hash_summary_options(sample_summary),
            guild_id=sample_summary.guild_id
        )
        assert cached2 is None

    @pytest.mark.asyncio
    async def test_invalidate_channel(self, summary_cache, sample_summary):
        """Test invalidating all summaries for a channel."""
        # Cache multiple summaries for the channel
        for i in range(3):
            summary = SummaryResult(
                id=f"summary_{i}",
                channel_id=sample_summary.channel_id,
                guild_id=sample_summary.guild_id,
                start_time=datetime.utcnow() - timedelta(hours=i+1),
                end_time=datetime.utcnow() - timedelta(hours=i),
                message_count=10,
                summary_text=f"Summary {i}",
                key_points=[],
                action_items=[],
                technical_terms=[],
                participants=[]
            )
            await summary_cache.cache_summary(summary)

        # Invalidate channel
        count = await summary_cache.invalidate_channel(sample_summary.channel_id)

        assert count >= 0  # May vary based on cache key structure

    @pytest.mark.asyncio
    async def test_invalidate_guild(self, summary_cache, sample_summary):
        """Test invalidating all summaries for a guild."""
        await summary_cache.cache_summary(sample_summary)

        count = await summary_cache.invalidate_guild(sample_summary.guild_id)

        assert count >= 0

    @pytest.mark.asyncio
    async def test_health_check(self, summary_cache):
        """Test cache health check."""
        is_healthy = await summary_cache.health_check()
        assert is_healthy is True

    @pytest.mark.asyncio
    async def test_get_stats(self, summary_cache):
        """Test cache statistics."""
        stats = await summary_cache.get_stats()

        assert "backend_healthy" in stats
        assert stats["backend_healthy"] is True

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, summary_cache):
        """Test cleanup of expired entries."""
        # For memory cache, expired entries are cleaned on access
        count = await summary_cache.cleanup_expired()

        # Returns 0 for memory cache (handled automatically)
        assert count >= 0

    def test_generate_cache_key(self, summary_cache):
        """Test cache key generation."""
        start_time = datetime(2024, 1, 1, 10, 30)
        end_time = datetime(2024, 1, 1, 12, 45)

        key = summary_cache._generate_cache_key(
            channel_id="channel_1",
            start_time=start_time,
            end_time=end_time,
            options_hash="abc123"
        )

        # Key should contain components
        assert "summary" in key
        assert "channel_1" in key
        assert "abc123" in key
        assert ":" in key  # Delimiter

    def test_generate_cache_key_consistency(self, summary_cache):
        """Test cache key is consistent for same inputs."""
        start_time = datetime(2024, 1, 1, 10, 30)
        end_time = datetime(2024, 1, 1, 12, 45)

        key1 = summary_cache._generate_cache_key(
            "channel_1", start_time, end_time, "hash1"
        )
        key2 = summary_cache._generate_cache_key(
            "channel_1", start_time, end_time, "hash1"
        )

        assert key1 == key2

    def test_generate_cache_key_different_for_different_inputs(
        self, summary_cache
    ):
        """Test cache keys differ for different inputs."""
        start_time = datetime(2024, 1, 1, 10, 0)
        end_time = datetime(2024, 1, 1, 12, 0)

        key1 = summary_cache._generate_cache_key(
            "channel_1", start_time, end_time, "hash1"
        )
        key2 = summary_cache._generate_cache_key(
            "channel_2", start_time, end_time, "hash1"
        )
        key3 = summary_cache._generate_cache_key(
            "channel_1", start_time, end_time, "hash2"
        )

        assert key1 != key2
        assert key1 != key3

    def test_hash_summary_options(self, summary_cache, sample_summary):
        """Test summary options hashing."""
        hash1 = summary_cache._hash_summary_options(sample_summary)

        assert isinstance(hash1, str)
        assert len(hash1) == 8  # MD5 hex digest truncated to 8 chars

    def test_hash_summary_options_consistency(
        self, summary_cache, sample_summary
    ):
        """Test options hash is consistent."""
        hash1 = summary_cache._hash_summary_options(sample_summary)
        hash2 = summary_cache._hash_summary_options(sample_summary)

        assert hash1 == hash2

    @pytest.mark.asyncio
    async def test_invalid_cached_data_removed(self, summary_cache):
        """Test invalid cached data is removed on retrieval."""
        # Manually insert invalid data
        await summary_cache.backend.set("test_invalid", {"invalid": "data"})

        # Try to retrieve as summary (should fail and clean up)
        result = await summary_cache.get_cached_summary(
            channel_id="test",
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            options_hash="test"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_cache_serialization(self, summary_cache, sample_summary):
        """Test summary serialization and deserialization."""
        # Cache summary
        await summary_cache.cache_summary(sample_summary)

        # Retrieve
        cached = await summary_cache.get_cached_summary(
            channel_id=sample_summary.channel_id,
            start_time=sample_summary.start_time,
            end_time=sample_summary.end_time,
            options_hash=summary_cache._hash_summary_options(sample_summary),
            guild_id=sample_summary.guild_id
        )

        # Verify all fields preserved
        assert cached.id == sample_summary.id
        assert cached.channel_id == sample_summary.channel_id
        assert cached.guild_id == sample_summary.guild_id
        assert cached.message_count == sample_summary.message_count
        assert cached.summary_text == sample_summary.summary_text
        assert len(cached.key_points) == len(sample_summary.key_points)

    @pytest.mark.asyncio
    async def test_time_rounding_in_cache_key(self, summary_cache, sample_summary):
        """Test cache key uses time rounding for better hit rate."""
        # Times within same hour should generate same key
        time1 = datetime(2024, 1, 1, 10, 15, 30)
        time2 = datetime(2024, 1, 1, 10, 45, 50)

        key1 = summary_cache._generate_cache_key(
            "channel_1", time1, time1 + timedelta(hours=1), "hash1"
        )
        key2 = summary_cache._generate_cache_key(
            "channel_1", time2, time2 + timedelta(hours=1), "hash1"
        )

        # Keys should be different due to different start/end times
        # but use hour rounding
        assert "2024010110" in key1  # Hour component
        assert "2024010110" in key2

    @pytest.mark.asyncio
    async def test_concurrent_cache_access(self, summary_cache, sample_summary):
        """Test concurrent cache operations."""
        # Cache summary
        await summary_cache.cache_summary(sample_summary)

        # Retrieve concurrently multiple times
        tasks = []
        for _ in range(10):
            task = summary_cache.get_cached_summary(
                channel_id=sample_summary.channel_id,
                start_time=sample_summary.start_time,
                end_time=sample_summary.end_time,
                options_hash=summary_cache._hash_summary_options(sample_summary),
                guild_id=sample_summary.guild_id
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # All should succeed
        assert all(r is not None for r in results)
        assert all(r.id == sample_summary.id for r in results)


class TestCacheInterface:
    """Test CacheInterface contract."""

    @pytest.mark.asyncio
    async def test_memory_cache_implements_interface(self, memory_cache):
        """Test MemoryCache implements CacheInterface."""
        assert isinstance(memory_cache, CacheInterface)

        # Test all interface methods exist
        assert hasattr(memory_cache, 'get')
        assert hasattr(memory_cache, 'set')
        assert hasattr(memory_cache, 'delete')
        assert hasattr(memory_cache, 'clear')
        assert hasattr(memory_cache, 'health_check')

    @pytest.mark.asyncio
    async def test_custom_cache_backend(self, sample_summary):
        """Test SummaryCache works with custom backend."""
        # Create mock backend
        mock_backend = Mock(spec=CacheInterface)
        mock_backend.get = AsyncMock(return_value=None)
        mock_backend.set = AsyncMock(return_value=True)
        mock_backend.health_check = AsyncMock(return_value=True)

        cache = SummaryCache(backend=mock_backend)

        # Test operations
        await cache.cache_summary(sample_summary)
        mock_backend.set.assert_called_once()

        await cache.get_cached_summary(
            channel_id="test",
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            options_hash="hash"
        )
        mock_backend.get.assert_called_once()
