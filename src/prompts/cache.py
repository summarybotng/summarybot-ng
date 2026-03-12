"""
Prompt cache manager with multi-level caching and stale-while-revalidate pattern.

Cache Levels:
1. In-memory (process local) - Fast, but not shared across instances
2. Database (SQLite) - Persistent, shared across restarts
3. Stale cache - Expired but still usable during outages

Features:
- TTL-based expiration (default 5 minutes)
- Stale-while-revalidate pattern
- Background refresh
- Guild-scoped cache keys
"""

import asyncio
import logging
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Optional, Dict
import hashlib

from .models import PromptContext, CachedPrompt, ResolvedPrompt, PromptSource
from src.utils.time import utc_now_naive

logger = logging.getLogger(__name__)


class PromptCacheManager:
    """
    Manages caching of resolved prompts for performance.

    Implements stale-while-revalidate pattern:
    - Serve fresh cache if available (< TTL)
    - Serve stale cache if fresh unavailable, trigger background refresh
    - Only block if no cache available at all
    """

    DEFAULT_TTL = 300  # 5 minutes in seconds
    STALE_TTL = 3600  # 1 hour for stale cache
    MAX_CACHE_SIZE = 1000  # Maximum entries in memory

    def __init__(self, ttl: int = DEFAULT_TTL, stale_ttl: int = STALE_TTL):
        """
        Initialize the cache manager.

        Phase 4: Uses OrderedDict for O(1) LRU eviction.

        Args:
            ttl: Fresh cache TTL in seconds
            stale_ttl: Stale cache TTL in seconds (how long to keep expired entries)
        """
        self.ttl = ttl
        self.stale_ttl = stale_ttl
        # OrderedDict for O(1) LRU eviction
        self._memory_cache: OrderedDict[str, CachedPrompt] = OrderedDict()
        self._background_tasks = set()

    async def get(
        self,
        guild_id: str,
        context: PromptContext
    ) -> Optional[CachedPrompt]:
        """
        Get cached prompt, returns fresh if available.

        Args:
            guild_id: Discord guild ID
            context: Prompt context

        Returns:
            CachedPrompt if found and fresh, None otherwise
        """
        cache_key = self._generate_cache_key(guild_id, context)

        # Check memory cache
        cached = self._memory_cache.get(cache_key)
        if cached and cached.is_fresh:
            logger.debug(f"Cache HIT (fresh) for guild {guild_id}")
            # Move to end for LRU ordering
            self._memory_cache.move_to_end(cache_key)
            return cached

        logger.debug(f"Cache MISS for guild {guild_id}")
        return None

    async def get_stale(
        self,
        guild_id: str,
        context: PromptContext
    ) -> Optional[CachedPrompt]:
        """
        Get cached prompt even if stale (for fallback during outages).

        Args:
            guild_id: Discord guild ID
            context: Prompt context

        Returns:
            CachedPrompt if found (even if stale), None if too old or not found
        """
        cache_key = self._generate_cache_key(guild_id, context)

        # Check memory cache
        cached = self._memory_cache.get(cache_key)
        if cached:
            # Check if within stale threshold
            age_seconds = (utc_now_naive() - cached.cached_at).total_seconds()
            if age_seconds < self.stale_ttl:
                logger.info(
                    f"Cache HIT (stale, age={cached.age_minutes:.1f}m) for guild {guild_id}"
                )
                return cached
            else:
                logger.debug(
                    f"Cache entry too old ({age_seconds}s > {self.stale_ttl}s), removing"
                )
                del self._memory_cache[cache_key]

        return None

    async def set(
        self,
        guild_id: str,
        context: PromptContext,
        prompt: ResolvedPrompt,
        ttl: Optional[int] = None
    ) -> None:
        """
        Cache a resolved prompt.

        Args:
            guild_id: Discord guild ID
            context: Prompt context
            prompt: Resolved prompt to cache
            ttl: Optional custom TTL (uses default if None)
        """
        cache_key = self._generate_cache_key(guild_id, context)
        ttl = ttl or self.ttl

        now = utc_now_naive()
        cached = CachedPrompt(
            content=prompt.content,
            source=prompt.source.value,
            version=prompt.version,
            cached_at=now,
            expires_at=now + timedelta(seconds=ttl),
            repo_url=prompt.repo_url,
            context_hash=self._compute_context_hash(context)
        )

        # Store in memory cache
        self._memory_cache[cache_key] = cached

        # Enforce cache size limit (simple LRU)
        if len(self._memory_cache) > self.MAX_CACHE_SIZE:
            await self._evict_oldest()

        logger.debug(
            f"Cached prompt for guild {guild_id} (source={prompt.source.value}, ttl={ttl}s)"
        )

    async def invalidate_guild(self, guild_id: str) -> int:
        """
        Invalidate all cached prompts for a guild.

        Args:
            guild_id: Discord guild ID

        Returns:
            Number of entries invalidated
        """
        # Find all keys for this guild
        keys_to_remove = [
            key for key in self._memory_cache.keys()
            if key.startswith(f"prompt:{guild_id}:")
        ]

        # Remove them
        for key in keys_to_remove:
            del self._memory_cache[key]

        logger.info(f"Invalidated {len(keys_to_remove)} cache entries for guild {guild_id}")
        return len(keys_to_remove)

    async def clear_all(self) -> None:
        """Clear all cached prompts."""
        count = len(self._memory_cache)
        self._memory_cache.clear()
        logger.info(f"Cleared all cache ({count} entries)")

    def _generate_cache_key(self, guild_id: str, context: PromptContext) -> str:
        """
        Generate cache key for a guild and context.

        Args:
            guild_id: Discord guild ID
            context: Prompt context

        Returns:
            Cache key string

        Format: "prompt:{guild_id}:{context_hash}"
        Example: "prompt:123456789:a3d4f56c"
        """
        context_hash = self._compute_context_hash(context)
        return f"prompt:{guild_id}:{context_hash}"

    def _compute_context_hash(self, context: PromptContext) -> str:
        """
        Generate stable hash from context.

        Args:
            context: Prompt context

        Returns:
            SHA256 hash (first 8 chars)
        """
        # Create stable string representation
        context_str = (
            f"{context.category}:"
            f"{context.channel_name or ''}:"
            f"{context.summary_type}"
        )

        # Hash it
        hash_obj = hashlib.sha256(context_str.encode())
        return hash_obj.hexdigest()[:8]

    async def _evict_oldest(self) -> None:
        """Evict oldest cache entry to enforce size limit.

        Phase 4: O(1) eviction using OrderedDict.popitem(last=False).
        """
        if not self._memory_cache:
            return

        # Remove oldest entry (first item in OrderedDict) - O(1)
        oldest_key, _ = self._memory_cache.popitem(last=False)
        logger.debug(f"Evicted oldest cache entry: {oldest_key}")

    async def get_with_revalidation(
        self,
        guild_id: str,
        context: PromptContext,
        refresh_callback
    ) -> Optional[CachedPrompt]:
        """
        Get cached prompt with background revalidation if stale.

        Implements stale-while-revalidate pattern:
        1. If fresh: return immediately
        2. If stale but exists: return stale + trigger background refresh
        3. If not found: return None

        Args:
            guild_id: Discord guild ID
            context: Prompt context
            refresh_callback: Async function to refresh the cache

        Returns:
            CachedPrompt if found, None otherwise
        """
        cache_key = self._generate_cache_key(guild_id, context)

        cached = self._memory_cache.get(cache_key)
        if not cached:
            return None

        if cached.is_fresh:
            # Fresh cache - return immediately
            return cached

        # Stale cache - return it but trigger background refresh
        if cached.is_stale:
            logger.info(
                f"Serving stale cache (age={cached.age_minutes:.1f}m), "
                f"triggering background refresh for guild {guild_id}"
            )

            # Trigger background refresh
            task = asyncio.create_task(
                self._background_refresh(guild_id, context, refresh_callback)
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

            return cached

        return None

    async def _background_refresh(
        self,
        guild_id: str,
        context: PromptContext,
        refresh_callback
    ) -> None:
        """
        Background task to refresh stale cache.

        Args:
            guild_id: Discord guild ID
            context: Prompt context
            refresh_callback: Async function to fetch fresh prompt
        """
        try:
            logger.debug(f"Background refresh started for guild {guild_id}")
            await refresh_callback(guild_id, context)
            logger.debug(f"Background refresh completed for guild {guild_id}")
        except Exception as e:
            logger.error(
                f"Background refresh failed for guild {guild_id}: {e}",
                exc_info=True
            )

    @property
    def cache_size(self) -> int:
        """Get current number of cached entries."""
        return len(self._memory_cache)

    @property
    def cache_stats(self) -> Dict:
        """Get cache statistics."""
        now = utc_now_naive()
        fresh_count = sum(
            1 for cached in self._memory_cache.values()
            if cached.is_fresh
        )
        stale_count = len(self._memory_cache) - fresh_count

        return {
            "total_entries": len(self._memory_cache),
            "fresh_entries": fresh_count,
            "stale_entries": stale_count,
            "max_size": self.MAX_CACHE_SIZE,
            "ttl_seconds": self.ttl,
            "stale_ttl_seconds": self.stale_ttl,
        }
