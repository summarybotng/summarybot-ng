"""
Command registration and management for Discord slash commands.
"""

import logging
from typing import Optional, TYPE_CHECKING
import discord
from discord import app_commands

if TYPE_CHECKING:
    from .bot import SummaryBot

logger = logging.getLogger(__name__)


class CommandRegistry:
    """Manages Discord slash command registration and setup."""

    def __init__(self, bot: 'SummaryBot'):
        """
        Initialize the command registry.

        Args:
            bot: The SummaryBot instance
        """
        self.bot = bot
        self.tree = bot.client.tree
        self.command_handlers = {}  # Store command handler instances

    async def setup_commands(self) -> None:
        """
        Set up all slash commands for the bot.

        This method registers all command handlers with the command tree.
        """
        logger.info("Setting up slash commands...")

        # Register /summarize command
        @self.tree.command(
            name="summarize",
            description="Create an AI-powered summary of recent channel messages"
        )
        @discord.app_commands.describe(
            messages="Number of messages to summarize (default: 100)",
            hours="Summarize messages from the last N hours",
            minutes="Summarize messages from the last N minutes",
            length="Summary length (default: detailed)",
            perspective="Perspective/audience for the summary (default: general)",
            channel="Single channel to summarize (mutually exclusive with category)",
            category="Category to summarize all channels from (mutually exclusive with channel)",
            mode="For category: 'combined' (one summary) or 'individual' (per-channel summaries)",
            exclude_channels="Comma-separated channel IDs or mentions to exclude from category"
        )
        @discord.app_commands.choices(
            length=[
                discord.app_commands.Choice(name="Brief", value="brief"),
                discord.app_commands.Choice(name="Detailed (default)", value="detailed"),
                discord.app_commands.Choice(name="Comprehensive", value="comprehensive")
            ],
            perspective=[
                discord.app_commands.Choice(name="General (default)", value="general"),
                discord.app_commands.Choice(name="Developer/Technical", value="developer"),
                discord.app_commands.Choice(name="Marketing/Brand", value="marketing"),
                discord.app_commands.Choice(name="Product Manager", value="product"),
                discord.app_commands.Choice(name="Finance/Business", value="finance"),
                discord.app_commands.Choice(name="Executive/Leadership", value="executive"),
                discord.app_commands.Choice(name="Support/Customer Success", value="support")
            ]
        )
        async def summarize_command(
            interaction: discord.Interaction,
            messages: Optional[int] = None,
            hours: Optional[int] = None,
            minutes: Optional[int] = None,
            length: Optional[str] = "detailed",
            perspective: Optional[str] = "general",
            channel: Optional[discord.TextChannel] = None,
            category: Optional[discord.CategoryChannel] = None,
            mode: Optional[str] = "combined",
            exclude_channels: Optional[str] = None
        ):
            """Summarize recent channel messages."""
            logger.info(f"🎯 SUMMARIZE COMMAND CALLED: user={interaction.user}, guild={interaction.guild_id}, channel={interaction.channel_id}, target_channel={channel.id if channel else 'current'}, category={category.id if category else None}, mode={mode}, messages={messages}, hours={hours}, minutes={minutes}, length={length}, perspective={perspective}")

            # Validate mutual exclusivity
            if channel and category:
                await interaction.response.send_message(
                    "❌ Please specify either a channel OR a category, not both.",
                    ephemeral=True
                )
                return

            # Defer response since summarization takes time
            await interaction.response.defer(ephemeral=False)

            try:
                # Get the command handler from bot services
                handler = self.bot.services.get('summarize_handler')
                if not handler:
                    await interaction.followup.send(
                        "❌ Summarization service is not available",
                        ephemeral=True
                    )
                    return

                # Call the handler's method
                await handler.handle_summarize_interaction(
                    interaction,
                    messages=messages,
                    hours=hours,
                    minutes=minutes,
                    length=length,
                    perspective=perspective,
                    channel=channel,
                    category=category,
                    mode=mode,
                    exclude_channels=exclude_channels
                )

            except Exception as e:
                logger.error(f"Error in summarize command: {e}", exc_info=True)
                try:
                    await interaction.followup.send(
                        f"❌ An error occurred: {str(e)}",
                        ephemeral=True
                    )
                except Exception as followup_error:
                    # SEC-005: Log the error instead of silently swallowing
                    logger.warning(f"Failed to send error followup: {followup_error}")

        # Register /schedule command group
        schedule_group = discord.app_commands.Group(
            name="schedule",
            description="Manage scheduled summaries"
        )

        @schedule_group.command(
            name="list",
            description="List all scheduled summaries for this server"
        )
        async def schedule_list_command(interaction: discord.Interaction):
            """List scheduled summaries."""
            handler = self.bot.services.get('schedule_handler')
            if not handler:
                await interaction.response.send_message(
                    "❌ Scheduling feature is not available",
                    ephemeral=True
                )
                return

            await handler.handle_schedule_list(interaction)

        @schedule_group.command(
            name="create",
            description="Create a new scheduled summary"
        )
        @discord.app_commands.describe(
            channel="Primary channel to summarize",
            frequency="How often to generate summaries (daily, weekly, half-weekly, monthly)",
            time="Time to generate summary (HH:MM format, UTC)",
            length="Summary length (brief, detailed, comprehensive)",
            days="Days for half-weekly schedule (e.g., 'mon,wed,fri' or 'tue,thu,sat')",
            additional_channels="Additional channels for cross-channel summary (comma-separated IDs or #mentions)"
        )
        async def schedule_create_command(
            interaction: discord.Interaction,
            channel: discord.TextChannel,
            frequency: str,
            time: Optional[str] = None,
            length: str = "detailed",
            days: Optional[str] = None,
            additional_channels: Optional[str] = None
        ):
            """Create a scheduled summary."""
            handler = self.bot.services.get('schedule_handler')
            if not handler:
                await interaction.response.send_message(
                    "❌ Scheduling feature is not available",
                    ephemeral=True
                )
                return

            await handler.handle_schedule_create(
                interaction,
                channel=channel,
                frequency=frequency,
                time_of_day=time,
                length=length,
                days=days,
                additional_channels=additional_channels
            )

        @schedule_group.command(
            name="delete",
            description="Delete a scheduled summary"
        )
        @discord.app_commands.describe(
            task_id="ID of the scheduled task to delete"
        )
        async def schedule_delete_command(
            interaction: discord.Interaction,
            task_id: str
        ):
            """Delete a scheduled summary."""
            handler = self.bot.services.get('schedule_handler')
            if not handler:
                await interaction.response.send_message(
                    "❌ Scheduling feature is not available",
                    ephemeral=True
                )
                return

            await handler.handle_schedule_delete(interaction, task_id=task_id)

        @schedule_group.command(
            name="pause",
            description="Pause a scheduled summary"
        )
        @discord.app_commands.describe(
            task_id="ID of the scheduled task to pause"
        )
        async def schedule_pause_command(
            interaction: discord.Interaction,
            task_id: str
        ):
            """Pause a scheduled summary."""
            handler = self.bot.services.get('schedule_handler')
            if not handler:
                await interaction.response.send_message(
                    "❌ Scheduling feature is not available",
                    ephemeral=True
                )
                return

            await handler.handle_schedule_pause(interaction, task_id=task_id)

        @schedule_group.command(
            name="resume",
            description="Resume a paused scheduled summary"
        )
        @discord.app_commands.describe(
            task_id="ID of the scheduled task to resume"
        )
        async def schedule_resume_command(
            interaction: discord.Interaction,
            task_id: str
        ):
            """Resume a scheduled summary."""
            handler = self.bot.services.get('schedule_handler')
            if not handler:
                await interaction.response.send_message(
                    "❌ Scheduling feature is not available",
                    ephemeral=True
                )
                return

            await handler.handle_schedule_resume(interaction, task_id=task_id)

        # Add the schedule command group to the tree
        self.tree.add_command(schedule_group)

        # Register /prompt-config command group
        prompt_config_group = discord.app_commands.Group(
            name="prompt-config",
            description="Manage custom prompt configurations"
        )

        @prompt_config_group.command(
            name="set",
            description="Configure custom prompts from a GitHub repository"
        )
        @discord.app_commands.describe(
            repo_url="GitHub repository URL (e.g., github.com/owner/repo)",
            branch="Git branch (defaults to main)"
        )
        async def prompt_config_set_command(
            interaction: discord.Interaction,
            repo_url: str,
            branch: Optional[str] = None
        ):
            """Configure custom prompts."""
            handler = self.bot.services.get('prompt_config_handler')
            if not handler:
                await interaction.response.send_message(
                    "❌ Prompt configuration feature is not available",
                    ephemeral=True
                )
                return

            await handler.handle_set(interaction, repo_url=repo_url, branch=branch)

        @prompt_config_group.command(
            name="status",
            description="Show current prompt configuration status"
        )
        async def prompt_config_status_command(interaction: discord.Interaction):
            """Show prompt configuration status."""
            handler = self.bot.services.get('prompt_config_handler')
            if not handler:
                await interaction.response.send_message(
                    "❌ Prompt configuration feature is not available",
                    ephemeral=True
                )
                return

            await handler.handle_status(interaction)

        @prompt_config_group.command(
            name="remove",
            description="Remove custom prompt configuration"
        )
        async def prompt_config_remove_command(interaction: discord.Interaction):
            """Remove custom prompts."""
            handler = self.bot.services.get('prompt_config_handler')
            if not handler:
                await interaction.response.send_message(
                    "❌ Prompt configuration feature is not available",
                    ephemeral=True
                )
                return

            await handler.handle_remove(interaction)

        @prompt_config_group.command(
            name="refresh",
            description="Refresh prompt cache and fetch fresh prompts"
        )
        async def prompt_config_refresh_command(interaction: discord.Interaction):
            """Refresh prompt cache."""
            handler = self.bot.services.get('prompt_config_handler')
            if not handler:
                await interaction.response.send_message(
                    "❌ Prompt configuration feature is not available",
                    ephemeral=True
                )
                return

            await handler.handle_refresh(interaction)

        @prompt_config_group.command(
            name="test",
            description="Test prompt resolution for a category"
        )
        @discord.app_commands.describe(
            category="Prompt category to test (meeting, discussion, moderation)"
        )
        async def prompt_config_test_command(
            interaction: discord.Interaction,
            category: str = "discussion"
        ):
            """Test prompt resolution."""
            handler = self.bot.services.get('prompt_config_handler')
            if not handler:
                await interaction.response.send_message(
                    "❌ Prompt configuration feature is not available",
                    ephemeral=True
                )
                return

            await handler.handle_test(interaction, category=category)

        # Add the prompt-config command group to the tree
        self.tree.add_command(prompt_config_group)

        # Register /config command group
        config_group = discord.app_commands.Group(
            name="config",
            description="Manage server configuration"
        )

        @config_group.command(
            name="view",
            description="View current server configuration"
        )
        async def config_view_command(interaction: discord.Interaction):
            """View configuration."""
            handler = self.bot.services.get('config_handler')
            if not handler:
                await interaction.response.send_message(
                    "❌ Configuration feature is not available",
                    ephemeral=True
                )
                return

            await handler.handle_config_view(interaction)

        @config_group.command(
            name="set-cross-channel-role",
            description="Set the role allowed to use cross-channel summaries"
        )
        @discord.app_commands.describe(
            role_name="Name of the Discord role (leave empty to disable feature)"
        )
        async def config_set_cross_channel_role_command(
            interaction: discord.Interaction,
            role_name: Optional[str] = None
        ):
            """Set cross-channel summary role."""
            handler = self.bot.services.get('config_handler')
            if not handler:
                await interaction.response.send_message(
                    "❌ Configuration feature is not available",
                    ephemeral=True
                )
                return

            await handler.handle_config_set_cross_channel_role(interaction, role_name=role_name)

        @config_group.command(
            name="permissions",
            description="Configure permission requirements for bot commands"
        )
        @discord.app_commands.describe(
            require="Require permissions to use commands (false = everyone can use)"
        )
        async def config_permissions_command(
            interaction: discord.Interaction,
            require: bool
        ):
            """Configure permission requirements."""
            handler = self.bot.services.get('config_handler')
            if not handler:
                await interaction.response.send_message(
                    "❌ Configuration feature is not available",
                    ephemeral=True
                )
                return

            await handler.handle_config_permissions(interaction, require=require)

        @config_group.command(
            name="reset",
            description="Reset all server configuration to defaults"
        )
        async def config_reset_command(interaction: discord.Interaction):
            """Reset configuration."""
            handler = self.bot.services.get('config_handler')
            if not handler:
                await interaction.response.send_message(
                    "❌ Configuration feature is not available",
                    ephemeral=True
                )
                return

            await handler.handle_config_reset(interaction)

        # Add the config command group to the tree
        self.tree.add_command(config_group)

        # Register help command
        @self.tree.command(
            name="help",
            description="Show help information about the bot and its commands"
        )
        async def help_command(interaction: discord.Interaction):
            """Display help information."""
            embed = discord.Embed(
                title="Summary Bot NG - Help",
                description="AI-powered conversation summarization for Discord",
                color=0x4A90E2
            )

            embed.add_field(
                name="/summarize",
                value=(
                    "Create a summary of recent channel messages\n"
                    "• Use `channel` parameter to summarize other channels (requires configured role)\n"
                    "• Brief summaries automatically use faster Haiku model for 12x cost savings"
                ),
                inline=False
            )

            embed.add_field(
                name="/schedule",
                value="Manage scheduled summaries (list, create, delete, pause, resume)",
                inline=False
            )

            embed.add_field(
                name="/prompt-config",
                value="Configure custom prompts from GitHub repositories (set, status, remove, refresh, test)",
                inline=False
            )

            embed.add_field(
                name="/config",
                value="Manage server configuration (view, set-cross-channel-role, reset)",
                inline=False
            )

            embed.add_field(
                name="/status",
                value="Check the bot's current status and health",
                inline=False
            )

            embed.add_field(
                name="/ping",
                value="Check the bot's response time",
                inline=False
            )

            embed.add_field(
                name="/about",
                value="Information about Summary Bot NG",
                inline=False
            )

            embed.set_footer(text="For detailed documentation, visit the project repository")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        # Register about command
        @self.tree.command(
            name="about",
            description="Information about Summary Bot NG"
        )
        async def about_command(interaction: discord.Interaction):
            """Display information about the bot."""
            embed = discord.Embed(
                title="About Summary Bot NG",
                description=(
                    "An advanced Discord bot that uses Claude AI to create "
                    "intelligent summaries of channel conversations.\n\n"
                    "**Features:**\n"
                    "• AI-powered conversation summarization\n"
                    "• Action item extraction\n"
                    "• Technical term definitions\n"
                    "• Participant analysis\n"
                    "• Scheduled summaries\n"
                    "• Webhook integration\n"
                ),
                color=0x4A90E2
            )

            embed.add_field(
                name="Version",
                value="1.0.0",
                inline=True
            )

            embed.add_field(
                name="Powered by",
                value="Anthropic Claude",
                inline=True
            )

            embed.add_field(
                name="Servers",
                value=str(len(self.bot.client.guilds)),
                inline=True
            )

            embed.set_footer(text="Summary Bot NG - Open Source Project")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        # Register status command
        @self.tree.command(
            name="status",
            description="Check the bot's current status and health"
        )
        async def status_command(interaction: discord.Interaction):
            """Display bot status information."""
            embed = discord.Embed(
                title="Bot Status",
                color=0x2ECC71  # Green
            )

            # Bot status
            embed.add_field(
                name="Status",
                value="🟢 Online",
                inline=True
            )

            # Latency
            latency_ms = round(self.bot.client.latency * 1000)
            latency_emoji = "🟢" if latency_ms < 100 else "🟡" if latency_ms < 300 else "🔴"
            embed.add_field(
                name="Latency",
                value=f"{latency_emoji} {latency_ms}ms",
                inline=True
            )

            # Guild count
            embed.add_field(
                name="Servers",
                value=str(len(self.bot.client.guilds)),
                inline=True
            )

            # TODO: Add more status information when other services are available
            # - Claude API status
            # - Database connection status
            # - Cache status

            embed.set_footer(text="All systems operational")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        # Register ping command
        @self.tree.command(
            name="ping",
            description="Check the bot's response time"
        )
        async def ping_command(interaction: discord.Interaction):
            """Display bot latency."""
            latency_ms = round(self.bot.client.latency * 1000)

            embed = discord.Embed(
                title="🏓 Pong!",
                description=f"Bot latency: **{latency_ms}ms**",
                color=0x3498DB
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        logger.info("Slash commands setup complete")

    async def sync_commands(self, guild_id: Optional[str] = None) -> int:
        """
        Sync slash commands with Discord.

        Args:
            guild_id: Optional guild ID to sync commands for a specific guild.
                     If None, syncs globally.

        Returns:
            int: Number of commands synced
        """
        try:
            if guild_id:
                # Sync commands for a specific guild (faster)
                guild = discord.Object(id=int(guild_id))
                synced = await self.tree.sync(guild=guild)
                logger.info(f"Synced {len(synced)} commands for guild {guild_id}")
            else:
                # Global sync (slower, takes up to 1 hour to propagate)
                synced = await self.tree.sync()
                logger.info(f"Synced {len(synced)} commands globally")

            return len(synced)

        except discord.HTTPException as e:
            logger.error(f"Failed to sync commands: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error syncing commands: {e}", exc_info=True)
            raise

    async def clear_commands(self, guild_id: Optional[str] = None) -> None:
        """
        Clear all slash commands.

        Args:
            guild_id: Optional guild ID to clear commands for a specific guild.
                     If None, clears globally.
        """
        try:
            if guild_id:
                guild = discord.Object(id=int(guild_id))
                self.tree.clear_commands(guild=guild)
                await self.tree.sync(guild=guild)
                logger.info(f"Cleared commands for guild {guild_id}")
            else:
                self.tree.clear_commands(guild=None)
                await self.tree.sync()
                logger.info("Cleared global commands")

        except Exception as e:
            logger.error(f"Failed to clear commands: {e}", exc_info=True)
            raise

    def get_command_count(self) -> int:
        """
        Get the number of registered commands.

        Returns:
            int: Number of commands
        """
        return len(self.tree.get_commands())

    def get_command_names(self) -> list[str]:
        """
        Get a list of all registered command names.

        Returns:
            list[str]: List of command names
        """
        return [cmd.name for cmd in self.tree.get_commands()]
