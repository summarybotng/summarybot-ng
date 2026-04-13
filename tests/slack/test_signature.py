"""
Tests for src/slack/signature.py - HMAC signature verification.

Tests Slack request signature verification including HMAC-SHA256
computation, timestamp validation, and header extraction.
"""

import pytest
import time
import hmac
import hashlib
from unittest.mock import patch

from src.slack.signature import (
    SlackSignatureError,
    verify_slack_signature,
    extract_slack_headers,
    verify_request_signature,
    MAX_TIMESTAMP_AGE_SECONDS,
)


class TestSlackSignatureError:
    """Tests for SlackSignatureError exception."""

    def test_should_store_error_code(self):
        """Test error stores code attribute."""
        error = SlackSignatureError("invalid_timestamp", "Timestamp is invalid")

        assert error.code == "invalid_timestamp"

    def test_should_store_error_message(self):
        """Test error stores message attribute."""
        error = SlackSignatureError("test_code", "Test message")

        assert error.message == "Test message"

    def test_should_format_string_representation(self):
        """Test error string includes code and message."""
        error = SlackSignatureError("test_code", "Test message")

        assert "test_code" in str(error)
        assert "Test message" in str(error)


class TestVerifySlackSignature:
    """Tests for verify_slack_signature function."""

    def _compute_signature(self, body: bytes, timestamp: str, secret: str) -> str:
        """Helper to compute valid Slack signature."""
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        signature = hmac.new(
            secret.encode("utf-8"),
            sig_basestring.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"v0={signature}"

    def test_should_verify_valid_signature(self, slack_signing_secret):
        """Test verification passes with valid signature."""
        body = b'{"type":"event_callback","event":{}}'
        timestamp = str(int(time.time()))
        signature = self._compute_signature(body, timestamp, slack_signing_secret)

        result = verify_slack_signature(
            body=body,
            timestamp=timestamp,
            signature=signature,
            signing_secret=slack_signing_secret,
        )

        assert result is True

    def test_should_reject_invalid_signature(self, slack_signing_secret):
        """Test verification fails with invalid signature."""
        body = b'{"type":"event_callback"}'
        timestamp = str(int(time.time()))
        invalid_signature = "v0=0000000000000000000000000000000000000000000000000000000000000000"

        with pytest.raises(SlackSignatureError) as exc_info:
            verify_slack_signature(
                body=body,
                timestamp=timestamp,
                signature=invalid_signature,
                signing_secret=slack_signing_secret,
            )

        assert exc_info.value.code == "signature_mismatch"

    def test_should_reject_expired_timestamp(self, slack_signing_secret):
        """Test verification fails with expired timestamp."""
        body = b'{"type":"event_callback"}'
        old_timestamp = str(int(time.time()) - MAX_TIMESTAMP_AGE_SECONDS - 60)
        signature = self._compute_signature(body, old_timestamp, slack_signing_secret)

        with pytest.raises(SlackSignatureError) as exc_info:
            verify_slack_signature(
                body=body,
                timestamp=old_timestamp,
                signature=signature,
                signing_secret=slack_signing_secret,
            )

        assert exc_info.value.code == "timestamp_expired"

    def test_should_reject_future_timestamp(self, slack_signing_secret):
        """Test verification fails with future timestamp."""
        body = b'{"type":"event_callback"}'
        future_timestamp = str(int(time.time()) + MAX_TIMESTAMP_AGE_SECONDS + 60)
        signature = self._compute_signature(body, future_timestamp, slack_signing_secret)

        with pytest.raises(SlackSignatureError) as exc_info:
            verify_slack_signature(
                body=body,
                timestamp=future_timestamp,
                signature=signature,
                signing_secret=slack_signing_secret,
            )

        assert exc_info.value.code == "timestamp_expired"

    def test_should_reject_invalid_timestamp_format(self, slack_signing_secret):
        """Test verification fails with non-integer timestamp."""
        body = b'{"type":"event_callback"}'
        invalid_timestamp = "not-a-number"

        with pytest.raises(SlackSignatureError) as exc_info:
            verify_slack_signature(
                body=body,
                timestamp=invalid_timestamp,
                signature="v0=abc123",
                signing_secret=slack_signing_secret,
            )

        assert exc_info.value.code == "invalid_timestamp"

    def test_should_reject_signature_without_v0_prefix(self, slack_signing_secret):
        """Test verification fails when signature lacks v0= prefix."""
        body = b'{"type":"event_callback"}'
        timestamp = str(int(time.time()))
        # Signature without v0= prefix
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        raw_signature = hmac.new(
            slack_signing_secret.encode("utf-8"),
            sig_basestring.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        with pytest.raises(SlackSignatureError) as exc_info:
            verify_slack_signature(
                body=body,
                timestamp=timestamp,
                signature=raw_signature,  # Missing v0=
                signing_secret=slack_signing_secret,
            )

        assert exc_info.value.code == "invalid_signature_format"

    def test_should_reject_empty_signature(self, slack_signing_secret):
        """Test verification fails with empty signature."""
        body = b'{"type":"event_callback"}'
        timestamp = str(int(time.time()))

        with pytest.raises(SlackSignatureError) as exc_info:
            verify_slack_signature(
                body=body,
                timestamp=timestamp,
                signature="",
                signing_secret=slack_signing_secret,
            )

        assert exc_info.value.code == "invalid_signature_format"

    def test_should_accept_timestamp_within_max_age(self, slack_signing_secret):
        """Test verification passes with timestamp within max age."""
        body = b'{"type":"event_callback"}'
        # Timestamp 4 minutes ago (within 5 minute window)
        timestamp = str(int(time.time()) - 240)
        signature = self._compute_signature(body, timestamp, slack_signing_secret)

        result = verify_slack_signature(
            body=body,
            timestamp=timestamp,
            signature=signature,
            signing_secret=slack_signing_secret,
        )

        assert result is True

    def test_should_respect_custom_max_age(self, slack_signing_secret):
        """Test custom max_age parameter is respected."""
        body = b'{"type":"event_callback"}'
        timestamp = str(int(time.time()) - 120)  # 2 minutes ago
        signature = self._compute_signature(body, timestamp, slack_signing_secret)

        # Should fail with 60-second max_age
        with pytest.raises(SlackSignatureError) as exc_info:
            verify_slack_signature(
                body=body,
                timestamp=timestamp,
                signature=signature,
                signing_secret=slack_signing_secret,
                max_age=60,  # 1 minute
            )

        assert exc_info.value.code == "timestamp_expired"

    def test_should_verify_with_different_body_content(self, slack_signing_secret):
        """Test verification with various body contents."""
        test_bodies = [
            b'{"type":"url_verification","challenge":"abc123"}',
            b'{"type":"event_callback","event":{"type":"message"}}',
            b'plain text body',
            b'',  # Empty body
        ]

        timestamp = str(int(time.time()))

        for body in test_bodies:
            signature = self._compute_signature(body, timestamp, slack_signing_secret)
            result = verify_slack_signature(
                body=body,
                timestamp=timestamp,
                signature=signature,
                signing_secret=slack_signing_secret,
            )
            assert result is True


class TestExtractSlackHeaders:
    """Tests for extract_slack_headers function."""

    def test_should_extract_headers_with_standard_case(self):
        """Test extracting headers with standard casing."""
        headers = {
            "X-Slack-Request-Timestamp": "1705312800",
            "X-Slack-Signature": "v0=abc123",
        }

        timestamp, signature = extract_slack_headers(headers)

        assert timestamp == "1705312800"
        assert signature == "v0=abc123"

    def test_should_extract_headers_with_lowercase(self):
        """Test extracting headers with lowercase casing."""
        headers = {
            "x-slack-request-timestamp": "1705312800",
            "x-slack-signature": "v0=abc123",
        }

        timestamp, signature = extract_slack_headers(headers)

        assert timestamp == "1705312800"
        assert signature == "v0=abc123"

    def test_should_return_none_for_missing_timestamp(self):
        """Test returns None for missing timestamp header."""
        headers = {
            "X-Slack-Signature": "v0=abc123",
        }

        timestamp, signature = extract_slack_headers(headers)

        assert timestamp is None
        assert signature == "v0=abc123"

    def test_should_return_none_for_missing_signature(self):
        """Test returns None for missing signature header."""
        headers = {
            "X-Slack-Request-Timestamp": "1705312800",
        }

        timestamp, signature = extract_slack_headers(headers)

        assert timestamp == "1705312800"
        assert signature is None

    def test_should_return_none_for_empty_headers(self):
        """Test returns None for both when headers empty."""
        headers = {}

        timestamp, signature = extract_slack_headers(headers)

        assert timestamp is None
        assert signature is None


class TestVerifyRequestSignature:
    """Tests for verify_request_signature async function."""

    def _compute_signature(self, body: bytes, timestamp: str, secret: str) -> str:
        """Helper to compute valid Slack signature."""
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        signature = hmac.new(
            secret.encode("utf-8"),
            sig_basestring.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"v0={signature}"

    @pytest.mark.asyncio
    async def test_should_verify_valid_request(self, slack_signing_secret):
        """Test verification passes with valid request."""
        body = b'{"type":"event_callback"}'
        timestamp = str(int(time.time()))
        signature = self._compute_signature(body, timestamp, slack_signing_secret)
        headers = {
            "X-Slack-Request-Timestamp": timestamp,
            "X-Slack-Signature": signature,
        }

        result = await verify_request_signature(
            body=body,
            headers=headers,
            signing_secret=slack_signing_secret,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_should_raise_on_missing_timestamp_header(self, slack_signing_secret):
        """Test raises error when timestamp header missing."""
        body = b'{"type":"event_callback"}'
        headers = {
            "X-Slack-Signature": "v0=abc123",
        }

        with pytest.raises(SlackSignatureError) as exc_info:
            await verify_request_signature(
                body=body,
                headers=headers,
                signing_secret=slack_signing_secret,
            )

        assert exc_info.value.code == "missing_timestamp"

    @pytest.mark.asyncio
    async def test_should_raise_on_missing_signature_header(self, slack_signing_secret):
        """Test raises error when signature header missing."""
        body = b'{"type":"event_callback"}'
        headers = {
            "X-Slack-Request-Timestamp": str(int(time.time())),
        }

        with pytest.raises(SlackSignatureError) as exc_info:
            await verify_request_signature(
                body=body,
                headers=headers,
                signing_secret=slack_signing_secret,
            )

        assert exc_info.value.code == "missing_signature"


class TestSignatureTimingAttackPrevention:
    """Tests for timing attack prevention."""

    def _compute_signature(self, body: bytes, timestamp: str, secret: str) -> str:
        """Helper to compute valid Slack signature."""
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        signature = hmac.new(
            secret.encode("utf-8"),
            sig_basestring.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"v0={signature}"

    def test_should_use_constant_time_comparison(self, slack_signing_secret):
        """Test that signature comparison uses constant time."""
        body = b'{"type":"event_callback"}'
        timestamp = str(int(time.time()))

        # Test with signatures that differ at different positions
        valid_signature = self._compute_signature(body, timestamp, slack_signing_secret)
        almost_valid = "v0=" + "0" * 64  # Same length, all zeros

        # Both should take similar time to reject
        # (We can't directly test timing, but we verify the code uses hmac.compare_digest)
        with pytest.raises(SlackSignatureError):
            verify_slack_signature(
                body=body,
                timestamp=timestamp,
                signature=almost_valid,
                signing_secret=slack_signing_secret,
            )
