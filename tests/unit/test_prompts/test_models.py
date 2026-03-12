"""
Unit tests for prompts/models.py.

Tests dataclasses and their methods for the external prompt hosting system.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from src.prompts.models import (
    PromptSource,
    SchemaVersion,
    PromptContext,
    ResolvedPrompt,
    CachedPrompt,
    GuildPromptConfig,
    PATHFileRoute,
    PATHFileConfig,
    ValidationResult,
    RepoContents,
)


class TestPromptSource:
    """Tests for PromptSource enum."""

    def test_prompt_source_values(self):
        """Verify all source types exist."""
        assert PromptSource.CUSTOM.value == "custom"
        assert PromptSource.CACHED.value == "cached"
        assert PromptSource.DEFAULT.value == "default"
        assert PromptSource.FALLBACK.value == "fallback"


class TestSchemaVersion:
    """Tests for SchemaVersion enum."""

    def test_schema_version_values(self):
        """Verify schema version values."""
        assert SchemaVersion.V1.value == "v1"
        assert SchemaVersion.V2.value == "v2"


class TestPromptContext:
    """Tests for PromptContext dataclass."""

    def test_default_values(self):
        """PromptContext has correct defaults."""
        ctx = PromptContext(guild_id="123")
        assert ctx.guild_id == "123"
        assert ctx.channel_name is None
        assert ctx.category == "discussion"
        assert ctx.summary_type == "detailed"
        assert ctx.perspective == "general"
        assert ctx.message_count == 0

    def test_to_dict_basic(self):
        """to_dict returns all expected keys."""
        ctx = PromptContext(guild_id="123")
        d = ctx.to_dict()
        assert d["guild_id"] == "123"
        assert d["guild"] == "123"
        assert d["channel"] == ""
        assert d["category"] == "discussion"
        assert d["type"] == "detailed"
        assert d["perspective"] == "general"

    def test_to_dict_with_channel(self):
        """to_dict includes channel name."""
        ctx = PromptContext(guild_id="123", channel_name="general")
        d = ctx.to_dict()
        assert d["channel"] == "general"
        assert d["channel_name"] == "general"

    def test_to_dict_with_additional_context(self):
        """to_dict merges additional context."""
        ctx = PromptContext(
            guild_id="123",
            additional_context={"custom_key": "custom_value"}
        )
        d = ctx.to_dict()
        assert d["custom_key"] == "custom_value"


class TestResolvedPrompt:
    """Tests for ResolvedPrompt dataclass."""

    def test_default_values(self):
        """ResolvedPrompt has correct defaults."""
        prompt = ResolvedPrompt(
            content="Test prompt",
            source=PromptSource.DEFAULT
        )
        assert prompt.content == "Test prompt"
        assert prompt.source == PromptSource.DEFAULT
        assert prompt.version == "v1"
        assert prompt.is_stale is False

    def test_get_age_seconds(self):
        """get_age_seconds calculates correct age."""
        past = datetime.utcnow() - timedelta(seconds=30)
        prompt = ResolvedPrompt(
            content="Test",
            source=PromptSource.DEFAULT,
            resolved_at=past
        )
        age = prompt.get_age_seconds()
        assert 29 <= age <= 31  # Allow small variance

    def test_to_source_info(self):
        """to_source_info returns correct structure."""
        prompt = ResolvedPrompt(
            content="Test",
            source=PromptSource.CUSTOM,
            file_path="prompts/discussion/detailed.md",
            tried_paths=["prompts/general.md", "prompts/discussion/detailed.md"],
            repo_url="https://github.com/user/repo"
        )
        info = prompt.to_source_info()
        assert info["source"] == "custom"
        assert info["file_path"] == "prompts/discussion/detailed.md"
        assert len(info["tried_paths"]) == 2
        assert info["repo_url"] == "https://github.com/user/repo"


class TestCachedPrompt:
    """Tests for CachedPrompt dataclass."""

    def test_is_fresh_when_not_expired(self):
        """is_fresh returns True when not expired."""
        cached = CachedPrompt(
            content="Test",
            source="default",
            version="v1",
            cached_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        assert cached.is_fresh is True
        assert cached.is_stale is False

    def test_is_stale_when_expired(self):
        """is_stale returns True when expired."""
        cached = CachedPrompt(
            content="Test",
            source="default",
            version="v1",
            cached_at=datetime.utcnow() - timedelta(hours=2),
            expires_at=datetime.utcnow() - timedelta(hours=1)
        )
        assert cached.is_fresh is False
        assert cached.is_stale is True

    def test_age_minutes(self):
        """age_minutes calculates correct age."""
        past = datetime.utcnow() - timedelta(minutes=15)
        cached = CachedPrompt(
            content="Test",
            source="default",
            version="v1",
            cached_at=past,
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        age = cached.age_minutes
        assert 14.9 <= age <= 15.1


class TestGuildPromptConfig:
    """Tests for GuildPromptConfig dataclass."""

    def test_default_values(self):
        """GuildPromptConfig has correct defaults."""
        config = GuildPromptConfig(guild_id="123")
        assert config.guild_id == "123"
        assert config.repo_url is None
        assert config.branch == "main"
        assert config.enabled is True
        assert config.last_sync_status == "never"

    def test_has_custom_prompts_when_configured(self):
        """has_custom_prompts returns True when configured."""
        config = GuildPromptConfig(
            guild_id="123",
            repo_url="https://github.com/user/prompts",
            enabled=True
        )
        assert config.has_custom_prompts is True

    def test_has_custom_prompts_when_disabled(self):
        """has_custom_prompts returns False when disabled."""
        config = GuildPromptConfig(
            guild_id="123",
            repo_url="https://github.com/user/prompts",
            enabled=False
        )
        assert config.has_custom_prompts is False

    def test_has_custom_prompts_when_no_repo(self):
        """has_custom_prompts returns False when no repo."""
        config = GuildPromptConfig(
            guild_id="123",
            enabled=True
        )
        assert config.has_custom_prompts is False


class TestPATHFileRoute:
    """Tests for PATHFileRoute dataclass."""

    def test_default_values(self):
        """PATHFileRoute has correct defaults."""
        route = PATHFileRoute(
            name="discussion_detailed",
            path_template="prompts/{category}/{type}.md"
        )
        assert route.name == "discussion_detailed"
        assert route.conditions == []
        assert route.priority == 0
        assert route.variables == {}

    def test_with_conditions(self):
        """PATHFileRoute with conditions."""
        route = PATHFileRoute(
            name="meeting_summary",
            path_template="prompts/meeting.md",
            conditions=["category == 'meeting'"],
            priority=10
        )
        assert len(route.conditions) == 1
        assert route.priority == 10


class TestPATHFileConfig:
    """Tests for PATHFileConfig dataclass."""

    def test_creation(self):
        """PATHFileConfig creates correctly."""
        config = PATHFileConfig(
            version=SchemaVersion.V1,
            routes={"default": PATHFileRoute(name="default", path_template="prompts/default.md")},
            fallback_chain=["default"]
        )
        assert config.version == SchemaVersion.V1
        assert "default" in config.routes
        assert config.fallback_chain == ["default"]


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_default_is_valid(self):
        """ValidationResult starts valid."""
        result = ValidationResult(is_valid=True)
        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_add_error_marks_invalid(self):
        """add_error marks result as invalid."""
        result = ValidationResult(is_valid=True)
        result.add_error("Something is wrong")
        assert result.is_valid is False
        assert "Something is wrong" in result.errors

    def test_add_warning_keeps_valid(self):
        """add_warning keeps result valid."""
        result = ValidationResult(is_valid=True)
        result.add_warning("Consider this")
        assert result.is_valid is True
        assert "Consider this" in result.warnings

    def test_multiple_errors(self):
        """Multiple errors accumulate."""
        result = ValidationResult(is_valid=True)
        result.add_error("Error 1")
        result.add_error("Error 2")
        assert len(result.errors) == 2
        assert result.is_valid is False


class TestRepoContents:
    """Tests for RepoContents dataclass."""

    def test_default_values(self):
        """RepoContents has correct defaults."""
        contents = RepoContents()
        assert contents.path_file is None
        assert contents.schema_version is None
        assert contents.prompts == {}
        assert contents.fetched_at is not None

    def test_with_prompts(self):
        """RepoContents with prompts."""
        contents = RepoContents(
            path_file="PATH.yaml",
            schema_version="v1",
            prompts={"default": "prompt content"}
        )
        assert contents.prompts["default"] == "prompt content"
