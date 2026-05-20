"""
LLM-based date extraction for Confluence publishing (ADR-100).

Uses Claude via OpenRouter to intelligently extract dates from summary text,
handling natural language variations that regex cannot reliably parse.
"""

import json
import logging
import os
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

# OpenRouter configuration
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# Use Haiku for speed and cost efficiency (OpenRouter model ID format)
DEFAULT_MODEL = "anthropic/claude-3.5-haiku"


@dataclass
class ExtractedDate:
    """A date extracted from text."""
    original_text: str  # The exact text that was matched
    start_pos: int  # Start position in original text
    end_pos: int  # End position in original text
    timestamp_ms: int  # Unix timestamp in milliseconds
    is_range_start: bool = False
    is_range_end: bool = False
    range_pair_index: Optional[int] = None  # Index of paired date in range


async def extract_dates_with_llm(
    text: str,
    context_year: int,
    context_month: int = 6,
) -> List[ExtractedDate]:
    """
    Extract dates from text using Claude.

    Args:
        text: The summary text to extract dates from
        context_year: Year context for dates without explicit year
        context_month: Month context for year boundary inference

    Returns:
        List of ExtractedDate objects sorted by position
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        logger.warning("No OPENROUTER_API_KEY - skipping date extraction")
        return []

    prompt = f"""Extract all dates and date ranges from this text. The text is from conversations that occurred around {datetime(context_year, context_month, 1).strftime('%B %Y')}.

Text:
{text}

For each date found, return a JSON array with objects containing:
- "text": the exact text as it appears (e.g., "March 15th", "August 28-30, 2026")
- "start": character position where the date text starts
- "end": character position where the date text ends
- "dates": array of ISO date strings (YYYY-MM-DD). For ranges, include both start and end dates.

Rules:
1. Include ALL date references: explicit dates, relative dates ("yesterday", "next Monday"), and ranges
2. For dates without a year, infer the year based on context ({context_year}, or {context_year - 1} if the month suggests previous year)
3. For relative dates like "yesterday" or "next week", resolve them relative to {datetime(context_year, context_month, 15).strftime('%B %d, %Y')}
4. Match the EXACT text - positions must be precise
5. Skip dates in backticks (code blocks)

Return ONLY a JSON array, no other text. Empty array [] if no dates found.

Example output:
[
  {{"text": "March 15, 2024", "start": 45, "end": 59, "dates": ["2024-03-15"]}},
  {{"text": "August 28-30", "start": 120, "end": 132, "dates": ["2024-08-28", "2024-08-30"]}}
]"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://summarybot-ng.fly.dev",
                    "X-Title": "SummaryBot",
                },
                json={
                    "model": DEFAULT_MODEL,
                    "max_tokens": 2048,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                },
            )

            if response.status_code != 200:
                logger.warning(f"Date extraction API error: {response.status_code} - {response.text[:200]}")
                return []

            result = response.json()
            # OpenRouter uses OpenAI format: choices[0].message.content
            choices = result.get("choices", [])
            if not choices:
                logger.warning("No choices in date extraction response")
                return []

            # Parse the JSON response
            json_text = choices[0].get("message", {}).get("content", "[]")
            # Clean up potential markdown code blocks
            if json_text.startswith("```"):
                json_text = json_text.split("```")[1]
                if json_text.startswith("json"):
                    json_text = json_text[4:]
            json_text = json_text.strip()

            date_data = json.loads(json_text)

            # Convert to ExtractedDate objects
            extracted: List[ExtractedDate] = []
            for item in date_data:
                original = item.get("text", "")
                start = item.get("start", 0)
                end = item.get("end", 0)
                dates = item.get("dates", [])

                # Verify the position matches (LLM might be off)
                actual_text = text[start:end] if start < len(text) and end <= len(text) else ""
                if actual_text != original:
                    # Try to find the actual position
                    found_pos = text.find(original)
                    if found_pos >= 0:
                        start = found_pos
                        end = found_pos + len(original)
                    else:
                        logger.debug(f"Could not find date text '{original}' in text")
                        continue

                if len(dates) == 1:
                    # Single date
                    try:
                        dt = datetime.fromisoformat(dates[0])
                        extracted.append(ExtractedDate(
                            original_text=original,
                            start_pos=start,
                            end_pos=end,
                            timestamp_ms=int(dt.timestamp() * 1000),
                        ))
                    except ValueError:
                        pass
                elif len(dates) >= 2:
                    # Date range - add both dates
                    try:
                        dt_start = datetime.fromisoformat(dates[0])
                        dt_end = datetime.fromisoformat(dates[1])
                        range_idx = len(extracted)
                        extracted.append(ExtractedDate(
                            original_text=original,
                            start_pos=start,
                            end_pos=end,
                            timestamp_ms=int(dt_start.timestamp() * 1000),
                            is_range_start=True,
                            range_pair_index=range_idx + 1,
                        ))
                        extracted.append(ExtractedDate(
                            original_text=original,
                            start_pos=start,
                            end_pos=end,
                            timestamp_ms=int(dt_end.timestamp() * 1000),
                            is_range_end=True,
                            range_pair_index=range_idx,
                        ))
                    except ValueError:
                        pass

            # Sort by position
            extracted.sort(key=lambda x: (x.start_pos, -x.end_pos))

            logger.info(f"Extracted {len(extracted)} date references from text")
            return extracted

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse date extraction response: {e}")
        return []
    except Exception as e:
        logger.warning(f"Date extraction failed: {e}")
        return []


def build_adf_content_with_dates(
    text: str,
    dates: List[ExtractedDate],
) -> List[dict]:
    """
    Build ADF content nodes with dates converted to date chips.

    Args:
        text: Original text
        dates: List of ExtractedDate from LLM extraction

    Returns:
        List of ADF content nodes
    """
    if not dates:
        return [{"type": "text", "text": text}]

    content: List[dict] = []
    last_end = 0

    # Group dates by position (ranges share same position)
    i = 0
    while i < len(dates):
        date = dates[i]

        # Add text before this date
        if date.start_pos > last_end:
            preceding = text[last_end:date.start_pos]
            if preceding:
                content.append({"type": "text", "text": preceding})

        # Check if this is a range (has paired date at same position)
        if date.is_range_start and i + 1 < len(dates) and dates[i + 1].is_range_end:
            # Range: add start date, separator, end date
            content.append({
                "type": "date",
                "attrs": {"timestamp": date.timestamp_ms},
            })
            content.append({"type": "text", "text": " – "})  # en-dash
            content.append({
                "type": "date",
                "attrs": {"timestamp": dates[i + 1].timestamp_ms},
            })
            last_end = date.end_pos
            i += 2  # Skip both range dates
        else:
            # Single date
            content.append({
                "type": "date",
                "attrs": {"timestamp": date.timestamp_ms},
            })
            last_end = date.end_pos
            i += 1

    # Add remaining text
    if last_end < len(text):
        remaining = text[last_end:]
        if remaining:
            content.append({"type": "text", "text": remaining})

    return content if content else [{"type": "text", "text": text}]
