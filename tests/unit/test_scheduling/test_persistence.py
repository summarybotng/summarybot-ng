"""
Unit tests for task persistence.
"""

import pytest
import json
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, mock_open

from src.scheduling.persistence import TaskPersistence
from src.models.task import ScheduledTask, ScheduleType, Destination, DestinationType
from src.models.summary import SummaryOptions, SummaryLength
from src.exceptions import ConfigurationError


@pytest.fixture
def temp_storage(tmp_path):
    """Create temporary storage directory."""
    storage_path = tmp_path / "task_storage"
    storage_path.mkdir()
    return str(storage_path)


@pytest.fixture
def persistence(temp_storage):
    """Create TaskPersistence instance."""
    return TaskPersistence(storage_path=temp_storage)


@pytest.fixture
def sample_task():
    """Create a sample scheduled task."""
    return ScheduledTask(
        id="task_123",
        name="Daily Summary",
        channel_id="123456789",
        guild_id="987654321",
        schedule_type=ScheduleType.DAILY,
        schedule_time="09:00",
        destinations=[
            Destination(
                type=DestinationType.DISCORD_CHANNEL,
                target="123456789",
                format="embed",
                enabled=True
            )
        ],
        summary_options=SummaryOptions(
            summary_length=SummaryLength.DETAILED,
            min_messages=10
        ),
        is_active=True,
        created_at=datetime.utcnow(),
        created_by="user_456"
    )


@pytest.mark.asyncio
async def test_persistence_initialization(temp_storage):
    """Test TaskPersistence initialization."""
    persistence = TaskPersistence(storage_path=temp_storage)

    assert persistence.storage_path == Path(temp_storage)
    assert persistence.storage_path.exists()
    assert persistence.storage_path.is_dir()


