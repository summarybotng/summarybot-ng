# ADR-016: Summary Regeneration Data Integrity

## Status
Proposed

## Context

When attempting to regenerate summary `sum_8d35d83ed123`, the operation failed due to missing data. Investigation revealed that many stored summaries lack the fields required for regeneration:

- `start_time` / `end_time` - Time range of source messages
- `source_channel_ids` - Discord channels the messages came from
- `source_content` - Original message text (for offline regeneration)

This ADR analyzes root causes and proposes solutions to ensure all summaries can be regenerated.

## Problem Analysis

### What Regeneration Requires

To regenerate a summary with grounding (ADR-004), we need:

| Field | Purpose | Can Recover? |
|-------|---------|--------------|
| `guild_id` | Discord API access | ✅ Always present |
| `source_channel_ids` | Fetch messages from Discord | ⚠️ Sometimes missing |
| `start_time` | Message fetch window start | ⚠️ Sometimes missing |
| `end_time` | Message fetch window end | ⚠️ Sometimes missing |
| `source_content` | Offline regeneration fallback | ⚠️ Often missing |

### Root Causes

#### 1. Archive Summaries (ADR-008)

**Issue:** Archive generator's `_save_to_database` created minimal `SummaryResult` objects that didn't always include time range.

```python
# Before fix - missing fields
db_summary_result = SummaryResult(
    id=summary_id,
    guild_id=job.source.server_id or "",
    channel_id=job.source.channel_id or "",  # Single channel, not list
    # start_time/end_time from period, but not always passed
    ...
)
```

**Root cause:** The `SummarizationAdapter` returned a response object without all the fields from the engine's `SummaryResult`.

#### 2. Early Summaries (Pre-ADR-005)

**Issue:** Summaries created before the stored summary system may have been migrated without complete metadata.

#### 3. Scheduled Summaries

**Issue:** Some scheduled summary jobs may not preserve the full context needed for regeneration.

#### 4. Manual/Dashboard Summaries

**Issue:** The generate endpoint stores summaries but the time range calculation happens in the background task, which may fail silently.

### Data Flow Gaps

```
Message Fetch → Processing → Summarization → Storage
     ↓              ↓             ↓            ↓
  time range    processed     SummaryResult  StoredSummary
  known here    messages      has times      SHOULD have times
                                             but sometimes doesn't
```

## Decision

### 1. Enforce Required Fields at Storage Time

Add validation before saving any `StoredSummary`:

```python
def validate_for_regeneration(stored: StoredSummary) -> List[str]:
    """Check if summary has data needed for regeneration."""
    issues = []

    if not stored.source_channel_ids:
        issues.append("missing source_channel_ids")

    result = stored.summary_result
    if result:
        if not result.start_time:
            issues.append("missing start_time")
        if not result.end_time:
            issues.append("missing end_time")
    else:
        issues.append("missing summary_result")

    return issues
```

Log warnings but don't block saves (to avoid data loss).

### 2. Store Source Content as Fallback

Always store `source_content` (formatted messages) so regeneration can work even without Discord access:

```python
# In summarization flow
result.source_content = format_messages_for_storage(processed_messages)

# Format that preserves enough info for re-summarization
# [2024-02-22 14:32] username: message content
# [2024-02-22 14:33] other_user: their message
```

This enables:
- Regeneration when Discord channels are deleted
- Regeneration when bot loses access to server
- Offline testing and development

### 3. Add Regeneration Eligibility Flag

Track whether a summary can be regenerated:

```python
@dataclass
class StoredSummary:
    # ... existing fields ...

    # Regeneration metadata
    can_regenerate: bool = False
    regeneration_method: str = "none"  # "discord", "source_content", "none"
    regeneration_issues: List[str] = field(default_factory=list)
```

Compute on save and update:
```python
def compute_regeneration_status(self) -> None:
    issues = []

    # Check Discord regeneration
    can_discord = bool(
        self.source_channel_ids and
        self.summary_result and
        self.summary_result.start_time and
        self.summary_result.end_time
    )

    # Check source_content regeneration
    can_source = bool(
        self.summary_result and
        self.summary_result.source_content
    )

    if can_discord:
        self.can_regenerate = True
        self.regeneration_method = "discord"
    elif can_source:
        self.can_regenerate = True
        self.regeneration_method = "source_content"
    else:
        self.can_regenerate = False
        self.regeneration_method = "none"

        # Record why
        if not self.source_channel_ids:
            issues.append("no source channels")
        if not self.summary_result:
            issues.append("no summary result")
        elif not self.summary_result.start_time:
            issues.append("no start time")
        elif not self.summary_result.end_time:
            issues.append("no end time")
        if not (self.summary_result and self.summary_result.source_content):
            issues.append("no source content")

    self.regeneration_issues = issues
```

### 4. Fix Existing Summaries (Migration)

Create a migration/repair script:

