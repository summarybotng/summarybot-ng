# QE Tests and Coverage Report
## summarybot-ng
**Date:** 2026-03-13
**Analyst:** V3 QE Coverage Specialist (Agentic QE v3)
**Branch:** aqe-fleet-working-branch

---

## Executive Summary

**Overall Test Health Grade: B-**

The summarybot-ng project has a substantial unit test suite with strong coverage of the core business logic. However, significant structural gaps exist in integration and E2E testing, and a large set of source modules — particularly the dashboard route layer, feeds subsystem, scheduling delivery backends, archive sub-modules, and all exception classes — have no direct test files at all. The frontend has near-zero unit test coverage. Flakiness risk is elevated by real-time sleeps in unit tests, and the test pyramid is heavily top-heavy with unit tests comprising over 88% of test functions.

### Key Metrics

| Metric | Value |
|---|---|
| Source files (Python, non-init) | 141 |
| Source files with testable code | ~140 |
| Test files | 67 |
| Total test functions | ~1,442 |
| Unit test functions | 1,261 (87.4%) |
| Integration test functions | 42 (2.9%) |
| E2E test functions | 14 (1.0%) |
| Security test functions | 47 (3.3%) |
| Performance test functions | 23 (1.6%) |
| Logging test functions | 46 (3.2%) |
| Misc (root-level) test functions | 9 (0.6%) |
| Source modules with no test file | ~83 |
| `pytest.mark.parametrize` usages | 1 |
| Real-time sleep calls in tests | 31 |
| Placeholder (`pass`) tests | 2 |
| Frontend unit test files | 1 (trivial) |
| Frontend Playwright test files | 2 |

---

## Coverage Gap Analysis

The following table maps source modules to their test counterparts. "Direct test file" means a test file whose name directly corresponds to the source module. "Tested via" means the module is exercised through a higher-level test file.

### Fully Covered Modules (direct test files)

| Source Module | Test File | Notes |
|---|---|---|
| `summarization/engine.py` | `test_summarization/test_engine.py` | Good depth |
| `summarization/claude_client.py` | `test_summarization/test_claude_client.py` | Excellent depth |
| `summarization/cache.py` | `test_summarization/test_cache.py` | Good |
| `summarization/retry_strategy.py` | `test_summarization/test_retry_strategy.py` | Good |
| `summarization/prompt_builder.py` | `test_summarization/test_prompt_builder.py` | Good |
| `summarization/response_parser.py` | `test_summarization/test_response_parser.py` | Good |
| `summarization/optimization.py` | `test_summarization/test_optimization.py` | Good |
| `scheduling/scheduler.py` | `test_scheduling/test_scheduler.py` | Good |
| `scheduling/executor.py` | `test_scheduling/test_executor.py` | Good |
| `scheduling/persistence.py` | `test_scheduling/test_persistence.py` | Good |
| `scheduling/tasks.py` | `test_scheduling/test_tasks.py` | Good |
| `permissions/manager.py` | `test_permissions/test_manager.py` | Good |
| `permissions/cache.py` | `test_permissions/test_cache.py` | Good |
| `permissions/roles.py` | `test_permissions/test_roles.py` | Good |
| `permissions/validators.py` | `test_permissions/test_validators.py` | Good |
| `discord_bot/bot.py` | `test_discord_bot/test_bot.py` | Good |
| `discord_bot/commands.py` | `test_discord_bot/test_commands.py` | Partial |
| `discord_bot/events.py` | `test_discord_bot/test_events.py` | Good |
| `discord_bot/utils.py` | `test_discord_bot/test_utils.py` | Good |
| `message_processing/cleaner.py` | `test_message_processing/test_cleaner.py` | Good |
| `message_processing/filter.py` | `test_message_processing/test_filter.py` | Good |
| `message_processing/extractor.py` | `test_message_processing/test_extractor.py` | Good |
| `message_processing/validator.py` | `test_message_processing/test_validator.py` | Good |
| `dashboard/auth.py` | `test_dashboard/test_auth.py` | Good |
| `dashboard/middleware.py` | `test_dashboard/test_middleware.py` | Good |
| `dashboard/models.py` | `test_dashboard/test_models.py` | Good |
| `dashboard/utils/scope_resolver.py` | `test_dashboard/test_scope_resolver.py` | Good |
| `webhook_service/auth.py` | `test_webhook_service/test_auth.py` | Good |
| `webhook_service/endpoints.py` | `test_webhook_service/test_endpoints.py` | Good |
| `webhook_service/formatters.py` | `test_webhook_service/test_formatters.py` | Good |
| `webhook_service/server.py` | `test_webhook_service/test_server.py` | Good |
| `webhook_service/validators.py` | `test_webhook_service/test_validators.py` | Good |
| `command_handlers/base.py` | `test_command_handlers/test_base.py` | Good |
| `command_handlers/config.py` | `test_command_handlers/test_config.py` | Good |
| `command_handlers/schedule.py` | `test_command_handlers/test_schedule.py` | Good |
| `command_handlers/summarize.py` | `test_command_handlers/test_summarize.py` | Good |
| `command_handlers/utils.py` | `test_command_handlers/test_utils.py` | Good |
| `config/settings.py` | `test_config/test_settings.py` | Good |
| `data/sqlite/*` (repositories) | `test_data/test_repositories.py`, `test_sqlite.py`, `test_stored_summary_repository.py` | Reasonable |
| `archive/importers/whatsapp.py` | `test_archive/test_whatsapp_importer.py` | Good |
| `services/anonymization/phone_anonymizer.py` | `test_anonymization/test_phone_anonymizer.py` | Good |
| `services/email_delivery.py` | `test_email_delivery.py` | Good |
| `logging/logger.py` | `test_logging/test_logger.py` | Good |
| `logging/models.py` | `test_logging/test_models.py` | Good |
| `logging/sanitizer.py` | `test_logging/test_sanitizer.py` | Good |
| `prompts/models.py` | `test_prompts/test_models.py` | Good |
| `prompts/schema_validator.py` | `test_prompts/test_schema_validator.py` | Good |
| `models/summary.py` | `test_models/test_summary.py` | Good |

