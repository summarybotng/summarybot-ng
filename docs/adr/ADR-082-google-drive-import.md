# ADR-082: Google Drive Import for WhatsApp Exports

## Status
Accepted (Revised)

## Date
2026-05-02 (Revised 2026-05-03)

## Context

Users currently import WhatsApp exports via drag-and-drop file upload (ADR-081). However, many users store their WhatsApp exports in Google Drive, requiring them to:

1. Open Google Drive
2. Download the file locally
3. Navigate to the WhatsApp imports page
4. Upload the file

This friction reduces adoption. Users should be able to import directly from Google Drive.

### Privacy Concern

The original design used Google Picker API with `drive.readonly` scope, which requests access to browse ALL files in a user's Drive. This is:
- Overly broad for our needs
- Scary for privacy-conscious users
- Requires OAuth consent flow

## Decision

Use a **shared upload folder** approach instead of per-user OAuth:

1. App maintains a Google Drive folder for uploads (via service account)
2. Users receive a shareable link to upload files
3. App scans folder for new files and processes them
4. Processed files move to archive subfolder

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Flow                                 │
│                                                                  │
│  1. User clicks "Get Upload Link"                               │
│  2. User receives per-guild upload folder link                  │
│  3. User uploads .txt/.zip to that folder                       │
│  4. Backend polls folder, processes new files                   │
│  5. Processed files move to /processed subfolder                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Google Drive                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  /SummaryBot Uploads/                                       ││
│  │    ├── guild_123456789/                                     ││
│  │    │     ├── WhatsApp Chat - AI Code.txt    ← NEW           ││
│  │    │     └── /processed/                                    ││
│  │    │           └── WhatsApp Chat - AI Code.txt (imported)   ││
│  │    └── guild_987654321/                                     ││
│  │          └── ...                                            ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Service Account Access
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Backend                                   │
│  ┌─────────────────┐    ┌─────────────────┐                     │
│  │  Drive Folder   │───▶│  WhatsApp       │                     │
│  │  Scanner        │    │  Importer       │                     │
│  └────────┬────────┘    └─────────────────┘                     │
│           │                                                      │
│           │ Scheduled scan (every 5 min)                         │
│           ▼                                                      │
│  ┌─────────────────┐                                            │
│  │  Google Drive   │                                            │
│  │  Service Acct   │                                            │
│  └─────────────────┘                                            │
└─────────────────────────────────────────────────────────────────┘
```

### Shared Folder Approach

No per-user OAuth required. Uses existing service account (from ADR-007 sync).

#### 1. Folder Structure

```
/SummaryBot Uploads/              (created by service account)
  ├── {guild_id}/                 (per-guild subfolder)
  │     ├── *.txt, *.zip          (user uploads here)
  │     └── /processed/           (files move here after import)
  └── ...
```

Each guild gets a unique upload folder. Users can only see/upload to their guild's folder.

#### 2. Backend: Folder Scanner Service

```python
# src/archive/sync/drive_folder_scanner.py

class DriveFolderScanner:
    """Scans shared upload folders for new WhatsApp exports."""

    def __init__(self, service_account_creds):
        self.drive = build('drive', 'v3', credentials=service_account_creds)
        self.root_folder_id = None

    async def scan_guild_folder(self, guild_id: str) -> List[DriveFile]:
        """Find new files in guild's upload folder."""
        folder_id = await self.get_or_create_guild_folder(guild_id)

        # List files not in /processed
        results = self.drive.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="files(id, name, mimeType, size, createdTime)"
        ).execute()

        return [f for f in results.get('files', [])
                if f['name'].endswith(('.txt', '.zip'))]

    async def process_and_archive(self, file_id: str, guild_id: str):
        """Download file, process as import, move to /processed."""
        # Download
        content = self.download_file(file_id)

        # Import (reuse existing WhatsApp import logic)
        await process_whatsapp_import(guild_id, content, ...)

        # Move to processed folder
        processed_folder = await self.get_processed_folder(guild_id)
        self.drive.files().update(
            fileId=file_id,
            addParents=processed_folder,
            removeParents=original_folder
        ).execute()
```

#### 3. Backend: Get Upload Link Endpoint

```python
# GET /api/v1/whatsapp/guilds/{guild_id}/drive/upload-link

@router.get("/guilds/{guild_id}/drive/upload-link")
async def get_upload_link(guild_id: str, user: dict = Depends(get_current_user)):
    """Get the Google Drive upload folder link for this guild."""
    scanner = get_drive_scanner()
    folder_id = await scanner.get_or_create_guild_folder(guild_id)

    # Create shareable link (anyone with link can upload)
    permission = {
        'type': 'anyone',
        'role': 'writer',  # Can upload files
    }
    scanner.drive.permissions().create(
        fileId=folder_id,
        body=permission
    ).execute()

    return {
        "folder_url": f"https://drive.google.com/drive/folders/{folder_id}",
        "folder_id": folder_id,
        "instructions": "Upload your WhatsApp export (.txt or .zip) to this folder"
    }
