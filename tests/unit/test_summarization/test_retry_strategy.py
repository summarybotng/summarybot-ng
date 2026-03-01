"""
Unit tests for ADR-024: Resilient Summary Generation retry strategy.

Tests cover retry logic, model escalation, cost caps, and attempt tracking.
"""

import pytest
from unittest.mock import MagicMock

from src.summarization.retry_strategy import (
    RetryReason,
    RetryAction,
    GenerationAttempt,
    GenerationAttemptTracker,
    determine_retry_strategy,
    is_malformed_content,
    detect_quality_issue,
)


@pytest.mark.unit
class TestRetryReason:
    """Test RetryReason enum values."""

    def test_all_reasons_have_string_values(self):
        """Verify all retry reasons have meaningful string values."""
        assert RetryReason.TRUNCATION.value == "truncation"
        assert RetryReason.JSON_PARSE_ERROR.value == "json_parse_error"
        assert RetryReason.MALFORMED_CONTENT.value == "malformed_content"
        assert RetryReason.RATE_LIMIT.value == "rate_limit"
        assert RetryReason.NETWORK_ERROR.value == "network_error"
        assert RetryReason.MODEL_UNAVAILABLE.value == "model_unavailable"
        assert RetryReason.TIMEOUT.value == "timeout"


@pytest.mark.unit
class TestRetryAction:
    """Test RetryAction enum values."""

    def test_all_actions_have_string_values(self):
        """Verify all retry actions have meaningful string values."""
        assert RetryAction.SAME_MODEL.value == "same_model"
        assert RetryAction.ESCALATE_MODEL.value == "escalate_model"
        assert RetryAction.INCREASE_TOKENS.value == "increase_tokens"
        assert RetryAction.ADD_PROMPT_HINT.value == "add_prompt_hint"


@pytest.mark.unit
class TestGenerationAttempt:
    """Test GenerationAttempt dataclass."""

    def test_create_successful_attempt(self):
        """Test creating a successful generation attempt."""
        attempt = GenerationAttempt(
            attempt_number=1,
            model="anthropic/claude-3-haiku",
            success=True,
            input_tokens=1000,
            output_tokens=200,
            cost_usd=0.001,
            latency_ms=1500,
        )

        assert attempt.attempt_number == 1
        assert attempt.model == "anthropic/claude-3-haiku"
        assert attempt.success is True
        assert attempt.retry_reason is None
        assert attempt.retry_action is None

    def test_create_failed_attempt(self):
        """Test creating a failed generation attempt."""
        attempt = GenerationAttempt(
            attempt_number=2,
            model="anthropic/claude-3-haiku",
            success=False,
            retry_reason=RetryReason.MALFORMED_CONTENT,
            retry_action=RetryAction.ESCALATE_MODEL,
            input_tokens=1000,
            output_tokens=150,
            cost_usd=0.001,
            latency_ms=2000,
            error_message="Content contained [Unable to parse...]",
        )

        assert attempt.success is False
        assert attempt.retry_reason == RetryReason.MALFORMED_CONTENT
        assert attempt.retry_action == RetryAction.ESCALATE_MODEL

    def test_to_dict(self):
        """Test converting attempt to dictionary."""
        attempt = GenerationAttempt(
            attempt_number=1,
            model="anthropic/claude-3-haiku",
            success=False,
            retry_reason=RetryReason.TRUNCATION,
            retry_action=RetryAction.INCREASE_TOKENS,
            input_tokens=1000,
            output_tokens=200,
            cost_usd=0.00125,
            latency_ms=1500,
        )

        result = attempt.to_dict()

        assert result["attempt"] == 1
        assert result["model"] == "anthropic/claude-3-haiku"
        assert result["success"] is False
        assert result["retry_reason"] == "truncation"
        assert result["retry_action"] == "increase_tokens"
        assert result["tokens"] == 1200
        assert result["cost_usd"] == 0.00125
        assert result["latency_ms"] == 1500

    def test_to_dict_truncates_long_errors(self):
        """Test that long error messages are truncated."""
        long_error = "x" * 500
        attempt = GenerationAttempt(
            attempt_number=1,
            model="test",
            success=False,
            error_message=long_error,
        )

        result = attempt.to_dict()
        assert len(result["error"]) == 200