### Modules with No Test File (Coverage Gaps)

| Source Module | Risk Level | Gap Description |
|---|---|---|
| `dashboard/routes/summaries.py` (2,732 lines) | **Critical** | Largest source file; handles all summary CRUD, regeneration, push-to-channel. No direct test. |
| `dashboard/routes/archive.py` (2,069 lines) | **Critical** | Second largest; archive browsing, filtering, export. No direct test. |
| `command_handlers/prompt_config.py` | **High** | Command handler for prompt configuration. No test. |
| `summarization/engine.py` sub-paths | Medium | `engine.py` has tests but missing coverage for streaming and advanced caching paths |
| `scheduling/delivery/discord.py` | **High** | Discord delivery backend; used in all scheduled summaries. No test. |
| `scheduling/delivery/email.py` | **High** | Email delivery backend. No test. |
| `scheduling/delivery/webhook.py` | **High** | Webhook delivery backend. No test. |
| `scheduling/delivery/dashboard.py` | **High** | Dashboard delivery backend. No test. |
| `dashboard/routes/guilds.py` | **High** | Guild CRUD endpoints. No test. |
| `dashboard/routes/schedules.py` | **High** | Schedule CRUD endpoints. No test. |
| `dashboard/routes/feeds.py` | **High** | Feed CRUD endpoints. No test. |
| `dashboard/routes/webhooks.py` | High | Webhook configuration endpoints. No test. |
| `dashboard/routes/prompts.py` | High | Prompt configuration endpoints. No test. |
| `dashboard/routes/push_templates.py` | Medium | Push template endpoints. No test. |
| `dashboard/routes/health.py` | Medium | Health endpoint. Covered indirectly in E2E. |
| `dashboard/routes/events.py` | Medium | Event streaming endpoints. No test. |
| `dashboard/routes/errors.py` | Medium | Error routes. No test. |
| `dashboard/router.py` | Medium | FastAPI router assembly. No test. |
| `feeds/generator.py` | **High** | RSS/Atom feed generation. No test. |
| `feeds/ingest_handler.py` | **High** | Ingest handling for external feeds. No test. |
| `feeds/whatsapp_routes.py` | Medium | WhatsApp webhook routes. No test. |
| `services/push_message_builder.py` | **High** | Builds push notification messages. No test. |
| `services/summary_push.py` (905 lines) | **High** | Large module; coordinates push delivery. No test. |
| `archive/generator.py` (872 lines) | **High** | Core archive generation logic. No test. |
| `archive/scanner.py` | **High** | Archive scanning. No test. |
| `archive/writer.py` | **High** | Archive writing. No test. |
| `archive/retention.py` | High | Archive retention policy. No test. |
| `archive/locking.py` | High | File locking for archive concurrency. No test. |
| `archive/backfill.py` | Medium | Backfill functionality. No test. |
| `archive/cost_tracker.py` | Medium | Partially tested via `test_archive.py`. |
| `archive/sources.py` | Medium | Partially tested via `test_archive.py`. |
| `archive/sync/service.py` | High | Google Drive sync service. No test. |
| `archive/sync/google_drive.py` | High | Google Drive integration. No test. |
| `archive/sync/oauth.py` | **Critical** | OAuth flows for sync. No test. |
| `archive/api_keys/backends.py` | High | API key storage backends. No test. |
| `archive/api_keys/resolver.py` | High | API key resolution. No test. |
| `message_processing/fetcher.py` | **High** | Discord message fetching; critical path. No test. |
| `message_processing/processor.py` | **High** | Main message processing pipeline. No test. |
| `message_processing/whatsapp_processor.py` | High | WhatsApp-specific processing. No test. |
| `config/environment.py` | Medium | Environment variable loading. No test. |
| `config/constants.py` | Low | Constants file. Low risk. |
| `config/validation.py` | High | Config validation logic. No test. |
| `exceptions/api_errors.py` | Medium | Exception classes. No test. |
| `exceptions/discord_errors.py` | Medium | Exception classes. No test. |
| `exceptions/summarization.py` | Medium | Exception classes. No test. |
| `exceptions/validation.py` | Medium | Exception classes. No test. |
| `exceptions/webhook.py` | Medium | Exception classes. No test. |
| `data/push_template_repository.py` | High | Repository for push templates. No test. |
| `data/sqlite/config_repository.py` | High | Config repository implementation. No direct test. |
| `data/sqlite/error_repository.py` | Medium | Error log repository. No test. |
| `data/sqlite/feed_repository.py` | High | Feed repository. No test. |
| `data/sqlite/filters.py` | Medium | SQL filter builder. No test. |
| `data/sqlite/ingest_repository.py` | High | Ingest repository. No test. |
| `data/sqlite/summary_job_repository.py` | High | Summary job repository. No test. |
| `data/sqlite/webhook_repository.py` | High | Webhook repository. No test. |
| `logging/analytics.py` | Medium | Log analytics. No test. |
| `logging/cleanup.py` | Medium | Log cleanup. No test. |
| `logging/decorators.py` | Medium | Logging decorators. No test. |
| `logging/error_tracker.py` | High | Error tracking. No test. |
| `logging/query.py` | Medium | Log query interface. No test. |
| `logging/repository.py` | High | Log repository. Mocked in tests, not tested directly. |
| `prompts/cache.py` | High | Prompt caching. No direct test. |
| `prompts/default_provider.py` | High | Default prompt provider. No test. |
| `prompts/fallback_chain.py` | High | Prompt fallback chain. No test. |
| `prompts/github_client.py` | High | GitHub prompt retrieval. No test. |
| `prompts/guild_config_store.py` | High | Guild prompt config store. No test. |
| `prompts/path_parser.py` | Medium | Prompt path parsing. No test. |
| `prompts/resolver.py` | **Critical** | Top-level prompt resolution. No test. |
| `models/message.py` | High | Core message model. No dedicated test. |
| `models/task.py` | Medium | Used in scheduler tests but not directly tested. |
| `models/user.py` | Medium | User/permission model. No direct test. |
| `models/stored_summary.py` | Medium | Stored summary model. No direct test. |
| `models/feed.py` | Medium | Feed model. No test. |
| `models/ingest.py` | Medium | Ingest model. No test. |
| `models/webhook.py` | Medium | Webhook model. No test. |
| `models/push_template.py` | Medium | Push template model. No test. |
| `models/reference.py` | Low | Reference model. No test. |
| `models/summary_job.py` | Medium | Summary job model. No test. |
| `models/error_log.py` | Medium | Error log model. No test. |
| `utils/time.py` | Medium | Time utilities. No test. |
| `webhook_service/logging_middleware.py` | Medium | Request logging middleware. No test. |
| `main.py` | Low | App entrypoint. No test (acceptable). |

