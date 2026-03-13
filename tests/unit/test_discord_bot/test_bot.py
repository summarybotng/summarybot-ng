"""
Unit tests for discord_bot.bot module.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock, patch
import discord

from src.discord_bot.bot import SummaryBot
from src.config.settings import BotConfig


@pytest.fixture
def mock_config():
    """Create a mock bot configuration."""
    config = Mock(spec=BotConfig)
    config.discord_token = "test_token_123"
    config.claude_api_key = "test_api_key_123"
    config.guild_configs = {}
    return config


@pytest.fixture
def summary_bot(mock_config):
    """Create a SummaryBot instance with mocked Discord client."""
    with patch('discord.Client'), patch('discord.app_commands.CommandTree'):
        bot = SummaryBot(config=mock_config)
        bot.client = MagicMock()
        bot.client.tree = MagicMock()
        bot.client.user = Mock()
        bot.client.user.name = "TestBot"
        bot.client.user.id = 123456789
        bot.client.guilds = []
        bot.client.is_ready = Mock(return_value=False)
        bot.client.latency = 0.05
        bot.client.start = AsyncMock()
        bot.client.close = AsyncMock()
        bot.client.change_presence = AsyncMock()
        bot.client.wait_until_ready = AsyncMock()
        bot.client.get_guild = Mock(return_value=None)
        bot.client.get_channel = Mock(return_value=None)
        bot.client.fetch_guild = AsyncMock(return_value=None)
        bot.client.fetch_channel = AsyncMock(return_value=None)

        return bot


class TestSummaryBotInitialization:
    """Tests for SummaryBot initialization."""

    def test_bot_initialization(self, mock_config):
        """Test basic bot initialization."""
        with patch('discord.Client'), patch('discord.app_commands.CommandTree'):
            bot = SummaryBot(config=mock_config)

            assert bot.config == mock_config
            assert bot.services == {}
            assert not bot.is_running
            assert bot.event_handler is not None
            assert bot.command_registry is not None

    def test_bot_initialization_with_services(self, mock_config):
        """Test bot initialization with services."""
        services = {"test_service": Mock()}

        with patch('discord.Client'), patch('discord.app_commands.CommandTree'):
            bot = SummaryBot(config=mock_config, services=services)

            assert bot.services == services


class TestBotLifecycle:
    """Tests for bot lifecycle methods."""

    @pytest.mark.asyncio
    async def test_start_bot(self, summary_bot):
        """Test starting the bot."""
        summary_bot.event_handler.register_events = Mock()
        summary_bot.setup_commands = AsyncMock()

        # Start bot in background
        task = asyncio.create_task(summary_bot.start())

        # Wait a moment for setup
        await asyncio.sleep(0.1)

        # Verify setup was called
        summary_bot.event_handler.register_events.assert_called_once()
        summary_bot.setup_commands.assert_called_once()
        summary_bot.client.start.assert_called_once_with("test_token_123")

        # Cancel the task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_stop_bot(self, summary_bot):
        """Test stopping the bot."""
        summary_bot._is_running = True

        await summary_bot.stop()

        summary_bot.client.change_presence.assert_called_once()
        summary_bot.client.close.assert_called_once()
        assert not summary_bot.is_running

    @pytest.mark.asyncio
    async def test_stop_bot_not_running(self, summary_bot):
        """Test stopping bot that isn't running."""
        summary_bot._is_running = False

        await summary_bot.stop()

        summary_bot.client.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_wait_until_ready(self, summary_bot):
        """Test waiting until bot is ready."""
        await summary_bot.wait_until_ready()

        summary_bot.client.wait_until_ready.assert_called_once()

    @pytest.mark.asyncio
    async def test_wait_until_ready_timeout(self, summary_bot):
        """Test wait_until_ready with timeout."""
        summary_bot.client.wait_until_ready = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )

        with pytest.raises(TimeoutError):
            await summary_bot.wait_until_ready(timeout=1.0)


class TestCommandManagement:
    """Tests for command management methods."""

    @pytest.mark.asyncio
    async def test_setup_commands(self, summary_bot):
        """Test setting up commands."""
        summary_bot.command_registry.setup_commands = AsyncMock()
        summary_bot.command_registry.get_command_count = Mock(return_value=5)

        await summary_bot.setup_commands()

        summary_bot.command_registry.setup_commands.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_commands_global(self, summary_bot):
        """Test syncing commands globally."""
        summary_bot.command_registry.sync_commands = AsyncMock(return_value=5)

        await summary_bot.sync_commands()

        summary_bot.command_registry.sync_commands.assert_called_once_with(None)

    @pytest.mark.asyncio
    async def test_sync_commands_guild(self, summary_bot):
        """Test syncing commands for a specific guild."""
        summary_bot.command_registry.sync_commands = AsyncMock(return_value=5)
        guild_id = "123456789"

        await summary_bot.sync_commands(guild_id=guild_id)

        summary_bot.command_registry.sync_commands.assert_called_once_with(guild_id)