```python
async def repair_summary_metadata(summary_id: str) -> dict:
    """Attempt to repair missing metadata for a summary."""
    stored = await repo.get(summary_id)
    repairs = []

    # Try to infer time range from created_at
    if stored.summary_result and not stored.summary_result.start_time:
        # Default: 24 hours before creation
        stored.summary_result.start_time = stored.created_at - timedelta(hours=24)
        stored.summary_result.end_time = stored.created_at
        repairs.append("inferred time range from created_at")

    # Try to get channel from archive metadata
    if not stored.source_channel_ids and stored.archive_source_key:
        # Parse channel from source key: "discord/guild_id/channel_id"
        parts = stored.archive_source_key.split("/")
        if len(parts) >= 3:
            stored.source_channel_ids = [parts[2]]
            repairs.append(f"extracted channel from archive_source_key")

    # Recompute regeneration status
    stored.compute_regeneration_status()

    await repo.update(stored)
    return {"repairs": repairs, "can_regenerate": stored.can_regenerate}
```

### 5. UI Improvements

Show regeneration status in the UI:

```typescript
// In StoredSummaryCard or detail view
{!summary.can_regenerate && (
  <Badge variant="outline" className="text-muted-foreground">
    <AlertCircle className="mr-1 h-3 w-3" />
    Cannot regenerate: {summary.regeneration_issues?.join(", ")}
  </Badge>
)}
```

Disable regenerate button with tooltip explaining why:

```typescript
<Button
  disabled={!summary.can_regenerate}
  title={summary.can_regenerate
    ? "Regenerate with grounding"
    : `Cannot regenerate: ${summary.regeneration_issues?.join(", ")}`
  }
>
  Regenerate
</Button>
```

### 6. Source Content Regeneration Path

Implement fallback regeneration using stored `source_content`:

```python
async def regenerate_from_source_content(summary_id: str) -> SummaryResult:
    """Regenerate summary from stored source_content."""
    stored = await repo.get(summary_id)

    if not stored.summary_result.source_content:
        raise ValueError("No source content available")

    # Parse source_content back to messages
    messages = parse_source_content(stored.summary_result.source_content)

    # Generate new summary with grounding
    new_result = await engine.summarize_messages(
        messages=messages,
        options=get_original_options(stored),
        context=build_context(stored),
        guild_id=stored.guild_id,
        channel_id=stored.source_channel_ids[0] if stored.source_channel_ids else "",
    )

    return new_result
```

## Implementation Plan

### Phase 1: Prevention (Immediate)
1. Add `source_content` storage to all summarization paths
2. Validate required fields before StoredSummary.save()
3. Log warnings for incomplete data

### Phase 2: Visibility (Short-term)
1. Add `can_regenerate` field to StoredSummary model
2. Compute regeneration status on save
3. Show status in UI
4. Disable button with explanation for non-regenerable summaries

### Phase 3: Repair (Medium-term)
1. Create repair migration script
2. Backfill missing data where inferable
3. Implement source_content fallback regeneration

### Phase 4: Monitoring (Ongoing)
1. Dashboard metric: % of summaries that can regenerate
2. Alert on summaries saved without regeneration capability
3. Audit log for regeneration attempts

## Database Changes

```sql
-- Add regeneration tracking columns
ALTER TABLE stored_summaries ADD COLUMN can_regenerate BOOLEAN DEFAULT FALSE;
ALTER TABLE stored_summaries ADD COLUMN regeneration_method TEXT DEFAULT 'none';
ALTER TABLE stored_summaries ADD COLUMN regeneration_issues TEXT DEFAULT '[]';

-- Backfill existing rows
UPDATE stored_summaries
SET can_regenerate = (
    source_channel_ids IS NOT NULL
    AND source_channel_ids != '[]'
    AND json_extract(summary_json, '$.start_time') IS NOT NULL
    AND json_extract(summary_json, '$.end_time') IS NOT NULL
);
```

## Consequences

### Positive
- Clear visibility into which summaries can be regenerated
- Fallback path via source_content
- Prevention of future data gaps
- Self-documenting system (issues explain why)

### Negative
- Additional storage for source_content (~5-10KB per summary)
- Migration complexity for existing data
- Some old summaries may never be regenerable

### Mitigations
- Compress source_content if storage is concern
- Accept that pre-ADR summaries may have limitations
- Document which summaries are affected

## Related ADRs

- ADR-004: Grounded Summary Citations
- ADR-005: Stored Summary Management
- ADR-008: Unified Summary Experience
- ADR-015: Summary Deep Linking

## Appendix: Affected Summary Sources

| Source | Likely Has Data? | Fix |
|--------|-----------------|-----|
| Archive (ADR-008) | ⚠️ Partial | Fixed in commit 134d336 |
| Scheduled | ✅ Usually | Verify storage path |
| Manual/Dashboard | ✅ Usually | Verify storage path |
| Imported | ❌ Unlikely | Require on import |
| Pre-ADR-005 | ❌ No | Mark as non-regenerable |
