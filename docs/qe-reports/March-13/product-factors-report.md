# SFDIPOT Product Factors Assessment: summarybot-ng
**Date:** 2026-03-13
**Analyst:** QE Product Factors Assessor (James Bach HTSM Framework)
**Framework:** SFDIPOT — Structure, Function, Data, Interfaces, Platform, Operations, Time
**Source:** Direct code analysis of /workspaces/summarybot-ng

---

## Executive Summary

**Overall Product Maturity Grade: B+ (78/100)**

summarybot-ng is a production-ready Discord bot for AI-powered message summarization with a companion web dashboard. The codebase demonstrates substantial architectural maturity: structured module boundaries, a layered exception hierarchy, ADR-documented design decisions, automated database migrations, a resilient LLM fallback chain, and multi-platform deployment configurations. These are genuine strengths.

However, several risk areas require attention before the system can be rated higher:

- **Single SQLite file** with a pool_size=1 constraint creates a hard ceiling on concurrent throughput and represents a single point of failure with no replication
- **In-memory cache only** — restart events flush all cached summaries; no Redis-backed distribution means horizontal scaling is blocked
- **JWT secret defaults** are conditionally blocked in production but the development-mode fallback (ephemeral auto-generated secret) is not communicated clearly to operators
- **Timezone handling is UTC-only** in the scheduler; multi-timezone user bases will experience unexpected schedule drift
- **Token comparison for private feeds** uses `!=` (not constant-time equality), creating a timing oracle for feed token enumeration
- **No soft-delete strategy** for summaries — record deletions are permanent, which conflicts with any future audit or compliance posture
- Test suite breadth is good (unit, integration, e2e, performance, security folders all present) but test-to-code ratios for newer modules are unknown without execution

---

## 1. STRUCTURE Analysis

### 1.1 Module Architecture

```
summarybot-ng/
├── src/                         Python backend (~54k lines)
│   ├── main.py                  SummaryBotApp orchestrator (683 lines)
│   ├── __main__.py              Resilient entry point with emergency fallback
│   ├── config/                  BotConfig, GuildConfig, EnvironmentLoader, constants
│   ├── models/                  summary, task, message, feed, error_log, webhook, user ...
│   ├── exceptions/              Typed hierarchy: base, summarization, discord, api, validation, webhook
│   ├── summarization/           ClaudeClient, SummarizationEngine, ResilientSummarizationEngine
│   │                            PromptBuilder, ResponseParser, RetryStrategy, Cache
│   ├── discord_bot/             SummaryBot, CommandRegistry, EventHandler
│   ├── command_handlers/        SummarizeCommandHandler, ConfigCommandHandler,
│   │                            ScheduleCommandHandler, PromptConfigCommandHandler
│   ├── scheduling/              TaskScheduler (APScheduler), TaskExecutor, TaskPersistence
│   ├── permissions/             PermissionManager, PermissionValidator, RoleManager, PermissionCache
│   ├── dashboard/               FastAPI router, auth (OAuth2/JWT), 13 route modules
│   ├── webhook_service/         FastAPI server, rate-limiting, auth, endpoint handlers
│   ├── data/                    Repository factory, SQLite implementations, 18 migrations
│   ├── feeds/                   RSS/Atom generator, WhatsApp ingest handler
│   ├── prompts/                 External GitHub-hosted prompt templates
│   ├── services/                SummaryPush, email delivery
│   ├── archive/                 Archive generator
│   ├── logging/                 CommandLogger, ErrorTracker, CommandLogRepository
│   ├── message_processing/      MessageProcessor
│   ├── templates/               (Jinja2 templates)
│   └── utils/                   time utilities
│
├── src/frontend/                TypeScript SPA (Vite + React implied by config)
│   ├── src/                     Application source
│   ├── tests/                   Playwright E2E tests
│   └── dist/ (build artifact)
│
├── tests/                       Python test suite
│   ├── unit/                    Per-module unit tests
│   ├── integration/             Integration tests
│   ├── e2e/                     E2E test files
│   ├── performance/             Performance test suite
│   └── security/                Security test suite
│
└── Deployment configs
    ├── Dockerfile (multi-stage: node20 → python3.11-slim)
    ├── fly.toml    (Fly.io, Toronto region, 512MB RAM, 1 shared CPU)
    ├── railway.json
    └── render.yaml
```

### 1.2 Dependency Graph (Key Coupling Points)

```
SummaryBotApp
  └─> ConfigManager ─> EnvironmentLoader ─> os.environ
  └─> SummarizationEngine ─> ClaudeClient (OpenRouter/Anthropic)
                           ─> SummaryCache (MemoryCache only)
                           ─> PromptTemplateResolver ─> GuildPromptConfigStore ─> SQLite
  └─> SummaryBot ─> CommandRegistry ─> command_handlers
                 └─> EventHandler
  └─> PermissionManager
  └─> TaskScheduler ─> APScheduler ─> TaskExecutor ─> SummarizationEngine
                    └─> TaskRepository ─> SQLite
  └─> WebhookServer ─> FastAPI ─> DashboardRouter ─> 13 sub-routers
                               └─> SummaryRouter
                               └─> FeedRouter
                               └─> WhatsAppRouter
  └─> CommandLogger ─> CommandLogRepository ─> SQLite (shared connection)
```

### 1.3 Structural Risk Findings

