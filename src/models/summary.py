"""
Summary-related data models.
"""

import os
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum

from .base import BaseModel, generate_id, utc_now
from ..config.constants import DEFAULT_SUMMARIZATION_MODEL, DEFAULT_BRIEF_MODEL, DEFAULT_COMPREHENSIVE_MODEL

# Import reference models (lazy to avoid circular imports)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .reference import ReferencedClaim, SummaryReference

logger = logging.getLogger(__name__)


class SummaryLength(Enum):
    """Summary length options."""
    BRIEF = "brief"
    DETAILED = "detailed"
    COMPREHENSIVE = "comprehensive"


class Priority(Enum):
    """Priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class SummaryWarning(BaseModel):
    """Warning generated during summary creation."""
    code: str  # e.g., "model_fallback", "partial_content", "permission_error"
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionItem(BaseModel):
    """Represents an action item extracted from a summary."""
    description: str
    assignee: Optional[str] = None
    deadline: Optional[datetime] = None
    priority: Priority = Priority.MEDIUM
    source_message_ids: List[str] = field(default_factory=list)
    completed: bool = False
    
    def to_markdown(self) -> str:
        """Convert to markdown format."""
        priority_emoji = {
            Priority.HIGH: "🔴",
            Priority.MEDIUM: "🟡",
            Priority.LOW: "🟢",
            # Also support string keys for data loaded from DB
            "high": "🔴",
            "medium": "🟡",
            "low": "🟢",
        }

        status = "✅" if self.completed else "⭕"
        assignee_text = f" (@{self.assignee})" if self.assignee else ""
        deadline_text = f" - Due: {self.deadline.strftime('%Y-%m-%d')}" if self.deadline else ""

        # Handle both enum and string priority values
        emoji = priority_emoji.get(self.priority, "🟡")
        return f"{status} {emoji} {self.description}{assignee_text}{deadline_text}"


@dataclass
class TechnicalTerm(BaseModel):
    """Represents a technical term with definition."""
    term: str
    definition: str
    context: str
    source_message_id: str
    category: Optional[str] = None
    
    def to_markdown(self) -> str:
        """Convert to markdown format."""
        return f"**{self.term}**: {self.definition}"


@dataclass
class Participant(BaseModel):
    """Represents a conversation participant."""
    user_id: str
    display_name: str
    message_count: int
    key_contributions: List[str] = field(default_factory=list)
    first_message_time: Optional[datetime] = None
    last_message_time: Optional[datetime] = None
    # ADR-004: Referenced contributions (optional, for grounded summaries)
    referenced_contributions: List[Any] = field(default_factory=list)  # List[ReferencedClaim]

    def to_markdown(self, include_citations: bool = False) -> str:
        """Convert to markdown format.

        Args:
            include_citations: Whether to include [N] citation markers (ADR-004)
        """
        if include_citations and self.referenced_contributions:
            contributions = "\n".join([
                f"  - {contrib.to_markdown(include_citations=True)}"
                for contrib in self.referenced_contributions
            ])
        else:
            contributions = "\n".join([f"  - {contrib}" for contrib in self.key_contributions])
        return f"**{self.display_name}** ({self.message_count} messages)\n{contributions}"


@dataclass
class SummarizationContext(BaseModel):
    """Context information for summarization."""
    channel_name: str
    guild_name: str
    total_participants: int
    time_span_hours: float
    message_types: Dict[str, int] = field(default_factory=dict)  # e.g., {"text": 45, "image": 3}
    dominant_topics: List[str] = field(default_factory=list)
    thread_count: int = 0


@dataclass
class SummaryResult(BaseModel):
    """Complete summary result with all extracted information."""
    id: str = field(default_factory=generate_id)
    channel_id: str = ""
    guild_id: str = ""
    start_time: datetime = field(default_factory=utc_now)
    end_time: datetime = field(default_factory=utc_now)
    message_count: int = 0
    key_points: List[str] = field(default_factory=list)
    action_items: List[ActionItem] = field(default_factory=list)
    technical_terms: List[TechnicalTerm] = field(default_factory=list)
    participants: List[Participant] = field(default_factory=list)
    summary_text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    context: Optional[SummarizationContext] = None
    # Prompt and source tracking
    prompt_system: Optional[str] = None  # System prompt used
    prompt_user: Optional[str] = None  # User prompt with formatted messages
    prompt_template_id: Optional[str] = None  # Custom prompt template ID if used
    source_content: Optional[str] = None  # Original messages in readable format
    # Warnings generated during summary creation
    warnings: List[SummaryWarning] = field(default_factory=list)

    # ADR-004: Grounded summary references (optional, for cited summaries)
    referenced_key_points: List[Any] = field(default_factory=list)  # List[ReferencedClaim]
    referenced_action_items: List[Any] = field(default_factory=list)  # List[ReferencedClaim]
    referenced_decisions: List[Any] = field(default_factory=list)  # List[ReferencedClaim]
    referenced_topics: List[Any] = field(default_factory=list)  # List[ReferencedClaim]
    reference_index: List[Any] = field(default_factory=list)  # List[SummaryReference] - deduped index

    def add_warning(self, code: str, message: str, details: Dict[str, Any] = None):
        """Add a warning to the summary."""
        self.warnings.append(SummaryWarning(
            code=code,
            message=message,
            details=details or {}
        ))

    def to_embed_dict(self) -> Dict[str, Any]:
        """Convert to Discord embed dictionary."""
        embed = {
            "title": f"📋 Summary for #{self.context.channel_name if self.context else 'Unknown Channel'}",
            "description": self.summary_text[:2048],  # Discord embed description limit
            "color": 0x4A90E2,  # Blue color
            "timestamp": self.created_at.isoformat(),
            "fields": []
        }
        
        # Add key points field - fit as many as possible within 1024 char limit
        if self.key_points:
            key_points_lines = []
            total_len = 0
            included_count = 0
            for point in self.key_points:
                line = f"• {point}"
                if total_len + len(line) + 1 < 950:  # Leave room for "and X more"
                    key_points_lines.append(line)
                    total_len += len(line) + 1
                    included_count += 1
                else:
                    break
            key_points_text = "\n".join(key_points_lines)
            if included_count < len(self.key_points):
                key_points_text += f"\n*...and {len(self.key_points) - included_count} more*"
            embed["fields"].append({
                "name": f"🎯 Key Points ({len(self.key_points)})",
                "value": key_points_text,
                "inline": False
            })

        # Add action items field - fit as many as possible within 1024 char limit
        if self.action_items:
            action_lines = []
            total_len = 0
            included_count = 0
            for item in self.action_items:
                line = item.to_markdown()
                if total_len + len(line) + 1 < 950:  # Leave room for "and X more"
                    action_lines.append(line)
                    total_len += len(line) + 1
                    included_count += 1
                else:
                    break
            action_text = "\n".join(action_lines)
            if included_count < len(self.action_items):
                action_text += f"\n*...and {len(self.action_items) - included_count} more*"
            embed["fields"].append({
                "name": f"📝 Action Items ({len(self.action_items)})",
                "value": action_text,
                "inline": False
            })
        
        # Add participants field
        if self.participants:
            top_participants = sorted(self.participants, key=lambda p: p.message_count, reverse=True)[:5]
            participants_text = "\n".join([
                f"• {p.display_name} ({p.message_count} messages)" 
                for p in top_participants
            ])
            embed["fields"].append({
                "name": "👥 Top Participants",
                "value": participants_text,
                "inline": True
            })
        
        # Add technical terms field
        if self.technical_terms:
            terms_text = "\n".join([
                f"• **{term.term}**: {term.definition[:50]}..." 
                if len(term.definition) > 50 else f"• **{term.term}**: {term.definition}"
                for term in self.technical_terms[:3]
            ])
            embed["fields"].append({
                "name": "🔧 Technical Terms",
                "value": terms_text,
                "inline": True
            })
        
        # Add summary statistics
        stats_text = (
            f"📊 {self.message_count} messages\n"
            f"⏱️ {(self.end_time - self.start_time).total_seconds() / 3600:.1f}h timespan\n"
            f"👥 {len(self.participants)} participants"
        )
        embed["fields"].append({
            "name": "📈 Statistics",
            "value": stats_text,
            "inline": True
        })
        
        # Add footer with summary options
        footer_parts = [f"Summary ID: {self.id[:8]}..."]

        # Add length if available in metadata
        if self.metadata.get("summary_length"):
            length = self.metadata["summary_length"].capitalize()
            footer_parts.append(f"Length: {length}")

        # Add perspective if available and not "general"
        perspective = self.metadata.get("perspective", "general")
        if perspective and perspective != "general":
            footer_parts.append(f"Perspective: {perspective.capitalize()}")

        footer_parts.append("Generated by Summary Bot NG")

        embed["footer"] = {
            "text": " | ".join(footer_parts)
        }

        return embed
    
    def to_markdown(self, include_citations: bool = False) -> str:
        """Convert to markdown format.

        Args:
            include_citations: Whether to include [N] citation markers and sources table (ADR-004)
        """
        md = f"# 📋 Summary: #{self.context.channel_name if self.context else 'Unknown Channel'}\n\n"
        md += f"**Time Period:** {self.start_time.strftime('%Y-%m-%d %H:%M')} - {self.end_time.strftime('%Y-%m-%d %H:%M')}\n"
        md += f"**Messages:** {self.message_count} | **Participants:** {len(self.participants)}\n\n"

        # Main summary
        md += f"## 📖 Summary\n\n{self.summary_text}\n\n"

        # Key points (use referenced if available and citations requested)
        if include_citations and self.referenced_key_points:
            md += "## 🎯 Key Points\n\n"
            for claim in self.referenced_key_points:
                md += f"- {claim.to_markdown(include_citations=True)}\n"
            md += "\n"
        elif self.key_points:
            md += "## 🎯 Key Points\n\n"
            for point in self.key_points:
                md += f"- {point}\n"
            md += "\n"

        # Decisions (new in ADR-004)
        if include_citations and self.referenced_decisions:
            md += "## ✅ Decisions\n\n"
            for claim in self.referenced_decisions:
                md += f"- {claim.to_markdown(include_citations=True)}\n"
            md += "\n"

        # Action items (use referenced if available)
        if include_citations and self.referenced_action_items:
            md += "## 📝 Action Items\n\n"
            for claim in self.referenced_action_items:
                md += f"- [ ] {claim.to_markdown(include_citations=True)}\n"
            md += "\n"
        elif self.action_items:
            md += "## 📝 Action Items\n\n"
            for item in self.action_items:
                md += f"- {item.to_markdown()}\n"
            md += "\n"

        # Technical terms
        if self.technical_terms:
            md += "## 🔧 Technical Terms\n\n"
            for term in self.technical_terms:
                md += f"- {term.to_markdown()}\n"
            md += "\n"

        # Participants
        if self.participants:
            md += "## 👥 Participants\n\n"
            sorted_participants = sorted(self.participants, key=lambda p: p.message_count, reverse=True)
            for participant in sorted_participants:
                md += f"### {participant.display_name} ({participant.message_count} messages)\n"
                if include_citations and participant.referenced_contributions:
                    md += "Key contributions:\n"
                    for contrib in participant.referenced_contributions:
                        md += f"- {contrib.to_markdown(include_citations=True)}\n"
                elif participant.key_contributions:
                    md += "Key contributions:\n"
                    for contribution in participant.key_contributions:
                        md += f"- {contribution}\n"
                md += "\n"

        # Sources table (ADR-004)
        if include_citations and self.reference_index:
            md += "---\n\n### Sources\n\n"
            md += "| # | Who | When | Said |\n"
            md += "|---|-----|------|------|\n"
            for ref in self.reference_index:
                # Handle both object and dict formats, and both datetime and string timestamps
                if hasattr(ref, 'timestamp'):
                    timestamp = ref.timestamp
                    sender = ref.sender
                    snippet = ref.snippet
                    position = ref.position
                else:
                    # Dict format
                    timestamp = ref.get('timestamp')
                    sender = ref.get('sender', 'Unknown')
                    snippet = ref.get('snippet', '')
                    position = ref.get('position', 0)

                # Parse string timestamp if needed
                if isinstance(timestamp, str):
                    try:
                        from datetime import datetime as dt
                        timestamp = dt.fromisoformat(timestamp.replace('Z', '+00:00'))
                    except (ValueError, TypeError):
                        timestamp = None

                time_str = timestamp.strftime("%H:%M") if timestamp else "??:??"
                # Escape pipe characters in snippet
                snippet = snippet.replace("|", "\\|")
                if len(snippet) > 60:
                    snippet = snippet[:57] + "..."
                md += f"| [{position}] | {sender} | {time_str} | \"{snippet}\" |\n"
            md += "\n"

        # Metadata
        md += f"---\n*Summary generated on {self.created_at.strftime('%Y-%m-%d at %H:%M UTC')} | ID: {self.id}*\n"

        return md
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics."""
        stats = {
            "id": self.id,
            "message_count": self.message_count,
            "participant_count": len(self.participants),
            "key_points_count": len(self.key_points),
            "action_items_count": len(self.action_items),
            "technical_terms_count": len(self.technical_terms),
            "time_span_hours": (self.end_time - self.start_time).total_seconds() / 3600,
            "words_in_summary": len(self.summary_text.split()),
            "created_at": self.created_at,
            "channel_id": self.channel_id,
            "guild_id": self.guild_id
        }
        # ADR-004: Add reference stats if grounded
        if self.reference_index:
            stats["grounded"] = True
            stats["reference_count"] = len(self.reference_index)
            stats["referenced_key_points_count"] = len(self.referenced_key_points)
            stats["referenced_decisions_count"] = len(self.referenced_decisions)
        else:
            stats["grounded"] = False
        return stats

    def has_references(self) -> bool:
        """Check if this summary has grounded references (ADR-004)."""
        return bool(self.reference_index)


