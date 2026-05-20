# ADR-098: Summary Scope Metadata and Filtering

## Status
Accepted

## Context

Users cannot easily understand or filter summaries by their generation scope:
- **Server-wide**: Combined summary across all channels
- **Per-category**: Summary of channels within a specific category
- **Single-channel**: Summary of one specific channel

### Current Issues

1. **Job descriptions lack context**: Job `job_8feceeec` doesn't show which category it was run for
2. **Summary metadata incomplete**: Category summaries (e.g., `sum_d615ba86d2a1`) don't reflect their scope in title or metadata
3. **No scope filtering**: Cannot filter summaries list by "show only category summaries" or "show only server-wide"
4. **"Skipped" validation**: When jobs report "15 skipped as already exist", we don't verify they actually exist in the database

## Decision

### 1. Add Scope Metadata to Summaries

**Database Schema** (`stored_summaries` table):
```sql
ALTER TABLE stored_summaries ADD COLUMN scope_type TEXT;  -- 'guild', 'category', 'channel'
ALTER TABLE stored_summaries ADD COLUMN category_id TEXT;
ALTER TABLE stored_summaries ADD COLUMN category_name TEXT;
```

**StoredSummary Model**:
```python
@dataclass
class StoredSummary:
    # ... existing fields ...
    scope_type: Optional[str] = None  # 'guild', 'category', 'channel'
    category_id: Optional[str] = None
    category_name: Optional[str] = None
```

### 2. Populate Scope on Summary Creation

When saving a summary, derive scope from `archive_source_key`:
- `discord:123456` → scope_type = 'guild'
- `discord:123456:category:789` → scope_type = 'category', category_id = '789'
- `discord:123456:channel:456` → scope_type = 'channel'

### 3. Include Scope in Summary Title

Auto-generate titles that reflect scope:
- Guild: "FRC 2609 - Beaverworx Weekly Summary (Jan 15-21)"
- Category: "Media & Marketing Category Summary (Jan 15-21)"
- Channel: "#announcements Summary (Jan 15-21)"

### 4. Add Scope Filtering API

**Endpoint**: `GET /api/v1/guilds/{id}/stored-summaries`

New query parameter:
```
scope_type: "guild" | "category" | "channel" | "all"
```

### 5. Enhance Job Metadata

**Job Response**:
```json
{
  "job_id": "job_8feceeec",
  "scope": {
    "type": "category",
    "category_id": "123456789",
    "category_name": "Media, Business & Marketing"
  },
  "progress": {
    "total": 20,
    "completed": 5,
    "skipped": 15,
    "skipped_verified": true  // NEW: verified summaries exist in DB
  }
}
```

### 6. Verify "Skipped" Summaries Exist

Before marking a period as "skipped (already exists)", verify:
1. Check lock file has `status: complete`
2. Query database for matching summary record
3. If lock says complete but DB has no record, regenerate instead of skip

## Implementation

### Phase 1: Database & Model
1. Add migration for new columns
2. Update StoredSummary model
3. Backfill existing summaries by parsing `archive_source_key`

### Phase 2: Creation & Display
1. Populate scope fields on summary save
2. Update title generation to include scope context
3. Include scope in API responses

### Phase 3: Filtering
1. Add `scope_type` query parameter to stored-summaries endpoint
2. Add frontend filter dropdown
3. Show scope badge on summary cards

### Phase 4: Job Improvements
1. Include scope info in job responses
2. Verify skipped summaries exist in DB
3. Log scope context in job progress messages

## API Changes

### Summary Response
```json
{
  "id": "sum_d615ba86d2a1",
  "title": "Media & Marketing Category Summary (May 15-21)",
  "scope_type": "category",
  "category_id": "987654321",
  "category_name": "Media, Business & Marketing",
  // ... existing fields ...
}
```

### Job Response
```json
{
  "job_id": "job_8feceeec",
  "scope_type": "category",
  "category_id": "987654321",
  "category_name": "Media, Business & Marketing",
  "progress": {
    "message": "5 generated, 15 skipped (verified in DB)"
  }
}
```

### Filter Parameters
```
GET /api/v1/guilds/{id}/stored-summaries?scope_type=category
GET /api/v1/guilds/{id}/stored-summaries?scope_type=channel
GET /api/v1/guilds/{id}/stored-summaries?scope_type=guild
```

## Frontend Changes

### Summary Card
Display scope badge:
- 🌐 Server-wide
- 📁 Category: {name}
- #️⃣ Channel: {name}

### Filter Dropdown
Add "Scope" filter with options:
- All scopes
- Server-wide only
- Category summaries
- Single channel

### Summary Detail View
Show scope metadata in the "Metadata" section.

## Consequences

### Positive
- Clear understanding of what each summary covers
- Easy filtering to find specific summary types
- Better job visibility showing what was generated
- More reliable skip verification

### Negative
- Requires database migration
- Backfill needed for existing summaries
- Additional storage for scope fields

## Migration Strategy

1. Add columns with NULL default
2. Run backfill script to parse `archive_source_key`
3. Update code to populate on new summaries
4. Make fields non-null after backfill complete