```

#### 4. Scheduled Scanner Task

```python
# Run every 5 minutes via scheduler

async def scan_all_guild_folders():
    """Scan all guild upload folders for new files."""
    scanner = get_drive_scanner()

    # Get all guilds with Drive import enabled
    guilds = await get_guilds_with_drive_folders()

    for guild in guilds:
        try:
            new_files = await scanner.scan_guild_folder(guild.id)
            for file in new_files:
                await scanner.process_and_archive(file.id, guild.id)
                logger.info(f"Imported {file.name} for guild {guild.id}")
        except Exception as e:
            logger.error(f"Error scanning guild {guild.id}: {e}")
```

### Security Considerations

1. **Isolation**: Each guild has its own folder - users can't see other guilds' files
2. **Write-Only Sharing**: Users can upload but can't list/read other uploads
3. **Service Account**: No user OAuth needed - service account owns all folders
4. **File Validation**: Validate file type/size before processing
5. **Auto-Archive**: Processed files move to /processed, keeping inbox clean

### Database Changes

Simplified - just track guild folder mappings:

```sql
-- Track guild upload folders
CREATE TABLE IF NOT EXISTS guild_drive_folders (
    guild_id TEXT PRIMARY KEY,
    folder_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Keep drive_import_log for audit trail
CREATE TABLE IF NOT EXISTS drive_import_log (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    drive_file_id TEXT NOT NULL,
    drive_file_name TEXT NOT NULL,
    file_size_bytes INTEGER,
    import_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);
```

### UI Changes

#### WhatsApp Imports Page

```
┌─────────────────────────────────────────────────────────────────┐
│  Upload Export                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                                                           │  │
│  │     📁 Drop WhatsApp .txt or .zip here                   │  │
│  │         or click to browse                               │  │
│  │                                                           │  │
│  │  ─────────────────── or ───────────────────              │  │
│  │                                                           │  │
│  │     [📁 Upload via Google Drive]                         │  │
│  │                                                           │  │
│  │     Opens shared folder link - just drop files there     │  │
│  │     Files are automatically imported within 5 minutes    │  │
│  │                                                           │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Implementation Phases

#### Phase 1: Backend Foundation
- [x] Create `guild_drive_folders` table migration
- [ ] Implement DriveFolderScanner service
- [ ] Add `/drive/upload-link` endpoint
- [ ] Add scheduled folder scanner task

#### Phase 2: Frontend Integration
- [ ] Add "Upload via Google Drive" button
- [ ] Show folder link in modal with instructions
- [ ] Add pending imports indicator

#### Phase 3: Polish
- [ ] Add webhook for instant processing (instead of polling)
- [ ] Show recent Drive imports in UI
- [ ] Email notification when import completes

### Configuration

Required environment variables:

```bash
# Google Cloud Console - Service Account (existing from ADR-007)
GOOGLE_SERVICE_ACCOUNT_KEY='{...}'  # JSON key file contents

# Optional: Root folder name
DRIVE_UPLOAD_ROOT_FOLDER=SummaryBot Uploads
```

### Error Handling

| Error | User Message | Action |
|-------|--------------|--------|
| Folder creation failed | "Could not create upload folder" | Retry |
| File too large | "File exceeds 50MB limit" | Skip, log error |
| Invalid format | "Only .txt and .zip files supported" | Skip, move to /rejected |
| Import failed | "Could not process file" | Keep in folder, log |

### Advantages Over OAuth Approach

1. **No scary permissions**: Users don't grant access to their entire Drive
2. **Simpler flow**: Just click a link, drop files
3. **Works on mobile**: Native Drive app supports folder uploads
4. **No token management**: Service account handles everything
5. **Privacy**: Users only see their guild's folder

## Consequences

### Positive
- **No scary permissions**: Users don't grant access to their entire Drive
- **Simpler UX**: Just click a link and drop files
- **Works on mobile**: Native Drive app supports folder uploads
- **No token management**: Service account handles everything
- **Privacy-friendly**: Users only see their guild's upload folder
- **Reuses existing infrastructure**: Service account from ADR-007 sync

### Negative
- **Polling delay**: Up to 5 minutes before files are processed (vs instant with Picker)
- **Requires Google account**: Users need a Google account to upload
- **Folder management**: Service account accumulates folders over time

### Neutral
- Users without Google accounts unaffected (direct file upload still works)
- Processed files stay in Drive (in /processed folder) for reference

## References

- [Google Drive API v3](https://developers.google.com/drive/api/v3/reference)
- [Google Drive Sharing](https://developers.google.com/drive/api/guides/manage-sharing)
- [ADR-007: Google Drive Sync](./ADR-007-archive-sync.md)
- [ADR-081: WhatsApp Import Management](./ADR-081-whatsapp-import-management.md)
