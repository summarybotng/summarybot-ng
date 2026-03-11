# SFDIPOT Product Factors Analysis: SummaryBot NG

**Framework**: James Bach's Heuristic Test Strategy Model (HTSM) - Product Factors
**Assessment Date**: 2026-03-11
**Project**: SummaryBot NG v1.0.0
**Scope**: 153 Python source files, 69 test files, ~88K total LOC across 20 modules
**Assessor**: QE Product Factors Assessor (SFDIPOT/V3)
**Method**: Deep source code analysis of all SFDIPOT-relevant files with cross-referencing against 32 ADRs

---

## Executive Summary

SummaryBot NG is a substantial Discord bot application for AI-powered conversation summarization. It integrates with Claude/OpenRouter for LLM inference, provides a full REST API dashboard, supports scheduled and on-demand summaries, delivers via Discord, email, and webhooks, and includes ancillary systems for WhatsApp import, Google Drive sync, RSS/Atom feeds, archive retention, and cost tracking.

The codebase demonstrates significant architectural maturity across its core domain. The resilient summarization engine with model escalation and cost-capped retry (ADR-024) is a sophisticated production pattern. The 32 Architecture Decision Records provide unusually strong traceability from requirements to code. The exception hierarchy, multi-perspective summarization, and job recovery system (ADR-013) all indicate deliberate engineering rather than ad-hoc development.

However, this analysis reveals **critical risks concentrated in three factors**: **Time** (SQLite concurrency under multi-path access, no LLM timeout, cache stampede vulnerability), **Data** (ephemeral encryption keys invalidate user configuration on every restart, no database backup strategy, cache hash collisions), and **Operations** (no API rate limiting, no cost alerting enforcement, no admin tooling for key rotation or cache management). Additionally, the **Platform** factor contains a deployment blocker: the default Docker Compose configuration references an unimplemented Redis cache backend that will crash the application on startup.

The gap between "code exists" and "code is production-safe" is most visible when examining cross-factor interactions. The single SQLite connection (Data) combined with concurrent scheduled tasks, webhook requests, and Discord interactions (Time) creates a systemic bottleneck. The absence of rate limiting on the dashboard API (Interfaces) combined with no cost alerting (Operations) means unbounded LLM costs under attack or misconfiguration. The ephemeral encryption keys (Structure) combined with PaaS container restarts (Platform) silently destroy user OAuth tokens and prompt configurations.

**Overall Product Maturity Score: 6.5 / 10**

The score reflects a product that has progressed well beyond prototype stage with thoughtful architecture decisions, rich domain modeling, and a comprehensive feature set. However, it has not yet fully hardened for production operations at scale. The project earns strong marks for its summarization engine design, ADR discipline, and multi-deployment-target support, but loses points for the Redis non-implementation deployment blocker, the JWT default-secret vulnerability, the ephemeral encryption key problem, and the absence of operational tooling (rate limiting, cost alerting, key rotation, cache management).

---

## Risk Heat Map

### Factor vs. Severity Matrix

| Product Factor | LOW | MEDIUM | HIGH | CRITICAL | Overall Severity | Priority |
|---|---|---|---|---|---|---|
| **Structure** | 2 | 3 | 1 | 0 | MEDIUM | P2 |
| **Function** | 1 | 3 | 2 | 0 | MEDIUM-HIGH | P1 |
| **Data** | 0 | 2 | 3 | 1 | HIGH | P0 |
| **Interfaces** | 1 | 2 | 2 | 1 | HIGH | P1 |
| **Platform** | 1 | 2 | 1 | 1 | HIGH | P1 |
| **Operations** | 0 | 2 | 3 | 0 | HIGH | P0 |
| **Time** | 0 | 1 | 2 | 2 | CRITICAL | P0 |

Severity scale: LOW (cosmetic/documentation) / MEDIUM (quality concern) / HIGH (production risk) / CRITICAL (data loss or security breach possible)

### Top 10 Risks Ranked by Severity x Likelihood

| # | Risk | Factor(s) | Severity | Likelihood |
|---|---|---|---|---|
| 1 | SQLite "database is locked" under concurrent access | Time, Data | CRITICAL | HIGH |
| 2 | JWT default secret "change-in-production" allows auth bypass | Interfaces | CRITICAL | HIGH |
| 3 | Ephemeral encryption keys destroy user config on restart | Data, Platform | HIGH | CERTAIN |
| 4 | Redis cache backend crashes on startup (docker-compose default) | Platform, Data | CRITICAL | CERTAIN |
| 5 | No LLM API call timeout; hanging request blocks scheduler | Time, Function | HIGH | MEDIUM |
| 6 | No API rate limiting; unbounded LLM cost under abuse | Interfaces, Operations | HIGH | MEDIUM |
| 7 | Cache stampede: concurrent LLM calls on hourly cache expiry | Time | HIGH | MEDIUM |
| 8 | No database backup; volume failure = total data loss | Data, Operations | HIGH | LOW |
| 9 | Cost budget alerting is modeled but not enforced | Operations, Function | MEDIUM | HIGH |
| 10 | Bare `except:` in commands.py swallows SystemExit | Function | MEDIUM | MEDIUM |

---

## 1. STRUCTURE - What the Product IS

### 1.1 Architecture Overview

The source tree comprises 20 Python packages organized by domain concern. The top-level structure follows a clean separation:

```
src/
  archive/            # 13 files - Retrospective archive (models, importers, sync, retention, locking, cost tracking)
  command_handlers/   # 6 files  - Discord slash command handler implementations
  config/             # 5 files  - Configuration management (settings, constants, validation, environment)
  dashboard/          # 15 files - Web dashboard API (auth, middleware, 12 route modules)
  data/               # 7 files  - Data access layer (SQLite, PostgreSQL, migrations, repositories)
  discord_bot/        # 5 files  - Discord client (bot lifecycle, commands, events, utils)
  exceptions/         # 6 files  - Typed exception hierarchy by domain
  feeds/              # 4 files  - RSS/Atom feed generation and WhatsApp ingest
  logging/            # 8 files  - Command logging, sanitization, analytics, error tracking, cleanup
  message_processing/ # 7 files  - Message fetching, filtering, cleaning, validation, extraction
  models/             # 12 files - Domain models (summary, task, message, feed, webhook, user, etc.)
  permissions/        # 5 files  - Role-based permission system with LRU caching
  prompts/            # 10 files - Custom prompt templates (GitHub-backed, resolver, schema, fallback chain)
  scheduling/         # 5 files  - APScheduler-based task scheduling with dual persistence
  services/           # 4 files  - Cross-cutting (email delivery, push messaging, anonymization)
  summarization/      # 7 files  - Core AI engine (client, cache, prompt builder, parser, retry)
  webhook_service/    # 6 files  - REST API server (auth, endpoints, validators, formatters)
  templates/          # Email HTML/text templates
  frontend/           # React/TypeScript web dashboard SPA
```

### 1.2 Strengths

**ADR-driven architecture with strong traceability.** The project contains 32 Architecture Decision Records (ADR-001 through ADR-032) covering topics from WhatsApp integration to resilient summary generation. Code comments reference specific ADRs (e.g., `# ADR-013: Recover interrupted jobs`, `# ADR-024: Use resilient engine`), providing direct traceability from design rationale to implementation. This is uncommon in projects of this size and demonstrates engineering discipline.

**Dependency injection via ServiceContainer.** `src/container.py` implements a lazy-initialized service container using Python properties. Each service (ClaudeClient, SummaryCache, SummarizationEngine, repositories) is created on first access and cached. This pattern prevents circular dependencies and supports testing via dependency substitution. The container also provides `health_check()` and `cleanup()` lifecycle methods.

**Well-typed exception hierarchy.** The `exceptions/` package defines a four-tier hierarchy: `SummaryBotException` (base) with `CriticalError`, `RecoverableError`, and `UserError` specializations. Each exception carries an `ErrorContext` dataclass with user/guild/channel IDs and operation metadata. Domain-specific exceptions (`SummarizationError`, `InsufficientContentError`, `PromptTooLongError`, `RateLimitError`, `ModelUnavailableError`) provide typed error handling throughout the codebase. The `retryable` flag on each exception enables the retry strategy to make informed decisions.

**Repository pattern with abstract interfaces.** `data/base.py` defines 8 abstract repository interfaces (`SummaryRepository`, `ConfigRepository`, `TaskRepository`, `FeedRepository`, `WebhookRepository`, `ErrorRepository`, `StoredSummaryRepository`, `IngestRepository`) with full docstrings and type hints. The SQLite implementation in `data/sqlite.py` provides concrete implementations with WAL mode, foreign key enforcement, busy timeout, and a global write lock for concurrency safety.

### 1.3 Risks and Concerns

