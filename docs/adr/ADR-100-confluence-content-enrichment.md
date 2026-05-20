# ADR-100: Confluence Content Enrichment

## Status
Accepted

## Context

ADR-099 introduced Confluence publishing for summaries. However, the current implementation includes source references which may contain sensitive information (message snippets, user names) or irrelevant details. Additionally, the published pages lack:

1. **Channel context** - No indication of which Discord channels the summary covers
2. **Temporal formatting** - Dates mentioned in summary text appear as plain text, missing Confluence's native date rendering
3. **Discoverability** - No labels for filtering/searching pages by channel

Confluence supports:
- **Labels** - Metadata tags for page organization and search
- **Date macros** - Native date chips that render contextually (e.g., "yesterday", "next week")
- **ADF date nodes** - `{"type": "date", "attrs": {"timestamp": 1234567890000}}`

## Decision

### 1. Omit Source References

Remove the "Source References" section from Confluence output. The references contain:
- Message snippets that may include sensitive information
- User identifiers that may not be relevant outside Discord
- Internal Discord message IDs with no meaning in Confluence

The summary text itself provides sufficient context without exposing raw source material.

### 2. Include Channel List

Add channel information in two ways:

**In Content (Info Panel):**
```
Channels: #general, #engineering, #product-updates
```

**As Labels:**
- `channel-general`
- `channel-engineering`
- `channel-product-updates`
- `summarybot` (always added for filtering all bot-generated pages)

Label format: `channel-{sanitized_channel_name}` where sanitization:
- Lowercase
- Replace spaces/special chars with hyphens
- Max 40 chars (Confluence limit: 255, but keep short for usability)

### 3. LLM-Based Date Extraction

**Why LLM over Regex:**
Regex-based date parsing is fragile and misses many natural language variations:
- "the week of March 15th"
- "mid-August"
- "Q1 2024"
- "next Monday"
- Ambiguous formats like "3/4" (March 4 or April 3?)

**Implementation:**
Use Claude Haiku for cost-effective, intelligent date extraction:

```python
# src/services/date_extractor.py
async def extract_dates_with_llm(
    text: str,
    context_year: int,
    context_month: int,
) -> List[ExtractedDate]:
    """Extract dates using Claude Haiku."""
```

**Prompt Strategy:**
1. Provide conversation timeframe context (year/month)
2. Ask LLM to find ALL date references with exact text positions
3. LLM returns structured JSON with text spans and ISO dates
4. Validate positions match actual text (LLM may be off-by-one)
5. Convert to Confluence ADF date nodes

**Year Context:**
When a date lacks a year, the LLM infers from:
1. The summary's `start_time` or `end_time` (conversation timeframe)
2. Year boundary logic: "December 28" in January context → previous year

**ADF Date Node:**
```json
{
  "type": "date",
  "attrs": {
    "timestamp": 1710460800000
  }
}
```

**Cost:** ~$0.0001 per summary (Haiku pricing)

### 4. Scope Metadata as Labels

Leverage ADR-098 scope metadata for additional labels:
- `scope-guild` / `scope-category` / `scope-channel`
- `category-{category_name}` (if category-scoped)

## Implementation

### Date Extractor Module

Create `src/services/date_extractor.py`:

```python
async def extract_dates_with_llm(
    text: str,
    context_year: int,
    context_month: int = 6,
) -> List[ExtractedDate]:
    """
    Extract dates from text using Claude Haiku.

    Returns list of ExtractedDate with:
    - original_text: exact matched text
    - start_pos/end_pos: character positions
    - timestamp_ms: Unix timestamp in milliseconds
    - is_range_start/is_range_end: for date ranges
    """

def build_adf_content_with_dates(
    text: str,
    dates: List[ExtractedDate],
) -> List[dict]:
    """Build ADF content nodes with dates as date chips."""
```

### Modified ADF Formatter

Update `src/services/confluence.py`:

