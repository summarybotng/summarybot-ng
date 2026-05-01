# ADR-080: Wiki Perspective Filtering

## Status
Proposed

## Context

Wiki auto-ingest (ADR-067) currently ingests all summaries regardless of their perspective. When multiple perspectives are generated for the same time period (e.g., a "support" perspective summary and a "general" daily comprehensive summary), both get ingested into the wiki.

### Current Problem

1. **Same-day duplicates** - A support perspective summary and a general summary for the same day both get ingested
2. **Wiki synthesis confusion** - The wiki synthesizer tries to merge conflicting perspectives, leading to confusing outputs
3. **Content pollution** - Support/security perspectives contain specialized content not suitable for a general-audience wiki
4. **No admin control** - Wiki admins cannot choose which perspectives should feed into their wiki

### Perspective Types

From ADR-033 (Custom Perspectives):
- `general` - Default, broad audience
- `developer` - Technical focus
- `marketing` - External communication focus
- `executive` - High-level strategic view
- `support` - Customer support focus
- `security` - Security-focused analysis
- Custom user-defined perspectives

## Decision

### 1. Add Wiki Allowed Perspectives Setting

Add a `wiki_allowed_perspectives` setting to `guild_configs` that controls which perspective summaries are ingested into the wiki.

```sql
-- Migration 064
ALTER TABLE guild_configs
ADD COLUMN wiki_allowed_perspectives TEXT DEFAULT '["general"]';
```

Default value `["general"]` means only general-perspective summaries are auto-ingested.

### 2. Filter at Auto-Ingest Time

Modify the auto-ingest flow in `src/scheduling/delivery/dashboard.py` to check the summary's perspective against the allowed list:

```python
# In deliver_to_dashboard() after wiki_auto_ingest check

# Get allowed perspectives (default to general only)
allowed_perspectives = ["general"]
if row and row.get('wiki_allowed_perspectives'):
    try:
        allowed_perspectives = json.loads(row['wiki_allowed_perspectives'])
    except json.JSONDecodeError:
        pass

# Get summary's perspective from metadata
summary_perspective = "general"
if summary.metadata and summary.metadata.get('perspective'):
    summary_perspective = summary.metadata['perspective']

# Skip if perspective not allowed
if summary_perspective not in allowed_perspectives:
    logger.info(
        f"Skipping wiki ingest for summary {summary.id}: "
        f"perspective '{summary_perspective}' not in allowed list {allowed_perspectives}"
    )
    return
```

### 3. API Endpoint for Available Perspectives

New endpoint to show what perspectives exist in the guild's summaries:

```
GET /guilds/{guild_id}/wiki/available-perspectives
```

Response:
```json
{
  "available": ["general", "developer", "support", "security"],
  "allowed": ["general"],
  "counts": {
    "general": 45,
    "developer": 12,
    "support": 8,
    "security": 3
  }
}
```

This helps wiki admins see what perspectives they could enable.

### 4. Settings Update

Extend the wiki settings endpoint:

```
PUT /guilds/{guild_id}/wiki/settings
{
  "auto_ingest": true,
  "allowed_perspectives": ["general", "developer"]
}
```

### 5. Frontend UI

Add perspective selection to the Wiki settings page:
- Multi-select checkbox or chip selector
- Show available perspectives with counts
- Help text explaining the impact
- Default "general" pre-selected

## Implementation

### Files to Create

| File | Purpose |
|------|---------|
| `src/data/migrations/064_wiki_allowed_perspectives.sql` | Add column to guild_configs |

### Files to Modify

| File | Changes |
|------|---------|
| `src/scheduling/delivery/dashboard.py` | Add perspective filtering at auto-ingest |
| `src/dashboard/routes/wiki.py` | Add available-perspectives endpoint, extend settings |
| `src/frontend/src/pages/Wiki.tsx` | Add perspective selection UI |

### Migration

```sql
-- 064_wiki_allowed_perspectives.sql
ALTER TABLE guild_configs
ADD COLUMN wiki_allowed_perspectives TEXT DEFAULT '["general"]';
```

## Consequences

### Positive
- Wiki content focused on intended perspectives
- Admin control over wiki composition
- Eliminates same-day duplicate confusion
- Clear separation of concern - support summaries stay out of general wiki
- Easy to enable more perspectives if desired

### Negative
- Support/security summaries won't auto-ingest by default (intended behavior)
- Existing wiki content from other perspectives remains (no retroactive cleanup)
- Slight increase in settings complexity

### Neutral
- General summaries continue to work exactly as before
- No change for guilds that only generate general summaries

## Future Considerations

1. **Perspective-specific wikis** - Could have separate wiki collections per perspective
2. **Retroactive filtering** - Offer option to remove existing non-allowed perspective pages
3. **Perspective inheritance** - Wiki pages could track which perspectives contributed to them

## References
- ADR-067: Automatic Wiki Ingestion
- ADR-033: Custom Perspectives
- ADR-056: Compounding Wiki Standard
- ADR-065: Wiki Synthesis Controls