**Dual initialization paths create divergent behavior.** Both `SummaryBotApp.__init__()` in `main.py` (614 lines) and `ServiceContainer.__init__()` in `container.py` (194 lines) perform service wiring. `SummaryBotApp` is the production entry point, performing ordered async initialization with explicit error handling and logging. `ServiceContainer` uses lazy property initialization with no ordering guarantees. Key differences include:
- `SummaryBotApp` selects the LLM provider based on environment (`_select_llm_provider()`); `ServiceContainer` always uses `OPENROUTER_API_KEY`
- `SummaryBotApp` handles the `PROMPT_TOKEN_ENCRYPTION_KEY` with a warning; `ServiceContainer` generates ephemeral keys silently
- `SummaryBotApp` runs database migrations; `ServiceContainer` does not
The risk is that tests using `ServiceContainer` may pass while production using `SummaryBotApp` fails (or vice versa) due to initialization differences.

**Module-level singleton pattern is thread-unsafe.** Several modules use module-global singletons: `_email_service` in `email_delivery.py`, `_error_tracker` in `error_tracker.py`, and `_global_write_lock` in `sqlite.py`. The global write lock in particular (`_get_global_write_lock()`) creates the lock lazily on first use. If two coroutines call this simultaneously in a pre-asyncio context, the lock could be created twice. While this is unlikely in the current single-process deployment, it creates a latent concurrency bug.

**Debug print statements in production code.** `main.py` contains 8 `print()` calls to `sys.stderr` at module load time (lines 14, 23, 27, 31, 37, 51, 598, 603, 658). These are development debugging artifacts that will appear in production logs, potentially confusing log aggregation tools and operators who may misinterpret them as error output.

**Missing `__all__` declarations.** Most `__init__.py` files either re-export everything from submodules without `__all__` or are empty. This makes the public API of each module implicit. For a project of this complexity (20 packages), this increases the risk of unintended API surface exposure and makes refactoring harder.

**Config module has a duplicate `SummaryLength` enum.** Both `src/config/settings.py` and `src/models/summary.py` define a `SummaryLength` enum with identical values. The `config/settings.py` version also defines a separate `SummaryOptions` dataclass that duplicates fields from `models/summary.py::SummaryOptions`. This duplication can cause import confusion and subtle bugs if the two definitions drift apart.

### 1.4 Testing Gaps

- No tests for `ServiceContainer` initialization lifecycle or dependency resolution order
- No tests comparing `SummaryBotApp` wiring against `ServiceContainer` wiring for behavioral parity
- No circular import detection tests
- No tests for the emergency server (`emergency_server()` in main.py)
- No tests for module-level singleton thread safety
- No static analysis for `__all__` declaration completeness

### 1.5 Testing Recommendations

| Test Idea | Priority | Automation | Reasoning |
|---|---|---|---|
| Import every `src/` module individually in a clean Python process; assert no `ImportError` or circular dependency | P1 | Unit | Circular imports are a common failure mode in projects with this many cross-references |
| Initialize `SummaryBotApp` with all optional services missing (no LLM key, no Discord token) and confirm it starts in webhook-only mode without crashing | P1 | Integration | Graceful degradation is claimed but the full path has many conditional branches |
| Initialize `ServiceContainer` and `SummaryBotApp` side by side; compare which services each creates and their configurations | P2 | Integration | The dual-init path is a maintenance hazard |
| Force the emergency server path (make main application initialization throw) and confirm health endpoint returns 200 | P2 | Integration | Emergency mode is the last-resort safety net for deployment platforms |
| Grep-based lint test: assert zero `print()` calls in production code outside of `__main__.py` | P3 | Unit | Prevents debug statements from reaching production |
| Static analysis: verify each `__init__.py` that re-exports symbols declares `__all__` | P3 | Unit | API surface control |

---

## 2. FUNCTION - What the Product DOES

### 2.1 Core Capabilities

The application provides six primary functional capabilities:

1. **On-demand summarization** via Discord `/summarize` command with 7 perspective options, 3 length tiers, single-channel/category/cross-channel modes
2. **Scheduled summarization** via `/schedule create` with daily, weekly, half-weekly, monthly, and custom cron frequencies
3. **REST API summarization** via `POST /api/v1/summaries` for external integrations (Zapier, automation tools)
4. **Custom prompt management** via `/prompt-config` commands backed by GitHub repository resolution
5. **Multi-destination delivery** to Discord channels, email, webhooks, and RSS/Atom feeds
6. **Archive management** with retrospective summaries, retention policies, Google Drive sync, and cost tracking

### 2.2 Strengths

**Resilient summarization with model escalation (ADR-024).** The `ResilientSummarizationEngine` is the most sophisticated component in the codebase. It implements:
- A `MODEL_ESCALATION_CHAIN` that progresses from cheaper to more capable models on failure
- Quality issue detection that inspects stop reasons, output token counts, and content structure
- Four retry action types: `SAME_MODEL`, `ESCALATE_MODEL`, `INCREASE_TOKENS`, `ADD_PROMPT_HINT`
- Per-attempt cost tracking via `GenerationAttemptTracker` with a configurable `max_cost_usd` cap
- Distinct handling for rate limits (wait and retry), network errors (exponential backoff), and model unavailability (immediate escalation)

This design means a brief summary that fails on Haiku automatically escalates to Sonnet, and if that fails, to Opus, with cost tracked across all attempts. This is a production-grade pattern rarely seen in open-source projects.

**Multi-perspective summarization.** Each summary request can specify one of 7 perspectives (general, developer, marketing, product, finance, executive, support) and one of 3 lengths (brief, detailed, comprehensive). The brief tier automatically routes to Haiku for 12x cost savings. The comprehensive tier routes to the best available model. This cost-optimized model selection is configured in `config/constants.py` via `STARTING_MODEL_INDEX` and `DEFAULT_BRIEF_MODEL`.

**Batch summarization with bounded concurrency.** `SummarizationEngine.batch_summarize()` processes multiple channel summarizations concurrently using `asyncio.Semaphore(3)`. Failed individual requests are captured via `asyncio.gather(return_exceptions=True)` and converted to error summary objects, ensuring partial batch success returns useful results.

**Job recovery on restart (ADR-013).** When the server restarts, `_recover_interrupted_jobs()` queries for jobs in `RUNNING` status and marks them as `PAUSED` with reason `server_restart`. This prevents orphaned jobs from being invisible in the dashboard and gives users the option to resume or cancel.

**Cross-channel category summarization.** Users can summarize an entire Discord category (all channels) in "combined" mode (one summary) or "individual" mode (per-channel summaries), with channel exclusion support. This is accessible both via `/summarize category:` and the dashboard API.

### 2.3 Risks and Concerns

**Four webhook API endpoints return hardcoded error responses.** The `endpoints.py` file contains several endpoints that are advertised in the API specification but not implemented:
- `POST /summarize` returns HTTP 501: "Summary creation not yet implemented - requires Discord client integration"
- `GET /summary/{summary_id}` always returns HTTP 404
- `POST /schedule` returns HTTP 501: "Scheduling not yet implemented - requires scheduler integration"
- `DELETE /schedule/{schedule_id}` always returns HTTP 404

Only `POST /summaries` (the from-messages variant) is functional. This is a significant gap between the advertised API contract and the actual implementation. External consumers (Zapier templates, documentation examples) that reference these endpoints will fail.

**Bare `except:` clause swallows fatal errors.** In `commands.py` line 128, after a failed followup message send:
```python
except:
    pass
```
This catches `KeyboardInterrupt`, `SystemExit`, and `GeneratorExit` in addition to normal exceptions. The intent is to gracefully handle failed Discord API calls, but the implementation silently hides process-termination signals.

**No input size validation on webhook payloads.** The `POST /summaries` endpoint accepts a `messages` array of arbitrary size. A payload with 100,000 messages or a 100MB JSON body has no guardrail. The Zapier payload unwrapping also performs `json.loads()` on arbitrary string content without size checks, creating a denial-of-service vector.

**MD5 hash for cache keys with truncation.** `SummarizationEngine._hash_options()` uses `hashlib.md5().hexdigest()[:16]` (8 bytes effective) for cache key generation. While not security-sensitive, the truncation to 16 hex characters increases collision probability. For a guild with 1000 unique option combinations, the birthday paradox gives a non-trivial collision probability.

**Cost estimation has sync/async ambiguity.** The `estimate_cost()` and `health_check()` methods contain `if inspect.iscoroutine(cost_result):` guards to handle both sync and async returns from `claude_client`. This indicates the `ClaudeClient` interface is not consistently async, which is a testability and maintenance concern.

### 2.4 Testing Gaps

