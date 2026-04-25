# ADR-058: Wiki Rendering & Google Drive Sync

## Status
Proposed (Depends on ADR-056/057)

## Context

ADR-056/057 define the Compounding Wiki data model and agent workflows. This ADR addresses:

1. **How users interact with the wiki** - Dashboard UI, search, navigation
2. **External sync** - Google Drive integration for editing, sharing, and backup

The wiki becomes more valuable when it's:
- Accessible in the dashboard (browse, search, query)
- Editable via familiar tools (Google Docs)
- Shareable with stakeholders who don't use the dashboard
- Backed up externally

## Decision

Implement a hybrid rendering approach with bidirectional Google Drive sync:

1. **Dashboard** - Primary read interface with AI-powered search
2. **Google Drive** - External editing, sharing, and backup
3. **Bidirectional sync** - Changes flow both directions

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    WIKI RENDERING & SYNC ARCHITECTURE                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                     USER INTERFACES                              │   │
│   │                                                                   │   │
│   │   Dashboard              Google Drive           Slack/Discord    │   │
│   │   ┌─────────┐            ┌─────────┐            ┌─────────┐     │   │
│   │   │ Wiki UI │            │  Docs   │            │ /wiki   │     │   │
│   │   │ Browse  │            │ Editor  │            │ command │     │   │
│   │   │ Search  │            │ Share   │            │         │     │   │
│   │   └────┬────┘            └────┬────┘            └────┬────┘     │   │
│   │        │                      │                      │          │   │
│   └────────┼──────────────────────┼──────────────────────┼──────────┘   │
│            │                      │                      │               │
│            ▼                      ▼                      ▼               │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                     SYNC LAYER                                   │   │
│   │                                                                   │   │
│   │   ┌─────────────────┐    ┌─────────────────┐                    │   │
│   │   │  Wiki Renderer  │    │  Drive Sync     │                    │   │
│   │   │  (Markdown→UI)  │    │  (Bidirectional)│                    │   │
│   │   └────────┬────────┘    └────────┬────────┘                    │   │
│   │            │                      │                              │   │
│   │            └──────────┬───────────┘                              │   │
│   │                       │                                          │   │
│   └───────────────────────┼──────────────────────────────────────────┘   │
│                           │                                              │
│                           ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                     WIKI DATA (ADR-056/057)                      │   │
│   │                                                                   │   │
│   │   wiki_pages │ wiki_sources │ wiki_log │ wiki_links             │   │
│   │                                                                   │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Part 1: Dashboard Rendering

### Navigation Structure

```
Dashboard
├── Summaries
├── Schedules
├── Archive
├── 📚 Wiki                    ◀── New tab
│   ├── Browse                 (tree view)
│   ├── Search                 (AI-powered)
│   ├── Recent Changes         (activity feed)
│   └── Questions              (knowledge gaps)
├── Jobs
└── Settings
```

### Wiki Tab Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│  📚 Wiki                                         [🔍 Search...] [Sync] │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐  ┌────────────────────────────────────────────────┐  │
│  │ Navigation   │  │                                                │  │
│  │              │  │  # Authentication                              │  │
│  │ 📁 Topics    │  │                                                │  │
│  │  ├ auth      │  │  Our system uses JWT tokens with OAuth 2.0    │  │
│  │  ├ caching   │  │  for third-party integrations.                │  │
│  │  ├ deploy    │  │                                                │  │
│  │  └ api       │  │  ## Token Lifecycle                           │  │
│  │              │  │                                                │  │
│  │ 📁 Decisions │  │  - Access tokens: 15 minute expiry            │  │
│  │  ├ 2024-01   │  │  - Refresh tokens: 7 day expiry               │  │
│  │  └ 2024-02   │  │                                                │  │
│  │              │  │  > 📄 Source: [backend-standup-jan-15]        │  │
│  │ 📁 Processes │  │                                                │  │
│  │  ├ deploy    │  │  ## Related                                   │  │
│  │  └ incident  │  │  - [OAuth Implementation](oauth.md)           │  │
│  │              │  │  - [Session Management](sessions.md)          │  │
│  │ 👥 Experts   │  │                                                │  │
│  │              │  │  ────────────────────────────────────────────  │  │
│  │ ❓ Questions │  │                                                │  │
│  │              │  │  📊 12 sources │ Updated 2d ago │ 8 links     │  │
│  │ 📋 Recent    │  │  👤 Experts: @alice, @bob                     │  │
│  │              │  │  📂 Open in Google Drive                      │  │
│  └──────────────┘  └────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Search Interface

