"""
Backfill tooling for RuVector (ADR-057 Phase 3).

Migrates existing wiki content to RuVector:
1. Wiki sources → Knowledge units
2. Wiki pages → Knowledge units
3. Rebuild edges for all units
"""

import logging
import asyncio
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime
from dataclasses import dataclass, field

from .models import KnowledgeUnit, KnowledgeUnitType, ExtractionResult
from .embeddings import EmbeddingService
from .knowledge_extractor import KnowledgeExtractor
from .vector_store import VectorStore
from .edge_inference import EdgeInferenceEngine
from .coherence_gate import CoherenceGate

if TYPE_CHECKING:
    from ...summarization.claude_client import ClaudeClient

logger = logging.getLogger(__name__)


@dataclass
class BackfillProgress:
    """Progress tracking for backfill operation."""
    guild_id: str
    phase: str
    total_items: int = 0
    processed_items: int = 0
    units_created: int = 0
    edges_created: int = 0
    errors: List[str] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def percent_complete(self) -> float:
        if self.total_items == 0:
            return 0.0
        return (self.processed_items / self.total_items) * 100

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None


@dataclass
class BackfillResult:
    """Result of backfill operation."""
    guild_id: str
    sources_processed: int
    pages_processed: int
    units_created: int
    edges_created: int
    errors: List[str]
    duration_seconds: float