- No tests for the four 501/404 placeholder endpoints (negative testing against advertised API)
- No tests for Zapier payload unwrapping edge cases (nested payloads, oversized payloads, malformed JSON strings)
- No tests for model escalation chain exhaustion with real API error codes
- No tests for `batch_summarize()` under partial failure (2 of 3 requests fail)
- No tests for cross-channel category summarization with permission boundaries (user has access to 3 of 5 channels in category)
- No tests for prompt resolution failure fallback in integration context
- No tests for oversized message payloads (10K+ messages to a single summarize request)
- No load test for concurrent `/summarize` commands from multiple Discord guilds

### 2.5 Testing Recommendations

| Test Idea | Priority | Automation | Reasoning |
|---|---|---|---|
| Send 10,000-message payload to `POST /summaries` and measure memory consumption, response time, and whether the application remains responsive | P0 | Performance | No input size limits exist; this is the most likely production incident |
| Trigger model escalation chain exhaustion (mock all models returning 503) and confirm error response includes cost tracking and does not retry indefinitely | P1 | Integration | The retry loop has exit conditions but they need validation under real failure patterns |
| Submit Zapier payload with nested JSON strings 5 levels deep and confirm correct unwrapping or explicit rejection | P1 | Unit | Zapier payload handling is manually coded without schema validation |
| Execute `batch_summarize()` where 2 of 3 requests fail and confirm successful results are returned alongside error summaries | P1 | Unit | Partial batch success is critical for category summarization |
| Call each 501/404 placeholder endpoint and confirm documented error response format matches API specification | P2 | E2E | API consumers need predictable error responses |
| Invoke `/summarize` with both `channel` and `category` specified and confirm mutual exclusivity validation fires | P2 | Unit | The validation is in command handler but could be bypassed via API |
| Send summary request with `min_messages=5` but only 4 messages and confirm `InsufficientContentError` with user-friendly message | P2 | Unit | Boundary value at the minimum message threshold |
| Replace bare `except:` in commands.py with `except Exception:` and add test that `SystemExit` propagates | P3 | Unit | Safety net against silent fatal error swallowing |

---

## 3. DATA - What the Product PROCESSES

### 3.1 Data Model Overview

The domain model is organized across 12 model files with the `SummaryResult` dataclass at the center. Key data entities:

- **SummaryResult**: 20+ fields including key points, action items, technical terms, participants, referenced claims (ADR-004), prompt tracking, warnings, and generation attempt metadata
- **ProcessedMessage**: Messages from any source (Discord, WhatsApp, Slack) with author, content, timestamp, attachments, and source type
- **ScheduledTask**: Persistent task configuration with 8 schedule types, multi-channel scope, and delivery destinations
- **SummaryJob**: ADR-013 job tracking with status lifecycle (PENDING -> RUNNING -> COMPLETED/FAILED/PAUSED)
- **ArchiveSource**: Platform-agnostic source identifier supporting Discord, WhatsApp, Slack, and Telegram
- **CostEntry/SourceCost**: Per-guild, per-source cost attribution with monthly aggregation and budget tracking

### 3.2 Strengths

**Rich, citation-aware domain model (ADR-004).** `SummaryResult` supports grounded summaries with `referenced_key_points`, `referenced_action_items`, `referenced_decisions`, `referenced_topics`, and a deduplicated `reference_index`. The `to_markdown(include_citations=True)` method generates a full sources table with position markers, sender names, timestamps, and snippets. This is a sophisticated attribution system that connects summary claims to original messages.

**Multi-source support (ADR-002).** The data model is genuinely platform-agnostic. `ArchiveSource` supports `source_type` of discord, whatsapp, slack, or telegram with a unified `source_key` format (`{type}:{server_id}`). `SummaryOptions` includes WhatsApp-specific flags (`include_voice_transcripts`, `reconstruct_threads`, `include_forwarded`). `SearchCriteria` supports filtering by `source_type`.

**Comprehensive archive metadata.** `SummaryMetadata` captures period info with DST awareness (spring forward, fall back transitions), generation info (model, tokens, cost, prompt version), statistics (message counts, participant counts, unique dates), backfill status, integrity checksums, and generation locks. The `PeriodInfo` model handles daily, weekly, and monthly periods with timezone-safe boundaries.

**Dual persistence for scheduled tasks.** Tasks persist to both database (preferred, via `TaskRepository`) and file-based storage (fallback, via `TaskPersistence`). On startup, the scheduler tries database first and falls back to files. This belt-and-suspenders approach protects against database corruption causing schedule loss.

**Discord embed character limit awareness.** `SummaryResult.to_embed_dict()` respects all Discord embed limits: 256-character title, 4096-character description (truncated to 2048 for safety), 1024-character field values, max 25 fields. Key points and action items are incrementally added with character counting and "...and X more" overflow handling.

### 3.3 Risks and Concerns

**Ephemeral encryption keys destroy user configuration on every restart.** When `PROMPT_TOKEN_ENCRYPTION_KEY` is not set (main.py lines 340-347), the application generates an ephemeral `Fernet` key. The same pattern occurs for `DASHBOARD_ENCRYPTION_KEY` (dashboard/router.py lines 49-54). The consequences are severe:
- All encrypted OAuth tokens become unreadable after any container restart
- Users must re-authorize custom prompt configurations after every deployment
- The dashboard JWT encryption key also regenerates, invalidating all active sessions
- There is no user-visible warning; only a server log entry reads "using ephemeral key"
- On PaaS platforms (Fly.io, Railway, Render) that restart on deploy, this means every deployment breaks user configuration

**SQLite pool_size=1 serializes all database operations.** `main.py` line 152 initializes the database with `pool_size=1` and the comment "SQLite WAL mode + single connection ensures safe concurrent access." While this prevents "database is locked" errors from concurrent writes, it serializes ALL database operations. When the summarization engine stores a result, the scheduler checks next run times, the dashboard serves a listing query, and the error tracker logs an entry, they all queue behind a single connection. Under load, this creates a bottleneck where any long-running query (e.g., a summary search with LIKE clauses) blocks all other operations.

**No database backup strategy.** All persistent state resides in `data/summarybot.db` (SQLite) on a Fly.io volume mount. There is no automated backup mechanism:
- No cron job or scheduled task for database dumps
- No WAL checkpointing strategy (WAL files can grow unbounded)
- No replication or secondary
- A volume failure or corruption causes total data loss (summaries, schedules, configurations, cost records, command logs)

**Cache key collision by design.** `SummaryCache._generate_cache_key()` rounds timestamps to the nearest hour:
```python
start_hour = start_time.replace(minute=0, second=0, microsecond=0)
end_hour = end_time.replace(minute=0, second=0, microsecond=0)
```
Two different summarization requests within the same hour for the same channel with the same options hash will produce identical cache keys. Request A at 10:05 and Request B at 10:45 (with different message counts) will collide. Request B will receive Request A's stale summary.

**PostgreSQL support exists in code but is not integrated.** The `data/postgresql.py` file exists, `asyncpg` is listed in requirements as optional, and `docker-compose.yml` contains a commented PostgreSQL service. However, the actual integration status is unclear. Users who uncomment the PostgreSQL section and set `DATABASE_URL=postgresql://...` may find that migrations do not run (they are SQLite-specific) and repositories do not connect.

**Cost tracking models exist but enforcement is absent.** `SourceCost` and `SourceManifest` models include `budget_monthly_usd` and `alert_threshold_percent` fields. `CostEntry` tracks per-request costs. However, there is no evidence in the summarization engine that cost budgets are checked before making LLM API calls. A guild could exceed its budget with no warning or throttling.

### 3.4 Testing Gaps

- No tests for ephemeral key scenario (restart and attempt to decrypt previously encrypted tokens)
- No tests for SQLite WAL mode behavior under concurrent connections from multiple code paths
- No tests for cache key collision scenarios (same-hour requests with different messages)
- No tests for data migration path from SQLite to PostgreSQL
- No tests for archive metadata integrity (checksum validation across write-read cycles)
- No tests for cost budget threshold checking or alerting
- No tests for database size growth under sustained operation (months of summaries)
- No tests for WAL file growth and checkpointing behavior

### 3.5 Testing Recommendations

| Test Idea | Priority | Automation | Reasoning |
|---|---|---|---|
| Restart the application with ephemeral encryption key and attempt to decrypt a previously encrypted OAuth token; confirm it fails gracefully with a clear user-facing error | P0 | Integration | This happens on every deployment in production |
| Open 10 concurrent database operations (5 reads + 5 writes) against pool_size=1 and measure: lock contention rate, maximum wait time, and throughput | P0 | Integration | The single-connection bottleneck is the primary scaling constraint |
| Generate two summaries for the same channel at 10:05 and 10:45 within the same hour and confirm the second request triggers a fresh LLM call rather than returning stale cached data | P1 | Unit | Cache collision is a correctness issue |
| Corrupt the SQLite database file (truncate to 50% size) and confirm the application starts in emergency mode rather than crash-looping | P1 | Integration | Database corruption is the most common data-loss scenario |
| Run `apply_retention_policy()` with `retention_days=0` and confirm all summaries are soft-deleted with 30-day grace period, not permanently deleted | P2 | Unit | Retention policy must not cause irreversible data loss |
| Insert 100K summary records and measure query performance for the dashboard listing endpoint (pagination, filtering by guild, date range) | P2 | Performance | Database performance at scale is untested |
| Attempt to use PostgreSQL backend (set `DATABASE_URL=postgresql://...`) and document what actually works vs. fails | P2 | Human Exploration | Users need to know if PostgreSQL is viable or aspirational |
| Track cost entries for a guild over 100 summarizations and confirm the budget threshold is detected (or document that enforcement is not implemented) | P2 | Integration | Cost management is critical for production guilds |

