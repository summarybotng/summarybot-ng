# ADR-007: Per-Server Google Drive Sync with Fallback

**Status:** Proposed
**Date:** 2026-02-15
**Depends on:** ADR-006 (Retrospective Summary Archive)
**Repository:** [summarybotng/summarybot-ng](https://github.com/summarybotng/summarybot-ng)

---

## 1. Problem Statement

The current archive system stores summaries in ephemeral local storage, which is lost on redeployment. ADR-006 introduced Google Drive sync capability, but it lacks:

1. **Per-Server Configuration** — Different Discord servers may want their archives synced to different Google Drives (e.g., each organization owns their data).

2. **No Fallback Mechanism** — If a server doesn't have a configured Google Drive, there's no default location to sync their archives.

3. **Configuration Complexity** — Server administrators need an easy way to configure their own Google Drive without accessing the bot's infrastructure.

4. **Cost Isolation** — Organizations may want their archive storage costs separate from other servers.

5. **Data Ownership** — Some organizations require their data to be stored in their own cloud accounts for compliance or governance reasons.

---

## 2. Decision

Implement a **hierarchical Google Drive configuration system** with:

1. **Server-level configuration** — Each Discord server can configure its own Google Drive folder
2. **Global fallback** — A default Google Drive for servers without custom configuration
3. **Dashboard UI** — Server admins can configure their Drive via the web dashboard
4. **OAuth flow** — Secure Google Drive authorization without sharing credentials

### 2.1 Configuration Hierarchy

```
┌─────────────────────────────────────────────────────────────────┐
│                     Drive Resolution Order                       │
├─────────────────────────────────────────────────────────────────┤
│  1. Server-specific Drive (configured by server admin)          │
│     ↓ (if not configured)                                       │
│  2. Global fallback Drive (configured by bot operator)          │
│     ↓ (if not configured)                                       │
│  3. Local storage only (no cloud sync)                          │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Configuration Schema

#### Server-Level Configuration (stored in `server-manifest.json`)

```json
{
  "server_id": "1283874310720716890",
  "server_name": "Agentics Foundation",
  "sync": {
    "google_drive": {
      "enabled": true,
      "folder_id": "1ABC123xyz...",
      "folder_name": "Agentics Archive",
      "credentials_type": "oauth",
      "oauth_token_id": "srv_1283874310720716890_gdrive",
      "configured_by": "123456789012345678",
      "configured_at": "2026-02-15T10:00:00Z",
      "last_sync": "2026-02-15T12:00:00Z",
      "sync_frequency": "on_generation",
      "sync_options": {
        "preserve_structure": true,
        "include_metadata": true,
        "include_cost_reports": false
      }
    }
  }
}
```

#### Global Fallback Configuration (stored in `.archive-config.json`)

```json
{
  "schema_version": "1.0.0",
  "sync": {
    "default_provider": "google_drive",
    "google_drive": {
      "enabled": true,
      "folder_id": "1XYZ789abc...",
      "folder_name": "SummaryBot Archives",
      "credentials_type": "service_account",
      "credentials_path": "/secrets/google-drive-sa.json",
      "create_server_subfolders": true,
      "subfolder_naming": "{server_name}_{server_id}",
      "sync_frequency": "hourly",
      "retention_days": null
    }
  },
  "servers": {
    "allow_custom_drives": true,
    "require_admin_approval": false,
    "allowed_domains": ["*"]
  }
}
```

### 2.3 OAuth Flow for Server Configuration

Server administrators configure their Google Drive through a secure OAuth flow:

```
┌──────────────────────────────────────────────────────────────────┐
│                    Server Admin OAuth Flow                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. Admin clicks "Connect Google Drive" in Dashboard              │
│     └─► Dashboard redirects to /api/v1/archive/oauth/google       │
│                                                                   │
│  2. Server generates OAuth URL with state token                   │
│     └─► State includes: server_id, user_id, redirect_uri          │
│                                                                   │
│  3. Admin authorizes on Google consent screen                     │
│     └─► Scopes: drive.file (limited to bot-created files)         │
│                                                                   │
│  4. Google redirects back with authorization code                 │
│     └─► /api/v1/archive/oauth/google/callback?code=...&state=...  │
│                                                                   │
│  5. Server exchanges code for tokens                              │
│     └─► Stores encrypted refresh_token in secure storage          │
│                                                                   │
│  6. Admin selects or creates target folder                        │
│     └─► Dashboard shows folder picker UI                          │
│                                                                   │
│  7. Configuration saved to server-manifest.json                   │
│     └─► Immediate sync triggered to verify access                 │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 2.4 Sync Resolution Logic

```python
class DriveResolver:
    """Resolves which Google Drive to use for a given source."""

    def __init__(self, archive_root: Path, global_config: GlobalSyncConfig):
        self.archive_root = archive_root
        self.global_config = global_config
        self._token_store = SecureTokenStore()

    async def resolve_drive(self, source: ArchiveSource) -> Optional[GoogleDriveConfig]:
        """
        Resolve the Google Drive configuration for a source.

        Resolution order:
        1. Server-specific configuration
        2. Global fallback
        3. None (local-only)
        """
        # Try server-specific config first
        server_config = await self._get_server_config(source)
        if server_config and server_config.sync.google_drive.enabled:
            return await self._build_drive_config(
                server_config.sync.google_drive,
                source
            )

        # Fall back to global config
        if self.global_config.google_drive.enabled:
            return await self._build_fallback_config(source)

        # No sync configured
        return None

    async def _get_server_config(self, source: ArchiveSource) -> Optional[ServerManifest]:
        """Load server-specific manifest."""
        manifest_path = self._get_manifest_path(source)
        if not manifest_path.exists():
            return None
        return ServerManifest.from_file(manifest_path)

    async def _build_drive_config(
        self,
        config: ServerDriveConfig,
        source: ArchiveSource
    ) -> GoogleDriveConfig:
        """Build drive config from server settings."""
        # Get OAuth tokens from secure storage
        tokens = await self._token_store.get_tokens(config.oauth_token_id)

        return GoogleDriveConfig(
            enabled=True,
            folder_id=config.folder_id,
            credentials_type="oauth",
            oauth_tokens=tokens,
            preserve_structure=config.sync_options.get("preserve_structure", True),
        )

    async def _build_fallback_config(self, source: ArchiveSource) -> GoogleDriveConfig:
        """Build drive config using global fallback."""
        config = self.global_config.google_drive

        # Create server subfolder if configured
        folder_id = config.folder_id
        if config.create_server_subfolders:
            subfolder_name = config.subfolder_naming.format(
                server_name=source.server_name,
                server_id=source.server_id,
                source_type=source.source_type.value,
            )
            folder_id = await self._ensure_subfolder(folder_id, subfolder_name)

        return GoogleDriveConfig(
            enabled=True,
            folder_id=folder_id,
            credentials_type="service_account",
            credentials_path=config.credentials_path,
            preserve_structure=True,
        )
```

### 2.5 API Endpoints

#### OAuth Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/archive/oauth/google` | Initiate OAuth flow |
| `GET` | `/api/v1/archive/oauth/google/callback` | Handle OAuth callback |
| `DELETE` | `/api/v1/archive/oauth/google/{server_id}` | Disconnect Google Drive |

#### Configuration Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/archive/sync/config` | Get global sync config |
| `PUT` | `/api/v1/archive/sync/config` | Update global sync config |
| `GET` | `/api/v1/archive/sync/config/{server_id}` | Get server sync config |
| `PUT` | `/api/v1/archive/sync/config/{server_id}` | Update server sync config |
| `GET` | `/api/v1/archive/sync/status/{server_id}` | Get sync status |
| `POST` | `/api/v1/archive/sync/trigger/{server_id}` | Trigger manual sync |

### 2.6 Dashboard UI

#### Server Settings → Archive Sync

```
┌─────────────────────────────────────────────────────────────────┐
│  Archive Sync Settings                                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Google Drive Sync                                               │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  ○ Use default archive location (Bot operator's Drive)     │ │
│  │  ● Use custom Google Drive                                  │ │
│  │                                                              │ │
│  │  Connected: My Organization Drive                           │ │
│  │  Folder: /Archives/Discord Summaries                        │ │
│  │  Last sync: 5 minutes ago (32 files)                        │ │
│  │                                                              │ │
│  │  [Disconnect]  [Change Folder]  [Sync Now]                  │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  Sync Options                                                    │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  ☑ Sync automatically after each summary generation        │ │
│  │  ☐ Include metadata files (.meta.json)                      │ │
│  │  ☐ Include cost reports                                     │ │
│  │  ☑ Preserve folder structure (YYYY/MM/...)                  │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  [Save Settings]                                                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.7 Security Considerations

1. **OAuth Token Storage**
   - Refresh tokens encrypted at rest using server-side key
   - Tokens stored separately from other configuration
   - Token IDs reference secure storage, not embedded in manifests

2. **Scope Limitation**
   - Use `drive.file` scope (access only to files created by the app)
   - Cannot access user's other Drive files

3. **Permission Verification**
   - Only server admins (ADMINISTRATOR permission) can configure Drive
   - Bot operator can restrict which servers can use custom drives

4. **Audit Trail**
   - Log all sync operations with timestamps
   - Record who configured/modified sync settings

### 2.8 Environment Variables

```bash
# Global fallback Google Drive (service account)
ARCHIVE_GOOGLE_DRIVE_ENABLED=true
ARCHIVE_GOOGLE_DRIVE_FOLDER_ID=1XYZ789abc...
ARCHIVE_GOOGLE_DRIVE_CREDENTIALS_PATH=/secrets/google-drive-sa.json
ARCHIVE_GOOGLE_DRIVE_CREATE_SUBFOLDERS=true

# OAuth configuration (for server-specific drives)
GOOGLE_OAUTH_CLIENT_ID=123456789.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=GOCSPX-...
GOOGLE_OAUTH_REDIRECT_URI=https://summarybot-ng.fly.dev/api/v1/archive/oauth/google/callback

# Token encryption
ARCHIVE_TOKEN_ENCRYPTION_KEY=<32-byte-base64-key>

# Policy settings
ARCHIVE_ALLOW_CUSTOM_DRIVES=true
ARCHIVE_REQUIRE_ADMIN_APPROVAL=false
```

---

## 3. Consequences

### 3.1 Positive

1. **Data Ownership** — Organizations control where their archives are stored
2. **Compliance** — Supports data residency and governance requirements
3. **Cost Separation** — Storage costs attributed to respective organizations
4. **Flexibility** — Works with or without custom configuration
5. **Security** — OAuth flow more secure than shared credentials

### 3.2 Negative

1. **Complexity** — More configuration surfaces to manage
2. **OAuth Maintenance** — Tokens can expire, requiring re-authorization
3. **Support Burden** — Users may need help configuring their drives

### 3.3 Mitigations

1. **Clear Documentation** — Step-by-step setup guides with screenshots
2. **Token Refresh** — Automatic token refresh before expiration
3. **Status Monitoring** — Dashboard shows sync health, alerts on failures
4. **Graceful Degradation** — Falls back to default/local on sync failures

---

## 4. Implementation Phases

### Phase 1: Global Fallback (MVP)
- [ ] Environment variable configuration
- [ ] Service account authentication
- [ ] Auto-sync after summary generation
- [ ] Sync status in dashboard

### Phase 2: Server-Specific Configuration
- [ ] OAuth flow implementation
- [ ] Secure token storage
- [ ] Server manifest updates
- [ ] Dashboard UI for configuration

### Phase 3: Advanced Features
- [ ] Folder picker UI
- [ ] Sync scheduling options
- [ ] Selective sync (include/exclude patterns)
- [ ] Sync conflict resolution settings

---

## 5. Alternatives Considered

### 5.1 Shared Service Account Only

**Rejected because:**
- All archives in one Drive account
- No data ownership separation
- Single point of failure
- Storage quota limits

### 5.2 Direct Credential Input

**Rejected because:**
- Security risk (users paste credentials)
- Difficult to rotate
- No standardized flow

### 5.3 Webhook-Based Sync

**Rejected because:**
- Requires users to run their own sync service
- More complex setup
- Less reliable

---

## 6. References

- [Google Drive API - OAuth 2.0](https://developers.google.com/drive/api/guides/about-auth)
- [Google Drive API - Manage Files](https://developers.google.com/drive/api/guides/manage-uploads)
- [ADR-006: Retrospective Summary Archive](./006-retrospective-summary-archive.md)
- [OAuth 2.0 Security Best Practices](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-security-topics)
