"""
Default prompt provider for built-in prompts.

Provides fallback prompts when custom prompts are unavailable.
Supports hierarchical prompts organized by perspective and length.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, List

from .models import PromptContext, ResolvedPrompt, PromptSource

logger = logging.getLogger(__name__)


class DefaultPromptProvider:
    """
    Provides built-in default prompts.

    Prompts are loaded from the defaults/ directory and cached in memory.
    Supports hierarchical organization:
    - defaults/{perspective}/{length}.md (e.g., developer/brief.md)
    - defaults/{category}.md (e.g., discussion.md)
    - defaults/default.md (fallback)
    """

    def __init__(self):
        """Initialize the default prompt provider."""
        self.defaults_dir = Path(__file__).parent / "defaults"
        self._cache: Dict[str, str] = {}
        self._hierarchical_cache: Dict[str, Dict[str, str]] = {}
        self._load_defaults()

    def _load_defaults(self) -> None:
        """Load all default prompts into memory cache."""
        if not self.defaults_dir.exists():
            logger.warning(f"Defaults directory not found: {self.defaults_dir}")
            return

        # Load flat category prompts (defaults/*.md)
        for prompt_file in self.defaults_dir.glob("*.md"):
            prompt_name = prompt_file.stem
            try:
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self._cache[prompt_name] = content
                    logger.debug(f"Loaded default prompt: {prompt_name}")
            except Exception as e:
                logger.error(f"Failed to load default prompt {prompt_name}: {e}")

        # Load hierarchical prompts (defaults/{perspective}/*.md)
        for perspective_dir in self.defaults_dir.iterdir():
            if perspective_dir.is_dir():
                perspective = perspective_dir.name
                self._hierarchical_cache[perspective] = {}
                for prompt_file in perspective_dir.glob("*.md"):
                    length = prompt_file.stem
                    try:
                        with open(prompt_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                            self._hierarchical_cache[perspective][length] = content
                            logger.debug(f"Loaded hierarchical prompt: {perspective}/{length}")
                    except Exception as e:
                        logger.error(f"Failed to load prompt {perspective}/{length}: {e}")

    def get_prompt(self, context: PromptContext) -> Optional[ResolvedPrompt]:
        """
        Get default prompt for the given context.

        Resolution order:
        1. {perspective}/{summary_length}.md (e.g., developer/detailed.md)
        2. {category}.md (e.g., discussion.md)
        3. default.md

        Args:
            context: Prompt context

        Returns:
            ResolvedPrompt or None if no matching default
        """
        tried_paths = []
        resolved_variables = {}

        # Get perspective and length from context
        perspective = getattr(context, 'perspective', None) or 'general'
        summary_length = getattr(context, 'summary_length', None) or 'detailed'

        # Try hierarchical prompt first: {perspective}/{length}.md
        if perspective in self._hierarchical_cache:
            resolved_variables['perspective'] = perspective
            resolved_variables['summary_length'] = summary_length
            hierarchical_path = f"{perspective}/{summary_length}.md"
            tried_paths.append(f"defaults/{hierarchical_path}")

            if summary_length in self._hierarchical_cache[perspective]:
                file_path = str(self.defaults_dir / perspective / f"{summary_length}.md")
                return ResolvedPrompt(
                    content=self._hierarchical_cache[perspective][summary_length],
                    source=PromptSource.DEFAULT,
                    version="v1",
                    variables=context.to_dict(),
                    file_path=file_path,
                    tried_paths=tried_paths,
                    path_template="defaults/{perspective}/{summary_length}.md",
                    resolved_variables=resolved_variables
                )

        # Try category-specific prompt
        if context.category:
            resolved_variables['category'] = context.category
            category_file = f"{context.category}.md"
            tried_paths.append(f"defaults/{category_file}")
            category_prompt = self._cache.get(context.category)
            if category_prompt:
                file_path = str(self.defaults_dir / category_file)
                return ResolvedPrompt(
                    content=category_prompt,
                    source=PromptSource.DEFAULT,
                    version="v1",
                    variables=context.to_dict(),
                    file_path=file_path,
                    tried_paths=tried_paths,
                    path_template="defaults/{category}.md",
                    resolved_variables=resolved_variables
                )

        # Fall back to default.md
        tried_paths.append("defaults/default.md")
        default_prompt = self._cache.get("default")
        if default_prompt:
            file_path = str(self.defaults_dir / "default.md")
            return ResolvedPrompt(
                content=default_prompt,
                source=PromptSource.DEFAULT,
                version="v1",
                variables=context.to_dict(),
                file_path=file_path,
                tried_paths=tried_paths
            )

        return None

    def get_fallback_prompt(self) -> ResolvedPrompt:
        """
        Get the global fallback prompt (always available).

        Returns:
            ResolvedPrompt with hardcoded fallback
        """
        # Try to use default.md if available
        if "default" in self._cache:
            file_path = str(self.defaults_dir / "default.md")
            return ResolvedPrompt(
                content=self._cache["default"],
                source=PromptSource.FALLBACK,
                version="v1",
                file_path=file_path,
                tried_paths=["defaults/default.md"]
            )

        # Ultimate fallback - hardcoded
        return ResolvedPrompt(
            content=self._get_hardcoded_fallback(),
            source=PromptSource.FALLBACK,
            version="v1",
            file_path="<hardcoded>",
            tried_paths=["defaults/default.md", "<hardcoded>"]
        )

    def _get_hardcoded_fallback(self) -> str:
        """Get hardcoded fallback prompt (used when files can't be read)."""
        return """# Discord Conversation Summary

You are a helpful AI assistant that creates summaries of Discord conversations.

Analyze the following messages and provide a clear, concise summary:

{messages}

Please organize your summary with:
- Main topics discussed
- Key decisions or conclusions
- Important points raised
- Any action items or follow-ups

Use Markdown formatting for readability.
"""

    @property
    def available_categories(self) -> list[str]:
        """Get list of available category prompts."""
        return [name for name in self._cache.keys() if name != "default"]

    @property
    def available_perspectives(self) -> list[str]:
        """Get list of available perspective prompts."""
        return list(self._hierarchical_cache.keys())

    def get_available_lengths(self, perspective: str) -> list[str]:
        """Get available lengths for a perspective."""
        return list(self._hierarchical_cache.get(perspective, {}).keys())

    def get_all_prompts(self) -> Dict[str, any]:
        """
        Get all available prompts in a structured format.

        Returns:
            Dict with 'categories' and 'perspectives' keys
        """
        result = {
            "categories": [],
            "perspectives": {}
        }

        # Add category prompts
        for category in self._cache.keys():
            file_path = self.defaults_dir / f"{category}.md"
            result["categories"].append({
                "name": category,
                "file_path": f"defaults/{category}.md",
                "content": self._cache[category],
                "description": self._get_category_description(category)
            })

        # Add hierarchical prompts
        for perspective, lengths in self._hierarchical_cache.items():
            result["perspectives"][perspective] = {
                "description": self._get_perspective_description(perspective),
                "lengths": {}
            }
            for length, content in lengths.items():
                result["perspectives"][perspective]["lengths"][length] = {
                    "name": length,
                    "file_path": f"defaults/{perspective}/{length}.md",
                    "content": content,
                    "description": self._get_length_description(length)
                }

        return result

    def _get_category_description(self, category: str) -> str:
        """Get description for a category."""
        descriptions = {
            "default": "General-purpose summary prompt",
            "discussion": "Optimized for casual discussions",
            "meeting": "Structured for meeting notes",
            "moderation": "Focused on moderation-relevant content"
        }
        return descriptions.get(category, f"Prompt for {category} category")

    def _get_perspective_description(self, perspective: str) -> str:
        """Get description for a perspective."""
        descriptions = {
            "general": "Balanced summaries for general audiences",
            "developer": "Technical focus on code, architecture, and engineering",
            "marketing": "Customer insights, sentiment, and market opportunities",
            "executive": "Strategic decisions, risks, and business impact",
            "support": "Issue tracking, troubleshooting, and customer support"
        }
        return descriptions.get(perspective, f"Summaries from {perspective} perspective")

    def _get_length_description(self, length: str) -> str:
        """Get description for a length."""
        descriptions = {
            "brief": "Concise 2-3 paragraph summary of key points only",
            "detailed": "Thorough coverage of topics, decisions, and context",
            "comprehensive": "Complete documentation with full analysis"
        }
        return descriptions.get(length, f"{length.capitalize()} summary")
