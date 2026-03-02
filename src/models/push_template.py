"""
Push template models for Discord summary delivery (ADR-014).

These models define customizable templates for pushing summaries to Discord,
including thread creation, section configuration, and formatting options.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum

from .base import BaseModel


class SectionType(str, Enum):
    """Available section types for push templates."""
    KEY_POINTS = "key_points"
    ACTION_ITEMS = "action_items"
    DECISIONS = "decisions"
    TECHNICAL_TERMS = "technical_terms"
    PARTICIPANTS = "participants"
    SOURCES = "sources"


class ReferenceStyle(str, Enum):
    """Reference formatting styles."""
    NUMBERED = "numbered"  # [1][2]
    INLINE = "inline"  # (Bob, 9:15)
    NONE = "none"  # No references shown


@dataclass
class SectionConfig(BaseModel):
    """Configuration for a single section in the push output.

    ADR-014: Template-based push sends ALL content without truncation.
    Content is paginated across multiple messages if needed.
    """
    type: str  # key_points, action_items, decisions, technical_terms, participants, sources
    enabled: bool = True
    max_items: int = 100  # High limit - pagination handles overflow
    title_override: Optional[str] = None  # Custom section title
    combine_with_previous: bool = False  # Combine into same message as previous section

    # Section-specific emoji (defaults provided)
    SECTION_EMOJIS = {
        "key_points": "🎯",
        "action_items": "📝",
        "decisions": "✅",
        "technical_terms": "🔧",
        "participants": "👥",
        "sources": "📚",
    }

    SECTION_TITLES = {
        "key_points": "Key Points",
        "action_items": "Action Items",
        "decisions": "Decisions",
        "technical_terms": "Technical Terms",
        "participants": "Participants",
        "sources": "Sources",
    }

    def get_title(self) -> str:
        """Get the display title for this section."""
        if self.title_override:
            return self.title_override
        emoji = self.SECTION_EMOJIS.get(self.type, "📌")
        title = self.SECTION_TITLES.get(self.type, self.type.replace("_", " ").title())
        return f"{emoji} **{title}**"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.type,
            "enabled": self.enabled,
            "max_items": self.max_items,
            "title_override": self.title_override,
            "combine_with_previous": self.combine_with_previous,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SectionConfig':
        """Create from dictionary."""
        return cls(
            type=data.get("type", "key_points"),
            enabled=data.get("enabled", True),
            max_items=data.get("max_items", 100),  # ADR-014: No truncation
            title_override=data.get("title_override"),
            combine_with_previous=data.get("combine_with_previous", False),
        )


@dataclass
class PushTemplate(BaseModel):
    """Configuration for how summaries are pushed to Discord.

    ADR-014: Discord Push Templates with Thread Support.
    """
    # Schema version for forward compatibility
    schema_version: int = 1

    # Thread settings
    use_thread: bool = True
    thread_name_format: str = "Summary: {scope} ({date_range})"
    thread_auto_archive_minutes: int = 1440  # 24 hours (Discord options: 60, 1440, 4320, 10080)

    # Message 1: Header + Summary
    header_format: str = "📋 **Summary: {scope}**"
    show_date_range: bool = True
    show_stats: bool = True  # message count, participants
    show_summary_text: bool = True

    # Sections (order determines message order)
    # ADR-014: All content sent without truncation - pagination handles overflow
    sections: List[SectionConfig] = field(default_factory=lambda: [
        SectionConfig(type="key_points", enabled=True, max_items=100),
        SectionConfig(type="action_items", enabled=True, max_items=100),
        SectionConfig(type="decisions", enabled=True, max_items=100),
        SectionConfig(type="technical_terms", enabled=False, max_items=100),
        SectionConfig(type="participants", enabled=False, max_items=100),
        SectionConfig(type="sources", enabled=True, max_items=100),
    ])

    # Reference formatting
    include_references: bool = True
    include_jump_links: bool = True
    reference_style: str = "numbered"  # "numbered" [1][2], "inline" (Bob, 9:15), "none"

    # Embed settings
    use_embeds: bool = True
    embed_color: int = 0x4A90E2  # Blue

    def get_enabled_sections(self) -> List[SectionConfig]:
        """Get only enabled sections in order."""
        return [s for s in self.sections if s.enabled]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "schema_version": self.schema_version,
            "use_thread": self.use_thread,
            "thread_name_format": self.thread_name_format,
            "thread_auto_archive_minutes": self.thread_auto_archive_minutes,
            "header_format": self.header_format,
            "show_date_range": self.show_date_range,
            "show_stats": self.show_stats,
            "show_summary_text": self.show_summary_text,
            "sections": [s.to_dict() for s in self.sections],
            "include_references": self.include_references,
            "include_jump_links": self.include_jump_links,
            "reference_style": self.reference_style,
            "use_embeds": self.use_embeds,
            "embed_color": self.embed_color,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PushTemplate':
        """Create from dictionary with defaults for missing fields."""
        sections = data.get("sections", [])
        if sections:
            sections = [SectionConfig.from_dict(s) for s in sections]
        else:
            sections = DEFAULT_SECTIONS.copy()

        return cls(
            schema_version=data.get("schema_version", 1),
            use_thread=data.get("use_thread", True),
            thread_name_format=data.get("thread_name_format", "Summary: {scope} ({date_range})"),
            thread_auto_archive_minutes=data.get("thread_auto_archive_minutes", 1440),
            header_format=data.get("header_format", "📋 **Summary: {scope}**"),
            show_date_range=data.get("show_date_range", True),
            show_stats=data.get("show_stats", True),
            show_summary_text=data.get("show_summary_text", True),
            sections=sections,
            include_references=data.get("include_references", True),
            include_jump_links=data.get("include_jump_links", True),
            reference_style=data.get("reference_style", "numbered"),
            use_embeds=data.get("use_embeds", True),
            embed_color=data.get("embed_color", 0x4A90E2),
        )


# Default sections configuration
# ADR-014: All content sent - pagination handles message limits
DEFAULT_SECTIONS = [
    SectionConfig(type="key_points", enabled=True, max_items=100),
    SectionConfig(type="action_items", enabled=True, max_items=100),
    SectionConfig(type="decisions", enabled=True, max_items=100),
    SectionConfig(type="sources", enabled=True, max_items=100),
]

# Default push template
DEFAULT_PUSH_TEMPLATE = PushTemplate(
    schema_version=1,
    use_thread=True,
    thread_name_format="Summary: {scope} ({date_range})",
    thread_auto_archive_minutes=1440,
    header_format="📋 **Summary: {scope}**",
    show_date_range=True,
    show_stats=True,
    show_summary_text=True,
    sections=DEFAULT_SECTIONS.copy(),
    include_references=True,
    include_jump_links=True,
    reference_style="numbered",
    use_embeds=True,
    embed_color=0x4A90E2,
)


@dataclass
class GuildPushTemplate(BaseModel):
    """Guild-specific push template override.

    Stored in guild_push_templates table.
    """
    guild_id: str
    template: PushTemplate
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None  # User ID who configured

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "guild_id": self.guild_id,
            "template": self.template.to_dict(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GuildPushTemplate':
        """Create from dictionary."""
        return cls(
            guild_id=data["guild_id"],
            template=PushTemplate.from_dict(data["template"]),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.utcnow(),
            created_by=data.get("created_by"),
        )


def format_scope(
    channel_names: List[str],
    category_name: Optional[str] = None,
    is_server_wide: bool = False,
) -> str:
    """Format the {scope} placeholder value.

    Args:
        channel_names: List of channel names (without #)
        category_name: Category name if category-scoped
        is_server_wide: Whether this is a server-wide summary

    Returns:
        Formatted scope string
    """
    if is_server_wide:
        return "🌐 Server-wide"

    if category_name:
        return f"📁 {category_name}"

    if not channel_names:
        return "Unknown"

    def format_name(name: str) -> str:
        """Format a single channel/source name with appropriate prefix."""
        # ADR-026: Don't add # prefix for platform-prefixed names (WhatsApp:, Slack:, etc.)
        if ":" in name and name.split(":")[0].lower() in ("whatsapp", "slack", "discord", "telegram"):
            return name
        return f"#{name}"

    if len(channel_names) == 1:
        return format_name(channel_names[0])

    if len(channel_names) <= 3:
        return ", ".join(format_name(name) for name in channel_names)

    first_three = ", ".join(format_name(name) for name in channel_names[:3])
    return f"{first_three} +{len(channel_names) - 3} more"


def format_date_range(start_time: datetime, end_time: datetime) -> str:
    """Format the {date_range} placeholder value.

    Args:
        start_time: Start of the summary period
        end_time: End of the summary period

    Returns:
        Formatted date range string
    """
    # Same day
    if start_time.date() == end_time.date():
        return start_time.strftime("%b %d")

    # Same month
    if start_time.year == end_time.year and start_time.month == end_time.month:
        return f"{start_time.strftime('%b %d')}-{end_time.strftime('%d')}"

    # Same year, different month
    if start_time.year == end_time.year:
        return f"{start_time.strftime('%b %d')} - {end_time.strftime('%b %d')}"

    # Different year
    return f"{start_time.strftime('%b %d, %Y')} - {end_time.strftime('%b %d, %Y')}"


def validate_template(template: PushTemplate) -> List[str]:
    """Validate a push template configuration.

    Args:
        template: Template to validate

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Validate thread settings
    valid_archive_options = [60, 1440, 4320, 10080]
    if template.thread_auto_archive_minutes not in valid_archive_options:
        errors.append(
            f"thread_auto_archive_minutes must be one of {valid_archive_options}, "
            f"got {template.thread_auto_archive_minutes}"
        )

    # Validate sections
    valid_section_types = {"key_points", "action_items", "decisions", "technical_terms", "participants", "sources"}
    for section in template.sections:
        if section.type not in valid_section_types:
            errors.append(f"Invalid section type: {section.type}")
        if section.max_items < 1 or section.max_items > 50:
            errors.append(f"Section {section.type} max_items must be 1-50, got {section.max_items}")

    # Validate reference style
    valid_styles = {"numbered", "inline", "none"}
    if template.reference_style not in valid_styles:
        errors.append(f"Invalid reference_style: {template.reference_style}")

    # Validate embed color
    if template.embed_color < 0 or template.embed_color > 0xFFFFFF:
        errors.append(f"embed_color must be 0x000000-0xFFFFFF, got {template.embed_color}")

    return errors
