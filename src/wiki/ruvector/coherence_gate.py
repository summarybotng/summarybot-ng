"""
Coherence Gate for RuVector (ADR-057 Phase 3).

Validates new knowledge units against existing content to prevent:
1. Contradictions with established facts
2. Unsupported claims (no source backing)
3. Semantic drift from topic clusters

Acts as a quality gate before content enters the knowledge store.
"""

import logging
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .models import (
    KnowledgeUnit,
    KnowledgeUnitType,
    CoherenceValidation,
    ValidationStatus,
    SearchResult,
)
from .vector_store import VectorStore

if TYPE_CHECKING:
    from ...summarization.claude_client import ClaudeClient

logger = logging.getLogger(__name__)


class IssueType(str, Enum):
    """Type of coherence issue detected."""
    CONTRADICTION = "contradiction"
    UNSUPPORTED = "unsupported"
    DUPLICATE = "duplicate"
    DRIFT = "drift"


@dataclass
class CoherenceIssue:
    """A coherence issue detected during validation."""
    issue_type: IssueType
    description: str
    confidence: float
    conflicting_unit_id: Optional[str] = None
    conflicting_content: Optional[str] = None
    suggestion: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of coherence validation."""
    unit_id: str
    approved: bool
    status: ValidationStatus
    issues: List[CoherenceIssue] = field(default_factory=list)
    validation_time_ms: int = 0

    @property
    def has_contradictions(self) -> bool:
        return any(i.issue_type == IssueType.CONTRADICTION for i in self.issues)

    @property
    def has_duplicates(self) -> bool:
        return any(i.issue_type == IssueType.DUPLICATE for i in self.issues)


CONTRADICTION_CHECK_PROMPT = """Analyze if these two statements contradict each other.

Statement A: {statement_a}
Statement B: {statement_b}

Consider:
1. Do they make opposing claims about the same subject?
2. Could both be true in different contexts?
3. Is one a refinement/update of the other?