---

## Test Quality Assessment

### Overall Quality: Good in covered areas, with structural concerns

#### test_summarization/ (7 files, ~3,800 lines)
**Grade: A-**

- `test_claude_client.py`: Excellent. Tests retry logic, rate limiting, all error types, cost estimation, streaming. Proper use of `patch.object` on internal client. Assertions are specific (checks `api_name`, `message`, token counts). Minor weakness: one assertion checks `exc_info.value is not None` (lines 166, 224) instead of message content.
- `test_engine.py`: Good. Tests success path, cached results, insufficient content, API errors, thread context, attachments. AAA pattern is clear. The prompt content assertion (`"thread" in prompt_arg.lower()`) is somewhat loose but acceptable.
- `test_retry_strategy.py`: Good. Tests enum values, dataclass creation, tracker logic. Thorough.
- `test_optimization.py`: Good. Tests batch processing and deduplication logic.
- `test_response_parser.py`: Large (610 lines). Good coverage of parsing logic.
- `test_cache.py`: Contains real-time sleeps (`await asyncio.sleep(1.1)`) for TTL testing — this is a flakiness risk on slow CI machines.
- `test_prompt_builder.py`: Good.

#### test_scheduling/ (4 files, ~2,500 lines)
**Grade: B+**

- `test_scheduler.py`: Very comprehensive. Tests all schedule types (daily, weekly, monthly, custom CRON, one-time), pause/resume, concurrent tasks, persistence across restarts, double-start/stop idempotency. Edge cases covered. The key weakness is two tests use `asyncio.sleep(2)` and `asyncio.sleep(3)` to wait for APScheduler task execution — these are inherently flaky on CI under load.
- `test_executor.py` and `test_persistence.py`: Good depth with real file-system I/O in `test_persistence.py` using `tmp_path`.
- `test_tasks.py`: Good model validation coverage.

