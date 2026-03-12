"""
Prompt configuration command handlers for Discord slash commands.
"""

import logging
from datetime import datetime
from typing import Optional
import discord
import re

from .base import BaseCommandHandler
from src.utils.time import utc_now_naive
from ..prompts import (
    PromptTemplateResolver,
    PromptContext,
    GuildPromptConfig,
    ValidationResult
)
from ..prompts.guild_config_store import GuildPromptConfigStore
from ..exceptions import UserError

logger = logging.getLogger(__name__)


class PromptConfigCommandHandler(BaseCommandHandler):
    """Handler for /prompt-config commands."""

    def __init__(
        self,
        config_store: GuildPromptConfigStore,
        resolver: PromptTemplateResolver,
        permission_manager=None,
        command_logger=None
    ):
        """
        Initialize prompt config command handler.

        Args:
            config_store: Guild prompt config repository
            resolver: Prompt template resolver
            permission_manager: Permission manager (optional)
            command_logger: Command logger for audit logging (optional)
        """
        super().__init__(None, permission_manager, command_logger=command_logger)
        self.config_store = config_store
        self.resolver = resolver

    async def _execute_command(self, interaction: discord.Interaction, **kwargs) -> None:
        """Execute command - routes to specific handlers."""
        pass

    async def handle_set(
        self,
        interaction: discord.Interaction,
        repo_url: str,
        branch: Optional[str] = None
    ) -> None:
        """
        Handle /prompt-config set command.

        Args:
            interaction: Discord interaction
            repo_url: GitHub repository URL
            branch: Git branch (defaults to main)
        """
        await self.defer_response(interaction, ephemeral=True)

        try:
            # Check permissions (admin only)
            if not interaction.user.guild_permissions.administrator:
                raise UserError(
                    message="Admin permission required",
                    error_code="PERMISSION_DENIED",
                    user_message="Only server administrators can configure custom prompts."
                )

            # Validate repository URL format
            repo_url = self._normalize_repo_url(repo_url)
            if not self._is_valid_repo_url(repo_url):
                raise UserError(
                    message=f"Invalid repo URL: {repo_url}",
                    error_code="INVALID_REPO_URL",
                    user_message="Invalid repository URL. Format: `github.com/owner/repo` or full GitHub URL"
                )

            # Create configuration
            config = GuildPromptConfig(
                guild_id=str(interaction.guild_id),
                repo_url=repo_url,
                branch=branch or "main",
                enabled=True,
                last_sync_status="pending"
            )

            # Send status message
            status_embed = discord.Embed(
                title="🔄 Testing Repository",
                description=f"Validating `{repo_url}` (branch: `{config.branch}`)...",
                color=0x4A90E2,
                timestamp=utc_now_naive()
            )
            await interaction.followup.send(embed=status_embed, ephemeral=True)

            # Test repository by trying to fetch PATH file
            from ..prompts.github_client import GitHubRepositoryClient
            github_client = GitHubRepositoryClient()

            try:
                path_file = await github_client.fetch_file(
                    repo_url=repo_url,
                    file_path="PATH",
                    branch=config.branch
                )

                if not path_file:
                    raise UserError(
                        message="PATH file not found",
                        error_code="PATH_FILE_NOT_FOUND",
                        user_message=f"Repository `{repo_url}` does not contain a `PATH` file in the root directory."
                    )

                # Validate PATH file
                from ..prompts.schema_validator import SchemaValidator
                validator = SchemaValidator()
                validation = validator.validate_path_file(path_file)

                if not validation.is_valid:
                    config.last_sync_status = "validation_failed"
                    config.validation_errors = validation.errors
                    await self.config_store.set_config(config)

                    error_list = "\n".join(f"• {err}" for err in validation.errors[:5])
                    raise UserError(
                        message="PATH file validation failed",
                        error_code="VALIDATION_FAILED",
                        user_message=f"Repository PATH file has validation errors:\n{error_list}"
                    )

                # Save configuration
                config.last_sync = utc_now_naive()
                config.last_sync_status = "success"
                await self.config_store.set_config(config)

                # Success embed
                success_embed = discord.Embed(
                    title="✅ Custom Prompts Configured",
                    description=f"Successfully configured custom prompts from `{repo_url}`",
                    color=0x2ECC71,
                    timestamp=utc_now_naive()
                )

                success_embed.add_field(
                    name="Repository",
                    value=f"`{repo_url}`",
                    inline=False
                )

                success_embed.add_field(
                    name="Branch",
                    value=f"`{config.branch}`",
                    inline=True
                )

                success_embed.add_field(
                    name="Status",
                    value="🟢 Active",
                    inline=True
                )

                success_embed.set_footer(text="Custom prompts will be used for all summaries in this server")

                await interaction.edit_original_response(embed=success_embed)

                logger.info(f"Configured custom prompts for guild {interaction.guild_id}: {repo_url}")

            except UserError:
                raise
            except Exception as e:
                logger.error(f"Failed to validate repository: {e}", exc_info=True)
                config.last_sync_status = "failed"
                config.validation_errors = [str(e)]
                await self.config_store.set_config(config)

                raise UserError(
                    message=f"Repository validation failed: {e}",
                    error_code="REPO_VALIDATION_FAILED",
                    user_message=f"Failed to access repository: {str(e)}\n\nPlease check that:\n• The repository exists and is public\n• The branch name is correct\n• The PATH file exists in the root directory"
                )

        except UserError as e:
            await self.send_error_response(interaction, e)
        except Exception as e:
            logger.exception(f"Unexpected error in prompt-config set: {e}")
            error = UserError(
                message=str(e),
                error_code="CONFIG_SET_FAILED",
                user_message="Failed to configure custom prompts. Please try again later."
            )
            await self.send_error_response(interaction, error)

    async def handle_status(self, interaction: discord.Interaction) -> None:
        """
        Handle /prompt-config status command.

        Args:
            interaction: Discord interaction
        """
        await self.defer_response(interaction, ephemeral=True)

        try:
            config = await self.config_store.get_config(str(interaction.guild_id))

            if not config or not config.repo_url:
                # No custom prompts configured
                embed = discord.Embed(
                    title="📋 Prompt Configuration Status",
                    description="This server is using the default built-in prompts.",
                    color=0x95A5A6,
                    timestamp=utc_now_naive()
                )

                embed.add_field(
                    name="Status",
                    value="🟡 Default Prompts",
                    inline=True
                )

                embed.add_field(
                    name="Custom Prompts",
                    value="Not configured",
                    inline=True
                )

                embed.set_footer(text="Use /prompt-config set to configure custom prompts")

                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Custom prompts configured
            status_emoji = "🟢" if config.enabled and config.last_sync_status == "success" else "🔴"
            status_text = "Active" if config.enabled else "Disabled"

            if config.last_sync_status == "failed":
                status_text = "Failed"
            elif config.last_sync_status == "validation_failed":
                status_text = "Validation Failed"
            elif config.last_sync_status == "pending":
                status_text = "Pending Validation"

            embed = discord.Embed(
                title="📋 Prompt Configuration Status",
                description=f"Custom prompts configured from GitHub repository",
                color=0x2ECC71 if config.enabled and config.last_sync_status == "success" else 0xE74C3C,
                timestamp=utc_now_naive()
            )

            embed.add_field(
                name="Repository",
                value=f"`{config.repo_url}`",
                inline=False
            )

            embed.add_field(
                name="Branch",
                value=f"`{config.branch}`",
                inline=True
            )

            embed.add_field(
                name="Status",
                value=f"{status_emoji} {status_text}",
                inline=True
            )

            if config.last_sync:
                embed.add_field(
                    name="Last Sync",
                    value=f"<t:{int(config.last_sync.timestamp())}:R>",
                    inline=True
                )

            if config.validation_errors:
                error_list = "\n".join(f"• {err}" for err in config.validation_errors[:3])
                if len(config.validation_errors) > 3:
                    error_list += f"\n• ...and {len(config.validation_errors) - 3} more"

                embed.add_field(
                    name="⚠️ Validation Errors",
                    value=error_list,
                    inline=False
                )

            # Cache stats
            cache_stats = self.resolver.cache_stats
            embed.add_field(
                name="Cache Stats",
                value=f"Entries: {cache_stats['total_entries']} | Fresh: {cache_stats['fresh_entries']} | Stale: {cache_stats['stale_entries']}",
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception(f"Error in prompt-config status: {e}")
            error = UserError(
                message=str(e),
                error_code="STATUS_FAILED",
                user_message="Failed to retrieve prompt configuration status."
            )
            await self.send_error_response(interaction, error)

    async def handle_remove(self, interaction: discord.Interaction) -> None:
        """
        Handle /prompt-config remove command.

        Args:
            interaction: Discord interaction
        """
        await self.defer_response(interaction, ephemeral=True)

        try:
            # Check permissions (admin only)
            if not interaction.user.guild_permissions.administrator:
                raise UserError(
                    message="Admin permission required",
                    error_code="PERMISSION_DENIED",
                    user_message="Only server administrators can remove custom prompt configuration."
                )

            # Delete configuration
            deleted = await self.config_store.delete_config(str(interaction.guild_id))

            if not deleted:
                embed = discord.Embed(
                    title="ℹ️ No Configuration Found",
                    description="This server doesn't have custom prompts configured.",
                    color=0x95A5A6
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Invalidate cache
            await self.resolver.invalidate_guild_cache(str(interaction.guild_id))

            # Success embed
            embed = discord.Embed(
                title="✅ Custom Prompts Removed",
                description="Custom prompt configuration has been removed. This server will now use default prompts.",
                color=0x2ECC71,
                timestamp=utc_now_naive()
            )

            embed.set_footer(text="You can reconfigure custom prompts anytime with /prompt-config set")

            await interaction.followup.send(embed=embed, ephemeral=True)

            logger.info(f"Removed custom prompts for guild {interaction.guild_id}")

        except UserError as e:
            await self.send_error_response(interaction, e)
        except Exception as e:
            logger.exception(f"Error in prompt-config remove: {e}")
            error = UserError(
                message=str(e),
                error_code="REMOVE_FAILED",
                user_message="Failed to remove custom prompt configuration."
            )
            await self.send_error_response(interaction, error)

    async def handle_refresh(self, interaction: discord.Interaction) -> None:
        """
        Handle /prompt-config refresh command.

        Args:
            interaction: Discord interaction
        """
        await self.defer_response(interaction, ephemeral=True)

        try:
            # Check permissions (admin only)
            if not interaction.user.guild_permissions.administrator:
                raise UserError(
                    message="Admin permission required",
                    error_code="PERMISSION_DENIED",
                    user_message="Only server administrators can refresh prompt cache."
                )

            # Invalidate cache
            invalidated = await self.resolver.invalidate_guild_cache(str(interaction.guild_id))

            embed = discord.Embed(
                title="✅ Cache Refreshed",
                description=f"Invalidated {invalidated} cached prompt(s). Fresh prompts will be fetched on next summary.",
                color=0x2ECC71,
                timestamp=utc_now_naive()
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

            logger.info(f"Refreshed prompt cache for guild {interaction.guild_id}: {invalidated} entries")

        except Exception as e:
            logger.exception(f"Error in prompt-config refresh: {e}")
            error = UserError(
                message=str(e),
                error_code="REFRESH_FAILED",
                user_message="Failed to refresh prompt cache."
            )
            await self.send_error_response(interaction, error)

    async def handle_test(
        self,
        interaction: discord.Interaction,
        category: str = "discussion"
    ) -> None:
        """
        Handle /prompt-config test command.

        Args:
            interaction: Discord interaction
            category: Prompt category to test (meeting, discussion, moderation)
        """
        await self.defer_response(interaction, ephemeral=True)

        try:
            # Create test context
            context = PromptContext(
                guild_id=str(interaction.guild_id),
                channel_name=interaction.channel.name,
                category=category,
                summary_type="detailed",
                message_count=100
            )

            # Resolve prompt
            resolved = await self.resolver.resolve_prompt(
                guild_id=str(interaction.guild_id),
                context=context
            )

            # Create result embed
            source_emoji = {
                "custom": "🌐",
                "cached": "💾",
                "default": "📦",
                "fallback": "⚠️"
            }

            embed = discord.Embed(
                title="🧪 Prompt Test Results",
                description=f"Test prompt resolution for category: `{category}`",
                color=0x3498DB,
                timestamp=utc_now_naive()
            )

            embed.add_field(
                name="Source",
                value=f"{source_emoji.get(resolved.source.value, '❓')} {resolved.source.value.title()}",
                inline=True
            )

            embed.add_field(
                name="Version",
                value=f"`{resolved.version}`",
                inline=True
            )

            if resolved.is_stale:
                embed.add_field(
                    name="Cache Status",
                    value="⚠️ Stale (using cached fallback)",
                    inline=True
                )

            if resolved.repo_url:
                embed.add_field(
                    name="Repository",
                    value=f"`{resolved.repo_url}`",
                    inline=False
                )

            # Show prompt preview (first 500 chars)
            preview = resolved.content[:500]
            if len(resolved.content) > 500:
                preview += "..."

            embed.add_field(
                name="Prompt Preview",
                value=f"```\n{preview}\n```",
                inline=False
            )

            embed.add_field(
                name="Variables Substituted",
                value=f"{len(resolved.variables)} variable(s)",
                inline=True
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception(f"Error in prompt-config test: {e}")
            error = UserError(
                message=str(e),
                error_code="TEST_FAILED",
                user_message=f"Failed to test prompt resolution: {str(e)}"
            )
            await self.send_error_response(interaction, error)

    def _normalize_repo_url(self, repo_url: str) -> str:
        """
        Normalize repository URL to github.com/owner/repo format.

        Args:
            repo_url: Input URL (various formats accepted)

        Returns:
            Normalized URL
        """
        # Remove trailing slashes
        repo_url = repo_url.rstrip('/')

        # Extract owner/repo from various formats
        if repo_url.startswith('https://github.com/'):
            repo_url = repo_url.replace('https://github.com/', 'github.com/')
        elif repo_url.startswith('http://github.com/'):
            repo_url = repo_url.replace('http://github.com/', 'github.com/')
        elif not repo_url.startswith('github.com/'):
            # Assume it's just owner/repo
            if '/' in repo_url and not repo_url.startswith('github.com'):
                repo_url = f'github.com/{repo_url}'

        return repo_url

    def _is_valid_repo_url(self, repo_url: str) -> bool:
        """
        Validate repository URL format.

        Args:
            repo_url: Repository URL

        Returns:
            True if valid
        """
        # Should match: github.com/owner/repo
        pattern = r'^github\.com/[\w\-\.]+/[\w\-\.]+$'
        return bool(re.match(pattern, repo_url))