| ID | Finding | Severity | Evidence |
|----|---------|----------|---------|
| S-01 | `src/main.py` exceeds 683 lines; `SummaryBotApp._initialize_*` methods do too much inline | Medium | Lines 106-515 |
| S-02 | `src/dashboard/routes/summaries.py` is 2,732 lines — single-responsibility principle violated | High | File size count |
| S-03 | `SummaryLength` enum duplicated in both `config/settings.py` and `models/summary.py` | Medium | Both files define identical enum |
| S-04 | Circular import risk mitigated by TYPE_CHECKING guards and lazy imports, but `__getattr__` on module level is fragile | Medium | `config/settings.py` lines 16-20 |
| S-05 | Emergency server defined in both `__main__.py` and `main.py` — duplication creates maintenance surface | Low | Both files |
| S-06 | File-based task persistence (`data/tasks/`) coexists with DB persistence — two authoritative stores | Medium | `scheduler.py` lines 686-705 |
| S-07 | `pool_size=1` SQLite constraint documented as intentional but blocks any concurrent write path | High | `main.py` line 168 |

### 1.4 Dependency Health

| Dependency | Version Constraint | Risk |
|-----------|-------------------|------|
| discord.py | >=2.3.0 | No upper bound; major version change could break slash commands |
| anthropic | >=0.5.0 | Very wide range; API client interface may change |
| fastapi | >=0.104.0 | Acceptable |
| aiosqlite | >=0.19.0 | Acceptable |
| apscheduler | >=3.10.0 | APScheduler 4.x is a breaking redesign; constraint allows it |
| pydantic | >=2.5.0 | Acceptable |
| cryptography | >=42.0.0,<47.0.0 | Good — upper bound set |
| redis | >=5.0.0 | Listed as dependency but no Redis code path is activated by default |
| python-jose | >=3.3.0 | python-jose has known security advisories; should pin or replace with PyJWT |

---

## 2. FUNCTION Analysis

### 2.1 Feature Completeness Matrix

| Feature | Status | Notes |
|---------|--------|-------|
| /summarize (channel, time range, message count) | Implemented | Supports `messages`, `hours`, `minutes` params |
| Summary length (brief/detailed/comprehensive) | Implemented | Model routing per length: Haiku → Sonnet 4.5 |
| Perspective filtering (7 types) | Implemented | general, developer, marketing, product, finance, executive, support |
| Cross-channel summary | Implemented | Role-gated via `cross_channel_summary_role_name` |
| Category-wide summary (all channels in category) | Implemented | `combined` and `individual` modes |
| Scheduled summaries | Implemented | APScheduler with DB persistence; once/15min/hourly/4h/daily/weekly/half-weekly/monthly/custom cron |
| Custom prompt templates (GitHub-hosted) | Implemented | Per-guild; Fernet-encrypted token storage |
| Web dashboard | Implemented | OAuth2 + JWT; 13 route groups |
| RSS/Atom feeds | Implemented | ETag + Last-Modified caching |
| WhatsApp ingest | Implemented (ADR-002) | Separate ingest endpoint |
| Webhook integration | Implemented | External delivery, rate-limited |
| Email delivery | Implemented (ADR-030) | SMTP via aiosmtplib |
| Archive generation | Implemented | `archive/generator.py` |
| Retrospective summarization | Implemented | Daily/weekly/monthly granularity |
| Cost estimation | Implemented | Pre-generation cost estimate endpoint |
| Model escalation / retry | Implemented (ADR-024) | 7 retries, $0.50 cost cap, 6-model chain |
| Full-text search on summaries | Implemented (ADR-020) | SQLite FTS5 with porter tokenizer |
| Command logging | Implemented | Async writes with configurable retention |
| Error tracking | Implemented (ADR-031) | Per-request capture, cleanup task |
| Interrupted job recovery | Implemented (ADR-013) | PAUSED status on restart |
| Webhook-only mode (no Discord token) | Implemented | Dashboard API functional without bot |
| Permission management | Implemented | Role + user allow-lists, require_permissions flag |
| /status, /ping, /help, /about | Implemented | Utility commands |
| Redis cache backend | Config exists, not active | CacheConfig.backend="memory" is the only live path |
| Multi-region / horizontal scaling | Not supported | SQLite + in-memory cache prevents it |
| Audit log export | Not found | No endpoint to export command_logs or error_logs |

### 2.2 Error Handling Assessment

The exception hierarchy is well-structured:
```
SummaryBotException
  ├── SummarizationError, InsufficientContentError, PromptTooLongError, TokenLimitExceededError
  ├── ClaudeAPIError → RateLimitError, AuthenticationError, NetworkError, TimeoutError, ModelUnavailableError
  ├── DiscordPermissionError, ChannelAccessError, MessageFetchError, BotPermissionError
  ├── ValidationError, ConfigurationError, InvalidInputError, MissingRequiredFieldError
  └── WebhookError, WebhookAuthError, WebhookDeliveryError
```

**Gaps found:**
- `batch_summarize` in engine.py catches all exceptions and converts to error SummaryResult objects — errors are silently swallowed into the result list without raising; callers may not inspect metadata["error"]
- The `_signal_handler` in `SummaryBotApp` calls `asyncio.create_task(self.stop())` from a synchronous signal handler context — this can fail silently if the event loop is not running at signal receipt time
- `config/_watch_config_file` uses bare `print()` for reload notifications instead of the logger

### 2.3 Security Function Assessment

