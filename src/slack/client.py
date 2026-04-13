"""
Slack API client wrapper (ADR-043).

Provides async HTTP client for Slack Web API with rate limiting,
error handling, and automatic token management.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

import httpx

from .models import (
    SlackWorkspace, SlackChannel, SlackUser, SlackMessage,
    SlackChannelType, SlackScopeTier,
)
from .token_store import SecureSlackTokenStore
from .rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)

# Slack API endpoints
SLACK_API_BASE = "https://slack.com/api"


class SlackAPIError(Exception):
    """Slack API error with error code and details."""

    def __init__(self, error: str, message: str = "", response: Optional[Dict] = None):
        self.error = error
        self.message = message or error
        self.response = response or {}
        super().__init__(f"Slack API error: {error} - {message}")

    @property
    def is_rate_limited(self) -> bool:
        return self.error == "ratelimited"

    @property
    def is_token_revoked(self) -> bool:
        return self.error in ("token_revoked", "invalid_auth", "account_inactive")

    @property
    def is_channel_not_found(self) -> bool:
        return self.error in ("channel_not_found", "is_archived")


class SlackClient:
    """Async Slack Web API client (ADR-043).

    Handles rate limiting, token decryption, and response parsing.
    """

    def __init__(
        self,
        workspace: SlackWorkspace,
        timeout: float = 30.0,
    ):
        """Initialize Slack client.

        Args:
            workspace: SlackWorkspace with encrypted bot token
            timeout: HTTP request timeout in seconds
        """
        self.workspace = workspace
        self.workspace_id = workspace.workspace_id
        self._token = SecureSlackTokenStore.decrypt_token(workspace.encrypted_bot_token)
        self._rate_limiter = get_rate_limiter(workspace.workspace_id)
        self._http_client: Optional[httpx.AsyncClient] = None
        self._timeout = timeout

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=self._timeout,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
            )
        return self._http_client

    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def _request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make a rate-limited request to Slack API.

        Args:
            method: Slack API method (e.g., "conversations.list")
            params: Query parameters
            json_body: JSON body for POST requests

        Returns:
            Parsed JSON response

        Raises:
            SlackAPIError: On API errors
        """
        # Apply rate limiting
        await self._rate_limiter.acquire(method)

        url = f"{SLACK_API_BASE}/{method}"
        client = await self._get_http_client()

        try:
            if json_body:
                response = await client.post(url, json=json_body)
            else:
                response = await client.get(url, params=params)

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                self._rate_limiter.record_rate_limit(method, retry_after)
                raise SlackAPIError(
                    "ratelimited",
                    f"Rate limited, retry after {retry_after}s",
                    {"retry_after": retry_after},
                )

            data = response.json()

            if not data.get("ok", False):
                error = data.get("error", "unknown_error")
                raise SlackAPIError(error, data.get("error", ""), data)

            return data

        except httpx.RequestError as e:
            logger.error(f"Slack API request failed: {e}")
            raise SlackAPIError("request_failed", str(e))

    # =========================================================================
    # Team / Auth Methods
    # =========================================================================

    async def auth_test(self) -> Dict[str, Any]:
        """Test authentication and get workspace info.

        Returns:
            Dict with team_id, user_id, bot_id, etc.
        """
        return await self._request("auth.test")

    async def team_info(self) -> Dict[str, Any]:
        """Get workspace information.

        Returns:
            Dict with team info
        """
        data = await self._request("team.info")
        return data.get("team", {})

    # =========================================================================
    # Conversations Methods
    # =========================================================================

    async def list_channels(
        self,
        types: str = "public_channel",
        exclude_archived: bool = True,
        limit: int = 200,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List channels in the workspace.

        Args:
            types: Comma-separated channel types
            exclude_archived: Exclude archived channels
            limit: Max channels per page (default 200, max 1000)
            cursor: Pagination cursor

        Returns:
            Dict with channels list and response_metadata
        """
        params = {
            "types": types,
            "exclude_archived": str(exclude_archived).lower(),
            "limit": limit,
        }
        if cursor:
            params["cursor"] = cursor

        return await self._request("conversations.list", params=params)

    async def get_all_channels(
        self,
        include_private: bool = False,
    ) -> List[SlackChannel]:
        """Get all channels with pagination.

        Args:
            include_private: Include private channels (requires groups:read scope)

        Returns:
            List of SlackChannel objects
        """
        types = "public_channel"
        if include_private and self.workspace.can_access_private():
            types = "public_channel,private_channel"

        channels = []
        cursor = None

        while True:
            data = await self.list_channels(types=types, cursor=cursor)

            for ch in data.get("channels", []):
                channel = SlackChannel(
                    channel_id=ch["id"],
                    workspace_id=self.workspace_id,
                    channel_name=ch.get("name", ""),
                    channel_type=self._map_channel_type(ch),
                    is_shared=ch.get("is_shared", False) or ch.get("is_ext_shared", False),
                    is_archived=ch.get("is_archived", False),
                    topic=ch.get("topic", {}).get("value"),
                    purpose=ch.get("purpose", {}).get("value"),
                    member_count=ch.get("num_members", 0),
                )
                channels.append(channel)

            # Handle pagination
            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        return channels

    async def get_channel_history(
        self,
        channel_id: str,
        oldest: Optional[str] = None,
        latest: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get messages from a channel.

        Args:
            channel_id: Channel ID
            oldest: Only messages after this Unix timestamp
            latest: Only messages before this Unix timestamp
            limit: Max messages per page (default 100, max 1000)
            cursor: Pagination cursor

        Returns:
            Dict with messages and response_metadata
        """
        params = {
            "channel": channel_id,
            "limit": limit,
        }
        if oldest:
            params["oldest"] = oldest
        if latest:
            params["latest"] = latest
        if cursor:
            params["cursor"] = cursor

        return await self._request("conversations.history", params=params)

    async def get_thread_replies(
        self,
        channel_id: str,
        thread_ts: str,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get replies in a thread.

        Args:
            channel_id: Channel ID
            thread_ts: Parent message timestamp
            limit: Max replies per page
            cursor: Pagination cursor

        Returns:
            Dict with messages and response_metadata
        """
        params = {
            "channel": channel_id,
            "ts": thread_ts,
            "limit": limit,
        }
        if cursor:
            params["cursor"] = cursor

        return await self._request("conversations.replies", params=params)

    async def get_channel_info(self, channel_id: str) -> SlackChannel:
        """Get detailed channel information.

        Args:
            channel_id: Channel ID

        Returns:
            SlackChannel object
        """
        data = await self._request("conversations.info", params={"channel": channel_id})
        ch = data.get("channel", {})

        return SlackChannel(
            channel_id=ch["id"],
            workspace_id=self.workspace_id,
            channel_name=ch.get("name", ""),
            channel_type=self._map_channel_type(ch),
            is_shared=ch.get("is_shared", False) or ch.get("is_ext_shared", False),
            is_archived=ch.get("is_archived", False),
            topic=ch.get("topic", {}).get("value"),
            purpose=ch.get("purpose", {}).get("value"),
            member_count=ch.get("num_members", 0),
        )

    # =========================================================================
    # Users Methods
    # =========================================================================

    async def list_users(
        self,
        limit: int = 200,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List users in the workspace.

        Args:
            limit: Max users per page
            cursor: Pagination cursor

        Returns:
            Dict with members and response_metadata
        """
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor

        return await self._request("users.list", params=params)

    async def get_all_users(self) -> List[SlackUser]:
        """Get all users with pagination.

        Returns:
            List of SlackUser objects
        """
        users = []
        cursor = None

        while True:
            data = await self.list_users(cursor=cursor)

            for u in data.get("members", []):
                if u.get("deleted"):
                    continue  # Skip deactivated users

                profile = u.get("profile", {})
                user = SlackUser(
                    user_id=u["id"],
                    workspace_id=self.workspace_id,
                    display_name=profile.get("display_name") or profile.get("real_name", ""),
                    real_name=profile.get("real_name"),
                    email=profile.get("email"),
                    is_bot=u.get("is_bot", False),
                    is_admin=u.get("is_admin", False),
                    is_owner=u.get("is_owner", False),
                    avatar_url=profile.get("image_72"),
                    timezone=u.get("tz"),
                    status_text=profile.get("status_text"),
                    status_emoji=profile.get("status_emoji"),
                )
                users.append(user)

            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        return users

    async def get_user_info(self, user_id: str) -> SlackUser:
        """Get detailed user information.

        Args:
            user_id: User ID

        Returns:
            SlackUser object
        """
        data = await self._request("users.info", params={"user": user_id})
        u = data.get("user", {})
        profile = u.get("profile", {})

        return SlackUser(
            user_id=u["id"],
            workspace_id=self.workspace_id,
            display_name=profile.get("display_name") or profile.get("real_name", ""),
            real_name=profile.get("real_name"),
            email=profile.get("email"),
            is_bot=u.get("is_bot", False),
            is_admin=u.get("is_admin", False),
            is_owner=u.get("is_owner", False),
            avatar_url=profile.get("image_72"),
            timezone=u.get("tz"),
            status_text=profile.get("status_text"),
            status_emoji=profile.get("status_emoji"),
        )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _map_channel_type(self, channel_data: Dict[str, Any]) -> SlackChannelType:
        """Map Slack channel data to SlackChannelType."""
        if channel_data.get("is_im"):
            return SlackChannelType.DM
        elif channel_data.get("is_mpim"):
            return SlackChannelType.MPIM
        elif channel_data.get("is_private"):
            return SlackChannelType.PRIVATE
        else:
            return SlackChannelType.PUBLIC

    def parse_message(self, msg: Dict[str, Any], channel_id: str) -> SlackMessage:
        """Parse a Slack message dict into SlackMessage object.

        Args:
            msg: Raw message data from Slack API
            channel_id: Channel ID for context

        Returns:
            SlackMessage object
        """
        return SlackMessage(
            ts=msg["ts"],
            channel_id=channel_id,
            workspace_id=self.workspace_id,
            user_id=msg.get("user", msg.get("bot_id", "")),
            text=msg.get("text", ""),
            thread_ts=msg.get("thread_ts"),
            reply_count=msg.get("reply_count", 0),
            reply_users_count=msg.get("reply_users_count", 0),
            reactions=msg.get("reactions", []),
            attachments=msg.get("attachments", []),
            files=msg.get("files", []),
            is_edited="edited" in msg,
            edited_ts=msg.get("edited", {}).get("ts"),
            subtype=msg.get("subtype"),
            metadata=msg.get("metadata", {}),
        )