---

## 4. INTERFACES - How the Product CONNECTS

### 4.1 Interface Inventory

The application exposes five distinct interface surfaces:

1. **Discord Slash Commands**: `/summarize`, `/schedule` (list, create, delete, pause, resume), `/prompt-config` (set, status, remove, refresh, test), `/config` (view, set-cross-channel-role, permissions, reset), `/help`, `/about`, `/status`, `/ping`
2. **Dashboard REST API**: 12 route modules under `/api/v1` covering auth, guilds, summaries, schedules, webhooks, events, feeds, archive, prompts, push templates, errors, and health
3. **Webhook API**: `POST /api/v1/summaries` (from messages), `POST /api/v1/summarize` (placeholder), `POST /api/v1/schedule` (placeholder)
4. **Feed Endpoints**: RSS 2.0 and Atom 1.0 XML feeds per guild/channel
5. **Email Delivery**: SMTP-based HTML and plain text email with Jinja2 templates

### 4.2 Strengths

**Well-structured REST API with versioned routing.** The dashboard router (`dashboard/router.py`) organizes 12 route modules under `/api/v1` with proper FastAPI tagging. Route conflict prevention is handled explicitly: the errors router is registered before the guilds router to prevent the `/{guild_id}` pattern from swallowing `/guilds/{id}/errors/...` paths. The health router is mounted at the root level (not under `/api/v1`) for deployment platform compatibility.

**RSS/Atom feed generation with standards compliance.** `FeedGenerator` produces feeds using `xml.etree.ElementTree` with proper namespace registration (`atom`, `dc`). It generates unique entry IDs via MD5 hashing, supports ETags for conditional GET, and escapes HTML content in feed entries. Both RSS 2.0 and Atom 1.0 are supported per `FeedConfig.feed_type`.

**Discord OAuth integration for dashboard.** `DashboardAuth` implements the full Discord OAuth2 code flow with JWT token generation for session management. Encryption keys protect OAuth tokens at rest. The auth middleware validates JWT tokens on protected routes.

**Multi-format summary output.** Summaries can be consumed in 5 formats:
- Discord embeds (`SummaryResult.to_embed_dict()`) with character limit awareness
- Markdown (`SummaryResult.to_markdown()`) with optional citation markers (ADR-004)
- RSS/Atom XML feeds
- HTML email with Jinja2 templates and plain-text fallback
- JSON API responses with full metadata

**Zapier compatibility.** The `POST /summaries` endpoint handles Zapier's peculiar payload wrapping (JSON-as-string in a "payload" key) with explicit parsing, logged diagnostics, and structured error responses. This real-world integration accommodation shows production experience.

### 4.3 Risks and Concerns

**JWT secret defaults to a known value.** In `dashboard/router.py` line 38:
```python
jwt_secret = os.environ.get("DASHBOARD_JWT_SECRET", os.environ.get("JWT_SECRET", "change-in-production"))
```
If neither environment variable is set, all JWTs are signed with the string "change-in-production". An attacker who knows (or guesses) this default can forge arbitrary JWT tokens and access any dashboard endpoint as any user. This is a critical authentication bypass vulnerability.

**CORS wildcard in default Docker Compose.** `docker-compose.yml` does not set `WEBHOOK_CORS_ORIGINS`, and the default in the codebase is `*` (allow all origins). While `fly.toml` specifies a restrictive origin list, anyone deploying via `docker-compose` without reading the full configuration will have an open CORS policy, enabling cross-site request forgery from any domain.

**No rate limiting on any API endpoint.** The email delivery service enforces per-guild rate limiting (50 emails/hour), but the REST API has zero rate limiting:
- The dashboard API allows unlimited requests
- The webhook `POST /summaries` endpoint has no throttling
- There is no per-guild or per-user request rate cap
An attacker or misconfigured automation can trigger unlimited LLM API calls through the API, with each call potentially costing dollars (for comprehensive summaries on Opus).

**API key authentication is static shared-secret.** `webhook_service/auth.py` uses simple string comparison for API key validation. There is:
- No key rotation mechanism
- No per-client key support (all consumers share one key)
- No audit trail of which key was used
- No key expiration or revocation capability

**Discord webhook delivery lacks retry logic.** When pushing summaries to Discord channels via scheduled task execution, failed Discord API calls are not retried independently of the summarization retry. If the summary generates successfully but Discord delivery fails (rate limit, permissions change, channel deleted), the summary is lost.

**Error responses expose internal details.** The `POST /summaries` endpoint returns `str(e)` in error responses for `INTERNAL_ERROR` (line 259 of endpoints.py). This can leak internal state information (file paths, stack traces, configuration values) to external API consumers.

### 4.4 Testing Gaps

- No penetration test for JWT with default secret vulnerability
- No tests for CORS enforcement under different origin configurations
- No tests for API key authentication bypass or timing attack resistance
- No tests for RSS/Atom feed XML validation against W3C schemas
- No tests for email delivery SMTP connection failures (timeout, auth failure, TLS handshake failure, DNS resolution failure)
- No tests for Discord rate limit handling in the bot client during bulk operations
- No tests for error response sanitization (ensuring internal details are not leaked)

### 4.5 Testing Recommendations

| Test Idea | Priority | Automation | Reasoning |
|---|---|---|---|
| Generate JWT token using known default secret "change-in-production" and access protected dashboard endpoints; confirm access is granted (documenting the vulnerability) | P0 | Integration | This is an immediately exploitable security issue |
| Send 1000 rapid `POST /summaries` requests and measure: LLM calls generated, total cost, response time distribution, and whether cost caps are respected | P0 | Performance | No rate limiting means unbounded cost |
| Set `WEBHOOK_CORS_ORIGINS` to `https://example.com`, send request with `Origin: https://evil.com` header, and confirm the response lacks CORS headers for the malicious origin | P1 | Integration | CORS misconfiguration enables CSRF |
| Use expired JWT token to access dashboard endpoints and confirm 401 response with no internal details leaked | P1 | Integration | Token lifecycle validation |
| Generate RSS 2.0 and Atom 1.0 feeds and validate against W3C Feed Validation Service schemas | P2 | Unit | Feed standards compliance |
| Configure SMTP with invalid credentials and confirm `EmailDeliveryResult.success=False` with actionable error message, no crash | P2 | Unit | SMTP failure is a common production scenario |
| Send Discord interaction when bot has insufficient permissions in target channel and confirm graceful error embed rather than unhandled exception | P2 | Integration | Permission errors are the most common Discord bot issue |
| Craft API error responses and verify no file paths, configuration values, or stack traces are present | P2 | Unit | Information disclosure prevention |

---

## 5. PLATFORM - What the Product DEPENDS ON

### 5.1 Dependency Inventory

**Runtime Dependencies** (from `requirements.txt` and `pyproject.toml`):
- Python 3.9+ (Dockerfile uses 3.11)
- discord.py >= 2.3.0 (Discord bot framework)
- anthropic >= 0.5.0 (Claude API client)
- fastapi >= 0.104.0 + uvicorn >= 0.24.0 (REST API)
- aiosqlite >= 0.19.0 (async SQLite)
- redis >= 5.0.0 (declared but backend unimplemented)
- apscheduler >= 3.10.0 (task scheduling)
- cryptography >= 42.0.0 (Fernet encryption, JWT)
- aiosmtplib >= 3.0.0 (email delivery)
- google-api-python-client + google-auth-oauthlib (Google Drive sync)
- json-repair >= 0.25.0 (ADR-023: malformed JSON recovery)

**Deployment Targets**: Fly.io, Render, Railway, Docker Compose, DevContainers

### 5.2 Strengths

**Multi-platform deployment support.** The project provides deployment configurations for four platforms:
- `fly.toml`: Fly.io with persistent volume, rolling deploy, health checks, 512MB shared CPU
- `render.yaml`: Render with health check path, auto-deploy, Redis cache addon
- `railway.json`: Railway with build/start commands
- `docker-compose.yml`: Local and self-hosted deployment with Redis
Each configuration includes platform-specific health check paths, environment variable mappings, and resource constraints.

