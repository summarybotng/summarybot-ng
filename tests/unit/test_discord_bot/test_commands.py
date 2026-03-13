"""
Unit tests for discord_bot.commands module.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import discord
from discord import app_commands

from src.discord_bot.commands import CommandRegistry


@pytest.fixture
def mock_bot():
    """Create a mock SummaryBot instance."""
    bot = Mock()
    bot.client = Mock()
    bot.client.tree = Mock(spec=app_commands.CommandTree)
    bot.client.tree.command = Mock()
    bot.client.tree.sync = AsyncMock(return_value=[Mock(), Mock(), Mock()])
    bot.client.tree.clear_commands = Mock()
    bot.client.tree.get_commands = Mock(return_value=[])
    bot.client.guilds = []

    return bot


@pytest.fixture
def command_registry(mock_bot):
    """Create a CommandRegistry instance."""
    return CommandRegistry(mock_bot)


class TestCommandRegistryInitialization:
    """Tests for CommandRegistry initialization."""

    def test_initialization(self, mock_bot):
        """Test command registry initialization."""
        registry = CommandRegistry(mock_bot)

        assert registry.bot == mock_bot
        assert registry.tree == mock_bot.client.tree


class TestSetupCommands:
    """Tests for setup_commands method."""

    @pytest.mark.asyncio
    async def test_setup_commands(self, command_registry):
        """Test command setup."""
        # Mock the command decorator
        def mock_command(name, description):
            def decorator(func):
                return func
            return decorator

        command_registry.tree.command = mock_command

        await command_registry.setup_commands()

        # Verify commands were set up (they should be registered)
        # This is a basic test - in practice, we'd verify the commands exist


class TestSyncCommands:
    """Tests for sync_commands method."""

    @pytest.mark.asyncio
    async def test_sync_commands_global(self, command_registry, mock_bot):
        """Test syncing commands globally."""
        result = await command_registry.sync_commands()

        mock_bot.client.tree.sync.assert_called_once_with()
        assert result == 3

    @pytest.mark.asyncio
    async def test_sync_commands_guild(self, command_registry, mock_bot):
        """Test syncing commands for a specific guild."""
        guild_id = "123456789"

        result = await command_registry.sync_commands(guild_id=guild_id)

        # Verify sync was called with guild object
        call_args = mock_bot.client.tree.sync.call_args
        assert call_args is not None
        guild_arg = call_args.kwargs.get('guild')
        assert guild_arg is not None
        assert guild_arg.id == int(guild_id)

    @pytest.mark.asyncio
    async def test_sync_commands_http_error(self, command_registry, mock_bot):
        """Test sync_commands with HTTP error."""
        mock_response = Mock()
        mock_response.status = 500
        mock_response.headers = {}
        mock_bot.client.tree.sync = AsyncMock(
            side_effect=discord.HTTPException(mock_response, "Internal Server Error")
        )

        with pytest.raises(discord.HTTPException):
            await command_registry.sync_commands()

    @pytest.mark.asyncio
    async def test_sync_commands_unexpected_error(self, command_registry, mock_bot):
        """Test sync_commands with unexpected error."""
        mock_bot.client.tree.sync = AsyncMock(side_effect=Exception("Unexpected"))

        with pytest.raises(Exception):
            await command_registry.sync_commands()


class TestClearCommands:
    """Tests for clear_commands method."""

    @pytest.mark.asyncio
    async def test_clear_commands_global(self, command_registry, mock_bot):
        """Test clearing global commands."""
        await command_registry.clear_commands()

        mock_bot.client.tree.clear_commands.assert_called_once()
        mock_bot.client.tree.sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_commands_guild(self, command_registry, mock_bot):
        """Test clearing guild commands."""
        guild_id = "123456789"

        await command_registry.clear_commands(guild_id=guild_id)

        mock_bot.client.tree.clear_commands.assert_called_once()
        mock_bot.client.tree.sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_commands_error(self, command_registry, mock_bot):
        """Test clear_commands with error."""
        mock_bot.client.tree.clear_commands = Mock(side_effect=Exception("Failed"))

        with pytest.raises(Exception):
            await command_registry.clear_commands()


class TestCommandInfo:
    """Tests for command information methods."""

    def test_get_command_count(self, command_registry, mock_bot):
        """Test getting command count."""
        mock_commands = [Mock(), Mock(), Mock()]
        mock_bot.client.tree.get_commands = Mock(return_value=mock_commands)

        count = command_registry.get_command_count()

        assert count == 3

    def test_get_command_names(self, command_registry, mock_bot):
        """Test getting command names."""
        mock_cmd1 = Mock()
        mock_cmd1.name = "help"
        mock_cmd2 = Mock()
        mock_cmd2.name = "about"
        mock_cmd3 = Mock()
        mock_cmd3.name = "status"

        mock_bot.client.tree.get_commands = Mock(
            return_value=[mock_cmd1, mock_cmd2, mock_cmd3]
        )

        names = command_registry.get_command_names()

        assert names == ["help", "about", "status"]

    def test_get_command_names_empty(self, command_registry, mock_bot):
        """Test getting command names when no commands exist."""
        mock_bot.client.tree.get_commands = Mock(return_value=[])

        names = command_registry.get_command_names()

        assert names == []
