"""
ADR-024: Resilient Summary Generation with Multi-Model Retry.

Provides retry strategies, model escalation, and attempt tracking for
robust summary generation that handles various failure modes.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


class RetryReason(Enum):
    """Reasons for retrying summary generation."""
    TRUNCATION = "truncation"
    JSON_PARSE_ERROR = "json_parse_error"
    MALFORMED_CONTENT = "malformed_content"
    RATE_LIMIT = "rate_limit"
    NETWORK_ERROR = "network_error"
    MODEL_UNAVAILABLE = "model_unavailable"
    TIMEOUT = "timeout"


class RetryAction(Enum):
    """Actions to take when retrying."""
    SAME_MODEL = "same_model"
    ESCALATE_MODEL = "escalate_model"
    INCREASE_TOKENS = "increase_tokens"
    ADD_PROMPT_HINT = "add_prompt_hint"


@dataclass
class GenerationAttempt:
    """Records a single attempt at generating a summary."""
    attempt_number: int
    model: str
    success: bool
    retry_reason: Optional[RetryReason] = None
    retry_action: Optional[RetryAction] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for metadata storage."""
        result = {
            "attempt": self.attempt_number,
            "model": self.model,
            "success": self.success,
            "tokens": self.input_tokens + self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "latency_ms": self.latency_ms,
        }
        if self.retry_reason:
            result["retry_reason"] = self.retry_reason.value
        if self.retry_action:
            result["retry_action"] = self.retry_action.value
        if self.error_message:
            result["error"] = self.error_message[:200]  # Truncate long errors
        return result


@dataclass
class GenerationAttemptTracker:
    """Tracks all attempts for a single summary generation.

    Enforces limits on attempts and cost to prevent runaway API usage.
    """
    max_attempts: int = 7
    max_cost_usd: float = 0.50
    attempts: List[GenerationAttempt] = field(default_factory=list)
    _start_time_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    @property
    def total_cost_usd(self) -> float:
        """Get total cost across all attempts."""
        return sum(a.cost_usd for a in self.attempts)

    @property
    def total_tokens(self) -> int:
        """Get total tokens used across all attempts."""
        return sum(a.input_tokens + a.output_tokens for a in self.attempts)

    @property
    def attempt_count(self) -> int:
        """Get number of attempts made."""
        return len(self.attempts)

    @property
    def final_model(self) -> Optional[str]:
        """Get the model used in the last attempt."""
        if self.attempts:
            return self.attempts[-1].model
        return None

    @property
    def total_latency_ms(self) -> int:
        """Get total latency across all attempts."""
        return int(time.time() * 1000) - self._start_time_ms

    def can_retry(self) -> bool:
        """Check if another retry attempt is allowed.

        Returns:
            True if within attempt and cost limits.
        """
        if self.attempt_count >= self.max_attempts:
            logger.warning(f"Max attempts ({self.max_attempts}) reached")
            return False
        if self.total_cost_usd >= self.max_cost_usd:
            logger.warning(f"Cost cap (${self.max_cost_usd}) reached: ${self.total_cost_usd:.4f}")
            return False
        return True

    def should_escalate_model(self, reason: RetryReason) -> bool:
        """Determine if model escalation is recommended for this failure.

        Args:
            reason: The reason for the failure.

        Returns:
            True if model escalation is recommended.
        """
        # Model escalation is preferred for quality issues
        quality_issues = {
            RetryReason.MALFORMED_CONTENT,
            RetryReason.JSON_PARSE_ERROR,
        }

        # Also escalate after token increase didn't help
        if reason == RetryReason.TRUNCATION:
            # Check if we already tried increasing tokens
            for attempt in self.attempts:
                if attempt.retry_action == RetryAction.INCREASE_TOKENS:
                    return True
            return False  # Try increasing tokens first

        return reason in quality_issues

    def add_attempt(self, attempt: GenerationAttempt) -> None:
        """Record a generation attempt."""
        self.attempts.append(attempt)
        logger.info(
            f"Attempt {attempt.attempt_number}: model={attempt.model}, "
            f"success={attempt.success}, reason={attempt.retry_reason}, "
            f"cost=${attempt.cost_usd:.4f}"
        )

    def to_metadata(self) -> Dict[str, Any]:
        """Convert tracker to metadata dictionary for storage.

        Returns:
            Dictionary suitable for storing in SummaryResult.metadata.
        """
        return {
            "total_attempts": self.attempt_count,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_tokens": self.total_tokens,
            "total_latency_ms": self.total_latency_ms,
            "final_model": self.final_model,
            "attempts": [a.to_dict() for a in self.attempts],
        }


