# ADR-059: Wiki External Sync (Google Drive)

## Status
Proposed (Depends on ADR-056/057, ADR-058)

## Context

The Compounding Wiki (ADR-056/057) lives in the summarybot-ng database. However, organizations often need:

1. **External editing** - Edit wiki content in familiar tools (Google Docs)
2. **Sharing** - Share knowledge with stakeholders who don't use the dashboard
3. **Backup** - External backup of knowledge base
4. **Offline access** - View wiki content without dashboard access

This ADR proposes bidirectional sync with Google Drive.

## Decision

Implement optional Google Drive sync with:

1. **Wiki → Drive** - Push wiki pages to Drive as markdown/docs
2. **Drive → Wiki** - Pull human edits back to wiki
3. **Conflict resolution** - Human edits take precedence

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     BIDIRECTIONAL SYNC ARCHITECTURE                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   summarybot-ng                              Google Drive                │
│   ─────────────                              ────────────                │
│                                                                          │
│   wiki/                          ◀────────▶  📁 SummaryBot Wiki/        │
│   ├── topics/                                ├── 📁 Topics/              │
│   │   ├── auth.md                            │   ├── 📄 Authentication   │
│   │   └── caching.md                         │   └── 📄 Caching          │
│   ├── decisions/                             ├── 📁 Decisions/           │
│   │   └── 2024-01-redis.md                   │   └── 📄 2024-01 Redis   │
│   └── processes/                             └── 📁 Processes/           │
│       └── deploy.md                              └── 📄 Deployment       │
│                                                                          │
│   ┌─────────────────┐            ┌─────────────────┐                    │
│   │  Sync Engine    │◀──────────▶│  Drive API      │                    │
│   │  (push/pull)    │            │  + Webhooks     │                    │
│   └─────────────────┘            └─────────────────┘                    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Sync Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SYNC FLOW                                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   WIKI → DRIVE (Automatic)                                               │
│   ────────────────────────                                               │
│                                                                          │
│   Summary Generated                                                      │
│         │                                                                │
│         ▼                                                                │
│   Wiki Ingest Agent                                                      │
│         │                                                                │
│         ▼                                                                │
│   Pages Updated                                                          │
│         │                                                                │
│         ▼                                                                │
│   Sync Queue ──────────────▶ Drive API ──────────────▶ Files Updated    │
│                                                                          │
│   ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│   DRIVE → WIKI (Webhook-triggered)                                       │
│   ────────────────────────────────                                       │
│                                                                          │
│   Human edits file in Drive                                              │
│         │                                                                │
│         ▼                                                                │
│   Drive Webhook fires                                                    │
│         │                                                                │
│         ▼                                                                │
│   Sync Engine pulls content                                              │
│         │                                                                │
│         ▼                                                                │
│   Conflict check                                                         │
│         │                                                                │
│   ┌─────┴─────┐                                                         │
│   │           │                                                         │
│   ▼           ▼                                                         │
│   No conflict  Conflict                                                  │
│   │           │                                                         │
│   ▼           ▼                                                         │
│   Update wiki  Flag for review                                          │
│               (ADR-060 curation)                                        │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Drive Folder Structure

```
📁 SummaryBot Wiki (Company Name)/
├── 📁 Topics/
│   ├── 📄 Authentication.md
│   ├── 📄 Caching.md
│   ├── 📄 Rate Limiting.md
│   └── 📄 Deployment.md
├── 📁 Decisions/
│   ├── 📄 2024-01 Use Redis for Caching.md
│   └── 📄 2024-01 JWT Token Strategy.md
├── 📁 Processes/
│   ├── 📄 Deploy to Production.md
│   └── 📄 Handle Incident.md
├── 📁 Experts/
│   └── 📄 Expertise Map.md
├── 📁 Questions/
│   └── 📄 Unanswered Questions.md
├── 📄 _Index.md
├── 📄 _Recent Changes.md
└── 📄 _README.md              ← Explains this is auto-synced
```

### File Naming

