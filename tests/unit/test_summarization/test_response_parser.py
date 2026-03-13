"""
Unit tests for ResponseParser.

Tests cover:
- Parsing valid JSON responses
- Handling malformed responses
- Extraction of key points, action items, technical terms
- Various output formats (JSON, markdown, freeform)
- Error recovery and fallback parsing
- Message analysis enhancement
"""

import pytest
import json
from datetime import datetime, timedelta
from typing import List

from src.summarization.response_parser import (
    ResponseParser, ParsedSummary
)
from src.models.summary import (
    SummaryResult, ActionItem, TechnicalTerm,
    Participant, Priority, SummarizationContext
)
from src.models.message import ProcessedMessage
from src.exceptions import SummarizationError


@pytest.fixture
def response_parser():
    """Create ResponseParser instance."""
    return ResponseParser()


@pytest.fixture
def sample_messages() -> List[ProcessedMessage]:
    """Create sample messages."""
    messages = []
    for i in range(3):
        msg = ProcessedMessage(
            id=f"msg_{i}",
            content=f"Important message {i} about the project.",
            author_id=f"user_{i}",
            author_name=f"TestUser{i}",
            timestamp=datetime.utcnow() - timedelta(minutes=10-i),
            channel_id="channel_1"
        )
        messages.append(msg)
    return messages


@pytest.fixture
def valid_json_response():
    """Valid JSON response from Claude."""
    return json.dumps({
        "summary_text": "The team discussed the new feature implementation and assigned tasks.",
        "key_points": [
            "Feature X needs to be implemented by next week",
            "Database schema requires updates",
            "Testing phase starts on Monday"
        ],
        "action_items": [
            {
                "description": "Update database schema",
                "assignee": "TestUser1",
                "priority": "high"
            },
            {
                "description": "Write unit tests",
                "assignee": "TestUser2",
                "priority": "medium"
            }
        ],
        "technical_terms": [
            {
                "term": "API Gateway",
                "definition": "Service that handles API routing",
                "context": "Used for microservices communication"
            }
        ],
        "participants": [
            {
                "name": "TestUser0",
                "message_count": 5,
                "key_contribution": "Proposed the architecture design"
            },
            {
                "name": "TestUser1",
                "message_count": 3,
                "key_contribution": "Reviewed database requirements"
            }
        ]
    })


@pytest.fixture
def json_response_in_code_block():
    """JSON response wrapped in code block."""
    return '''```json
{
    "summary_text": "Discussion about API design",
    "key_points": ["RESTful API", "Authentication needed"],
    "action_items": [],
    "technical_terms": [],
    "participants": []
}
```'''


@pytest.fixture
def markdown_response():
    """Markdown formatted response."""
    return """## Summary
The team discussed the new API design and database architecture.

## Key Points
- RESTful API design chosen
- PostgreSQL for database
- JWT for authentication

## Action Items
- Implement API endpoints - TestUser1
- Design database schema - TestUser2

## Technical Terms
- JWT: JSON Web Tokens for authentication
- REST: Representational State Transfer architecture

## Participants
- TestUser0 (5 messages): Led the discussion
- TestUser1 (3 messages): Database expert"""


@pytest.fixture
def freeform_response():
    """Freeform text response."""
    return """The team had a productive discussion about the new feature.
The main topics covered were API design, database architecture, and authentication.
Everyone agreed to use RESTful API with JWT authentication.
TestUser1 will implement the endpoints while TestUser2 designs the schema."""