def _get_default_model() -> str:
    """Get default summarization model from environment or use fallback.

    Checks SUMMARIZATION_MODEL first, then falls back to legacy SUMMARY_CLAUDE_MODEL
    for backward compatibility, and finally uses the constant default.
    """
    # Try new environment variable name first
    model = os.getenv('SUMMARIZATION_MODEL')
    if model:
        return model

    # Fall back to legacy environment variable name
    legacy_model = os.getenv('SUMMARY_CLAUDE_MODEL')
    if legacy_model:
        logger.warning(
            "Using deprecated environment variable 'SUMMARY_CLAUDE_MODEL'. "
            "Please rename to 'SUMMARIZATION_MODEL'."
        )
        return legacy_model

    # Use constant default
    return DEFAULT_SUMMARIZATION_MODEL


@dataclass
class SummaryOptions(BaseModel):
    """Options for controlling summarization behavior."""
    summary_length: SummaryLength = SummaryLength.DETAILED
    perspective: str = "general"  # general, developer, marketing, product, finance, executive, support
    include_bots: bool = False
    include_attachments: bool = True
    excluded_users: List[str] = field(default_factory=list)
    min_messages: int = 5
    summarization_model: str = field(default_factory=_get_default_model)
    temperature: float = 0.3
    max_tokens: int = 8000  # Default to max to not limit comprehensive summaries
    extract_action_items: bool = True
    extract_technical_terms: bool = True
    extract_key_points: bool = True
    include_participant_analysis: bool = True
    # ADR-002: Multi-source support
    source_type: str = "discord"  # 'discord', 'whatsapp', etc.
    # WhatsApp-specific options (ADR-002)
    include_voice_transcripts: bool = True  # Include voice note transcriptions
    include_forwarded: bool = True  # Include forwarded messages
    reconstruct_threads: bool = True  # Reconstruct conversation threads from reply chains
    
    def get_max_tokens_for_length(self) -> int:
        """Get appropriate max tokens based on summary length."""
        token_mapping = {
            SummaryLength.BRIEF: 1000,
            SummaryLength.DETAILED: 4000,
            SummaryLength.COMPREHENSIVE: 8000
        }
        return min(self.max_tokens, token_mapping[self.summary_length])
    
    def get_system_prompt_additions(self) -> List[str]:
        """Get additional system prompt requirements based on options."""
        additions = []
        
        if not self.extract_action_items:
            additions.append("Do not extract action items.")
        
        if not self.extract_technical_terms:
            additions.append("Do not define technical terms.")
        
        if not self.extract_key_points:
            additions.append("Focus on narrative summary only, no bullet points.")
        
        if not self.include_participant_analysis:
            additions.append("Do not analyze individual participant contributions.")
        
        length_instructions = {
            SummaryLength.BRIEF: "Keep the summary concise and focus on the most important points only.",
            SummaryLength.DETAILED: "Provide a balanced summary with good coverage of the discussion.",
            SummaryLength.COMPREHENSIVE: "Provide an extensive summary covering all aspects of the conversation."
        }
        additions.append(length_instructions[self.summary_length])

        return additions

    def get_model_for_length(self) -> str:
        """
        Get the appropriate model based on summary length.

        For BRIEF summaries, automatically use Haiku for speed and cost efficiency.
        For COMPREHENSIVE summaries, use the best available model for quality.
        For DETAILED summaries, use the configured model.

        Returns:
            Model identifier string (e.g., 'claude-3-haiku-20240307')
        """
        if self.summary_length == SummaryLength.BRIEF:
            return DEFAULT_BRIEF_MODEL

        if self.summary_length == SummaryLength.COMPREHENSIVE:
            return DEFAULT_COMPREHENSIVE_MODEL

        # For detailed, use configured model
        return self.summarization_model