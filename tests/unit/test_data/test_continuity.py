"""
Tests for ADR-087: Weekly Continuity Summaries.

Tests the continuity chain functionality for weekly scheduled summaries.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from typing import AsyncGenerator

from src.data.sqlite import SQLiteConnection, SQLiteStoredSummaryRepository
from src.models.stored_summary import StoredSummary, SummarySource
from src.models.summary import SummaryResult


@pytest_asyncio.fixture
async def continuity_db() -> AsyncGenerator[SQLiteConnection, None]:
    """Create an in-memory SQLite database for continuity testing."""
    connection = SQLiteConnection(":memory:", pool_size=1)
    await connection.connect()

    # Create stored_summaries table with continuity columns
    await connection.execute("""
        CREATE TABLE IF NOT EXISTS stored_summaries (
            id TEXT PRIMARY KEY,
            guild_id TEXT NOT NULL,
            source_channel_ids TEXT NOT NULL,
            schedule_id TEXT,
            summary_json TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            viewed_at TIMESTAMP,
            pushed_at TIMESTAMP,
            push_deliveries TEXT,
            title TEXT NOT NULL,
            is_pinned BOOLEAN DEFAULT FALSE,
            is_archived BOOLEAN DEFAULT FALSE,
            tags TEXT,
            source TEXT DEFAULT 'realtime',
            archive_period TEXT,
            archive_granularity TEXT,
            archive_source_key TEXT,
            channel_id TEXT,
            channel_name TEXT,
            start_time TEXT,
            end_time TEXT,
            timezone TEXT DEFAULT 'UTC',
            message_count INTEGER DEFAULT 0,
            participant_count INTEGER DEFAULT 0,
            scope TEXT DEFAULT 'channel',
            category_id TEXT,
            category_name TEXT,
            wiki_ingested INTEGER DEFAULT 0,
            wiki_ingested_at TIMESTAMP,
            contains_sensitive_channels INTEGER DEFAULT 0,
            split_from TEXT,
            split_private_id TEXT,
            split_public_id TEXT,
            previous_summary_id TEXT,
            continuity_week_number INTEGER
        )
    """)

    yield connection
    await connection.disconnect()


@pytest_asyncio.fixture
async def continuity_repo(continuity_db: SQLiteConnection) -> SQLiteStoredSummaryRepository:
    """Create a stored summary repository for continuity testing."""
    return SQLiteStoredSummaryRepository(continuity_db)


def create_weekly_summary(
    summary_id: str,
    guild_id: str,
    channel_id: str,
    created_at: datetime,
    week_number: int | None = None,
    previous_id: str | None = None,
    summary_text: str = "Test summary",
    key_points: list[str] | None = None,
) -> StoredSummary:
    """Helper to create a weekly summary for testing."""
    result = SummaryResult(
        id=summary_id,
        channel_id=channel_id,
        guild_id=guild_id,
        start_time=created_at - timedelta(days=7),
        end_time=created_at,
        message_count=50,
        summary_text=summary_text,
        key_points=key_points or ["Point 1", "Point 2"],
        action_items=[],
        technical_terms=[],
        participants=[],
        metadata={},
        created_at=created_at,
    )

    return StoredSummary(
        id=summary_id,
        guild_id=guild_id,
        source_channel_ids=[channel_id],
        summary_result=result,
        title=f"Week {week_number or 1} Summary",
        source=SummarySource.SCHEDULED,
        archive_granularity="weekly",
        created_at=created_at,
        previous_summary_id=previous_id,
        continuity_week_number=week_number,
    )


class TestContinuityChain:
    """Tests for weekly summary continuity chain."""

    @pytest.mark.asyncio
    async def test_save_summary_with_continuity(self, continuity_repo: SQLiteStoredSummaryRepository):
        """Test saving a summary with continuity metadata."""
        summary = create_weekly_summary(
            summary_id="week1",
            guild_id="guild123",
            channel_id="channel456",
            created_at=datetime.utcnow(),
            week_number=1,
            previous_id=None,
        )

        await continuity_repo.save(summary)

        # Retrieve and verify
        retrieved = await continuity_repo.get("week1")
        assert retrieved is not None
        assert retrieved.continuity_week_number == 1
        assert retrieved.previous_summary_id is None
        assert retrieved.archive_granularity == "weekly"

    @pytest.mark.asyncio
    async def test_save_summary_chain(self, continuity_repo: SQLiteStoredSummaryRepository):
        """Test saving a chain of weekly summaries."""
        now = datetime.utcnow()

        # Week 1
        week1 = create_weekly_summary(
            summary_id="week1",
            guild_id="guild123",
            channel_id="channel456",
            created_at=now - timedelta(weeks=2),
            week_number=1,
            previous_id=None,
        )
        await continuity_repo.save(week1)

        # Week 2 links to Week 1
        week2 = create_weekly_summary(
            summary_id="week2",
            guild_id="guild123",
            channel_id="channel456",
            created_at=now - timedelta(weeks=1),
            week_number=2,
            previous_id="week1",
        )
        await continuity_repo.save(week2)

        # Week 3 links to Week 2
        week3 = create_weekly_summary(
            summary_id="week3",
            guild_id="guild123",
            channel_id="channel456",
            created_at=now,
            week_number=3,
            previous_id="week2",
        )
        await continuity_repo.save(week3)

        # Verify chain
        retrieved_week3 = await continuity_repo.get("week3")
        assert retrieved_week3.continuity_week_number == 3
        assert retrieved_week3.previous_summary_id == "week2"

        retrieved_week2 = await continuity_repo.get("week2")
        assert retrieved_week2.continuity_week_number == 2
        assert retrieved_week2.previous_summary_id == "week1"

        retrieved_week1 = await continuity_repo.get("week1")
        assert retrieved_week1.continuity_week_number == 1
        assert retrieved_week1.previous_summary_id is None


class TestGetPreviousWeeklySummary:
    """Tests for get_previous_weekly_summary repository method."""

    @pytest.mark.asyncio
    async def test_get_previous_weekly_summary_found(self, continuity_repo: SQLiteStoredSummaryRepository):
        """Test finding the previous weekly summary."""
        now = datetime.utcnow()

        # Create week 1 summary
        week1 = create_weekly_summary(
            summary_id="week1",
            guild_id="guild123",
            channel_id="channel456",
            created_at=now - timedelta(weeks=1),
            week_number=1,
        )
        await continuity_repo.save(week1)

        # Look for previous summary before now
        previous = await continuity_repo.get_previous_weekly_summary(
            guild_id="guild123",
            channel_id="channel456",
            before_date=now,
        )

        assert previous is not None
        assert previous.id == "week1"
        assert previous.continuity_week_number == 1

    @pytest.mark.asyncio
    async def test_get_previous_weekly_summary_not_found(self, continuity_repo: SQLiteStoredSummaryRepository):
        """Test when no previous weekly summary exists."""
        previous = await continuity_repo.get_previous_weekly_summary(
            guild_id="guild123",
            channel_id="channel456",
            before_date=datetime.utcnow(),
        )

        assert previous is None

    @pytest.mark.asyncio
    async def test_get_previous_weekly_summary_different_channel(self, continuity_repo: SQLiteStoredSummaryRepository):
        """Test that summaries from different channels are not returned."""
        now = datetime.utcnow()

        # Create summary for different channel
        other_channel = create_weekly_summary(
            summary_id="other",
            guild_id="guild123",
            channel_id="other_channel",
            created_at=now - timedelta(weeks=1),
            week_number=1,
        )
        await continuity_repo.save(other_channel)

        # Look for previous summary for our channel
        previous = await continuity_repo.get_previous_weekly_summary(
            guild_id="guild123",
            channel_id="channel456",
            before_date=now,
        )

        assert previous is None

    @pytest.mark.asyncio
    async def test_get_previous_weekly_summary_most_recent(self, continuity_repo: SQLiteStoredSummaryRepository):
        """Test that the most recent previous summary is returned."""
        now = datetime.utcnow()

        # Create multiple weeks
        for i in range(3):
            summary = create_weekly_summary(
                summary_id=f"week{i+1}",
                guild_id="guild123",
                channel_id="channel456",
                created_at=now - timedelta(weeks=3-i),
                week_number=i + 1,
            )
            await continuity_repo.save(summary)

        # Look for previous summary - should get week 3 (most recent before now)
        previous = await continuity_repo.get_previous_weekly_summary(
            guild_id="guild123",
            channel_id="channel456",
            before_date=now,
        )

        assert previous is not None
        assert previous.id == "week3"
        assert previous.continuity_week_number == 3

    @pytest.mark.asyncio
    async def test_get_previous_weekly_summary_ignores_daily(self, continuity_repo: SQLiteStoredSummaryRepository):
        """Test that daily summaries are not returned."""
        now = datetime.utcnow()

        # Create a daily summary (not weekly)
        daily = StoredSummary(
            id="daily1",
            guild_id="guild123",
            source_channel_ids=["channel456"],
            summary_result=SummaryResult(
                id="daily1",
                channel_id="channel456",
                guild_id="guild123",
                start_time=now - timedelta(days=1),
                end_time=now,
                message_count=20,
                summary_text="Daily summary",
                key_points=["Daily point"],
                action_items=[],
                technical_terms=[],
                participants=[],
                metadata={},
                created_at=now - timedelta(hours=1),
            ),
            title="Daily Summary",
            source=SummarySource.SCHEDULED,
            archive_granularity="daily",  # Not weekly
            created_at=now - timedelta(hours=1),
        )
        await continuity_repo.save(daily)

        # Look for previous weekly summary
        previous = await continuity_repo.get_previous_weekly_summary(
            guild_id="guild123",
            channel_id="channel456",
            before_date=now,
        )

        # Should not find the daily summary
        assert previous is None


class TestFindContinuityChain:
    """Tests for find_continuity_chain repository method."""

    @pytest.mark.asyncio
    async def test_find_continuity_chain(self, continuity_repo: SQLiteStoredSummaryRepository):
        """Test finding the full continuity chain."""
        now = datetime.utcnow()

        # Create chain of 5 weeks
        for i in range(5):
            summary = create_weekly_summary(
                summary_id=f"week{i+1}",
                guild_id="guild123",
                channel_id="channel456",
                created_at=now - timedelta(weeks=5-i),
                week_number=i + 1,
                previous_id=f"week{i}" if i > 0 else None,
            )
            await continuity_repo.save(summary)

        # Find chain
        chain = await continuity_repo.find_continuity_chain(
            guild_id="guild123",
            channel_id="channel456",
            limit=10,
        )

        assert len(chain) == 5
        # Should be ordered by week number descending
        assert chain[0].continuity_week_number == 5
        assert chain[4].continuity_week_number == 1

    @pytest.mark.asyncio
    async def test_find_continuity_chain_with_limit(self, continuity_repo: SQLiteStoredSummaryRepository):
        """Test that limit is respected."""
        now = datetime.utcnow()

        # Create chain of 5 weeks
        for i in range(5):
            summary = create_weekly_summary(
                summary_id=f"week{i+1}",
                guild_id="guild123",
                channel_id="channel456",
                created_at=now - timedelta(weeks=5-i),
                week_number=i + 1,
            )
            await continuity_repo.save(summary)

        # Find chain with limit
        chain = await continuity_repo.find_continuity_chain(
            guild_id="guild123",
            channel_id="channel456",
            limit=3,
        )

        assert len(chain) == 3
        # Should get most recent 3
        assert chain[0].continuity_week_number == 5
        assert chain[2].continuity_week_number == 3


class TestStoredSummaryContinuityFields:
    """Tests for continuity fields in StoredSummary model."""

    def test_to_dict_includes_continuity(self):
        """Test that to_dict includes continuity fields."""
        summary = create_weekly_summary(
            summary_id="test",
            guild_id="guild123",
            channel_id="channel456",
            created_at=datetime.utcnow(),
            week_number=3,
            previous_id="week2",
        )

        data = summary.to_dict()

        assert "previous_summary_id" in data
        assert data["previous_summary_id"] == "week2"
        assert "continuity_week_number" in data
        assert data["continuity_week_number"] == 3

    def test_to_list_item_dict_includes_continuity(self):
        """Test that to_list_item_dict includes continuity fields."""
        summary = create_weekly_summary(
            summary_id="test",
            guild_id="guild123",
            channel_id="channel456",
            created_at=datetime.utcnow(),
            week_number=5,
            previous_id="week4",
        )

        data = summary.to_list_item_dict()

        assert data["previous_summary_id"] == "week4"
        assert data["continuity_week_number"] == 5

    def test_from_dict_parses_continuity(self):
        """Test that from_dict parses continuity fields."""
        data = {
            "id": "test",
            "guild_id": "guild123",
            "source_channel_ids": ["channel456"],
            "title": "Test",
            "created_at": datetime.utcnow().isoformat(),
            "previous_summary_id": "previous",
            "continuity_week_number": 7,
        }

        summary = StoredSummary.from_dict(data)

        assert summary.previous_summary_id == "previous"
        assert summary.continuity_week_number == 7
