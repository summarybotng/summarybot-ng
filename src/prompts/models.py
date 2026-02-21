"""
Data models for the external prompt hosting system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Any
from enum import Enum


class PromptSource(Enum):
    """Source of a resolved prompt."""
    CUSTOM = "custom"  # From guild's GitHub repo
    CACHED = "cached"  # From cache (may be stale)
    DEFAULT = "default"  # Built-in default for category
    FALLBACK = "fallback"  # Global fallback prompt


class SchemaVersion(Enum):
    """Supported PATH file schema versions."""
    V1 = "v1"
    V2 = "v2"


@dataclass
class PromptContext:
    """
    Context information for prompt resolution.

    Contains all variables that can be used in PATH template substitution.
    """
    guild_id: str
    channel_name: Optional[str] = None
    channel_id: Optional[str] = None
    category: str = "discussion"  # meeting, discussion, moderation
    summary_type: str = "detailed"  # brief, detailed, action_items, comprehensive
    perspective: str = "general"  # general, developer, marketing, product, finance, executive, support
    message_count: int = 0
    user_id: Optional[str] = None
    additional_context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for template substitution."""
        return {
            "guild_id": self.guild_id,
            "guild": self.guild_id,
            "channel": self.channel_name or "",
            "channel_name": self.channel_name or "",
            "channel_id": self.channel_id or "",
            "category": self.category,
            "type": self.summary_type,
            "summary_type": self.summary_type,
            "perspective": self.perspective,
            "message_count": self.message_count,
            "user_id": self.user_id or "",
            **self.additional_context
        }


@dataclass
class ResolvedPrompt:
    """
    A successfully resolved prompt template.
    """
    content: str
    source: PromptSource
    version: str = "v1"
    variables: Dict[str, str] = field(default_factory=dict)
    is_stale: bool = False
    repo_url: Optional[str] = None
    resolved_at: datetime = field(default_factory=datetime.utcnow)
    # Path tracking for transparency
    file_path: Optional[str] = None  # The file path that was actually used
    tried_paths: List[str] = field(default_factory=list)  # All paths tried in order
    github_file_url: Optional[str] = None  # Full GitHub URL to the file (if from GitHub)
    # Path resolution details - ADR-010
    path_template: Optional[str] = None  # e.g., "prompts/{perspective}/{type}.md"
    resolved_variables: Dict[str, str] = field(default_factory=dict)  # Variables that drove selection

    def get_age_seconds(self) -> float:
        """Get age of this resolved prompt in seconds."""
        return (datetime.utcnow() - self.resolved_at).total_seconds()

    def to_source_info(self) -> Dict[str, Any]:
        """Get prompt source information for API responses."""
        return {
            "source": self.source.value,
            "file_path": self.file_path,
            "tried_paths": self.tried_paths,
            "repo_url": self.repo_url,
            "github_file_url": self.github_file_url,
            "version": self.version,
            "is_stale": self.is_stale,
            # Path resolution details - ADR-010
            "path_template": self.path_template,
            "resolved_variables": self.resolved_variables,
        }


@dataclass
class CachedPrompt:
    """
    A cached prompt with metadata.
    """
    content: str
    source: str
    version: str
    cached_at: datetime
    expires_at: datetime
    repo_url: Optional[str] = None
    context_hash: Optional[str] = None

    @property
    def is_fresh(self) -> bool:
        """Check if cache entry is still fresh."""
        return datetime.utcnow() < self.expires_at

    @property
    def is_stale(self) -> bool:
        """Check if cache entry is stale but still usable."""
        return not self.is_fresh

    @property
    def age_minutes(self) -> float:
        """Get age of cache entry in minutes."""
        return (datetime.utcnow() - self.cached_at).total_seconds() / 60


@dataclass
class GuildPromptConfig:
    """
    Guild-specific prompt configuration stored in database.
    """
    guild_id: str
    repo_url: Optional[str] = None
    branch: str = "main"
    enabled: bool = True
    auth_token: Optional[str] = None  # Encrypted PAT for private repos
    last_sync: Optional[datetime] = None
    last_sync_status: str = "never"  # success, failed, rate_limited, never
    validation_errors: Optional[List[str]] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def has_custom_prompts(self) -> bool:
        """Check if guild has custom prompts configured."""
        return self.enabled and self.repo_url is not None


@dataclass
class PATHFileRoute:
    """
    A single route definition from a PATH file.
    """
    name: str
    path_template: str
    conditions: List[str] = field(default_factory=list)
    priority: int = 0
    variables: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PATHFileConfig:
    """
    Parsed PATH file configuration.
    """
    version: SchemaVersion
    routes: Dict[str, PATHFileRoute]
    fallback_chain: List[str]
    variables: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """
    Result of schema validation.
    """
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, error: str) -> None:
        """Add a validation error."""
        self.errors.append(error)
        self.is_valid = False

    def add_warning(self, warning: str) -> None:
        """Add a validation warning."""
        self.warnings.append(warning)


@dataclass
class RepoContents:
    """
    Contents fetched from a GitHub repository.
    """
    path_file: Optional[str] = None
    schema_version: Optional[str] = None
    prompts: Dict[str, str] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=datetime.utcnow)
