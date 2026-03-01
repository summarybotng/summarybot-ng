"""
Pytest fixtures for data layer tests.

This module provides fixtures specifically for testing the data layer,
including in-memory SQLite databases, repository factories, and test data.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from typing import AsyncGenerator

from src.data.sqlite import SQLiteConnection, SQLiteSummaryRepository, SQLiteConfigRepository, SQLiteTaskRepository, SQLiteStoredSummaryRepository
from src.data.base import SearchCriteria
from src.models.summary import (
    SummaryResult, SummaryOptions, ActionItem, TechnicalTerm,
    Participant, SummarizationContext, Priority, SummaryLength
)
from src.models.task import (
    ScheduledTask, TaskResult, Destination, TaskStatus,
    ScheduleType, DestinationType, TaskType
)
from src.config.settings import GuildConfig, PermissionSettings


@pytest_asyncio.fixture
async def in_memory_db() -> AsyncGenerator[SQLiteConnection, None]:
    """Create an in-memory SQLite database for testing."""
    connection = SQLiteConnection(":memory:", pool_size=1)
    await connection.connect()

    # Create tables
    await _create_schema(connection)

    yield connection

    # Cleanup
    await connection.disconnect()


async def _create_schema(connection: SQLiteConnection) -> None:
    """Create database schema for testing."""
    # Summaries table
    await connection.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            id TEXT PRIMARY KEY,
            channel_id TEXT NOT NULL,
            guild_id TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            message_count INTEGER NOT NULL,
            summary_text TEXT NOT NULL,
            key_points TEXT NOT NULL,
            action_items TEXT NOT NULL,
            technical_terms TEXT NOT NULL,
            participants TEXT NOT NULL,
            metadata TEXT NOT NULL,
            created_at TEXT NOT NULL,
            context TEXT
        )
    """)

    # Guild configs table
    await connection.execute("""
        CREATE TABLE IF NOT EXISTS guild_configs (
            guild_id TEXT PRIMARY KEY,
            enabled_channels TEXT NOT NULL,
            excluded_channels TEXT NOT NULL,
            default_summary_options TEXT NOT NULL,
            permission_settings TEXT NOT NULL,
            webhook_enabled INTEGER DEFAULT 0,
            webhook_secret TEXT
        )
    """)

    # Scheduled tasks table
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
            retry_delay_minutes INTEGER DEFAULT 5
        )
    """)

    # Task results table
    await connection.execute("""
        CREATE TABLE IF NOT EXISTS task_results (
            execution_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            summary_id TEXT,
            error_message TEXT,
            error_details TEXT,
            delivery_results TEXT NOT NULL,
            execution_time_seconds REAL,
            FOREIGN KEY (task_id) REFERENCES scheduled_tasks(id)
        )
    """)

    # Stored summaries table (ADR-008, ADR-012, ADR-017)
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
            FOREIGN KEY (schedule_id) REFERENCES scheduled_tasks(id) ON DELETE SET NULL
        )
    """)


@pytest_asyncio.fixture
async def summary_repository(in_memory_db: SQLiteConnection) -> SQLiteSummaryRepository:
    """Create a summary repository with in-memory database."""
    return SQLiteSummaryRepository(in_memory_db)


@pytest_asyncio.fixture
async def config_repository(in_memory_db: SQLiteConnection) -> SQLiteConfigRepository:
    """Create a config repository with in-memory database."""
    return SQLiteConfigRepository(in_memory_db)


@pytest_asyncio.fixture
async def task_repository(in_memory_db: SQLiteConnection) -> SQLiteTaskRepository:
    """Create a task repository with in-memory database."""
    return SQLiteTaskRepository(in_memory_db)


@pytest_asyncio.fixture
async def stored_summary_repository(in_memory_db: SQLiteConnection) -> SQLiteStoredSummaryRepository:
    """Create a stored summary repository with in-memory database."""
    return SQLiteStoredSummaryRepository(in_memory_db)


