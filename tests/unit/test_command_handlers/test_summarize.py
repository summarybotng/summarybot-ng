"""
Unit tests for SummarizeCommandHandler.

Tests cover:
- /summarize command with various options
- /quick-summary command
- Time period parsing
- Channel selection
- Summary customization (length, format)
- Error scenarios (no messages, API failures)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
import discord

from src.command_handlers.summarize import SummarizeCommandHandler
from src.models.summary import SummaryOptions, SummaryLength, SummaryResult
from src.models.message import ProcessedMessage
from src.exceptions import UserError, InsufficientContentError, ChannelAccessError


@pytest.fixture
def mock_interaction():
    """Create mock Discord interaction."""
    interaction = AsyncMock(spec=discord.Interaction)
    interaction.user = MagicMock()
    interaction.user.id = 123456789
    interaction.guild = MagicMock()
    interaction.guild.id = 987654321
    interaction.guild.name = "Test Guild"
    interaction.guild.me = MagicMock()
    interaction.channel_id = 111222333
    interaction.command = MagicMock()
    interaction.command.name = "summarize"
    interaction.response = AsyncMock()
    interaction.response.is_done.return_value = False
    interaction.followup = AsyncMock()
    return interaction


@pytest.fixture
def mock_text_channel():
    """Create mock text channel."""
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 111222333
    channel.name = "test-channel"
    channel.mention = "<#111222333>"

    # Mock permissions
    permissions = MagicMock()
    permissions.read_message_history = True
    channel.permissions_for.return_value = permissions

    # Mock history
    async def mock_history(limit, after, before, oldest_first):
        return AsyncMock()

    channel.history = MagicMock(return_value=AsyncMock())

    return channel


@pytest.fixture
def summarize_handler(mock_summarization_engine):
    """Create summarize command handler."""
    return SummarizeCommandHandler(
        summarization_engine=mock_summarization_engine,
        permission_manager=None,
        message_fetcher=None,
        message_filter=None,
        message_cleaner=None
    )


@pytest.fixture
def sample_processed_messages():
    """Create sample processed messages."""
    base_time = datetime.utcnow() - timedelta(hours=1)
    messages = []

    for i in range(10):
        msg = ProcessedMessage(
            id=str(1000 + i),
            author_name=f"User{i % 3}",
            author_id=str(100 + (i % 3)),
            content=f"Test message {i}: This is a substantial message with content.",
            timestamp=base_time + timedelta(minutes=i * 5),
            attachments=[],
            references=[],
            mentions=[]
        )
        messages.append(msg)

    return messages


class TestSummarizeCommandHandler:
    """Test SummarizeCommandHandler functionality."""

    @pytest.mark.asyncio
    async def test_handle_summarize_basic(self, summarize_handler, mock_interaction,
                                         mock_text_channel, sample_processed_messages):
        """Test basic summarize command."""
        mock_interaction.channel = mock_text_channel

        # Mock message history
        async def mock_history_iter(*args, **kwargs):
            for msg in sample_processed_messages:
                discord_msg = MagicMock()
                discord_msg.id = msg.id
                discord_msg.author = MagicMock()
                discord_msg.author.display_name = msg.author_name
                discord_msg.author.id = msg.author_id
                discord_msg.author.bot = False
                discord_msg.content = msg.content
                discord_msg.created_at = msg.timestamp
                discord_msg.attachments = []
                yield discord_msg

        mock_text_channel.history.return_value.__aiter__ = mock_history_iter

        # Mock summary result
        summary_result = MagicMock(spec=SummaryResult)
        summary_result.to_embed_dict.return_value = {
            "title": "Summary",
            "description": "Test summary"
        }
        summarize_handler.summarization_engine.summarize_messages.return_value = summary_result

        await summarize_handler.handle_summarize(
            interaction=mock_interaction,
            channel=mock_text_channel,
            hours=24,
            length="detailed"
        )

        # Should defer response
        mock_interaction.response.defer.assert_called_once()

        # Should send summary
        assert mock_interaction.followup.send.called

    @pytest.mark.asyncio
    async def test_handle_summarize_custom_channel(self, summarize_handler, mock_interaction,
                                                   mock_text_channel, sample_processed_messages):
        """Test summarizing a different channel."""
        other_channel = MagicMock(spec=discord.TextChannel)
        other_channel.id = 999888777
        other_channel.name = "other-channel"
        other_channel.mention = "<#999888777>"

        permissions = MagicMock()
        permissions.read_message_history = True
        other_channel.permissions_for.return_value = permissions

        # Mock history
        async def mock_history_iter(*args, **kwargs):
            for msg in sample_processed_messages:
                discord_msg = MagicMock()
                discord_msg.id = msg.id
                discord_msg.author = MagicMock()
                discord_msg.author.display_name = msg.author_name
                discord_msg.author.id = msg.author_id
                discord_msg.author.bot = False
                discord_msg.content = msg.content
                discord_msg.created_at = msg.timestamp
                discord_msg.attachments = []
                yield discord_msg

        other_channel.history.return_value.__aiter__ = mock_history_iter

        summary_result = MagicMock(spec=SummaryResult)
        summary_result.to_embed_dict.return_value = {"title": "Summary"}
        summarize_handler.summarization_engine.summarize_messages.return_value = summary_result

        await summarize_handler.handle_summarize(
            interaction=mock_interaction,
            channel=other_channel,
            hours=12
        )

        # Should use specified channel
        assert mock_interaction.followup.send.called

    @pytest.mark.asyncio
    async def test_handle_summarize_no_permission(self, summarize_handler, mock_interaction, mock_text_channel):
        """Test summarizing channel without read permission."""
        mock_interaction.channel = mock_text_channel

        # Deny read permission
        permissions = MagicMock()
        permissions.read_message_history = False
        mock_text_channel.permissions_for.return_value = permissions

        await summarize_handler.handle_summarize(
            interaction=mock_interaction,
            channel=mock_text_channel
        )

        # Should send error response
        assert mock_interaction.followup.send.called or mock_interaction.response.send_message.called

    @pytest.mark.asyncio
    async def test_handle_summarize_invalid_channel_type(self, summarize_handler, mock_interaction):
        """Test summarizing non-text channel."""
        voice_channel = MagicMock(spec=discord.VoiceChannel)

        await summarize_handler.handle_summarize(
            interaction=mock_interaction,
            channel=voice_channel
        )

        # Should send error
        assert mock_interaction.followup.send.called or mock_interaction.response.send_message.called

    @pytest.mark.asyncio
    async def test_handle_summarize_custom_time_range(self, summarize_handler, mock_interaction,
                                                     mock_text_channel, sample_processed_messages):
        """Test summarizing with custom time range."""
        mock_interaction.channel = mock_text_channel

        async def mock_history_iter(*args, **kwargs):
            for msg in sample_processed_messages:
                discord_msg = MagicMock()
                discord_msg.id = msg.id
                discord_msg.author = MagicMock()
                discord_msg.author.display_name = msg.author_name
                discord_msg.author.id = msg.author_id
                discord_msg.author.bot = False
                discord_msg.content = msg.content
                discord_msg.created_at = msg.timestamp
                discord_msg.attachments = []
                yield discord_msg

        mock_text_channel.history.return_value.__aiter__ = mock_history_iter

        summary_result = MagicMock(spec=SummaryResult)
        summary_result.to_embed_dict.return_value = {"title": "Summary"}
        summarize_handler.summarization_engine.summarize_messages.return_value = summary_result

        await summarize_handler.handle_summarize(
            interaction=mock_interaction,
            channel=mock_text_channel,
            start_time="2 hours ago",
            end_time="1 hour ago"
        )

        assert mock_interaction.followup.send.called

    @pytest.mark.asyncio
    async def test_handle_summarize_different_lengths(self, summarize_handler, mock_interaction,
                                                      mock_text_channel, sample_processed_messages):
        """Test different summary lengths."""
        mock_interaction.channel = mock_text_channel

        async def mock_history_iter(*args, **kwargs):
            for msg in sample_processed_messages:
                discord_msg = MagicMock()
                discord_msg.id = msg.id
                discord_msg.author = MagicMock()
                discord_msg.author.display_name = msg.author_name
                discord_msg.author.id = msg.author_id
                discord_msg.author.bot = False
                discord_msg.content = msg.content
                discord_msg.created_at = msg.timestamp
                discord_msg.attachments = []
                yield discord_msg

        mock_text_channel.history.return_value.__aiter__ = mock_history_iter

        summary_result = MagicMock(spec=SummaryResult)
        summary_result.to_embed_dict.return_value = {"title": "Summary"}
        summarize_handler.summarization_engine.summarize_messages.return_value = summary_result

        for length in ["brief", "detailed", "comprehensive"]:
            mock_interaction.response.is_done.return_value = False
            mock_interaction.response.defer.reset_mock()
            mock_interaction.followup.send.reset_mock()

            await summarize_handler.handle_summarize(
                interaction=mock_interaction,
                channel=mock_text_channel,
                length=length
            )

            assert mock_interaction.followup.send.called

    @pytest.mark.asyncio
    async def test_handle_summarize_invalid_length(self, summarize_handler, mock_interaction, mock_text_channel):
        """Test summarizing with invalid length."""
        await summarize_handler.handle_summarize(
            interaction=mock_interaction,
            channel=mock_text_channel,
            length="invalid_length"
        )

        # Should send error
        assert mock_interaction.followup.send.called or mock_interaction.response.send_message.called

    @pytest.mark.asyncio
    async def test_handle_summarize_include_bots(self, summarize_handler, mock_interaction,
                                                 mock_text_channel, sample_processed_messages):
        """Test summarizing with bot messages included."""
        mock_interaction.channel = mock_text_channel

        # Mix of bot and user messages
        async def mock_history_iter(*args, **kwargs):
            for i, msg in enumerate(sample_processed_messages):
                discord_msg = MagicMock()
                discord_msg.id = msg.id
                discord_msg.author = MagicMock()
                discord_msg.author.display_name = msg.author_name
                discord_msg.author.id = msg.author_id
                discord_msg.author.bot = (i % 2 == 0)  # Every other is a bot
                discord_msg.content = msg.content
                discord_msg.created_at = msg.timestamp
                discord_msg.attachments = []
                yield discord_msg

        mock_text_channel.history.return_value.__aiter__ = mock_history_iter

        summary_result = MagicMock(spec=SummaryResult)
        summary_result.to_embed_dict.return_value = {"title": "Summary"}
        summarize_handler.summarization_engine.summarize_messages.return_value = summary_result

        await summarize_handler.handle_summarize(
            interaction=mock_interaction,
            channel=mock_text_channel,
            include_bots=True
        )

        assert mock_interaction.followup.send.called

    @pytest.mark.asyncio
    async def test_handle_summarize_insufficient_messages(self, summarize_handler, mock_interaction, mock_text_channel):
        """Test summarizing with too few messages."""
        mock_interaction.channel = mock_text_channel

        # Return only 2 messages (below minimum)
        async def mock_history_iter(*args, **kwargs):
            for i in range(2):
                discord_msg = MagicMock()
                discord_msg.id = str(i)
                discord_msg.author = MagicMock()
                discord_msg.author.bot = False
                discord_msg.content = f"Message {i}"
                discord_msg.created_at = datetime.utcnow()
                discord_msg.attachments = []
                yield discord_msg

        mock_text_channel.history.return_value.__aiter__ = mock_history_iter

        await summarize_handler.handle_summarize(
            interaction=mock_interaction,
            channel=mock_text_channel
        )

        # Should send error about insufficient messages
        assert mock_interaction.followup.send.called or mock_interaction.response.send_message.called

    @pytest.mark.asyncio
    async def test_handle_quick_summary(self, summarize_handler, mock_interaction,
                                       mock_text_channel, sample_processed_messages):
        """Test quick summary command."""
        mock_interaction.channel = mock_text_channel

        async def mock_history_iter(*args, **kwargs):
            for msg in sample_processed_messages:
                discord_msg = MagicMock()
                discord_msg.id = msg.id
                discord_msg.author = MagicMock()
                discord_msg.author.display_name = msg.author_name
                discord_msg.author.id = msg.author_id
                discord_msg.author.bot = False
                discord_msg.content = msg.content
                discord_msg.created_at = msg.timestamp
                discord_msg.attachments = []
                yield discord_msg

        mock_text_channel.history.return_value.__aiter__ = mock_history_iter

        summary_result = MagicMock(spec=SummaryResult)
        summary_result.to_embed_dict.return_value = {"title": "Summary"}
        summarize_handler.summarization_engine.summarize_messages.return_value = summary_result

        await summarize_handler.handle_quick_summary(
            interaction=mock_interaction,
            minutes=60
        )

        assert mock_interaction.followup.send.called

    @pytest.mark.asyncio
    async def test_handle_quick_summary_invalid_minutes(self, summarize_handler, mock_interaction):
        """Test quick summary with invalid minutes."""
        # Too few minutes
        await summarize_handler.handle_quick_summary(
            interaction=mock_interaction,
            minutes=2
        )

        assert mock_interaction.followup.send.called or mock_interaction.response.send_message.called

        # Reset mocks
        mock_interaction.followup.send.reset_mock()
        mock_interaction.response.send_message.reset_mock()
        mock_interaction.response.is_done.return_value = False

        # Too many minutes
        await summarize_handler.handle_quick_summary(
            interaction=mock_interaction,
            minutes=2000
        )

        assert mock_interaction.followup.send.called or mock_interaction.response.send_message.called

    @pytest.mark.asyncio
    async def test_estimate_summary_cost(self, summarize_handler, mock_interaction,
                                        mock_text_channel, sample_processed_messages):
        """Test cost estimation for summary."""
        mock_interaction.channel = mock_text_channel

        async def mock_history_iter(*args, **kwargs):
            for msg in sample_processed_messages:
                discord_msg = MagicMock()
                discord_msg.id = msg.id
                discord_msg.author = MagicMock()
                discord_msg.author.display_name = msg.author_name
                discord_msg.author.id = msg.author_id
                discord_msg.author.bot = False
                discord_msg.content = msg.content
                discord_msg.created_at = msg.timestamp
                discord_msg.attachments = []
                yield discord_msg

        mock_text_channel.history.return_value.__aiter__ = mock_history_iter

        # Mock cost estimate
        summarize_handler.summarization_engine.estimate_cost.return_value = {
            "message_count": 10,
            "estimated_cost_usd": 0.05,
            "input_tokens": 1000,
            "output_tokens": 200,
            "model": "claude-3-sonnet-20240229"
        }

        await summarize_handler.estimate_summary_cost(
            interaction=mock_interaction,
            channel=mock_text_channel,
            hours=24
        )

        assert mock_interaction.followup.send.called
        call_kwargs = mock_interaction.followup.send.call_args[1]
        assert call_kwargs['ephemeral'] is True

    @pytest.mark.asyncio
    async def test_fetch_and_process_messages_with_fetcher(self, mock_summarization_engine,
                                                          mock_text_channel, sample_processed_messages):
        """Test message fetching with MessageFetcher."""
        # Create Discord-like mock messages (fetcher returns raw messages, not ProcessedMessage)
        raw_messages = []
        for msg in sample_processed_messages:
            discord_msg = MagicMock()
            discord_msg.id = msg.id
            discord_msg.author = MagicMock()
            discord_msg.author.display_name = msg.author_name
            discord_msg.author.id = msg.author_id
            discord_msg.author.bot = False
            discord_msg.content = msg.content
            discord_msg.created_at = msg.timestamp
            discord_msg.attachments = []
            raw_messages.append(discord_msg)

        mock_fetcher = AsyncMock()
        mock_fetcher.fetch_messages.return_value = raw_messages

        handler = SummarizeCommandHandler(
            summarization_engine=mock_summarization_engine,
            message_fetcher=mock_fetcher
        )

        start_time = datetime.utcnow() - timedelta(hours=1)
        end_time = datetime.utcnow()
        options = SummaryOptions()

        result = await handler._fetch_and_process_messages(
            mock_text_channel,
            start_time,
            end_time,
            options
        )

        # Should use fetcher
        mock_fetcher.fetch_messages.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_summarize_api_failure(self, summarize_handler, mock_interaction,
                                               mock_text_channel, sample_processed_messages):
        """Test handling of API failures."""
        mock_interaction.channel = mock_text_channel

        async def mock_history_iter(*args, **kwargs):
            for msg in sample_processed_messages:
                discord_msg = MagicMock()
                discord_msg.id = msg.id
                discord_msg.author = MagicMock()
                discord_msg.author.display_name = msg.author_name
                discord_msg.author.id = msg.author_id
                discord_msg.author.bot = False
                discord_msg.content = msg.content
                discord_msg.created_at = msg.timestamp
                discord_msg.attachments = []
                yield discord_msg

        mock_text_channel.history.return_value.__aiter__ = mock_history_iter

        # Mock API failure
        summarize_handler.summarization_engine.summarize_messages.side_effect = Exception("API Error")

        await summarize_handler.handle_summarize(
            interaction=mock_interaction,
            channel=mock_text_channel
        )

        # Should send error response
        assert mock_interaction.followup.send.called or mock_interaction.response.send_message.called
