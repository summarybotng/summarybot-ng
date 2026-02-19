"""
Google Drive OAuth flow for per-server configuration.

Phase 2 of ADR-007: Per-server Google Drive sync.
"""

import base64
import hashlib
import json
import logging
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


@dataclass
class OAuthTokens:
    """OAuth token storage."""
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_at: Optional[datetime] = None
    scope: str = ""

    def is_expired(self) -> bool:
        """Check if access token is expired."""
        if not self.expires_at:
            return True
        # Consider expired 5 minutes before actual expiry
        return datetime.utcnow() >= (self.expires_at - timedelta(minutes=5))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_type": self.token_type,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "scope": self.scope,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OAuthTokens":
        expires_at = None
        if data.get("expires_at"):
            expires_at = datetime.fromisoformat(data["expires_at"])
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            token_type=data.get("token_type", "Bearer"),
            expires_at=expires_at,
            scope=data.get("scope", ""),
        )


@dataclass
class OAuthState:
    """OAuth state for CSRF protection."""
    state_token: str
    server_id: str
    user_id: str
    redirect_uri: str
    created_at: datetime = field(default_factory=datetime.utcnow)

    def is_expired(self) -> bool:
        """State tokens expire after 10 minutes."""
        return datetime.utcnow() > (self.created_at + timedelta(minutes=10))


class SecureTokenStore:
    """
    Secure storage for OAuth tokens.

    Tokens are encrypted at rest using Fernet symmetric encryption.
    """

    def __init__(self, storage_path: Path):
        """
        Initialize token store.

        Args:
            storage_path: Path to store encrypted tokens
        """
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._cipher = self._get_cipher()

    def _get_cipher(self) -> Fernet:
        """Get or create encryption cipher."""
        key = os.environ.get("ARCHIVE_TOKEN_ENCRYPTION_KEY")

        if not key:
            # Generate a key if not provided (will be lost on restart)
            logger.warning(
                "ARCHIVE_TOKEN_ENCRYPTION_KEY not set. "
                "Using ephemeral key - tokens will be lost on restart."
            )
            key = Fernet.generate_key().decode()
        else:
            # Ensure key is valid Fernet key (32 bytes, base64 encoded)
            try:
                # If it's a plain string, derive a key from it
                if len(key) != 44:  # Fernet keys are 44 chars base64
                    key = base64.urlsafe_b64encode(
                        hashlib.sha256(key.encode()).digest()
                    ).decode()
            except Exception:
                key = Fernet.generate_key().decode()

        return Fernet(key.encode())

    def _get_token_path(self, token_id: str) -> Path:
        """Get path for a token file."""
        # Sanitize token_id
        safe_id = "".join(c for c in token_id if c.isalnum() or c in "_-")
        return self.storage_path / f"{safe_id}.token"

    async def store_tokens(self, token_id: str, tokens: OAuthTokens) -> None:
        """
        Store encrypted tokens.

        Args:
            token_id: Unique identifier for the tokens
            tokens: OAuth tokens to store
        """
        token_path = self._get_token_path(token_id)

        # Encrypt token data
        token_data = json.dumps(tokens.to_dict()).encode()
        encrypted = self._cipher.encrypt(token_data)

        # Write to file
        token_path.write_bytes(encrypted)
        logger.info(f"Stored tokens for {token_id}")

    async def get_tokens(self, token_id: str) -> Optional[OAuthTokens]:
        """
        Retrieve and decrypt tokens.

        Args:
            token_id: Token identifier

        Returns:
            OAuth tokens if found
        """
        token_path = self._get_token_path(token_id)

        if not token_path.exists():
            return None

        try:
            encrypted = token_path.read_bytes()
            decrypted = self._cipher.decrypt(encrypted)
            data = json.loads(decrypted.decode())
            return OAuthTokens.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to decrypt tokens for {token_id}: {e}")
            return None

    async def delete_tokens(self, token_id: str) -> bool:
        """
        Delete tokens.

        Args:
            token_id: Token identifier

        Returns:
            True if deleted
        """
        token_path = self._get_token_path(token_id)

        if token_path.exists():
            token_path.unlink()
            logger.info(f"Deleted tokens for {token_id}")
            return True
        return False

    async def has_tokens(self, token_id: str) -> bool:
        """Check if tokens exist."""
        return self._get_token_path(token_id).exists()


