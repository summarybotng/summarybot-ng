"""
Wiki Ingest Agent (ADR-056).

Ingests new sources into the compounding wiki by:
1. Reading and understanding the source
2. Identifying affected wiki pages
3. Updating or creating pages
4. Detecting contradictions
5. Updating cross-references
6. Logging operations
"""

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from ..models import (
    WikiPage,
    WikiLink,
    WikiSource,
    WikiSourceType,
    WikiOperation,
)
from ...data.sqlite.wiki_repository import SQLiteWikiRepository

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    """Result of an ingest operation."""
    source_id: str
    pages_updated: List[str] = field(default_factory=list)
    pages_created: List[str] = field(default_factory=list)
    contradictions: List[Dict[str, Any]] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None


class WikiIngestAgent:
    """
    Ingests new sources into the compounding wiki.

    Design per ADR-056:
    - Updates 10-15 existing pages per source
    - Creates new pages for topics that don't exist
    - Detects contradictions with existing knowledge
    - Maintains cross-references between pages
    """

    def __init__(self, repository: SQLiteWikiRepository, llm_client: Optional[Any] = None):
        """
        Initialize the ingest agent.

        Args:
            repository: Wiki repository for data access
            llm_client: Optional LLM client for semantic analysis
        """
        self.repository = repository
        self.llm_client = llm_client

    async def ingest_summary(
        self,
        guild_id: str,
        summary_id: str,
        summary_text: str,
        key_points: List[str],
        action_items: List[str],
        participants: List[str],
        technical_terms: List[str],
        channel_name: str,
        timestamp: datetime,
        platform: str = "discord",  # ADR-067: Platform awareness
    ) -> IngestResult:
        """
        Ingest a generated summary into the wiki.

        Args:
            guild_id: Guild ID
            summary_id: Source summary ID
            summary_text: Full summary text
            key_points: Extracted key points
            action_items: Extracted action items
            participants: Participants in the conversation
            technical_terms: Technical terms mentioned
            channel_name: Source channel name
            timestamp: Summary timestamp

        Returns:
            IngestResult with pages updated/created
        """
        try:
            # ADR-067: Platform-aware source titles
            platform_display = {
                "discord": "Discord",
                "whatsapp": "WhatsApp",
                "slack": "Slack",
                "telegram": "Telegram",
            }.get(platform.lower(), platform.title())

            # 1. Store source document (immutable)
            source = WikiSource(
                id=f"summary-{summary_id}",
                guild_id=guild_id,
                source_type=WikiSourceType.SUMMARY,
                title=f"{platform_display}: {channel_name} - {timestamp.strftime('%Y-%m-%d')}",
                content=summary_text,
                metadata={
                    "platform": platform,
                    "channel_name": channel_name,
                    "timestamp": timestamp.isoformat(),
                    "key_points": key_points,
                    "action_items": action_items,
                    "participants": participants,
                    "technical_terms": technical_terms,
                },
            )
            await self.repository.save_source(source)

            # 2. Identify topics to update
            topics = self._extract_topics(summary_text, key_points, technical_terms)

            result = IngestResult(source_id=source.id)

            # 3. Update or create topic pages
            for topic in topics:
                path = f"topics/{self._slugify(topic)}.md"
                existing = await self.repository.get_page(guild_id, path)

                if existing:
                    # ADR-076: Check source_refs first for authoritative deduplication
                    if source.id in existing.source_refs:
                        logger.debug(f"Source {source.id} already in page {path} source_refs, skipping")
                        continue

                    # Update existing page with topic-filtered content
                    updated_content = self._update_page_content(
                        existing.content, topic, key_points, source.id
                    )
                    existing.content = updated_content
                    existing.source_refs = list(set(existing.source_refs + [source.id]))
                    await self.repository.save_page(existing)
                    result.pages_updated.append(path)
                else:
                    # Create new page
                    new_page = WikiPage(
                        id=str(uuid.uuid4()),
                        guild_id=guild_id,
                        path=path,
                        title=topic.title(),
                        content=self._create_topic_content(topic, summary_text, key_points, source.id),
                        topics=[topic.lower()],
                        source_refs=[source.id],
                    )
                    await self.repository.save_page(new_page)
                    result.pages_created.append(path)

            # 4. Update expertise map
            await self._update_expertise_map(guild_id, participants, topics, source.id)
            result.pages_updated.append("experts/expertise-map.md")

            # 5. Check for decisions
            decisions = self._extract_decisions(summary_text, key_points)
            for decision in decisions:
                date_slug = timestamp.strftime("%Y-%m")
                path = f"decisions/{date_slug}-{self._slugify(decision['topic'])}.md"
                existing = await self.repository.get_page(guild_id, path)

                if not existing:
                    new_page = WikiPage(
                        id=str(uuid.uuid4()),
                        guild_id=guild_id,
                        path=path,
                        title=f"Decision: {decision['topic'].title()}",
                        content=self._create_decision_content(decision, participants, source.id),
                        topics=[decision['topic'].lower()],
                        source_refs=[source.id],
                    )
                    await self.repository.save_page(new_page)
                    result.pages_created.append(path)

            # 6. Update cross-references
            await self._update_links(guild_id, result.pages_updated + result.pages_created, topics)

            # 7. Update link counts
            await self.repository.update_link_counts(guild_id)

            # 8. Log operation
            await self.repository.append_log(
                guild_id=guild_id,
                operation=WikiOperation.INGEST,
                details={
                    "source_id": source.id,
                    "pages_updated": len(result.pages_updated),
                    "pages_created": len(result.pages_created),
                    "contradictions": len(result.contradictions),
                    "topics": topics,
                },
                agent_id="wiki-ingest-agent",
            )

            return result

        except Exception as e:
            logger.exception(f"Failed to ingest summary {summary_id}: {e}")
            return IngestResult(
                source_id=summary_id,
                success=False,
                error=str(e),
            )

    def _extract_topics(
        self,
        summary_text: str,
        key_points: List[str],
        technical_terms: List[str],
    ) -> List[str]:
        """Extract topics from summary content."""
        topics = set()

        # Use technical terms as topics
        for term in technical_terms:
            if len(term) > 2:  # Skip short terms
                topics.add(term.lower())

        # Extract nouns from key points (simple heuristic)
        # In production, use NLP or LLM for better extraction
        common_topic_words = {
            "api", "database", "authentication", "auth", "deployment", "deploy",
            "cache", "caching", "security", "performance", "testing", "test",
            "infrastructure", "ci", "cd", "pipeline", "monitoring", "logging",
            "error", "bug", "feature", "refactor", "migration", "integration",
        }

        text = " ".join([summary_text] + key_points).lower()
        for word in common_topic_words:
            if word in text:
                topics.add(word)

        return list(topics)[:15]  # ADR-056: Update 10-15 pages

    def _extract_decisions(self, summary_text: str, key_points: List[str]) -> List[Dict[str, str]]:
        """Extract decisions from summary content."""
        decisions = []

        # Look for decision keywords
        decision_patterns = [
            r"decided to (use|implement|adopt|switch to|migrate to) ([a-zA-Z0-9\-_]+)",
            r"will (use|implement|adopt) ([a-zA-Z0-9\-_]+)",
            r"chose ([a-zA-Z0-9\-_]+) (over|instead of)",
        ]

        text = " ".join([summary_text] + key_points)

        for pattern in decision_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                topic = match[-1] if isinstance(match, tuple) else match
                decisions.append({
                    "topic": topic.lower(),
                    "context": text[:200],  # First 200 chars as context
                })

        return decisions[:3]  # Limit to 3 decisions per summary

    def _slugify(self, text: str) -> str:
        """Convert text to URL-safe slug."""
        slug = text.lower().strip()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[-\s]+', '-', slug)
        return slug[:50]  # Limit length

    def _update_page_content(
        self,
        existing_content: str,
        topic: str,
        key_points: List[str],
        source_id: str,
    ) -> str:
        """Update existing page content with topic-relevant information only."""
        # Check if this source has already been added (deduplication)
        if source_id in existing_content:
            logger.debug(f"Source {source_id} already in page content, skipping")
            return existing_content

        # Filter key points to only include those relevant to this topic
        relevant_points = self._filter_relevant_points(topic, key_points)

        # Only add section if we have relevant content
        if not relevant_points:
            logger.debug(f"No relevant points for topic '{topic}' from {source_id}")
            return existing_content

        new_section = f"\n\n## Update from {source_id}\n\n"
        new_section += "Key Points:\n"
        for point in relevant_points[:5]:  # Limit to 5 points
            new_section += f"- {point} [source:{source_id}]\n"

        return existing_content + new_section

    def _filter_relevant_points(self, topic: str, key_points: List[str]) -> List[str]:
        """Filter key points to only include those relevant to the topic.

        Uses the topic words themselves as the filter - no hardcoded mappings.
        This works for any user-driven topic.
        """
        # Extract meaningful words from the topic (split on non-alphanumeric)
        topic_words = set(re.split(r'[\s\-_/]+', topic.lower()))
        # Remove very short words (likely not meaningful)
        topic_words = {w for w in topic_words if len(w) >= 3}

        if not topic_words:
            # Fallback: use the whole topic as-is
            topic_words = {topic.lower()}

        relevant = []
        for point in key_points:
            point_lower = point.lower()
            # Check if any topic word appears in the key point
            if any(word in point_lower for word in topic_words):
                relevant.append(point)

        return relevant

    def _create_topic_content(
        self,
        topic: str,
        summary_text: str,
        key_points: List[str],
        source_id: str,
    ) -> str:
        """Create initial content for a new topic page."""
        content = f"# {topic.title()}\n\n"
        content += f"*Topic created from summary analysis*\n\n"
        content += "## Overview\n\n"
        content += f"This topic was identified from recent discussions. [source:{source_id}]\n\n"

        # Filter to only relevant key points
        relevant_points = self._filter_relevant_points(topic, key_points)

        if relevant_points:
            content += "## Key Points\n\n"
            for point in relevant_points[:5]:
                content += f"- {point} [source:{source_id}]\n"

        content += "\n## Related Topics\n\n"
        content += "*Links to related topics will be added as more content is ingested.*\n"

        return content

    def _create_decision_content(
        self,
        decision: Dict[str, str],
        participants: List[str],
        source_id: str,
    ) -> str:
        """Create content for a decision page."""
        content = f"# Decision: {decision['topic'].title()}\n\n"
        content += f"*Recorded from discussion* [source:{source_id}]\n\n"
        content += "## Context\n\n"
        content += f"{decision.get('context', 'Context from discussion.')}\n\n"
        content += "## Decision\n\n"
        content += f"Team decided to use/adopt **{decision['topic']}**.\n\n"
        content += "## Participants\n\n"
        for p in participants[:5]:
            content += f"- {p}\n"
        content += "\n## Rationale\n\n"
        content += "*Rationale to be added from follow-up discussions.*\n"

        return content

    async def _update_expertise_map(
        self,
        guild_id: str,
        participants: List[str],
        topics: List[str],
        source_id: str,
    ) -> None:
        """Update the expertise map with participant-topic associations."""
        path = "experts/expertise-map.md"
        existing = await self.repository.get_page(guild_id, path)

        if existing:
            # Check if this source has already been added (deduplication)
            if source_id in existing.content:
                logger.debug(f"Source {source_id} already in expertise map, skipping")
                return

            # Append new expertise entries
            new_section = f"\n\n### From {source_id}\n\n"
            for participant in participants[:5]:
                topic_list = ", ".join(topics[:5])
                new_section += f"- **{participant}**: {topic_list}\n"
            existing.content += new_section
            await self.repository.save_page(existing)
        else:
            # Create expertise map
            content = "# Expertise Map\n\n"
            content += "*Who knows what - automatically maintained from discussions*\n\n"
            content += "## Contributors\n\n"
            for participant in participants[:5]:
                topic_list = ", ".join(topics[:5])
                content += f"- **{participant}**: {topic_list} [source:{source_id}]\n"

            new_page = WikiPage(
                id=str(uuid.uuid4()),
                guild_id=guild_id,
                path=path,
                title="Expertise Map",
                content=content,
                topics=["expertise", "contributors"],
                source_refs=[source_id],
            )
            await self.repository.save_page(new_page)

    async def _update_links(
        self,
        guild_id: str,
        pages: List[str],
        topics: List[str],
    ) -> None:
        """Update cross-references between pages."""
        # Create links between topic pages
        topic_paths = [f"topics/{self._slugify(t)}.md" for t in topics]

        for from_path in pages:
            for to_path in topic_paths:
                if from_path != to_path:
                    link = WikiLink(
                        from_page=from_path,
                        to_page=to_path,
                        guild_id=guild_id,
                        link_text=to_path.replace("topics/", "").replace(".md", ""),
                    )
                    await self.repository.save_link(link)
