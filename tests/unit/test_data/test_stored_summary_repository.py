"""
Unit tests for SQLiteStoredSummaryRepository.

Tests cover:
- Message count sorting (ADR-017)
- Filtering by various fields
- Pagination
"""

import pytest
import pytest_asyncio
import json
from datetime import datetime, timedelta
from typing import List
import uuid

from src.data.sqlite import SQLiteConnection, SQLiteStoredSummaryRepository
from src.models.stored_summary import StoredSummary


@pytest.mark.asyncio
class TestStoredSummaryRepositorySorting:
    """Test sorting functionality for stored summaries."""

    async def _create_test_summary(
        self,
        repo: SQLiteStoredSummaryRepository,
        guild_id: str,
        message_count: int,
        title: str = None,
    ) -> StoredSummary:
        """Helper to create a test summary with specific message_count."""
        summary_id = str(uuid.uuid4())
        if title is None:
            title = f"Test Summary {message_count} messages"

        summary_json = json.dumps({
            "id": summary_id,
            "channel_id": "channel-123",
            "guild_id": guild_id,
            "start_time": datetime.utcnow().isoformat(),
            "end_time": datetime.utcnow().isoformat(),
            "message_count": message_count,
            "key_points": ["point1", "point2"],
            "action_items": [],
            "technical_terms": [],
            "participants": [],
            "summary_text": f"Summary with {message_count} messages",
            "metadata": {},
            "created_at": datetime.utcnow().isoformat(),
        })

        # Insert directly into database
        await repo.connection.execute(
            """
            INSERT INTO stored_summaries (
                id, guild_id, source_channel_ids, summary_json, created_at,
                title, is_pinned, is_archived, tags, source, message_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary_id,
                guild_id,
                json.dumps(["channel-123"]),
                summary_json,
                datetime.utcnow().isoformat(),
                title,
                0,
                0,
                json.dumps([]),
                "realtime",
                message_count,
            )
        )

        return summary_id

    async def test_sort_by_message_count_desc(
        self,
        stored_summary_repository: SQLiteStoredSummaryRepository,
    ):
        """Test sorting by message_count in descending order."""
        guild_id = "test-guild-sort"

        # Create summaries with varying message counts (not in order)
        message_counts = [15, 67, 8, 44, 27]
        for count in message_counts:
            await self._create_test_summary(
                stored_summary_repository,
                guild_id,
                count,
            )

        # Fetch with message_count DESC sorting
        summaries = await stored_summary_repository.find_by_guild(
            guild_id=guild_id,
            limit=10,
            offset=0,
            sort_by="message_count",
            sort_order="desc",
        )

        # Extract message counts from results
        result_counts = [s.summary_result.message_count for s in summaries]
        expected = sorted(message_counts, reverse=True)

        assert result_counts == expected, (
            f"Expected descending order {expected}, got {result_counts}"
        )

    async def test_sort_by_message_count_asc(
        self,
        stored_summary_repository: SQLiteStoredSummaryRepository,
    ):
        """Test sorting by message_count in ascending order."""
        guild_id = "test-guild-sort-asc"

        # Create summaries with varying message counts
        message_counts = [15, 67, 8, 44, 27]
        for count in message_counts:
            await self._create_test_summary(
                stored_summary_repository,
                guild_id,
                count,
            )

        # Fetch with message_count ASC sorting
        summaries = await stored_summary_repository.find_by_guild(
            guild_id=guild_id,
            limit=10,
            offset=0,
            sort_by="message_count",
            sort_order="asc",
        )

        # Extract message counts from results
        result_counts = [s.summary_result.message_count for s in summaries]
        expected = sorted(message_counts)

        assert result_counts == expected, (
            f"Expected ascending order {expected}, got {result_counts}"
        )

    async def test_sort_by_message_count_with_null_values(
        self,
        stored_summary_repository: SQLiteStoredSummaryRepository,
    ):
        """Test that NULL message_count values are handled correctly."""
        guild_id = "test-guild-sort-null"

        # Create summaries with and without message_count
        await self._create_test_summary(stored_summary_repository, guild_id, 50)
        await self._create_test_summary(stored_summary_repository, guild_id, 10)

        # Create one with NULL message_count
        summary_id = str(uuid.uuid4())
        await stored_summary_repository.connection.execute(
            """
            INSERT INTO stored_summaries (
                id, guild_id, source_channel_ids, summary_json, created_at,
                title, is_pinned, is_archived, tags, source, message_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                summary_id,
                guild_id,
                json.dumps(["channel-123"]),
                json.dumps({
                    "id": summary_id,
                    "channel_id": "channel-123",
                    "guild_id": guild_id,
                    "start_time": datetime.utcnow().isoformat(),
                    "end_time": datetime.utcnow().isoformat(),
                    "message_count": 0,
                    "key_points": [],
                    "action_items": [],
                    "technical_terms": [],
                    "participants": [],
                    "summary_text": "No message count",
                    "metadata": {},
                    "created_at": datetime.utcnow().isoformat(),
                }),
                datetime.utcnow().isoformat(),
                "Null message count summary",
                0,
                0,
                json.dumps([]),
                "realtime",
            )
        )

        # Fetch with message_count DESC - NULL should be treated as 0
        summaries = await stored_summary_repository.find_by_guild(
            guild_id=guild_id,
            limit=10,
            offset=0,
            sort_by="message_count",
            sort_order="desc",
        )

        result_counts = [s.summary_result.message_count for s in summaries]

        # 50 should come first, then 10, then 0 (from NULL)
        assert result_counts == [50, 10, 0], (
            f"Expected [50, 10, 0], got {result_counts}"
        )

    async def test_sort_by_created_at_default(
        self,
        stored_summary_repository: SQLiteStoredSummaryRepository,
    ):
        """Test default sorting by created_at."""
        guild_id = "test-guild-sort-created"

        # Create summaries at different times
        await self._create_test_summary(stored_summary_repository, guild_id, 10)
        await self._create_test_summary(stored_summary_repository, guild_id, 20)
        await self._create_test_summary(stored_summary_repository, guild_id, 30)

        # Default sort is created_at DESC
        summaries = await stored_summary_repository.find_by_guild(
            guild_id=guild_id,
            limit=10,
            offset=0,
        )

        # Most recent first (30 was created last)
        result_counts = [s.summary_result.message_count for s in summaries]
        assert result_counts == [30, 20, 10]

    async def test_pinned_always_first(
        self,
        stored_summary_repository: SQLiteStoredSummaryRepository,
    ):
        """Test that pinned summaries appear first regardless of sort order."""
        guild_id = "test-guild-pinned"

        # Create non-pinned summaries
        await self._create_test_summary(stored_summary_repository, guild_id, 100)
        await self._create_test_summary(stored_summary_repository, guild_id, 50)

        # Create a pinned summary with lower message count
        pinned_id = str(uuid.uuid4())
        await stored_summary_repository.connection.execute(
            """
            INSERT INTO stored_summaries (
                id, guild_id, source_channel_ids, summary_json, created_at,
                title, is_pinned, is_archived, tags, source, message_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pinned_id,
                guild_id,
                json.dumps(["channel-123"]),
                json.dumps({
                    "id": pinned_id,
                    "channel_id": "channel-123",
                    "guild_id": guild_id,
                    "start_time": datetime.utcnow().isoformat(),
                    "end_time": datetime.utcnow().isoformat(),
                    "message_count": 5,
                    "key_points": [],
                    "action_items": [],
                    "technical_terms": [],
                    "participants": [],
                    "summary_text": "Pinned summary",
                    "metadata": {},
                    "created_at": datetime.utcnow().isoformat(),
                }),
                datetime.utcnow().isoformat(),
                "Pinned Summary",
                1,  # is_pinned = True
                0,
                json.dumps([]),
                "realtime",
                5,
            )
        )

        # Sort by message_count DESC
        summaries = await stored_summary_repository.find_by_guild(
            guild_id=guild_id,
            limit=10,
            offset=0,
            sort_by="message_count",
            sort_order="desc",
        )

        # Pinned (5 msgs) should be first despite lower count
        result_counts = [s.summary_result.message_count for s in summaries]
        assert result_counts[0] == 5, "Pinned summary should be first"
        assert result_counts[1:] == [100, 50], "Non-pinned should be sorted DESC"