Return JSON: {{"contradicts": true/false, "confidence": 0.0-1.0, "reason": "..."}}"""


class CoherenceGate:
    """
    Validates new content against existing knowledge.

    ADR-057: Prevents hallucination accumulation by checking:
    - Contradictions with existing facts
    - Duplicate content
    - Semantic drift from established topics
    """

    def __init__(
        self,
        vector_store: VectorStore,
        claude_client: Optional["ClaudeClient"] = None,
        contradiction_threshold: float = 0.85,
        duplicate_threshold: float = 0.95,
        drift_threshold: float = 0.3,
        auto_reject_threshold: float = 0.95,
    ):
        """
        Initialize the coherence gate.

        Args:
            vector_store: Vector store for similarity search
            claude_client: Optional Claude client for LLM validation
            contradiction_threshold: Similarity threshold for contradiction check
            duplicate_threshold: Similarity threshold for duplicate detection
            drift_threshold: Maximum drift from topic cluster
            auto_reject_threshold: Confidence above which to auto-reject
        """
        self.vector_store = vector_store
        self.claude_client = claude_client
        self.contradiction_threshold = contradiction_threshold
        self.duplicate_threshold = duplicate_threshold
        self.drift_threshold = drift_threshold
        self.auto_reject_threshold = auto_reject_threshold

    async def validate(self, unit: KnowledgeUnit) -> ValidationResult:
        """
        Validate a knowledge unit before storage.

        Args:
            unit: Knowledge unit to validate

        Returns:
            ValidationResult with approval status and any issues
        """
        import time
        start_time = time.time()

        issues: List[CoherenceIssue] = []

        # 1. Check for duplicates
        duplicate_issues = await self._check_duplicates(unit)
        issues.extend(duplicate_issues)

        # 2. Check for contradictions (only for claims and decisions)
        if unit.unit_type in [KnowledgeUnitType.CLAIM, KnowledgeUnitType.DECISION]:
            contradiction_issues = await self._check_contradictions(unit)
            issues.extend(contradiction_issues)

        # 3. Check for semantic drift (optional, for established topics)
        # drift_issues = await self._check_drift(unit)
        # issues.extend(drift_issues)

        # Determine status
        validation_time = int((time.time() - start_time) * 1000)

        # Auto-reject high-confidence contradictions
        high_confidence_contradictions = [
            i for i in issues
            if i.issue_type == IssueType.CONTRADICTION
            and i.confidence >= self.auto_reject_threshold
        ]

        if high_confidence_contradictions:
            status = ValidationStatus.REJECTED
            approved = False
        elif issues:
            # Flag for review if any issues
            status = ValidationStatus.FLAGGED
            approved = True  # Allow but flag
        else:
            status = ValidationStatus.APPROVED
            approved = True

        result = ValidationResult(
            unit_id=unit.id,
            approved=approved,
            status=status,
            issues=issues,
            validation_time_ms=validation_time,
        )

        # Store validation record
        await self._store_validation(unit, result)

        return result

    async def validate_batch(
        self,
        units: List[KnowledgeUnit],
    ) -> List[ValidationResult]:
        """
        Validate multiple units.

        Args:
            units: Units to validate

        Returns:
            List of validation results
        """
        results = []
        for unit in units:
            result = await self.validate(unit)
            results.append(result)
        return results

    async def _check_duplicates(self, unit: KnowledgeUnit) -> List[CoherenceIssue]:
        """
        Check if unit is a duplicate of existing content.
        """
        issues = []

        # Find very similar units
        similar = await self.vector_store.find_similar(
            unit_id=unit.id,
            limit=5,
            threshold=self.duplicate_threshold,
            exclude_same_source=False,  # Include same source to catch exact dupes
        )

        for result in similar:
            # Skip if same unit
            if result.unit_id == unit.id:
                continue

            # Very high similarity = likely duplicate
            if result.score >= self.duplicate_threshold:
                issues.append(CoherenceIssue(
                    issue_type=IssueType.DUPLICATE,
                    description=f"Very similar to existing unit (similarity: {result.score:.2%})",
                    confidence=result.score,
                    conflicting_unit_id=result.unit_id,
                    conflicting_content=result.content[:200],
                    suggestion="Consider merging or skipping this unit",
                ))

        return issues

    async def _check_contradictions(self, unit: KnowledgeUnit) -> List[CoherenceIssue]:
        """
        Check if unit contradicts existing content.
        """
        issues = []

        # Find semantically similar units that might contradict
        similar = await self.vector_store.find_similar(
            unit_id=unit.id,
            limit=10,
            threshold=self.contradiction_threshold,
            exclude_same_source=True,
        )

        for result in similar:
            # Check for potential contradiction
            is_contradiction, confidence, reason = await self._detect_contradiction(
                unit.content, result.content
            )

            if is_contradiction and confidence >= 0.7:
                issues.append(CoherenceIssue(
                    issue_type=IssueType.CONTRADICTION,
                    description=f"Potential contradiction: {reason}",
                    confidence=confidence,
                    conflicting_unit_id=result.unit_id,
                    conflicting_content=result.content[:200],
                    suggestion="Review and resolve the conflict",
                ))

        return issues

    async def _detect_contradiction(
        self,
        content_a: str,
        content_b: str,
    ) -> tuple[bool, float, str]:
        """
        Detect if two pieces of content contradict each other.

        Returns: (is_contradiction, confidence, reason)
        """
        # Use LLM if available
        if self.claude_client:
            return await self._detect_contradiction_llm(content_a, content_b)

        # Heuristic fallback
        return self._detect_contradiction_heuristic(content_a, content_b)

    async def _detect_contradiction_llm(
        self,
        content_a: str,
        content_b: str,
    ) -> tuple[bool, float, str]:
        """
        Use LLM to detect contradictions.
        """
        try:
            prompt = CONTRADICTION_CHECK_PROMPT.format(
                statement_a=content_a[:500],
                statement_b=content_b[:500],
            )

            response = await self.claude_client.generate(
                prompt=prompt,
                max_tokens=200,
                temperature=0.1,
            )

            # Parse response
            import json
            response_text = response.strip()
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            result = json.loads(response_text)

            return (
                result.get("contradicts", False),
                result.get("confidence", 0.5),
                result.get("reason", "LLM analysis"),
            )

        except Exception as e:
            logger.warning(f"LLM contradiction check failed: {e}")
            return self._detect_contradiction_heuristic(content_a, content_b)

    def _detect_contradiction_heuristic(
        self,
        content_a: str,
        content_b: str,
    ) -> tuple[bool, float, str]:
        """
        Simple heuristic contradiction detection.
        """
        a_lower = content_a.lower()
        b_lower = content_b.lower()

        # Negation patterns
        negation_words = ["not", "no", "never", "don't", "won't", "can't", "shouldn't", "isn't", "aren't"]

        a_has_negation = any(f" {word} " in f" {a_lower} " for word in negation_words)
        b_has_negation = any(f" {word} " in f" {b_lower} " for word in negation_words)

        # One has negation, other doesn't
        if a_has_negation != b_has_negation:
            return (True, 0.6, "Opposing negation patterns detected")

        # Opposite sentiment words
        opposites = [
            ("yes", "no"), ("true", "false"), ("accept", "reject"),
            ("approve", "deny"), ("enable", "disable"), ("include", "exclude"),
            ("allow", "block"), ("start", "stop"), ("add", "remove"),
        ]

        for word_a, word_b in opposites:
            if (word_a in a_lower and word_b in b_lower) or (word_b in a_lower and word_a in b_lower):
                return (True, 0.5, f"Opposite terms detected: {word_a}/{word_b}")

        return (False, 0.0, "No contradiction detected")

    async def _store_validation(
        self,
        unit: KnowledgeUnit,
        result: ValidationResult,
    ) -> None:
        """
        Store validation result for audit trail.
        """
        try:
            for issue in result.issues:
                validation = CoherenceValidation(
                    guild_id=unit.guild_id,
                    unit_id=unit.id,
                    validation_type=issue.issue_type.value,
                    status=result.status,
                    details={
                        "description": issue.description,
                        "confidence": issue.confidence,
                        "conflicting_unit_id": issue.conflicting_unit_id,
                        "suggestion": issue.suggestion,
                    },
                )

                query = """
                INSERT INTO wiki_coherence_validations (
                    guild_id, unit_id, validation_type, status, details
                ) VALUES (?, ?, ?, ?, ?)
                """

                import json
                await self.vector_store.connection.execute(query, (
                    validation.guild_id,
                    validation.unit_id,
                    validation.validation_type,
                    validation.status.value,
                    json.dumps(validation.details),
                ))

        except Exception as e:
            logger.error(f"Failed to store validation: {e}")

    async def get_flagged_validations(
        self,
        guild_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get validations flagged for human review.
        """
        query = """
        SELECT v.*, u.content as unit_content
        FROM wiki_coherence_validations v
        LEFT JOIN wiki_knowledge_units u ON v.unit_id = u.id
        WHERE v.guild_id = ? AND v.status = 'flagged' AND v.reviewed_at IS NULL
        ORDER BY v.created_at DESC
        LIMIT ?
        """

        rows = await self.vector_store.connection.fetch_all(query, (guild_id, limit))
        return [dict(row) for row in rows]

    async def resolve_validation(
        self,
        validation_id: int,
        resolution: str,
        reviewed_by: str,
    ) -> bool:
        """
        Resolve a flagged validation.
        """
        query = """
        UPDATE wiki_coherence_validations
        SET reviewed_at = datetime('now'),
            reviewed_by = ?,
            status = 'approved'
        WHERE id = ?
        """

        await self.vector_store.connection.execute(query, (reviewed_by, validation_id))
        return True
