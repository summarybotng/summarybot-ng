"""
Wiki module for Compounding Wiki (ADR-056).

This module implements a persistent, incrementally-maintained knowledge artifact
where an LLM agent actively builds and maintains a structured wiki that grows
more valuable with each interaction.
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

__all__ = [
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
]
