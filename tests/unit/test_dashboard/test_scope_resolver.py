"""
Unit tests for dashboard/utils/scope_resolver.py.

Tests channel resolution for different scopes (channel, category, guild).
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, PropertyMock
from fastapi import HTTPException

import discord

from src.dashboard.utils.scope_resolver import (
    CategoryInfo,
    ResolvedScope,
    resolve_channels_for_scope,
    get_category_info,
    get_scope_display_name,
)
from src.dashboard.models import SummaryScope


class TestCategoryInfo:
    """Tests for CategoryInfo dataclass."""

    def test_basic_creation(self):
        """Create CategoryInfo with required fields."""
        info = CategoryInfo(
            id="123",
            name="General",
            channel_count=3,
            channels=[
                {"id": "1", "name": "chat"},
                {"id": "2", "name": "help"},
                {"id": "3", "name": "announcements"},
            ]
        )
        assert info.id == "123"
        assert info.name == "General"
        assert info.channel_count == 3
        assert len(info.channels) == 3


class TestResolvedScope:
    """Tests for ResolvedScope dataclass."""

    def test_basic_creation(self):
        """Create ResolvedScope with required fields."""
        channels = [MagicMock(spec=discord.TextChannel)]
        scope = ResolvedScope(
            channels=channels,
            scope=SummaryScope.CHANNEL
        )
        assert len(scope.channels) == 1
        assert scope.scope == SummaryScope.CHANNEL
        assert scope.category_info is None

    def test_with_category_info(self):
        """ResolvedScope with category info."""
        category_info = CategoryInfo(
            id="123",
            name="Dev",
            channel_count=2,
            channels=[]
        )
        scope = ResolvedScope(
            channels=[],
            scope=SummaryScope.CATEGORY,
            category_info=category_info
        )
        assert scope.category_info.name == "Dev"


class TestResolveChannelsForScope:
    """Tests for resolve_channels_for_scope function."""

    @pytest.fixture
    def mock_guild(self):
        """Create mock Discord guild."""
        guild = MagicMock(spec=discord.Guild)
        guild.me = MagicMock()
        return guild

    @pytest.fixture
    def mock_text_channel(self):
        """Create mock text channel with permissions."""
        def _create(channel_id, name="test-channel", has_permission=True):
            channel = MagicMock(spec=discord.TextChannel)
            channel.id = int(channel_id)
            channel.name = name
            permissions = MagicMock()
            permissions.read_message_history = has_permission
            channel.permissions_for.return_value = permissions
            return channel
        return _create

    @pytest.mark.asyncio
    async def test_channel_scope_success(self, mock_guild, mock_text_channel):
        """Resolve CHANNEL scope with valid channels."""
        channel = mock_text_channel("123", "general")
        mock_guild.get_channel.return_value = channel

        result = await resolve_channels_for_scope(
            guild=mock_guild,
            scope=SummaryScope.CHANNEL,
            channel_ids=["123"]
        )

        assert len(result.channels) == 1
        assert result.scope == SummaryScope.CHANNEL
        assert result.channel_ids == ["123"]

    @pytest.mark.asyncio
    async def test_channel_scope_missing_ids(self, mock_guild):
        """CHANNEL scope without channel_ids raises error."""
        with pytest.raises(HTTPException) as exc_info:
            await resolve_channels_for_scope(
                guild=mock_guild,
                scope=SummaryScope.CHANNEL,
                channel_ids=None
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_channel_scope_no_valid_channels(self, mock_guild):
        """CHANNEL scope with no valid channels raises error."""
        mock_guild.get_channel.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await resolve_channels_for_scope(
                guild=mock_guild,
                scope=SummaryScope.CHANNEL,
                channel_ids=["999999"]  # Valid numeric ID but channel doesn't exist
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_channel_scope_no_permission(self, mock_guild, mock_text_channel):
        """Channel without read permission is skipped."""
        channel = mock_text_channel("123", "private", has_permission=False)
        mock_guild.get_channel.return_value = channel

        with pytest.raises(HTTPException) as exc_info:
            await resolve_channels_for_scope(
                guild=mock_guild,
                scope=SummaryScope.CHANNEL,
                channel_ids=["123"]
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_category_scope_success(self, mock_guild, mock_text_channel):
        """Resolve CATEGORY scope with valid category."""
        channel1 = mock_text_channel("1", "chat")
        channel2 = mock_text_channel("2", "help")

        category = MagicMock(spec=discord.CategoryChannel)
        category.id = 123
        category.name = "General"
        category.text_channels = [channel1, channel2]

        mock_guild.get_channel.return_value = category

        result = await resolve_channels_for_scope(
            guild=mock_guild,
            scope=SummaryScope.CATEGORY,
            category_id="123"
        )

        assert len(result.channels) == 2
        assert result.scope == SummaryScope.CATEGORY
        assert result.category_info.name == "General"
        assert result.category_info.channel_count == 2

    @pytest.mark.asyncio
    async def test_category_scope_missing_id(self, mock_guild):
        """CATEGORY scope without category_id raises error."""
        with pytest.raises(HTTPException) as exc_info:
            await resolve_channels_for_scope(
                guild=mock_guild,
                scope=SummaryScope.CATEGORY,
                category_id=None
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_category_scope_not_found(self, mock_guild):
        """CATEGORY scope with non-existent ID raises error."""
        mock_guild.get_channel.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await resolve_channels_for_scope(
                guild=mock_guild,
                scope=SummaryScope.CATEGORY,
                category_id="999999"  # Valid numeric ID but category doesn't exist
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_category_scope_not_category(self, mock_guild, mock_text_channel):
        """Non-category channel raises error."""
        channel = mock_text_channel("123", "not-category")
        mock_guild.get_channel.return_value = channel

        with pytest.raises(HTTPException) as exc_info:
            await resolve_channels_for_scope(
                guild=mock_guild,
                scope=SummaryScope.CATEGORY,
                category_id="123"
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_guild_scope_success(self, mock_guild, mock_text_channel):
        """Resolve GUILD scope with enabled channels."""
        channel1 = mock_text_channel("1", "general")
        channel2 = mock_text_channel("2", "random")

        mock_guild.get_channel.side_effect = lambda id: {
            1: channel1,
            2: channel2
        }.get(id)

        result = await resolve_channels_for_scope(
            guild=mock_guild,
            scope=SummaryScope.GUILD,
            enabled_channels=["1", "2"]
        )

        assert len(result.channels) == 2
        assert result.scope == SummaryScope.GUILD

    @pytest.mark.asyncio
    async def test_guild_scope_fallback_all_channels(self, mock_guild, mock_text_channel):
        """GUILD scope without enabled_channels uses all accessible channels."""
        channel1 = mock_text_channel("1", "general")
        channel2 = mock_text_channel("2", "random")
        mock_guild.text_channels = [channel1, channel2]

        result = await resolve_channels_for_scope(
            guild=mock_guild,
            scope=SummaryScope.GUILD,
            enabled_channels=None
        )

        assert len(result.channels) == 2

    @pytest.mark.asyncio
    async def test_guild_scope_no_channels(self, mock_guild):
        """GUILD scope with no accessible channels raises error."""
        mock_guild.text_channels = []
        mock_guild.get_channel.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await resolve_channels_for_scope(
                guild=mock_guild,
                scope=SummaryScope.GUILD,
                enabled_channels=["1"]
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_unknown_scope(self, mock_guild):
        """Unknown scope raises error."""
        with pytest.raises(HTTPException) as exc_info:
            await resolve_channels_for_scope(
                guild=mock_guild,
                scope="UNKNOWN",  # type: ignore
            )
        assert exc_info.value.status_code == 400


class TestGetCategoryInfo:
    """Tests for get_category_info function."""

    @pytest.fixture
    def mock_guild(self):
        """Create mock Discord guild."""
        guild = MagicMock(spec=discord.Guild)
        guild.me = MagicMock()
        return guild

    @pytest.mark.asyncio
    async def test_get_category_info_success(self, mock_guild):
        """Get category info successfully."""
        channel1 = MagicMock(spec=discord.TextChannel)
        channel1.id = 1
        channel1.name = "chat"
        channel1.permissions_for.return_value.read_message_history = True

        category = MagicMock(spec=discord.CategoryChannel)
        category.id = 123
        category.name = "General"
        category.text_channels = [channel1]

        mock_guild.get_channel.return_value = category

        result = await get_category_info(mock_guild, "123")

        assert result.id == "123"
        assert result.name == "General"
        assert result.channel_count == 1

    @pytest.mark.asyncio
    async def test_get_category_info_not_found(self, mock_guild):
        """Category not found raises error."""
        mock_guild.get_channel.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_category_info(mock_guild, "999999")  # Valid numeric ID but category doesn't exist
        assert exc_info.value.status_code == 404


class TestGetScopeDisplayName:
    """Tests for get_scope_display_name function."""

    def test_channel_scope_single(self):
        """Single channel display name."""
        result = get_scope_display_name(
            SummaryScope.CHANNEL,
            channel_names=["general"]
        )
        assert result == "#general"

    def test_channel_scope_few(self):
        """Few channels display name."""
        result = get_scope_display_name(
            SummaryScope.CHANNEL,
            channel_names=["general", "random", "help"]
        )
        assert "#general" in result
        assert "#random" in result
        assert "#help" in result

    def test_channel_scope_many(self):
        """Many channels show count."""
        result = get_scope_display_name(
            SummaryScope.CHANNEL,
            channel_names=["a", "b", "c", "d", "e"]
        )
        assert "5 channels" in result

    def test_channel_scope_no_names(self):
        """No channel names fallback."""
        result = get_scope_display_name(
            SummaryScope.CHANNEL,
            channel_names=None
        )
        assert "Selected channels" in result

    def test_category_scope_with_name(self):
        """Category scope with name."""
        result = get_scope_display_name(
            SummaryScope.CATEGORY,
            category_name="Development"
        )
        assert "Category: Development" in result

    def test_category_scope_no_name(self):
        """Category scope without name."""
        result = get_scope_display_name(
            SummaryScope.CATEGORY,
            category_name=None
        )
        assert result == "Category"

    def test_guild_scope_with_name(self):
        """Guild scope with name."""
        result = get_scope_display_name(
            SummaryScope.GUILD,
            guild_name="My Server"
        )
        assert "Server: My Server" in result

    def test_guild_scope_no_name(self):
        """Guild scope without name."""
        result = get_scope_display_name(
            SummaryScope.GUILD,
            guild_name=None
        )
        assert "Entire server" in result
