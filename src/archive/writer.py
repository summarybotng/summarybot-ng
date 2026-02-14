"""
Markdown file writer for archive summaries.

Generates human-readable Markdown files with platform-aware templates.
"""

import hashlib
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict, Any

from .models import (
    SourceType,
    ArchiveSource,
    PeriodInfo,
    SummaryMetadata,
    SummaryStatistics,
    GenerationInfo,
    BackfillInfo,
    SummaryStatus,
)

logger = logging.getLogger(__name__)


class SummaryWriter:
    """
    Writes summary files to the archive.

    Handles Markdown generation and metadata companion files.
    """

    def __init__(self, archive_root: Path):
        """
        Initialize summary writer.

        Args:
            archive_root: Root path of the archive
        """
        self.archive_root = archive_root

    def write_summary(
        self,
        source: ArchiveSource,
        period: PeriodInfo,
        content: str,
        statistics: SummaryStatistics,
        generation: GenerationInfo,
        is_backfill: bool = False,
        backfill_reason: Optional[str] = None,
        summary_id: Optional[str] = None,
    ) -> Path:
        """
        Write a summary to the archive.

        Args:
            source: Source information
            period: Time period for the summary
            content: Summary content (raw from LLM)
            statistics: Message statistics
            generation: Generation information
            is_backfill: Whether this is a backfill
            backfill_reason: Reason for backfill
            summary_id: Optional summary ID

        Returns:
            Path to the written summary file
        """
        # Generate summary ID if not provided
        if not summary_id:
            import uuid
            summary_id = f"sum_{uuid.uuid4().hex[:12]}"

        # Determine output paths
        summary_dir = source.get_archive_path(self.archive_root)
        date_dir = summary_dir / period.start.strftime("%Y") / period.start.strftime("%m")
        date_dir.mkdir(parents=True, exist_ok=True)

        filename = self._generate_filename(period)
        md_path = date_dir / f"{filename}.md"
        meta_path = date_dir / f"{filename}.meta.json"

        # Generate full Markdown content
        full_content = self._generate_markdown(
            source=source,
            period=period,
            content=content,
            statistics=statistics,
            generation=generation,
        )

        # Write Markdown file
        md_path.write_text(full_content)
        logger.info(f"Wrote summary: {md_path}")

        # Calculate content checksum
        content_checksum = f"sha256:{hashlib.sha256(full_content.encode()).hexdigest()[:16]}"

        # Create and write metadata
        metadata = SummaryMetadata(
            summary_id=summary_id,
            generated_at=datetime.utcnow(),
            period=period,
            source=source,
            status=SummaryStatus.COMPLETE,
            statistics=statistics,
            generation=generation,
            backfill=BackfillInfo(
                is_backfill=is_backfill,
                backfilled_at=datetime.utcnow() if is_backfill else None,
                reason=backfill_reason,
            ) if is_backfill else None,
            content_checksum=content_checksum,
            references_validated=False,  # TODO: Validate references
        )

        metadata.save(meta_path)
        logger.debug(f"Wrote metadata: {meta_path}")

        return md_path

    def write_incomplete_marker(
        self,
        source: ArchiveSource,
        period: PeriodInfo,
        reason_code: str,
        reason_message: str,
        details: Optional[Dict[str, Any]] = None,
        backfill_eligible: bool = True,
    ) -> Path:
        """
        Write a marker file for an incomplete summary.

        Args:
            source: Source information
            period: Time period
            reason_code: Incomplete reason code
            reason_message: Human-readable message
            details: Additional details
            backfill_eligible: Whether backfill can fix this

        Returns:
            Path to the marker file
        """
        from .models import IncompleteInfo

        # Determine output path
        summary_dir = source.get_archive_path(self.archive_root)
        date_dir = summary_dir / period.start.strftime("%Y") / period.start.strftime("%m")
        date_dir.mkdir(parents=True, exist_ok=True)

        filename = self._generate_filename(period)
        meta_path = date_dir / f"{filename}.meta.json"

        # Create metadata with incomplete status
        metadata = SummaryMetadata(
            summary_id=None,
            generated_at=None,
            period=period,
            source=source,
            status=SummaryStatus.INCOMPLETE,
            incomplete_reason=IncompleteInfo(
                code=reason_code,
                message=reason_message,
                details=details or {},
            ),
            backfill_eligible=backfill_eligible,
        )

        metadata.save(meta_path)
        logger.info(f"Wrote incomplete marker: {meta_path}")

        return meta_path

    def _generate_filename(self, period: PeriodInfo) -> str:
        """Generate filename based on period."""
        start_date = period.start.date() if isinstance(period.start, datetime) else period.start

        # Daily
        duration = period.duration_hours
        if duration <= 24:
            return f"{start_date.isoformat()}_daily"

        # Weekly (7 days)
        elif duration <= 168:
            year, week, _ = start_date.isocalendar()
            return f"{year}-W{week:02d}_weekly"

        # Monthly
        elif duration <= 744:
            return f"{start_date.strftime('%Y-%m')}_monthly"

        # Custom range
        else:
            end_date = period.end.date() if isinstance(period.end, datetime) else period.end
            return f"{start_date.isoformat()}_to_{end_date.isoformat()}"

    def _generate_markdown(
        self,
        source: ArchiveSource,
        period: PeriodInfo,
        content: str,
        statistics: SummaryStatistics,
        generation: GenerationInfo,
    ) -> str:
        """Generate full Markdown content with header and footer."""

        # Format header based on source type
        header = self._generate_header(source, period, statistics)

        # Format footer
        footer = self._generate_footer(generation)

        return f"{header}\n---\n\n{content}\n\n---\n\n{footer}"

    def _generate_header(
        self,
        source: ArchiveSource,
        period: PeriodInfo,
        statistics: SummaryStatistics,
    ) -> str:
        """Generate platform-aware header."""

        # Determine title and platform info
        if source.source_type == SourceType.DISCORD:
            title = f"Daily Summary: {source.server_name}"
            platform_info = f"**Server:** {source.server_name}"
            if source.channel_name:
                platform_info += f"\n**Channel:** #{source.channel_name}"
        elif source.source_type == SourceType.WHATSAPP:
            title = f"Daily Summary: {source.server_name}"
            platform_info = f"**Group:** {source.server_name}"
        elif source.source_type == SourceType.SLACK:
            title = f"Daily Summary: {source.server_name}"
            platform_info = f"**Workspace:** {source.server_name}"
            if source.channel_name:
                platform_info += f"\n**Channel:** #{source.channel_name}"
        elif source.source_type == SourceType.TELEGRAM:
            title = f"Daily Summary: {source.server_name}"
            platform_info = f"**Chat:** {source.server_name}"
        else:
            title = f"Daily Summary: {source.server_name}"
            platform_info = f"**Source:** {source.server_name}"

        # Format date
        start_date = period.start
        if isinstance(start_date, datetime):
            date_str = start_date.strftime("%Y-%m-%d (%A)")
            time_range = f"{start_date.strftime('%H:%M')} — {period.end.strftime('%H:%M')}"
        else:
            date_str = start_date.isoformat()
            time_range = "00:00 — 23:59"

        # Build header
        header_lines = [
            f"# {title}",
            "",
            f"**Platform:** {source.source_type.value.capitalize()}",
            platform_info,
            f"**Date:** {date_str}",
            f"**Timezone:** {period.timezone}",
            f"**Period:** {time_range}",
            f"**Messages:** {statistics.message_count} from {statistics.participant_count} participants",
        ]

        return "\n".join(header_lines)

    def _generate_footer(self, generation: GenerationInfo) -> str:
        """Generate summary footer."""
        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        return (
            f"*Generated by SummaryBot-NG on {timestamp}*\n"
            f"*Prompt version: {generation.prompt_version} ({generation.prompt_checksum})*\n"
            f"*Model: {generation.model} | Cost: ${generation.cost_usd:.4f}*"
        )


def get_summary_path(
    archive_root: Path,
    source: ArchiveSource,
    target_date: date,
) -> Path:
    """
    Get the expected path for a summary file.

    Args:
        archive_root: Root path of the archive
        source: Source information
        target_date: Date of the summary

    Returns:
        Expected path to the summary .md file
    """
    summary_dir = source.get_archive_path(archive_root)
    return summary_dir / str(target_date.year) / f"{target_date.month:02d}" / f"{target_date.isoformat()}_daily.md"


def summary_exists(
    archive_root: Path,
    source: ArchiveSource,
    target_date: date,
) -> bool:
    """
    Check if a summary exists for a date.

    Args:
        archive_root: Root path of the archive
        source: Source information
        target_date: Date to check

    Returns:
        True if summary exists
    """
    md_path = get_summary_path(archive_root, source, target_date)
    return md_path.exists()
