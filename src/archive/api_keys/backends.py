"""
API key storage backends.

Supports multiple secure storage options for per-server OpenRouter keys:
- Environment variables
- Encrypted files
- HashiCorp Vault (future)
- Database (future)
"""

import base64
import json
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ApiKeyBackend(ABC):
    """Abstract base class for API key storage backends."""

    @abstractmethod
    async def get_key(self, key_ref: str) -> Optional[str]:
        """
        Retrieve an API key.

        Args:
            key_ref: Key reference (format depends on backend)

        Returns:
            API key value or None if not found
        """
        pass

    @abstractmethod
    async def set_key(self, key_ref: str, key_value: str) -> bool:
        """
        Store an API key.

        Args:
            key_ref: Key reference
            key_value: API key value

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def delete_key(self, key_ref: str) -> bool:
        """
        Delete an API key.

        Args:
            key_ref: Key reference

        Returns:
            True if deleted
        """
        pass

    @abstractmethod
    async def key_exists(self, key_ref: str) -> bool:
        """
        Check if a key exists.

        Args:
            key_ref: Key reference

        Returns:
            True if key exists
        """
        pass


class EnvVarBackend(ApiKeyBackend):
    """
    Environment variable backend.

    Key references use format: env:VARIABLE_NAME
    Example: env:OPENROUTER_KEY_DISCORD_123456789
    """

    def _parse_ref(self, key_ref: str) -> str:
        """Parse key reference to get env var name."""
        if key_ref.startswith("env:"):
            return key_ref[4:]
        return key_ref

    async def get_key(self, key_ref: str) -> Optional[str]:
        var_name = self._parse_ref(key_ref)
        value = os.environ.get(var_name)
        if value:
            logger.debug(f"Retrieved key from env var: {var_name}")
        return value

    async def set_key(self, key_ref: str, key_value: str) -> bool:
        var_name = self._parse_ref(key_ref)
        os.environ[var_name] = key_value
        logger.info(f"Set key in env var: {var_name}")
        return True

    async def delete_key(self, key_ref: str) -> bool:
        var_name = self._parse_ref(key_ref)
        if var_name in os.environ:
            del os.environ[var_name]
            logger.info(f"Deleted key from env var: {var_name}")
            return True
        return False

    async def key_exists(self, key_ref: str) -> bool:
        var_name = self._parse_ref(key_ref)
        return var_name in os.environ


class EncryptedFileBackend(ApiKeyBackend):
    """
    Encrypted file backend.

    Key references use format: file:filename
    Example: file:keys/discord_123456789.enc

    Uses Fernet symmetric encryption with a master key from environment.
    """

    def __init__(
        self,
        keys_dir: Path,
        master_key_env: str = "SUMMARYBOT_MASTER_KEY"
    ):
        """
        Initialize encrypted file backend.

        Args:
            keys_dir: Directory for encrypted key files
            master_key_env: Environment variable name for master key
        """
        self.keys_dir = keys_dir
        self.master_key_env = master_key_env
        self._fernet = None

    def _get_fernet(self):
        """Get or create Fernet instance."""
        if self._fernet is None:
            master_key = os.environ.get(self.master_key_env)
            if not master_key:
                raise ValueError(
                    f"Master key not found in environment: {self.master_key_env}"
                )

            # Ensure key is valid Fernet format
            try:
                from cryptography.fernet import Fernet
                self._fernet = Fernet(master_key.encode())
            except Exception as e:
                raise ValueError(f"Invalid master key format: {e}")

        return self._fernet

    def _parse_ref(self, key_ref: str) -> Path:
        """Parse key reference to get file path."""
        if key_ref.startswith("file:"):
            filename = key_ref[5:]
        else:
            filename = key_ref

        return self.keys_dir / filename

    async def get_key(self, key_ref: str) -> Optional[str]:
        try:
            file_path = self._parse_ref(key_ref)
            if not file_path.exists():
                return None

            encrypted_data = file_path.read_bytes()
            fernet = self._get_fernet()
            decrypted = fernet.decrypt(encrypted_data)
            logger.debug(f"Retrieved key from file: {file_path}")
            return decrypted.decode()

        except Exception as e:
            logger.error(f"Failed to get key from file {key_ref}: {e}")
            return None

    async def set_key(self, key_ref: str, key_value: str) -> bool:
        try:
            file_path = self._parse_ref(key_ref)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            fernet = self._get_fernet()
            encrypted = fernet.encrypt(key_value.encode())
            file_path.write_bytes(encrypted)

            # Set restrictive permissions
            file_path.chmod(0o600)
            logger.info(f"Saved encrypted key to file: {file_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to set key in file {key_ref}: {e}")
            return False

    async def delete_key(self, key_ref: str) -> bool:
        try:
            file_path = self._parse_ref(key_ref)
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted encrypted key file: {file_path}")
                return True
            return False

        except Exception as e:
            logger.error(f"Failed to delete key file {key_ref}: {e}")
            return False

    async def key_exists(self, key_ref: str) -> bool:
        file_path = self._parse_ref(key_ref)
        return file_path.exists()


class VaultBackend(ApiKeyBackend):
    """
    HashiCorp Vault backend (stub for future implementation).

    Key references use format: vault:path/to/secret
    Example: vault:openrouter/acme-corp
    """

    def __init__(
        self,
        vault_addr: str,
        vault_token: Optional[str] = None,
        path_prefix: str = "secret/summarybot/openrouter"
    ):
        """
        Initialize Vault backend.

        Args:
            vault_addr: Vault server address
            vault_token: Vault token (or from VAULT_TOKEN env)
            path_prefix: Path prefix for secrets
        """
        self.vault_addr = vault_addr
        self.vault_token = vault_token or os.environ.get("VAULT_TOKEN")
        self.path_prefix = path_prefix

    async def get_key(self, key_ref: str) -> Optional[str]:
        # TODO: Implement Vault integration
        logger.warning("Vault backend not implemented")
        raise NotImplementedError("Vault backend not yet implemented")

    async def set_key(self, key_ref: str, key_value: str) -> bool:
        raise NotImplementedError("Vault backend not yet implemented")

    async def delete_key(self, key_ref: str) -> bool:
        raise NotImplementedError("Vault backend not yet implemented")

    async def key_exists(self, key_ref: str) -> bool:
        raise NotImplementedError("Vault backend not yet implemented")


def get_backend_for_ref(key_ref: str, config: dict) -> ApiKeyBackend:
    """
    Get the appropriate backend for a key reference.

    Args:
        key_ref: Key reference (e.g., "env:VAR", "file:path", "vault:path")
        config: Backend configuration

    Returns:
        Appropriate backend instance
    """
    if key_ref.startswith("env:"):
        return EnvVarBackend()

    elif key_ref.startswith("file:"):
        keys_dir = Path(config.get("keys_dir", "./data/keys"))
        return EncryptedFileBackend(keys_dir)

    elif key_ref.startswith("vault:"):
        vault_addr = config.get("vault_addr", os.environ.get("VAULT_ADDR"))
        if not vault_addr:
            raise ValueError("Vault address not configured")
        return VaultBackend(vault_addr)

    else:
        # Default to env var
        return EnvVarBackend()
