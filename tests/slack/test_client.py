"""
Tests for src/slack/client.py - Slack API wrapper.

Tests the async Slack Web API client including rate limiting,
error handling, response parsing, and API method wrappers.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from src.slack.client import (
    SlackClient,
    SlackAPIError,
    SLACK_API_BASE,
)
from src.slack.models import (
    SlackWorkspace,
    SlackChannel,
    SlackUser,
    SlackMessage,
    SlackChannelType,
    SlackScopeTier,
)


class TestSlackAPIError:
    """Tests for SlackAPIError exception."""

    def test_should_store_error_code(self):
        """Test error stores error code."""
        error = SlackAPIError("invalid_auth", "Invalid authentication")

        assert error.error == "invalid_auth"

    def test_should_store_message(self):
        """Test error stores message."""
        error = SlackAPIError("test_error", "Test error message")

        assert error.message == "Test error message"

    def test_should_store_response(self):
        """Test error stores response dict."""
        response = {"ok": False, "error": "test_error", "detail": "extra info"}
        error = SlackAPIError("test_error", "Test", response)

        assert error.response == response

    def test_should_detect_rate_limited(self):
        """Test is_rate_limited property."""
        error = SlackAPIError("ratelimited", "Rate limited")

        assert error.is_rate_limited is True

    def test_should_detect_token_revoked(self):
        """Test is_token_revoked property."""
        for error_code in ["token_revoked", "invalid_auth", "account_inactive"]:
            error = SlackAPIError(error_code, "Auth error")
            assert error.is_token_revoked is True

    def test_should_detect_channel_not_found(self):
        """Test is_channel_not_found property."""
        for error_code in ["channel_not_found", "is_archived"]:
            error = SlackAPIError(error_code, "Channel error")
            assert error.is_channel_not_found is True


class TestSlackClientInit:
    """Tests for SlackClient initialization."""

    def test_should_initialize_with_workspace(self, slack_workspace):
        """Test client initializes from workspace."""
        client = SlackClient(slack_workspace)

        assert client.workspace is slack_workspace
        assert client.workspace_id == "T12345678"

    def test_should_decrypt_token(self, slack_workspace):
        """Test token is decrypted from workspace."""
        client = SlackClient(slack_workspace)

        # Token should be decrypted (not the encrypted version)
        assert client._token.startswith("xoxb-")

    def test_should_accept_custom_timeout(self, slack_workspace):
        """Test custom timeout is accepted."""
        client = SlackClient(slack_workspace, timeout=60.0)

        assert client._timeout == 60.0


class TestSlackClientRequest:
    """Tests for SlackClient HTTP requests."""

    @pytest.fixture
    def client(self, slack_workspace):
        """Create a client for testing."""
        return SlackClient(slack_workspace)

    @pytest.mark.asyncio
    async def test_should_make_get_request(self, client, mock_httpx_client):
        """Test GET request is made correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "data": "test"}
        mock_httpx_client.get.return_value = mock_response

        with patch.object(client, "_get_http_client", return_value=mock_httpx_client):
            with patch.object(client._rate_limiter, "acquire", new_callable=AsyncMock):
                result = await client._request("test.method", params={"key": "value"})

        assert result == {"ok": True, "data": "test"}
        mock_httpx_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_make_post_request_with_json(self, client, mock_httpx_client):
        """Test POST request with JSON body."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_get_http_client", return_value=mock_httpx_client):
            with patch.object(client._rate_limiter, "acquire", new_callable=AsyncMock):
                result = await client._request("test.method", json_body={"data": "test"})

        assert result == {"ok": True}
        mock_httpx_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_handle_rate_limit_response(self, client, mock_httpx_client):
        """Test 429 rate limit response is handled."""
        mock_response = AsyncMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "30"}
        mock_httpx_client.get.return_value = mock_response

        with patch.object(client, "_get_http_client", return_value=mock_httpx_client):
            with patch.object(client._rate_limiter, "acquire", new_callable=AsyncMock):
                with patch.object(client._rate_limiter, "record_rate_limit") as mock_record:
                    with pytest.raises(SlackAPIError) as exc_info:
                        await client._request("test.method")

        assert exc_info.value.is_rate_limited is True
        mock_record.assert_called_once_with("test.method", 30)

    @pytest.mark.asyncio
    async def test_should_handle_api_error_response(self, client, mock_httpx_client):
        """Test API error response raises exception."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": False, "error": "channel_not_found"}
        mock_httpx_client.get.return_value = mock_response

        with patch.object(client, "_get_http_client", return_value=mock_httpx_client):
            with patch.object(client._rate_limiter, "acquire", new_callable=AsyncMock):
                with pytest.raises(SlackAPIError) as exc_info:
                    await client._request("conversations.info")

        assert exc_info.value.error == "channel_not_found"

    @pytest.mark.asyncio
    async def test_should_handle_request_error(self, client, mock_httpx_client):
        """Test network error is handled."""
        mock_httpx_client.get.side_effect = httpx.RequestError("Connection failed")

        with patch.object(client, "_get_http_client", return_value=mock_httpx_client):
            with patch.object(client._rate_limiter, "acquire", new_callable=AsyncMock):
                with pytest.raises(SlackAPIError) as exc_info:
                    await client._request("test.method")

        assert exc_info.value.error == "request_failed"

    @pytest.mark.asyncio
    async def test_should_close_http_client(self, client):
        """Test close method closes HTTP client."""
        mock_http = AsyncMock()
        client._http_client = mock_http

        await client.close()

        mock_http.aclose.assert_called_once()
        assert client._http_client is None