class TestBotProperties:
    """Tests for bot properties."""

    def test_is_ready_true(self, summary_bot):
        """Test is_ready property when bot is ready."""
        summary_bot.client.is_ready = Mock(return_value=True)

        assert summary_bot.is_ready == True

    def test_is_ready_false(self, summary_bot):
        """Test is_ready property when bot is not ready."""
        summary_bot.client.is_ready = Mock(return_value=False)

        assert summary_bot.is_ready == False

    def test_is_running_true(self, summary_bot):
        """Test is_running property when bot is running."""
        summary_bot._is_running = True

        assert summary_bot.is_running == True

    def test_is_running_false(self, summary_bot):
        """Test is_running property when bot is not running."""
        summary_bot._is_running = False

        assert summary_bot.is_running == False

    def test_user_property(self, summary_bot):
        """Test user property."""
        assert summary_bot.user == summary_bot.client.user

    def test_guilds_property(self, summary_bot):
        """Test guilds property."""
        mock_guilds = [Mock(), Mock()]
        summary_bot.client.guilds = mock_guilds

        assert summary_bot.guilds == mock_guilds


class TestGuildAndChannelAccess:
    """Tests for guild and channel access methods."""

    def test_get_guild_found(self, summary_bot):
        """Test getting a guild that exists."""
        mock_guild = Mock()
        summary_bot.client.get_guild = Mock(return_value=mock_guild)

        result = summary_bot.get_guild(123456789)

        assert result == mock_guild
        summary_bot.client.get_guild.assert_called_once_with(123456789)

    def test_get_guild_not_found(self, summary_bot):
        """Test getting a guild that doesn't exist."""
        summary_bot.client.get_guild = Mock(return_value=None)

        result = summary_bot.get_guild(123456789)

        assert result is None

    def test_get_channel_found(self, summary_bot):
        """Test getting a channel that exists."""
        mock_channel = Mock()
        summary_bot.client.get_channel = Mock(return_value=mock_channel)

        result = summary_bot.get_channel(123456789)

        assert result == mock_channel

    def test_get_channel_not_found(self, summary_bot):
        """Test getting a channel that doesn't exist."""
        summary_bot.client.get_channel = Mock(return_value=None)

        result = summary_bot.get_channel(123456789)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_or_fetch_guild_cached(self, summary_bot):
        """Test getting a guild from cache."""
        mock_guild = Mock()
        summary_bot.client.get_guild = Mock(return_value=mock_guild)

        result = await summary_bot.get_or_fetch_guild(123456789)

        assert result == mock_guild
        summary_bot.client.fetch_guild.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_or_fetch_guild_fetch(self, summary_bot):
        """Test fetching a guild from API."""
        mock_guild = Mock()
        summary_bot.client.get_guild = Mock(return_value=None)
        summary_bot.client.fetch_guild = AsyncMock(return_value=mock_guild)

        result = await summary_bot.get_or_fetch_guild(123456789)

        assert result == mock_guild
        summary_bot.client.fetch_guild.assert_called_once_with(123456789)

    @pytest.mark.asyncio
    async def test_get_or_fetch_guild_not_found(self, summary_bot):
        """Test fetching a guild that doesn't exist."""
        summary_bot.client.get_guild = Mock(return_value=None)
        mock_response = Mock()
        mock_response.status = 404
        mock_response.reason = "Not Found"
        summary_bot.client.fetch_guild = AsyncMock(
            side_effect=discord.NotFound(mock_response, "Not Found")
        )

        result = await summary_bot.get_or_fetch_guild(123456789)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_or_fetch_channel_cached(self, summary_bot):
        """Test getting a channel from cache."""
        mock_channel = Mock()
        summary_bot.client.get_channel = Mock(return_value=mock_channel)

        result = await summary_bot.get_or_fetch_channel(123456789)

        assert result == mock_channel
        summary_bot.client.fetch_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_or_fetch_channel_fetch(self, summary_bot):
        """Test fetching a channel from API."""
        mock_channel = Mock()
        summary_bot.client.get_channel = Mock(return_value=None)
        summary_bot.client.fetch_channel = AsyncMock(return_value=mock_channel)

        result = await summary_bot.get_or_fetch_channel(123456789)

        assert result == mock_channel
        summary_bot.client.fetch_channel.assert_called_once_with(123456789)


class TestBotRepresentation:
    """Tests for bot string representation."""

    def test_repr_running(self, summary_bot):
        """Test repr when bot is running."""
        summary_bot._is_running = True

        repr_str = repr(summary_bot)

        assert "running" in repr_str
        assert "TestBot" in repr_str

    def test_repr_stopped(self, summary_bot):
        """Test repr when bot is stopped."""
        summary_bot._is_running = False

        repr_str = repr(summary_bot)

        assert "stopped" in repr_str
