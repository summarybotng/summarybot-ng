# ADR-029: Confluence Integration

**Status:** Proposed
**Date:** 2026-03-03
**Depends on:** ADR-008 (Unified Summary Experience)

## 1. Context

Users want to export summaries to Confluence for:
- Team documentation and knowledge bases
- Meeting notes archives
- Project activity logs
- Searchable historical records

### Options Considered

| Approach | Pros | Cons |
|----------|------|------|
| **REST API** | Full control, simple deployment, no extra processes | Must implement auth/formatting ourselves |
| **Atlassian MCP Server** | Pre-built auth, Claude-native | Architecture mismatch (MCP is for AI reading, we need to write), extra process |
| **Community MCP** | Supports Server/DC, pre-built tools | Same architecture mismatch, another dependency |

### Decision

**Use Confluence REST API directly** because:
1. SummaryBot needs to **push** content to Confluence (MCP optimized for AI pulling)
2. Server-side operation with no interactive Claude session
3. Simpler deployment without additional MCP server process
4. Full control over page formatting and structure

## 2. Design

### 2.1 Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│  StoredSummary  │────▶│ ConfluenceExporter   │────▶│ Confluence API  │
│  (Database)     │     │ - format conversion  │     │ (Cloud or DC)   │
└─────────────────┘     │ - page management    │     └─────────────────┘
                        │ - auth handling      │
                        └──────────────────────┘
```

### 2.2 Export Service

```python
class ConfluenceExporter:
    """Export summaries to Confluence pages."""

    async def export_summary(
        self,
        summary: StoredSummary,
        space_key: str,
        parent_page_id: Optional[str] = None,
        title_template: str = "{channel} - {date}",
    ) -> ConfluenceExportResult:
        """Export a single summary to a Confluence page."""

    async def export_batch(
        self,
        summaries: List[StoredSummary],
        space_key: str,
        parent_page_id: Optional[str] = None,
    ) -> List[ConfluenceExportResult]:
        """Export multiple summaries as child pages."""
```

### 2.3 Authentication

Support both Confluence Cloud and Server/Data Center:

| Deployment | Auth Method | Credentials |
|------------|-------------|-------------|
| **Cloud** | API Token | `email` + `api_token` |
| **Server/DC** | Basic Auth or PAT | `username` + `password` or `personal_access_token` |

```python
@dataclass
class ConfluenceConfig:
    base_url: str           # https://company.atlassian.net/wiki or https://confluence.company.com
    auth_type: str          # "cloud" or "server"
    email: Optional[str]    # Cloud only
    api_token: str          # API token or PAT
    username: Optional[str] # Server only
```

Environment variables:
```env
CONFLUENCE_BASE_URL=https://company.atlassian.net/wiki
CONFLUENCE_AUTH_TYPE=cloud
CONFLUENCE_EMAIL=user@company.com
CONFLUENCE_API_TOKEN=your_api_token
```

### 2.4 Content Formatting

Confluence uses a storage format (XHTML-based). We need to convert:

| Source | Target |
|--------|--------|
| Markdown summary | Confluence storage format |
| Key points list | Confluence bullet list |
| Action items | Task list macro or checkboxes |
| References | Links with jump URLs |

**Conversion approach:**
1. Parse summary Markdown
2. Convert to Confluence storage format using a converter
3. Wrap in structured template with metadata panel

**Page template:**
```xml
<ac:structured-macro ac:name="info">
  <ac:rich-text-body>
    <p><strong>Summary Period:</strong> {start} - {end}</p>
    <p><strong>Source:</strong> {source_type} / {channel_name}</p>
    <p><strong>Messages:</strong> {message_count}</p>
  </ac:rich-text-body>
</ac:structured-macro>

<h2>Summary</h2>
{converted_summary_content}

<h2>Key Points</h2>
<ul>
  {key_points_as_list_items}
</ul>

<h2>Action Items</h2>
{action_items_as_tasks}

<ac:structured-macro ac:name="expand">
  <ac:parameter ac:name="title">Generation Details</ac:parameter>
  <ac:rich-text-body>
    <p>Model: {model}</p>
    <p>Generated: {timestamp}</p>
    <p>Prompt Version: {prompt_version}</p>
  </ac:rich-text-body>
