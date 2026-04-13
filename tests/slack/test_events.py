"""
Tests for src/slack/events.py - Slack Events API handler.

Tests event handler registration, URL verification,
event callback processing, and deduplication integration.
"""

import pytest
import json
import time
import hmac
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.slack.events import (
    router,
    register_event_handler,
    _event_handlers,
    _default_message_handler,
    _handle_app_uninstalled,
    _handle_tokens_revoked,
    _process_event_callback,
)
from src.slack.signature import SlackSignatureError


class TestRegisterEventHandler:
    """Tests for event handler registration."""

    def test_should_register_handler_for_event_type(self):
        """Test handler is registered for event type."""
        handler = AsyncMock()
        event_type = "test_event_type"

        register_event_handler(event_type, handler)

        assert event_type in _event_handlers
        assert _event_handlers[event_type] is handler

    def test_should_overwrite_existing_handler(self):
        """Test new handler overwrites existing one."""
        handler1 = AsyncMock()
        handler2 = AsyncMock()
        event_type = "overwrite_test"

        register_event_handler(event_type, handler1)
        register_event_handler(event_type, handler2)

        assert _event_handlers[event_type] is handler2


class TestDefaultEventHandlers:
    """Tests for default event handlers."""

    @pytest.mark.asyncio
    async def test_should_log_message_event(self, caplog):
        """Test message handler logs event details."""
        import logging
        caplog.set_level(logging.INFO)

        event = {
            "type": "message",
            "channel": "C12345678",
            "user": "U11111111",
            "text": "Hello world",
            "ts": "1705312800.000001",
        }

        await _default_message_handler("T12345678", event)

        assert "Slack message received" in caplog.text
        assert "T12345678" in caplog.text

    @pytest.mark.asyncio
    async def test_should_skip_bot_messages(self, caplog):
        """Test bot messages are skipped."""
        import logging
        caplog.set_level(logging.INFO)

        event = {
            "type": "message",
            "subtype": "bot_message",
            "channel": "C12345678",
            "text": "Bot says hello",
            "ts": "1705312800.000001",
        }

        await _default_message_handler("T12345678", event)

        # Should not log the message
        assert "Slack message received" not in caplog.text

    @pytest.mark.asyncio
    async def test_should_skip_message_changed_events(self, caplog):
        """Test message_changed events are skipped."""
        import logging
        caplog.set_level(logging.INFO)

        event = {
            "type": "message",
            "subtype": "message_changed",
            "channel": "C12345678",
            "ts": "1705312800.000001",
        }

        await _default_message_handler("T12345678", event)

        assert "Slack message received" not in caplog.text

    @pytest.mark.asyncio
    async def test_should_handle_app_uninstalled_event(self, caplog):
        """Test app_uninstalled handler logs warning."""
        import logging
        caplog.set_level(logging.WARNING)

        with patch(
            "src.data.repositories.get_slack_repository",
            new_callable=AsyncMock
        ) as mock_repo_getter:
            mock_repo = AsyncMock()
            mock_repo.get_workspace.return_value = None
            mock_repo_getter.return_value = mock_repo

            await _handle_app_uninstalled("T12345678", {})

        assert "uninstalled" in caplog.text

    @pytest.mark.asyncio
    async def test_should_handle_tokens_revoked_with_bot_tokens(self, caplog):
        """Test tokens_revoked handler processes bot tokens."""
        import logging
        caplog.set_level(logging.WARNING)

        event = {
            "tokens": {
                "bot": ["U87654321"],
                "oauth": [],
            }
        }

        with patch("src.slack.events._handle_app_uninstalled", new_callable=AsyncMock) as mock_uninstall:
            await _handle_tokens_revoked("T12345678", event)

            mock_uninstall.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_ignore_tokens_revoked_without_bot(self):
        """Test tokens_revoked ignores non-bot token revocations."""
        event = {
            "tokens": {
                "bot": [],
                "oauth": ["some_oauth_token"],
            }
        }

        with patch("src.slack.events._handle_app_uninstalled", new_callable=AsyncMock) as mock_uninstall:
            await _handle_tokens_revoked("T12345678", event)

            mock_uninstall.assert_not_called()


