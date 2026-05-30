# ADR-112: WhatsApp Coverage Gap Awareness

## Status
Proposed

## Date
2026-05-30

## Context

When users export WhatsApp chats, the exported data only contains messages from the period when:
1. The exporting user was a member of the group
2. The chat existed on their device (not deleted/restored)
3. WhatsApp's message retention hasn't pruned older messages

This creates a fundamental gap between:
- **Chat Creation Date**: When the group was originally created
- **Export Coverage**: The actual message date range in the export file

### Example Scenario

```
Timeline:
├── 2020-01-15: Group "Agentic Tribe" created by Alice
├── 2020-01-15 - 2022-06-01: Messages exist (Alice, Bob present)
├── 2022-06-01: Carol joins the group
├── 2022-06-01 - 2024-12-31: Messages exist (Carol present)
└── 2024-12-31: Carol exports chat

Carol's Export Contains:
├── date_range_start: 2022-06-01  (when Carol joined)
├── date_range_end: 2024-12-31
├── message_count: 5000
└── MISSING: 2020-01-15 to 2022-05-31 (Alice and Bob's messages)
```

### Current System Behavior

The existing system tracks coverage per chat:
- `date_range_start`: Earliest message in imports
- `date_range_end`: Latest message in imports
- `import_count`: Number of import files
- `gaps`: Currently empty (TODO in code)

However, the system has no awareness of:
1. When the chat was actually created
2. When each user joined the chat
3. What date ranges are "missing" vs "don't exist"

### Affected Processes

| Process | Impact | Severity |
|---------|--------|----------|
| Archive Generation | Requests dates with no data, gets "No messages found" | Medium |
| Retrospective Summaries | Shows gaps as empty periods without explanation | High |
| Coverage Visualization | Can't distinguish "no messages" vs "not imported" | High |
| Summary Quality | Missing context from earlier discussions | Medium |
| Search | Can't find discussions that happened before export | Medium |

## Decision

Implement coverage gap awareness through four mechanisms:

### 1. Join Date Detection

Extract join dates from WhatsApp system messages during import:

```python
JOIN_PATTERNS = [
    r"(\d{1,2}/\d{1,2}/\d{2,4}).*added you",
    r"(\d{1,2}/\d{1,2}/\d{2,4}).*You were added",
    r"(\d{1,2}/\d{1,2}/\d{2,4}).*joined using this group's invite link",
    r"(\d{1,2}/\d{1,2}/\d{2,4}).*created group",
]
```

Store as metadata:
```sql
ALTER TABLE whatsapp_imports ADD COLUMN detected_join_date TEXT;
ALTER TABLE whatsapp_imports ADD COLUMN detected_events_json TEXT;
-- Events: group_created, user_joined, user_added, etc.
```

### 2. Coverage Gap Calculation

Implement the TODO in `ChatCoverage.gaps`:

```python
@dataclass
class CoverageGap:
    start: date
    end: date
    gap_type: Literal["before_join", "between_imports", "after_last"]
    days: int
    can_fill: bool  # True if another user might have this data

def calculate_gaps(self, imports: List[WhatsAppImport]) -> List[CoverageGap]:
    """Calculate gaps in coverage from multiple imports."""
    gaps = []

    # Sort imports by date range
    sorted_imports = sorted(imports, key=lambda i: i.date_range_start)

    # Gap before first import (if join date detected)
    if self.detected_join_date and sorted_imports:
        first_msg = sorted_imports[0].date_range_start
        if first_msg > self.detected_join_date:
            gaps.append(CoverageGap(
                start=self.detected_join_date,
                end=first_msg - timedelta(days=1),
                gap_type="before_join",
                can_fill=True  # Another user might have this
            ))

    # Gaps between imports
    for i in range(len(sorted_imports) - 1):
        current_end = sorted_imports[i].date_range_end
        next_start = sorted_imports[i + 1].date_range_start
        if next_start > current_end + timedelta(days=1):
            gaps.append(CoverageGap(
                start=current_end + timedelta(days=1),
                end=next_start - timedelta(days=1),
                gap_type="between_imports",
                can_fill=True
            ))

    return gaps
```

### 3. Coverage Visualization

Add coverage timeline to the UI:

```
Chat: Agentic Tribe
Coverage Timeline:
├─ ░░░░░░░░░░░░ Gap: Jan 2020 - May 2022 (29 months)
│               ⚠️ Earlier messages may exist - invite others to import
├─ ████████████ Carol's Import: Jun 2022 - Dec 2024 (5000 msgs)
└─ ░░░░░░░░░░░░ Gap: Jan 2025 - Present
                📤 Export and import recent messages

Legend: █ Covered  ░ Gap (fillable)  ▒ Gap (unfillable)
```

API response enhancement:
```json
{
  "chat_id": "agentic-tribe-a7a830",
  "coverage": {
    "earliest": "2022-06-01",
    "latest": "2024-12-31",
    "total_messages": 5000,
    "detected_join_date": "2022-06-01",
    "gaps": [
      {
        "start": "2020-01-15",
        "end": "2022-05-31",
        "type": "before_join",
        "days": 868,
        "can_fill": true,
        "fill_hint": "Ask group members who joined before June 2022 to export"
      }
    ],
    "coverage_percent": 48.5
  }
}
```

### 4. Collaborative Gap Filling

Encourage users to fill gaps through:

#### 4.1 Notifications
When generating summaries for dates with gaps:
```
⚠️ Coverage Gap Detected

Your import covers Jun 2022 - Dec 2024, but you requested summaries from Jan 2020.

Options:
1. Generate summaries for covered period only
2. Invite other members to import their chat history
3. Continue anyway (gaps will show as "No messages")

[Share Import Link] [Continue with Gaps] [Adjust Date Range]
```

#### 4.2 Member Import Tracking

Track which guild members have imported which date ranges:

```sql
CREATE TABLE whatsapp_coverage_contributors (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    import_id TEXT NOT NULL,
    date_range_start DATE NOT NULL,
    date_range_end DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_coverage_chat ON whatsapp_coverage_contributors(guild_id, chat_id);
```

API endpoint to show who can help:
```
GET /api/v1/whatsapp/chats/{chat_id}/coverage/contributors

Response:
{
  "chat_id": "agentic-tribe-a7a830",
  "contributors": [
    {"user_id": "carol", "covers": "2022-06-01 to 2024-12-31"},
    {"user_id": "bob", "covers": null, "status": "not_imported"}
  ],
  "suggested_contributors": [
    {"user_id": "alice", "reason": "Likely has earlier messages", "invite_sent": false}
  ]
}
```

#### 4.3 Import Invitation System

Add ability to request imports from other members:

```
POST /api/v1/whatsapp/chats/{chat_id}/request-import

{
  "target_user_ids": ["alice", "bob"],
  "date_range_needed": {"start": "2020-01-01", "end": "2022-05-31"},
  "message": "Help fill in the history before June 2022!"
}
```

Sends Discord DM or in-app notification with instructions.

## Implementation Plan

### Phase 1: Detection (Low Effort)
1. Parse system messages during import to extract join dates
2. Store `detected_join_date` and events in database
3. Update import response to include detected metadata

### Phase 2: Gap Calculation (Medium Effort)
1. Implement `calculate_gaps()` in repository
2. Return gaps in coverage API response
3. Add gap warnings to summary generation

### Phase 3: Visualization (Medium Effort)
1. Add coverage timeline component to frontend
2. Show gaps with fill hints
3. Add coverage warnings to Archive page

### Phase 4: Collaboration (Higher Effort)
1. Implement contributor tracking
2. Add import request/invitation system
3. Dashboard showing org-wide coverage gaps

## Consequences

### Positive
- Users understand why some dates have no data
- Clear path to fill coverage gaps
- Better summary quality when gaps are filled
- Organizational awareness of data completeness

### Negative
- Complexity in tracking who has what
- Privacy consideration: revealing who has access to which chats
- Storage overhead for gap metadata

### Mitigations
- Gap contributor tracking is opt-in
- Only show "someone can fill this" not who specifically
- Minimal storage: just dates, not message content

## Related ADRs

- **ADR-028**: WhatsApp PII Anonymization
- **ADR-082**: Google Drive WhatsApp Uploads
- **ADR-111**: Auto-publish to Confluence (needs gap awareness)

## References

- WhatsApp Export Format Documentation
- Existing `ChatCoverage` model in `whatsapp_import_repository.py:665-729`
- System message patterns in `whatsapp.py:111-122`
