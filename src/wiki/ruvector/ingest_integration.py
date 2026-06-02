"""
RuVector integration for wiki ingestion (ADR-057 Phase 2).

Extends the WikiIngestAgent to also store knowledge units in RuVector,
enabling semantic search and automatic relationship discovery.
"""

import logging
from typing import List, Optional, Any, TYPE_CHECKING
from datetime import datetime

from .models import KnowledgeUnit, Edge, EdgeType, ExtractionResult
from .embeddings import EmbeddingService
from .knowledge_extractor import KnowledgeExtractor
from .vector_store import VectorStore

if TYPE_CHECKING:
    from ...summarization.claude_client import ClaudeClient

logger = logging.getLogger(__name__)


class RuVectorIngestIntegration:
    """
    Integrates RuVector with wiki ingestion pipeline.

    This class wraps the extraction, embedding, and storage of
    knowledge units from summaries and messages.
    """

    def __init__(
        self,
        connection: Any,  # SQLiteConnection
        claude_client: Optional["ClaudeClient"] = None,
        embedding_service: Optional[EmbeddingService] = None,
        enable_edge_inference: bool = True,
        edge_similarity_threshold: float = 0.75,
    ):
        """
        Initialize the RuVector integration.

        Args:
            connection: SQLite database connection
            claude_client: Claude client for LLM extraction
            embedding_service: Service for generating embeddings
            enable_edge_inference: Whether to automatically infer edges
            edge_similarity_threshold: Minimum similarity for edge inference
        """
        self.embedding_service = embedding_service or EmbeddingService()
        self.extractor = KnowledgeExtractor(
            claude_client=claude_client,
            min_confidence=0.5,
        )
        self.vector_store = VectorStore(
            connection=connection,
            embedding_service=self.embedding_service,
        )
        self.enable_edge_inference = enable_edge_inference
        self.edge_similarity_threshold = edge_similarity_threshold

    async def ingest_summary(
        self,
        guild_id: str,
        summary_id: str,
        summary_text: str,
        channel_name: Optional[str] = None,
        summary_date: Optional[datetime] = None,
        key_points: Optional[List[str]] = None,
        action_items: Optional[List[str]] = None,
    ) -> ExtractionResult:
        """
        Ingest a summary into RuVector.

        Extracts knowledge units, generates embeddings, stores them,
        and optionally infers edges to related content.

        Args:
            guild_id: Guild ID
            summary_id: Source summary ID
            summary_text: Full summary text
            channel_name: Source channel name
            summary_date: Summary timestamp
            key_points: Pre-extracted key points
            action_items: Pre-extracted action items

        Returns:
            ExtractionResult with extracted units
        """
        logger.info(f"RuVector ingesting summary {summary_id} for guild {guild_id}")

        # ADR-118: Check if knowledge units already exist for this summary
        # This prevents duplicates during rolling schedule re-runs
        existing_count = await self.vector_store.count_units_by_summary_id(
            guild_id, summary_id
        )
        if existing_count > 0:
            logger.info(
                f"Skipping RuVector extraction for {summary_id}: "
                f"{existing_count} units already exist"
            )
            # Return existing units instead of re-extracting
            existing_units = await self.vector_store.get_units_by_summary_id(
                guild_id, summary_id
            )
            return ExtractionResult(
                units=existing_units,
                source_id=summary_id,
                extraction_model="cached",
                token_count=0,
                processing_time_ms=0,
            )

        # 1. Extract knowledge units
        extraction = await self.extractor.extract_from_summary(
            guild_id=guild_id,
            summary_id=summary_id,
            summary_text=summary_text,
            channel_name=channel_name,
            summary_date=summary_date,
            key_points=key_points,
            action_items=action_items,
        )

        if not extraction.units:
            logger.info(f"No knowledge units extracted from summary {summary_id}")
            return extraction

        # 2. Store units with embeddings
        unit_ids = await self.vector_store.store_units_batch(extraction.units)
        logger.info(f"Stored {len(unit_ids)} knowledge units from summary {summary_id}")

        # 3. Infer edges to related content
        if self.enable_edge_inference:
            edges_created = await self._infer_edges_for_units(extraction.units)
            logger.info(f"Inferred {edges_created} edges for summary {summary_id}")

        return extraction

    async def ingest_messages(
        self,
        guild_id: str,
        messages: List[dict],
        channel_name: Optional[str] = None,
        batch_id: Optional[str] = None,
    ) -> ExtractionResult:
        """
        Ingest raw messages into RuVector.

        Args:
            guild_id: Guild ID
            messages: List of message dicts
            channel_name: Channel name
            batch_id: Optional batch identifier

        Returns:
            ExtractionResult with extracted units
        """
        logger.info(f"RuVector ingesting {len(messages)} messages for guild {guild_id}")

        # 1. Extract knowledge units
        extraction = await self.extractor.extract_from_messages(
            guild_id=guild_id,
            messages=messages,
            channel_name=channel_name,
            batch_id=batch_id,
        )

        if not extraction.units:
            logger.info(f"No knowledge units extracted from messages")
            return extraction

        # 2. Store units with embeddings
        unit_ids = await self.vector_store.store_units_batch(extraction.units)
        logger.info(f"Stored {len(unit_ids)} knowledge units from messages")

        # 3. Infer edges
        if self.enable_edge_inference:
            edges_created = await self._infer_edges_for_units(extraction.units)
            logger.info(f"Inferred {edges_created} edges for messages")

        return extraction

    async def _infer_edges_for_units(self, units: List[KnowledgeUnit]) -> int:
        """
        Infer edges between new units and existing content.

        Uses semantic similarity to find related units and creates
        appropriate edge types based on unit types.
        """
        edges_created = 0

        for unit in units:
            if not unit.embedding:
                continue

            # Find similar existing units
            similar = await self.vector_store.find_similar(
                unit_id=unit.id,
                limit=5,
                threshold=self.edge_similarity_threshold,
                exclude_same_source=True,
            )

            for result in similar:
                # Determine edge type based on unit types
                edge_type = self._determine_edge_type(unit, result)

                edge = Edge(
                    guild_id=unit.guild_id,
                    from_unit_id=unit.id,
                    to_unit_id=result.unit_id,
                    edge_type=edge_type,
                    weight=result.score,
                    inferred_by="gnn",
                )

                await self.vector_store.store_edge(edge)
                edges_created += 1

        return edges_created

    def _determine_edge_type(
        self,
        from_unit: KnowledgeUnit,
        to_result: Any,  # SearchResult
    ) -> EdgeType:
        """
        Determine the appropriate edge type between two units.

        Uses unit types to infer relationship semantics:
        - question → claim/decision = might be answered
        - decision → claim = supports/implements
        - action_item → decision = implements
        - claim → claim = relates_to
        """
        from .models import KnowledgeUnitType

        from_type = from_unit.unit_type
        to_type = to_result.unit_type

        # Question to answer patterns
        if from_type == KnowledgeUnitType.QUESTION:
            if to_type in [KnowledgeUnitType.CLAIM, KnowledgeUnitType.DECISION]:
                return EdgeType.ANSWERS

        # Decision relationships
        if from_type == KnowledgeUnitType.DECISION:
            if to_type == KnowledgeUnitType.CLAIM:
                return EdgeType.SUPPORTS

        # Action item relationships
        if from_type == KnowledgeUnitType.ACTION_ITEM:
            if to_type == KnowledgeUnitType.DECISION:
                return EdgeType.IMPLEMENTS

        # Check for temporal supersession (newer content might supersede older)
        if from_unit.source_date and to_result.source_date:
            if from_unit.source_date > to_result.source_date:
                # Could be superseding older content
                # Only apply if very high similarity
                if hasattr(to_result, 'score') and to_result.score > 0.9:
                    return EdgeType.SUPERSEDES

        # Default to general relationship
        return EdgeType.RELATES_TO


class RuVectorIngestHook:
    """
    Hook for integrating RuVector with existing WikiIngestAgent.

    Can be called after wiki ingestion to also populate RuVector.
    """

    def __init__(self, integration: RuVectorIngestIntegration):
        self.integration = integration
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value

    async def on_summary_ingested(
        self,
        guild_id: str,
        summary_id: str,
        summary_text: str,
        channel_name: Optional[str] = None,
        summary_date: Optional[datetime] = None,
        key_points: Optional[List[str]] = None,
        action_items: Optional[List[str]] = None,
    ) -> Optional[ExtractionResult]:
        """
        Hook called after a summary is ingested into the wiki.

        This allows RuVector ingestion to run alongside wiki ingestion
        without modifying the existing WikiIngestAgent code.
        """
        if not self._enabled:
            return None

        try:
            return await self.integration.ingest_summary(
                guild_id=guild_id,
                summary_id=summary_id,
                summary_text=summary_text,
                channel_name=channel_name,
                summary_date=summary_date,
                key_points=key_points,
                action_items=action_items,
            )
        except Exception as e:
            logger.error(f"RuVector ingest hook failed: {e}")
            # Don't fail the main ingestion
            return None