class RuVectorBackfill:
    """
    Backfill existing wiki content to RuVector.

    ADR-057/087: Migrates existing wiki sources and pages to the
    knowledge unit store for semantic search and view rendering.
    """

    def __init__(
        self,
        wiki_connection: Any,  # SQLiteConnection for wiki
        vector_store: VectorStore,
        knowledge_extractor: KnowledgeExtractor,
        edge_inference: Optional[EdgeInferenceEngine] = None,
        coherence_gate: Optional[CoherenceGate] = None,
        batch_size: int = 50,
        enable_coherence_check: bool = True,
    ):
        """
        Initialize backfill tooling.

        Args:
            wiki_connection: Database connection for wiki tables
            vector_store: RuVector store
            knowledge_extractor: Extractor for creating units
            edge_inference: Optional edge inference engine
            coherence_gate: Optional coherence validation
            batch_size: Items to process per batch
            enable_coherence_check: Whether to validate during backfill
        """
        self.wiki_connection = wiki_connection
        self.vector_store = vector_store
        self.extractor = knowledge_extractor
        self.edge_inference = edge_inference
        self.coherence_gate = coherence_gate
        self.batch_size = batch_size
        self.enable_coherence_check = enable_coherence_check

    async def backfill_guild(
        self,
        guild_id: str,
        include_sources: bool = True,
        include_pages: bool = True,
        rebuild_edges: bool = True,
        progress_callback: Optional[callable] = None,
    ) -> BackfillResult:
        """
        Backfill all wiki content for a guild.

        Args:
            guild_id: Guild to backfill
            include_sources: Backfill wiki_sources
            include_pages: Backfill wiki_pages
            rebuild_edges: Rebuild edges after backfill
            progress_callback: Optional callback for progress updates

        Returns:
            BackfillResult with statistics
        """
        import time
        start_time = time.time()

        result = BackfillResult(
            guild_id=guild_id,
            sources_processed=0,
            pages_processed=0,
            units_created=0,
            edges_created=0,
            errors=[],
            duration_seconds=0,
        )

        try:
            # Phase 1: Backfill sources
            if include_sources:
                logger.info(f"Backfilling sources for guild {guild_id}")
                source_result = await self._backfill_sources(guild_id, progress_callback)
                result.sources_processed = source_result["processed"]
                result.units_created += source_result["units_created"]
                result.errors.extend(source_result["errors"])

            # Phase 2: Backfill pages (for content not from sources)
            if include_pages:
                logger.info(f"Backfilling pages for guild {guild_id}")
                page_result = await self._backfill_pages(guild_id, progress_callback)
                result.pages_processed = page_result["processed"]
                result.units_created += page_result["units_created"]
                result.errors.extend(page_result["errors"])

            # Phase 3: Rebuild edges
            if rebuild_edges and self.edge_inference:
                logger.info(f"Rebuilding edges for guild {guild_id}")
                edge_result = await self.edge_inference.rebuild_edges_for_guild(
                    guild_id, batch_size=self.batch_size
                )
                result.edges_created = edge_result.get("edges_created", 0)

        except Exception as e:
            logger.exception(f"Backfill failed for guild {guild_id}: {e}")
            result.errors.append(str(e))

        result.duration_seconds = time.time() - start_time
        logger.info(
            f"Backfill complete for guild {guild_id}: "
            f"{result.units_created} units, {result.edges_created} edges, "
            f"{len(result.errors)} errors in {result.duration_seconds:.1f}s"
        )

        return result

    async def _backfill_sources(
        self,
        guild_id: str,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Backfill wiki sources to knowledge units.
        """
        result = {"processed": 0, "units_created": 0, "errors": []}

        # Get total count
        count_query = "SELECT COUNT(*) as count FROM wiki_sources WHERE guild_id = ?"
        count_row = await self.wiki_connection.fetch_one(count_query, (guild_id,))
        total = count_row["count"] if count_row else 0

        if total == 0:
            logger.info(f"No sources to backfill for guild {guild_id}")
            return result

        # Process in batches
        offset = 0
        while offset < total:
            query = """
            SELECT id, guild_id, source_type, title, content, metadata, ingested_at
            FROM wiki_sources
            WHERE guild_id = ?
            ORDER BY ingested_at
            LIMIT ? OFFSET ?
            """

            rows = await self.wiki_connection.fetch_all(
                query, (guild_id, self.batch_size, offset)
            )

            for row in rows:
                try:
                    units = await self._process_source(row)
                    result["units_created"] += len(units)
                except Exception as e:
                    result["errors"].append(f"Source {row['id']}: {e}")

                result["processed"] += 1

            offset += self.batch_size

            if progress_callback:
                progress_callback(BackfillProgress(
                    guild_id=guild_id,
                    phase="sources",
                    total_items=total,
                    processed_items=result["processed"],
                    units_created=result["units_created"],
                ))

        return result

    async def _process_source(self, row: Dict[str, Any]) -> List[KnowledgeUnit]:
        """
        Process a single wiki source into knowledge units.
        """
        import json

        guild_id = row["guild_id"]
        source_id = row["id"]
        content = row["content"]
        metadata = json.loads(row.get("metadata") or "{}")

        # Extract channel and date from metadata
        channel_name = metadata.get("channel_name")
        timestamp_str = metadata.get("timestamp")
        source_date = None
        if timestamp_str:
            try:
                source_date = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        # Extract knowledge units
        extraction = await self.extractor.extract_from_summary(
            guild_id=guild_id,
            summary_id=source_id,
            summary_text=content,
            channel_name=channel_name,
            summary_date=source_date,
            key_points=metadata.get("key_points", []),
            action_items=metadata.get("action_items", []),
        )

        # Optionally validate
        if self.enable_coherence_check and self.coherence_gate:
            for unit in extraction.units:
                validation = await self.coherence_gate.validate(unit)
                if not validation.approved:
                    logger.warning(f"Unit rejected by coherence gate: {unit.id}")
                    extraction.units.remove(unit)

        # Store units
        if extraction.units:
            await self.vector_store.store_units_batch(extraction.units)

        return extraction.units

    async def _backfill_pages(
        self,
        guild_id: str,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Backfill wiki pages that have content not from sources.

        This captures manually edited content and synthesis.
        """
        result = {"processed": 0, "units_created": 0, "errors": []}

        # Get pages with synthesis (manually created content)
        query = """
        SELECT id, guild_id, path, title, synthesis, updated_at
        FROM wiki_pages
        WHERE guild_id = ? AND synthesis IS NOT NULL AND synthesis != ''
        """

        rows = await self.wiki_connection.fetch_all(query, (guild_id,))
        total = len(rows)

        if total == 0:
            logger.info(f"No pages with synthesis to backfill for guild {guild_id}")
            return result

        for row in rows:
            try:
                units = await self._process_page(row)
                result["units_created"] += len(units)
            except Exception as e:
                result["errors"].append(f"Page {row['path']}: {e}")

            result["processed"] += 1

            if progress_callback:
                progress_callback(BackfillProgress(
                    guild_id=guild_id,
                    phase="pages",
                    total_items=total,
                    processed_items=result["processed"],
                    units_created=result["units_created"],
                ))

        return result

    async def _process_page(self, row: Dict[str, Any]) -> List[KnowledgeUnit]:
        """
        Process a wiki page synthesis into knowledge units.
        """
        guild_id = row["guild_id"]
        page_id = row["id"]
        path = row["path"]
        synthesis = row.get("synthesis") or ""

        if not synthesis:
            return []

        # Parse date
        updated_at = None
        if row.get("updated_at"):
            try:
                updated_at = datetime.fromisoformat(row["updated_at"])
            except (ValueError, TypeError):
                pass

        # Extract knowledge units from synthesis
        extraction = await self.extractor.extract_from_summary(
            guild_id=guild_id,
            summary_id=f"page-{page_id}",
            summary_text=synthesis,
            channel_name=path,  # Use path as channel identifier
            summary_date=updated_at,
        )

        # Mark as from synthesis
        for unit in extraction.units:
            unit.source_type = "wiki_synthesis"

        # Store units
        if extraction.units:
            await self.vector_store.store_units_batch(extraction.units)

        return extraction.units

    async def get_backfill_status(self, guild_id: str) -> Dict[str, Any]:
        """
        Get current backfill status for a guild.
        """
        # Count existing units
        unit_query = """
        SELECT COUNT(*) as count FROM wiki_knowledge_units WHERE guild_id = ?
        """
        unit_row = await self.vector_store.connection.fetch_one(unit_query, (guild_id,))
        unit_count = unit_row["count"] if unit_row else 0

        # Count sources
        source_query = """
        SELECT COUNT(*) as count FROM wiki_sources WHERE guild_id = ?
        """
        source_row = await self.wiki_connection.fetch_one(source_query, (guild_id,))
        source_count = source_row["count"] if source_row else 0

        # Count edges
        edge_query = """
        SELECT COUNT(*) as count FROM wiki_edges WHERE guild_id = ?
        """
        edge_row = await self.vector_store.connection.fetch_one(edge_query, (guild_id,))
        edge_count = edge_row["count"] if edge_row else 0

        return {
            "guild_id": guild_id,
            "knowledge_units": unit_count,
            "wiki_sources": source_count,
            "edges": edge_count,
            "estimated_coverage": min(1.0, unit_count / max(1, source_count * 5)),  # ~5 units per source
        }

    async def clear_guild_data(self, guild_id: str, confirm: bool = False) -> int:
        """
        Clear all RuVector data for a guild.

        USE WITH CAUTION - this deletes all knowledge units and edges.
        """
        if not confirm:
            raise ValueError("Must set confirm=True to clear data")

        deleted = 0

        # Delete edges
        edge_result = await self.vector_store.connection.execute(
            "DELETE FROM wiki_edges WHERE guild_id = ?", (guild_id,)
        )
        deleted += getattr(edge_result, 'rowcount', 0)

        # Delete learning signals
        signal_result = await self.vector_store.connection.execute(
            "DELETE FROM wiki_learning_signals WHERE guild_id = ?", (guild_id,)
        )
        deleted += getattr(signal_result, 'rowcount', 0)

        # Delete validations
        validation_result = await self.vector_store.connection.execute(
            "DELETE FROM wiki_coherence_validations WHERE guild_id = ?", (guild_id,)
        )
        deleted += getattr(validation_result, 'rowcount', 0)

        # Delete units
        unit_result = await self.vector_store.connection.execute(
            "DELETE FROM wiki_knowledge_units WHERE guild_id = ?", (guild_id,)
        )
        deleted += getattr(unit_result, 'rowcount', 0)

        logger.info(f"Cleared {deleted} RuVector records for guild {guild_id}")
        return deleted
