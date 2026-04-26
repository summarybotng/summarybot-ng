"""
Wiki Page Synthesis (ADR-063).

Generates LLM-synthesized summaries from raw wiki page updates.
"""

import logging
import re
from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..summarization.claude_client import ClaudeClient

logger = logging.getLogger(__name__)


@dataclass
class SynthesisResult:
    """Result of synthesizing a wiki page."""
    synthesis: str
    source_count: int
    conflicts_found: int
    topics_extracted: List[str]
    confidence: float  # 0-1 based on source agreement


SYNTHESIS_SYSTEM_PROMPT = """You are a technical documentation synthesizer for a software team's wiki.
Your task is to consolidate multiple updates into a single coherent document.

Guidelines:
- Write in present tense
- Be concise but complete
- Preserve key facts and decisions
- Note any contradictions with [Conflict: ...]
- Do NOT include source citations - they're shown separately
- Use markdown formatting with headers and bullet points"""

SYNTHESIS_USER_PROMPT = """Synthesize this wiki page about "{title}" from the following updates:

{content}

Create a well-organized document with:
1. A brief overview paragraph
2. Key Points section with bullet points
3. Any additional relevant sections

Output clean Markdown only."""


async def synthesize_wiki_page(
    page_title: str,
    page_content: str,
    source_refs: List[str],
    claude_client: Optional["ClaudeClient"] = None,
) -> SynthesisResult:
    """
    Generate a synthesized summary of wiki page content.

    Args:
        page_title: Title of the wiki page
        page_content: Raw content with all updates
        source_refs: List of source IDs referenced
        claude_client: Optional ClaudeClient for AI synthesis

    Returns:
        SynthesisResult with synthesized content
    """
    source_count = len(source_refs)

    # Check for potential conflicts in content
    conflicts_found = _count_potential_conflicts(page_content)

    # Extract topics mentioned
    topics_extracted = _extract_topics_from_content(page_content)

    # If no Claude client, use heuristic synthesis
    if claude_client is None:
        synthesis = _heuristic_synthesis(page_title, page_content, source_count)
        confidence = 0.7 if conflicts_found == 0 else 0.5
    else:
        try:
            from ..summarization.claude_client import ClaudeOptions

            # Use Claude for synthesis
            user_prompt = SYNTHESIS_USER_PROMPT.format(
                title=page_title,
                content=page_content[:12000],  # Limit to avoid token overflow
            )

            options = ClaudeOptions(
                max_tokens=2000,
                temperature=0.3,
            )

            response = await claude_client.create_summary_with_fallback(
                prompt=user_prompt,
                system_prompt=SYNTHESIS_SYSTEM_PROMPT,
                options=options,
            )

            synthesis = response.content
            confidence = 0.9 if conflicts_found == 0 else 0.7

            logger.info(f"Wiki synthesis generated: {response.input_tokens} in, {response.output_tokens} out, model={response.model}")

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