| Check | Status |
|-------|--------|
| JWT secret blocked in production if insecure | Yes (dashboard/router.py lines 43-57) |
| Fernet encryption key required in production | Yes (dashboard/router.py lines 71-79) |
| Discord token never serialized to config file | Yes (settings.py `to_dict()` returns `***REDACTED***`) |
| Rate limiting on all webhook endpoints | Yes (setup_rate_limiting middleware) |
| CORS restricted to configured origins + dev defaults | Yes |
| Security headers (X-Content-Type, X-Frame-Options, CSP) | Yes (server.py lines 131-160) |
| HSTS only in production | Yes |
| Feed token comparison is NOT constant-time | NO — timing oracle risk (server.py line 364: `token != feed.token`) |
| SQL injection protection (parameterized queries) | Yes (all queries use `?` placeholders) |
| Input length validation for Discord embed fields | Yes (summary.py `to_embed_dict` truncates all fields) |
| `unsafe-eval` in frontend CSP | Present — necessary but widens attack surface |

---

## 3. DATA Analysis

### 3.1 Data Model Overview

**Primary entities and their storage:**

| Entity | Table | Key Columns | Serialization |
|--------|-------|-------------|---------------|
| SummaryResult | `summaries` → `stored_summaries` | id, channel_id, guild_id, start_time, end_time | JSON blobs for arrays |
| GuildConfig | `guild_configs` | guild_id (PK), enabled_channels, permission_settings | JSON blobs |
| ScheduledTask | `scheduled_tasks` | id, guild_id, schedule_type, cron_expression, next_run | JSON blob for destinations |
| TaskResult | `task_results` | execution_id, task_id, status, delivery_results | JSON blob |
| SummaryJob | `summary_jobs` | id, guild_id, job_type, status, progress | JSON for channel_ids, metadata |
| CommandLog | `command_logs` (migration 002) | guild_id, user_id, command, status | Structured |
| GuildPromptConfig | `guild_prompt_configs` (003) | guild_id, encrypted token | Fernet-encrypted |
| Feed | `feeds` (004) | feed_id, guild_id, feed_type, token, is_public | |
| ErrorLog | `error_logs` (006) | error_type, severity, guild_id | JSON details |
| StoredSummary | `stored_summaries` (009/011/012) | id, source, guild_id, summary_text | FTS5 virtual table |
| PushTemplate | `push_templates` (014) | id, guild_id, name, subject_template | Jinja2 |

### 3.2 Schema Migration Assessment

18 numbered SQL migration files (001–018) applied via a migration runner. This is evidence of disciplined schema evolution.

**Migration risks found:**

| ID | Finding | Severity |
|----|---------|----------|
| D-01 | Migration 013 (`fix_stored_summaries_fk.sql`) and 012 (`consolidate_summaries.sql`) suggest earlier FK design was incorrect — indicates schema iteration debt | Medium |
| D-02 | Migration 016 comment: "FTS population and triggers are handled at the application level" — FTS table can be out of sync with base table if save() is bypassed | High |
| D-03 | No DOWN/rollback migrations exist — forward-only schema changes increase deployment risk | High |
| D-04 | JSON blobs used extensively (key_points, action_items, participants, metadata) — no JSONSchema validation at DB layer | Medium |
| D-05 | `summary_fts` virtual table is not populated by triggers; manual insert in repository can be missed in bulk import paths | Medium |

### 3.3 Data Flow Diagram

```
Discord Messages
      |
      v
MessageProcessor (filter, clean, deduplicate)
      |
      v
PromptBuilder (format messages + system prompt + custom template)
      |
      v
ClaudeClient --[API call]--> OpenRouter --[inference]--> Claude models
      |
      v
ResponseParser (extract: key_points, action_items, technical_terms, participants, citations)
      |
      v
SummarizationEngine (assemble SummaryResult, attach metadata, check cache)
      |
      +--[cache hit]---------> MemoryCache (TTL=3600s)
      |
      +--[cache miss]--------> cache.cache_summary()
      |
      v
Repository Layer
      |
      +---> stored_summaries (DB)
      +---> summary_fts (FTS5 virtual)
      +---> summary_jobs (progress tracking)
      |
      v
Delivery
      +---> Discord embed (via channel.send or interaction.followup)
      +---> Webhook push (POST to configured URLs)
      +---> Email delivery (SMTP)
      +---> RSS/Atom feed
      +---> Dashboard API (REST)
```

### 3.4 Data Boundary and Validation Findings

| ID | Finding | Severity |
|----|---------|----------|
| D-06 | `max_message_batch` defaults to 10,000 messages with no chunking strategy — single LLM call for 10k messages risks token limit breach | High |
| D-07 | `options.temperature` accepted as float with no range validation in EnvironmentLoader | Low |
| D-08 | `schedule_time` field stored as `HH:MM` string; no TZ offset — ambiguous for non-UTC users | Medium |
| D-09 | `excluded_users` stored as JSON array of user IDs (strings); no validation that values are valid Discord snowflakes | Low |
| D-10 | `webhook_secret` in `guild_configs` table stored as plain text, not encrypted | High |
| D-11 | `SummaryOptions` in `models/summary.py` has `max_tokens=8000` default; `config/settings.py` has `max_tokens=4000` — inconsistent defaults across duplicate classes | Medium |
| D-12 | `source_content` field on SummaryResult stores raw message text — PII risk if messages contain personal data and summaries are retained indefinitely | High |

### 3.5 Data Retention

