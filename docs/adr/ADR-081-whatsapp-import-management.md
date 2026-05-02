# ADR-081: WhatsApp Import Management

## Status
Proposed

## Context

WhatsApp chat exports present unique challenges compared to Discord/Slack integrations:

1. **Manual file-based imports** - No API integration; users export `.txt` files from their phones
2. **Per-exporter contact names** - Each person's export uses their contact book names
3. **PII in exports** - Phone numbers may appear directly in exports
4. **Multiple importers** - Different people may import overlapping time periods
5. **No central identity** - Same person appears differently in different exports

### The Contact Name Problem

When Alice exports a WhatsApp group chat:
```
[01/05/2026, 09:15:32] Rob Smith: Good morning everyone
[01/05/2026, 09:16:45] You: Hey Rob!
[01/05/2026, 09:17:02] +1 555 123 4567: I'll join later
```

When Bob exports the same chat:
```
[01/05/2026, 09:15:32] Robert: Good morning everyone
[01/05/2026, 09:16:45] Alice: Hey Rob!
[01/05/2026, 09:17:02] Dad: I'll join later
```

The same person appears as:
- "Rob Smith", "Robert", "Robbie" (different contact book entries)
- "You" (the exporter themselves)
- "+1 555 123 4567" (not in contact book)
- "Dad", "Boss", "My Husband" (relationship-based names)

### Current State

- Imports tracked in `import-manifest.json` (file-based archive)
- Batches stored in `ingest_batches` table (database)
- Phone numbers anonymized to pseudonyms (ADR-028): "Swift Penguin 4827"
- Message fingerprint: `timestamp|sender|content[:50]`
- **No tracking of who imported**
- **No UI for managing imports**
- **No identity resolution across exports**
- **No way to view or delete imports**

## Decision

### 1. Import Tracking Model

Introduce comprehensive import tracking with user attribution:

```python
@dataclass
class WhatsAppImport:
    id: str  # UUID: imp_{12-char hex}
    guild_id: str  # Associated Discord guild
    chat_id: str  # WhatsApp JID or group identifier
    chat_name: str  # Display name of chat

    # Import metadata
    imported_by: str  # User ID who uploaded
    imported_at: datetime
    original_filename: str
    file_hash: str  # SHA-256 of original file (for duplicate detection)
    file_size_bytes: int
    format: str  # "whatsapp_txt", "whatsapp_txt_android", "reader_bot_json"

    # Content summary
    date_range_start: datetime
    date_range_end: datetime
    message_count: int
    participant_count: int

    # Processing status
    status: str  # "pending", "processing", "completed", "failed"
    error_message: Optional[str]
    processed_at: Optional[datetime]

    # Anonymization
    anonymization_version: int
    participants_json: str  # JSON: list of {pseudonym, hash, message_count, aliases}

    # Soft delete
    deleted_at: Optional[datetime]
    deleted_by: Optional[str]
```

### 2. Identity Resolution System

Create a participant identity system that handles name variations:

```python
@dataclass
class WhatsAppParticipant:
    id: str  # UUID: part_{12-char hex}
    guild_id: str
    chat_id: str

    # Canonical identity
    phone_hash: Optional[str]  # HMAC-SHA256 hash (when phone known)
    pseudonym: str  # "Swift Penguin 4827"

    # Known aliases (display names from various exports)
    aliases: List[str]  # ["Rob Smith", "Robert", "Robbie"]
    preferred_name: Optional[str]  # User-set preferred display name

    # Attribution
    first_seen_import_id: str
    message_count: int

    created_at: datetime
    updated_at: datetime
```

#### Identity Resolution Algorithm

```
For each message in import:
  sender_name = raw sender from export

  IF sender_name matches phone pattern:
    phone_hash = hash(normalize(sender_name))
    participant = find_or_create_by_phone_hash(phone_hash)
  ELSE IF sender_name == "You":
    # Map to importer's identity (if known)
    participant = resolve_importer_identity(import.imported_by)
  ELSE:
    # Contact name - try fuzzy match to existing aliases
    participant = fuzzy_match_alias(sender_name) OR create_new_participant()
    participant.aliases.append(sender_name)

  # Create consistent message fingerprint using canonical identity
  fingerprint = f"{timestamp}|{participant.id}|{content[:50]}"
```

#### Fuzzy Alias Matching

For non-phone sender names, attempt matching:

1. **Exact match** - "Rob Smith" already in aliases
2. **Case-insensitive** - "ROB SMITH" matches "Rob Smith"
3. **Normalized** - Remove accents, punctuation: "Róbert" matches "Robert"
4. **Substring** - "Rob" could match "Robert Smith" (with low confidence)

Matches below a confidence threshold flagged for manual review.

### 3. De-duplication Strategy

#### Import-Level Deduplication

Prevent re-importing the same file:

```python
def check_duplicate_import(file_content: bytes, guild_id: str, chat_id: str) -> Optional[str]:
    file_hash = hashlib.sha256(file_content).hexdigest()
    existing = db.query("""
        SELECT id FROM whatsapp_imports
        WHERE file_hash = ? AND guild_id = ? AND chat_id = ?
        AND deleted_at IS NULL
    """, file_hash, guild_id, chat_id)
    return existing.id if existing else None
```

UI response: "This file was already imported on {date} by {user}. Import anyway?"

#### Message-Level Deduplication

Using identity-resolved fingerprints:

```python
def fingerprint_message(msg: Message, participant: WhatsAppParticipant) -> str:
    # Use canonical participant ID instead of raw sender name
    timestamp_str = msg.timestamp.strftime("%Y%m%d%H%M%S")
    content_hash = hashlib.md5(msg.content.encode()).hexdigest()[:8]
    return f"{timestamp_str}|{participant.id}|{content_hash}"
```

When processing an import:
1. Build fingerprint set from new messages
2. Query existing fingerprints for date range
3. Skip messages with matching fingerprints
4. Report: "147 new messages added, 53 duplicates skipped"

### 4. Database Schema

```sql
-- Migration: 081_whatsapp_import_management.sql

-- WhatsApp imports (replaces import-manifest.json)
CREATE TABLE whatsapp_imports (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    chat_name TEXT NOT NULL,

    -- Attribution
    imported_by TEXT NOT NULL,  -- User ID
    imported_at TEXT NOT NULL,

    -- File metadata
    original_filename TEXT NOT NULL,
    file_hash TEXT NOT NULL,  -- SHA-256
    file_size_bytes INTEGER NOT NULL,
    format TEXT NOT NULL,

    -- Content
    date_range_start TEXT NOT NULL,
    date_range_end TEXT NOT NULL,
    message_count INTEGER NOT NULL,
    participant_count INTEGER NOT NULL,

    -- Processing
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    processed_at TEXT,

    -- Anonymization
    anonymization_version INTEGER DEFAULT 1,
    participants_json TEXT,  -- JSON array

    -- Soft delete
    deleted_at TEXT,
    deleted_by TEXT,

    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_wa_imports_guild_chat ON whatsapp_imports(guild_id, chat_id);
CREATE INDEX idx_wa_imports_hash ON whatsapp_imports(file_hash);
CREATE INDEX idx_wa_imports_date ON whatsapp_imports(imported_at);
CREATE INDEX idx_wa_imports_status ON whatsapp_imports(status);

-- WhatsApp participant identities
CREATE TABLE whatsapp_participants (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,

    -- Identity
    phone_hash TEXT,  -- HMAC hash of normalized phone (nullable)
    pseudonym TEXT NOT NULL,  -- "Swift Penguin 4827"

    -- Aliases (JSON array)
    aliases_json TEXT DEFAULT '[]',
    preferred_name TEXT,

    -- Statistics
    first_seen_import_id TEXT REFERENCES whatsapp_imports(id),
    message_count INTEGER DEFAULT 0,

    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_wa_participants_guild_chat ON whatsapp_participants(guild_id, chat_id);
CREATE UNIQUE INDEX idx_wa_participants_phone ON whatsapp_participants(guild_id, chat_id, phone_hash)
    WHERE phone_hash IS NOT NULL;

-- Identity merge history (for audit trail)
CREATE TABLE whatsapp_identity_merges (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,

    -- The merge
    source_participant_id TEXT NOT NULL,
    target_participant_id TEXT NOT NULL,

    -- Attribution
    merged_by TEXT NOT NULL,  -- User ID
    merged_at TEXT NOT NULL,
    reason TEXT,  -- "manual", "phone_match", "fuzzy_alias"

    -- Reversibility
    reversed_at TEXT,
    reversed_by TEXT
);

-- Message fingerprints for deduplication
CREATE TABLE whatsapp_message_fingerprints (
    fingerprint TEXT PRIMARY KEY,
    import_id TEXT NOT NULL REFERENCES whatsapp_imports(id) ON DELETE CASCADE,
    participant_id TEXT NOT NULL REFERENCES whatsapp_participants(id),
    message_timestamp TEXT NOT NULL,

    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_wa_fingerprints_import ON whatsapp_message_fingerprints(import_id);
CREATE INDEX idx_wa_fingerprints_time ON whatsapp_message_fingerprints(message_timestamp);
```

