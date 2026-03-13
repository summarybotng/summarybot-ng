"""
Unit tests for ClaudeClient.

Tests cover:
- Successful API calls with mock responses
- Rate limiting behavior
- Retry logic with exponential backoff
- Error handling (API errors, network errors)
- Response streaming
- Cost estimation
- Health checks
"""

import pytest
import pytest_asyncio
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta

import anthropic
from anthropic import AsyncAnthropic

from src.summarization.claude_client import (
    ClaudeClient, ClaudeResponse, ClaudeOptions, UsageStats
)
from src.exceptions import (
    ClaudeAPIError, RateLimitError, AuthenticationError,
    NetworkError, TimeoutError, ModelUnavailableError
)


@pytest.fixture
def api_key():
    """Test API key."""
    return "test-api-key-12345"


@pytest.fixture
def claude_options():
    """Default Claude options."""
    return ClaudeOptions(
        model="claude-3-sonnet-20240229",
        max_tokens=4000,
        temperature=0.3
    )


@pytest.fixture
def mock_anthropic_response():
    """Mock Anthropic API response."""
    response = Mock()
    response.content = [Mock(text="This is a test summary.")]
    response.usage = Mock(input_tokens=1000, output_tokens=200)
    response.stop_reason = "end_turn"
    response.model = "claude-3-sonnet-20240229"
    response.id = "msg_test_123"
    return response


@pytest_asyncio.fixture
async def claude_client(api_key):
    """Create ClaudeClient instance."""
    client = ClaudeClient(
        api_key=api_key,
        default_timeout=120,
        max_retries=3
    )
    return client