@pytest.mark.asyncio
async def test_persistence_creates_directory():
    """Test that persistence creates storage directory if it doesn't exist."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        non_existent = Path(tmpdir) / "new_dir" / "tasks"

        persistence = TaskPersistence(storage_path=str(non_existent))

        assert persistence.storage_path.exists()


@pytest.mark.asyncio
async def test_save_task(persistence, sample_task):
    """Test saving a task to storage."""
    await persistence.save_task(sample_task)

    # Verify file was created
    task_file = persistence.storage_path / f"{sample_task.id}.json"
    assert task_file.exists()

    # Verify content
    with open(task_file, 'r') as f:
        data = json.load(f)

    assert data["id"] == sample_task.id
    assert data["name"] == sample_task.name
    assert data["channel_id"] == sample_task.channel_id


@pytest.mark.asyncio
async def test_load_task(persistence, sample_task):
    """Test loading a task from storage."""
    # Save task first
    await persistence.save_task(sample_task)

    # Load it back
    loaded_task = await persistence.load_task(sample_task.id)

    assert loaded_task is not None
    assert loaded_task.id == sample_task.id
    assert loaded_task.name == sample_task.name
    assert loaded_task.channel_id == sample_task.channel_id
    assert loaded_task.guild_id == sample_task.guild_id
    assert loaded_task.schedule_type == sample_task.schedule_type


@pytest.mark.asyncio
async def test_load_task_not_found(persistence):
    """Test loading a non-existent task."""
    loaded_task = await persistence.load_task("nonexistent_id")

    assert loaded_task is None


@pytest.mark.asyncio
async def test_load_all_tasks(persistence, sample_task):
    """Test loading all tasks from storage."""
    # Save multiple tasks
    tasks_to_save = []
    for i in range(5):
        task = ScheduledTask(
            id=f"task_{i}",
            name=f"Task {i}",
            channel_id=f"channel_{i}",
            guild_id="987654321",
            schedule_type=ScheduleType.DAILY
        )
        tasks_to_save.append(task)
        await persistence.save_task(task)

    # Load all tasks
    loaded_tasks = await persistence.load_all_tasks()

    assert len(loaded_tasks) == 5
    assert all(isinstance(task, ScheduledTask) for task in loaded_tasks)

    loaded_ids = {task.id for task in loaded_tasks}
    expected_ids = {f"task_{i}" for i in range(5)}
    assert loaded_ids == expected_ids


@pytest.mark.asyncio
async def test_load_all_tasks_empty_directory(persistence):
    """Test loading all tasks from empty storage."""
    tasks = await persistence.load_all_tasks()

    assert tasks == []


@pytest.mark.asyncio
async def test_update_task(persistence, sample_task):
    """Test updating an existing task."""
    # Save initial task
    await persistence.save_task(sample_task)

    # Modify task
    sample_task.name = "Updated Name"
    sample_task.is_active = False

    # Update it
    await persistence.update_task(sample_task)

    # Load and verify
    loaded_task = await persistence.load_task(sample_task.id)

    assert loaded_task.name == "Updated Name"
    assert loaded_task.is_active is False


@pytest.mark.asyncio
async def test_delete_task(persistence, sample_task):
    """Test deleting a task."""
    # Save task first
    await persistence.save_task(sample_task)

    # Verify it exists
    assert (persistence.storage_path / f"{sample_task.id}.json").exists()

    # Delete it
    result = await persistence.delete_task(sample_task.id)

    assert result is True
    assert not (persistence.storage_path / f"{sample_task.id}.json").exists()


@pytest.mark.asyncio
async def test_delete_task_not_found(persistence):
    """Test deleting a non-existent task."""
    result = await persistence.delete_task("nonexistent_id")

    assert result is False


@pytest.mark.asyncio
async def test_get_tasks_by_guild(persistence):
    """Test getting tasks filtered by guild ID."""
    # Create tasks for different guilds
    guild1_tasks = []
    guild2_tasks = []

    for i in range(3):
        task1 = ScheduledTask(
            id=f"guild1_task_{i}",
            channel_id="123456789",
            guild_id="guild_1",
            schedule_type=ScheduleType.DAILY
        )
        guild1_tasks.append(task1)
        await persistence.save_task(task1)

        task2 = ScheduledTask(
            id=f"guild2_task_{i}",
            channel_id="987654321",
            guild_id="guild_2",
            schedule_type=ScheduleType.DAILY
        )
        guild2_tasks.append(task2)
        await persistence.save_task(task2)

    # Get tasks for guild_1
    guild1_loaded = await persistence.get_tasks_by_guild("guild_1")

    assert len(guild1_loaded) == 3
    assert all(task.guild_id == "guild_1" for task in guild1_loaded)


@pytest.mark.asyncio
async def test_serialize_deserialize_task(persistence, sample_task):
    """Test task serialization and deserialization."""
    # Serialize
    serialized = persistence._serialize_task(sample_task)

    assert isinstance(serialized, dict)
    assert serialized["id"] == sample_task.id
    assert serialized["schedule_type"] == sample_task.schedule_type.value

    # Deserialize
    deserialized = persistence._deserialize_task(serialized)

    assert isinstance(deserialized, ScheduledTask)
    assert deserialized.id == sample_task.id
    assert deserialized.name == sample_task.name
    assert deserialized.schedule_type == sample_task.schedule_type


@pytest.mark.asyncio
async def test_serialize_task_with_all_fields(persistence):
    """Test serialization with all optional fields populated."""
    task = ScheduledTask(
        id="task_123",
        name="Complete Task",
        channel_id="123456789",
        guild_id="987654321",
        schedule_type=ScheduleType.WEEKLY,
        schedule_time="14:30",
        schedule_days=[0, 2, 4],
        cron_expression=None,
        destinations=[
            Destination(
                type=DestinationType.DISCORD_CHANNEL,
                target="123456789",
                format="embed",
                enabled=True
            ),
            Destination(
                type=DestinationType.WEBHOOK,
                target="https://example.com/webhook",
                format="json",
                enabled=False
            )
        ],
        summary_options=SummaryOptions(
            summary_length=SummaryLength.BRIEF,
            include_bots=True,
            extract_action_items=True
        ),
        is_active=True,
        created_at=datetime.utcnow(),
        created_by="user_456",
        last_run=datetime.utcnow() - timedelta(hours=1),
        next_run=datetime.utcnow() + timedelta(hours=23),
        run_count=5,
        failure_count=1,
        max_failures=3,
        retry_delay_minutes=10
    )

    serialized = persistence._serialize_task(task)
    deserialized = persistence._deserialize_task(serialized)

    assert deserialized.id == task.id
    assert len(deserialized.destinations) == 2
    assert deserialized.run_count == 5
    assert deserialized.failure_count == 1


@pytest.mark.asyncio
async def test_file_corruption_handling(persistence):
    """Test handling of corrupted JSON files."""
    # Create a corrupted file
    corrupted_file = persistence.storage_path / "corrupted_task.json"
    with open(corrupted_file, 'w') as f:
        f.write("{invalid json content")

    # Try to load it
    loaded_task = await persistence.load_task("corrupted_task")

    # Should return None instead of crashing
    assert loaded_task is None


@pytest.mark.asyncio
async def test_load_all_tasks_with_corrupted_file(persistence, sample_task):
    """Test that load_all_tasks continues despite corrupted files."""
    # Save a valid task
    await persistence.save_task(sample_task)

    # Create a corrupted file
    corrupted_file = persistence.storage_path / "corrupted_task.json"
    with open(corrupted_file, 'w') as f:
        f.write("{invalid}")

    # Load all tasks
    loaded_tasks = await persistence.load_all_tasks()

    # Should load the valid task and skip the corrupted one
    assert len(loaded_tasks) == 1
    assert loaded_tasks[0].id == sample_task.id


@pytest.mark.asyncio
async def test_cleanup_old_tasks(persistence):
    """Test cleaning up old inactive tasks."""
    # Create old inactive task
    old_task = ScheduledTask(
        id="old_task",
        channel_id="123456789",
        guild_id="987654321",
        schedule_type=ScheduleType.DAILY,
        is_active=False,
        last_run=datetime.utcnow() - timedelta(days=100)
    )
    await persistence.save_task(old_task)

    # Create recent inactive task
    recent_task = ScheduledTask(
        id="recent_task",
        channel_id="123456789",
        guild_id="987654321",
        schedule_type=ScheduleType.DAILY,
        is_active=False,
        last_run=datetime.utcnow() - timedelta(days=10)
    )
    await persistence.save_task(recent_task)

    # Create active task
    active_task = ScheduledTask(
        id="active_task",
        channel_id="123456789",
        guild_id="987654321",
        schedule_type=ScheduleType.DAILY,
        is_active=True,
        last_run=datetime.utcnow() - timedelta(days=100)
    )
    await persistence.save_task(active_task)

    # Cleanup tasks older than 90 days
    cleaned_count = await persistence.cleanup_old_tasks(days=90)

    # Only old inactive task should be cleaned
    assert cleaned_count == 1

    # Verify remaining tasks
    remaining_tasks = await persistence.load_all_tasks()
    remaining_ids = {task.id for task in remaining_tasks}

    assert "old_task" not in remaining_ids
    assert "recent_task" in remaining_ids
    assert "active_task" in remaining_ids


@pytest.mark.asyncio
async def test_export_tasks(persistence, sample_task, tmp_path):
    """Test exporting tasks to backup file."""
    # Save some tasks
    await persistence.save_task(sample_task)

    task2 = ScheduledTask(
        id="task_2",
        channel_id="111111111",
        guild_id="987654321",
        schedule_type=ScheduleType.WEEKLY
    )
    await persistence.save_task(task2)

    # Export tasks
    export_file = tmp_path / "export.json"
    result = await persistence.export_tasks(str(export_file))

    assert result is True
    assert export_file.exists()

    # Verify export content
    with open(export_file, 'r') as f:
        export_data = json.load(f)

    assert "export_date" in export_data
    assert export_data["task_count"] == 2
    assert len(export_data["tasks"]) == 2


@pytest.mark.asyncio
async def test_import_tasks(persistence, tmp_path):
    """Test importing tasks from backup file."""
    # Create export file
    export_data = {
        "export_date": datetime.utcnow().isoformat(),
        "task_count": 2,
        "tasks": [
            {
                "id": "imported_1",
                "name": "Imported Task 1",
                "channel_id": "123456789",
                "guild_id": "987654321",
                "schedule_type": "daily",
                "schedule_time": None,
                "schedule_days": [],
                "cron_expression": None,
                "destinations": [],
                "summary_options": {
                    "summary_length": "detailed",
                    "include_bots": False,
                    "include_attachments": True,
                    "excluded_users": [],
                    "min_messages": 5,
                    "claude_model": "claude-3-sonnet-20240229",
                    "temperature": 0.3,
                    "max_tokens": 4000,
                    "extract_action_items": True,
                    "extract_technical_terms": True,
                    "extract_key_points": True,
                    "include_participant_analysis": True
                },
                "is_active": True,
                "created_at": datetime.utcnow().isoformat(),
                "created_by": "user_123",
                "last_run": None,
                "next_run": None,
                "run_count": 0,
                "failure_count": 0,
                "max_failures": 3,
                "retry_delay_minutes": 5
            },
            {
                "id": "imported_2",
                "name": "Imported Task 2",
                "channel_id": "987654321",
                "guild_id": "123456789",
                "schedule_type": "weekly",
                "schedule_time": "10:00",
                "schedule_days": [0, 2, 4],
                "cron_expression": None,
                "destinations": [],
                "summary_options": {
                    "summary_length": "brief",
                    "include_bots": False,
                    "include_attachments": True,
                    "excluded_users": [],
                    "min_messages": 5,
                    "claude_model": "claude-3-sonnet-20240229",
                    "temperature": 0.3,
                    "max_tokens": 4000,
                    "extract_action_items": True,
                    "extract_technical_terms": True,
                    "extract_key_points": True,
                    "include_participant_analysis": True
                },
                "is_active": True,
                "created_at": datetime.utcnow().isoformat(),
                "created_by": "user_456",
                "last_run": None,
                "next_run": None,
                "run_count": 0,
                "failure_count": 0,
                "max_failures": 3,
                "retry_delay_minutes": 5
            }
        ]
    }

    import_file = tmp_path / "import.json"
    with open(import_file, 'w') as f:
        json.dump(export_data, f)

    # Import tasks
    imported_count = await persistence.import_tasks(str(import_file))

    assert imported_count == 2

    # Verify tasks were imported
    all_tasks = await persistence.load_all_tasks()
    imported_ids = {task.id for task in all_tasks}

    assert "imported_1" in imported_ids
    assert "imported_2" in imported_ids


@pytest.mark.asyncio
async def test_import_tasks_invalid_file(persistence, tmp_path):
    """Test importing from invalid file."""
    invalid_file = tmp_path / "invalid.json"
    invalid_file.write_text("{invalid json")

    imported_count = await persistence.import_tasks(str(invalid_file))

    assert imported_count == 0


@pytest.mark.asyncio
async def test_import_tasks_partial_failure(persistence, tmp_path):
    """Test that import continues despite individual task failures."""
    export_data = {
        "export_date": datetime.utcnow().isoformat(),
        "task_count": 2,
        "tasks": [
            {
                "id": "valid_task",
                "name": "Valid Task",
                "channel_id": "123456789",
                "guild_id": "987654321",
                "schedule_type": "daily",
                "schedule_time": None,
                "schedule_days": [],
                "cron_expression": None,
                "destinations": [],
                "summary_options": {
                    "summary_length": "detailed",
                    "include_bots": False,
                    "include_attachments": True,
                    "excluded_users": [],
                    "min_messages": 5,
                    "claude_model": "claude-3-sonnet-20240229",
                    "temperature": 0.3,
                    "max_tokens": 4000,
                    "extract_action_items": True,
                    "extract_technical_terms": True,
                    "extract_key_points": True,
                    "include_participant_analysis": True
                },
                "is_active": True,
                "created_at": datetime.utcnow().isoformat(),
                "created_by": "user_123",
                "last_run": None,
                "next_run": None,
                "run_count": 0,
                "failure_count": 0,
                "max_failures": 3,
                "retry_delay_minutes": 5
            },
            {
                # Missing required fields - will fail
                "id": "invalid_task"
            }
        ]
    }

    import_file = tmp_path / "partial.json"
    with open(import_file, 'w') as f:
        json.dump(export_data, f)

    imported_count = await persistence.import_tasks(str(import_file))

    # Should import only the valid task
    assert imported_count == 1

    loaded_task = await persistence.load_task("valid_task")
    assert loaded_task is not None


@pytest.mark.asyncio
async def test_concurrent_save_operations(persistence):
    """Test concurrent save operations don't corrupt data."""
    tasks = [
        ScheduledTask(
            id=f"concurrent_task_{i}",
            channel_id="123456789",
            guild_id="987654321",
            schedule_type=ScheduleType.DAILY
        )
        for i in range(10)
    ]

    # Save all tasks concurrently
    await asyncio.gather(*[persistence.save_task(task) for task in tasks])

    # Verify all were saved correctly
    loaded_tasks = await persistence.load_all_tasks()

    assert len(loaded_tasks) == 10
    loaded_ids = {task.id for task in loaded_tasks}
    expected_ids = {f"concurrent_task_{i}" for i in range(10)}
    assert loaded_ids == expected_ids


@pytest.mark.asyncio
async def test_concurrent_load_operations(persistence, sample_task):
    """Test concurrent load operations."""
    # Save task first
    await persistence.save_task(sample_task)

    # Load concurrently multiple times
    results = await asyncio.gather(*[
        persistence.load_task(sample_task.id)
        for _ in range(10)
    ])

    # All should succeed
    assert all(result is not None for result in results)
    assert all(result.id == sample_task.id for result in results)


@pytest.mark.asyncio
async def test_save_task_io_error(persistence, sample_task):
    """Test handling of IO errors during save."""
    with patch('builtins.open', mock_open()) as mock_file:
        mock_file.side_effect = IOError("Disk full")

        with pytest.raises(ConfigurationError) as exc_info:
            await persistence.save_task(sample_task)

        assert "persist" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_persistence_with_custom_path():
    """Test persistence with default path."""
    persistence = TaskPersistence()

    # Should use default path
    assert str(persistence.storage_path).endswith("data/tasks")

    # Should create the directory
    assert persistence.storage_path.exists()

    # Cleanup
    import shutil
    shutil.rmtree("./data", ignore_errors=True)
