"""
Knowledge unit extractor for RuVector (ADR-057).

Extracts atomic knowledge units from summaries and messages using LLM.
Each unit represents a single fact, decision, question, or action item.
"""

import logging
import json
import uuid
import time
import hashlib
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime

from .models import (
    KnowledgeUnit,
    KnowledgeUnitType,
    ExtractionResult,
)


def generate_deterministic_unit_id(
    guild_id: str,
    source_id: str,
    content: str,
    unit_type: str,
) -> str:
    """
    Generate a deterministic ID for a knowledge unit based on content.

    ADR-118: This enables proper upsert behavior when the same content
    is extracted multiple times (e.g., during rolling schedule re-runs).

    Args:
        guild_id: Guild ID
        source_id: Source summary/message ID
        content: The unit content text
        unit_type: The unit type (claim, decision, etc.)

    Returns:
        32-character hex ID derived from content hash
    """
    # Normalize content for consistent hashing
    normalized_content = content.strip().lower()
    key = f"{guild_id}:{source_id}:{unit_type}:{normalized_content}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]

if TYPE_CHECKING:
    from ...summarization.claude_client import ClaudeClient

logger = logging.getLogger(__name__)


EXTRACTION_SYSTEM_PROMPT = """You are a knowledge extraction system. Your task is to decompose text into atomic knowledge units.

Each unit should be:
- Self-contained: Understandable without external context
- Atomic: Contains exactly one fact, decision, question, or action
- Precise: Uses specific terms, not vague language
- Attributed: Preserves who said/decided what when relevant

Unit types:
- claim: A factual statement or assertion
- decision: A choice or determination that was made
- question: An open question that needs answering
- action_item: A task or action someone needs to do
- context: Background information that provides context
- definition: A term or concept being defined
- reference: A reference to external documentation or resources

Output JSON array of objects with: content, type, confidence (0-1)"""


EXTRACTION_USER_PROMPT = """Extract knowledge units from this content:

Source: {source_type} from {channel_name}
Date: {date}

Content:
{content}

Return a JSON array. Example:
[
  {{"content": "The API migration will use OAuth 2.0 for authentication", "type": "decision", "confidence": 0.95}},
  {{"content": "John will create the migration guide by Friday", "type": "action_item", "confidence": 0.9}},
  {{"content": "How will we handle backward compatibility?", "type": "question", "confidence": 0.85}}
]

Extract all meaningful units. Be thorough but avoid trivial or redundant information."""