#### test_permissions/ (4 files, ~1,500 lines)
**Grade: A-**

- `test_manager.py`: Excellent. Tests access control, caching behavior, error-defaulting-to-deny, cache invalidation. Integration tests within the same file using real `PermissionCache` instance (not mocked) improve confidence.
- `test_cache.py`: Contains real-time sleeps for TTL expiry (`asyncio.sleep(0.01)`) — low risk on modern hardware but not deterministic by design.
- `test_roles.py` and `test_validators.py`: Good.

#### test_discord_bot/ (4 files, ~1,070 lines)
**Grade: B**

- `test_bot.py`: Good lifecycle testing, property checks, guild/channel access. The `test_start_bot` test uses `asyncio.sleep(0.1)` to wait for task setup — fragile if the event loop is under load.
- `test_commands.py`: Only 174 lines — shallow for a 691-line source file. Missing tests for error handling within command dispatch, permission failures at the app-command level, and deferred responses.
- `test_events.py`: Good coverage of Discord event handlers.
- `test_utils.py`: Good.

#### test_message_processing/ (4 files, ~1,000 lines)
**Grade: A-**

- `test_cleaner.py`: Excellent. Tests Discord mention normalization, custom emoji handling, WhatsApp-specific formatting conversion, empty/null content. Evidence-based assertions checking output strings.
- `test_filter.py`, `test_extractor.py`, `test_validator.py`: All good with clear AAA patterns.
- **Gap**: `fetcher.py`, `processor.py`, and `whatsapp_processor.py` have no tests at all.

#### test_data/ (6 files, ~2,600 lines including conftest)
**Grade: B+**

- `conftest.py`: Well-structured. Defines in-memory SQLite with full schema. Provides rich fixture factories for `SummaryResult`, `GuildConfig`, `ScheduledTask`, `TaskResult` with realistic data.
- `test_repositories.py`: Comprehensive repository CRUD testing using in-memory DB. Tests pagination, search, update, and edge cases.
- `test_stored_summary_repository.py`: Good.
- `test_sqlite.py`: Good connection-level tests.
- `test_migrations.py`: Good schema validation. However, `test_migration_execution` is a **placeholder** (`pass` only) — actual Alembic migration execution is not tested.
- `test_models.py`: Thorough model validation.
- **Gap**: Individual SQLite repository files (`config_repository.py`, `error_repository.py`, `feed_repository.py`, `filters.py`, `ingest_repository.py`, `summary_job_repository.py`, `webhook_repository.py`) have no direct tests.

#### test_command_handlers/ (5 files, ~2,400 lines)
**Grade: B+**

- `test_summarize.py` (515 lines): Good. Tests slash command flow, permission checks, time range parsing, error responses.
- `test_schedule.py`, `test_config.py`: Good.
- `test_base.py`, `test_utils.py`: Good.
- **Gap**: `prompt_config.py` command handler has no test.

#### test_dashboard/ (4 files, ~1,350 lines)
**Grade: B**

- `test_auth.py` (392 lines): Good. Tests OAuth URL generation, JWT creation/validation, session management.
- `test_middleware.py`: Good.
- `test_models.py`, `test_scope_resolver.py`: Good.
- **Critical Gap**: 10 dashboard route files (`summaries.py` at 2,732 lines, `archive.py` at 2,069 lines, `guilds.py`, `schedules.py`, `feeds.py`, `webhooks.py`, `prompts.py`, `push_templates.py`, `health.py`, `events.py`) have zero tests.

#### test_webhook_service/ (5 files, ~2,300 lines)
**Grade: B+**

