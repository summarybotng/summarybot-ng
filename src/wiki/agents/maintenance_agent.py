"""
Wiki Maintenance Agent (ADR-056).

Performs periodic wiki hygiene operations:
- Find contradictions between pages
- Find orphaned pages
- Find missing cross-references
- Find stale content
- Auto-fix what can be fixed
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from ..models import WikiPageSummary, WikiContradiction, WikiOperation
from ...data.sqlite.wiki_repository import SQLiteWikiRepository

logger = logging.getLogger(__name__)


@dataclass
class LintIssue:
    """A wiki quality issue."""
    type: str  # contradiction, orphan, missing_link, stale
    severity: str  # high, medium, low
    page_path: str
    description: str
    auto_fixable: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LintResult:
    """Result of a lint operation."""
    issues: List[LintIssue] = field(default_factory=list)
    auto_fixed: List[LintIssue] = field(default_factory=list)
    needs_review: List[LintIssue] = field(default_factory=list)


class WikiMaintenanceAgent:
    """
    Audits and maintains wiki quality.

    Per ADR-056:
    - Find contradictions between pages
    - Find orphaned pages (no inbound links)
    - Find missing cross-references
    - Find stale content (not updated in 30+ days)
    - Auto-fix what we can
    - Flag remaining issues for human review
    """

    def __init__(self, repository: SQLiteWikiRepository, llm_client: Optional[Any] = None):
        """
        Initialize the maintenance agent.

        Args:
            repository: Wiki repository for data access
            llm_client: Optional LLM client for semantic analysis
        """
        self.repository = repository
        self.llm_client = llm_client

    async def lint(self, guild_id: str) -> LintResult:
        """
        Run lint operations on the wiki.

        Args:
            guild_id: Guild ID

        Returns:
            LintResult with issues found, fixed, and needing review
        """
        result = LintResult()

        # 1. Find orphaned pages
        orphan_issues = await self._find_orphans(guild_id)
        result.issues.extend(orphan_issues)

        # 2. Find stale content
        stale_issues = await self._find_stale_content(guild_id)
        result.issues.extend(stale_issues)

        # 3. Get existing contradictions
        contradiction_issues = await self._get_contradictions(guild_id)
        result.issues.extend(contradiction_issues)

        # 4. Auto-fix what we can
        for issue in result.issues:
            if issue.auto_fixable:
                fixed = await self._auto_fix(guild_id, issue)
                if fixed:
                    result.auto_fixed.append(issue)
                else:
                    result.needs_review.append(issue)
            else:
                result.needs_review.append(issue)

        # 5. Log the operation
        await self.repository.append_log(
            guild_id=guild_id,
            operation=WikiOperation.LINT,
            details={
                "issues_found": len(result.issues),
                "auto_fixed": len(result.auto_fixed),
                "needs_review": len(result.needs_review),
                "issue_types": {
                    "orphans": len(orphan_issues),
                    "stale": len(stale_issues),
                    "contradictions": len(contradiction_issues),
                },
            },
            agent_id="wiki-maintenance-agent",
        )

        return result

    async def _find_orphans(self, guild_id: str) -> List[LintIssue]:
        """Find pages with no inbound links."""
        orphans = await self.repository.find_orphan_pages(guild_id)

        issues = []
        for page in orphans:
            issues.append(LintIssue(
                type="orphan",
                severity="low",
                page_path=page.path,
                description=f"Page '{page.title}' has no inbound links",
                auto_fixable=True,  # Can add to index
                details={"title": page.title, "updated_at": page.updated_at.isoformat() if page.updated_at else None},
            ))

        return issues

    async def _find_stale_content(self, guild_id: str, days: int = 30) -> List[LintIssue]:
        """Find content not updated recently."""
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Get all pages and filter by update time
        pages = await self.repository.list_pages(guild_id, limit=500)

        issues = []
        for page in pages:
            if page.updated_at and page.updated_at < cutoff:
                days_stale = (datetime.utcnow() - page.updated_at).days
                issues.append(LintIssue(
                    type="stale",
                    severity="medium" if days_stale > 60 else "low",
                    page_path=page.path,
                    description=f"Page '{page.title}' hasn't been updated in {days_stale} days",
                    auto_fixable=False,  # Needs human review
                    details={"days_stale": days_stale, "last_updated": page.updated_at.isoformat()},
                ))

        return issues

    async def _get_contradictions(self, guild_id: str) -> List[LintIssue]:
        """Get existing unresolved contradictions as issues."""
        contradictions = await self.repository.get_unresolved_contradictions(guild_id)

        issues = []
        for c in contradictions:
            issues.append(LintIssue(
                type="contradiction",
                severity="high",
                page_path=c.page_a,
                description=f"Contradiction between '{c.page_a}' and '{c.page_b}'",
                auto_fixable=False,  # Needs human resolution
                details={
                    "page_b": c.page_b,
                    "claim_a": c.claim_a,
                    "claim_b": c.claim_b,
                    "detected_at": c.detected_at.isoformat() if c.detected_at else None,
                },
            ))

        return issues

    async def _auto_fix(self, guild_id: str, issue: LintIssue) -> bool:
        """Attempt to auto-fix an issue."""
        if issue.type == "orphan":
            # Add orphan page to index
            return await self._add_to_index(guild_id, issue.page_path)

        return False

    async def _add_to_index(self, guild_id: str, page_path: str) -> bool:
        """Add a page to the wiki index."""
        try:
            # Get or create index page
            index_path = "index.md"
            index_page = await self.repository.get_page(guild_id, index_path)

            if index_page:
                # Add link to orphan page
                page = await self.repository.get_page(guild_id, page_path)
                if page:
                    new_link = f"- [{page.title}]({page_path})\n"
                    if new_link not in index_page.content:
                        index_page.content += f"\n{new_link}"
                        await self.repository.save_page(index_page)

                        # Create link record
                        from ..models import WikiLink
                        link = WikiLink(
                            from_page=index_path,
                            to_page=page_path,
                            guild_id=guild_id,
                            link_text=page.title,
                        )
                        await self.repository.save_link(link)
                        return True

            return False
        except Exception as e:
            logger.warning(f"Failed to add {page_path} to index: {e}")
            return False
