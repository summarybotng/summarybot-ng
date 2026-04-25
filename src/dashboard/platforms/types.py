"""
Platform abstraction types (ADR-051).

Shared types for platform-agnostic message fetching.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime

from src.models.message import ProcessedMessage


@dataclass
class FetchResult:
    """Result of a message fetching operation."""

    messages: List[ProcessedMessage]
    channel_names: Dict[str, str]  # channel_id -> display name
    user_names: Dict[str, str]     # user_id -> display name
    errors: List[tuple]            # List of (channel_id, error_message)

    @property
    def total_messages(self) -> int:
        return len(self.messages)

    @property
    def successful_channels(self) -> int:
        return len(self.channel_names) - len(self.errors)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0


@dataclass
class PlatformContext:
    """Context for summarization with platform-specific info."""

    platform_name: str       # "Discord", "Slack", "WhatsApp"
    server_name: str         # Guild name or workspace name
    server_id: str           # Guild ID or workspace ID
    primary_channel_name: str
    channel_names: Dict[str, str] = field(default_factory=dict)

    def get_channel_name(self, channel_id: str) -> str:
        """Get channel display name, falling back to ID."""
        return self.channel_names.get(channel_id, channel_id)


@dataclass
class ChannelInfo:
    """Basic channel information."""

    channel_id: str
    name: str
    channel_type: str  # "text", "voice", "category", "public", "private"
    is_accessible: bool = True
    parent_id: Optional[str] = None  # Category ID for Discord


@dataclass
class UserInfo:
    """Basic user information."""

    user_id: str
    display_name: str
    real_name: Optional[str] = None
    is_bot: bool = False