- `test_endpoints.py`: Good FastAPI TestClient usage. Tests success, validation errors, auth failures.
- `test_auth.py`, `test_formatters.py`, `test_validators.py`: Good.
- `test_server.py`: Good, but contains `asyncio.sleep(100)` inside an infinite-loop mock — this is fine but unusual.
- **Gap**: `logging_middleware.py` has no test.

#### test_config/ (1 file, 459 lines)
**Grade: B**

- Tests `SummaryOptions`, `BotConfig`, `GuildConfig`, `ConfigManager`.
- Contains `assert True` on line 181 — likely a placeholder condition that was never completed.
- `config/environment.py` and `config/validation.py` have no tests.

#### test_archive.py and test_archive/
**Grade: B-**

- `test_archive.py` tests `ArchiveSource`, `SummaryWriter`, `CostTracker`, `LockManager` models.
- `test_archive/test_whatsapp_importer.py` tests fingerprinting and deduplication.
- **Critical Gaps**: `generator.py` (872 lines), `scanner.py`, `writer.py`, `retention.py`, all `sync/` files, and both `api_keys/` files have no tests.

#### test_logging/ (4 files, ~820 lines)
**Grade: B+**

- Good tests for `CommandLogger`, `LogSanitizer`, and `LoggingModels`.
- `test_integration.py`: Tests log flush behavior.
- **Gaps**: `analytics.py`, `cleanup.py`, `decorators.py`, `error_tracker.py`, `query.py`, `repository.py` have no direct tests.

#### Security Tests (2 files, ~1,500 lines)
**Grade: B**

- Covers permission escalation prevention, unauthorized channel/guild access, input injection (SQL injection patterns, XSS), API key validation, and rate limiting.
- Contains `asyncio.sleep(45)` in a timeout validation test — this is a severe performance risk for CI.
- Uses real `BotConfig`/`GuildConfig` objects, which is good. However, it imports `AuthenticationMiddleware` with a try/except, falling back to a mock — meaning the authentication middleware itself is not tested.

#### Performance Tests (2 files, ~1,200 lines)
**Grade: B-**

- `test_load_testing.py`: Tests summarization engine under 10K messages, webhook concurrent load, memory usage.
- `test_performance_optimization.py`: Tests optimizer performance.
- Assertions use relative performance bounds (e.g., `< 0.5s`, `< 100 MB`) which are environment-dependent and may fail on resource-constrained CI.

---

## Test Pyramid Analysis

```
                    [E2E: 14]
                 [Security: 47]
              [Performance: 23]
           [Logging: 46]
        [Integration: 42]
     [Unit: 1,261]
```

**Current distribution:**
- Unit: 87.4%
- Integration: 2.9%
- E2E: 1.0%
- Security: 3.3%
- Performance: 1.6%
- Logging: ~3.2%

**Assessment:** The pyramid is inverted in a healthy sense (unit tests dominate), but the integration layer is disproportionately thin given the complexity of the system. With 141 source files and 10+ database repositories, 42 integration test functions are insufficient. The E2E layer at 14 functions is very thin for a system with Discord bot + webhook API + dashboard API + scheduler + archive subsystems.

**Recommended target distribution:**
- Unit: 70%
- Integration: 20%
- E2E: 7%
- Specialist (security, performance): 3%

---

## Mock Quality Review

**Grade: A-**

The mocking strategy is well-executed across the project:

1. **spec-constrained mocks**: Fixtures consistently use `AsyncMock(spec=ClaudeClient)`, `MagicMock(spec=discord.Message)` etc. This prevents test-passes-against-wrong-interface bugs.

2. **Builder pattern**: `ClaudeResponseBuilder` and `DiscordMessageBuilder` in `tests/utils/mocking.py` enable fluent construction of test objects with realistic defaults. This is a professional pattern well-executed.

3. **Factory functions**: `create_mock_user()`, `create_mock_guild()`, `create_mock_channel()`, `create_conversation_scenario()` in `tests/fixtures/discord_fixtures.py` reduce boilerplate and ensure consistency.

4. **patch.object**: Used correctly to patch internal methods (e.g., `patch.object(claude_client._client.messages, 'create')`) rather than blanket module patches where possible.

**Issues identified:**

- In `test_database_integration.py`, a manual `try/except` swallows an expected error without asserting what the state is post-rollback (line 122). The comment says "validates that the transaction pattern exists" — this is weak.
- Some tests use `MagicMock()` without `spec=` for peripheral objects (e.g., usage stats mock in engine tests uses `MagicMock()` for the usage object returned by Claude). This allows the test to pass even if the real return type changes.
- `conftest.py` at root creates a `mock_cache` fixture referencing `src.cache.base.CacheInterface` — this class may not exist in the current codebase (no `src/cache/` directory was found in source listing), making this fixture potentially broken.

