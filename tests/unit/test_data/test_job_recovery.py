"""
Tests for ADR-013 job recovery on startup.

When the server restarts, jobs that were RUNNING should be marked PAUSED
with reason 'server_restart'.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.models.summary_job import SummaryJob, JobType, JobStatus


class TestJobRecovery:
    """Tests for interrupted job recovery."""

    @pytest.fixture
    def running_job(self):
        """Create a job in RUNNING status."""
        return SummaryJob(
            id="job_test123",
            guild_id="123456789",
            job_type=JobType.RETROSPECTIVE,
            status=JobStatus.RUNNING,
            progress_current=5,
            progress_total=10,
            started_at=datetime.utcnow(),
        )

    @pytest.fixture
    def completed_job(self):
        """Create a completed job."""
        return SummaryJob(
            id="job_done456",
            guild_id="123456789",
            job_type=JobType.RETROSPECTIVE,
            status=JobStatus.COMPLETED,
            progress_current=10,
            progress_total=10,
            completed_at=datetime.utcnow(),
        )

    def test_job_can_be_paused(self, running_job):
        """Test that a running job can be paused."""
        assert running_job.status == JobStatus.RUNNING
        running_job.pause("server_restart")
        assert running_job.status == JobStatus.PAUSED
        assert running_job.pause_reason == "server_restart"

    def test_job_can_be_resumed(self, running_job):
        """Test that a paused job can be resumed."""
        running_job.pause("server_restart")
        assert running_job.status == JobStatus.PAUSED
        running_job.resume()
        assert running_job.status == JobStatus.RUNNING
        assert running_job.pause_reason is None

    def test_job_preserves_progress_after_pause(self, running_job):
        """Test that job progress is preserved after pause."""
        original_progress = running_job.progress_current
        running_job.pause("server_restart")
        assert running_job.progress_current == original_progress

    def test_completed_job_not_affected(self, completed_job):
        """Test that completed jobs are not affected by recovery."""
        # Completed jobs should not be pauseable
        assert completed_job.status == JobStatus.COMPLETED
        # The can_cancel property returns False for completed jobs
        assert not completed_job.can_cancel


class TestMarkInterruptedJobs:
    """Tests for the repository mark_interrupted_jobs method."""

    @pytest.mark.asyncio
    async def test_mark_interrupted_jobs_updates_running(self):
        """Test that mark_interrupted_jobs updates RUNNING jobs to PAUSED."""
        from src.data.sqlite import SQLiteSummaryJobRepository

        # Create mock connection
        mock_connection = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 3  # Simulating 3 jobs marked

        mock_connection.execute = AsyncMock(return_value=mock_cursor)

        repo = SQLiteSummaryJobRepository(mock_connection)
        result = await repo.mark_interrupted_jobs("server_restart")

        # Verify the correct query was executed
        mock_connection.execute.assert_called_once()
        call_args = mock_connection.execute.call_args
        query = call_args[0][0]
        params = call_args[0][1]

        assert "UPDATE summary_jobs" in query
        assert "status = 'paused'" in query
        assert "WHERE status = 'running'" in query
        assert params == ("server_restart",)
        assert result == 3

    @pytest.mark.asyncio
    async def test_mark_interrupted_jobs_no_jobs(self):
        """Test mark_interrupted_jobs when no jobs are running."""
        from src.data.sqlite import SQLiteSummaryJobRepository

        mock_connection = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 0

        mock_connection.execute = AsyncMock(return_value=mock_cursor)

        repo = SQLiteSummaryJobRepository(mock_connection)
        result = await repo.mark_interrupted_jobs("server_restart")

        assert result == 0
