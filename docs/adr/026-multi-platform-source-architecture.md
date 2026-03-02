# ADR-026: Multi-Platform Source Architecture

## Status
ACCEPTED (Minimal Implementation Completed)

## Implementation (Spike - March 2026)

A minimal "spike" implementation was completed to enable viewing WhatsApp summaries alongside Discord summaries without building the full Linked Sources infrastructure.

### Approach: PRIMARY_GUILD_ID Pattern

Instead of implementing the full `guild_linked_sources` table, we use a simpler approach:

1. **Store WhatsApp summaries under a primary Discord guild** - Non-Discord sources (WhatsApp, Slack, etc.) store their summaries with `guild_id` set to `PRIMARY_GUILD_ID` from environment config
2. **Preserve original source in `archive_source_key`** - The source attribution (e.g., `whatsapp:ai-code`) is preserved for display and filtering
3. **Filter by platform** - Added platform filter to allow viewing only Discord or only WhatsApp summaries

### Files Modified

**Backend:**
- `src/archive/generator.py` - Modified `_save_to_database()` to use `PRIMARY_GUILD_ID` for non-Discord sources
- `src/dashboard/routes/archive.py` - Added `/migrate-source` endpoint for existing summaries
- `src/dashboard/routes/summaries.py` - Added `platform` query parameter
- `src/data/sqlite.py` - Added `platform` filter to `find_by_guild()` and `count_by_guild()`

**Frontend:**
- `src/frontend/src/components/summaries/SummaryFilters.tsx` - Added Platform dropdown filter
- `src/frontend/src/components/summaries/StoredSummariesTab.tsx` - Pass platform filter to API
- `src/frontend/src/hooks/useStoredSummaries.ts` - Added platform to query params

**Configuration:**
- `.env` - Added `PRIMARY_GUILD_ID=1283874310720716890`
- `fly.toml` - Added `PRIMARY_GUILD_ID` for production

### Key Code Change

```python
# src/archive/generator.py - _save_to_database()
async def _save_to_database(self, ...):
    """
    ADR-026: For non-Discord sources (WhatsApp, Slack, etc.), store
    summaries under the PRIMARY_GUILD_ID so they appear in the main
    guild's summaries view. The original source is preserved in
    archive_source_key for attribution.
    """
    # Determine guild_id for storage
    if job.source.source_type != SourceType.DISCORD:
        storage_guild_id = os.environ.get("PRIMARY_GUILD_ID", job.source.server_id or "")
    else:
        storage_guild_id = job.source.server_id or ""
```

### Migration Endpoint

For existing WhatsApp summaries stored with the wrong `guild_id`:

```bash
curl -X POST "https://summarybot-ng.fly.dev/api/v1/archive/migrate-source" \
  -H "X-Test-Auth-Key: $TEST_AUTH_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"source_key": "whatsapp:ai-code", "target_guild_id": "1283874310720716890"}'
```

### What This Enables

1. WhatsApp summaries appear in the main guild's summaries list at `/guilds/{PRIMARY_GUILD_ID}/summaries`
2. Users can filter by platform (All/Discord/WhatsApp) to find specific summaries
3. The `archive_source_key` field shows the original source (e.g., "whatsapp:ai-code")
4. No database schema changes required

### What This Doesn't Solve (Deferred)

- Multiple organizations with different primary guilds
- Formal linking/unlinking of sources
- Permission-level access control
- Audit logging
- Source ownership verification

These require the full Linked Sources model described in this ADR.

---

## Context

SummaryBot-NG was originally built around Discord guilds as the primary organizational unit. The URL structure, database schema, and UI all assume a Discord-centric model:

- Routes: `/guilds/{discord_guild_id}/summaries`
- Database: `guild_id` as primary key for summaries
- UI: Guild selector in sidebar, guild-scoped views

With the addition of WhatsApp support (ADR-006), we've introduced a new platform that doesn't fit this model:

### Current Situation

**The Agentics Foundation example:**
- 1 Discord guild (ID: `1283874310720716890`)
- Multiple WhatsApp groups/channels (potentially in a WhatsApp Community)
- Each WhatsApp group has its own `group_id` (e.g., `ai-code`)

