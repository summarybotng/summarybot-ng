"""
Unit tests for data models.

Tests cover:
- SummaryResult serialization/deserialization
- ProcessedMessage model
- ScheduledTask model
- Model validation
- to_dict/from_dict methods
- JSON serialization
"""

import pytest
import json
from datetime import datetime, timedelta

from src.models.summary import (
    SummaryResult, SummaryOptions, ActionItem, TechnicalTerm,
    Participant, SummarizationContext, Priority, SummaryLength
)
from src.models.task import (
    ScheduledTask, TaskResult, Destination, TaskStatus,
    ScheduleType, DestinationType, TaskType
)
from src.models.base import generate_id, utc_now


class TestBaseModel:
    """Test base model functionality."""

    def test_generate_id_unique(self):
        """Test that generate_id produces unique IDs."""
        ids = [generate_id() for _ in range(100)]
        assert len(set(ids)) == 100

    def test_generate_id_format(self):
        """Test that generated IDs are valid UUIDs."""
        id_str = generate_id()
        # UUID4 format: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
        assert len(id_str) == 36
        assert id_str.count('-') == 4

    def test_utc_now_no_microseconds(self):
        """Test that utc_now returns datetime without microseconds."""
        now = utc_now()
        assert now.microsecond == 0


class TestActionItem:
    """Test ActionItem model."""

    def test_action_item_creation(self):
        """Test creating an action item."""
        item = ActionItem(
            description="Fix the bug",
            assignee="user123",
            priority=Priority.HIGH,
            source_message_ids=["msg1", "msg2"]
        )

        assert item.description == "Fix the bug"
        assert item.assignee == "user123"
        assert item.priority == Priority.HIGH
        assert not item.completed

    def test_action_item_to_dict(self):
        """Test converting action item to dictionary."""
        item = ActionItem(
            description="Test task",
            priority=Priority.MEDIUM
        )

        item_dict = item.to_dict()

        assert item_dict["description"] == "Test task"
        assert item_dict["priority"] == Priority.MEDIUM.value
        assert "source_message_ids" in item_dict

    def test_action_item_to_markdown(self):
        """Test converting action item to markdown."""
        item = ActionItem(
            description="Review PR",
            assignee="alice",
            priority=Priority.HIGH,
            completed=False
        )

        markdown = item.to_markdown()

        assert "Review PR" in markdown
        assert "@alice" in markdown
        assert "🔴" in markdown  # High priority emoji

    def test_action_item_completed_markdown(self):
        """Test markdown for completed action item."""
        item = ActionItem(
            description="Done task",
            completed=True,
            priority=Priority.LOW
        )

        markdown = item.to_markdown()

        assert "✅" in markdown  # Completed emoji


class TestTechnicalTerm:
    """Test TechnicalTerm model."""

    def test_technical_term_creation(self):
        """Test creating a technical term."""
        term = TechnicalTerm(
            term="REST API",
            definition="Representational State Transfer Application Programming Interface",
            context="Used for web services",
            source_message_id="msg123",
            category="web"
        )

        assert term.term == "REST API"
        assert term.category == "web"

    def test_technical_term_to_markdown(self):
        """Test converting technical term to markdown."""
        term = TechnicalTerm(
            term="OAuth",
            definition="Open Authorization protocol",
            context="Authentication",
            source_message_id="msg1"
        )

        markdown = term.to_markdown()

        assert "**OAuth**" in markdown
        assert "Open Authorization protocol" in markdown


class TestParticipant:
    """Test Participant model."""

    def test_participant_creation(self):
        """Test creating a participant."""
        now = datetime.utcnow()
        participant = Participant(
            user_id="user123",
            display_name="Alice",
            message_count=15,
            key_contributions=["Proposed solution", "Found bug"],
            first_message_time=now - timedelta(hours=1),
            last_message_time=now
        )

        assert participant.display_name == "Alice"
        assert participant.message_count == 15
        assert len(participant.key_contributions) == 2

    def test_participant_to_markdown(self):
        """Test converting participant to markdown."""
        participant = Participant(
            user_id="user1",
            display_name="Bob",
            message_count=10,
            key_contributions=["Fixed issue", "Reviewed code"]
        )

        markdown = participant.to_markdown()

        assert "**Bob**" in markdown
        assert "(10 messages)" in markdown
        assert "Fixed issue" in markdown


