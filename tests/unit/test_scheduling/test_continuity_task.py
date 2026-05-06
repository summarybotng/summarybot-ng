"""
Tests for ADR-087: Weekly Continuity in ScheduledTask model.

Tests the enable_continuity field on ScheduledTask.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from typing import AsyncGenerator

from src.data.sqlite import SQLiteConnection, SQLiteTaskRepository
from src.models.task import (
    ScheduledTask, ScheduleType, Destination, DestinationType, TaskType
)
from src.models.summary import SummaryOptions, SummaryLength


@pytest_asyncio.fixture
async def task_db() -> AsyncGenerator[SQLiteConnection, None]:
    """Create an in-memory SQLite database for task testing."""
    connection = SQLiteConnection(":memory:", pool_size=1)
    await connection.connect()

    # Create scheduled_tasks table with enable_continuity
    await connection.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            guild_id TEXT NOT NULL,
            schedule_type TEXT NOT NULL,
            schedule_time TEXT,
            schedule_days TEXT NOT NULL,
            cron_expression TEXT,
            destinations TEXT NOT NULL,
            summary_options TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            last_run TEXT,
            next_run TEXT,
            run_count INTEGER DEFAULT 0,
            failure_count INTEGER DEFAULT 0,
            max_failures INTEGER DEFAULT 3,
            retry_delay_minutes INTEGER DEFAULT 5,
            scope TEXT,
            channel_ids TEXT DEFAULT '[]',
            category_id TEXT,
            excluded_channel_ids TEXT DEFAULT '[]',
            resolve_category_at_runtime INTEGER DEFAULT 0,
            timezone TEXT DEFAULT 'UTC',
            prompt_template_id TEXT,
            platform TEXT DEFAULT 'discord',
            enable_continuity INTEGER DEFAULT 0
        )
    """)

    yield connection
    await connection.disconnect()


@pytest_asyncio.fixture
async def task_repo(task_db: SQLiteConnection) -> SQLiteTaskRepository:
    """Create a task repository for testing."""
    return SQLiteTaskRepository(task_db)


def create_weekly_task(
    task_id: str = "task123",
    name: str = "Weekly Summary",
    enable_continuity: bool = False,
) -> ScheduledTask:
    """Helper to create a weekly scheduled task."""
    return ScheduledTask(
        id=task_id,
        name=name,
        channel_id="channel456",
        channel_ids=["channel456"],
        guild_id="guild789",
        task_type=TaskType.SUMMARY,
        schedule_type=ScheduleType.WEEKLY,
        schedule_time="09:00",
        schedule_days=[0],  # Sunday
        destinations=[
            Destination(
                type=DestinationType.DASHBOARD,
                target="default",
                format="embed",
                enabled=True,
            )
        ],
        summary_options=SummaryOptions(
            summary_length=SummaryLength.DETAILED,
        ),
        is_active=True,
        created_at=datetime.utcnow(),
        created_by="user123",
        timezone="UTC",
        enable_continuity=enable_continuity,
    )


class TestEnableContinuityField:
    """Tests for enable_continuity field on ScheduledTask."""

    def test_default_value_is_false(self):
        """Test that enable_continuity defaults to False."""
        task = ScheduledTask(
            id="test",
            name="Test",
            channel_id="ch1",
            guild_id="g1",
            created_by="u1",
        )
        assert task.enable_continuity is False

    def test_can_set_enable_continuity_true(self):
        """Test setting enable_continuity to True."""
        task = create_weekly_task(enable_continuity=True)
        assert task.enable_continuity is True

    def test_can_set_enable_continuity_false(self):
        """Test setting enable_continuity to False explicitly."""
        task = create_weekly_task(enable_continuity=False)
        assert task.enable_continuity is False


class TestEnableContinuityPersistence:
    """Tests for persisting enable_continuity to database."""

    @pytest.mark.asyncio
    async def test_save_task_with_continuity_enabled(self, task_repo: SQLiteTaskRepository):
        """Test saving a task with enable_continuity=True."""
        task = create_weekly_task(task_id="cont1", enable_continuity=True)

        await task_repo.save_task(task)

        # Retrieve and verify
        retrieved = await task_repo.get_task("cont1")
        assert retrieved is not None
        assert retrieved.enable_continuity is True

    @pytest.mark.asyncio
    async def test_save_task_with_continuity_disabled(self, task_repo: SQLiteTaskRepository):
        """Test saving a task with enable_continuity=False."""
        task = create_weekly_task(task_id="nocont1", enable_continuity=False)

        await task_repo.save_task(task)

        # Retrieve and verify
        retrieved = await task_repo.get_task("nocont1")
        assert retrieved is not None
        assert retrieved.enable_continuity is False

    @pytest.mark.asyncio
    async def test_update_task_continuity(self, task_repo: SQLiteTaskRepository):
        """Test updating enable_continuity on an existing task."""
        # Create with continuity disabled
        task = create_weekly_task(task_id="update1", enable_continuity=False)
        await task_repo.save_task(task)

        # Update to enable continuity
        task.enable_continuity = True
        await task_repo.save_task(task)

        # Retrieve and verify
        retrieved = await task_repo.get_task("update1")
        assert retrieved.enable_continuity is True

    @pytest.mark.asyncio
    async def test_get_active_tasks_with_continuity(self, task_repo: SQLiteTaskRepository):
        """Test that active tasks include continuity field."""
        task1 = create_weekly_task(task_id="active1", enable_continuity=True)
        task2 = create_weekly_task(task_id="active2", enable_continuity=False)

        await task_repo.save_task(task1)
        await task_repo.save_task(task2)

        active_tasks = await task_repo.get_active_tasks()

        assert len(active_tasks) == 2

        # Find tasks by ID and verify continuity
        task1_found = next(t for t in active_tasks if t.id == "active1")
        task2_found = next(t for t in active_tasks if t.id == "active2")

        assert task1_found.enable_continuity is True
        assert task2_found.enable_continuity is False

    @pytest.mark.asyncio
    async def test_get_tasks_by_guild_with_continuity(self, task_repo: SQLiteTaskRepository):
        """Test that tasks by guild include continuity field."""
        task = create_weekly_task(task_id="guild1", enable_continuity=True)
        await task_repo.save_task(task)

        tasks = await task_repo.get_tasks_by_guild("guild789")

        assert len(tasks) == 1
        assert tasks[0].enable_continuity is True


class TestContinuityOnlyForWeekly:
    """Tests verifying continuity makes sense for weekly schedules."""

    def test_daily_task_can_have_continuity_field(self):
        """Daily tasks can have the field but it won't be used."""
        task = ScheduledTask(
            id="daily1",
            name="Daily",
            channel_id="ch1",
            guild_id="g1",
            schedule_type=ScheduleType.DAILY,
            created_by="u1",
            enable_continuity=True,  # Set but won't be used
        )
        # Field exists but executor will ignore for non-weekly
        assert task.enable_continuity is True
        assert task.schedule_type == ScheduleType.DAILY

    def test_weekly_task_schedule_type(self):
        """Verify weekly task has correct schedule type."""
        task = create_weekly_task(enable_continuity=True)
        assert task.schedule_type == ScheduleType.WEEKLY
        assert task.enable_continuity is True
