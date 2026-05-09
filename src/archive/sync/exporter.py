"""
Summary exporter for Google Drive sync.

ADR-007.1: Exports stored summaries as markdown (human-readable) and
JSON (complete backup) for Google Drive sync.

ADR-091: Adds period folder organization and configurable export options.
"""

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

from src.models.stored_summary import StoredSummary

logger = logging.getLogger(__name__)


def get_period_folder_name(date: datetime, grouping: str = "week") -> str:
    """
    Generate period folder name from a date.

    ADR-091: Uses date ranges (e.g., '2026-05-05--2026-05-11') for clarity.

    Args:
        date: Date to get period for
        grouping: "week" or "month"

    Returns:
        Folder name like '2026-05-05--2026-05-11'
    """
    if grouping == "week":
        # ISO week: Monday to Sunday
        week_start = date - timedelta(days=date.weekday())
        week_end = week_start + timedelta(days=6)
        return f"{week_start.strftime('%Y-%m-%d')}--{week_end.strftime('%Y-%m-%d')}"
    elif grouping == "month":
        # Full month
        month_start = date.replace(day=1)
        # Get last day of month
        if month_start.month == 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month = month_start.replace(month=month_start.month + 1)
        month_end = next_month - timedelta(days=1)
        return f"{month_start.strftime('%Y-%m-%d')}--{month_end.strftime('%Y-%m-%d')}"
    else:
        # Default to week
        return get_period_folder_name(date, "week")


def generate_filename(summary: StoredSummary, extension: str = "") -> str:
    """
    Generate a consistent filename for a summary.

    Format: {date}_{title_slug}_{id_prefix}
    Example: 2026-05-09_weekly-development-sync_12ab.md

    Args:
        summary: StoredSummary to generate filename for
        extension: File extension (e.g., ".md", ".json")

    Returns:
        Sanitized filename
    """
    # Get date from created_at
    date_str = summary.created_at.strftime("%Y-%m-%d")

    # Slugify title
    title = summary.title or "summary"
    # Remove special characters, replace spaces with hyphens
    title_slug = re.sub(r'[^\w\s-]', '', title.lower())
    title_slug = re.sub(r'[\s_]+', '-', title_slug)
    title_slug = title_slug[:40]  # Limit length

    # Use first 8 chars of ID for uniqueness
    id_prefix = summary.id[:8] if summary.id else "unknown"

    filename = f"{date_str}_{title_slug}_{id_prefix}"

    if extension:
        filename += extension

    return filename


