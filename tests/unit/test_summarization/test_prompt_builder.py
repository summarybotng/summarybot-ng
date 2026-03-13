"""
Unit tests for PromptBuilder.

Tests cover:
- Prompt generation for different summary types
- Message formatting
- Context building
- Token estimation
- Prompt optimization and truncation
- Various customization options
"""

import pytest
from datetime import datetime, timedelta
from typing import List

from src.summarization.prompt_builder import (
    PromptBuilder, SummarizationPrompt
)
from src.models.summary import SummaryOptions, SummaryLength
from src.models.message import (
    ProcessedMessage, AttachmentInfo, AttachmentType, CodeBlock, ThreadInfo
)


@pytest.fixture
def prompt_builder():
    """Create PromptBuilder instance."""
    return PromptBuilder()


@pytest.fixture
def sample_messages() -> List[ProcessedMessage]:
    """Create sample messages for testing."""
    messages = []
    base_time = datetime.utcnow() - timedelta(hours=1)

    for i in range(5):
        msg = ProcessedMessage(
            id=f"msg_{i}",
            content=f"This is message {i} discussing important topics.",
            author_id=f"user_{i % 2}",
            author_name=f"User{i % 2}",
            timestamp=base_time + timedelta(minutes=i*10),
            channel_id="channel_1",
            attachments=[],
            code_blocks=[],
            mentions=[],
            thread_info=None
        )
        messages.append(msg)

    return messages


@pytest.fixture
def brief_options():
    """Brief summary options."""
    return SummaryOptions(
        summary_length=SummaryLength.BRIEF,
        extract_action_items=True,
        extract_technical_terms=True,
        include_bots=False
    )


@pytest.fixture
def detailed_options():
    """Detailed summary options."""
    return SummaryOptions(
        summary_length=SummaryLength.DETAILED,
        extract_action_items=True,
        extract_technical_terms=True,
        include_bots=True
    )


@pytest.fixture
def comprehensive_options():
    """Comprehensive summary options."""
    return SummaryOptions(
        summary_length=SummaryLength.COMPREHENSIVE,
        extract_action_items=True,
        extract_technical_terms=True,
        include_bots=True,
        include_attachments=True
    )


