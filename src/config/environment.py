"""
Environment variable handling for Summary Bot NG configuration.
"""

import os
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
from .settings import (
    BotConfig, GuildConfig, SummaryOptions, PermissionSettings,
    DatabaseConfig, CacheConfig, WebhookConfig, LogLevel, SummaryLength
)
from .constants import DEFAULT_SUMMARIZATION_MODEL


class EnvironmentLoader:
    """Loads configuration from environment variables."""
    
    @staticmethod
    def load_config() -> BotConfig:
        """Load configuration from environment variables."""
        # Load .env file if it exists (override=True to prefer .env over shell env)
        load_dotenv(override=True)

        # Discord token - optional for webhook-only mode
        # When not set, bot runs in webhook-only mode (dashboard still works)
        discord_token = os.getenv('DISCORD_TOKEN', '')
        # Claude API key not needed - bot always uses OpenRouter
        
        # Database configuration
        database_config = None
        database_url = os.getenv('DATABASE_URL')
        if database_url:
            database_config = DatabaseConfig(
                url=database_url,
                pool_size=int(os.getenv('DB_POOL_SIZE', '10')),
                max_overflow=int(os.getenv('DB_MAX_OVERFLOW', '20')),
                pool_timeout=int(os.getenv('DB_POOL_TIMEOUT', '30')),
                pool_recycle=int(os.getenv('DB_POOL_RECYCLE', '3600')),
                echo=os.getenv('DB_ECHO', 'false').lower() == 'true'
            )
        
        # Cache configuration
        cache_config = CacheConfig(
            backend=os.getenv('CACHE_BACKEND', 'memory'),
            redis_url=os.getenv('REDIS_URL'),
            default_ttl=int(os.getenv('CACHE_DEFAULT_TTL', '3600')),
            max_size=int(os.getenv('CACHE_MAX_SIZE', '1000'))
        )
        
        # Webhook configuration
        webhook_config = WebhookConfig(
            host=os.getenv('WEBHOOK_HOST', '0.0.0.0'),
            port=int(os.getenv('WEBHOOK_PORT', '5000')),
            enabled=os.getenv('WEBHOOK_ENABLED', 'true').lower() == 'true',
            cors_origins=EnvironmentLoader._parse_list(os.getenv('WEBHOOK_CORS_ORIGINS', '')),
            rate_limit=int(os.getenv('WEBHOOK_RATE_LIMIT', '100'))
        )
        
        # Log level
        log_level_str = os.getenv('LOG_LEVEL', 'INFO').upper()
        log_level = LogLevel.INFO  # default
        try:
            log_level = LogLevel(log_level_str)
        except ValueError:
            pass  # Use default
        
        # Guild configurations (loaded from environment if present)
        guild_configs = EnvironmentLoader._load_guild_configs_from_env()
        
        return BotConfig(
            discord_token=discord_token,
            guild_configs=guild_configs,
            webhook_config=webhook_config,
            database_config=database_config,
            cache_config=cache_config,
            log_level=log_level,
            max_message_batch=int(os.getenv('MAX_MESSAGE_BATCH', '10000')),
            cache_ttl=int(os.getenv('CACHE_TTL', '3600'))
        )
    
    @staticmethod
    def _get_required_env(key: str) -> str:
        """Get a required environment variable or raise an error."""
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Required environment variable {key} is not set")
        return value
    
    @staticmethod
    def _parse_list(value: str, delimiter: str = ',') -> List[str]:
        """Parse a comma-separated string into a list."""
        if not value:
            return []
        return [item.strip() for item in value.split(delimiter) if item.strip()]
    
    @staticmethod
    def _load_guild_configs_from_env() -> Dict[str, GuildConfig]:
        """Load guild configurations from environment variables."""
        guild_configs = {}
        
        # Look for guild-specific environment variables
        # Format: GUILD_{GUILD_ID}_{SETTING}
        guild_ids = set()
        for key in os.environ:
            if key.startswith('GUILD_') and key.count('_') >= 2:
                parts = key.split('_', 2)
                if len(parts) >= 2:
                    guild_ids.add(parts[1])
        
        for guild_id in guild_ids:
            guild_config = EnvironmentLoader._load_single_guild_config(guild_id)
            if guild_config:
                guild_configs[guild_id] = guild_config
        
        return guild_configs
    
    @staticmethod
    def _load_single_guild_config(guild_id: str) -> Optional[GuildConfig]:
        """Load configuration for a single guild from environment variables."""
        prefix = f'GUILD_{guild_id}_'
        
        # Check if any settings exist for this guild
        guild_env_vars = {k: v for k, v in os.environ.items() if k.startswith(prefix)}
        if not guild_env_vars:
            return None
        
        # Load basic settings
        enabled_channels = EnvironmentLoader._parse_list(
            os.getenv(f'{prefix}ENABLED_CHANNELS', '')
        )
        excluded_channels = EnvironmentLoader._parse_list(
            os.getenv(f'{prefix}EXCLUDED_CHANNELS', '')
        )
        
        # Load summary options
        summary_length_str = os.getenv(f'{prefix}DEFAULT_SUMMARY_LENGTH', 'detailed')
        summary_length = SummaryLength.DETAILED  # default
        try:
            summary_length = SummaryLength(summary_length_str.lower())
        except ValueError:
            pass  # Use default
        
        # Read model from environment (try new name first, fall back to legacy)
        model = os.getenv(f'{prefix}MODEL')  # Try new SUMMARY_MODEL or SUMMARIZATION_MODEL
        if not model:
            model = os.getenv(f'{prefix}CLAUDE_MODEL')  # Legacy fallback
        if not model:
            model = DEFAULT_SUMMARIZATION_MODEL

        default_summary_options = SummaryOptions(
            summary_length=summary_length,
            include_bots=os.getenv(f'{prefix}INCLUDE_BOTS', 'false').lower() == 'true',
            include_attachments=os.getenv(f'{prefix}INCLUDE_ATTACHMENTS', 'true').lower() == 'true',
            excluded_users=EnvironmentLoader._parse_list(os.getenv(f'{prefix}EXCLUDED_USERS', '')),
            min_messages=int(os.getenv(f'{prefix}MIN_MESSAGES', '5')),
            summarization_model=model,
            temperature=float(os.getenv(f'{prefix}TEMPERATURE', '0.3')),
            max_tokens=int(os.getenv(f'{prefix}MAX_TOKENS', '4000'))
        )
        
        # Load permission settings
        permission_settings = PermissionSettings(
            allowed_roles=EnvironmentLoader._parse_list(os.getenv(f'{prefix}ALLOWED_ROLES', '')),
            allowed_users=EnvironmentLoader._parse_list(os.getenv(f'{prefix}ALLOWED_USERS', '')),
            admin_roles=EnvironmentLoader._parse_list(os.getenv(f'{prefix}ADMIN_ROLES', '')),
            require_permissions=os.getenv(f'{prefix}REQUIRE_PERMISSIONS', 'true').lower() == 'true'
        )
        
        # Load webhook settings
        webhook_enabled = os.getenv(f'{prefix}WEBHOOK_ENABLED', 'false').lower() == 'true'
        webhook_secret = os.getenv(f'{prefix}WEBHOOK_SECRET')
        
        return GuildConfig(
            guild_id=guild_id,
            enabled_channels=enabled_channels,
            excluded_channels=excluded_channels,
            default_summary_options=default_summary_options,
            permission_settings=permission_settings,
            webhook_enabled=webhook_enabled,
            webhook_secret=webhook_secret
        )