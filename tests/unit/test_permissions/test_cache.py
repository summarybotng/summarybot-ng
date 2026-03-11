"""
Unit tests for permissions/cache.py.

Tests CacheEntry and PermissionCache.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch

from src.permissions.cache import CacheEntry, PermissionCache


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_create_entry(self):
        """Create a basic cache entry."""
        entry = CacheEntry(key="test_key", value="test_value")

        assert entry.key == "test_key"
        assert entry.value == "test_value"
        assert entry.access_count == 0
        assert entry.expires_at is None

    def test_create_entry_with_expiration(self):
        """Create entry with expiration time."""
        expires = datetime.utcnow() + timedelta(hours=1)
        entry = CacheEntry(
            key="test_key",
            value="test_value",
            expires_at=expires
        )

        assert entry.expires_at == expires
        assert entry.is_expired() is False

    def test_is_expired_true(self):
        """Entry past expiration is expired."""
        expires = datetime.utcnow() - timedelta(hours=1)
        entry = CacheEntry(
            key="test_key",
            value="test_value",
            expires_at=expires
        )

        assert entry.is_expired() is True

    def test_is_expired_no_expiration(self):
        """Entry without expiration never expires."""
        entry = CacheEntry(key="test_key", value="test_value")

        assert entry.is_expired() is False

    def test_access_updates_stats(self):
        """Accessing entry updates access count and time."""
        entry = CacheEntry(key="test_key", value="test_value")
        original_time = entry.last_accessed

        # Small delay to ensure time difference
        import time
        time.sleep(0.01)

        result = entry.access()

        assert result == "test_value"
        assert entry.access_count == 1
        assert entry.last_accessed >= original_time

    def test_multiple_accesses(self):
        """Multiple accesses increment count."""
        entry = CacheEntry(key="test_key", value="test_value")

        entry.access()
        entry.access()
        entry.access()

        assert entry.access_count == 3

    def test_to_dict(self):
        """to_dict serializes entry correctly."""
        entry = CacheEntry(
            key="test_key",
            value={"complex": "value"},
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )

        d = entry.to_dict()

        assert d["key"] == "test_key"
        assert "complex" in d["value"]
        assert d["access_count"] == 0
        assert d["expires_at"] is not None


class TestPermissionCache:
    """Tests for PermissionCache class."""

    @pytest.fixture
    def cache(self):
        """Create a fresh PermissionCache instance."""
        return PermissionCache(ttl=3600, max_size=100)

    @pytest.mark.asyncio
    async def test_set_and_get(self, cache):
        """Can set and retrieve values."""
        await cache.set("key1", "value1")
        result = await cache.get("key1")

        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, cache):
        """Getting nonexistent key returns None."""
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_expired(self, cache):
        """Getting expired entry returns None."""
        # Set with very short TTL
        await cache.set("key1", "value1", ttl=0)

        # Wait a moment for expiration
        await asyncio.sleep(0.01)

        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_custom_ttl(self, cache):
        """Can set custom TTL per entry."""
        await cache.set("key1", "value1", ttl=1)

        # Should still be there
        result = await cache.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_delete_existing(self, cache):
        """Can delete existing key."""
        await cache.set("key1", "value1")
        deleted = await cache.delete("key1")

        assert deleted is True
        assert await cache.get("key1") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, cache):
        """Deleting nonexistent key returns False."""
        deleted = await cache.delete("nonexistent")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_invalidate_pattern_wildcard(self, cache):
        """Can invalidate by wildcard pattern."""
        await cache.set("user:123:perm1", "value1")
        await cache.set("user:123:perm2", "value2")
        await cache.set("user:456:perm1", "value3")

        count = await cache.invalidate_pattern("user:123:*")

        assert count == 2
        assert await cache.get("user:123:perm1") is None
        assert await cache.get("user:123:perm2") is None
        assert await cache.get("user:456:perm1") == "value3"

    @pytest.mark.asyncio
    async def test_invalidate_pattern_all(self, cache):
        """Can invalidate all entries with *."""
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")

        count = await cache.invalidate_pattern("*")

        assert count == 2
        assert len(cache) == 0

    @pytest.mark.asyncio
    async def test_clear(self, cache):
        """Can clear all entries."""
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")

        await cache.clear()

        assert len(cache) == 0

    @pytest.mark.asyncio
    async def test_eviction_on_max_size(self):
        """LRU eviction happens when max_size is reached."""
        cache = PermissionCache(ttl=3600, max_size=3)

        await cache.set("key1", "value1")
        await asyncio.sleep(0.01)
        await cache.set("key2", "value2")
        await asyncio.sleep(0.01)
        await cache.set("key3", "value3")

        # Access key1 to make it more recently used
        await cache.get("key1")

        # Add fourth entry - should evict key2 (LRU)
        await cache.set("key4", "value4")

        assert len(cache) == 3
        assert await cache.get("key1") is not None
        assert await cache.get("key3") is not None
        assert await cache.get("key4") is not None

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, cache):
        """cleanup_expired removes all expired entries."""
        # Set entries with very short TTL
        await cache.set("key1", "value1", ttl=0)
        await cache.set("key2", "value2", ttl=0)
        await cache.set("key3", "value3", ttl=3600)  # Not expired

        # Wait for expiration
        await asyncio.sleep(0.01)

        count = await cache.cleanup_expired()

        assert count == 2
        assert await cache.get("key3") == "value3"

    def test_get_stats(self, cache):
        """get_stats returns correct statistics."""
        stats = cache.get_stats()

        assert stats["size"] == 0
        assert stats["max_size"] == 100
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["ttl"] == 3600

    @pytest.mark.asyncio
    async def test_stats_tracking(self, cache):
        """Stats track hits and misses correctly."""
        await cache.set("key1", "value1")

        # Hit
        await cache.get("key1")
        # Miss
        await cache.get("nonexistent")

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert "50.00%" in stats["hit_rate"]

    def test_reset_stats(self, cache):
        """reset_stats clears hit/miss counters."""
        cache._hits = 10
        cache._misses = 5

        cache.reset_stats()

        assert cache._hits == 0
        assert cache._misses == 0

    @pytest.mark.asyncio
    async def test_get_entry_info(self, cache):
        """Can get detailed info about an entry."""
        await cache.set("key1", "value1")

        info = await cache.get_entry_info("key1")

        assert info is not None
        assert info["key"] == "key1"
        assert "created_at" in info
        assert "expires_at" in info

    @pytest.mark.asyncio
    async def test_get_entry_info_nonexistent(self, cache):
        """get_entry_info returns None for nonexistent key."""
        info = await cache.get_entry_info("nonexistent")
        assert info is None

    @pytest.mark.asyncio
    async def test_get_all_keys(self, cache):
        """Can get all cache keys."""
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("other3", "value3")

        all_keys = await cache.get_all_keys()
        assert len(all_keys) == 3

        filtered_keys = await cache.get_all_keys(prefix="key")
        assert len(filtered_keys) == 2
        assert "key1" in filtered_keys
        assert "key2" in filtered_keys

    def test_len(self, cache):
        """__len__ returns correct count."""
        assert len(cache) == 0

    @pytest.mark.asyncio
    async def test_contains(self, cache):
        """__contains__ works for existing and expired entries."""
        await cache.set("key1", "value1")
        await cache.set("key2", "value2", ttl=0)

        # Wait for key2 to expire
        await asyncio.sleep(0.01)

        assert "key1" in cache
        assert "key2" not in cache  # Expired
        assert "nonexistent" not in cache

    @pytest.mark.asyncio
    async def test_concurrent_access(self, cache):
        """Cache handles concurrent access correctly."""
        async def writer(key):
            for i in range(10):
                await cache.set(f"{key}:{i}", f"value{i}")

        async def reader(key):
            for i in range(10):
                await cache.get(f"{key}:{i}")

        # Run multiple writers and readers concurrently
        await asyncio.gather(
            writer("a"),
            writer("b"),
            reader("a"),
            reader("b")
        )

        # Should complete without errors
        assert len(cache) <= 20

    @pytest.mark.asyncio
    async def test_complex_value_types(self, cache):
        """Cache handles complex value types."""
        # Dict
        await cache.set("dict_key", {"nested": {"key": "value"}})
        result = await cache.get("dict_key")
        assert result["nested"]["key"] == "value"

        # List
        await cache.set("list_key", [1, 2, 3])
        result = await cache.get("list_key")
        assert result == [1, 2, 3]

        # Boolean
        await cache.set("bool_key", True)
        result = await cache.get("bool_key")
        assert result is True