class GoogleOAuthFlow:
    """
    Handles Google OAuth 2.0 flow for Drive access.
    """

    GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
    SCOPES = [
        "https://www.googleapis.com/auth/drive.file",  # Create/access app files
        "https://www.googleapis.com/auth/drive.metadata.readonly",  # Browse existing folders
    ]

    def __init__(self, token_store: SecureTokenStore):
        """
        Initialize OAuth flow.

        Args:
            token_store: Secure token storage
        """
        self.token_store = token_store
        self._pending_states: Dict[str, OAuthState] = {}

    @property
    def client_id(self) -> str:
        """Get client ID from environment (dynamic reload)."""
        return os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")

    @property
    def client_secret(self) -> str:
        """Get client secret from environment (dynamic reload)."""
        return os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")

    @property
    def redirect_uri(self) -> str:
        """Get redirect URI from environment."""
        return os.environ.get(
            "GOOGLE_OAUTH_REDIRECT_URI",
            "https://summarybot-ng.fly.dev/api/v1/archive/oauth/google/callback"
        )

    def is_configured(self) -> bool:
        """Check if OAuth is configured."""
        return bool(self.client_id and self.client_secret)

    def generate_auth_url(self, server_id: str, user_id: str) -> tuple[str, str]:
        """
        Generate OAuth authorization URL.

        Args:
            server_id: Discord server ID
            user_id: Discord user ID initiating the flow

        Returns:
            Tuple of (auth_url, state_token)
        """
        if not self.is_configured():
            raise ValueError("Google OAuth not configured")

        # Generate state token for CSRF protection
        state_token = secrets.token_urlsafe(32)

        # Store state
        self._pending_states[state_token] = OAuthState(
            state_token=state_token,
            server_id=server_id,
            user_id=user_id,
            redirect_uri=self.redirect_uri,
        )

        # Clean up expired states
        self._cleanup_expired_states()

        # Build auth URL
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.SCOPES),
            "access_type": "offline",  # Get refresh token
            "prompt": "consent",  # Always show consent to get refresh token
            "state": state_token,
        }

        auth_url = f"{self.GOOGLE_AUTH_URL}?{urlencode(params)}"
        return auth_url, state_token

    def validate_state(self, state_token: str) -> Optional[OAuthState]:
        """
        Validate and retrieve state from token.

        Args:
            state_token: State token from callback

        Returns:
            OAuth state if valid
        """
        state = self._pending_states.get(state_token)

        if not state:
            return None

        if state.is_expired():
            del self._pending_states[state_token]
            return None

        # Remove state after validation (one-time use)
        del self._pending_states[state_token]
        return state

    async def exchange_code(self, code: str, state: OAuthState) -> OAuthTokens:
        """
        Exchange authorization code for tokens.

        Args:
            code: Authorization code from callback
            state: Validated OAuth state

        Returns:
            OAuth tokens
        """
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.GOOGLE_TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": state.redirect_uri,
                },
            )

            if response.status_code != 200:
                error = response.json()
                raise ValueError(f"Token exchange failed: {error}")

            data = response.json()

            # Calculate expiry time
            expires_at = None
            if "expires_in" in data:
                expires_at = datetime.utcnow() + timedelta(seconds=data["expires_in"])

            tokens = OAuthTokens(
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token", ""),
                token_type=data.get("token_type", "Bearer"),
                expires_at=expires_at,
                scope=data.get("scope", ""),
            )

            # Store tokens
            token_id = f"srv_{state.server_id}_gdrive"
            await self.token_store.store_tokens(token_id, tokens)

            return tokens

    async def refresh_tokens(self, token_id: str) -> Optional[OAuthTokens]:
        """
        Refresh expired access token.

        Args:
            token_id: Token identifier

        Returns:
            Refreshed tokens if successful
        """
        import httpx

        tokens = await self.token_store.get_tokens(token_id)
        if not tokens or not tokens.refresh_token:
            return None

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.GOOGLE_TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": tokens.refresh_token,
                    "grant_type": "refresh_token",
                },
            )

            if response.status_code != 200:
                logger.error(f"Token refresh failed for {token_id}")
                return None

            data = response.json()

            # Calculate expiry time
            expires_at = None
            if "expires_in" in data:
                expires_at = datetime.utcnow() + timedelta(seconds=data["expires_in"])

            # Update tokens (keep existing refresh token if not returned)
            new_tokens = OAuthTokens(
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token", tokens.refresh_token),
                token_type=data.get("token_type", "Bearer"),
                expires_at=expires_at,
                scope=data.get("scope", tokens.scope),
            )

            await self.token_store.store_tokens(token_id, new_tokens)
            return new_tokens

    async def get_valid_tokens(self, token_id: str) -> Optional[OAuthTokens]:
        """
        Get valid (non-expired) tokens, refreshing if necessary.

        Args:
            token_id: Token identifier

        Returns:
            Valid tokens if available
        """
        tokens = await self.token_store.get_tokens(token_id)
        if not tokens:
            return None

        if tokens.is_expired():
            tokens = await self.refresh_tokens(token_id)

        return tokens

    async def disconnect(self, server_id: str) -> bool:
        """
        Disconnect Google Drive for a server.

        Args:
            server_id: Discord server ID

        Returns:
            True if disconnected
        """
        token_id = f"srv_{server_id}_gdrive"
        return await self.token_store.delete_tokens(token_id)

    def _cleanup_expired_states(self) -> None:
        """Remove expired state tokens."""
        expired = [
            token for token, state in self._pending_states.items()
            if state.is_expired()
        ]
        for token in expired:
            del self._pending_states[token]


# Singleton instances
_token_store: Optional[SecureTokenStore] = None
_oauth_flow: Optional[GoogleOAuthFlow] = None


def get_token_store(archive_root: Path) -> SecureTokenStore:
    """Get or create token store singleton."""
    global _token_store
    if _token_store is None:
        storage_path = archive_root / ".tokens"
        _token_store = SecureTokenStore(storage_path)
    return _token_store


def get_oauth_flow(archive_root: Path) -> GoogleOAuthFlow:
    """Get or create OAuth flow singleton."""
    global _oauth_flow
    if _oauth_flow is None:
        token_store = get_token_store(archive_root)
        _oauth_flow = GoogleOAuthFlow(token_store)
    return _oauth_flow