---

## Fixture Quality Review

**Grade: A-**

### Root conftest.py (653 lines)
Well-structured with:
- Proper scoped event loop (`scope="session"`) — note: this is deprecated in newer pytest-asyncio versions and should migrate to `pytest.ini` settings.
- Rich mock factories: `mock_config`, `mock_bot`, `mock_discord_guild`, `mock_discord_channel`, `mock_discord_user`, `mock_discord_message`, `sample_messages`
- Domain object factories: `summary_result_factory`, `processed_message_factory`
- Error simulation fixtures: `claude_api_error`, `discord_permission_error`, `insufficient_content_error`
- Utilities: `performance_monitor`, `freeze_time`, `env_vars`, `mock_file_system`
- Infrastructure mocks: `mock_redis_client`, `mock_http_client`

**Issue:** The `test_db_engine` and `test_db_session` fixtures use `from src.models.base import Base` — if this import fails (e.g., the project uses a different ORM base), these fixtures silently break. No evidence of `src/models/base.py` in the listed source files.

### test_data/conftest.py (364 lines)
Excellent. Defines inline SQLite schema as Python strings rather than relying on external migration files. Provides specific repository fixtures with realistic test data including complex nested objects (`ActionItem`, `TechnicalTerm`, `Participant`). The `sample_summary_result` fixture is comprehensive.

**Issue:** Schema defined twice (once in `conftest.py` and once inline in `test_database_integration.py` via file reading the actual migration SQL). These could diverge.

### tests/utils/mocking.py (456 lines)
Good utility library. `AsyncIteratorMock`, `AsyncContextManagerMock`, `FrozenTime`, `AsyncCallRecorder` are well-implemented. `FakeDataGenerator` provides realistic names and content.

**Issue:** `create_coro_mock` creates a coroutine and immediately calls it, so `mock.return_value` holds an already-exhausted coroutine. This is only correct if called once per mock creation. Better to use `AsyncMock` directly.

---

## Flaky Test Risk Assessment

**Risk Level: Medium-High**

### High-Risk Flaky Patterns

| Test | Location | Risk | Reason |
|---|---|---|---|
| `test_task_execution_trigger` | `test_scheduler.py:234` | **High** | `asyncio.sleep(2)` then asserts mock was called. APScheduler timing is not deterministic. |
| `test_concurrent_task_execution` | `test_scheduler.py:354` | **High** | `asyncio.sleep(3)` for concurrent task execution assertion. |
| `test_cache_ttl_expiry` | `test_summarization/test_cache.py:85` | Medium | `asyncio.sleep(1.1)` for TTL — passes on fast hardware, may fail under CI load. |
| `test_ttl_expiry` | `test_permissions/test_cache.py` | Medium | Multiple `asyncio.sleep(0.01)` calls for TTL checks. |
| `test_start_bot` | `test_discord_bot/test_bot.py:86` | Low-Medium | `asyncio.sleep(0.1)` to let async task setup complete — fragile. |
| Security timeout test | `test_security_validation.py:682` | **Critical** | `asyncio.sleep(45)` — will cause test suite timeout on CI. |
| `test_memory_usage` | `test_e2e/test_full_system.py` | Medium | Uses `psutil` memory measurements — environment-dependent. |
| Archive lock test | `test_archive.py:269` | Medium | `asyncio.sleep(1.5)` for lock expiry. |

### Medium-Risk Flaky Patterns

- Performance tests with hard timing bounds (`assert duration < 0.5`) will fail on loaded CI environments.
- The `event_loop` session-scoped fixture (conftest.py) combined with `asyncio` test isolation issues — this pattern is deprecated and may cause problems with pytest-asyncio 0.21+.

---

## Missing Test Types

### Property-Based Testing
**Status: Absent**

There is exactly 1 use of `pytest.mark.parametrize` across 67 test files. This is a critical gap. Property-based testing (e.g., via `hypothesis`) would be highly valuable for:
- Message content cleaning (arbitrary Unicode, control characters, zero-width chars)
- Cost estimation with boundary token values
- Schedule cron expression parsing
- Permission cache key generation with unusual user/guild IDs

### Mutation Testing
**Status: Absent**

No mutation testing (e.g., `mutmut`) is configured. Given the rich unit test suite, mutation testing would reveal tests that pass even when production logic is inverted (e.g., `>=` vs `>` in message threshold checks).

### Contract Testing
**Status: Absent**

The `ClaudeClient` wraps the Anthropic SDK, and the dashboard routes consume the Discord OAuth API. Neither has contract tests to detect API drift. A pact-style contract test would prevent regressions when the Anthropic SDK upgrades.

