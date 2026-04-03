"""
Guild Prompt Template model for ADR-034.

Allows guilds to create reusable prompt templates that can be
assigned to scheduled summaries.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any

from .base import BaseModel, generate_id
from src.utils.time import utc_now_naive


@dataclass
class GuildPromptTemplate(BaseModel):
    """A reusable prompt template owned by a guild.

    Attributes:
        id: Unique identifier for the template
        guild_id: The guild this template belongs to
        name: Human-readable name (unique within guild)
        description: Optional help text explaining the template's purpose
        content: The actual prompt text
        based_on_default: Which system default this was seeded from, if any
            (e.g., "developer/detailed", "discussion")
        created_by: User ID who created the template
        created_at: When the template was created
        updated_at: When the template was last modified
    """
    id: str = field(default_factory=generate_id)
    guild_id: str = ""
    name: str = ""
    description: Optional[str] = None
    content: str = ""
    based_on_default: Optional[str] = None
    created_by: str = ""
    created_at: datetime = field(default_factory=utc_now_naive)
    updated_at: datetime = field(default_factory=utc_now_naive)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "guild_id": self.guild_id,
            "name": self.name,
            "description": self.description,
            "content": self.content,
            "based_on_default": self.based_on_default,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GuildPromptTemplate":
        """Create from dictionary."""
        created_at = data.get("created_at")
        updated_at = data.get("updated_at")

        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        return cls(
            id=data.get("id", generate_id()),
            guild_id=data.get("guild_id", ""),
            name=data.get("name", ""),
            description=data.get("description"),
            content=data.get("content", ""),
            based_on_default=data.get("based_on_default"),
            created_by=data.get("created_by", ""),
            created_at=created_at or utc_now_naive(),
            updated_at=updated_at or utc_now_naive(),
        )

    def update(self, **kwargs) -> "GuildPromptTemplate":
        """Return a new template with updated fields."""
        data = self.to_dict()
        data.update(kwargs)
        data["updated_at"] = utc_now_naive()
        return GuildPromptTemplate.from_dict(data)
