"""
Unit tests for dashboard/models.py.

Tests dataclasses and Pydantic schemas for the dashboard API.
"""

import pytest
from datetime import datetime, timedelta

from src.dashboard.models import (
    GuildRole,
    ConfigStatus,
    DashboardUser,
    DashboardGuild,
    DashboardSession,
    AuthLoginResponse,
    AuthCallbackRequest,
    UserResponse,
    GuildBriefResponse,
    AuthCallbackResponse,
    AuthRefreshResponse,
    GuildListItem,
)


class TestGuildRoleEnum:
    """Tests for GuildRole enum."""

    def test_role_values(self):
        """Verify all role values."""
        assert GuildRole.OWNER.value == "owner"
        assert GuildRole.ADMIN.value == "admin"
        assert GuildRole.MEMBER.value == "member"

    def test_role_from_string(self):
        """Role can be created from string."""
        assert GuildRole("owner") == GuildRole.OWNER
        assert GuildRole("admin") == GuildRole.ADMIN
        assert GuildRole("member") == GuildRole.MEMBER


class TestConfigStatusEnum:
    """Tests for ConfigStatus enum."""

    def test_status_values(self):
        """Verify all status values."""
        assert ConfigStatus.CONFIGURED.value == "configured"
        assert ConfigStatus.NEEDS_SETUP.value == "needs_setup"
        assert ConfigStatus.INACTIVE.value == "inactive"


class TestDashboardUser:
    """Tests for DashboardUser dataclass."""

    def test_basic_creation(self):
        """Create user with basic info."""
        user = DashboardUser(
            id="123456789",
            username="testuser",
            discriminator="1234",
            avatar="abc123"
        )
        assert user.id == "123456789"
        assert user.username == "testuser"
        assert user.discriminator == "1234"
        assert user.avatar == "abc123"

    def test_avatar_url_with_avatar(self):
        """avatar_url returns CDN URL when avatar exists."""
        user = DashboardUser(
            id="123456789",
            username="testuser",
            discriminator=None,
            avatar="abc123"
        )
        expected = "https://cdn.discordapp.com/avatars/123456789/abc123.png"
        assert user.avatar_url == expected

    def test_avatar_url_without_avatar(self):
        """avatar_url returns None when no avatar."""
        user = DashboardUser(
            id="123456789",
            username="testuser",
            discriminator=None,
            avatar=None
        )
        assert user.avatar_url is None

    def test_optional_discriminator(self):
        """discriminator is optional."""
        user = DashboardUser(
            id="123",
            username="user",
            discriminator=None,
            avatar=None
        )
        assert user.discriminator is None


class TestDashboardGuild:
    """Tests for DashboardGuild dataclass."""

    def test_basic_creation(self):
        """Create guild with basic info."""
        guild = DashboardGuild(
            id="987654321",
            name="Test Server",
            icon="def456",
            owner=False,
            permissions=0
        )
        assert guild.id == "987654321"
        assert guild.name == "Test Server"
        assert guild.owner is False

    def test_icon_url_with_icon(self):
        """icon_url returns CDN URL when icon exists."""
        guild = DashboardGuild(
            id="987654321",
            name="Test Server",
            icon="def456",
            owner=False,
            permissions=0
        )
        expected = "https://cdn.discordapp.com/icons/987654321/def456.png"
        assert guild.icon_url == expected

    def test_icon_url_without_icon(self):
        """icon_url returns None when no icon."""
        guild = DashboardGuild(
            id="987654321",
            name="Test Server",
            icon=None,
            owner=False,
            permissions=0
        )
        assert guild.icon_url is None

    def test_can_manage_owner(self):
        """Owner can manage guild."""
        guild = DashboardGuild(
            id="987654321",
            name="Test Server",
            icon=None,
            owner=True,
            permissions=0
        )
        assert guild.can_manage() is True

    def test_can_manage_administrator(self):
        """User with ADMINISTRATOR permission can manage."""
        ADMINISTRATOR = 0x8
        guild = DashboardGuild(
            id="987654321",
            name="Test Server",
            icon=None,
            owner=False,
            permissions=ADMINISTRATOR
        )
        assert guild.can_manage() is True

    def test_can_manage_manage_guild(self):
        """User with MANAGE_GUILD permission can manage."""
        MANAGE_GUILD = 0x20
        guild = DashboardGuild(
            id="987654321",
            name="Test Server",
            icon=None,
            owner=False,
            permissions=MANAGE_GUILD
        )
        assert guild.can_manage() is True

    def test_cannot_manage_no_permissions(self):
        """User without permissions cannot manage."""
        guild = DashboardGuild(
            id="987654321",
            name="Test Server",
            icon=None,
            owner=False,
            permissions=0
        )
        assert guild.can_manage() is False

    def test_get_role_owner(self):
        """get_role returns OWNER for owner."""
        guild = DashboardGuild(
            id="987654321",
            name="Test Server",
            icon=None,
            owner=True,
            permissions=0
        )
        assert guild.get_role() == GuildRole.OWNER

    def test_get_role_admin(self):
        """get_role returns ADMIN for admin."""
        ADMINISTRATOR = 0x8
        guild = DashboardGuild(
            id="987654321",
            name="Test Server",
            icon=None,
            owner=False,
            permissions=ADMINISTRATOR
        )
        assert guild.get_role() == GuildRole.ADMIN

    def test_get_role_member(self):
        """get_role returns MEMBER for regular member."""
        guild = DashboardGuild(
            id="987654321",
            name="Test Server",
            icon=None,
            owner=False,
            permissions=0
        )
        assert guild.get_role() == GuildRole.MEMBER