- Log rotation is configured (10MB, 5 backups)
- Command log retention is configurable via `LoggingConfig.retention_days`
- Error log cleanup runs every 24 hours
- **No TTL/retention policy for summaries or stored_summaries** — unbounded growth
- **No PII anonymization path for stored `source_content`** field on summaries

---

## 4. INTERFACE Analysis

### 4.1 Discord Bot Interface

**Slash Commands (registered globally):**

| Command | Parameters | Notes |
|---------|-----------|-------|
| `/summarize` | messages, hours, minutes, length, perspective, channel, category, mode, exclude_channels | Defers response; handles all 4 time-range modes |
| `/schedule list` | — | Guild-scoped |
| `/schedule create` | channel, frequency, time, length, days, additional_channels | |
| `/schedule delete` | task_id | |
| `/schedule pause` | task_id | |
| `/schedule resume` | task_id | |
| `/prompt-config set` | repo_url, branch | GitHub URL of custom prompt repo |
| `/prompt-config status` | — | |
| `/prompt-config remove` | — | |
| `/prompt-config refresh` | — | |
| `/prompt-config test` | category | |
| `/config view` | — | Admin |
| `/config set-cross-channel-role` | role_name | Admin |
| `/config permissions` | require | Admin |
| `/config reset` | — | Admin |
| `/help` | — | Ephemeral |
| `/status` | — | Ephemeral |
| `/ping` | — | Ephemeral |
| `/about` | — | Ephemeral |

**Interface Risk:**
- `/status` command's TODO comment at line 593 acknowledges Claude API, database, and cache statuses are not surfaced — status is incomplete
- Global command sync can take up to 1 hour to propagate per Discord's documentation — no mechanism to force guild-specific sync after deployment

### 4.2 REST API Interface (Dashboard + Webhook)

**Base path:** `/api/v1`

**Route groups identified:**
- `/api/v1/auth/*` — Discord OAuth2 login, callback, token refresh, logout, current user
- `/api/v1/guilds/*` — Guild listing, guild config, channels, members
- `/api/v1/guilds/{guild_id}/summaries/*` — CRUD + search + regenerate
- `/api/v1/guilds/{guild_id}/schedules/*` — Schedule management
- `/api/v1/guilds/{guild_id}/webhooks/*` — Webhook config
- `/api/v1/guilds/{guild_id}/feeds/*` — Feed management
- `/api/v1/guilds/{guild_id}/archive/*` — Archive generation and download
- `/api/v1/guilds/{guild_id}/prompts/*` — Custom prompt config
- `/api/v1/guilds/{guild_id}/errors/*` — Error log viewing
- `/api/v1/push-templates/*` — Push template CRUD
- `/api/v1/events/*` — Server-Sent Events for job progress
- `/health` — Health check (always 200, status field indicates degraded)
- `/feeds/{feed_id}.rss` — Public RSS
- `/feeds/{feed_id}.atom` — Public Atom
- `/docs`, `/redoc` — OpenAPI documentation (enabled in production)

**Interface Risk:**

| ID | Finding | Severity |
|----|---------|----------|
| I-01 | OpenAPI docs (`/docs`, `/redoc`) exposed in production — reveals full API surface to unauthorized users | Medium |
| I-02 | SSE events endpoint (`/events`) — no maximum connection limit specified; could be used for resource exhaustion | Medium |
| I-03 | `/{path:path}` SPA catch-all route must be registered last; ordering is critical and relies on Python dict ordering in `_setup_routes` | Medium |
| I-04 | Dashboard router comments: "Register errors_router before guilds_router to avoid route conflicts" — fragile manual ordering | Low |
| I-05 | Route `/api/v1/guilds/{guild_id}` uses string guild_id with no format validation — invalid snowflakes accepted | Low |
| I-06 | `FEED_BASE_URL` defaults to hardcoded `https://summarybot-ng.fly.dev` in server.py line 400 — wrong URL in non-Fly deployments | High |

### 4.3 Internal Module Interfaces

- Modules communicate through explicit dependency injection in `SummaryBotApp`
- Shared database connection passed explicitly to avoid SQLite lock contention (documented pattern)
- `set_services()` global state in `dashboard/routes/__init__.py` introduces hidden coupling — functions accessing services rely on module-level globals rather than explicit parameters

### 4.4 WhatsApp/External Ingest Interface

- `POST /ingest` — accepts WhatsApp export format
- `POST /whatsapp/summarize` — end-to-end WhatsApp ingest + summarize
- ADR-002 documented but external format documentation not found in public API spec

---

## 5. PLATFORM Analysis

### 5.1 Runtime Environment Matrix

| Factor | Value | Risk |
|--------|-------|------|
| Python version | 3.9 minimum, 3.11 in Docker | Python 3.9 EOL Oct 2025 — development environments risk using unsupported runtime |
| Docker base | python:3.11-slim | Acceptable; slim image reduces attack surface |
| Frontend build | node:20-slim | LTS through April 2026 |
| Discord.py | >=2.3.0 | v2.x API is stable |
| SQLite | File-based, single connection | Not horizontally scalable; acceptable for small-to-medium deployments |
| Redis | Optional, not default | Cannot be used for distributed rate-limiting without enabling |
| APScheduler | 3.x | APScheduler 4.x is a rewrite; `>=3.10.0` allows installing it |

### 5.2 Deployment Platform Matrix

