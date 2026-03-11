"""
Base classes for delivery strategies (CS-008).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol

from ...models.summary import SummaryResult
from ...models.task import Destination


@dataclass
class DeliveryResult:
    """Result of a delivery attempt."""
    destination_type: str
    target: str
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "destination_type": self.destination_type,
            "target": self.target,
            "success": self.success,
        }
        if self.message_id:
            result["message_id"] = self.message_id
        if self.error:
            result["error"] = self.error
        if self.details:
            result["details"] = self.details
        if self.success and not self.error:
            result["message"] = self.details.get("message", "Delivered successfully")
        return result


class DeliveryContext(Protocol):
    """Context needed for delivery - provided by TaskExecutor."""
    guild_id: str
    discord_client: Any
    scheduled_task: Any

    def get_all_channel_ids(self) -> list:
        """Get all channel IDs for this task."""
        ...


class DeliveryStrategy(ABC):
    """Abstract base class for delivery strategies."""

    @property
    @abstractmethod
    def destination_type(self) -> str:
        """Return the destination type this strategy handles."""
        ...

    @abstractmethod
    async def deliver(
        self,
        summary: SummaryResult,
        destination: Destination,
        context: DeliveryContext,
    ) -> DeliveryResult:
        """Deliver a summary to the destination.

        Args:
            summary: Summary result to deliver
            destination: Destination configuration
            context: Delivery context from the task

        Returns:
            Delivery result
        """
        ...
