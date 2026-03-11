"""
Unit tests for permissions/manager.py.

Tests PermissionManager class.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

from src.permissions.manager import PermissionManager
from src.permissions.cache import PermissionCache
from src.permissions.validators import ValidationResult
from src.models.user import PermissionLevel, UserPermissions


class TestPermissionManager:
    """Tests for PermissionManager class."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock BotConfig."""
        config = MagicMock()
        config.cache_ttl = 3600

        # Guild config
        guild_config = MagicMock()
        guild_config.excluded_channels = []
        guild_config.enabled_channels = []
        guild_config.permission_settings.require_permissions = False
        guild_config.permission_settings.allowed_users = ["user123"]
        guild_config.permission_settings.allowed_roles = []
        guild_config.permission_settings.admin_roles = []

        config.get_guild_config.return_value = guild_config

        return config

    @pytest.fixture
    def cache(self):
        """Create a fresh PermissionCache."""
        return PermissionCache(ttl=3600, max_size=100)

    @pytest.fixture
    def manager(self, mock_config, cache):
        """Create a PermissionManager instance."""
        return PermissionManager(config=mock_config, cache=cache)

    @pytest.fixture
    def mock_channel(self):
        """Create a mock Discord text channel."""
        channel = MagicMock()
        channel.id = 987654321
        channel.guild.id = 123456789

        permissions = MagicMock()
        permissions.read_messages = True
        permissions.read_message_history = True
        permissions.send_messages = True
        permissions.embed_links = True
        channel.permissions_for.return_value = permissions

        return channel

    @pytest.fixture
    def mock_member(self):
        """Create a mock Discord member."""
        member = MagicMock()
        member.id = 111111111
        return member

    # check_channel_access tests

    @pytest.mark.asyncio
    async def test_check_channel_access_granted(self, manager):
        """User with access to channel returns True."""
        result = await manager.check_channel_access(
            user_id="user123",
            channel_id="channel123",
            guild_id="guild123"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_check_channel_access_excluded_channel(self, manager, mock_config):
        """User cannot access excluded channel."""
        guild_config = mock_config.get_guild_config.return_value
        guild_config.excluded_channels = ["channel123"]

        result = await manager.check_channel_access(
            user_id="user123",
            channel_id="channel123",
            guild_id="guild123"
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_check_channel_access_not_in_enabled(self, manager, mock_config):
        """User cannot access channel not in enabled list."""
        guild_config = mock_config.get_guild_config.return_value
        guild_config.enabled_channels = ["other_channel"]

        result = await manager.check_channel_access(
            user_id="user123",
            channel_id="channel123",
            guild_id="guild123"
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_check_channel_access_cached(self, manager):
        """Channel access result is cached."""
        # First call
        await manager.check_channel_access(
            user_id="user123",
            channel_id="channel123",
            guild_id="guild123"
        )

        # Check cache - use manager's cache directly
        cache_key = "channel_access:guild123:user123:channel123"
        cached_result = await manager.cache.get(cache_key)

        assert cached_result is not None

    @pytest.mark.asyncio
    async def test_check_channel_access_uses_cache(self, manager):
        """Subsequent calls use cached result."""
        # Pre-populate manager's cache
        cache_key = "channel_access:guild123:user123:channel123"
        await manager.cache.set(cache_key, False)

        result = await manager.check_channel_access(
            user_id="user123",
            channel_id="channel123",
            guild_id="guild123"
        )

        # Should return cached False even though config would allow
        assert result is False

    @pytest.mark.asyncio
    async def test_check_channel_access_error_handling(self, manager, mock_config):
        """Errors default to denying access."""
        mock_config.get_guild_config.side_effect = Exception("Config error")

        result = await manager.check_channel_access(
            user_id="user123",
            channel_id="channel123",
            guild_id="guild123"
        )

        assert result is False

    # check_command_permission tests

    @pytest.mark.asyncio
    async def test_check_command_permission_granted(self, manager):
        """User with permission returns True."""
        result = await manager.check_command_permission(
            user_id="user123",
            command="summarize",
            guild_id="guild123"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_check_command_permission_denied(self, manager, mock_config):
        """User without permission returns False."""
        guild_config = mock_config.get_guild_config.return_value
        guild_config.permission_settings.require_permissions = True
        guild_config.permission_settings.allowed_users = []

        result = await manager.check_command_permission(
            user_id="user456",  # Not in allowed users
            command="schedule",
            guild_id="guild123"
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_check_command_permission_cached(self, manager):
        """Command permission result is cached."""
        await manager.check_command_permission(
            user_id="user123",
            command="summarize",
            guild_id="guild123"
        )

        cache_key = "command_perm:guild123:user123:summarize"
        cached_result = await manager.cache.get(cache_key)

        assert cached_result is not None

    @pytest.mark.asyncio
    async def test_check_command_permission_schedule_denied(self, manager, mock_config):
        """Schedule command requires can_schedule_summaries."""
        # Grant basic permission but not scheduling
        guild_config = mock_config.get_guild_config.return_value
        guild_config.permission_settings.require_permissions = False

        result = await manager.check_command_permission(
            user_id="user123",
            command="schedule",
            guild_id="guild123"
        )

        # Should be denied because can_schedule_summaries is False by default
        assert result is False

    @pytest.mark.asyncio
    async def test_check_command_permission_error_handling(self, manager, mock_config):
        """Errors default to denying permission."""
        mock_config.get_guild_config.side_effect = Exception("Config error")

        result = await manager.check_command_permission(
            user_id="user123",
            command="summarize",
            guild_id="guild123"
        )

        assert result is False

    # get_user_permissions tests

    @pytest.mark.asyncio
    async def test_get_user_permissions_basic(self, manager):
        """Gets user permissions for a guild."""
        perms = await manager.get_user_permissions(
            user_id="user123",
            guild_id="guild123"
        )

        assert perms.user_id == "user123"
        assert perms.guild_id == "guild123"

    @pytest.mark.asyncio
    async def test_get_user_permissions_no_requirement(self, manager, mock_config):
        """When permissions not required, grants SUMMARIZE level."""
        guild_config = mock_config.get_guild_config.return_value
        guild_config.permission_settings.require_permissions = False

        perms = await manager.get_user_permissions(
            user_id="user123",
            guild_id="guild123"
        )

        assert perms.level == PermissionLevel.SUMMARIZE

    @pytest.mark.asyncio
    async def test_get_user_permissions_allowed_user(self, manager, mock_config):
        """Users in allowed_users list get SUMMARIZE level."""
        guild_config = mock_config.get_guild_config.return_value
        guild_config.permission_settings.require_permissions = True
        guild_config.permission_settings.allowed_users = ["user123"]

        perms = await manager.get_user_permissions(
            user_id="user123",
            guild_id="guild123"
        )

        assert perms.level == PermissionLevel.SUMMARIZE

    @pytest.mark.asyncio
    async def test_get_user_permissions_cached(self, manager):
        """User permissions are cached."""
        await manager.get_user_permissions(
            user_id="user123",
            guild_id="guild123"
        )

        cache_key = "user_perms:guild123:user123"
        cached_perms = await manager.cache.get(cache_key)

        assert cached_perms is not None

    @pytest.mark.asyncio
    async def test_get_user_permissions_uses_cache(self, manager):
        """Subsequent calls use cached permissions."""
        # Pre-populate manager's cache with specific permissions
        cache_key = "user_perms:guild123:user123"
        cached_perms = UserPermissions(
            user_id="user123",
            guild_id="guild123",
            level=PermissionLevel.ADMIN
        )
        await manager.cache.set(cache_key, cached_perms)

        perms = await manager.get_user_permissions(
            user_id="user123",
            guild_id="guild123"
        )

        assert perms.level == PermissionLevel.ADMIN

    @pytest.mark.asyncio
    async def test_get_user_permissions_error_handling(self, manager, mock_config):
        """Errors return minimal permissions."""
        mock_config.get_guild_config.side_effect = Exception("Config error")

        perms = await manager.get_user_permissions(
            user_id="user123",
            guild_id="guild123"
        )

        assert perms.level == PermissionLevel.NONE

    # validate_discord_member_permissions tests

    @pytest.mark.asyncio
    async def test_validate_discord_member_permissions(
        self, manager, mock_member, mock_channel
    ):
        """Validates Discord member permissions."""
        result = await manager.validate_discord_member_permissions(
            member=mock_member,
            channel=mock_channel
        )

        assert isinstance(result, ValidationResult)

    # check_bot_permissions tests

    @pytest.mark.asyncio
    async def test_check_bot_permissions_success(self, manager, mock_channel):
        """Bot with required permissions returns True."""
        bot_member = MagicMock()

        result = await manager.check_bot_permissions(
            bot_member=bot_member,
            channel=mock_channel,
            required_permissions=["read_messages", "send_messages"]
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_check_bot_permissions_missing(self, manager, mock_channel):
        """Bot missing permissions returns False."""
        bot_member = MagicMock()
        permissions = mock_channel.permissions_for.return_value
        permissions.send_messages = False

        result = await manager.check_bot_permissions(
            bot_member=bot_member,
            channel=mock_channel,
            required_permissions=["send_messages"]
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_check_bot_permissions_error_handling(self, manager, mock_channel):
        """Errors return False."""
        bot_member = MagicMock()
        mock_channel.permissions_for.side_effect = Exception("Permission error")

        result = await manager.check_bot_permissions(
            bot_member=bot_member,
            channel=mock_channel,
            required_permissions=["read_messages"]
        )

        assert result is False

    # invalidate_cache tests

    @pytest.mark.asyncio
    async def test_invalidate_cache_user_and_guild(self, manager):
        """Can invalidate cache for specific user and guild."""
        # The invalidation pattern is *:{guild_id}:{user_id}:* which requires trailing content
        await manager.cache.set("channel_access:guild123:user123:channel1", True)
        await manager.cache.set("command_perm:guild123:user123:summarize", True)
        await manager.cache.set("channel_access:guild123:user456:channel1", True)

        await manager.invalidate_cache(user_id="user123", guild_id="guild123")

        # Specific user's entries should be gone
        assert await manager.cache.get("channel_access:guild123:user123:channel1") is None
        assert await manager.cache.get("command_perm:guild123:user123:summarize") is None
        # Other user's entries should remain
        assert await manager.cache.get("channel_access:guild123:user456:channel1") is True

    @pytest.mark.asyncio
    async def test_invalidate_cache_guild_only(self, manager):
        """Can invalidate all cache entries for a guild."""
        await manager.cache.set("user_perms:guild123:user123", "value1")
        await manager.cache.set("user_perms:guild123:user456", "value2")
        await manager.cache.set("user_perms:guild789:user123", "value3")

        await manager.invalidate_cache(guild_id="guild123")

        assert await manager.cache.get("user_perms:guild123:user123") is None
        assert await manager.cache.get("user_perms:guild123:user456") is None
        assert await manager.cache.get("user_perms:guild789:user123") == "value3"

    @pytest.mark.asyncio
    async def test_invalidate_cache_all(self, manager):
        """Can invalidate entire cache."""
        await manager.cache.set("key1", "value1")
        await manager.cache.set("key2", "value2")

        await manager.invalidate_cache()

        assert len(manager.cache) == 0

    # update_user_permissions tests

    @pytest.mark.asyncio
    async def test_update_user_permissions(self, manager):
        """Can update user permissions in cache."""
        new_perms = UserPermissions(
            user_id="user123",
            guild_id="guild123",
            level=PermissionLevel.ADMIN,
            can_schedule_summaries=True
        )

        await manager.update_user_permissions(
            user_id="user123",
            guild_id="guild123",
            permissions=new_perms
        )

        cached = await manager.cache.get("user_perms:guild123:user123")
        assert cached.level == PermissionLevel.ADMIN
        assert cached.can_schedule_summaries is True


class TestPermissionManagerIntegration:
    """Integration tests for PermissionManager with real components."""

    @pytest.fixture
    def full_manager(self):
        """Create PermissionManager with real cache."""
        config = MagicMock()
        config.cache_ttl = 60

        guild_config = MagicMock()
        guild_config.excluded_channels = ["excluded_channel"]
        guild_config.enabled_channels = []
        guild_config.permission_settings.require_permissions = True
        guild_config.permission_settings.allowed_users = ["admin_user"]
        guild_config.permission_settings.allowed_roles = []
        guild_config.permission_settings.admin_roles = []

        config.get_guild_config.return_value = guild_config

        return PermissionManager(config=config)

    @pytest.mark.asyncio
    async def test_full_permission_flow(self, full_manager):
        """Test complete permission check flow."""
        # Admin user should have access
        result = await full_manager.check_channel_access(
            user_id="admin_user",
            channel_id="channel123",
            guild_id="guild123"
        )
        assert result is True

        # Non-admin should not have access (permissions required)
        result = await full_manager.check_channel_access(
            user_id="regular_user",
            channel_id="channel123",
            guild_id="guild123"
        )
        assert result is False

        # Excluded channel should be denied for everyone
        result = await full_manager.check_channel_access(
            user_id="admin_user",
            channel_id="excluded_channel",
            guild_id="guild123"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_cache_invalidation_flow(self, full_manager):
        """Test cache invalidation updates permissions."""
        # Get initial permissions
        perms1 = await full_manager.get_user_permissions(
            user_id="admin_user",
            guild_id="guild123"
        )
        assert perms1.level == PermissionLevel.SUMMARIZE

        # Update permissions
        new_perms = UserPermissions(
            user_id="admin_user",
            guild_id="guild123",
            level=PermissionLevel.ADMIN
        )
        await full_manager.update_user_permissions(
            user_id="admin_user",
            guild_id="guild123",
            permissions=new_perms
        )

        # Should get updated permissions
        perms2 = await full_manager.get_user_permissions(
            user_id="admin_user",
            guild_id="guild123"
        )
        assert perms2.level == PermissionLevel.ADMIN