```
┌─────────────────────────────────────────────────────────────────────────┐
│  🔍 Search Wiki                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  How do we handle rate limiting?                             [⏎] │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  💡 Answer                                                       │   │
│  │                                                                   │   │
│  │  Rate limiting is set to 100 requests/minute per client IP.     │   │
│  │  Exceeded requests receive HTTP 429 with Retry-After header.    │   │
│  │  Redis is used for distributed rate tracking.                   │   │
│  │                                                                   │   │
│  │  Sources: [rate-limiting.md] [decisions/2024-01-redis.md]       │   │
│  │                                                                   │   │
│  │  [📝 Save this answer to wiki]                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  📄 Related Pages                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  rate-limiting.md                              Updated 5d ago    │   │
│  │  API rate limiting configuration and strategies...              │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  decisions/2024-01-redis-caching.md            Updated 12d ago   │   │
│  │  Decision to use Redis for caching and rate limiting...        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Summary Integration

Each summary shows wiki updates it triggered:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Summary: Backend Standup - Jan 15, 2024                    [Regenerate]│
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ## Summary                                                              │
│  Team discussed caching strategy and decided on Redis...                │
│                                                                          │
│  ## Key Points                                                           │
│  • Decided to use Redis for caching (replacing Memcached)               │
│  • Rate limiting set to 100 req/min                                     │
│  • @alice will handle OAuth implementation                              │
│                                                                          │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│  📚 Wiki Updates                                        [View all →]    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  This summary updated 8 wiki pages:                              │   │
│  │                                                                   │   │
│  │  📝 Modified:                                                    │   │
│  │  • [topics/caching.md] - Added Redis decision                   │   │
│  │  • [topics/rate-limiting.md] - Updated to 100 req/min           │   │
│  │  • [experts/expertise-map.md] - @alice → OAuth                  │   │
│  │                                                                   │   │
│  │  ✨ Created:                                                     │   │
│  │  • [decisions/2024-01-redis-caching.md]                         │   │
│  │                                                                   │   │
│  │  ⚠️ Contradictions flagged: 1                                   │   │
│  │  • [caching.md] previously mentioned Memcached                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Cmd+K Quick Search

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│     ┌───────────────────────────────────────────────────────────────┐   │
│     │  🔍  authentication                                            │   │
│     ├───────────────────────────────────────────────────────────────┤   │
│     │                                                                │   │
│     │  📚 Wiki Pages                                                 │   │
│     │  ├─ topics/authentication.md                                  │   │
│     │  ├─ topics/oauth.md                                           │   │
│     │  └─ decisions/2024-01-jwt-tokens.md                          │   │
│     │                                                                │   │
│     │  📄 Summaries                                                  │   │
│     │  ├─ Backend Standup - Jan 15 (mentions auth)                 │   │
│     │  └─ Security Review - Jan 22                                  │   │
│     │                                                                │   │
│     │  👤 Experts                                                    │   │
│     │  └─ @alice (92% confidence)                                   │   │
│     │                                                                │   │
│     └───────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Part 2: Google Drive Sync

### Sync Model

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     BIDIRECTIONAL SYNC MODEL                             │
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
│   Sync Direction:                                                        │
│   ───────────────                                                        │
│   • Wiki → Drive: On ingest, lint, page update                          │
│   • Drive → Wiki: On Drive file change (webhook)                        │
│   • Conflict: Drive wins (human edits take precedence)                  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Drive Folder Structure

```
📁 SummaryBot Wiki (guild-name)/
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
├── 📄 Index.md
└── 📄 Recent Changes.md
```

### Sync Implementation

```python
# src/wiki/drive_sync.py

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

