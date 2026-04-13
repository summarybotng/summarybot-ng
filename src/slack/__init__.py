"""
Slack workspace integration package (ADR-043).

Provides OAuth installation, API client, message processing, and
webhook event handling for Slack workspace integration.

Phase 1: Token Storage, OAuth, Polling
- models.py: Data models (SlackWorkspace, SlackChannel, SlackUser)
- token_store.py: Fernet-encrypted token storage
- rate_limiter.py: Tier-based API rate limiting
- client.py: Slack Web API client
- auth.py: OAuth 2.0 flow handler
- normalizer.py: Message → ProcessedMessage conversion

Phase 2: Events API (ADR-043 Section 5)
- signature.py: HMAC signature verification
- dedup.py: Event deduplication
- events.py: Events API webhook handler

Phase 3: Threads and Files (ADR-043 Section 6)
- thread_handler.py: Thread reply fetching
- file_handler.py: File download with expiration handling
"""

from .models import (
    SlackWorkspace,
    SlackChannel,
    SlackUser,
    SlackMessage,
    SlackScopeTier,
    SlackChannelType,
    SLACK_SCOPES_PUBLIC,
    SLACK_SCOPES_FULL,
)
from .token_store import SecureSlackTokenStore
from .rate_limiter import (
    SlackRateLimiter,
    SlackAPITier,
    get_rate_limiter,
)
from .client import SlackClient, SlackAPIError
from .auth import (
    SlackAuth,
    SlackOAuthError,
    get_slack_auth,
    initialize_slack_auth,
)
from .normalizer import SlackMessageProcessor, SlackThreadReconstructor
# Phase 2: Events API
from .signature import (
    verify_slack_signature,
    verify_request_signature,
    SlackSignatureError,
)
from .dedup import (
    SlackEventDeduplicator,
    get_deduplicator,
    initialize_deduplicator,
    shutdown_deduplicator,
)
from .events import router as events_router, register_event_handler
# Phase 3: Threads and Files
from .thread_handler import SlackThreadHandler, ThreadInfo, ThreadReplies
from .file_handler import SlackFileHandler, SlackFile

__all__ = [
    # Models
    "SlackWorkspace",
    "SlackChannel",
    "SlackUser",
    "SlackMessage",
    "SlackScopeTier",
    "SlackChannelType",
    "SLACK_SCOPES_PUBLIC",
    "SLACK_SCOPES_FULL",
    # Token Storage
    "SecureSlackTokenStore",
    # Rate Limiting
    "SlackRateLimiter",
    "SlackAPITier",
    "get_rate_limiter",
    # Client
    "SlackClient",
    "SlackAPIError",
    # OAuth
    "SlackAuth",
    "SlackOAuthError",
    "get_slack_auth",
    "initialize_slack_auth",
    # Message Processing
    "SlackMessageProcessor",
    "SlackThreadReconstructor",
    # Signature Verification (Phase 2)
    "verify_slack_signature",
    "verify_request_signature",
    "SlackSignatureError",
    # Event Deduplication (Phase 2)
    "SlackEventDeduplicator",
    "get_deduplicator",
    "initialize_deduplicator",
    "shutdown_deduplicator",
    # Events Router (Phase 2)
    "events_router",
    "register_event_handler",
    # Thread Handling (Phase 3)
    "SlackThreadHandler",
    "ThreadInfo",
    "ThreadReplies",
    # File Handling (Phase 3)
    "SlackFileHandler",
    "SlackFile",
]
