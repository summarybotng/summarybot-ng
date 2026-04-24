"""
Slack OAuth authentication handler (ADR-043).

Implements OAuth 2.0 flow for Slack app installation with two-tier scopes.
"""

import os
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, List
from urllib.parse import urlencode

import httpx

from .models import SlackWorkspace, SlackScopeTier, SLACK_SCOPES_PUBLIC, SLACK_SCOPES_FULL
from .token_store import SecureSlackTokenStore
from ..utils.time import utc_now_naive

logger = logging.getLogger(__name__)

# Slack OAuth endpoints
SLACK_OAUTH_AUTHORIZE = "https://slack.com/oauth/v2/authorize"
SLACK_OAUTH_TOKEN = "https://slack.com/api/oauth.v2.access"


class SlackOAuthError(Exception):
    """Slack OAuth error with code and description."""

    def __init__(self, code: str, description: str = ""):
        self.code = code
        self.description = description
        super().__init__(f"Slack OAuth error: {code} - {description}")


class SlackAuth:
    """Handles Slack OAuth app installation flow (ADR-043 Section 3).

    Supports two-tier OAuth scopes:
    - PUBLIC tier: Public channels only (default, safer)
    - FULL tier: All channels including private (requires admin approval)
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        signing_secret: Optional[str] = None,
    ):
        """Initialize Slack OAuth handler.

        Args:
            client_id: Slack app client ID
            client_secret: Slack app client secret
            redirect_uri: OAuth redirect URI
            signing_secret: Slack signing secret for webhook verification
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.signing_secret = signing_secret

        # Pending OAuth states for CSRF protection (state -> (created_at, discord_user_id, scope_tier, guild_id))
        self._pending_states: Dict[str, Tuple[datetime, str, SlackScopeTier, Optional[str]]] = {}

        # HTTP client
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def get_scopes_for_tier(self, tier: SlackScopeTier) -> List[str]:
        """Get OAuth scopes for a tier.

        Args:
            tier: Scope tier (PUBLIC or FULL)

        Returns:
            List of OAuth scope strings
        """
        if tier == SlackScopeTier.FULL:
            return SLACK_SCOPES_FULL
        return SLACK_SCOPES_PUBLIC

    def create_oauth_state(
        self,
        discord_user_id: str,
        scope_tier: SlackScopeTier = SlackScopeTier.PUBLIC,
        guild_id: Optional[str] = None,
    ) -> str:
        """Generate and store OAuth state token.

        Args:
            discord_user_id: Discord user ID initiating the install
            scope_tier: Requested scope tier
            guild_id: Discord guild ID to link workspace to

        Returns:
            State token for CSRF protection
        """
        state = secrets.token_urlsafe(32)
        self._pending_states[state] = (utc_now_naive(), discord_user_id, scope_tier, guild_id)

        # Cleanup expired states (>10 min)
        cutoff = utc_now_naive() - timedelta(minutes=10)
        self._pending_states = {
            s: v for s, v in self._pending_states.items()
            if v[0] > cutoff
        }

        return state

    def validate_oauth_state(self, state: str) -> Optional[Tuple[str, SlackScopeTier, Optional[str]]]:
        """Validate and consume OAuth state token.

        Args:
            state: State token from callback

        Returns:
            Tuple of (discord_user_id, scope_tier, guild_id) if valid, None otherwise
        """
        state_data = self._pending_states.pop(state, None)
        if state_data is None:
            return None

        created_at, discord_user_id, scope_tier, guild_id = state_data
        if utc_now_naive() - created_at > timedelta(minutes=10):
            return None

        return discord_user_id, scope_tier, guild_id

    def get_install_url(
        self,
        discord_user_id: str,
        scope_tier: SlackScopeTier = SlackScopeTier.PUBLIC,
        team_id: Optional[str] = None,
        guild_id: Optional[str] = None,
    ) -> str:
        """Generate Slack app installation URL.

        Args:
            discord_user_id: Discord user ID to associate with install
            scope_tier: Requested scope tier
            team_id: Optional workspace ID to pre-select
            guild_id: Discord guild ID to link workspace to

        Returns:
            OAuth authorization URL
        """
        state = self.create_oauth_state(discord_user_id, scope_tier, guild_id)
        scopes = self.get_scopes_for_tier(scope_tier)

        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": ",".join(scopes),
            "state": state,
        }

        if team_id:
            params["team"] = team_id

        return f"{SLACK_OAUTH_AUTHORIZE}?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        state: str,
    ) -> Tuple[SlackWorkspace, str, Optional[str]]:
        """Exchange OAuth code for access token.

        Args:
            code: Authorization code from Slack
            state: State parameter for validation

        Returns:
            Tuple of (SlackWorkspace, discord_user_id, guild_id)

        Raises:
            SlackOAuthError: If exchange fails or state invalid
        """
        # Validate state
        state_data = self.validate_oauth_state(state)
        if state_data is None:
            raise SlackOAuthError("invalid_state", "OAuth state invalid or expired")

        discord_user_id, scope_tier, guild_id = state_data

        client = await self._get_http_client()

        # Exchange code for token
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": self.redirect_uri,
        }

        try:
            response = await client.post(
                SLACK_OAUTH_TOKEN,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            result = response.json()

            if not result.get("ok"):
                error = result.get("error", "unknown_error")
                raise SlackOAuthError(error, result.get("error", ""))

            # Extract workspace info
            team = result.get("team", {})
            authed_user = result.get("authed_user", {})
            enterprise = result.get("enterprise")

            # Get bot token (this is what we use for API calls)
            bot_token = result.get("access_token")
            if not bot_token:
                raise SlackOAuthError("no_token", "No bot token in response")

            # Encrypt token for storage
            encrypted_token = SecureSlackTokenStore.encrypt_token(bot_token)

            # Create workspace object
            workspace = SlackWorkspace(
                workspace_id=team.get("id", ""),
                workspace_name=team.get("name", ""),
                encrypted_bot_token=encrypted_token,
                bot_user_id=result.get("bot_user_id", ""),
                installed_by_discord_user=discord_user_id,
                installed_at=utc_now_naive(),
                scopes=result.get("scope", ""),
                scope_tier=scope_tier,
                is_enterprise=enterprise is not None,
                enterprise_id=enterprise.get("id") if enterprise else None,
            )

            logger.info(
                f"Slack workspace installed: {workspace.workspace_name} "
                f"({workspace.workspace_id}) by Discord user {discord_user_id}"
                f" for guild {guild_id}"
            )

            return workspace, discord_user_id, guild_id

        except httpx.RequestError as e:
            logger.error(f"Slack OAuth request failed: {e}")
            raise SlackOAuthError("request_failed", str(e))

    async def revoke_token(self, encrypted_token: str) -> bool:
        """Revoke a Slack access token.

        Args:
            encrypted_token: Encrypted bot token

        Returns:
            True if revoked successfully
        """
        try:
            token = SecureSlackTokenStore.decrypt_token(encrypted_token)
            client = await self._get_http_client()

            response = await client.post(
                "https://slack.com/api/auth.revoke",
                headers={"Authorization": f"Bearer {token}"},
            )

            result = response.json()
            return result.get("ok", False)

        except Exception as e:
            logger.error(f"Failed to revoke Slack token: {e}")
            return False


# Global auth instance
_slack_auth: Optional[SlackAuth] = None


def get_slack_auth() -> Optional[SlackAuth]:
    """Get the global Slack auth instance."""
    return _slack_auth


def initialize_slack_auth(
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    redirect_uri: Optional[str] = None,
    signing_secret: Optional[str] = None,
) -> Optional[SlackAuth]:
    """Initialize the global Slack auth instance.

    Uses environment variables if arguments not provided:
    - SLACK_CLIENT_ID
    - SLACK_CLIENT_SECRET
    - SLACK_REDIRECT_URI
    - SLACK_SIGNING_SECRET

    Returns:
        SlackAuth instance if configured, None otherwise
    """
    global _slack_auth

    client_id = client_id or os.environ.get("SLACK_CLIENT_ID")
    client_secret = client_secret or os.environ.get("SLACK_CLIENT_SECRET")
    redirect_uri = redirect_uri or os.environ.get("SLACK_REDIRECT_URI")
    signing_secret = signing_secret or os.environ.get("SLACK_SIGNING_SECRET")

    if not all([client_id, client_secret, redirect_uri]):
        logger.warning("Slack OAuth not configured: missing client_id, client_secret, or redirect_uri")
        return None

    _slack_auth = SlackAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        signing_secret=signing_secret,
    )

    return _slack_auth
