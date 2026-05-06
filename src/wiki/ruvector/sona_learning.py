"""
SONA Learning for RuVector (ADR-057 Phase 3).

Self-Optimizing Neural Attention system that learns from user interactions
to improve search relevance over time.

Tracks three tiers of signals:
1. Immediate: Per-query signals (clicks, dwell time)
2. Session: Per-user patterns (query refinements)
3. Long-term: System-wide patterns (content evolution)
"""

import logging
import math
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

from .models import (
    LearningSignal,
    SignalType,
)
from .vector_store import VectorStore

logger = logging.getLogger(__name__)


@dataclass
class RelevanceScore:
    """Calculated relevance score for a unit."""
    unit_id: str
    base_score: float
    click_boost: float
    dwell_boost: float
    recency_boost: float
    total_score: float


class SONALearning:
    """
    Self-Optimizing Neural Attention for relevance learning.

    ADR-057: Learns from user interactions to boost relevant content:
    - Frequently clicked results get higher relevance
    - High dwell time indicates valuable content
    - Recent content gets freshness boost
    - Query refinement patterns inform intent
    """

    def __init__(
        self,
        vector_store: VectorStore,
        click_decay_hours: float = 168,  # 1 week
        dwell_decay_hours: float = 336,  # 2 weeks
        recency_decay_days: float = 30,
        max_boost: float = 0.3,  # Maximum boost to apply
    ):
        """
        Initialize SONA learning.

        Args:
            vector_store: Vector store for signal storage
            click_decay_hours: Half-life for click signals
            dwell_decay_hours: Half-life for dwell signals
            recency_decay_days: Half-life for recency boost
            max_boost: Maximum boost to apply to base score
        """
        self.vector_store = vector_store
        self.click_decay_hours = click_decay_hours
        self.dwell_decay_hours = dwell_decay_hours
        self.recency_decay_days = recency_decay_days
        self.max_boost = max_boost

    # -------------------------------------------------------------------------
    # Signal Recording
    # -------------------------------------------------------------------------

    async def on_search_click(
        self,
        guild_id: str,
        query: str,
        unit_id: str,
        position: int,
        user_id: Optional[str] = None,
    ) -> None:
        """
        Record that a user clicked a search result.

        Higher position clicks (lower in list) indicate stronger relevance.
        """
        signal = LearningSignal(
            guild_id=guild_id,
            signal_type=SignalType.SEARCH_CLICK,
            unit_id=unit_id,
            context={
                "query": query,
                "position": position,
                "boost": 1.0 + (0.1 * max(0, 10 - position)),  # Boost for clicks on lower results
            },
            user_id=user_id,
        )

        await self.vector_store.record_signal(signal)
        logger.debug(f"Recorded search click: unit={unit_id}, position={position}")

    async def on_dwell(
        self,
        guild_id: str,
        unit_id: str,
        dwell_seconds: float,
        user_id: Optional[str] = None,
    ) -> None:
        """
        Record time spent viewing content.

        Longer dwell time indicates more valuable content.
        """
        # Normalize dwell time (diminishing returns after 60 seconds)
        normalized_dwell = min(dwell_seconds / 60.0, 3.0)  # Cap at 3 minutes

        signal = LearningSignal(
            guild_id=guild_id,
            signal_type=SignalType.DWELL,
            unit_id=unit_id,
            context={
                "dwell_seconds": dwell_seconds,
                "normalized_dwell": normalized_dwell,
                "boost": 0.1 * normalized_dwell,
            },
            user_id=user_id,
        )

        await self.vector_store.record_signal(signal)
        logger.debug(f"Recorded dwell: unit={unit_id}, seconds={dwell_seconds}")

    async def on_query_refinement(
        self,
        guild_id: str,
        original_query: str,
        refined_query: str,
        user_id: Optional[str] = None,
    ) -> None:
        """
        Record query refinement pattern.

        Helps understand user intent and query expansion/focus patterns.
        """
        # Determine refinement type
        if len(refined_query) > len(original_query):
            pattern = "expansion"
        elif len(refined_query) < len(original_query):
            pattern = "focus"
        else:
            pattern = "modification"

        signal = LearningSignal(
            guild_id=guild_id,
            signal_type=SignalType.REFINEMENT,
            unit_id=None,
            context={
                "original_query": original_query,
                "refined_query": refined_query,
                "pattern": pattern,
            },
            user_id=user_id,
        )

        await self.vector_store.record_signal(signal)
        logger.debug(f"Recorded refinement: {pattern}")

    async def on_feedback(
        self,
        guild_id: str,
        unit_id: str,
        feedback_type: str,  # helpful, not_helpful, report
        comment: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        """
        Record explicit user feedback.
        """
        boost = {
            "helpful": 0.2,
            "not_helpful": -0.2,
            "report": -0.5,
        }.get(feedback_type, 0.0)

        signal = LearningSignal(
            guild_id=guild_id,
            signal_type=SignalType.FEEDBACK,
            unit_id=unit_id,
            context={
                "feedback_type": feedback_type,
                "comment": comment,
                "boost": boost,
            },
            user_id=user_id,
        )

        await self.vector_store.record_signal(signal)
        logger.debug(f"Recorded feedback: unit={unit_id}, type={feedback_type}")

    async def on_page_view(
        self,
        guild_id: str,
        page_path: str,
        unit_ids: List[str],
        user_id: Optional[str] = None,
    ) -> None:
        """
        Record wiki page view (impacts all units on the page).
        """
        signal = LearningSignal(
            guild_id=guild_id,
            signal_type=SignalType.PAGE_VIEW,
            unit_id=None,
            context={
                "page_path": page_path,
                "unit_ids": unit_ids,
                "boost": 0.05,  # Small boost per view
            },
            user_id=user_id,
        )

        await self.vector_store.record_signal(signal)

    # -------------------------------------------------------------------------
    # Relevance Calculation
    # -------------------------------------------------------------------------

    async def get_relevance_boost(self, unit_id: str) -> float:
        """
        Calculate total relevance boost for a unit based on learned signals.

        Returns a value between 0 and max_boost.
        """
        signals = await self.vector_store.get_signals_for_unit(
            unit_id=unit_id,
            limit=100,
        )

        if not signals:
            return 0.0

        now = datetime.utcnow()
        total_boost = 0.0

        for signal in signals:
            if not signal.created_at:
                continue

            age_hours = (now - signal.created_at).total_seconds() / 3600
            context = signal.context or {}
            raw_boost = context.get("boost", 0.0)

            # Apply time decay based on signal type
            if signal.signal_type == SignalType.SEARCH_CLICK:
                decay = math.exp(-age_hours / self.click_decay_hours)
            elif signal.signal_type == SignalType.DWELL:
                decay = math.exp(-age_hours / self.dwell_decay_hours)
            elif signal.signal_type == SignalType.FEEDBACK:
                decay = math.exp(-age_hours / (self.click_decay_hours * 2))  # Slower decay
            else:
                decay = math.exp(-age_hours / self.click_decay_hours)

            total_boost += raw_boost * decay

        # Clamp to max_boost
        return min(max(total_boost, -self.max_boost), self.max_boost)

    async def get_relevance_scores(
        self,
        unit_ids: List[str],
        base_scores: Optional[Dict[str, float]] = None,
    ) -> List[RelevanceScore]:
        """
        Calculate relevance scores for multiple units.

        Args:
            unit_ids: Units to score
            base_scores: Optional base scores (e.g., from semantic search)

        Returns:
            List of RelevanceScore objects
        """
        base_scores = base_scores or {}
        results = []

        for unit_id in unit_ids:
            base = base_scores.get(unit_id, 1.0)
            boost = await self.get_relevance_boost(unit_id)

            # Get unit for recency calculation
            unit = await self.vector_store.get_unit(unit_id)
            recency_boost = 0.0
            if unit and unit.source_date:
                age_days = (datetime.utcnow() - unit.source_date).days
                recency_boost = 0.1 * math.exp(-age_days / self.recency_decay_days)

            total = base * (1 + boost + recency_boost)

            results.append(RelevanceScore(
                unit_id=unit_id,
                base_score=base,
                click_boost=boost,  # Simplified - includes all signal boosts
                dwell_boost=0.0,  # Included in click_boost
                recency_boost=recency_boost,
                total_score=total,
            ))

        return results

    async def rerank_results(
        self,
        results: List[Any],  # SearchResult
        guild_id: str,
    ) -> List[Any]:
        """
        Rerank search results using learned relevance.

        Args:
            results: Search results to rerank
            guild_id: Guild ID

        Returns:
            Reranked results
        """
        if not results:
            return results

        # Get relevance scores
        unit_ids = [r.unit_id for r in results]
        base_scores = {r.unit_id: r.score for r in results}

        scores = await self.get_relevance_scores(unit_ids, base_scores)
        score_map = {s.unit_id: s.total_score for s in scores}

        # Sort by total score
        reranked = sorted(
            results,
            key=lambda r: score_map.get(r.unit_id, r.score),
            reverse=True,
        )

        return reranked

    # -------------------------------------------------------------------------
    # Analytics
    # -------------------------------------------------------------------------

    async def get_learning_stats(self, guild_id: str) -> Dict[str, Any]:
        """
        Get statistics about learning signals.
        """
        query = """
        SELECT signal_type, COUNT(*) as count
        FROM wiki_learning_signals
        WHERE guild_id = ?
        GROUP BY signal_type
        """

        rows = await self.vector_store.connection.fetch_all(query, (guild_id,))
        signals_by_type = {row["signal_type"]: row["count"] for row in rows}

        # Get recent signal count
        query = """
        SELECT COUNT(*) as count
        FROM wiki_learning_signals
        WHERE guild_id = ? AND created_at > datetime('now', '-7 days')
        """
        row = await self.vector_store.connection.fetch_one(query, (guild_id,))
        recent_signals = row["count"] if row else 0

        # Get top clicked units
        query = """
        SELECT unit_id, COUNT(*) as clicks
        FROM wiki_learning_signals
        WHERE guild_id = ? AND signal_type = 'search_click' AND unit_id IS NOT NULL
        GROUP BY unit_id
        ORDER BY clicks DESC
        LIMIT 10
        """
        rows = await self.vector_store.connection.fetch_all(query, (guild_id,))
        top_clicked = [(row["unit_id"], row["clicks"]) for row in rows]

        return {
            "signals_by_type": signals_by_type,
            "total_signals": sum(signals_by_type.values()),
            "recent_signals_7d": recent_signals,
            "top_clicked_units": top_clicked,
        }

    async def cleanup_old_signals(
        self,
        guild_id: str,
        older_than_days: int = 90,
    ) -> int:
        """
        Clean up old learning signals.
        """
        query = """
        DELETE FROM wiki_learning_signals
        WHERE guild_id = ? AND created_at < datetime('now', ? || ' days')
        """

        result = await self.vector_store.connection.execute(
            query, (guild_id, f"-{older_than_days}")
        )

        # Get affected rows count
        return getattr(result, 'rowcount', 0)
