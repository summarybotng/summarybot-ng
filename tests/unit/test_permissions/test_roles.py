"""
Unit tests for permissions/roles.py.

Tests RoleHierarchy, RolePermissionMapping, and RoleManager.
"""

import pytest
from unittest.mock import MagicMock, PropertyMock
from datetime import datetime

from src.permissions.roles import (
    RoleHierarchy,
    RolePermissionMapping,
    RoleManager
)
from src.models.user import PermissionLevel, UserPermissions


class TestRoleHierarchy:
    """Tests for RoleHierarchy enum."""

    def test_hierarchy_values_ordering(self):
        """Hierarchy values should increase from NONE to OWNER."""
        assert RoleHierarchy.NONE.value < RoleHierarchy.MEMBER.value
        assert RoleHierarchy.MEMBER.value < RoleHierarchy.MODERATOR.value
        assert RoleHierarchy.MODERATOR.value < RoleHierarchy.ADMIN.value
        assert RoleHierarchy.ADMIN.value < RoleHierarchy.OWNER.value

    def test_hierarchy_comparison(self):
        """Can compare hierarchy levels by value."""
        assert RoleHierarchy.OWNER.value > RoleHierarchy.ADMIN.value
        assert RoleHierarchy.NONE.value == 0
        assert RoleHierarchy.OWNER.value == 4


class TestRolePermissionMapping:
    """Tests for RolePermissionMapping dataclass."""

    def test_create_basic_mapping(self):
        """Create mapping with required fields."""
        mapping = RolePermissionMapping(
            role_id="123456",
            role_name="Moderator",
            permission_level=PermissionLevel.ADMIN,
            hierarchy_level=RoleHierarchy.MODERATOR
        )

        assert mapping.role_id == "123456"
        assert mapping.role_name == "Moderator"
        assert mapping.permission_level == PermissionLevel.ADMIN
        assert mapping.hierarchy_level == RoleHierarchy.MODERATOR
        assert mapping.allowed_commands == set()
        assert mapping.allowed_channels == set()

    def test_create_mapping_with_commands(self):
        """Create mapping with allowed commands."""
        mapping = RolePermissionMapping(
            role_id="123456",
            role_name="Helper",
            permission_level=PermissionLevel.SUMMARIZE,
            hierarchy_level=RoleHierarchy.MEMBER,
            allowed_commands={"summarize", "quick_summary"}
        )

        assert "summarize" in mapping.allowed_commands
        assert "quick_summary" in mapping.allowed_commands
        assert "config" not in mapping.allowed_commands

    def test_create_mapping_with_channels(self):
        """Create mapping with allowed channels."""
        mapping = RolePermissionMapping(
            role_id="123456",
            role_name="Channel Helper",
            permission_level=PermissionLevel.SUMMARIZE,
            hierarchy_level=RoleHierarchy.MEMBER,
            allowed_channels={"channel1", "channel2"}
        )

        assert "channel1" in mapping.allowed_channels
        assert "channel2" in mapping.allowed_channels

    def test_to_dict_serialization(self):
        """to_dict should serialize all fields correctly."""
        mapping = RolePermissionMapping(
            role_id="123",
            role_name="Test Role",
            permission_level=PermissionLevel.ADMIN,
            hierarchy_level=RoleHierarchy.ADMIN,
            allowed_commands={"config"},
            allowed_channels={"channel1"}
        )

        result = mapping.to_dict()

        assert result["role_id"] == "123"
        assert result["role_name"] == "Test Role"
        assert result["permission_level"] == "admin"
        assert result["hierarchy_level"] == 3
        assert "config" in result["allowed_commands"]
        assert "channel1" in result["allowed_channels"]


