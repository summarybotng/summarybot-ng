"""
Configuration validation for Summary Bot NG.
"""

from typing import List, Set
import re
from .settings import BotConfig, GuildConfig, SummaryOptions
from .constants import VALID_MODELS


class ConfigValidator:
    """Validates configuration settings."""
    
    @staticmethod
    def validate_config(config: BotConfig) -> List[str]:
        """Validate the entire bot configuration."""
        errors = []
        
        # Validate required fields
        errors.extend(ConfigValidator._validate_required_fields(config))
        
        # Validate Discord token format
        errors.extend(ConfigValidator._validate_discord_token(config.discord_token))

        # Claude API key validation removed - bot always uses OpenRouter

        # Validate webhook configuration
        errors.extend(ConfigValidator._validate_webhook_config(config))
        
        # Validate cache configuration
        errors.extend(ConfigValidator._validate_cache_config(config))
        
        # Validate each guild configuration
        for guild_id, guild_config in config.guild_configs.items():
            errors.extend(ConfigValidator._validate_guild_config(guild_config, guild_id))
        
        # Validate numeric ranges
        errors.extend(ConfigValidator._validate_numeric_ranges(config))
        
        return errors
    
    @staticmethod
    def _validate_required_fields(config: BotConfig) -> List[str]:
        """Validate required configuration fields."""
        errors = []

        # Discord token is optional - app can run in webhook-only mode
        # When not set, bot features are disabled but dashboard API still works

        # Claude API key not needed - bot always uses OpenRouter

        return errors
    
    @staticmethod
    def _validate_discord_token(token: str) -> List[str]:
        """Validate Discord token format."""
        errors = []
        
        if not token:
            return errors  # Already handled in required fields
        
        # Discord bot tokens should be at least 24 characters
        if len(token) < 24:
            errors.append("Discord token appears to be too short")
        
        # Discord tokens typically contain only alphanumeric characters, dots, and underscores
        if not re.match(r'^[A-Za-z0-9._-]+$', token):
            errors.append("Discord token contains invalid characters")
        
        return errors
    
    @staticmethod
    def _validate_claude_api_key(api_key: str) -> List[str]:
        """Validate Claude API key format."""
        errors = []
        
        if not api_key:
            return errors  # Already handled in required fields
        
        # Claude API keys typically start with 'sk-ant-'
        if not api_key.startswith('sk-ant-'):
            errors.append("Claude API key should start with 'sk-ant-'")
        
        # Should be at least 40 characters
        if len(api_key) < 40:
            errors.append("Claude API key appears to be too short")
        
        return errors
    
    @staticmethod
    def _validate_webhook_config(config: BotConfig) -> List[str]:
        """Validate webhook configuration."""
        errors = []
        
        webhook_config = config.webhook_config
        
        # Validate port range
        if not (1 <= webhook_config.port <= 65535):
            errors.append(f"Webhook port {webhook_config.port} is not in valid range (1-65535)")
        
        # Validate rate limit
        if webhook_config.rate_limit <= 0:
            errors.append("Webhook rate limit must be positive")
        
        # Validate CORS origins format
        for origin in webhook_config.cors_origins:
            if not ConfigValidator._is_valid_url_or_wildcard(origin):
                errors.append(f"Invalid CORS origin: {origin}")
        
        return errors
    
    @staticmethod
    def _validate_cache_config(config: BotConfig) -> List[str]:
        """Validate cache configuration."""
        errors = []
        
        cache_config = config.cache_config
        
        # Validate backend type
        if cache_config.backend not in ['memory', 'redis']:
            errors.append(f"Invalid cache backend: {cache_config.backend}")
        
        # If Redis backend is selected, validate Redis URL
        if cache_config.backend == 'redis' and not cache_config.redis_url:
            errors.append("Redis URL is required when using Redis cache backend")
        
        # Validate TTL
        if cache_config.default_ttl <= 0:
            errors.append("Cache default TTL must be positive")
        
        # Validate max size for memory cache
        if cache_config.backend == 'memory' and cache_config.max_size <= 0:
            errors.append("Cache max size must be positive")
        
        return errors
    
    @staticmethod
    def _validate_guild_config(guild_config: GuildConfig, guild_id: str) -> List[str]:
        """Validate a single guild configuration."""
        errors = []
        
        # Validate guild ID format (should be numeric)
        if not guild_id.isdigit():
            errors.append(f"Invalid guild ID format: {guild_id}")
        
        # Validate channel IDs (should be numeric)
        for channel_id in guild_config.enabled_channels:
            if not channel_id.isdigit():
                errors.append(f"Invalid enabled channel ID: {channel_id}")
        
        for channel_id in guild_config.excluded_channels:
            if not channel_id.isdigit():
                errors.append(f"Invalid excluded channel ID: {channel_id}")
        
        # Check for channel conflicts
        enabled_set = set(guild_config.enabled_channels)
        excluded_set = set(guild_config.excluded_channels)
        conflicts = enabled_set.intersection(excluded_set)
        if conflicts:
            errors.append(f"Channels cannot be both enabled and excluded: {', '.join(conflicts)}")
        
        # Validate summary options
        errors.extend(ConfigValidator._validate_summary_options(guild_config.default_summary_options))
        
        # Validate user IDs in excluded users and permission settings
        for user_id in guild_config.default_summary_options.excluded_users:
            if not user_id.isdigit():
                errors.append(f"Invalid excluded user ID: {user_id}")

        # Handle permission_settings as either dict or PermissionSettings object
        if hasattr(guild_config.permission_settings, 'allowed_users'):
            for user_id in guild_config.permission_settings.allowed_users:
                if not user_id.isdigit():
                    errors.append(f"Invalid allowed user ID: {user_id}")
        elif isinstance(guild_config.permission_settings, dict):
            for user_id in guild_config.permission_settings.get('allowed_users', []):
                if not user_id.isdigit():
                    errors.append(f"Invalid allowed user ID: {user_id}")

        return errors
    
    @staticmethod
    def _validate_summary_options(options: SummaryOptions) -> List[str]:
        """Validate summary options."""
        errors = []
        
        # Validate min_messages
        if options.min_messages < 1:
            errors.append("Minimum messages must be at least 1")
        
        # Validate temperature range
        if not (0.0 <= options.temperature <= 2.0):
            errors.append(f"Temperature {options.temperature} must be between 0.0 and 2.0")
        
        # Validate max_tokens
        if options.max_tokens < 100:
            errors.append("Max tokens must be at least 100")
        if options.max_tokens > 200000:
            errors.append("Max tokens cannot exceed 200,000")
        
        # Validate model name
        if options.summarization_model not in VALID_MODELS:
            errors.append(f"Unknown model: {options.summarization_model}. Valid models: {', '.join(VALID_MODELS)}")
        
        return errors
    
    @staticmethod
    def _validate_numeric_ranges(config: BotConfig) -> List[str]:
        """Validate numeric configuration values."""
        errors = []
        
        # Validate max_message_batch
        if config.max_message_batch < 1:
            errors.append("Max message batch must be at least 1")
        if config.max_message_batch > 50000:
            errors.append("Max message batch cannot exceed 50,000")
        
        # Validate cache_ttl
        if config.cache_ttl <= 0:
            errors.append("Cache TTL must be positive")
        
        return errors
    
    @staticmethod
    def _is_valid_url_or_wildcard(origin: str) -> bool:
        """Check if a CORS origin is a valid URL or wildcard."""
        if origin == '*':
            return True
        
        # Basic URL validation
        url_pattern = r'^https?://[a-zA-Z0-9.-]+(?::[0-9]+)?(?:/.*)?$'
        return bool(re.match(url_pattern, origin))


class ValidationError(Exception):
    """Exception raised for configuration validation errors."""
    
    def __init__(self, message: str, errors: List[str]):
        super().__init__(message)
        self.errors = errors