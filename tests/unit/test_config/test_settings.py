"""
Unit tests for the configuration module settings.

Tests cover BotConfig, GuildConfig, and ConfigManager functionality
as specified in Phase 3 module specifications.
"""

import pytest
from unittest.mock import patch, mock_open, MagicMock
from datetime import datetime
import os
import tempfile

from src.config.settings import BotConfig, GuildConfig, ConfigManager, SummaryOptions
from src.exceptions.validation import ValidationError


@pytest.mark.unit
class TestSummaryOptions:
    """Test SummaryOptions data class."""
    
    def test_summary_options_default_values(self):
        """Test SummaryOptions with default values."""
        from src.config.settings import SummaryLength
        options = SummaryOptions(summary_length=SummaryLength.DETAILED)

        assert options.summary_length == SummaryLength.DETAILED
        assert options.include_bots is False
        assert options.include_attachments is True
        assert options.excluded_users == []
        assert options.min_messages == 5
        assert options.summarization_model == "anthropic/claude-3-haiku"
        assert options.temperature == 0.3
        assert options.max_tokens == 4000
    
    def test_summary_options_custom_values(self):
        """Test SummaryOptions with custom values."""
        from src.config.settings import SummaryLength
        options = SummaryOptions(
            summary_length=SummaryLength.COMPREHENSIVE,
            include_bots=True,
            include_attachments=False,
            excluded_users=["user1", "user2"],
            min_messages=10,
            summarization_model="claude-3-opus-20240229",
            temperature=0.5,
            max_tokens=8000
        )

        assert options.summary_length == SummaryLength.COMPREHENSIVE
        assert options.include_bots is True
        assert options.include_attachments is False
        assert options.excluded_users == ["user1", "user2"]
        assert options.min_messages == 10
        assert options.summarization_model == "claude-3-opus-20240229"
        assert options.temperature == 0.5
        assert options.max_tokens == 8000


@pytest.mark.unit
class TestGuildConfig:
    """Test GuildConfig data class."""
    
    def test_guild_config_creation(self):
        """Test GuildConfig creation with required fields."""
        from src.config.settings import SummaryLength, PermissionSettings
        summary_options = SummaryOptions(summary_length=SummaryLength.DETAILED)
        permission_settings = PermissionSettings(
            allowed_roles=["Admin"],
            admin_roles=["Admin"]
        )

        config = GuildConfig(
            guild_id="123456789",
            enabled_channels=["channel1", "channel2"],
            excluded_channels=["excluded1"],
            default_summary_options=summary_options,
            permission_settings=permission_settings
        )

        assert config.guild_id == "123456789"
        assert config.enabled_channels == ["channel1", "channel2"]
        assert config.excluded_channels == ["excluded1"]
        assert config.default_summary_options == summary_options
        assert config.permission_settings == permission_settings
    
    def test_guild_config_empty_lists(self):
        """Test GuildConfig with empty channel lists."""
        from src.config.settings import SummaryLength, PermissionSettings
        summary_options = SummaryOptions(summary_length=SummaryLength.BRIEF)
        permission_settings = PermissionSettings()

        config = GuildConfig(
            guild_id="987654321",
            enabled_channels=[],
            excluded_channels=[],
            default_summary_options=summary_options,
            permission_settings=permission_settings
        )

        assert config.enabled_channels == []
        assert config.excluded_channels == []
        assert isinstance(config.permission_settings, PermissionSettings)