| Wiki Path | Drive Name |
|-----------|------------|
| `topics/authentication.md` | `Topics/Authentication.md` |
| `decisions/2024-01-redis.md` | `Decisions/2024-01 Use Redis for Caching.md` |
| `processes/deploy.md` | `Processes/Deploy to Production.md` |

---

## Implementation

### Sync Engine

```python
# src/wiki/drive_sync.py

class WikiDriveSync:
    """
    Bidirectional sync between wiki and Google Drive.
    """

    def __init__(self, guild_id: str, credentials: Credentials):
        self.guild_id = guild_id
        self.drive = build('drive', 'v3', credentials=credentials)

    # ─────────────────────────────────────────────────────────────
    # SETUP
    # ─────────────────────────────────────────────────────────────

    async def setup_wiki_folder(self) -> str:
        """Create wiki folder structure in Drive."""
        # Create main folder
        folder = await self._create_folder('SummaryBot Wiki')

        # Create subfolders
        for category in ['Topics', 'Decisions', 'Processes', 'Experts', 'Questions']:
            await self._create_folder(category, parent=folder['id'])

        # Create README
        await self._create_readme(folder['id'])

        # Store folder ID
        await self._store_config(folder['id'])

        return folder['id']

    async def setup_webhook(self) -> None:
        """Set up Drive change notifications."""
        channel = self.drive.files().watch(
            fileId=self.wiki_folder_id,
            body={
                'id': f'wiki-sync-{self.guild_id}',
                'type': 'web_hook',
                'address': f'{settings.BASE_URL}/api/webhooks/drive/{self.guild_id}',
                'expiration': int((datetime.now() + timedelta(days=7)).timestamp() * 1000)
            }
        ).execute()

        await self._store_channel(channel)

    # ─────────────────────────────────────────────────────────────
    # WIKI → DRIVE
    # ─────────────────────────────────────────────────────────────

    async def push_page(self, page: WikiPage) -> str:
        """Push a wiki page to Drive."""
        folder_id = await self._get_folder_for_category(page.category)
        drive_name = self._to_drive_name(page)
        content = self._prepare_content(page)

        existing = await self._find_file(page.path)

        if existing:
            # Update existing
            await self._update_file(existing['id'], content)
            return existing['id']
        else:
            # Create new
            file = await self._create_file(
                name=drive_name,
                content=content,
                parent=folder_id,
                properties={'wiki_path': page.path}
            )
            return file['id']

    async def push_all(self) -> SyncResult:
        """Push all wiki pages to Drive."""
        pages = await wiki_repo.list_all_pages(self.guild_id)
        results = []

        for page in pages:
            file_id = await self.push_page(page)
            results.append({'path': page.path, 'file_id': file_id})

        return SyncResult(synced=len(results), errors=[])

    # ─────────────────────────────────────────────────────────────
    # DRIVE → WIKI
    # ─────────────────────────────────────────────────────────────

    async def pull_changes(self, file_id: str) -> PullResult:
        """Pull a changed file from Drive back to wiki."""
        # Get file metadata and content
        file = await self._get_file(file_id)
        content = await self._get_file_content(file_id)

        wiki_path = file['properties'].get('wiki_path')
        if not wiki_path:
            return PullResult(status='skipped', reason='Not a wiki file')

        # Get current wiki version
        wiki_page = await wiki_repo.get_page(self.guild_id, wiki_path)

        # Check for conflict
        drive_modified = parse_datetime(file['modifiedTime'])
        wiki_modified = wiki_page.updated_at if wiki_page else None

        if wiki_page and drive_modified <= wiki_modified:
            return PullResult(status='skipped', reason='Wiki is newer')

        # Parse content
        parsed = self._parse_drive_content(content)

        if wiki_page:
            # Check for conflict
            if self._has_conflict(wiki_page.content, parsed.content):
                # Flag for curation (ADR-060)
                await curation_queue.add(
                    type='drive_conflict',
                    wiki_path=wiki_path,
                    wiki_content=wiki_page.content,
                    drive_content=parsed.content,
                    drive_modified_by=file.get('lastModifyingUser', {}).get('emailAddress')
                )
                return PullResult(status='conflict', reason='Flagged for review')

        # Update wiki
        await wiki_repo.update_page(
            path=wiki_path,
            content=parsed.content,
            source='google_drive',
            modified_by=file.get('lastModifyingUser', {}).get('emailAddress')
        )

        # Log
        await wiki_log.append(
            operation='drive_pull',
            details={
                'wiki_path': wiki_path,
                'file_id': file_id,
                'modified_by': file.get('lastModifyingUser', {}).get('emailAddress')
            }
        )

        return PullResult(status='updated', wiki_path=wiki_path)

    # ─────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────

    def _prepare_content(self, page: WikiPage) -> str:
        """Add metadata header to content for Drive."""
        header = f"""<!--
╔══════════════════════════════════════════════════════════════╗
║  SummaryBot Wiki - Auto-synced                               ║
║                                                              ║
║  Path: {page.path:<52} ║
║  Last Updated: {page.updated_at.isoformat():<43} ║
║  Sources: {len(page.source_refs):<48} ║
║                                                              ║
║  ⚠️  Edits here will sync back to the wiki.                 ║
║  Human edits take precedence over AI updates.               ║
╚══════════════════════════════════════════════════════════════╝
-->

"""
        return header + page.content

    def _has_conflict(self, wiki_content: str, drive_content: str) -> bool:
        """
        Detect if changes conflict or are compatible.
        Compatible: additive changes (both added different sections)
        Conflict: same section modified differently
        """
        wiki_sections = self._extract_sections(wiki_content)
        drive_sections = self._extract_sections(drive_content)

        for section_id in set(wiki_sections.keys()) & set(drive_sections.keys()):
            if wiki_sections[section_id] != drive_sections[section_id]:
                return True

        return False
```

