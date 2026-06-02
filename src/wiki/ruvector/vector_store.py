"""
Vector store for RuVector (ADR-057).

Stores and searches knowledge unit embeddings using SQLite.
Implements approximate nearest neighbor search for semantic retrieval.

Note: For production scale (>100K units), consider migrating to
dedicated vector databases like Pinecone, Weaviate, or pgvector.
"""

import logging
import json
import struct
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from .models import (
    KnowledgeUnit,
    KnowledgeUnitType,
    Edge,
    EdgeType,
    SearchResult,
    LearningSignal,
    SignalType,
    CoherenceValidation,
    ValidationStatus,
    ContinuityCheckpoint,
)
from .embeddings import EmbeddingService, EMBEDDING_DIMENSIONS

logger = logging.getLogger(__name__)


def serialize_embedding(embedding: List[float]) -> bytes:
    """Serialize embedding to bytes for SQLite BLOB storage."""
    return struct.pack(f'{len(embedding)}f', *embedding)


def deserialize_embedding(blob: bytes) -> List[float]:
    """Deserialize embedding from SQLite BLOB."""
    count = len(blob) // 4  # 4 bytes per float32
    return list(struct.unpack(f'{count}f', blob))


class VectorStore:
    """
    SQLite-backed vector store for knowledge units.

    ADR-057 Phase 1: Implements basic vector storage and brute-force
    similarity search. For large-scale deployments, this can be
    upgraded to use sqlite-vec or an external vector database.
    """

    def __init__(
        self,
        connection: Any,  # SQLiteConnection
        embedding_service: Optional[EmbeddingService] = None,
    ):
        """
        Initialize the vector store.

        Args:
            connection: SQLite database connection
            embedding_service: Service for generating embeddings
        """
        self.connection = connection
        self.embedding_service = embedding_service or EmbeddingService()

    # -------------------------------------------------------------------------
    # Knowledge Units
    # -------------------------------------------------------------------------

    async def store_unit(self, unit: KnowledgeUnit) -> str:
        """
        Store a knowledge unit with its embedding.

        Args:
            unit: Knowledge unit to store

        Returns:
            Unit ID
        """
        # Generate embedding if not provided
        if unit.embedding is None:
            result = await self.embedding_service.embed(unit.content)
            unit.embedding = result.embedding

        # Serialize embedding
        embedding_blob = serialize_embedding(unit.embedding) if unit.embedding else None

        # ADR-090: Include extraction_source and summary_id
        extraction_source = getattr(unit, 'extraction_source', None)
        if extraction_source is not None:
            from .models import ExtractionSource
            extraction_source = extraction_source.value if isinstance(extraction_source, ExtractionSource) else extraction_source

        query = """
        INSERT INTO wiki_knowledge_units (
            id, guild_id, content, unit_type, source_id, source_type,
            source_channel, source_date, embedding, embedding_model, confidence,
            extraction_source, summary_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            content = excluded.content,
            unit_type = excluded.unit_type,
            embedding = excluded.embedding,
            confidence = excluded.confidence,
            extraction_source = excluded.extraction_source,
            summary_id = excluded.summary_id,
            updated_at = datetime('now')
        """

        params = (
            unit.id,
            unit.guild_id,
            unit.content,
            unit.unit_type.value if isinstance(unit.unit_type, KnowledgeUnitType) else unit.unit_type,
            unit.source_id,
            unit.source_type,
            unit.source_channel,
            unit.source_date.isoformat() if unit.source_date else None,
            embedding_blob,
            unit.embedding_model,
            unit.confidence,
            extraction_source,
            getattr(unit, 'summary_id', None),
        )

        await self.connection.execute(query, params)
        return unit.id

    async def store_units_batch(self, units: List[KnowledgeUnit]) -> List[str]:
        """
        Store multiple knowledge units efficiently.

        Args:
            units: List of knowledge units

        Returns:
            List of unit IDs
        """
        if not units:
            return []

        # Batch generate embeddings for units without them
        units_needing_embedding = [u for u in units if u.embedding is None]
        if units_needing_embedding:
            texts = [u.content for u in units_needing_embedding]
            results = await self.embedding_service.embed_batch(texts)
            for unit, result in zip(units_needing_embedding, results):
                unit.embedding = result.embedding

        # Store all units
        ids = []
        for unit in units:
            unit_id = await self.store_unit(unit)
            ids.append(unit_id)

        return ids

    async def get_unit(self, unit_id: str) -> Optional[KnowledgeUnit]:
        """Get a knowledge unit by ID."""
        query = "SELECT * FROM wiki_knowledge_units WHERE id = ?"
        row = await self.connection.fetch_one(query, (unit_id,))
        return self._row_to_unit(row) if row else None

    async def get_units_by_source(
        self,
        guild_id: str,
        source_id: str,
    ) -> List[KnowledgeUnit]:
        """Get all units from a specific source."""
        query = """
        SELECT * FROM wiki_knowledge_units
        WHERE guild_id = ? AND source_id = ?
        ORDER BY created_at
        """
        rows = await self.connection.fetch_all(query, (guild_id, source_id))
        return [self._row_to_unit(row) for row in rows]

    async def get_units_by_summary_id(
        self,
        guild_id: str,
        summary_id: str,
    ) -> List[KnowledgeUnit]:
        """
        Get all units extracted from a specific summary.

        ADR-118: Used to check if knowledge units already exist for a summary
        before triggering extraction, preventing duplicates during rolling
        schedule updates.

        Args:
            guild_id: Guild ID
            summary_id: Source summary ID

        Returns:
            List of existing knowledge units for this summary
        """
        query = """
        SELECT * FROM wiki_knowledge_units
        WHERE guild_id = ? AND summary_id = ?
        ORDER BY created_at
        """
        rows = await self.connection.fetch_all(query, (guild_id, summary_id))
        return [self._row_to_unit(row) for row in rows]

    async def count_units_by_summary_id(
        self,
        guild_id: str,
        summary_id: str,
    ) -> int:
        """
        Count units for a summary without loading full objects.

        ADR-118: Lightweight check for deduplication guard clause.
        """
        query = """
        SELECT COUNT(*) as count FROM wiki_knowledge_units
        WHERE guild_id = ? AND summary_id = ?
        """
        row = await self.connection.fetch_one(query, (guild_id, summary_id))
        return row["count"] if row else 0

    async def delete_unit(self, unit_id: str) -> bool:
        """Delete a knowledge unit and its edges."""
        # Delete edges first
        await self.connection.execute(
            "DELETE FROM wiki_edges WHERE from_unit_id = ? OR to_unit_id = ?",
            (unit_id, unit_id)
        )

        # Delete unit
        result = await self.connection.execute(
            "DELETE FROM wiki_knowledge_units WHERE id = ?",
            (unit_id,)
        )
        return True

    def _row_to_unit(self, row: Dict[str, Any]) -> KnowledgeUnit:
        """Convert database row to KnowledgeUnit."""
        embedding = None
        if row.get("embedding"):
            embedding = deserialize_embedding(row["embedding"])

        source_date = None
        if row.get("source_date"):
            try:
                source_date = datetime.fromisoformat(row["source_date"])
            except (ValueError, TypeError):
                pass

        return KnowledgeUnit(
            id=row["id"],
            guild_id=row["guild_id"],
            content=row["content"],
            unit_type=KnowledgeUnitType(row["unit_type"]),
            source_id=row["source_id"],
            source_type=row["source_type"],
            source_channel=row.get("source_channel"),
            source_date=source_date,
            embedding=embedding,
            embedding_model=row.get("embedding_model", "text-embedding-3-small"),
            confidence=row.get("confidence", 1.0),
            created_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row.get("updated_at") else None,
        )

    # -------------------------------------------------------------------------
    # Semantic Search
    # -------------------------------------------------------------------------

    async def search(
        self,
        query: str,
        guild_id: str,
        limit: int = 10,
        threshold: float = 0.7,
        unit_types: Optional[List[KnowledgeUnitType]] = None,
        channel: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> List[SearchResult]:
        """
        Semantic search for knowledge units.

        Args:
            query: Search query text
            guild_id: Guild to search in
            limit: Maximum results to return
            threshold: Minimum similarity threshold (0-1)
            unit_types: Filter by unit types
            channel: Filter by source channel
            date_from: Filter by date range start
            date_to: Filter by date range end

        Returns:
            List of SearchResult objects sorted by similarity
        """
        # Generate query embedding
        query_result = await self.embedding_service.embed(query)
        query_embedding = query_result.embedding

        # Build filter conditions
        conditions = ["guild_id = ?"]
        params: List[Any] = [guild_id]

        if unit_types:
            placeholders = ",".join("?" * len(unit_types))
            conditions.append(f"unit_type IN ({placeholders})")
            params.extend([ut.value for ut in unit_types])

        if channel:
            conditions.append("source_channel = ?")
            params.append(channel)

        if date_from:
            conditions.append("source_date >= ?")
            params.append(date_from.isoformat())

        if date_to:
            conditions.append("source_date <= ?")
            params.append(date_to.isoformat())

        where_clause = " AND ".join(conditions)

        # Fetch candidates (brute force for now)
        # For production, use sqlite-vec or external vector DB
        query_sql = f"""
        SELECT id, content, unit_type, source_id, source_channel, source_date, embedding
        FROM wiki_knowledge_units
        WHERE {where_clause} AND embedding IS NOT NULL
        """

        rows = await self.connection.fetch_all(query_sql, tuple(params))

        # Calculate similarities
        results: List[Tuple[float, Dict[str, Any]]] = []
        for row in rows:
            if not row.get("embedding"):
                continue

            unit_embedding = deserialize_embedding(row["embedding"])
            similarity = self.embedding_service.cosine_similarity(
                query_embedding, unit_embedding
            )

            if similarity >= threshold:
                results.append((similarity, row))

        # Sort by similarity and limit
        results.sort(key=lambda x: x[0], reverse=True)
        results = results[:limit]

        # Convert to SearchResult objects
        search_results = []
        for similarity, row in results:
            source_date = None
            if row.get("source_date"):
                try:
                    source_date = datetime.fromisoformat(row["source_date"])
                except (ValueError, TypeError):
                    pass

            search_results.append(SearchResult(
                unit_id=row["id"],
                content=row["content"],
                unit_type=KnowledgeUnitType(row["unit_type"]),
                score=similarity,
                source_id=row["source_id"],
                source_channel=row.get("source_channel"),
                source_date=source_date,
            ))

        return search_results

    async def find_similar(
        self,
        unit_id: str,
        limit: int = 10,
        threshold: float = 0.7,
        exclude_same_source: bool = True,
    ) -> List[SearchResult]:
        """
        Find units similar to a given unit.

        Args:
            unit_id: ID of unit to find similar units for
            limit: Maximum results
            threshold: Minimum similarity
            exclude_same_source: Exclude units from same source

        Returns:
            List of similar units
        """
        unit = await self.get_unit(unit_id)
        if not unit or not unit.embedding:
            return []

        # Build query
        conditions = ["guild_id = ?", "id != ?", "embedding IS NOT NULL"]
        params: List[Any] = [unit.guild_id, unit_id]

        if exclude_same_source:
            conditions.append("source_id != ?")
            params.append(unit.source_id)

        where_clause = " AND ".join(conditions)

        query = f"""
        SELECT id, content, unit_type, source_id, source_channel, source_date, embedding
        FROM wiki_knowledge_units
        WHERE {where_clause}
        """

        rows = await self.connection.fetch_all(query, tuple(params))

        # Calculate similarities
        results: List[Tuple[float, Dict[str, Any]]] = []
        for row in rows:
            if not row.get("embedding"):
                continue

            other_embedding = deserialize_embedding(row["embedding"])
            similarity = self.embedding_service.cosine_similarity(
                unit.embedding, other_embedding
            )

            if similarity >= threshold:
                results.append((similarity, row))

        # Sort and limit
        results.sort(key=lambda x: x[0], reverse=True)
        results = results[:limit]

        # Convert to SearchResult
        search_results = []
        for similarity, row in results:
            source_date = None
            if row.get("source_date"):
                try:
                    source_date = datetime.fromisoformat(row["source_date"])
                except (ValueError, TypeError):
                    pass

            search_results.append(SearchResult(
                unit_id=row["id"],
                content=row["content"],
                unit_type=KnowledgeUnitType(row["unit_type"]),
                score=similarity,
                source_id=row["source_id"],
                source_channel=row.get("source_channel"),
                source_date=source_date,
            ))

        return search_results

    # -------------------------------------------------------------------------
    # Edges (Relationships)
    # -------------------------------------------------------------------------

    async def store_edge(self, edge: Edge) -> int:
        """Store a relationship edge between units."""
        query = """
        INSERT INTO wiki_edges (
            guild_id, from_unit_id, to_unit_id, edge_type, weight, inferred_by
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id, from_unit_id, to_unit_id, edge_type) DO UPDATE SET
            weight = excluded.weight,
            inferred_by = excluded.inferred_by
        """

        result = await self.connection.execute(query, (
            edge.guild_id,
            edge.from_unit_id,
            edge.to_unit_id,
            edge.edge_type.value if isinstance(edge.edge_type, EdgeType) else edge.edge_type,
            edge.weight,
            edge.inferred_by,
        ))

        return result.lastrowid if hasattr(result, 'lastrowid') else 0

    async def get_edges_from(
        self,
        unit_id: str,
        edge_types: Optional[List[EdgeType]] = None,
    ) -> List[Edge]:
        """Get outbound edges from a unit."""
        conditions = ["from_unit_id = ?"]
        params: List[Any] = [unit_id]

        if edge_types:
            placeholders = ",".join("?" * len(edge_types))
            conditions.append(f"edge_type IN ({placeholders})")
            params.extend([et.value for et in edge_types])

        query = f"""
        SELECT * FROM wiki_edges WHERE {' AND '.join(conditions)}
        """

        rows = await self.connection.fetch_all(query, tuple(params))
        return [self._row_to_edge(row) for row in rows]

    async def get_edges_to(
        self,
        unit_id: str,
        edge_types: Optional[List[EdgeType]] = None,
    ) -> List[Edge]:
        """Get inbound edges to a unit."""
        conditions = ["to_unit_id = ?"]
        params: List[Any] = [unit_id]

        if edge_types:
            placeholders = ",".join("?" * len(edge_types))
            conditions.append(f"edge_type IN ({placeholders})")
            params.extend([et.value for et in edge_types])

        query = f"""
        SELECT * FROM wiki_edges WHERE {' AND '.join(conditions)}
        """

        rows = await self.connection.fetch_all(query, tuple(params))
        return [self._row_to_edge(row) for row in rows]

    def _row_to_edge(self, row: Dict[str, Any]) -> Edge:
        """Convert database row to Edge."""
        return Edge(
            id=row.get("id"),
            guild_id=row["guild_id"],
            from_unit_id=row["from_unit_id"],
            to_unit_id=row["to_unit_id"],
            edge_type=EdgeType(row["edge_type"]),
            weight=row.get("weight", 1.0),
            inferred_by=row.get("inferred_by", "gnn"),
            created_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else None,
        )

    # -------------------------------------------------------------------------
    # Learning Signals
    # -------------------------------------------------------------------------

    async def record_signal(self, signal: LearningSignal) -> int:
        """Record a learning signal for SONA."""
        query = """
        INSERT INTO wiki_learning_signals (
            guild_id, signal_type, unit_id, context, user_id
        ) VALUES (?, ?, ?, ?, ?)
        """

        result = await self.connection.execute(query, (
            signal.guild_id,
            signal.signal_type.value if isinstance(signal.signal_type, SignalType) else signal.signal_type,
            signal.unit_id,
            json.dumps(signal.context),
            signal.user_id,
        ))

        return result.lastrowid if hasattr(result, 'lastrowid') else 0

    async def get_signals_for_unit(
        self,
        unit_id: str,
        signal_types: Optional[List[SignalType]] = None,
        limit: int = 100,
    ) -> List[LearningSignal]:
        """Get learning signals for a unit."""
        conditions = ["unit_id = ?"]
        params: List[Any] = [unit_id]

        if signal_types:
            placeholders = ",".join("?" * len(signal_types))
            conditions.append(f"signal_type IN ({placeholders})")
            params.extend([st.value for st in signal_types])

        query = f"""
        SELECT * FROM wiki_learning_signals
        WHERE {' AND '.join(conditions)}
        ORDER BY created_at DESC
        LIMIT ?
        """
        params.append(limit)

        rows = await self.connection.fetch_all(query, tuple(params))
        return [self._row_to_signal(row) for row in rows]

    def _row_to_signal(self, row: Dict[str, Any]) -> LearningSignal:
        """Convert database row to LearningSignal."""
        context = {}
        if row.get("context"):
            try:
                context = json.loads(row["context"])
            except json.JSONDecodeError:
                pass

        return LearningSignal(
            id=row.get("id"),
            guild_id=row["guild_id"],
            signal_type=SignalType(row["signal_type"]),
            unit_id=row.get("unit_id"),
            context=context,
            user_id=row.get("user_id"),
            created_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else None,
        )

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    async def get_stats(self, guild_id: str) -> Dict[str, Any]:
        """Get statistics for a guild's knowledge store."""
        stats = {}

        # Unit counts by type
        query = """
        SELECT unit_type, COUNT(*) as count
        FROM wiki_knowledge_units
        WHERE guild_id = ?
        GROUP BY unit_type
        """
        rows = await self.connection.fetch_all(query, (guild_id,))
        stats["units_by_type"] = {row["unit_type"]: row["count"] for row in rows}
        stats["total_units"] = sum(stats["units_by_type"].values())

        # Edge counts by type
        query = """
        SELECT edge_type, COUNT(*) as count
        FROM wiki_edges
        WHERE guild_id = ?
        GROUP BY edge_type
        """
        rows = await self.connection.fetch_all(query, (guild_id,))
        stats["edges_by_type"] = {row["edge_type"]: row["count"] for row in rows}
        stats["total_edges"] = sum(stats["edges_by_type"].values())

        # Signal counts
        query = """
        SELECT COUNT(*) as count FROM wiki_learning_signals WHERE guild_id = ?
        """
        row = await self.connection.fetch_one(query, (guild_id,))
        stats["total_signals"] = row["count"] if row else 0

        # Units with embeddings
        query = """
        SELECT COUNT(*) as count FROM wiki_knowledge_units
        WHERE guild_id = ? AND embedding IS NOT NULL
        """
        row = await self.connection.fetch_one(query, (guild_id,))
        stats["units_with_embeddings"] = row["count"] if row else 0

        return stats