**Current Implementation Problems:**
1. WhatsApp summaries are stored with `guild_id: "{whatsapp_group_id}"` (e.g., `ai-code`)
2. The summaries page at `/guilds/{discord_guild_id}/summaries` only shows summaries where `guild_id` matches
3. WhatsApp summaries don't appear in the Discord guild's summaries view
4. No unified view across platforms for an organization

**Attempted Quick Fix (reverted):**
- Navigate to `/guilds/{whatsapp_group_id}/summaries` to view WhatsApp summaries
- This is a hack that treats WhatsApp groups as pseudo-guilds
- Doesn't scale for organizations with multiple platforms

## Decision Drivers

1. **Organization-centric**: Users think in terms of their organization, not individual platforms
2. **Platform diversity**: Support Discord, WhatsApp, Slack, Telegram without platform-specific hacks
3. **Backward compatibility**: Existing Discord summaries should continue to work
4. **Scalability**: Support organizations with dozens of WhatsApp groups + Discord guilds
5. **Source attribution**: Clear indication of where each summary originated

## Options Considered

### Option A: Organization Container Model

Introduce a new "Organization" entity that contains multiple sources:

```
Organization (e.g., "Agentics Foundation")
├── Discord Guild: 1283874310720716890
│   ├── #general summaries
│   └── #dev summaries
├── WhatsApp Group: ai-code
│   └── summaries
├── WhatsApp Group: marketing
│   └── summaries
└── Slack Workspace: agentics
    └── #general summaries
```

**Database Changes:**
```sql
CREATE TABLE organizations (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TIMESTAMP
);

CREATE TABLE organization_sources (
  organization_id TEXT REFERENCES organizations(id),
  source_key TEXT NOT NULL,  -- "discord:123", "whatsapp:ai-code"
  source_type TEXT NOT NULL,
  source_name TEXT NOT NULL,
  PRIMARY KEY (organization_id, source_key)
);

-- Add to stored_summaries
ALTER TABLE stored_summaries ADD COLUMN organization_id TEXT;
```

**URL Structure:**
- `/orgs/{org_id}/summaries` - All summaries across platforms
- `/orgs/{org_id}/sources` - Manage connected sources
- `/orgs/{org_id}/sources/{source_key}/summaries` - Source-specific view

**Pros:**
- Clean conceptual model
- Supports arbitrary platform combinations
- Future-proof for new platforms

**Cons:**
- Significant migration effort
- Requires org creation/management UI
- Breaking change to existing URLs

### Option B: Source-Keyed Navigation

Keep the current model but add source-aware routing:

**URL Structure:**
- `/sources` - List all sources (Discord guilds + WhatsApp groups + etc.)
- `/sources/{source_key}/summaries` - View summaries for a specific source
- `/guilds/{id}/*` - Legacy Discord-specific routes (kept for compatibility)

**Database Changes:**
- No schema changes required
- `archive_source_key` already tracks the source

**UI Changes:**
- Add "Sources" to sidebar showing all platforms
- Source cards link to source-specific summary views
- Archive page becomes the hub for non-Discord sources

**Pros:**
- Minimal database changes
- Backward compatible
- Incremental adoption

**Cons:**
- No unified cross-platform view
- "Sources" vs "Guilds" terminology confusion
- Doesn't solve organization grouping

### Option C: Unified Source Model (Recommended)

Evolve the existing model to treat all platforms uniformly:

**Key Insight:** A Discord guild IS a source, just like a WhatsApp group. The current `guild_id` field is really `source_id`.

**Database Changes:**
```sql
-- Rename for clarity (or add alias)
-- guild_id -> source_id (conceptually)

-- Add source metadata table
CREATE TABLE sources (
  source_key TEXT PRIMARY KEY,  -- "discord:123", "whatsapp:ai-code"
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,      -- The platform-specific ID
  display_name TEXT NOT NULL,
  parent_source_key TEXT,       -- For WhatsApp Community -> Group hierarchy
  metadata JSONB,
  created_at TIMESTAMP
);
```

**URL Structure:**
- `/sources` - All sources (replaces guild selector for multi-platform users)
- `/sources/{source_key}` - Dashboard for a source
- `/sources/{source_key}/summaries` - Summaries for a source
- `/guilds/{id}/*` - Redirect to `/sources/discord:{id}/*` for compatibility

