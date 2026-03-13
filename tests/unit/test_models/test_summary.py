"""
Unit tests for summary models.

Tests cover SummaryResult, SummaryOptions, and related model functionality
as specified in Phase 3 module specifications.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
import json
import discord

from src.models.summary import SummaryResult, SummaryOptions, ActionItem, TechnicalTerm, Participant, Priority
from src.models.base import BaseModel


@pytest.mark.unit
class TestActionItem:
    """Test ActionItem model."""

    def test_action_item_creation(self):
        """Test ActionItem creation with required fields."""
        action = ActionItem(
            description="Complete the documentation",
            assignee="john_doe",
            deadline=datetime(2024, 12, 31, 23, 59),
            priority=Priority.HIGH
        )

        assert action.description == "Complete the documentation"
        assert action.assignee == "john_doe"
        assert action.deadline == datetime(2024, 12, 31, 23, 59)
        assert action.priority == Priority.HIGH

    def test_action_item_optional_fields(self):
        """Test ActionItem with optional fields."""
        action = ActionItem(
            description="Review code",
            assignee=None,
            deadline=None,
            priority=Priority.MEDIUM
        )

        assert action.assignee is None
        assert action.deadline is None


@pytest.mark.unit
class TestTechnicalTerm:
    """Test TechnicalTerm model."""

    def test_technical_term_creation(self):
        """Test TechnicalTerm creation."""
        term = TechnicalTerm(
            term="API",
            definition="Application Programming Interface",
            context="Used for service communication",
            source_message_id="msg_001"
        )

        assert term.term == "API"
        assert term.definition == "Application Programming Interface"
        assert term.context == "Used for service communication"
        assert term.source_message_id == "msg_001"

    def test_technical_term_with_category(self):
        """Test TechnicalTerm with optional category."""
        term = TechnicalTerm(
            term="REST",
            definition="Representational State Transfer",
            context="Web architecture",
            source_message_id="msg_002",
            category="networking"
        )

        assert term.category == "networking"


@pytest.mark.unit
class TestParticipant:
    """Test Participant model."""

    def test_participant_creation(self):
        """Test Participant creation."""
        participant = Participant(
            user_id="123456789",
            display_name="Test User",
            message_count=15,
            first_message_time=datetime(2024, 1, 1, 10, 0),
            last_message_time=datetime(2024, 1, 1, 12, 0)
        )

        assert participant.user_id == "123456789"
        assert participant.display_name == "Test User"
        assert participant.message_count == 15
        assert participant.first_message_time == datetime(2024, 1, 1, 10, 0)
        assert participant.last_message_time == datetime(2024, 1, 1, 12, 0)

    def test_participant_to_markdown(self):
        """Test participant to_markdown output."""
        participant = Participant(
            user_id="123456789",
            display_name="Test User",
            message_count=5,
            key_contributions=["Proposed new API design", "Fixed bug"],
            first_message_time=datetime(2024, 1, 1, 10, 0),
            last_message_time=datetime(2024, 1, 1, 11, 30)
        )

        md = participant.to_markdown()
        assert "Test User" in md
        assert "5 messages" in md
        assert "Proposed new API design" in md

    def test_participant_default_fields(self):
        """Test participant default field values."""
        participant = Participant(
            user_id="123456789",
            display_name="Test User",
            message_count=10,
        )

        assert participant.key_contributions == []
        assert participant.first_message_time is None
        assert participant.last_message_time is None


@pytest.mark.unit
class TestSummaryResult:
    """Test SummaryResult model and methods."""

    def test_summary_result_creation(self):
        """Test SummaryResult creation with required fields."""
        start_time = datetime(2024, 1, 1, 10, 0)
        end_time = datetime(2024, 1, 1, 12, 0)
        created_at = datetime(2024, 1, 1, 12, 1)

        participants = [
            Participant(
                user_id="123456789",
                display_name="Test User",
                message_count=10,
                first_message_time=start_time,
                last_message_time=end_time
            )
        ]

        action_items = [
            ActionItem(
                description="Complete task",
                assignee="testuser",
                deadline=datetime(2024, 1, 2),
                priority=Priority.HIGH
            )
        ]

        technical_terms = [
            TechnicalTerm(
                term="API",
                definition="Application Programming Interface",
                context="Service communication",
                source_message_id="msg_001"
            )
        ]

        summary = SummaryResult(
            id="summary_123",
            channel_id="987654321",
            guild_id="123456789",
            start_time=start_time,
            end_time=end_time,
            message_count=10,
            key_points=["Point 1", "Point 2", "Point 3"],
            action_items=action_items,
            technical_terms=technical_terms,
            participants=participants,
            summary_text="This is a comprehensive summary of the conversation.",
            metadata={"model": "claude-3-sonnet", "tokens": 1200},
            created_at=created_at
        )

        assert summary.id == "summary_123"
        assert summary.channel_id == "987654321"
        assert summary.guild_id == "123456789"
        assert summary.message_count == 10
        assert len(summary.key_points) == 3
        assert len(summary.action_items) == 1
        assert len(summary.technical_terms) == 1
        assert len(summary.participants) == 1
        assert "comprehensive summary" in summary.summary_text

    def test_summary_result_to_dict(self):
        """Test SummaryResult to_dict method."""
        start_time = datetime(2024, 1, 1, 10, 0)
        end_time = datetime(2024, 1, 1, 12, 0)

        summary = SummaryResult(
            id="summary_123",
            channel_id="987654321",
            guild_id="123456789",
            start_time=start_time,
            end_time=end_time,
            message_count=5,
            key_points=["Point 1"],
            action_items=[],
            technical_terms=[],
            participants=[],
            summary_text="Test summary",
            metadata={"test": "value"},
            created_at=datetime(2024, 1, 1, 12, 1)
        )

        result_dict = summary.to_dict()

        assert result_dict["id"] == "summary_123"
        assert result_dict["channel_id"] == "987654321"
        assert result_dict["message_count"] == 5
        assert result_dict["key_points"] == ["Point 1"]
        assert result_dict["metadata"]["test"] == "value"

        # Check datetime serialization
        assert isinstance(result_dict["start_time"], str)
        assert isinstance(result_dict["end_time"], str)

    def test_summary_result_to_embed_dict(self):
        """Test SummaryResult to_embed_dict method."""
        from src.models.summary import SummarizationContext

        start_time = datetime(2024, 1, 1, 10, 0)
        end_time = datetime(2024, 1, 1, 12, 0)

        participants = [
            Participant(
                user_id="123456789",
                display_name="Test User",
                message_count=5,
                first_message_time=start_time,
                last_message_time=end_time
            )
        ]

        context = SummarizationContext(
            channel_name="general",
            guild_name="Test Guild",
            total_participants=1,
            time_span_hours=2.0
        )

        summary = SummaryResult(
            id="summary_123",
            channel_id="987654321",
            guild_id="123456789",
            start_time=start_time,
            end_time=end_time,
            message_count=5,
            key_points=["Key point 1", "Key point 2"],
            action_items=[],
            technical_terms=[],
            participants=participants,
            summary_text="Test summary text",
            metadata={},
            created_at=datetime(2024, 1, 1, 12, 1),
            context=context
        )

        result = summary.to_embed_dict()

        # Verify embed dict structure
        assert "title" in result
        assert "description" in result
        assert "fields" in result
        assert "Test summary text" in result["description"]

    def test_summary_result_to_markdown(self):
        """Test SummaryResult to_markdown method."""
        from src.models.summary import SummarizationContext

        start_time = datetime(2024, 1, 1, 10, 0)
        end_time = datetime(2024, 1, 1, 12, 0)

        participants = [
            Participant(
                user_id="123456789",
                display_name="testuser",
                message_count=5,
                first_message_time=start_time,
                last_message_time=end_time
            )
        ]

        action_items = [
            ActionItem(
                description="Complete documentation",
                assignee="testuser",
                deadline=datetime(2024, 1, 2),
                priority=Priority.HIGH
            )
        ]

        context = SummarizationContext(
            channel_name="general",
            guild_name="Test Guild",
            total_participants=1,
            time_span_hours=2.0
        )

        summary = SummaryResult(
            id="summary_123",
            channel_id="987654321",
            guild_id="123456789",
            start_time=start_time,
            end_time=end_time,
            message_count=5,
            key_points=["Key point 1", "Key point 2"],
            action_items=action_items,
            technical_terms=[],
            participants=participants,
            summary_text="Test summary text",
            metadata={},
            created_at=datetime(2024, 1, 1, 12, 1),
            context=context
        )

        markdown = summary.to_markdown()

        # Verify markdown structure
        assert "Summary" in markdown
        assert "Key Points" in markdown
        assert "Action Items" in markdown
        assert "Participants" in markdown
        assert "Test summary text" in markdown
        assert "Key point 1" in markdown
        assert "Complete documentation" in markdown
        assert "testuser" in markdown

    def test_summary_result_to_json(self):
        """Test SummaryResult to_json method."""
        start_time = datetime(2024, 1, 1, 10, 0)
        end_time = datetime(2024, 1, 1, 12, 0)

        summary = SummaryResult(
            id="summary_123",
            channel_id="987654321",
            guild_id="123456789",
            start_time=start_time,
            end_time=end_time,
            message_count=5,
            key_points=["Point 1"],
            action_items=[],
            technical_terms=[],
            participants=[],
            summary_text="Test summary",
            metadata={},
            created_at=datetime(2024, 1, 1, 12, 1)
        )

        json_str = summary.to_json()

        # Verify it's valid JSON
        parsed = json.loads(json_str)

        assert parsed["id"] == "summary_123"
        assert parsed["channel_id"] == "987654321"
        assert parsed["message_count"] == 5
        assert parsed["summary_text"] == "Test summary"

    def test_summary_result_get_summary_stats(self):
        """Test get_summary_stats method."""
        start_time = datetime(2024, 1, 1, 10, 0)
        end_time = datetime(2024, 1, 1, 12, 30)

        summary = SummaryResult(
            id="summary_123",
            channel_id="987654321",
            guild_id="123456789",
            start_time=start_time,
            end_time=end_time,
            message_count=10,
            key_points=["Point 1", "Point 2"],
            action_items=[],
            technical_terms=[],
            participants=[],
            summary_text="Test summary text",
            metadata={},
            created_at=datetime.now()
        )

        stats = summary.get_summary_stats()
        assert stats["message_count"] == 10
        assert stats["key_points_count"] == 2
        assert stats["action_items_count"] == 0
        assert abs(stats["time_span_hours"] - 2.5) < 0.01
        assert stats["grounded"] is False

    def test_summary_result_has_references(self):
        """Test has_references method."""
        summary = SummaryResult(
            id="summary_123",
            channel_id="987654321",
            guild_id="123456789",
            start_time=datetime.now(),
            end_time=datetime.now(),
            message_count=5,
            key_points=[],
            action_items=[],
            technical_terms=[],
            participants=[],
            summary_text="Test",
            metadata={},
            created_at=datetime.now()
        )

        assert summary.has_references() is False

    def test_summary_result_add_warning(self):
        """Test add_warning method."""
        summary = SummaryResult(
            id="summary_123",
            channel_id="987654321",
            guild_id="123456789",
            start_time=datetime.now(),
            end_time=datetime.now(),
            message_count=5,
            key_points=[],
            action_items=[],
            technical_terms=[],
            participants=[],
            summary_text="Test",
            metadata={},
            created_at=datetime.now()
        )

        summary.add_warning("model_fallback", "Fell back to default model", {"original": "claude-3-opus"})

        assert len(summary.warnings) == 1
        assert summary.warnings[0].code == "model_fallback"
        assert summary.warnings[0].message == "Fell back to default model"
        assert summary.warnings[0].details["original"] == "claude-3-opus"

    def test_summary_result_word_count(self):
        """Test word count via get_summary_stats."""
        summary = SummaryResult(
            id="summary_123",
            channel_id="987654321",
            guild_id="123456789",
            start_time=datetime.now(),
            end_time=datetime.now(),
            message_count=5,
            key_points=[],
            action_items=[],
            technical_terms=[],
            participants=[],
            summary_text="This is a test summary with exactly ten words total.",
            metadata={},
            created_at=datetime.now()
        )

        stats = summary.get_summary_stats()
        assert stats["words_in_summary"] == 10
