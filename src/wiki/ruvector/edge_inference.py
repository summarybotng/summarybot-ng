"""
GNN-style edge inference for RuVector (ADR-057 Phase 2).

Discovers relationships between knowledge units using:
1. Semantic similarity (embedding distance)
2. Temporal proximity (same time period)
3. Source correlation (same channel/discussion)
4. LLM classification (for high-confidence edges)
"""

import logging
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime, timedelta

from .models import (
    KnowledgeUnit,
    KnowledgeUnitType,
    Edge,
    EdgeType,
    SearchResult,
)
from .vector_store import VectorStore

if TYPE_CHECKING:
    from ...summarization.claude_client import ClaudeClient

logger = logging.getLogger(__name__)


EDGE_CLASSIFICATION_PROMPT = """Given two knowledge units, classify their relationship.

Unit A ({unit_a_type}): {unit_a_content}
Unit B ({unit_b_type}): {unit_b_content}

What is the relationship from A to B?
Options:
- relates_to: General topical relationship
- depends_on: A depends on or requires B
- contradicts: A conflicts with or contradicts B
- supersedes: A is newer information that replaces B
- supports: A provides evidence or support for B
- answers: A answers the question in B
- implements: A is an implementation of B
- none: No meaningful relationship

Return JSON: {{"relationship": "...", "confidence": 0.0-1.0, "reason": "..."}}"""