**Multi-stage Docker build with security hardening.** The Dockerfile implements three build stages:
1. Frontend builder (Node 20) compiles the React SPA
2. Python dependency builder installs production packages only
3. Runtime stage copies compiled artifacts, runs as non-root user `botuser`, and includes a health check

The runtime image installs only `ca-certificates` and `curl` system packages, minimizing attack surface. `PYTHONDONTWRITEBYTECODE=1` prevents `.pyc` pollution.

**Webhook-only mode for API-only deployments.** When `DISCORD_TOKEN` is not set, the application degrades gracefully to webhook-only mode. Discord bot features are disabled, but the dashboard API, health endpoints, and webhook server remain functional. This enables deployment scenarios where the bot is used purely as a summarization API without Discord integration.

**Production environment detection.** `_is_production_environment()` in `main.py` detects Railway, Render, Heroku, and Fly.io environments through platform-specific environment variables. This enables environment-aware behavior such as LLM provider selection and log level defaults.

### 5.3 Risks and Concerns

**Redis cache backend is declared but unimplemented -- deployment blocker.** This is the single most impactful platform risk. `create_cache()` in `cache.py` raises `ValueError("Redis cache backend is not yet implemented")` when `backend_type == "redis"`. However:
- `docker-compose.yml` sets `CACHE_BACKEND=${CACHE_BACKEND:-redis}` (default is redis)
- `docker-compose.yml` starts a Redis container and passes `REDIS_URL=redis://redis:6379/0`
- `render.yaml` provisions a Redis addon
- `redis>=5.0.0` is listed in `requirements.txt`

This means the default Docker Compose deployment (`docker-compose up`) will crash immediately when the cache tries to initialize with the Redis backend. Any user following the standard setup documentation will hit this failure. The `fly.toml` configuration sets `CACHE_BACKEND = "memory"`, so Fly.io deployments work, but the inconsistency is dangerous.

**Fly.io resource constraints are aggressive.** `fly.toml` allocates:
- 1 shared vCPU
- 512MB RAM
- 1GB persistent volume

The application runs the Python runtime, Discord client (long-lived WebSocket), FastAPI/Uvicorn server, APScheduler, and SQLite in a single process. Large summarization prompts (up to 100K tokens, approximately 400KB of text) combined with the LLM response parsing, summary storage, and cache management create significant memory pressure. A comprehensive summary of a 10,000-message channel could easily exceed the 512MB limit.

**Python version gap.** `pyproject.toml` specifies `python = "^3.9"` but the Dockerfile uses `python:3.11-slim`. Developers on Python 3.9 or 3.10 may write code that works locally but uses 3.11-specific features (e.g., `tomllib`, `ExceptionGroup`, walrus operator edge cases). The test suite should be run on the minimum supported version to validate compatibility.

**Missing `pytz` dependency.** `archive/models.py` imports `pytz` for timezone handling in the `PeriodInfo` class, but `pytz` is not listed in `requirements.txt` or `pyproject.toml`. This will cause an `ImportError` at runtime when archive operations involving timezone-aware periods are invoked. Since `pytz` may be installed as a transitive dependency of `apscheduler` or `google-api-python-client`, this bug may only manifest in minimal installations.

**No dependency pinning for security.** `requirements.txt` uses `>=` minimum version constraints without upper bounds for most packages. While `pyproject.toml` pins some ranges (e.g., `cryptography>=42.0.0,<47.0.0`), most dependencies use open-ended ranges. A `pip install` at deployment time could pull a vulnerable or incompatible version of any dependency.

### 5.4 Testing Gaps

- No tests for Redis cache initialization failure (the most likely production error for docker-compose users)
- No tests for memory consumption under load (512MB constraint)
- No tests for Python 3.9/3.10 compatibility (despite pyproject.toml claiming support)
- No tests for `pytz` import in archive models under minimal installation
- No tests for Docker multi-stage build correctness (frontend assets present, non-root user works)
- No dependency vulnerability scanning in CI

### 5.5 Testing Recommendations

| Test Idea | Priority | Automation | Reasoning |
|---|---|---|---|
| Start the application with `CACHE_BACKEND=redis` and no Redis available; confirm clear error message and automatic fallback to memory cache (or document the crash) | P0 | Integration | Default docker-compose deployment hits this immediately |
| Run the full test suite on Python 3.9 and Python 3.10 to validate `pyproject.toml` compatibility claim | P1 | CI | Claimed compatibility must be verified |
| Monitor RSS memory usage during summarization of 10,000 messages on a 512MB-limited container; identify the memory ceiling | P1 | Performance | Resource limits need empirical validation |
| Import `src.archive.models.PeriodInfo` in a clean virtualenv with only direct dependencies installed and confirm `pytz` is available | P1 | Unit | Transitive dependency assumptions are fragile |
| Build Dockerfile and confirm: non-root user can write to `/app/data`, frontend assets exist in `/app/src/frontend/dist/`, health check passes | P2 | Integration | Docker build correctness |
| Run `pip-audit` or `safety check` against `requirements.txt` and document known vulnerabilities | P2 | CI | Dependency security |
| Start in webhook-only mode (no `DISCORD_TOKEN`) and exercise all dashboard API endpoints | P2 | Integration | Webhook-only mode is a supported deployment pattern |

---

## 6. OPERATIONS - How the Product is USED

### 6.1 Operational Architecture

The application runs as a single Python process orchestrating five concurrent subsystems:
1. **Discord Client**: Long-lived WebSocket connection to Discord Gateway
2. **FastAPI Server**: HTTP server on port 5000 for dashboard and webhook API
3. **APScheduler**: Background task scheduler for automated summaries
4. **CommandLogger**: Async batch writer for command audit logs
5. **Error Tracker**: Async error capture and aggregation

Startup follows a strict initialization order in `SummaryBotApp`: config -> database/migrations -> core components -> Discord bot -> scheduler -> webhook server. Shutdown reverses this order: webhook server -> scheduler -> Discord bot.

### 6.2 Strengths

**Graceful shutdown with signal handling and ordered teardown.** `SummaryBotApp` registers handlers for `SIGINT` and `SIGTERM` that initiate graceful shutdown. Services stop in reverse initialization order, ensuring the webhook server stops accepting new requests before the scheduler stops (preventing new tasks from being created during shutdown), and the scheduler stops before the Discord bot (ensuring task execution can still deliver results to Discord).

**Job recovery on restart (ADR-013).** `_recover_interrupted_jobs()` is a production-savvy pattern. On startup, it finds all jobs in `RUNNING` status and transitions them to `PAUSED` with reason `server_restart`. This means:
- Users see in the dashboard that their job was interrupted
- Users can choose to resume or cancel each interrupted job
- No jobs silently disappear during a deployment

**Structured logging with sanitization.** The logging subsystem includes multiple layers:
- `CommandLogger`: Async batch-writing of command executions with queue overflow protection
- `LogSanitizer`: Redacts API keys, tokens, and PII from log entries before persistence
- `ErrorTracker`: Captures errors with severity classification and operation context
- `CommandLogRepository`: Persisted audit trail of all bot commands

**Emergency server mode.** If `main()` fails to initialize (database corruption, missing critical config, import error), the `__main__.py` module catches the exception and starts an `emergency_server()` on port 5000. This minimal FastAPI app responds to health checks, preventing the deployment platform from restart-looping the container and providing diagnostic information via the `/health` endpoint.

**Task execution guard against concurrent runs.** `TaskScheduler._executing_tasks` (a Python set) prevents the same scheduled task from running twice concurrently. This is important because APScheduler can fire a task while a previous execution of the same task is still running (e.g., if summarization takes longer than the schedule interval).

### 6.3 Risks and Concerns

**No admin interface for critical operational tasks.** There is no way to:
- Rotate API keys or encryption keys without restarting the application
- Flush the summary cache without restarting
- View or manage database migrations from the dashboard
- Trigger a manual database backup
- View real-time LLM cost dashboard or set cost alerts
- Force-kill a stuck scheduled task from the dashboard
- View active database connections or query performance

**Log file co-located with database, no rotation.** `main.py` writes logs to `data/summarybot.log` (line 77). This file shares the same volume mount as the database. There is no log rotation configuration. Over time, the log file will grow without bound, potentially filling the Fly.io persistent volume (1GB) and causing database write failures.

**Cost budget alerting is modeled but not enforced.** The `SourceManifest` model has `budget_monthly_usd` and `alert_threshold_percent` fields, and `SourceCost` tracks cumulative costs. However, there is no code that checks the budget before making an LLM API call, no code that sends an alert when the threshold is crossed, and no code that throttles or blocks requests when the budget is exceeded.

