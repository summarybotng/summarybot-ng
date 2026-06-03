# SummaryBot-NG: Product Requirements Document for Complete Rewrite

**Version**: 2.0 (Rewrite)
**Date**: 2026-06-02
**Status**: Draft
**Methodology**: SPARC (Specification, Pseudocode, Architecture, Refinement, Completion)

---

## Executive Summary

This PRD defines the complete requirements for a ground-up rewrite of SummaryBot-NG, a multi-platform conversation summarization system. The rewrite addresses critical technical debt (see `docs/technical-debt.md`) while preserving all 120+ functional requirements from the existing system.

### Why Rewrite?

The current codebase suffers from:
- **God Files**: 5,574-line route files with 46+ endpoints
- **In-Memory State**: Production code using dict-based tracking instead of persistent storage
- **36% Test Coverage**: Critical paths untested
- **Half-Implemented Patterns**: Repository pattern not fully adopted

### Rewrite Goals

1. **Modular Architecture**: No file > 500 lines, single responsibility per module
2. **100% Repository Pattern**: Business logic in services, routes are thin adapters
3. **80%+ Test Coverage**: TDD for all new code
4. **Production-Ready State Management**: All state in database, Redis for ephemeral
5. **Clean API Contracts**: OpenAPI-first design

---

## Table of Contents

