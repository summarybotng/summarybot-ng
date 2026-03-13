"""
Unit tests for summarization optimization.

Tests cover:
- Batch processing
- Performance optimizations
- Message filtering
- Deduplication
- Message prioritization
- Request optimization
"""

import pytest
from datetime import datetime, timedelta
from typing import List

from src.summarization.optimization import SummaryOptimizer
from src.models.message import ProcessedMessage, AttachmentInfo, AttachmentType
from src.models.summary import SummaryOptions, SummaryLength


@pytest.fixture
def optimizer():
    """Create SummaryOptimizer instance."""
    return SummaryOptimizer()


@pytest.fixture
def sample_messages() -> List[ProcessedMessage]:
    """Create sample messages."""
    messages = []
    base_time = datetime.utcnow() - timedelta(hours=1)

    for i in range(20):
        msg = ProcessedMessage(
            id=f"msg_{i}",
            content=f"This is message {i} with substantial content for testing.",
            author_id=f"user_{i % 5}",
            author_name=f"User{i % 5}",
            timestamp=base_time + timedelta(minutes=i*2),
            channel_id="channel_1",
            attachments=[],
            code_blocks=[],
            mentions=[],
            thread_info=None
        )
        messages.append(msg)

    return messages


@pytest.fixture
def summary_options():
    """Create summary options."""
    return SummaryOptions(
        summary_length=SummaryLength.DETAILED,
        include_bots=False,
        excluded_users=[]
    )