### 5. API Endpoints

```
# Import management
POST   /guilds/{guild_id}/whatsapp/imports          # Upload new import
GET    /guilds/{guild_id}/whatsapp/imports          # List all imports
GET    /guilds/{guild_id}/whatsapp/imports/{id}     # Import details
DELETE /guilds/{guild_id}/whatsapp/imports/{id}     # Soft delete import
GET    /guilds/{guild_id}/whatsapp/imports/{id}/messages  # View sanitized messages

# Participant management
GET    /guilds/{guild_id}/whatsapp/participants     # List participants
GET    /guilds/{guild_id}/whatsapp/participants/{id}  # Participant details
PATCH  /guilds/{guild_id}/whatsapp/participants/{id}  # Update preferred name
POST   /guilds/{guild_id}/whatsapp/participants/merge  # Merge two identities

# Chat overview
GET    /guilds/{guild_id}/whatsapp/chats            # List chats with import counts
GET    /guilds/{guild_id}/whatsapp/chats/{chat_id}  # Chat details & coverage
```

#### Upload Import Request

```typescript
interface UploadImportRequest {
  file: File;  // .txt or .json
  chat_id?: string;  // Optional, auto-detected if possible
  chat_name?: string;  // Display name
}

interface UploadImportResponse {
  import_id: string;
  status: "processing" | "completed" | "duplicate_warning";
  message_count: number;
  participant_count: number;
  date_range: { start: string; end: string };
  duplicate_of?: string;  // If duplicate detected
  new_messages?: number;  // After deduplication
  skipped_messages?: number;
}
```

#### List Imports Response

```typescript
interface WhatsAppImportSummary {
  id: string;
  chat_name: string;
  imported_by: {
    id: string;
    name: string;
    avatar?: string;
  };
  imported_at: string;
  original_filename: string;
  date_range: { start: string; end: string };
  message_count: number;
  participant_count: number;
  status: "pending" | "processing" | "completed" | "failed";
}

interface ListImportsResponse {
  imports: WhatsAppImportSummary[];
  total: number;
  chats: Array<{
    chat_id: string;
    chat_name: string;
    import_count: number;
    total_messages: number;
    coverage: { earliest: string; latest: string };
  }>;
}
```

#### View Messages Response (Sanitized)

```typescript
interface SanitizedMessage {
  id: string;
  timestamp: string;
  sender: string;  // Pseudonym only, never phone/real name
  content: string;  // Phone numbers in content also anonymized
  is_system: boolean;
  has_attachment: boolean;
  attachment_type?: string;  // "image", "audio", "document"
}

interface ViewMessagesResponse {
  messages: SanitizedMessage[];
  pagination: { page: number; per_page: number; total: number };
  participants: Array<{
    pseudonym: string;
    message_count: number;
    // Note: aliases NOT exposed in API response
  }>;
}
```

### 6. UI Components

#### Import Management Page

**Route**: `/guilds/{guild_id}/whatsapp/imports`

```
+------------------------------------------------------------------+
| WhatsApp Imports                                         [Upload] |
+------------------------------------------------------------------+
|                                                                   |
| Chats:  [All Chats ▾]  Status:  [All ▾]  Date:  [Last 30 days ▾] |
|                                                                   |
+------------------------------------------------------------------+
| Chat: "Project Team"              3 imports    1,234 messages    |
|   Coverage: Jan 1 - Apr 30, 2026  (gap: Feb 15-20)               |
+------------------------------------------------------------------+
|                                                                   |
| ┌─────────────────────────────────────────────────────────────┐  |
| │ project-team-export.txt                                     │  |
| │ Imported by: Alice Smith  •  May 1, 2026                    │  |
| │ 456 messages  •  8 participants  •  Mar 1 - Apr 30          │  |
| │ Status: ✓ Completed                                         │  |
| │                                        [View] [Delete]      │  |
| └─────────────────────────────────────────────────────────────┘  |
|                                                                   |
| ┌─────────────────────────────────────────────────────────────┐  |
| │ WhatsApp Chat with Project Team.txt                         │  |
| │ Imported by: Bob Johnson  •  Mar 15, 2026                   │  |
| │ 389 messages (47 duplicates skipped)  •  8 participants     │  |
| │ Jan 1 - Mar 14                                              │  |
| │ Status: ✓ Completed                                         │  |
| │                                        [View] [Delete]      │  |
| └─────────────────────────────────────────────────────────────┘  |
|                                                                   |
+------------------------------------------------------------------+
```

