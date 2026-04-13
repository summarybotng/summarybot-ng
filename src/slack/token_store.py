"""
Secure token storage for Slack OAuth tokens (ADR-043).

Uses Fernet symmetric encryption from src/utils/encryption.py.
"""

import logging
from typing import Optional

from ..utils.encryption import encrypt_value, decrypt_value

logger = logging.getLogger(__name__)


class SecureSlackTokenStore:
    """Manages encrypted storage of Slack OAuth tokens (ADR-043 Section 8.1)."""

    @staticmethod
    def encrypt_token(token: str) -> str:
        """Encrypt a Slack bot token for storage.

        Args:
            token: Plain text Slack bot token (xoxb-*)

        Returns:
            Fernet-encrypted token string

        Raises:
            ValueError: If token is invalid
        """
        if not token:
            raise ValueError("Token cannot be empty")

        if not token.startswith(("xoxb-", "xoxp-", "xoxa-")):
            logger.warning("Token does not appear to be a valid Slack token format")

        encrypted = encrypt_value(token)
        if encrypted is None:
            raise ValueError("Failed to encrypt token")

        return encrypted

    @staticmethod
    def decrypt_token(encrypted_token: str) -> str:
        """Decrypt a stored Slack bot token.

        Args:
            encrypted_token: Fernet-encrypted token string

        Returns:
            Plain text Slack bot token

        Raises:
            ValueError: If decryption fails
        """
        if not encrypted_token:
            raise ValueError("Encrypted token cannot be empty")

        decrypted = decrypt_value(encrypted_token)
        if decrypted is None:
            raise ValueError("Failed to decrypt token")

        return decrypted

    @staticmethod
    def mask_token(token: str) -> str:
        """Mask a token for logging/display purposes.

        Args:
            token: Plain text or encrypted token

        Returns:
            Masked token showing only first and last 4 characters
        """
        if not token:
            return "***"

        if len(token) <= 12:
            return "***"

        return f"{token[:8]}...{token[-4:]}"

    @staticmethod
    def validate_token_format(token: str) -> bool:
        """Validate that a token has the correct Slack format.

        Args:
            token: Token to validate

        Returns:
            True if token appears to be valid Slack format
        """
        if not token:
            return False

        # Bot tokens: xoxb-*
        # User tokens: xoxp-* (OAuth user token)
        # App tokens: xoxa-* (App-level token)
        valid_prefixes = ("xoxb-", "xoxp-", "xoxa-")
        return token.startswith(valid_prefixes) and len(token) > 20

    @staticmethod
    def get_token_type(token: str) -> Optional[str]:
        """Determine the type of Slack token.

        Args:
            token: Plain text Slack token

        Returns:
            Token type string or None if invalid
        """
        if not token:
            return None

        if token.startswith("xoxb-"):
            return "bot"
        elif token.startswith("xoxp-"):
            return "user"
        elif token.startswith("xoxa-"):
            return "app"
        else:
            return None
