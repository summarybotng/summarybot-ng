# ADR-075: Private Content Regeneration Split

## Status
Accepted (Backend Implemented)

## Context

When a multi-channel summary contains content from both public and private channels, the entire summary is flagged as "contains private content" (ADR-074). This creates issues:

1. **Wiki exclusion**: The entire summary is excluded from wiki ingestion, even though most content may be public
2. **All-or-nothing**: Users cannot share public portions without also sharing private content
3. **No separation**: Regeneration preserves the same channel scope, keeping private and public content mixed

### Example Scenario
Summary `2501d2f7-277e-4ed9-a4ae-704abced7129` covers 50+ channels including `#business-operations` (locked). When regenerated:
- The new summary retains the same ID
- Private channel content remains mixed with public content
- The entire summary remains flagged as private

## Decision

### Regeneration Split Option

When regenerating a summary that contains private channel content, offer an option to **split** the summary:

```
┌─────────────────────────────────────────────────────┐
│ Regenerate Summary                                   │
├─────────────────────────────────────────────────────┤
│ ⚠️ This summary contains content from locked channels│
│                                                      │
│ Options:                                             │
│ ○ Regenerate as-is (keeps private content mixed)    │
│ ○ Split into public/private summaries               │
│   - Creates separate summary for private channels   │
│   - Original becomes public-only                    │
│   - Private summary linked to original              │
└─────────────────────────────────────────────────────┘
```

### Split Behavior

When "Split" is selected:

1. **Identify channel groups**:
   - Public channels: `source_channel_ids` where channel is not locked
   - Private channels: `source_channel_ids` where channel is locked

2. **Create two summaries**:

   **Public Summary** (replaces original):
   - `id`: Same as original (preserves links/references)
   - `source_channel_ids`: Only public channels
   - `contains_sensitive_channels`: `false`
   - `wiki_visible`: `true` (can be ingested to wiki)
   - `split_from`: `null`
   - `split_private_id`: Reference to private summary

   **Private Summary** (new):
   - `id`: New generated ID
   - `source_channel_ids`: Only locked channels
   - `contains_sensitive_channels`: `true`
   - `wiki_visible`: `false`
   - `split_from`: Original summary ID
   - `split_public_id`: Reference to public summary

3. **Regenerate both**:
   - Each summary regenerated with its respective channel set
   - References only include messages from that summary's channels
   - Metadata tracks the split relationship

### Database Schema

```sql
-- Add split tracking columns to stored_summaries
ALTER TABLE stored_summaries ADD COLUMN split_from TEXT;
ALTER TABLE stored_summaries ADD COLUMN split_private_id TEXT;
ALTER TABLE stored_summaries ADD COLUMN split_public_id TEXT;

-- Index for finding related summaries
CREATE INDEX idx_stored_summaries_split ON stored_summaries(split_from);
```

### API Changes

#### POST /guilds/{guild_id}/stored-summaries/{summary_id}/regenerate

Add request body option:
```json
{
  "split_private": true,
  "model": "claude-3-5-sonnet",
  "summary_length": "detailed"
}
```

Response when split:
```json
{
  "task_id": "task_xxx",
  "status": "queued",
  "split": {
    "public_summary_id": "sum_593ff4fd575c",
    "private_summary_id": "sum_new123456"
  }
}
```

### UI Changes

1. **Regenerate Dialog**: Show split option when summary has private content
2. **Summary Card**: Show "Split from" link when viewing a split summary
3. **Summary Detail**: Show related public/private summary link
4. **Filter**: Option to show/hide split summaries

## Consequences

### Positive
1. **Granular wiki visibility**: Public content can be wiki-ingested
2. **Privacy preservation**: Private content remains separate and protected
3. **Traceability**: Split summaries linked to original
4. **User choice**: Can regenerate as-is or split

### Negative
1. **Complexity**: Two summaries instead of one
2. **Storage**: Slight increase in storage for split summaries
3. **UX**: Users must understand split concept

### Technical Debt Created
- Regeneration pipeline needs refactoring to support split
- Need migration for existing mixed summaries (optional bulk split)

## Alternatives Considered

### 1. Always Split Automatically
Rejected: Users may want combined view for internal use

### 2. Redact Private Content In-Place
Rejected: Loses private channel information entirely

### 3. Content-Level Redaction
Mark individual paragraphs as private within same summary.
Rejected: More complex, harder to implement wiki boundary

## Implementation Order

1. ✅ Add split tracking columns to database (Migration 061)
2. ✅ Implement channel grouping logic in regeneration (`group_channels_by_privacy()`)
3. ✅ Update regeneration endpoint to accept `split_private` option
4. ✅ Add UI for split option in regenerate dialog
5. ✅ Show split relationship in summary cards/detail
6. (Optional) Bulk split tool for existing mixed summaries

## Related ADRs

- **ADR-073**: Channel Access Controls (defines locked channels)
- **ADR-074**: Private Channel Content Detection (detection logic)
- **ADR-067**: Wiki Ingestion (split enables selective ingestion)