**UI Changes:**
1. Sidebar shows "Sources" instead of (or in addition to) "Guilds"
2. Each source card shows platform icon (Discord, WhatsApp, etc.)
3. Archive/Retrospective page integrated into source management
4. Filter summaries by source type

**Pros:**
- Conceptually clean - everything is a "source"
- Incremental migration path
- Supports platform hierarchy (WhatsApp Communities)
- Archive page becomes natural home for all sources

**Cons:**
- Terminology change (guild -> source)
- Some URL restructuring needed

## Recommendation

**Option C: Unified Source Model** with phased implementation:

### Phase 1: Backend Unification (Low Risk)
- Add `sources` table to track all sources
- Populate from existing Discord guilds + WhatsApp imports
- Keep `guild_id` field but treat as `source_id`
- Archive API already uses `source_key` correctly

### Phase 2: Source-Aware UI (Medium Risk)
- Add `/sources` route listing all sources
- Source cards show platform type with icon
- "View Summaries" button on each source card
- Archive page shows sources grouped by platform

### Phase 3: URL Migration (Higher Risk, Optional)
- Add `/sources/{source_key}/*` routes
- Redirect `/guilds/{id}/*` to `/sources/discord:{id}/*`
- Update internal links

## Immediate Actions

Before implementing the full solution, we should:

1. **Document the current state** - WhatsApp summaries exist but aren't easily viewable
2. **Add source-type filter** to Archive summaries endpoint
3. **Add "View Summaries" to Archive source cards** - Navigate to a source-specific view
4. **Create source-aware summaries route** - `/sources/{source_key}/summaries`
5. **Add `guild_linked_sources` table** - Enable cross-platform access control
6. **Auto-link existing WhatsApp sources** - Connect to primary Discord guild via config
7. **Add WhatsApp import deduplication** - Prevent duplicate messages from overlapping uploads

## Questions to Resolve

