"""
Wiki view renderers for RuVector (ADR-057 Phase 2, ADR-087).

Generates wiki page content from RuVector knowledge units.
Supports multiple view types:
- Topic pages: Semantic clustering of related content
- Daily digest: Cross-channel summary for a day
- Weekly rollup: Theme clustering over a week
- Decision log: Filtered view of decisions
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from .models import (
    KnowledgeUnit,
    KnowledgeUnitType,
    SearchResult,
)
from .vector_store import VectorStore

logger = logging.getLogger(__name__)


@dataclass
class RenderedView:
    """Result of rendering a wiki view."""
    title: str
    content: str
    source_units: List[str] = field(default_factory=list)  # Unit IDs used
    generated_at: datetime = field(default_factory=datetime.utcnow)
    view_type: str = "topic"
    cache_key: Optional[str] = None


class WikiViewRenderer:
    """
    Renders wiki views from RuVector knowledge units.

    ADR-087: Wiki pages become rendered views from the knowledge graph,
    not the primary store. This enables flexible granularity at query time.
    """

    def __init__(self, vector_store: VectorStore):
        """
        Initialize the view renderer.

        Args:
            vector_store: Vector store for querying knowledge units
        """
        self.vector_store = vector_store

    async def render_topic_page(
        self,
        guild_id: str,
        topic: str,
        max_units: int = 30,
        include_related: bool = True,
    ) -> RenderedView:
        """
        Render a topic page from semantically related units.

        Args:
            guild_id: Guild ID
            topic: Topic to render page for
            max_units: Maximum units to include
            include_related: Whether to include related topics section

        Returns:
            RenderedView with markdown content
        """
        # Search for units related to the topic
        results = await self.vector_store.search(
            query=topic,
            guild_id=guild_id,
            limit=max_units,
            threshold=0.6,
        )

        if not results:
            return RenderedView(
                title=topic.title(),
                content=f"# {topic.title()}\n\n*No content found for this topic yet.*\n",
                view_type="topic",
            )

        # Group by unit type
        claims = [r for r in results if r.unit_type == KnowledgeUnitType.CLAIM]
        decisions = [r for r in results if r.unit_type == KnowledgeUnitType.DECISION]
        questions = [r for r in results if r.unit_type == KnowledgeUnitType.QUESTION]
        action_items = [r for r in results if r.unit_type == KnowledgeUnitType.ACTION_ITEM]
        definitions = [r for r in results if r.unit_type == KnowledgeUnitType.DEFINITION]

        # Build content
        content = f"# {topic.title()}\n\n"
        content += f"*Generated from {len(results)} knowledge units*\n\n"

        # Definitions first
        if definitions:
            content += "## Definitions\n\n"
            for d in definitions[:5]:
                content += f"- {d.content}\n"
            content += "\n"

        # Key information (claims)
        if claims:
            content += "## Key Information\n\n"
            for c in claims[:10]:
                channel = f" ({c.source_channel})" if c.source_channel else ""
                content += f"- {c.content}{channel}\n"
            content += "\n"

        # Decisions
        if decisions:
            content += "## Decisions\n\n"
            for d in decisions[:5]:
                date = d.source_date.strftime("%Y-%m-%d") if d.source_date else "Unknown"
                content += f"- **{date}**: {d.content}\n"
            content += "\n"

        # Open questions
        if questions:
            content += "## Open Questions\n\n"
            for q in questions[:5]:
                content += f"- {q.content}\n"
            content += "\n"

        # Action items
        if action_items:
            content += "## Action Items\n\n"
            for a in action_items[:5]:
                content += f"- [ ] {a.content}\n"
            content += "\n"

        # Related topics
        if include_related:
            related = await self._find_related_topics(guild_id, results)
            if related:
                content += "## Related Topics\n\n"
                for r in related[:5]:
                    content += f"- [{r}](topics/{self._slugify(r)}.md)\n"

        return RenderedView(
            title=topic.title(),
            content=content,
            source_units=[r.unit_id for r in results],
            view_type="topic",
            cache_key=f"topic:{guild_id}:{self._slugify(topic)}",
        )

    async def render_daily_digest(
        self,
        guild_id: str,
        date: datetime,
        include_all_channels: bool = True,
    ) -> RenderedView:
        """
        Render a daily cross-channel digest.

        ADR-087: Aggregates knowledge units from all channels for a day.

        Args:
            guild_id: Guild ID
            date: Date to render digest for
            include_all_channels: Whether to include all channels

        Returns:
            RenderedView with markdown content
        """
        # Query units for the date
        date_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        date_end = date_start + timedelta(days=1)

        query = """
        SELECT * FROM wiki_knowledge_units
        WHERE guild_id = ? AND source_date >= ? AND source_date < ?
        ORDER BY source_date
        """

        rows = await self.vector_store.connection.fetch_all(
            query, (guild_id, date_start.isoformat(), date_end.isoformat())
        )

        units = [self.vector_store._row_to_unit(row) for row in rows]

        if not units:
            return RenderedView(
                title=f"Daily Digest - {date.strftime('%Y-%m-%d')}",
                content=f"# Daily Digest - {date.strftime('%A, %B %d, %Y')}\n\n*No activity recorded for this day.*\n",
                view_type="daily_digest",
            )

        # Group by channel
        by_channel: Dict[str, List[KnowledgeUnit]] = {}
        for unit in units:
            channel = unit.source_channel or "general"
            if channel not in by_channel:
                by_channel[channel] = []
            by_channel[channel].append(unit)

        # Build content
        content = f"# Daily Digest - {date.strftime('%A, %B %d, %Y')}\n\n"
        content += f"*{len(units)} items across {len(by_channel)} channels*\n\n"

        # Summary section - key decisions and action items
        all_decisions = [u for u in units if u.unit_type == KnowledgeUnitType.DECISION]
        all_actions = [u for u in units if u.unit_type == KnowledgeUnitType.ACTION_ITEM]

        if all_decisions:
            content += "## Key Decisions\n\n"
            for d in all_decisions[:5]:
                channel = f" (#{d.source_channel})" if d.source_channel else ""
                content += f"- {d.content}{channel}\n"
            content += "\n"

        if all_actions:
            content += "## Action Items\n\n"
            for a in all_actions[:10]:
                channel = f" (#{a.source_channel})" if a.source_channel else ""
                content += f"- [ ] {a.content}{channel}\n"
            content += "\n"

        # Per-channel breakdown
        content += "## By Channel\n\n"
        for channel, channel_units in sorted(by_channel.items()):
            content += f"### #{channel}\n\n"
            for unit in channel_units[:5]:
                type_emoji = {
                    KnowledgeUnitType.CLAIM: "📌",
                    KnowledgeUnitType.DECISION: "✅",
                    KnowledgeUnitType.QUESTION: "❓",
                    KnowledgeUnitType.ACTION_ITEM: "📋",
                }.get(unit.unit_type, "•")
                content += f"{type_emoji} {unit.content}\n"
            if len(channel_units) > 5:
                content += f"*...and {len(channel_units) - 5} more items*\n"
            content += "\n"

        return RenderedView(
            title=f"Daily Digest - {date.strftime('%Y-%m-%d')}",
            content=content,
            source_units=[u.id for u in units],
            view_type="daily_digest",
            cache_key=f"daily:{guild_id}:{date.strftime('%Y-%m-%d')}",
        )

    async def render_weekly_rollup(
        self,
        guild_id: str,
        week_start: datetime,
    ) -> RenderedView:
        """
        Render a weekly rollup with theme clustering.

        ADR-087: Aggregates and clusters a week's content.

        Args:
            guild_id: Guild ID
            week_start: Start of week (Monday)

        Returns:
            RenderedView with markdown content
        """
        week_end = week_start + timedelta(days=7)

        query = """
        SELECT * FROM wiki_knowledge_units
        WHERE guild_id = ? AND source_date >= ? AND source_date < ?
        ORDER BY source_date
        """

        rows = await self.vector_store.connection.fetch_all(
            query, (guild_id, week_start.isoformat(), week_end.isoformat())
        )

        units = [self.vector_store._row_to_unit(row) for row in rows]

        if not units:
            return RenderedView(
                title=f"Week of {week_start.strftime('%B %d, %Y')}",
                content=f"# Week of {week_start.strftime('%B %d, %Y')}\n\n*No activity recorded for this week.*\n",
                view_type="weekly_rollup",
            )

        # Build content
        content = f"# Week of {week_start.strftime('%B %d, %Y')}\n\n"
        content += f"*{len(units)} items recorded*\n\n"

        # Count by type
        type_counts = {}
        for unit in units:
            type_name = unit.unit_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1

        content += "## Overview\n\n"
        content += "| Type | Count |\n|------|-------|\n"
        for type_name, count in sorted(type_counts.items()):
            content += f"| {type_name.title()} | {count} |\n"
        content += "\n"

        # Decisions for the week
        decisions = [u for u in units if u.unit_type == KnowledgeUnitType.DECISION]
        if decisions:
            content += "## Decisions Made\n\n"
            for d in decisions[:10]:
                date = d.source_date.strftime("%a") if d.source_date else ""
                channel = f"#{d.source_channel}" if d.source_channel else ""
                content += f"- **{date}** ({channel}): {d.content}\n"
            content += "\n"

        # Action items
        actions = [u for u in units if u.unit_type == KnowledgeUnitType.ACTION_ITEM]
        if actions:
            content += "## Action Items\n\n"
            for a in actions[:15]:
                content += f"- [ ] {a.content}\n"
            content += "\n"

        # Open questions
        questions = [u for u in units if u.unit_type == KnowledgeUnitType.QUESTION]
        if questions:
            content += "## Open Questions\n\n"
            for q in questions[:10]:
                content += f"- {q.content}\n"
            content += "\n"

        # Day-by-day breakdown
        content += "## Daily Activity\n\n"
        for day_offset in range(7):
            day = week_start + timedelta(days=day_offset)
            day_units = [u for u in units if u.source_date and u.source_date.date() == day.date()]
            if day_units:
                content += f"### {day.strftime('%A, %B %d')}\n\n"
                content += f"*{len(day_units)} items*\n\n"

        return RenderedView(
            title=f"Week of {week_start.strftime('%B %d, %Y')}",
            content=content,
            source_units=[u.id for u in units],
            view_type="weekly_rollup",
            cache_key=f"weekly:{guild_id}:{week_start.strftime('%Y-%W')}",
        )

    async def render_decisions_log(
        self,
        guild_id: str,
        limit: int = 50,
        channel: Optional[str] = None,
    ) -> RenderedView:
        """
        Render a log of decisions.

        Args:
            guild_id: Guild ID
            limit: Maximum decisions to show
            channel: Optional channel filter

        Returns:
            RenderedView with markdown content
        """
        conditions = ["guild_id = ?", "unit_type = ?"]
        params: List[Any] = [guild_id, "decision"]

        if channel:
            conditions.append("source_channel = ?")
            params.append(channel)

        params.append(limit)

        query = f"""
        SELECT * FROM wiki_knowledge_units
        WHERE {' AND '.join(conditions)}
        ORDER BY source_date DESC
        LIMIT ?
        """

        rows = await self.vector_store.connection.fetch_all(query, tuple(params))
        units = [self.vector_store._row_to_unit(row) for row in rows]

        # Build content
        title = "Decision Log"
        if channel:
            title += f" - #{channel}"

        content = f"# {title}\n\n"
        content += f"*{len(units)} decisions recorded*\n\n"

        if not units:
            content += "*No decisions found.*\n"
        else:
            # Group by month
            by_month: Dict[str, List[KnowledgeUnit]] = {}
            for unit in units:
                if unit.source_date:
                    month_key = unit.source_date.strftime("%Y-%m")
                else:
                    month_key = "Unknown"
                if month_key not in by_month:
                    by_month[month_key] = []
                by_month[month_key].append(unit)

            for month, month_units in sorted(by_month.items(), reverse=True):
                if month != "Unknown":
                    month_date = datetime.strptime(month, "%Y-%m")
                    content += f"## {month_date.strftime('%B %Y')}\n\n"
                else:
                    content += "## Unknown Date\n\n"

                for unit in month_units:
                    date = unit.source_date.strftime("%d") if unit.source_date else ""
                    channel_str = f"#{unit.source_channel}" if unit.source_channel else ""
                    content += f"- **{date}** ({channel_str}): {unit.content}\n"
                content += "\n"

        return RenderedView(
            title=title,
            content=content,
            source_units=[u.id for u in units],
            view_type="decisions",
            cache_key=f"decisions:{guild_id}:{channel or 'all'}",
        )

    async def _find_related_topics(
        self,
        guild_id: str,
        source_results: List[SearchResult],
    ) -> List[str]:
        """
        Find topics related to the given search results.

        Looks at the sources of similar units to find other topics.
        """
        # Get channels from source results
        channels = set()
        for r in source_results:
            if r.source_channel:
                channels.add(r.source_channel)

        # This is a simple approach - in production would use
        # topic modeling or clustering on the full content
        return list(channels)[:5]

    def _slugify(self, text: str) -> str:
        """Convert text to URL-safe slug."""
        import re
        slug = text.lower().strip()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[-\s]+', '-', slug)
        return slug[:50]