class TestSummarizationContext:
    """Test SummarizationContext model."""

    def test_context_creation(self):
        """Test creating summarization context."""
        context = SummarizationContext(
            channel_name="general",
            guild_name="Test Server",
            total_participants=5,
            time_span_hours=3.5,
            message_types={"text": 100, "image": 5},
            dominant_topics=["testing", "deployment"],
            thread_count=2
        )

        assert context.channel_name == "general"
        assert context.total_participants == 5
        assert context.time_span_hours == 3.5
        assert len(context.dominant_topics) == 2

    def test_context_to_dict(self):
        """Test converting context to dictionary."""
        context = SummarizationContext(
            channel_name="dev",
            guild_name="Company",
            total_participants=3,
            time_span_hours=2.0
        )

        context_dict = context.to_dict()

        assert context_dict["channel_name"] == "dev"
        assert context_dict["total_participants"] == 3


class TestSummaryOptions:
    """Test SummaryOptions model."""

    def test_default_options(self):
        """Test default summary options."""
        options = SummaryOptions()

        assert options.summary_length == SummaryLength.DETAILED
        assert options.include_bots is False
        assert options.extract_action_items is True

    def test_custom_options(self):
        """Test creating custom summary options."""
        options = SummaryOptions(
            summary_length=SummaryLength.BRIEF,
            include_bots=True,
            min_messages=10,
            temperature=0.5
        )

        assert options.summary_length == SummaryLength.BRIEF
        assert options.include_bots is True
        assert options.min_messages == 10

    def test_get_max_tokens_for_length(self):
        """Test getting max tokens based on summary length."""
        brief = SummaryOptions(summary_length=SummaryLength.BRIEF)
        assert brief.get_max_tokens_for_length() == 1000

        detailed = SummaryOptions(summary_length=SummaryLength.DETAILED)
        assert detailed.get_max_tokens_for_length() == 4000

        comprehensive = SummaryOptions(summary_length=SummaryLength.COMPREHENSIVE)
        assert comprehensive.get_max_tokens_for_length() == 8000

    def test_get_system_prompt_additions(self):
        """Test getting system prompt additions."""
        options = SummaryOptions(
            summary_length=SummaryLength.BRIEF,
            extract_action_items=False
        )

        additions = options.get_system_prompt_additions()

        assert any("action items" in add.lower() for add in additions)
        assert any("concise" in add.lower() for add in additions)

    def test_options_serialization(self):
        """Test serializing summary options."""
        options = SummaryOptions(
            summary_length=SummaryLength.COMPREHENSIVE,
            include_bots=True
        )

        options_dict = options.to_dict()

        assert options_dict["summary_length"] == SummaryLength.COMPREHENSIVE.value
        assert options_dict["include_bots"] is True


class TestSummaryResult:
    """Test SummaryResult model."""

    def test_summary_result_creation(self, sample_summary_result: SummaryResult):
        """Test creating a summary result."""
        assert sample_summary_result.id is not None
        assert sample_summary_result.message_count == 48
        assert len(sample_summary_result.key_points) == 3
        assert len(sample_summary_result.action_items) == 2

    def test_summary_result_to_dict(self, sample_summary_result: SummaryResult):
        """Test converting summary result to dictionary."""
        result_dict = sample_summary_result.to_dict()

        assert result_dict["id"] == sample_summary_result.id
        assert result_dict["message_count"] == 48
        assert "key_points" in result_dict
        assert "action_items" in result_dict

    def test_summary_result_to_json(self, sample_summary_result: SummaryResult):
        """Test converting summary result to JSON."""
        json_str = sample_summary_result.to_json()

        assert isinstance(json_str, str)

        # Verify it's valid JSON
        parsed = json.loads(json_str)
        assert parsed["id"] == sample_summary_result.id

    def test_summary_result_to_embed_dict(self, sample_summary_result: SummaryResult):
        """Test converting summary result to Discord embed."""
        embed = sample_summary_result.to_embed_dict()

        assert "title" in embed
        assert "description" in embed
        assert "fields" in embed
        assert "footer" in embed
        assert embed["color"] == 0x4A90E2

    def test_summary_result_to_markdown(self, sample_summary_result: SummaryResult):
        """Test converting summary result to markdown."""
        markdown = sample_summary_result.to_markdown()

        assert "# 📋 Summary" in markdown
        assert sample_summary_result.summary_text in markdown
        assert "## 🎯 Key Points" in markdown
        assert "## 📝 Action Items" in markdown

    def test_get_summary_stats(self, sample_summary_result: SummaryResult):
        """Test getting summary statistics."""
        stats = sample_summary_result.get_summary_stats()

        assert stats["message_count"] == 48
        assert stats["participant_count"] == 2
        assert stats["key_points_count"] == 3
        assert stats["action_items_count"] == 2
        assert "time_span_hours" in stats


