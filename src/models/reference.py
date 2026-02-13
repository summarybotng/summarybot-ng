"""
Reference models for grounded summary citations (ADR-004).

These models enable message-level citations in summaries, allowing users to trace
claims back to specific source messages.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, TYPE_CHECKING

from .base import BaseModel

if TYPE_CHECKING:
    from .message import ProcessedMessage


@dataclass
class SummaryReference(BaseModel):
    """A citation pointing to a specific source message in a summary.

    This is distinct from MessageReference (in message.py) which represents
    Discord reply/quote references. SummaryReference is for summary citations.
    """
    message_id: str
    sender: str
    timestamp: datetime
    snippet: str  # Max 200 chars of the relevant message content
    position: int  # 1-based position in the conversation window

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "message_id": self.message_id,
            "sender": self.sender,
            "timestamp": self.timestamp.isoformat(),
            "snippet": self.snippet,
            "position": self.position
        }

    def to_footnote(self) -> str:
        """Format as a footnote entry for markdown output."""
        time_str = self.timestamp.strftime("%H:%M")
        return f"[{self.position}] | {self.sender} | {time_str} | \"{self.snippet}\""

    def to_inline(self) -> str:
        """Format as inline citation for plain text output."""
        time_str = self.timestamp.strftime("%H:%M")
        return f"({self.sender}, {time_str})"


@dataclass
class ReferencedClaim(BaseModel):
    """A summary claim with one or more supporting references.

    Each key point, action item, decision, or contribution carries references
    to the specific message(s) that support it.
    """
    text: str
    references: List[SummaryReference] = field(default_factory=list)
    confidence: float = 1.0  # Model's self-assessed confidence (0.0-1.0)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "text": self.text,
            "references": [ref.to_dict() for ref in self.references],
            "confidence": self.confidence
        }

    def to_markdown(self, include_citations: bool = True) -> str:
        """Format as markdown with optional inline citations.

        Args:
            include_citations: Whether to include [N] citation markers

        Returns:
            Markdown string with optional citation markers
        """
        if not include_citations or not self.references:
            return self.text

        # Add citation markers like [2][4]
        citations = "".join(f"[{ref.position}]" for ref in self.references)
        return f"{self.text} {citations}"

    def to_plain_text(self) -> str:
        """Format as plain text with parenthetical citations."""
        if not self.references:
            return self.text

        # Add inline citations like (Bob, 14:32)
        citations = ", ".join(ref.to_inline() for ref in self.references[:2])
        if len(self.references) > 2:
            citations += f", +{len(self.references) - 2} more"
        return f"{self.text} ({citations})"

    @property
    def position_numbers(self) -> List[int]:
        """Get list of position numbers for this claim."""
        return [ref.position for ref in self.references]


class PositionIndex:
    """Maps [N] position numbers to source message metadata.

    Built during prompt formatting and used during response parsing
    to resolve position numbers back to full SummaryReference objects.
    """

    def __init__(self, messages: List['ProcessedMessage']):
        """Initialize the position index from a list of messages.

        Args:
            messages: List of processed messages in conversation order
        """
        self._index: Dict[int, 'ProcessedMessage'] = {}
        self._position_to_msg: Dict[int, 'ProcessedMessage'] = {}

        for i, msg in enumerate(messages, start=1):
            self._index[i] = msg
            self._position_to_msg[i] = msg

    def resolve(self, position: int) -> Optional[SummaryReference]:
        """Resolve a position number to a SummaryReference.

        Args:
            position: 1-based position number from Claude's response

        Returns:
            SummaryReference if position is valid, None otherwise
        """
        msg = self._index.get(position)
        if msg is None:
            return None

        # Create snippet from message content (max 200 chars)
        snippet = msg.content or ""
        if len(snippet) > 200:
            snippet = snippet[:197] + "..."

        return SummaryReference(
            message_id=msg.id,
            sender=msg.author_name,
            timestamp=msg.timestamp,
            snippet=snippet,
            position=position,
        )

    def resolve_many(self, positions: List[int]) -> List[SummaryReference]:
        """Resolve multiple position numbers to SummaryReferences.

        Args:
            positions: List of 1-based position numbers

        Returns:
            List of resolved references (invalid positions are skipped)
        """
        refs = []
        for p in positions:
            ref = self.resolve(p)
            if ref is not None:
                refs.append(ref)
        return refs

    def get_message(self, position: int) -> Optional['ProcessedMessage']:
        """Get the original message for a position.

        Args:
            position: 1-based position number

        Returns:
            ProcessedMessage if position is valid, None otherwise
        """
        return self._index.get(position)

    def __len__(self) -> int:
        """Return the number of indexed messages."""
        return len(self._index)

    def __contains__(self, position: int) -> bool:
        """Check if a position exists in the index."""
        return position in self._index


def build_deduped_reference_index(
    *claim_lists: List[ReferencedClaim]
) -> List[SummaryReference]:
    """Build a deduplicated reference index from multiple claim lists.

    Args:
        *claim_lists: Variable number of ReferencedClaim lists

    Returns:
        Deduplicated list of all references, sorted by position
    """
    seen_positions: Dict[int, SummaryReference] = {}

    for claims in claim_lists:
        for claim in claims:
            for ref in claim.references:
                if ref.position not in seen_positions:
                    seen_positions[ref.position] = ref

    # Sort by position
    return sorted(seen_positions.values(), key=lambda r: r.position)