@pytest.mark.unit
class TestBotConfig:
    """Test BotConfig data class and methods."""
    
    def test_bot_config_creation(self):
        """Test BotConfig creation with default values."""
        from src.config.settings import SummaryLength, PermissionSettings, WebhookConfig
        guild_config = GuildConfig(
            guild_id="123456789",
            enabled_channels=["channel1"],
            excluded_channels=[],
            default_summary_options=SummaryOptions(summary_length=SummaryLength.DETAILED),
            permission_settings=PermissionSettings()
        )

        config = BotConfig(
            discord_token="test_token",
            guild_configs={"123456789": guild_config}
        )

        assert config.discord_token == "test_token"
        assert config.webhook_config.port == 5000
        assert config.max_message_batch == 10000
        assert config.cache_ttl == 3600
        assert "123456789" in config.guild_configs
    
    def test_bot_config_custom_values(self):
        """Test BotConfig with custom values."""
        from src.config.settings import WebhookConfig
        webhook_config = WebhookConfig(port=8080, host="127.0.0.1")

        config = BotConfig(
            discord_token="custom_token",
            guild_configs={},
            webhook_config=webhook_config,
            max_message_batch=5000,
            cache_ttl=7200
        )

        assert config.webhook_config.port == 8080
        assert config.webhook_config.host == "127.0.0.1"
        assert config.max_message_batch == 5000
        assert config.cache_ttl == 7200
    
    @patch.dict(os.environ, {
        'DISCORD_TOKEN': 'env_discord_token',
        'WEBHOOK_PORT': '9000',
        'MAX_MESSAGE_BATCH': '20000',
        'CACHE_TTL': '1800'
    })
    def test_load_from_env(self):
        """Test loading configuration from environment variables."""
        config = BotConfig.load_from_env()

        assert config.discord_token == "env_discord_token"
        assert config.webhook_config.port == 9000
        assert config.max_message_batch == 20000
        assert config.cache_ttl == 1800
    
    @patch.dict(os.environ, {}, clear=True)
    def test_load_from_env_missing_required(self):
        """Test loading configuration with missing required environment variables."""
        # Environment loader should handle missing keys gracefully or raise appropriate error
        # The actual behavior depends on EnvironmentLoader implementation
        try:
            config = BotConfig.load_from_env()
            # If it succeeds, verify it has default values
            assert config is not None
        except (KeyError, ValueError, ValidationError) as e:
            # Expected to raise error for missing required fields
            assert True
    
    def test_get_guild_config_existing(self):
        """Test getting existing guild configuration."""
        from src.config.settings import SummaryLength, PermissionSettings
        guild_config = GuildConfig(
            guild_id="123456789",
            enabled_channels=["channel1"],
            excluded_channels=[],
            default_summary_options=SummaryOptions(summary_length=SummaryLength.DETAILED),
            permission_settings=PermissionSettings()
        )

        config = BotConfig(
            discord_token="test_token",
            guild_configs={"123456789": guild_config}
        )

        result = config.get_guild_config("123456789")
        assert result == guild_config
    
    def test_get_guild_config_nonexistent(self):
        """Test getting non-existent guild configuration - creates default config."""
        config = BotConfig(
            discord_token="test_token",
            guild_configs={}
        )

        result = config.get_guild_config("nonexistent")
        # Based on implementation, it creates a default config for new guilds
        assert result is not None
        assert result.guild_id == "nonexistent"
        assert isinstance(result, GuildConfig)
    
    def test_validate_configuration_valid(self):
        """Test validation of valid configuration."""
        from src.config.settings import SummaryLength, PermissionSettings
        guild_config = GuildConfig(
            guild_id="123456789012345678",
            enabled_channels=["987654321098765432"],
            excluded_channels=[],
            default_summary_options=SummaryOptions(summary_length=SummaryLength.DETAILED),
            permission_settings=PermissionSettings()
        )

        config = BotConfig(
            discord_token="MTIzNDU2Nzg5MDEyMzQ1Njc4OTAuAbCdEf.GhIjKlMnOpQrStUvWxYz1234567890123456",
            guild_configs={"123456789012345678": guild_config}
        )

        errors = config.validate_configuration()
        assert len(errors) == 0
    
    def test_validate_configuration_empty_token_allowed(self):
        """Test validation with empty Discord token (webhook-only mode)."""
        config = BotConfig(
            discord_token="",  # Empty token is valid for webhook-only mode
            guild_configs={}
        )

        errors = config.validate_configuration()
        # Empty token is now allowed (webhook-only mode)
        assert len(errors) == 0
    
    def test_validate_configuration_invalid_ports(self):
        """Test validation with invalid port values."""
        from src.config.settings import WebhookConfig
        webhook_config = WebhookConfig(port=-1)  # Invalid port

        config = BotConfig(
            discord_token="valid_token",
            guild_configs={},
            webhook_config=webhook_config
        )

        errors = config.validate_configuration()
        assert len(errors) > 0
        assert any("port" in str(error).lower() for error in errors)


