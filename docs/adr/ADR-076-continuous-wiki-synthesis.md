# ADR-076: Continuous Wiki Synthesis

## Status
Accepted

## Context
Wiki pages accumulate content through ingest operations, but the synthesized view can become stale when new content is added. Users need:
1. A toggle to enable/disable automatic wiki synthesis
2. On-demand synthesis when accessing stale pages
3. Visibility into when synthesis occurred
4. Audit trail for synthesis operations

## Decision

### 1. Auto-Synthesis Guild Setting
Add `wiki_auto_synthesis` boolean column to `guild_configs` table (migration 062):
- Default: TRUE (synthesis enabled)
- Configurable via Wiki settings UI and API

### 2. On-Demand Synthesis on Page Access
When a wiki page is accessed via `GET /guilds/{guild_id}/wiki/pages/{path}`:
1. Check if `wiki_auto_synthesis` is enabled for the guild
2. Determine if page is "stale":
   - No synthesis exists, OR
   - `page.updated_at > page.synthesis_updated_at`
3. If stale and auto-synthesis enabled, synthesize before returning

### 3. Audit Logging
Log synthesis events with event type `action.wiki.auto_synthesize`:
- Guild ID
- Page path
- Model used
- Source count
- Trigger: "on_access" or "post_ingest"

### 4. UI Visibility
- Show `synthesis_updated_at` timestamp on wiki page view
- Show "Auto-synthesized" indicator when synthesis was triggered automatically
- Auto-synthesis toggle in Wiki header with tooltip explanation

### 5. API Endpoints
```
GET  /guilds/{guild_id}/wiki/settings
PATCH /guilds/{guild_id}/wiki/settings
  - wiki_auto_ingest: boolean
  - wiki_auto_synthesis: boolean
  - wiki_synthesis_job_enabled: boolean
  - wiki_synthesis_job_interval_hours: integer
```

### 6. Periodic Synthesis Job (Amendment)

In addition to on-access synthesis, a periodic background job regenerates dirty pages:

#### Dirty Page Detection
A page is marked "dirty" (needs regeneration) when:
- `page.updated_at > page.synthesis_updated_at`, OR
- `synthesis_updated_at IS NULL`

#### Guild Settings (migration 090)
```sql
ALTER TABLE guild_configs ADD COLUMN wiki_synthesis_job_enabled BOOLEAN DEFAULT TRUE;
ALTER TABLE guild_configs ADD COLUMN wiki_synthesis_job_last_run TEXT;
ALTER TABLE guild_configs ADD COLUMN wiki_synthesis_job_interval_hours INTEGER DEFAULT 24;
```

#### Job Behavior
1. Runs as a scheduled task (configurable interval, default 24 hours)
2. For each guild with `wiki_synthesis_job_enabled = TRUE`:
   - Find all pages where `updated_at > synthesis_updated_at`
   - Process dirty pages in batches (max 10 per run to limit costs)
   - Update `wiki_synthesis_job_last_run` after completion
3. Creates a job record for tracking (reuses `wiki_regeneration_jobs` table from ADR-084)

#### UI Display
- Show toggle: "Periodic synthesis job enabled"
- Show last run time: "Last job: May 9, 2026 at 3:45 PM"
- Show interval selector: 6h / 12h / 24h / 48h
- Show count of dirty pages awaiting regeneration

#### Manual Trigger
- Button to trigger the job immediately (respects rate limits)
- Rate limited: max once per 5 minutes per guild

## Consequences

### Positive
- Users always see synthesized content when enabled
- Clear audit trail for synthesis operations
- Configurable per-guild behavior
- Transparent indication of synthesis timing

### Negative
- Additional latency on first access to stale pages
- Increased LLM API costs when auto-synthesis is enabled

## Implementation
- Migration: `062_wiki_auto_synthesis.sql` (auto-synthesis toggle)
- Migration: `090_wiki_synthesis_job.sql` (periodic job settings)
- Backend: `src/dashboard/routes/wiki.py` (`_maybe_synthesize_on_access`, job endpoints)
- Backend: `src/wiki/synthesis_job.py` (periodic job logic)
- Frontend: `src/frontend/src/pages/Wiki.tsx` (toggle + timestamp display + job controls)