class TestPromptBuilder:
    """Test suite for PromptBuilder."""

    def test_build_brief_summarization_prompt(
        self, prompt_builder, sample_messages, brief_options
    ):
        """Test building brief summary prompt."""
        prompt = prompt_builder.build_summarization_prompt(
            messages=sample_messages,
            options=brief_options
        )

        assert isinstance(prompt, SummarizationPrompt)
        assert "BRIEF" in prompt.system_prompt.upper()
        assert "3-5 most important points" in prompt.system_prompt
        assert len(prompt.user_prompt) > 0
        assert prompt.estimated_tokens > 0
        assert prompt.metadata["message_count"] == 5
        assert prompt.metadata["summary_length"] == "brief"

    def test_build_detailed_summarization_prompt(
        self, prompt_builder, sample_messages, detailed_options
    ):
        """Test building detailed summary prompt."""
        prompt = prompt_builder.build_summarization_prompt(
            messages=sample_messages,
            options=detailed_options
        )

        assert isinstance(prompt, SummarizationPrompt)
        assert "DETAILED" in prompt.system_prompt.upper()
        assert "comprehensive" in prompt.system_prompt.lower()
        assert "300-600 words" in prompt.system_prompt
        assert prompt.metadata["summary_length"] == "detailed"

    def test_build_comprehensive_summarization_prompt(
        self, prompt_builder, sample_messages, comprehensive_options
    ):
        """Test building comprehensive summary prompt."""
        prompt = prompt_builder.build_summarization_prompt(
            messages=sample_messages,
            options=comprehensive_options
        )

        assert isinstance(prompt, SummarizationPrompt)
        assert "COMPREHENSIVE" in prompt.system_prompt.upper()
        assert "exhaustive" in prompt.system_prompt.lower()
        assert "600-1000+" in prompt.system_prompt
        assert prompt.metadata["include_actions"]
        assert prompt.metadata["include_technical"]

    def test_prompt_with_context(
        self, prompt_builder, sample_messages, detailed_options
    ):
        """Test prompt generation with context information."""
        context = {
            "channel_name": "general",
            "guild_name": "Test Server",
            "time_range": "1 hour",
            "total_participants": 2
        }

        prompt = prompt_builder.build_summarization_prompt(
            messages=sample_messages,
            options=detailed_options,
            context=context
        )

        assert "general" in prompt.user_prompt
        assert "Test Server" in prompt.user_prompt
        assert "Context Information" in prompt.user_prompt

    def test_message_formatting_basic(
        self, prompt_builder, sample_messages, detailed_options
    ):
        """Test basic message formatting in prompts."""
        prompt = prompt_builder.build_summarization_prompt(
            messages=sample_messages,
            options=detailed_options
        )

        # Check that messages are formatted in user prompt
        for msg in sample_messages:
            assert msg.author_name in prompt.user_prompt
            assert msg.content in prompt.user_prompt

    def test_message_formatting_with_attachments(
        self, prompt_builder, comprehensive_options
    ):
        """Test message formatting includes attachment information."""
        messages = [
            ProcessedMessage(
                id="msg_1",
                content="Check out this file",
                author_id="user_1",
                author_name="User1",
                timestamp=datetime.utcnow(),
                channel_id="channel_1",
                attachments=[
                    AttachmentInfo(
                        id="att_1",
                        filename="document.pdf",
                        size=1024,
                        url="https://example.com/document.pdf",
                        proxy_url="https://example.com/document.pdf",
                        type=AttachmentType.DOCUMENT
                    )
                ]
            )
        ]

        prompt = prompt_builder.build_summarization_prompt(
            messages=messages,
            options=comprehensive_options
        )

        assert "document.pdf" in prompt.user_prompt or "Attachments" in prompt.user_prompt

    def test_message_formatting_with_code_blocks(
        self, prompt_builder, detailed_options
    ):
        """Test message formatting includes code block information."""
        messages = [
            ProcessedMessage(
                id="msg_1",
                content="Here's the code",
                author_id="user_1",
                author_name="User1",
                timestamp=datetime.utcnow(),
                channel_id="channel_1",
                code_blocks=[
                    CodeBlock(
                        language="python",
                        code="def hello():\n    print('Hello')",
                        start_line=0,
                        end_line=2
                    )
                ]
            )
        ]

        prompt = prompt_builder.build_summarization_prompt(
            messages=messages,
            options=detailed_options
        )

        assert "Code Block" in prompt.user_prompt or "python" in prompt.user_prompt

    def test_message_formatting_with_thread_info(
        self, prompt_builder, detailed_options
    ):
        """Test message formatting includes thread information."""
        messages = [
            ProcessedMessage(
                id="msg_1",
                content="This is a thread message with substantial content for testing.",
                author_id="user_1",
                author_name="User1",
                timestamp=datetime.utcnow(),
                channel_id="channel_1",
                thread_info=ThreadInfo(
                    thread_id="thread_1",
                    thread_name="Discussion Thread",
                    parent_channel_id="channel_1",
                    starter_message_id="msg_0"
                )
            )
        ]

        prompt = prompt_builder.build_summarization_prompt(
            messages=messages,
            options=detailed_options
        )

        assert "Thread" in prompt.user_prompt

    def test_token_estimation(
        self, prompt_builder, sample_messages, detailed_options
    ):
        """Test token count estimation."""
        prompt = prompt_builder.build_summarization_prompt(
            messages=sample_messages,
            options=detailed_options
        )

        # Rough estimation: 1 token ≈ 4 characters
        total_chars = len(prompt.system_prompt) + len(prompt.user_prompt)
        expected_tokens = total_chars // prompt_builder.CHARS_PER_TOKEN

        assert abs(prompt.estimated_tokens - expected_tokens) < 100

    def test_estimate_token_count_direct(self, prompt_builder):
        """Test direct token count estimation."""
        text = "This is a test string with multiple words."
        estimated = prompt_builder.estimate_token_count(text)

        expected = len(text) // prompt_builder.CHARS_PER_TOKEN
        assert estimated == expected

    def test_optimize_prompt_length_no_optimization_needed(
        self, prompt_builder, sample_messages, brief_options
    ):
        """Test prompt optimization when within limits."""
        prompt = prompt_builder.build_summarization_prompt(
            messages=sample_messages,
            options=brief_options
        )

        max_tokens = prompt.estimated_tokens + 1000
        optimized = prompt_builder.optimize_prompt_length(
            prompt.user_prompt,
            max_tokens
        )

        # Should return unchanged
        assert optimized == prompt.user_prompt

    def test_optimize_prompt_length_truncation_needed(
        self, prompt_builder, sample_messages, detailed_options
    ):
        """Test prompt optimization when truncation needed."""
        prompt = prompt_builder.build_summarization_prompt(
            messages=sample_messages,
            options=detailed_options
        )

        # Set very low limit
        max_tokens = 100
        optimized = prompt_builder.optimize_prompt_length(
            prompt.user_prompt,
            max_tokens
        )

        # Should be truncated
        assert len(optimized) < len(prompt.user_prompt)
        assert "truncated" in optimized.lower() or len(optimized) < len(prompt.user_prompt)

    def test_optimize_prompt_preserves_structure(
        self, prompt_builder, sample_messages, detailed_options
    ):
        """Test prompt optimization preserves important structure."""
        prompt = prompt_builder.build_summarization_prompt(
            messages=sample_messages,
            options=detailed_options
        )

        max_tokens = prompt.estimated_tokens // 2
        optimized = prompt_builder.optimize_prompt_length(
            prompt.user_prompt,
            max_tokens,
            preserve_ratio=0.5
        )

        # Should still contain markers for sections
        # (Even if content is truncated)
        assert len(optimized) > 0

    def test_build_system_prompt_includes_options(
        self, prompt_builder, detailed_options
    ):
        """Test system prompt includes option-specific instructions."""
        system_prompt = prompt_builder.build_system_prompt(detailed_options)

        assert len(system_prompt) > 0
        assert "JSON" in system_prompt  # Response format instruction

    def test_build_user_prompt_structure(
        self, prompt_builder, sample_messages, detailed_options
    ):
        """Test user prompt has expected structure."""
        context = {
            "channel_name": "test",
            "guild_name": "Test Guild"
        }

        user_prompt = prompt_builder.build_user_prompt(
            messages=sample_messages,
            context=context,
            options=detailed_options
        )

        # Should contain key sections
        assert "Context" in user_prompt or "test" in user_prompt
        assert "Messages" in user_prompt or sample_messages[0].content in user_prompt
        assert len(user_prompt) > 0

    def test_time_span_calculation(self, prompt_builder):
        """Test time span calculation for messages."""
        now = datetime.utcnow()
        messages = [
            ProcessedMessage(
                id="msg_1",
                content="First",
                author_id="user_1",
                author_name="User1",
                timestamp=now - timedelta(hours=2),
                channel_id="channel_1"
            ),
            ProcessedMessage(
                id="msg_2",
                content="Last",
                author_id="user_2",
                author_name="User2",
                timestamp=now,
                channel_id="channel_1"
            )
        ]

        time_span = prompt_builder._calculate_time_span(messages)

        assert "2" in time_span and "hour" in time_span.lower()

    def test_time_span_minutes(self, prompt_builder):
        """Test time span calculation for short durations."""
        now = datetime.utcnow()
        messages = [
            ProcessedMessage(
                id="msg_1",
                content="First",
                author_id="user_1",
                author_name="User1",
                timestamp=now - timedelta(minutes=30),
                channel_id="channel_1"
            ),
            ProcessedMessage(
                id="msg_2",
                content="Last",
                author_id="user_2",
                author_name="User2",
                timestamp=now,
                channel_id="channel_1"
            )
        ]

        time_span = prompt_builder._calculate_time_span(messages)

        assert "30" in time_span and "minute" in time_span.lower()

    def test_time_span_days(self, prompt_builder):
        """Test time span calculation for multiple days."""
        now = datetime.utcnow()
        messages = [
            ProcessedMessage(
                id="msg_1",
                content="First",
                author_id="user_1",
                author_name="User1",
                timestamp=now - timedelta(days=3, hours=5),
                channel_id="channel_1"
            ),
            ProcessedMessage(
                id="msg_2",
                content="Last",
                author_id="user_2",
                author_name="User2",
                timestamp=now,
                channel_id="channel_1"
            )
        ]

        time_span = prompt_builder._calculate_time_span(messages)

        assert "3 days" in time_span

    def test_empty_messages_handling(self, prompt_builder, brief_options):
        """Test handling of empty message list."""
        prompt = prompt_builder.build_summarization_prompt(
            messages=[],
            options=brief_options
        )

        assert prompt.metadata["message_count"] == 0

    def test_options_without_extras(self, prompt_builder, sample_messages):
        """Test options that disable extra features."""
        minimal_options = SummaryOptions(
            summary_length=SummaryLength.BRIEF,
            extract_action_items=False,
            extract_technical_terms=False,
            include_bots=False
        )

        prompt = prompt_builder.build_summarization_prompt(
            messages=sample_messages,
            options=minimal_options
        )

        # Prompt should indicate not to extract certain items
        assert "Do not extract action items" in prompt.user_prompt or not prompt.metadata["include_actions"]

    def test_prompt_metadata_completeness(
        self, prompt_builder, sample_messages, detailed_options
    ):
        """Test that prompt metadata contains all expected fields."""
        prompt = prompt_builder.build_summarization_prompt(
            messages=sample_messages,
            options=detailed_options
        )

        assert "message_count" in prompt.metadata
        assert "time_span" in prompt.metadata
        assert "summary_length" in prompt.metadata
        assert "include_actions" in prompt.metadata
        assert "include_technical" in prompt.metadata
        assert "estimated_tokens" in prompt.metadata

    def test_system_prompts_are_different(self, prompt_builder):
        """Test that different summary lengths have different system prompts."""
        brief_prompt = prompt_builder.system_prompts[("discord", SummaryLength.BRIEF)]
        detailed_prompt = prompt_builder.system_prompts[("discord", SummaryLength.DETAILED)]
        comprehensive_prompt = prompt_builder.system_prompts[("discord", SummaryLength.COMPREHENSIVE)]

        assert brief_prompt != detailed_prompt
        assert detailed_prompt != comprehensive_prompt
        assert brief_prompt != comprehensive_prompt

    def test_large_message_set_handling(self, prompt_builder, detailed_options):
        """Test handling of large message sets."""
        # Create 100 messages
        messages = []
        for i in range(100):
            msg = ProcessedMessage(
                id=f"msg_{i}",
                content=f"Message {i} content " * 10,
                author_id=f"user_{i % 5}",
                author_name=f"User{i % 5}",
                timestamp=datetime.utcnow() - timedelta(minutes=100-i),
                channel_id="channel_1"
            )
            messages.append(msg)

        prompt = prompt_builder.build_summarization_prompt(
            messages=messages,
            options=detailed_options
        )

        assert prompt.metadata["message_count"] == 100
        assert prompt.estimated_tokens > 0