class WikiDriveSync:
    """
    Bidirectional sync between wiki and Google Drive.
    """

    def __init__(self, guild_id: str, credentials: Credentials):
        self.guild_id = guild_id
        self.drive = build('drive', 'v3', credentials=credentials)
        self.docs = build('docs', 'v1', credentials=credentials)

    async def setup_wiki_folder(self) -> str:
        """
        Create or get the wiki folder in Drive.
        Returns folder ID.
        """
        # Check if folder exists
        results = self.drive.files().list(
            q=f"name='SummaryBot Wiki' and mimeType='application/vnd.google-apps.folder'",
            spaces='drive'
        ).execute()

        if results.get('files'):
            return results['files'][0]['id']

        # Create folder
        folder = self.drive.files().create(
            body={
                'name': 'SummaryBot Wiki',
                'mimeType': 'application/vnd.google-apps.folder'
            }
        ).execute()

        # Create subfolders
        for subfolder in ['Topics', 'Decisions', 'Processes', 'Experts', 'Questions']:
            self.drive.files().create(
                body={
                    'name': subfolder,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [folder['id']]
                }
            ).execute()

        return folder['id']

    async def sync_page_to_drive(self, page: WikiPage) -> str:
        """
        Upload/update a wiki page to Google Drive.
        Returns the Drive file ID.
        """
        folder_id = self.get_folder_for_category(page.category)

        # Check if file exists
        existing = await self.find_drive_file(page.path)

        content = self._add_drive_metadata(page)

        if existing:
            # Update existing file
            self.drive.files().update(
                fileId=existing['id'],
                media_body=MediaIoBaseUpload(
                    io.BytesIO(content.encode()),
                    mimetype='text/markdown'
                )
            ).execute()
            return existing['id']
        else:
            # Create new file
            file = self.drive.files().create(
                body={
                    'name': f"{page.title}.md",
                    'parents': [folder_id],
                    'properties': {
                        'wiki_path': page.path,
                        'wiki_guild': self.guild_id
                    }
                },
                media_body=MediaIoBaseUpload(
                    io.BytesIO(content.encode()),
                    mimetype='text/markdown'
                )
            ).execute()
            return file['id']

    async def sync_from_drive(self, file_id: str) -> WikiPage:
        """
        Pull changes from Drive back to wiki.
        """
        # Get file content
        content = self.drive.files().get_media(fileId=file_id).execute()

        # Get file metadata
        file = self.drive.files().get(
            fileId=file_id,
            fields='properties,modifiedTime'
        ).execute()

        wiki_path = file['properties']['wiki_path']

        # Parse content and update wiki
        page_content = self._strip_drive_metadata(content.decode())

        return await wiki_repo.update_page(
            path=wiki_path,
            content=page_content,
            source='google_drive',
            modified_at=file['modifiedTime']
        )

    def _add_drive_metadata(self, page: WikiPage) -> str:
        """
        Add metadata header for Drive files.
        """
        header = f"""<!--
SummaryBot Wiki Page
Path: {page.path}
Last Updated: {page.updated_at}
Sources: {len(page.source_refs)}
DO NOT EDIT THIS HEADER
-->

"""
        return header + page.content

    async def setup_webhook(self) -> None:
        """
        Set up Drive webhook for change notifications.
        """
        channel = self.drive.files().watch(
            fileId=self.wiki_folder_id,
            body={
                'id': f'wiki-sync-{self.guild_id}',
                'type': 'web_hook',
                'address': f'{settings.BASE_URL}/api/webhooks/drive/{self.guild_id}'
            }
        ).execute()

        # Store channel info for renewal
        await self.store_channel(channel)
```

### Webhook Handler

```python
# src/dashboard/routes/webhooks.py

@router.post("/drive/{guild_id}")
async def drive_webhook(
    guild_id: str,
    x_goog_channel_id: str = Header(...),
    x_goog_resource_state: str = Header(...)
):
    """
    Handle Google Drive change notifications.
    """
    if x_goog_resource_state == 'sync':
        # Initial sync confirmation
        return {"status": "ok"}

    if x_goog_resource_state in ('change', 'update'):
        # File was modified in Drive
        sync = WikiDriveSync(guild_id)

        # Get changed files
        changes = await sync.get_recent_changes()

        for change in changes:
            if change['file']['properties'].get('wiki_path'):
                # This is a wiki file, sync it back
                await sync.sync_from_drive(change['file']['id'])

                # Log the sync
                await wiki_log.append(
                    operation='drive_sync',
                    details={
                        'file_id': change['file']['id'],
                        'wiki_path': change['file']['properties']['wiki_path'],
                        'modified_by': change.get('lastModifyingUser', {}).get('emailAddress')
                    }
                )

    return {"status": "processed"}