class TestSummaryOptimizer:
    """Test suite for SummaryOptimizer."""

    def test_optimize_message_list_no_changes(
        self, optimizer, sample_messages, summary_options
    ):
        """Test optimization when no changes needed."""
        optimized, stats = optimizer.optimize_message_list(
            messages=sample_messages,
            options=summary_options
        )

        assert len(optimized) == len(sample_messages)
        assert stats["original_count"] == 20
        assert stats["final_count"] == 20
        assert stats["reduction_ratio"] == 0.0

    def test_optimize_filters_empty_messages(
        self, optimizer, summary_options
    ):
        """Test filtering of messages without content."""
        messages = [
            ProcessedMessage(
                id="msg_1",
                content="Good content here",
                author_id="user_1",
                author_name="User1",
                timestamp=datetime.utcnow(),
                channel_id="channel_1"
            ),
            ProcessedMessage(
                id="msg_2",
                content="",  # Empty
                author_id="user_2",
                author_name="User2",
                timestamp=datetime.utcnow(),
                channel_id="channel_1"
            ),
            ProcessedMessage(
                id="msg_3",
                content="More good content",
                author_id="user_3",
                author_name="User3",
                timestamp=datetime.utcnow(),
                channel_id="channel_1"
            )
        ]

        optimized, stats = optimizer.optimize_message_list(
            messages=messages,
            options=summary_options
        )

        assert len(optimized) < len(messages)
        assert stats["filtered_count"] < stats["original_count"]

    def test_optimize_filters_bot_messages(self, optimizer):
        """Test filtering of bot messages when excluded."""
        options = SummaryOptions(
            summary_length=SummaryLength.BRIEF,
            include_bots=False
        )

        messages = [
            ProcessedMessage(
                id="msg_1",
                content="This is a human message with substantial content for testing",
                author_id="user_1",
                author_name="User1",
                timestamp=datetime.utcnow(),
                channel_id="channel_1"
            ),
            ProcessedMessage(
                id="msg_2",
                content="This is a bot message with substantial content for testing",
                author_id="bot_1",
                author_name="BotUser [BOT]",
                timestamp=datetime.utcnow(),
                channel_id="channel_1"
            )
        ]

        optimized, stats = optimizer.optimize_message_list(
            messages=messages,
            options=options
        )

        # Bot should be filtered out
        assert len(optimized) == 1
        assert optimized[0].author_name == "User1"

    def test_optimize_filters_excluded_users(self, optimizer):
        """Test filtering of excluded users."""
        options = SummaryOptions(
            summary_length=SummaryLength.BRIEF,
            excluded_users=["user_2"]
        )

        messages = [
            ProcessedMessage(
                id="msg_1",
                content="Keep this message because it has substantial content for testing",
                author_id="user_1",
                author_name="User1",
                timestamp=datetime.utcnow(),
                channel_id="channel_1"
            ),
            ProcessedMessage(
                id="msg_2",
                content="Remove this message because this user is excluded from summary",
                author_id="user_2",
                author_name="User2",
                timestamp=datetime.utcnow(),
                channel_id="channel_1"
            )
        ]

        optimized, stats = optimizer.optimize_message_list(
            messages=messages,
            options=options
        )

        assert len(optimized) == 1
        assert optimized[0].author_id == "user_1"

    def test_optimize_removes_duplicates(
        self, optimizer, summary_options
    ):
        """Test deduplication of similar messages."""
        messages = [
            ProcessedMessage(
                id="msg_1",
                content="Hello world this is a substantial message for deduplication testing",
                author_id="user_1",
                author_name="User1",
                timestamp=datetime.utcnow(),
                channel_id="channel_1"
            ),
            ProcessedMessage(
                id="msg_2",
                content="Hello world this is a substantial message for deduplication testing",  # Duplicate
                author_id="user_1",
                author_name="User1",
                timestamp=datetime.utcnow(),
                channel_id="channel_1"
            ),
            ProcessedMessage(
                id="msg_3",
                content="This is a completely different message with unique content",
                author_id="user_1",
                author_name="User1",
                timestamp=datetime.utcnow(),
                channel_id="channel_1"
            )
        ]

        optimized, stats = optimizer.optimize_message_list(
            messages=messages,
            options=summary_options
        )

        assert len(optimized) == 2  # Duplicate removed
        assert stats["deduplication_removed"] == 1

    def test_optimize_smart_truncation(
        self, optimizer, sample_messages, summary_options
    ):
        """Test smart truncation keeps important messages."""
        # Limit to 10 messages
        optimized, stats = optimizer.optimize_message_list(
            messages=sample_messages,
            options=summary_options,
            max_messages=10
        )

        assert len(optimized) == 10
        assert stats["truncated_count"] > 0
        assert stats["final_count"] == 10

    def test_smart_truncation_prioritizes_content(
        self, optimizer, summary_options
    ):
        """Test smart truncation prioritizes messages with more content."""
        messages = [
            ProcessedMessage(
                id="msg_1",
                content="Short",
                author_id="user_1",
                author_name="User1",
                timestamp=datetime.utcnow(),
                channel_id="channel_1"
            ),
            ProcessedMessage(
                id="msg_2",
                content="This is a much longer message with substantial content " * 5,
                author_id="user_2",
                author_name="User2",
                timestamp=datetime.utcnow(),
                channel_id="channel_1"
            )
        ]

        optimized = optimizer._smart_truncate_messages(messages, max_count=1)

        # Should keep the longer message
        assert len(optimized) == 1
        assert optimized[0].id == "msg_2"

    def test_smart_truncation_maintains_chronological_order(
        self, optimizer, sample_messages, summary_options
    ):
        """Test truncation maintains chronological order."""
        optimized = optimizer._smart_truncate_messages(
            sample_messages, max_count=10
        )

        # Check timestamps are in order
        for i in range(len(optimized) - 1):
            assert optimized[i].timestamp <= optimized[i+1].timestamp

    def test_estimate_optimization_benefit(
        self, optimizer, sample_messages, summary_options
    ):
        """Test optimization benefit estimation."""
        estimates = optimizer.estimate_optimization_benefit(
            messages=sample_messages,
            options=summary_options
        )

        assert "current_message_count" in estimates
        assert "estimated_after_filtering" in estimates
        assert "estimated_duplicates" in estimates
        assert "potential_token_savings" in estimates
        assert "potential_cost_savings_usd" in estimates
        assert estimates["current_message_count"] == 20

    def test_estimate_with_empty_messages(
        self, optimizer, summary_options
    ):
        """Test benefit estimation with messages lacking content."""
        messages = [
            ProcessedMessage(
                id="msg_1",
                content="",  # Empty
                author_id="user_1",
                author_name="User1",
                timestamp=datetime.utcnow(),
                channel_id="channel_1"
            ),
            ProcessedMessage(
                id="msg_2",
                content="Good content",
                author_id="user_2",
                author_name="User2",
                timestamp=datetime.utcnow(),
                channel_id="channel_1"
            )
        ]

        estimates = optimizer.estimate_optimization_benefit(
            messages=messages,
            options=summary_options
        )

        assert estimates["estimated_after_filtering"] < estimates["current_message_count"]

    def test_optimize_batch_requests_deduplication(self, optimizer):
        """Test batch request deduplication."""
        # Create duplicate requests
        requests = [
            {
                "channel_id": "channel_1",
                "guild_id": "guild_1",
                "messages": [],
                "options": SummaryOptions()
            },
            {
                "channel_id": "channel_1",
                "guild_id": "guild_1",
                "messages": [],
                "options": SummaryOptions()
            },
            {
                "channel_id": "channel_2",
                "guild_id": "guild_1",
                "messages": [],
                "options": SummaryOptions()
            }
        ]

        optimized, stats = optimizer.optimize_batch_requests(requests)

        # Should deduplicate similar requests
        assert len(optimized) <= len(requests)
        assert stats["original_request_count"] == 3

    def test_get_content_hash_consistency(self, optimizer):
        """Test content hash is consistent."""
        msg1 = ProcessedMessage(
            id="msg_1",
            content="Test content",
            author_id="user_1",
            author_name="User1",
            timestamp=datetime.utcnow(),
            channel_id="channel_1"
        )

        msg2 = ProcessedMessage(
            id="msg_2",  # Different ID
            content="Test content",  # Same content
            author_id="user_1",
            author_name="User1",  # Same author
            timestamp=datetime.utcnow(),
            channel_id="channel_1"
        )

        hash1 = optimizer._get_content_hash(msg1)
        hash2 = optimizer._get_content_hash(msg2)

        assert hash1 == hash2

    def test_get_content_hash_different_content(self, optimizer):
        """Test different content produces different hashes."""
        msg1 = ProcessedMessage(
            id="msg_1",
            content="Content A",
            author_id="user_1",
            author_name="User1",
            timestamp=datetime.utcnow(),
            channel_id="channel_1"
        )

        msg2 = ProcessedMessage(
            id="msg_2",
            content="Content B",
            author_id="user_1",
            author_name="User1",
            timestamp=datetime.utcnow(),
            channel_id="channel_1"
        )

        hash1 = optimizer._get_content_hash(msg1)
        hash2 = optimizer._get_content_hash(msg2)

        assert hash1 != hash2

    def test_get_request_signature(self, optimizer):
        """Test request signature generation."""
        request = {
            "channel_id": "channel_1",
            "guild_id": "guild_1",
            "messages": [
                ProcessedMessage(
                    id="msg_1",
                    content="Test message with substantial content for request signature testing",
                    author_id="user_1",
                    author_name="User1",
                    timestamp=datetime.utcnow(),
                    channel_id="channel_1"
                )
            ],
            "options": SummaryOptions()
        }

        signature = optimizer._get_request_signature(request)

        assert isinstance(signature, str)
        assert len(signature) == 16  # MD5 hash truncated

    def test_optimization_stats_completeness(
        self, optimizer, sample_messages, summary_options
    ):
        """Test optimization stats contain all expected fields."""
        _, stats = optimizer.optimize_message_list(
            messages=sample_messages,
            options=summary_options,
            max_messages=15
        )

        assert "original_count" in stats
        assert "filtered_count" in stats
        assert "deduplication_removed" in stats
        assert "truncated_count" in stats
        assert "final_count" in stats
        assert "reduction_ratio" in stats
        assert "optimization_applied" in stats

    def test_filters_old_messages(self, optimizer, summary_options):
        """Test filtering of very old messages."""
        old_time = datetime.utcnow() - timedelta(days=100)

        messages = [
            ProcessedMessage(
                id="msg_1",
                content="This is a recent message with substantial content for age filtering test",
                author_id="user_1",
                author_name="User1",
                timestamp=datetime.utcnow(),
                channel_id="channel_1"
            ),
            ProcessedMessage(
                id="msg_2",
                content="This is an old message with substantial content for age filtering test",
                author_id="user_2",
                author_name="User2",
                timestamp=old_time,
                channel_id="channel_1"
            )
        ]

        optimized, _ = optimizer.optimize_message_list(
            messages=messages,
            options=summary_options
        )

        # Old message should be filtered
        assert len(optimized) == 1
        assert optimized[0].id == "msg_1"

    def test_smart_truncation_with_attachments(
        self, optimizer, summary_options
    ):
        """Test messages with attachments are prioritized."""
        messages = [
            ProcessedMessage(
                id="msg_1",
                content="Regular message",
                author_id="user_1",
                author_name="User1",
                timestamp=datetime.utcnow(),
                channel_id="channel_1",
                attachments=[]
            ),
            ProcessedMessage(
                id="msg_2",
                content="Message with attachment",
                author_id="user_2",
                author_name="User2",
                timestamp=datetime.utcnow(),
                channel_id="channel_1",
                attachments=[
                    AttachmentInfo(
                        id="att_1",
                        filename="file.pdf",
                        size=1024,
                        url="https://example.com/file.pdf",
                        proxy_url="https://example.com/file.pdf",
                        type=AttachmentType.DOCUMENT
                    )
                ]
            )
        ]

        optimized = optimizer._smart_truncate_messages(messages, max_count=1)

        # Should prefer message with attachment
        assert optimized[0].id == "msg_2"

    def test_smart_truncation_with_code_blocks(
        self, optimizer, summary_options
    ):
        """Test messages with code blocks are prioritized."""
        from src.models.message import CodeBlock

        messages = [
            ProcessedMessage(
                id="msg_1",
                content="Regular message",
                author_id="user_1",
                author_name="User1",
                timestamp=datetime.utcnow(),
                channel_id="channel_1",
                code_blocks=[]
            ),
            ProcessedMessage(
                id="msg_2",
                content="Message with code",
                author_id="user_2",
                author_name="User2",
                timestamp=datetime.utcnow(),
                channel_id="channel_1",
                code_blocks=[
                    CodeBlock(language="python", code="print('hello')", start_line=0, end_line=1)
                ]
            )
        ]

        optimized = optimizer._smart_truncate_messages(messages, max_count=1)

        # Should prefer message with code
        assert optimized[0].id == "msg_2"

    def test_empty_message_list_handling(
        self, optimizer, summary_options
    ):
        """Test handling of empty message list."""
        optimized, stats = optimizer.optimize_message_list(
            messages=[],
            options=summary_options
        )

        assert len(optimized) == 0
        assert stats["original_count"] == 0
        assert stats["final_count"] == 0
