# ADR-106: Summary Metadata Panel Redesign

## Status
Accepted

## Context

The current "How This Summary Was Generated" panel shows limited metadata about summaries:
- Model used
- Summary length & perspective
- Token counts
- Basic context (channel, time span, participants)

However, the system stores significantly more metadata that could be valuable for debugging, understanding quality, and transparency:

**Currently hidden but stored:**
- `requested_model` vs `claude_model` - Shows when model was upgraded/changed
- `retry_of` - Indicates this summary was a retry of a failed job
- `generation_attempts` - Full attempt history with latency/cost per attempt
- `extraction_stats` - Counts of key points, action items, references extracted
- `api_response_id` - For tracing API calls
- `latency_ms` / `processing_time` - Performance metrics
- `grounded` / `citations_enabled` - Whether citations were used
- `prompt_source` details - Already shown, but could be more prominent

Users and developers benefit from seeing this data when diagnosing issues like:
- "Why did this summary take so long?"
- "Why was a different model used than expected?"
- "Was this a retry? What failed before?"

## Decision

Redesign the metadata panel with the following changes:

### 1. Rename to "Metadata"
- Shorter, clearer label
- "How This Summary Was Generated" is wordy and imprecise

### 2. Collapse by Default
- Use `<details>` element to make the entire section collapsible
- Reduces visual noise when users just want to read the summary
- Power users can expand to see full details

### 3. Show All Stored Metadata
Add new fields to the display:

| Field | Display As | Notes |
|-------|-----------|-------|
| `requested_model` | "Requested Model" | Show alongside actual model if different |
| `claude_model` | "Actual Model" | Highlight if different from requested |
| `retry_of` | "Retry Of" | Link to original job ID if available |
| `generation_attempts` | "Attempts" | Show count and expand for details |
| `extraction_stats` | Inline with extraction counts | key_points, action_items, etc. |
| `api_response_id` | "API Response" | Truncated with copy button |
| `latency_ms` | "Latency" | Show in seconds with ms precision |

### 4. Hierarchy
```
▶ Metadata (collapsed by default)
  ├─ Core: Model, Length, Perspective
  ├─ Performance: Tokens, Latency, Attempts
  ├─ Extraction: Key Points, Actions, References
  ├─ Context: Channel, Server, Time Span
  ├─ Prompt Source: Template, Variables
  └─ ▶ View Generation Details (nested expander)
       ├─ Source Messages
       ├─ System Prompt
       └─ User Prompt
```

## Implementation

Update `StoredSummariesTab.tsx`:
1. Wrap entire metadata card in `<details>` with summary "Metadata"
2. Add new metadata fields to the grid
3. Highlight model mismatch with visual indicator
4. Show retry indicator if `retry_of` is present
5. Keep "View Generation Details" as nested `<details>` inside

## Consequences

### Positive
- More transparency for users and developers
- Easier debugging of generation issues
- Model upgrade/retry visibility helps understand costs
- Cleaner default view (collapsed)

### Negative
- More visual complexity when expanded
- Some technical fields may confuse non-technical users

### Neutral
- No backend changes required (data already stored)
- Backwards compatible (new fields just won't show for old summaries)

## References

- ADR-010: Summary Metadata Storage
- ADR-073/074: Privacy indicators (already in panel)
- ADR-075: Split relationship indicator (already in panel)
