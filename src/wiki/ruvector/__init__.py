"""
RuVector: Vector-enhanced wiki with semantic search and knowledge graph.

ADR-057 implementation providing:
- HNSW vector index for semantic search
- Knowledge unit extraction from summaries/messages
- GNN-style edge inference for relationship discovery
- SONA temporal learning for relevance optimization
- Coherence gate for hallucination prevention
"""

from .models import (
    KnowledgeUnit,
    KnowledgeUnitType,
    Edge,
    EdgeType,
    LearningSignal,
    SignalType,
    CoherenceValidation,
    ValidationStatus,
    ContinuityCheckpoint,
    SearchResult,
    ExtractionResult,
)
from .embeddings import EmbeddingService
from .knowledge_extractor import KnowledgeExtractor
from .vector_store import VectorStore
# Phase 2: Integration and inference
from .ingest_integration import RuVectorIngestIntegration, RuVectorIngestHook
from .edge_inference import EdgeInferenceEngine
from .view_renderer import WikiViewRenderer, RenderedView

__all__ = [
    # Models
    "KnowledgeUnit",
    "KnowledgeUnitType",
    "Edge",
    "EdgeType",
    "LearningSignal",
    "SignalType",
    "CoherenceValidation",
    "ValidationStatus",
    "ContinuityCheckpoint",
    "SearchResult",
    "ExtractionResult",
    # Phase 1: Core services
    "EmbeddingService",
    "KnowledgeExtractor",
    "VectorStore",
    # Phase 2: Integration and inference
    "RuVectorIngestIntegration",
    "RuVectorIngestHook",
    "EdgeInferenceEngine",
    "WikiViewRenderer",
    "RenderedView",
]
