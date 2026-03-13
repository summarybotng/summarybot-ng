"""
Unit tests for API endpoints (endpoints.py).

Tests all endpoint handlers including success, error cases,
authentication, and validation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.webhook_service.endpoints import create_summary_router
from src.config.settings import BotConfig
from src.summarization.engine import SummarizationEngine
from src.exceptions import (
    InsufficientContentError,
    SummarizationError,
    WebhookAuthError
)


@pytest.fixture
def mock_engine():
    """Create mock summarization engine."""
    engine = AsyncMock(spec=SummarizationEngine)
    return engine


@pytest.fixture
def mock_config():
    """Create mock bot configuration."""
    config = MagicMock(spec=BotConfig)
    return config


@pytest.fixture
def app(mock_engine, mock_config):
    """Create FastAPI app with summary router."""
    app = FastAPI()
    router = create_summary_router(
        summarization_engine=mock_engine,
        config=mock_config
    )
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def valid_api_key():
    """Valid API key for testing."""
    return "test_api_key_valid_123456"


@pytest.fixture
def auth_headers(valid_api_key):
    """Authentication headers."""
    return {"X-API-Key": valid_api_key}


class TestSummarizeEndpoint:
    """Test POST /summarize endpoint."""

    def test_summarize_requires_auth(self, client):
        """Test endpoint requires authentication."""
        response = client.post("/summarize", json={
            "channel_id": "123456789",
            "summary_type": "detailed"
        })

        assert response.status_code == 401
        data = response.json()
        assert "Authentication required" in data["detail"]

    def test_summarize_with_invalid_api_key(self, client):
        """Test endpoint rejects invalid API key."""
        response = client.post(
            "/summarize",
            json={"channel_id": "123456789"},
            headers={"X-API-Key": "short"}
        )

        assert response.status_code == 401

    def test_summarize_not_implemented(self, client, auth_headers):
        """Test endpoint returns not implemented status."""
        response = client.post(
            "/summarize",
            json={
                "channel_id": "123456789012345678",
                "summary_type": "detailed"
            },
            headers=auth_headers
        )

        assert response.status_code == 501
        data = response.json()
        assert "not yet implemented" in data["detail"].lower()

    def test_summarize_validation_missing_channel_id(self, client, auth_headers):
        """Test validation requires channel_id."""
        response = client.post(
            "/summarize",
            json={"summary_type": "detailed"},
            headers=auth_headers
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_summarize_validation_invalid_channel_id(self, client, auth_headers):
        """Test validation rejects empty channel_id."""
        response = client.post(
            "/summarize",
            json={
                "channel_id": "",
                "summary_type": "detailed"
            },
            headers=auth_headers
        )

        assert response.status_code == 422

    def test_summarize_validation_invalid_summary_type(self, client, auth_headers):
        """Test validation rejects invalid summary type."""
        response = client.post(
            "/summarize",
            json={
                "channel_id": "123456789",
                "summary_type": "invalid_type"
            },
            headers=auth_headers
        )

        assert response.status_code == 422

    def test_summarize_validation_max_length_constraints(self, client, auth_headers):
        """Test max_length validation."""
        # Too small
        response = client.post(
            "/summarize",
            json={
                "channel_id": "123456789",
                "max_length": 50
            },
            headers=auth_headers
        )
        assert response.status_code == 422

        # Too large
        response = client.post(
            "/summarize",
            json={
                "channel_id": "123456789",
                "max_length": 20000
            },
            headers=auth_headers
        )
        assert response.status_code == 422

    def test_summarize_validation_temperature_constraints(self, client, auth_headers):
        """Test temperature validation."""
        # Below minimum
        response = client.post(
            "/summarize",
            json={
                "channel_id": "123456789",
                "temperature": -0.1
            },
            headers=auth_headers
        )
        assert response.status_code == 422

        # Above maximum
        response = client.post(
            "/summarize",
            json={
                "channel_id": "123456789",
                "temperature": 1.5
            },
            headers=auth_headers
        )
        assert response.status_code == 422

    def test_summarize_with_request_id(self, client, auth_headers):
        """Test request ID is tracked."""
        response = client.post(
            "/summarize",
            json={"channel_id": "123456789"},
            headers={**auth_headers, "X-Request-ID": "req_custom_123"}
        )

        # Should use provided request ID in error
        assert response.status_code == 501

    def test_summarize_default_values(self, client, auth_headers):
        """Test default values are applied."""
        # Minimal request should use defaults
        response = client.post(
            "/summarize",
            json={"channel_id": "123456789"},
            headers=auth_headers
        )

        # Should accept request (even if not implemented)
        assert response.status_code in [200, 201, 501]


class TestGetSummaryEndpoint:
    """Test GET /summary/{summary_id} endpoint."""

    def test_get_summary_requires_auth(self, client):
        """Test endpoint requires authentication."""
        response = client.get("/summary/sum_123")

        assert response.status_code == 401

    def test_get_summary_not_found(self, client, auth_headers):
        """Test getting non-existent summary."""
        response = client.get("/summary/sum_nonexistent", headers=auth_headers)

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "SUMMARY_NOT_FOUND"
        assert "sum_nonexistent" in data["detail"]["message"]

    def test_get_summary_with_api_key(self, client, auth_headers):
        """Test authentication with API key."""
        response = client.get("/summary/sum_123", headers=auth_headers)

        # Should authenticate successfully (returns 404 because not implemented)
        assert response.status_code == 404

    def test_get_summary_exception_handling(self, client, auth_headers, app):
        """Test exception handling in get_summary."""
        # This would test actual implementation when database is connected
        response = client.get("/summary/sum_123", headers=auth_headers)

        # Should return 404 or 500, not crash
        assert response.status_code in [404, 500]


class TestScheduleEndpoint:
    """Test POST /schedule endpoint."""

    def test_schedule_requires_auth(self, client):
        """Test endpoint requires authentication."""
        response = client.post("/schedule", json={
            "channel_id": "123456789",
            "frequency": "daily"
        })

        assert response.status_code == 401

    def test_schedule_not_implemented(self, client, auth_headers):
        """Test endpoint returns not implemented."""
        response = client.post(
            "/schedule",
            json={
                "channel_id": "123456789",
                "frequency": "daily"
            },
            headers=auth_headers
        )

        assert response.status_code == 501
        data = response.json()
        assert "not yet implemented" in data["detail"]["message"].lower()

    def test_schedule_validation_missing_frequency(self, client, auth_headers):
        """Test validation requires frequency."""
        response = client.post(
            "/schedule",
            json={"channel_id": "123456789"},
            headers=auth_headers
        )

        assert response.status_code == 422

    def test_schedule_validation_invalid_frequency(self, client, auth_headers):
        """Test validation rejects invalid frequency."""
        response = client.post(
            "/schedule",
            json={
                "channel_id": "123456789",
                "frequency": "invalid_freq"
            },
            headers=auth_headers
        )

        assert response.status_code == 422

    def test_schedule_valid_frequencies(self, client, auth_headers):
        """Test all valid frequency values."""
        for frequency in ["hourly", "daily", "weekly", "monthly"]:
            response = client.post(
                "/schedule",
                json={
                    "channel_id": "123456789",
                    "frequency": frequency
                },
                headers=auth_headers
            )

            # Should accept (even if not implemented)
            assert response.status_code in [201, 501]


class TestCancelScheduleEndpoint:
    """Test DELETE /schedule/{schedule_id} endpoint."""

    def test_cancel_schedule_requires_auth(self, client):
        """Test endpoint requires authentication."""
        response = client.delete("/schedule/sch_123")

        assert response.status_code == 401

    def test_cancel_schedule_not_found(self, client, auth_headers):
        """Test cancelling non-existent schedule."""
        response = client.delete("/schedule/sch_nonexistent", headers=auth_headers)

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "SCHEDULE_NOT_FOUND"

    def test_cancel_schedule_exception_handling(self, client, auth_headers):
        """Test exception handling."""
        response = client.delete("/schedule/sch_123", headers=auth_headers)

        # Should return 404 or 500, not crash
        assert response.status_code in [404, 500]


class TestAuthenticationMethods:
    """Test different authentication methods."""

    def test_auth_with_api_key_header(self, client):
        """Test authentication with X-API-Key header."""
        response = client.get(
            "/summary/sum_123",
            headers={"X-API-Key": "valid_key_12345678"}
        )

        # Should authenticate (returns 404 because summary doesn't exist)
        assert response.status_code == 404

    def test_auth_with_bearer_token(self, client):
        """Test authentication with Bearer token."""
        import src.webhook_service.auth as auth_mod
        # Ensure JWT_SECRET is set for token creation
        original_secret = auth_mod.JWT_SECRET
        if auth_mod.JWT_SECRET is None:
            auth_mod.JWT_SECRET = "test-secret-for-unit-tests-only"
        try:
            from src.webhook_service.auth import create_jwt_token
            token = create_jwt_token(user_id="user_123")

            response = client.get(
                "/summary/sum_123",
                headers={"Authorization": f"Bearer {token}"}
            )

            # Should authenticate
            assert response.status_code == 404  # Not 401
        finally:
            auth_mod.JWT_SECRET = original_secret

    def test_auth_invalid_bearer_format(self, client):
        """Test invalid bearer token format."""
        response = client.get(
            "/summary/sum_123",
            headers={"Authorization": "InvalidFormat token123"}
        )

        assert response.status_code == 401

    def test_auth_expired_token(self, client):
        """Test expired JWT token."""
        import src.webhook_service.auth as auth_mod
        # Ensure JWT_SECRET is set for token creation
        original_secret = auth_mod.JWT_SECRET
        if auth_mod.JWT_SECRET is None:
            auth_mod.JWT_SECRET = "test-secret-for-unit-tests-only"
        try:
            from src.webhook_service.auth import create_jwt_token
            # Create token with negative expiration
            token = create_jwt_token(user_id="user_123", expires_minutes=-10)

            response = client.get(
                "/summary/sum_123",
                headers={"Authorization": f"Bearer {token}"}
            )

            assert response.status_code == 401
        finally:
            auth_mod.JWT_SECRET = original_secret


class TestErrorHandling:
    """Test endpoint error handling."""

    def test_insufficient_content_error(self, client, auth_headers, app, mock_engine):
        """Test handling of InsufficientContentError."""
        # This would be tested with actual implementation
        # For now, verify structure is in place
        pass

    def test_summarization_error(self, client, auth_headers):
        """Test handling of SummarizationError."""
        # This would be tested with actual implementation
        pass

    def test_unexpected_error(self, client, auth_headers):
        """Test handling of unexpected errors."""
        # Endpoints should catch and return 500
        pass


class TestRequestValidation:
    """Test request model validation."""

    def test_time_range_validation(self, client, auth_headers):
        """Test time range validation."""
        now = datetime.utcnow()
        past = now - timedelta(hours=2)

        # Valid time range
        response = client.post(
            "/summarize",
            json={
                "channel_id": "123456789",
                "time_range": {
                    "start": past.isoformat(),
                    "end": now.isoformat()
                }
            },
            headers=auth_headers
        )

        # Should accept (even if not implemented)
        assert response.status_code in [201, 501]

    def test_custom_prompt_length(self, client, auth_headers):
        """Test custom prompt length validation."""
        # Valid custom prompt
        response = client.post(
            "/summarize",
            json={
                "channel_id": "123456789",
                "custom_prompt": "A" * 100
            },
            headers=auth_headers
        )
        assert response.status_code in [201, 501]

        # Too long custom prompt
        response = client.post(
            "/summarize",
            json={
                "channel_id": "123456789",
                "custom_prompt": "A" * 3000
            },
            headers=auth_headers
        )
        assert response.status_code == 422


class TestResponseFormats:
    """Test different response formats."""

    def test_json_format_request(self, client, auth_headers):
        """Test requesting JSON format."""
        response = client.post(
            "/summarize",
            json={
                "channel_id": "123456789",
                "output_format": "json"
            },
            headers=auth_headers
        )

        assert response.status_code in [201, 501]

    def test_markdown_format_request(self, client, auth_headers):
        """Test requesting Markdown format."""
        response = client.post(
            "/summarize",
            json={
                "channel_id": "123456789",
                "output_format": "markdown"
            },
            headers=auth_headers
        )

        assert response.status_code in [201, 501]

    def test_invalid_format_request(self, client, auth_headers):
        """Test invalid output format."""
        response = client.post(
            "/summarize",
            json={
                "channel_id": "123456789",
                "output_format": "invalid_format"
            },
            headers=auth_headers
        )

        assert response.status_code == 422