@pytest.mark.unit
class TestGenerationAttemptTracker:
    """Test GenerationAttemptTracker class."""

    def test_initial_state(self):
        """Test tracker initial state."""
        tracker = GenerationAttemptTracker()

        assert tracker.max_attempts == 7
        assert tracker.max_cost_usd == 0.50
        assert tracker.attempt_count == 0
        assert tracker.total_cost_usd == 0.0
        assert tracker.total_tokens == 0
        assert tracker.final_model is None

    def test_custom_limits(self):
        """Test tracker with custom limits."""
        tracker = GenerationAttemptTracker(max_attempts=3, max_cost_usd=0.10)

        assert tracker.max_attempts == 3
        assert tracker.max_cost_usd == 0.10

    def test_add_attempt(self):
        """Test adding attempts to tracker."""
        tracker = GenerationAttemptTracker()
        attempt = GenerationAttempt(
            attempt_number=1,
            model="anthropic/claude-3-haiku",
            success=True,
            input_tokens=1000,
            output_tokens=200,
            cost_usd=0.00125,
            latency_ms=1500,
        )

        tracker.add_attempt(attempt)

        assert tracker.attempt_count == 1
        assert tracker.total_cost_usd == 0.00125
        assert tracker.total_tokens == 1200
        assert tracker.final_model == "anthropic/claude-3-haiku"

    def test_can_retry_within_limits(self):
        """Test can_retry when within limits."""
        tracker = GenerationAttemptTracker(max_attempts=3, max_cost_usd=0.10)

        # Add one attempt
        tracker.add_attempt(GenerationAttempt(
            attempt_number=1,
            model="test",
            success=False,
            cost_usd=0.01,
        ))

        assert tracker.can_retry() is True

    def test_can_retry_max_attempts_reached(self):
        """Test can_retry when max attempts reached."""
        tracker = GenerationAttemptTracker(max_attempts=2)

        # Add max attempts
        for i in range(2):
            tracker.add_attempt(GenerationAttempt(
                attempt_number=i + 1,
                model="test",
                success=False,
                cost_usd=0.001,
            ))

        assert tracker.can_retry() is False

    def test_can_retry_cost_cap_reached(self):
        """Test can_retry when cost cap reached."""
        tracker = GenerationAttemptTracker(max_cost_usd=0.05)

        # Add expensive attempt
        tracker.add_attempt(GenerationAttempt(
            attempt_number=1,
            model="test",
            success=False,
            cost_usd=0.06,  # Exceeds cap
        ))

        assert tracker.can_retry() is False

    def test_should_escalate_model_malformed_content(self):
        """Test model escalation recommendation for malformed content."""
        tracker = GenerationAttemptTracker()

        assert tracker.should_escalate_model(RetryReason.MALFORMED_CONTENT) is True

    def test_should_escalate_model_json_error(self):
        """Test model escalation recommendation for JSON errors."""
        tracker = GenerationAttemptTracker()

        assert tracker.should_escalate_model(RetryReason.JSON_PARSE_ERROR) is True

    def test_should_not_escalate_truncation_first(self):
        """Test that truncation tries token increase first."""
        tracker = GenerationAttemptTracker()

        # First truncation should not escalate
        assert tracker.should_escalate_model(RetryReason.TRUNCATION) is False

    def test_should_escalate_truncation_after_token_increase(self):
        """Test that truncation escalates after token increase failed."""
        tracker = GenerationAttemptTracker()

        # Add an attempt where we already tried increasing tokens
        tracker.add_attempt(GenerationAttempt(
            attempt_number=1,
            model="test",
            success=False,
            retry_action=RetryAction.INCREASE_TOKENS,
        ))

        # Now truncation should escalate
        assert tracker.should_escalate_model(RetryReason.TRUNCATION) is True

    def test_to_metadata(self):
        """Test converting tracker to metadata dictionary."""
        tracker = GenerationAttemptTracker()

        tracker.add_attempt(GenerationAttempt(
            attempt_number=1,
            model="anthropic/claude-3-haiku",
            success=False,
            retry_reason=RetryReason.MALFORMED_CONTENT,
            retry_action=RetryAction.ESCALATE_MODEL,
            input_tokens=1000,
            output_tokens=200,
            cost_usd=0.001,
            latency_ms=1500,
        ))

        tracker.add_attempt(GenerationAttempt(
            attempt_number=2,
            model="anthropic/claude-3.5-sonnet",
            success=True,
            input_tokens=1000,
            output_tokens=300,
            cost_usd=0.005,
            latency_ms=2000,
        ))

        metadata = tracker.to_metadata()

        assert metadata["total_attempts"] == 2
        assert metadata["total_cost_usd"] == 0.006
        assert metadata["total_tokens"] == 2500
        assert metadata["final_model"] == "anthropic/claude-3.5-sonnet"
        assert len(metadata["attempts"]) == 2
        assert "total_latency_ms" in metadata