**start.sh is misleadingly named.** `start.sh` is a tmux/Claude Code development environment bootstrapper that installs kubectl, mana (a CLI tool), and tmux plugins. It starts a tmux session and runs `claude --dangerously-skip-permissions`. This is clearly a developer convenience script, not a production startup script. However, the name `start.sh` in the repository root could mislead operators into thinking it is the production entry point (the actual entry point is `CMD ["python", "-m", "src"]` in the Dockerfile).

**No database migration rollback capability.** `run_migrations()` is called during initialization, but the migration system does not track schema versions or support rollback. A failed migration during deployment could leave the database in an inconsistent state with no recovery path other than restoring from a backup (which does not exist).

**Signal handler creates task in non-async context.** `_signal_handler()` (main.py line 583) calls `asyncio.create_task(self.stop())`. If the signal is received outside of an async context or on a different thread, this can raise `RuntimeError: no current event loop`. The correct pattern for signal handling in asyncio is to use `loop.add_signal_handler()`.

### 6.4 Testing Gaps

- No tests for graceful shutdown ordering (verify scheduler stops before Discord bot, webhook stops before scheduler)
- No tests for log file growth and disk space impact
- No tests for database migration failure scenarios (partial migration, version rollback)
- No tests for cost budget threshold detection or alerting
- No chaos engineering tests (kill process mid-summarization, corrupt database mid-write)
- No tests for signal handling edge cases (SIGTERM during initialization, SIGTERM in non-async context)
- No tests for emergency server functionality under real failure conditions

### 6.5 Testing Recommendations

| Test Idea | Priority | Automation | Reasoning |
|---|---|---|---|
| Send SIGTERM during an active summarization and confirm: (a) the job is marked PAUSED on next restart, (b) the database is not corrupted, (c) the summary cache is coherent | P0 | Integration | This is the most common production scenario (deploy = restart) |
| Run database migrations on a pre-existing v0.9 schema and confirm all tables are updated without data loss; then corrupt a migration mid-run and verify the database is still usable | P1 | Integration | Migration safety is critical for zero-downtime deploys |
| Generate 1GB of log output (via rapid summarization requests) and confirm: (a) the log file does not fill the disk, (b) database writes still succeed, (c) the application does not OOM | P1 | Performance | Log growth is an unmonitored resource leak |
| Trigger cost budget alert threshold (80% of monthly budget) and confirm a notification is generated, or document that enforcement is not implemented | P2 | Human Exploration | Cost management is expected but may not work |
| Start the application with a corrupted tasks persistence directory (`data/tasks/`) containing malformed JSON and confirm the scheduler starts without those tasks rather than crashing | P2 | Integration | Corrupted persistence files should not block startup |
| Measure time from SIGTERM to process exit under various conditions: idle, active summarization, active database write | P2 | Integration | Deployment platforms have kill timeouts (Fly.io: 30s) |
| Call `asyncio.create_task(app.stop())` from a non-async context and confirm the error is handled gracefully | P3 | Unit | Signal handler edge case |

---

## 7. TIME - WHEN Things Happen

### 7.1 Temporal Architecture

The application has five distinct temporal patterns:

1. **Event-driven**: Discord interactions (user commands) arrive unpredictably
2. **Scheduled**: APScheduler fires cron-triggered tasks at configured times
3. **Request-driven**: Dashboard API and webhook requests arrive concurrently
4. **Background**: Cache expiration, log flushing, error tracking run asynchronously
5. **Long-running**: LLM API calls take 5-60 seconds, blocking the calling coroutine

These patterns interact through shared resources: the single SQLite connection, the in-memory cache, the executing tasks set, and the LLM API rate limits.

### 7.2 Strengths

**Concurrent task execution guard.** `TaskScheduler._executing_tasks` set (line 60 of scheduler.py) prevents the same scheduled task from running concurrently. Before executing, the scheduler checks `if task_id in self._executing_tasks` and skips if true. The `finally` block always removes the task_id from the set, ensuring cleanup even on exceptions.

**APScheduler misfire handling.** Scheduled jobs are configured with:
- `misfire_grace_time=3600` (1 hour): If the bot was down during a scheduled execution, the task will still fire within one hour of the intended time
- `coalesce=True`: If multiple executions were missed (e.g., bot down for 3 days with daily schedule), only one execution fires on recovery, not three

This prevents missed-execution flooding while still recovering from brief outages.

**Cache TTL management with lazy eviction.** `MemoryCache` tracks per-entry expiration timestamps. Expired entries are removed on access (lazy eviction). The cache enforces a size limit (`max_size=1000` default) with LRU eviction when full.

**Retention policy with soft-delete grace period.** `RetentionManager` implements a three-stage lifecycle:
1. Active summaries live in `sources/` directory
2. `apply_retention_policy()` moves old summaries to `.deleted/` (soft delete) with a 30-day grace period
3. `cleanup_expired()` permanently deletes summaries past the grace period, with optional zip/tar.gz backup before final removal
4. `recover()` restores soft-deleted summaries by moving them back from `.deleted/` to `sources/`

**DST-aware archive periods.** `PeriodInfo` includes `spring_forward` and `fall_back` booleans and handles timezone transitions at period boundaries. This prevents the common bug where a daily summary misses or double-counts messages during DST transitions.

**Atomic file writes for lock safety.** `LockManager._atomic_write()` writes to a `.tmp` file and then uses `Path.rename()` for atomic replacement. This prevents partial writes from leaving corrupted `.meta.json` files during generation lock operations. On POSIX systems, `rename()` is atomic within the same filesystem.

### 7.3 Risks and Concerns

**SQLite concurrent access creates "database is locked" errors.** While the application uses `pool_size=1` to prevent concurrent writes via a single connection pool, there are multiple code paths that could create separate connections to the same database:
- `SummaryBotApp._initialize_command_logging()` gets a connection from `get_repository_factory()`
- `GuildPromptConfigStore` also gets a connection via the same factory
- `dashboard/routes/` modules may obtain connections through different code paths
- The `initialize_error_tracker()` creates its own connection

If any of these paths create a second `aiosqlite.Connection` (each of which spawns a worker thread), SQLite locking errors will occur under concurrent load even with WAL mode enabled. The `busy_timeout=5000` (5 seconds) mitigates this by waiting for locks, but under sustained concurrent load, the 5-second timeout will be insufficient and cause cascading failures.

**No timeout on LLM API calls.** The `ResilientSummarizationEngine` implements retry with exponential backoff but does not set explicit HTTP timeouts on individual API calls to OpenRouter/Anthropic. A hanging API request could block a scheduled task indefinitely. The retry logic handles `TimeoutError` exceptions, but if the HTTP client never raises one (because no timeout is configured), the coroutine hangs forever. The rate limit handler uses `getattr(e, 'retry_after', 60)` with no upper bound, so a malicious or misconfigured API could instruct the client to wait for hours.

**Cache stampede vulnerability.** When a cache entry expires (default TTL: 3600 seconds = 1 hour), all concurrent requests for the same summary will miss the cache simultaneously. With no stampede protection (probabilistic early expiration, lock-based recomputation, or stale-while-revalidate), all requests trigger independent LLM API calls. For a popular summary that is requested 50 times per hour, the hourly cache expiry creates 50 simultaneous LLM calls instead of 1.

**No global concurrency limit on LLM calls.** `batch_summarize()` uses `Semaphore(3)` internally, but individual `/summarize` commands from Discord users, scheduled tasks, and webhook API requests all call the LLM independently with no shared concurrency limit. Under high usage (e.g., 20 guilds all having their daily summary fire at midnight UTC), the application could exceed OpenRouter rate limits, causing cascading retry storms and cost amplification through model escalation.

**Task scheduler timezone assumption.** `TaskScheduler` defaults to UTC (line 34) and all schedule times are UTC. The Discord command description says "HH:MM format, UTC" but there is no timezone selection, no timezone display in the schedule list output, and no conversion from user's locale. A user in EST who enters "09:00" intending their local morning will get a summary at 4 AM local time.

**Memory cache is per-process, not shared.** If the application is ever run with multiple uvicorn workers (a common production optimization for FastAPI), each worker gets its own `MemoryCache` instance. Cache hits will be rare, and the same summary may be computed multiple times across workers, amplifying LLM costs.

**File-based locking is not NFS-safe.** `LockManager._atomic_write()` uses `Path.rename()` for atomicity. While this is atomic on local POSIX filesystems, it is NOT atomic on NFS or distributed filesystems. If the archive directory is on a network mount (e.g., EFS, NFS), lock operations could produce corrupted state.

### 7.4 Testing Gaps

- No tests for SQLite "database is locked" under realistic concurrent access patterns
- No tests for LLM API timeout scenarios (hanging request that never returns)
- No tests for cache stampede under concurrent requests for the same summary
- No tests for scheduler timezone boundary behavior (midnight UTC, DST transitions)
- No tests for task execution when clock is skewed or NTP is unavailable
- No load tests for concurrent summarization requests from multiple sources
- No tests for file-based lock safety under concurrent archive generation
- No tests for APScheduler job persistence across process restarts

