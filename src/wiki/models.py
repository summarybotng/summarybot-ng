"""
Wiki data models (ADR-056).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum


class WikiSourceType(str, Enum):
    """Type of wiki source document."""
    SUMMARY = "summary"
    ARCHIVE = "archive"
    DOCUMENT = "document"


class WikiOperation(str, Enum):
    """Wiki operation types for logging."""
    INGEST = "ingest"
    QUERY = "query"
    QUERY_PERSIST = "query_persist"
    LINT = "lint"


@dataclass
class WikiPage:
    """A wiki page with full content and metadata."""
    id: str
    guild_id: str
    path: str
    title: str
    content: str  # Raw updates (append-only)
    topics: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    inbound_links: int = 0
    outbound_links: int = 0
    confidence: int = 100
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # ADR-063: Synthesis fields
    synthesis: Optional[str] = None  # LLM-generated summary
    synthesis_updated_at: Optional[datetime] = None
    synthesis_source_count: int = 0
    # ADR-064/065: Rating and model tracking
    synthesis_model: Optional[str] = None
    rating_sum: int = 0
    rating_count: int = 0

    @property
    def average_rating(self) -> Optional[float]:
        """Calculate average rating."""
        if self.rating_count == 0:
            return None
        return self.rating_sum / self.rating_count

    @property
    def source_count(self) -> int:
        """Number of sources referenced."""
        return len(self.source_refs)

    @property
    def category(self) -> str:
        """Extract category from path (e.g., 'topics' from 'topics/auth.md')."""
        parts = self.path.split("/")
        return parts[0] if len(parts) > 1 else "root"


@dataclass
class WikiPageSummary:
    """Summary view of a wiki page for listings."""
    id: str
    path: str
    title: str
    topics: List[str]
    updated_at: Optional[datetime]
    inbound_links: int = 0
    confidence: int = 100
    # ADR-064: Filter fields
    created_at: Optional[datetime] = None
    source_count: int = 0
    has_synthesis: bool = False
    synthesis_model: Optional[str] = None
    average_rating: Optional[float] = None
    rating_count: int = 0


@dataclass
class WikiLink:
    """A link between wiki pages."""
    from_page: str
    to_page: str
    guild_id: str
    link_text: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class WikiLogEntry:
    """An entry in the wiki operation log."""
    id: int
    guild_id: str
    operation: WikiOperation
    details: Dict[str, Any]
    agent_id: Optional[str] = None
    timestamp: Optional[datetime] = None


@dataclass
class WikiContradiction:
    """A detected contradiction between wiki pages."""
    id: int
    guild_id: str
    page_a: str
    page_b: str
    claim_a: str
    claim_b: str
    detected_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolution: Optional[str] = None

    @property
    def is_resolved(self) -> bool:
        return self.resolved_at is not None


@dataclass
class WikiSource:
    """An immutable source document."""
    id: str
    guild_id: str
    source_type: WikiSourceType
    content: str
    title: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    ingested_at: Optional[datetime] = None


@dataclass
class WikiTreeNode:
    """A node in the wiki navigation tree."""
    path: str
    title: str
    children: List["WikiTreeNode"] = field(default_factory=list)
    page_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "title": self.title,
            "children": [c.to_dict() for c in self.children],
            "page_count": self.page_count,
        }


@dataclass
class WikiTree:
    """Navigation tree structure for the wiki."""
    guild_id: str
    topics: WikiTreeNode = field(default_factory=lambda: WikiTreeNode("topics", "Topics"))
    decisions: WikiTreeNode = field(default_factory=lambda: WikiTreeNode("decisions", "Decisions"))
    processes: WikiTreeNode = field(default_factory=lambda: WikiTreeNode("processes", "Processes"))
    experts: WikiTreeNode = field(default_factory=lambda: WikiTreeNode("experts", "Experts"))
    questions: WikiTreeNode = field(default_factory=lambda: WikiTreeNode("questions", "Questions"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "guild_id": self.guild_id,
            "categories": [
                self.topics.to_dict(),
                self.decisions.to_dict(),
                self.processes.to_dict(),
                self.experts.to_dict(),
                self.questions.to_dict(),
            ]
        }


@dataclass
class WikiSearchResult:
    """Result of a wiki search."""
    query: str
    total: int
    pages: List[WikiPageSummary]
    synthesis: Optional[str] = None  # AI-generated answer
    gaps: List[str] = field(default_factory=list)  # Knowledge gaps identified


@dataclass
class WikiChange:
    """A recent change to the wiki."""
    page_path: str
    page_title: str
    operation: str
    changed_at: datetime
    source_id: Optional[str] = None
    agent_id: Optional[str] = None


@dataclass
class SynthesisOptions:
    """Options for wiki synthesis generation (ADR-065)."""
    model: str = "auto"  # auto, haiku, sonnet, opus
    temperature: float = 0.3
    max_tokens: int = 2000
    focus_areas: List[str] = field(default_factory=list)
    custom_instructions: Optional[str] = None


@dataclass
class WikiSynthesisRating:
    """A user rating for a wiki synthesis (ADR-065)."""
    id: int
    guild_id: str
    page_path: str
    user_id: str
    rating: int  # 1-5
    feedback: Optional[str] = None
    synthesis_model: Optional[str] = None
    synthesis_version: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class WikiFilterFacets:
    """Facet counts for wiki filtering (ADR-064)."""
    source_count: Dict[str, int] = field(default_factory=dict)  # "1": 20, "2-5": 50
    rating: Dict[str, int] = field(default_factory=dict)  # "unrated": 80, "5": 15
    synthesis_model: Dict[str, int] = field(default_factory=dict)  # "haiku": 60
    has_synthesis: Dict[str, int] = field(default_factory=dict)  # "true": 100
