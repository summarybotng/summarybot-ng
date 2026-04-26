"""
Tests for Wiki Repository (ADR-056).

Tests cover:
- CRUD operations for wiki pages
- Full-text search with FTS5
- Navigation tree building
- Link tracking
- Contradiction detection
- Source document management
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.wiki.models import (
    WikiPage,
    WikiSource,
    WikiSourceType,
    WikiTree,
    WikiTreeNode,
)
from src.data.sqlite.wiki_repository import SQLiteWikiRepository


@pytest.fixture
def mock_connection():
    """Create mock SQLite connection."""
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetch_one = AsyncMock()
    conn.fetch_all = AsyncMock()
    return conn


@pytest.fixture
def wiki_repo(mock_connection):
    """Create wiki repository with mock connection."""
    return SQLiteWikiRepository(mock_connection)


@pytest.fixture
def sample_page():
    """Create sample wiki page."""
    return WikiPage(
        id="page-123",
        guild_id="guild-456",
        path="topics/authentication.md",
        title="Authentication",
        content="# Authentication\n\nThis page covers authentication...",
        topics=["authentication", "security"],
        source_refs=["summary-abc"],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def sample_source():
    """Create sample wiki source."""
    return WikiSource(
        id="source-789",
        guild_id="guild-456",
        source_type=WikiSourceType.SUMMARY,
        title="Summary: #general - 2024-01-15",
        content="Discussion about authentication patterns...",
        metadata={"channel_id": "123", "message_count": 50},
    )


class TestWikiPageCRUD:
    """Test wiki page CRUD operations."""

    @pytest.mark.asyncio
    async def test_save_page_creates_new_page(self, wiki_repo, mock_connection, sample_page):
        """Test saving a new wiki page."""
        mock_connection.fetch_one.return_value = None  # Page doesn't exist

        await wiki_repo.save_page(sample_page)

        # Verify INSERT was called
        assert mock_connection.execute.called
        call_args = mock_connection.execute.call_args_list[0]
        assert "INSERT INTO wiki_pages" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_save_page_updates_fts_index(self, wiki_repo, mock_connection, sample_page):
        """Test that saving a page updates FTS index."""
        mock_connection.fetch_one.return_value = None

        await wiki_repo.save_page(sample_page)

        # Should have FTS operations
        fts_calls = [c for c in mock_connection.execute.call_args_list
                     if "wiki_fts" in str(c)]
        assert len(fts_calls) >= 1

    @pytest.mark.asyncio
    async def test_get_page_returns_page_when_exists(self, wiki_repo, mock_connection, sample_page):
        """Test getting an existing page."""
        mock_connection.fetch_one.return_value = {
            "id": sample_page.id,
            "guild_id": sample_page.guild_id,
            "path": sample_page.path,
            "title": sample_page.title,
            "content": sample_page.content,
            "topics": '["authentication", "security"]',
            "source_refs": '["summary-abc"]',
            "created_at": sample_page.created_at.isoformat(),
            "updated_at": sample_page.updated_at.isoformat(),
            "inbound_links": 5,
            "outbound_links": 3,
            "confidence": 100,
        }

        result = await wiki_repo.get_page("guild-456", "topics/authentication.md")

        assert result is not None
        assert result.id == sample_page.id
        assert result.title == "Authentication"
        assert "authentication" in result.topics

    @pytest.mark.asyncio
    async def test_get_page_returns_none_when_not_exists(self, wiki_repo, mock_connection):
        """Test getting a non-existent page returns None."""
        mock_connection.fetch_one.return_value = None

        result = await wiki_repo.get_page("guild-456", "nonexistent.md")

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_page_removes_from_db_and_fts(self, wiki_repo, mock_connection):
        """Test deleting a page removes it from DB and FTS."""
        mock_connection.execute.return_value = MagicMock(rowcount=1)

        result = await wiki_repo.delete_page("guild-456", "topics/old.md")

        assert result is True
        # Should delete from both wiki_pages and wiki_fts
        delete_calls = [c for c in mock_connection.execute.call_args_list
                        if "DELETE" in str(c)]
        assert len(delete_calls) >= 2


class TestWikiSearch:
    """Test wiki full-text search."""

    @pytest.mark.asyncio
    async def test_search_pages_uses_fts5(self, wiki_repo, mock_connection):
        """Test search uses FTS5 virtual table."""
        mock_connection.fetch_all.return_value = [
            {
                "id": "page-1",
                "guild_id": "guild-456",
                "path": "topics/auth.md",
                "title": "Auth",
                "topics": "[]",
                "updated_at": datetime.utcnow().isoformat(),
                "inbound_links": 0,
                "confidence": 100,
            }
        ]

        await wiki_repo.search_pages("guild-456", "authentication")

        # Verify FTS query was made
        call_args = mock_connection.fetch_all.call_args
        assert "wiki_fts" in call_args[0][0]
        assert "MATCH" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_search_returns_ranked_results(self, wiki_repo, mock_connection):
        """Test search results are ranked by relevance."""
        mock_connection.fetch_all.return_value = [
            {"id": "1", "guild_id": "g", "path": "a.md", "title": "A",
             "topics": "[]", "updated_at": "2024-01-01", "inbound_links": 0, "confidence": 100},
            {"id": "2", "guild_id": "g", "path": "b.md", "title": "B",
             "topics": "[]", "updated_at": "2024-01-01", "inbound_links": 0, "confidence": 100},
        ]

        results = await wiki_repo.search_pages("g", "query")

        assert len(results) == 2
        # Verify ORDER BY bm25 is in query
        call_args = mock_connection.fetch_all.call_args
        assert "bm25" in call_args[0][0].lower() or "rank" in call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_search_respects_limit(self, wiki_repo, mock_connection):
        """Test search respects limit parameter."""
        mock_connection.fetch_all.return_value = []

        await wiki_repo.search_pages("guild-456", "query", limit=5)

        call_args = mock_connection.fetch_all.call_args
        assert "LIMIT" in call_args[0][0]


class TestWikiTree:
    """Test wiki navigation tree."""

    @pytest.mark.asyncio
    async def test_get_tree_returns_all_categories(self, wiki_repo, mock_connection):
        """Test tree includes all 5 categories."""
        mock_connection.fetch_all.side_effect = [
            # Category counts
            [
                {"category": "topics", "count": 10},
                {"category": "decisions", "count": 5},
                {"category": "experts", "count": 2},
            ],
            # Topics children
            [{"path": "topics/a.md", "title": "A"}],
            # Decisions children
            [{"path": "decisions/b.md", "title": "B"}],
            # Processes children
            [],
            # Experts children
            [],
            # Questions children
            [],
        ]

        tree = await wiki_repo.get_tree("guild-456")

        assert tree.guild_id == "guild-456"
        assert tree.topics.page_count == 10
        assert tree.decisions.page_count == 5
        assert tree.experts.page_count == 2
        assert tree.processes.page_count == 0
        assert tree.questions.page_count == 0

    @pytest.mark.asyncio
    async def test_get_tree_populates_children(self, wiki_repo, mock_connection):
        """Test tree populates child nodes."""
        mock_connection.fetch_all.side_effect = [
            [{"category": "topics", "count": 2}],
            [
                {"path": "topics/auth.md", "title": "Authentication"},
                {"path": "topics/api.md", "title": "API Design"},
            ],
            [], [], [], [],
        ]

        tree = await wiki_repo.get_tree("guild-456")

        assert len(tree.topics.children) == 2
        assert tree.topics.children[0].title == "Authentication"
        assert tree.topics.children[1].title == "API Design"


class TestWikiSources:
    """Test wiki source document management."""

    @pytest.mark.asyncio
    async def test_save_source_creates_immutable_record(self, wiki_repo, mock_connection, sample_source):
        """Test saving source creates immutable record."""
        await wiki_repo.save_source(sample_source)

        call_args = mock_connection.execute.call_args
        assert "INSERT" in call_args[0][0]
        assert "wiki_sources" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_count_sources_returns_correct_count(self, wiki_repo, mock_connection):
        """Test counting sources returns correct value."""
        mock_connection.fetch_one.return_value = {"count": 42}

        count = await wiki_repo.count_sources("guild-456")

        assert count == 42


class TestWikiLinks:
    """Test wiki link tracking."""

    @pytest.mark.asyncio
    async def test_find_orphan_pages_returns_unlinked(self, wiki_repo, mock_connection):
        """Test finding orphan pages (no inbound links)."""
        mock_connection.fetch_all.return_value = [
            {"id": "1", "guild_id": "g", "path": "orphan.md", "title": "Orphan",
             "topics": "[]", "updated_at": "2024-01-01", "inbound_links": 0, "confidence": 100}
        ]

        orphans = await wiki_repo.find_orphan_pages("guild-456")

        assert len(orphans) == 1
        assert orphans[0].path == "orphan.md"
        # Verify query filters for inbound_links = 0
        call_args = mock_connection.fetch_all.call_args
        assert "inbound_links" in call_args[0][0]


class TestWikiContradictions:
    """Test wiki contradiction detection."""

    @pytest.mark.asyncio
    async def test_get_unresolved_contradictions(self, wiki_repo, mock_connection):
        """Test getting unresolved contradictions."""
        mock_connection.fetch_all.return_value = [
            {
                "id": 1,
                "guild_id": "g",
                "page_a": "topics/a.md",
                "page_b": "topics/b.md",
                "claim_a": "X is true",
                "claim_b": "X is false",
                "detected_at": "2024-01-01",
                "resolved_at": None,
                "resolution": None,
            }
        ]

        contradictions = await wiki_repo.get_unresolved_contradictions("guild-456")

        assert len(contradictions) == 1
        assert contradictions[0].page_a == "topics/a.md"
        assert contradictions[0].resolution is None

    @pytest.mark.asyncio
    async def test_resolve_contradiction_marks_resolved(self, wiki_repo, mock_connection):
        """Test resolving a contradiction."""
        mock_connection.execute.return_value = MagicMock(rowcount=1)

        result = await wiki_repo.resolve_contradiction(1, "Claim A was correct")

        assert result is True
        call_args = mock_connection.execute.call_args
        assert "UPDATE" in call_args[0][0]
        assert "resolved_at" in call_args[0][0]


class TestWikiRecentChanges:
    """Test wiki recent changes."""

    @pytest.mark.asyncio
    async def test_get_recent_changes_filters_by_days(self, wiki_repo, mock_connection):
        """Test recent changes filters by day range."""
        mock_connection.fetch_all.return_value = []

        await wiki_repo.get_recent_changes("guild-456", days=7)

        call_args = mock_connection.fetch_all.call_args
        # Should filter by timestamp
        assert "timestamp" in call_args[0][0] or "datetime" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_get_recent_changes_returns_operations(self, wiki_repo, mock_connection):
        """Test recent changes returns operation details from wiki_pages."""
        mock_connection.fetch_all.return_value = [
            {
                "path": "topics/new.md",
                "title": "New Topic",
                "updated_at": "2024-01-15T10:00:00",
                "source_refs": '["summary-123"]',
            }
        ]

        changes = await wiki_repo.get_recent_changes("guild-456")

        assert len(changes) == 1
        assert changes[0].operation == "update"  # Implementation hardcodes this
        assert changes[0].page_path == "topics/new.md"
        assert changes[0].page_title == "New Topic"
        assert changes[0].source_id == "summary-123"