### Webhook Handler

```python
# src/dashboard/routes/webhooks.py

@router.post("/drive/{guild_id}")
async def drive_webhook(
    guild_id: str,
    x_goog_channel_id: str = Header(...),
    x_goog_resource_state: str = Header(...),
    x_goog_changed: str = Header(default='')
):
    """Handle Google Drive change notifications."""

    if x_goog_resource_state == 'sync':
        # Initial confirmation
        return {"status": "ok"}

    if x_goog_resource_state in ('change', 'update'):
        sync = WikiDriveSync(guild_id)

        # Get changed files
        changes = await sync.get_changes_since_last_sync()

        results = []
        for change in changes:
            if change['file'].get('properties', {}).get('wiki_path'):
                result = await sync.pull_changes(change['file']['id'])
                results.append(result)

        return {"status": "processed", "changes": len(results)}

    return {"status": "ignored"}
```

---

## Settings UI

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Settings > Wiki > External Sync                                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  📁 Google Drive Sync                                                    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Status: ✅ Connected                                            │   │
│  │                                                                   │   │
│  │  Folder: My Drive / SummaryBot Wiki                             │   │
│  │  Last sync: 5 minutes ago (32 files)                            │   │
│  │                                                                   │   │
│  │  [📂 Open in Drive]  [🔄 Sync Now]  [⚙️ Configure]  [❌ Disconnect] │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│  Sync Settings                                                           │
│                                                                          │
│  Sync Direction                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  ○ Wiki → Drive only                                            │   │
│  │    Push wiki changes to Drive. Drive edits are ignored.        │   │
│  │                                                                   │   │
│  │  ○ Drive → Wiki only                                            │   │
│  │    Pull Drive edits to wiki. Wiki changes aren't pushed.       │   │
│  │                                                                   │   │
│  │  ● Bidirectional (Recommended)                                  │   │
│  │    Changes sync both ways. Human edits take precedence.         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  Conflict Handling                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  ● Flag for review                                              │   │
│  │    Conflicts go to curation queue for human decision.          │   │
│  │                                                                   │   │
│  │  ○ Drive always wins                                            │   │
│  │    Human edits automatically override AI content.              │   │
│  │                                                                   │   │
│  │  ○ Attempt merge                                                │   │
│  │    Try to merge changes. Flag only if incompatible.            │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│  Sharing Defaults                                                        │
│                                                                          │
│  Default access: [Workspace members ▾] [Can edit ▾]                     │
│                                                                          │
│  ☑ Create shareable links for new pages                                │
│  ☐ Allow sharing outside workspace                                      │
│  ☑ Notify #wiki-updates channel on changes                             │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Database Schema

