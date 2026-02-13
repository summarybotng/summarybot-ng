"""
Stored summary model for ADR-005: Summary Delivery Destinations.

This module defines the StoredSummary model for summaries delivered to the
dashboard destination, enabling viewing, management, and push-to-channel actions.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any

from .base import BaseModel, generate_id
from .summary import SummaryResult


@dataclass
class PushDelivery:
    """Record of a summary push to a Discord channel."""
    channel_id: str
    pushed_at: datetime
    message_id: Optional[str] = None  # Discord message ID if successful
    success: bool = True
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "channel_id": self.channel_id,
            "pushed_at": self.pushed_at.isoformat(),
            "message_id": self.message_id,
            "success": self.success,
            "error": self.error
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PushDelivery':
        """Create from dictionary."""
        return cls(
            channel_id=data["channel_id"],
            pushed_at=datetime.fromisoformat(data["pushed_at"]),
            message_id=data.get("message_id"),
            success=data.get("success", True),
            error=data.get("error")
        )


@dataclass
class StoredSummary(BaseModel):
    """A summary stored in the dashboard for viewing and optional channel push.

    ADR-005: Summary Delivery Destinations

    StoredSummary persists summaries delivered to the DASHBOARD destination type,
    enabling:
    - Viewing summaries in the dashboard UI
    - Searching and filtering past summaries
    - Push-to-channel action for manual delivery
    - Archiving and organizing with tags
    """
    id: str = field(default_factory=generate_id)
    guild_id: str = ""
    source_channel_ids: List[str] = field(default_factory=list)
    schedule_id: Optional[str] = None  # If from a scheduled task

    # Summary content - stores the full SummaryResult
    summary_result: Optional[SummaryResult] = None

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    viewed_at: Optional[datetime] = None  # First view timestamp
    pushed_at: Optional[datetime] = None  # Last push timestamp

    # Delivery tracking
    push_deliveries: List[PushDelivery] = field(default_factory=list)

    # Metadata
    title: str = ""
    is_pinned: bool = False
    is_archived: bool = False
    tags: List[str] = field(default_factory=list)

    def get_pushed_channel_ids(self) -> List[str]:
        """Get list of channel IDs this summary was pushed to."""
        return [d.channel_id for d in self.push_deliveries if d.success]

    def add_push_delivery(
        self,
        channel_id: str,
        message_id: Optional[str] = None,
        success: bool = True,
        error: Optional[str] = None
    ) -> None:
        """Record a push delivery to a channel."""
        delivery = PushDelivery(
            channel_id=channel_id,
            pushed_at=datetime.utcnow(),
            message_id=message_id,
            success=success,
            error=error
        )
        self.push_deliveries.append(delivery)
        if success:
            self.pushed_at = delivery.pushed_at

    def mark_viewed(self) -> None:
        """Mark the summary as viewed (only sets first view time)."""
        if self.viewed_at is None:
            self.viewed_at = datetime.utcnow()

    def pin(self) -> None:
        """Pin the summary."""
        self.is_pinned = True

    def unpin(self) -> None:
        """Unpin the summary."""
        self.is_pinned = False

    def archive(self) -> None:
        """Archive the summary."""
        self.is_archived = True

    def unarchive(self) -> None:
        """Unarchive the summary."""
        self.is_archived = False

    def add_tag(self, tag: str) -> None:
        """Add a tag to the summary."""
        if tag not in self.tags:
            self.tags.append(tag)

    def remove_tag(self, tag: str) -> None:
        """Remove a tag from the summary."""
        if tag in self.tags:
            self.tags.remove(tag)

    def get_key_points_count(self) -> int:
        """Get count of key points in the summary."""
        if self.summary_result:
            # Check both plain key_points and referenced_key_points (ADR-004)
            if hasattr(self.summary_result, 'referenced_key_points') and self.summary_result.referenced_key_points:
                return len(self.summary_result.referenced_key_points)
            return len(self.summary_result.key_points)
        return 0

    def get_action_items_count(self) -> int:
        """Get count of action items in the summary."""
        if self.summary_result:
            if hasattr(self.summary_result, 'referenced_action_items') and self.summary_result.referenced_action_items:
                return len(self.summary_result.referenced_action_items)
            return len(self.summary_result.action_items)
        return 0

    def get_message_count(self) -> int:
        """Get count of messages summarized."""
        if self.summary_result:
            return self.summary_result.message_count
        return 0

    def has_references(self) -> bool:
        """Check if summary has grounded references (ADR-004)."""
        if self.summary_result and hasattr(self.summary_result, 'has_references'):
            return self.summary_result.has_references()
        return False

    def to_list_item_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for list display (minimal data)."""
        return {
            "id": self.id,
            "guild_id": self.guild_id,
            "title": self.title,
            "source_channel_ids": self.source_channel_ids,
            "schedule_id": self.schedule_id,
            "created_at": self.created_at.isoformat(),
            "viewed_at": self.viewed_at.isoformat() if self.viewed_at else None,
            "pushed_at": self.pushed_at.isoformat() if self.pushed_at else None,
            "pushed_to_channels": self.get_pushed_channel_ids(),
            "is_pinned": self.is_pinned,
            "is_archived": self.is_archived,
            "tags": self.tags,
            "key_points_count": self.get_key_points_count(),
            "action_items_count": self.get_action_items_count(),
            "message_count": self.get_message_count(),
            "has_references": self.has_references()
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "guild_id": self.guild_id,
            "source_channel_ids": self.source_channel_ids,
            "schedule_id": self.schedule_id,
            "summary_result": self.summary_result.to_dict() if self.summary_result else None,
            "created_at": self.created_at.isoformat(),
            "viewed_at": self.viewed_at.isoformat() if self.viewed_at else None,
            "pushed_at": self.pushed_at.isoformat() if self.pushed_at else None,
            "push_deliveries": [d.to_dict() for d in self.push_deliveries],
            "title": self.title,
            "is_pinned": self.is_pinned,
            "is_archived": self.is_archived,
            "tags": self.tags
        }
