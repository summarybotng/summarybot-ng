"""
Permission caching implementation for Summary Bot NG.

This module provides caching functionality for permission checks to reduce
redundant permission validation and improve performance.
"""

from typing import Optional, Any, Dict, Pattern
from datetime import datetime, timedelta
import asyncio
import logging
import re
from dataclasses import dataclass, field
from src.utils.time import utc_now_naive

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Represents a single cache entry."""

    key: str
    value: Any
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    access_count: int = 0
    last_accessed: datetime = field(default_factory=datetime.utcnow)

    def is_expired(self) -> bool:
        """Check if the cache entry is expired."""
        if not self.expires_at:
            return False
        return utc_now_naive() > self.expires_at

    def access(self) -> Any:
        """Access the cache entry and update access statistics."""
        self.access_count += 1
        self.last_accessed = utc_now_naive()
        return self.value

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "key": self.key,
            "value": str(self.value),
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat()
        }


class PermissionCache:
    """
    In-memory cache for permission checks.

    This cache stores permission validation results to avoid redundant
    checks and improve performance. It supports TTL expiration and
    pattern-based invalidation.
    """

    def __init__(self, ttl: int = 3600, max_size: int = 10000):
        """
        Initialize the permission cache.

        Args:
            ttl: Time-to-live in seconds for cache entries (default: 1 hour)
            max_size: Maximum number of entries to store (default: 10000)
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._ttl = ttl
        self._max_size = max_size
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

        logger.info(
            f"PermissionCache initialized with TTL={ttl}s, max_size={max_size}"
        )

    async def get(self, key: str) -> Optional[Any]:
        """
        Get a value from the cache.

        Args:
            key: Cache key

        Returns:
            Cached value if found and not expired, None otherwise
        """
        async with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._misses += 1
                logger.debug(f"Cache miss: {key}")
                return None

            if entry.is_expired():
                # Remove expired entry
                del self._cache[key]
                self._misses += 1
                logger.debug(f"Cache expired: {key}")
                return None

            self._hits += 1
            logger.debug(f"Cache hit: {key}")
            return entry.access()

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> None:
        """
        Set a value in the cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Optional TTL in seconds (uses default if not provided)
        """
        async with self._lock:
            # Check if we need to evict entries
            if len(self._cache) >= self._max_size:
                await self._evict_lru()

            # Calculate expiration time
            ttl_seconds = ttl if ttl is not None else self._ttl
            expires_at = utc_now_naive() + timedelta(seconds=ttl_seconds)

            # Create and store entry
            entry = CacheEntry(
                key=key,
                value=value,
                expires_at=expires_at
            )

            self._cache[key] = entry
            logger.debug(f"Cache set: {key} (TTL: {ttl_seconds}s)")

    async def delete(self, key: str) -> bool:
        """
        Delete a specific key from the cache.

        Args:
            key: Cache key to delete

        Returns:
            True if key was deleted, False if it didn't exist
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"Cache deleted: {key}")
                return True
            return False

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all cache entries matching a pattern.

        Supports simple wildcard patterns using * as a wildcard character.

        Args:
            pattern: Pattern to match (e.g., "user:123:*")

        Returns:
            Number of entries invalidated
        """
        async with self._lock:
            # Convert simple wildcard pattern to regex
            regex_pattern = pattern.replace("*", ".*")
            regex = re.compile(f"^{regex_pattern}$")

            # Find matching keys
            matching_keys = [
                key for key in self._cache.keys()
                if regex.match(key)
            ]

            # Delete matching entries
            for key in matching_keys:
                del self._cache[key]

            count = len(matching_keys)
            if count > 0:
                logger.info(
                    f"Invalidated {count} cache entries matching pattern: {pattern}"
                )

            return count

    async def clear(self) -> None:
        """Clear all entries from the cache."""
        async with self._lock:
            entry_count = len(self._cache)
            self._cache.clear()
            logger.info(f"Cleared {entry_count} entries from cache")

    async def _evict_lru(self) -> None:
        """
        Evict least recently used entry from the cache.

        This method is called when the cache reaches max_size.
        """
        if not self._cache:
            return

        # Find entry with oldest last_accessed time
        lru_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k].last_accessed
        )

        del self._cache[lru_key]
        logger.debug(f"Evicted LRU entry: {lru_key}")

    async def cleanup_expired(self) -> int:
        """
        Remove all expired entries from the cache.

        Returns:
            Number of entries removed
        """
        async with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired()
            ]

            for key in expired_keys:
                del self._cache[key]

            count = len(expired_keys)
            if count > 0:
                logger.info(f"Cleaned up {count} expired cache entries")

            return count

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0

        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{hit_rate:.2f}%",
            "ttl": self._ttl
        }

    def reset_stats(self) -> None:
        """Reset cache statistics."""
        self._hits = 0
        self._misses = 0
        logger.debug("Cache statistics reset")

    async def get_entry_info(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a cache entry.

        Args:
            key: Cache key

        Returns:
            Dictionary with entry information or None if not found
        """
        async with self._lock:
            entry = self._cache.get(key)
            if entry:
                return entry.to_dict()
            return None

    async def get_all_keys(self, prefix: Optional[str] = None) -> list[str]:
        """
        Get all cache keys, optionally filtered by prefix.

        Args:
            prefix: Optional prefix to filter keys

        Returns:
            List of cache keys
        """
        async with self._lock:
            if prefix:
                return [
                    key for key in self._cache.keys()
                    if key.startswith(prefix)
                ]
            return list(self._cache.keys())

    def __len__(self) -> int:
        """Get the number of entries in the cache."""
        return len(self._cache)

    def __contains__(self, key: str) -> bool:
        """Check if a key exists in the cache."""
        entry = self._cache.get(key)
        if entry and not entry.is_expired():
            return True
        return False