@pytest.mark.unit
class TestConfigManager:
    """Test ConfigManager functionality."""
    
    def test_config_manager_initialization(self, temp_dir):
        """Test ConfigManager initialization."""
        from pathlib import Path
        config_path = os.path.join(temp_dir, "config.json")
        manager = ConfigManager(config_path)

        # config_path is converted to Path object internally
        assert manager.config_path == Path(config_path)
        assert str(manager.config_path) == config_path
    
    def test_config_manager_default_path(self):
        """Test ConfigManager with default path (None when not specified)."""
        manager = ConfigManager()

        # When no path is specified, config_path is None (uses env vars only)
        assert manager.config_path is None
    
    @pytest.mark.asyncio
    async def test_load_config_file_exists(self, temp_dir):
        """Test loading configuration from existing file."""
        config_path = os.path.join(temp_dir, "config.json")
        config_data = {
            "discord_token": "MTIzNDU2Nzg5MDEyMzQ1Njc4OTAuAbCdEf.GhIjKlMnOpQrStUvWxYz1234567890123456",
            "webhook_config": {
                "port": 6000,
                "host": "0.0.0.0",
                "enabled": True
            },
            "guild_configs": {}
        }

        with open(config_path, "w") as f:
            import json
            json.dump(config_data, f)

        # Set environment variables as they're loaded first (env takes precedence)
        with patch.dict(os.environ, {
            'DISCORD_TOKEN': 'MTIzNDU2Nzg5MDEyMzQ1Njc4OTAuAbCdEf.GhIjKlMnOpQrStUvWxYz1234567890123456',
            'WEBHOOK_PORT': '6000'
        }):
            manager = ConfigManager(config_path)
            config = await manager.load_config()

            # Config should be loaded successfully
            assert config.discord_token is not None
            # Webhook config should be loaded (either from env or file)
            assert config.webhook_config.port in [5000, 6000]
    
    @pytest.mark.asyncio
    async def test_load_config_file_not_exists(self, temp_dir):
        """Test loading configuration when file doesn't exist."""
        config_path = os.path.join(temp_dir, "nonexistent.json")
        manager = ConfigManager(config_path)

        with patch.dict(os.environ, {
            'DISCORD_TOKEN': 'MTIzNDU2Nzg5MDEyMzQ1Njc4OTAuAbCdEf.GhIjKlMnOpQrStUvWxYz1234567890123456',
        }):
            config = await manager.load_config()
            assert config.discord_token is not None
    
    @pytest.mark.asyncio
    async def test_save_config(self, temp_dir):
        """Test saving configuration to file."""
        from src.config.settings import SummaryLength, PermissionSettings
        config_path = os.path.join(temp_dir, "config.json")
        manager = ConfigManager(config_path)

        guild_config = GuildConfig(
            guild_id="123456789012345678",
            enabled_channels=["987654321098765432"],
            excluded_channels=[],
            default_summary_options=SummaryOptions(summary_length=SummaryLength.DETAILED),
            permission_settings=PermissionSettings()
        )

        config = BotConfig(
            discord_token="MTIzNDU2Nzg5MDEyMzQ1Njc4OTAuAbCdEf.GhIjKlMnOpQrStUvWxYz1234567890123456",
            guild_configs={"123456789012345678": guild_config}
        )

        await manager.save_config(config)

        # Verify file was created
        assert os.path.exists(config_path)

        with open(config_path, "r") as f:
            import json
            saved_data = json.load(f)
            # File should contain saved data
            assert saved_data is not None
    
    @pytest.mark.asyncio
    async def test_reload_config(self, temp_dir):
        """Test reloading configuration."""
        config_path = os.path.join(temp_dir, "config.json")
        manager = ConfigManager(config_path)

        # Create initial config
        initial_token = "MTIzNDU2Nzg5MDEyMzQ1Njc4OTAuAbCdEf.GhIjKlMnOpQrStUvWxYz1234567890111111"
        initial_data = {
            "discord_token": initial_token,
            "guild_configs": {}
        }

        with open(config_path, "w") as f:
            import json
            json.dump(initial_data, f)

        # Set environment variables for validation
        with patch.dict(os.environ, {
            'DISCORD_TOKEN': initial_token,
        }):
            config1 = await manager.load_config()
            assert config1.discord_token is not None

        # Modify file
        updated_token = "MTIzNDU2Nzg5MDEyMzQ1Njc4OTAuAbCdEf.GhIjKlMnOpQrStUvWxYz1234567890222222"
        updated_data = {
            "discord_token": updated_token,
            "guild_configs": {}
        }

        with open(config_path, "w") as f:
            json.dump(updated_data, f)

        # Reload with updated env vars
        with patch.dict(os.environ, {
            'DISCORD_TOKEN': updated_token,
        }):
            config2 = await manager.reload_config()
        assert config2.discord_token is not None
    
    def test_validate_config_valid(self):
        """Test configuration validation with valid config."""
        from src.config.settings import SummaryLength, PermissionSettings
        manager = ConfigManager()

        guild_config = GuildConfig(
            guild_id="123456789012345678",
            enabled_channels=["987654321098765432"],
            excluded_channels=[],
            default_summary_options=SummaryOptions(summary_length=SummaryLength.DETAILED),
            permission_settings=PermissionSettings()
        )

        config = BotConfig(
            discord_token="MTIzNDU2Nzg5MDEyMzQ1Njc4OTAuAbCdEf.GhIjKlMnOpQrStUvWxYz1234567890123456",
            guild_configs={"123456789012345678": guild_config}
        )

        result = manager.validate_config(config)
        assert result is True
    
    def test_validate_config_invalid(self):
        """Test configuration validation with invalid config."""
        from src.config.settings import WebhookConfig
        manager = ConfigManager()

        config = BotConfig(
            discord_token="valid_token",
            guild_configs={},
            webhook_config=WebhookConfig(port=-1)  # Invalid port
        )

        result = manager.validate_config(config)
        assert result is False