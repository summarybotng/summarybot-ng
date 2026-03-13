"""Tests for P0-1: HMAC signature validation wired to ingest endpoint."""

import hashlib
import hmac
import json
import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.feeds.ingest_handler import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)

VALID_PAYLOAD = {
    "source_type": "whatsapp",
    "channel_name": "test",
    "messages": [
        {
            "id": "1",
            "content": "hi",
            "author": "user1",
            "timestamp": "2026-01-01T00:00:00",
        }
    ],
}


@patch("src.feeds.ingest_handler._store_ingest_batch", new_callable=AsyncMock)
@patch.dict(os.environ, {"INGEST_API_KEY": "test-key"}, clear=False)
def test_ingest_no_secret_no_signature_required(mock_store):
    """When INGEST_WEBHOOK_SECRET is NOT set, requests proceed without X-Signature."""
    # Remove INGEST_WEBHOOK_SECRET if present
    env = os.environ.copy()
    env.pop("INGEST_WEBHOOK_SECRET", None)
    with patch.dict(os.environ, env, clear=True):
        response = client.post(
            "/api/v1/ingest",
            json=VALID_PAYLOAD,
            headers={"X-API-Key": "test-key"},
        )
    # Should NOT be a 401 for missing signature
    assert response.status_code != 401 or "signature" not in response.json().get(
        "detail", ""
    ).lower()


@patch("src.feeds.ingest_handler._store_ingest_batch", new_callable=AsyncMock)
@patch.dict(
    os.environ,
    {"INGEST_API_KEY": "test-key", "INGEST_WEBHOOK_SECRET": "s3cret"},
    clear=False,
)
def test_ingest_secret_configured_missing_signature_401(mock_store):
    """When INGEST_WEBHOOK_SECRET is set but X-Signature header is missing, return 401."""
    response = client.post(
        "/api/v1/ingest",
        json=VALID_PAYLOAD,
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 401
    assert "Missing X-Signature" in response.json()["detail"]


@patch("src.feeds.ingest_handler._store_ingest_batch", new_callable=AsyncMock)
@patch.dict(
    os.environ,
    {"INGEST_API_KEY": "test-key", "INGEST_WEBHOOK_SECRET": "s3cret"},
    clear=False,
)
def test_ingest_secret_configured_invalid_signature_401(mock_store):
    """When INGEST_WEBHOOK_SECRET is set and X-Signature is wrong, return 401."""
    response = client.post(
        "/api/v1/ingest",
        json=VALID_PAYLOAD,
        headers={
            "X-API-Key": "test-key",
            "X-Signature": "deadbeef",
        },
    )
    assert response.status_code == 401
    assert "Invalid webhook signature" in response.json()["detail"]


@patch("src.feeds.ingest_handler._store_ingest_batch", new_callable=AsyncMock)
@patch.dict(
    os.environ,
    {"INGEST_API_KEY": "test-key", "INGEST_WEBHOOK_SECRET": "s3cret"},
    clear=False,
)
def test_ingest_secret_configured_valid_signature_success(mock_store):
    """When INGEST_WEBHOOK_SECRET is set and X-Signature is correct, request passes signature check."""
    secret = "s3cret"
    body = json.dumps(VALID_PAYLOAD).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    response = client.post(
        "/api/v1/ingest",
        content=body,
        headers={
            "X-API-Key": "test-key",
            "X-Signature": signature,
            "Content-Type": "application/json",
        },
    )
    # Should NOT be 401 for signature issues; it passed signature validation
    assert response.status_code != 401
