"""
Unit tests for summarization engine.

Tests cover SummarizationEngine functionality including message summarization,
batch processing, and cost estimation as specified in Phase 3.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from typing import List

from src.summarization.engine import SummarizationEngine, CostEstimate
from src.summarization.claude_client import ClaudeClient, ClaudeResponse
from src.summarization.cache import SummaryCache
from src.models.summary import SummaryResult, SummaryOptions, SummarizationContext
from src.models.summary import SummaryLength
from src.models.message import ProcessedMessage
from src.exceptions import SummarizationError, ClaudeAPIError, InsufficientContentError


@pytest.mark.unit
class TestSummarizationEngine:
    """Test SummarizationEngine core functionality."""
    
    @pytest.fixture
    def mock_claude_client(self):
        """Mock Claude client for testing."""
        import json
        client = AsyncMock(spec=ClaudeClient)
        summary_json = json.dumps({
            "summary_text": "This is a test summary of the conversation covering key points and action items.",
            "key_points": [
                {"text": "Key point 1", "references": [1], "confidence": 0.9}
            ],
            "action_items": [],
            "decisions": [],
            "participants": [
                {"name": "user_0", "message_count": 4, "key_contributions": [
                    {"text": "Contributed to discussion", "references": [1]}
                ]}
            ],
            "technical_terms": [],
            "sources": [
                {"position": 1, "author": "user_0", "time": "12:00", "snippet": "Test message"}
            ]
        })
        response = ClaudeResponse(
            content=summary_json,
            usage={"input_tokens": 1000, "output_tokens": 200},
            model="claude-3-sonnet-20240229",
            stop_reason="end_turn",
            created_at=datetime.utcnow(),
            fallback_info={}
        )
        client.create_summary_with_fallback.return_value = response
        client.create_summary.return_value = response
        def mock_estimate_cost(input_tokens, output_tokens, model=""):
            # Return higher cost for opus models
            if "opus" in model:
                return 0.015
            return 0.005
        client.estimate_cost.side_effect = mock_estimate_cost
        return client
    
    @pytest.fixture
    def mock_cache(self):
        """Mock summary cache for testing."""
        cache = AsyncMock(spec=SummaryCache)
        cache.get_cached_summary.return_value = None  # No cached result by default
        return cache
    
    @pytest.fixture
    def summarization_engine(self, mock_claude_client, mock_cache):
        """Create SummarizationEngine instance for testing."""
        return SummarizationEngine(mock_claude_client, mock_cache)
    
    @pytest.fixture
    def sample_messages(self):
        """Create sample processed messages for testing."""
        messages = []
        base_time = datetime.utcnow() - timedelta(hours=1)
        
        for i in range(10):
            message = ProcessedMessage(
                id=f"msg_{i}",
                author_name=f"user_{i % 3}",
                author_id=f"user_id_{i % 3}",
                content=f"This is test message number {i+1} with some content.",
                timestamp=base_time + timedelta(minutes=i * 5),
                thread_info=None,
                attachments=[],
                references=[]
            )
            messages.append(message)
        
        return messages
    
    @pytest.fixture
    def summary_options(self):
        """Create summary options for testing."""
        return SummaryOptions(
            summary_length=SummaryLength.DETAILED,
            include_bots=False,
            include_attachments=True,
            min_messages=5,
            summarization_model="claude-3-sonnet-20240229",
            temperature=0.3,
            max_tokens=4000
        )
    
    @pytest.fixture
    def summarization_context(self):
        """Create summarization context for testing."""
        return SummarizationContext(
            channel_name="test-channel",
            guild_name="Test Guild",
            total_participants=3,
            time_span_hours=1.0,
            message_types={"text": 10},
            dominant_topics=["testing"],
            thread_count=0
        )
    
    @pytest.mark.asyncio
    async def test_summarize_messages_success(
        self, 
        summarization_engine, 
        sample_messages, 
        summary_options, 
        summarization_context,
        mock_claude_client,
        mock_cache
    ):
        """Test successful message summarization."""
        result = await summarization_engine.summarize_messages(
            messages=sample_messages,
            options=summary_options,
            context=summarization_context
        )
        
        # Verify Claude client was called
        mock_claude_client.create_summary_with_fallback.assert_called_once()

        # Verify cache was checked and result was cached
        mock_cache.get_cached_summary.assert_called_once()
        mock_cache.cache_summary.assert_called_once()

        # Verify result structure
        assert isinstance(result, SummaryResult)
        assert result.message_count == len(sample_messages)
        assert "test summary" in result.summary_text.lower()
        assert result.start_time <= result.end_time
    
    @pytest.mark.asyncio
    async def test_summarize_messages_cached_result(
        self, 
        summarization_engine, 
        sample_messages, 
        summary_options, 
        summarization_context,
        mock_claude_client,
        mock_cache
    ):
        """Test summarization with cached result available."""
        # Setup cached result
        cached_summary = SummaryResult(
            id="cached_123",
            channel_id="channel_123",
            guild_id="guild_123",
            start_time=datetime.utcnow() - timedelta(hours=1),
            end_time=datetime.utcnow(),
            message_count=len(sample_messages),
            key_points=["Cached point 1"],
            action_items=[],
            technical_terms=[],
            participants=[],
            summary_text="Cached summary",
            metadata={},
            created_at=datetime.utcnow()
        )
        mock_cache.get_cached_summary.return_value = cached_summary
        
        result = await summarization_engine.summarize_messages(
            messages=sample_messages,
            options=summary_options,
            context=summarization_context
        )
        
        # Verify cache was checked but Claude client was not called
        mock_cache.get_cached_summary.assert_called_once()
        mock_claude_client.create_summary_with_fallback.assert_not_called()
        
        # Verify cached result was returned
        assert result == cached_summary
        assert result.summary_text == "Cached summary"
    
    @pytest.mark.asyncio
    async def test_summarize_messages_insufficient_content(
        self, 
        summarization_engine, 
        summary_options, 
        summarization_context
    ):
        """Test summarization with insufficient messages."""
        # Create fewer messages than minimum required
        few_messages = [
            ProcessedMessage(
                id="msg_1",
                author_name="user_1",
                author_id="user_id_1",
                content="Short message",
                timestamp=datetime.utcnow(),
                thread_info=None,
                attachments=[],
                references=[]
            )
        ]
        
        with pytest.raises(InsufficientContentError) as exc_info:
            await summarization_engine.summarize_messages(
                messages=few_messages,
                options=summary_options,
                context=summarization_context
            )
        
        assert "insufficient content" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_summarize_messages_claude_api_error(
        self, 
        summarization_engine, 
        sample_messages, 
        summary_options, 
        summarization_context,
        mock_claude_client
    ):
        """Test summarization with Claude API error."""
        # Configure Claude client to raise an error
        mock_claude_client.create_summary_with_fallback.side_effect = ClaudeAPIError(
            "Rate limit exceeded", "RATE_LIMIT_EXCEEDED"
        )
        
        with pytest.raises(SummarizationError) as exc_info:
            await summarization_engine.summarize_messages(
                messages=sample_messages,
                options=summary_options,
                context=summarization_context
            )
        
        assert "summarization failed" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_batch_summarize_success(
        self, 
        summarization_engine, 
        sample_messages, 
        summary_options, 
        summarization_context
    ):
        """Test successful batch summarization."""
        # Create multiple summarization requests as dicts
        requests = [
            {
                "messages": sample_messages[:5],
                "options": summary_options,
                "context": summarization_context,
                "channel_id": "channel_1",
                "guild_id": "guild_1"
            },
            {
                "messages": sample_messages[5:],
                "options": summary_options,
                "context": summarization_context,
                "channel_id": "channel_2",
                "guild_id": "guild_1"
            }
        ]
        
        results = await summarization_engine.batch_summarize(requests)
        
        assert len(results) == 2
        assert all(isinstance(result, SummaryResult) for result in results)
        assert results[0].channel_id == "channel_1"
        assert results[1].channel_id == "channel_2"
    
    @pytest.mark.asyncio
    async def test_batch_summarize_partial_failure(
        self, 
        summarization_engine, 
        sample_messages, 
        summary_options, 
        summarization_context,
        mock_claude_client
    ):
        """Test batch summarization with partial failures."""
        import json
        # Configure Claude client to fail on all calls for the second batch request
        # The resilient engine retries multiple times, so we provide enough responses
        success_response = ClaudeResponse(
            content=json.dumps({
                "summary_text": "First summary successful",
                "key_points": [], "action_items": [], "decisions": [],
                "participants": [], "technical_terms": [], "sources": []
            }),
            usage={"input_tokens": 500, "output_tokens": 100},
            model="claude-3-sonnet-20240229",
            stop_reason="end_turn",
            created_at=datetime.utcnow(),
            fallback_info={}
        )
        error = ClaudeAPIError("Second request failed", "API_ERROR")
        # First request succeeds (resilient engine may retry), second always fails
        mock_claude_client.create_summary_with_fallback.side_effect = (
            [success_response] + [error] * 20
        )

        requests = [
            {
                "messages": sample_messages[:5],
                "options": summary_options,
                "context": summarization_context,
                "channel_id": "channel_1",
                "guild_id": "guild_1"
            },
            {
                "messages": sample_messages[5:],
                "options": summary_options,
                "context": summarization_context,
                "channel_id": "channel_2",
                "guild_id": "guild_1"
            }
        ]

        # batch_summarize returns error results instead of raising
        results = await summarization_engine.batch_summarize(requests)
        assert len(results) == 2
        # Second result should be an error summary
        assert results[1].metadata.get("error") is True
    
    @pytest.mark.asyncio
    async def test_estimate_cost(self, summarization_engine, sample_messages, summary_options):
        """Test cost estimation for summarization."""
        estimate = await summarization_engine.estimate_cost(
            messages=sample_messages,
            options=summary_options
        )
        
        assert isinstance(estimate, CostEstimate)
        assert estimate.total_tokens > 0
        assert estimate.estimated_cost_usd > 0.0
        assert estimate.model == summary_options.summarization_model
    
    @pytest.mark.asyncio
    async def test_estimate_cost_large_batch(self, summarization_engine, summary_options):
        """Test cost estimation for large message batch."""
        # Create large message batch
        large_messages = []
        for i in range(1000):
            message = ProcessedMessage(
                id=f"large_msg_{i}",
                author_name=f"user_{i % 10}",
                author_id=f"user_id_{i % 10}",
                content=f"Large batch message {i+1} with substantial content to test token estimation.",
                timestamp=datetime.utcnow(),
                thread_info=None,
                attachments=[],
                references=[]
            )
            large_messages.append(message)

        estimate = await summarization_engine.estimate_cost(
            messages=large_messages,
            options=summary_options
        )
        
        assert estimate.total_tokens > 10000  # Should be substantial for 1000 messages
        assert estimate.estimated_cost_usd > 0.0  # Should have meaningful cost
    
    @pytest.mark.asyncio
    async def test_estimate_cost_different_models(self, summarization_engine, sample_messages):
        """Test cost estimation for different Claude models."""
        sonnet_options = SummaryOptions(
            summary_length=SummaryLength.DETAILED,
            summarization_model="claude-3-sonnet-20240229"
        )

        opus_options = SummaryOptions(
            summary_length=SummaryLength.DETAILED,
            summarization_model="claude-3-opus-20240229"
        )

        sonnet_estimate = await summarization_engine.estimate_cost(sample_messages, sonnet_options)
        opus_estimate = await summarization_engine.estimate_cost(sample_messages, opus_options)
        
        # Opus should be more expensive than Sonnet
        assert opus_estimate.estimated_cost_usd > sonnet_estimate.estimated_cost_usd
        assert opus_estimate.model == "claude-3-opus-20240229"
        assert sonnet_estimate.model == "claude-3-sonnet-20240229"
    
    @pytest.mark.asyncio
    async def test_summarize_with_thread_context(
        self, 
        summarization_engine, 
        summary_options, 
        summarization_context,
        mock_claude_client
    ):
        """Test summarization with thread context."""
        # Create messages with thread information
        thread_messages = []
        base_time = datetime.utcnow() - timedelta(hours=1)
        
        for i in range(5):
            message = ProcessedMessage(
                id=f"thread_msg_{i}",
                author_name="thread_user",
                author_id="thread_user_id",
                content=f"This thread message number {i+1} discusses important implementation details",
                timestamp=base_time + timedelta(minutes=i * 2),
                thread_info=MagicMock(
                    thread_id="thread_123",
                    thread_name="Test Thread",
                    parent_message_id="parent_msg_1"
                ),
                attachments=[],
                references=[]
            )
            thread_messages.append(message)
        
        result = await summarization_engine.summarize_messages(
            messages=thread_messages,
            options=summary_options,
            context=summarization_context
        )
        
        # Verify thread context was included in the prompt
        call_args = mock_claude_client.create_summary_with_fallback.call_args
        prompt_arg = call_args[1]['prompt'] if 'prompt' in call_args[1] else call_args[0][0]

        assert "thread" in prompt_arg.lower()
        assert isinstance(result, SummaryResult)
    
    @pytest.mark.asyncio
    async def test_summarize_with_attachments(
        self, 
        summarization_engine, 
        summary_options, 
        summarization_context,
        mock_claude_client
    ):
        """Test summarization with message attachments."""
        # Create messages with attachments
        attachment_messages = []
        base_time = datetime.utcnow() - timedelta(hours=1)
        
        for i in range(5):
            attachments = []
            if i % 2 == 0:  # Every other message has an attachment
                att_mock = MagicMock()
                att_mock.filename = f"file_{i}.pdf"
                att_mock.size = 1024 * (i + 1)
                att_mock.content_type = "application/pdf"
                att_mock.get_summary_text.return_value = f"file_{i}.pdf (PDF, {1024 * (i + 1)} bytes)"
                attachments = [att_mock]
            
            message = ProcessedMessage(
                id=f"attach_msg_{i}",
                author_name="attach_user",
                author_id="attach_user_id",
                content=f"This message contains important attachment details number {i+1} for review",
                timestamp=base_time + timedelta(minutes=i * 3),
                thread_info=None,
                attachments=attachments,
                references=[]
            )
            attachment_messages.append(message)
        
        result = await summarization_engine.summarize_messages(
            messages=attachment_messages,
            options=summary_options,
            context=summarization_context
        )
        
        # Verify attachment information was processed
        assert isinstance(result, SummaryResult)
        assert result.message_count == len(attachment_messages)
        
        # Check that attachment info was included in the Claude prompt
        call_args = mock_claude_client.create_summary_with_fallback.call_args
        prompt_arg = call_args[1]['prompt'] if 'prompt' in call_args[1] else call_args[0][0]
        assert "attachment" in prompt_arg.lower() or "file" in prompt_arg.lower()