"""
Wiki Query Agent (ADR-056).

Answers questions using wiki knowledge and persists valuable explorations.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from ..models import WikiPageSummary, WikiOperation
from ...data.sqlite.wiki_repository import SQLiteWikiRepository

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Result of a wiki query."""
    answer: str
    citations: List[WikiPageSummary] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    persisted_page: Optional[str] = None


class WikiQueryAgent:
    """
    Answers questions using wiki knowledge.

    Per ADR-056:
    - Searches wiki for relevant pages
    - Synthesizes answer with citations
    - Persists valuable explorations as new wiki content
    - Identifies knowledge gaps
    """

    def __init__(self, repository: SQLiteWikiRepository, llm_client: Optional[Any] = None):
        """
        Initialize the query agent.

        Args:
            repository: Wiki repository for data access
            llm_client: LLM client for synthesis (required for AI answers)
        """
        self.repository = repository
        self.llm_client = llm_client

    async def query(
        self,
        guild_id: str,
        question: str,
        user_id: str,
        synthesize: bool = True,
    ) -> QueryResult:
        """
        Answer a question using wiki knowledge.

        Args:
            guild_id: Guild ID
            question: User's question
            user_id: ID of the asking user
            synthesize: Whether to generate AI synthesis

        Returns:
            QueryResult with answer, citations, and gaps
        """
        # 1. Search wiki for relevant pages
        relevant_pages = await self.repository.search_pages(guild_id, question, limit=10)

        if not relevant_pages:
            # Log the query for knowledge gap detection
            await self.repository.append_log(
                guild_id=guild_id,
                operation=WikiOperation.QUERY,
                details={
                    "question": question,
                    "user_id": user_id,
                    "pages_found": 0,
                    "gaps": [question],
                },
                agent_id="wiki-query-agent",
            )

            return QueryResult(
                answer="No relevant information found in the wiki.",
                citations=[],
                gaps=[f"No wiki content for: {question}"],
            )

        # 2. Synthesize answer (if LLM available and requested)
        answer = ""
        if synthesize and self.llm_client:
            answer = await self._synthesize_answer(question, relevant_pages)
        else:
            # Fallback: list relevant pages
            answer = self._format_page_list(relevant_pages)

        # 3. Identify gaps
        gaps = self._identify_gaps(question, relevant_pages)

        # 4. Log the query
        await self.repository.append_log(
            guild_id=guild_id,
            operation=WikiOperation.QUERY,
            details={
                "question": question,
                "user_id": user_id,
                "pages_found": len(relevant_pages),
                "answer_length": len(answer),
                "gaps": gaps,
            },
            agent_id="wiki-query-agent",
        )

        return QueryResult(
            answer=answer,
            citations=relevant_pages,
            gaps=gaps,
        )

    async def _synthesize_answer(
        self,
        question: str,
        pages: List[WikiPageSummary],
    ) -> str:
        """Synthesize an answer using LLM (placeholder for integration)."""
        # TODO: Integrate with actual LLM for synthesis
        # For now, return a formatted summary
        return self._format_page_list(pages)

    def _format_page_list(self, pages: List[WikiPageSummary]) -> str:
        """Format pages as a simple list."""
        if not pages:
            return "No relevant pages found."

        lines = ["Based on the wiki, relevant information can be found in:\n"]
        for page in pages[:5]:
            lines.append(f"- **{page.title}** ({page.path})")

        if len(pages) > 5:
            lines.append(f"\n...and {len(pages) - 5} more pages.")

        return "\n".join(lines)

    def _identify_gaps(
        self,
        question: str,
        pages: List[WikiPageSummary],
    ) -> List[str]:
        """Identify knowledge gaps based on query and results."""
        gaps = []

        # If few results, might be a gap
        if len(pages) < 3:
            gaps.append(f"Limited coverage for: {question}")

        # Check for question words that indicate missing info
        question_lower = question.lower()
        missing_indicators = {
            "how to": "Process documentation",
            "why": "Rationale/decision documentation",
            "who": "Expertise/ownership documentation",
            "when": "Timeline/schedule documentation",
        }

        for indicator, doc_type in missing_indicators.items():
            if indicator in question_lower:
                # Check if any page covers this
                covered = any(
                    indicator in (p.title.lower() + " ".join(p.topics).lower())
                    for p in pages
                )
                if not covered:
                    gaps.append(f"Possible gap in {doc_type}")

        return gaps[:5]  # Limit gaps