@pytest.mark.unit
class TestDetermineRetryStrategy:
    """Test determine_retry_strategy function."""

    def test_rate_limit_retries_same_model(self):
        """Test that rate limit retries on same model."""
        tracker = GenerationAttemptTracker()

        action, model_idx, tokens = determine_retry_strategy(
            reason=RetryReason.RATE_LIMIT,
            current_model_index=0,
            current_max_tokens=4000,
            tracker=tracker,
        )

        assert action == RetryAction.SAME_MODEL
        assert model_idx is None
        assert tokens is None

    def test_network_error_retries_same_model(self):
        """Test that network error retries on same model."""
        tracker = GenerationAttemptTracker()

        action, model_idx, tokens = determine_retry_strategy(
            reason=RetryReason.NETWORK_ERROR,
            current_model_index=1,
            current_max_tokens=4000,
            tracker=tracker,
        )

        assert action == RetryAction.SAME_MODEL

    def test_timeout_retries_same_model(self):
        """Test that timeout retries on same model."""
        tracker = GenerationAttemptTracker()

        action, model_idx, tokens = determine_retry_strategy(
            reason=RetryReason.TIMEOUT,
            current_model_index=0,
            current_max_tokens=4000,
            tracker=tracker,
        )

        assert action == RetryAction.SAME_MODEL

    def test_model_unavailable_escalates(self):
        """Test that model unavailable escalates immediately."""
        tracker = GenerationAttemptTracker()

        action, model_idx, tokens = determine_retry_strategy(
            reason=RetryReason.MODEL_UNAVAILABLE,
            current_model_index=0,
            current_max_tokens=4000,
            tracker=tracker,
        )

        assert action == RetryAction.ESCALATE_MODEL
        assert model_idx == 1

    def test_truncation_increases_tokens_first(self):
        """Test that truncation increases tokens before escalating."""
        tracker = GenerationAttemptTracker()

        action, model_idx, tokens = determine_retry_strategy(
            reason=RetryReason.TRUNCATION,
            current_model_index=0,
            current_max_tokens=4000,
            tracker=tracker,
        )

        assert action == RetryAction.INCREASE_TOKENS
        assert model_idx is None
        assert tokens == 8000  # Doubled

    def test_truncation_respects_token_cap(self):
        """Test that truncation respects max token cap."""
        tracker = GenerationAttemptTracker()

        action, model_idx, tokens = determine_retry_strategy(
            reason=RetryReason.TRUNCATION,
            current_model_index=0,
            current_max_tokens=12000,
            tracker=tracker,
            max_tokens_cap=16000,
        )

        assert action == RetryAction.INCREASE_TOKENS
        assert tokens == 16000  # Capped

    def test_truncation_escalates_at_token_cap(self):
        """Test that truncation escalates when at token cap."""
        tracker = GenerationAttemptTracker()

        action, model_idx, tokens = determine_retry_strategy(
            reason=RetryReason.TRUNCATION,
            current_model_index=0,
            current_max_tokens=16000,
            tracker=tracker,
            max_tokens_cap=16000,
        )

        assert action == RetryAction.ESCALATE_MODEL
        assert model_idx == 1

    def test_json_error_adds_hint_first(self):
        """Test that JSON error adds prompt hint before escalating."""
        tracker = GenerationAttemptTracker()

        action, model_idx, tokens = determine_retry_strategy(
            reason=RetryReason.JSON_PARSE_ERROR,
            current_model_index=0,
            current_max_tokens=4000,
            tracker=tracker,
        )

        assert action == RetryAction.ADD_PROMPT_HINT
        assert model_idx is None

    def test_json_error_escalates_after_hint(self):
        """Test that JSON error escalates after hint was tried."""
        tracker = GenerationAttemptTracker()
        tracker.add_attempt(GenerationAttempt(
            attempt_number=1,
            model="test",
            success=False,
            retry_action=RetryAction.ADD_PROMPT_HINT,
        ))

        action, model_idx, tokens = determine_retry_strategy(
            reason=RetryReason.JSON_PARSE_ERROR,
            current_model_index=0,
            current_max_tokens=4000,
            tracker=tracker,
        )

        assert action == RetryAction.ESCALATE_MODEL
        assert model_idx == 1

    def test_malformed_content_escalates_immediately(self):
        """Test that malformed content escalates immediately."""
        tracker = GenerationAttemptTracker()

        action, model_idx, tokens = determine_retry_strategy(
            reason=RetryReason.MALFORMED_CONTENT,
            current_model_index=2,
            current_max_tokens=4000,
            tracker=tracker,
        )

        assert action == RetryAction.ESCALATE_MODEL
        assert model_idx == 3

    def test_raises_when_cannot_retry(self):
        """Test that StopIteration is raised when limits exceeded."""
        tracker = GenerationAttemptTracker(max_attempts=1)
        tracker.add_attempt(GenerationAttempt(
            attempt_number=1,
            model="test",
            success=False,
        ))

        with pytest.raises(StopIteration):
            determine_retry_strategy(
                reason=RetryReason.MALFORMED_CONTENT,
                current_model_index=0,
                current_max_tokens=4000,
                tracker=tracker,
            )


