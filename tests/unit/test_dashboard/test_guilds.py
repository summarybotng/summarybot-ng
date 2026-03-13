"""
Tests for guild routes N+1 query fix (P1-6).

Verifies that list_guilds and get_guild use count_by_guild
instead of find_by_guild(limit=10000) and use asyncio.gather
for parallel queries.
"""

import inspect

from src.dashboard.routes import guilds


def test_list_guilds_uses_count_not_find_10000():
    """Verify list_guilds uses count_by_guild instead of find_by_guild(limit=10000)."""
    source = inspect.getsource(guilds.list_guilds)
    assert "find_by_guild" not in source or "limit=10000" not in source
    assert "count_by_guild" in source


def test_get_guild_uses_parallel_count_queries():
    """Verify get_guild uses count_by_guild with asyncio.gather for parallel queries."""
    source = inspect.getsource(guilds.get_guild)
    assert "count_by_guild" in source
    assert "asyncio.gather" in source