</ac:structured-macro>
```

### 2.5 Page Management

**Page naming:** Configurable template with variables:
- `{channel}` - Channel or source name
- `{date}` - Summary date (YYYY-MM-DD)
- `{period}` - "Daily", "Weekly", "Monthly"
- `{guild}` - Server/guild name

**Update behavior:**
- Check if page with same title exists in space
- If exists: update content (preserves page ID, comments, history)
- If not: create new page

**Hierarchy options:**
1. **Flat** - All summaries as siblings under parent
2. **By date** - Year → Month → Day pages
3. **By channel** - Channel parent → date children

### 2.6 Database Model

Track exports for idempotency and linking:

```sql
CREATE TABLE confluence_exports (
    id TEXT PRIMARY KEY,
    summary_id TEXT NOT NULL,
    confluence_page_id TEXT NOT NULL,
    confluence_page_url TEXT NOT NULL,
    space_key TEXT NOT NULL,
    exported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    exported_by TEXT,

    FOREIGN KEY (summary_id) REFERENCES stored_summaries(id)
);

CREATE INDEX idx_confluence_exports_summary ON confluence_exports(summary_id);
CREATE INDEX idx_confluence_exports_page ON confluence_exports(confluence_page_id);
```

## 3. API Endpoints

### Export Single Summary
```
POST /api/v1/summaries/{summary_id}/export/confluence
{
  "space_key": "TEAM",
  "parent_page_id": "123456",  // optional
  "title": "Custom Title"       // optional, uses template if omitted
}

Response:
{
  "page_id": "789012",
  "page_url": "https://company.atlassian.net/wiki/spaces/TEAM/pages/789012",
  "title": "general - 2026-03-03",
  "created": true  // false if updated existing
}
```

### Export Batch
```
POST /api/v1/export/confluence/batch
{
  "summary_ids": ["sum_abc123", "sum_def456"],
  "space_key": "TEAM",
  "parent_page_id": "123456"
}

Response:
{
  "exported": 2,
  "failed": 0,
  "results": [...]
}
```

### List Available Spaces
```
GET /api/v1/confluence/spaces

Response:
{
  "spaces": [
    {"key": "TEAM", "name": "Team Documentation"},
    {"key": "ENG", "name": "Engineering"}
  ]
}
```

## 4. UI Integration

### Summary Card Actions
Add "Export to Confluence" option in summary actions dropdown:
- Opens modal to select space and parent page
- Shows preview of page title
- Displays link after successful export

### Bulk Export
In Summaries tab with multi-select:
- "Export Selected to Confluence" button
- Batch export with progress indicator

### Settings Page
Confluence configuration section:
- Connection settings (URL, auth)
- Test connection button
- Default space and parent page
- Title template configuration

## 5. Implementation Plan

### Phase 1: Core Service
- [ ] `ConfluenceClient` - HTTP client with auth
- [ ] `ConfluenceExporter` - Export logic
- [ ] Markdown → Confluence converter
- [ ] Database migration for exports table

### Phase 2: API & Testing
- [ ] REST endpoints for export
- [ ] Spaces/pages listing endpoints
- [ ] Unit tests with mocked API
- [ ] Integration tests with real Confluence (optional)

### Phase 3: UI
- [ ] Export modal component
- [ ] Settings page section
- [ ] Bulk export support
- [ ] Export history/status display

## 6. Security Considerations

1. **Token storage**: API tokens stored encrypted (like prompt tokens)
2. **Least privilege**: Only request necessary Confluence permissions
3. **Audit logging**: Log all exports with user attribution
4. **Rate limiting**: Respect Confluence API limits (Cloud: ~100 req/min)

## 7. Error Handling

| Error | Handling |
|-------|----------|
| Auth failure | Clear error message, prompt to check credentials |
| Space not found | List available spaces for user |
| Permission denied | Show which permission is missing |
| Page conflict | Offer to update or create with suffix |
| Rate limited | Queue and retry with backoff |

## 8. Future Enhancements

- **Scheduled exports**: Auto-export daily summaries to Confluence
- **Two-way sync**: Detect manual edits in Confluence
- **Templates**: User-defined page templates
- **Labels**: Auto-apply Confluence labels based on content
- **Attachments**: Export charts/visualizations as images
