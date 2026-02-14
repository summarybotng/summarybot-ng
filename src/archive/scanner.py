"""
Archive scanner for gap detection and backfill analysis.

Phase 7: Backfill Analysis - Scanner component
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .models import (
    SourceType,
    ArchiveSource,
    SummaryMetadata,
    SummaryStatus,
    PeriodInfo,
)

logger = logging.getLogger(__name__)


@dataclass
class SummaryInfo:
    """Information about a summary in the archive."""
    date: date
    status: SummaryStatus
    prompt_version: Optional[str] = None
    prompt_checksum: Optional[str] = None
    is_backfill_eligible: bool = True
    incomplete_reason: Optional[str] = None
    meta_path: Optional[Path] = None


@dataclass
class GapInfo:
    """Information about a gap in coverage."""
    start_date: date
    end_date: date
    reason: str  # "missing", "failed", "no_messages", "export_unavailable"
    days: int = 0
    backfill_eligible: bool = True

    def __post_init__(self):
        if self.days == 0:
            self.days = (self.end_date - self.start_date).days + 1


@dataclass
class OutdatedInfo:
    """Information about an outdated summary."""
    date: date
    current_version: str
    summary_version: str
    meta_path: Path


@dataclass
class ScanResult:
    """Result of scanning a source."""
    source: ArchiveSource
    total_days: int
    complete: int
    failed: int
    missing: int
    outdated: int
    summaries: List[SummaryInfo] = field(default_factory=list)
    gaps: List[GapInfo] = field(default_factory=list)
    outdated_summaries: List[OutdatedInfo] = field(default_factory=list)
    earliest_date: Optional[date] = None
    latest_date: Optional[date] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_key": self.source.source_key,
            "total_days": self.total_days,
            "complete": self.complete,
            "failed": self.failed,
            "missing": self.missing,
            "outdated": self.outdated,
            "gaps": [
                {
                    "start": g.start_date.isoformat(),
                    "end": g.end_date.isoformat(),
                    "days": g.days,
                    "reason": g.reason,
                    "backfill_eligible": g.backfill_eligible,
                }
                for g in self.gaps
            ],
            "date_range": {
                "earliest": self.earliest_date.isoformat() if self.earliest_date else None,
                "latest": self.latest_date.isoformat() if self.latest_date else None,
            },
        }


class ArchiveScanner:
    """
    Scans archive for gaps and outdated summaries.

    Identifies:
    - Missing summaries (no file exists)
    - Failed summaries (incomplete status)
    - Outdated summaries (old prompt version)
    """

    def __init__(self, archive_root: Path):
        """
        Initialize scanner.

        Args:
            archive_root: Root path of the archive
        """
        self.archive_root = archive_root

    def scan_source(
        self,
        source: ArchiveSource,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        current_prompt_version: Optional[str] = None,
        outdated_threshold: str = "minor",  # "major", "minor", "patch"
    ) -> ScanResult:
        """
        Scan a source for gaps and outdated summaries.

        Args:
            source: Source to scan
            start_date: Start of scan range (default: earliest in archive)
            end_date: End of scan range (default: yesterday)
            current_prompt_version: Current prompt version for outdated detection
            outdated_threshold: Minimum version change to flag as outdated

        Returns:
            Scan result with gaps and outdated info
        """
        archive_path = source.get_archive_path(self.archive_root)

        # Find all existing summaries
        summaries: Dict[date, SummaryInfo] = {}

        if archive_path.exists():
            for meta_path in archive_path.glob("**/*.meta.json"):
                try:
                    info = self._parse_meta_file(meta_path)
                    if info:
                        summaries[info.date] = info
                except Exception as e:
                    logger.warning(f"Failed to parse {meta_path}: {e}")

        # Determine date range
        if summaries:
            dates = list(summaries.keys())
            earliest = start_date or min(dates)
            latest = end_date or min(max(dates), date.today() - timedelta(days=1))
        else:
            earliest = start_date or date.today() - timedelta(days=30)
            latest = end_date or date.today() - timedelta(days=1)

        # Scan each day in range
        complete = 0
        failed = 0
        missing = 0
        outdated = 0
        gaps: List[GapInfo] = []
        outdated_list: List[OutdatedInfo] = []
        gap_start = None

        current = earliest
        while current <= latest:
            if current in summaries:
                info = summaries[current]

                if info.status == SummaryStatus.COMPLETE:
                    complete += 1

                    # Check if outdated
                    if current_prompt_version and info.prompt_version:
                        if self._is_outdated(
                            info.prompt_version,
                            current_prompt_version,
                            outdated_threshold
                        ):
                            outdated += 1
                            outdated_list.append(OutdatedInfo(
                                date=current,
                                current_version=current_prompt_version,
                                summary_version=info.prompt_version,
                                meta_path=info.meta_path,
                            ))

                elif info.status == SummaryStatus.INCOMPLETE:
                    failed += 1
                    # Add to gap if backfill eligible
                    if info.is_backfill_eligible:
                        if gap_start is None:
                            gap_start = current
                else:
                    missing += 1
                    if gap_start is None:
                        gap_start = current

                # Close gap if we have a complete summary
                if info.status == SummaryStatus.COMPLETE and gap_start:
                    gaps.append(GapInfo(
                        start_date=gap_start,
                        end_date=current - timedelta(days=1),
                        reason="failed" if failed > 0 else "missing",
                    ))
                    gap_start = None

            else:
                # No summary exists
                missing += 1
                if gap_start is None:
                    gap_start = current

            current += timedelta(days=1)

        # Close final gap
        if gap_start:
            gaps.append(GapInfo(
                start_date=gap_start,
                end_date=latest,
                reason="missing",
            ))

        return ScanResult(
            source=source,
            total_days=(latest - earliest).days + 1,
            complete=complete,
            failed=failed,
            missing=missing,
            outdated=outdated,
            summaries=list(summaries.values()),
            gaps=gaps,
            outdated_summaries=outdated_list,
            earliest_date=earliest,
            latest_date=latest,
        )

    def scan_all_sources(
        self,
        current_prompt_version: Optional[str] = None,
    ) -> List[ScanResult]:
        """
        Scan all sources in the archive.

        Args:
            current_prompt_version: Current prompt version

        Returns:
            List of scan results
        """
        results = []
        sources_path = self.archive_root / "sources"

        if not sources_path.exists():
            return results

        for source_type_dir in sources_path.iterdir():
            if not source_type_dir.is_dir():
                continue

            try:
                source_type = SourceType(source_type_dir.name)
            except ValueError:
                continue

            for server_dir in source_type_dir.iterdir():
                if not server_dir.is_dir():
                    continue

                # Parse folder name
                folder_name = server_dir.name
                last_underscore = folder_name.rfind('_')
                if last_underscore == -1:
                    continue

                server_name = folder_name[:last_underscore]
                server_id = folder_name[last_underscore + 1:]

                # Check for channels
                channels_dir = server_dir / "channels"
                if channels_dir.exists():
                    for channel_dir in channels_dir.iterdir():
                        if not channel_dir.is_dir():
                            continue

                        channel_folder = channel_dir.name
                        ch_underscore = channel_folder.rfind('_')
                        if ch_underscore == -1:
                            continue

                        channel_name = channel_folder[:ch_underscore]
                        channel_id = channel_folder[ch_underscore + 1:]

                        source = ArchiveSource(
                            source_type=source_type,
                            server_id=server_id,
                            server_name=server_name,
                            channel_id=channel_id,
                            channel_name=channel_name,
                        )
                        results.append(self.scan_source(
                            source,
                            current_prompt_version=current_prompt_version
                        ))
                else:
                    source = ArchiveSource(
                        source_type=source_type,
                        server_id=server_id,
                        server_name=server_name,
                    )
                    results.append(self.scan_source(
                        source,
                        current_prompt_version=current_prompt_version
                    ))

        return results

    def _parse_meta_file(self, meta_path: Path) -> Optional[SummaryInfo]:
        """Parse a metadata file into SummaryInfo."""
        with open(meta_path, 'r') as f:
            data = json.load(f)

        period = data.get("period", {})
        start_str = period.get("start")
        if not start_str:
            return None

        # Parse date from start timestamp
        start_dt = datetime.fromisoformat(start_str)
        summary_date = start_dt.date()

        status = SummaryStatus(data.get("status", "incomplete"))
        generation = data.get("generation", {})
        incomplete = data.get("incomplete_reason", {})

        return SummaryInfo(
            date=summary_date,
            status=status,
            prompt_version=generation.get("prompt_version"),
            prompt_checksum=generation.get("prompt_checksum"),
            is_backfill_eligible=data.get("backfill_eligible", True),
            incomplete_reason=incomplete.get("code") if incomplete else None,
            meta_path=meta_path,
        )

    def _is_outdated(
        self,
        old_version: str,
        new_version: str,
        threshold: str
    ) -> bool:
        """Check if version difference exceeds threshold."""
        try:
            old_parts = [int(x) for x in old_version.split('.')]
            new_parts = [int(x) for x in new_version.split('.')]

            # Pad to 3 parts
            while len(old_parts) < 3:
                old_parts.append(0)
            while len(new_parts) < 3:
                new_parts.append(0)

            if threshold == "major":
                return new_parts[0] > old_parts[0]
            elif threshold == "minor":
                return (new_parts[0] > old_parts[0] or
                        (new_parts[0] == old_parts[0] and new_parts[1] > old_parts[1]))
            else:  # patch
                return new_parts > old_parts

        except (ValueError, AttributeError):
            # Can't parse versions, assume not outdated
            return False

    def get_backfill_candidates(
        self,
        source: ArchiveSource,
        include_failed: bool = True,
        include_outdated: bool = False,
        current_prompt_version: Optional[str] = None,
    ) -> List[date]:
        """
        Get list of dates that need backfill.

        Args:
            source: Source to check
            include_failed: Include failed summaries
            include_outdated: Include outdated summaries
            current_prompt_version: Required if include_outdated=True

        Returns:
            List of dates needing backfill
        """
        result = self.scan_source(
            source,
            current_prompt_version=current_prompt_version if include_outdated else None,
        )

        candidates = []

        # Add missing dates from gaps
        for gap in result.gaps:
            if gap.backfill_eligible:
                current = gap.start_date
                while current <= gap.end_date:
                    candidates.append(current)
                    current += timedelta(days=1)

        # Add outdated dates if requested
        if include_outdated:
            for outdated in result.outdated_summaries:
                if outdated.date not in candidates:
                    candidates.append(outdated.date)

        return sorted(candidates)
