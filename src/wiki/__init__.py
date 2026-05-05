"""
Wiki module for Compounding Wiki (ADR-056, ADR-057).

This module implements a persistent, incrementally-maintained knowledge artifact
where an LLM agent actively builds and maintains a structured wiki that grows
more valuable with each interaction.

ADR-057 adds RuVector: vector-enhanced wiki with semantic search,
knowledge graph, and self-improving relevance.
"""

from .models import (
    WikiPage,
    WikiPageSummary,
    WikiLink,
    WikiLogEntry,
    WikiContradiction,
    WikiSource,
    WikiTree,
    WikiTreeNode,
    WikiSearchResult,
    WikiChange,
)

# ADR-057: RuVector components
from .ruvector import (
    KnowledgeUnit,
    KnowledgeUnitType,
    Edge,
    EdgeType,
    SearchResult as RuVectorSearchResult,
    EmbeddingService,
    KnowledgeExtractor,
    VectorStore,
)

__all__ = [
    # ADR-056: Original wiki models
    "WikiPage",
    "WikiPageSummary",
    "WikiLink",
    "WikiLogEntry",
    "WikiContradiction",
    "WikiSource",
    "WikiTree",
    "WikiTreeNode",
    "WikiSearchResult",
    "WikiChange",
    # ADR-057: RuVector models
    "KnowledgeUnit",
    "KnowledgeUnitType",
    "Edge",
    "EdgeType",
    "RuVectorSearchResult",
    # ADR-057: RuVector services
    "EmbeddingService",
    "KnowledgeExtractor",
    "VectorStore",
]