#### Import Detail View

**Route**: `/guilds/{guild_id}/whatsapp/imports/{import_id}`

```
+------------------------------------------------------------------+
| ← Back to Imports                                                 |
|                                                                   |
| project-team-export.txt                              [Delete]     |
+------------------------------------------------------------------+
| Imported by:     Alice Smith                                      |
| Import date:     May 1, 2026 at 2:34 PM                          |
| File size:       127 KB                                           |
| Format:          WhatsApp iOS Export                              |
|                                                                   |
| Date range:      March 1 - April 30, 2026                        |
| Messages:        456 total (12 duplicates skipped)               |
| Participants:    8                                                |
+------------------------------------------------------------------+
|                                                                   |
| Tabs: [Messages] [Participants] [Processing Log]                  |
|                                                                   |
+------------------------------------------------------------------+
| Messages (sanitized view)                    Search: [________]   |
|                                                                   |
| Mar 1, 2026                                                       |
| ┌─────────────────────────────────────────────────────────────┐  |
| │ Swift Penguin 4827                              9:15 AM     │  |
| │ Good morning everyone! Ready for the standup?               │  |
| └─────────────────────────────────────────────────────────────┘  |
| ┌─────────────────────────────────────────────────────────────┐  |
| │ Brave Fox 0142                                  9:16 AM     │  |
| │ Yes, let me share my screen                                 │  |
| └─────────────────────────────────────────────────────────────┘  |
|                                                                   |
| [Load more...]                                                    |
+------------------------------------------------------------------+
```

#### Participants Tab

```
+------------------------------------------------------------------+
| Participants                                                      |
+------------------------------------------------------------------+
|                                                                   |
| ┌─────────────────────────────────────────────────────────────┐  |
| │ Swift Penguin 4827                        142 messages      │  |
| │ Known aliases: "Rob Smith", "Robert"      [Set Display ▾]   │  |
| └─────────────────────────────────────────────────────────────┘  |
|                                                                   |
| ┌─────────────────────────────────────────────────────────────┐  |
| │ Brave Fox 0142                            98 messages       │  |
| │ Known aliases: "Alice"                    [Set Display ▾]   │  |
| └─────────────────────────────────────────────────────────────┘  |
|                                                                   |
| ┌─────────────────────────────────────────────────────────────┐  |
| │ Cosmic Falcon 4552                        76 messages       │  |
| │ Known aliases: "Dad", "+1 555 ***"        [Set Display ▾]   │  |
| │ ⚠️ Possible duplicate of Calm Tiger 1234  [Merge] [Ignore] │  |
| └─────────────────────────────────────────────────────────────┘  |
|                                                                   |
+------------------------------------------------------------------+
```

### 7. PII Handling

#### What's Stored vs. Displayed

| Data | Storage | API Response | UI Display |
|------|---------|--------------|------------|
| Phone number | HMAC hash only | Never | Never |
| Contact name | In `aliases_json` | Never | Never (admin only) |
| Pseudonym | Plain text | Yes | Yes |
| Message content | Anonymized | Yes | Yes |
| Importer identity | User ID | User info | Avatar + name |

#### Viewing Permissions

- **Any authorized user**: Can see sanitized messages (pseudonyms only)
- **Import owner**: Can see their own import details, delete their imports
- **Guild admin**: Can see all imports, delete any import, manage participants
- **System admin**: Can see aliases for debugging (not exposed in UI)

#### Delete Behavior

Soft delete with cascading:
1. Mark import as `deleted_at = now(), deleted_by = user_id`
2. Messages remain in `ingest_messages` (for deduplication reference)
3. Fingerprints remain (to prevent re-adding duplicates)
4. Deleted imports hidden from UI but queryable by admins

Hard delete (admin only):
1. Remove import record
2. Cascade delete fingerprints
3. Messages in `ingest_messages` remain but orphaned
4. Recalculate participant message counts

### 8. "You" Resolution

When an exporter appears as "You" in their export:

```python
def resolve_you_identity(import_record: WhatsAppImport) -> Optional[str]:
    """
    Attempt to identify who "You" is in this export.

    Strategies:
    1. If importer has WhatsApp linked, use their phone hash
    2. If importer previously appeared in other imports, use that identity
    3. Create new participant with alias "You (imported by {username})"
    """
    importer_user = get_user(import_record.imported_by)

    # Strategy 1: Linked WhatsApp account
    if importer_user.whatsapp_phone_hash:
        return find_participant_by_phone_hash(importer_user.whatsapp_phone_hash)

    # Strategy 2: Previous appearance in same chat
    previous_imports = get_imports_by_user_for_chat(
        import_record.imported_by,
        import_record.chat_id
    )
    for prev in previous_imports:
        # Look for non-"You" identity from other exports
        if prev.importer_participant_id:
            return prev.importer_participant_id

    # Strategy 3: Create new with attribution
    return create_participant(
        aliases=[f"You (via {importer_user.display_name})"],
        pseudonym=generate_pseudonym()
    )
```

### 9. Coverage Tracking

Track what time periods are covered by imports:

```python
def calculate_coverage(guild_id: str, chat_id: str) -> CoverageReport:
    """
    Analyze import coverage to identify gaps.
    """
    imports = get_imports(guild_id, chat_id, status="completed")

    # Build timeline of covered periods
    periods = [(i.date_range_start, i.date_range_end) for i in imports]
    merged = merge_overlapping_periods(periods)

    # Identify gaps
    gaps = []
    for i in range(len(merged) - 1):
        gap_start = merged[i][1]
        gap_end = merged[i + 1][0]
        if gap_end - gap_start > timedelta(days=1):
            gaps.append({
                "start": gap_start,
                "end": gap_end,
                "days": (gap_end - gap_start).days
            })

    return CoverageReport(
        earliest=merged[0][0] if merged else None,
        latest=merged[-1][1] if merged else None,
        total_days=sum((p[1] - p[0]).days for p in merged),
        gaps=gaps,
        import_count=len(imports)
    )
```

UI displays coverage as a timeline visualization with gaps highlighted.

## Consequences

### Positive

1. **Full import visibility** - Users can see all imports, who imported, and when
2. **Accountable imports** - Clear attribution prevents anonymous data dumps
3. **Better deduplication** - Identity resolution improves cross-import matching
4. **PII protection** - Sanitized views prevent accidental exposure
5. **Manageable data** - Soft delete allows cleanup without data loss
6. **Coverage awareness** - Users know what periods are missing

### Negative

1. **Complexity** - Identity resolution adds significant complexity
2. **Storage overhead** - Fingerprints and participant tables add storage
3. **Manual work** - Fuzzy matches require human review
4. **Import time** - Processing includes identity resolution, slower imports

### Neutral

1. **Migration needed** - Existing imports need backfill to new schema
2. **UX learning** - Users need to understand pseudonym system
3. **Admin burden** - Someone needs to review merge suggestions

## Implementation Plan

### Phase 1: Import Tracking (Week 1)
- [ ] Create migration `081_whatsapp_import_management.sql`
- [ ] Add `imported_by` to import flow
- [ ] Create `/whatsapp/imports` API endpoints
- [ ] Build basic import list UI

### Phase 2: Sanitized Viewing (Week 2)
- [ ] Add message viewing endpoint with anonymization
- [ ] Build import detail view UI
- [ ] Add soft delete functionality
- [ ] Implement file hash duplicate detection

### Phase 3: Identity Resolution (Week 3)
- [ ] Create participant table and repository
- [ ] Implement phone-based identity matching
- [ ] Add fuzzy alias matching
- [ ] Update fingerprinting to use participant IDs

### Phase 4: Participant Management (Week 4)
- [ ] Build participant list UI
- [ ] Add merge/split functionality
- [ ] Implement "You" resolution
- [ ] Add preferred name setting

### Phase 5: Coverage & Polish (Week 5)
- [ ] Implement coverage calculation
- [ ] Add coverage visualization
- [ ] Migrate existing imports
- [ ] Performance optimization

## Alternatives Considered

### 1. Require Phone Number Export Format

**Rejected**: Not all WhatsApp versions/regions export phone numbers consistently. Would exclude many users.

### 2. Let Users Manually Tag All Messages

**Rejected**: Too labor-intensive. Average group has thousands of messages.

### 3. Use ML for Name Matching

**Considered for future**: Could use embeddings to match "Robert" to "Rob" with higher confidence. Added complexity not justified for MVP.

### 4. No Identity Resolution

**Rejected**: Defeats purpose of cross-import deduplication. Same person counted multiple times in stats.

## References

- ADR-002: Multi-source ingest architecture
- ADR-028: Phone number anonymization
- WhatsApp export format documentation
- Current implementation: `src/archive/importers/whatsapp.py`
