"""
User and permission models.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum

from .base import BaseModel
from src.utils.time import utc_now_naive


class PermissionLevel(Enum):
    """Permission levels for users."""
    NONE = "none"
    READ = "read"
    SUMMARIZE = "summarize"
    ADMIN = "admin"
    OWNER = "owner"


@dataclass
class UserPermissions(BaseModel):
    """User permissions for a specific guild."""
    user_id: str
    guild_id: str
    level: PermissionLevel = PermissionLevel.NONE
    allowed_channels: List[str] = field(default_factory=list)
    denied_channels: List[str] = field(default_factory=list)
    can_schedule_summaries: bool = False
    can_use_webhooks: bool = False
    can_manage_config: bool = False
    granted_by: Optional[str] = None  # User ID who granted permissions
    granted_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    
    def has_channel_access(self, channel_id: str) -> bool:
        """Check if user has access to a specific channel."""
        if self.level in [PermissionLevel.ADMIN, PermissionLevel.OWNER]:
            return True
        
        if channel_id in self.denied_channels:
            return False
        
        if self.allowed_channels:
            return channel_id in self.allowed_channels
        
        return self.level != PermissionLevel.NONE
    
    def can_perform_action(self, action: str) -> bool:
        """Check if user can perform a specific action."""
        if self.level == PermissionLevel.OWNER:
            return True
        
        action_requirements = {
            "read_summaries": PermissionLevel.READ,
            "create_summaries": PermissionLevel.SUMMARIZE,
            "schedule_summaries": PermissionLevel.ADMIN,
            "manage_config": PermissionLevel.ADMIN,
            "use_webhooks": PermissionLevel.ADMIN,
            "manage_permissions": PermissionLevel.OWNER
        }
        
        required_level = action_requirements.get(action, PermissionLevel.OWNER)
        level_hierarchy = {
            PermissionLevel.NONE: 0,
            PermissionLevel.READ: 1,
            PermissionLevel.SUMMARIZE: 2,
            PermissionLevel.ADMIN: 3,
            PermissionLevel.OWNER: 4
        }
        
        return level_hierarchy[self.level] >= level_hierarchy[required_level]
    
    def is_expired(self) -> bool:
        """Check if permissions are expired."""
        if not self.expires_at:
            return False
        return utc_now_naive() > self.expires_at


@dataclass
class User(BaseModel):
    """User information across guilds."""
    id: str
    username: str
    display_name: str
    avatar_url: Optional[str] = None
    is_bot: bool = False
    guild_permissions: Dict[str, UserPermissions] = field(default_factory=dict)
    first_seen: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    total_summaries_requested: int = 0
    preferred_summary_length: str = "detailed"
    
    def get_guild_permissions(self, guild_id: str) -> UserPermissions:
        """Get permissions for a specific guild."""
        if guild_id not in self.guild_permissions:
            self.guild_permissions[guild_id] = UserPermissions(
                user_id=self.id,
                guild_id=guild_id
            )
        return self.guild_permissions[guild_id]
    
    def has_permission_in_guild(self, guild_id: str, permission: str) -> bool:
        """Check if user has a specific permission in a guild."""
        guild_perms = self.get_guild_permissions(guild_id)
        return guild_perms.can_perform_action(permission)
    
    def can_access_channel(self, guild_id: str, channel_id: str) -> bool:
        """Check if user can access a specific channel."""
        guild_perms = self.get_guild_permissions(guild_id)
        return guild_perms.has_channel_access(channel_id)
    
    def update_last_seen(self) -> None:
        """Update last seen timestamp."""
        self.last_seen = utc_now_naive()
    
    def increment_summary_count(self) -> None:
        """Increment the count of summaries requested."""
        self.total_summaries_requested += 1
        self.update_last_seen()
    
    def to_profile_dict(self) -> Dict[str, Any]:
        """Convert to profile dictionary for display."""
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "avatar_url": self.avatar_url,
            "is_bot": self.is_bot,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "total_summaries": self.total_summaries_requested,
            "preferred_length": self.preferred_summary_length,
            "guild_count": len(self.guild_permissions)
        }