class TestDashboardSession:
    """Tests for DashboardSession dataclass."""

    def test_basic_creation(self):
        """Create session with all fields."""
        now = datetime.utcnow()
        session = DashboardSession(
            id="session123",
            discord_user_id="123456789",
            discord_username="testuser",
            discord_discriminator="1234",
            discord_avatar="abc123",
            discord_access_token="encrypted_access",
            discord_refresh_token="encrypted_refresh",
            token_expires_at=now + timedelta(hours=1),
            manageable_guild_ids=["guild1", "guild2"],
            jwt_token_hash="hash123",
            created_at=now,
            last_activity=now,
            expires_at=now + timedelta(days=7),
        )
        assert session.discord_user_id == "123456789"
        assert len(session.manageable_guild_ids) == 2

    def test_optional_fields(self):
        """Optional fields can be None."""
        now = datetime.utcnow()
        session = DashboardSession(
            id="session123",
            discord_user_id="123456789",
            discord_username="testuser",
            discord_discriminator=None,
            discord_avatar=None,
            discord_access_token="token",
            discord_refresh_token="refresh",
            token_expires_at=now,
            manageable_guild_ids=[],
            jwt_token_hash="hash",
            created_at=now,
            last_activity=now,
            expires_at=now,
            ip_address=None,
            user_agent=None,
        )
        assert session.ip_address is None
        assert session.user_agent is None


class TestPydanticModels:
    """Tests for Pydantic API schemas."""

    def test_auth_login_response(self):
        """AuthLoginResponse validates correctly."""
        response = AuthLoginResponse(redirect_url="https://discord.com/oauth2/authorize")
        assert response.redirect_url.startswith("https://")

    def test_auth_callback_request(self):
        """AuthCallbackRequest validates correctly."""
        request = AuthCallbackRequest(code="abc123")
        assert request.code == "abc123"

    def test_user_response(self):
        """UserResponse validates correctly."""
        response = UserResponse(
            id="123",
            username="testuser",
            avatar_url="https://cdn.discordapp.com/avatars/123/abc.png"
        )
        assert response.id == "123"
        assert response.avatar_url is not None

    def test_user_response_no_avatar(self):
        """UserResponse allows null avatar."""
        response = UserResponse(
            id="123",
            username="testuser",
            avatar_url=None
        )
        assert response.avatar_url is None

    def test_guild_brief_response(self):
        """GuildBriefResponse validates correctly."""
        response = GuildBriefResponse(
            id="987",
            name="Test Server",
            icon_url="https://cdn.discordapp.com/icons/987/def.png",
            role=GuildRole.ADMIN
        )
        assert response.role == GuildRole.ADMIN

    def test_auth_callback_response(self):
        """AuthCallbackResponse validates correctly."""
        response = AuthCallbackResponse(
            token="jwt.token.here",
            user=UserResponse(id="123", username="test", avatar_url=None),
            guilds=[
                GuildBriefResponse(
                    id="987",
                    name="Server",
                    icon_url=None,
                    role=GuildRole.MEMBER
                )
            ]
        )
        assert response.token == "jwt.token.here"
        assert len(response.guilds) == 1

    def test_auth_refresh_response(self):
        """AuthRefreshResponse validates correctly."""
        response = AuthRefreshResponse(token="new.jwt.token")
        assert response.token == "new.jwt.token"
        assert response.guilds is None

    def test_auth_refresh_response_with_guilds(self):
        """AuthRefreshResponse with guilds."""
        response = AuthRefreshResponse(
            token="new.jwt.token",
            guilds=["guild1", "guild2"]
        )
        assert len(response.guilds) == 2

    def test_guild_list_item(self):
        """GuildListItem validates correctly."""
        item = GuildListItem(
            id="987",
            name="Test Server",
            icon_url="https://cdn.discordapp.com/icons/987/abc.png",
            member_count=150,
            summary_count=42,
            last_summary_at=None,
            config_status=ConfigStatus.CONFIGURED,
        )
        assert item.id == "987"
        assert item.name == "Test Server"
        assert item.member_count == 150
        assert item.config_status == ConfigStatus.CONFIGURED