```sql
-- Drive sync configuration
CREATE TABLE wiki_drive_sync (
    guild_id TEXT PRIMARY KEY,
    drive_folder_id TEXT NOT NULL,
    credentials_encrypted TEXT NOT NULL,
    sync_direction TEXT DEFAULT 'bidirectional',
    conflict_resolution TEXT DEFAULT 'flag_for_review',
    last_sync TEXT,
    last_sync_token TEXT,  -- Drive changes token
    webhook_channel_id TEXT,
    webhook_expiry TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- File mapping (wiki path ↔ Drive file)
CREATE TABLE wiki_drive_files (
    wiki_path TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    drive_file_id TEXT NOT NULL,
    drive_name TEXT NOT NULL,
    drive_modified TEXT,
    wiki_modified TEXT,
    sync_status TEXT DEFAULT 'synced',
    last_synced TEXT,
    PRIMARY KEY (wiki_path, guild_id),
    FOREIGN KEY (guild_id) REFERENCES wiki_drive_sync(guild_id) ON DELETE CASCADE
);

-- Sync history (for debugging)
CREATE TABLE wiki_drive_sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    direction TEXT NOT NULL,  -- push, pull
    wiki_path TEXT,
    drive_file_id TEXT,
    action TEXT NOT NULL,  -- create, update, delete, conflict, skip
    details TEXT,  -- JSON
    modified_by TEXT,
    timestamp TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_drive_files_guild ON wiki_drive_files(guild_id);
CREATE INDEX idx_drive_sync_log_timestamp ON wiki_drive_sync_log(timestamp);
```

---

## Future: Other Sync Targets

The sync architecture is designed to support additional targets:

| Target | Status | Notes |
|--------|--------|-------|
| Google Drive | Proposed | This ADR |
| Notion | Future | Export as Notion pages |
| Confluence | Future | Enterprise wiki sync |
| GitHub | Future | Sync to repo wiki |
| Obsidian | Future | Local vault sync |

---

## Implementation Phases

### Phase 1: Setup (2 weeks)
- [ ] OAuth flow for Drive access
- [ ] Folder structure creation
- [ ] Settings UI

### Phase 2: Push (2 weeks)
- [ ] Wiki → Drive sync
- [ ] File mapping table
- [ ] Incremental sync

### Phase 3: Pull (2 weeks)
- [ ] Webhook setup
- [ ] Drive → Wiki sync
- [ ] Conflict detection

### Phase 4: Polish (1 week)
- [ ] Sync status UI
- [ ] Error handling
- [ ] Retry logic

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Sync adoption | >30% of guilds | Settings enabled |
| Sync latency | <5 minutes | Time to propagate |
| External edits | >10% of changes | Sync log analysis |
| Conflict rate | <5% | Conflicts / total syncs |

## Consequences

### Positive
- Edit wiki in familiar tools (Google Docs)
- Share knowledge outside dashboard
- External backup
- Collaboration with non-dashboard users

### Negative
- Google Drive dependency
- OAuth complexity
- Potential sync conflicts
- Webhook reliability concerns

### Mitigations
- Sync is optional
- Clear conflict resolution UI
- Polling fallback if webhooks fail
- Comprehensive sync logging

## References

- [ADR-056: Compounding Wiki - Standard](./ADR-056-compounding-wiki-standard.md)
- [ADR-058: Wiki Rendering](./ADR-058-wiki-rendering.md)
- [ADR-060: Wiki Curation Model](./ADR-060-wiki-curation-model.md)
- [ADR-049: Google Workspace SSO](./ADR-049-google-workspace-sso.md)
- [Google Drive API](https://developers.google.com/drive/api)