def export_to_markdown(summary: StoredSummary) -> str:
    """
    Export a StoredSummary to rich markdown with YAML frontmatter.

    Creates a human-readable document suitable for viewing in Google Drive
    or any markdown editor. Includes all key fields in structured frontmatter.

    Args:
        summary: StoredSummary to export

    Returns:
        Markdown string with YAML frontmatter
    """
    sr = summary.summary_result

    # Build YAML frontmatter
    frontmatter: Dict[str, Any] = {
        "id": summary.id,
        "title": summary.title,
        "created_at": summary.created_at.isoformat(),
        "source": summary.source.value,
        "guild_id": summary.guild_id,
        "channels": summary.source_channel_ids,
    }

    # Add time range if available
    if sr and sr.start_time and sr.end_time:
        frontmatter["time_range"] = {
            "start": sr.start_time.isoformat() if hasattr(sr.start_time, 'isoformat') else str(sr.start_time),
            "end": sr.end_time.isoformat() if hasattr(sr.end_time, 'isoformat') else str(sr.end_time),
        }

    # Add archive info
    if summary.archive_period:
        frontmatter["archive"] = {
            "period": summary.archive_period,
            "granularity": summary.archive_granularity,
            "source_key": summary.archive_source_key,
        }

    # Add stats
    frontmatter["stats"] = {
        "message_count": sr.message_count if sr else 0,
        "participant_count": len(sr.participants) if sr and sr.participants else 0,
        "key_point_count": len(sr.key_points) if sr and sr.key_points else 0,
        "action_item_count": len(sr.action_items) if sr and sr.action_items else 0,
    }

    # Add metadata
    if sr and sr.metadata:
        frontmatter["generation"] = {
            "model": sr.metadata.get("model_used") or sr.metadata.get("model"),
            "summary_length": sr.metadata.get("summary_length"),
            "perspective": sr.metadata.get("perspective"),
            "grounded": sr.metadata.get("grounded", False),
            "tokens_used": sr.metadata.get("tokens_used"),
        }

    # Add tags and flags
    if summary.tags:
        frontmatter["tags"] = summary.tags
    if summary.is_pinned:
        frontmatter["pinned"] = True
    if summary.contains_sensitive_channels:
        frontmatter["contains_private_channels"] = True
    if summary.continuity_week_number:
        frontmatter["continuity"] = {
            "week_number": summary.continuity_week_number,
            "previous_id": summary.previous_summary_id,
        }

    # Build markdown sections
    sections = []

    # Title
    sections.append(f"# {summary.title or 'Summary'}")
    sections.append("")

    # Summary text
    if sr and sr.summary_text:
        sections.append("## Summary")
        sections.append("")
        sections.append(sr.summary_text)
        sections.append("")

    # Key points
    if sr and sr.key_points:
        sections.append("## Key Points")
        sections.append("")
        for i, point in enumerate(sr.key_points, 1):
            sections.append(f"{i}. {point}")
        sections.append("")

    # Action items
    if sr and sr.action_items:
        sections.append("## Action Items")
        sections.append("")
        for item in sr.action_items:
            priority = item.priority.value if hasattr(item.priority, 'value') else item.priority
            assignee = f" @{item.assignee}" if item.assignee else ""
            checkbox = "[x]" if item.completed else "[ ]"
            priority_label = f" ({priority})" if priority != "medium" else ""
            sections.append(f"- {checkbox} {item.description}{assignee}{priority_label}")
        sections.append("")

    # Participants
    if sr and sr.participants:
        sections.append("## Participants")
        sections.append("")
        sections.append("| Participant | Messages |")
        sections.append("|-------------|----------|")
        for p in sorted(sr.participants, key=lambda x: x.message_count, reverse=True)[:10]:
            sections.append(f"| {p.display_name} | {p.message_count} |")
        if len(sr.participants) > 10:
            sections.append(f"| *...and {len(sr.participants) - 10} more* | |")
        sections.append("")

    # Technical terms
    if sr and sr.technical_terms:
        sections.append("## Technical Terms")
        sections.append("")
        for term in sr.technical_terms[:10]:
            sections.append(f"- **{term.term}**: {term.definition}")
        if len(sr.technical_terms) > 10:
            sections.append(f"- *...and {len(sr.technical_terms) - 10} more*")
        sections.append("")

    # References section (for grounded summaries)
    if sr and hasattr(sr, 'references') and sr.references:
        sections.append("## References")
        sections.append("")
        for ref in sr.references[:20]:
            author = ref.get('author', 'Unknown')
            content = ref.get('content', '')[:100]
            timestamp = ref.get('timestamp', '')
            sections.append(f"- [{ref.get('id', '?')}] **{author}** ({timestamp}): {content}...")
        if len(sr.references) > 20:
            sections.append(f"- *...and {len(sr.references) - 20} more*")
        sections.append("")

    # Footer
    sections.append("---")
    sections.append(f"*Generated by SummaryBot on {summary.created_at.strftime('%Y-%m-%d %H:%M UTC')}*")

    # Combine frontmatter and content
    yaml_frontmatter = _dict_to_yaml(frontmatter)
    markdown_content = "\n".join(sections)

    return f"---\n{yaml_frontmatter}---\n\n{markdown_content}"


def _dict_to_yaml(d: Dict[str, Any], indent: int = 0) -> str:
    """
    Convert a dictionary to YAML format.
    Simple implementation for frontmatter - handles basic types.
    """
    lines = []
    prefix = "  " * indent

    for key, value in d.items():
        if value is None:
            continue
        elif isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            lines.append(_dict_to_yaml(value, indent + 1))
        elif isinstance(value, list):
            if not value:
                continue
            lines.append(f"{prefix}{key}:")
            for item in value:
                if isinstance(item, dict):
                    # First item inline, rest indented
                    lines.append(f"{prefix}  -")
                    lines.append(_dict_to_yaml(item, indent + 2))
                else:
                    lines.append(f"{prefix}  - {_yaml_escape(item)}")
        elif isinstance(value, bool):
            lines.append(f"{prefix}{key}: {str(value).lower()}")
        elif isinstance(value, (int, float)):
            lines.append(f"{prefix}{key}: {value}")
        else:
            lines.append(f"{prefix}{key}: {_yaml_escape(str(value))}")

    return "\n".join(lines)


def _yaml_escape(s: str) -> str:
    """Escape a string for YAML if needed."""
    if not s:
        return '""'
    # Quote if contains special characters
    if any(c in s for c in [':', '#', '{', '}', '[', ']', ',', '&', '*', '?', '|', '-', '<', '>', '=', '!', '%', '@', '`', '"', "'"]):
        return f'"{s.replace(chr(34), chr(92)+chr(34))}"'
    return s


def export_to_json(summary: StoredSummary) -> str:
    """
    Export a StoredSummary to complete JSON format.

    Creates a lossless export suitable for backup/restoration.
    Uses the model's to_dict() method for complete serialization.

    Args:
        summary: StoredSummary to export

    Returns:
        JSON string with all fields
    """
    data = summary.to_dict()

    # Add export metadata
    data["_export"] = {
        "exported_at": datetime.utcnow().isoformat(),
        "format_version": "1.0",
        "exporter": "summarybot-sync",
    }

    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def export_summary(summary: StoredSummary) -> Tuple[str, str, str]:
    """
    Export a summary to both markdown and JSON formats.

    Args:
        summary: StoredSummary to export

    Returns:
        Tuple of (base_filename, markdown_content, json_content)
    """
    base_filename = generate_filename(summary)
    markdown = export_to_markdown(summary)
    json_content = export_to_json(summary)

    return base_filename, markdown, json_content
