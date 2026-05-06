"""
Example test file demonstrating data module usage.

This file shows how to use the data module repositories and serves
as a reference for implementation.
"""

import asyncio
import pytest
import pytest_asyncio
from datetime import datetime
from pathlib import Path

from src.data import (
    initialize_repositories,
    get_summary_repository,
    get_config_repository,
    get_task_repository,
    SearchCriteria,
    run_migrations
)
from src.models.summary import (
    SummaryResult,
    SummaryOptions,
    ActionItem,
    TechnicalTerm,
    Participant,
    SummarizationContext,
    Priority,
    SummaryLength
)
from src.models.task import (
    ScheduledTask,
    TaskResult,
    Destination,
    TaskStatus,
    ScheduleType,
    DestinationType
)
from src.config.settings import GuildConfig, PermissionSettings


@pytest_asyncio.fixture
async def test_db():
    """Create a test database."""
    db_path = "tests/data/test_summarybot.db"
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    # Run migrations
    await run_migrations(db_path)

    # Initialize repositories
    initialize_repositories(backend="sqlite", db_path=db_path, pool_size=2)

    yield db_path

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_summary_repository(test_db):
    """Test summary repository operations."""
    repo = await get_summary_repository()

    # Create a test summary
    context = SummarizationContext(
        channel_name="general",
        guild_name="Test Server",
        total_participants=3,
        time_span_hours=2.5
    )

    summary = SummaryResult(
        channel_id="123456789",
        guild_id="987654321",
        start_time=datetime.utcnow(),
        end_time=datetime.utcnow(),
        message_count=50,
        key_points=["Point 1", "Point 2", "Point 3"],
        action_items=[
            ActionItem(
                description="Implement feature X",
                assignee="user123",
                priority=Priority.HIGH
            )
        ],
        technical_terms=[
            TechnicalTerm(
                term="API",
                definition="Application Programming Interface",
                context="Used to describe REST endpoints",
                source_message_id="msg123"
            )
        ],
        participants=[
            Participant(
                user_id="user1",
                display_name="Alice",
                message_count=25
            ),
            Participant(
                user_id="user2",
                display_name="Bob",
                message_count=15
            )
        ],
        summary_text="This is a comprehensive summary of the discussion.",
        context=context
    )

    # Save summary
    summary_id = await repo.save_summary(summary)
    assert summary_id == summary.id

    # Retrieve summary
    retrieved = await repo.get_summary(summary_id)
    assert retrieved is not None
    assert retrieved.id == summary_id
    assert retrieved.channel_id == summary.channel_id
    assert retrieved.message_count == summary.message_count
    assert len(retrieved.key_points) == 3

    # Search summaries
    criteria = SearchCriteria(
        guild_id="987654321",
        channel_id="123456789",
        limit=10
    )
    results = await repo.find_summaries(criteria)
    assert len(results) > 0
    assert results[0].id == summary_id

    # Count summaries
    count = await repo.count_summaries(criteria)
    assert count > 0

    # Get summaries by channel
    channel_summaries = await repo.get_summaries_by_channel("123456789", limit=5)
    assert len(channel_summaries) > 0

    # Delete summary
    deleted = await repo.delete_summary(summary_id)
    assert deleted is True

    # Verify deletion
    retrieved_after_delete = await repo.get_summary(summary_id)
    assert retrieved_after_delete is None


@pytest.mark.asyncio
async def test_config_repository(test_db):
    """Test configuration repository operations."""
    repo = await get_config_repository()

    # Create a test guild config
    config = GuildConfig(
        guild_id="123456789",
        enabled_channels=["channel1", "channel2"],
        excluded_channels=["channel3"],
        default_summary_options=SummaryOptions(
            summary_length=SummaryLength.DETAILED,
            include_bots=False
        ),
        permission_settings=PermissionSettings(
            allowed_roles=["role1", "role2"],
            require_permissions=True
        ),
        webhook_enabled=True,
        webhook_secret="secret123"
    )

    # Save config
    await repo.save_guild_config(config)

    # Retrieve config
    retrieved = await repo.get_guild_config("123456789")
    assert retrieved is not None
    assert retrieved.guild_id == "123456789"
    assert len(retrieved.enabled_channels) == 2
    assert retrieved.webhook_enabled is True

    # Get all configs
    all_configs = await repo.get_all_guild_configs()
    assert len(all_configs) > 0

    # Delete config
    deleted = await repo.delete_guild_config("123456789")
    assert deleted is True

    # Verify deletion
    retrieved_after_delete = await repo.get_guild_config("123456789")
    assert retrieved_after_delete is None


@pytest.mark.asyncio
async def test_task_repository(test_db):
    """Test task repository operations."""
    repo = await get_task_repository()

    # Create a test scheduled task
    task = ScheduledTask(
        name="Daily Summary",
        channel_id="123456789",
        guild_id="987654321",
        schedule_type=ScheduleType.DAILY,
        schedule_time="09:00",
        destinations=[
            Destination(
                type=DestinationType.DISCORD_CHANNEL,
                target="summary-channel",
                format="embed"
            )
        ],
        summary_options=SummaryOptions(),
        is_active=True,
        created_by="user123"
    )

    # Calculate next run
    task.next_run = task.calculate_next_run()

    # Save task
    task_id = await repo.save_task(task)
    assert task_id == task.id

    # Retrieve task
    retrieved = await repo.get_task(task_id)
    assert retrieved is not None
    assert retrieved.id == task_id
    assert retrieved.schedule_type == ScheduleType.DAILY

    # Get tasks by guild
    guild_tasks = await repo.get_tasks_by_guild("987654321")
    assert len(guild_tasks) > 0

    # Get active tasks
    active_tasks = await repo.get_active_tasks()
    assert len(active_tasks) > 0

    # Save task result
    result = TaskResult(
        task_id=task_id,
        status=TaskStatus.COMPLETED,
        summary_id="summary123"
    )
    result.mark_completed("summary123")

    result_id = await repo.save_task_result(result)
    assert result_id == result.execution_id

    # Get task results
    results = await repo.get_task_results(task_id, limit=10)
    assert len(results) > 0
    assert results[0].task_id == task_id

    # Delete task
    deleted = await repo.delete_task(task_id)
    assert deleted is True


if __name__ == "__main__":
    # Run a simple test
    async def main():
        db_path = "tests/data/test_summarybot.db"
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # Run migrations
        print("Running migrations...")
        await run_migrations(db_path)
        print("Migrations complete!")

        # Initialize repositories
        print("Initializing repositories...")
        initialize_repositories(backend="sqlite", db_path=db_path, pool_size=2)
        print("Repositories initialized!")

        # Test summary repository
        print("\nTesting summary repository...")
        repo = await get_summary_repository()

        context = SummarizationContext(
            channel_name="general",
            guild_name="Test Server",
            total_participants=2,
            time_span_hours=1.5
        )

        summary = SummaryResult(
            channel_id="123",
            guild_id="456",
            message_count=10,
            key_points=["Test point"],
            summary_text="Test summary",
            context=context
        )

        summary_id = await repo.save_summary(summary)
        print(f"Saved summary: {summary_id}")

        retrieved = await repo.get_summary(summary_id)
        print(f"Retrieved summary: {retrieved.id}")
        print(f"Summary stats: {retrieved.get_summary_stats()}")

        print("\nAll tests passed!")

    asyncio.run(main())
