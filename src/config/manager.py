"""
Configuration manager for handling config loading, saving, and reloading.
"""

import json
import os
import asyncio
from typing import Optional, Dict, Any
from pathlib import Path

from .settings import BotConfig, GuildConfig
from .environment import EnvironmentLoader
from .validation import ConfigValidator, ValidationError
from .constants import DEFAULT_SUMMARIZATION_MODEL


class ConfigManager:
    """Manages configuration loading, validation, and persistence."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the configuration manager.
        
        Args:
            config_path: Optional path to configuration file. If None, uses environment variables only.
        """
        self.config_path = Path(config_path) if config_path else None
        self._config: Optional[BotConfig] = None
        self._file_watcher_task: Optional[asyncio.Task] = None
        self._save_lock = asyncio.Lock()
    
    async def load_config(self) -> BotConfig:
        """Load configuration from environment and/or file."""
        # Always start with environment variables
        config = EnvironmentLoader.load_config()
        
        # If config file exists, merge with file-based settings
        if self.config_path and self.config_path.exists():
            file_config = await self._load_from_file()
            config = self._merge_configs(config, file_config)
        
        # Validate the final configuration
        errors = ConfigValidator.validate_config(config)
        if errors:
            # Log validation errors for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Configuration validation failed with {len(errors)} errors:")
            for i, error in enumerate(errors, 1):
                logger.error(f"  {i}. {error}")
            raise ValidationError("Configuration validation failed", errors)
        
        self._config = config
        return config
    
    async def save_config(self, config: BotConfig) -> None:
        """Save configuration to file if config path is set."""
        if not self.config_path:
            raise ValueError("Cannot save config: no config path specified")
        
        # Validate before saving
        errors = ConfigValidator.validate_config(config)
        if errors:
            raise ValidationError("Cannot save invalid configuration", errors)
        
        # Ensure directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert to serializable format (excluding sensitive data)
        config_dict = self._config_to_serializable_dict(config)
        
        # Write to file atomically
        temp_path = self.config_path.with_suffix('.tmp')
        try:
            async with self._save_lock:
                with open(temp_path, 'w') as f:
                    json.dump(config_dict, f, indent=2, default=str)
                temp_path.replace(self.config_path)
        except Exception:
            # Clean up temp file on error
            if temp_path.exists():
                temp_path.unlink()
            raise
        
        self._config = config
    
    async def reload_config(self) -> BotConfig:
        """Reload configuration from sources."""
        return await self.load_config()
    
    def validate_config(self, config: BotConfig) -> bool:
        """Validate configuration and return True if valid."""
        errors = ConfigValidator.validate_config(config)
        return len(errors) == 0
    
    def get_current_config(self) -> Optional[BotConfig]:
        """Get the currently loaded configuration."""
        return self._config
    
    async def update_guild_config(self, guild_id: str, guild_config: GuildConfig) -> None:
        """Update configuration for a specific guild."""
        if not self._config:
            raise ValueError("No configuration loaded")
        
        self._config.guild_configs[guild_id] = guild_config
        
        # Save if config path is specified
        if self.config_path:
            await self.save_config(self._config)
    
    async def remove_guild_config(self, guild_id: str) -> bool:
        """Remove configuration for a specific guild."""
        if not self._config:
            return False
        
        if guild_id in self._config.guild_configs:
            del self._config.guild_configs[guild_id]
            
            # Save if config path is specified
            if self.config_path:
                await self.save_config(self._config)
            
            return True
        
        return False
    
    async def start_file_watcher(self) -> None:
        """Start watching config file for changes."""
        if not self.config_path or self._file_watcher_task:
            return
        
        self._file_watcher_task = asyncio.create_task(self._watch_config_file())
    
    async def stop_file_watcher(self) -> None:
        """Stop watching config file for changes."""
        if self._file_watcher_task:
            self._file_watcher_task.cancel()
            try:
                await self._file_watcher_task
            except asyncio.CancelledError:
                pass
            self._file_watcher_task = None
    
    async def _load_from_file(self) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            raise ValueError(f"Failed to load config file {self.config_path}: {e}")
    
    def _merge_configs(self, env_config: BotConfig, file_config: Dict[str, Any]) -> BotConfig:
        """Merge environment config with file config.
        
        Environment variables take precedence over file settings.
        """
        # For now, prioritize environment config
        # File config can provide additional guild configurations
        if 'guild_configs' in file_config:
            for guild_id, guild_data in file_config['guild_configs'].items():
                if guild_id not in env_config.guild_configs:
                    # Create guild config from file data
                    guild_config = self._dict_to_guild_config(guild_id, guild_data)
                    env_config.guild_configs[guild_id] = guild_config
        
        return env_config
    
    def _dict_to_guild_config(self, guild_id: str, data: Dict[str, Any]) -> GuildConfig:
        """Convert dictionary to GuildConfig object."""
        from .settings import SummaryOptions, PermissionSettings, SummaryLength
        
        # Parse summary options
        summary_options_data = data.get('default_summary_options', {})

        # Read model: try new field name first, fall back to old for backward compatibility
        model = summary_options_data.get('summarization_model')
        if not model:
            model = summary_options_data.get('claude_model')  # Backward compatibility
        if not model:
            model = DEFAULT_SUMMARIZATION_MODEL

        summary_options = SummaryOptions(
            summary_length=SummaryLength(summary_options_data.get('summary_length', 'detailed')),
            include_bots=summary_options_data.get('include_bots', False),
            include_attachments=summary_options_data.get('include_attachments', True),
            excluded_users=summary_options_data.get('excluded_users', []),
            min_messages=summary_options_data.get('min_messages', 5),
            summarization_model=model,
            temperature=summary_options_data.get('temperature', 0.3),
            max_tokens=summary_options_data.get('max_tokens', 4000)
        )
        
        # Parse permission settings
        permission_data = data.get('permission_settings', {})
        permission_settings = PermissionSettings(
            allowed_roles=permission_data.get('allowed_roles', []),
            allowed_users=permission_data.get('allowed_users', []),
            admin_roles=permission_data.get('admin_roles', []),
            require_permissions=permission_data.get('require_permissions', True)
        )
        
        return GuildConfig(
            guild_id=guild_id,
            enabled_channels=data.get('enabled_channels', []),
            excluded_channels=data.get('excluded_channels', []),
            default_summary_options=summary_options,
            permission_settings=permission_settings,
            webhook_enabled=data.get('webhook_enabled', False),
            webhook_secret=data.get('webhook_secret'),
            cross_channel_summary_role_name=data.get('cross_channel_summary_role_name')
        )
    
    def _config_to_serializable_dict(self, config: BotConfig) -> Dict[str, Any]:
        """Convert config to dictionary suitable for JSON serialization."""
        return {
            # Don't save sensitive tokens to file
            'guild_configs': {
                guild_id: guild_config.to_dict()
                for guild_id, guild_config in config.guild_configs.items()
            },
            'webhook_config': {
                'host': config.webhook_config.host,
                'port': config.webhook_config.port,
                'enabled': config.webhook_config.enabled,
                'cors_origins': config.webhook_config.cors_origins,
                'rate_limit': config.webhook_config.rate_limit
            },
            'cache_config': {
                'backend': config.cache_config.backend,
                'default_ttl': config.cache_config.default_ttl,
                'max_size': config.cache_config.max_size
            },
            'log_level': config.log_level.value,
            'max_message_batch': config.max_message_batch,
            'cache_ttl': config.cache_ttl
        }
    
    async def _watch_config_file(self) -> None:
        """Watch config file for changes and reload when modified."""
        if not self.config_path or not self.config_path.exists():
            return
        
        last_modified = self.config_path.stat().st_mtime
        
        while True:
            try:
                await asyncio.sleep(1)  # Check every second
                
                if not self.config_path.exists():
                    continue
                
                current_modified = self.config_path.stat().st_mtime
                if current_modified > last_modified:
                    last_modified = current_modified
                    
                    try:
                        await self.reload_config()
                        # Log successful reload (would use proper logging in production)
                        print(f"Configuration reloaded from {self.config_path}")
                    except Exception as e:
                        # Log error but continue watching
                        print(f"Error reloading configuration: {e}")
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log error but continue watching
                print(f"Error in config file watcher: {e}")
                await asyncio.sleep(5)  # Wait longer after error