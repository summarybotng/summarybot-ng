"""
API key resolver for per-server OpenRouter keys.

Resolves the appropriate API key for a source based on configuration:
1. Server-specific key (if configured and enabled)
2. Default installation key (fallback)
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, Optional, Any, Literal

from .backends import get_backend_for_ref

logger = logging.getLogger(__name__)


class KeyStatus(Enum):
    """Status of an API key."""
    VALID = "valid"
    INVALID = "invalid"
    EXPIRED = "expired"
    RATE_LIMITED = "rate_limited"
    UNCHECKED = "unchecked"


@dataclass
class ResolvedKey:
    """Result of key resolution."""
    key: str
    source: Literal["server", "default"]
    source_key: str  # e.g., "discord:123456789"
    key_ref: str  # Reference used (e.g., "env:OPENROUTER_KEY_DISCORD_123")

    @property
    def api_key_used(self) -> str:
        """Format for cost ledger attribution."""
        if self.source == "server":
            return f"server:{self.source_key}"
        return "default"


class ApiKeyResolver:
    """
    Resolves API keys for generation requests.

    Handles the key hierarchy:
    1. Server-specific key (if configured and valid)
    2. Default installation key (fallback)
    """

    def __init__(
        self,
        default_key: Optional[str] = None,
        backend_config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize API key resolver.

        Args:
            default_key: Default OpenRouter API key
            backend_config: Configuration for key storage backends
        """
        self.default_key = default_key or os.environ.get("OPENROUTER_API_KEY")
        self.backend_config = backend_config or {}
        self._key_cache: Dict[str, tuple] = {}  # ref -> (key, expiry)
        self._validation_cache: Dict[str, tuple] = {}  # key -> (status, expiry)

    async def get_key_for_source(
        self,
        source_key: str,
        server_manifest: Optional[Dict[str, Any]] = None
    ) -> ResolvedKey:
        """
        Get the appropriate API key for a source.

        Args:
            source_key: Source identifier (e.g., "discord:123456789")
            server_manifest: Optional server manifest with api_keys config

        Returns:
            ResolvedKey with key value and metadata

        Raises:
            ValueError: If no API key is available
        """
        api_config = (server_manifest or {}).get("api_keys", {})

        # Check if server has its own key and wants to use it
        if api_config.get("use_server_key") and api_config.get("openrouter_key_ref"):
            key_ref = api_config["openrouter_key_ref"]

            try:
                key = await self._fetch_key(key_ref)
                if key:
                    # Optionally validate the key
                    if await self._validate_key(key):
                        logger.debug(f"Using server key for {source_key}")
                        return ResolvedKey(
                            key=key,
                            source="server",
                            source_key=source_key,
                            key_ref=key_ref,
                        )
                    else:
                        logger.warning(f"Server key validation failed for {source_key}")

            except Exception as e:
                logger.warning(f"Failed to fetch server key for {source_key}: {e}")

                # Only fall back if configured to do so
                if not api_config.get("fallback_to_default", True):
                    raise ValueError(
                        f"Server key fetch failed and fallback disabled for {source_key}"
                    )

        # Fall back to default key
        if not self.default_key:
            raise ValueError("No API key available (no server key and no default key)")

        return ResolvedKey(
            key=self.default_key,
            source="default",
            source_key=source_key,
            key_ref="default",
        )

    async def _fetch_key(self, key_ref: str) -> Optional[str]:
        """
        Fetch a key from the appropriate backend.

        Args:
            key_ref: Key reference

        Returns:
            API key value or None
        """
        # Check cache first
        if key_ref in self._key_cache:
            cached_key, expiry = self._key_cache[key_ref]
            if datetime.utcnow() < expiry:
                return cached_key

        # Get appropriate backend
        backend = get_backend_for_ref(key_ref, self.backend_config)
        key = await backend.get_key(key_ref)

        if key:
            # Cache for 5 minutes
            from datetime import timedelta
            self._key_cache[key_ref] = (key, datetime.utcnow() + timedelta(minutes=5))

        return key

    async def _validate_key(self, key: str) -> bool:
        """
        Validate an API key with OpenRouter.

        Args:
            key: API key to validate

        Returns:
            True if key is valid
        """
        # Check validation cache
        key_hash = hash(key)
        if key_hash in self._validation_cache:
            status, expiry = self._validation_cache[key_hash]
            if datetime.utcnow() < expiry:
                return status == KeyStatus.VALID

        # Validate with OpenRouter
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://openrouter.ai/api/v1/auth/key",
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=5.0
                )

                is_valid = response.status_code == 200

                # Cache result for 1 hour
                from datetime import timedelta
                status = KeyStatus.VALID if is_valid else KeyStatus.INVALID
                self._validation_cache[key_hash] = (
                    status,
                    datetime.utcnow() + timedelta(hours=1)
                )

                return is_valid

        except Exception as e:
            logger.warning(f"Key validation failed: {e}")
            # Don't cache failures - try again next time
            return True  # Assume valid on network errors

    async def validate_key(
        self,
        key_ref: str
    ) -> Dict[str, Any]:
        """
        Validate a key and return detailed status.

        Args:
            key_ref: Key reference

        Returns:
            Validation result with status and details
        """
        try:
            key = await self._fetch_key(key_ref)
            if not key:
                return {
                    "valid": False,
                    "key_ref": key_ref,
                    "error": "Key not found",
                    "validated_at": datetime.utcnow().isoformat(),
                }

            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://openrouter.ai/api/v1/auth/key",
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=10.0
                )

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "valid": True,
                        "key_ref": key_ref,
                        "credits_remaining": data.get("credits_remaining"),
                        "rate_limit": data.get("rate_limit"),
                        "validated_at": datetime.utcnow().isoformat(),
                    }
                else:
                    return {
                        "valid": False,
                        "key_ref": key_ref,
                        "error": f"HTTP {response.status_code}",
                        "validated_at": datetime.utcnow().isoformat(),
                    }

        except Exception as e:
            return {
                "valid": False,
                "key_ref": key_ref,
                "error": str(e),
                "validated_at": datetime.utcnow().isoformat(),
            }

    async def set_server_key(
        self,
        source_key: str,
        api_key: str,
        key_ref: Optional[str] = None
    ) -> str:
        """
        Set an API key for a server.

        Args:
            source_key: Source identifier
            api_key: API key value
            key_ref: Optional key reference (auto-generated if not provided)

        Returns:
            Key reference that was used
        """
        # Generate reference if not provided
        if not key_ref:
            # Use env var format by default
            safe_source = source_key.replace(":", "_").upper()
            key_ref = f"env:OPENROUTER_KEY_{safe_source}"

        backend = get_backend_for_ref(key_ref, self.backend_config)
        await backend.set_key(key_ref, api_key)

        # Clear caches
        self._key_cache.pop(key_ref, None)
        key_hash = hash(api_key)
        self._validation_cache.pop(key_hash, None)

        logger.info(f"Set API key for {source_key} with ref {key_ref}")
        return key_ref

    async def remove_server_key(self, key_ref: str) -> bool:
        """
        Remove an API key.

        Args:
            key_ref: Key reference

        Returns:
            True if deleted
        """
        backend = get_backend_for_ref(key_ref, self.backend_config)
        result = await backend.delete_key(key_ref)

        # Clear cache
        self._key_cache.pop(key_ref, None)

        logger.info(f"Removed API key with ref {key_ref}")
        return result

    def clear_caches(self) -> None:
        """Clear all caches."""
        self._key_cache.clear()
        self._validation_cache.clear()
