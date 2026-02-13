# ADR-005: Summary Delivery Destinations — UI Storage and Channel Push

**Status:** Proposed
**Date:** 2026-02-13
**Depends on:** None (extends existing scheduling system)
**Repository:** [summarybotng/summarybot-ng](https://github.com/summarybotng/summarybot-ng)

---

## 1. Problem Statement

Currently, scheduled summaries can only be delivered to Discord channels or webhooks. This creates several limitations:

1. **No Preview Capability** — Users cannot review a scheduled summary before it's posted to a channel. Once generated, it's immediately public.

2. **No Summary Archive in Dashboard** — Generated summaries disappear into Discord's message history. The dashboard has no way to browse, search, or re-access past summaries.

3. **No Manual Push** — If a user generates an ad-hoc summary via the UI (or receives a scheduled one to the UI), there's no way to then push it to a Discord channel after review.

4. **Inflexible Scheduling** — Users must choose between "post to channel automatically" or "don't generate at all". There's no middle ground for "generate and hold for review".

These limitations are particularly problematic for:
- **Moderation teams** who want to review summaries before posting to public channels
- **Community managers** who want to curate which summaries get posted
- **Users exploring the tool** who want to see what summaries look like before enabling auto-posting

---

## 2. Decision

Add **UI-based delivery** as a first-class destination type alongside Discord channels and webhooks. Summaries delivered to the UI are stored in a database and accessible through the dashboard. Additionally, add a **"Push to Channel"** action that allows any stored summary to be posted to a Discord channel on demand.

### 2.1 New Destination Type: `DASHBOARD`

```python
class DestinationType(Enum):
    DISCORD_CHANNEL = "discord_channel"
    WEBHOOK = "webhook"
    EMAIL = "email"
    FILE = "file"
    DASHBOARD = "dashboard"  # NEW: Store in dashboard for viewing/manual push
```

A `DASHBOARD` destination stores the summary in the database, accessible via:
- The dashboard's "Summaries" tab (new)
- API endpoint for listing/retrieving stored summaries
- Push-to-channel action from the UI

### 2.2 Summary Storage Model

Summaries delivered to `DASHBOARD` are persisted in SQLite (or the configured database):

```python
@dataclass
class StoredSummary:
    """A summary stored in the dashboard for viewing and optional channel push."""
    id: str                          # UUID
    guild_id: str                    # Discord guild ID
    source_channel_ids: List[str]   # Channels that were summarized
    schedule_id: Optional[str]       # If from a scheduled task

    # Summary content
    summary_result: SummaryResult    # Full summary with references (ADR-004)

    # Delivery tracking
    created_at: datetime
    viewed_at: Optional[datetime]    # First view timestamp
    pushed_to_channels: List[str]    # Channel IDs where this was pushed
    pushed_at: Optional[datetime]    # Last push timestamp

    # Metadata
    title: str                       # User-friendly title (auto-generated or custom)
    is_pinned: bool = False          # Pin important summaries
    is_archived: bool = False        # Hide from default view
    tags: List[str] = []             # User-defined tags for organization
```

### 2.3 Push-to-Channel Action

From the dashboard, users can push any stored summary to one or more Discord channels:

```
┌─────────────────────────────────────────────────────────────┐
│  Summary: #general + #development (Feb 13, 2026)           │
│  ─────────────────────────────────────────────────────────  │
│  📋 Key Points                                              │
│  - Team decided to adopt TypeScript for new services [2]    │
│  - Deployment pipeline needs optimization [5][7]            │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Push to Channel                              [▼]   │    │
│  │  ┌─────────────────────────────────────────────┐    │    │
│  │  │ ☑ #announcements                            │    │    │
│  │  │ ☐ #general                                  │    │    │
│  │  │ ☐ #team-leads                               │    │    │
│  │  └─────────────────────────────────────────────┘    │    │
│  │  Format: [Embed ▼]   [ Push Summary ]               │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Data Model Changes

### 3.1 New: `StoredSummary` Table

```sql
CREATE TABLE stored_summaries (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    source_channel_ids TEXT NOT NULL,  -- JSON array
    schedule_id TEXT,

    -- Summary content (JSON blob)
    summary_json TEXT NOT NULL,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    viewed_at TIMESTAMP,
    pushed_at TIMESTAMP,

    -- Delivery tracking
    pushed_to_channels TEXT,  -- JSON array of {channel_id, pushed_at, message_id}

    -- Metadata
    title TEXT NOT NULL,
    is_pinned BOOLEAN DEFAULT FALSE,
    is_archived BOOLEAN DEFAULT FALSE,
    tags TEXT,  -- JSON array

    -- Indexes
    FOREIGN KEY (guild_id) REFERENCES guilds(id),
    FOREIGN KEY (schedule_id) REFERENCES scheduled_tasks(id)
);

CREATE INDEX idx_stored_summaries_guild ON stored_summaries(guild_id);
CREATE INDEX idx_stored_summaries_created ON stored_summaries(created_at DESC);
CREATE INDEX idx_stored_summaries_schedule ON stored_summaries(schedule_id);
```

### 3.2 Modified: `Destination` Model

Add `DASHBOARD` type and optional metadata:

```python
@dataclass
class Destination(BaseModel):
    type: DestinationType
    target: str  # For DASHBOARD: can be "default" or a custom view/folder name
    format: str = "embed"
    enabled: bool = True

    # NEW: Dashboard-specific options
    auto_archive_days: Optional[int] = None  # Auto-archive after N days
    notify_on_delivery: bool = False  # Send notification when summary is ready
```

### 3.3 Modified: `ScheduleCreateRequest` / `ScheduleUpdateRequest`

The existing `destinations` array already supports multiple destinations. No schema change needed — just document that `type: "dashboard"` is now valid.

---

## 4. API Changes

### 4.1 New Endpoints: Stored Summaries

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/guilds/{guild_id}/summaries` | GET | List stored summaries (paginated, filterable) |
| `/api/v1/guilds/{guild_id}/summaries/{summary_id}` | GET | Get full summary details |
| `/api/v1/guilds/{guild_id}/summaries/{summary_id}` | PATCH | Update metadata (title, tags, pin, archive) |
| `/api/v1/guilds/{guild_id}/summaries/{summary_id}` | DELETE | Delete stored summary |
| `/api/v1/guilds/{guild_id}/summaries/{summary_id}/push` | POST | Push summary to channel(s) |

### 4.2 List Summaries Request/Response

```python
# GET /api/v1/guilds/{guild_id}/summaries?page=1&limit=20&pinned=true&archived=false

class StoredSummaryListItem(BaseModel):
    id: str
    title: str
    source_channel_ids: List[str]
    schedule_id: Optional[str]
    created_at: datetime
    is_pinned: bool
    is_archived: bool
    tags: List[str]
    pushed_to_channels: List[str]
    # Preview fields
    key_points_count: int
    action_items_count: int
    message_count: int
    has_references: bool  # ADR-004: grounded summary

class StoredSummaryListResponse(BaseModel):
    items: List[StoredSummaryListItem]
    total: int
    page: int
    limit: int
```

### 4.3 Push to Channel Request/Response

```python
# POST /api/v1/guilds/{guild_id}/summaries/{summary_id}/push

class PushToChannelRequest(BaseModel):
    channel_ids: List[str]  # One or more channels to push to
    format: str = "embed"   # "embed", "markdown", "plain"
    include_references: bool = True  # ADR-004: include sources table
    custom_message: Optional[str] = None  # Optional intro text

class PushToChannelResponse(BaseModel):
    success: bool
    deliveries: List[DeliveryResult]

class DeliveryResult(BaseModel):
    channel_id: str
    success: bool
    message_id: Optional[str]  # Discord message ID if successful
    error: Optional[str]
```

---

## 5. Frontend Changes

### 5.1 New Tab: "Summaries"

Add a new tab to the dashboard navigation alongside Channels, Schedules, Settings:

```
┌──────────────────────────────────────────────────────────────┐
│  SummaryBot Dashboard                                        │
│  ────────────────────────────────────────────────────────── │
│  [Channels] [Schedules] [Summaries] [Settings]              │
│                           ^^^^^^^^                           │
└──────────────────────────────────────────────────────────────┘
```

### 5.2 Summaries List View

```
┌──────────────────────────────────────────────────────────────┐
│  Summaries                                    [+ New Summary] │
│  ─────────────────────────────────────────────────────────── │
│  Filter: [All ▼] [Pinned ☐] [Archived ☐]  Search: [______]  │
│  ─────────────────────────────────────────────────────────── │
│                                                              │
│  📌 #general + #dev — Feb 13, 14:30                         │
│     5 key points • 2 action items • 47 messages             │
│     Tags: weekly, team-sync                                  │
│     [View] [Push to Channel] [⋮]                            │
│  ─────────────────────────────────────────────────────────── │
│  #announcements — Feb 12, 09:00                              │
│     3 key points • 0 action items • 12 messages             │
│     Pushed to: #team-leads (Feb 12, 10:15)                  │
│     [View] [Push to Channel] [⋮]                            │
│  ─────────────────────────────────────────────────────────── │
│                                                              │
│  Page 1 of 5  [< Prev] [Next >]                             │
└──────────────────────────────────────────────────────────────┘
```

### 5.3 Summary Detail View

Full summary display with:
- All key points, action items, decisions (with ADR-004 citations)
- Participant breakdown
- Sources table (if grounded)
- Metadata editing (title, tags)
- Push to channel action
- Delivery history (where/when it was pushed)

### 5.4 Schedule Form Update

Add destination picker to schedule creation/editing:

```
┌──────────────────────────────────────────────────────────────┐
│  Create Schedule                                             │
│  ─────────────────────────────────────────────────────────── │
│  Name: [Weekly Team Sync Summary____________]                │
│                                                              │
│  Source Channels:                                            │
│  [#general ×] [#development ×] [+ Add Channel]              │
│                                                              │
│  Schedule: [Weekly ▼] at [09:00 ▼] on [Mon ☑] [Fri ☐]       │
│                                                              │
│  Delivery Destinations:                                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ ☑ Dashboard (view in Summaries tab)                    │ │
│  │ ☐ Discord Channel: [Select channel ▼]                  │ │
│  │ ☐ Webhook: [https://...________________]               │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  Summary Options:                                            │
│  Length: [Detailed ▼]  Perspective: [General ▼]            │
│                                                              │
│  [Cancel]                                    [Create Schedule]│
└──────────────────────────────────────────────────────────────┘
```

---

## 6. Execution Flow Changes

### 6.1 Delivery to Dashboard

When `TaskExecutor._deliver_summary()` encounters a `DASHBOARD` destination:

```python
async def _deliver_to_dashboard(
    self,
    summary: SummaryResult,
    task: ScheduledTask,
    destination: Destination
) -> DeliveryResult:
    """Store summary in database for dashboard viewing."""

    # Generate title from context
    channel_names = await self._get_channel_names(task.channel_ids)
    title = f"{', '.join(channel_names)} — {datetime.now().strftime('%b %d, %H:%M')}"

    # Create stored summary
    stored = StoredSummary(
        id=generate_id(),
        guild_id=task.guild_id,
        source_channel_ids=task.channel_ids,
        schedule_id=task.id,
        summary_result=summary,
        created_at=datetime.utcnow(),
        title=title,
    )

    # Persist to database
    await self.summary_repository.save(stored)

    # Optional: Send notification
    if destination.notify_on_delivery:
        await self._send_dashboard_notification(task, stored)

    return DeliveryResult(
        destination_type="dashboard",
        success=True,
        details={"summary_id": stored.id}
    )
```

### 6.2 Push to Channel from Dashboard

New service method for pushing stored summaries:

```python
class SummaryPushService:
    """Handles pushing stored summaries to Discord channels."""

    async def push_to_channels(
        self,
        summary_id: str,
        channel_ids: List[str],
        format: str = "embed",
        include_references: bool = True,
        custom_message: Optional[str] = None,
        user_id: str = None  # For audit trail
    ) -> List[DeliveryResult]:
        """Push a stored summary to one or more Discord channels."""

        # Load summary
        stored = await self.summary_repository.get(summary_id)
        if not stored:
            raise NotFoundError(f"Summary {summary_id} not found")

        # Verify user has permission for target channels
        for channel_id in channel_ids:
            await self._verify_channel_permission(user_id, channel_id)

        # Deliver to each channel
        results = []
        for channel_id in channel_ids:
            result = await self._deliver_to_discord(
                summary=stored.summary_result,
                channel_id=channel_id,
                format=format,
                include_references=include_references,
                custom_message=custom_message
            )
            results.append(result)

            # Track delivery
            if result.success:
                stored.pushed_to_channels.append(channel_id)
                stored.pushed_at = datetime.utcnow()

        # Update stored summary with delivery info
        await self.summary_repository.update(stored)

        return results
```

---

## 7. File-by-File Change Map

| # | File | Action | Risk | Description |
|---|------|--------|------|-------------|
| 1 | `src/models/task.py` | **M** | Low | Add `DASHBOARD` to `DestinationType` enum |
| 2 | `src/models/stored_summary.py` | **N** | Low | New `StoredSummary` model |
| 3 | `src/data/summary_repository.py` | **N** | Medium | Repository for stored summary CRUD |
| 4 | `src/data/sqlite.py` | **M** | Medium | Add `stored_summaries` table schema |
| 5 | `src/scheduling/executor.py` | **M** | Medium | Add `_deliver_to_dashboard()` method |
| 6 | `src/dashboard/routes/summaries.py` | **N** | Medium | New API routes for stored summaries |
| 7 | `src/dashboard/models.py` | **M** | Low | Add request/response models for summaries |
| 8 | `src/services/summary_push.py` | **N** | Medium | Push-to-channel service |
| 9 | `src/frontend/src/pages/Summaries.tsx` | **N** | Medium | New Summaries tab page |
| 10 | `src/frontend/src/components/summaries/SummaryCard.tsx` | **N** | Low | Summary list card component |
| 11 | `src/frontend/src/components/summaries/SummaryDetail.tsx` | **N** | Medium | Full summary view with push action |
| 12 | `src/frontend/src/components/summaries/PushToChannelModal.tsx` | **N** | Low | Channel selection modal for pushing |
| 13 | `src/frontend/src/components/schedules/ScheduleForm.tsx` | **M** | Medium | Add destination picker UI |
| 14 | `src/frontend/src/types/index.ts` | **M** | Low | Add StoredSummary types |
| 15 | `src/frontend/src/api/client.ts` | **M** | Low | Add summary API methods |
| 16 | `tests/unit/test_stored_summary.py` | **N** | — | Unit tests for stored summary model |
| 17 | `tests/unit/test_summary_push.py` | **N** | — | Unit tests for push service |
| 18 | `tests/integration/test_dashboard_delivery.py` | **N** | — | Integration tests for full flow |

**Totals:** 10 files modified, 9 files created.

---

## 8. Edge Cases and Mitigations

| Edge Case | Mitigation |
|-----------|------------|
| Summary storage grows unbounded | Auto-archive after configurable days; paginated API; archival/deletion UI |
| Push to channel user lacks permission | Verify channel permissions before push; return clear error |
| Push to deleted channel | Graceful failure with "channel not found" error; don't crash |
| Large summary exceeds Discord embed limits | Truncate with "...continued in thread" and create thread for full content |
| User deletes schedule but summaries remain | Summaries are independent; orphaned summaries remain accessible |
| Multiple users push same summary simultaneously | Idempotent push; track all deliveries; show "already pushed to #X" |
| Summary references (ADR-004) in push | Format sources table for Discord; may need simplified format for embeds |

---

## 9. Security Considerations

1. **Channel Permission Verification**: Before pushing to any channel, verify the requesting user has `SEND_MESSAGES` permission in that channel via Discord API.

2. **Guild Isolation**: Summaries are scoped to guilds. Users can only view/push summaries for guilds they belong to.

3. **Rate Limiting**: Push-to-channel should be rate-limited to prevent spam (e.g., 10 pushes per minute per user).

4. **Audit Trail**: Track who pushed what summary where and when for accountability.

---

## 10. Implementation Phases

### Phase 1 — Core Storage (2-3 days)
- [ ] Add `DASHBOARD` to `DestinationType`
- [ ] Create `StoredSummary` model and database table
- [ ] Create `SummaryRepository` with CRUD operations
- [ ] Update `TaskExecutor` to deliver to dashboard

### Phase 2 — API Endpoints (1-2 days)
- [ ] Add `/summaries` list endpoint with pagination/filtering
- [ ] Add `/summaries/{id}` detail endpoint
- [ ] Add `/summaries/{id}/push` endpoint
- [ ] Add request/response models

### Phase 3 — Push Service (1-2 days)
- [ ] Create `SummaryPushService`
- [ ] Implement channel permission verification
- [ ] Handle Discord embed formatting with ADR-004 references
- [ ] Track delivery history

### Phase 4 — Frontend: Summaries Tab (2-3 days)
- [ ] Create Summaries page with list view
- [ ] Create SummaryCard component
- [ ] Create SummaryDetail view with full content
- [ ] Create PushToChannelModal

### Phase 5 — Frontend: Schedule Form (1 day)
- [ ] Add destination picker to ScheduleForm
- [ ] Support multiple destination selection
- [ ] Show dashboard as default/recommended option

### Phase 6 — Testing & Polish (1-2 days)
- [ ] Unit tests for models and services
- [ ] Integration tests for full flow
- [ ] E2E test for UI workflow
- [ ] Documentation updates

---

## 11. Future Extensions

| Extension | Description |
|-----------|-------------|
| **Email Delivery** | Implement `EMAIL` destination type to send summaries via email |
| **Scheduled Push** | Schedule a summary to be pushed at a specific time (review window) |
| **Summary Diff** | Compare two summaries from the same channels over different periods |
| **Export Options** | Export stored summaries as PDF, Markdown, or JSON |
| **Summary Sharing** | Generate shareable links for summaries (with optional auth) |
| **Notification Preferences** | Per-user notification settings for when summaries are ready |
| **Folders/Collections** | Organize summaries into user-defined folders |

---

## 12. Consequences

### Positive
- **Review before publish**: Users can verify summary quality before posting
- **Summary archive**: Historical summaries accessible anytime from dashboard
- **Flexible workflow**: Generate once, deliver anywhere, anytime
- **Better onboarding**: New users can explore summaries without affecting channels

### Negative
- **Storage growth**: Stored summaries consume database space
- **UI complexity**: New tab and workflows to learn
- **Permission complexity**: Must verify channel permissions at push time

### Trade-offs
- **Storage vs. Simplicity**: We chose to store full summary content (including ADR-004 references) for rich viewing, at the cost of larger storage
- **Push-on-demand vs. Scheduled Push**: We chose immediate push for simplicity; scheduled push can be added later

---

## 13. References

- [ADR-004: Grounded Summary References](./004-grounded-summary-references.md) — Citation format in summaries
- [Discord Embed Limits](https://discord.com/developers/docs/resources/message#embed-object) — Max 6000 chars total
- [Existing Scheduling Architecture](../scheduling_module_implementation.md) — Current scheduling implementation