### Snapshot Testing
**Status: Absent**

The `PromptBuilder` and response formatters generate large multi-line strings. There are no snapshot tests to detect unintended prompt template regressions. Any change to prompt templates will silently pass unless the exact output is being tested by hand.

### Frontend Unit Tests
**Status: Near-Absent**

The vitest configuration (`vitest.config.ts`) includes `src/**/*.{test,spec}.{ts,tsx}`, but only one file exists: `src/test/example.test.ts` which contains a single trivial `expect(true).toBe(true)` assertion.

The `tests/unit-metadata.spec.ts` file contains meaningful type guard checks but is inside the Playwright test directory, not the Vitest directory — it may not be picked up by the correct runner. There are no component tests for:
- `SummaryCalendar.tsx`
- `BulkActionBar.tsx`
- `ScheduleForm.tsx`
- `FeedForm.tsx`
- `ProtectedRoute.tsx`
- `ScopeSelector.tsx`
- `api/client.ts`

The Playwright test `tests/regeneration.spec.ts` tests frontend behavior via browser automation but requires a running backend. The web server configuration is commented out in `playwright.config.ts`, meaning the E2E tests do not have a configured backend to run against.

### Integration Tests for Repository Layer
**Status: Thin**

Only `SQLiteSummaryRepository` and `SQLiteTaskRepository` have integration tests. The following repositories are either completely untested or only tested via unit-level mocking:
- `SQLiteConfigRepository`
- `SQLiteStoredSummaryRepository` (has unit test but not integration)
- `SQLiteFeedRepository`
- `SQLiteWebhookRepository`
- `SQLiteIngestRepository`
- `SQLiteSummaryJobRepository`
- `PushTemplateRepository`

---

## Test Maintainability Score

**Score: 6.5/10**

### Positive Factors
- Clear file organization mirroring `src/` structure
- Consistent naming: `test_<module>.py` pattern followed in most places
- Good use of fixtures to reduce duplication
- Builder utilities in `tests/utils/mocking.py` reduce copy-paste
- `@pytest.mark.asyncio` used consistently for async tests
- Local conftest in `tests/unit/test_data/` properly scopes domain-specific fixtures

### Negative Factors

1. **Session-scoped event loop deprecation**: The root `conftest.py` defines `event_loop` as a `session`-scoped fixture. This pattern was deprecated in pytest-asyncio 0.18 and removed in 0.21. Tests may already fail with newer pytest-asyncio depending on mode configuration.

2. **`pytest_asyncio.plugin.pytest_asyncio_mode = "auto"` on line 520 of conftest.py**: Setting a plugin attribute directly is fragile and non-standard. Should use `pytest.ini` or `pyproject.toml` with `asyncio_mode = "auto"`.

3. **Sparse use of parametrize**: Only 1 parametrize call across 1,442 tests. Dozens of similar tests (e.g., testing the same logic with different models, time formats, or input types) are written as separate test functions. This inflates test count without adding proportional value and makes refactoring harder.

4. **Test isolation gaps in integration tests**: `test_database_integration.py` shares `test_db_connection` across multiple tests within a class. If one test leaves the DB in a dirty state (e.g., partial insert), subsequent tests may be affected.

5. **Duplicate fixture definitions**: `mock_config` is defined both in root `conftest.py` and in `tests/unit/test_discord_bot/test_bot.py`. This creates shadowing — the bot test's local fixture may not match what other tests using the root fixture expect.

6. **Root-level test files**: `tests/test_data_example.py` and `tests/test_regeneration_e2e.py` are at the root of the tests directory without clear categorization. `test_data_example.py` appears to be a development/exploration file rather than a production test.

---

## Recommendations (Prioritized)

### P0 - Critical (Address Immediately)

1. **Remove or fix the `asyncio.sleep(45)` in `test_security_validation.py:682`**. This will time out the CI pipeline. Replace with a proper mock or a timeout fixture.

2. **Fix the deprecated session-scoped `event_loop` fixture** in root `conftest.py`. Migrate to `asyncio_mode = "auto"` in `pytest.ini`/`pyproject.toml` and remove the manual fixture.

3. **Add tests for `dashboard/routes/summaries.py`** (2,732 lines, zero tests). This is the largest source file and the primary API surface for the dashboard. Use `httpx.AsyncClient` with `ASGITransport` for FastAPI endpoint testing.

4. **Add tests for the delivery backends**: `scheduling/delivery/discord.py`, `scheduling/delivery/email.py`, `scheduling/delivery/webhook.py`. These are critical paths for the scheduler's primary function and are completely untested.