@pytest.mark.unit
class TestIsMalformedContent:
    """Test is_malformed_content helper function."""

    def test_detects_unable_to_parse(self):
        """Test detection of [Unable to parse...] marker."""
        text = "[Unable to parse summary format. Raw content preview:]\n\nSome content"
        assert is_malformed_content(text) is True

    def test_detects_extraction_failure(self):
        """Test detection of extraction failure message."""
        text = "Summary could not be extracted from response."
        assert is_malformed_content(text) is True

    def test_detects_raw_content_preview(self):
        """Test detection of raw content preview marker."""
        text = "Some intro [Raw content preview:] then more text"
        assert is_malformed_content(text) is True

    def test_normal_content_is_not_malformed(self):
        """Test that normal content is not flagged."""
        text = "This is a valid summary of the discussion about API design."
        assert is_malformed_content(text) is False

    def test_empty_content_is_not_malformed(self):
        """Test that empty content is not flagged as malformed."""
        text = ""
        assert is_malformed_content(text) is False


@pytest.mark.unit
class TestDetectQualityIssue:
    """Test detect_quality_issue function."""

    def test_detects_truncation(self):
        """Test detection of truncated response."""
        reason = detect_quality_issue(
            summary_text="Valid summary",
            key_points=["Point 1", "Point 2"],
            stop_reason="max_tokens",
            output_tokens=4000,
            max_tokens=4000,
        )

        assert reason == RetryReason.TRUNCATION

    def test_detects_malformed_summary(self):
        """Test detection of malformed summary text."""
        reason = detect_quality_issue(
            summary_text="[Unable to parse summary format]",
            key_points=["Point 1"],
            stop_reason="end_turn",
            output_tokens=200,
            max_tokens=4000,
        )

        assert reason == RetryReason.MALFORMED_CONTENT

    def test_detects_malformed_key_points(self):
        """Test detection of malformed key points."""
        reason = detect_quality_issue(
            summary_text="Valid summary",
            key_points=["Valid point", "[Unable to parse key point 2]"],
            stop_reason="end_turn",
            output_tokens=200,
            max_tokens=4000,
        )

        assert reason == RetryReason.MALFORMED_CONTENT

    def test_detects_empty_key_points(self):
        """Test detection of empty key points."""
        reason = detect_quality_issue(
            summary_text="Valid summary",
            key_points=["Valid point", "   ", ""],
            stop_reason="end_turn",
            output_tokens=200,
            max_tokens=4000,
        )

        assert reason == RetryReason.MALFORMED_CONTENT

    def test_no_issue_for_valid_output(self):
        """Test that valid output returns None."""
        reason = detect_quality_issue(
            summary_text="This is a perfectly valid summary.",
            key_points=["Point 1", "Point 2", "Point 3"],
            stop_reason="end_turn",
            output_tokens=200,
            max_tokens=4000,
        )

        assert reason is None
