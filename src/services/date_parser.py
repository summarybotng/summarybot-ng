"""
Date parser for Confluence ADF date chips (ADR-100).

Parses dates in summary text and converts them to Confluence date nodes.
"""

import re
import logging
from datetime import datetime, timedelta
from typing import List, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DateMatch:
    """Represents a parsed date in text."""
    start: int  # Start position in text
    end: int  # End position in text
    original: str  # Original matched text
    timestamp: int  # Unix timestamp in milliseconds
    is_range_end: bool = False  # True if this is the end of a range


class DateParser:
    """Parse dates from summary text with year context awareness (ADR-100)."""

    # Month name patterns
    MONTH_PATTERN = r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'

    # Ordinal suffixes
    ORDINAL = r'(?:st|nd|rd|th)'

    def __init__(self, context_year: int, context_month: int = 6):
        """
        Initialize parser with year context.

        Args:
            context_year: The year to use when dates lack year info
            context_month: The month context (for year boundary inference)
        """
        self.context_year = context_year
        self.context_month = context_month

    def parse_and_replace(self, text: str) -> Tuple[str, List[DateMatch]]:
        """
        Parse dates in text and return matches.

        Returns:
            Tuple of (original_text, list of DateMatch objects)
            The text is NOT modified - caller uses matches to build ADF nodes.
        """
        matches: List[DateMatch] = []

        # Skip text in backticks (escape mechanism)
        # We'll track which regions to skip
        skip_regions = []
        for m in re.finditer(r'`[^`]+`', text):
            skip_regions.append((m.start(), m.end()))

        def in_skip_region(pos: int) -> bool:
            return any(start <= pos < end for start, end in skip_regions)

        # Pattern 1: ISO dates (2024-03-15)
        for m in re.finditer(r'\b(\d{4})-(\d{2})-(\d{2})\b', text):
            if in_skip_region(m.start()):
                continue
            try:
                year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
                dt = datetime(year, month, day)
                matches.append(DateMatch(
                    start=m.start(),
                    end=m.end(),
                    original=m.group(0),
                    timestamp=int(dt.timestamp() * 1000),
                ))
            except ValueError:
                pass  # Invalid date

        # Pattern 2: US format with 4-digit year (03/15/2024 or 3/15/2024)
        for m in re.finditer(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b', text):
            if in_skip_region(m.start()):
                continue
            try:
                month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
                dt = datetime(year, month, day)
                matches.append(DateMatch(
                    start=m.start(),
                    end=m.end(),
                    original=m.group(0),
                    timestamp=int(dt.timestamp() * 1000),
                ))
            except ValueError:
                pass

        # Pattern 3: US format with 2-digit year (03/15/24)
        for m in re.finditer(r'\b(\d{1,2})/(\d{1,2})/(\d{2})\b', text):
            if in_skip_region(m.start()):
                continue
            try:
                month, day, year_short = int(m.group(1)), int(m.group(2)), int(m.group(3))
                # Assume 2000s for years < 50, 1900s otherwise
                year = 2000 + year_short if year_short < 50 else 1900 + year_short
                dt = datetime(year, month, day)
                matches.append(DateMatch(
                    start=m.start(),
                    end=m.end(),
                    original=m.group(0),
                    timestamp=int(dt.timestamp() * 1000),
                ))
            except ValueError:
                pass

        # IMPORTANT: Pattern order matters! More specific patterns (ranges) must come
        # BEFORE less specific patterns (single dates) to avoid partial matches.

        # Pattern 4: Date ranges with year (August 28-30, 2026) - BEFORE single dates
        pattern_range_with_year = rf'\b({self.MONTH_PATTERN})\.?\s+(\d{{1,2}}){self.ORDINAL}?\s*[-–]+\s*(\d{{1,2}}){self.ORDINAL}?,?\s+(\d{{4}})\b'
        for m in re.finditer(pattern_range_with_year, text, re.IGNORECASE):
            if in_skip_region(m.start()):
                continue
            if any(existing.start <= m.start() < existing.end for existing in matches):
                continue
            try:
                month_name, day_start, day_end, year = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
                month = self._month_name_to_num(month_name)
                if month:
                    dt_start = datetime(year, month, day_start)
                    dt_end = datetime(year, month, day_end)
                    matches.append(DateMatch(
                        start=m.start(),
                        end=m.end(),
                        original=m.group(0),
                        timestamp=int(dt_start.timestamp() * 1000),
                    ))
                    matches.append(DateMatch(
                        start=m.start(),
                        end=m.end(),
                        original=m.group(0),
                        timestamp=int(dt_end.timestamp() * 1000),
                        is_range_end=True,
                    ))
            except ValueError:
                pass

        # Pattern 5: Written dates with year (March 15, 2024 or March 15th, 2024)
        pattern_written_full = rf'\b({self.MONTH_PATTERN})\.?\s+(\d{{1,2}}){self.ORDINAL}?,?\s+(\d{{4}})\b'
        for m in re.finditer(pattern_written_full, text, re.IGNORECASE):
            if in_skip_region(m.start()):
                continue
            # Skip if overlaps with already-matched range
            if any(existing.start <= m.start() < existing.end for existing in matches):
                continue
            try:
                month_name, day, year = m.group(1), int(m.group(2)), int(m.group(3))
                month = self._month_name_to_num(month_name)
                if month:
                    dt = datetime(year, month, day)
                    matches.append(DateMatch(
                        start=m.start(),
                        end=m.end(),
                        original=m.group(0),
                        timestamp=int(dt.timestamp() * 1000),
                    ))
            except ValueError:
                pass

        # Pattern 6: Date ranges without year (March 15-20) - BEFORE single dates without year
        pattern_range_no_year = rf'\b({self.MONTH_PATTERN})\.?\s+(\d{{1,2}}){self.ORDINAL}?\s*[-–]+\s*(\d{{1,2}}){self.ORDINAL}?\b(?!\s*,?\s*\d{{4}})'
        for m in re.finditer(pattern_range_no_year, text, re.IGNORECASE):
            if in_skip_region(m.start()):
                continue
            if any(existing.start <= m.start() < existing.end for existing in matches):
                continue
            try:
                month_name, day_start, day_end = m.group(1), int(m.group(2)), int(m.group(3))
                month = self._month_name_to_num(month_name)
                if month:
                    year = self._infer_year(month)
                    dt_start = datetime(year, month, day_start)
                    dt_end = datetime(year, month, day_end)
                    matches.append(DateMatch(
                        start=m.start(),
                        end=m.end(),
                        original=m.group(0),
                        timestamp=int(dt_start.timestamp() * 1000),
                    ))
                    matches.append(DateMatch(
                        start=m.start(),
                        end=m.end(),
                        original=m.group(0),
                        timestamp=int(dt_end.timestamp() * 1000),
                        is_range_end=True,
                    ))
            except ValueError:
                pass

        # Pattern 7: Written dates without year (March 15 or March 15th) - LAST
        pattern_written_no_year = rf'\b({self.MONTH_PATTERN})\.?\s+(\d{{1,2}}){self.ORDINAL}?\b(?!\s*[-–]|\s*,?\s*\d{{4}})'
        for m in re.finditer(pattern_written_no_year, text, re.IGNORECASE):
            if in_skip_region(m.start()):
                continue
            # Skip if overlaps with already-matched date
            if any(existing.start <= m.start() < existing.end or
                   existing.start < m.end() <= existing.end
                   for existing in matches):
                continue
            try:
                month_name, day = m.group(1), int(m.group(2))
                month = self._month_name_to_num(month_name)
                if month:
                    year = self._infer_year(month)
                    dt = datetime(year, month, day)
                    matches.append(DateMatch(
                        start=m.start(),
                        end=m.end(),
                        original=m.group(0),
                        timestamp=int(dt.timestamp() * 1000),
                    ))
            except ValueError:
                pass

        # Sort by position and remove duplicates/overlaps
        matches = self._deduplicate_matches(matches)

        return text, matches

    def _month_name_to_num(self, name: str) -> Optional[int]:
        """Convert month name to number."""
        months = {
            'jan': 1, 'january': 1,
            'feb': 2, 'february': 2,
            'mar': 3, 'march': 3,
            'apr': 4, 'april': 4,
            'may': 5,
            'jun': 6, 'june': 6,
            'jul': 7, 'july': 7,
            'aug': 8, 'august': 8,
            'sep': 9, 'sept': 9, 'september': 9,
            'oct': 10, 'october': 10,
            'nov': 11, 'november': 11,
            'dec': 12, 'december': 12,
        }
        return months.get(name.lower().rstrip('.'))

    def _infer_year(self, month: int) -> int:
        """
        Infer year for a date without year.

        If the month is significantly ahead of context_month, assume previous year.
        E.g., if context is January 2024 and we see "December 28", it's likely Dec 2023.
        """
        # If context month is Jan-Mar and date month is Oct-Dec, likely previous year
        if self.context_month <= 3 and month >= 10:
            return self.context_year - 1
        # If context month is Oct-Dec and date month is Jan-Mar, likely next year
        if self.context_month >= 10 and month <= 3:
            return self.context_year + 1
        return self.context_year

    def _deduplicate_matches(self, matches: List[DateMatch]) -> List[DateMatch]:
        """Remove overlapping matches, keeping the most specific."""
        if not matches:
            return []

        # Sort by start position, then by length (longer = more specific)
        matches.sort(key=lambda m: (m.start, -(m.end - m.start)))

        result = []
        last_end = -1

        for match in matches:
            # Keep range ends even if they overlap (they're part of the same range)
            if match.is_range_end:
                if result and result[-1].start == match.start:
                    result.append(match)
                continue
            # Skip if this overlaps with previous match
            if match.start < last_end:
                continue
            result.append(match)
            last_end = match.end

        return result


def get_context_year_from_summary(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    created_at: Optional[datetime] = None,
) -> Tuple[int, int]:
    """
    Determine context year and month from summary timestamps.

    Returns:
        Tuple of (year, month) for date inference
    """
    # Prefer conversation timeframe
    if end_time:
        return end_time.year, end_time.month
    if start_time:
        return start_time.year, start_time.month
    if created_at:
        return created_at.year, created_at.month
    # Fallback to current date
    now = datetime.utcnow()
    return now.year, now.month