class TestProcessEventCallback:
    """Tests for event callback processing."""

    @pytest.mark.asyncio
    async def test_should_process_valid_event_callback(self):
        """Test valid event callback is processed."""
        payload = {
            "type": "event_callback",
            "event_id": "Ev12345678",
            "team_id": "T12345678",
            "event": {
                "type": "message",
                "channel": "C12345678",
                "user": "U11111111",
                "text": "Test message",
                "ts": "1705312800.000001",
            },
        }

        with patch("src.slack.events.get_deduplicator") as mock_dedup:
            mock_dedup_instance = AsyncMock()
            mock_dedup_instance.should_process.return_value = True
            mock_dedup.return_value = mock_dedup_instance

            result = await _process_event_callback(payload)

            assert result == {"ok": True}
            mock_dedup_instance.mark_processed.assert_called_once_with("Ev12345678")

    @pytest.mark.asyncio
    async def test_should_skip_duplicate_events(self):
        """Test duplicate events are skipped."""
        payload = {
            "type": "event_callback",
            "event_id": "Ev_duplicate",
            "team_id": "T12345678",
            "event": {"type": "message"},
        }

        with patch("src.slack.events.get_deduplicator") as mock_dedup:
            mock_dedup_instance = AsyncMock()
            mock_dedup_instance.should_process.return_value = False
            mock_dedup.return_value = mock_dedup_instance

            result = await _process_event_callback(payload)

            assert result == {"ok": True}
            mock_dedup_instance.mark_processed.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_handle_missing_event_id(self):
        """Test handles payload without event_id."""
        payload = {
            "type": "event_callback",
            "team_id": "T12345678",
            "event": {"type": "message"},
        }

        result = await _process_event_callback(payload)

        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_should_handle_missing_team_id(self):
        """Test handles payload without team_id."""
        payload = {
            "type": "event_callback",
            "event_id": "Ev12345678",
            "event": {"type": "message"},
        }

        result = await _process_event_callback(payload)

        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_should_mark_failed_on_handler_error(self):
        """Test marks event as failed when handler raises."""
        payload = {
            "type": "event_callback",
            "event_id": "Ev_error_test",
            "team_id": "T12345678",
            "event": {"type": "message"},
        }

        with patch("src.slack.events.get_deduplicator") as mock_dedup:
            mock_dedup_instance = AsyncMock()
            mock_dedup_instance.should_process.return_value = True
            mock_dedup.return_value = mock_dedup_instance

            # Register a handler that raises
            error_handler = AsyncMock(side_effect=Exception("Handler failed"))
            _event_handlers["message"] = error_handler

            result = await _process_event_callback(payload)

            assert result == {"ok": True}
            mock_dedup_instance.mark_failed.assert_called_once_with("Ev_error_test")

    @pytest.mark.asyncio
    async def test_should_handle_unknown_event_type(self, caplog):
        """Test handles unknown event types gracefully."""
        import logging
        caplog.set_level(logging.DEBUG)

        payload = {
            "type": "event_callback",
            "event_id": "Ev12345678",
            "team_id": "T12345678",
            "event": {"type": "unknown_event_type"},
        }

        with patch("src.slack.events.get_deduplicator") as mock_dedup:
            mock_dedup_instance = AsyncMock()
            mock_dedup_instance.should_process.return_value = True
            mock_dedup.return_value = mock_dedup_instance

            result = await _process_event_callback(payload)

            assert result == {"ok": True}
            assert "No handler for event type" in caplog.text