class TestDestination:
    """Test Destination model."""

    def test_destination_creation(self):
        """Test creating a destination."""
        dest = Destination(
            type=DestinationType.DISCORD_CHANNEL,
            target="channel-123",
            format="embed",
            enabled=True
        )

        assert dest.type == DestinationType.DISCORD_CHANNEL
        assert dest.target == "channel-123"
        assert dest.enabled is True

    def test_destination_to_display_string(self):
        """Test converting destination to display string."""
        dest = Destination(
            type=DestinationType.WEBHOOK,
            target="https://example.com/webhook",
            format="json",
            enabled=True
        )

        display = dest.to_display_string()

        assert "Webhook" in display
        assert "https://example.com/webhook" in display
        assert "✅" in display  # Enabled emoji

    def test_disabled_destination_display(self):
        """Test display string for disabled destination."""
        dest = Destination(
            type=DestinationType.EMAIL,
            target="test@example.com",
            format="markdown",
            enabled=False
        )

        display = dest.to_display_string()

        assert "❌" in display  # Disabled emoji


class TestScheduledTask:
    """Test ScheduledTask model."""

    def test_scheduled_task_creation(self, sample_scheduled_task: ScheduledTask):
        """Test creating a scheduled task."""
        assert sample_scheduled_task.id is not None
        assert sample_scheduled_task.name == "Daily Summary"
        assert sample_scheduled_task.schedule_type == ScheduleType.DAILY
        assert len(sample_scheduled_task.destinations) == 2

    def test_calculate_next_run_daily(self):
        """Test calculating next run for daily task."""
        task = ScheduledTask(
            id="task-1",
            name="Daily Task",
            channel_id="ch1",
            guild_id="g1",
            schedule_type=ScheduleType.DAILY,
            schedule_time="09:00",
            summary_options=SummaryOptions(),
            created_by="admin"
        )

        next_run = task.calculate_next_run()

        assert next_run is not None
        assert next_run.hour == 9
        assert next_run.minute == 0

    def test_calculate_next_run_weekly(self):
        """Test calculating next run for weekly task."""
        task = ScheduledTask(
            id="task-1",
            name="Weekly Task",
            channel_id="ch1",
            guild_id="g1",
            schedule_type=ScheduleType.WEEKLY,
            schedule_time="14:00",
            schedule_days=[1, 3],  # Tuesday and Thursday
            summary_options=SummaryOptions(),
            created_by="admin"
        )

        next_run = task.calculate_next_run()

        assert next_run is not None
        assert next_run.weekday() in [1, 3]

    def test_calculate_next_run_once(self):
        """Test calculating next run for one-time task."""
        task = ScheduledTask(
            id="task-1",
            name="One-time Task",
            channel_id="ch1",
            guild_id="g1",
            schedule_type=ScheduleType.ONCE,
            summary_options=SummaryOptions(),
            created_by="admin"
        )

        # Before first run
        next_run = task.calculate_next_run()
        assert next_run is not None

        # After first run
        task.last_run = datetime.utcnow()
        next_run = task.calculate_next_run()
        assert next_run is None

    def test_should_run_now(self):
        """Test checking if task should run."""
        task = ScheduledTask(
            id="task-1",
            name="Test Task",
            channel_id="ch1",
            guild_id="g1",
            schedule_type=ScheduleType.DAILY,
            is_active=True,
            summary_options=SummaryOptions(),
            created_by="admin"
        )

        # Set next_run to past
        task.next_run = datetime.utcnow() - timedelta(minutes=5)

        assert task.should_run_now() is True

    def test_should_not_run_when_inactive(self):
        """Test that inactive tasks don't run."""
        task = ScheduledTask(
            id="task-1",
            name="Inactive Task",
            channel_id="ch1",
            guild_id="g1",
            schedule_type=ScheduleType.DAILY,
            is_active=False,
            summary_options=SummaryOptions(),
            created_by="admin"
        )

        assert task.should_run_now() is False

    def test_mark_run_started(self):
        """Test marking a run as started."""
        task = ScheduledTask(
            id="task-1",
            name="Test Task",
            channel_id="ch1",
            guild_id="g1",
            schedule_type=ScheduleType.DAILY,
            summary_options=SummaryOptions(),
            created_by="admin"
        )

        initial_count = task.run_count

        task.mark_run_started()

        assert task.run_count == initial_count + 1
        assert task.last_run is not None

    def test_mark_run_completed(self):
        """Test marking a run as completed."""
        task = ScheduledTask(
            id="task-1",
            name="Test Task",
            channel_id="ch1",
            guild_id="g1",
            schedule_type=ScheduleType.DAILY,
            summary_options=SummaryOptions(),
            created_by="admin"
        )

        task.failure_count = 2
        task.mark_run_completed()

        assert task.failure_count == 0
        assert task.next_run is not None

    def test_mark_run_failed(self):
        """Test marking a run as failed."""
        task = ScheduledTask(
            id="task-1",
            name="Test Task",
            channel_id="ch1",
            guild_id="g1",
            schedule_type=ScheduleType.DAILY,
            max_failures=3,
            summary_options=SummaryOptions(),
            created_by="admin"
        )

        task.mark_run_failed()
        assert task.failure_count == 1
        assert task.is_active is True

        task.mark_run_failed()
        task.mark_run_failed()
        assert task.failure_count == 3
        assert task.is_active is False  # Should be deactivated

    def test_get_schedule_description(self, sample_scheduled_task: ScheduledTask):
        """Test getting human-readable schedule description."""
        description = sample_scheduled_task.get_schedule_description()

        assert "09:00" in description
        # Should include weekday names for weekly schedule

    def test_to_status_dict(self, sample_scheduled_task: ScheduledTask):
        """Test converting task to status dictionary."""
        status = sample_scheduled_task.to_status_dict()

        assert status["id"] == sample_scheduled_task.id
        assert status["name"] == sample_scheduled_task.name
        assert status["is_active"] == sample_scheduled_task.is_active
        assert "destinations" in status


