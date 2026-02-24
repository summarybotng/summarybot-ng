# ADR-020: Summary Navigation and Search

## Status
Proposed

## Date
2026-02-24

## Context

Users browsing summaries need efficient ways to:
1. Navigate between summaries chronologically (next/previous)
2. Search for specific content, keywords, or participants
3. Find related summaries across time periods

Currently, users must manually browse the list or use basic date filtering. This becomes cumbersome with large archives spanning months of activity.

## Decision

Implement comprehensive navigation and search capabilities for summaries.

### 1. Chronological Navigation

Add next/previous navigation to summary detail views:

```typescript
interface SummaryNavigation {
  previous_id: string | null;
  previous_date: string | null;
  next_id: string | null;
  next_date: string | null;
}
```

**API Changes:**

```
GET /guilds/{guild_id}/stored-summaries/{summary_id}
Response includes:
{
  ...existing fields...
  "navigation": {
    "previous_id": "sum_abc123",
    "previous_date": "2026-01-21",
    "next_id": "sum_def456",
    "next_date": "2026-01-23"
  }
}
```

**Implementation:**
- Query for summaries with `created_at < current` (previous) and `created_at > current` (next)
- Filter by same guild_id
- Optionally filter by same source (archive vs realtime) or channel
- Order by created_at to get adjacent summaries

### 2. Full-Text Search

Add search endpoint for finding summaries by content:

```
GET /guilds/{guild_id}/stored-summaries/search
Query params:
  - q: Search query (required)
  - fields: Comma-separated fields to search (default: all)
    - summary_text
    - key_points
    - action_items
    - participants
    - technical_terms
  - source: Filter by source (archive, realtime, scheduled, manual)
  - date_from: Start date filter
  - date_to: End date filter
  - limit: Results per page (default: 20)
  - offset: Pagination offset
```

**Response:**
```json
{
  "query": "authentication bug",
  "total": 5,
  "items": [
    {
      "id": "sum_abc123",
      "title": "Daily Summary - Jan 22",
      "archive_period": "2026-01-22",
      "relevance_score": 0.95,
      "highlights": [
        {
          "field": "summary_text",
          "snippet": "...discussed the **authentication bug** in the login flow..."
        },
        {
          "field": "action_items",
          "snippet": "Fix **authentication bug** before release"
        }
      ],
      "created_at": "2026-01-22T00:00:00Z"
    }
  ]
}
```

**Implementation Options:**

#### Option A: SQLite FTS5 (Recommended for MVP)
- Use SQLite's Full-Text Search extension
- Create virtual FTS table mirroring summary content
- Supports ranking, snippets, and boolean queries
- Low operational complexity

```sql
CREATE VIRTUAL TABLE summary_search USING fts5(
  summary_id,
  summary_text,
  key_points,
  action_items,
  participants,
  technical_terms,
  content='stored_summaries',
  content_rowid='rowid'
);
```

#### Option B: In-Memory Search
- Load summary text into memory
- Use simple substring/regex matching
- Good for small datasets (<10k summaries)
- No additional dependencies

#### Option C: External Search Service
- Elasticsearch, Meilisearch, or Typesense
- Best for large-scale deployments
- Adds operational complexity

### 3. Participant Search

Find all summaries mentioning specific participants:

```
GET /guilds/{guild_id}/stored-summaries/by-participant
Query params:
  - user_id: Discord user ID (optional)
  - display_name: Partial name match (optional)
  - min_mentions: Minimum mention count (default: 1)
  - date_from, date_to: Date range
  - limit, offset: Pagination
```

**Response:**
```json
{
  "participant": {
    "user_id": "123456789",
    "display_name": "Alice",
    "total_summaries": 42,
    "total_messages": 1250
  },
  "summaries": [
    {
      "id": "sum_abc123",
      "title": "Daily Summary - Jan 22",
      "message_count": 15,
      "key_contributions": ["Led discussion on architecture", "Proposed caching solution"]
    }
  ]
}
```

### 4. Keyboard Navigation

Add keyboard shortcuts in the UI:
- `j` / `k` or `↓` / `↑`: Navigate between summaries in list
- `←` / `→`: Previous/next summary in detail view
- `/`: Focus search input
- `Esc`: Close detail view / clear search

### 5. URL Deep Linking

Support direct links to:
- Specific summaries: `/summaries/{guild_id}/{summary_id}`
- Search results: `/summaries/{guild_id}?q=authentication&source=archive`
- Date range: `/summaries/{guild_id}?from=2026-01-01&to=2026-01-31`
- Participant view: `/summaries/{guild_id}/participant/{user_id}`

## Database Changes

### Migration: Add FTS Table

```sql
-- Migration 020: Add full-text search
CREATE VIRTUAL TABLE IF NOT EXISTS summary_fts USING fts5(
  summary_text,
  key_points,
  action_items_text,
  participants_text,
  technical_terms_text,
  content='stored_summaries'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER summary_fts_insert AFTER INSERT ON stored_summaries BEGIN
  INSERT INTO summary_fts(rowid, summary_text, key_points, ...)
  SELECT NEW.rowid, json_extract(NEW.summary_json, '$.summary_text'), ...;
END;

CREATE TRIGGER summary_fts_delete AFTER DELETE ON stored_summaries BEGIN
  INSERT INTO summary_fts(summary_fts, rowid, summary_text, ...)
  VALUES('delete', OLD.rowid, ...);
END;

CREATE TRIGGER summary_fts_update AFTER UPDATE ON stored_summaries BEGIN
  INSERT INTO summary_fts(summary_fts, rowid, summary_text, ...)
  VALUES('delete', OLD.rowid, ...);
  INSERT INTO summary_fts(rowid, summary_text, ...)
  SELECT NEW.rowid, ...;
END;
```

### Index for Navigation

```sql
-- Index for efficient prev/next queries
CREATE INDEX IF NOT EXISTS idx_stored_summaries_nav
ON stored_summaries(guild_id, created_at);
```

## API Summary

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/stored-summaries/{id}` | GET | Detail with navigation |
| `/stored-summaries/search` | GET | Full-text search |
| `/stored-summaries/by-participant` | GET | Participant search |
| `/stored-summaries/participants` | GET | List all participants |

## Implementation Phases

### Phase 1: Navigation (MVP)
- Add prev/next to detail response
- Add navigation index
- UI prev/next buttons

### Phase 2: Basic Search
- SQLite FTS5 setup
- Search endpoint
- UI search input with results

### Phase 3: Advanced Features
- Participant search
- Keyboard navigation
- URL deep linking
- Search highlighting

## Alternatives Considered

1. **Client-side search only**: Fast but limited to loaded data
2. **Vector search with embeddings**: Semantic search but adds complexity
3. **External search service**: Powerful but operational overhead

## Consequences

### Positive
- Users can quickly find relevant summaries
- Chronological browsing becomes seamless
- Participants can track their contributions
- Deep linking enables sharing specific summaries

### Negative
- FTS table adds ~20% storage overhead
- Search indexing adds write latency
- Need to backfill existing summaries into FTS

### Risks
- FTS query performance on large datasets
- Keeping FTS in sync with main table

## References

- [SQLite FTS5 Documentation](https://www.sqlite.org/fts5.html)
- ADR-005: Stored Summaries
- ADR-008: Unified Summary Experience
- ADR-019: Database-Primary Archive Storage