class TestSlackEventEndpoint:
    """Tests for the Slack events endpoint."""

    def _compute_signature(self, body: bytes, timestamp: str, secret: str) -> str:
        """Helper to compute valid Slack signature."""
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        signature = hmac.new(
            secret.encode("utf-8"),
            sig_basestring.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"v0={signature}"

    @pytest.fixture
    def app(self):
        """Create FastAPI app with router."""
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    def test_should_handle_url_verification(self, client, slack_signing_secret):
        """Test URL verification challenge is returned."""
        payload = {
            "type": "url_verification",
            "challenge": "test_challenge_12345",
        }
        body = json.dumps(payload).encode()
        timestamp = str(int(time.time()))
        signature = self._compute_signature(body, timestamp, slack_signing_secret)

        with patch("src.slack.events.get_slack_auth") as mock_auth:
            mock_auth_instance = MagicMock()
            mock_auth_instance.signing_secret = slack_signing_secret
            mock_auth.return_value = mock_auth_instance

            response = client.post(
                "/slack/events",
                content=body,
                headers={
                    "X-Slack-Request-Timestamp": timestamp,
                    "X-Slack-Signature": signature,
                    "Content-Type": "application/json",
                },
            )

        assert response.status_code == 200
        assert response.text == "test_challenge_12345"

    def test_should_reject_invalid_signature(self, client, slack_signing_secret):
        """Test invalid signature is rejected."""
        payload = {"type": "event_callback"}
        body = json.dumps(payload).encode()
        timestamp = str(int(time.time()))
        invalid_signature = "v0=invalid_signature_0000000000000000000000000000000000000000"

        with patch("src.slack.events.get_slack_auth") as mock_auth:
            mock_auth_instance = MagicMock()
            mock_auth_instance.signing_secret = slack_signing_secret
            mock_auth.return_value = mock_auth_instance

            response = client.post(
                "/slack/events",
                content=body,
                headers={
                    "X-Slack-Request-Timestamp": timestamp,
                    "X-Slack-Signature": invalid_signature,
                    "Content-Type": "application/json",
                },
            )

        assert response.status_code == 401

    def test_should_reject_when_signing_secret_not_configured(self, client):
        """Test request is rejected when signing secret not configured."""
        payload = {"type": "event_callback"}

        with patch("src.slack.events.get_slack_auth") as mock_auth:
            mock_auth.return_value = None

            response = client.post(
                "/slack/events",
                json=payload,
            )

        assert response.status_code == 503

    def test_should_reject_invalid_json(self, client, slack_signing_secret):
        """Test invalid JSON is rejected."""
        body = b"invalid json {"
        timestamp = str(int(time.time()))
        signature = self._compute_signature(body, timestamp, slack_signing_secret)

        with patch("src.slack.events.get_slack_auth") as mock_auth:
            mock_auth_instance = MagicMock()
            mock_auth_instance.signing_secret = slack_signing_secret
            mock_auth.return_value = mock_auth_instance

            response = client.post(
                "/slack/events",
                content=body,
                headers={
                    "X-Slack-Request-Timestamp": timestamp,
                    "X-Slack-Signature": signature,
                    "Content-Type": "application/json",
                },
            )

        assert response.status_code == 400


class TestEventsStatusEndpoint:
    """Tests for the events status endpoint."""

    @pytest.fixture
    def app(self):
        """Create FastAPI app with router."""
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    def test_should_return_status(self, client):
        """Test status endpoint returns configuration info."""
        with patch("src.slack.events.get_slack_auth") as mock_auth:
            mock_auth_instance = MagicMock()
            mock_auth_instance.signing_secret = "test_secret"
            mock_auth.return_value = mock_auth_instance

            with patch("src.slack.events.get_deduplicator") as mock_dedup:
                mock_dedup_instance = AsyncMock()
                mock_dedup_instance.get_stats = AsyncMock(return_value={
                    "total_entries": 10,
                    "processed": 8,
                    "pending": 2,
                })
                mock_dedup.return_value = mock_dedup_instance

                response = client.get("/slack/events/status")

        assert response.status_code == 200
        data = response.json()
        assert data["configured"] is True
        assert "handlers_registered" in data
        assert "deduplication_stats" in data

    def test_should_show_unconfigured_status(self, client):
        """Test status shows unconfigured when no auth."""
        with patch("src.slack.events.get_slack_auth") as mock_auth:
            mock_auth.return_value = None

            with patch("src.slack.events.get_deduplicator") as mock_dedup:
                mock_dedup_instance = AsyncMock()
                mock_dedup_instance.get_stats = AsyncMock(return_value={})
                mock_dedup.return_value = mock_dedup_instance

                response = client.get("/slack/events/status")

        assert response.status_code == 200
        data = response.json()
        assert data["configured"] is False