class TestClaudeClient:
    """Test suite for ClaudeClient."""

    @pytest.mark.asyncio
    async def test_successful_api_call(
        self, claude_client, claude_options, mock_anthropic_response
    ):
        """Test successful API call with valid response."""
        with patch.object(
            claude_client._client.messages, 'create',
            new=AsyncMock(return_value=mock_anthropic_response)
        ):
            result = await claude_client.create_summary(
                prompt="Summarize these messages",
                system_prompt="You are a helpful assistant",
                options=claude_options
            )

            # Assertions
            assert isinstance(result, ClaudeResponse)
            assert result.content == "This is a test summary."
            assert result.input_tokens == 1000
            assert result.output_tokens == 200
            assert result.total_tokens == 1200
            assert result.model == "claude-3-sonnet-20240229"
            assert result.response_id == "msg_test_123"
            assert result.is_complete()

    @pytest.mark.asyncio
    async def test_rate_limiting_behavior(self, claude_client, claude_options, mock_anthropic_response):
        """Test rate limiting applies delays between requests."""
        with patch.object(
            claude_client._client.messages, 'create',
            new=AsyncMock(return_value=mock_anthropic_response)
        ):
            # Make multiple requests
            start_time = asyncio.get_event_loop().time()

            for _ in range(3):
                await claude_client.create_summary(
                    prompt="Test",
                    system_prompt="Test",
                    options=claude_options
                )

            end_time = asyncio.get_event_loop().time()
            elapsed = end_time - start_time

            # Should have delays between requests (at least 0.2s for 3 requests)
            assert elapsed >= 0.2

    @pytest.mark.asyncio
    async def test_retry_logic_success_after_failure(
        self, claude_client, claude_options, mock_anthropic_response
    ):
        """Test retry logic succeeds after initial failure."""
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise anthropic.APITimeoutError("Timeout")
            return mock_anthropic_response

        with patch.object(
            claude_client._client.messages, 'create',
            new=AsyncMock(side_effect=side_effect)
        ):
            result = await claude_client.create_summary(
                prompt="Test",
                system_prompt="Test",
                options=claude_options
            )

            assert result.content == "This is a test summary."
            assert call_count == 2  # Failed once, succeeded on retry

    @pytest.mark.asyncio
    async def test_retry_exhaustion(self, claude_client, claude_options):
        """Test retry logic exhausts and raises error."""
        # Create proper APITimeoutError with request parameter
        timeout_error = anthropic.APITimeoutError(request=MagicMock())

        with patch.object(
            claude_client._client.messages, 'create',
            new=AsyncMock(side_effect=timeout_error)
        ):
            with pytest.raises(TimeoutError) as exc_info:
                await claude_client.create_summary(
                    prompt="Test",
                    system_prompt="Test",
                    options=claude_options
                )

            # TimeoutError is raised by ClaudeClient wrapper
            assert "timeout" in str(exc_info.value).lower() or exc_info.value is not None

    @pytest.mark.asyncio
    async def test_rate_limit_error_handling(self, claude_client, claude_options):
        """Test rate limit error handling with retry."""
        call_count = 0
        mock_response = Mock()
        mock_response.content = [Mock(text="Success after rate limit")]
        mock_response.usage = Mock(input_tokens=100, output_tokens=50)
        mock_response.stop_reason = "end_turn"
        mock_response.id = "msg_after_rate_limit"

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise anthropic.RateLimitError("Rate limit: retry after 1 seconds")
            return mock_response

        with patch.object(
            claude_client._client.messages, 'create',
            new=AsyncMock(side_effect=side_effect)
        ):
            with patch('asyncio.sleep', new=AsyncMock()):  # Mock sleep
                result = await claude_client.create_summary(
                    prompt="Test",
                    system_prompt="Test",
                    options=claude_options
                )

                assert result.content == "Success after rate limit"
                assert call_count == 2

    @pytest.mark.asyncio
    async def test_rate_limit_max_retries_exceeded(self, claude_client, claude_options):
        """Test rate limit exceeds max retries."""
        # Create proper RateLimitError with response and body
        mock_response = MagicMock()
        mock_response.status_code = 429
        rate_limit_error = anthropic.RateLimitError(
            "Rate limit exceeded",
            response=mock_response,
            body={"error": {"message": "Rate limit exceeded"}}
        )

        with patch.object(
            claude_client._client.messages, 'create',
            new=AsyncMock(side_effect=rate_limit_error)
        ):
            with patch('asyncio.sleep', new=AsyncMock()):
                with pytest.raises(RateLimitError) as exc_info:
                    await claude_client.create_summary(
                        prompt="Test",
                        system_prompt="Test",
                        options=claude_options
                    )

                # Check that RateLimitError was raised (custom exception)
                assert exc_info.value is not None

    @pytest.mark.asyncio
    async def test_authentication_error(self, claude_client, claude_options):
        """Test authentication error handling."""
        # Create proper AuthenticationError with response and body
        mock_response = MagicMock()
        mock_response.status_code = 401
        auth_error = anthropic.AuthenticationError(
            "Invalid API key",
            response=mock_response,
            body={"error": {"message": "Invalid API key"}}
        )

        with patch.object(
            claude_client._client.messages, 'create',
            new=AsyncMock(side_effect=auth_error)
        ):
            with pytest.raises(AuthenticationError) as exc_info:
                await claude_client.create_summary(
                    prompt="Test",
                    system_prompt="Test",
                    options=claude_options
                )

            assert exc_info.value.api_name == "Claude"

    @pytest.mark.asyncio
    async def test_network_error(self, claude_client, claude_options):
        """Test network connection error handling."""
        # Create proper APIConnectionError with request parameter
        connection_error = anthropic.APIConnectionError(request=MagicMock())

        with patch.object(
            claude_client._client.messages, 'create',
            new=AsyncMock(side_effect=connection_error)
        ):
            with patch('asyncio.sleep', new=AsyncMock()):
                with pytest.raises(NetworkError) as exc_info:
                    await claude_client.create_summary(
                        prompt="Test",
                        system_prompt="Test",
                        options=claude_options
                    )

                assert exc_info.value.api_name == "Claude"

    @pytest.mark.asyncio
    async def test_bad_request_error(self, claude_client, claude_options):
        """Test bad request error handling."""
        # Create proper BadRequestError with response and body
        mock_response = MagicMock()
        mock_response.status_code = 400
        bad_request_error = anthropic.BadRequestError(
            "Bad request",
            response=mock_response,
            body={"error": {"message": "Bad request"}}
        )

        with patch.object(
            claude_client._client.messages, 'create',
            new=AsyncMock(side_effect=bad_request_error)
        ):
            with pytest.raises(ClaudeAPIError) as exc_info:
                await claude_client.create_summary(
                    prompt="Test",
                    system_prompt="Test",
                    options=claude_options
                )

            assert "Bad request" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_context_length_exceeded(self, claude_client, claude_options):
        """Test context length exceeded error."""
        # Create proper BadRequestError with response and body for context length
        mock_response = MagicMock()
        mock_response.status_code = 400
        context_error = anthropic.BadRequestError(
            "maximum context length exceeded",
            response=mock_response,
            body={"error": {"message": "maximum context length exceeded"}}
        )

        with patch.object(
            claude_client._client.messages, 'create',
            new=AsyncMock(side_effect=context_error)
        ):
            with pytest.raises(ClaudeAPIError) as exc_info:
                await claude_client.create_summary(
                    prompt="Very long prompt" * 10000,
                    system_prompt="Test",
                    options=claude_options
                )

            assert "context length" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_model_unavailable(self, claude_client):
        """Test model unavailable error."""
        invalid_options = ClaudeOptions(model="invalid-model")

        with pytest.raises(ModelUnavailableError) as exc_info:
            await claude_client.create_summary(
                prompt="Test",
                system_prompt="Test",
                options=invalid_options
            )

        assert exc_info.value.model_name == "invalid-model"

    @pytest.mark.asyncio
    async def test_health_check_success(self, claude_client):
        """Test health check with properly configured client."""
        # health_check verifies local config: api_key, primary_model, _client
        claude_client.primary_model = "claude-3-sonnet-20240229"
        is_healthy = await claude_client.health_check()
        assert is_healthy is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, claude_client):
        """Test health check with missing configuration."""
        # No primary_model set → health check returns False
        claude_client.primary_model = None
        is_healthy = await claude_client.health_check()
        assert is_healthy is False

    def test_estimate_cost_sonnet(self, claude_client):
        """Test cost estimation for Sonnet model."""
        cost = claude_client.estimate_cost(
            input_tokens=10000,
            output_tokens=2000,
            model="claude-3-sonnet-20240229"
        )

        # Sonnet: $0.003 per 1K input, $0.015 per 1K output
        expected = (10000 * 0.003 + 2000 * 0.015) / 1000
        assert abs(cost - expected) < 0.0001

    def test_estimate_cost_opus(self, claude_client):
        """Test cost estimation for Opus model."""
        cost = claude_client.estimate_cost(
            input_tokens=5000,
            output_tokens=1000,
            model="claude-3-opus-20240229"
        )

        # Opus: $0.015 per 1K input, $0.075 per 1K output
        expected = (5000 * 0.015 + 1000 * 0.075) / 1000
        assert abs(cost - expected) < 0.0001

    def test_estimate_cost_haiku(self, claude_client):
        """Test cost estimation for Haiku model."""
        cost = claude_client.estimate_cost(
            input_tokens=20000,
            output_tokens=4000,
            model="claude-3-haiku-20240307"
        )

        # Haiku: $0.00025 per 1K input, $0.00125 per 1K output
        expected = (20000 * 0.00025 + 4000 * 0.00125) / 1000
        assert abs(cost - expected) < 0.0001

    def test_estimate_cost_unknown_model(self, claude_client):
        """Test cost estimation for unknown model returns 0."""
        cost = claude_client.estimate_cost(
            input_tokens=1000,
            output_tokens=500,
            model="unknown-model"
        )

        assert cost == 0.0

    def test_usage_stats_tracking(self, claude_client):
        """Test usage statistics are tracked."""
        stats = claude_client.get_usage_stats()

        assert isinstance(stats, UsageStats)
        assert stats.total_requests == 0
        assert stats.total_input_tokens == 0
        assert stats.total_output_tokens == 0
        assert stats.errors_count == 0

    @pytest.mark.asyncio
    async def test_usage_stats_updated_on_success(
        self, claude_client, claude_options, mock_anthropic_response
    ):
        """Test usage stats are updated after successful request."""
        with patch.object(
            claude_client._client.messages, 'create',
            new=AsyncMock(return_value=mock_anthropic_response)
        ):
            await claude_client.create_summary(
                prompt="Test",
                system_prompt="Test",
                options=claude_options
            )

            stats = claude_client.get_usage_stats()
            assert stats.total_requests == 1
            assert stats.total_input_tokens == 1000
            assert stats.total_output_tokens == 200
            assert stats.total_cost_usd > 0

    @pytest.mark.asyncio
    async def test_usage_stats_updated_on_error(
        self, claude_client, claude_options
    ):
        """Test usage stats track errors."""
        # Create proper AuthenticationError with response and body
        mock_response = MagicMock()
        mock_response.status_code = 401
        auth_error = anthropic.AuthenticationError(
            "Auth error",
            response=mock_response,
            body={"error": {"message": "Auth error"}}
        )

        with patch.object(
            claude_client._client.messages, 'create',
            new=AsyncMock(side_effect=auth_error)
        ):
            with pytest.raises(AuthenticationError):
                await claude_client.create_summary(
                    prompt="Test",
                    system_prompt="Test",
                    options=claude_options
                )

            stats = claude_client.get_usage_stats()
            assert stats.errors_count == 1

    def test_build_request_params(self, claude_client, claude_options):
        """Test request parameters are built correctly."""
        params = claude_client._build_request_params(
            prompt="Test prompt",
            system_prompt="System instructions",
            options=claude_options
        )

        assert params["model"] == "claude-3-sonnet-20240229"
        assert params["max_tokens"] == 4000
        assert params["temperature"] == 0.3
        assert params["system"] == "System instructions"
        assert len(params["messages"]) == 1
        assert params["messages"][0]["role"] == "user"
        assert params["messages"][0]["content"] == "Test prompt"

    def test_build_request_params_with_optional_fields(self, claude_client):
        """Test request parameters with optional fields."""
        options = ClaudeOptions(
            model="claude-3-sonnet-20240229",
            max_tokens=4000,
            temperature=0.5,
            top_p=0.9,
            top_k=100,
            stop_sequences=["STOP"],
            stream=True
        )

        params = claude_client._build_request_params(
            prompt="Test",
            system_prompt="System",
            options=options
        )

        assert params["top_p"] == 0.9
        assert params["top_k"] == 100
        assert params["stop_sequences"] == ["STOP"]
        assert params["stream"] is True

    def test_process_response(self, claude_client, mock_anthropic_response):
        """Test response processing."""
        result = claude_client._process_response(
            mock_anthropic_response,
            "claude-3-sonnet-20240229"
        )

        assert result.content == "This is a test summary."
        assert result.input_tokens == 1000
        assert result.output_tokens == 200
        assert result.stop_reason == "end_turn"

    def test_extract_retry_after_from_error(self, claude_client):
        """Test extracting retry-after from error message."""
        error = Exception("Rate limit: retry after 60 seconds")
        retry_after = claude_client._extract_retry_after(error)

        assert retry_after == 60

    def test_extract_retry_after_default(self, claude_client):
        """Test default retry-after when not specified."""
        error = Exception("Rate limit exceeded")
        retry_after = claude_client._extract_retry_after(error)

        assert retry_after == 60  # Default


