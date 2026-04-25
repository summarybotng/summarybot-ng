"""
Slack workspace integration models (ADR-043).

Defines dataclasses for Slack workspaces, channels, and users.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class SlackScopeTier(str, Enum):
    """OAuth scope tiers per ADR-043 Section 3.2."""
    PUBLIC = "public"  # channels:history, channels:read, users:read, team:read
    FULL = "full"  # Adds groups:*, im:*, mpim:*, files:read


class SlackChannelType(str, Enum):
    """Slack channel types."""
    PUBLIC = "public_channel"
    PRIVATE = "private_channel"
    DM = "im"
    MPIM = "mpim"  # Multi-person instant message (group DM)


@dataclass
class SlackWorkspace:
    """Represents a connected Slack workspace (ADR-043)."""
    workspace_id: str  # Slack team ID (T...)
    workspace_name: str
    workspace_domain: Optional[str] = None
    encrypted_bot_token: str = ""  # Fernet-encrypted xoxb-* token
    bot_user_id: str = ""  # Bot's Slack user ID (U...)
    installed_by_discord_user: str = ""  # Discord user ID who installed
    installed_at: datetime = field(default_factory=datetime.utcnow)
    scopes: str = ""  # Comma-separated granted scopes
    scope_tier: SlackScopeTier = SlackScopeTier.PUBLIC
    is_enterprise: bool = False
    enterprise_id: Optional[str] = None  # Grid enterprise ID (E...)
    enabled: bool = True
    last_sync_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Guild linking (ADR-046)
    linked_guild_id: Optional[str] = None
    linked_at: Optional[datetime] = None

    def has_scope(self, scope: str) -> bool:
        """Check if workspace has a specific OAuth scope."""
        return scope in self.scopes.split(",")

    def can_access_private(self) -> bool:
        """Check if workspace can access private channels."""
        return self.scope_tier == SlackScopeTier.FULL

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses (excludes sensitive data)."""
        return {
            "workspace_id": self.workspace_id,
            "workspace_name": self.workspace_name,
            "workspace_domain": self.workspace_domain,
            "bot_user_id": self.bot_user_id,
            "installed_by_discord_user": self.installed_by_discord_user,
            "installed_at": self.installed_at.isoformat() if self.installed_at else None,
            "scope_tier": self.scope_tier.value,
            "is_enterprise": self.is_enterprise,
            "enterprise_id": self.enterprise_id,
            "enabled": self.enabled,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "linked_guild_id": self.linked_guild_id,
            "linked_at": self.linked_at.isoformat() if self.linked_at else None,
        }


@dataclass
class SlackChannel:
    """Represents a Slack channel (ADR-043)."""
    channel_id: str  # Slack channel ID (C..., G..., D...)
    workspace_id: str
    channel_name: str
    channel_type: SlackChannelType = SlackChannelType.PUBLIC
    is_shared: bool = False  # Slack Connect shared channel
    is_archived: bool = False
    is_sensitive: bool = False  # ADR-046 sensitivity flag
    auto_summarize: bool = False
    summary_schedule: Optional[str] = None  # Cron expression
    last_message_ts: Optional[str] = None  # Slack timestamp of last message
    created_at: datetime = field(default_factory=datetime.utcnow)
    topic: Optional[str] = None
    purpose: Optional[str] = None
    member_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "channel_id": self.channel_id,
            "workspace_id": self.workspace_id,
            "channel_name": self.channel_name,
            "channel_type": self.channel_type.value,
            "is_shared": self.is_shared,
            "is_archived": self.is_archived,
            "is_sensitive": self.is_sensitive,
            "auto_summarize": self.auto_summarize,
            "summary_schedule": self.summary_schedule,
            "last_message_ts": self.last_message_ts,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "topic": self.topic,
            "purpose": self.purpose,
            "member_count": self.member_count,
        }


@dataclass
class SlackUser:
    """Represents a Slack user (ADR-043)."""
    user_id: str  # Slack user ID (U..., W...)
    workspace_id: str
    display_name: str
    real_name: Optional[str] = None
    email: Optional[str] = None
    is_bot: bool = False
    is_admin: bool = False
    is_owner: bool = False
    avatar_url: Optional[str] = None
    updated_at: datetime = field(default_factory=datetime.utcnow)
    timezone: Optional[str] = None
    status_text: Optional[str] = None
    status_emoji: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "user_id": self.user_id,
            "workspace_id": self.workspace_id,
            "display_name": self.display_name,
            "real_name": self.real_name,
            "is_bot": self.is_bot,
            "is_admin": self.is_admin,
            "is_owner": self.is_owner,
            "avatar_url": self.avatar_url,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "timezone": self.timezone,
        }


@dataclass
class SlackMessage:
    """Represents a Slack message for processing."""
    ts: str  # Slack message timestamp (unique ID)
    channel_id: str
    workspace_id: str
    user_id: str
    text: str
    thread_ts: Optional[str] = None  # Parent thread timestamp
    reply_count: int = 0
    reply_users_count: int = 0
    reactions: List[Dict[str, Any]] = field(default_factory=list)
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    files: List[Dict[str, Any]] = field(default_factory=list)
    is_edited: bool = False
    edited_ts: Optional[str] = None
    subtype: Optional[str] = None  # bot_message, file_share, etc.
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def timestamp(self) -> datetime:
        """Convert Slack ts to datetime."""
        return datetime.fromtimestamp(float(self.ts.split(".")[0]))

    def is_thread_parent(self) -> bool:
        """Check if this message is a thread parent."""
        return self.thread_ts == self.ts or (self.reply_count > 0 and not self.thread_ts)

    def is_thread_reply(self) -> bool:
        """Check if this message is a thread reply."""
        return self.thread_ts is not None and self.thread_ts != self.ts


# OAuth scope constants per ADR-043 Section 3.2
SLACK_SCOPES_PUBLIC = [
    "channels:history",
    "channels:read",
    "channels:join",  # Required for auto-joining public channels
    "users:read",
    "team:read",
    "reactions:read",
]

SLACK_SCOPES_FULL = SLACK_SCOPES_PUBLIC + [
    "groups:history",
    "groups:read",
    "im:history",
    "im:read",
    "mpim:history",
    "mpim:read",
    "files:read",
]