class TestTaskResult:
    """Test TaskResult model."""

    def test_task_result_creation(self, sample_task_result: TaskResult):
        """Test creating a task result."""
        assert sample_task_result.task_id == "task-123"
        assert sample_task_result.status == TaskStatus.COMPLETED
        assert sample_task_result.summary_id == "summary-789"

    def test_mark_completed(self):
        """Test marking task result as completed."""
        result = TaskResult(
            task_id="task-1",
            status=TaskStatus.RUNNING
        )

        result.mark_completed("summary-123")

        assert result.status == TaskStatus.COMPLETED
        assert result.summary_id == "summary-123"
        assert result.completed_at is not None
        assert result.execution_time_seconds is not None

    def test_mark_failed(self):
        """Test marking task result as failed."""
        result = TaskResult(
            task_id="task-1",
            status=TaskStatus.RUNNING
        )

        result.mark_failed("Connection timeout", {"code": "TIMEOUT"})

        assert result.status == TaskStatus.FAILED
        assert result.error_message == "Connection timeout"
        assert result.error_details["code"] == "TIMEOUT"
        assert result.completed_at is not None

    def test_add_delivery_result(self):
        """Test adding a delivery result."""
        result = TaskResult(task_id="task-1")

        result.add_delivery_result(
            destination_type="discord_channel",
            target="channel-123",
            success=True,
            message="Delivered successfully"
        )

        assert len(result.delivery_results) == 1
        assert result.delivery_results[0]["success"] is True
        assert result.delivery_results[0]["target"] == "channel-123"

    def test_get_summary_text_completed(self, sample_task_result: TaskResult):
        """Test getting summary text for completed task."""
        summary = sample_task_result.get_summary_text()

        assert "✅" in summary
        assert "Completed" in summary
        assert "2/2 deliveries successful" in summary

    def test_get_summary_text_failed(self):
        """Test getting summary text for failed task."""
        result = TaskResult(
            task_id="task-1",
            status=TaskStatus.FAILED,
            error_message="Network error"
        )
        result.completed_at = datetime.utcnow()
        result.execution_time_seconds = 10.5

        summary = result.get_summary_text()

        assert "❌" in summary
        assert "Failed" in summary
        assert "Network error" in summary
