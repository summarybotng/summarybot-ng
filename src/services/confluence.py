"""
Confluence Publishing Service for ADR-099/ADR-100: Remote Platform Publishing.

This module handles publishing summaries to Atlassian Confluence using the REST API.
Supports per-tenant (guild) configuration stored in the database.

ADR-100 Enhancements:
- Omit source references (may contain sensitive details)
- Include channel list in content and as page labels
- Parse dates and convert to Confluence date chips
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

import httpx

from ..models.summary import SummaryResult
from src.utils.time import utc_now_naive
from .date_extractor import extract_dates_with_llm, build_adf_content_with_dates

logger = logging.getLogger(__name__)


@dataclass
class ConfluenceConfig:
    """Confluence configuration - can be from environment or per-guild database settings."""
    enabled: bool = False
    base_url: str = ""  # e.g., https://company.atlassian.net
    space_key: str = ""  # e.g., TEAM
    parent_page_id: Optional[str] = None  # Optional parent page for hierarchy
    email: str = ""  # Service account email
    api_token: str = ""  # API token from id.atlassian.com
    page_title_template: str = "{title}"  # Template for page titles
    guild_id: Optional[str] = None  # Guild ID if per-guild config

    def is_configured(self) -> bool:
        """Check if Confluence is properly configured."""
        return bool(
            self.enabled
            and self.base_url
            and self.space_key
            and self.email
            and self.api_token
        )

    @classmethod
    def from_env(cls) -> "ConfluenceConfig":
        """Load configuration from environment variables (global fallback)."""
        return cls(
            enabled=os.getenv("CONFLUENCE_ENABLED", "false").lower() == "true",
            base_url=os.getenv("CONFLUENCE_BASE_URL", "").rstrip("/"),
            space_key=os.getenv("CONFLUENCE_SPACE_KEY", ""),
            parent_page_id=os.getenv("CONFLUENCE_PARENT_PAGE_ID") or None,
            email=os.getenv("CONFLUENCE_EMAIL", ""),
            api_token=os.getenv("CONFLUENCE_API_TOKEN", ""),
        )

    @classmethod
    def from_settings(cls, settings: "ConfluenceSettings") -> "ConfluenceConfig":
        """Create config from database settings.

        Args:
            settings: ConfluenceSettings from repository
        """
        from ..data.sqlite.confluence_repository import ConfluenceSettings
        return cls(
            enabled=settings.enabled,
            base_url=settings.base_url.rstrip("/") if settings.base_url else "",
            space_key=settings.space_key,
            parent_page_id=settings.parent_page_id,
            email=settings.email,
            api_token=settings.api_token,
            page_title_template=settings.page_title_template,
            guild_id=settings.guild_id,
        )


@dataclass
class ConfluencePublishResult:
    """Result of a Confluence publish operation."""
    success: bool
    page_id: Optional[str] = None
    page_url: Optional[str] = None
    page_version: Optional[int] = None
    error: Optional[str] = None
    conflict: bool = False  # True if version conflict detected


class ConfluencePublisher:
    """Handles publishing summaries to Confluence.

    ADR-099: Remote Platform Publishing for Confluence.
    Uses Atlassian Document Format (ADF) for rich content.
    """

    def __init__(self, config: ConfluenceConfig):
        """Initialize publisher with Confluence config.

        Args:
            config: Confluence configuration
        """
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None

    def is_configured(self) -> bool:
        """Check if Confluence publishing is configured."""
        return self.config.is_configured()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=f"{self.config.base_url}/wiki/api/v2",
                auth=(self.config.email, self.config.api_token),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def get_page(self, page_id: str) -> Optional[Dict[str, Any]]:
        """Get a Confluence page by ID.

        Args:
            page_id: Confluence page ID

        Returns:
            Page data dict or None if not found
        """
        try:
            client = await self._get_client()
            response = await client.get(f"/pages/{page_id}")
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            else:
                logger.error(f"Failed to get page {page_id}: {response.status_code} {response.text}")
                return None
        except Exception as e:
            logger.exception(f"Error getting Confluence page {page_id}: {e}")
            return None

    async def publish_summary(
        self,
        summary: SummaryResult,
        title: str,
        existing_page_id: Optional[str] = None,
        existing_version: Optional[int] = None,
        force: bool = False,
        summary_id: Optional[str] = None,
        guild_id: Optional[str] = None,
        channel_names: Optional[List[str]] = None,
        scope_type: Optional[str] = None,
        category_name: Optional[str] = None,
        user_timezone: Optional[str] = None,
        dashboard_base_url: Optional[str] = None,  # ADR-079: tenant-aware URL
    ) -> ConfluencePublishResult:
        """Publish a summary to Confluence.

        Creates a new page or updates an existing one. Supports conflict detection
        when updating - if the page has been edited since last publish, returns
        conflict=True unless force=True.

        ADR-100: Includes channel names as labels and in content,
        parses dates for Confluence date chips.

        Args:
            summary: SummaryResult to publish
            title: Page title
            existing_page_id: If updating, the existing page ID
            existing_version: If updating, the expected page version (for conflict detection)
            force: If True, override conflict detection
            summary_id: Optional summary ID for link back to SummaryBot
            guild_id: Optional guild ID for link back to SummaryBot
            channel_names: ADR-100: List of channel names for labels and content
            scope_type: ADR-100: Summary scope (guild/category/channel)
            category_name: ADR-100: Category name if category-scoped
            user_timezone: User's timezone for footer timestamp (e.g., "America/New_York")

        Returns:
            ConfluencePublishResult with page details or error
        """
        if not self.is_configured():
            return ConfluencePublishResult(
                success=False,
                error="Confluence not configured",
            )

        try:
            client = await self._get_client()

            # ADR-100: Build ADF content with channel info and LLM date extraction
            adf_content = await self._format_adf_content(
                summary=summary,
                summary_id=summary_id,
                guild_id=guild_id,
                channel_names=channel_names,
                user_timezone=user_timezone,
                dashboard_base_url=dashboard_base_url,
            )

            # ADR-100: Generate labels for the page
            labels = self._generate_labels(
                channel_names=channel_names,
                scope_type=scope_type,
                category_name=category_name,
            )

            if existing_page_id:
                # Update existing page
                result = await self._update_page(
                    client=client,
                    page_id=existing_page_id,
                    title=title,
                    adf_content=adf_content,
                    expected_version=existing_version,
                    force=force,
                )
                # Add labels after successful update
                if result.success and result.page_id and labels:
                    await self._set_page_labels(client, result.page_id, labels)
                return result
            else:
                # Create new page
                result = await self._create_page(
                    client=client,
                    title=title,
                    adf_content=adf_content,
                )
                # Add labels after successful creation
                if result.success and result.page_id and labels:
                    await self._set_page_labels(client, result.page_id, labels)
                return result

        except httpx.HTTPStatusError as e:
            logger.exception(f"HTTP error publishing to Confluence: {e}")
            return ConfluencePublishResult(
                success=False,
                error=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            )
        except Exception as e:
            logger.exception(f"Error publishing to Confluence: {e}")
            return ConfluencePublishResult(
                success=False,
                error=str(e),
            )

    async def _create_page(
        self,
        client: httpx.AsyncClient,
        title: str,
        adf_content: Dict[str, Any],
    ) -> ConfluencePublishResult:
        """Create a new Confluence page."""
        payload: Dict[str, Any] = {
            "spaceId": await self._get_space_id(client),
            "status": "current",
            "title": title,
            "body": {
                "representation": "atlas_doc_format",
                "value": json.dumps(adf_content),  # API expects JSON string
            },
        }

        # Add parent page if configured
        if self.config.parent_page_id:
            payload["parentId"] = self.config.parent_page_id

        response = await client.post("/pages", json=payload)

        if response.status_code in (200, 201):
            data = response.json()
            page_url = f"{self.config.base_url}/wiki{data.get('_links', {}).get('webui', '')}"
            logger.info(f"Created Confluence page: {data['id']} - {title}")
            return ConfluencePublishResult(
                success=True,
                page_id=data["id"],
                page_url=page_url,
                page_version=data.get("version", {}).get("number", 1),
            )
        else:
            error_msg = response.text[:500]
            logger.error(f"Failed to create Confluence page: {response.status_code} {error_msg}")
            return ConfluencePublishResult(
                success=False,
                error=f"Failed to create page: {error_msg}",
            )

    async def _update_page(
        self,
        client: httpx.AsyncClient,
        page_id: str,
        title: str,
        adf_content: Dict[str, Any],
        expected_version: Optional[int],
        force: bool,
    ) -> ConfluencePublishResult:
        """Update an existing Confluence page with conflict detection."""
        # First, get current page to check version
        current_page = await self.get_page(page_id)
        if not current_page:
            return ConfluencePublishResult(
                success=False,
                error=f"Page {page_id} not found",
            )

        current_version = current_page.get("version", {}).get("number", 1)

        # Conflict detection: if expected version doesn't match current version
        if expected_version and current_version != expected_version and not force:
            logger.warning(
                f"Confluence conflict detected: expected v{expected_version}, found v{current_version}"
            )
            return ConfluencePublishResult(
                success=False,
                page_id=page_id,
                page_version=current_version,
                error=f"Page was modified (version {current_version}). Use force to override.",
                conflict=True,
            )

        # Update the page
        payload = {
            "id": page_id,
            "status": "current",
            "title": title,
            "body": {
                "representation": "atlas_doc_format",
                "value": json.dumps(adf_content),  # API expects JSON string
            },
            "version": {
                "number": current_version + 1,
                "message": "Updated via SummaryBot",
            },
        }

        response = await client.put(f"/pages/{page_id}", json=payload)

        if response.status_code == 200:
            data = response.json()
            page_url = f"{self.config.base_url}/wiki{data.get('_links', {}).get('webui', '')}"
            logger.info(f"Updated Confluence page: {page_id} to v{current_version + 1}")
            return ConfluencePublishResult(
                success=True,
                page_id=page_id,
                page_url=page_url,
                page_version=current_version + 1,
            )
        elif response.status_code == 409:
            # Version conflict during update
            return ConfluencePublishResult(
                success=False,
                page_id=page_id,
                page_version=current_version,
                error="Concurrent edit detected. Please retry.",
                conflict=True,
            )
        else:
            error_msg = response.text[:500]
            logger.error(f"Failed to update Confluence page: {response.status_code} {error_msg}")
            return ConfluencePublishResult(
                success=False,
                error=f"Failed to update page: {error_msg}",
            )

    async def _get_space_id(self, client: httpx.AsyncClient) -> str:
        """Get the space ID from the space key."""
        response = await client.get(f"/spaces", params={"keys": self.config.space_key})
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            if results:
                return results[0]["id"]
        raise ValueError(f"Space '{self.config.space_key}' not found")

    async def _format_adf_content(
        self,
        summary: SummaryResult,
        summary_id: Optional[str] = None,
        guild_id: Optional[str] = None,
        channel_names: Optional[List[str]] = None,
        user_timezone: Optional[str] = None,
        dashboard_base_url: Optional[str] = None,  # ADR-079: tenant-aware URL
    ) -> Dict[str, Any]:
        """Format summary as Atlassian Document Format (ADF) JSON.

        ADR-099/ADR-100: Creates a rich document with:
        - Info panel with metadata and channel list
        - Summary text with date chips (LLM-extracted)
        - Key points as bullet list
        - Action items as task list
        - Participants in expand section
        - Footer with link back to SummaryBot (in user's timezone)

        NOTE: References are intentionally omitted per ADR-100 (may contain sensitive info).
        """
        content: List[Dict[str, Any]] = []

        # Info panel with metadata (channels now in separate expand section)
        metadata_text = self._build_metadata_text(summary)
        content.append({
            "type": "panel",
            "attrs": {"panelType": "info"},
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": metadata_text}],
                }
            ],
        })

        # Summary text with LLM-based date extraction (ADR-100)
        if summary.summary_text:
            content.append({
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Summary"}],
            })

            # ADR-100: Use LLM to extract dates intelligently
            context_year = summary.end_time.year if summary.end_time else (
                summary.start_time.year if summary.start_time else datetime.utcnow().year
            )
            context_month = summary.end_time.month if summary.end_time else (
                summary.start_time.month if summary.start_time else 6
            )

            # Extract dates from full summary text
            extracted_dates = await extract_dates_with_llm(
                summary.summary_text,
                context_year=context_year,
                context_month=context_month,
            )

            # Build content with date chips
            if extracted_dates:
                # Process full text with dates, then split into paragraphs
                full_content = build_adf_content_with_dates(summary.summary_text, extracted_dates)
                # Wrap in a single paragraph (ADF will handle line breaks)
                content.append({
                    "type": "paragraph",
                    "content": full_content,
                })
            else:
                # No dates extracted - use plain paragraphs
                for para in summary.summary_text.split("\n\n"):
                    if para.strip():
                        content.append({
                            "type": "paragraph",
                            "content": [{"type": "text", "text": para.strip()}],
                        })

        # Key points
        if summary.key_points:
            content.append({
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Key Points"}],
            })
            content.append({
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": point}],
                            }
                        ],
                    }
                    for point in summary.key_points
                ],
            })

        # Action items as task list
        if summary.action_items:
            content.append({
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Action Items"}],
            })
            content.append({
                "type": "taskList",
                "attrs": {"localId": "action-items"},
                "content": [
                    {
                        "type": "taskItem",
                        "attrs": {
                            "localId": f"action-{i}",
                            "state": "TODO",
                        },
                        "content": [
                            {
                                "type": "text",
                                "text": self._format_action_item(item),
                            }
                        ],
                    }
                    for i, item in enumerate(summary.action_items)
                ],
            })

        # Participants in expand section
        if summary.participants:
            content.append({
                "type": "expand",
                "attrs": {"title": f"Participants ({len(summary.participants)})"},
                "content": [
                    {
                        "type": "bulletList",
                        "content": [
                            {
                                "type": "listItem",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": f"{p.display_name} ({p.message_count} messages)",
                                            }
                                        ],
                                    }
                                ],
                            }
                            for p in summary.participants[:20]  # Limit to top 20
                        ],
                    }
                ],
            })

        # ADR-100: Channels in expand section
        if channel_names:
            content.append({
                "type": "expand",
                "attrs": {"title": f"Channels ({len(channel_names)})"},
                "content": [
                    {
                        "type": "bulletList",
                        "content": [
                            {
                                "type": "listItem",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": f"#{name}",
                                            }
                                        ],
                                    }
                                ],
                            }
                            for name in channel_names
                        ],
                    }
                ],
            })

        # ADR-100: References intentionally omitted - may contain sensitive information.
        # Users can view detailed references in SummaryBot via the "View in SummaryBot" link.

        # Footer with generation info and link back to SummaryBot
        content.append({
            "type": "rule",
        })

        # Format timestamp in user's timezone if provided
        now_utc = utc_now_naive()
        if user_timezone:
            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo(user_timezone)
                # Get timezone abbreviation (e.g., "EDT", "PST")
                local_time = now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
                tz_abbrev = local_time.strftime("%Z")
                timestamp_str = local_time.strftime(f"%Y-%m-%d %H:%M {tz_abbrev}")
            except Exception as e:
                logger.warning(f"Failed to convert timezone {user_timezone}: {e}")
                timestamp_str = now_utc.strftime("%Y-%m-%d %H:%M UTC")
        else:
            timestamp_str = now_utc.strftime("%Y-%m-%d %H:%M UTC")

        footer_content: List[Dict[str, Any]] = [
            {
                "type": "text",
                "text": f"Generated by SummaryBot at {timestamp_str}",
                "marks": [{"type": "em"}],
            }
        ]

        # Add link back to SummaryBot if we have the IDs
        if summary_id and guild_id:
            dashboard_url = dashboard_base_url or os.environ.get("DASHBOARD_URL", "https://summarybot.app")
            summary_url = f"{dashboard_url}/guilds/{guild_id}/summaries?view={summary_id}"
            footer_content.append({
                "type": "text",
                "text": " — ",
                "marks": [{"type": "em"}],
            })
            footer_content.append({
                "type": "text",
                "text": "View in SummaryBot",
                "marks": [
                    {"type": "em"},
                    {"type": "link", "attrs": {"href": summary_url}},
                ],
            })

        content.append({
            "type": "paragraph",
            "content": footer_content,
        })

        return {
            "version": 1,
            "type": "doc",
            "content": content,
        }

    def _build_metadata_text(self, summary: SummaryResult) -> str:
        """Build metadata string for info panel."""
        parts = []
        if summary.message_count:
            parts.append(f"{summary.message_count} messages")
        if summary.participants:
            parts.append(f"{len(summary.participants)} participants")
        if summary.start_time and summary.end_time:
            start = summary.start_time.strftime("%b %d, %Y %H:%M")
            end = summary.end_time.strftime("%b %d, %Y %H:%M")
            parts.append(f"{start} - {end} UTC")
        return " | ".join(parts) if parts else "Summary"

    def _format_action_item(self, item) -> str:
        """Format an action item for display."""
        text = item.description if hasattr(item, 'description') else str(item)
        if hasattr(item, 'assignee') and item.assignee:
            text += f" (@{item.assignee})"
        if hasattr(item, 'priority') and item.priority:
            text = f"[{item.priority.upper()}] {text}"
        return text

    # NOTE: _build_text_with_dates removed - now using LLM-based date_extractor.py

    def _generate_labels(
        self,
        channel_names: Optional[List[str]] = None,
        scope_type: Optional[str] = None,
        category_name: Optional[str] = None,
    ) -> List[str]:
        """Generate Confluence labels for the page (ADR-100).

        Args:
            channel_names: List of Discord channel names
            scope_type: Summary scope (guild/category/channel)
            category_name: Category name if category-scoped

        Returns:
            List of labels (max 10 per Confluence best practice)
        """
        labels = ["summarybot"]  # Always include for filtering

        if channel_names:
            for name in channel_names[:5]:  # Limit to avoid too many labels
                sanitized = self._sanitize_label(name)
                if sanitized:
                    labels.append(f"channel-{sanitized}")

        if scope_type:
            labels.append(f"scope-{scope_type}")

        if category_name:
            sanitized = self._sanitize_label(category_name)
            if sanitized:
                labels.append(f"category-{sanitized}")

        return labels[:10]  # Confluence best practice: limit labels

    def _sanitize_label(self, name: str) -> str:
        """Sanitize a name for use as a Confluence label (ADR-100).

        Confluence labels must be lowercase, no spaces, limited special chars.
        """
        # Lowercase, replace non-alphanumeric with hyphen, collapse multiple hyphens
        sanitized = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
        # Collapse multiple hyphens
        sanitized = re.sub(r'-+', '-', sanitized)
        return sanitized[:40] if sanitized else ""

    async def _set_page_labels(
        self,
        client: httpx.AsyncClient,
        page_id: str,
        labels: List[str],
    ) -> bool:
        """Set labels on a Confluence page (ADR-100).

        NOTE: Must use v1 API - v2 API doesn't support adding labels yet.
        See: https://community.atlassian.com/forums/Confluence-questions/Adding-a-label-to-a-page-via-REST-API-v2/qaq-p/3012451

        Args:
            client: HTTP client
            page_id: Confluence page ID
            labels: List of label names

        Returns:
            True if successful
        """
        try:
            # Must use v1 API for labels - v2 doesn't support it
            # v1 endpoint: POST /wiki/rest/api/content/{id}/label
            v1_url = f"{self.config.base_url}/wiki/rest/api/content/{page_id}/label"
            payload = [{"prefix": "global", "name": label} for label in labels]

            # Create a separate request since we need different base URL
            async with httpx.AsyncClient(
                auth=(self.config.email, self.config.api_token),
                headers={"Content-Type": "application/json"},
                timeout=30.0,
            ) as v1_client:
                response = await v1_client.post(v1_url, json=payload)

                if response.status_code in (200, 201):
                    logger.info(f"Added labels to page {page_id}: {labels}")
                    return True
                else:
                    # Labels are non-critical, just log warning
                    logger.warning(
                        f"Failed to add labels to page {page_id}: "
                        f"{response.status_code} {response.text[:200]}"
                    )
                    return False
        except Exception as e:
            logger.warning(f"Error adding labels to page {page_id}: {e}")
            return False


# Module-level cache for per-guild publishers
_confluence_services: Dict[str, ConfluencePublisher] = {}
_fallback_service: Optional[ConfluencePublisher] = None


def get_confluence_service() -> ConfluencePublisher:
    """Get the global fallback Confluence publisher.

    This uses environment variables and is used when no per-guild
    configuration is available.

    Returns:
        ConfluencePublisher instance
    """
    global _fallback_service
    if _fallback_service is None:
        config = ConfluenceConfig.from_env()
        _fallback_service = ConfluencePublisher(config)
        logger.info(
            f"Confluence fallback service initialized: enabled={config.enabled}, "
            f"url={config.base_url}, space={config.space_key}, "
            f"configured={config.is_configured()}"
        )
    return _fallback_service


async def get_confluence_service_for_guild(guild_id: str) -> ConfluencePublisher:
    """Get the Confluence publisher for a specific guild.

    Loads per-guild configuration from database, falling back to
    environment variables if no guild-specific config exists.

    Args:
        guild_id: Discord guild ID

    Returns:
        ConfluencePublisher configured for the guild
    """
    global _confluence_services

    # Check cache first
    if guild_id in _confluence_services:
        return _confluence_services[guild_id]

    # Try to load per-guild settings from database
    try:
        from ..data.repositories import get_confluence_repository

        repo = await get_confluence_repository()
        logger.debug(f"Confluence repo for guild {guild_id}: repo={repo is not None}")
        if repo:
            settings = await repo.get_settings(guild_id)
            logger.debug(
                f"Confluence settings for guild {guild_id}: "
                f"settings={settings is not None}, "
                f"enabled={settings.enabled if settings else None}, "
                f"has_token={bool(settings.api_token) if settings else None}, "
                f"is_configured={settings.is_configured() if settings else None}"
            )
            if settings and settings.is_configured():
                config = ConfluenceConfig.from_settings(settings)
                publisher = ConfluencePublisher(config)
                _confluence_services[guild_id] = publisher
                logger.info(
                    f"Confluence service for guild {guild_id}: "
                    f"url={config.base_url}, space={config.space_key}"
                )
                return publisher
            elif settings:
                # Settings exist but not fully configured - log why
                logger.warning(
                    f"Confluence settings for guild {guild_id} incomplete: "
                    f"enabled={settings.enabled}, base_url={bool(settings.base_url)}, "
                    f"space_key={bool(settings.space_key)}, email={bool(settings.email)}, "
                    f"api_token={bool(settings.api_token)}"
                )
    except Exception as e:
        logger.exception(f"Failed to load Confluence settings for guild {guild_id}: {e}")

    # Fall back to global service
    logger.debug(f"Using fallback Confluence service for guild {guild_id}")
    return get_confluence_service()


def clear_guild_confluence_cache(guild_id: str) -> None:
    """Clear cached Confluence publisher for a guild.

    Call this when guild settings are updated to force reload.

    Args:
        guild_id: Discord guild ID
    """
    if guild_id in _confluence_services:
        del _confluence_services[guild_id]
        logger.info(f"Cleared Confluence cache for guild {guild_id}")


def configure_confluence_service(config: ConfluenceConfig) -> ConfluencePublisher:
    """Configure the global fallback Confluence publisher.

    Args:
        config: Confluence configuration

    Returns:
        Configured ConfluencePublisher
    """
    global _fallback_service
    _fallback_service = ConfluencePublisher(config)
    return _fallback_service