1. [Core Features](#1-core-features)
2. [Multi-Platform Support](#2-multi-platform-support)
3. [Scheduling System](#3-scheduling-system)
4. [Delivery System](#4-delivery-system)
5. [Dashboard & Web API](#5-dashboard--web-api)
6. [Authentication & Authorization](#6-authentication--authorization)
7. [Data Architecture](#7-data-architecture)
8. [Knowledge Management](#8-knowledge-management)
9. [External Integrations](#9-external-integrations)
10. [Error Handling & Observability](#10-error-handling--observability)
11. [New Architecture Design](#11-new-architecture-design)
12. [Implementation Roadmap](#12-implementation-roadmap)

---

## 1. Core Features

### 1.1 AI-Powered Summary Generation

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| SUM-001 | Generate summaries using LLM (Claude via OpenRouter) | Critical | Core functionality |
| SUM-002 | Support three lengths: BRIEF, DETAILED, COMPREHENSIVE | Critical | Model selection varies by length |
| SUM-003 | Extract key points from conversations | Critical | |
| SUM-004 | Extract action items with assignee, priority, deadline | Critical | |
| SUM-005 | Extract technical terms with definitions | High | |
| SUM-006 | Analyze participant contributions | High | Message counts, contribution scores |
| SUM-007 | Support custom system prompts per guild | High | ADR-034 |
| SUM-008 | Support perspectives (general, developer, executive, support) | Medium | |
| SUM-009 | Include grounded citations [N] linking to source messages | High | ADR-004 |
| SUM-010 | Extract knowledge units for RuVector storage | Medium | ADR-090 |
| SUM-011 | Handle model fallback with retry chain | High | |
| SUM-012 | Track generation metrics (attempts, cost, latency) | Medium | |
| SUM-013 | Cache summaries with hash-based invalidation | Medium | |
| SUM-014 | Respect minimum message threshold (default 5) | High | |
| SUM-015 | Handle prompt length optimization for token limits | High | |

**Non-Functional Requirements**:
- Response time: < 30 seconds for < 1000 messages
- Cost cap per generation: Configurable (default $0.50)
- Max retry attempts: Configurable (default 5)

### 1.2 Message Processing

| ID | Requirement | Priority |
|----|-------------|----------|
| MSG-001 | Process Discord messages (mentions, emojis, embeds, attachments) | Critical |
| MSG-002 | Process WhatsApp messages (voice transcripts, forwards, replies) | High |
| MSG-003 | Process Slack messages (threads, reactions, files) | High |
| MSG-004 | Clean platform-specific formatting | High |
| MSG-005 | Extract code blocks with language detection | Medium |
| MSG-006 | Handle attachments (images, videos, audio, documents) | High |
| MSG-007 | Support thread context | High |
| MSG-008 | Identify substantial vs trivial content | Medium |
| MSG-009 | Support multi-channel message aggregation | High |

---

## 2. Multi-Platform Support

### 2.1 Discord Integration

| ID | Requirement | Priority |
|----|-------------|----------|
| DIS-001 | Connect using bot token with required intents | Critical |
| DIS-002 | Register/sync slash commands globally and per-guild | Critical |
| DIS-003 | Fetch message history with time range | Critical |
| DIS-004 | Support category-based channel grouping | High |
| DIS-005 | Support guild-wide summarization | High |
| DIS-006 | Send summary embeds | High |
| DIS-007 | Send markdown summaries | Medium |
| DIS-008 | Create threads for detailed delivery | Medium |
| DIS-009 | Send direct messages | Medium |
| DIS-010 | Check bot permissions in channels | High |

### 2.2 Slack Integration

| ID | Requirement | Priority |
|----|-------------|----------|
| SLK-001 | OAuth2 authentication flow | Critical |
| SLK-002 | Encrypted token storage | Critical |
| SLK-003 | List public/private channels | High |
| SLK-004 | Fetch channel message history with pagination | High |
| SLK-005 | Fetch thread replies | High |
| SLK-006 | Get user display names | High |
| SLK-007 | Handle rate limiting with retry-after | High |
| SLK-008 | Support multiple scope tiers | Medium |

### 2.3 WhatsApp Integration

| ID | Requirement | Priority |
|----|-------------|----------|
| WHA-001 | API endpoint for chat export ingestion | High |
| WHA-002 | Parse WhatsApp message format | High |
| WHA-003 | Handle voice note transcriptions (Whisper) | Medium |
| WHA-004 | Handle forwarded message markers | Medium |
| WHA-005 | Preserve reply chains | Medium |
| WHA-006 | Never expose phone numbers in outputs | Critical |
| WHA-007 | List ingested chats with statistics | Medium |
| WHA-008 | API key authentication for ingest | High |

---

## 3. Scheduling System

### 3.1 Task Scheduling

| ID | Requirement | Priority |
|----|-------------|----------|
| SCH-001 | Support schedule types: ONCE, FIFTEEN_MINUTES, HOURLY, EVERY_4_HOURS, DAILY, WEEKLY, HALF_WEEKLY, MONTHLY, CUSTOM | Critical |
| SCH-002 | Schedule time in HH:MM format | High |
| SCH-003 | Day-of-week selection (0=Monday to 6=Sunday) | High |
| SCH-004 | Timezone-aware scheduling | High |
| SCH-005 | Persist tasks to database | Critical |
| SCH-006 | Restore tasks on server restart | Critical |
| SCH-007 | Grace period for missed executions (1 hour) | High |
| SCH-008 | Auto-disable after max_failures (default 3) | High |
| SCH-009 | Skip when insufficient messages | High |
| SCH-010 | Track run/failure counts and timestamps | High |
| SCH-011 | Pause/resume tasks | Medium |
| SCH-012 | Delete tasks | Medium |
| SCH-013 | Update task configuration | Medium |

### 3.2 Summary Scope Types (ADR-011)

| ID | Requirement | Priority |
|----|-------------|----------|
| SCP-001 | CHANNEL scope: Single or multiple channels | Critical |
| SCP-002 | CATEGORY scope: All channels in category | High |
| SCP-003 | GUILD scope: All accessible channels | High |
| SCP-004 | Support excluded_channel_ids | High |
| SCP-005 | Runtime channel resolution | High |
| SCP-006 | Category mode: combined or individual | Medium |

### 3.3 Rolling Period Summaries (ADR-101)

| ID | Requirement | Priority |
|----|-------------|----------|
| ROL-001 | Support weekly, biweekly, monthly periods | Medium |
| ROL-002 | Accumulate content across runs | Medium |
| ROL-003 | Finalize on period end day | Medium |
| ROL-004 | Track accumulation count and raw segments | Medium |
| ROL-005 | Support strategies: append, resummarize, hybrid | Medium |
| ROL-006 | Deliver intermediate updates | Low |

### 3.4 Lookback Period (ADR-089)

| ID | Requirement | Priority |
|----|-------------|----------|
| LBK-001 | Configurable time_range_hours per schedule | High |
| LBK-002 | Fetch messages from (now - hours) to now | High |

---

## 4. Delivery System

### 4.1 Delivery Destinations

| ID | Requirement | Priority |
|----|-------------|----------|
| DEL-001 | DISCORD_CHANNEL: Deliver to text channel | Critical |
| DEL-002 | DISCORD_DM: Deliver via direct message | Medium |
| DEL-003 | WEBHOOK: POST to external URL | High |
| DEL-004 | EMAIL: Send via SMTP | Medium |
| DEL-005 | DASHBOARD: Store for web viewing | Critical |
| DEL-006 | CONFLUENCE: Publish to Atlassian Confluence | Medium |
| DEL-007 | Support multiple destinations per schedule | High |
| DEL-008 | Enable/disable individual destinations | High |
| DEL-009 | Track delivery results | High |

### 4.2 Delivery Formats

| ID | Requirement | Priority |
|----|-------------|----------|
| FMT-001 | embed: Discord rich embed | High |
| FMT-002 | markdown: Plain markdown | High |
| FMT-003 | template: ADR-014 with thread creation | Medium |
| FMT-004 | json: Raw JSON for webhooks | Low |

---

## 5. Dashboard & Web API

### 5.1 Summary Management

| ID | Requirement | Priority |
|----|-------------|----------|
| DSH-001 | Store summaries with full SummaryResult | Critical |
| DSH-002 | List with pagination and filtering | Critical |
| DSH-003 | View details (participants, key points, actions) | Critical |
| DSH-004 | Full-text search | High |
| DSH-005 | Search by participant | Medium |
| DSH-006 | Previous/next navigation | Medium |
| DSH-007 | Pin/unpin summaries | Medium |
| DSH-008 | Archive/unarchive | Medium |
| DSH-009 | Add/remove tags | Medium |
| DSH-010 | Push to Discord from dashboard | High |
| DSH-011 | Push to email | Medium |
| DSH-012 | Push to Confluence | Medium |
| DSH-013 | Bulk delete | Medium |
| DSH-014 | Bulk regenerate | Low |
| DSH-015 | Track view timestamp | Low |
| DSH-016 | Track push history | Medium |

### 5.2 Schedule Management

| ID | Requirement | Priority |
|----|-------------|----------|
| SCM-001 | List schedules for guild | Critical |
| SCM-002 | Create schedule with wizard | Critical |
| SCM-003 | Update schedule | High |
| SCM-004 | Delete schedule | High |
| SCM-005 | View execution history | High |
| SCM-006 | View next run time | High |
| SCM-007 | Trigger immediate execution | Medium |
| SCM-008 | Pause/resume | Medium |

### 5.3 Job Tracking (ADR-013)

| ID | Requirement | Priority |
|----|-------------|----------|
| JOB-001 | Track status: PENDING, RUNNING, COMPLETED, FAILED, PAUSED, CANCELLED | High |
| JOB-002 | Track type: SCHEDULED, ON_DEMAND | High |
| JOB-003 | Track progress (current/total steps) | Medium |
| JOB-004 | List active jobs | High |
| JOB-005 | Mark interrupted as PAUSED on restart | High |
| JOB-006 | Cleanup old jobs | Low |

---

## 6. Authentication & Authorization

### 6.1 Authentication

| ID | Requirement | Priority |
|----|-------------|----------|
| AUTH-001 | Discord OAuth2 login | Critical |
| AUTH-002 | JWT token with expiration | Critical |
| AUTH-003 | Validate guild access | Critical |
| AUTH-004 | Check admin status for management | High |
| AUTH-005 | API key auth for integrations | Medium |

### 6.2 Permissions

| ID | Requirement | Priority |
|----|-------------|----------|
| PRM-001 | Permission levels: NONE, SUMMARIZE, SCHEDULE, ADMIN | High |
| PRM-002 | Role-based assignment | High |
| PRM-003 | User-specific assignment | High |
| PRM-004 | Channel access control | High |
| PRM-005 | Command-level checks | High |
| PRM-006 | Permission caching | Medium |
| PRM-007 | Optional enforcement flag | High |

---

## 7. Data Architecture

### 7.1 Core Data Models

#### SummaryResult
```python
class SummaryResult:
    id: str                           # UUID
    channel_id: str
    guild_id: str
    start_time: datetime
    end_time: datetime
    message_count: int
    summary_text: str
    key_points: List[str]
    action_items: List[ActionItem]
    technical_terms: List[TechnicalTerm]
    participants: List[Participant]
    metadata: Dict[str, Any]          # model, tokens, cost
    referenced_key_points: List[ReferencedClaim]  # ADR-004
    reference_index: List[SummaryReference]
    knowledge_units: List[KnowledgeUnit]  # ADR-090
```

#### StoredSummary
```python
class StoredSummary:
    id: str
    guild_id: str
    source_channel_ids: List[str]
    schedule_id: Optional[str]
    schedule_name_snapshot: Optional[str]  # ADR-109
    summary_result: SummaryResult
    source: SummarySource              # realtime, scheduled, archive
    title: str
    is_pinned: bool
    is_archived: bool
    tags: List[str]
    push_deliveries: List[PushDelivery]
    wiki_ingested: bool                # ADR-067
    vector_ingested: bool              # ADR-093
    scope_type: Optional[str]          # ADR-098
    rolling_period_type: Optional[str] # ADR-101
    created_at: datetime
```

#### ScheduledTask
```python
class ScheduledTask:
    id: str
    name: str
    guild_id: str
    channel_ids: List[str]
    schedule_type: ScheduleType
    schedule_time: Optional[str]
    schedule_days: List[int]
    timezone: str
    destinations: List[Destination]
    summary_options: SummaryOptions
    scope: SummaryScope                # ADR-011
    category_id: Optional[str]
    excluded_channel_ids: List[str]
    prompt_template_id: Optional[str]  # ADR-034
    enable_continuity: bool            # ADR-087
    time_range_hours: int              # ADR-089
    rolling_period: Optional[str]      # ADR-101
    is_active: bool
    run_count: int
    failure_count: int
```

#### SummaryJob
```python
class SummaryJob:
    id: str
    guild_id: str
    job_type: JobType
    status: JobStatus
    scope: Optional[str]
    channel_ids: List[str]
    progress_current: int
    progress_total: int
    cost_usd: float
    error: Optional[str]
    created_at: datetime
```

#### ProcessedMessage
```python
class ProcessedMessage:
    id: str
    author_name: str
    author_id: str
    content: str
    timestamp: datetime
    source_type: SourceType            # discord, slack, whatsapp
    thread_info: Optional[ThreadInfo]
    attachments: List[AttachmentInfo]
    code_blocks: List[CodeBlock]
    channel_id: Optional[str]
```

### 7.2 Repository Pattern (Full Implementation)

| Repository | Model | Status |
|------------|-------|--------|
| SummaryRepository | SummaryResult | Exists |
| StoredSummaryRepository | StoredSummary | Exists |
| TaskRepository | ScheduledTask, TaskResult | Exists |
| ConfigRepository | GuildConfig | Exists |
| ErrorRepository | ErrorLog | Exists |
| SummaryJobRepository | SummaryJob | Exists |
| PromptTemplateRepository | GuildPromptTemplate | Exists |
| FeedRepository | FeedConfig | Exists |
| IngestRepository | IngestDocument | Exists |

**NEW: Service Layer** (currently missing)

```
services/
├── summary_service.py          # Summary generation business logic
├── schedule_service.py         # Schedule management logic
├── delivery_service.py         # Multi-destination delivery
├── job_service.py              # Job lifecycle management
├── permission_service.py       # Permission checks
└── confluence_service.py       # Confluence publishing
```

---

## 8. Knowledge Management

### 8.1 RuVector Knowledge Units (ADR-057, ADR-090)

| ID | Requirement | Priority |
|----|-------------|----------|
| KNO-001 | Extract units during summarization | Medium |
| KNO-002 | Generate embeddings for semantic search | Medium |
| KNO-003 | Store in vector database | Medium |
| KNO-004 | Track ingestion status | Low |
| KNO-005 | Query by semantic similarity | Low |

### 8.2 Wiki Synthesis (ADR-067)

| ID | Requirement | Priority |
|----|-------------|----------|
| WIK-001 | Ingest summaries to wiki structure | Low |
| WIK-002 | Track ingestion status | Low |
| WIK-003 | Regenerate wiki pages | Low |

---

## 9. External Integrations

### 9.1 Confluence Publishing (ADR-099)

| ID | Requirement | Priority |
|----|-------------|----------|
| CFL-001 | Per-guild Confluence configuration | Medium |
| CFL-002 | Publish as Confluence pages | Medium |
| CFL-003 | Template-based titles | Medium |
| CFL-004 | Add labels (scope, category, channels) | Low |
| CFL-005 | Track publication status | Medium |
| CFL-006 | Bulk publish/unpublish | Low |

### 9.2 Email Delivery (ADR-030)

| ID | Requirement | Priority |
|----|-------------|----------|
| EML-001 | SMTP server configuration | Medium |
| EML-002 | Send summaries to email | Medium |
| EML-003 | HTML formatting | Medium |
| EML-004 | Track delivery status | Medium |

### 9.3 Webhook Delivery

| ID | Requirement | Priority |
|----|-------------|----------|
| WHK-001 | POST JSON to configured URL | High |
| WHK-002 | Include auth headers | Medium |
| WHK-003 | Track status and retry | Medium |

---

## 10. Error Handling & Observability

### 10.1 Error Tracking

| ID | Requirement | Priority |
|----|-------------|----------|
| ERR-001 | Capture errors with type, severity, context | High |
| ERR-002 | Error types: SUMMARIZATION, PERMISSION, SCHEDULE, FALLBACK | High |
| ERR-003 | Severity levels: INFO, WARNING, ERROR, CRITICAL | High |
| ERR-004 | Query by guild, type, severity | High |
| ERR-005 | Resolve with notes | Medium |
| ERR-006 | Bulk resolve by type | Low |
| ERR-007 | Auto-cleanup old errors | Low |
| ERR-008 | Consolidated access tracking (ADR-041) | Medium |

### 10.2 Audit Logging (ADR-045)

| ID | Requirement | Priority |
|----|-------------|----------|
| AUD-001 | Log command executions | Medium |
| AUD-002 | Log scheduled task executions | Medium |
| AUD-003 | Sanitize sensitive data | High |

---

## 11. New Architecture Design

### 11.1 Directory Structure

```
src/
├── api/                          # HTTP layer (thin routes)
│   ├── routes/
│   │   ├── summaries/
│   │   │   ├── __init__.py
│   │   │   ├── crud.py           # ~200 lines
│   │   │   ├── search.py         # ~150 lines
│   │   │   ├── bulk.py           # ~200 lines
│   │   │   ├── delivery.py       # ~300 lines
│   │   │   ├── confluence.py     # ~250 lines
│   │   │   └── jobs.py           # ~200 lines
│   │   ├── schedules/
│   │   ├── archive/
│   │   ├── wiki/
│   │   └── auth/
│   ├── middleware/
│   └── deps.py
│
├── services/                     # Business logic layer
│   ├── summary/
│   │   ├── generation.py         # Core generation
│   │   ├── extraction.py         # Key points, actions
│   │   └── grounding.py          # Citation references
│   ├── scheduling/
│   │   ├── executor.py           # Task execution
│   │   ├── scheduler.py          # APScheduler wrapper
│   │   └── rolling.py            # Rolling period logic
│   ├── delivery/
│   │   ├── base.py               # Abstract delivery
│   │   ├── discord.py
│   │   ├── email.py
│   │   ├── webhook.py
│   │   └── confluence.py
│   └── auth/
│
├── domain/                       # Domain models
│   ├── summary.py
│   ├── schedule.py
│   ├── job.py
│   └── message.py
│
├── data/                         # Data access layer
│   ├── repositories/
│   │   ├── base.py
│   │   ├── summary.py
│   │   ├── schedule.py
│   │   └── job.py
│   ├── migrations/
│   └── connection.py
│
├── platforms/                    # Platform adapters
│   ├── discord/
│   │   ├── bot.py
│   │   ├── commands.py
│   │   └── events.py
│   ├── slack/
│   │   ├── client.py
│   │   └── oauth.py
│   └── whatsapp/
│       └── ingest.py
│
├── wiki/                         # Knowledge management
│   ├── ruvector/
│   └── synthesis/
│
└── shared/                       # Cross-cutting concerns
    ├── config.py
    ├── logging.py
    ├── errors.py
    └── cache.py
```

### 11.2 Key Architectural Principles

1. **Thin Routes**: Routes only parse requests and call services
2. **Fat Services**: Business logic lives in service layer
3. **Repository Isolation**: All DB access through repositories
4. **Dependency Injection**: Use FastAPI `Depends()` for all dependencies
5. **State in Database**: No in-memory dict tracking in production code
6. **Event-Driven Updates**: SSE/WebSocket for real-time UI updates

### 11.3 State Management Migration

| Current (In-Memory) | New (Persistent) |
|---------------------|------------------|
| `_generation_tasks: dict` | `SummaryJobRepository` |
| `session_store: dict` | Redis or database sessions |
| `event_queues: dict` | Redis pub/sub |

### 11.4 Testing Strategy

| Layer | Test Type | Coverage Target |
|-------|-----------|-----------------|
| Services | Unit tests | 90% |
| Repositories | Integration tests | 80% |
| Routes | Integration tests | 80% |
| Platform adapters | Mock-based unit tests | 70% |

---

## 12. Implementation Roadmap

### Phase 1: Foundation (Week 1-2)

1. Set up new directory structure
2. Migrate domain models to `domain/`
3. Create service layer interfaces
4. Replace in-memory state with repository calls
5. Add missing tests for critical paths

### Phase 2: Route Decomposition (Week 3-4)

1. Split `summaries.py` (5,574 lines → 6 modules)
2. Split `archive.py` (4,051 lines → 5 modules)
3. Split `wiki.py` (2,277 lines → 4 modules)
4. Extract business logic to services

### Phase 3: Service Layer (Week 5-6)

1. Implement `SummaryService`
2. Implement `ScheduleService`
3. Implement `DeliveryService`
4. Implement `JobService`

### Phase 4: Testing & Stabilization (Week 7-8)

1. Add unit tests for all services
2. Add integration tests for repositories
3. Add API contract tests
4. Fix migration numbering gaps

### Phase 5: Knowledge Management (Week 9-10)

1. Refactor RuVector integration
2. Implement coherence gate properly
3. Add wiki synthesis tests

---

## Appendix A: Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| DISCORD_TOKEN | Yes | Discord bot token |
| OPENROUTER_API_KEY | Yes | LLM API key |
| DATABASE_URL | Yes | SQLite/PostgreSQL connection |
| JWT_SECRET | Yes | Dashboard JWT secret |
| REDIS_URL | No | Redis for sessions/events |
| INGEST_API_KEY | No | WhatsApp ingest auth |
| SMTP_* | No | Email configuration |
| SLACK_CLIENT_* | No | Slack OAuth |
| CONFLUENCE_* | No | Confluence integration |

---

## Appendix B: API Endpoint Summary

### Summary Management
- `GET /guilds/{guild_id}/summaries` - List
- `GET /guilds/{guild_id}/summaries/{id}` - Detail
- `POST /guilds/{guild_id}/summaries/generate` - Generate
- `POST /guilds/{guild_id}/summaries/{id}/push` - Push
- `DELETE /guilds/{guild_id}/summaries/{id}` - Delete

### Schedule Management
- `GET /guilds/{guild_id}/schedules` - List
- `POST /guilds/{guild_id}/schedules` - Create
- `PATCH /guilds/{guild_id}/schedules/{id}` - Update
- `DELETE /guilds/{guild_id}/schedules/{id}` - Delete
- `POST /guilds/{guild_id}/schedules/{id}/execute` - Trigger

### Archive
- `GET /archive/sources` - List sources
- `POST /archive/generate` - Start retrospective
- `GET /archive/jobs/{id}` - Job status

### Wiki
- `GET /guilds/{guild_id}/wiki/pages` - List pages
- `GET /guilds/{guild_id}/wiki/search` - Search
- `POST /guilds/{guild_id}/wiki/pages/{path}/synthesize` - Synthesize

### RuVector
- `GET /ruvector/guilds/{guild_id}/search` - Semantic search
- `GET /ruvector/guilds/{guild_id}/graph` - Knowledge graph

---

## Appendix C: Referenced ADRs

| ADR | Title | Status |
|-----|-------|--------|
| ADR-004 | Grounded Summary References | Implemented |
| ADR-005 | Summary Delivery Destinations | Implemented |
| ADR-008 | Unified Summary Experience | Implemented |
| ADR-011 | Unified Scope Selection | Implemented |
| ADR-013 | Unified Job Tracking | Implemented |
| ADR-014 | Push Templates | Implemented |
| ADR-030 | Email Delivery | Implemented |
| ADR-034 | Guild Prompt Templates | Implemented |
| ADR-045 | Audit Logging | Implemented |
| ADR-057 | RuVector Knowledge Units | Implemented |
| ADR-067 | Wiki Synthesis | Implemented |
| ADR-079 | Multi-Tenancy | Implemented |
| ADR-087 | Weekly Continuity | Implemented |
| ADR-089 | Lookback Period | Implemented |
| ADR-090 | Vector Ingestion | Implemented |
| ADR-099 | Confluence Publishing | Implemented |
| ADR-101 | Rolling Period Summaries | Implemented |
| ADR-111 | Confluence Auto-Publish | Implemented |
| ADR-118 | RuVector Deduplication | Implemented |

---

## 13. Future Requirements (Proposed but Unimplemented)

This section captures features that were discussed, planned, or documented in ADRs but **never implemented**. These represent the product vision beyond the current implementation.

> **Important**: A new build from this PRD should consider these requirements for inclusion, as they represent stakeholder intent that was not captured in the existing codebase.

---

### 13.1 Platform-Agnostic Architecture (ADR-066)

**Status**: Proposed (Never Implemented)
**Priority**: HIGH - Critical for enterprise adoption
**Stakeholder Request**: "Allow organizations that don't run Discord to use the system (e.g., Slack-only)"

#### Problem Statement
The current system requires Discord:
- Login requires Discord OAuth
- All entities keyed by `guild_id` (Discord term)
- Cannot onboard Slack-only organizations

#### Proposed Solution

| Current | Future |
|---------|--------|
| `guild_id` everywhere | `workspace_id` (platform-agnostic) |
| Discord OAuth only | Discord, Slack, Google, Email login |
| "Guild" terminology | "Workspace" terminology |
| Discord bot required | Optional platform connections |

#### Key Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FUT-001 | Support authentication without Discord (email magic link, Google SSO) | Critical |
| FUT-002 | Replace `guild_id` with `workspace_id` throughout | Critical |
| FUT-003 | Allow workspaces with Slack-only connections | High |
| FUT-004 | Support cross-platform workspaces (Discord + Slack in one) | Medium |
| FUT-005 | Unified user identity across platforms | Medium |
| FUT-006 | Platform adapter pattern for fetchers | High |

#### Data Model Changes
```sql
-- New workspace model (replaces guild-centric design)
CREATE TABLE workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE workspace_connections (
    workspace_id TEXT NOT NULL,
    platform TEXT NOT NULL,  -- discord, slack, whatsapp
    platform_id TEXT NOT NULL,  -- guild_id, team_id, etc.
    UNIQUE (platform, platform_id)
);
```

---

### 13.2 WhatsApp Live Message Retrieval (ADR-053)

**Status**: Rejected (API Limitations)
**Priority**: BLOCKED
**Stakeholder Request**: "Retrieve messages from WhatsApp using Baileys or similar"

#### Why Rejected

| Capability | Discord/Slack | WhatsApp |
|------------|---------------|----------|
| Fetch historical messages | ✅ | ❌ |
| On-demand time-range queries | ✅ | ❌ |
| API-based retrieval | ✅ | ❌ (push-only) |

WhatsApp Cloud API is **push-only** - you receive webhooks but cannot query "give me messages from the last 24 hours."

#### Alternatives Considered

| Approach | Status | Risk |
|----------|--------|------|
| File import (current) | ✅ Implemented | Manual user action |
| Webhook streaming | ✅ Implemented | Only future messages |
| Third-party APIs (Baileys, whapi.cloud) | ❌ Rejected | TOS violations, account bans |

#### Requirements (If Unblocked)

| ID | Requirement | Status |
|----|-------------|--------|
| FUT-007 | WhatsApp live message fetching | BLOCKED |
| FUT-008 | WhatsApp scheduled summaries (like Discord) | BLOCKED |
| FUT-009 | WhatsApp group selection in wizard | BLOCKED |

---

### 13.3 Subdomain Multi-Tenancy (ADR-079)

**Status**: Proposed (Partial Implementation)
**Priority**: HIGH - Required for white-label deployments

#### Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FUT-010 | Custom subdomains per tenant (acme.summarybot.app) | High |
| FUT-011 | Custom domains with verification | Medium |
| FUT-012 | Tenant branding (logo, colors, app name) | Medium |
| FUT-013 | Tenant member management (invites, roles) | High |
| FUT-014 | Workspace linking to tenants | High |
| FUT-015 | Tenant-scoped OAuth redirects | High |

---

### 13.4 RuVector Full Integration Vision (ADR-052)

**Status**: Proposed (Partial - Only basic vector search implemented)
**Priority**: MEDIUM - Advanced knowledge features

#### Proposed Phases

| Phase | Feature | Status |
|-------|---------|--------|
| Phase 1 | Semantic summary search | ✅ Implemented |
| Phase 2 | Conversation graph analysis (GNN) | ❌ Not implemented |
| Phase 3 | QE agent memory persistence | ❌ Not implemented |
| Phase 4 | Self-learning query optimization (SONA) | ❌ Not implemented |
| Phase 5 | Edge deployment (rvLite) | ❌ Not implemented |

#### Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FUT-016 | GNN-based conversation topology modeling | Low |
| FUT-017 | Cross-session agent memory via RuVector | Medium |
| FUT-018 | Query pattern optimization (self-learning) | Low |
| FUT-019 | Local/offline summarization (rvLite) | Low |
| FUT-020 | Coherence gate for hallucination prevention | Medium |

---

### 13.5 AI Wiki Curator Agent (ADR-077)

**Status**: Proposed (Not Implemented)
**Priority**: MEDIUM - Quality automation

#### Problem Statement
The compounding wiki accumulates content but needs curation:
- Low-quality pages with sparse content
- Duplicate topics ("auth" vs "authentication")
- Stale content
- Missing cross-references

#### Proposed Agent Skills

| Skill | Purpose |
|-------|---------|
| `topic_merger` | Merge similar/duplicate topics |
| `quality_assessor` | Score pages, flag issues |
| `cross_linker` | Add bidirectional links |
| `contradiction_resolver` | Detect and resolve conflicts |
| `content_pruner` | Remove stale content |
| `gap_detector` | Identify missing topics |

#### Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FUT-021 | AI agent for wiki curation | Medium |
| FUT-022 | Automatic topic merging | Medium |
| FUT-023 | Quality scoring for wiki pages | Low |
| FUT-024 | Automated cross-reference linking | Low |
| FUT-025 | Contradiction detection and resolution | Medium |

---

### 13.6 Knowledge Base Enhancement Agents (ADR-055)

**Status**: Proposed (Depends on ADR-056/057)
**Priority**: LOW - Advanced features

#### Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FUT-026 | Signal classification (tag by knowledge type) | Low |
| FUT-027 | Expertise mapping (who knows what) | Low |
| FUT-028 | Knowledge gap detection | Low |
| FUT-029 | Provenance tracking (claim → source) | Medium |

---

### 13.7 Additional Proposed Features

#### From Various ADRs

| ID | Requirement | ADR | Status |
|----|-------------|-----|--------|
| FUT-030 | Custom user-defined perspectives | ADR-033 | Proposed |
| FUT-031 | Self-healing parameter validation | ADR-038 | Proposed |
| FUT-032 | Content coverage tracking & backfill | ADR-072 | Proposed |
| FUT-033 | Adaptive summary granularity | ADR-096 | Proposed |
| FUT-034 | Channel accessibility display | ADR-097 | Proposed |
| FUT-035 | Summary deduplication | ADR-071 | Proposed |
| FUT-036 | Email landing pages | ADR-032 | Proposed |
| FUT-037 | Wiki external sync (Notion, Confluence) | ADR-059 | Proposed |
| FUT-038 | WhatsApp coverage gap awareness | ADR-112 | Proposed |
| FUT-039 | Google Workspace group-based admin | ADR-050 | Proposed |
| FUT-040 | Summary deep linking | ADR-015 | Proposed |

---

### 13.8 Partially Implemented Features

These features have some implementation but are incomplete:

| ID | Requirement | ADR | Status |
|----|-------------|-----|--------|
| PART-001 | Soft-fail channel permissions | ADR-041 | Partial |
| PART-002 | Service resilience (Phase 1 only) | ADR-024 | Phase 1 only |
| PART-003 | Simplified scheduling UX (Phases 5-6 pending) | ADR-089 | Phases 1-4 only |

---

### 13.9 Stakeholder Verbal Requests (Not in ADRs)

> **Warning**: These were discussed but never formally documented. Verify with stakeholders before implementing.

| ID | Request | Source | Notes |
|----|---------|--------|-------|
| VERBAL-001 | Slack-only organization support | User discussion | Captured in ADR-066 |
| VERBAL-002 | Baileys-based WhatsApp retrieval | User discussion | Rejected in ADR-053 |
| VERBAL-003 | (Add other verbal requests here) | - | - |

---

## Appendix D: ADR Status Summary

### Implemented (118 ADRs referenced in code)
See Appendix C for key implemented ADRs.

### Proposed but Not Implemented

| ADR | Title | Priority |
|-----|-------|----------|
| ADR-052 | RuVector Integration Vision | Medium |
| ADR-055 | Knowledge Base Agents | Low |
| ADR-056 | Compounding Wiki Standard | Medium |
| ADR-057 | Compounding Wiki RuVector | Medium |
| ADR-058 | Wiki Rendering | Low |
| ADR-059 | Wiki External Sync | Low |
| ADR-060 | Wiki Curation Model | Low |
| ADR-061 | Wiki Population Strategies | Low |
| ADR-063 | Wiki Page Tabs | Low |
| ADR-066 | Platform-Agnostic Architecture | **High** |
| ADR-071 | Summary Deduplication | Medium |
| ADR-072 | Content Coverage Tracking | Medium |
| ADR-077 | AI Wiki Curator Agent | Medium |
| ADR-078 | Platform Agnostic UX | High |
| ADR-079 | Subdomain Multi-Tenancy | **High** |
| ADR-080 | Wiki Perspective Filtering | Low |
| ADR-088 | Unified Scheduling UX | Medium |
| ADR-096 | Adaptive Summary Granularity | Low |
| ADR-097 | Channel Accessibility Display | Low |

### Rejected

| ADR | Title | Reason |
|-----|-------|--------|
| ADR-053 | WhatsApp Live Fetch | API limitations (push-only) |

---

*Generated via SPARC methodology - Phase 1 (Specification) complete.*
*Next: Phase 2 (Pseudocode/Architecture detailed design)*
