"""
Tests for src/slack/token_store.py - Secure token storage.

Tests encryption/decryption round-trip, token validation,
masking, and type detection for Slack OAuth tokens.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.slack.token_store import SecureSlackTokenStore


class TestEncryptToken:
    """Tests for encrypt_token method."""

    def test_should_encrypt_valid_bot_token(self):
        """Test encrypting a valid bot token."""
        token = "xoxb-fake-test-token-not-real-abc123"

        encrypted = SecureSlackTokenStore.encrypt_token(token)

        assert encrypted is not None
        assert encrypted != token
        assert len(encrypted) > len(token)

    def test_should_encrypt_user_token(self):
        """Test encrypting a user token."""
        token = "xoxp-fake-user-token-for-testing-only"

        encrypted = SecureSlackTokenStore.encrypt_token(token)

        assert encrypted is not None
        assert encrypted != token

    def test_should_encrypt_app_token(self):
        """Test encrypting an app token."""
        token = "xoxa-fake-app-token-testing-only"

        encrypted = SecureSlackTokenStore.encrypt_token(token)

        assert encrypted is not None
        assert encrypted != token

    def test_should_raise_on_empty_token(self):
        """Test encrypt_token raises on empty token."""
        with pytest.raises(ValueError) as exc_info:
            SecureSlackTokenStore.encrypt_token("")

        assert "cannot be empty" in str(exc_info.value)

    def test_should_warn_on_invalid_format(self, caplog):
        """Test encrypt_token warns on invalid token format."""
        import logging
        caplog.set_level(logging.WARNING)

        # Token without valid prefix
        token = "invalid-token-format-12345"
        encrypted = SecureSlackTokenStore.encrypt_token(token)

        # Should still encrypt but log warning
        assert encrypted is not None
        assert "does not appear to be a valid Slack token format" in caplog.text


class TestDecryptToken:
    """Tests for decrypt_token method."""

    def test_should_decrypt_encrypted_token(self):
        """Test decrypting an encrypted token."""
        original = "xoxb-fake-test-token-not-real-abc123"
        encrypted = SecureSlackTokenStore.encrypt_token(original)

        decrypted = SecureSlackTokenStore.decrypt_token(encrypted)

        assert decrypted == original

    def test_should_roundtrip_preserve_token(self):
        """Test encrypt-decrypt roundtrip preserves original."""
        tokens = [
            "xoxb-fake-test-token-not-real-abc123",
            "xoxp-fake-user-token-testing-only",
            "xoxa-fake-app-token-testing",
        ]

        for token in tokens:
            encrypted = SecureSlackTokenStore.encrypt_token(token)
            decrypted = SecureSlackTokenStore.decrypt_token(encrypted)
            assert decrypted == token

    def test_should_raise_on_empty_encrypted_token(self):
        """Test decrypt_token raises on empty input."""
        with pytest.raises(ValueError) as exc_info:
            SecureSlackTokenStore.decrypt_token("")

        assert "cannot be empty" in str(exc_info.value)

    def test_should_produce_different_ciphertexts(self):
        """Test same plaintext produces different ciphertexts (random IV)."""
        token = "xoxb-same-token-for-both-encryptions"

        encrypted1 = SecureSlackTokenStore.encrypt_token(token)
        encrypted2 = SecureSlackTokenStore.encrypt_token(token)

        # Fernet uses random IV, so ciphertexts should differ
        assert encrypted1 != encrypted2

        # But both should decrypt to the same value
        assert SecureSlackTokenStore.decrypt_token(encrypted1) == token
        assert SecureSlackTokenStore.decrypt_token(encrypted2) == token


class TestMaskToken:
    """Tests for mask_token method."""

    def test_should_mask_token_showing_prefix_and_suffix(self):
        """Test token masking shows first 8 and last 4 chars."""
        token = "xoxb-fake-test-token-not-real-abc123"

        masked = SecureSlackTokenStore.mask_token(token)

        assert masked.startswith("xoxb-fak")
        assert masked.endswith("123")
        assert "..." in masked

    def test_should_mask_short_token_completely(self):
        """Test short tokens are fully masked."""
        token = "short"

        masked = SecureSlackTokenStore.mask_token(token)

        assert masked == "***"

    def test_should_handle_empty_token(self):
        """Test empty token returns asterisks."""
        masked = SecureSlackTokenStore.mask_token("")

        assert masked == "***"

    def test_should_handle_none_token(self):
        """Test None token returns asterisks."""
        masked = SecureSlackTokenStore.mask_token(None)

        assert masked == "***"

    def test_should_mask_token_at_boundary_length(self):
        """Test tokens at boundary length (12 chars) are fully masked."""
        token = "exactly12chr"

        masked = SecureSlackTokenStore.mask_token(token)

        assert masked == "***"

    def test_should_mask_token_just_above_boundary(self):
        """Test tokens just above boundary are partially masked."""
        token = "exactly13chrs"  # 13 chars

        masked = SecureSlackTokenStore.mask_token(token)

        assert masked.startswith("exactly1")
        assert masked.endswith("chrs")


class TestValidateTokenFormat:
    """Tests for validate_token_format method."""

    def test_should_validate_bot_token(self):
        """Test valid bot token format."""
        token = "xoxb-fake-test-token-not-real-abc123"

        assert SecureSlackTokenStore.validate_token_format(token) is True

    def test_should_validate_user_token(self):
        """Test valid user token format."""
        token = "xoxp-fake-user-token-testing-only"

        assert SecureSlackTokenStore.validate_token_format(token) is True

    def test_should_validate_app_token(self):
        """Test valid app token format."""
        token = "xoxa-fake-app-token-testing"

        assert SecureSlackTokenStore.validate_token_format(token) is True

    def test_should_reject_invalid_prefix(self):
        """Test token with invalid prefix is rejected."""
        token = "xoxz-invalid-prefix-token"

        assert SecureSlackTokenStore.validate_token_format(token) is False

    def test_should_reject_empty_token(self):
        """Test empty token is rejected."""
        assert SecureSlackTokenStore.validate_token_format("") is False

    def test_should_reject_none_token(self):
        """Test None token is rejected."""
        assert SecureSlackTokenStore.validate_token_format(None) is False

    def test_should_reject_short_token(self):
        """Test token shorter than 20 chars is rejected."""
        token = "xoxb-short"  # Valid prefix but too short

        assert SecureSlackTokenStore.validate_token_format(token) is False


class TestGetTokenType:
    """Tests for get_token_type method."""

    def test_should_identify_bot_token(self):
        """Test bot token type detection."""
        token = "xoxb-fake-short-token"

        assert SecureSlackTokenStore.get_token_type(token) == "bot"

    def test_should_identify_user_token(self):
        """Test user token type detection."""
        token = "xoxp-fake-user-token-testing-only"

        assert SecureSlackTokenStore.get_token_type(token) == "user"

    def test_should_identify_app_token(self):
        """Test app token type detection."""
        token = "xoxa-fake-app-token-testing"

        assert SecureSlackTokenStore.get_token_type(token) == "app"

    def test_should_return_none_for_invalid_prefix(self):
        """Test unknown prefix returns None."""
        token = "xoxz-unknown-prefix"

        assert SecureSlackTokenStore.get_token_type(token) is None

    def test_should_return_none_for_empty_token(self):
        """Test empty token returns None."""
        assert SecureSlackTokenStore.get_token_type("") is None

    def test_should_return_none_for_none_token(self):
        """Test None token returns None."""
        assert SecureSlackTokenStore.get_token_type(None) is None


class TestTokenStoreIntegration:
    """Integration tests for token store."""

    def test_should_encrypt_validate_and_decrypt(self):
        """Test full workflow: validate, encrypt, mask, decrypt."""
        token = "xoxb-fake-test-token-not-real-abc123"

        # Validate format
        assert SecureSlackTokenStore.validate_token_format(token) is True

        # Get type
        assert SecureSlackTokenStore.get_token_type(token) == "bot"

        # Encrypt
        encrypted = SecureSlackTokenStore.encrypt_token(token)
        assert encrypted != token

        # Mask (for logging)
        masked = SecureSlackTokenStore.mask_token(token)
        assert "..." in masked
        assert token not in masked

        # Decrypt
        decrypted = SecureSlackTokenStore.decrypt_token(encrypted)
        assert decrypted == token

    def test_should_handle_encrypted_token_masking(self):
        """Test masking an encrypted token."""
        token = "xoxb-fake-test-token-not-real-abc123"
        encrypted = SecureSlackTokenStore.encrypt_token(token)

        masked = SecureSlackTokenStore.mask_token(encrypted)

        # Should mask the encrypted string
        assert "..." in masked
        assert len(masked) < len(encrypted)
