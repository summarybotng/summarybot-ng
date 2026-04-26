"""
Wiki Page Synthesis (ADR-063).

Generates LLM-synthesized summaries from raw wiki page updates.
"""

import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class SynthesisResult:
    """Result of synthesizing a wiki page."""
    synthesis: str
    source_count: int
    conflicts_found: int
    topics_extracted: List[str]
    confidence: float  # 0-1 based on source agreement


SYNTHESIS_PROMPT = """You are summarizing a wiki page about "{title}" for a software team.

The page contains multiple updates from different summaries. Synthesize these
into a coherent, well-organized document that:

1. Consolidates duplicate/overlapping information
2. Presents the most current understanding
3. Notes any unresolved contradictions with [Conflict: ...]
4. Preserves key facts and decisions
5. Organizes into logical sections (Overview, Key Points, Related, etc.)

Keep the synthesis concise but complete. Write in present tense.
Do NOT include source citations in the synthesis - they're shown separately.

## Raw Updates to Synthesize:

{content}

## Output:

Write clean Markdown. Group related information. Use bullet points for lists.
Start with a brief overview paragraph, then organize into sections."""


async def synthesize_wiki_page(
    page_title: str,
    page_content: str,
    source_refs: List[str],
    llm_client: Optional[Any] = None,
) -> SynthesisResult:
    """
    Generate a synthesized summary of wiki page content.

    Args:
        page_title: Title of the wiki page
        page_content: Raw content with all updates
        source_refs: List of source IDs referenced
        llm_client: Optional LLM client for AI synthesis

    Returns:
        SynthesisResult with synthesized content
    """
    source_count = len(source_refs)

    # Check for potential conflicts in content
    conflicts_found = _count_potential_conflicts(page_content)

    # Extract topics mentioned
    topics_extracted = _extract_topics_from_content(page_content)

    # If no LLM client, use heuristic synthesis
    if llm_client is None:
        synthesis = _heuristic_synthesis(page_title, page_content, source_count)
        confidence = 0.7 if conflicts_found == 0 else 0.5
    else:
        try:
            # Use LLM for synthesis
            prompt = SYNTHESIS_PROMPT.format(
                title=page_title,
                content=page_content[:8000],  # Limit to avoid token overflow
            )
            synthesis = await llm_client.generate(prompt)
            confidence = 0.9 if conflicts_found == 0 else 0.7
        except Exception as e:
            logger.warning(f"LLM synthesis failed, using heuristic: {e}")
            synthesis = _heuristic_synthesis(page_title, page_content, source_count)
            confidence = 0.6

    return SynthesisResult(
        synthesis=synthesis,
        source_count=source_count,
        conflicts_found=conflicts_found,
        topics_extracted=topics_extracted,
        confidence=confidence,
    )


def _heuristic_synthesis(title: str, content: str, source_count: int) -> str:
    """
    Generate a heuristic synthesis without LLM.

    Extracts key points and structures them into a summary.
    """
    lines = content.split("\n")

    # Extract title (first H1 if present)
    overview_lines = []
    key_points = []
    current_section = None

    for line in lines:
        stripped = line.strip()

        # Skip empty lines and source references
        if not stripped or stripped.startswith("[source:"):
            continue

        # Skip update headers
        if stripped.startswith("## Update from summary-"):
            continue

        # Track section headers
        if stripped.startswith("# "):
            current_section = "title"
            continue
        elif stripped.startswith("## "):
            if "key point" in stripped.lower() or "overview" in stripped.lower():
                current_section = "overview"
            else:
                current_section = "section"
            continue

        # Collect key points (bullet points)
        if stripped.startswith("- ") or stripped.startswith("* "):
            point = stripped[2:].strip()
            # Remove trailing source references
            point = re.sub(r'\s*\[source:summary-[\w-]+\]\s*$', '', point)
            if point and point not in key_points:
                key_points.append(point)
        elif current_section == "overview" and len(stripped) > 20:
            overview_lines.append(stripped)

    # Build synthesis
    synthesis = f"# {title}\n\n"

    # Add overview if we have one
    if overview_lines:
        synthesis += " ".join(overview_lines[:3]) + "\n\n"
    else:
        synthesis += f"This page consolidates information about {title.lower()} from {source_count} source(s).\n\n"

    # Add key points
    if key_points:
        synthesis += "## Key Points\n\n"
        for point in key_points[:10]:  # Limit to 10 points
            synthesis += f"- {point}\n"
        synthesis += "\n"

    # Add metadata footer
    synthesis += f"---\n\n*Synthesized from {source_count} source(s)*\n"

    return synthesis


def _count_potential_conflicts(content: str) -> int:
    """Count potential conflicts in content based on contradictory language."""
    conflict_patterns = [
        r"however,?\s+(earlier|previously|before)",
        r"(changed|updated|revised)\s+from",
        r"no longer\s+(true|valid|applicable)",
        r"instead of\s+\w+",
        r"(contradicts?|conflicts? with)",
    ]

    count = 0
    content_lower = content.lower()
    for pattern in conflict_patterns:
        matches = re.findall(pattern, content_lower)
        count += len(matches)

    return count


def _extract_topics_from_content(content: str) -> List[str]:
    """Extract topic keywords from content."""
    # Common technical topics to look for
    topic_keywords = {
        "api", "authentication", "auth", "database", "caching", "cache",
        "deployment", "deploy", "testing", "test", "security", "performance",
        "infrastructure", "ci", "cd", "pipeline", "monitoring", "logging",
        "error", "bug", "feature", "refactor", "migration", "integration",
        "oauth", "jwt", "token", "session", "user", "role", "permission",
    }

    content_lower = content.lower()
    found_topics = []

    for topic in topic_keywords:
        if topic in content_lower:
            found_topics.append(topic)

    return found_topics[:10]  # Limit to 10 topics
