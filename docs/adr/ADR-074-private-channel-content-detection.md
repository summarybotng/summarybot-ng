# ADR-074: Private Channel Content Detection

## Status
Accepted

## Context

ADR-073 introduced locked channel detection and the `contains_sensitive_channels` flag on summaries. However, the initial implementation had a flaw: summaries were flagged as "containing private content" if locked channels were **in scope** at generation time, even if those channels contributed no actual content to the summary.

For example, a multi-channel summary covering 66 channels might include 12 locked channels in its scope, but if those 12 channels had no messages during the time period, the summary contains no actual private content. Flagging it as "private" is misleading and reduces trust in the indicator.

### Current (Flawed) Logic
```python
# Backfill checked if ANY locked channel was in source_channel_ids
for channel_id in summary.source_channel_ids:
    if channel_id in locked_channel_ids:
        summary.contains_sensitive_channels = True
```

### Problems
1. **False positives**: Summaries flagged as private when no private content exists
2. **User confusion**: Filter shows 304 "private" summaries but many may be fully public
3. **Undermines trust**: Users stop trusting the indicator if it's frequently wrong

## Decision

### Refined Detection Logic

A summary `contains_sensitive_channels = True` only when **actual content** from locked channels is included. Detection uses this priority:

#### 1. Reference-Based Detection (Preferred)
If the summary has grounded references (`SummaryReference` objects), check if any reference's `channel_id` matches a locked channel:

```python
def _has_private_content_from_references(
    summary: StoredSummary,
    locked_channel_ids: Set[str]
) -> bool:
    """Check if any grounded reference came from a locked channel."""
    if not summary.summary_result or not summary.summary_result.references:
        return False

    for ref in summary.summary_result.references:
        if ref.channel_id and ref.channel_id in locked_channel_ids:
            return True
    return False
```

#### 2. Single-Channel Scope (Fallback)
If the summary has only one channel in scope and that channel is locked, the summary contains private content (since all content came from that channel):

```python
def _has_private_content_single_channel(
    summary: StoredSummary,
    locked_channel_ids: Set[str]
) -> bool:
    """For single-channel summaries, check if that channel is locked."""
    if len(summary.source_channel_ids) == 1:
        return summary.source_channel_ids[0] in locked_channel_ids
    return False
```

#### 3. Conservative Fallback (No References, Multi-Channel)
For multi-channel summaries without grounded references, we cannot determine which channels contributed content. Options:
- **Option A**: Mark as `contains_sensitive_channels = None` (unknown)
- **Option B**: Mark as `False` (assume public until proven otherwise)
- **Option C**: Keep scope-based check (conservative, current behavior)

**Decision**: Use **Option B** - mark as `False`. Rationale:
- Reduces false positives significantly
- Users can regenerate with grounding to get accurate detection
- Privacy boundary at wiki ingestion (ADR-073 section 5) provides additional protection

### Combined Logic

```python
def determine_private_content(
    summary: StoredSummary,
    locked_channel_ids: Set[str]
) -> bool:
    """
    Determine if a summary contains actual content from locked channels.

    Priority:
    1. Check grounded references (most accurate)
    2. Check single-channel scope (certain)
    3. Default to False for multi-channel without references
    """
    # Check references first (most accurate)
    if summary.summary_result and summary.summary_result.references:
        for ref in summary.summary_result.references:
            if ref.channel_id and ref.channel_id in locked_channel_ids:
                return True
        # Has references but none from locked channels
        return False

    # Single-channel fallback
    if len(summary.source_channel_ids) == 1:
        return summary.source_channel_ids[0] in locked_channel_ids

    # Multi-channel without references - cannot determine
    return False
```

## Database Changes

No schema changes required. The `contains_sensitive_channels` column already exists.

### Backfill Migration

```sql
-- Reset all summaries to recalculate
UPDATE stored_summaries SET contains_sensitive_channels = 0;
```

Then run Python backfill with refined logic:

```python
async def backfill_private_content_refined():
    """Backfill contains_sensitive_channels using refined logic."""
    # Get all locked channel IDs
    locked_channels = await get_locked_channel_ids()

    # Process each summary
    summaries = await get_all_summaries()
    for summary in summaries:
        is_private = determine_private_content(summary, locked_channels)
        if is_private:
            await update_summary_sensitive_flag(summary.id, True)
```

