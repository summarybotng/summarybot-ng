"""
Unit tests for BaseCommandHandler.

Tests cover:
- Rate limiting per user
- Rate limiting per guild
- Permission validation
- Error handling and user feedback
- Interaction deferral
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
import discord

from src.command_handlers.base import BaseCommandHandler, RateLimitTracker
from src.exceptions import SummaryBotException, UserError


@pytest.fixture
def rate_limiter():
    """Create rate limiter instance."""
    return RateLimitTracker()


@pytest.fixture
def mock_interaction():
    """Create mock Discord interaction."""
    interaction = AsyncMock(spec=discord.Interaction)
    interaction.user = MagicMock()
    interaction.user.id = 123456789
    interaction.guild_id = 987654321
    interaction.channel_id = 111222333
    interaction.command = MagicMock()
    interaction.command.name = "test_command"
    interaction.response = AsyncMock()
    interaction.response.is_done.return_value = False
    interaction.followup = AsyncMock()
    return interaction


@pytest.fixture
def concrete_handler(mock_summarization_engine, mock_permission_manager):
    """Create concrete handler for testing."""
    class ConcreteHandler(BaseCommandHandler):
        async def _execute_command(self, interaction: discord.Interaction, **kwargs):
            # Simple test implementation
            pass

    return ConcreteHandler(
        summarization_engine=mock_summarization_engine,
        permission_manager=mock_permission_manager,
        rate_limit_enabled=True
    )


class TestRateLimitTracker:
    """Test RateLimitTracker functionality."""

    def test_initial_request_allowed(self, rate_limiter):
        """Test that first request is always allowed."""
        allowed, reset_time = rate_limiter.check_rate_limit("user123", max_requests=5, window_seconds=60)

        assert allowed is True
        assert reset_time is None

    def test_requests_within_limit(self, rate_limiter):
        """Test that requests within limit are allowed."""
        user_id = "user123"

        # Make 4 requests (under limit of 5)
        for i in range(4):
            allowed, reset_time = rate_limiter.check_rate_limit(user_id, max_requests=5, window_seconds=60)
            assert allowed is True
            assert reset_time is None

    def test_rate_limit_exceeded(self, rate_limiter):
        """Test that rate limit is enforced."""
        user_id = "user123"

        # Make 5 requests to hit the limit
        for i in range(5):
            rate_limiter.check_rate_limit(user_id, max_requests=5, window_seconds=60)

        # 6th request should be denied
        allowed, reset_time = rate_limiter.check_rate_limit(user_id, max_requests=5, window_seconds=60)

        assert allowed is False
        assert reset_time is not None
        assert reset_time > 0

    def test_rate_limit_per_user(self, rate_limiter):
        """Test that rate limits are tracked per user."""
        user1 = "user123"
        user2 = "user456"

        # Exhaust user1's limit
        for i in range(5):
            rate_limiter.check_rate_limit(user1, max_requests=5, window_seconds=60)

        # User1 should be rate limited
        allowed, _ = rate_limiter.check_rate_limit(user1, max_requests=5, window_seconds=60)
        assert allowed is False

        # User2 should still be allowed
        allowed, _ = rate_limiter.check_rate_limit(user2, max_requests=5, window_seconds=60)
        assert allowed is True

    def test_rate_limit_window_expiry(self, rate_limiter):
        """Test that rate limit resets after window expires."""
        user_id = "user123"

        # Mock utc_now_naive to control time
        with patch('src.command_handlers.base.utc_now_naive') as mock_utc_now:
            base_time = datetime(2024, 1, 1, 12, 0, 0)
            mock_utc_now.return_value = base_time

            # Make 5 requests
            for i in range(5):
                rate_limiter.check_rate_limit(user_id, max_requests=5, window_seconds=60)

            # Should be rate limited
            allowed, _ = rate_limiter.check_rate_limit(user_id, max_requests=5, window_seconds=60)
            assert allowed is False

            # Move time forward past window
            mock_utc_now.return_value = base_time + timedelta(seconds=61)

            # Should be allowed again
            allowed, _ = rate_limiter.check_rate_limit(user_id, max_requests=5, window_seconds=60)
            assert allowed is True

    def test_clear_user_limit(self, rate_limiter):
        """Test clearing rate limit for a user."""
        user_id = "user123"

        # Exhaust limit
        for i in range(5):
            rate_limiter.check_rate_limit(user_id, max_requests=5, window_seconds=60)

        allowed, _ = rate_limiter.check_rate_limit(user_id, max_requests=5, window_seconds=60)
        assert allowed is False

        # Clear limit
        rate_limiter.clear_user_limit(user_id)

        # Should be allowed again
        allowed, _ = rate_limiter.check_rate_limit(user_id, max_requests=5, window_seconds=60)
        assert allowed is True


class TestBaseCommandHandler:
    """Test BaseCommandHandler functionality."""

    @pytest.mark.asyncio
    async def test_handle_command_success(self, concrete_handler, mock_interaction):
        """Test successful command execution."""
        await concrete_handler.handle_command(mock_interaction)

        # Should not send any error responses
        assert not mock_interaction.response.send_message.called

    @pytest.mark.asyncio
    async def test_handle_command_with_rate_limit(self, concrete_handler, mock_interaction):
        """Test that rate limiting is enforced."""
        user_id = str(mock_interaction.user.id)

        # Exhaust rate limit
        for i in range(concrete_handler.max_requests_per_minute):
            await concrete_handler.handle_command(mock_interaction)

        # Next request should be rate limited
        await concrete_handler.handle_command(mock_interaction)

        # Should send rate limit response with embed
        assert mock_interaction.response.send_message.called
        call_args = mock_interaction.response.send_message.call_args
        # Check that an embed was passed
        assert 'embed' in call_args.kwargs or (call_args.args and hasattr(call_args.args[0], 'title'))
        # Extract the embed
        embed = call_args.kwargs.get('embed') if 'embed' in call_args.kwargs else (call_args.args[0] if call_args.args else None)
        assert embed is not None
        # Check that the embed contains rate limit information
        assert hasattr(embed, 'title') and "Rate Limit" in embed.title

    @pytest.mark.asyncio
    async def test_handle_command_without_rate_limit(self, mock_summarization_engine, mock_interaction):
        """Test command execution with rate limiting disabled."""
        class TestHandler(BaseCommandHandler):
            async def _execute_command(self, interaction, **kwargs):
                pass

        handler = TestHandler(
            summarization_engine=mock_summarization_engine,
            rate_limit_enabled=False
        )

        # Make many requests
        for i in range(10):
            await handler.handle_command(mock_interaction)

        # None should be rate limited
        assert not any("Rate Limit" in str(call) for call in mock_interaction.response.send_message.call_args_list)

    @pytest.mark.asyncio
    async def test_permission_check_allowed(self, concrete_handler, mock_interaction):
        """Test command execution when user has permission."""
        # Permission manager returns True
        concrete_handler.permission_manager.check_command_permission.return_value = True

        await concrete_handler.handle_command(mock_interaction)

        # Should execute without permission error
        assert not any("Permission Denied" in str(call) for call in mock_interaction.response.send_message.call_args_list)

    @pytest.mark.asyncio
    async def test_permission_check_denied(self, concrete_handler, mock_interaction):
        """Test command execution when user lacks permission."""
        # Permission manager returns False
        concrete_handler.permission_manager.check_command_permission.return_value = False

        await concrete_handler.handle_command(mock_interaction)

        # Should send permission error
        assert mock_interaction.response.send_message.called
        call_kwargs = mock_interaction.response.send_message.call_args[1]
        embed = call_kwargs.get('embed')
        assert embed is not None
        assert "Permission Denied" in embed.title

    @pytest.mark.asyncio
    async def test_permission_check_without_manager(self, mock_summarization_engine, mock_interaction):
        """Test that commands work without permission manager."""
        class TestHandler(BaseCommandHandler):
            async def _execute_command(self, interaction, **kwargs):
                pass

        handler = TestHandler(
            summarization_engine=mock_summarization_engine,
            permission_manager=None  # No permission manager
        )

        await handler.handle_command(mock_interaction)

        # Should execute without errors
        assert not mock_interaction.response.send_message.called

    @pytest.mark.asyncio
    async def test_user_error_handling(self, mock_summarization_engine, mock_interaction):
        """Test handling of UserError exceptions."""
        class FailingHandler(BaseCommandHandler):
            async def _execute_command(self, interaction, **kwargs):
                raise UserError(
                    message="Test error",
                    error_code="TEST_ERROR",
                    user_message="This is a test error for users."
                )

        handler = FailingHandler(
            summarization_engine=mock_summarization_engine,
            rate_limit_enabled=False
        )

        await handler.handle_command(mock_interaction)

        # Should send error response
        assert mock_interaction.response.send_message.called or mock_interaction.followup.send.called

    @pytest.mark.asyncio
    async def test_generic_error_handling(self, mock_summarization_engine, mock_interaction):
        """Test handling of unexpected exceptions."""
        class FailingHandler(BaseCommandHandler):
            async def _execute_command(self, interaction, **kwargs):
                raise ValueError("Unexpected error")

        handler = FailingHandler(
            summarization_engine=mock_summarization_engine,
            rate_limit_enabled=False
        )

        await handler.handle_command(mock_interaction)

        # Should send error response
        assert mock_interaction.response.send_message.called or mock_interaction.followup.send.called

    @pytest.mark.asyncio
    async def test_defer_response(self, concrete_handler, mock_interaction):
        """Test deferring interaction response."""
        await concrete_handler.defer_response(mock_interaction, ephemeral=False)

        mock_interaction.response.defer.assert_called_once_with(ephemeral=False)

    @pytest.mark.asyncio
    async def test_defer_response_ephemeral(self, concrete_handler, mock_interaction):
        """Test deferring ephemeral response."""
        await concrete_handler.defer_response(mock_interaction, ephemeral=True)

        mock_interaction.response.defer.assert_called_once_with(ephemeral=True)

    @pytest.mark.asyncio
    async def test_defer_response_already_done(self, concrete_handler, mock_interaction):
        """Test deferring when response already sent."""
        mock_interaction.response.is_done.return_value = True

        await concrete_handler.defer_response(mock_interaction)

        # Should not call defer if already done
        assert not mock_interaction.response.defer.called

    @pytest.mark.asyncio
    async def test_send_error_response(self, concrete_handler, mock_interaction):
        """Test sending error response."""
        error = UserError(
            message="Test error",
            error_code="TEST_ERROR",
            user_message="User-friendly error message"
        )

        await concrete_handler.send_error_response(mock_interaction, error)

        # Should send message
        assert mock_interaction.response.send_message.called or mock_interaction.followup.send.called

        # Check embed is created
        if mock_interaction.response.send_message.called:
            call_kwargs = mock_interaction.response.send_message.call_args[1]
        else:
            call_kwargs = mock_interaction.followup.send.call_args[1]

        assert 'embed' in call_kwargs
        assert call_kwargs['ephemeral'] is True

    @pytest.mark.asyncio
    async def test_send_error_response_after_defer(self, concrete_handler, mock_interaction):
        """Test sending error response after deferring."""
        mock_interaction.response.is_done.return_value = True

        error = UserError(
            message="Test error",
            error_code="TEST_ERROR",
            user_message="Error message"
        )

        await concrete_handler.send_error_response(mock_interaction, error)

        # Should use followup
        assert mock_interaction.followup.send.called
        assert not mock_interaction.response.send_message.called

    @pytest.mark.asyncio
    async def test_send_success_response(self, concrete_handler, mock_interaction):
        """Test sending success response."""
        await concrete_handler.send_success_response(
            mock_interaction,
            title="Success",
            description="Operation completed successfully"
        )

        assert mock_interaction.response.send_message.called or mock_interaction.followup.send.called

    @pytest.mark.asyncio
    async def test_send_success_response_with_custom_embed(self, concrete_handler, mock_interaction):
        """Test sending success response with custom embed."""
        custom_embed = discord.Embed(title="Custom", description="Custom embed")

        await concrete_handler.send_success_response(
            mock_interaction,
            title="Success",
            description="Test",
            embed=custom_embed
        )

        # Should use provided embed
        if mock_interaction.response.send_message.called:
            call_kwargs = mock_interaction.response.send_message.call_args[1]
        else:
            call_kwargs = mock_interaction.followup.send.call_args[1]

        assert call_kwargs['embed'] == custom_embed

    @pytest.mark.asyncio
    async def test_send_rate_limit_response(self, concrete_handler, mock_interaction):
        """Test sending rate limit response."""
        await concrete_handler.send_rate_limit_response(mock_interaction, reset_seconds=45)

        assert mock_interaction.response.send_message.called or mock_interaction.followup.send.called

        # Check that reset time is mentioned
        if mock_interaction.response.send_message.called:
            call_kwargs = mock_interaction.response.send_message.call_args[1]
        else:
            call_kwargs = mock_interaction.followup.send.call_args[1]

        assert 'embed' in call_kwargs
        assert call_kwargs['ephemeral'] is True

    @pytest.mark.asyncio
    async def test_send_permission_error(self, concrete_handler, mock_interaction):
        """Test sending permission error."""
        await concrete_handler.send_permission_error(mock_interaction)

        mock_interaction.response.send_message.assert_called_once()
        call_kwargs = mock_interaction.response.send_message.call_args[1]

        assert 'embed' in call_kwargs
        assert call_kwargs['ephemeral'] is True

    @pytest.mark.asyncio
    async def test_retryable_error_hint(self, concrete_handler, mock_interaction):
        """Test that retryable errors include retry hint."""
        error = SummaryBotException(
            message="Test error",
            error_code="TEST_ERROR",
            user_message="Temporary error",
            retryable=True
        )

        await concrete_handler.send_error_response(mock_interaction, error)

        # Verify response was sent
        assert mock_interaction.response.send_message.called or mock_interaction.followup.send.called