```python
def _format_adf_content(
    self,
    summary: SummaryResult,
    title: str,
    summary_id: Optional[str] = None,
    guild_id: Optional[str] = None,
    channel_names: Optional[List[str]] = None,
    scope_type: Optional[str] = None,
    category_name: Optional[str] = None,
) -> dict:
    """Format summary as ADF with date chips and channel info."""

    # Parse dates in summary text
    context_year = self._get_context_year(summary)
    date_parser = DateParser(context_year)
    processed_text, date_positions = date_parser.parse_and_replace(
        summary.summary_text
    )

    # Build content with date nodes inline
    summary_content = self._build_text_with_dates(processed_text, date_positions)

    # Channel info panel (if channels provided)
    channel_panel = None
    if channel_names:
        channel_panel = {
            "type": "panel",
            "attrs": {"panelType": "info"},
            "content": [{
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Channels: ", "marks": [{"type": "strong"}]},
                    {"type": "text", "text": ", ".join(f"#{name}" for name in channel_names)},
                ]
            }]
        }

    # ... rest of ADF construction (omit references section)
```

### Label Generation

```python
def _generate_labels(
    self,
    channel_names: Optional[List[str]] = None,
    scope_type: Optional[str] = None,
    category_name: Optional[str] = None,
) -> List[str]:
    """Generate Confluence labels for the page."""
    labels = ["summarybot"]  # Always include for filtering

    if channel_names:
        for name in channel_names:
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
    """Sanitize name for use as Confluence label."""
    # Lowercase, replace non-alphanumeric with hyphen, collapse multiple hyphens
    sanitized = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    return sanitized[:40] if sanitized else ""
```

### API Changes

Update publish endpoint to pass channel names:

```python
# In summaries.py publish endpoint
channel_names = []
try:
    guild = _get_guild_or_404(guild_id)
    for ch_id in summary.source_channel_ids or []:
        channel = guild.get_channel(int(ch_id))
        if channel:
            channel_names.append(channel.name)
except:
    pass  # Continue without channel names if unavailable

result = await confluence_service.publish_summary(
    summary=summary.summary_result,
    title=page_title,
    channel_names=channel_names,
    scope_type=summary.scope_type,
    category_name=summary.category_name,
    # ... other params
)
```

## Date Chip Rendering Examples

**Input text:**
> The team discussed the Q1 roadmap on March 15. Follow-up meeting scheduled for March 22nd.

**Output ADF (conceptual):**
> The team discussed the Q1 roadmap on [March 15, 2024]. Follow-up meeting scheduled for [March 22, 2024].

Where `[date]` renders as a Confluence date lozenge showing relative time ("2 months ago") on hover.

## Edge Cases

### Year Boundary
- Summary created January 5, 2024
- Text mentions "December 28"
- Infer: December 28, 2023 (not 2024)

### Ambiguous Dates
- "3/4" could be March 4 or April 3
- Use locale setting (default US: MM/DD)
- If no clear resolution, leave as plain text

### Date Ranges Spanning Months
- "March 28 to April 3"
- Render as two date chips: `[March 28] to [April 3]`

## Consequences

### Positive
- Cleaner Confluence pages without potentially sensitive references
- Channel context preserved for readers
- Labels enable powerful search/filtering in Confluence
- Date chips provide dynamic, contextual time display
- Pages integrate better with Confluence's native features

### Negative
- Loss of source attribution (references removed)
- Date parsing may occasionally misidentify dates in technical content
- Additional processing overhead for date parsing

### Mitigations
- Keep reference data in SummaryBot for users who need source details
- Add escape mechanism: dates in backticks (`2024-03-15`) are not converted
- Cache parsed results if same summary published multiple times

## Related ADRs
- ADR-099: Remote Platform Publishing (parent feature)
- ADR-098: Summary Scope Metadata (scope labels)
- ADR-004: Source References (references being omitted)
