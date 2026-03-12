"""
Summary caching logic for performance optimization.
"""

import json
import hashlib
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod

from ..models.summary import SummaryResult
from ..models.base import BaseModel


class CacheInterface(ABC):
    """Abstract interface for caching backends."""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Get value by key."""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """Set value with optional TTL."""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete value by key."""
        pass
    
    @abstractmethod
    async def clear(self, pattern: str = None) -> int:
        """Clear cache entries matching pattern."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if cache backend is healthy."""
        pass


class MemoryCache(CacheInterface):
    """Simple in-memory cache implementation with O(1) LRU eviction.

    Phase 4: Uses OrderedDict for O(1) LRU eviction instead of O(n) min() scan.
    """

    def __init__(self, max_size: int = 1000, default_ttl: int = 3600):
        self.max_size = max_size
        self.default_ttl = default_ttl
        # OrderedDict maintains insertion order, enabling O(1) LRU eviction
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()

    async def get(self, key: str) -> Optional[Any]:
        """Get value by key, moving to end for LRU ordering."""
        if key not in self._cache:
            return None

        entry = self._cache[key]

        # Check expiration
        if entry.get("expires_at") and datetime.utcnow() > entry["expires_at"]:
            del self._cache[key]
            return None

        # Move to end for LRU (most recently used)
        self._cache.move_to_end(key)

        return entry["value"]
    
    async def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """Set value with optional TTL."""
        # Enforce size limit with O(1) LRU eviction
        if len(self._cache) >= self.max_size and key not in self._cache:
            # Remove oldest entry (first item in OrderedDict) - O(1)
            self._cache.popitem(last=False)

        ttl = ttl or self.default_ttl
        expires_at = datetime.utcnow() + timedelta(seconds=ttl) if ttl > 0 else None

        self._cache[key] = {
            "value": value,
            "created_at": datetime.utcnow(),
            "expires_at": expires_at
        }

        return True
    
    async def delete(self, key: str) -> bool:
        """Delete value by key."""
        if key in self._cache:
            del self._cache[key]
            return True
        return False
    
    async def clear(self, pattern: str = None) -> int:
        """Clear cache entries matching pattern."""
        if pattern is None:
            count = len(self._cache)
            self._cache.clear()
            return count
        
        # Simple pattern matching (just prefix for now)
        keys_to_delete = [k for k in self._cache.keys() if k.startswith(pattern)]
        for key in keys_to_delete:
            del self._cache[key]
        
        return len(keys_to_delete)
    
    async def health_check(self) -> bool:
        """Check if cache backend is healthy."""
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        now = datetime.utcnow()
        expired_count = sum(
            1 for entry in self._cache.values()
            if entry.get("expires_at") and now > entry["expires_at"]
        )
        
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "expired_entries": expired_count,
            "hit_ratio": "N/A",  # Would need tracking
            "backend": "memory"
        }


