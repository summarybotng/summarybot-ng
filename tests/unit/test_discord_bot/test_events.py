"""
Unit tests for discord_bot.events module.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import discord

from src.discord_bot.events import EventHandler
from src.exceptions.base import SummaryBotException, ErrorContext
from src.exceptions.discord_errors import DiscordPermissionError


@pytest.fixture
def mock_bot():
    """Create a mock SummaryBot instance."""
    bot = Mock()
    bot.config = Mock()
    bot.config.get_guild_config = Mock(return_value=Mock())
    bot.client = Mock(spec=discord.Client)
    bot.client.user = Mock()
    bot.client.user.id = 123456789
    bot.client.user.name = "TestBot"
    bot.client.guilds = []
    bot.client.latency = 0.05
    bot.client.change_presence = AsyncMock()
    bot.sync_commands = AsyncMock()
    bot.client.tree = Mock()
    bot.client.tree.error = Mock()
    bot.client.event = Mock()

    return bot


@pytest.fixture
def event_handler(mock_bot):
    """Create an EventHandler instance."""
    return EventHandler(mock_bot)


class TestEventHandlerInitialization:
    """Tests for EventHandler initialization."""

    def test_initialization(self, mock_bot):
        """Test event handler initialization."""
        handler = EventHandler(mock_bot)

        assert handler.bot == mock_bot
        assert handler.config == mock_bot.config


class TestOnReady:
    """Tests for on_ready event handler."""

    @pytest.mark.asyncio
    async def test_on_ready_success(self, event_handler, mock_bot):
        """Test successful on_ready event."""
        mock_guild = Mock()
        mock_guild.name = "Test Guild"
        mock_guild.id = 987654321
        mock_guild.member_count = 100

        mock_bot.client.guilds = [mock_guild]
        mock_bot.client.tree.clear_commands = Mock()
        mock_bot.client.tree.copy_global_to = Mock()

        mock_update = AsyncMock()
        with patch.object(event_handler, '_update_presence', mock_update):
            await event_handler.on_ready()

        mock_bot.sync_commands.assert_called_once_with(guild_id=str(mock_guild.id))
        mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_ready_sync_failure(self, event_handler, mock_bot):
        """Test on_ready when command sync fails."""
        mock_bot.sync_commands = AsyncMock(side_effect=Exception("Sync failed"))
        mock_bot.client.tree.clear_commands = Mock()
        mock_bot.client.tree.copy_global_to = Mock()

        mock_update = AsyncMock()
        with patch.object(event_handler, '_update_presence', mock_update):
            # Should not raise exception
            await event_handler.on_ready()

        mock_update.assert_called_once()


class TestOnGuildJoin:
    """Tests for on_guild_join event handler."""

    @pytest.mark.asyncio
    async def test_on_guild_join_with_system_channel(self, event_handler, mock_bot):
        """Test guild join with system channel available."""
        mock_guild = Mock()
        mock_guild.name = "Test Guild"
        mock_guild.id = 987654321
        mock_guild.member_count = 50
        mock_guild.me = Mock()

        mock_channel = Mock()
        mock_channel.send = AsyncMock()
        mock_channel.permissions_for = Mock(return_value=Mock(send_messages=True))
        mock_guild.system_channel = mock_channel
        mock_guild.text_channels = []

        await event_handler.on_guild_join(mock_guild)

        mock_channel.send.assert_called_once()
        mock_bot.sync_commands.assert_called_once_with(guild_id="987654321")

    @pytest.mark.asyncio
    async def test_on_guild_join_no_system_channel(self, event_handler, mock_bot):
        """Test guild join without system channel."""
        mock_guild = Mock()
        mock_guild.name = "Test Guild"
        mock_guild.id = 987654321
        mock_guild.member_count = 50
        mock_guild.me = Mock()
        mock_guild.system_channel = None

        mock_channel = Mock()
        mock_channel.send = AsyncMock()
        mock_channel.permissions_for = Mock(return_value=Mock(send_messages=True))
        mock_guild.text_channels = [mock_channel]

        await event_handler.on_guild_join(mock_guild)

        mock_channel.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_guild_join_no_permission(self, event_handler, mock_bot):
        """Test guild join when bot lacks send permission."""
        mock_guild = Mock()
        mock_guild.name = "Test Guild"
        mock_guild.id = 987654321
        mock_guild.member_count = 50
        mock_guild.me = Mock()

        mock_channel = Mock()
        mock_resp = Mock()
        mock_resp.status = 403
        mock_resp.headers = {}
        mock_channel.send = AsyncMock(side_effect=discord.Forbidden(mock_resp, "Forbidden"))
        mock_channel.permissions_for = Mock(return_value=Mock(send_messages=True))
        mock_guild.system_channel = mock_channel
        mock_guild.text_channels = []

        # Should not raise exception
        await event_handler.on_guild_join(mock_guild)


class TestOnGuildRemove:
    """Tests for on_guild_remove event handler."""

    @pytest.mark.asyncio
    async def test_on_guild_remove(self, event_handler):
        """Test guild remove event."""
        mock_guild = Mock()
        mock_guild.name = "Test Guild"
        mock_guild.id = 987654321

        # Should not raise exception
        await event_handler.on_guild_remove(mock_guild)


class TestOnApplicationCommandError:
    """Tests for on_application_command_error event handler."""

    @pytest.mark.asyncio
    async def test_custom_exception(self, event_handler):
        """Test handling custom SummaryBotException."""
        mock_interaction = Mock(spec=discord.Interaction)
        mock_interaction.user = Mock(id=111111)
        mock_interaction.guild_id = 222222
        mock_interaction.channel_id = 333333
        mock_interaction.command = Mock(name="test_command")
        mock_interaction.response = Mock()
        mock_interaction.response.is_done = Mock(return_value=False)
        mock_interaction.response.send_message = AsyncMock()

        error = SummaryBotException(
            message="Test error",
            error_code="TEST_ERROR",
            user_message="User friendly error"
        )

        await event_handler.on_application_command_error(mock_interaction, error)

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert call_args.kwargs['ephemeral'] == True

    @pytest.mark.asyncio
    async def test_discord_forbidden_error(self, event_handler):
        """Test handling Discord Forbidden error."""
        mock_interaction = Mock(spec=discord.Interaction)
        mock_interaction.user = Mock(id=111111)
        mock_interaction.guild_id = 222222
        mock_interaction.channel_id = 333333
        mock_interaction.command = Mock(name="test_command")
        mock_interaction.response = Mock()
        mock_interaction.response.is_done = Mock(return_value=False)
        mock_interaction.response.send_message = AsyncMock()

        mock_resp = Mock()
        mock_resp.status = 403
        mock_resp.headers = {}
        error = discord.Forbidden(mock_resp, "Forbidden")

        await event_handler.on_application_command_error(mock_interaction, error)

        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_discord_not_found_error(self, event_handler):
        """Test handling Discord NotFound error."""
        mock_interaction = Mock(spec=discord.Interaction)
        mock_interaction.user = Mock(id=111111)
        mock_interaction.guild_id = 222222
        mock_interaction.channel_id = 333333
        mock_interaction.command = Mock(name="test_command")
        mock_interaction.response = Mock()
        mock_interaction.response.is_done = Mock(return_value=False)
        mock_interaction.response.send_message = AsyncMock()

        mock_resp = Mock()
        mock_resp.status = 404
        mock_resp.headers = {}
        error = discord.NotFound(mock_resp, "Not Found")

        await event_handler.on_application_command_error(mock_interaction, error)

        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_unexpected_error(self, event_handler):
        """Test handling unexpected error."""
        mock_interaction = Mock(spec=discord.Interaction)
        mock_interaction.user = Mock(id=111111)
        mock_interaction.guild_id = 222222
        mock_interaction.channel_id = 333333
        mock_interaction.command = Mock(name="test_command")
        mock_interaction.response = Mock()
        mock_interaction.response.is_done = Mock(return_value=False)
        mock_interaction.response.send_message = AsyncMock()

        error = ValueError("Unexpected error")

        await event_handler.on_application_command_error(mock_interaction, error)

        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_response_already_sent(self, event_handler):
        """Test error handling when response was already sent."""
        mock_interaction = Mock(spec=discord.Interaction)
        mock_interaction.user = Mock(id=111111)
        mock_interaction.guild_id = 222222
        mock_interaction.channel_id = 333333
        mock_interaction.command = Mock(name="test_command")
        mock_interaction.response = Mock()
        mock_interaction.response.is_done = Mock(return_value=True)
        mock_interaction.followup = Mock()
        mock_interaction.followup.send = AsyncMock()

        error = Exception("Test error")

        await event_handler.on_application_command_error(mock_interaction, error)

        mock_interaction.followup.send.assert_called_once()


class TestUpdatePresence:
    """Tests for _update_presence method."""

    @pytest.mark.asyncio
    async def test_update_presence_success(self, event_handler, mock_bot):
        """Test successful presence update."""
        await event_handler._update_presence()

        mock_bot.client.change_presence.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_presence_failure(self, event_handler, mock_bot):
        """Test presence update failure."""
        mock_bot.client.change_presence = AsyncMock(side_effect=Exception("Failed"))

        # Should not raise exception
        await event_handler._update_presence()


class TestRegisterEvents:
    """Tests for register_events method."""

    def test_register_events(self, event_handler, mock_bot):
        """Test event registration."""
        event_handler.register_events()

        # Verify events were registered
        assert mock_bot.client.event.called
        assert mock_bot.client.tree.error.called