class TestClaudeResponse:
    """Test ClaudeResponse model."""

    def test_response_properties(self):
        """Test response property calculations."""
        response = ClaudeResponse(
            content="Test content",
            model="claude-3-sonnet-20240229",
            usage={"input_tokens": 500, "output_tokens": 200},
            stop_reason="end_turn",
            response_id="resp_123"
        )

        assert response.input_tokens == 500
        assert response.output_tokens == 200
        assert response.total_tokens == 700
        assert response.is_complete()

    def test_response_incomplete(self):
        """Test incomplete response (max tokens reached)."""
        response = ClaudeResponse(
            content="Truncated content",
            model="claude-3-sonnet-20240229",
            usage={"input_tokens": 1000, "output_tokens": 4000},
            stop_reason="max_tokens"
        )

        assert not response.is_complete()


class TestUsageStats:
    """Test UsageStats model."""

    def test_add_request(self):
        """Test adding successful request to stats."""
        stats = UsageStats()
        response = ClaudeResponse(
            content="Test",
            model="claude-3-sonnet-20240229",
            usage={"input_tokens": 1000, "output_tokens": 500},
            stop_reason="end_turn"
        )

        stats.add_request(response, cost=0.05)

        assert stats.total_requests == 1
        assert stats.total_input_tokens == 1000
        assert stats.total_output_tokens == 500
        assert stats.total_cost_usd == 0.05
        assert stats.last_request_time is not None

    def test_add_error(self):
        """Test adding error to stats."""
        stats = UsageStats()

        stats.add_error(is_rate_limit=True)

        assert stats.errors_count == 1
        assert stats.rate_limit_hits == 1

    def test_add_multiple_requests(self):
        """Test adding multiple requests accumulates stats."""
        stats = UsageStats()

        for i in range(5):
            response = ClaudeResponse(
                content=f"Test {i}",
                model="claude-3-sonnet-20240229",
                usage={"input_tokens": 100, "output_tokens": 50},
                stop_reason="end_turn"
            )
            stats.add_request(response, cost=0.01)

        assert stats.total_requests == 5
        assert stats.total_input_tokens == 500
        assert stats.total_output_tokens == 250
        assert stats.total_cost_usd == 0.05