| Platform | Config File | Volume | Notes |
|----------|------------|--------|-------|
| Fly.io | fly.toml | `summarybot_data` 1GB persistent volume mounted at `/app/data` | Primary platform; Toronto (yyz) region; rolling deploy strategy |
| Railway | railway.json | Unclear from config | Secondary |
| Render | render.yaml | Unclear from config | Tertiary |
| Docker Compose | docker-compose.yml | Likely volume-mounted `/app/data` | Local development |

**Fly.io Resource Constraints:**
- 1 shared vCPU, 512MB RAM
- Hard connection limit: 100
- HTTP/S only via TCP with forced HTTPS
- Health check: GET /health every 30s, 60s grace period, 15s timeout

### 5.3 Platform Risk Findings

| ID | Finding | Severity |
|----|---------|----------|
| P-01 | 512MB RAM limit with in-memory cache (`max_size=1000`) and large Discord message batches (up to 10,000) could cause OOM eviction | High |
| P-02 | SQLite on a Fly.io persistent volume is not replicated — volume loss = all data loss | High |
| P-03 | `python-jose` has active CVEs; no pinning in pyproject.toml — upgrade path unclear | High |
| P-04 | APScheduler `>=3.10.0` allows APScheduler 4.x which is an incompatible rewrite (new API, new imports) | Medium |
| P-05 | `anthropic` package `>=0.5.0` spans several major API generations — client initialization patterns differ | Medium |
| P-06 | Build copies all of `scripts/` into production image — may include maintenance scripts not needed at runtime | Low |
| P-07 | No `HEALTHCHECK` equivalent for the Discord bot connection itself — `/health` only checks the HTTP server | Medium |
| P-08 | `pyproject.toml` declares `python = "^3.9"` but Docker uses 3.11; local dev environments on 3.9/3.10 may hit compatibility issues not caught in CI | Low |

### 5.4 Browser Compatibility (Frontend)

- Vite + Tailwind CSS + TypeScript frontend
- No explicit browser target configuration found in `vite.config.ts` (not read in detail)
- Playwright E2E tests present — browser matrix unknown without reading test config

---

## 6. OPERATIONS Analysis

### 6.1 Deployment Readiness

| Capability | Present | Notes |
|------------|---------|-------|
| Health endpoint | Yes | `/health` always 200; body contains status field |
| Graceful shutdown | Yes | SIGTERM/SIGINT handled; services stopped in reverse-init order |
| Emergency fallback server | Yes | `__main__.py` starts minimal FastAPI if main app fails |
| Rotating file logs | Yes | RotatingFileHandler: 10MB/file, 5 backups |
| Database migration on startup | Yes | `run_migrations()` called before service init |
| Interrupted job recovery on restart | Yes | ADR-013: RUNNING → PAUSED on startup |
| Rolling deploy strategy | Yes | Fly.io `strategy = "rolling"` |
| Auto-rollback | Yes | `auto_rollback = true` in fly.toml |
| Build number in health response | Yes | `BUILD_NUMBER` env var |
| Secret management | Partial | Secrets via env vars; no secret rotation mechanism |

### 6.2 Monitoring and Observability

| Signal | Status | Notes |
|--------|--------|-------|
| Structured application logs | Yes | Python logging with timestamps and module names |
| Request access logs | Yes | uvicorn access_log=True |
| Error tracking database | Yes | `error_logs` table with severity, type, guild context |
| Command execution logging | Yes | `command_logs` table with async writes |
| API usage tracking (per-request cost) | Yes | Token counts in SummaryResult metadata |
| Generation attempt tracking | Yes | ADR-024: `generation_attempts` in metadata |
| Model fallback warnings | Yes | Emitted to SummaryResult.warnings and error_logs |
| External metrics endpoint | Not found | No Prometheus/OpenMetrics endpoint |
| Alerting configuration | Not found | No alerting defined |
| Distributed tracing | Not found | No trace IDs beyond X-Request-ID header |
| Dashboard for error logs | Yes | `/api/v1/guilds/{id}/errors` endpoint |

### 6.3 Configuration Management