@pytest.fixture
def sample_summary_result() -> SummaryResult:
    """Create a sample summary result for testing."""
    now = datetime.utcnow()

    context = SummarizationContext(
        channel_name="test-channel",
        guild_name="Test Guild",
        total_participants=3,
        time_span_hours=2.5,
        message_types={"text": 45, "image": 3},
        dominant_topics=["testing", "development"],
        thread_count=2
    )

    return SummaryResult(
        id="test-summary-123",
        channel_id="channel-456",
        guild_id="guild-789",
        start_time=now - timedelta(hours=2),
        end_time=now,
        message_count=48,
        key_points=[
            "Discussed project architecture",
            "Reviewed pull requests",
            "Planned next sprint"
        ],
        action_items=[
            ActionItem(
                description="Update documentation",
                assignee="user123",
                priority=Priority.HIGH,
                source_message_ids=["msg1", "msg2"]
            ),
            ActionItem(
                description="Fix bug in authentication",
                priority=Priority.MEDIUM,
                source_message_ids=["msg3"]
            )
        ],
        technical_terms=[
            TechnicalTerm(
                term="OAuth2",
                definition="Open standard for access delegation",
                context="Used in authentication flow",
                source_message_id="msg4",
                category="security"
            )
        ],
        participants=[
            Participant(
                user_id="user123",
                display_name="Alice",
                message_count=20,
                key_contributions=["Proposed new architecture"],
                first_message_time=now - timedelta(hours=2),
                last_message_time=now - timedelta(minutes=30)
            ),
            Participant(
                user_id="user456",
                display_name="Bob",
                message_count=18,
                key_contributions=["Reviewed code"],
                first_message_time=now - timedelta(hours=1, minutes=45),
                last_message_time=now
            )
        ],
        summary_text="The team discussed project architecture and reviewed pull requests.",
        metadata={"version": "1.0", "model": "claude-3-sonnet"},
        created_at=now,
        context=context
    )


@pytest.fixture
def sample_guild_config() -> GuildConfig:
    """Create a sample guild configuration for testing."""
    return GuildConfig(
        guild_id="guild-789",
        enabled_channels=["channel-456", "channel-789"],
        excluded_channels=["spam-channel"],
        default_summary_options=SummaryOptions(
            summary_length=SummaryLength.DETAILED,
            include_bots=False,
            include_attachments=True,
            min_messages=5,
            extract_action_items=True,
            extract_technical_terms=True
        ),
        permission_settings=PermissionSettings(
            admin_roles=["admin", "moderator"],
            allowed_channels=["channel-456"],
            denied_users=["spammer123"]
        ),
        webhook_enabled=True,
        webhook_secret="test-secret-key"
    )


@pytest.fixture
def sample_scheduled_task() -> ScheduledTask:
    """Create a sample scheduled task for testing."""
    now = datetime.utcnow()

    return ScheduledTask(
        id="task-123",
        name="Daily Summary",
        channel_id="channel-456",
        guild_id="guild-789",
        task_type=TaskType.SUMMARY,
        schedule_type=ScheduleType.DAILY,
        schedule_time="09:00",
        schedule_days=[0, 1, 2, 3, 4],  # Weekdays
        destinations=[
            Destination(
                type=DestinationType.DISCORD_CHANNEL,
                target="summary-channel",
                format="embed",
                enabled=True
            ),
            Destination(
                type=DestinationType.WEBHOOK,
                target="https://example.com/webhook",
                format="json",
                enabled=True
            )
        ],
        summary_options=SummaryOptions(
            summary_length=SummaryLength.BRIEF,
            include_bots=False
        ),
        is_active=True,
        created_at=now - timedelta(days=7),
        created_by="admin-user",
        last_run=now - timedelta(days=1),
        next_run=now + timedelta(hours=8),
        run_count=7,
        failure_count=0,
        max_failures=3,
        retry_delay_minutes=5
    )


@pytest.fixture
def sample_task_result() -> TaskResult:
    """Create a sample task result for testing."""
    now = datetime.utcnow()

    result = TaskResult(
        task_id="task-123",
        execution_id="exec-456",
        status=TaskStatus.COMPLETED,
        started_at=now - timedelta(seconds=45),
        completed_at=now,
        summary_id="summary-789",
        execution_time_seconds=45.2
    )

    result.add_delivery_result(
        destination_type="discord_channel",
        target="summary-channel",
        success=True,
        message="Successfully posted to channel"
    )

    result.add_delivery_result(
        destination_type="webhook",
        target="https://example.com/webhook",
        success=True,
        message="Webhook delivered"
    )

    return result


@pytest.fixture
def search_criteria() -> SearchCriteria:
    """Create sample search criteria for testing."""
    return SearchCriteria(
        guild_id="guild-789",
        channel_id="channel-456",
        start_time=datetime.utcnow() - timedelta(days=7),
        end_time=datetime.utcnow(),
        limit=10,
        offset=0,
        order_by="created_at",
        order_direction="DESC"
    )