class EdgeInferenceEngine:
    """
    Infers relationships between knowledge units.

    Uses multiple signals to discover edges:
    - Semantic similarity from embeddings
    - Temporal patterns
    - Source/channel correlation
    - Optional LLM classification for ambiguous cases
    """

    def __init__(
        self,
        vector_store: VectorStore,
        claude_client: Optional["ClaudeClient"] = None,
        similarity_threshold: float = 0.75,
        temporal_window_hours: int = 24,
        use_llm_classification: bool = False,
    ):
        """
        Initialize the edge inference engine.

        Args:
            vector_store: Vector store for similarity search
            claude_client: Optional Claude client for LLM classification
            similarity_threshold: Minimum similarity for edge creation
            temporal_window_hours: Hours window for temporal proximity
            use_llm_classification: Whether to use LLM for edge classification
        """
        self.vector_store = vector_store
        self.claude_client = claude_client
        self.similarity_threshold = similarity_threshold
        self.temporal_window = timedelta(hours=temporal_window_hours)
        self.use_llm_classification = use_llm_classification and claude_client is not None

    async def infer_edges_for_unit(
        self,
        unit: KnowledgeUnit,
        max_edges: int = 10,
    ) -> List[Edge]:
        """
        Infer edges from a single unit to related units.

        Args:
            unit: The source unit
            max_edges: Maximum edges to create

        Returns:
            List of inferred edges
        """
        if not unit.embedding:
            logger.warning(f"Unit {unit.id} has no embedding, skipping edge inference")
            return []

        # Find semantically similar units
        similar = await self.vector_store.find_similar(
            unit_id=unit.id,
            limit=max_edges * 2,  # Over-fetch for filtering
            threshold=self.similarity_threshold,
            exclude_same_source=True,
        )

        edges = []
        for result in similar[:max_edges]:
            # Calculate edge weight from multiple signals
            weight = self._calculate_edge_weight(unit, result)

            if weight < self.similarity_threshold:
                continue

            # Determine edge type
            edge_type = await self._classify_edge(unit, result)

            edge = Edge(
                guild_id=unit.guild_id,
                from_unit_id=unit.id,
                to_unit_id=result.unit_id,
                edge_type=edge_type,
                weight=weight,
                inferred_by="gnn",
            )
            edges.append(edge)

        return edges

    async def rebuild_edges_for_guild(
        self,
        guild_id: str,
        batch_size: int = 100,
    ) -> Dict[str, int]:
        """
        Rebuild all edges for a guild.

        Useful for initial setup or after significant changes.

        Args:
            guild_id: Guild to rebuild edges for
            batch_size: Units to process per batch

        Returns:
            Statistics about edges created
        """
        stats = {"units_processed": 0, "edges_created": 0, "edges_removed": 0}

        # Get all units for guild (paginated)
        offset = 0
        while True:
            query = """
            SELECT id FROM wiki_knowledge_units
            WHERE guild_id = ? AND embedding IS NOT NULL
            LIMIT ? OFFSET ?
            """
            rows = await self.vector_store.connection.fetch_all(
                query, (guild_id, batch_size, offset)
            )

            if not rows:
                break

            for row in rows:
                unit = await self.vector_store.get_unit(row["id"])
                if not unit:
                    continue

                edges = await self.infer_edges_for_unit(unit)
                for edge in edges:
                    await self.vector_store.store_edge(edge)
                    stats["edges_created"] += 1

                stats["units_processed"] += 1

            offset += batch_size
            logger.info(f"Processed {stats['units_processed']} units, created {stats['edges_created']} edges")

        return stats

    def _calculate_edge_weight(
        self,
        from_unit: KnowledgeUnit,
        to_result: SearchResult,
    ) -> float:
        """
        Calculate edge weight from multiple signals.

        Combines:
        - Semantic similarity (primary)
        - Temporal proximity (boost for same time period)
        - Source correlation (boost for same channel)
        """
        # Start with semantic similarity
        weight = to_result.score

        # Temporal proximity boost
        if from_unit.source_date and to_result.source_date:
            time_diff = abs((from_unit.source_date - to_result.source_date).total_seconds())
            if time_diff < self.temporal_window.total_seconds():
                # Boost up to 10% for same time period
                temporal_boost = 0.1 * (1 - time_diff / self.temporal_window.total_seconds())
                weight = min(1.0, weight + temporal_boost)

        # Same channel boost
        if (from_unit.source_channel and to_result.source_channel and
            from_unit.source_channel == to_result.source_channel):
            weight = min(1.0, weight + 0.05)

        return weight

    async def _classify_edge(
        self,
        from_unit: KnowledgeUnit,
        to_result: SearchResult,
    ) -> EdgeType:
        """
        Classify the edge type between two units.
        """
        # Use LLM classification for high-value edges
        if self.use_llm_classification and to_result.score > 0.85:
            return await self._classify_with_llm(from_unit, to_result)

        # Heuristic classification based on unit types
        return self._classify_heuristic(from_unit, to_result)

    def _classify_heuristic(
        self,
        from_unit: KnowledgeUnit,
        to_result: SearchResult,
    ) -> EdgeType:
        """
        Classify edge type using heuristics.
        """
        from_type = from_unit.unit_type
        to_type = to_result.unit_type

        # Question → Answer patterns
        if from_type == KnowledgeUnitType.QUESTION:
            if to_type in [KnowledgeUnitType.CLAIM, KnowledgeUnitType.DECISION, KnowledgeUnitType.DEFINITION]:
                return EdgeType.ANSWERS

        # Answer → Question (reverse)
        if to_type == KnowledgeUnitType.QUESTION:
            if from_type in [KnowledgeUnitType.CLAIM, KnowledgeUnitType.DECISION]:
                return EdgeType.ANSWERS

        # Action item → Decision
        if from_type == KnowledgeUnitType.ACTION_ITEM:
            if to_type == KnowledgeUnitType.DECISION:
                return EdgeType.IMPLEMENTS

        # Decision → Claim support
        if from_type == KnowledgeUnitType.DECISION:
            if to_type == KnowledgeUnitType.CLAIM:
                return EdgeType.SUPPORTS

        # Temporal supersession
        if from_unit.source_date and to_result.source_date:
            if from_unit.source_date > to_result.source_date:
                # Very high similarity + newer = likely supersedes
                if to_result.score > 0.9:
                    return EdgeType.SUPERSEDES

        return EdgeType.RELATES_TO

    async def _classify_with_llm(
        self,
        from_unit: KnowledgeUnit,
        to_result: SearchResult,
    ) -> EdgeType:
        """
        Use LLM to classify edge type.
        """
        if not self.claude_client:
            return self._classify_heuristic(from_unit, to_result)

        try:
            prompt = EDGE_CLASSIFICATION_PROMPT.format(
                unit_a_type=from_unit.unit_type.value,
                unit_a_content=from_unit.content[:500],
                unit_b_type=to_result.unit_type.value,
                unit_b_content=to_result.content[:500],
            )

            response = await self.claude_client.generate(
                prompt=prompt,
                max_tokens=200,
                temperature=0.1,
            )

            # Parse response
            import json
            # Try to extract JSON from response
            response_text = response.strip()
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            result = json.loads(response_text)
            relationship = result.get("relationship", "relates_to")

            # Map to EdgeType
            type_map = {
                "relates_to": EdgeType.RELATES_TO,
                "depends_on": EdgeType.DEPENDS_ON,
                "contradicts": EdgeType.CONTRADICTS,
                "supersedes": EdgeType.SUPERSEDES,
                "supports": EdgeType.SUPPORTS,
                "answers": EdgeType.ANSWERS,
                "implements": EdgeType.IMPLEMENTS,
            }

            return type_map.get(relationship, EdgeType.RELATES_TO)

        except Exception as e:
            logger.warning(f"LLM edge classification failed: {e}")
            return self._classify_heuristic(from_unit, to_result)

    async def detect_contradictions(
        self,
        guild_id: str,
        threshold: float = 0.8,
    ) -> List[Dict[str, Any]]:
        """
        Detect potential contradictions in the knowledge base.

        Finds units that are semantically similar but might conflict.
        """
        contradictions = []

        # Get all decision and claim units
        query = """
        SELECT id FROM wiki_knowledge_units
        WHERE guild_id = ? AND unit_type IN ('decision', 'claim')
        AND embedding IS NOT NULL
        """
        rows = await self.vector_store.connection.fetch_all(query, (guild_id,))

        checked_pairs = set()

        for row in rows:
            unit = await self.vector_store.get_unit(row["id"])
            if not unit:
                continue

            # Find similar units
            similar = await self.vector_store.find_similar(
                unit_id=unit.id,
                limit=5,
                threshold=threshold,
                exclude_same_source=True,
            )

            for result in similar:
                # Skip if already checked
                pair_key = tuple(sorted([unit.id, result.unit_id]))
                if pair_key in checked_pairs:
                    continue
                checked_pairs.add(pair_key)

                # Check for potential contradiction
                # High similarity but different conclusions might indicate conflict
                if await self._might_contradict(unit, result):
                    contradictions.append({
                        "unit_a_id": unit.id,
                        "unit_a_content": unit.content,
                        "unit_b_id": result.unit_id,
                        "unit_b_content": result.content,
                        "similarity": result.score,
                        "type": "potential_contradiction",
                    })

        return contradictions

    async def _might_contradict(
        self,
        unit_a: KnowledgeUnit,
        unit_b: SearchResult,
    ) -> bool:
        """
        Check if two units might contradict each other.

        Simple heuristics - in production would use LLM.
        """
        content_a = unit_a.content.lower()
        content_b = unit_b.content.lower()

        # Look for negation patterns
        negation_words = ["not", "no", "never", "don't", "won't", "shouldn't", "can't", "instead of", "rather than"]

        a_has_negation = any(word in content_a for word in negation_words)
        b_has_negation = any(word in content_b for word in negation_words)

        # One has negation, other doesn't, but similar content = potential conflict
        if a_has_negation != b_has_negation:
            return True

        return False
