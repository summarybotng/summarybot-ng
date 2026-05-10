"""
RuVector data models (ADR-057).

Defines knowledge units, edges, learning signals, and related types.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum


class KnowledgeUnitType(str, Enum):
    """Type of knowledge unit extracted from content."""
    CLAIM = "claim"  # Factual statement
    DECISION = "decision"  # A decision that was made
    QUESTION = "question"  # An open question
    ACTION_ITEM = "action_item"  # Something to be done
    CONTEXT = "context"  # Background/contextual information
    DEFINITION = "definition"  # Term or concept definition
    REFERENCE = "reference"  # Reference to external resource


class EdgeType(str, Enum):
    """Type of relationship between knowledge units."""
    RELATES_TO = "relates_to"  # General topical relationship
    DEPENDS_ON = "depends_on"  # Causal/dependency relationship
    CONTRADICTS = "contradicts"  # Conflicting information
    SUPERSEDES = "supersedes"  # Newer info replaces older
    SUPPORTS = "supports"  # Evidence supporting a claim
    ANSWERS = "answers"  # Answer to a question
    IMPLEMENTS = "implements"  # Implementation of a decision


class SignalType(str, Enum):
    """Type of learning signal from user interaction."""
    SEARCH_CLICK = "search_click"  # User clicked a search result
    DWELL = "dwell"  # Time spent on content
    REFINEMENT = "refinement"  # Query refinement pattern
    FEEDBACK = "feedback"  # Explicit user feedback
    PAGE_VIEW = "page_view"  # Wiki page view


class ValidationStatus(str, Enum):
    """Status of coherence validation."""
    APPROVED = "approved"  # Passed validation
    REJECTED = "rejected"  # Failed validation, not stored
    FLAGGED = "flagged"  # Needs human review


class ExtractionSource(str, Enum):
    """Source of knowledge unit extraction (ADR-090)."""
    INLINE = "inline"  # Extracted during summarization (optimal)
    BACKFILL = "backfill"  # Extracted from historical stored_summaries
    MANUAL = "manual"  # Extracted via 360° Generate (legacy)


@dataclass
class KnowledgeUnit:
    """An atomic unit of knowledge extracted from content."""
    id: str
    guild_id: str
    content: str
    unit_type: KnowledgeUnitType
    source_id: str
    source_type: str  # summary, message, archive, human_edit
    source_channel: Optional[str] = None
    source_date: Optional[datetime] = None
    embedding: Optional[List[float]] = None
    embedding_model: str = "text-embedding-3-small"
    confidence: float = 1.0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # ADR-090: Track extraction source
    extraction_source: ExtractionSource = ExtractionSource.MANUAL
    summary_id: Optional[str] = None  # Direct link to source summary

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "guild_id": self.guild_id,
            "content": self.content,
            "unit_type": self.unit_type.value if isinstance(self.unit_type, KnowledgeUnitType) else self.unit_type,
            "source_id": self.source_id,
            "source_type": self.source_type,
            "source_channel": self.source_channel,
            "source_date": self.source_date.isoformat() if self.source_date else None,
            "embedding_model": self.embedding_model,
            "confidence": self.confidence,
            # ADR-090: Inline extraction tracking
            "extraction_source": self.extraction_source.value if isinstance(self.extraction_source, ExtractionSource) else self.extraction_source,
            "summary_id": self.summary_id,
        }


@dataclass
class Edge:
    """A relationship between two knowledge units."""
    id: Optional[int] = None
    guild_id: str = ""
    from_unit_id: str = ""
    to_unit_id: str = ""
    edge_type: EdgeType = EdgeType.RELATES_TO
    weight: float = 1.0
    inferred_by: str = "gnn"  # gnn, manual, coherence_gate
    created_at: Optional[datetime] = None


@dataclass
class LearningSignal:
    """A learning signal from user interaction."""
    id: Optional[int] = None
    guild_id: str = ""
    signal_type: SignalType = SignalType.PAGE_VIEW
    unit_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    user_id: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class CoherenceValidation:
    """Result of coherence validation for a knowledge unit."""
    id: Optional[int] = None
    guild_id: str = ""
    unit_id: str = ""
    validation_type: str = ""  # contradiction, unsupported, drift
    status: ValidationStatus = ValidationStatus.APPROVED
    details: Dict[str, Any] = field(default_factory=dict)
    reviewed_by: Optional[str] = None
    created_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None


@dataclass
class ContinuityCheckpoint:
    """Weekly checkpoint for carrying context forward."""
    id: str
    guild_id: str
    channel_id: str
    week_start: datetime
    week_end: datetime
    summary: str
    key_topics: List[str] = field(default_factory=list)
    open_threads: List[str] = field(default_factory=list)
    unit_count: int = 0
    created_at: Optional[datetime] = None


@dataclass
class SearchResult:
    """Result from semantic vector search."""
    unit_id: str
    content: str
    unit_type: KnowledgeUnitType
    score: float  # Similarity score (0-1)
    source_id: str
    source_channel: Optional[str] = None
    source_date: Optional[datetime] = None

    # Optional: populated if edges are requested
    related_units: List["SearchResult"] = field(default_factory=list)


@dataclass
class ExtractionResult:
    """Result from knowledge extraction."""
    units: List[KnowledgeUnit]
    source_id: str
    extraction_model: str
    token_count: int = 0
    processing_time_ms: int = 0
