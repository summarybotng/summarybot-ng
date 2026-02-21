"""
Prompt template resolver - main orchestrator for external prompt hosting.

This is the primary entry point for prompt resolution. It coordinates:
- Cache checking
- GitHub fetching
- PATH template parsing
- Fallback chain execution
- Template variable substitution
"""

import logging
from typing import Optional
import re

from .models import PromptContext, ResolvedPrompt, PromptSource, GuildPromptConfig
from .cache import PromptCacheManager
from .github_client import GitHubRepositoryClient
from .path_parser import PATHFileParser
from .schema_validator import SchemaValidator
from .default_provider import DefaultPromptProvider
from .fallback_chain import FallbackChainExecutor

logger = logging.getLogger(__name__)


class PromptTemplateResolver:
    """
    Main orchestrator for prompt template resolution.

    Resolves prompts using this flow:
    1. Check cache for fresh prompt → return if found
    2. Fetch guild config → check if custom prompts enabled
    3. If custom prompts: fetch from GitHub using PATH file
    4. Cache the result
    5. If GitHub fails: execute fallback chain
    6. Substitute template variables
    7. Return resolved prompt
    """

    def __init__(
        self,
        config_store=None,
        github_client: Optional[GitHubRepositoryClient] = None,
        cache_manager: Optional[PromptCacheManager] = None,
        path_parser: Optional[PATHFileParser] = None,
        default_provider: Optional[DefaultPromptProvider] = None,
        validator: Optional[SchemaValidator] = None
    ):
        """
        Initialize the prompt template resolver.

        Args:
            config_store: Optional GuildPromptConfigStore for fetching guild configs

        Args:
            github_client: GitHub client for fetching repos
            cache_manager: Cache manager for caching prompts
            path_parser: PATH file parser
            default_provider: Default prompt provider
            validator: Schema validator
        """
        self.config_store = config_store
        self.validator = validator or SchemaValidator()
        self.github_client = github_client or GitHubRepositoryClient(validator=self.validator)
        self.cache_manager = cache_manager or PromptCacheManager()
        self.path_parser = path_parser or PATHFileParser(validator=self.validator)
        self.default_provider = default_provider or DefaultPromptProvider()
        self.fallback_executor = FallbackChainExecutor(
            cache_manager=self.cache_manager,
            default_provider=self.default_provider
        )

    async def resolve_prompt(
        self,
        guild_id: str,
        context: PromptContext,
        guild_config: Optional[GuildPromptConfig] = None
    ) -> ResolvedPrompt:
        """
        Resolve prompt for the given guild and context.

        This is the main entry point for prompt resolution.

        Args:
            guild_id: Discord guild ID
            context: Prompt context with variables
            guild_config: Optional guild configuration (fetched if not provided)

        Returns:
            ResolvedPrompt with content and metadata
        """
        # Step 0: Fetch guild config if not provided and config_store available
        if guild_config is None and self.config_store is not None:
            try:
                guild_config = await self.config_store.get_config(guild_id)
                if guild_config:
                    logger.debug(f"Fetched guild config for {guild_id} from config_store")
            except Exception as e:
                logger.warning(f"Failed to fetch guild config for {guild_id}: {e}")
                guild_config = None

        # Step 1: Check cache for fresh prompt
        cached = await self.cache_manager.get(guild_id, context)
        if cached:
            logger.debug(f"Cache HIT for guild {guild_id}")
            return ResolvedPrompt(
                content=self._substitute_variables(cached.content, context),
                source=PromptSource(cached.source),
                version=cached.version,
                repo_url=cached.repo_url
            )

        # Step 2: Check if guild has custom prompts enabled
        has_custom_prompts = (
            guild_config is not None
            and guild_config.enabled
        )

        if not has_custom_prompts:
            # No custom prompts configured - use defaults
            logger.debug(f"No custom prompts for guild {guild_id}, using defaults")
            return await self._resolve_default(context)

        # Step 3: Try to fetch custom prompt from GitHub
        custom_fetcher = lambda gid, ctx: self._fetch_custom_prompt(
            guild_config, ctx
        )

        resolved = await self.fallback_executor.resolve_with_fallback(
            guild_id=guild_id,
            context=context,
            custom_fetcher=custom_fetcher
        )

        # Step 4: Cache the result (if not stale)
        if not resolved.is_stale:
            await self.cache_manager.set(guild_id, context, resolved)

        # Step 5: Substitute variables
        resolved.content = self._substitute_variables(resolved.content, context)

        return resolved

    async def _fetch_custom_prompt(
        self,
        guild_config: GuildPromptConfig,
        context: PromptContext
    ) -> Optional[ResolvedPrompt]:
        """
        Fetch custom prompt from GitHub repository.

        Args:
            guild_config: Guild configuration with repo URL
            context: Prompt context

        Returns:
            ResolvedPrompt or None if fetch fails
        """
        if not guild_config.repo_url:
            return None

        # Fetch PATH file
        path_file_content = await self.github_client.fetch_file(
            repo_url=guild_config.repo_url,
            file_path="PATH",
            branch=guild_config.branch
        )

        if not path_file_content:
            logger.warning(
                f"No PATH file found in {guild_config.repo_url}"
            )
            return None

        # Parse PATH file
        try:
            path_config = self.path_parser.parse(path_file_content)
        except ValueError as e:
            logger.error(f"Invalid PATH file: {e}")
            return None

        # Resolve paths using PATH config
        file_paths = self.path_parser.resolve_paths(path_config, context)

        # Get the first matching route's path template for transparency
        path_template = None
        if path_config.fallback_chain and path_config.routes:
            first_route = path_config.fallback_chain[0]
            if first_route in path_config.routes:
                path_template = path_config.routes[first_route].path_template

        # Build resolved variables dict for transparency (ADR-010)
        context_dict = context.to_dict()
        resolved_variables = {
            k: str(v) for k, v in context_dict.items()
            if v and k in ['perspective', 'summary_type', 'category', 'channel_name']
        }

        # Try each path until we find a file
        tried_paths = []
        for file_path in file_paths:
            logger.debug(f"Trying path: {file_path}")
            tried_paths.append(file_path)

            prompt_content = await self.github_client.fetch_file(
                repo_url=guild_config.repo_url,
                file_path=file_path,
                branch=guild_config.branch
            )

            if prompt_content:
                # Validate the prompt
                validation = self.validator.validate_prompt_template(prompt_content)
                if not validation.is_valid:
                    logger.error(
                        f"Invalid prompt template at {file_path}: "
                        f"{'; '.join(validation.errors)}"
                    )
                    continue

                logger.info(
                    f"Fetched custom prompt from {guild_config.repo_url}/{file_path}"
                )

                # Build GitHub file URL for transparency
                github_file_url = self._build_github_file_url(
                    guild_config.repo_url,
                    file_path,
                    guild_config.branch
                )

                return ResolvedPrompt(
                    content=prompt_content,
                    source=PromptSource.CUSTOM,
                    version=path_config.version.value,
                    repo_url=guild_config.repo_url,
                    variables=context.to_dict(),
                    file_path=file_path,
                    tried_paths=tried_paths,
                    github_file_url=github_file_url,
                    path_template=path_template,
                    resolved_variables=resolved_variables,
                )

        # No prompt found in any path
        logger.warning(
            f"No prompt found in {guild_config.repo_url} for paths: {file_paths}"
        )
        return None

    async def _resolve_default(self, context: PromptContext) -> ResolvedPrompt:
        """
        Resolve default prompt (no custom repository).

        Args:
            context: Prompt context

        Returns:
            ResolvedPrompt from default provider
        """
        prompt = self.default_provider.get_prompt(context)
        if prompt:
            prompt.content = self._substitute_variables(prompt.content, context)
            return prompt

        # Ultimate fallback
        fallback = self.default_provider.get_fallback_prompt()
        fallback.content = self._substitute_variables(fallback.content, context)
        return fallback

    def _substitute_variables(self, template: str, context: PromptContext) -> str:
        """
        Substitute template variables with values from context.

        Args:
            template: Template string with {variable} placeholders
            context: Prompt context with values

        Returns:
            Template with variables substituted

        Example:
            Template: "Summarize {message_count} messages from {channel}"
            Context: {message_count: 50, channel: "general"}
            Result: "Summarize 50 messages from general"
        """
        result = template
        context_dict = context.to_dict()

        # Find all variables in template
        variables = re.findall(r'\{([^}]+)\}', template)

        for var in variables:
            value = context_dict.get(var, "")
            if value:
                result = result.replace(f"{{{var}}}", str(value))
            else:
                # Variable not found - leave placeholder or use default
                logger.warning(f"Variable '{var}' not found in context")
                result = result.replace(f"{{{var}}}", f"[{var}]")

        return result

    async def invalidate_guild_cache(self, guild_id: str) -> int:
        """
        Invalidate all cached prompts for a guild.

        Useful when guild admin updates their repository.

        Args:
            guild_id: Discord guild ID

        Returns:
            Number of cache entries invalidated
        """
        return await self.cache_manager.invalidate_guild(guild_id)

    @property
    def cache_stats(self) -> dict:
        """Get cache statistics."""
        return self.cache_manager.cache_stats

    def _build_github_file_url(
        self,
        repo_url: str,
        file_path: str,
        branch: str = "main"
    ) -> str:
        """
        Build a full GitHub URL to view a file.

        Args:
            repo_url: Repository URL (e.g., https://github.com/user/repo)
            file_path: File path within the repo
            branch: Branch name

        Returns:
            Full GitHub URL to the file (e.g., https://github.com/user/repo/blob/main/path/to/file.md)
        """
        # Normalize repo URL (remove trailing slash, .git suffix)
        repo_url = repo_url.rstrip("/")
        if repo_url.endswith(".git"):
            repo_url = repo_url[:-4]

        # Build the blob URL
        return f"{repo_url}/blob/{branch}/{file_path}"
