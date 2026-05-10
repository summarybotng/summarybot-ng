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

from .models import KnowledgeUnit, KnowledgeUnitType, ExtractionResult, ExtractionSource
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

    async def backfill_from_summaries(
        self,
        guild_id: str,
        use_llm: bool = False,
        max_summaries: Optional[int] = None,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        ADR-090: Backfill KUs from stored_summaries.

        This extracts knowledge units from historical summaries that were created
        before inline extraction was enabled.

        Args:
            guild_id: Guild to backfill
            use_llm: If True, use LLM to extract KUs (more comprehensive but slower).
                     If False, convert existing key_points/decisions/action_items (faster).
            max_summaries: Maximum summaries to process (None for all)
            progress_callback: Optional callback for progress updates

        Returns:
            Dict with statistics
        """
        import json
        from ...models.base import generate_id

        result = {
            "processed": 0,
            "skipped": 0,
            "units_created": 0,
            "errors": [],
        }

        # Find summaries that don't have KUs yet
        query = """
        SELECT ss.id, ss.guild_id, ss.summary_json, ss.created_at,
               ss.source_channel_ids
        FROM stored_summaries ss
        WHERE ss.guild_id = ?
          AND NOT EXISTS (
            SELECT 1 FROM wiki_knowledge_units ku
            WHERE ku.summary_id = ss.id
          )
        ORDER BY ss.created_at DESC
        """
        params = [guild_id]

        if max_summaries:
            query += " LIMIT ?"
            params.append(max_summaries)

        rows = await self.wiki_connection.fetch_all(query, tuple(params))
        total = len(rows)

        if total == 0:
            logger.info(f"No summaries to backfill for guild {guild_id}")
            return result

        logger.info(f"Backfilling {total} summaries for guild {guild_id}")

        for row in rows:
            try:
                summary_id = row["id"]
                summary_json = row.get("summary_json")

                if not summary_json:
                    result["skipped"] += 1
                    continue

                summary_data = json.loads(summary_json)

                # Get channel info
                channel_ids = json.loads(row.get("source_channel_ids") or "[]")
                channel_name = channel_ids[0] if channel_ids else None

                # Parse date
                created_at = None
                if row.get("created_at"):
                    try:
                        created_at = datetime.fromisoformat(row["created_at"])
                    except (ValueError, TypeError):
                        pass

                if use_llm:
                    # Use LLM extraction (more comprehensive)
                    units = await self._extract_units_with_llm(
                        guild_id=guild_id,
                        summary_id=summary_id,
                        summary_data=summary_data,
                        channel_name=channel_name,
                        created_at=created_at,
                    )
                else:
                    # Convert existing data to KUs (faster, no LLM)
                    units = self._convert_summary_to_units(
                        guild_id=guild_id,
                        summary_id=summary_id,
                        summary_data=summary_data,
                        channel_name=channel_name,
                        created_at=created_at,
                    )

                # Store units
                if units:
                    await self.vector_store.store_units_batch(units)
                    result["units_created"] += len(units)

                result["processed"] += 1

                if progress_callback:
                    progress_callback(BackfillProgress(
                        guild_id=guild_id,
                        phase="summaries",
                        total_items=total,
                        processed_items=result["processed"],
                        units_created=result["units_created"],
                    ))

            except Exception as e:
                result["errors"].append(f"Summary {row['id']}: {e}")
                logger.warning(f"Error backfilling summary {row['id']}: {e}")

        logger.info(
            f"Summary backfill complete for guild {guild_id}: "
            f"{result['processed']} processed, {result['units_created']} units created"
        )

        return result

    def _convert_summary_to_units(
        self,
        guild_id: str,
        summary_id: str,
        summary_data: Dict[str, Any],
        channel_name: Optional[str],
        created_at: Optional[datetime],
    ) -> List[KnowledgeUnit]:
        """
        ADR-090: Convert existing summary data to KUs without LLM.

        Uses key_points, decisions (referenced_decisions), and action_items
        already extracted during summarization.
        """
        from ...models.base import generate_id

        units = []

        # Convert key_points to claims
        key_points = summary_data.get("key_points", [])
        for kp in key_points:
            if isinstance(kp, str) and kp.strip():
                units.append(KnowledgeUnit(
                    id=generate_id(),
                    guild_id=guild_id,
                    content=kp.strip(),
                    unit_type=KnowledgeUnitType.CLAIM,
                    source_id=summary_id,
                    source_type="summary",
                    source_channel=channel_name,
                    source_date=created_at,
                    confidence=0.9,  # Slightly lower since indirect extraction
                    extraction_source=ExtractionSource.BACKFILL,
                    summary_id=summary_id,
                ))

        # Convert referenced_key_points (with confidence)
        ref_key_points = summary_data.get("referenced_key_points", [])
        for rkp in ref_key_points:
            if isinstance(rkp, dict) and rkp.get("text"):
                units.append(KnowledgeUnit(
                    id=generate_id(),
                    guild_id=guild_id,
                    content=rkp["text"],
                    unit_type=KnowledgeUnitType.CLAIM,
                    source_id=summary_id,
                    source_type="summary",
                    source_channel=channel_name,
                    source_date=created_at,
                    confidence=rkp.get("confidence", 0.9),
                    extraction_source=ExtractionSource.BACKFILL,
                    summary_id=summary_id,
                ))

        # Convert decisions
        ref_decisions = summary_data.get("referenced_decisions", [])
        for dec in ref_decisions:
            if isinstance(dec, dict) and dec.get("text"):
                units.append(KnowledgeUnit(
                    id=generate_id(),
                    guild_id=guild_id,
                    content=dec["text"],
                    unit_type=KnowledgeUnitType.DECISION,
                    source_id=summary_id,
                    source_type="summary",
                    source_channel=channel_name,
                    source_date=created_at,
                    confidence=dec.get("confidence", 0.9),
                    extraction_source=ExtractionSource.BACKFILL,
                    summary_id=summary_id,
                ))

        # Convert action items
        action_items = summary_data.get("action_items", [])
        for item in action_items:
            description = ""
            if isinstance(item, dict):
                description = item.get("description", "")
            elif isinstance(item, str):
                description = item

            if description.strip():
                units.append(KnowledgeUnit(
                    id=generate_id(),
                    guild_id=guild_id,
                    content=description.strip(),
                    unit_type=KnowledgeUnitType.ACTION_ITEM,
                    source_id=summary_id,
                    source_type="summary",
                    source_channel=channel_name,
                    source_date=created_at,
                    confidence=0.95,
                    extraction_source=ExtractionSource.BACKFILL,
                    summary_id=summary_id,
                ))

        # Convert technical terms to definitions
        tech_terms = summary_data.get("technical_terms", [])
        for term in tech_terms:
            if isinstance(term, dict) and term.get("term") and term.get("definition"):
                content = f"{term['term']}: {term['definition']}"
                units.append(KnowledgeUnit(
                    id=generate_id(),
                    guild_id=guild_id,
                    content=content,
                    unit_type=KnowledgeUnitType.DEFINITION,
                    source_id=summary_id,
                    source_type="summary",
                    source_channel=channel_name,
                    source_date=created_at,
                    confidence=0.95,
                    extraction_source=ExtractionSource.BACKFILL,
                    summary_id=summary_id,
                ))

        return units

    async def _extract_units_with_llm(
        self,
        guild_id: str,
        summary_id: str,
        summary_data: Dict[str, Any],
        channel_name: Optional[str],
        created_at: Optional[datetime],
    ) -> List[KnowledgeUnit]:
        """
        ADR-090: Extract KUs using LLM (more comprehensive).

        Uses the KnowledgeExtractor to re-extract from summary text.
        """
        summary_text = summary_data.get("summary_text", "")
        key_points = [
            kp if isinstance(kp, str) else kp.get("text", "")
            for kp in summary_data.get("key_points", [])
        ]
        action_items = [
            item.get("description", "") if isinstance(item, dict) else item
            for item in summary_data.get("action_items", [])
        ]

        extraction = await self.extractor.extract_from_summary(
            guild_id=guild_id,
            summary_id=summary_id,
            summary_text=summary_text,
            channel_name=channel_name,
            summary_date=created_at,
            key_points=key_points,
            action_items=action_items,
        )

        # Mark all units as backfill
        for unit in extraction.units:
            unit.extraction_source = ExtractionSource.BACKFILL
            unit.summary_id = summary_id

        return extraction.units
