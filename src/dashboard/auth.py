"""
Dashboard authentication with Discord OAuth and JWT.
"""

import os
import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict
from urllib.parse import urlencode

import httpx
from jose import jwt, JWTError
from cryptography.fernet import Fernet
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .models import DashboardUser, DashboardGuild, DashboardSession, GuildRole
from src.utils.time import utc_now_naive

logger = logging.getLogger(__name__)

# Discord API endpoints
DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_OAUTH_AUTHORIZE = "https://discord.com/oauth2/authorize"
DISCORD_OAUTH_TOKEN = f"{DISCORD_API_BASE}/oauth2/token"

# Required OAuth scopes
OAUTH_SCOPES = ["identify", "guilds"]


class DashboardAuth:
    """Handles Discord OAuth and JWT authentication."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        jwt_secret: str,
        encryption_key: Optional[bytes] = None,
        jwt_expiration_hours: int = 24,
        session_expiration_days: int = 7,
    ):
        """Initialize authentication handler.

        Args:
            client_id: Discord application client ID
            client_secret: Discord application client secret
            redirect_uri: OAuth redirect URI
            jwt_secret: Secret for JWT signing
            encryption_key: Fernet key for token encryption
            jwt_expiration_hours: JWT token expiration in hours
            session_expiration_days: Session expiration in days
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.jwt_secret = jwt_secret
        self.jwt_expiration_hours = jwt_expiration_hours
        self.session_expiration_days = session_expiration_days

        # Initialize encryption
        if encryption_key:
            self._cipher = Fernet(encryption_key)
        else:
            self._cipher = Fernet(Fernet.generate_key())
            logger.warning("No encryption key provided, using ephemeral key")

        # In-memory session store (replace with database in production)
        self._sessions: dict[str, DashboardSession] = {}

        # Pending OAuth states for CSRF protection (state_token -> created_at)
        self._pending_states: dict[str, datetime] = {}

        # HTTP client for Discord API
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

    # =========================================================================
    # OAuth Flow
    # =========================================================================

    def get_oauth_url(self, state: Optional[str] = None) -> str:
        """Generate Discord OAuth authorization URL.

        Args:
            state: Optional state parameter for CSRF protection

        Returns:
            Authorization URL
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(OAUTH_SCOPES),
        }
        if state:
            params["state"] = state

        return f"{DISCORD_OAUTH_AUTHORIZE}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> Tuple[str, str, int]:
        """Exchange OAuth code for tokens.

        Args:
            code: Authorization code from Discord

        Returns:
            Tuple of (access_token, refresh_token, expires_in)

        Raises:
            HTTPException: If token exchange fails
        """
        client = await self._get_http_client()

        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
        }

        try:
            response = await client.post(
                DISCORD_OAUTH_TOKEN,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                logger.error(f"Token exchange failed: {response.text}")
                raise HTTPException(
                    status_code=400,
                    detail={"code": "OAUTH_FAILED", "message": "Failed to exchange authorization code"},
                )

            token_data = response.json()
            return (
                token_data["access_token"],
                token_data["refresh_token"],
                token_data["expires_in"],
            )

        except httpx.RequestError as e:
            logger.error(f"Discord API request failed: {e}")
            raise HTTPException(
                status_code=502,
                detail={"code": "DISCORD_ERROR", "message": "Failed to connect to Discord"},
            )

    async def refresh_discord_token(self, refresh_token: str) -> Tuple[str, str, int]:
        """Refresh Discord access token.

        Args:
            refresh_token: Discord refresh token

        Returns:
            Tuple of (access_token, refresh_token, expires_in)
        """
        client = await self._get_http_client()

        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        response = await client.post(
            DISCORD_OAUTH_TOKEN,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=401,
                detail={"code": "TOKEN_REFRESH_FAILED", "message": "Failed to refresh token"},
            )

        token_data = response.json()
        return (
            token_data["access_token"],
            token_data["refresh_token"],
            token_data["expires_in"],
        )

    # =========================================================================
    # Discord API
    # =========================================================================

    async def get_user(self, access_token: str) -> DashboardUser:
        """Get Discord user info.

        Args:
            access_token: Discord access token

        Returns:
            DashboardUser object
        """
        client = await self._get_http_client()

        response = await client.get(
            f"{DISCORD_API_BASE}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=401,
                detail={"code": "INVALID_TOKEN", "message": "Invalid Discord token"},
            )

        data = response.json()
        return DashboardUser(
            id=data["id"],
            username=data["username"],
            discriminator=data.get("discriminator"),
            avatar=data.get("avatar"),
        )

    async def get_user_guilds(self, access_token: str) -> List[DashboardGuild]:
        """Get guilds the user is in.

        Args:
            access_token: Discord access token

        Returns:
            List of DashboardGuild objects
        """
        client = await self._get_http_client()

        response = await client.get(
            f"{DISCORD_API_BASE}/users/@me/guilds",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=401,
                detail={"code": "INVALID_TOKEN", "message": "Invalid Discord token"},
            )

        guilds = []
        for data in response.json():
            guilds.append(
                DashboardGuild(
                    id=data["id"],
                    name=data["name"],
                    icon=data.get("icon"),
                    owner=data.get("owner", False),
                    permissions=int(data.get("permissions", 0)),
                )
            )

        return guilds

    # =========================================================================
    # JWT Tokens
    # =========================================================================

    def create_jwt(
        self,
        user: DashboardUser,
        guild_ids: List[str],
        guild_roles: Optional[Dict[str, str]] = None,
    ) -> str:
        """Create JWT token for authenticated user.

        Args:
            user: Authenticated user
            guild_ids: List of accessible guild IDs
            guild_roles: Dict mapping guild_id to role (owner/admin/member)

        Returns:
            JWT token string
        """
        now = utc_now_naive()
        payload = {
            "sub": user.id,
            "username": user.username,
            "avatar": user.avatar,
            "guilds": guild_ids,
            "guild_roles": guild_roles or {},  # Maps guild_id to role string
            "iat": now,
            "exp": now + timedelta(hours=self.jwt_expiration_hours),
        }
        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")

    def verify_jwt(self, token: str) -> dict:
        """Verify and decode JWT token.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            HTTPException: If token is invalid or expired
        """
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
            logger.debug(f"JWT verified successfully for user: {payload.get('sub', 'unknown')}, secret prefix: {self.jwt_secret[:8]}...")
            return payload
        except JWTError as e:
            error_str = str(e).lower()
            # Log details for debugging
            logger.warning(f"JWT verification failed: {e}, secret prefix: {self.jwt_secret[:8]}...")
            try:
                # Decode without verification to see what's in the token
                unverified = jwt.decode(token, options={"verify_signature": False})
                logger.warning(f"Unverified token payload: sub={unverified.get('sub')}, auth_provider={unverified.get('auth_provider')}")
            except Exception:
                logger.warning("Could not decode token even without verification")
            if "expired" in error_str:
                raise HTTPException(
                    status_code=401,
                    detail={"code": "TOKEN_EXPIRED", "message": "Token has expired"},
                )
            raise HTTPException(
                status_code=401,
                detail={"code": "INVALID_TOKEN", "message": "Invalid token"},
            )

    def refresh_jwt(self, token: str) -> str:
        """Refresh JWT token if still valid.

        Args:
            token: Current JWT token

        Returns:
            New JWT token
        """
        payload = self.verify_jwt(token)

        # Create new token with same user info (preserving guild_roles)
        user = DashboardUser(
            id=payload["sub"],
            username=payload["username"],
            discriminator=None,
            avatar=payload.get("avatar"),
        )
        return self.create_jwt(user, payload["guilds"], payload.get("guild_roles", {}))

    async def refresh_jwt_with_guilds(
        self, token: str, bot_guild_ids: set[str]
    ) -> Tuple[str, List[str]]:
        """Refresh JWT token with a fresh guild list from Discord.

        Looks up the session, refreshes the Discord access token if needed,
        re-fetches guilds from the Discord API, and filters to guilds
        where the bot is present (now includes members).

        Args:
            token: Current JWT token
            bot_guild_ids: Set of guild IDs the bot is currently in

        Returns:
            Tuple of (new_jwt_token, updated_guild_ids)
        """
        payload = self.verify_jwt(token)

        user = DashboardUser(
            id=payload["sub"],
            username=payload["username"],
            discriminator=None,
            avatar=payload.get("avatar"),
        )

        # Try to get the session so we can call Discord for fresh guilds
        session = await self.get_session(token)
        if session is None:
            # No session -- cannot fetch fresh guilds without Discord token
            # Raise error so frontend can tell user to re-login
            logger.warning("No session found for token refresh, user must re-login")
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "SESSION_EXPIRED",
                    "message": "Session expired. Please log out and log back in to refresh your server list.",
                },
            )

        # Get a valid Discord access token (auto-refreshes if expired)
        discord_token = await self.get_discord_token(session)

        # Fetch fresh guild list from Discord
        all_guilds = await self.get_user_guilds(discord_token)

        # Filter to guilds where the bot is present (includes members now)
        accessible_guilds = [
            g for g in all_guilds
            if g.id in bot_guild_ids
        ]
        guild_ids = [g.id for g in accessible_guilds]
        guild_roles = {g.id: g.get_role().value for g in accessible_guilds}

        # Update session with new guild list
        session.manageable_guild_ids = guild_ids

        # Invalidate old JWT hash and create new token
        old_hash = self._hash_token(token)
        new_token = self.create_jwt(user, guild_ids, guild_roles)
        new_hash = self._hash_token(new_token)

        # Move session to new hash
        if old_hash in self._sessions:
            del self._sessions[old_hash]
        session.jwt_token_hash = new_hash
        self._sessions[new_hash] = session

        return new_token, guild_ids

    # =========================================================================
    # Session Management
    # =========================================================================

    def _encrypt(self, value: str) -> str:
        """Encrypt a string value."""
        return self._cipher.encrypt(value.encode()).decode()

    def _decrypt(self, value: str) -> str:
        """Decrypt a string value."""
        return self._cipher.decrypt(value.encode()).decode()

    def _hash_token(self, token: str) -> str:
        """Create hash of JWT token for session lookup."""
        return hashlib.sha256(token.encode()).hexdigest()

    async def create_session(
        self,
        user: DashboardUser,
        access_token: str,
        refresh_token: str,
        expires_in: int,
        manageable_guilds: List[DashboardGuild],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[str, DashboardSession]:
        """Create a new dashboard session.

        Args:
            user: Authenticated user
            access_token: Discord access token
            refresh_token: Discord refresh token
            expires_in: Token expiration in seconds
            manageable_guilds: Guilds user can access (includes members now)
            ip_address: Client IP address
            user_agent: Client user agent

        Returns:
            Tuple of (jwt_token, session)
        """
        now = utc_now_naive()
        guild_ids = [g.id for g in manageable_guilds]
        # Build guild_roles dict mapping guild_id to role string
        guild_roles = {g.id: g.get_role().value for g in manageable_guilds}

        # Create JWT with roles
        jwt_token = self.create_jwt(user, guild_ids, guild_roles)

        # Create session
        session = DashboardSession(
            id=secrets.token_urlsafe(32),
            discord_user_id=user.id,
            discord_username=user.username,
            discord_discriminator=user.discriminator,
            discord_avatar=user.avatar,
            discord_access_token=self._encrypt(access_token),
            discord_refresh_token=self._encrypt(refresh_token),
            token_expires_at=now + timedelta(seconds=expires_in),
            manageable_guild_ids=guild_ids,
            jwt_token_hash=self._hash_token(jwt_token),
            created_at=now,
            last_activity=now,
            expires_at=now + timedelta(days=self.session_expiration_days),
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Store session
        self._sessions[session.jwt_token_hash] = session

        return jwt_token, session

    async def get_session(self, jwt_token: str) -> Optional[DashboardSession]:
        """Get session by JWT token.

        Args:
            jwt_token: JWT token

        Returns:
            Session if found and valid, None otherwise
        """
        token_hash = self._hash_token(jwt_token)
        session = self._sessions.get(token_hash)

        if session and session.expires_at > utc_now_naive():
            # Update last activity
            session.last_activity = utc_now_naive()
            return session

        return None

    async def invalidate_session(self, jwt_token: str) -> bool:
        """Invalidate a session.

        Args:
            jwt_token: JWT token

        Returns:
            True if session was invalidated
        """
        token_hash = self._hash_token(jwt_token)
        if token_hash in self._sessions:
            del self._sessions[token_hash]
            return True
        return False

    async def get_discord_token(self, session: DashboardSession) -> str:
        """Get decrypted Discord access token, refreshing if needed.

        Args:
            session: Dashboard session

        Returns:
            Valid Discord access token
        """
        # Check if token needs refresh
        if session.token_expires_at <= utc_now_naive() + timedelta(minutes=5):
            # Refresh token
            refresh_token = self._decrypt(session.discord_refresh_token)
            access_token, new_refresh, expires_in = await self.refresh_discord_token(refresh_token)

            # Update session
            session.discord_access_token = self._encrypt(access_token)
            session.discord_refresh_token = self._encrypt(new_refresh)
            session.token_expires_at = utc_now_naive() + timedelta(seconds=expires_in)

            return access_token

        return self._decrypt(session.discord_access_token)

    def cleanup_expired_sessions(self):
        """Remove expired sessions."""
        now = utc_now_naive()
        expired = [
            token_hash
            for token_hash, session in self._sessions.items()
            if session.expires_at <= now
        ]
        for token_hash in expired:
            del self._sessions[token_hash]

    def create_oauth_state(self) -> str:
        """Generate and store a CSRF state token for OAuth flow."""
        state = secrets.token_urlsafe(32)
        self._pending_states[state] = utc_now_naive()
        # Cleanup expired states (>10 min)
        cutoff = utc_now_naive() - timedelta(minutes=10)
        self._pending_states = {s: t for s, t in self._pending_states.items() if t > cutoff}
        return state

    def validate_oauth_state(self, state: str) -> bool:
        """Validate and consume an OAuth state token. Returns True if valid."""
        created_at = self._pending_states.pop(state, None)
        if created_at is None:
            return False
        return utc_now_naive() - created_at <= timedelta(minutes=10)


# ============================================================================
# FastAPI Dependencies
# ============================================================================

# Security scheme
security = HTTPBearer(auto_error=False)

# Global auth instance (set by router)
_auth_instance: Optional[DashboardAuth] = None


def set_auth_instance(auth: DashboardAuth):
    """Set the global auth instance."""
    global _auth_instance
    _auth_instance = auth


def get_auth() -> DashboardAuth:
    """Get the auth instance."""
    if _auth_instance is None:
        raise RuntimeError("Auth not initialized")
    return _auth_instance


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """FastAPI dependency to get current authenticated user.

    Returns:
        JWT payload with user info

    Raises:
        HTTPException: If not authenticated
    """
    # Test bypass: check for X-Test-Auth-Key header
    # Two levels of access:
    #   - TEST_AUTH_ADMIN_SECRET: Admin-level access (can use admin-only endpoints like email)
    #   - TEST_AUTH_SECRET: User-level access (read-only, member permissions)
    #
    # SEC-002: Only allow test bypass in non-production environments or when TESTING=true
    provided_key = request.headers.get("X-Test-Auth-Key")
    if provided_key:
        environment = os.getenv("ENVIRONMENT", "development").lower()
        # SEC-FIX: Only allow test auth in explicit dev/test environments.
        # Never in production, regardless of TESTING flag.
        allowed_environments = ("development", "test", "testing", "ci")
        if environment not in allowed_environments:
            logger.warning(
                "Test auth bypass attempted in non-development environment. "
                f"Environment: {environment}, "
                f"Client IP: {request.client.host if request.client else 'unknown'}"
            )
            raise HTTPException(
                status_code=401,
                detail={"code": "UNAUTHORIZED", "message": "Test authentication not available"},
            )

        admin_secret = os.getenv("TEST_AUTH_ADMIN_SECRET")
        user_secret = os.getenv("TEST_AUTH_SECRET")

        is_admin = admin_secret and provided_key == admin_secret
        is_user = user_secret and provided_key == user_secret

        if is_admin or is_user:
            # Return a mock user - TEST_GUILD_ID can be comma-separated list or "*" for all
            test_guild_config = os.getenv("TEST_GUILD_ID", "*")
            if test_guild_config == "*":
                # Extract guild_id from path if present
                path_parts = request.url.path.split("/")
                guilds = []
                for i, part in enumerate(path_parts):
                    if part == "guilds" and i + 1 < len(path_parts):
                        next_part = path_parts[i + 1]
                        # Only add if it looks like a guild ID (all digits)
                        if next_part.isdigit():
                            guilds.append(next_part)
                        break

                # If no guild in path, include all bot guilds for list endpoints
                if not guilds:
                    from dashboard.routes import get_discord_bot
                    bot = get_discord_bot()
                    if bot and bot.client:
                        guilds = [str(g.id) for g in bot.client.guilds]
            else:
                guilds = [g.strip() for g in test_guild_config.split(",")]

            # Build guild_roles based on access level
            role = "admin" if is_admin else "member"
            guild_roles = {g: role for g in guilds}

            return {
                "sub": f"test_{role}_user_id",
                "username": f"test_{role}_user",
                "avatar": None,
                "guilds": guilds,
                "guild_roles": guild_roles,
                "iat": utc_now_naive(),
                "exp": utc_now_naive() + timedelta(hours=24),
            }

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Not authenticated"},
        )

    auth = get_auth()
    return auth.verify_jwt(credentials.credentials)


async def get_current_session(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> DashboardSession:
    """FastAPI dependency to get current session.

    Returns:
        Dashboard session

    Raises:
        HTTPException: If not authenticated or session invalid
    """
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Not authenticated"},
        )

    auth = get_auth()
    session = await auth.get_session(credentials.credentials)

    if session is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "SESSION_EXPIRED", "message": "Session has expired"},
        )

    return session


def require_guild_access(guild_id: str):
    """Create a dependency that requires access to a specific guild.

    Args:
        guild_id: Guild ID to check access for

    Returns:
        Dependency function
    """
    async def dependency(user: dict = Depends(get_current_user)) -> dict:
        if guild_id not in user.get("guilds", []):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "FORBIDDEN",
                    "message": "You don't have permission to access this guild",
                },
            )
        return user

    return dependency


def get_user_role(user: dict, guild_id: str) -> Optional[str]:
    """Get the user's role in a specific guild.

    Args:
        user: JWT payload dict
        guild_id: Guild ID to check

    Returns:
        Role string (owner/admin/member) or None if no access
    """
    guild_roles = user.get("guild_roles", {})
    return guild_roles.get(guild_id)


def is_guild_admin(user: dict, guild_id: str) -> bool:
    """Check if user has admin-level access to a guild.

    Args:
        user: JWT payload dict
        guild_id: Guild ID to check

    Returns:
        True if user is owner or admin
    """
    role = get_user_role(user, guild_id)
    return role in ("owner", "admin")


def require_guild_admin(guild_id: str, user: dict):
    """Check that user has admin access to a guild, raise 403 if not.

    Args:
        guild_id: Guild ID to check
        user: JWT payload dict

    Raises:
        HTTPException: If user is not admin/owner
    """
    if guild_id not in user.get("guilds", []):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "FORBIDDEN",
                "message": "You don't have permission to access this guild",
            },
        )

    if not is_guild_admin(user, guild_id):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "FORBIDDEN",
                "message": "This action requires admin permissions",
            },
        )
