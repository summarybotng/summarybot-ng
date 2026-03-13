"""Tests for encryption integration in SQLiteConfigRepository."""

import json
import pytest
import pytest_asyncio
import os

import src.utils.encryption as encryption_module
from src.data.sqlite.config_repository import SQLiteConfigRepository
from src.data.sqlite.connection import SQLiteConnection
from src.config.settings import GuildConfig, PermissionSettings, SummaryOptions, SummaryLength
from src.utils.encryption import encrypt_value, decrypt_value, get_cipher
from cryptography.fernet import Fernet


# Use a fixed key for deterministic test results
TEST_ENCRYPTION_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def reset_encryption_state(monkeypatch):
    """Reset encryption cipher state and set a deterministic key for each test."""
    encryption_module._cipher = None
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    yield
    encryption_module._cipher = None


def _make_guild_config(guild_id: str = "guild-001", webhook_secret: str = None) -> GuildConfig:
    """Helper to create a GuildConfig with minimal boilerplate."""
    return GuildConfig(
        guild_id=guild_id,
        enabled_channels=["ch-1"],
        excluded_channels=[],
        default_summary_options=SummaryOptions(summary_length=SummaryLength.BRIEF),
        permission_settings=PermissionSettings(),
        webhook_enabled=True,
        webhook_secret=webhook_secret,
    )


@pytest.mark.asyncio
async def test_webhook_secret_encrypted_on_save(in_memory_db: SQLiteConnection):
    """Saving a GuildConfig should store the webhook_secret encrypted, not as plaintext."""
    repo = SQLiteConfigRepository(in_memory_db)
    config = _make_guild_config(webhook_secret="my_secret")

    await repo.save_guild_config(config)

    # Read raw value directly from DB, bypassing the repository decryption
    row = await in_memory_db.fetch_one(
        "SELECT webhook_secret FROM guild_configs WHERE guild_id = ?",
        ("guild-001",),
    )

    raw_value = row["webhook_secret"]
    # The stored value must NOT be the original plaintext
    assert raw_value != "my_secret"
    # But decrypting it should yield the original
    assert decrypt_value(raw_value) == "my_secret"


@pytest.mark.asyncio
async def test_webhook_secret_decrypted_on_read(in_memory_db: SQLiteConnection):
    """Reading a GuildConfig via the repository should return the decrypted secret."""
    repo = SQLiteConfigRepository(in_memory_db)
    config = _make_guild_config(webhook_secret="my_secret")

    await repo.save_guild_config(config)
    loaded = await repo.get_guild_config("guild-001")

    assert loaded is not None
    assert loaded.webhook_secret == "my_secret"


@pytest.mark.asyncio
async def test_legacy_plaintext_handled_gracefully(in_memory_db: SQLiteConnection):
    """A row with a plaintext (unencrypted) webhook_secret should be returned as-is."""
    # Directly insert a row with plaintext secret, simulating legacy data
    options = SummaryOptions(summary_length=SummaryLength.BRIEF)
    permissions = PermissionSettings()

    await in_memory_db.execute(
        """INSERT INTO guild_configs
           (guild_id, enabled_channels, excluded_channels,
            default_summary_options, permission_settings,
            webhook_enabled, webhook_secret)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            "guild-legacy",
            json.dumps([]),
            json.dumps([]),
            json.dumps(options.to_dict()),
            json.dumps(permissions.to_dict()),
            1,
            "plaintext_secret",
        ),
    )

    repo = SQLiteConfigRepository(in_memory_db)
    loaded = await repo.get_guild_config("guild-legacy")

    assert loaded is not None
    # decrypt_value falls back to returning plaintext when decryption fails
    assert loaded.webhook_secret == "plaintext_secret"