```

### Conflict Resolution

```python
class ConflictResolver:
    """
    Handles conflicts between wiki and Drive versions.
    """

    async def resolve(
        self,
        wiki_page: WikiPage,
        drive_content: str,
        drive_modified: datetime
    ) -> ResolutionResult:
        # Rule: Human edits (Drive) take precedence over LLM updates

        if drive_modified > wiki_page.updated_at:
            # Drive is newer - use Drive version
            return ResolutionResult(
                winner='drive',
                action='update_wiki',
                content=drive_content
            )

        # Check if changes are compatible
        if self._changes_are_additive(wiki_page.content, drive_content):
            # Merge: Drive additions + Wiki additions
            merged = await self._merge_content(wiki_page.content, drive_content)
            return ResolutionResult(
                winner='merge',
                action='update_both',
                content=merged
            )

        # True conflict - flag for human review
        return ResolutionResult(
            winner='conflict',
            action='flag_for_review',
            wiki_content=wiki_page.content,
            drive_content=drive_content
        )
```

---

## Part 3: Slack/Discord Commands

### Wiki Bot Commands

```
/wiki search <query>      - Search the wiki
/wiki page <path>         - Show a wiki page
/wiki ask <question>      - Ask a question (AI answers from wiki)
/wiki recent              - Show recent changes
/wiki expert <topic>      - Who knows about this topic?
```

### Command Implementation

```python
# src/bot/commands/wiki.py

@bot.slash_command(name="wiki", description="Search and query the knowledge wiki")
async def wiki_command(
    ctx,
    action: str = Option(choices=["search", "page", "ask", "recent", "expert"]),
    query: str = Option(default=None)
):
    if action == "search":
        results = await wiki_search.search(ctx.guild_id, query, limit=5)
        embed = discord.Embed(title=f"Wiki: {query}", color=0x5865F2)
        for page in results:
            embed.add_field(
                name=page.title,
                value=f"{page.snippet[:100]}...\n[View]({dashboard_url}/wiki/{page.path})",
                inline=False
            )
        await ctx.respond(embed=embed)

    elif action == "ask":
        # AI-powered answer
        answer = await wiki_query_agent.query(query, ctx.guild_id)
        embed = discord.Embed(title=query, description=answer.text, color=0x00D166)
        embed.add_field(
            name="Sources",
            value="\n".join([f"• [{c.title}]({dashboard_url}/wiki/{c.path})" for c in answer.citations])
        )
        await ctx.respond(embed=embed)

    elif action == "expert":
        experts = await expertise_mapper.get_experts(query, ctx.guild_id)
        embed = discord.Embed(title=f"Experts: {query}", color=0xFEE75C)
        for e in experts:
            embed.add_field(
                name=f"<@{e.user_id}>",
                value=f"{e.confidence:.0%} confidence ({e.contribution_count} contributions)",
                inline=True
            )
        await ctx.respond(embed=embed)
