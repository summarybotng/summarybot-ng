# ADR-086: Bidirectional Summary-Wiki Navigation

## Status
Accepted

## Date
2026-05-04

## Context

Currently, users can navigate from wiki pages to their source summaries:
- Wiki pages display `source_refs` showing which summaries contributed content
- Clicking a source reference links to the original summary

However, the reverse navigation is missing:
- From a summary view, users cannot see which wiki pages it contributed to
- Users cannot trace how their chat conversations become wiki content
- The `wiki_ingested` flag exists but isn't exposed in the UI

### Current Data Model

```
stored_summaries                    wiki_pages
┌──────────────────────┐           ┌──────────────────────┐
│ id                   │           │ path                 │
│ wiki_ingested: bool  │◀─────────▶│ source_refs: [       │
│ wiki_ingested_at     │   via     │   "summary-abc123",  │
└──────────────────────┘  lookup   │   "summary-xyz789"   │
                                   │ ]                    │
                                   └──────────────────────┘
```

## Decision

Add bidirectional navigation between summaries and wiki pages.

### 1. API Changes

#### Extend Summary Response

`GET /guilds/{guild_id}/stored-summaries/{summary_id}` now includes wiki info:

```json
{
  "id": "abc123",
  "wiki_ingested": true,
  "wiki_ingested_at": "2026-05-04T10:30:00Z",
  "wiki_pages": [
    {
      "path": "topics/authentication.md",
      "title": "Authentication",
      "updated_at": "2026-05-04T10:30:00Z"
    }
  ]
}
```

#### New Endpoint: Get Wiki Pages for Summary

`GET /guilds/{guild_id}/stored-summaries/{summary_id}/wiki-pages`

Returns all wiki pages that reference this summary:

```json
{
  "summary_id": "abc123",
  "wiki_pages": [
    {
      "path": "topics/authentication.md",
      "title": "Authentication",
      "excerpt": "OAuth2 implementation discussed in team standup...",
      "section": "Recent Updates",
      "updated_at": "2026-05-04T10:30:00Z"
    }
  ],
  "total_pages": 1
}
```

### 2. Frontend Changes

#### Summary Detail View

Add wiki section to summary detail:

```
┌─────────────────────────────────────────────────────────────┐
│  Summary: Team Standup - May 4, 2026                        │
│  ─────────────────────────────────────────────────────────  │
│  [Key Points] [Action Items] [Participants]                 │
│                                                             │
│  📄 Key Points                                              │
│  • Discussed OAuth2 implementation approach                 │
│  • ...                                                      │
│                                                             │
│  📚 Used in Wiki                                ← NEW       │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ ✓ Ingested May 4, 2026 10:30 AM                       │ │
│  │                                                        │ │
│  │ Pages updated:                                         │ │
│  │ • 📄 Authentication → View in Wiki                    │ │
│  │ • 📄 API Design → View in Wiki                        │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

#### Summary List View

Add wiki badge to summary cards:

```
┌─────────────────────────────────────────────────────────────┐
│ 📋 Team Standup               May 4, 2026    [Wiki ✓] [→]  │
│    #general • 45 messages                                   │
└─────────────────────────────────────────────────────────────┘
```

### 3. Implementation

#### Backend: Wiki Repository Method

```python
# src/data/sqlite/wiki_repository.py

async def find_pages_by_summary(
    self,
    guild_id: str,
    summary_id: str
) -> List[WikiPage]:
    """Find all wiki pages that reference a summary."""
    source_id = f"summary-{summary_id}"

    query = """
    SELECT * FROM wiki_pages
    WHERE guild_id = ?
    AND json_extract(source_refs, '$') LIKE ?
    """
    # Use LIKE for JSON array contains check
    rows = await self.connection.fetch_all(
        query, (guild_id, f'%"{source_id}"%')
    )
    return [self._row_to_page(row) for row in rows]
```

#### Backend: Summary Route Enhancement

```python
# src/dashboard/routes/summaries.py

@router.get("/guilds/{guild_id}/stored-summaries/{summary_id}/wiki-pages")
async def get_summary_wiki_pages(
    guild_id: str,
    summary_id: str,
    user: dict = Depends(get_current_user),
):
    """Get wiki pages that reference this summary."""
    wiki_repo = await get_wiki_repository()
    pages = await wiki_repo.find_pages_by_summary(guild_id, summary_id)

    return {
        "summary_id": summary_id,
        "wiki_pages": [
            {
                "path": p.path,
                "title": p.title,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p in pages
        ],
        "total_pages": len(pages),
    }
```

#### Frontend: Hook and Component

```typescript
// src/frontend/src/hooks/useSummaries.ts

export function useSummaryWikiPages(guildId: string, summaryId: string) {
  return useQuery({
    queryKey: ["summary-wiki-pages", guildId, summaryId],
    queryFn: () => api.get(`/guilds/${guildId}/stored-summaries/${summaryId}/wiki-pages`),
    enabled: !!guildId && !!summaryId,
  });
}
```

```tsx
// In summary detail component
{summary.wiki_ingested && (
  <div className="mt-4 border-t pt-4">
    <h4 className="text-sm font-medium flex items-center gap-2">
      <BookOpen className="h-4 w-4" />
      Used in Wiki
    </h4>
    <p className="text-xs text-muted-foreground">
      Ingested {formatDate(summary.wiki_ingested_at)}
    </p>
    <WikiPagesForSummary guildId={guildId} summaryId={summary.id} />
  </div>
)}
```

### 4. Navigation Flow

Complete bidirectional navigation:

```
Summary List     Summary Detail        Wiki Page         Wiki Source
    │                  │                   │                  │
    │    click         │                   │                  │
    ├─────────────────▶│                   │                  │
    │                  │    "View in       │                  │
    │                  │     Wiki" click   │                  │
    │                  ├──────────────────▶│                  │
    │                  │                   │   "View          │
    │                  │                   │   Source" click  │
    │                  │◀──────────────────┤──────────────────┤
    │                  │                   │                  │
```

## Consequences

### Positive
- Users can trace summary content to wiki pages
- Complete audit trail of knowledge synthesis
- Better understanding of wiki coverage
- Visual feedback for wiki-enabled guilds

### Negative
- Additional API calls for wiki page lookup
- Slightly more complex summary UI
- Performance consideration for summaries with many wiki references

### Neutral
- Only visible when wiki is enabled for guild
- Graceful fallback when no wiki pages exist

## Related ADRs

- ADR-061: AI Wiki Synthesis
- ADR-067: Automatic Wiki Ingestion
- ADR-080: Wiki Perspective Filtering
