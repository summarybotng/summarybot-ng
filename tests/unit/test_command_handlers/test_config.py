"""
Unit tests for ConfigCommandHandler.

Tests cover:
- Config view command
- Config update commands
- Channel whitelist/blacklist management
- Permission-based access
- Config validation
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import discord

from src.command_handlers.config import ConfigCommandHandler
from src.models.summary import SummaryOptions, SummaryLength
from src.config.settings import GuildConfig
from src.exceptions import UserError


@pytest.fixture
def mock_interaction():
    """Create mock Discord interaction."""
    interaction = AsyncMock(spec=discord.Interaction)
    interaction.user = MagicMock()
    interaction.user.id = 123456789
    interaction.guild = MagicMock()
    interaction.guild.id = 987654321
    interaction.guild.name = "Test Guild"
    interaction.guild_id = 987654321
    interaction.command = MagicMock()
    interaction.command.name = "config"
    interaction.response = AsyncMock()
    interaction.response.is_done.return_value = False
    interaction.followup = AsyncMock()
    return interaction


@pytest.fixture
def mock_admin_member():
    """Create mock admin member."""
    member = MagicMock()
    member.guild_permissions = MagicMock()
    member.guild_permissions.administrator = True
    member.guild_permissions.manage_guild = False
    return member


@pytest.fixture
def mock_regular_member():
    """Create mock regular member."""
    member = MagicMock()
    member.guild_permissions = MagicMock()
    member.guild_permissions.administrator = False
    member.guild_permissions.manage_guild = False
    return member


@pytest.fixture
def mock_config_manager():
    """Create mock config manager."""
    manager = MagicMock()

    # Default guild config
    guild_config = GuildConfig(
        guild_id="987654321",
        enabled_channels=["111222333", "444555666"],
        excluded_channels=["777888999"],
        default_summary_options=SummaryOptions(
            summary_length=SummaryLength.DETAILED,
            include_bots=False,
            min_messages=5,
            summarization_model="anthropic/claude-3-haiku"
        )
    )

    # Source code calls self.config_manager.get_current_config() -> bot_config
    # then bot_config.get_guild_config(guild_id) -> GuildConfig
    mock_bot_config = MagicMock()
    mock_bot_config.get_guild_config.return_value = guild_config
    manager.get_current_config.return_value = mock_bot_config

    # update_guild_config is async
    manager.update_guild_config = AsyncMock()
    return manager


@pytest.fixture
def config_handler(mock_summarization_engine, mock_config_manager):
    """Create config command handler."""
    return ConfigCommandHandler(
        summarization_engine=mock_summarization_engine,
        permission_manager=None,
        config_manager=mock_config_manager
    )


class TestConfigCommandHandler:
    """Test ConfigCommandHandler functionality."""

    @pytest.mark.asyncio
    async def test_check_admin_permission_as_admin(self, config_handler, mock_interaction, mock_admin_member):
        """Test admin permission check for administrator."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        result = await config_handler._check_admin_permission(mock_interaction)

        assert result is True

    @pytest.mark.asyncio
    async def test_check_admin_permission_as_manager(self, config_handler, mock_interaction):
        """Test admin permission check for guild manager."""
        member = MagicMock()
        member.guild_permissions = MagicMock()
        member.guild_permissions.administrator = False
        member.guild_permissions.manage_guild = True
        mock_interaction.guild.get_member.return_value = member

        result = await config_handler._check_admin_permission(mock_interaction)

        assert result is True

    @pytest.mark.asyncio
    async def test_check_admin_permission_as_regular_user(self, config_handler, mock_interaction, mock_regular_member):
        """Test admin permission check for regular user."""
        mock_interaction.guild.get_member.return_value = mock_regular_member

        result = await config_handler._check_admin_permission(mock_interaction)

        assert result is False

    @pytest.mark.asyncio
    async def test_check_admin_permission_no_guild(self, config_handler, mock_interaction):
        """Test admin permission check without guild context."""
        mock_interaction.guild = None

        result = await config_handler._check_admin_permission(mock_interaction)

        assert result is False

    @pytest.mark.asyncio
    async def test_handle_config_view_success(self, config_handler, mock_interaction, mock_admin_member):
        """Test viewing current configuration."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        await config_handler.handle_config_view(mock_interaction)

        # Should send config embed
        mock_interaction.response.send_message.assert_called_once()
        call_kwargs = mock_interaction.response.send_message.call_args[1]

        assert 'embed' in call_kwargs
        assert call_kwargs['ephemeral'] is True

    @pytest.mark.asyncio
    async def test_handle_config_view_no_permission(self, config_handler, mock_interaction, mock_regular_member):
        """Test viewing config without permission."""
        mock_interaction.guild.get_member.return_value = mock_regular_member

        await config_handler.handle_config_view(mock_interaction)

        # Should send permission error
        mock_interaction.response.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_handle_config_view_no_config(self, config_handler, mock_interaction,
                                               mock_admin_member, mock_config_manager):
        """Test viewing config when none exists."""
        mock_interaction.guild.get_member.return_value = mock_admin_member
        mock_config_manager.get_guild_config.return_value = None

        await config_handler.handle_config_view(mock_interaction)

        # Should show default config message
        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_config_set_channels_enable(self, config_handler, mock_interaction,
                                                     mock_admin_member, mock_config_manager):
        """Test enabling channels."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        # Mock channel lookup
        channel1 = MagicMock()
        channel1.id = 111222333
        channel2 = MagicMock()
        channel2.id = 444555666

        def get_channel(channel_id):
            if channel_id == 111222333:
                return channel1
            elif channel_id == 444555666:
                return channel2
            return None

        mock_interaction.guild.get_channel = get_channel

        await config_handler.handle_config_set_channels(
            interaction=mock_interaction,
            action="enable",
            channels="<#111222333>, <#444555666>"
        )

        # Should update config
        mock_config_manager.update_guild_config.assert_called_once()

        # Should send success message
        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_config_set_channels_exclude(self, config_handler, mock_interaction,
                                                      mock_admin_member, mock_config_manager):
        """Test excluding channels."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        channel = MagicMock()
        channel.id = 777888999
        mock_interaction.guild.get_channel.return_value = channel

        await config_handler.handle_config_set_channels(
            interaction=mock_interaction,
            action="exclude",
            channels="<#777888999>"
        )

        # Should update config
        mock_config_manager.update_guild_config.assert_called_once()

        # Should send success message
        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_config_set_channels_invalid_action(self, config_handler, mock_interaction, mock_admin_member):
        """Test setting channels with invalid action."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        await config_handler.handle_config_set_channels(
            interaction=mock_interaction,
            action="invalid",
            channels="<#111222333>"
        )

        # Should send error
        mock_interaction.response.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_handle_config_set_channels_no_valid_channels(self, config_handler, mock_interaction, mock_admin_member):
        """Test setting channels with no valid channel IDs."""
        mock_interaction.guild.get_member.return_value = mock_admin_member
        mock_interaction.guild.get_channel.return_value = None

        await config_handler.handle_config_set_channels(
            interaction=mock_interaction,
            action="enable",
            channels="invalid, channels, here"
        )

        # Should send error about no valid channels
        mock_interaction.response.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_handle_config_set_channels_mixed_formats(self, config_handler, mock_interaction,
                                                           mock_admin_member):
        """Test setting channels with mixed ID formats."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        channel1 = MagicMock()
        channel1.id = 111222333
        channel2 = MagicMock()
        channel2.id = 444555666

        def get_channel(channel_id):
            if channel_id == 111222333:
                return channel1
            elif channel_id == 444555666:
                return channel2
            return None

        mock_interaction.guild.get_channel = get_channel

        # Mix of mention and plain ID
        await config_handler.handle_config_set_channels(
            interaction=mock_interaction,
            action="enable",
            channels="<#111222333>, 444555666"
        )

        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_config_set_defaults_length(self, config_handler, mock_interaction,
                                                     mock_admin_member, mock_config_manager):
        """Test setting default summary length."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        await config_handler.handle_config_set_defaults(
            interaction=mock_interaction,
            length="brief"
        )

        # Should save config
        mock_config_manager.update_guild_config.assert_called_once()

        # Verify the config was updated correctly
        saved_config = mock_config_manager.update_guild_config.call_args[0][1]
        assert saved_config.default_summary_options.summary_length == SummaryLength.BRIEF

        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_config_set_defaults_invalid_length(self, config_handler, mock_interaction, mock_admin_member):
        """Test setting invalid summary length."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        await config_handler.handle_config_set_defaults(
            interaction=mock_interaction,
            length="invalid_length"
        )

        # Should send error
        mock_interaction.response.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_handle_config_set_defaults_include_bots(self, config_handler, mock_interaction,
                                                          mock_admin_member, mock_config_manager):
        """Test setting include_bots default."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        await config_handler.handle_config_set_defaults(
            interaction=mock_interaction,
            include_bots=True
        )

        mock_config_manager.update_guild_config.assert_called_once()
        saved_config = mock_config_manager.update_guild_config.call_args[0][1]
        assert saved_config.default_summary_options.include_bots is True

    @pytest.mark.asyncio
    async def test_handle_config_set_defaults_min_messages(self, config_handler, mock_interaction,
                                                          mock_admin_member, mock_config_manager):
        """Test setting minimum messages."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        await config_handler.handle_config_set_defaults(
            interaction=mock_interaction,
            min_messages=10
        )

        mock_config_manager.update_guild_config.assert_called_once()
        saved_config = mock_config_manager.update_guild_config.call_args[0][1]
        assert saved_config.default_summary_options.min_messages == 10

    @pytest.mark.asyncio
    async def test_handle_config_set_defaults_invalid_min_messages(self, config_handler, mock_interaction, mock_admin_member):
        """Test setting invalid minimum messages."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        # Too low
        await config_handler.handle_config_set_defaults(
            interaction=mock_interaction,
            min_messages=0
        )

        assert mock_interaction.response.send_message.called

        # Reset
        mock_interaction.response.send_message.reset_mock()

        # Too high
        await config_handler.handle_config_set_defaults(
            interaction=mock_interaction,
            min_messages=2000
        )

        assert mock_interaction.response.send_message.called

    @pytest.mark.asyncio
    async def test_handle_config_set_defaults_model(self, config_handler, mock_interaction,
                                                    mock_admin_member, mock_config_manager):
        """Test setting Claude model."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        await config_handler.handle_config_set_defaults(
            interaction=mock_interaction,
            model="claude-3-opus-20240229"
        )

        mock_config_manager.update_guild_config.assert_called_once()
        saved_config = mock_config_manager.update_guild_config.call_args[0][1]
        assert saved_config.default_summary_options.summarization_model == "claude-3-opus-20240229"

    @pytest.mark.asyncio
    async def test_handle_config_set_defaults_invalid_model(self, config_handler, mock_interaction, mock_admin_member):
        """Test setting invalid model."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        await config_handler.handle_config_set_defaults(
            interaction=mock_interaction,
            model="invalid-model"
        )

        # Should send error
        mock_interaction.response.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_handle_config_set_defaults_multiple_fields(self, config_handler, mock_interaction,
                                                             mock_admin_member, mock_config_manager):
        """Test setting multiple default fields at once."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        await config_handler.handle_config_set_defaults(
            interaction=mock_interaction,
            length="comprehensive",
            include_bots=True,
            min_messages=15
        )

        mock_config_manager.update_guild_config.assert_called_once()
        saved_config = mock_config_manager.update_guild_config.call_args[0][1]

        assert saved_config.default_summary_options.summary_length == SummaryLength.COMPREHENSIVE
        assert saved_config.default_summary_options.include_bots is True
        assert saved_config.default_summary_options.min_messages == 15

    @pytest.mark.asyncio
    async def test_handle_config_set_defaults_no_fields(self, config_handler, mock_interaction, mock_admin_member):
        """Test setting defaults with no fields specified."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        await config_handler.handle_config_set_defaults(
            interaction=mock_interaction
        )

        # Should send error about no updates
        mock_interaction.response.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_handle_config_set_defaults_no_permission(self, config_handler, mock_interaction, mock_regular_member):
        """Test setting defaults without permission."""
        mock_interaction.guild.get_member.return_value = mock_regular_member

        await config_handler.handle_config_set_defaults(
            interaction=mock_interaction,
            length="brief"
        )

        # Should send permission error
        mock_interaction.response.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_handle_config_reset(self, config_handler, mock_interaction,
                                      mock_admin_member, mock_config_manager):
        """Test resetting configuration."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        await config_handler.handle_config_reset(mock_interaction)

        # Should save default config
        mock_config_manager.update_guild_config.assert_called_once()

        # Should send success message
        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_config_reset_no_permission(self, config_handler, mock_interaction, mock_regular_member):
        """Test resetting config without permission."""
        mock_interaction.guild.get_member.return_value = mock_regular_member

        await config_handler.handle_config_reset(mock_interaction)

        # Should send permission error
        mock_interaction.response.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_handle_config_no_manager(self, mock_summarization_engine, mock_interaction, mock_admin_member):
        """Test config commands without config manager."""
        handler = ConfigCommandHandler(
            summarization_engine=mock_summarization_engine,
            config_manager=None
        )

        mock_interaction.guild.get_member.return_value = mock_admin_member

        await handler.handle_config_set_defaults(
            interaction=mock_interaction,
            length="brief"
        )

        # Should send error about unavailable feature
        mock_interaction.response.send_message.assert_called()
