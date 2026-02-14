# ADR-006: Retrospective Summary Archive — Historical Backfill with Versioned Prompts

**Status:** Proposed
**Date:** 2026-02-14
**Depends on:** ADR-004 (Grounded References), ADR-005 (Delivery Destinations)
**Repository:** [summarybotng/summarybot-ng](https://github.com/summarybotng/summarybot-ng)

---

## 1. Problem Statement

Current summarization is forward-looking only: summaries are generated for recent activity or on a schedule going forward. This creates several gaps:

1. **No Historical Record** — Communities with months/years of chat history have no way to generate retrospective summaries for past periods.

2. **Missing Summary Gaps** — If the bot was offline, a schedule failed, or summarization wasn't configured, those periods have no summaries and no easy way to fill them.

3. **No Portable Archive** — Summaries exist only in Discord messages or the database. There's no human-navigable, portable archive that can be stored externally (e.g., Google Drive) and browsed without the application.

4. **Configuration Drift** — When prompt templates or summary configurations change, there's no way to know which summaries were generated with which settings, making regeneration decisions difficult.

5. **Timezone Confusion** — Historical summaries need clear timezone labeling since "February 13, 2026" means different things in different timezones.

---

## 2. Decision

Implement a **Retrospective Summary Archive** system that:

1. **Generates summaries for arbitrary past time ranges** with configurable granularity (daily, weekly, monthly)
2. **Stores summaries as Markdown files** in a structured, human-navigable folder hierarchy
3. **Maintains manifest metadata** tracking generation status, configuration versions, and backfill potential
4. **Supports external sync** to Google Drive or other storage providers
5. **Enables intelligent backfill** by identifying gaps and configuration changes

### 2.1 Archive Folder Structure

```
summarybot-archive/
├── manifest.json                    # Global manifest with schema version
├── servers/
│   └── {guild_name}_{guild_id}/
│       ├── server-manifest.json     # Server-level config and prompt checksums
│       ├── channels/
│       │   └── {channel_name}_{channel_id}/
│       │       ├── channel-manifest.json
│       │       └── summaries/
│       │           └── {YYYY}/
│       │               └── {MM}/
│       │                   ├── {YYYY-MM-DD}_daily.md
│       │                   ├── {YYYY-MM-DD}_daily.meta.json
│       │                   ├── {YYYY}-W{WW}_weekly.md
│       │                   └── {YYYY}-W{WW}_weekly.meta.json
│       └── cross-channel/
│           └── {summary_name}/      # Named cross-channel summary configs
│               ├── config.json      # Which channels, options
│               └── summaries/
│                   └── {YYYY}/{MM}/...
└── .archive-config.json             # User preferences, sync settings
```

### 2.2 File Naming Convention

| Granularity | Filename Pattern | Example |
|-------------|-----------------|---------|
| Daily | `{YYYY-MM-DD}_daily.md` | `2026-02-14_daily.md` |
| Weekly | `{YYYY}-W{WW}_weekly.md` | `2026-W07_weekly.md` |
| Monthly | `{YYYY-MM}_monthly.md` | `2026-02_monthly.md` |
| Custom Range | `{YYYY-MM-DD}_to_{YYYY-MM-DD}.md` | `2026-02-01_to_2026-02-14.md` |

All dates use **ISO 8601** format for universal sorting and clarity.

### 2.3 Timezone Handling

Each summary file includes explicit timezone information:

```markdown
# Daily Summary: #general
**Date:** 2026-02-14 (Friday)
**Timezone:** America/New_York (UTC-5)
**Period:** 2026-02-14 00:00 to 2026-02-14 23:59 (America/New_York)
**Messages:** 147 from 23 participants

---

## Key Points
...
```

The archive supports generating summaries in different timezones:
- **Server timezone**: Default, based on server/guild settings
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
  "servers": [
    {
      "guild_id": "123456789",
      "guild_name": "My Community",
      "folder": "my-community_123456789",
      "channel_count": 12,
      "summary_count": 450,
      "date_range": {
        "earliest": "2025-06-01",
        "latest": "2026-02-14"
      }
    }
  ]
}
```

### 3.2 Server Manifest

```json
{
  "guild_id": "123456789",
  "guild_name": "My Community",
  "default_timezone": "America/New_York",
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
    "include_technical_terms": true,
    "include_participant_analysis": true
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
    "channel_id": "987654321",
    "channel_name": "general",
    "guild_id": "123456789"
  },
  "statistics": {
    "message_count": 147,
    "participant_count": 23,
    "word_count": 4521,
    "attachment_count": 12
  },
  "generation": {
    "prompt_checksum": "sha256:a1b2c3d4e5f6...",
    "prompt_version": "2.1.0",
    "model": "claude-sonnet-4-20250514",
    "options": {
      "summary_length": "detailed",
      "perspective": "developer",
      "include_action_items": true
    },
    "duration_seconds": 3.2,
    "tokens_used": {
      "input": 8500,
      "output": 1200
    }
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
// 2026-02-13_daily.meta.json (no .md file exists)
{
  "summary_id": null,
  "period": {
    "start": "2026-02-13T00:00:00-05:00",
    "end": "2026-02-13T23:59:59-05:00",
    "timezone": "America/New_York"
  },
  "status": "incomplete",
  "incomplete_reason": {
    "code": "NO_MESSAGES",
    "message": "No messages found in this period",
    "details": {
      "messages_checked": 0,
      "bot_messages_excluded": 5
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
| `CHANNEL_INACCESSIBLE` | No permission at time | Maybe (if fixed) |
| `PROMPT_ERROR` | Prompt template error | Yes (after fix) |

---

## 4. Prompt Version Tracking

### 4.1 Prompt Checksum Generation

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

### 4.2 Backfill Eligibility Detection

```python
class BackfillAnalyzer:
    """Analyzes archive for backfill opportunities."""

    def analyze_backfill_potential(
        self,
        archive_path: Path,
        current_prompt_checksum: str
    ) -> BackfillReport:
        """
        Scan archive and identify:
        1. Missing summaries (gaps in date range)
        2. Failed summaries eligible for retry
        3. Summaries generated with outdated prompts
        """
        report = BackfillReport()

        for meta_file in archive_path.glob("**/*.meta.json"):
            meta = json.loads(meta_file.read_text())

            # Check for incomplete/failed
            if meta.get("status") == "incomplete":
                if meta.get("backfill_eligible", True):
                    report.add_gap(
                        period=meta["period"],
                        reason=meta["incomplete_reason"]["code"]
                    )

            # Check for outdated prompt
            elif meta.get("generation", {}).get("prompt_checksum") != current_prompt_checksum:
                report.add_outdated(
                    period=meta["period"],
                    old_checksum=meta["generation"]["prompt_checksum"],
                    summary_file=meta_file.with_suffix(".md")
                )

        # Detect missing dates in range
        report.add_missing_dates(
            self._find_date_gaps(archive_path)
        )

        return report
```

### 4.3 Backfill Report

```python
@dataclass
class BackfillReport:
    """Report of backfill opportunities in an archive."""

    gaps: List[BackfillGap]              # Missing or failed periods
    outdated_prompts: List[OutdatedSummary]  # Different prompt checksum
    missing_dates: List[DateRange]       # Dates with no attempt

    def summary(self) -> str:
        return f"""
Backfill Analysis Report
========================
Missing/Failed Summaries: {len(self.gaps)}
Outdated Prompt Versions: {len(self.outdated_prompts)}
Unprocessed Date Ranges:  {len(self.missing_dates)}

Recommendation: {self._recommendation()}
"""

    def _recommendation(self) -> str:
        if len(self.gaps) > 50:
            return "Large backfill needed. Consider running in batches."
        elif len(self.outdated_prompts) > 0:
            return "Prompt changed. Regenerate for consistency? (optional)"
        elif len(self.missing_dates) > 0:
            return "Some dates never processed. Run retrospective generation."
        else:
            return "Archive is complete and current."
```

---

## 5. Summary Markdown Format

### 5.1 Standard Template

```markdown
# Daily Summary: #general

**Server:** My Community
**Date:** 2026-02-14 (Friday)
**Timezone:** America/New_York (UTC-5)
**Period:** 00:00 — 23:59
**Messages:** 147 from 23 participants

---

## Overview

A brief 2-3 sentence overview of the day's activity.

---

## Key Points

1. **Project Alpha Launch** — Team confirmed launch date for March 1st. Final review scheduled for Feb 28. [ref:msg_123, msg_124]

2. **Database Migration** — PostgreSQL migration completed successfully. Performance improved by 40%. [ref:msg_156]

3. **New Team Member** — @sarah.dev joined the backend team. Will focus on API development. [ref:msg_189]

---

## Action Items

- [ ] @john: Prepare launch checklist by Feb 20 [ref:msg_125]
- [ ] @team: Review migration docs before EOD Friday [ref:msg_158]
- [ ] @sarah.dev: Complete onboarding tasks [ref:msg_190]

---

## Technical Discussions

### API Rate Limiting
Discussion about implementing rate limiting for public endpoints. Decision: Use token bucket algorithm with 100 req/min default. [ref:msg_201-205]

### Frontend Performance
Identified bundle size issue. Solution: Code splitting for dashboard components. [ref:msg_230-235]

---

## Participant Highlights

| Participant | Messages | Topics |
|-------------|----------|--------|
| @john | 23 | Project management, launches |
| @alice | 19 | Database, performance |
| @bob | 15 | Frontend, React |

---

## Attachments & Links

- [Launch Timeline.pdf](attachment:att_001) shared by @john
- [Performance Report](https://link.example.com/report) — Database benchmarks

---

## Sentiment & Tone

Overall: **Productive** 📈
Energy: High activity during morning (9-11 AM), moderate afternoon

---

*Generated by SummaryBot-NG v2.1.0 on 2026-02-14T16:30:00Z*
*Prompt version: 2.1.0 (sha256:a1b2c3d4)*
```

### 5.2 Perspective Variants

Different perspectives generate different sections:

| Perspective | Emphasized Sections |
|-------------|---------------------|
| `general` | Overview, Key Points, Action Items |
| `developer` | Technical Discussions, Code References, Architecture Decisions |
| `executive` | Strategic Decisions, Metrics, Blockers, Timeline Impacts |
| `support` | User Issues, Bug Reports, Resolution Status |
| `marketing` | Announcements, Community Sentiment, Feature Requests |

---

## 6. Archive Generation API

### 6.1 New Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/archive/generate` | POST | Generate retrospective summaries |
| `/api/v1/archive/status/{job_id}` | GET | Check generation job status |
| `/api/v1/archive/backfill-report` | POST | Analyze archive for backfill opportunities |
| `/api/v1/archive/sync` | POST | Sync archive to external storage |
| `/api/v1/archive/download` | GET | Download archive as ZIP |

### 6.2 Generate Retrospective Request

```python
class RetrospectiveGenerateRequest(BaseModel):
    """Request to generate retrospective summaries."""

    guild_id: str

    # Scope
    channel_ids: Optional[List[str]] = None  # None = all channels

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

class DateRange(BaseModel):
    start: date  # Inclusive
    end: date    # Inclusive
```

### 6.3 Generation Job Response

```python
class GenerationJobResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    progress: GenerationProgress
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
```

---

## 7. External Storage Sync

### 7.1 Google Drive Integration

```python
class GoogleDriveSyncConfig(BaseModel):
    """Configuration for Google Drive sync."""

    enabled: bool = False
    folder_id: str              # Google Drive folder ID
    credentials_path: str       # Path to service account JSON

    # Sync behavior
    sync_frequency: Literal["realtime", "hourly", "daily"] = "hourly"
    sync_deletes: bool = False  # Remove from Drive if deleted locally

    # Conflict resolution
    conflict_strategy: Literal["local_wins", "remote_wins", "newest"] = "local_wins"

class ArchiveSyncService:
    """Syncs archive to external storage providers."""

    async def sync_to_google_drive(
        self,
        archive_path: Path,
        config: GoogleDriveSyncConfig,
        incremental: bool = True
    ) -> SyncResult:
        """
        Sync archive folder to Google Drive.

        - Preserves folder structure
        - Uploads new/modified files
        - Optionally removes deleted files
        - Updates manifest with sync status
        """
        ...
```

### 7.2 Sync Status in Manifest

```json
{
  "sync": {
    "google_drive": {
      "enabled": true,
      "folder_id": "1ABC123...",
      "last_sync": "2026-02-14T16:00:00Z",
      "last_sync_status": "success",
      "files_synced": 450,
      "files_failed": 0,
      "next_scheduled_sync": "2026-02-14T17:00:00Z"
    }
  }
}
```

---

## 8. Backfill Workflow

### 8.1 User-Initiated Backfill

```
┌──────────────────────────────────────────────────────────────────┐
│  Archive Manager                                                  │
│  ────────────────────────────────────────────────────────────────│
│                                                                   │
│  📊 Archive Status: #general                                      │
│  ─────────────────────────────────────────────────────────────── │
│  Date Range: 2025-06-01 to 2026-02-14 (259 days)                 │
│  Summaries: 245 complete, 8 failed, 6 missing                    │
│  Current Prompt: v2.1.0 (sha256:a1b2c3d4)                        │
│  Outdated Summaries: 52 (generated with v2.0.0)                  │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Backfill Options                                           │ │
│  │  ─────────────────────────────────────────────────────────  │ │
│  │  ☑ Retry failed summaries (8)                               │ │
│  │  ☑ Generate missing dates (6)                               │ │
│  │  ☐ Regenerate with current prompt (52)                      │ │
│  │                                                             │ │
│  │  Estimated API cost: ~$2.40 (14 summaries × $0.17)          │ │
│  │  Estimated time: 3-5 minutes                                │ │
│  │                                                             │ │
│  │  [Cancel]                              [Start Backfill]     │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  📅 Timeline View                                                 │
│  ─────────────────────────────────────────────────────────────── │
│  Feb 2026: ████████████░░ (12/14 complete)                       │
│  Jan 2026: ██████████████████████████████░ (30/31 complete)      │
│  Dec 2025: ████████████████████████████████ (31/31 complete)     │
│  ...                                                              │
│  ░ = missing  █ = complete  ▓ = outdated prompt                  │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 8.2 Automatic Gap Detection

```python
class ArchiveGapDetector:
    """Detects gaps in archive coverage."""

    def detect_gaps(
        self,
        archive_path: Path,
        expected_range: DateRange,
        granularity: str = "daily"
    ) -> List[Gap]:
        """
        Compare expected dates against actual summaries.
        Returns list of gaps with reasons.
        """
        expected_dates = self._generate_expected_dates(expected_range, granularity)
        actual_summaries = self._scan_archive(archive_path)

        gaps = []
        for expected in expected_dates:
            if expected not in actual_summaries:
                gaps.append(Gap(
                    date=expected,
                    reason="MISSING",
                    backfill_eligible=True
                ))
            elif actual_summaries[expected].status == "incomplete":
                gaps.append(Gap(
                    date=expected,
                    reason=actual_summaries[expected].incomplete_reason,
                    backfill_eligible=actual_summaries[expected].backfill_eligible
                ))

        return gaps
```

---

## 9. Configuration Management

### 9.1 Archive Settings

```python
class ArchiveConfig(BaseModel):
    """User configuration for archive management."""

    # Storage
    archive_root: Path = Path("./summarybot-archive")

    # Generation defaults
    default_granularity: Literal["daily", "weekly", "monthly"] = "daily"
    default_timezone: str = "UTC"

    # Retention
    auto_archive_after_days: Optional[int] = None  # Auto-generate after N days
    retention_days: Optional[int] = None           # Delete after N days

    # Naming
    folder_name_format: str = "{guild_name}_{guild_id}"
    summary_name_format: str = "{date}_{granularity}"

    # Sync
    google_drive: Optional[GoogleDriveSyncConfig] = None

    # Performance
    max_concurrent_generations: int = 3
    rate_limit_per_minute: int = 10
```

### 9.2 Per-Channel Overrides

```json
// channel-manifest.json
{
  "channel_id": "987654321",
  "channel_name": "general",
  "overrides": {
    "summary_options": {
      "perspective": "developer",
      "include_technical_terms": true
    },
    "granularity": "daily",
    "timezone": "America/Los_Angeles"
  },
  "exclude_from_archive": false,
  "archive_start_date": "2025-06-01"
}
```

---

## 10. File-by-File Change Map

| # | File | Action | Risk | Description |
|---|------|--------|------|-------------|
| 1 | `src/archive/models.py` | **N** | Low | Archive manifest and metadata models |
| 2 | `src/archive/generator.py` | **N** | Medium | Retrospective summary generation |
| 3 | `src/archive/writer.py` | **N** | Low | Markdown file writer with templates |
| 4 | `src/archive/scanner.py` | **N** | Low | Archive scanning and gap detection |
| 5 | `src/archive/backfill.py` | **N** | Medium | Backfill analysis and execution |
| 6 | `src/archive/sync/base.py` | **N** | Low | Base sync provider interface |
| 7 | `src/archive/sync/google_drive.py` | **N** | Medium | Google Drive sync implementation |
| 8 | `src/archive/prompt_tracker.py` | **N** | Low | Prompt checksum generation and tracking |
| 9 | `src/dashboard/routes/archive.py` | **N** | Medium | Archive management API endpoints |
| 10 | `src/dashboard/models.py` | **M** | Low | Add archive request/response models |
| 11 | `src/frontend/src/pages/Archive.tsx` | **N** | Medium | Archive management UI |
| 12 | `src/frontend/src/components/archive/TimelineView.tsx` | **N** | Low | Visual timeline of archive coverage |
| 13 | `src/frontend/src/components/archive/BackfillModal.tsx` | **N** | Low | Backfill configuration dialog |
| 14 | `src/frontend/src/components/archive/GapIndicator.tsx` | **N** | Low | Gap visualization component |
| 15 | `src/config/archive.py` | **N** | Low | Archive configuration schema |
| 16 | `src/scheduling/executor.py` | **M** | Low | Hook for auto-archive after scheduled run |
| 17 | `tests/unit/test_archive_*.py` | **N** | — | Unit tests for archive module |
| 18 | `tests/integration/test_retrospective.py` | **N** | — | Integration tests for generation |

**Totals:** 2 files modified, 16 files created.

---

## 11. Edge Cases and Mitigations

| Edge Case | Mitigation |
|-----------|------------|
| Channel deleted, history inaccessible | Mark as `CHANNEL_DELETED` in meta; not backfill eligible |
| Very long time range (years) | Paginate generation; show progress; allow pause/resume |
| Rate limits during batch generation | Exponential backoff; queue remaining; report partial progress |
| Conflicting timezone changes | Store canonical UTC times; convert on display |
| Large channels (10k+ messages/day) | Chunk processing; cache intermediate results |
| Prompt changes mid-backfill | Lock prompt version for job duration; note in manifest |
| Google Drive quota exceeded | Fail gracefully; queue for retry; notify user |
| Concurrent backfill jobs | Queue system; prevent duplicate date processing |
| Archive folder renamed/moved | Manifest references by ID, not path; rescan on load |

---

## 12. Security Considerations

1. **Message Access Permissions** — Retrospective generation requires historical message access. Verify bot had permissions during target period.

2. **Google Drive Credentials** — Service account keys stored securely; never in archive folder.

3. **Sensitive Content** — Same content filtering as real-time summaries applies to retrospective generation.

4. **Archive Access Control** — Archive files may contain summarized private conversations. Protect archive folder with appropriate filesystem permissions.

5. **API Key Usage** — Batch retrospective generation can consume significant API quota. Implement cost estimation and confirmation.

---

## 13. Implementation Phases

### Phase 1 — Core Archive Structure (3-4 days)
- [ ] Define archive folder structure and manifest schemas
- [ ] Implement `ArchiveWriter` for Markdown generation
- [ ] Implement `PromptTracker` for checksum management
- [ ] Create metadata file generation

### Phase 2 — Retrospective Generation (3-4 days)
- [ ] Implement `RetrospectiveGenerator` service
- [ ] Add historical message fetching with pagination
- [ ] Create job queue for batch processing
- [ ] Add progress tracking and reporting

### Phase 3 — Backfill Analysis (2-3 days)
- [ ] Implement `ArchiveScanner` for gap detection
- [ ] Create `BackfillAnalyzer` for recommendations
- [ ] Add prompt version comparison logic
- [ ] Generate backfill reports

### Phase 4 — API Endpoints (2 days)
- [ ] Add `/archive/generate` endpoint
- [ ] Add `/archive/status` endpoint
- [ ] Add `/archive/backfill-report` endpoint
- [ ] Add `/archive/download` endpoint

### Phase 5 — Google Drive Sync (2-3 days)
- [ ] Implement Google Drive API integration
- [ ] Add incremental sync logic
- [ ] Handle conflicts and errors
- [ ] Add sync status to manifest

### Phase 6 — Frontend UI (3-4 days)
- [ ] Create Archive page with server/channel browser
- [ ] Build Timeline visualization component
- [ ] Create Backfill configuration modal
- [ ] Add sync status and controls

### Phase 7 — Testing & Polish (2-3 days)
- [ ] Unit tests for all archive components
- [ ] Integration tests for generation workflow
- [ ] E2E tests for UI
- [ ] Documentation and examples

---

## 14. Future Extensions

| Extension | Description |
|-----------|-------------|
| **S3/Azure Blob Sync** | Additional cloud storage providers |
| **Archive Search** | Full-text search across archived summaries |
| **Archive Export** | Export to PDF, EPUB, or static HTML site |
| **Diff View** | Compare summaries across different prompt versions |
| **Archive Sharing** | Generate shareable links with optional auth |
| **Scheduled Archive** | Automatically archive to Drive on schedule |
| **Multi-Server Archives** | Cross-server archive management |
| **Archive Analytics** | Trends, statistics, and insights across archive |

---

## 15. Consequences

### Positive
- **Historical Coverage**: Communities can document their entire history
- **Portable Archives**: Human-readable Markdown works everywhere
- **Version Tracking**: Know exactly what configuration generated each summary
- **Smart Backfill**: Intelligently fill gaps without manual tracking
- **External Backup**: Google Drive sync provides redundancy

### Negative
- **Storage Requirements**: Full archives can grow large (estimate: ~50KB/day/channel)
- **API Costs**: Retrospective generation for long periods can be expensive
- **Complexity**: More configuration options and workflows to learn

### Trade-offs
- **Markdown vs. Database**: Chose Markdown for portability and human readability, sacrificing query performance
- **Granularity**: Support multiple granularities adds complexity but enables flexibility
- **Checksum Scope**: Include all prompt-affecting config in checksum; may flag more "outdated" than necessary

---

## 16. References

- [ADR-004: Grounded Summary References](./004-grounded-summary-references.md) — Citation format
- [ADR-005: Summary Delivery Destinations](./005-summary-delivery-destinations.md) — Storage model
- [ISO 8601 Date Format](https://en.wikipedia.org/wiki/ISO_8601) — Date naming standard
- [Google Drive API](https://developers.google.com/drive/api) — Sync integration
- [Discord Message History](https://discord.com/developers/docs/resources/channel#get-channel-messages) — Historical fetch limits