class SummaryCache:
    """High-level cache interface for summaries."""
    
    def __init__(self, backend: CacheInterface):
        self.backend = backend
    
    async def get_cached_summary(self,
                               channel_id: str,
                               start_time: datetime,
                               end_time: datetime,
                               options_hash: str,
                               guild_id: str = "") -> Optional[SummaryResult]:
        """Get cached summary if available.

        Args:
            channel_id: Discord channel ID
            start_time: Start time of message range
            end_time: End time of message range
            options_hash: Hash of summarization options
            guild_id: Discord guild ID (Phase 4: for proper cache key lookup)

        Returns:
            Cached summary result or None
        """
        cache_key = self._generate_cache_key(
            channel_id, start_time, end_time, options_hash, guild_id
        )
        
        cached_data = await self.backend.get(cache_key)
        if not cached_data:
            return None
        
        # Deserialize summary result
        try:
            return SummaryResult.from_dict(cached_data)
        except Exception:
            # Invalid cached data, remove it
            await self.backend.delete(cache_key)
            return None
    
    async def cache_summary(self,
                          summary: SummaryResult,
                          ttl: int = 3600) -> None:
        """Cache a summary result.

        Args:
            summary: Summary result to cache
            ttl: Time to live in seconds
        """
        # Generate cache key from summary properties (includes guild_id for proper invalidation)
        options_hash = self._hash_summary_options(summary)
        cache_key = self._generate_cache_key(
            summary.channel_id,
            summary.start_time,
            summary.end_time,
            options_hash,
            summary.guild_id  # Phase 4: Include guild_id
        )

        # Serialize summary
        cached_data = summary.to_dict()

        await self.backend.set(cache_key, cached_data, ttl)
    
    async def invalidate_channel(self, channel_id: str) -> int:
        """Invalidate all cached summaries for a channel.
        
        Args:
            channel_id: Channel to invalidate
            
        Returns:
            Number of entries removed
        """
        pattern = f"summary:{channel_id}:"
        return await self.backend.clear(pattern)
    
    async def invalidate_guild(self, guild_id: str) -> int:
        """Invalidate all cached summaries for a guild.

        Phase 4: Now properly invalidates only guild-specific entries
        using the guild_id prefix in cache keys.

        Args:
            guild_id: Guild to invalidate

        Returns:
            Number of entries removed
        """
        # Use guild_id prefix to invalidate only this guild's entries
        pattern = f"summary:{guild_id}:"
        return await self.backend.clear(pattern)
    
    async def cleanup_expired(self) -> int:
        """Clean up expired cache entries.
        
        Returns:
            Number of entries cleaned up
        """
        # This depends on the backend implementation
        # For memory cache, expired entries are removed on access
        # For Redis, we could use SCAN with TTL checks
        return 0
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        base_stats = {
            "backend_healthy": await self.backend.health_check()
        }
        
        # Add backend-specific stats if available
        if hasattr(self.backend, 'get_stats'):
            base_stats.update(self.backend.get_stats())
        
        return base_stats
    
    async def health_check(self) -> bool:
        """Check if cache is healthy."""
        return await self.backend.health_check()
    
    def _generate_cache_key(self,
                          channel_id: str,
                          start_time: datetime,
                          end_time: datetime,
                          options_hash: str,
                          guild_id: str = "") -> str:
        """Generate cache key for summary.

        Phase 4: Includes guild_id for proper guild-based invalidation.
        Key format: summary:{guild_id}:{channel_id}:{start}:{end}:{options}
        """
        # Use timestamp ranges rounded to nearest hour for better cache hits
        start_hour = start_time.replace(minute=0, second=0, microsecond=0)
        end_hour = end_time.replace(minute=0, second=0, microsecond=0)

        key_parts = [
            "summary",
            guild_id or "unknown",  # Include guild_id for proper invalidation
            channel_id,
            start_hour.strftime("%Y%m%d%H"),
            end_hour.strftime("%Y%m%d%H"),
            options_hash
        ]

        return ":".join(key_parts)
    
    def _hash_summary_options(self, summary: SummaryResult) -> str:
        """Generate hash from summary metadata that indicates options used."""
        # Extract relevant options from metadata
        options_data = {
            "model": summary.metadata.get("claude_model", ""),
            "max_tokens": summary.metadata.get("max_tokens", ""),
            # Could add more options here
        }

        options_str = json.dumps(options_data, sort_keys=True)
        return hashlib.md5(options_str.encode()).hexdigest()[:8]

    async def initialize(self) -> None:
        """Initialize the cache backend.

        This method is called during service container initialization.
        Can be used for connection setup, warming, etc.
        """
        # Perform health check to ensure backend is ready
        await self.backend.health_check()

    async def close(self) -> None:
        """Close the cache backend and cleanup resources.

        This method is called during service container cleanup.
        Can be used for connection teardown, final flushes, etc.
        """
        # Most backends don't need explicit cleanup, but provide hook for future use
        pass


def create_cache(cache_config) -> SummaryCache:
    """Factory function to create a SummaryCache instance from configuration.

    Args:
        cache_config: Cache configuration object containing backend settings

    Returns:
        Configured SummaryCache instance

    Raises:
        ValueError: If cache backend is not supported

    Example:
        >>> from src.config.settings import CacheConfig
        >>> config = CacheConfig(backend="memory", max_size=1000, default_ttl=3600)
        >>> cache = create_cache(config)
    """
    backend_type = cache_config.backend.lower()

    if backend_type == "memory":
        # Create in-memory cache backend
        backend = MemoryCache(
            max_size=cache_config.max_size,
            default_ttl=cache_config.default_ttl
        )
        return SummaryCache(backend=backend)

    elif backend_type == "redis":
        # Redis backend would be implemented here
        # For now, raise an error since Redis isn't implemented yet
        raise ValueError(
            f"Redis cache backend is not yet implemented. "
            f"Please use 'memory' backend instead."
        )

    else:
        raise ValueError(
            f"Unsupported cache backend: {backend_type}. "
            f"Supported backends: 'memory', 'redis'"
        )