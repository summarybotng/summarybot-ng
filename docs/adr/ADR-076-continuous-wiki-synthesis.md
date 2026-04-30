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
```

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
- Migration: `062_wiki_auto_synthesis.sql`
- Backend: `src/dashboard/routes/wiki.py` (`_maybe_synthesize_on_access`)
- Frontend: `src/frontend/src/pages/Wiki.tsx` (toggle + timestamp display)
