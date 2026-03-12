"""
Unit tests for dashboard/middleware.py.

Tests error logging and request context middleware.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import logging

from src.dashboard.middleware import (
    ErrorLoggingMiddleware,
    RequestContextMiddleware,
    setup_error_logging_middleware,
)


class TestErrorLoggingMiddleware:
    """Tests for ErrorLoggingMiddleware."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        app = MagicMock()
        return ErrorLoggingMiddleware(app)

    @pytest.fixture
    def mock_request(self):
        """Create mock request."""
        request = MagicMock()
        request.method = "GET"
        request.url.path = "/api/v1/test"
        request.state = MagicMock()
        return request

    @pytest.mark.asyncio
    async def test_success_response_no_log(self, middleware, mock_request):
        """Successful responses don't log at WARNING/ERROR."""
        response = MagicMock()
        response.status_code = 200

        call_next = AsyncMock(return_value=response)

        with patch('src.dashboard.middleware.logger') as mock_logger:
            mock_logger.isEnabledFor.return_value = False
            result = await middleware.dispatch(mock_request, call_next)

            assert result.status_code == 200
            mock_logger.error.assert_not_called()
            mock_logger.warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_response_debug_log(self, middleware, mock_request):
        """Successful responses log at DEBUG when enabled."""
        response = MagicMock()
        response.status_code = 200

        call_next = AsyncMock(return_value=response)

        with patch('src.dashboard.middleware.logger') as mock_logger:
            mock_logger.isEnabledFor.return_value = True
            result = await middleware.dispatch(mock_request, call_next)

            assert result.status_code == 200
            mock_logger.debug.assert_called_once()

    @pytest.mark.asyncio
    async def test_client_error_warning_log(self, middleware, mock_request):
        """4xx responses log at WARNING."""
        response = MagicMock()
        response.status_code = 404

        call_next = AsyncMock(return_value=response)

        with patch('src.dashboard.middleware.logger') as mock_logger:
            result = await middleware.dispatch(mock_request, call_next)

            assert result.status_code == 404
            mock_logger.warning.assert_called_once()
            assert "404" in mock_logger.warning.call_args[0][0]

    @pytest.mark.asyncio
    async def test_server_error_error_log(self, middleware, mock_request):
        """5xx responses log at ERROR."""
        response = MagicMock()
        response.status_code = 500

        call_next = AsyncMock(return_value=response)

        with patch('src.dashboard.middleware.logger') as mock_logger:
            result = await middleware.dispatch(mock_request, call_next)

            assert result.status_code == 500
            mock_logger.error.assert_called_once()
            assert "500" in mock_logger.error.call_args[0][0]

    @pytest.mark.asyncio
    async def test_unhandled_exception_logged(self, middleware, mock_request):
        """Unhandled exceptions log with traceback."""
        call_next = AsyncMock(side_effect=ValueError("Test error"))

        with patch('src.dashboard.middleware.logger') as mock_logger:
            with pytest.raises(ValueError):
                await middleware.dispatch(mock_request, call_next)

            mock_logger.exception.assert_called_once()
            assert "ValueError" in mock_logger.exception.call_args[0][0]

    @pytest.mark.asyncio
    async def test_request_id_generated(self, middleware, mock_request):
        """Request ID is generated and stored on request state."""
        response = MagicMock()
        response.status_code = 200

        call_next = AsyncMock(return_value=response)

        await middleware.dispatch(mock_request, call_next)

        assert hasattr(mock_request.state, 'request_id')
        assert len(mock_request.state.request_id) == 8

    @pytest.mark.asyncio
    async def test_duration_included_in_log(self, middleware, mock_request):
        """Response duration is included in log messages."""
        response = MagicMock()
        response.status_code = 404

        call_next = AsyncMock(return_value=response)

        with patch('src.dashboard.middleware.logger') as mock_logger:
            await middleware.dispatch(mock_request, call_next)

            log_message = mock_logger.warning.call_args[0][0]
            assert "ms" in log_message


class TestRequestContextMiddleware:
    """Tests for RequestContextMiddleware."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        app = MagicMock()
        return RequestContextMiddleware(app)

    @pytest.fixture
    def mock_request(self):
        """Create mock request."""
        request = MagicMock()
        request.state = MagicMock()
        return request

    @pytest.mark.asyncio
    async def test_extracts_guild_id_from_path(self, middleware, mock_request):
        """Guild ID extracted from /guilds/{id} path."""
        mock_request.url.path = "/api/v1/guilds/123456789/settings"

        response = MagicMock()
        call_next = AsyncMock(return_value=response)

        await middleware.dispatch(mock_request, call_next)

        assert mock_request.state.guild_id == "123456789"

    @pytest.mark.asyncio
    async def test_no_guild_id_when_not_in_path(self, middleware, mock_request):
        """Guild ID is None when not in path."""
        mock_request.url.path = "/api/v1/health"

        response = MagicMock()
        call_next = AsyncMock(return_value=response)

        await middleware.dispatch(mock_request, call_next)

        assert mock_request.state.guild_id is None

    @pytest.mark.asyncio
    async def test_guild_id_at_end_of_path(self, middleware, mock_request):
        """Guild ID extracted when at end of path."""
        mock_request.url.path = "/api/v1/guilds/987654321"

        response = MagicMock()
        call_next = AsyncMock(return_value=response)

        await middleware.dispatch(mock_request, call_next)

        assert mock_request.state.guild_id == "987654321"

    @pytest.mark.asyncio
    async def test_calls_next_middleware(self, middleware, mock_request):
        """Middleware calls the next handler."""
        mock_request.url.path = "/api/v1/test"

        response = MagicMock()
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(mock_request, call_next)

        call_next.assert_called_once_with(mock_request)
        assert result == response


class TestSetupMiddleware:
    """Tests for middleware setup function."""

    def test_adds_middleware_to_app(self):
        """setup_error_logging_middleware adds both middleware."""
        app = MagicMock()

        with patch('src.dashboard.middleware.logger'):
            setup_error_logging_middleware(app)

        assert app.add_middleware.call_count == 2
        # Verify both middleware types were added
        middleware_types = [call[0][0] for call in app.add_middleware.call_args_list]
        assert ErrorLoggingMiddleware in middleware_types
        assert RequestContextMiddleware in middleware_types

    def test_logs_setup_info(self):
        """Setup logs info message."""
        app = MagicMock()

        with patch('src.dashboard.middleware.logger') as mock_logger:
            setup_error_logging_middleware(app)

            mock_logger.info.assert_called_once()
            assert "ADR-031" in mock_logger.info.call_args[0][0]
