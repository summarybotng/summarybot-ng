"""Shared encryption utilities using Fernet symmetric encryption."""

import os
import logging
from typing import Optional

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

_cipher: Optional[Fernet] = None


def get_cipher() -> Fernet:
    """Get or create the Fernet cipher from ENCRYPTION_KEY env var."""
    global _cipher
    if _cipher is not None:
        return _cipher

    key = os.environ.get("ENCRYPTION_KEY")
    if not key:
        logger.warning(
            "ENCRYPTION_KEY not set, generating ephemeral key. "
            "Encrypted secrets will be lost on restart."
        )
        key = Fernet.generate_key().decode()

    _cipher = Fernet(key.encode() if isinstance(key, str) else key)
    return _cipher


def encrypt_value(plaintext: Optional[str]) -> Optional[str]:
    """Encrypt a string value. Returns None if input is None."""
    if plaintext is None:
        return None
    return get_cipher().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypt a string value. Returns None if input is None.

    Falls back to returning the raw value if decryption fails,
    to handle legacy unencrypted data gracefully.
    """
    if ciphertext is None:
        return None
    try:
        return get_cipher().decrypt(ciphertext.encode()).decode()
    except Exception:
        logger.warning("Failed to decrypt value, returning as plaintext (legacy data)")
        return ciphertext
