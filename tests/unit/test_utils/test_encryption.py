"""Tests for src.utils.encryption — Fernet encrypt / decrypt helpers."""

import os
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

import src.utils.encryption as enc
from src.utils.encryption import decrypt_value, encrypt_value


@pytest.fixture(autouse=True)
def reset_cipher():
    """Reset the module-level _cipher singleton so each test starts fresh."""
    enc._cipher = None
    yield
    enc._cipher = None


_STABLE_KEY = Fernet.generate_key().decode()


# ── Round-trip ───────────────────────────────────────────────────


@patch.dict(os.environ, {"ENCRYPTION_KEY": _STABLE_KEY})
def test_encrypt_decrypt_roundtrip():
    original = "super-secret-webhook-token"
    encrypted = encrypt_value(original)
    assert encrypted is not None
    assert encrypted != original
    assert decrypt_value(encrypted) == original


# ── None handling ────────────────────────────────────────────────


def test_encrypt_none_returns_none():
    assert encrypt_value(None) is None


def test_decrypt_none_returns_none():
    assert decrypt_value(None) is None


# ── Legacy / graceful fallback ───────────────────────────────────


@patch.dict(os.environ, {"ENCRYPTION_KEY": _STABLE_KEY})
def test_legacy_plaintext_handled_gracefully():
    raw = "not-encrypted-text"
    result = decrypt_value(raw)
    assert result == raw


# ── Fernet uses a random IV, so two encryptions should differ ───


@patch.dict(os.environ, {"ENCRYPTION_KEY": _STABLE_KEY})
def test_different_encryptions_differ():
    plaintext = "same-value"
    a = encrypt_value(plaintext)
    # Reset cipher to avoid caching, but keep the same key
    enc._cipher = None
    b = encrypt_value(plaintext)
    assert a != b