def determine_retry_strategy(
    reason: RetryReason,
    current_model_index: int,
    current_max_tokens: int,
    tracker: GenerationAttemptTracker,
    max_tokens_cap: int = 16000,
) -> tuple[RetryAction, Optional[int], Optional[int]]:
    """Determine the appropriate retry strategy for a failure.

    Args:
        reason: The reason for the failure.
        current_model_index: Index in the model escalation chain.
        current_max_tokens: Current max_tokens setting.
        tracker: The attempt tracker.
        max_tokens_cap: Maximum allowed max_tokens value.

    Returns:
        Tuple of (action, new_model_index, new_max_tokens).
        new_model_index or new_max_tokens may be None if unchanged.
    """
    if not tracker.can_retry():
        raise StopIteration("Cannot retry: limits exceeded")

    # Rate limit and network errors: retry same model with backoff
    if reason in {RetryReason.RATE_LIMIT, RetryReason.NETWORK_ERROR, RetryReason.TIMEOUT}:
        return RetryAction.SAME_MODEL, None, None

    # Model unavailable: escalate immediately
    if reason == RetryReason.MODEL_UNAVAILABLE:
        return RetryAction.ESCALATE_MODEL, current_model_index + 1, None

    # Truncation: try increasing tokens first, then escalate
    if reason == RetryReason.TRUNCATION:
        if current_max_tokens < max_tokens_cap:
            new_tokens = min(current_max_tokens * 2, max_tokens_cap)
            return RetryAction.INCREASE_TOKENS, None, new_tokens
        else:
            # Already at max tokens, try better model
            return RetryAction.ESCALATE_MODEL, current_model_index + 1, None

    # JSON parse error: add hint first, then escalate
    if reason == RetryReason.JSON_PARSE_ERROR:
        # Check if we already tried adding a hint
        hint_tried = any(
            a.retry_action == RetryAction.ADD_PROMPT_HINT
            for a in tracker.attempts
        )
        if not hint_tried:
            return RetryAction.ADD_PROMPT_HINT, None, None
        else:
            return RetryAction.ESCALATE_MODEL, current_model_index + 1, None

    # Malformed content: escalate immediately
    if reason == RetryReason.MALFORMED_CONTENT:
        return RetryAction.ESCALATE_MODEL, current_model_index + 1, None

    # Default: escalate model
    return RetryAction.ESCALATE_MODEL, current_model_index + 1, None


def is_malformed_content(summary_text: str) -> bool:
    """Check if summary content indicates a parsing failure.

    Args:
        summary_text: The generated summary text.

    Returns:
        True if the content appears malformed or is a fallback message.
    """
    malformed_indicators = [
        "[Unable to parse",
        "Summary could not be extracted",
        "[Raw content preview:]",
    ]
    return any(indicator in summary_text for indicator in malformed_indicators)


def detect_quality_issue(
    summary_text: str,
    key_points: List[str],
    stop_reason: str,
    output_tokens: int,
    max_tokens: int,
) -> Optional[RetryReason]:
    """Detect quality issues that warrant a retry.

    Args:
        summary_text: The generated summary text.
        key_points: Extracted key points.
        stop_reason: API stop reason.
        output_tokens: Number of output tokens used.
        max_tokens: Maximum tokens allowed.

    Returns:
        RetryReason if an issue is detected, None otherwise.
    """
    # Check for truncation
    if stop_reason == "max_tokens":
        logger.warning(f"Response truncated: used {output_tokens}/{max_tokens} tokens")
        return RetryReason.TRUNCATION

    # Check for malformed content
    if is_malformed_content(summary_text):
        logger.warning("Malformed content detected in summary")
        return RetryReason.MALFORMED_CONTENT

    # Check for empty or missing key points (indicates parsing issues)
    malformed_points = [
        p for p in key_points
        if "[Unable to parse" in p or not p.strip()
    ]
    if malformed_points:
        logger.warning(f"Malformed key points detected: {len(malformed_points)}")
        return RetryReason.MALFORMED_CONTENT

    return None
