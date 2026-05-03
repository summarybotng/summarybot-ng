"""
Tests for Wiki Regeneration Service (ADR-084).
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.wiki.regeneration import (
    WikiRegenerationService,
    RegenerationScope,
    RegenerationStatus,
    RegenerationJob,
    BULK_INGEST_THRESHOLD,
)


@pytest.fixture
def mock_wiki_repo():
    """Create a mock wiki repository."""
    repo = MagicMock()
    repo.connection = AsyncMock()
    repo.get_page = AsyncMock()
    repo.save_synthesis = AsyncMock()
    return repo


@pytest.fixture
def mock_claude_client():
    """Create a mock Claude client."""
    return AsyncMock()


@pytest.fixture
def service(mock_wiki_repo, mock_claude_client):
    """Create regeneration service with mocks."""
    return WikiRegenerationService(mock_wiki_repo, mock_claude_client)


class TestRegenerationService:
    """Tests for WikiRegenerationService."""

    @pytest.mark.asyncio
    async def test_create_job_full_scope(self, service, mock_wiki_repo):
        """Test creating a full regeneration job."""
        # Mock page count query
        mock_wiki_repo.connection.fetch_one = AsyncMock(
            return_value={"count": 25}
        )

        job = await service.create_job(
            guild_id="guild_123",
            scope=RegenerationScope.FULL,
            created_by="user_abc",
        )

        assert job.id.startswith("regen_")
        assert job.guild_id == "guild_123"
        assert job.scope == RegenerationScope.FULL
        assert job.status == RegenerationStatus.PENDING
        assert job.page_count == 25
        assert job.min_sources == 2  # Default
        assert job.created_by == "user_abc"

    @pytest.mark.asyncio
    async def test_create_job_with_min_sources(self, service, mock_wiki_repo):
        """Test creating a job with custom min_sources."""
        mock_wiki_repo.connection.fetch_one = AsyncMock(
            return_value={"count": 10}
        )

        job = await service.create_job(
            guild_id="guild_123",
            scope=RegenerationScope.FULL,
            min_sources=3,
            created_by="user_abc",
        )

        assert job.min_sources == 3

    @pytest.mark.asyncio
    async def test_create_job_selected_scope(self, service, mock_wiki_repo):
        """Test creating a job for selected summaries."""
        mock_wiki_repo.connection.fetch_one = AsyncMock(
            return_value={"count": 5}
        )

        job = await service.create_job(
            guild_id="guild_123",
            scope=RegenerationScope.SELECTED,
            summary_ids=["sum_1", "sum_2", "sum_3"],
        )

        assert job.scope == RegenerationScope.SELECTED
        assert job.summary_ids == ["sum_1", "sum_2", "sum_3"]

    @pytest.mark.asyncio
    async def test_should_auto_regenerate_below_threshold(self, service, mock_wiki_repo):
        """Test auto-regeneration check below threshold."""
        result = await service.should_auto_regenerate("guild_123", 2)
        assert result is False  # Below threshold

    @pytest.mark.asyncio
    async def test_should_auto_regenerate_above_threshold(self, service, mock_wiki_repo):
        """Test auto-regeneration check above threshold."""
        # No active job
        mock_wiki_repo.connection.fetch_one = AsyncMock(return_value=None)

        result = await service.should_auto_regenerate(
            "guild_123", BULK_INGEST_THRESHOLD
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_should_auto_regenerate_blocked_by_active_job(
        self, service, mock_wiki_repo
    ):
        """Test auto-regeneration blocked when job already running."""
        # Return an active job
        mock_wiki_repo.connection.fetch_one = AsyncMock(
            return_value={
                "id": "regen_existing",
                "guild_id": "guild_123",
                "scope": "full",
                "status": "processing",
                "summary_ids": None,
                "start_date": None,
                "end_date": None,
                "page_count": 10,
                "processed_count": 5,
                "started_at": datetime.utcnow().isoformat(),
                "completed_at": None,
                "error_message": None,
                "created_at": datetime.utcnow().isoformat(),
                "created_by": "user_123",
            }
        )

        result = await service.should_auto_regenerate(
            "guild_123", BULK_INGEST_THRESHOLD + 5
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_get_job_not_found(self, service, mock_wiki_repo):
        """Test getting non-existent job."""
        mock_wiki_repo.connection.fetch_one = AsyncMock(return_value=None)

        job = await service.get_job("regen_nonexistent")
        assert job is None

    @pytest.mark.asyncio
    async def test_trigger_auto_regeneration(self, service, mock_wiki_repo):
        """Test auto-triggering regeneration."""
        # No active job, above threshold
        mock_wiki_repo.connection.fetch_one = AsyncMock(
            side_effect=[
                None,  # get_active_job returns None
                {"count": 8},  # estimate_page_count
            ]
        )
        mock_wiki_repo.connection.execute = AsyncMock()

        summary_ids = [f"sum_{i}" for i in range(BULK_INGEST_THRESHOLD)]
        job = await service.trigger_auto_regeneration("guild_123", summary_ids)

        assert job is not None
        assert job.scope == RegenerationScope.SELECTED
        assert job.summary_ids == summary_ids
        assert job.created_by == "system:auto-regenerate"

    @pytest.mark.asyncio
    async def test_trigger_auto_regeneration_below_threshold(
        self, service, mock_wiki_repo
    ):
        """Test auto-trigger returns None below threshold."""
        summary_ids = ["sum_1", "sum_2"]  # Below threshold
        job = await service.trigger_auto_regeneration("guild_123", summary_ids)
        assert job is None


class TestRegenerationJob:
    """Tests for RegenerationJob dataclass."""

    def test_job_creation(self):
        """Test creating a regeneration job."""
        job = RegenerationJob(
            id="regen_test123",
            guild_id="guild_123",
            scope=RegenerationScope.FULL,
            status=RegenerationStatus.PENDING,
            page_count=10,
        )

        assert job.id == "regen_test123"
        assert job.scope == RegenerationScope.FULL
        assert job.status == RegenerationStatus.PENDING
        assert job.page_count == 10
        assert job.processed_count == 0
        assert job.min_sources == 2  # Default


class TestRegenerationScopes:
    """Tests for regeneration scopes."""

    def test_scope_values(self):
        """Test scope enum values."""
        assert RegenerationScope.SELECTED.value == "selected"
        assert RegenerationScope.DATE_RANGE.value == "date_range"
        assert RegenerationScope.FULL.value == "full"

    def test_status_values(self):
        """Test status enum values."""
        assert RegenerationStatus.PENDING.value == "pending"
        assert RegenerationStatus.PROCESSING.value == "processing"
        assert RegenerationStatus.COMPLETED.value == "completed"
        assert RegenerationStatus.FAILED.value == "failed"