### P1 - High Priority (Address This Sprint)

5. **Add tests for `message_processing/fetcher.py` and `message_processing/processor.py`**. The fetcher is in the critical path for all summarizations — it fetches Discord messages. The processor coordinates cleaning, filtering, and extraction. Neither has any tests.

6. **Add tests for `services/summary_push.py`** (905 lines). This module coordinates all push delivery, making it high-risk for regressions.

7. **Add tests for `archive/generator.py`** (872 lines). Core archive generation with no tests.

8. **Add tests for `dashboard/routes/archive.py`** (2,069 lines). Second largest source file, no tests.

9. **Replace timing-based scheduler tests** (`test_task_execution_trigger`, `test_concurrent_task_execution`) with deterministic execution: call `scheduler._execute_scheduled_task(task_id)` directly rather than sleeping and hoping APScheduler fires.

10. **Add integration tests for remaining SQLite repositories**: `SQLiteConfigRepository`, `SQLiteFeedRepository`, `SQLiteWebhookRepository`, `SQLiteIngestRepository`, `SQLiteSummaryJobRepository`, `PushTemplateRepository`.

### P2 - Medium Priority (Address Next Sprint)

11. **Add property-based tests** using `hypothesis` for `MessageCleaner._clean_content`, `ClaudeClient.estimate_cost`, and `PermissionCache` key generation. Even 3-5 property tests on the most edge-case-prone functions would provide disproportionate value.

12. **Add frontend component unit tests** using Vitest and React Testing Library. Minimum viable set: `ProtectedRoute.tsx`, `api/client.ts`, `ScheduleForm.tsx`, `BulkActionBar.tsx`. Move `tests/unit-metadata.spec.ts` into the `src/test/` directory to run under Vitest.

13. **Add `pytest.mark.parametrize`** to the Claude cost estimation tests and model-specific tests in `test_claude_client.py`. Currently, sonnet, opus, and haiku are three separate test functions with identical structure — collapse into one parametrized test.

14. **Add tests for exception classes** in `src/exceptions/`. Exception classes should verify `error_code`, `message`, `http_status` attributes and serialization behavior.

15. **Add tests for `prompts/resolver.py`**. The prompt resolution chain (resolver → fallback_chain → default_provider → cache) is complex and untested.

16. **Add contract-style tests for `ClaudeClient`** that validate the Anthropic SDK response schema to detect API drift.

### P3 - Low Priority (Backlog)

17. **Fix `create_coro_mock` in `tests/utils/mocking.py`** to not pre-exhaust the coroutine. Replace with `AsyncMock(return_value=return_value)`.

18. **Investigate the broken `mock_cache` fixture** in root conftest.py that references `src.cache.base.CacheInterface` — verify this import path is valid or remove the fixture if unused.

19. **Investigate schema drift risk** between inline schema in `test_data/conftest.py` and `001_initial_schema.sql`. Consider using a single source of truth.

20. **Add snapshot tests** for prompt templates in `test_prompts/`. If any prompt template changes accidentally, no test will catch the regression today.

21. **Configure Playwright properly** for frontend E2E tests by uncommenting the `webServer` in `playwright.config.ts` and adding a CI-compatible startup command.

22. **Consider mutation testing** (`mutmut` or `cosmic-ray`) on the `summarization/` and `permissions/` modules to evaluate test effectiveness, given the density of business logic.

---

## Appendix: Test File to Source Module Mapping

### Modules Tested via Higher-Level Tests Only

| Source Module | Exercised Via |
|---|---|
| `message_processing/fetcher.py` | Integration tests (mocked); no unit tests |
| `data/sqlite/connection.py` | `test_data/conftest.py` uses it, not directly tested |
| `prompts/cache.py` | Some engine tests indirectly; no direct test |
| `webhook_service/logging_middleware.py` | `test_webhook_service/test_server.py` partially |
| `dashboard/routes/archive.py` | Integration `test_discord_integration` partially |
| `config/environment.py` | conftest.py sets env vars; no direct test |

### Frontend Coverage Summary

| Component Group | Unit Tests | E2E Tests | Gap |
|---|---|---|---|
| UI components (40+ files) | 0 | 0 | Full gap |
| API client (`api/client.ts`) | 0 | Partial (Playwright) | Significant |
| Page components | 0 | Partial (Playwright) | Significant |
| React hooks / state | 0 | 0 | Full gap |
| Auth/routing | 0 | 0 | Full gap |

---

*Report generated by V3 QE Coverage Specialist — Agentic QE v3 (ADR-003)*
*Analysis based on static source inspection and test file review. Dynamic coverage numbers require instrumented test execution.*