```

---

## Settings UI

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Settings > Wiki                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  📚 Wiki Settings                                                        │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Auto-Ingest Summaries                                    [ON]  │   │
│  │  Automatically update wiki when summaries are generated         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  AI Search                                                [ON]  │   │
│  │  Synthesize answers from wiki content                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│  📁 Google Drive Sync                                                    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Status: ✅ Connected                                            │   │
│  │  Folder: My Drive / SummaryBot Wiki                             │   │
│  │  Last sync: 5 minutes ago                                       │   │
│  │                                                                   │   │
│  │  [Open in Drive]  [Force Sync]  [Disconnect]                    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  Sync Settings                                                           │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Sync Direction                                                  │   │
│  │  ○ Wiki → Drive only (backup)                                   │   │
│  │  ○ Drive → Wiki only (external editing)                         │   │
│  │  ● Bidirectional (recommended)                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Conflict Resolution                                             │   │
│  │  ○ Always use Drive version                                     │   │
│  │  ● Attempt merge, flag conflicts                                │   │
│  │  ○ Always use Wiki version                                      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  Sharing                                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Default sharing: [Workspace members - Editor ▾]                │   │
│  │                                                                   │   │
│  │  ☑ Notify when wiki pages are created                           │   │
│  │  ☐ Allow external sharing (outside workspace)                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Database Schema (Additions)

```sql
-- Drive sync state
CREATE TABLE wiki_drive_sync (
    guild_id TEXT PRIMARY KEY,
    drive_folder_id TEXT NOT NULL,
    credentials_encrypted TEXT NOT NULL,
    last_sync TEXT,
    sync_direction TEXT DEFAULT 'bidirectional',  -- wiki_to_drive, drive_to_wiki, bidirectional
    conflict_resolution TEXT DEFAULT 'merge',  -- drive_wins, wiki_wins, merge
    webhook_channel_id TEXT,
    webhook_expiry TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- File mapping
CREATE TABLE wiki_drive_files (
    wiki_path TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    drive_file_id TEXT NOT NULL,
    drive_modified TEXT,
    wiki_modified TEXT,
    sync_status TEXT DEFAULT 'synced',  -- synced, pending, conflict
    PRIMARY KEY (wiki_path, guild_id),
    FOREIGN KEY (guild_id) REFERENCES wiki_drive_sync(guild_id) ON DELETE CASCADE
);

-- Sync history
CREATE TABLE wiki_drive_sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    direction TEXT NOT NULL,  -- to_drive, from_drive
    wiki_path TEXT NOT NULL,
    drive_file_id TEXT,
    action TEXT NOT NULL,  -- create, update, delete, conflict
    modified_by TEXT,  -- email for Drive, 'llm' for wiki
    timestamp TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (guild_id) REFERENCES wiki_drive_sync(guild_id) ON DELETE CASCADE
);

CREATE INDEX idx_drive_files_guild ON wiki_drive_files(guild_id);
CREATE INDEX idx_drive_sync_log_guild ON wiki_drive_sync_log(guild_id);
```

---

## Implementation Phases

### Phase 1: Dashboard Rendering (3 weeks)
- [ ] Wiki tab with navigation tree
- [ ] Page view with markdown rendering
- [ ] Basic search (FTS5)
- [ ] Summary → wiki updates display

### Phase 2: AI Search (2 weeks)
- [ ] AI-synthesized answers
- [ ] Cmd+K quick search
- [ ] "Save answer to wiki" flow

### Phase 3: Google Drive Sync (3 weeks)
- [ ] OAuth connection flow
- [ ] Folder structure creation
- [ ] Wiki → Drive push
- [ ] Drive webhook setup

### Phase 4: Bidirectional Sync (2 weeks)
- [ ] Drive → Wiki pull
- [ ] Conflict detection
- [ ] Merge logic
- [ ] Sync settings UI

### Phase 5: Bot Commands (1 week)
- [ ] /wiki search
- [ ] /wiki ask
- [ ] /wiki expert

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Wiki page views | >50/week | Dashboard analytics |
| Search queries | >20/week | Query logs |
| AI answer satisfaction | >75% | Thumbs up/down |
| Drive sync adoption | >30% of guilds | Settings |
| External edits | >10% of updates | Sync logs |

## Consequences

### Positive
- Wiki accessible where users already work (dashboard, Drive, chat)
- External stakeholders can view/edit without dashboard access
- Human edits preserved and integrated
- Backup via Google Drive

### Negative
- Google Drive dependency for sync feature
- Conflict resolution complexity
- Additional OAuth scope requirements
- Sync latency considerations

### Mitigations
- Drive sync is optional (wiki works without it)
- Clear conflict UI with manual resolution option
- Incremental scope requests (drive.file only)
- Webhook-based near-real-time sync

## References

- [ADR-056: Compounding Wiki - Standard](./ADR-056-compounding-wiki-standard.md)
- [ADR-057: Compounding Wiki - RuVector](./ADR-057-compounding-wiki-ruvector.md)
- [ADR-049: Google Workspace SSO](./ADR-049-google-workspace-sso.md)
- [Google Drive API](https://developers.google.com/drive/api)
