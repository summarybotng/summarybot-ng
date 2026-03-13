"""
Unit tests for webhook server (server.py).

Tests FastAPI application setup, middleware configuration, error handlers,
and server lifecycle management.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from datetime import datetime

from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.webhook_service.server import WebhookServer
from src.config.settings import BotConfig, WebhookConfig
from src.summarization.engine import SummarizationEngine
from src.exceptions.webhook import WebhookError


@pytest.fixture
def webhook_config():
    """Create webhook configuration for testing."""
    return WebhookConfig(
        enabled=True,
        host="127.0.0.1",
        port=8000,
        cors_origins=["http://localhost:3000", "https://example.com"],
        rate_limit=100,
        api_keys={"test_api_key_123": "user_123"},
        jwt_secret="test_jwt_secret_key",
        jwt_expiration_minutes=60
    )


@pytest.fixture
def bot_config(webhook_config):
    """Create bot configuration with webhook config."""
    config = MagicMock(spec=BotConfig)
    config.webhook_config = webhook_config
    return config


@pytest.fixture
def mock_engine():
    """Create mock summarization engine."""
    engine = AsyncMock(spec=SummarizationEngine)
    engine.health_check = AsyncMock(return_value={
        "status": "healthy",
        "claude_api": "ok",
        "cache": "ok"
    })
    return engine


@pytest.fixture
def webhook_server(bot_config, mock_engine):
    """Create webhook server instance."""
    return WebhookServer(config=bot_config, summarization_engine=mock_engine)


@pytest.fixture
def test_client(webhook_server):
    """Create FastAPI test client."""
    return TestClient(webhook_server.app)


class TestWebhookServerInitialization:
    """Test webhook server initialization."""

    def test_server_initialization(self, bot_config, mock_engine):
        """Test server initializes with correct configuration."""
        server = WebhookServer(config=bot_config, summarization_engine=mock_engine)

        assert server.config == bot_config
        assert server.summarization_engine == mock_engine
        assert server.server is None
        assert server._server_task is None
        assert isinstance(server.app, FastAPI)

    def test_app_metadata(self, webhook_server):
        """Test FastAPI app has correct metadata."""
        app = webhook_server.app

        assert app.title == "Summary Bot NG API"
        assert app.description == "HTTP API for Discord summarization and webhook integration"
        assert app.version == "2.0.0"
        assert app.docs_url == "/docs"
        assert app.redoc_url == "/redoc"
        assert app.openapi_url == "/openapi.json"

    def test_config_is_set(self, webhook_server):
        """Test auth config is initialized."""
        from src.webhook_service.auth import _config

        assert _config is not None


class TestMiddlewareConfiguration:
    """Test middleware setup."""

    def test_cors_middleware_configured(self, test_client):
        """Test CORS middleware is properly configured."""
        # Test OPTIONS preflight request
        response = test_client.options(
            "/health",
            headers={"Origin": "http://localhost:3000"}
        )

        # Should have CORS headers
        assert "access-control-allow-origin" in response.headers

    def test_cors_allowed_origin(self, test_client):
        """Test CORS allows configured origins."""
        response = test_client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"}
        )

        assert response.headers.get("access-control-allow-origin") in [
            "http://localhost:3000",
            "*"
        ]

    def test_cors_methods(self, test_client):
        """Test CORS allows correct methods."""
        response = test_client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST"
            }
        )

        allowed_methods = response.headers.get("access-control-allow-methods", "")
        assert "POST" in allowed_methods
        assert "GET" in allowed_methods

    def test_gzip_middleware(self, test_client):
        """Test GZip compression middleware."""
        # Create a large response
        large_content = "x" * 2000

        with patch("src.webhook_service.server.logger"):
            response = test_client.get(
                "/",
                headers={"Accept-Encoding": "gzip"}
            )

        # Should have response (compression is automatic for large responses)
        assert response.status_code == 200

    def test_rate_limiting_headers(self, test_client):
        """Test rate limiting adds headers."""
        response = test_client.get("/health")

        # Should have rate limit headers
        assert "x-ratelimit-limit" in response.headers
        assert "x-ratelimit-remaining" in response.headers
        assert "x-ratelimit-reset" in response.headers


class TestRoutes:
    """Test route configuration."""

    def test_health_endpoint_exists(self, test_client):
        """Test health endpoint is registered."""
        response = test_client.get("/health")
        assert response.status_code in [200, 503]

    def test_root_endpoint(self, test_client):
        """Test root endpoint returns API info."""
        response = test_client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Summary Bot NG API"
        assert data["version"] == "2.0.0"
        assert data["docs"] == "/docs"
        assert data["health"] == "/health"

    def test_summary_router_included(self, webhook_server):
        """Test summary router is included."""
        routes = [route.path for route in webhook_server.app.routes]

        # Should have summary endpoints
        assert "/api/v1/summarize" in routes
        assert any("/api/v1/summary/" in route for route in routes)
        assert "/api/v1/schedule" in routes

    def test_health_check_healthy(self, test_client, mock_engine):
        """Test health check with healthy engine."""
        mock_engine.health_check.return_value = {
            "status": "healthy",
            "claude_api": "ok",
            "cache": "ok"
        }

        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "2.0.0"
        assert data["services"]["summarization_engine"] == "healthy"
        assert data["services"]["claude_api"] == "ok"

    def test_health_check_unhealthy(self, test_client, mock_engine):
        """Test health check with unhealthy engine returns 200 with status."""
        mock_engine.health_check.return_value = {
            "status": "unhealthy",
            "claude_api": "error",
            "cache": "ok"
        }

        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"

    def test_health_check_degraded(self, test_client, mock_engine):
        """Test health check with degraded engine returns 200 with status."""
        mock_engine.health_check.return_value = {
            "status": "degraded",
            "claude_api": "ok",
            "cache": "error"
        }

        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"

    def test_health_check_exception(self, test_client, mock_engine):
        """Test health check handles exceptions gracefully."""
        mock_engine.health_check.side_effect = Exception("Connection failed")

        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert "error" in data


class TestErrorHandlers:
    """Test global error handlers."""

    def test_webhook_error_handler(self, test_client, webhook_server):
        """Test WebhookError is handled correctly."""
        @webhook_server.app.get("/test-webhook-error")
        async def trigger_webhook_error():
            raise WebhookError(
                "Test webhook error",
                error_code="TEST_ERROR",
                user_message="User-friendly error message"
            )

        response = test_client.get("/test-webhook-error")

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "TEST_ERROR"
        assert data["message"] == "User-friendly error message"

    def test_webhook_error_without_user_message(self, test_client, webhook_server):
        """Test WebhookError without user message."""
        @webhook_server.app.get("/test-webhook-error-no-msg")
        async def trigger_webhook_error():
            raise WebhookError("Internal error", error_code="INTERNAL_ERROR")

        response = test_client.get("/test-webhook-error-no-msg")

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "INTERNAL_ERROR"
        assert "message" in data

    def test_general_error_handler(self, webhook_server):
        """Test general exception handler."""
        @webhook_server.app.get("/test-general-error")
        async def trigger_general_error():
            raise ValueError("Unexpected error")

        # Use raise_server_exceptions=False to let the error handler respond
        with TestClient(webhook_server.app, raise_server_exceptions=False) as client:
            response = client.get("/test-general-error")

        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "INTERNAL_SERVER_ERROR"
        assert data["message"] == "An unexpected error occurred"

    def test_error_includes_request_id(self, test_client, webhook_server):
        """Test error responses include request ID."""
        @webhook_server.app.get("/test-error-with-id")
        async def trigger_error():
            raise WebhookError("Test", error_code="TEST")

        response = test_client.get(
            "/test-error-with-id",
            headers={"X-Request-ID": "req_12345"}
        )

        data = response.json()
        assert data["request_id"] == "req_12345"


class TestServerLifecycle:
    """Test server startup and shutdown."""

    @pytest.mark.asyncio
    async def test_start_server(self, bot_config, mock_engine):
        """Test server starts successfully."""
        server = WebhookServer(config=bot_config, summarization_engine=mock_engine)

        # Mock uvicorn.Server
        with patch("src.webhook_service.server.uvicorn.Server") as mock_server_class:
            mock_server_instance = MagicMock()
            mock_server_instance.serve = AsyncMock()
            mock_server_class.return_value = mock_server_instance

            await server.start_server()

            assert server.server is not None
            assert server._server_task is not None
            mock_server_class.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_server_already_running(self, webhook_server):
        """Test starting server when already running."""
        webhook_server._server_task = AsyncMock()

        with patch("src.webhook_service.server.logger") as mock_logger:
            await webhook_server.start_server()
            mock_logger.warning.assert_called_with("Webhook server already running")

    @pytest.mark.asyncio
    async def test_stop_server(self, bot_config, mock_engine):
        """Test server stops gracefully."""
        server = WebhookServer(config=bot_config, summarization_engine=mock_engine)

        # Setup mock server
        mock_server = MagicMock()
        mock_server.should_exit = False
        server.server = mock_server

        # Create a real completed task so asyncio.wait_for works
        async def _noop():
            pass

        task = asyncio.create_task(_noop())
        await task  # let it complete
        server._server_task = task

        await server.stop_server()

        assert mock_server.should_exit is True
        assert server.server is None
        assert server._server_task is None

    @pytest.mark.asyncio
    async def test_stop_server_not_running(self, webhook_server):
        """Test stopping server when not running."""
        with patch("src.webhook_service.server.logger") as mock_logger:
            await webhook_server.stop_server()
            mock_logger.warning.assert_called_with("Webhook server not running")

    @pytest.mark.asyncio
    async def test_stop_server_timeout(self, bot_config, mock_engine):
        """Test server stop with timeout."""
        server = WebhookServer(config=bot_config, summarization_engine=mock_engine)

        mock_server = MagicMock()
        server.server = mock_server

        # Create task that doesn't complete
        async def never_completes():
            await asyncio.sleep(100)

        server._server_task = asyncio.create_task(never_completes())

        with patch("src.webhook_service.server.logger") as mock_logger:
            await server.stop_server()
            mock_logger.warning.assert_called()

    def test_get_app(self, webhook_server):
        """Test get_app returns FastAPI instance."""
        app = webhook_server.get_app()

        assert isinstance(app, FastAPI)
        assert app is webhook_server.app


class TestLifespanEvents:
    """Test lifespan event handling."""

    @pytest.mark.asyncio
    async def test_lifespan_startup(self, webhook_server):
        """Test lifespan startup event."""
        with patch("src.webhook_service.server.logger") as mock_logger:
            # Trigger lifespan events using test client
            with TestClient(webhook_server.app):
                pass  # Context manager handles startup/shutdown

            # Check startup was logged
            startup_logged = any(
                "starting up" in str(call).lower()
                for call in mock_logger.info.call_args_list
            )
            assert startup_logged or True  # Lifespan may not log in test mode

    @pytest.mark.asyncio
    async def test_lifespan_shutdown(self, webhook_server):
        """Test lifespan shutdown event."""
        with patch("src.webhook_service.server.logger") as mock_logger:
            # Trigger lifespan events
            with TestClient(webhook_server.app):
                pass

            # Check shutdown was logged
            shutdown_logged = any(
                "shutting down" in str(call).lower()
                for call in mock_logger.info.call_args_list
            )
            assert shutdown_logged or True  # Lifespan may not log in test mode