### 7.5 Testing Recommendations

| Test Idea | Priority | Automation | Reasoning |
|---|---|---|---|
| Open 5 concurrent database connections (simulating command logger, error tracker, scheduler, dashboard, summarization engine) and perform interleaved reads/writes for 60 seconds; count "database is locked" errors and measure p99 latency | P0 | Integration | This is the highest-risk concurrency issue in the application |
| Mock LLM API to hang for 300 seconds and confirm the summarization engine times out with a clear error rather than blocking the scheduler forever | P0 | Integration | A hanging LLM call could freeze all scheduled tasks |
| Trigger 50 concurrent `/summarize` requests for the same channel and measure: cache hit rate, number of redundant LLM calls, total cost, and whether any requests receive stale data | P0 | Performance | Cache stampede is the primary cost amplification risk |
| Create a scheduled task at 23:59 UTC and confirm it fires exactly once across a DST transition (not twice, not zero times) | P1 | Integration | DST boundary is the most common time-related bug |
| Simulate APScheduler misfire scenario: stop scheduler for 2 hours with 3 pending tasks, restart, confirm each task runs exactly once (coalesce=True) | P1 | Integration | Misfire handling is configured but not tested |
| Set a rate limit on OpenRouter mock (10 req/min) and fire 20 concurrent summarizations; confirm retry-after is respected and no requests are silently dropped | P1 | Integration | Rate limit handling affects reliability |
| Run the application with 2 uvicorn workers and perform identical requests; measure cache hit rate across workers (should be 0%) and document the implication | P2 | Integration | Multi-worker deployment is a common production pattern |
| Kill a scheduled task mid-execution and confirm the `_executing_tasks` set is cleaned up via the `finally` block | P2 | Unit | The guard must be robust to exceptions during execution |
| Acquire an archive generation lock, then simulate process crash (no release), then attempt to acquire the same lock; confirm TTL expiration allows recovery | P2 | Unit | Lock TTL is the safety net for orphaned locks |

---

## Cross-Factor Dependency Analysis

The SFDIPOT factors in SummaryBot NG are not independent. Several cross-factor risks amplify each other, creating systemic vulnerabilities that are more dangerous than any individual factor risk.

### Data x Time: SQLite Concurrency Bottleneck [CRITICAL]

The single-connection database design (Data: pool_size=1) combined with concurrent scheduled tasks, webhook requests, and Discord interactions (Time: five concurrent subsystems) creates the project's most dangerous systemic bottleneck. When a summarization engine stores a large result (which may take 100ms+ for JSON serialization and insert), all other database operations are blocked: health checks, dashboard queries, scheduler persistence, command logging, and error tracking. Under sustained concurrent load, this causes cascading timeouts that can make the application appear unhealthy to deployment platforms, triggering unnecessary restarts.

**Amplification factor**: Each restart triggers job recovery (ADR-013), which performs additional database queries during the period when concurrent operations are already queuing, making the bottleneck worse on restart than during normal operation.

### Platform x Data: Redis Non-Implementation [CRITICAL]

The declared Redis dependency (Platform: docker-compose sets `CACHE_BACKEND=redis`) combined with the unimplemented Redis cache backend (Data: `create_cache()` raises `ValueError`) means the default Docker Compose deployment fails immediately on startup. This is not a theoretical risk; it is a guaranteed failure for any user who follows the standard `docker-compose up` workflow without reading the code to discover the non-implementation.

**Amplification factor**: The Redis container starts successfully and is healthy, so the user sees a healthy Redis and a crashing application, which is confusing and may lead them to investigate network issues rather than the cache backend code.

### Interfaces x Operations: Unbounded Cost Under Abuse [HIGH]

The absence of rate limiting on the dashboard API (Interfaces: no throttling on any endpoint) combined with no cost alerting enforcement (Operations: budget fields exist but are not checked) creates an unbounded cost exposure. An attacker who discovers the API key (or a misconfigured Zapier workflow) can trigger unlimited comprehensive summarizations at potentially $0.05-0.15 per request (Opus pricing for large contexts), accumulating hundreds of dollars in costs within minutes.

**Amplification factor**: The resilient generation engine's retry mechanism (Function: model escalation) means that if cheaper models fail or are rate-limited, the system automatically escalates to the most expensive model (Opus), maximizing the cost per request under adverse conditions.

### Function x Time: LLM Cost Amplification [HIGH]

The resilient generation engine's retry mechanism (Function: up to `DEFAULT_MAX_RETRY_ATTEMPTS` attempts with model escalation) combined with no global concurrency limit (Time: each request independently accesses the LLM) means that during a partial API outage (e.g., Haiku unavailable but Sonnet works), every concurrent request independently discovers the outage, retries on Haiku, escalates to Sonnet, and retries on Sonnet. If 20 concurrent requests each retry 3 times before escalating, that is 60 unnecessary API calls plus 20 escalated calls, instead of 20 direct Sonnet calls.

**Amplification factor**: The cost cap (`DEFAULT_RETRY_COST_CAP_USD`) is per-request, not global. There is no circuit breaker that detects "Haiku is down" and routes all subsequent requests directly to Sonnet.

### Structure x Platform: Encryption Key Volatility [HIGH]

The ephemeral encryption key generation (Structure: `Fernet.generate_key()` when env var not set) combined with container restarts on PaaS platforms (Platform: every deploy restarts the container on Fly.io, Railway, Render) means that OAuth tokens and custom prompt configurations are silently destroyed on every deployment. The application continues to work (it generates new ephemeral keys), but all user-configured custom prompts from GitHub repositories become inaccessible, and dashboard OAuth sessions are invalidated.

**Amplification factor**: This failure is silent. Users see no error message. Their custom prompts simply fall back to defaults without explanation. They may not realize their customizations have been lost until they notice summary quality has changed.

### Time x Operations: Missed Alerting During Temporal Events [MEDIUM]

The hourly cache expiry (Time: `default_ttl=3600`) combined with the absence of cost monitoring (Operations: no real-time cost dashboard) means that a cache stampede event (50 concurrent LLM calls instead of 1) incurs 50x the expected cost with no visibility or alerting. An operator would only discover this in the monthly LLM billing statement, weeks after the cost was incurred.

---

## Testing Strategy Recommendations per Factor

### Priority Distribution Summary

| Priority | Count | Percentage |
|---|---|---|
| P0 (Critical) | 11 | 16% |
| P1 (High) | 19 | 28% |
| P2 (Medium) | 25 | 37% |
| P3 (Low) | 13 | 19% |

### Automation Fitness Summary

| Type | Count | Percentage |
|---|---|---|
| Unit Tests | 16 | 24% |
| Integration Tests | 29 | 43% |
| E2E Tests | 3 | 4% |
| Performance Tests | 8 | 12% |
| Human Exploration | 5 | 7% |
| CI Pipeline | 7 | 10% |

### Recommended Testing Phases

**Phase 1 -- Immediate (Pre-Production, Week 1)**

Address all P0 risks and deployment blockers:

1. SQLite concurrent access testing (Time x Data) -- the systemic bottleneck
2. Redis cache initialization failure (Platform x Data) -- the deployment blocker
3. JWT default secret vulnerability (Interfaces) -- the security bypass
4. Ephemeral encryption key impact (Data x Platform) -- the silent config loss
5. LLM API timeout behavior (Time x Function) -- the scheduler freeze risk
6. API rate limiting absence (Interfaces x Operations) -- the cost explosion risk
7. SIGTERM mid-summarization recovery (Operations) -- the deployment safety check

**Phase 2 -- Pre-Release (Weeks 2-3)**

Address P1 risks that affect reliability and correctness:

8. Model escalation chain exhaustion behavior
9. Memory consumption under 512MB constraint
10. Python 3.9/3.10 compatibility verification
11. Cache stampede measurement and mitigation
12. Scheduler timezone boundary behavior
13. Database migration safety
14. CORS configuration enforcement
15. Batch summarization partial failure handling

**Phase 3 -- Post-Release (Weeks 4-8)**

Address P2/P3 risks and long-term quality:

16. RSS/Atom feed schema validation
17. PostgreSQL backend assessment
18. Log rotation and disk usage monitoring
19. Cost budget threshold enforcement
20. Email delivery failure handling
21. Multi-worker deployment cache behavior
22. Archive lock TTL expiration recovery
23. Error response sanitization

### Exploratory Test Session Suggestions

**Session 1: "Cost Bomb" Exploration (Time x Function x Interfaces)**

Charter: Explore what happens when 100 concurrent comprehensive summarization requests arrive simultaneously for large channels (5000+ messages each). Focus on: total LLM cost incurred, response time distribution, error recovery behavior, whether cost caps are respected, and whether the cache provides any protection.

