"""
Tests for Slack integration modules (ADR-043).

This package contains unit tests for:
- models: Dataclasses, enums, serialization
- rate_limiter: Token bucket algorithm, tier limits
- token_store: Encryption/decryption, storage
- signature: HMAC verification, timestamp validation
- dedup: Event deduplication, TTL cache
- normalizer: Message conversion to ProcessedMessage
- events: Event handler, different event types
- thread_handler: Thread fetching logic
- client: API wrapper with mocked responses
"""