class TestSlackClientAuthMethods:
    """Tests for auth-related API methods."""

    @pytest.fixture
    def client(self, slack_workspace):
        """Create a client for testing."""
        return SlackClient(slack_workspace)

    @pytest.mark.asyncio
    async def test_should_call_auth_test(self, client):
        """Test auth.test method."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {
                "ok": True,
                "team_id": "T12345678",
                "user_id": "U11111111",
                "bot_id": "B22222222",
            }

            result = await client.auth_test()

        mock_request.assert_called_once_with("auth.test")
        assert result["team_id"] == "T12345678"

    @pytest.mark.asyncio
    async def test_should_call_team_info(self, client):
        """Test team.info method."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {
                "ok": True,
                "team": {
                    "id": "T12345678",
                    "name": "Test Team",
                    "domain": "test-team",
                },
            }

            result = await client.team_info()

        mock_request.assert_called_once_with("team.info")
        assert result["name"] == "Test Team"


class TestSlackClientConversationMethods:
    """Tests for conversation-related API methods."""

    @pytest.fixture
    def client(self, slack_workspace):
        """Create a client for testing."""
        return SlackClient(slack_workspace)

    @pytest.mark.asyncio
    async def test_should_list_channels(self, client, slack_api_response_channels):
        """Test conversations.list method."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = slack_api_response_channels

            result = await client.list_channels()

        mock_request.assert_called_once()
        assert len(result["channels"]) == 2

    @pytest.mark.asyncio
    async def test_should_get_all_channels_with_pagination(self, client):
        """Test get_all_channels handles pagination."""
        page1 = {
            "ok": True,
            "channels": [
                {"id": "C1", "name": "channel1", "is_private": False, "num_members": 10},
            ],
            "response_metadata": {"next_cursor": "page2"},
        }
        page2 = {
            "ok": True,
            "channels": [
                {"id": "C2", "name": "channel2", "is_private": False, "num_members": 5},
            ],
            "response_metadata": {"next_cursor": ""},
        }

        with patch.object(client, "list_channels", new_callable=AsyncMock) as mock_list:
            mock_list.side_effect = [page1, page2]

            result = await client.get_all_channels()

        assert len(result) == 2
        assert all(isinstance(ch, SlackChannel) for ch in result)

    @pytest.mark.asyncio
    async def test_should_include_private_channels_with_full_scope(self, slack_workspace_full_scopes):
        """Test private channels included with full scope tier."""
        client = SlackClient(slack_workspace_full_scopes)

        with patch.object(client, "list_channels", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = {
                "ok": True,
                "channels": [],
                "response_metadata": {"next_cursor": ""},
            }

            await client.get_all_channels(include_private=True)

        # Should request both public and private
        call_args = mock_list.call_args
        assert "private_channel" in call_args.kwargs.get("types", "")

    @pytest.mark.asyncio
    async def test_should_get_channel_history(self, client, slack_api_response_history):
        """Test conversations.history method."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = slack_api_response_history

            result = await client.get_channel_history("C12345678")

        mock_request.assert_called_once()
        assert len(result["messages"]) == 3

    @pytest.mark.asyncio
    async def test_should_get_thread_replies(self, client, slack_api_response_replies):
        """Test conversations.replies method."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = slack_api_response_replies

            result = await client.get_thread_replies("C12345678", "1705313000.000001")

        mock_request.assert_called_once()
        assert len(result["messages"]) == 3

    @pytest.mark.asyncio
    async def test_should_get_channel_info(self, client):
        """Test conversations.info method."""
        channel_response = {
            "ok": True,
            "channel": {
                "id": "C12345678",
                "name": "general",
                "is_private": False,
                "is_archived": False,
                "topic": {"value": "General discussion"},
                "purpose": {"value": "General chat"},
                "num_members": 50,
            },
        }

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = channel_response

            result = await client.get_channel_info("C12345678")

        assert isinstance(result, SlackChannel)
        assert result.channel_id == "C12345678"
        assert result.channel_name == "general"


class TestSlackClientUserMethods:
    """Tests for user-related API methods."""

    @pytest.fixture
    def client(self, slack_workspace):
        """Create a client for testing."""
        return SlackClient(slack_workspace)

    @pytest.mark.asyncio
    async def test_should_list_users(self, client, slack_api_response_users):
        """Test users.list method."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = slack_api_response_users

            result = await client.list_users()

        mock_request.assert_called_once()
        assert len(result["members"]) == 2

    @pytest.mark.asyncio
    async def test_should_get_all_users_with_pagination(self, client):
        """Test get_all_users handles pagination."""
        page1 = {
            "ok": True,
            "members": [
                {
                    "id": "U1",
                    "deleted": False,
                    "is_bot": False,
                    "profile": {"display_name": "user1", "real_name": "User One"},
                },
            ],
            "response_metadata": {"next_cursor": "page2"},
        }
        page2 = {
            "ok": True,
            "members": [
                {
                    "id": "U2",
                    "deleted": False,
                    "is_bot": False,
                    "profile": {"display_name": "user2", "real_name": "User Two"},
                },
            ],
            "response_metadata": {"next_cursor": ""},
        }

        with patch.object(client, "list_users", new_callable=AsyncMock) as mock_list:
            mock_list.side_effect = [page1, page2]

            result = await client.get_all_users()

        assert len(result) == 2
        assert all(isinstance(u, SlackUser) for u in result)

    @pytest.mark.asyncio
    async def test_should_skip_deleted_users(self, client):
        """Test deleted users are skipped."""
        response = {
            "ok": True,
            "members": [
                {"id": "U1", "deleted": False, "is_bot": False, "profile": {"display_name": "active"}},
                {"id": "U2", "deleted": True, "is_bot": False, "profile": {"display_name": "deleted"}},
            ],
            "response_metadata": {"next_cursor": ""},
        }

        with patch.object(client, "list_users", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = response

            result = await client.get_all_users()

        assert len(result) == 1
        assert result[0].user_id == "U1"

    @pytest.mark.asyncio
    async def test_should_get_user_info(self, client):
        """Test users.info method."""
        user_response = {
            "ok": True,
            "user": {
                "id": "U11111111",
                "deleted": False,
                "is_bot": False,
                "is_admin": True,
                "is_owner": False,
                "tz": "America/New_York",
                "profile": {
                    "display_name": "johndoe",
                    "real_name": "John Doe",
                    "email": "john@example.com",
                    "image_72": "https://example.com/avatar.png",
                },
            },
        }

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = user_response

            result = await client.get_user_info("U11111111")

        assert isinstance(result, SlackUser)
        assert result.user_id == "U11111111"
        assert result.display_name == "johndoe"
        assert result.is_admin is True


class TestSlackClientHelperMethods:
    """Tests for helper methods."""

    @pytest.fixture
    def client(self, slack_workspace):
        """Create a client for testing."""
        return SlackClient(slack_workspace)

    def test_should_map_public_channel_type(self, client):
        """Test public channel type mapping."""
        data = {"is_private": False, "is_im": False, "is_mpim": False}
        result = client._map_channel_type(data)

        assert result == SlackChannelType.PUBLIC

    def test_should_map_private_channel_type(self, client):
        """Test private channel type mapping."""
        data = {"is_private": True, "is_im": False, "is_mpim": False}
        result = client._map_channel_type(data)

        assert result == SlackChannelType.PRIVATE

    def test_should_map_dm_channel_type(self, client):
        """Test DM channel type mapping."""
        data = {"is_im": True}
        result = client._map_channel_type(data)

        assert result == SlackChannelType.DM

    def test_should_map_mpim_channel_type(self, client):
        """Test MPIM channel type mapping."""
        data = {"is_mpim": True}
        result = client._map_channel_type(data)

        assert result == SlackChannelType.MPIM

    def test_should_parse_message(self, client):
        """Test message parsing from API response."""
        msg_data = {
            "ts": "1705312800.000001",
            "user": "U11111111",
            "text": "Hello world",
            "thread_ts": "1705312800.000001",
            "reply_count": 3,
            "reply_users_count": 2,
            "reactions": [{"name": "thumbsup", "users": ["U2", "U3"]}],
            "attachments": [],
            "files": [{"id": "F1", "name": "file.pdf"}],
            "edited": {"ts": "1705312900.000001"},
            "subtype": None,
        }

        result = client.parse_message(msg_data, "C12345678")

        assert isinstance(result, SlackMessage)
        assert result.ts == "1705312800.000001"
        assert result.user_id == "U11111111"
        assert result.text == "Hello world"
        assert result.reply_count == 3
        assert result.is_edited is True
        assert len(result.files) == 1

    def test_should_parse_bot_message(self, client):
        """Test parsing message from bot."""
        msg_data = {
            "ts": "1705312800.000001",
            "bot_id": "B11111111",
            "text": "Bot message",
            "subtype": "bot_message",
        }

        result = client.parse_message(msg_data, "C12345678")

        assert result.user_id == "B11111111"
        assert result.subtype == "bot_message"

    def test_should_handle_missing_message_fields(self, client):
        """Test parsing message with missing optional fields."""
        msg_data = {
            "ts": "1705312800.000001",
        }

        result = client.parse_message(msg_data, "C12345678")

        assert result.ts == "1705312800.000001"
        assert result.user_id == ""
        assert result.text == ""
        assert result.reactions == []
        assert result.files == []