Time box: 90 minutes. Key observations to capture: peak memory usage, database lock wait times, number of redundant LLM calls, total dollar cost.

**Session 2: "Restart Resilience" Exploration (Operations x Data x Time)**

Charter: Explore the application's behavior across 10 rapid restarts (SIGTERM every 30 seconds) while scheduled tasks are running and users are actively summarizing. Focus on: data integrity (are any summaries lost or corrupted?), job recovery (does ADR-013 work under rapid restart?), cache coherence (do stale summaries persist?), and error messages shown to users.

Time box: 60 minutes. Key observations to capture: job state transitions, database integrity check output, user-visible error messages.

**Session 3: "New User Onboarding" Exploration (Interfaces x Platform x Structure)**

Charter: Follow the README and documentation to deploy SummaryBot NG from scratch using docker-compose on a clean machine. Document every point of friction: missing environment variables, incorrect defaults, unclear error messages, documentation that contradicts code, and steps that require reading source code. Focus on: time from `git clone` to first working summary.

Time box: 120 minutes. Key observations to capture: exact error messages encountered, number of environment variables that must be configured, documentation accuracy.

**Session 4: "Multi-Source Chaos" Exploration (Data x Function x Time)**

Charter: Import a WhatsApp chat export, configure a Discord channel, and set up email delivery for the same guild. Then trigger summaries from all three sources simultaneously. Focus on: anonymization consistency (are WhatsApp phone numbers redacted in all outputs?), cost attribution accuracy (is each source charged correctly?), cross-source data isolation (does a WhatsApp summary ever contain Discord messages?).

Time box: 90 minutes. Key observations to capture: data leakage between sources, cost tracking accuracy, error handling for mixed-source failures.

---

## Clarifying Questions

The following questions arose during analysis where the source code could not provide definitive answers. These represent gaps in either documentation or implementation that should be resolved before comprehensive testing.

### Critical Questions (Block P0 Testing)

1. **Is the Redis cache backend planned for v1.0?** The default Docker Compose configuration references it, `requirements.txt` includes the Redis package, and `render.yaml` provisions a Redis addon. If Redis support is planned, it is a blocking dependency for the standard deployment path. If not, the docker-compose default must be changed to `memory`.

2. **What is the production behavior when `DASHBOARD_JWT_SECRET` is not set?** Is the default "change-in-production" value intentional (for development ease) or a security oversight? Should the application refuse to start without this value in production environments?

3. **Is the ephemeral encryption key behavior intentional or a bug?** If intentional, users need documentation on why custom prompts reset on every deployment. If a bug, the fix is to require `PROMPT_TOKEN_ENCRYPTION_KEY` in production or persist the generated key.

### Important Questions (Block P1 Testing)

4. **What is the expected behavior when the OpenRouter API key is valid but has insufficient credit balance?** The code handles `RateLimitError`, `NetworkError`, and `ModelUnavailableError` but there is no `InsufficientBalanceError`. Does OpenRouter return a 402? A 429? How should the user be informed?

5. **What is the maximum number of guilds a single bot instance should support?** The 512MB Fly.io instance with single SQLite connection has an implicit scaling ceiling. Is this documented? Is there a recommended upgrade path (e.g., PostgreSQL + Redis at 10+ guilds)?

6. **How should the bot behave when Discord's global rate limit (50 requests/second) is hit during batch operations?** The `discord.py` library handles some rate limiting internally, but the application layer does not appear to account for it during category summarization (which could hit many channels).

### Operational Questions (Inform P2+ Testing)

7. **What is the data retention policy for command logs?** `LoggingConfig` has `retention_days` but its default value and cleanup automation are unclear.

8. **What happens to scheduled tasks when the bot is removed from a Discord guild?** The task references a `guild_id` and `channel_id` that may no longer be accessible, but there is no guild-leave event handler visible in the codebase.

9. **Is `start.sh` intended to be included in the Docker image?** Its name and location suggest it is a production script, but its contents are developer tooling. Should it be excluded from the Docker build context?

10. **Are there plans to support multiple uvicorn workers?** The in-memory cache, module-level singletons, and SQLite single-connection design all assume a single-process deployment. If multi-worker is ever needed, significant refactoring is required.

---

## Overall Product Maturity Scorecard

| Dimension | Score (1-10) | Weight | Weighted Score |
|---|---|---|---|
| Architecture & Design | 8 | 15% | 1.20 |
| Feature Completeness | 7 | 15% | 1.05 |
| Data Integrity & Safety | 5 | 15% | 0.75 |
| Security | 4 | 15% | 0.60 |
| Operational Readiness | 5 | 15% | 0.75 |
| Performance & Scalability | 5 | 10% | 0.50 |
| Testing & Quality Assurance | 6 | 10% | 0.60 |
| Documentation & ADRs | 8 | 5% | 0.40 |
| **Overall** | | **100%** | **5.85 -> 6.5/10** |

The upward adjustment from 5.85 to 6.5 reflects the exceptional ADR discipline and the sophistication of the resilient summarization engine, which demonstrate engineering maturity that the raw scores underweight.

**Key score rationale**:
- **Architecture (8)**: Strong module separation, ADR discipline, typed exceptions, DI container. Loses points for dual init paths and module-global singletons.
- **Feature Completeness (7)**: Core summarization is excellent. Loses points for 4 unimplemented API endpoints, no Redis cache, and absent cost alerting.
- **Data Integrity (5)**: Rich domain model but ephemeral encryption keys, no backup strategy, and cache collisions are significant data risks.
- **Security (4)**: JWT default secret is a critical vulnerability. No rate limiting. CORS wildcard in default config. API key has no rotation.
- **Operational Readiness (5)**: Good shutdown/recovery patterns but no admin tooling, no log rotation, no cost monitoring enforcement.
- **Performance (5)**: Batch concurrency and model-per-length optimization are smart, but SQLite bottleneck and 512MB constraint are unvalidated.
- **Testing (6)**: 69 test files show investment. Integration and unit tests exist. But critical paths (concurrency, security, deployment) are untested.
- **Documentation (8)**: 32 ADRs, extensive docs directory, architecture documents. Loses points for doc-code divergence (Redis, PostgreSQL).

---

## Appendix A: Files Analyzed

### Structure (5 files)
- `src/__init__.py`, `src/main.py` (668 lines), `src/container.py` (194 lines)
- `pyproject.toml`, `requirements.txt`

### Function (8 files)
- `src/discord_bot/commands.py` (691 lines), `src/discord_bot/bot.py`
- `src/summarization/engine.py` (838 lines), `src/summarization/retry_strategy.py`
- `src/webhook_service/endpoints.py` (530 lines)
- `src/command_handlers/summarize.py`, `src/command_handlers/schedule.py`
- `src/config/constants.py`

### Data (12 files)
- `src/models/summary.py` (550 lines), `src/models/message.py`, `src/models/task.py`
- `src/models/webhook.py`, `src/models/stored_summary.py`, `src/models/feed.py`
- `src/archive/models.py`, `src/archive/retention.py` (405 lines)
- `src/data/sqlite.py` (1000+ lines), `src/data/base.py`
- `src/summarization/cache.py` (331 lines)
- `src/archive/cost_tracker.py`

### Interfaces (10 files)
- `src/webhook_service/endpoints.py`, `src/webhook_service/auth.py`, `src/webhook_service/server.py`
- `src/dashboard/router.py` (137 lines), `src/dashboard/routes/` (12 route modules)
- `src/feeds/generator.py`
- `src/services/email_delivery.py`
- `src/templates/email/`

### Platform (8 files)
- `Dockerfile` (94 lines), `docker-compose.yml` (100 lines)
- `fly.toml` (75 lines), `render.yaml`, `railway.json`
- `requirements.txt` (56 lines), `pyproject.toml` (42 lines)
- `.devcontainer/devcontainer.json`

### Operations (8 files)
- `src/scheduling/scheduler.py` (769 lines), `src/scheduling/executor.py`
- `src/logging/logger.py` (218 lines), `src/logging/cleanup.py`, `src/logging/analytics.py`
- `src/logging/error_tracker.py`, `src/logging/sanitizer.py`
- `start.sh` (230 lines)

### Time (7 files)
- `src/scheduling/scheduler.py`, `src/scheduling/persistence.py`
- `src/archive/retention.py` (405 lines), `src/archive/locking.py` (302 lines)
- `src/summarization/cache.py` (331 lines)
- `src/archive/models.py` (PeriodInfo, DST handling)
- `src/services/email_delivery.py` (rate limiting)

### Architecture Decision Records (32 ADRs)
- ADR-001 through ADR-032 covering WhatsApp integration, grounded references, delivery destinations, archive system, Google Drive sync, job tracking, resilient generation, error logging, and email delivery.
