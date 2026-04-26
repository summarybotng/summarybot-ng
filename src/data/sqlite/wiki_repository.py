"""
SQLite implementation of wiki repository (ADR-056).
"""

import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

from .connection import SQLiteConnection
from ...wiki.models import (
    WikiPage,
    WikiPageSummary,
    WikiLink,
    WikiLogEntry,
    WikiContradiction,
    WikiSource,
    WikiSourceType,
    WikiOperation,
    WikiTree,
    WikiTreeNode,
    WikiSearchResult,
    WikiChange,
)

logger = logging.getLogger(__name__)


class SQLiteWikiRepository:
    """SQLite implementation of wiki repository (ADR-056)."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    # -------------------------------------------------------------------------
    # Pages
    # -------------------------------------------------------------------------

    async def save_page(self, page: WikiPage) -> str:
        """Save or update a wiki page."""
        if not page.id:
            page.id = str(uuid.uuid4())

        query = """
        INSERT INTO wiki_pages (
            id, guild_id, path, title, content, topics, source_refs,
            inbound_links, outbound_links, confidence, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        ON CONFLICT(guild_id, path) DO UPDATE SET
            title = excluded.title,
            content = excluded.content,
            topics = excluded.topics,
            source_refs = excluded.source_refs,
            inbound_links = excluded.inbound_links,
            outbound_links = excluded.outbound_links,
            confidence = excluded.confidence,
            updated_at = datetime('now')
        """

        params = (
            page.id,
            page.guild_id,
            page.path,
            page.title,
            page.content,
            json.dumps(page.topics),
            json.dumps(page.source_refs),
            page.inbound_links,
            page.outbound_links,
            page.confidence,
        )

        await self.connection.execute(query, params)

        # Sync FTS index (triggers can't be used due to migration runner limitations)
        await self._sync_fts(page)

        return page.id

    async def _sync_fts(self, page: WikiPage) -> None:
        """Sync a page to the FTS index."""
        # Delete existing entry
        delete_query = "DELETE FROM wiki_fts WHERE path = ? AND guild_id = ?"
        await self.connection.execute(delete_query, (page.path, page.guild_id))

        # Insert new entry
        insert_query = """
        INSERT INTO wiki_fts(path, title, content, topics, guild_id)
        VALUES (?, ?, ?, ?, ?)
        """
        await self.connection.execute(
            insert_query,
            (page.path, page.title, page.content, json.dumps(page.topics), page.guild_id)
        )

    async def get_page(self, guild_id: str, path: str) -> Optional[WikiPage]:
        """Get a wiki page by path."""
        query = "SELECT * FROM wiki_pages WHERE guild_id = ? AND path = ?"
        row = await self.connection.fetch_one(query, (guild_id, path))
        return self._row_to_page(row) if row else None

    async def get_page_by_id(self, page_id: str) -> Optional[WikiPage]:
        """Get a wiki page by ID."""
        query = "SELECT * FROM wiki_pages WHERE id = ?"
        row = await self.connection.fetch_one(query, (page_id,))
        return self._row_to_page(row) if row else None

    async def list_pages(
        self,
        guild_id: str,
        category: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[WikiPageSummary]:
        """List wiki pages with optional category filter."""
        conditions = ["guild_id = ?"]
        params: List[Any] = [guild_id]

        if category:
            conditions.append("path LIKE ?")
            params.append(f"{category}/%")

        where = " AND ".join(conditions)
        query = f"""
        SELECT id, path, title, topics, updated_at, inbound_links, confidence
        FROM wiki_pages
        WHERE {where}
        ORDER BY updated_at DESC
        LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        rows = await self.connection.fetch_all(query, tuple(params))
        return [self._row_to_page_summary(row) for row in rows]

    async def count_pages(self, guild_id: str, category: Optional[str] = None) -> int:
        """Count wiki pages."""
        if category:
            query = "SELECT COUNT(*) as count FROM wiki_pages WHERE guild_id = ? AND path LIKE ?"
            row = await self.connection.fetch_one(query, (guild_id, f"{category}/%"))
        else:
            query = "SELECT COUNT(*) as count FROM wiki_pages WHERE guild_id = ?"
            row = await self.connection.fetch_one(query, (guild_id,))
        return row["count"] if row else 0

    async def delete_page(self, guild_id: str, path: str) -> bool:
        """Delete a wiki page."""
        # Delete from FTS first
        fts_query = "DELETE FROM wiki_fts WHERE path = ? AND guild_id = ?"
        await self.connection.execute(fts_query, (path, guild_id))

        # Delete from main table
        query = "DELETE FROM wiki_pages WHERE guild_id = ? AND path = ?"
        cursor = await self.connection.execute(query, (guild_id, path))
        return cursor.rowcount > 0

    async def search_pages(
        self,
        guild_id: str,
        query_text: str,
        limit: int = 10,
    ) -> List[WikiPageSummary]:
        """Full-text search across wiki pages using FTS5."""
        query = """
        SELECT wp.id, wp.path, wp.title, wp.topics, wp.updated_at,
               wp.inbound_links, wp.confidence,
               snippet(wiki_fts, 2, '<mark>', '</mark>', '...', 32) as snippet
        FROM wiki_fts wf
        JOIN wiki_pages wp ON wf.path = wp.path AND wf.guild_id = wp.guild_id
        WHERE wf.guild_id = ? AND wiki_fts MATCH ?
        ORDER BY bm25(wiki_fts)
        LIMIT ?
        """
        rows = await self.connection.fetch_all(query, (guild_id, query_text, limit))
        return [self._row_to_page_summary(row) for row in rows]

    # -------------------------------------------------------------------------
    # Links
    # -------------------------------------------------------------------------

    async def save_link(self, link: WikiLink) -> None:
        """Save a link between wiki pages."""
        query = """
        INSERT OR REPLACE INTO wiki_links (from_page, to_page, guild_id, link_text, created_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        """
        await self.connection.execute(
            query, (link.from_page, link.to_page, link.guild_id, link.link_text)
        )

    async def get_links_from(self, guild_id: str, page_path: str) -> List[WikiLink]:
        """Get all outbound links from a page."""
        query = "SELECT * FROM wiki_links WHERE guild_id = ? AND from_page = ?"
        rows = await self.connection.fetch_all(query, (guild_id, page_path))
        return [self._row_to_link(row) for row in rows]

    async def get_links_to(self, guild_id: str, page_path: str) -> List[WikiLink]:
        """Get all inbound links to a page."""
        query = "SELECT * FROM wiki_links WHERE guild_id = ? AND to_page = ?"
        rows = await self.connection.fetch_all(query, (guild_id, page_path))
        return [self._row_to_link(row) for row in rows]

    async def delete_links_from(self, guild_id: str, page_path: str) -> int:
        """Delete all outbound links from a page."""
        query = "DELETE FROM wiki_links WHERE guild_id = ? AND from_page = ?"
        cursor = await self.connection.execute(query, (guild_id, page_path))
        return cursor.rowcount

    async def find_orphan_pages(self, guild_id: str) -> List[WikiPageSummary]:
        """Find pages with no inbound links (orphans)."""
        query = """
        SELECT wp.id, wp.path, wp.title, wp.topics, wp.updated_at,
               wp.inbound_links, wp.confidence
        FROM wiki_pages wp
        WHERE wp.guild_id = ? AND wp.inbound_links = 0
        AND wp.path NOT IN ('index.md', 'log.md')
        ORDER BY wp.updated_at DESC
        """
        rows = await self.connection.fetch_all(query, (guild_id,))
        return [self._row_to_page_summary(row) for row in rows]

    # -------------------------------------------------------------------------
    # Log
    # -------------------------------------------------------------------------

    async def append_log(
        self,
        guild_id: str,
        operation: WikiOperation,
        details: Dict[str, Any],
        agent_id: Optional[str] = None,
    ) -> int:
        """Append an entry to the operation log."""
        query = """
        INSERT INTO wiki_log (guild_id, operation, details, agent_id, timestamp)
        VALUES (?, ?, ?, ?, datetime('now'))
        """
        cursor = await self.connection.execute(
            query, (guild_id, operation.value, json.dumps(details), agent_id)
        )
        return cursor.lastrowid

    async def get_recent_log(
        self,
        guild_id: str,
        operation: Optional[WikiOperation] = None,
        limit: int = 50,
    ) -> List[WikiLogEntry]:
        """Get recent log entries."""
        if operation:
            query = """
            SELECT * FROM wiki_log
            WHERE guild_id = ? AND operation = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """
            rows = await self.connection.fetch_all(
                query, (guild_id, operation.value, limit)
            )
        else:
            query = """
            SELECT * FROM wiki_log
            WHERE guild_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """
            rows = await self.connection.fetch_all(query, (guild_id, limit))

        return [self._row_to_log_entry(row) for row in rows]

    # -------------------------------------------------------------------------
    # Contradictions
    # -------------------------------------------------------------------------

    async def save_contradiction(
        self,
        guild_id: str,
        page_a: str,
        page_b: str,
        claim_a: str,
        claim_b: str,
    ) -> int:
        """Save a detected contradiction."""
        query = """
        INSERT INTO wiki_contradictions (guild_id, page_a, page_b, claim_a, claim_b, detected_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        """
        cursor = await self.connection.execute(
            query, (guild_id, page_a, page_b, claim_a, claim_b)
        )
        return cursor.lastrowid

    async def get_unresolved_contradictions(
        self, guild_id: str, limit: int = 50
    ) -> List[WikiContradiction]:
        """Get unresolved contradictions for review."""
        query = """
        SELECT * FROM wiki_contradictions
        WHERE guild_id = ? AND resolved_at IS NULL
        ORDER BY detected_at DESC
        LIMIT ?
        """
        rows = await self.connection.fetch_all(query, (guild_id, limit))
        return [self._row_to_contradiction(row) for row in rows]

    async def resolve_contradiction(
        self, contradiction_id: int, resolution: str
    ) -> bool:
        """Mark a contradiction as resolved."""
        query = """
        UPDATE wiki_contradictions
        SET resolved_at = datetime('now'), resolution = ?
        WHERE id = ?
        """
        cursor = await self.connection.execute(query, (resolution, contradiction_id))
        return cursor.rowcount > 0

    # -------------------------------------------------------------------------
    # Sources
    # -------------------------------------------------------------------------

    async def save_source(self, source: WikiSource) -> str:
        """Save an immutable source document."""
        if not source.id:
            source.id = str(uuid.uuid4())

        query = """
        INSERT INTO wiki_sources (id, guild_id, source_type, title, content, metadata, ingested_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(id) DO NOTHING
        """
        await self.connection.execute(
            query,
            (
                source.id,
                source.guild_id,
                source.source_type.value,
                source.title,
                source.content,
                json.dumps(source.metadata),
            ),
        )
        return source.id

    async def get_source(self, source_id: str) -> Optional[WikiSource]:
        """Get a source document by ID."""
        query = "SELECT * FROM wiki_sources WHERE id = ?"
        row = await self.connection.fetch_one(query, (source_id,))
        return self._row_to_source(row) if row else None

    async def list_sources(
        self,
        guild_id: str,
        source_type: Optional[WikiSourceType] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[WikiSource]:
        """List source documents."""
        if source_type:
            query = """
            SELECT * FROM wiki_sources
            WHERE guild_id = ? AND source_type = ?
            ORDER BY ingested_at DESC
            LIMIT ? OFFSET ?
            """
            rows = await self.connection.fetch_all(
                query, (guild_id, source_type.value, limit, offset)
            )
        else:
            query = """
            SELECT * FROM wiki_sources
            WHERE guild_id = ?
            ORDER BY ingested_at DESC
            LIMIT ? OFFSET ?
            """
            rows = await self.connection.fetch_all(query, (guild_id, limit, offset))

        return [self._row_to_source(row) for row in rows]

    async def count_sources(self, guild_id: str) -> int:
        """Count source documents for a guild."""
        query = "SELECT COUNT(*) as count FROM wiki_sources WHERE guild_id = ?"
        row = await self.connection.fetch_one(query, (guild_id,))
        return row["count"] if row else 0

    # -------------------------------------------------------------------------
    # Navigation Tree
    # -------------------------------------------------------------------------

    async def get_tree(self, guild_id: str) -> WikiTree:
        """Build the navigation tree for the wiki."""
        tree = WikiTree(guild_id=guild_id)

        # Count pages per category
        query = """
        SELECT
            CASE
                WHEN path LIKE 'topics/%' THEN 'topics'
                WHEN path LIKE 'decisions/%' THEN 'decisions'
                WHEN path LIKE 'processes/%' THEN 'processes'
                WHEN path LIKE 'experts/%' THEN 'experts'
                WHEN path LIKE 'questions/%' THEN 'questions'
                ELSE 'other'
            END as category,
            COUNT(*) as count
        FROM wiki_pages
        WHERE guild_id = ?
        GROUP BY category
        """
        rows = await self.connection.fetch_all(query, (guild_id,))

        for row in rows:
            cat = row["category"]
            count = row["count"]
            if cat == "topics":
                tree.topics.page_count = count
            elif cat == "decisions":
                tree.decisions.page_count = count
            elif cat == "processes":
                tree.processes.page_count = count
            elif cat == "experts":
                tree.experts.page_count = count
            elif cat == "questions":
                tree.questions.page_count = count

        # Build child nodes for each category
        for category, node in [
            ("topics", tree.topics),
            ("decisions", tree.decisions),
            ("processes", tree.processes),
            ("experts", tree.experts),
            ("questions", tree.questions),
        ]:
            pages_query = """
            SELECT path, title FROM wiki_pages
            WHERE guild_id = ? AND path LIKE ?
            ORDER BY title
            """
            pages = await self.connection.fetch_all(
                pages_query, (guild_id, f"{category}/%")
            )
            for page in pages:
                node.children.append(
                    WikiTreeNode(path=page["path"], title=page["title"])
                )

        return tree

    # -------------------------------------------------------------------------
    # Source References
    # -------------------------------------------------------------------------

    async def find_pages_by_source(
        self, guild_id: str, source_id: str
    ) -> List[WikiPageSummary]:
        """Find all pages that reference a specific source."""
        # source_refs is stored as JSON array, use JSON functions to search
        query = """
        SELECT id, path, title, topics, updated_at, inbound_links, confidence
        FROM wiki_pages
        WHERE guild_id = ?
        AND source_refs LIKE ?
        ORDER BY updated_at DESC
        """
        # Use LIKE with the source_id wrapped to match JSON array elements
        rows = await self.connection.fetch_all(
            query, (guild_id, f'%"{source_id}"%')
        )
        return [self._row_to_page_summary(row) for row in rows]

    # -------------------------------------------------------------------------
    # Recent Changes
    # -------------------------------------------------------------------------

    async def get_recent_changes(
        self, guild_id: str, days: int = 7, limit: int = 50
    ) -> List[WikiChange]:
        """Get recent changes to the wiki by querying recently updated pages."""
        # Query recently updated pages directly instead of relying on log entries
        query = """
        SELECT path, title, updated_at, source_refs
        FROM wiki_pages
        WHERE guild_id = ?
        AND updated_at >= datetime('now', ?)
        ORDER BY updated_at DESC
        LIMIT ?
        """
        rows = await self.connection.fetch_all(
            query, (guild_id, f"-{days} days", limit)
        )

        changes = []
        for row in rows:
            source_refs = json.loads(row["source_refs"]) if row["source_refs"] else []
            changes.append(
                WikiChange(
                    page_path=row["path"],
                    page_title=row["title"],
                    operation="update",
                    changed_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.utcnow(),
                    source_id=source_refs[-1] if source_refs else None,
                    agent_id="wiki-ingest-agent",
                )
            )
        return changes

    # -------------------------------------------------------------------------
    # Synthesis (ADR-063)
    # -------------------------------------------------------------------------

    async def save_synthesis(
        self,
        guild_id: str,
        path: str,
        synthesis: str,
        source_count: int,
    ) -> bool:
        """Save synthesis for a wiki page."""
        query = """
        UPDATE wiki_pages
        SET synthesis = ?,
            synthesis_updated_at = datetime('now'),
            synthesis_source_count = ?
        WHERE guild_id = ? AND path = ?
        """
        result = await self.connection.execute(query, (synthesis, source_count, guild_id, path))
        return result.rowcount > 0 if hasattr(result, 'rowcount') else True

    # -------------------------------------------------------------------------
    # Clear Wiki
    # -------------------------------------------------------------------------

    async def clear_wiki(self, guild_id: str) -> dict:
        """Clear all wiki data for a guild. Returns counts of deleted items."""
        # Count before deleting
        pages_count = await self.count_pages(guild_id)
        sources_count = await self.count_sources(guild_id)

        # Delete in order to respect any implicit relationships
        await self.connection.execute(
            "DELETE FROM wiki_fts WHERE guild_id = ?", (guild_id,)
        )
        await self.connection.execute(
            "DELETE FROM wiki_links WHERE guild_id = ?", (guild_id,)
        )
        await self.connection.execute(
            "DELETE FROM wiki_contradictions WHERE guild_id = ?", (guild_id,)
        )
        await self.connection.execute(
            "DELETE FROM wiki_log WHERE guild_id = ?", (guild_id,)
        )
        await self.connection.execute(
            "DELETE FROM wiki_pages WHERE guild_id = ?", (guild_id,)
        )
        await self.connection.execute(
            "DELETE FROM wiki_sources WHERE guild_id = ?", (guild_id,)
        )

        return {"pages_deleted": pages_count, "sources_deleted": sources_count}

    # -------------------------------------------------------------------------
    # Link Count Updates
    # -------------------------------------------------------------------------

    async def update_link_counts(self, guild_id: str) -> None:
        """Recalculate inbound/outbound link counts for all pages."""
        # Update outbound counts
        await self.connection.execute(
            """
            UPDATE wiki_pages SET outbound_links = (
                SELECT COUNT(*) FROM wiki_links
                WHERE wiki_links.guild_id = wiki_pages.guild_id
                AND wiki_links.from_page = wiki_pages.path
            )
            WHERE guild_id = ?
            """,
            (guild_id,),
        )

        # Update inbound counts
        await self.connection.execute(
            """
            UPDATE wiki_pages SET inbound_links = (
                SELECT COUNT(*) FROM wiki_links
                WHERE wiki_links.guild_id = wiki_pages.guild_id
                AND wiki_links.to_page = wiki_pages.path
            )
            WHERE guild_id = ?
            """,
            (guild_id,),
        )

    # -------------------------------------------------------------------------
    # Row Converters
    # -------------------------------------------------------------------------

    def _row_to_page(self, row: Dict[str, Any]) -> WikiPage:
        """Convert database row to WikiPage."""
        return WikiPage(
            id=row["id"],
            guild_id=row["guild_id"],
            path=row["path"],
            title=row["title"],
            content=row["content"],
            topics=json.loads(row["topics"]) if row["topics"] else [],
            source_refs=json.loads(row["source_refs"]) if row["source_refs"] else [],
            inbound_links=row["inbound_links"],
            outbound_links=row["outbound_links"],
            confidence=row["confidence"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
            # ADR-063: Synthesis fields
            synthesis=row.get("synthesis"),
            synthesis_updated_at=datetime.fromisoformat(row["synthesis_updated_at"]) if row.get("synthesis_updated_at") else None,
            synthesis_source_count=row.get("synthesis_source_count", 0) or 0,
        )

    def _row_to_page_summary(self, row: Dict[str, Any]) -> WikiPageSummary:
        """Convert database row to WikiPageSummary."""
        return WikiPageSummary(
            id=row["id"],
            path=row["path"],
            title=row["title"],
            topics=json.loads(row["topics"]) if row["topics"] else [],
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
            inbound_links=row.get("inbound_links", 0),
            confidence=row.get("confidence", 100),
        )

    def _row_to_link(self, row: Dict[str, Any]) -> WikiLink:
        """Convert database row to WikiLink."""
        return WikiLink(
            from_page=row["from_page"],
            to_page=row["to_page"],
            guild_id=row["guild_id"],
            link_text=row.get("link_text"),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        )

    def _row_to_log_entry(self, row: Dict[str, Any]) -> WikiLogEntry:
        """Convert database row to WikiLogEntry."""
        return WikiLogEntry(
            id=row["id"],
            guild_id=row["guild_id"],
            operation=WikiOperation(row["operation"]),
            details=json.loads(row["details"]) if row["details"] else {},
            agent_id=row.get("agent_id"),
            timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else None,
        )

    def _row_to_contradiction(self, row: Dict[str, Any]) -> WikiContradiction:
        """Convert database row to WikiContradiction."""
        return WikiContradiction(
            id=row["id"],
            guild_id=row["guild_id"],
            page_a=row["page_a"],
            page_b=row["page_b"],
            claim_a=row["claim_a"],
            claim_b=row["claim_b"],
            detected_at=datetime.fromisoformat(row["detected_at"]) if row["detected_at"] else None,
            resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
            resolution=row.get("resolution"),
        )

    def _row_to_source(self, row: Dict[str, Any]) -> WikiSource:
        """Convert database row to WikiSource."""
        return WikiSource(
            id=row["id"],
            guild_id=row["guild_id"],
            source_type=WikiSourceType(row["source_type"]),
            content=row["content"],
            title=row.get("title"),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            ingested_at=datetime.fromisoformat(row["ingested_at"]) if row["ingested_at"] else None,
        )