class TestResponseParser:
    """Test suite for ResponseParser."""

    def test_parse_valid_json_response(
        self, response_parser, valid_json_response, sample_messages
    ):
        """Test parsing valid JSON response."""
        parsed = response_parser.parse_summary_response(
            response_content=valid_json_response,
            original_messages=sample_messages
        )

        assert isinstance(parsed, ParsedSummary)
        assert "feature implementation" in parsed.summary_text.lower()
        assert len(parsed.key_points) == 3
        assert len(parsed.action_items) == 2
        assert len(parsed.technical_terms) == 1
        assert parsed.parsing_metadata["parsing_method"] == "json"

    def test_parse_json_in_code_block(
        self, response_parser, json_response_in_code_block, sample_messages
    ):
        """Test parsing JSON wrapped in code block."""
        parsed = response_parser.parse_summary_response(
            response_content=json_response_in_code_block,
            original_messages=sample_messages
        )

        assert isinstance(parsed, ParsedSummary)
        assert "API design" in parsed.summary_text
        assert len(parsed.key_points) == 2
        assert parsed.parsing_metadata["parsing_method"] == "json"

    def test_parse_markdown_response(
        self, response_parser, markdown_response, sample_messages
    ):
        """Test parsing markdown formatted response."""
        parsed = response_parser.parse_summary_response(
            response_content=markdown_response,
            original_messages=sample_messages
        )

        assert isinstance(parsed, ParsedSummary)
        assert len(parsed.summary_text) > 0
        assert len(parsed.key_points) > 0
        assert len(parsed.action_items) > 0
        assert parsed.parsing_metadata["parsing_method"] == "markdown"

    def test_parse_freeform_response(
        self, response_parser, freeform_response, sample_messages
    ):
        """Test parsing freeform text response."""
        parsed = response_parser.parse_summary_response(
            response_content=freeform_response,
            original_messages=sample_messages
        )

        assert isinstance(parsed, ParsedSummary)
        assert len(parsed.summary_text) > 0
        assert parsed.parsing_metadata["parsing_method"] == "freeform"

    def test_parse_malformed_json_fallback(
        self, response_parser, sample_messages
    ):
        """Test fallback to other parsers on malformed JSON."""
        malformed = '{"summary_text": "Test", invalid json here'

        # Should not raise error, falls back to other parsers
        parsed = response_parser.parse_summary_response(
            response_content=malformed,
            original_messages=sample_messages
        )

        assert isinstance(parsed, ParsedSummary)
        assert len(parsed.summary_text) > 0

    def test_parse_empty_response_fallback(
        self, response_parser, sample_messages
    ):
        """Test empty response falls back to freeform parser with fallback text."""
        parsed = response_parser.parse_summary_response(
            response_content="",
            original_messages=sample_messages
        )

        # Freeform parser handles empty content with a fallback message
        assert isinstance(parsed, ParsedSummary)
        assert len(parsed.summary_text) > 0

    def test_action_item_parsing(
        self, response_parser, valid_json_response, sample_messages
    ):
        """Test action item extraction and parsing."""
        parsed = response_parser.parse_summary_response(
            response_content=valid_json_response,
            original_messages=sample_messages
        )

        assert len(parsed.action_items) == 2

        item1 = parsed.action_items[0]
        assert isinstance(item1, ActionItem)
        assert item1.description == "Update database schema"
        assert item1.assignee == "TestUser1"
        assert item1.priority == Priority.HIGH

        item2 = parsed.action_items[1]
        assert item2.priority == Priority.MEDIUM

    def test_action_item_string_format(self, response_parser, sample_messages):
        """Test parsing action items in string format."""
        response = json.dumps({
            "summary_text": "Test",
            "key_points": [],
            "action_items": ["Task 1", "Task 2"],
            "technical_terms": [],
            "participants": []
        })

        parsed = response_parser.parse_summary_response(
            response_content=response,
            original_messages=sample_messages
        )

        assert len(parsed.action_items) == 2
        assert parsed.action_items[0].description == "Task 1"
        assert parsed.action_items[0].priority == Priority.MEDIUM  # Default

    def test_technical_term_parsing(
        self, response_parser, valid_json_response, sample_messages
    ):
        """Test technical term extraction."""
        parsed = response_parser.parse_summary_response(
            response_content=valid_json_response,
            original_messages=sample_messages
        )

        assert len(parsed.technical_terms) == 1

        term = parsed.technical_terms[0]
        assert isinstance(term, TechnicalTerm)
        assert term.term == "API Gateway"
        assert "routing" in term.definition
        assert "microservices" in term.context

    def test_participant_parsing(
        self, response_parser, valid_json_response, sample_messages
    ):
        """Test participant extraction."""
        parsed = response_parser.parse_summary_response(
            response_content=valid_json_response,
            original_messages=sample_messages
        )

        # Should have participants from both response and message analysis
        assert len(parsed.participants) > 0

        # Check enhanced with message counts
        for participant in parsed.participants:
            assert isinstance(participant, Participant)
            assert len(participant.display_name) > 0

    def test_enhance_with_message_analysis(
        self, response_parser, valid_json_response, sample_messages
    ):
        """Test enhancement with actual message analysis."""
        parsed = response_parser.parse_summary_response(
            response_content=valid_json_response,
            original_messages=sample_messages
        )

        # Participants should be enhanced with actual message counts
        participant_names = [p.display_name for p in parsed.participants]

        # Should include users from messages
        assert any("TestUser" in name for name in participant_names)

        # Message counts should be populated
        for participant in parsed.participants:
            if "TestUser" in participant.display_name:
                assert participant.message_count > 0

    def test_validation_and_cleanup(
        self, response_parser, sample_messages
    ):
        """Test validation limits content appropriately."""
        # Create response with very long content
        long_response = json.dumps({
            "summary_text": "A" * 3000,  # Exceeds 2000 char limit
            "key_points": ["Point"] * 15,  # Exceeds 10 point limit
            "action_items": [],
            "technical_terms": [],
            "participants": []
        })

        parsed = response_parser.parse_summary_response(
            response_content=long_response,
            original_messages=sample_messages
        )

        # Should be truncated
        assert len(parsed.summary_text) <= 2000
        assert len(parsed.key_points) <= 10

    def test_extract_summary_result(self, response_parser, sample_messages):
        """Test conversion to SummaryResult."""
        parsed = ParsedSummary(
            summary_text="Test summary",
            key_points=["Point 1", "Point 2"],
            action_items=[],
            technical_terms=[],
            participants=[],
            raw_response="{}",
            parsing_metadata={}
        )

        result = response_parser.extract_summary_result(
            parsed=parsed,
            channel_id="channel_1",
            guild_id="guild_1",
            start_time=datetime.utcnow() - timedelta(hours=1),
            end_time=datetime.utcnow(),
            message_count=10
        )

        assert isinstance(result, SummaryResult)
        assert result.channel_id == "channel_1"
        assert result.guild_id == "guild_1"
        assert result.message_count == 10
        assert result.summary_text == "Test summary"
        assert len(result.key_points) == 2

    def test_extract_summary_result_with_context(
        self, response_parser, sample_messages
    ):
        """Test summary result with context."""
        context = SummarizationContext(
            channel_name="test-channel",
            guild_name="Test Guild",
            time_span_hours=1.0,
            total_participants=3
        )

        parsed = ParsedSummary(
            summary_text="Test",
            key_points=[],
            action_items=[],
            technical_terms=[],
            participants=[],
            raw_response="{}",
            parsing_metadata={}
        )

        result = response_parser.extract_summary_result(
            parsed=parsed,
            channel_id="channel_1",
            guild_id="guild_1",
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            message_count=5,
            context=context
        )

        assert result.context == context

    def test_markdown_section_extraction(self, response_parser):
        """Test markdown section extraction."""
        content = """## Introduction
This is the intro.

## Main Content
This is the main content.

## Conclusion
This is the conclusion."""

        section = response_parser._extract_markdown_section(
            content, r"## Main Content"
        )

        assert "main content" in section.lower()
        assert "intro" not in section.lower()

    def test_markdown_list_extraction(self, response_parser):
        """Test extracting items from markdown list."""
        content = """## Key Points
- First point
- Second point
- Third point"""

        items = response_parser._extract_markdown_list(content, r"## Key Points")

        assert len(items) == 3
        assert "First point" in items
        assert "Second point" in items

    def test_markdown_numbered_list_extraction(self, response_parser):
        """Test extracting numbered list items."""
        content = """## Tasks
1. First task
2. Second task
3. Third task"""

        items = response_parser._extract_markdown_list(content, r"## Tasks")

        assert len(items) == 3
        assert "First task" in items

    def test_ensure_list_helper(self, response_parser):
        """Test _ensure_list helper function."""
        # String input
        assert response_parser._ensure_list("test") == ["test"]

        # List input
        assert response_parser._ensure_list(["a", "b"]) == ["a", "b"]

        # None input
        assert response_parser._ensure_list(None) == []

        # Empty string
        assert response_parser._ensure_list("") == []

    def test_parse_with_missing_fields(self, response_parser, sample_messages):
        """Test parsing JSON with missing optional fields."""
        minimal_response = json.dumps({
            "summary_text": "Minimal summary",
            "key_points": ["Point 1"]
            # Missing action_items, technical_terms, participants
        })

        parsed = response_parser.parse_summary_response(
            response_content=minimal_response,
            original_messages=sample_messages
        )

        assert parsed.summary_text == "Minimal summary"
        assert len(parsed.key_points) == 1
        assert len(parsed.action_items) == 0
        assert len(parsed.technical_terms) == 0

    def test_parse_invalid_priority_defaults(
        self, response_parser, sample_messages
    ):
        """Test invalid priority values default to MEDIUM."""
        response = json.dumps({
            "summary_text": "Test",
            "key_points": [],
            "action_items": [{
                "description": "Task",
                "priority": "invalid_priority"
            }],
            "technical_terms": [],
            "participants": []
        })

        parsed = response_parser.parse_summary_response(
            response_content=response,
            original_messages=sample_messages
        )

        assert parsed.action_items[0].priority == Priority.MEDIUM

    def test_parser_fallback_order(self, response_parser, sample_messages):
        """Test parsers are tried in correct fallback order."""
        # Invalid content that should fall through parsers
        content = "Not JSON, not markdown, just text."

        parsed = response_parser.parse_summary_response(
            response_content=content,
            original_messages=sample_messages
        )

        # Should succeed with freeform parser
        assert parsed.parsing_metadata["parsing_method"] == "freeform"
        assert len(parsed.summary_text) > 0

    def test_empty_summary_text_fallback(self, response_parser, sample_messages):
        """Test fallback when summary_text is empty."""
        response = json.dumps({
            "summary_text": "",
            "key_points": ["Point 1"],
            "action_items": [],
            "technical_terms": [],
            "participants": []
        })

        parsed = response_parser.parse_summary_response(
            response_content=response,
            original_messages=sample_messages
        )

        # Should have fallback text
        assert len(parsed.summary_text) > 0
        assert "could not be extracted" in parsed.summary_text.lower()

    def test_parsing_metadata_completeness(
        self, response_parser, valid_json_response, sample_messages
    ):
        """Test parsing metadata is complete."""
        parsed = response_parser.parse_summary_response(
            response_content=valid_json_response,
            original_messages=sample_messages
        )

        assert "parsing_method" in parsed.parsing_metadata
        assert "response_length" in parsed.parsing_metadata
        assert "extraction_stats" in parsed.parsing_metadata or "final_stats" in parsed.parsing_metadata

    def test_participant_message_count_accuracy(
        self, response_parser, sample_messages
    ):
        """Test participant message counts are accurate."""
        # Create messages with specific authors
        messages = []
        for i in range(10):
            msg = ProcessedMessage(
                id=f"msg_{i}",
                content=f"Message {i}",
                author_id="user_1" if i < 7 else "user_2",
                author_name="User1" if i < 7 else "User2",
                timestamp=datetime.utcnow(),
                channel_id="channel_1"
            )
            messages.append(msg)

        response = json.dumps({
            "summary_text": "Test",
            "key_points": [],
            "action_items": [],
            "technical_terms": [],
            "participants": []
        })

        parsed = response_parser.parse_summary_response(
            response_content=response,
            original_messages=messages
        )

        # Find User1 participant
        user1 = next((p for p in parsed.participants if p.display_name == "User1"), None)
        assert user1 is not None
        assert user1.message_count == 7

        # Find User2 participant
        user2 = next((p for p in parsed.participants if p.display_name == "User2"), None)
        assert user2 is not None
        assert user2.message_count == 3

    def test_short_key_points_filtered(self, response_parser, sample_messages):
        """Test very short key points are filtered out."""
        response = json.dumps({
            "summary_text": "Test",
            "key_points": ["Good point", "a", "Another good point", "x"],
            "action_items": [],
            "technical_terms": [],
            "participants": []
        })

        parsed = response_parser.parse_summary_response(
            response_content=response,
            original_messages=sample_messages
        )

        # Short points should be filtered (< 5 chars)
        assert len(parsed.key_points) == 2
        assert "Good point" in parsed.key_points
        assert "Another good point" in parsed.key_points
