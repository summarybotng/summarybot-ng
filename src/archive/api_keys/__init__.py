"""
API key management for per-server OpenRouter keys.

Implements ADR-006 Section 4.6: Per-Server API Keys.
"""

from .resolver import ApiKeyResolver, ResolvedKey, KeyStatus
from .backends import (
    ApiKeyBackend,
    EnvVarBackend,
    EncryptedFileBackend,
)

__all__ = [
    "ApiKeyResolver",
    "ResolvedKey",
    "KeyStatus",
    "ApiKeyBackend",
    "EnvVarBackend",
    "EncryptedFileBackend",
]