class KnowledgeExtractor:
    """
    Extract atomic knowledge units from text content.

    ADR-057: Uses Claude to decompose summaries/messages into
    self-contained knowledge units for vector storage.
    """

    def __init__(
        self,
        claude_client: Optional["ClaudeClient"] = None,
        min_confidence: float = 0.5,
        max_units_per_source: int = 50,
    ):
        """
        Initialize the knowledge extractor.

        Args:
            claude_client: Claude client for LLM extraction
            min_confidence: Minimum confidence threshold for units
            max_units_per_source: Maximum units to extract per source
        """
        self.claude_client = claude_client
        self.min_confidence = min_confidence
        self.max_units_per_source = max_units_per_source

    async def extract_from_summary(
        self,
        guild_id: str,
        summary_id: str,
        summary_text: str,
        channel_name: Optional[str] = None,
        summary_date: Optional[datetime] = None,
        key_points: Optional[List[str]] = None,
        action_items: Optional[List[str]] = None,
    ) -> ExtractionResult:
        """
        Extract knowledge units from a summary.

        Args:
            guild_id: Guild ID
            summary_id: Source summary ID
            summary_text: Full summary text
            channel_name: Source channel name
            summary_date: Summary timestamp
            key_points: Pre-extracted key points (optional, used as hints)
            action_items: Pre-extracted action items (optional)

        Returns:
            ExtractionResult with extracted units
        """
        start_time = time.time()

        # Build content for extraction
        content_parts = [summary_text]

        if key_points:
            content_parts.append("\n\nKey Points:\n" + "\n".join(f"- {kp}" for kp in key_points))

        if action_items:
            content_parts.append("\n\nAction Items:\n" + "\n".join(f"- {ai}" for ai in action_items))

        content = "\n".join(content_parts)

        # Extract units
        units = await self._extract_units(
            guild_id=guild_id,
            source_id=summary_id,
            source_type="summary",
            content=content,
            channel_name=channel_name,
            source_date=summary_date,
        )

        processing_time = int((time.time() - start_time) * 1000)

        return ExtractionResult(
            units=units,
            source_id=summary_id,
            extraction_model="claude" if self.claude_client else "heuristic",
            token_count=len(content.split()),
            processing_time_ms=processing_time,
        )

    async def extract_from_messages(
        self,
        guild_id: str,
        messages: List[Dict[str, Any]],
        channel_name: Optional[str] = None,
        batch_id: Optional[str] = None,
    ) -> ExtractionResult:
        """
        Extract knowledge units from raw messages.

        Args:
            guild_id: Guild ID
            messages: List of message dicts with content, author, timestamp
            channel_name: Channel name
            batch_id: Optional batch identifier for grouping

        Returns:
            ExtractionResult with extracted units
        """
        start_time = time.time()

        # Format messages for extraction
        formatted_messages = []
        for msg in messages:
            author = msg.get("author", "Unknown")
            content = msg.get("content", "")
            timestamp = msg.get("timestamp", "")
            formatted_messages.append(f"[{timestamp}] {author}: {content}")

        content = "\n".join(formatted_messages)
        source_id = batch_id or f"messages-{uuid.uuid4().hex[:8]}"

        # Get date from first message
        source_date = None
        if messages and messages[0].get("timestamp"):
            try:
                source_date = datetime.fromisoformat(messages[0]["timestamp"].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        units = await self._extract_units(
            guild_id=guild_id,
            source_id=source_id,
            source_type="message",
            content=content,
            channel_name=channel_name,
            source_date=source_date,
        )

        processing_time = int((time.time() - start_time) * 1000)

        return ExtractionResult(
            units=units,
            source_id=source_id,
            extraction_model="claude" if self.claude_client else "heuristic",
            token_count=len(content.split()),
            processing_time_ms=processing_time,
        )

    async def _extract_units(
        self,
        guild_id: str,
        source_id: str,
        source_type: str,
        content: str,
        channel_name: Optional[str],
        source_date: Optional[datetime],
    ) -> List[KnowledgeUnit]:
        """
        Core extraction logic.
        """
        if self.claude_client:
            return await self._extract_with_llm(
                guild_id=guild_id,
                source_id=source_id,
                source_type=source_type,
                content=content,
                channel_name=channel_name,
                source_date=source_date,
            )
        else:
            return self._extract_heuristic(
                guild_id=guild_id,
                source_id=source_id,
                source_type=source_type,
                content=content,
                channel_name=channel_name,
                source_date=source_date,
            )

    async def _extract_with_llm(
        self,
        guild_id: str,
        source_id: str,
        source_type: str,
        content: str,
        channel_name: Optional[str],
        source_date: Optional[datetime],
    ) -> List[KnowledgeUnit]:
        """
        Extract units using Claude LLM.
        """
        prompt = EXTRACTION_USER_PROMPT.format(
            source_type=source_type,
            channel_name=channel_name or "unknown",
            date=source_date.isoformat() if source_date else "unknown",
            content=content,
        )

        try:
            response = await self.claude_client.generate(
                prompt=prompt,
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                max_tokens=4000,
                temperature=0.3,
            )

            # Parse JSON response
            # Try to find JSON array in response
            response_text = response.strip()

            # Handle markdown code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            extracted = json.loads(response_text)

            units = []
            for item in extracted[:self.max_units_per_source]:
                confidence = item.get("confidence", 0.8)
                if confidence < self.min_confidence:
                    continue

                unit_type_str = item.get("type", "claim")
                try:
                    unit_type = KnowledgeUnitType(unit_type_str)
                except ValueError:
                    unit_type = KnowledgeUnitType.CLAIM

                content_text = item.get("content", "")
                # ADR-118: Use deterministic ID for deduplication
                unit_id = generate_deterministic_unit_id(
                    guild_id=guild_id,
                    source_id=source_id,
                    content=content_text,
                    unit_type=unit_type.value,
                )

                unit = KnowledgeUnit(
                    id=unit_id,
                    guild_id=guild_id,
                    content=content_text,
                    unit_type=unit_type,
                    source_id=source_id,
                    source_type=source_type,
                    source_channel=channel_name,
                    source_date=source_date,
                    confidence=confidence,
                )
                units.append(unit)

            return units

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse extraction response: {e}")
            return self._extract_heuristic(
                guild_id, source_id, source_type, content, channel_name, source_date
            )
        except Exception as e:
            logger.error(f"LLM extraction error: {e}")
            return self._extract_heuristic(
                guild_id, source_id, source_type, content, channel_name, source_date
            )

    def _extract_heuristic(
        self,
        guild_id: str,
        source_id: str,
        source_type: str,
        content: str,
        channel_name: Optional[str],
        source_date: Optional[datetime],
    ) -> List[KnowledgeUnit]:
        """
        Fallback heuristic extraction when LLM is unavailable.

        Uses simple patterns to identify:
        - Questions (ends with ?)
        - Action items (contains "will", "should", "need to")
        - Decisions (contains "decided", "agreed", "chose")
        """
        units = []
        sentences = self._split_sentences(content)

        for sentence in sentences[:self.max_units_per_source]:
            sentence = sentence.strip()
            if len(sentence) < 10:
                continue

            # Determine unit type based on patterns
            unit_type = KnowledgeUnitType.CLAIM
            confidence = 0.6

            lower = sentence.lower()

            if sentence.endswith("?"):
                unit_type = KnowledgeUnitType.QUESTION
                confidence = 0.8
            elif any(kw in lower for kw in ["will ", "should ", "need to ", "must ", "todo:", "action:"]):
                unit_type = KnowledgeUnitType.ACTION_ITEM
                confidence = 0.7
            elif any(kw in lower for kw in ["decided", "agreed", "chose", "decision:", "we will"]):
                unit_type = KnowledgeUnitType.DECISION
                confidence = 0.75
            elif any(kw in lower for kw in ["means", "is defined as", "refers to"]):
                unit_type = KnowledgeUnitType.DEFINITION
                confidence = 0.7

            if confidence >= self.min_confidence:
                # ADR-118: Use deterministic ID for deduplication
                unit_id = generate_deterministic_unit_id(
                    guild_id=guild_id,
                    source_id=source_id,
                    content=sentence,
                    unit_type=unit_type.value,
                )

                unit = KnowledgeUnit(
                    id=unit_id,
                    guild_id=guild_id,
                    content=sentence,
                    unit_type=unit_type,
                    source_id=source_id,
                    source_type=source_type,
                    source_channel=channel_name,
                    source_date=source_date,
                    confidence=confidence,
                )
                units.append(unit)

        return units

    def _split_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences.

        Simple implementation - handles common cases.
        """
        import re

        # Split on sentence boundaries
        sentences = re.split(r'(?<=[.!?])\s+', text)

        # Also split on bullet points and numbered lists
        expanded = []
        for s in sentences:
            # Split on bullet points
            parts = re.split(r'\n\s*[-•*]\s*', s)
            expanded.extend(parts)

        # Filter empty and clean up
        return [s.strip() for s in expanded if s.strip()]

    async def extract_from_human_edit(
        self,
        guild_id: str,
        edit_id: str,
        old_content: str,
        new_content: str,
        page_path: str,
    ) -> ExtractionResult:
        """
        Extract knowledge units from a human wiki edit.

        Human edits are treated as high-confidence corrections.
        """
        start_time = time.time()

        # For human edits, we primarily care about what was added
        # Simple diff: treat new content as authoritative
        units = await self._extract_units(
            guild_id=guild_id,
            source_id=edit_id,
            source_type="human_edit",
            content=new_content,
            channel_name=page_path,
            source_date=datetime.utcnow(),
        )

        # Human edits get maximum confidence
        for unit in units:
            unit.confidence = 1.0

        processing_time = int((time.time() - start_time) * 1000)

        return ExtractionResult(
            units=units,
            source_id=edit_id,
            extraction_model="human_edit",
            token_count=len(new_content.split()),
            processing_time_ms=processing_time,
        )