Environment variables drive all configuration. Key secrets required at runtime:
- `DISCORD_TOKEN` — optional (webhook-only mode if absent)
- `OPENROUTER_API_KEY` — optional (summarization disabled if absent)
- `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET` — OAuth for dashboard
- `DASHBOARD_JWT_SECRET` — required in production (enforced)
- `DASHBOARD_ENCRYPTION_KEY` — required in production (enforced)
- `PROMPT_TOKEN_ENCRYPTION_KEY` — optional; ephemeral key if absent (custom prompts won't persist across restarts)

**Operational Risk:** The ephemeral `PROMPT_TOKEN_ENCRYPTION_KEY` behavior means guilds that configure custom prompts on a pod that lacks this env var will silently lose their prompt configuration on every restart. No warning is surfaced in Discord.

### 6.4 Maintenance Operations

| Operation | Mechanism |
|-----------|----------|
| Purge old error logs | Automatic: `_run_error_cleanup()` every 24h |
| Purge old command logs | `CommandLogger` respects `retention_days` |
| Summary cleanup | No automated cleanup |
| Database backup | Not defined (Fly volume snapshots must be configured externally) |
| Task cancellation via API | Yes, via dashboard |
| Manual task execution via API | Yes |
| Config reload | `ConfigManager.reload_config()` + file watcher available |

---

## 7. TIME Analysis

### 7.1 Scheduling Architecture

The system uses APScheduler 3.x with `AsyncIOScheduler` backed by an in-process trigger store (no persistent APScheduler jobstore — tasks are loaded from the custom SQLite repository on startup).

**Schedule types supported:**
- once (DateTrigger)
- 15min, hourly, 4-hour (IntervalTrigger)
- daily, weekly, half-weekly, monthly (CronTrigger)
- custom cron expression (CronTrigger.from_crontab)

### 7.2 Temporal Risk Findings

| ID | Finding | Severity |
|----|---------|----------|
| T-01 | Scheduler timezone defaults to "UTC" with no per-task override — users who configure daily summaries at "09:00" always mean UTC 09:00, not their local time. No timezone selector in `/schedule create` | High |
| T-02 | Monthly schedule anchors `day` to `task.created_at.day` — tasks created on the 31st will silently skip months with fewer than 31 days (APScheduler skips the trigger) | Medium |
| T-03 | `misfire_grace_time=3600` (1 hour) with `coalesce=True` — if the server is down for >1 hour, scheduled summaries are permanently skipped rather than queued | Medium |
| T-04 | `_execute_scheduled_task` uses `self._executing_tasks` set for concurrent execution guard, but this set is in-memory only — it is reset on restart, creating a race window during rolling deploys | Medium |
| T-05 | Cache TTL default is 3600 seconds (1 hour) — a summary generated at 23:59 and cached until 00:59 the next day could serve stale cross-midnight results | Low |
| T-06 | `datetime.utcnow()` used directly in `claude_client.py` line 46 (`created_at: datetime = field(default_factory=datetime.utcnow)`) — deprecated since Python 3.12; should use `datetime.now(UTC)` | Low |
| T-07 | Config file watcher polls `stat().st_mtime` every 1 second — creates 1 syscall/second baseline load during development | Low |
| T-08 | Rate limit backoff uses literal `await asyncio.sleep(retry_after)` where `retry_after` defaults to 60 seconds — no jitter, risk of thundering herd if multiple guilds hit rate limit simultaneously | Medium |

### 7.3 Concurrency Assessment

| Surface | Mechanism | Risk |
|---------|-----------|------|
| Discord command processing | asyncio event loop | No explicit semaphore on concurrent /summarize commands per guild |
| Webhook endpoint requests | FastAPI + uvicorn | Rate limited at 100 req/min |
| Batch summarization | `asyncio.Semaphore(3)` | Max 3 concurrent LLM calls — adequate |
| Scheduled task execution | `_executing_tasks` set guard | In-memory only; restart race exists |
| Database access | `pool_size=1` single connection | All DB operations serialized; contention if many events fire concurrently |
| Error cleanup task | Single asyncio.Task | Acceptable |

**Key Race Condition:** Two concurrent `/summarize` commands on the same channel issued within 1 second will both miss the cache (cache key includes start/end time range from messages; if both fetch the same messages, they will compute the same cache key only after the first completes and populates the cache). Both will call the LLM, doubling cost.

---

## 8. Risk Matrix

### 8.1 Consolidated Risk Summary

| ID | Category | Risk | Likelihood | Impact | Priority |
|----|----------|------|-----------|--------|----------|
| D-10 | Data | Webhook secrets stored in plain text in guild_configs table | Medium | High | P0 |
| D-12 | Data | source_content field retains raw PII messages indefinitely | Medium | High | P0 |
| I-06 | Interface | FEED_BASE_URL hardcoded to Fly.io URL — broken on Railway/Render | High | Medium | P0 |
| P-01 | Platform | 512MB RAM + 10k message batch could trigger OOM | Medium | High | P0 |
| T-01 | Time | All schedules are UTC with no user timezone support | High | High | P1 |
| S-07 | Structure | pool_size=1 blocks concurrent DB writes entirely | High | Medium | P1 |
| P-02 | Platform | SQLite on single volume — no replication or backup strategy | Low | Critical | P1 |
| P-03 | Platform | python-jose CVEs, no version pinning | Medium | High | P1 |
| D-06 | Data | 10k message batch with no chunking = likely token overflow | Medium | High | P1 |
| D-02 | Data | FTS5 table can desync from base table (no trigger, app-level only) | Medium | Medium | P2 |
| T-02 | Time | Monthly schedule silently skips months without day 31 | High | Low | P2 |
| T-04 | Time | Concurrent execution guard reset on restart during rolling deploy | Low | Medium | P2 |
| S-02 | Structure | summaries.py route file at 2,732 lines violates single-responsibility | High | Low | P2 |
| I-01 | Interface | /docs and /redoc exposed in production | High | Low | P2 |
| D-03 | Data | No schema rollback migrations | Medium | Medium | P2 |
| T-03 | Time | >1hr downtime causes permanent schedule miss (coalesce=True) | Low | Medium | P2 |
| P-04 | Platform | APScheduler 4.x allowed by version constraint (breaking change) | Low | High | P2 |
| D-11 | Data | Duplicate SummaryOptions classes have inconsistent max_tokens default | High | Low | P3 |
| T-06 | Time | datetime.utcnow() deprecated in Python 3.12 | High | Low | P3 |
| S-03 | Structure | SummaryLength enum duplicated in two modules | High | Low | P3 |
| T-08 | Time | No jitter in rate-limit retry backoff | Low | Low | P3 |

---

## 9. Testing Strategy Recommendations

### 9.1 Structure Testing

**Test Data Suggestions for STRUCTURE-based tests:**
- Import graph: use `modulegraph` or `importlab` to detect circular imports introduced by new changes
- File size monitor: CI gate to reject files >500 lines (per CLAUDE.md policy)
- Dependency lockfile audit: run `safety check` or `pip-audit` against poetry.lock in CI

**Exploratory Test Sessions for STRUCTURE:**
- Session: Navigate the full initialization sequence in `SummaryBotApp.__init__` + `initialize()` with each optional service unavailable in isolation (no Discord token, no LLM key, no DB write permission) — observe which optional features degrade gracefully vs. crash
- Session: Force APScheduler 4.x install and observe which import paths break

### 9.2 Function Testing

**Test Data Suggestions for FUNCTION-based tests:**
- Message batches: 0 messages, 4 messages (below min_messages=5), 5 messages (boundary), 100 messages, 10,000 messages, 10,001 messages
- Summary length permutations: all 3 lengths × all 7 perspectives = 21 combinations
- Schedule types: test all 9 types including custom cron `*/15 * * * *` and edge cases like `0 0 31 * *`
- Invalid Discord snowflakes in `excluded_users`, `allowed_users`, `allowed_roles`

**Exploratory Test Sessions for FUNCTION:**
- Session: Issue `/summarize` twice simultaneously on a high-traffic channel and confirm whether both complete independently or one hits a cache result
- Session: Configure a monthly task on the 31st; advance system clock to February; confirm task behavior
- Session: Set `PROMPT_TOKEN_ENCRYPTION_KEY`, configure a custom prompt, restart without the env var — confirm what the user sees when they next run `/summarize`

### 9.3 Data Testing

**Test Data Suggestions for DATA-based tests:**
- Unicode edge cases: messages with emoji, RTL text, null bytes, messages containing `"` and `|` characters (markdown table safety in `to_markdown`)
- JSON blob integrity: manually corrupt `key_points` JSON in the DB and verify that reading a summary with malformed JSON fails gracefully
- Large `source_content`: summary result with 500-char × 10,000 messages (5MB source_content field) — confirm DB write succeeds and response is not truncated

**Exploratory Test Sessions for DATA:**
- Session: Insert a summary manually bypassing the repository (direct SQL) and confirm FTS5 table is not populated; then trigger a search — confirm FTS returns no result and no error is raised
- Session: Set a webhook_secret on a guild, export the DB, search for the plaintext secret — confirm it is readable (this is a finding, not a pass)

### 9.4 Interface Testing

**Test Data Suggestions for INTERFACE-based tests:**
- API: Call every endpoint without Authorization header and confirm 401
- API: Call `/api/v1/guilds/not-a-snowflake/summaries` — confirm error response
- Discord: Send `/summarize` with both `channel` and `category` parameters set — confirm mutual exclusivity error
- Feed: Request `/feeds/nonexistent.rss` — confirm 404
- Feed: Request a private feed without token, with wrong token, with correct token

**Exploratory Test Sessions for INTERFACE:**
- Session: Enable OpenAPI docs in production; enumerate all POST/PUT/DELETE endpoints from `/openapi.json` without authentication; attempt to call each — confirm all require valid JWT
- Session: Send a summary webhook payload to an external service and observe whether the payload includes `source_content` (raw message PII)

### 9.5 Platform Testing

**Test Data Suggestions for PLATFORM-based tests:**
- Build the Docker image and run on a memory-limited container (`--memory=512m`) while processing a 10,000-message summarization request
- Deploy to Railway and verify `FEED_BASE_URL` is set correctly; generate a feed URL and verify it resolves
- Run tests with `python 3.9` (minimum declared version) to check for 3.10/3.11-only syntax (e.g., `match`, `|` union types)

**Exploratory Test Sessions for PLATFORM:**
- Session: Start the application without setting `PROMPT_TOKEN_ENCRYPTION_KEY`; configure a custom prompt; restart the app; verify the prompt is gone and user receives no notification
- Session: Kill the process during a running summarization job; restart; confirm the job appears as PAUSED in the dashboard

### 9.6 Operations Testing

**Test Data Suggestions for OPERATIONS-based tests:**
- Health endpoint under load: concurrent requests to `/health` while a 10,000-message summarization is running
- Log rotation trigger: generate > 10MB of log output by running many small summaries; confirm rotation creates `summarybot.log.1`
- Startup failure injection: set `DATABASE_URL` to an unwritable path; confirm emergency server starts on port 5000 and `/health` returns `status: emergency`

**Exploratory Test Sessions for OPERATIONS:**
- Session: Deploy via rolling strategy while a scheduled task is mid-execution — observe whether the job is marked PAUSED on the old pod and what happens on the new pod
- Session: Fill the SQLite database until the volume is nearly full; trigger a summarization — confirm error handling and whether the health endpoint reflects the degraded state

### 9.7 Time Testing

**Test Data Suggestions for TIME-based tests:**
- Schedule at 23:59 UTC daily; advance mock clock past midnight; confirm the next run is calculated as the next occurrence after the current time, not double-fired
- Create a custom cron `* * * * *` (every minute); let it fire 3 times; confirm `run_count` increments correctly and `last_run` is updated
- Create a scheduled task while the scheduler is shutting down (race condition between `stop()` and `schedule_task()`)

**Exploratory Test Sessions for TIME:**
- Session: Set the system timezone to `America/New_York`; create a daily summary at "09:00"; advance 24 hours; confirm the summary fires at UTC 09:00 not local 09:00 — this demonstrates the UTC-only limitation to stakeholders
- Session: Simulate a 90-minute server outage; restart; observe which scheduled tasks were missed and whether any ran on restart or were permanently skipped

### 9.8 Priority-Ranked Test Execution Backlog

| # | Test Idea | Factor | Priority | Automation Fit |
|---|-----------|--------|----------|----------------|
| 1 | Submit concurrent `/summarize` on same channel; confirm LLM is not called twice if messages overlap | Function/Time | P0 | Integration |
| 2 | Call `/health` endpoint while app is running without LLM key; confirm 200 with `status: degraded` | Operations | P0 | Unit |
| 3 | Query the `guild_configs` table directly; confirm `webhook_secret` is stored in plaintext | Data | P0 | Human-Exploration |
| 4 | Set `FEED_BASE_URL` to a Railway URL; generate a feed; confirm links are correct | Interface/Platform | P0 | E2E |
| 5 | Process 10,001 messages with `max_message_batch=10000`; confirm prompt optimization or graceful rejection | Data | P1 | Integration |
| 6 | Create a daily schedule via `/schedule create`; confirm next_run is in UTC not local time | Time | P1 | Integration |
| 7 | Restart app during active scheduled job; confirm job appears as PAUSED not RUNNING | Time/Operations | P1 | Integration |
| 8 | Run `pip-audit` against `poetry.lock`; confirm no known CVEs in production dependencies | Platform | P1 | Unit (CI) |
| 9 | Send malformed JSON in key_points column; read summary via API; confirm graceful error | Data | P2 | Integration |
| 10 | Request private feed with token using timing attack (measure response time difference); confirm constant-time comparison | Interface | P2 | Human-Exploration |
| 11 | Emit >10MB of logs; confirm rotation creates backups | Operations | P2 | Integration |
| 12 | Trigger FTS search after direct DB insert bypassing repository; confirm no error and empty result | Data | P2 | Integration |
| 13 | Install APScheduler 4.x via `pip install apscheduler`; run app; confirm import errors surface immediately | Platform | P2 | Unit |
| 14 | Browse `/docs` endpoint in production without authentication; confirm it is accessible | Interface | P2 | E2E |
| 15 | Configure monthly schedule on day 31; advance to February; confirm graceful skip behavior | Time | P2 | Integration |
| 16 | Start app without DISCORD_TOKEN; confirm webhook-only mode starts and `/health` is 200 | Function | P3 | Unit |
| 17 | Confirm `SummaryLength` enum values in `config/settings.py` and `models/summary.py` are identical | Structure | P3 | Unit |
| 18 | Confirm `to_markdown` handles messages with `|` characters without breaking the reference table | Data | P3 | Unit |

---

## Appendix A: Clarifying Questions

These questions identify gaps where requirements or intended behaviors are ambiguous. They are based on general risk patterns in the product type.

**Data Retention:**
1. What is the intended maximum age for summaries in `stored_summaries`? Is there a retention policy, or are they expected to grow unboundedly?
2. Is `source_content` (raw message text) retained intentionally for debugging purposes? If it contains user PII, is there a legal basis under GDPR/CCPA for retaining it?

**Multi-Guild Scaling:**
3. At what guild count does SQLite with `pool_size=1` become inadequate? Is there a migration path to PostgreSQL documented anywhere?
4. Is horizontal scaling (multiple instances) a current or planned requirement? If so, the in-memory cache and in-process APScheduler store need to be externalized.

**Timezone Support:**
5. Is the UTC-only scheduling behavior intentional and communicated to users in the Discord command description? If not, how should multi-timezone guilds configure schedules?

**Custom Prompts:**
6. What happens to a guild's existing custom prompt configuration when `PROMPT_TOKEN_ENCRYPTION_KEY` changes between deployments? Is there a migration path for the Fernet-encrypted token?

**Security:**
7. Is the `/docs` and `/redoc` endpoint intentionally public in production? What is the rationale?
8. Is constant-time token comparison required for feed tokens? Given that feed tokens are long random strings, is the timing oracle a realistic attack vector given the deployment context?

**Backup Strategy:**
9. What is the RPO (Recovery Point Objective) for the SQLite database on the Fly.io persistent volume? Are volume snapshots configured and tested?

**Testing:**
10. What is the current test coverage percentage for the `command_handlers` and `dashboard/routes` modules? These are the two largest untested surfaces identified in this review.

---

## Appendix B: ADR Cross-Reference

| ADR | Description | Test Impact |
|-----|-------------|------------|
| ADR-002 | Multi-source support (WhatsApp) | WhatsApp ingest needs dedicated E2E testing |
| ADR-004 | Grounded summaries with citations | Verify reference_index is not populated in non-cited mode |
| ADR-008 | Unified summary storage | Confirm old `summaries` table and `stored_summaries` are consistent |
| ADR-013 | Job tracking and recovery | Test restart recovery in integration environment |
| ADR-020 | Summary navigation and FTS search | Test FTS desync scenario |
| ADR-024 | Resilient generation with retry and model escalation | Test each escalation tier; test cost cap enforcement |
| ADR-026 | LLM routing (OpenRouter vs direct) | Confirm LLM_ROUTE env var switch works correctly |
| ADR-030 | Email delivery via SMTP | Test SMTP failure mode (server unreachable) |
| ADR-031 | Error logging middleware | Confirm 5xx errors are captured in error_logs with full context |

---

*Assessment completed: 2026-03-13 | Framework: James Bach HTSM SFDIPOT | Analyst: QE Product Factors Assessor V3*