1. Should WhatsApp Communities be modeled as parent sources containing groups?
2. Do users need cross-platform unified views, or is per-source sufficient?
3. Should the sidebar show all sources, or keep Discord-primary with "Other Sources" section?
4. ~~How do permissions work across platforms? (Discord has roles, WhatsApp doesn't)~~ → See Permission Model below

## Permission Model for Cross-Platform Access

### Current State

Discord OAuth provides identity + guild membership:
```
User logs in via Discord
  ↓
Discord API returns: guilds where user has MANAGE_GUILD permission
  ↓
Filter to: guilds where bot is also present
  ↓
JWT contains: { guilds: ["1283874310720716890", ...] }
  ↓
API checks: requested guild_id ∈ user.guilds
```

**Problem**: WhatsApp sources have no OAuth flow. Users can't access WhatsApp summaries because `whatsapp_group_id` is not in their Discord guilds list.

### Proposed Solution: Linked Sources Model

**Principle**: Discord remains the identity provider. Guild admins can link external sources to their guild. Anyone with guild access inherits access to linked sources.

```
Discord Guild: 1283874310720716890 (Agentics Foundation)
  ├── Native Discord channels (existing)
  └── Linked Sources:
      ├── whatsapp:ai-code
      ├── whatsapp:marketing
      └── slack:agentics-workspace (future)
```

### Database Schema

```sql
-- Track which sources are linked to which Discord guild
CREATE TABLE guild_linked_sources (
  guild_id TEXT NOT NULL,           -- Discord guild ID (the "owner")
  source_key TEXT NOT NULL,         -- "whatsapp:ai-code", "slack:xyz"
  linked_by TEXT NOT NULL,          -- Discord user ID who linked it
  linked_at TIMESTAMP DEFAULT NOW(),
  permissions TEXT DEFAULT 'full',  -- 'full', 'view_only' (future)
  PRIMARY KEY (guild_id, source_key)
);

-- Index for reverse lookup (which guild owns this source?)
CREATE INDEX idx_linked_sources_key ON guild_linked_sources(source_key);
```

### Access Control Flow

```
User requests: /sources/whatsapp:ai-code/summaries
  ↓
Lookup: SELECT guild_id FROM guild_linked_sources
        WHERE source_key = 'whatsapp:ai-code'
  ↓
Returns: guild_id = '1283874310720716890'
  ↓
Check: '1283874310720716890' ∈ user.guilds?
  ↓
If yes → Grant access
If no  → 403 Forbidden
```

### API Changes

```python
# New endpoint: Link a source to a guild
@router.post("/guilds/{guild_id}/linked-sources")
async def link_source(
    guild_id: str,
    body: LinkSourceRequest,  # { source_key: "whatsapp:ai-code" }
    user: dict = Depends(get_current_user),
):
    """Link an external source to this guild. Requires MANAGE_GUILD."""
    _check_guild_access(guild_id, user)
    # ... create guild_linked_sources record

# New endpoint: List linked sources
@router.get("/guilds/{guild_id}/linked-sources")
async def list_linked_sources(guild_id: str, user: dict = Depends(get_current_user)):
    """List all sources linked to this guild."""

# Modified: Source access check
async def check_source_access(source_key: str, user: dict) -> bool:
    """Check if user can access a source (native or linked)."""
    # 1. Is it a Discord source they have direct access to?
    if source_key.startswith("discord:"):
        discord_id = source_key.split(":")[1]
        return discord_id in user.get("guilds", [])

    # 2. Is it linked to a guild they have access to?
    linked_guild = await get_linked_guild(source_key)
    if linked_guild:
        return linked_guild in user.get("guilds", [])

    return False
```

### UI Flow for Linking Sources

1. **Archive Page** shows available WhatsApp sources (from imports)
2. Admin clicks "Link to Guild" on a WhatsApp source card
3. Modal shows their Discord guilds → select one
4. Source now appears under that guild's "Linked Sources" section
5. All guild members can now view summaries from that source

### Permission Levels (Future)

| Level | Can View Summaries | Can Regenerate | Can Delete | Can Unlink |
|-------|-------------------|----------------|------------|------------|
| `view_only` | ✓ | ✗ | ✗ | ✗ |
| `full` | ✓ | ✓ | ✓ | ✗ |
| `admin` | ✓ | ✓ | ✓ | ✓ |

Initially, we'll implement `full` access only. Granular permissions can be added later.

### Edge Cases

1. **Orphan sources**: WhatsApp sources that haven't been linked to any guild
   - Show in Archive page with "Link to Guild" CTA
   - Not accessible via normal auth flow until linked

2. **Multiple guilds linking same source**:
   - Allow it (source can be shared across organizations)
   - First-linked guild is "primary" (for display purposes only)

3. **Unlinking a source**:
   - Only the original linker or guild admins can unlink
   - Summaries remain in database, just become inaccessible until re-linked

4. **Source key conflicts**:
   - Use namespaced keys: `whatsapp:{group_id}`, `slack:{workspace}:{channel}`
   - Prevents collisions across platforms

5. **Organization with multiple Discord guilds**:
   See "Multi-Guild Organizations" section below.

### Multi-Guild Organizations

**Scenario**: An organization operates multiple Discord servers with potentially overlapping channel names.

```
Agentics Foundation
├── Discord: "Agentics Community" (guild_id: 111, public)
│   ├── #general
│   └── #announcements
├── Discord: "Agentics Team" (guild_id: 222, internal)
│   ├── #general          ← Same name, different content
│   └── #engineering
├── Discord: "Agentics Partners" (guild_id: 333, external)
│   └── #general          ← Same name, different content
└── WhatsApp: ai-code
```

**Key insight**: Channel names aren't unique, but `source_key` is.

**Source keys are always unique**:
```
discord:111           → Agentics Community (guild)
discord:111:456       → Agentics Community #general (channel)
discord:222           → Agentics Team (guild)
discord:222:789       → Agentics Team #general (different channel!)
whatsapp:ai-code      → WhatsApp group
```

**Access model for multi-guild orgs**:

| User | Has Access To | Can See |
|------|---------------|---------|
| Community member | Guild 111 only | Community summaries |
| Team member | Guilds 111 + 222 | Community + Team summaries |
| Partner | Guild 333 only | Partner summaries |
| Admin (all guilds) | Guilds 111, 222, 333 | Everything |

**WhatsApp linking**: Admin links `whatsapp:ai-code` to guild 222 (Team). Only Team members see it.

**Future: Organization Federation** (Phase 4+)

For organizations that need unified views across multiple Discord guilds:

```sql
CREATE TABLE organizations (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TIMESTAMP
);

CREATE TABLE organization_guilds (
  organization_id TEXT REFERENCES organizations(id),
  guild_id TEXT NOT NULL,
  role TEXT DEFAULT 'member',  -- 'primary', 'member'
  linked_at TIMESTAMP,
  PRIMARY KEY (organization_id, guild_id)
);
```

This enables:
- `/orgs/{org_id}/summaries` - Unified view across all federated guilds
- Cross-guild summary search
- Org-level analytics

**But this is complex** - requires:
- Org creation UI
- Federated permission model (who can add guilds to org?)
- Conflict resolution (same user in multiple orgs)

**Recommendation**: Defer federation. The per-guild model with linked sources handles 90% of use cases. Users who manage multiple guilds see each independently in the guild selector.

### WhatsApp Transcript Import Handling

**Current State**: Transcripts are stored but NOT deduplicated.

```
archive/sources/whatsapp/{group_name}_{group_id}/imports/
├── imp_abc123_messages.json   ← Upload: Jan 1-15
├── imp_def456_messages.json   ← Upload: Jan 10-20 (overlaps!)
└── import-manifest.json
```

When querying messages, ALL imports are loaded → duplicates appear.

**Problem**: Uploading overlapping date ranges creates duplicate messages in summaries.

**Proposed Solution: Message Deduplication**

Option A: **Dedupe on read** (simpler, lazy)
```python
async def get_messages_for_period(self, group_id, start, end):
    all_messages = []
    seen_ids = set()

    for msg_file in imports_dir.glob("*_messages.json"):
        for msg in messages:
            # Dedupe by content hash (timestamp + sender + content[:50])
            msg_key = f"{msg['timestamp']}|{msg['sender']}|{msg['content'][:50]}"
            if msg_key not in seen_ids:
                seen_ids.add(msg_key)
                all_messages.append(msg)

    return sorted(all_messages, key=lambda m: m["timestamp"])
```

Option B: **Dedupe on write** (more robust, upfront cost)
```python
async def import_txt_export(self, file_path, group_id, group_name):
    # Load existing messages from all imports
    existing = await self.get_all_messages(group_id)
    existing_keys = {self._message_key(m) for m in existing}

    # Only add new messages
    new_messages = [m for m in parsed_messages
                    if self._message_key(m) not in existing_keys]

    # Save only net-new messages
    await self._save_import(group_id, new_messages, ...)
```

Option C: **Replace overlapping ranges** (destructive but clean)
```python
# On upload of Jan 10-20:
# 1. Identify overlapping imports (Jan 1-15 overlaps Jan 10-15)
# 2. Remove messages from Jan 10-15 in old import
# 3. Add new import with Jan 10-20
```

**Recommendation**: Option A (dedupe on read) for simplicity. WhatsApp message IDs aren't guaranteed unique, so we hash `timestamp|sender|content[:50]` as a fingerprint.

**Import Manifest Enhancement**:
```json
{
  "imports": [
    {
      "import_id": "imp_abc123",
      "date_range": {"start": "2025-01-01", "end": "2025-01-15"},
      "message_count": 500,
      "superseded_by": null
    },
    {
      "import_id": "imp_def456",
      "date_range": {"start": "2025-01-10", "end": "2025-01-20"},
      "message_count": 400,
      "overlaps_with": ["imp_abc123"],
      "net_new_messages": 250
    }
  ],
  "coverage": {
    "earliest": "2025-01-01",
    "latest": "2025-01-20",
    "total_unique_messages": 750
  }
}
```

### Migration Path

**Phase 1**:
- Add `guild_linked_sources` table
- Auto-link existing WhatsApp sources to the primary Discord guild (manual or config-based)
- Existing Discord sources work unchanged (direct access)

**Phase 2**:
- Add "Linked Sources" section to guild settings
- Add "Link to Guild" button on Archive source cards
- Update source access checks to include linked sources

**Phase 3**:
- Add permission levels (view_only, admin)
- Add audit log for link/unlink actions

## Known Limitations & Failure Scenarios

### Critical Limitations

#### 1. Discord-Only Identity (P1 - Architectural)

**Problem**: Organizations without Discord cannot use the system.

| Scenario | Impact |
|----------|--------|
| Slack + WhatsApp org, no Discord | Completely blocked |
| WhatsApp-only user (e.g., marketing team) | Cannot log in to view own summaries |
| Discord OAuth outage | All access blocked, no fallback |

**Mitigation Options**:
- Add email/password auth as fallback
- Add API key auth for programmatic access
- Support Slack OAuth as alternative identity provider

**Status**: Not addressed. Discord OAuth is currently mandatory.

#### 2. Source Ownership & Hijacking (P2 - Security)

**Problem**: No verification that the person uploading a WhatsApp export actually owns/administers that group.

| Scenario | Risk |
|----------|------|
| User A uploads `whatsapp:exec-chat` | User B (different org) could link it to their guild first |
| Global namespace collision | Two orgs with `whatsapp:marketing` - first uploader "wins" |
| Malicious upload | Could upload fabricated conversations under any group_id |

**Mitigation Options**:
- Require ownership token: uploader must include a secret phrase that appears in the export
- Namespace by uploader: `whatsapp:{user_id}:{group_id}`
- Admin approval: new sources require review before linking

**Status**: Not addressed. Source keys are first-come-first-served.

### Data Integrity Limitations

#### 3. Edited Messages Not Handled (P2)

**Problem**: WhatsApp allows editing messages after sending. Our dedup keeps the *first* version seen.

```
Import v1 (Jan 15): "Meeting at 3pm"
Import v2 (Jan 20): "Meeting at 4pm" (edited)
                ↓
We keep: "Meeting at 3pm" (wrong!)
```

**Mitigation Options**:
- Keep latest version: update fingerprint index on each import
- Keep both: store versions with `edited_at` timestamp
- Detect edits: compare content when fingerprint matches on timestamp+sender

**Status**: Not addressed. First version wins.

#### 4. Timezone Deduplication Failures (P3)

**Problem**: WhatsApp exports use device timezone. Same message exported from different phones may have different timestamps.

```
Phone A (PST): "2025-01-15T10:00:00"
Phone B (UTC): "2025-01-15T18:00:00"
                ↓
Different fingerprints → duplicate messages
```

**Mitigation Options**:
- Normalize to UTC on import (requires timezone detection)
- Fuzzy timestamp matching (±1 hour window)
- Use message content + sender only (more collisions)

**Status**: Not addressed. Timestamps used as-is.

#### 5. Memory Pressure on Large Imports (P3)

**Problem**: Dedup on read loads all messages from all imports into memory.

| Import Size | Memory Impact |
|-------------|---------------|
| 10k messages, 5 imports | ~50MB - OK |
| 100k messages, 50 imports | ~500MB - Risky |
| 1M messages, 100 imports | ~5GB - OOM |

**Mitigation Options**:
- Pre-compute fingerprint index on import (not on read)
- Streaming dedup with bloom filter
- Limit imports per source (archive old imports)

**Status**: Partially addressed. Dedup on read is simple but doesn't scale.

### Access Control Limitations

#### 6. All-or-Nothing Guild Access (P2)

**Problem**: Linking a source to a guild gives ALL members access. No partial sharing.

| Scenario | Desired | Actual |
|----------|---------|--------|
| Share WhatsApp with 5 of 500 members | 5 see it | 500 see it |
| Partners need limited access | View-only | Full access |

**Mitigation Options**:
- Implement permission levels (view_only, full, admin) - already in roadmap
- Create sub-guilds or roles for access control
- Source-level access lists (complex)

**Status**: Deferred to Phase 3. Currently full access only.

#### 7. JWT Revocation Delay (P3)

**Problem**: User's JWT contains guild list. Unlink/permission changes don't take effect until JWT refresh (hours).

**Mitigation Options**:
- Shorter JWT expiry (more Discord API calls)
- Real-time permission check on sensitive operations
- Maintain server-side revocation list

**Status**: Not addressed. JWT caching is a known tradeoff.

### Operational Limitations

#### 8. Orphan Source Accumulation (P3)

**Problem**: Uploaded but never linked sources accumulate in archive. No cleanup mechanism.

```
archive/sources/whatsapp/
├── test_abc/        ← Uploaded Jan 2024, never linked
├── old-group_xyz/   ← Uploaded Feb 2024, never linked
├── typo_123/        ← Uploaded Mar 2024, never linked
└── ... (hundreds more)
```

**Mitigation Options**:
- Auto-delete after 30 days if not linked
- Admin UI to view/delete orphan sources
- Require linking at upload time

**Status**: Not addressed. Manual filesystem cleanup required.

#### 9. No Audit Trail (P2)

**Problem**: No logging of who linked/unlinked sources, who accessed summaries.

| Question | Answer |
|----------|--------|
| Who linked `whatsapp:exec-chat`? | Unknown |
| When was it unlinked? | Unknown |
| Who accessed it last month? | Unknown |

**Mitigation Options**:
- Add `audit_log` table: `(timestamp, user_id, action, source_key, guild_id)`
- Log access events (may be verbose)
- Integrate with external audit system

**Status**: Not addressed. Critical for enterprise/compliance.

#### 10. No Source Deletion (P3 - GDPR Risk)

**Problem**: Can unlink but cannot delete source data. GDPR "right to be forgotten" requires manual intervention.

**Mitigation Options**:
- Add hard delete endpoint (admin only)
- Cascade delete: source + all summaries + all imports
- Soft delete with scheduled purge

**Status**: Not addressed. Manual filesystem deletion required.

### Platform-Specific Limitations

#### 11. No Real-Time WhatsApp (P3 - UX)

**Problem**: Discord = live summaries. WhatsApp = batch imports. User confusion.

**Mitigation Options**:
- Clear UI indicators: "Last updated: 3 days ago"
- Scheduled import reminders
- WhatsApp Business API integration (future)

**Status**: Inherent limitation. UI should set expectations.

#### 12. Context Loss in WhatsApp Exports (P3)

**Problem**: WhatsApp native exports lack threading, reactions, read receipts. Summary quality may suffer.

| Feature | Discord | WhatsApp Export |
|---------|---------|-----------------|
| Reply threading | ✓ | Partial (text only) |
| Reactions | ✓ | ✗ |
| Read receipts | ✓ | ✗ |
| Attachments | ✓ | Filename only |

**Mitigation Options**:
- Use reader bot JSON format (has more metadata)
- Detect reply patterns in text ("Replying to @user:")
- Accept lower quality for WhatsApp summaries

**Status**: Inherent limitation. Reader bot format recommended.

### Multi-Guild Limitations

#### 13. No Unified Cross-Guild View (P2)

**Problem**: User with access to 5 guilds must view each separately. No dashboard across all.

**Mitigation Options**:
- Organization federation (Phase 4+)
- Client-side aggregation (fetch from multiple guilds)
- "My Sources" view showing all accessible sources

**Status**: Deferred. Per-guild model is simpler but less powerful.

#### 14. Primary Guild Deletion (P3)

**Problem**: WhatsApp linked to guild that gets deleted. Source becomes orphaned.

**Mitigation Options**:
- Prevent guild deletion if sources linked
- Auto-unlink on guild deletion (sources become orphans)
- Transfer ownership to another guild

**Status**: Not addressed. Edge case, but could cause data loss.

---

## Limitation Severity Summary

| ID | Issue | Severity | Likelihood | Priority |
|----|-------|----------|------------|----------|
| 1 | Discord-only identity | High | Medium | **P1** |
| 2 | Source hijacking | High | Low | **P2** |
| 3 | Edited messages | Medium | Medium | **P2** |
| 6 | All-or-nothing access | Medium | High | **P2** |
| 9 | No audit trail | Medium | High | **P2** |
| 13 | No unified view | Medium | High | **P2** |
| 4 | Timezone dedup | Medium | Medium | **P3** |
| 5 | Memory pressure | Low | Medium | **P3** |
| 7 | JWT revocation delay | Low | Medium | **P3** |
| 8 | Orphan accumulation | Low | High | **P3** |
| 10 | No source deletion | Medium | Low | **P3** |
| 11 | No real-time WhatsApp | Low | High | **P3** |
| 12 | WhatsApp context loss | Low | High | **P3** |
| 14 | Primary guild deletion | Medium | Low | **P3** |

## Related ADRs

- ADR-006: Retrospective Summary Archive (introduced WhatsApp support)
- ADR-008: Unified Summary Storage (archive_source_key field)

## References

- WhatsApp Communities: Groups can be part of a Community with shared admin
- Slack: Workspaces contain channels, similar to Discord guilds
- Telegram: Groups and Channels have different semantics
