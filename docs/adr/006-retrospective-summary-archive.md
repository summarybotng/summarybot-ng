# ADR-006: Retrospective Summary Archive — Historical Backfill with Versioned Prompts

**Status:** Proposed
**Date:** 2026-02-14
**Depends on:** ADR-002 (WhatsApp Integration), ADR-004 (Grounded References), ADR-005 (Delivery Destinations)
**Repository:** [summarybotng/summarybot-ng](https://github.com/summarybotng/summarybot-ng)

---

## 1. Problem Statement

Current summarization is forward-looking only: summaries are generated for recent activity or on a schedule going forward. This creates several gaps:

1. **No Historical Record** — Communities with months/years of chat history have no way to generate retrospective summaries for past periods.

2. **Missing Summary Gaps** — If the bot was offline, a schedule failed, or summarization wasn't configured, those periods have no summaries and no easy way to fill them.

3. **No Portable Archive** — Summaries exist only in platform messages or the database. There's no human-navigable, portable archive that can be stored externally (e.g., Google Drive) and browsed without the application.

4. **Configuration Drift** — When prompt templates or summary configurations change, there's no way to know which summaries were generated with which settings, making regeneration decisions difficult.

5. **Timezone Confusion** — Historical summaries need clear timezone labeling since "February 13, 2026" means different things in different timezones.

6. **Multi-Platform Fragmentation** — Organizations using Discord, WhatsApp, and Slack have no unified archive strategy across platforms.

7. **Cost Attribution** — When archiving multiple servers/groups, there's no way to track API costs per server for billing or budgeting purposes.

---

## 2. Decision

Implement a **Retrospective Summary Archive** system that:

1. **Generates summaries for arbitrary past time ranges** with configurable granularity (daily, weekly, monthly)
2. **Supports multiple source platforms** — Discord, WhatsApp, Slack, Telegram
3. **Stores summaries as Markdown files** in a structured, human-navigable folder hierarchy
4. **Maintains manifest metadata** tracking generation status, configuration versions, and backfill potential
5. **Supports flexible external sync** — servers can share a Google Drive or use separate drives
6. **Tracks costs per server** for attribution and budgeting
7. **Enables intelligent backfill** by identifying gaps and configuration changes

### 2.1 Archive Folder Structure

The archive uses a platform-agnostic structure that works for Discord servers, WhatsApp groups, Slack workspaces, etc.

```
summarybot-archive/
├── manifest.json                           # Global manifest with schema version
├── sources/
│   ├── discord/
│   │   └── {server_name}_{server_id}/
│   │       ├── server-manifest.json        # Server config, prompt checksums, costs
│   │       ├── channels/
│   │       │   └── {channel_name}_{channel_id}/
│   │       │       ├── channel-manifest.json
│   │       │       └── summaries/
│   │       │           └── {YYYY}/{MM}/
│   │       │               ├── {YYYY-MM-DD}_daily.md
│   │       │               └── {YYYY-MM-DD}_daily.meta.json
│   │       └── cross-channel/
│   │           └── {summary_name}/
│   │               └── summaries/{YYYY}/{MM}/...
│   ├── whatsapp/
│   │   └── {group_name}_{group_id}/
│   │       ├── group-manifest.json
│   │       └── summaries/
│   │           └── {YYYY}/{MM}/...
│   ├── slack/
│   │   └── {workspace_name}_{workspace_id}/
│   │       ├── workspace-manifest.json
│   │       └── channels/
│   │           └── {channel_name}_{channel_id}/...
│   └── telegram/
│       └── {chat_name}_{chat_id}/...
├── cost-ledger.json                        # Global cost tracking by source
└── .archive-config.json                    # User preferences, sync settings
```

### 2.2 Source Type Abstraction

```python
class SourceType(Enum):
    """Supported chat platforms."""
    DISCORD = "discord"
    WHATSAPP = "whatsapp"
    SLACK = "slack"
    TELEGRAM = "telegram"

@dataclass
class ArchiveSource:
    """Platform-agnostic source identifier."""
    source_type: SourceType
    server_id: str              # Guild ID, Group ID, Workspace ID, etc.
    server_name: str
    channel_id: Optional[str]   # None for single-channel sources (WhatsApp groups)
    channel_name: Optional[str]

    @property
    def folder_path(self) -> str:
        """Generate archive folder path for this source."""
        base = f"sources/{self.source_type.value}/{self.server_name}_{self.server_id}"
        if self.channel_id:
            return f"{base}/channels/{self.channel_name}_{self.channel_id}/summaries"
        return f"{base}/summaries"
```

### 2.3 File Naming Convention

| Granularity | Filename Pattern | Example |
|-------------|-----------------|---------|
| Daily | `{YYYY-MM-DD}_daily.md` | `2026-02-14_daily.md` |
| Weekly | `{YYYY}-W{WW}_weekly.md` | `2026-W07_weekly.md` |
| Monthly | `{YYYY-MM}_monthly.md` | `2026-02_monthly.md` |
| Custom Range | `{YYYY-MM-DD}_to_{YYYY-MM-DD}.md` | `2026-02-01_to_2026-02-14.md` |

All dates use **ISO 8601** format for universal sorting and clarity.

### 2.4 Timezone Handling

Each summary file includes explicit timezone information:

```markdown
# Daily Summary: Family Chat

**Platform:** WhatsApp
**Group:** Family Chat
**Date:** 2026-02-14 (Friday)
**Timezone:** America/New_York (UTC-5)
**Period:** 2026-02-14 00:00 to 2026-02-14 23:59 (America/New_York)
**Messages:** 47 from 8 participants

---

## Key Points
...
```

The archive supports generating summaries in different timezones:
- **Server/group timezone**: Default, based on server/group settings
- **User timezone**: Override for personal archives
- **UTC**: Canonical reference for cross-timezone consistency

---

## 3. Data Models

### 3.1 Archive Manifest (Global)

```json
{
  "schema_version": "1.0.0",
  "created_at": "2026-02-14T12:00:00Z",
  "last_updated": "2026-02-14T15:30:00Z",
  "generator": {
    "name": "SummaryBot-NG",
    "version": "2.1.0"
  },
  "sources": [
    {
      "source_type": "discord",
      "server_id": "123456789",
      "server_name": "My Community",
      "folder": "discord/my-community_123456789",
      "channel_count": 12,
      "summary_count": 450,
      "date_range": {
        "earliest": "2025-06-01",
        "latest": "2026-02-14"
      }
    },
    {
      "source_type": "whatsapp",
      "server_id": "group_abc123",
      "server_name": "Family Chat",
      "folder": "whatsapp/family-chat_group_abc123",
      "channel_count": 1,
      "summary_count": 180,
      "date_range": {
        "earliest": "2025-09-01",
        "latest": "2026-02-14"
      }
    },
    {
      "source_type": "slack",
      "server_id": "T01ABC123",
      "server_name": "Acme Corp",
      "folder": "slack/acme-corp_T01ABC123",
      "channel_count": 25,
      "summary_count": 890,
      "date_range": {
        "earliest": "2024-01-01",
        "latest": "2026-02-14"
      }
    }
  ]
}
```

### 3.2 Server/Group Manifest

Platform-agnostic manifest for any source:

```json
{
  "source_type": "whatsapp",
  "server_id": "group_abc123",
  "server_name": "Family Chat",
  "default_timezone": "America/Chicago",
  "prompt_versions": {
    "current": {
      "version": "2.1.0",
      "checksum": "sha256:a1b2c3d4e5f6...",
      "updated_at": "2026-02-10T09:00:00Z"
    },
    "history": [
      {
        "version": "2.0.0",
        "checksum": "sha256:9f8e7d6c5b4a...",
        "active_from": "2026-01-01T00:00:00Z",
        "active_until": "2026-02-10T08:59:59Z"
      }
    ]
  },
  "summary_options_default": {
    "summary_length": "detailed",
    "perspective": "general",
    "include_action_items": true,
    "include_technical_terms": false,
    "include_participant_analysis": true
  },
  "cost_tracking": {
    "enabled": true,
    "budget_monthly_usd": 50.00,
    "alert_threshold_percent": 80
  }
}
```

### 3.3 Summary Metadata File

Each summary `.md` file has a companion `.meta.json`:

```json
{
  "summary_id": "sum_abc123",
  "generated_at": "2026-02-14T16:30:00Z",
  "period": {
    "start": "2026-02-14T00:00:00-05:00",
    "end": "2026-02-14T23:59:59-05:00",
    "timezone": "America/New_York"
  },
  "source": {
    "source_type": "whatsapp",
    "server_id": "group_abc123",
    "server_name": "Family Chat",
    "channel_id": null,
    "channel_name": null
  },
  "statistics": {
    "message_count": 47,
    "participant_count": 8,
    "word_count": 1521,
    "attachment_count": 5
  },
  "generation": {
    "prompt_checksum": "sha256:a1b2c3d4e5f6...",
    "prompt_version": "2.1.0",
    "model": "claude-sonnet-4-20250514",
    "options": {
      "summary_length": "detailed",
      "perspective": "general",
      "include_action_items": true
    },
    "duration_seconds": 2.1,
    "tokens_used": {
      "input": 3200,
      "output": 850
    },
    "cost_usd": 0.0156
  },
  "backfill": {
    "is_backfill": true,
    "original_generation_failed": false,
    "backfilled_at": "2026-02-14T16:30:00Z",
    "reason": "historical_archive"
  },
  "status": "complete",
  "integrity": {
    "content_checksum": "sha256:x1y2z3...",
    "references_validated": true
  }
}
```

### 3.4 Gap/Incomplete Marker

When a summary cannot be generated (no messages, error, etc.), create a marker file:

```json
{
  "summary_id": null,
  "period": {
    "start": "2026-02-13T00:00:00-05:00",
    "end": "2026-02-13T23:59:59-05:00",
    "timezone": "America/New_York"
  },
  "source": {
    "source_type": "slack",
    "server_id": "T01ABC123",
    "channel_id": "C01XYZ789"
  },
  "status": "incomplete",
  "incomplete_reason": {
    "code": "NO_MESSAGES",
    "message": "No messages found in this period",
    "details": {
      "messages_checked": 0,
      "bot_messages_excluded": 2
    }
  },
  "backfill_eligible": false,
  "checked_at": "2026-02-14T08:00:00Z"
}
```

Status codes for incomplete summaries:

| Code | Description | Backfill Eligible |
|------|-------------|-------------------|
| `NO_MESSAGES` | No messages in period | No (no data exists) |
| `INSUFFICIENT_MESSAGES` | Below minimum threshold | Yes (lower threshold) |
| `API_ERROR` | Claude API failure | Yes |
| `RATE_LIMITED` | Rate limit hit | Yes |
| `BOT_OFFLINE` | Bot was offline | Yes |
| `SOURCE_INACCESSIBLE` | No permission at time | Maybe (if fixed) |
| `PROMPT_ERROR` | Prompt template error | Yes (after fix) |
| `EXPORT_UNAVAILABLE` | WhatsApp export not provided | Yes (when provided) |

---

## 4. Cost Attribution & Tracking

### 4.1 Cost Ledger

A global cost ledger tracks API costs per source for attribution:

```json
{
  "schema_version": "1.0.0",
  "currency": "USD",
  "pricing": {
    "claude-sonnet-4-20250514": {
      "input_per_1k": 0.003,
      "output_per_1k": 0.015
    },
    "claude-haiku-4-20250514": {
      "input_per_1k": 0.00025,
      "output_per_1k": 0.00125
    }
  },
  "sources": {
    "discord:123456789": {
      "server_name": "My Community",
      "total_cost_usd": 127.45,
      "summary_count": 450,
      "monthly": {
        "2026-02": { "cost_usd": 12.30, "summaries": 45, "tokens_input": 425000, "tokens_output": 67000 },
        "2026-01": { "cost_usd": 14.20, "summaries": 52, "tokens_input": 490000, "tokens_output": 78000 }
      },
      "last_updated": "2026-02-14T16:30:00Z"
    },
    "whatsapp:group_abc123": {
      "server_name": "Family Chat",
      "total_cost_usd": 28.90,
      "summary_count": 180,
      "monthly": {
        "2026-02": { "cost_usd": 3.45, "summaries": 14, "tokens_input": 112000, "tokens_output": 18500 }
      },
      "last_updated": "2026-02-14T16:30:00Z"
    },
    "slack:T01ABC123": {
      "server_name": "Acme Corp",
      "total_cost_usd": 312.80,
      "summary_count": 890,
      "monthly": {
        "2026-02": { "cost_usd": 28.90, "summaries": 98, "tokens_input": 980000, "tokens_output": 156000 }
      },
      "last_updated": "2026-02-14T16:30:00Z"
    }
  },
  "total_cost_usd": 469.15,
  "total_summaries": 1520
}
```

### 4.2 Cost Tracking Service

```python
@dataclass
class CostEntry:
    """Single cost entry for a summary generation."""
    source_key: str              # e.g., "discord:123456789"
    summary_id: str
    timestamp: datetime
    model: str
    tokens_input: int
    tokens_output: int
    cost_usd: float

class CostTracker:
    """Tracks and attributes costs per source."""

    def __init__(self, ledger_path: Path):
        self.ledger_path = ledger_path
        self.ledger = self._load_ledger()

    def record_cost(self, entry: CostEntry) -> None:
        """Record a cost entry to the ledger."""
        source = self.ledger["sources"].setdefault(entry.source_key, {
            "server_name": "",
            "total_cost_usd": 0,
            "summary_count": 0,
            "monthly": {}
        })

        month_key = entry.timestamp.strftime("%Y-%m")
        month = source["monthly"].setdefault(month_key, {
            "cost_usd": 0, "summaries": 0, "tokens_input": 0, "tokens_output": 0
        })

        source["total_cost_usd"] += entry.cost_usd
        source["summary_count"] += 1
        month["cost_usd"] += entry.cost_usd
        month["summaries"] += 1
        month["tokens_input"] += entry.tokens_input
        month["tokens_output"] += entry.tokens_output

        self.ledger["total_cost_usd"] += entry.cost_usd
        self.ledger["total_summaries"] += 1

        self._save_ledger()

    def get_source_cost(self, source_key: str,
                        month: Optional[str] = None) -> CostSummary:
        """Get cost summary for a source, optionally filtered by month."""
        ...

    def get_cost_report(self) -> CostReport:
        """Generate full cost report across all sources."""
        ...
```

### 4.3 Cost Report UI

```
┌──────────────────────────────────────────────────────────────────┐
│  Archive Cost Report                                              │
│  ────────────────────────────────────────────────────────────────│
│                                                                   │
│  Period: February 2026                   Total: $44.65            │
│  ─────────────────────────────────────────────────────────────── │
│                                                                   │
│  By Source:                                                       │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  💬 Discord: My Community                                  │  │
│  │     $12.30 (45 summaries, 492K tokens)                     │  │
│  │     Budget: $50/mo — 24.6% used ████░░░░░░░░░░░░          │  │
│  ├────────────────────────────────────────────────────────────┤  │
│  │  📱 WhatsApp: Family Chat                                  │  │
│  │     $3.45 (14 summaries, 130K tokens)                      │  │
│  │     Budget: $10/mo — 34.5% used ███████░░░░░░░░░░          │  │
│  ├────────────────────────────────────────────────────────────┤  │
│  │  💼 Slack: Acme Corp                                       │  │
│  │     $28.90 (98 summaries, 1.1M tokens)                     │  │
│  │     Budget: $100/mo — 28.9% used ██████░░░░░░░░░░░         │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  [Export CSV]  [Set Budgets]  [View History]                     │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 5. Prompt Version Tracking

### 5.1 Prompt Checksum Generation

```python
import hashlib
from typing import Dict, Any

def compute_prompt_checksum(prompt_config: Dict[str, Any]) -> str:
    """
    Generate a deterministic checksum of the prompt configuration.

    Includes:
    - System prompt template
    - User prompt template
    - Model parameters (temperature, max_tokens)
    - Extraction settings (action_items, technical_terms, etc.)
    """
    # Normalize and serialize deterministically
    canonical = json.dumps(prompt_config, sort_keys=True, separators=(',', ':'))
    return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"
```

### 5.2 Backfill Eligibility Detection

```python
class BackfillAnalyzer:
    """Analyzes archive for backfill opportunities."""

    def analyze_backfill_potential(
        self,
        archive_path: Path,
        source_filter: Optional[ArchiveSource] = None,
        current_prompt_checksum: str = None
    ) -> BackfillReport:
        """
        Scan archive and identify:
        1. Missing summaries (gaps in date range)
        2. Failed summaries eligible for retry
        3. Summaries generated with outdated prompts
        """
        report = BackfillReport()

        for meta_file in archive_path.glob("**/sources/**/*.meta.json"):
            meta = json.loads(meta_file.read_text())

            # Apply source filter if specified
            if source_filter and not self._matches_source(meta, source_filter):
                continue

            # Check for incomplete/failed
            if meta.get("status") == "incomplete":
                if meta.get("backfill_eligible", True):
                    report.add_gap(
                        source=meta["source"],
                        period=meta["period"],
                        reason=meta["incomplete_reason"]["code"]
                    )

            # Check for outdated prompt
            elif (current_prompt_checksum and
                  meta.get("generation", {}).get("prompt_checksum") != current_prompt_checksum):
                report.add_outdated(
                    source=meta["source"],
                    period=meta["period"],
                    old_checksum=meta["generation"]["prompt_checksum"],
                    summary_file=meta_file.with_suffix(".md")
                )

        return report
```

---

## 6. Google Drive Sync — Flexible Sharing

### 6.1 Sync Configuration Options

Archives can be synced to Google Drive with flexible organization:

**Option A: Shared Drive (All Sources Together)**
```
My Google Drive/
└── SummaryBot Archives/           ← Single shared folder
    ├── manifest.json
    └── sources/
        ├── discord/...
        ├── whatsapp/...
        └── slack/...
```

**Option B: Separate Drives Per Source**
```
Work Google Drive/
└── Slack Archives/                ← Separate folder per workspace
    └── acme-corp_T01ABC123/...

Personal Google Drive/
└── Family Archives/               ← Personal archives
    ├── whatsapp/family-chat/...
    └── discord/gaming-server/...
```

**Option C: Hybrid (Per-Organization)**
```
Acme Corp Shared Drive/
└── Chat Archives/
    ├── slack/acme-corp/...
    └── discord/acme-team/...

Personal Drive/
└── Personal Archives/
    └── whatsapp/family/...
```

### 6.2 Sync Configuration Model

```python
class GoogleDriveSyncConfig(BaseModel):
    """Configuration for Google Drive sync per source."""

    enabled: bool = False
    folder_id: str                  # Google Drive folder ID
    credentials_path: str           # Path to service account JSON

    # Sync behavior
    sync_frequency: Literal["realtime", "hourly", "daily"] = "hourly"
    sync_deletes: bool = False      # Remove from Drive if deleted locally

    # Conflict resolution
    conflict_strategy: Literal["local_wins", "remote_wins", "newest"] = "local_wins"

class ArchiveSyncSettings(BaseModel):
    """Sync settings supporting multiple destinations."""

    # Global default (optional)
    default_google_drive: Optional[GoogleDriveSyncConfig] = None

    # Per-source overrides (source_key -> config)
    # If not specified, uses default; if default not set, no sync
    source_overrides: Dict[str, GoogleDriveSyncConfig] = {}

    def get_sync_config(self, source_key: str) -> Optional[GoogleDriveSyncConfig]:
        """Get sync config for a source, falling back to default."""
        if source_key in self.source_overrides:
            return self.source_overrides[source_key]
        return self.default_google_drive
```

### 6.3 Archive Config File

```json
{
  "sync": {
    "default_google_drive": {
      "enabled": true,
      "folder_id": "1ABC123_shared_archives",
      "credentials_path": "/secure/gdrive-service-account.json",
      "sync_frequency": "hourly"
    },
    "source_overrides": {
      "slack:T01ABC123": {
        "enabled": true,
        "folder_id": "1XYZ789_acme_archives",
        "credentials_path": "/secure/acme-gdrive.json",
        "sync_frequency": "realtime"
      },
      "whatsapp:group_abc123": {
        "enabled": true,
        "folder_id": "1DEF456_personal_archives",
        "credentials_path": "/secure/personal-gdrive.json",
        "sync_frequency": "daily"
      }
    }
  }
}
```

### 6.4 Sync Status in Manifest

```json
{
  "sync": {
    "discord:123456789": {
      "destination": "google_drive",
      "folder_id": "1ABC123...",
      "last_sync": "2026-02-14T16:00:00Z",
      "last_sync_status": "success",
      "files_synced": 450,
      "files_failed": 0,
      "next_scheduled_sync": "2026-02-14T17:00:00Z"
    },
    "slack:T01ABC123": {
      "destination": "google_drive",
      "folder_id": "1XYZ789...",
      "last_sync": "2026-02-14T16:30:00Z",
      "last_sync_status": "success",
      "files_synced": 890
    },
    "whatsapp:group_abc123": {
      "destination": "google_drive",
      "folder_id": "1DEF456...",
      "last_sync": "2026-02-14T00:00:00Z",
      "last_sync_status": "success",
      "files_synced": 180
    }
  }
}
```

---

## 7. Summary Markdown Format

### 7.1 Standard Template (Platform-Aware)

```markdown
# Daily Summary: Family Chat

**Platform:** WhatsApp
**Group:** Family Chat
**Date:** 2026-02-14 (Friday)
**Timezone:** America/Chicago (UTC-6)
**Period:** 00:00 — 23:59
**Messages:** 47 from 8 participants

---

## Overview

A brief 2-3 sentence overview of the day's activity.

---

## Key Points

1. **Birthday Planning** — Mom's birthday party confirmed for Saturday at 3pm.
   Dad will bring the cake. [ref:msg_12, msg_15]

2. **Vacation Discussion** — Summer trip dates narrowed to July 15-22.
   Sarah will check flight prices. [ref:msg_28, msg_31]

---

## Action Items

- [ ] @Dad: Order birthday cake from Mario's Bakery [ref:msg_16]
- [ ] @Sarah: Compare flight prices by Sunday [ref:msg_32]
- [ ] @Everyone: RSVP for birthday party [ref:msg_20]

---

## Participant Highlights

| Participant | Messages | Topics |
|-------------|----------|--------|
| Mom | 12 | Birthday planning, recipes |
| Sarah | 10 | Vacation, travel |
| Dad | 8 | Party logistics |

---

## Media Shared

- 📷 Birthday cake options (3 photos) shared by Mom
- 🔗 [Hotel deals link](https://example.com) shared by Sarah

---

*Generated by SummaryBot-NG v2.1.0 on 2026-02-14T16:30:00Z*
*Prompt version: 2.1.0 (sha256:a1b2c3d4)*
*Cost: $0.016*
```

### 7.2 Platform-Specific Headers

| Platform | Header Format |
|----------|--------------|
| Discord | `**Server:** My Community` / `**Channel:** #general` |
| WhatsApp | `**Group:** Family Chat` |
| Slack | `**Workspace:** Acme Corp` / `**Channel:** #engineering` |
| Telegram | `**Chat:** Project Discussion` |

### 7.3 Perspective Variants

| Perspective | Emphasized Sections |
|-------------|---------------------|
| `general` | Overview, Key Points, Action Items |
| `developer` | Technical Discussions, Code References, Architecture Decisions |
| `executive` | Strategic Decisions, Metrics, Blockers, Timeline Impacts |
| `support` | User Issues, Bug Reports, Resolution Status |
| `marketing` | Announcements, Community Sentiment, Feature Requests |
| `family` | Events, Plans, Shared Media, Reminders |

---

## 8. Archive Generation API

### 8.1 New Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/archive/generate` | POST | Generate retrospective summaries |
| `/api/v1/archive/status/{job_id}` | GET | Check generation job status |
| `/api/v1/archive/backfill-report` | POST | Analyze archive for backfill opportunities |
| `/api/v1/archive/sync` | POST | Sync archive to external storage |
| `/api/v1/archive/download` | GET | Download archive as ZIP |
| `/api/v1/archive/costs` | GET | Get cost report by source |
| `/api/v1/archive/costs/{source_key}` | GET | Get cost details for specific source |

### 8.2 Generate Retrospective Request

```python
class RetrospectiveGenerateRequest(BaseModel):
    """Request to generate retrospective summaries."""

    # Source identification (platform-agnostic)
    source_type: SourceType
    server_id: str
    channel_ids: Optional[List[str]] = None  # None = all channels/whole group

    # Time range
    date_range: DateRange
    granularity: Literal["daily", "weekly", "monthly"] = "daily"
    timezone: str = "UTC"

    # Options
    summary_options: SummaryOptionsRequest

    # Backfill behavior
    skip_existing: bool = True          # Don't regenerate existing
    regenerate_outdated: bool = False   # Regenerate if prompt changed
    regenerate_failed: bool = True      # Retry failed attempts

    # Output
    output_format: Literal["archive", "database", "both"] = "both"
    archive_path: Optional[str] = None  # Custom path, or use default

    # Cost controls
    max_cost_usd: Optional[float] = None  # Stop if cost exceeds this
    dry_run: bool = False                  # Estimate cost without generating

class DateRange(BaseModel):
    start: date  # Inclusive
    end: date    # Inclusive
```

### 8.3 Generation Job Response

```python
class GenerationJobResponse(BaseModel):
    job_id: str
    source_key: str                     # e.g., "whatsapp:group_abc123"
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    progress: GenerationProgress
    cost: CostProgress
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

class GenerationProgress(BaseModel):
    total_periods: int
    completed: int
    failed: int
    skipped: int
    current_period: Optional[str]
    estimated_remaining_seconds: Optional[int]

class CostProgress(BaseModel):
    cost_usd: float
    tokens_input: int
    tokens_output: int
    max_cost_usd: Optional[float]
    percent_of_max: Optional[float]
```

---

## 9. Backfill Workflow

### 9.1 User-Initiated Backfill (Multi-Source)

```
┌──────────────────────────────────────────────────────────────────┐
│  Archive Manager                                                  │
│  ────────────────────────────────────────────────────────────────│
│                                                                   │
│  Sources: [All ▼]  Filter by: [Platform ▼]                       │
│  ─────────────────────────────────────────────────────────────── │
│                                                                   │
│  💬 Discord: My Community                                         │
│     259 days | 245 ✓ | 8 ✗ | 6 ○ | 52 outdated                  │
│     Estimated backfill: $2.40                                    │
│     [Expand] [Backfill]                                          │
│  ─────────────────────────────────────────────────────────────── │
│  📱 WhatsApp: Family Chat                                         │
│     180 days | 175 ✓ | 2 ✗ | 3 ○ | 0 outdated                   │
│     Estimated backfill: $0.85                                    │
│     [Expand] [Backfill]                                          │
│  ─────────────────────────────────────────────────────────────── │
│  💼 Slack: Acme Corp                                              │
│     420 days | 890 ✓ | 12 ✗ | 8 ○ | 120 outdated                │
│     Estimated backfill: $23.40                                   │
│     [Expand] [Backfill]                                          │
│  ─────────────────────────────────────────────────────────────── │
│                                                                   │
│  Legend: ✓ complete  ✗ failed  ○ missing  📋 outdated prompt     │
│                                                                   │
│  [Backfill All Selected]              Total Est: $26.65          │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 10. Configuration Management

### 10.1 Archive Settings

```python
class ArchiveConfig(BaseModel):
    """User configuration for archive management."""

    # Storage
    archive_root: Path = Path("./summarybot-archive")

    # Generation defaults
    default_granularity: Literal["daily", "weekly", "monthly"] = "daily"
    default_timezone: str = "UTC"

    # Retention
    auto_archive_after_days: Optional[int] = None
    retention_days: Optional[int] = None

    # Naming
    folder_name_format: str = "{server_name}_{server_id}"
    summary_name_format: str = "{date}_{granularity}"

    # Sync (flexible per-source configuration)
    sync: ArchiveSyncSettings = ArchiveSyncSettings()

    # Cost tracking
    cost_tracking_enabled: bool = True
    default_budget_monthly_usd: Optional[float] = None

    # Performance
    max_concurrent_generations: int = 3
    rate_limit_per_minute: int = 10
```

### 10.2 Per-Source Overrides

```json
{
  "source_type": "slack",
  "server_id": "T01ABC123",
  "server_name": "Acme Corp",
  "overrides": {
    "summary_options": {
      "perspective": "developer",
      "include_technical_terms": true
    },
    "granularity": "daily",
    "timezone": "America/Los_Angeles"
  },
  "cost_tracking": {
    "budget_monthly_usd": 100.00,
    "alert_threshold_percent": 80,
    "alert_email": "billing@acme.com"
  },
  "sync": {
    "google_drive": {
      "folder_id": "1XYZ_acme_specific_folder"
    }
  }
}
```

---

## 11. File-by-File Change Map

| # | File | Action | Risk | Description |
|---|------|--------|------|-------------|
| 1 | `src/archive/models.py` | **N** | Low | Archive manifest, metadata, cost models |
| 2 | `src/archive/sources.py` | **N** | Low | Platform-agnostic source abstraction |
| 3 | `src/archive/generator.py` | **N** | Medium | Retrospective summary generation |
| 4 | `src/archive/writer.py` | **N** | Low | Markdown file writer with templates |
| 5 | `src/archive/scanner.py` | **N** | Low | Archive scanning and gap detection |
| 6 | `src/archive/backfill.py` | **N** | Medium | Backfill analysis and execution |
| 7 | `src/archive/cost_tracker.py` | **N** | Low | Per-source cost attribution |
| 8 | `src/archive/sync/base.py` | **N** | Low | Base sync provider interface |
| 9 | `src/archive/sync/google_drive.py` | **N** | Medium | Google Drive sync (flexible sharing) |
| 10 | `src/archive/prompt_tracker.py` | **N** | Low | Prompt checksum generation and tracking |
| 11 | `src/dashboard/routes/archive.py` | **N** | Medium | Archive management API endpoints |
| 12 | `src/dashboard/routes/costs.py` | **N** | Low | Cost reporting API endpoints |
| 13 | `src/dashboard/models.py` | **M** | Low | Add archive/cost request/response models |
| 14 | `src/frontend/src/pages/Archive.tsx` | **N** | Medium | Archive management UI |
| 15 | `src/frontend/src/pages/Costs.tsx` | **N** | Low | Cost dashboard UI |
| 16 | `src/frontend/src/components/archive/TimelineView.tsx` | **N** | Low | Visual timeline |
| 17 | `src/frontend/src/components/archive/BackfillModal.tsx` | **N** | Low | Backfill configuration |
| 18 | `src/frontend/src/components/archive/SourceSelector.tsx` | **N** | Low | Multi-source picker |
| 19 | `src/frontend/src/components/costs/CostChart.tsx` | **N** | Low | Cost visualization |
| 20 | `src/config/archive.py` | **N** | Low | Archive configuration schema |
| 21 | `tests/unit/test_archive_*.py` | **N** | — | Unit tests |
| 22 | `tests/unit/test_cost_tracker.py` | **N** | — | Cost tracking tests |

**Totals:** 1 file modified, 21 files created.

---

## 12. Edge Cases and Mitigations

| Edge Case | Mitigation |
|-----------|------------|
| Source deleted, history inaccessible | Mark as `SOURCE_DELETED` in meta; not backfill eligible |
| WhatsApp export not provided for period | Mark as `EXPORT_UNAVAILABLE`; backfill when export provided |
| Very long time range (years) | Paginate generation; show progress; allow pause/resume |
| Rate limits during batch generation | Exponential backoff; queue remaining; report partial progress |
| Conflicting timezone changes | Store canonical UTC times; convert on display |
| Large channels (10k+ messages/day) | Chunk processing; cache intermediate results |
| Prompt changes mid-backfill | Lock prompt version for job duration; note in manifest |
| Google Drive quota exceeded | Fail gracefully; queue for retry; notify user |
| Concurrent backfill jobs | Queue system; prevent duplicate date processing |
| Cost budget exceeded mid-generation | Pause job; notify user; allow resume or cancel |
| Different prompt versions per source | Track per-source prompt history independently |

---

## 13. Security Considerations

1. **Message Access Permissions** — Retrospective generation requires historical message access. Verify access rights per platform.

2. **Google Drive Credentials** — Service account keys stored securely; never in archive folder. Support multiple credentials for different drives.

3. **Sensitive Content** — Same content filtering as real-time summaries applies to retrospective generation.

4. **Archive Access Control** — Archive files may contain summarized private conversations. Protect archive folder with appropriate filesystem permissions.

5. **API Key Usage** — Batch retrospective generation can consume significant API quota. Cost limits and confirmation required.

6. **Cross-Org Data Separation** — When using separate drives per source, ensure no cross-contamination of credentials or data.

---

## 14. Implementation Phases

### Phase 1 — Core Archive Structure (3-4 days)
- [ ] Define multi-source archive folder structure
- [ ] Implement `ArchiveSource` abstraction
- [ ] Create manifest schemas for all platforms
- [ ] Implement `ArchiveWriter` for Markdown generation

### Phase 2 — Cost Tracking (2-3 days)
- [ ] Implement `CostTracker` with per-source attribution
- [ ] Create cost ledger format and persistence
- [ ] Add cost estimation for dry runs
- [ ] Build cost reporting endpoints

### Phase 3 — Retrospective Generation (3-4 days)
- [ ] Implement `RetrospectiveGenerator` service
- [ ] Add historical message fetching per platform
- [ ] Create job queue with cost limits
- [ ] Add progress tracking and reporting

### Phase 4 — Backfill Analysis (2-3 days)
- [ ] Implement `ArchiveScanner` for gap detection
- [ ] Create `BackfillAnalyzer` with source filtering
- [ ] Add prompt version comparison logic
- [ ] Generate backfill reports

### Phase 5 — Google Drive Sync (2-3 days)
- [ ] Implement flexible sync configuration
- [ ] Support multiple drives per installation
- [ ] Add per-source sync status tracking
- [ ] Handle conflicts and errors

### Phase 6 — Frontend UI (3-4 days)
- [ ] Create Archive page with source browser
- [ ] Build Timeline visualization
- [ ] Create Cost dashboard
- [ ] Add Backfill configuration modal

### Phase 7 — Testing & Polish (2-3 days)
- [ ] Unit tests for all archive components
- [ ] Integration tests for each platform
- [ ] Cost tracking tests
- [ ] Documentation and examples

---

## 15. Future Extensions

| Extension | Description |
|-----------|-------------|
| **S3/Azure Blob Sync** | Additional cloud storage providers |
| **Archive Search** | Full-text search across archived summaries |
| **Cross-Platform Summaries** | Combined summaries from Discord + Slack for same team |
| **Budget Alerts** | Email/webhook when approaching budget limits |
| **Cost Optimization** | Suggest using Haiku for low-activity periods |
| **Archive Analytics** | Trends, statistics, and insights across archive |
| **Billing Integration** | Export cost data for invoicing/chargebacks |

---

## 16. Consequences

### Positive
- **Multi-Platform Support**: Unified archive for Discord, WhatsApp, Slack, Telegram
- **Flexible Storage**: Share or separate Google Drives as needed
- **Cost Transparency**: Know exactly what each server/group costs
- **Historical Coverage**: Communities can document their entire history
- **Portable Archives**: Human-readable Markdown works everywhere

### Negative
- **Storage Requirements**: Full archives can grow large (~50KB/day/channel)
- **API Costs**: Retrospective generation for long periods can be expensive
- **Complexity**: More configuration options and workflows to learn
- **Credential Management**: Multiple drives means multiple service accounts

### Trade-offs
- **Flexibility vs. Simplicity**: Supporting per-source drive config adds complexity but enables enterprise use cases
- **Markdown vs. Database**: Chose Markdown for portability, sacrificing query performance
- **Cost Granularity**: Per-summary cost tracking adds overhead but enables accurate attribution

---

## 17. References

- [ADR-002: WhatsApp Data Source Integration](./002-whatsapp-datasource-integration-summarybotng.md) — Multi-source architecture
- [ADR-004: Grounded Summary References](./004-grounded-summary-references.md) — Citation format
- [ADR-005: Summary Delivery Destinations](./005-summary-delivery-destinations.md) — Storage model
- [ISO 8601 Date Format](https://en.wikipedia.org/wiki/ISO_8601) — Date naming standard
- [Google Drive API](https://developers.google.com/drive/api) — Sync integration
- [Anthropic Pricing](https://www.anthropic.com/pricing) — Cost calculation reference
