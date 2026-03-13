"""Unit tests for ConfigManager save-lock fix (P0-4)."""

import asyncio
import json

import pytest
from unittest.mock import patch, MagicMock

from src.config.manager import ConfigManager
from src.config.settings import BotConfig


def _make_bot_config():
    """Create a minimal BotConfig mock for save tests."""
    cfg = MagicMock()
    cfg.guild_configs = {}
    cfg.webhook_config.host = "0.0.0.0"
    cfg.webhook_config.port = 8080
    cfg.webhook_config.enabled = False
    cfg.webhook_config.cors_origins = []
    cfg.webhook_config.rate_limit = 100
    cfg.cache_config.backend = "memory"
    cfg.cache_config.default_ttl = 300
    cfg.cache_config.max_size = 1000
    cfg.log_level.value = "INFO"
    cfg.max_message_batch = 100
    cfg.cache_ttl = 300
    return cfg


@pytest.mark.unit
class TestConfigManagerLock:
    """Tests verifying the instance-level _save_lock on ConfigManager."""

    def test_save_lock_is_instance_level(self):
        """_save_lock must be an asyncio.Lock on the instance."""
        mgr = ConfigManager(config_path="/tmp/dummy.json")
        assert isinstance(mgr._save_lock, asyncio.Lock)

        # Two instances must have distinct locks.
        mgr2 = ConfigManager(config_path="/tmp/dummy2.json")
        assert mgr._save_lock is not mgr2._save_lock

    @pytest.mark.asyncio
    @patch("src.config.validation.ConfigValidator.validate_config", return_value=[])
    async def test_concurrent_save_config_serialized(self, _mock_validate, tmp_path):
        """Two concurrent saves must both complete without corrupting the file."""
        config_file = tmp_path / "config.json"
        mgr = ConfigManager(config_path=str(config_file))

        cfg1 = _make_bot_config()
        cfg2 = _make_bot_config()

        # Run two saves concurrently; the lock must serialise them.
        await asyncio.gather(
            mgr.save_config(cfg1),
            mgr.save_config(cfg2),
        )

        # The file must exist and be valid JSON (not corrupted).
        assert config_file.exists()
        data = json.loads(config_file.read_text())
        assert isinstance(data, dict)
        assert "guild_configs" in data