## API Changes

### GET /guilds/{guild_id}/stored-summaries
- `contains_private_channels=true` filter now returns only summaries with **actual** private content

### Response Fields
- `contains_sensitive_channels: boolean` - True only if actual private content detected

## UI Changes

### Summary Metadata Section
When `contains_sensitive_channels = True`:
```
🔒 Contains content from private/locked channels
   Sources: #private-channel-1, #private-channel-2
```

Show which specific locked channels contributed content (when references available).

### Filter Accuracy Indicator
The "Private Channels" filter badge could show:
- "Private Channels (verified)" when detection was reference-based
- "Private Channels" when detection was scope-based (single-channel)

## Consequences

### Positive
1. **Accurate flagging**: Only summaries with actual private content are flagged
2. **Reduced noise**: Fewer false positives improve user trust
3. **Encourages grounding**: Users see value in regenerating with references
4. **Precise filtering**: Filter returns meaningful results

### Negative
1. **Complexity**: Detection logic is more nuanced
2. **Backfill required**: Must recalculate for existing summaries
3. **Edge cases**: Multi-channel summaries without references may miss private content

### Mitigations
- Wiki ingestion (ADR-073 section 5) provides second layer of protection
- Admins can manually mark summaries as sensitive if needed
- Regeneration with grounding fixes detection accuracy

## Production Finding

### Initial Issue
References are stored in `reference_index` field, not `references`. After correcting:

| Metric | Value |
|--------|-------|
| Total summaries | 626 |
| Summaries with references | 574 (91%) |
| **Actual private content** | **23** |
| Previous false positives | 304 (scope-based) |

### Accuracy Improvement
- **Before (scope-based)**: 304 flagged as private (48%)
- **After (reference-based)**: 23 flagged as private (3.7%)
- **False positive reduction**: 281 summaries no longer incorrectly flagged

### Implementation Note
References may be stored in either field depending on summary version:
- `summary_result.references` - newer format
- `summary_result.reference_index` - older format

The detection logic must check both:
```python
refs = summary_data.get("references") or summary_data.get("reference_index") or []
```

## Implementation Order

1. ✅ Create ADR-074 (this document)
2. Implement `determine_private_content()` function
3. Update summary generation to calculate flag at creation time
4. Update backfill script with refined logic
5. Run backfill on production
6. Update UI to show source channels when available
7. Add filter accuracy indicator (optional)

## Technical Debt

### TD-074-1: Dual Reference Field Names
**Severity**: Medium
**Description**: References stored in two different field names depending on summary version:
- `summary_result.references` - newer format
- `summary_result.reference_index` - older format

**Impact**: Detection logic must check both fields; easy to miss one.

**Resolution**: Migrate all summaries to use consistent `references` field name, or normalize at read time in repository layer.

### TD-074-2: Manual Backfill
**Severity**: Low
**Description**: Initial backfill was run via SSH Python script rather than proper migration.

**Impact**: Not repeatable; no audit trail; could drift if re-run differently.

**Resolution**: Create proper management command or migration script in codebase.

### TD-074-3: Detection Not Integrated at Generation Time
**Severity**: Medium
**Description**: `contains_sensitive_channels` is calculated via backfill, not set automatically when summaries are created.

**Impact**: New summaries may not have accurate flag until next backfill.

**Resolution**: Integrate `determine_private_content()` into summary storage pipeline.

### TD-074-4: UI Doesn't Show Source Channels
**Severity**: Low
**Description**: When a summary is flagged as private, UI shows generic "Contains private content" but doesn't list which locked channels contributed.

**Impact**: Users can't easily verify why summary is flagged.

**Resolution**: Implement `get_private_channel_sources()` in UI to show specific channels.

### TD-074-5: No Bulk Split Option
**Severity**: Low
**Description**: Existing mixed summaries cannot be easily split into public/private portions.

**Impact**: Historical summaries with private content remain excluded from wiki.

**Resolution**: See ADR-075 for proposed regeneration split feature.

## Related ADRs

- **ADR-073**: Channel Access Controls (parent ADR)
- **ADR-004**: Summary Grounding (references enable accurate detection)
- **ADR-046**: Channel Sensitivity Configuration
- **ADR-075**: Private Content Regeneration Split (addresses TD-074-5)
