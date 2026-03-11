"""
Integration tests for Discord bot command flow.

Tests the full Discord command flow from interaction -> handler -> engine -> response
using real components with mocked external APIs (Discord, Claude).
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from src.discord_bot.bot import SummaryBot
from src.config.settings import BotConfig, GuildConfig, SummaryOptions
from src.command_handlers.summarize import SummarizeCommandHandler
from src.models.summary import SummaryResult
from src.exceptions import InsufficientContentError, ChannelAccessError
from src.summarization.engine import SummarizationEngine


@pytest.mark.integration
class TestDiscordBotIntegration:
    """Integration tests for Discord bot startup and lifecycle."""

    @pytest_asyncio.fixture
    async def summarization_engine(self, mock_config):
        """Create summarization engine with mocked Claude client."""
        mock_claude = AsyncMock()
        mock_claude.create_summary.return_value = MagicMock(
            content="Test summary content",
            model="claude-3-5-sonnet-20241022",
            input_tokens=1000,
            output_tokens=200,
            total_tokens=1200,
            response_id="test_response_123"
        )

        async def mock_health_check():
            return True
        mock_claude.health_check = mock_health_check

        mock_claude.get_usage_stats.return_value = MagicMock(
            total_requests=1,
            total_tokens=1200,
            total_cost=0.01,
            to_dict=lambda: {"total_requests": 1, "total_tokens": 1200}
        )

        engine = SummarizationEngine(
            claude_client=mock_claude,
            cache=None
        )

        yield engine

        await mock_claude.close() if hasattr(mock_claude, 'close') else None

    @pytest.fixture
    def mock_discord_interaction(self, mock_discord_channel, mock_discord_user):
        """Create a mock Discord interaction for testing."""
        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild_id = 123456789
        interaction.guild = MagicMock()
        interaction.guild.id = 123456789
        interaction.guild.name = "Test Guild"
        interaction.guild.me = MagicMock()
        interaction.channel = mock_discord_channel
        interaction.user = mock_discord_user

        # Create response mock with is_done as a callable that returns False
        interaction.response = AsyncMock()
        interaction.response.is_done = MagicMock(return_value=False)  # Synchronous callable
        interaction.followup = AsyncMock()

        # Setup permissions
        interaction.channel.permissions_for = MagicMock(return_value=MagicMock(
            read_message_history=True,
            send_messages=True
        ))

        return interaction

    @pytest.mark.asyncio
    async def test_bot_initialization_with_engine(self, mock_config, summarization_engine):
        """Test bot initializes correctly with summarization engine."""
        # Create bot with engine service
        bot = SummaryBot(
            config=mock_config,
            services={
                'summarization_engine': summarization_engine
            }
        )

        # Verify bot components are initialized
        assert bot.config == mock_config
        assert bot.client is not None
        assert bot.event_handler is not None
        assert bot.command_registry is not None
        assert not bot.is_running
        assert not bot.is_ready

    @pytest.mark.asyncio
    async def test_command_registration_flow(self, mock_config, summarization_engine):
        """Test command registration with real command tree."""
        bot = SummaryBot(
            config=mock_config,
            services={'summarization_engine': summarization_engine}
        )

        # Setup commands
        await bot.setup_commands()

        # Verify commands are registered
        command_count = bot.command_registry.get_command_count()
        assert command_count > 0, "Commands should be registered"

    @pytest.mark.asyncio
    async def test_full_summarize_command_flow(
        self,
        mock_discord_interaction,
        summarization_engine,
        sample_messages
    ):
        """Test complete summarize command flow from interaction to response."""
        # Create command handler with engine
        handler = SummarizeCommandHandler(
            summarization_engine=summarization_engine
        )

        # Mock message fetching - the actual methods used by handle_summarize
        with patch.object(handler, 'fetch_messages') as mock_fetch, \
             patch.object(handler, '_process_messages') as mock_process:
            # Create processed messages
            from src.models.message import ProcessedMessage
            processed_messages = [
                ProcessedMessage(
                    id=str(msg.id),
                    author_name=msg.author.display_name,
                    author_id=str(msg.author.id),
                    content=msg.content,
                    timestamp=msg.created_at,
                    attachments=[],
                    references=[],
                    mentions=[]
                )
                for msg in sample_messages
            ]

            # Mock fetch_messages to return raw Discord messages
            mock_fetch.return_value = sample_messages
            # Mock _process_messages to return processed messages
            mock_process.return_value = processed_messages

            # Execute command
            await handler.handle_summarize(
                interaction=mock_discord_interaction,
                channel=mock_discord_interaction.channel,
                hours=24,
                length="detailed",
                include_bots=False
            )

            # Verify interaction flow
            mock_discord_interaction.response.defer.assert_called_once()

            # Should send status update and summary
            assert mock_discord_interaction.followup.send.call_count >= 2

            # Verify summary was sent
            calls = mock_discord_interaction.followup.send.call_args_list
            summary_call = calls[-1]
            assert 'embed' in summary_call[1]

    @pytest.mark.asyncio
    async def test_error_propagation_through_layers(
        self,
        mock_discord_interaction,
        summarization_engine
    ):
        """Test that errors propagate correctly through bot layers."""
        handler = SummarizeCommandHandler(
            summarization_engine=summarization_engine
        )

        # Mock insufficient messages
        with patch.object(handler, 'fetch_messages') as mock_fetch, \
             patch.object(handler, '_process_messages') as mock_process:
            mock_fetch.return_value = []  # No raw messages
            mock_process.return_value = []  # No processed messages

            # Execute command - should handle error gracefully
            await handler.handle_summarize(
                interaction=mock_discord_interaction,
                channel=mock_discord_interaction.channel,
                hours=24,
                length="detailed",
                include_bots=False
            )

            # Verify error was sent to user via response.send_message (initial response)
            # or followup.send (after response)
            # The error should be sent via response.send_message since response.is_done() is False
            assert (mock_discord_interaction.response.send_message.called or
                    mock_discord_interaction.followup.send.called), \
                   "Error should be sent via response or followup"

            # Check response.send_message for error embed
            if mock_discord_interaction.response.send_message.called:
                calls = mock_discord_interaction.response.send_message.call_args_list
                # Just verify an embed was sent - error handling is working
                assert len(calls) > 0, "Error response should be sent"
                assert 'embed' in calls[0][1], "Error response should include embed"
            else:
                # Check followup.send for error embed
                calls = mock_discord_interaction.followup.send.call_args_list
                assert len(calls) > 0, "Error response should be sent via followup"
                assert 'embed' in calls[0][1], "Error response should include embed"

    @pytest.mark.asyncio
    async def test_permission_check_integration(
        self,
        mock_discord_interaction,
        summarization_engine
    ):
        """Test permission checking in command flow."""
        handler = SummarizeCommandHandler(
            summarization_engine=summarization_engine
        )

        # Mock no read permission
        mock_discord_interaction.channel.permissions_for.return_value = MagicMock(
            read_message_history=False,
            send_messages=True
        )

        # Execute command
        await handler.handle_summarize(
            interaction=mock_discord_interaction,
            channel=mock_discord_interaction.channel,
            hours=24,
            length="detailed",
            include_bots=False
        )

        # Verify error response for permissions
        assert mock_discord_interaction.followup.send.called

    @pytest.mark.asyncio
    async def test_concurrent_command_execution(
        self,
        mock_config,
        summarization_engine,
        sample_messages
    ):
        """Test handling multiple concurrent command requests."""
        handler = SummarizeCommandHandler(
            summarization_engine=summarization_engine
        )

        # Create multiple interactions
        interactions = []
        for i in range(3):
            interaction = AsyncMock(spec=discord.Interaction)
            interaction.guild_id = 123456789
            interaction.guild = MagicMock()
            interaction.guild.id = 123456789
            interaction.channel = MagicMock()
            interaction.channel.id = 987654321 + i
            interaction.channel.name = f"test-channel-{i}"
            interaction.channel.permissions_for = MagicMock(return_value=MagicMock(
                read_message_history=True
            ))
            interaction.user = MagicMock()
            interaction.user.id = 111111111
            interaction.response = AsyncMock()
            interaction.followup = AsyncMock()
            interactions.append(interaction)

        # Mock message processing
        from src.models.message import ProcessedMessage
        processed_messages = [
            ProcessedMessage(
                id=str(msg.id),
                author_name=msg.author.display_name,
                author_id=str(msg.author.id),
                content=msg.content,
                timestamp=msg.created_at,
                attachments=[],
                references=[],
                mentions=[]
            )
            for msg in sample_messages
        ]

        with patch.object(handler, 'fetch_messages') as mock_fetch, \
             patch.object(handler, '_process_messages') as mock_process:
            mock_fetch.return_value = sample_messages
            mock_process.return_value = processed_messages

            # Execute commands concurrently
            tasks = [
                handler.handle_summarize(
                    interaction=inter,
                    channel=inter.channel,
                    hours=24,
                    length="brief",
                    include_bots=False
                )
                for inter in interactions
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # All should complete without exceptions
            for result in results:
                assert not isinstance(result, Exception)

            # All interactions should receive responses
            for interaction in interactions:
                assert interaction.followup.send.called


@pytest.mark.integration
class TestCommandHandlerIntegration:
    """Integration tests for command handlers with real engine."""

    @pytest.fixture
    def mock_discord_interaction(self, mock_discord_channel, mock_discord_user):
        """Create a mock Discord interaction for testing."""
        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild_id = 123456789
        interaction.guild = MagicMock()
        interaction.guild.id = 123456789
        interaction.guild.name = "Test Guild"
        interaction.guild.me = MagicMock()
        interaction.channel = mock_discord_channel
        interaction.user = mock_discord_user

        # Create response mock with is_done as a callable that returns False
        interaction.response = AsyncMock()
        interaction.response.is_done = MagicMock(return_value=False)  # Synchronous callable
        interaction.followup = AsyncMock()

        # Setup permissions
        interaction.channel.permissions_for = MagicMock(return_value=MagicMock(
            read_message_history=True,
            send_messages=True
        ))

        return interaction

    @pytest.mark.asyncio
    async def test_cost_estimation_integration(
        self,
        mock_discord_interaction,
        sample_messages
    ):
        """Test cost estimation with real prompt building."""
        from src.summarization.engine import SummarizationEngine
        from src.summarization.claude_client import ClaudeClient

        # Create real engine with mocked Claude client
        with patch('src.summarization.claude_client.ClaudeClient') as mock_claude:
            mock_instance = AsyncMock()
            mock_instance.estimate_cost.return_value = 0.0123
            mock_instance.get_usage_stats.return_value = MagicMock(
                to_dict=lambda: {"total_requests": 0}
            )
            mock_claude.return_value = mock_instance

            engine = SummarizationEngine(
                claude_client=mock_instance,
                cache=None
            )

            handler = SummarizeCommandHandler(summarization_engine=engine)

            # Mock message fetching
            from src.models.message import ProcessedMessage
            processed_messages = [
                ProcessedMessage(
                    id=str(msg.id),
                    author_name=msg.author.display_name,
                    author_id=str(msg.author.id),
                    content=msg.content,
                    timestamp=msg.created_at,
                    attachments=[],
                    references=[],
                    mentions=[]
                )
                for msg in sample_messages
            ]

            with patch.object(handler, '_fetch_and_process_messages') as mock_fetch:
                mock_fetch.return_value = processed_messages

                # Execute cost estimation
                await handler.estimate_summary_cost(
                    interaction=mock_discord_interaction,
                    channel=mock_discord_interaction.channel,
                    hours=24
                )

                # Verify response was sent
                assert mock_discord_interaction.followup.send.called
                call_args = mock_discord_interaction.followup.send.call_args
                assert 'embed' in call_args[1]