class TestRoleManager:
    """Tests for RoleManager class."""

    @pytest.fixture
    def role_manager(self):
        """Create a fresh RoleManager instance."""
        return RoleManager()

    @pytest.fixture
    def mock_member(self):
        """Create a mock Discord member."""
        member = MagicMock()
        member.id = 111111111
        member.guild.owner_id = 999999999
        member.guild_permissions.administrator = False

        # Create mock roles
        role1 = MagicMock()
        role1.id = 123456
        role2 = MagicMock()
        role2.id = 789012
        member.roles = [role1, role2]

        return member

    def test_register_role_mapping(self, role_manager):
        """Can register a role mapping."""
        role_manager.register_role_mapping(
            role_id="123456",
            role_name="Moderator",
            permission_level=PermissionLevel.ADMIN,
            hierarchy_level=RoleHierarchy.MODERATOR
        )

        mapping = role_manager.get_role_mapping("123456")
        assert mapping is not None
        assert mapping.role_name == "Moderator"
        assert mapping.permission_level == PermissionLevel.ADMIN

    def test_get_nonexistent_role_mapping(self, role_manager):
        """Getting nonexistent role returns None."""
        mapping = role_manager.get_role_mapping("nonexistent")
        assert mapping is None

    def test_resolve_member_permissions_server_owner(self, role_manager, mock_member):
        """Server owner gets OWNER level permissions."""
        mock_member.guild.owner_id = mock_member.id  # Make member the owner

        permissions = role_manager.resolve_member_permissions(
            member=mock_member,
            guild_id="guild123",
            allowed_roles=[],
            admin_roles=[]
        )

        assert permissions.level == PermissionLevel.OWNER
        assert permissions.can_schedule_summaries is True
        assert permissions.can_use_webhooks is True
        assert permissions.can_manage_config is True

    def test_resolve_member_permissions_administrator(self, role_manager, mock_member):
        """Discord administrator gets ADMIN level permissions."""
        mock_member.guild_permissions.administrator = True

        permissions = role_manager.resolve_member_permissions(
            member=mock_member,
            guild_id="guild123",
            allowed_roles=[],
            admin_roles=[]
        )

        assert permissions.level == PermissionLevel.ADMIN
        assert permissions.can_schedule_summaries is True

    def test_resolve_member_permissions_admin_role(self, role_manager, mock_member):
        """Member with admin role gets ADMIN level."""
        permissions = role_manager.resolve_member_permissions(
            member=mock_member,
            guild_id="guild123",
            allowed_roles=[],
            admin_roles=["123456"]  # Matches one of member's roles
        )

        assert permissions.level == PermissionLevel.ADMIN

    def test_resolve_member_permissions_allowed_role(self, role_manager, mock_member):
        """Member with allowed role gets SUMMARIZE level."""
        permissions = role_manager.resolve_member_permissions(
            member=mock_member,
            guild_id="guild123",
            allowed_roles=["123456"],  # Matches one of member's roles
            admin_roles=[]
        )

        assert permissions.level == PermissionLevel.SUMMARIZE

    def test_resolve_member_permissions_no_roles(self, role_manager, mock_member):
        """Member without matching roles gets NONE level."""
        permissions = role_manager.resolve_member_permissions(
            member=mock_member,
            guild_id="guild123",
            allowed_roles=["other_role"],
            admin_roles=["another_role"]
        )

        assert permissions.level == PermissionLevel.NONE

    def test_resolve_member_permissions_with_custom_mapping(self, role_manager, mock_member):
        """Custom role mapping is applied to member."""
        # Register a custom mapping for one of the member's roles
        role_manager.register_role_mapping(
            role_id="123456",
            role_name="Custom Role",
            permission_level=PermissionLevel.ADMIN,
            hierarchy_level=RoleHierarchy.MODERATOR
        )

        permissions = role_manager.resolve_member_permissions(
            member=mock_member,
            guild_id="guild123",
            allowed_roles=[],
            admin_roles=[]
        )

        assert permissions.level == PermissionLevel.ADMIN

    def test_get_required_level_for_command(self, role_manager):
        """Commands have correct required permission levels."""
        assert role_manager.get_required_level_for_command("summarize") == PermissionLevel.SUMMARIZE
        assert role_manager.get_required_level_for_command("quick_summary") == PermissionLevel.SUMMARIZE
        assert role_manager.get_required_level_for_command("schedule") == PermissionLevel.ADMIN
        assert role_manager.get_required_level_for_command("config") == PermissionLevel.ADMIN
        assert role_manager.get_required_level_for_command("permissions") == PermissionLevel.OWNER
        assert role_manager.get_required_level_for_command("view") == PermissionLevel.READ
        # Unknown command defaults to ADMIN
        assert role_manager.get_required_level_for_command("unknown") == PermissionLevel.ADMIN

    def test_can_execute_command_owner(self, role_manager):
        """Owner can execute all commands."""
        perms = UserPermissions(
            user_id="123",
            guild_id="guild123",
            level=PermissionLevel.OWNER
        )

        assert role_manager.can_execute_command(perms, "summarize") is True
        assert role_manager.can_execute_command(perms, "schedule") is True
        assert role_manager.can_execute_command(perms, "permissions") is True

    def test_can_execute_command_admin(self, role_manager):
        """Admin can execute most commands but not permissions."""
        perms = UserPermissions(
            user_id="123",
            guild_id="guild123",
            level=PermissionLevel.ADMIN
        )

        assert role_manager.can_execute_command(perms, "summarize") is True
        assert role_manager.can_execute_command(perms, "schedule") is True
        assert role_manager.can_execute_command(perms, "permissions") is False

    def test_can_execute_command_summarize_level(self, role_manager):
        """SUMMARIZE level can only execute summarize commands."""
        perms = UserPermissions(
            user_id="123",
            guild_id="guild123",
            level=PermissionLevel.SUMMARIZE
        )

        assert role_manager.can_execute_command(perms, "summarize") is True
        assert role_manager.can_execute_command(perms, "view") is True
        assert role_manager.can_execute_command(perms, "schedule") is False
        assert role_manager.can_execute_command(perms, "config") is False

    def test_can_execute_command_none_level(self, role_manager):
        """NONE level cannot execute any commands."""
        perms = UserPermissions(
            user_id="123",
            guild_id="guild123",
            level=PermissionLevel.NONE
        )

        assert role_manager.can_execute_command(perms, "summarize") is False
        assert role_manager.can_execute_command(perms, "view") is False

    def test_list_available_commands_owner(self, role_manager):
        """Owner has access to all commands."""
        perms = UserPermissions(
            user_id="123",
            guild_id="guild123",
            level=PermissionLevel.OWNER
        )

        commands = role_manager.list_available_commands(perms)

        assert "permissions" in commands
        assert "config" in commands
        assert "summarize" in commands
        assert "view" in commands

    def test_list_available_commands_summarize_level(self, role_manager):
        """SUMMARIZE level has limited commands."""
        perms = UserPermissions(
            user_id="123",
            guild_id="guild123",
            level=PermissionLevel.SUMMARIZE
        )

        commands = role_manager.list_available_commands(perms)

        assert "summarize" in commands
        assert "quick_summary" in commands
        assert "view" in commands
        assert "permissions" not in commands
        assert "config" not in commands

    def test_check_role_hierarchy_higher(self, role_manager):
        """Actor with higher role hierarchy returns True."""
        role_manager.register_role_mapping(
            role_id="admin_role",
            role_name="Admin",
            permission_level=PermissionLevel.ADMIN,
            hierarchy_level=RoleHierarchy.ADMIN
        )
        role_manager.register_role_mapping(
            role_id="member_role",
            role_name="Member",
            permission_level=PermissionLevel.SUMMARIZE,
            hierarchy_level=RoleHierarchy.MEMBER
        )

        actor_role = MagicMock()
        actor_role.id = "admin_role"
        target_role = MagicMock()
        target_role.id = "member_role"

        result = role_manager.check_role_hierarchy([actor_role], [target_role])
        assert result is True

    def test_check_role_hierarchy_lower(self, role_manager):
        """Actor with lower role hierarchy returns False."""
        role_manager.register_role_mapping(
            role_id="admin_role",
            role_name="Admin",
            permission_level=PermissionLevel.ADMIN,
            hierarchy_level=RoleHierarchy.ADMIN
        )
        role_manager.register_role_mapping(
            role_id="member_role",
            role_name="Member",
            permission_level=PermissionLevel.SUMMARIZE,
            hierarchy_level=RoleHierarchy.MEMBER
        )

        actor_role = MagicMock()
        actor_role.id = "member_role"
        target_role = MagicMock()
        target_role.id = "admin_role"

        result = role_manager.check_role_hierarchy([actor_role], [target_role])
        assert result is False
