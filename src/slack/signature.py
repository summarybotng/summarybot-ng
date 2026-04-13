"""
Slack request signature verification (ADR-043 Section 8.2).

Verifies HMAC-SHA256 signatures on incoming webhook requests from Slack
using the Slack Signing Secret.
"""

import hmac
import hashlib
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Maximum age of request timestamp (5 minutes per Slack docs)
MAX_TIMESTAMP_AGE_SECONDS = 60 * 5


class SlackSignatureError(Exception):
    """Raised when signature verification fails."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"Signature verification failed: {code} - {message}")


def verify_slack_signature(
    body: bytes,
    timestamp: str,
    signature: str,
    signing_secret: str,
    max_age: int = MAX_TIMESTAMP_AGE_SECONDS,
) -> bool:
    """Verify Slack request signature.

    Implements HMAC-SHA256 verification per Slack's signing secret spec:
    https://api.slack.com/authentication/verifying-requests-from-slack

    Args:
        body: Raw request body bytes
        timestamp: X-Slack-Request-Timestamp header value
        signature: X-Slack-Signature header value (format: v0=<hex_digest>)
        signing_secret: Slack app signing secret
        max_age: Maximum allowed age of timestamp in seconds

    Returns:
        True if signature is valid

    Raises:
        SlackSignatureError: If verification fails
    """
    # Validate timestamp to prevent replay attacks
    try:
        request_timestamp = int(timestamp)
    except (ValueError, TypeError):
        raise SlackSignatureError("invalid_timestamp", "Timestamp is not a valid integer")

    current_time = int(time.time())
    if abs(current_time - request_timestamp) > max_age:
        raise SlackSignatureError(
            "timestamp_expired",
            f"Request timestamp {request_timestamp} is too old (current: {current_time})"
        )

    # Validate signature format
    if not signature or not signature.startswith("v0="):
        raise SlackSignatureError("invalid_signature_format", "Signature must start with 'v0='")

    expected_signature = signature[3:]  # Remove "v0=" prefix

    # Compute HMAC-SHA256
    # Base string format: v0:{timestamp}:{body}
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    computed_signature = hmac.new(
        signing_secret.encode("utf-8"),
        sig_basestring.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    # Use constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(computed_signature, expected_signature):
        logger.warning(
            f"Slack signature mismatch. "
            f"Expected: {expected_signature[:16]}..., "
            f"Computed: {computed_signature[:16]}..."
        )
        raise SlackSignatureError("signature_mismatch", "HMAC signature does not match")

    return True


def extract_slack_headers(headers: dict) -> tuple[Optional[str], Optional[str]]:
    """Extract Slack signature headers from request headers.

    Args:
        headers: Request headers dict (case-insensitive keys supported)

    Returns:
        Tuple of (timestamp, signature) or (None, None) if missing
    """
    # Headers may be case-insensitive depending on framework
    timestamp = (
        headers.get("X-Slack-Request-Timestamp") or
        headers.get("x-slack-request-timestamp")
    )
    signature = (
        headers.get("X-Slack-Signature") or
        headers.get("x-slack-signature")
    )

    return timestamp, signature


async def verify_request_signature(
    body: bytes,
    headers: dict,
    signing_secret: str,
) -> bool:
    """Verify Slack request signature from headers.

    Convenience wrapper that extracts headers and calls verify_slack_signature.

    Args:
        body: Raw request body
        headers: Request headers
        signing_secret: Slack signing secret

    Returns:
        True if valid

    Raises:
        SlackSignatureError: If verification fails or headers missing
    """
    timestamp, signature = extract_slack_headers(headers)

    if not timestamp:
        raise SlackSignatureError("missing_timestamp", "X-Slack-Request-Timestamp header missing")

    if not signature:
        raise SlackSignatureError("missing_signature", "X-Slack-Signature header missing")

    return verify_slack_signature(body, timestamp, signature, signing_secret)
