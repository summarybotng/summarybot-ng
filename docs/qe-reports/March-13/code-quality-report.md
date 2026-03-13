# Code Quality Report - summarybot-ng
**Date:** 2026-03-13
**Reviewer:** V3 QE Code Reviewer (Agentic QE v3)
**Scope:** Full codebase - Python backend (src/) + TypeScript frontend (src/frontend/)
**Files Examined:** 80+ Python source files across 20 modules

---

## Executive Summary

**Overall Quality Grade: C+ (68/100)**

The summarybot-ng codebase demonstrates a well-structured, domain-driven design with genuine effort to implement architectural decision records (ADRs). Core patterns like the Strategy pattern for delivery (CS-008), retry logic (ADR-024), and repository abstraction are sound. However, the codebase carries significant technical debt across three areas: rampant code duplication in dashboard routes, dangerous anti-patterns in concurrency primitives, and a pervasive problem of critical TODO stubs in production paths.

| Quality Dimension | Score | Grade |
|---|---|---|
| Readability & Naming | 78/100 | C+ |
| Maintainability | 60/100 | D+ |
| SOLID Compliance | 65/100 | D+ |
| DRY Compliance | 55/100 | F+ |
| Error Handling | 72/100 | C |
| Architecture | 74/100 | C |
| Test Completeness | 70/100 | C |
| Technical Debt Volume | 50/100 | F |

---

## 1. Code Smells Found

### 1.1 God Class / Class Too Large

**Severity: HIGH**

Several classes exceed the 500-line project guideline and accumulate unrelated responsibilities.

| Class | File | Lines | Responsibilities |
|---|---|---|---|
| `SummarizationEngine` | `src/summarization/engine.py` | 838 | Summarization + retry orchestration + cost estimation + caching + health checks + model selection |
| `SummarizeCommandHandler` | `src/command_handlers/summarize.py` | 1118 | Single-channel + multi-channel + category + individual mode + cost estimation + message fetching + UI interaction handling |
| `TaskScheduler` | `src/scheduling/scheduler.py` | 769 | Scheduling + persistence + recovery + execution coordination + statistics |
| `TaskExecutor` | `src/scheduling/executor.py` | 762 | Single-mode + individual-mode execution + scope resolution + delivery + error tracking + failure notification |

The `SummarizeCommandHandler` is the most egregious offender. Its `handle_summarize_interaction` method alone coordinates at least six distinct concerns: permission validation, channel/category resolution, message fetching, individual vs combined mode selection, Discord interaction deferred responses, and error formatting.

### 1.2 Long Methods

**Severity: HIGH**

Several methods exceed 100 lines, indicating they need extraction.

- `SummarizationEngine.summarize_messages` (`src/summarization/engine.py`, lines 353-622): 270 lines. Mixes cache lookup, prompt resolution, prompt building, token limit checking, resilient generation, metadata assembly, and fallback tracking.
- `CommandRegistry.setup_commands` (`src/discord_bot/commands.py`, lines 30-619): 589 lines. Registers 15+ slash command handlers as inline closures with no extraction.
- `TaskScheduler._execute_scheduled_task` (`src/scheduling/scheduler.py`, lines 535-685): 151 lines. Creates job records, manages progress tracking, calls executor, updates job status, handles exceptions, and updates metadata.
- `list_guilds` dashboard route (`src/dashboard/routes/guilds.py`, lines 70-176): 106 lines. Initializes six repositories, loops over guilds, fetches counts from five separate sources, and assembles a response.
- `get_guild` dashboard route (`src/dashboard/routes/guilds.py`, lines 189-356): 167 lines. Fetches guild config, resolves channels, counts summaries from multiple time windows, counts by source type, and assembles stats.

### 1.3 Duplicated Code

**Severity: CRITICAL**

The most severe code smell in the codebase is the verbatim repetition of the config-fetch fallback pattern across dashboard routes.

**Pattern (repeated at least 6 times in `src/dashboard/routes/guilds.py` alone, and throughout `schedules.py`, `summaries.py`, `archive.py`):**

```python
guild_config = None
if config_repo:
    guild_config = await config_repo.get_guild_config(guild_id)
if not guild_config and config_manager:
    current_config = config_manager.get_current_config()
    if current_config:
        guild_config = current_config.guild_configs.get(guild_id)
```

This identical 6-line block appears at `guilds.py:100-108`, `guilds.py:201-208`, `guilds.py:385-392`, `guilds.py:459-465`, and equivalently in `schedules.py` and `archive.py`. There is no shared helper function, no base class method, no utility function. Each usage is copy-pasted.

**Unbounded query pattern (repeated 10+ times):**

```python
all_summaries = await stored_repo.find_by_guild(guild_id=guild_id, limit=10000)
```

This pattern appears in `guilds.py:118`, `guilds.py:298`, `guilds.py:318`, `archive.py:1091`, `archive.py:1856`, `archive.py:2045`, `summaries.py:1866`. Using a hardcoded limit of 10,000 as a workaround for a missing COUNT query is a performance anti-pattern and a duplication of the problem.

**Channel name resolution (repeated in executor.py):**

At `executor.py:259-266` (in `_execute_individual_mode`) and at `executor.py:376-388` (in `_execute_combined_mode`), the identical pattern of resolving a channel name with a try/except around `discord_client.get_channel` is duplicated verbatim.

### 1.4 Primitive Obsession / Data Clumps

**Severity: MEDIUM**

The `_select_llm_provider` method in `src/main.py` (lines 241-284) returns a 4-tuple `(provider_name, api_key, base_url, model)`. This is a primitive obsession - these four values naturally form a `LLMProviderConfig` dataclass. The consumer immediately unpacks this tuple and re-checks individual values, obscuring intent.

The `_create_trigger` method in `src/scheduling/scheduler.py` (lines 445-533) contains a 90-line if-elif chain for 8 schedule types, extracting `hour, minute` from a time string in four separate branches:

```python
if task.schedule_time:
    hour, minute = map(int, task.schedule_time.split(':'))
else:
    hour, minute = 0, 0
```

This identical extract-or-default block appears four times (for DAILY, WEEKLY, HALF_WEEKLY, MONTHLY).

### 1.5 Feature Envy

**Severity: MEDIUM**

`SQLiteConfigRepository._row_to_guild_config` (lines 66-96 in `src/data/sqlite/config_repository.py`) reaches deeply into `SummaryOptions` internals to perform field migration and filtering:

```python
from dataclasses import fields as dataclass_fields
valid_fields = {f.name for f in dataclass_fields(SummaryOptions)}
options_data = {k: v for k, v in options_data.items() if k in valid_fields}
```

This is field migration logic that belongs in `SummaryOptions.from_dict()` or a migration-aware factory, not in the repository layer.

### 1.6 Lazy Class / Speculative Generality

**Severity: MEDIUM**

`src/scheduling/persistence.py` contains a `DatabaseTaskPersistence` class (lines 389-401) that exists only as a stub:

```python
class DatabaseTaskPersistence:
    def __init__(self, database_url: str):
        # TODO: Implement database persistence
        raise NotImplementedError("Database persistence not yet implemented")
```

This is dead code in production - it raises immediately on construction. The entire class should not exist until it is implemented.

Multiple webhook endpoints in `src/webhook_service/endpoints.py` (lines 301-327, 395-397, 454, 507) contain TODO stubs that raise HTTP 501 Not Implemented, indicating the webhook API surface is partially shipped:

```python
# TODO: Check user permissions based on guild_id/channel_id
# TODO: Fetch messages from Discord based on request parameters
raise HTTPException(status_code=501, detail="Summary creation not yet implemented...")
```

### 1.7 Inappropriate Intimacy

**Severity: MEDIUM**

`src/scheduling/executor.py:_execute_individual_mode` (lines 234-239) directly mutates fields on `task.scheduled_task`, which is a child object:

```python
single_task_data = task.scheduled_task
single_task_data.channel_id = channel_id
single_task_data.channel_ids = [channel_id]
```

This bypasses encapsulation of `ScheduledTask` and creates aliased mutation. The loop mutates a shared object, meaning each iteration overwrites the previous channel context on the parent task.

---

## 2. SOLID Violations

### 2.1 Single Responsibility Principle (SRP)

**Severity: HIGH**

**`SummaryBotApp` (src/main.py)** is the primary SRP offender. It acts as:
- Service locator (stores references to all components)
- Initializer for all subsystems (8 distinct `_initialize_*` methods)
- LLM provider selector (`_select_llm_provider`)
- Environment detector (`_is_production_environment`)
- Signal handler
- Application lifecycle manager

The class is 684 lines and contains initialization code that belongs in dedicated factory classes.

**`SummarizationEngine` (src/summarization/engine.py)** conflates:
- Cache management
- Prompt building coordination
- Model selection for length
- Cost estimation
- Health checking
- Resilient generation (which is already split into `ResilientSummarizationEngine`, but the main engine still re-instantiates it on every call at line 494)

### 2.2 Open/Closed Principle (OCP)

**Severity: MEDIUM**

`TaskScheduler._create_trigger` (lines 445-533) uses an if-elif chain over `ScheduleType` enum values. Adding a new schedule type requires modifying this method. The trigger creation logic should be dispatched through a registry or factory keyed by `ScheduleType`, making it open for extension without modification.

`PermissionManager.check_command_permission` (lines 124-193) contains a hardcoded `command_action_map` dict and special-case logic for specific commands. Adding a new command requires modifying this method.

### 2.3 Liskov Substitution Principle (LSP)

**Severity: LOW**

`DatabaseTaskPersistence` inherits from `TaskPersistence` but raises `NotImplementedError` on construction. Any code holding a `TaskPersistence` reference cannot substitute this subclass, violating LSP.

### 2.4 Interface Segregation Principle (ISP)

**Severity: MEDIUM**

`RepositoryFactory` (src/data/repositories/__init__.py) exposes 10 `get_*_repository()` methods via a single class. Consumers that only need a summary repository receive an interface burdened with feed, webhook, ingest, and error repository accessors. Each accessor contains a copy-pasted if/elif backend check:

```python
if self.backend == "sqlite":
    return SQLite<X>Repository(connection)
elif self.backend == "postgresql":
    raise NotImplementedError(...)
else:
    raise ValueError(...)
```

This pattern repeats 10 times in the same class.

### 2.5 Dependency Inversion Principle (DIP)

**Severity: MEDIUM**

`SummarizationEngine.__init__` accepts `prompt_resolver=None` typed as `Any` (no type annotation) in the constructor. The engine depends directly on a concrete `PromptTemplateResolver` class from the prompts module, and the import occurs inline mid-method at line 422:

```python
from ..prompts.models import PromptContext
```

Inline imports inside `try` blocks to avoid circular dependencies indicate an architecture that has not fully resolved its dependency graph.

---

## 3. DRY Violations

### 3.1 Duplicate `SummaryLength` Enum

**Severity: HIGH**

`SummaryLength` is defined in two places:
- `src/config/settings.py:23`
- `src/models/summary.py:23`

Both enumerations define `BRIEF = "brief"`, `DETAILED = "detailed"`, `COMPREHENSIVE = "comprehensive"`. The config-layer version is used by `GuildConfig.default_summary_options` (a `SummaryOptions` from `config.settings`), while the model-layer version is used by the `SummarizationEngine`. This split means downstream code imports from different paths depending on context.

### 3.2 Duplicate `SummaryOptions` Dataclass

**Severity: HIGH**

`SummaryOptions` exists in two distinct places:
- `src/config/settings.py:39` - a config-focused dataclass without `perspective`, with `summarization_model`, `temperature`, `max_tokens`, `extract_action_items`, `extract_technical_terms`
- `src/models/summary.py:476` - a richer model-layer dataclass that adds `perspective`, `source_type`, WhatsApp-specific options, and helper methods like `get_model_for_length()`

The two classes are incompatible. The repository layer (`config_repository.py:10`) imports `SummaryOptions` from `config.settings` while the engine imports it from `models.summary`. This creates a bidirectional translation burden at the repository boundary and explains why the config repository performs field filtering (line 78-81): it must reject fields present in `models.SummaryOptions` that do not exist in `config.SummaryOptions`.

### 3.3 Duplicate `JobStatus` Enum

**Severity: MEDIUM**

`JobStatus` is defined in three separate locations:
- `src/archive/generator.py:46`
- `src/models/summary_job.py:22`
- `src/dashboard/models.py:970` (as `class JobStatus(str, Enum)`)

The `archive.generator.JobStatus` and `models.summary_job.JobStatus` carry an explicit comment in `generator.py` noting they must match: `# Note: Use PENDING (not QUEUED) to match SummaryJob model in database`. This is a self-documented DRY violation - requiring a comment to keep two definitions synchronized is a maintenance hazard.

### 3.4 Duplicate `OutputFormat` and `TaskType` Enums

**Severity: MEDIUM**

- `OutputFormat` defined in `src/webhook_service/formatters.py:14` and `src/webhook_service/validators.py:22` - within the same module directory.
- `TaskType` defined in `src/scheduling/tasks.py:15` and `src/models/task.py:57`.

### 3.5 Duplicated Legacy Field (`claude_model`)

**Severity: MEDIUM**

The field `claude_model` is a renamed legacy field (`summarization_model` is the canonical name). Despite the rename, references to `claude_model` persist across:
- `src/config/settings.py:62` - emitted for backward compat
- `src/scheduling/persistence.py:199,247`
- `src/scheduling/tasks.py:121`
- `src/config/manager.py:176`
- `src/summarization/engine.py:529` - stored in metadata
- `src/webhook_service/endpoints.py:306` - uses `claude_model=` as kwarg (line 306 passes `claude_model` to `SummaryOptions`, but `config.settings.SummaryOptions` has no such field)
- `src/dashboard/routes/summaries.py:281,1046`

This indicates an incomplete migration that has been partially addressed but not finished.

### 3.6 Guild Config Fetch Fallback Pattern (30 occurrences)

As documented in Section 1.3, the 6-line "try database, fall back to in-memory config" pattern occurs approximately 30 times across the dashboard routes (confirmed via grep). No shared helper function exists to encapsulate this pattern.

---

## 4. Architecture Assessment

### 4.1 Strengths

The overall module decomposition is principled. Bounded contexts are clearly delineated: `summarization`, `scheduling`, `message_processing`, `permissions`, `dashboard`, `webhook_service`, `archive`, `feeds`, `prompts`, and `data` each represent coherent domains.

The repository pattern (abstract base + SQLite implementation) is cleanly applied. The delivery strategy pattern (`src/scheduling/delivery/`) is well-structured. The exception hierarchy (`SummaryBotException`, `UserError`, `RecoverableError`, `CriticalError`) is explicit and serializable.

The ADR documentation trail is evidence of deliberate architectural decision-making.

### 4.2 Dashboard Routes Files Are Excessively Large

**Severity: HIGH**

| File | Lines | Finding |
|---|---|---|
| `src/dashboard/routes/summaries.py` | 2732 | Violates 500-line project limit by 5.5x |
| `src/dashboard/routes/archive.py` | 2069 | Violates 500-line project limit by 4x |
| `src/dashboard/models.py` | 1058 | Violates 500-line limit by 2x |

`summaries.py` contains 28 async handler functions. These should be decomposed into logical sub-routers or service classes.

### 4.3 Global Module State in Dashboard Routes

**Severity: MEDIUM**

`src/dashboard/routes/__init__.py` uses module-level global variables as a service locator:

```python
_discord_bot = None
_summarization_engine = None
_task_scheduler = None
_config_manager = None

def set_services(discord_bot=None, ...):
    global _discord_bot, _summarization_engine, ...
```

This pattern couples all dashboard route modules to a shared mutable global state, makes testing difficult (state persists between test runs), and violates dependency injection principles.

### 4.4 `SummaryBotApp` as God Object

**Severity: HIGH**

`src/main.py` contains a 684-line `SummaryBotApp` class that is the application-level service locator and orchestrator. It holds references to all subsystems and performs all initialization. The `initialize()` method is 43 lines and delegates to 6 private methods (`_initialize_database`, `_initialize_command_logging`, `_recover_interrupted_jobs`, `_initialize_core_components`, `_initialize_discord_bot`, `_initialize_scheduler`). While delegation is used, each method still performs direct component wiring that belongs in a dependency injection container or factory chain.

### 4.5 Debug Print Statements in Production Code

**Severity: MEDIUM**

`src/main.py` and `src/__main__.py` contain 14 `print()` calls used for startup diagnostics:

```python
print("=== Summary Bot NG module loading ===", flush=True, file=sys.stderr)
print("Standard library imports OK", flush=True, file=sys.stderr)
print("Config imports OK", flush=True, file=sys.stderr)
...
```

Additionally, `src/config/manager.py:257-266` and `src/message_processing/processor.py:125` contain bare `print()` calls inside what should be logger calls. These bypass the structured logging system.

### 4.6 Async Lock Misuse

**Severity: CRITICAL**

`src/config/manager.py:73` creates a new `asyncio.Lock()` on every call to `save_config`:

```python
async with asyncio.Lock():
    with open(temp_path, 'w') as f:
        json.dump(config_dict, f, indent=2, default=str)
```

This is a critical concurrency bug. `asyncio.Lock()` instantiated inline does not provide mutual exclusion - each `asyncio.Lock()` call creates a new, independent lock object. Concurrent callers each acquire their own lock, providing no protection against concurrent writes. The lock must be an instance attribute set once in `__init__`.

### 4.7 Inline Imports for Circular Dependency Avoidance

**Severity: MEDIUM**

Throughout the codebase, imports are deferred to inside functions or `try` blocks to avoid circular imports. Examples:
- `src/summarization/engine.py:422,444,566,567,689,737,804` - 7 inline imports in one file
- `src/main.py:189,344,345,474` - inline imports inside initialization methods
- `src/dashboard/routes/guilds.py:78,281` - inline imports inside route handlers

Circular imports indicate an unresolved dependency direction. They should be resolved through interface abstraction or module reorganization, not by deferring imports.

---

## 5. Naming and Convention Issues

### 5.1 Inconsistent Field Names for the Same Concept

`summarization_model` (canonical, in `models/summary.py`) vs. `claude_model` (legacy, used in metadata keys, serialization, and a direct kwarg call at `webhook_service/endpoints.py:306`). The API surface is incoherent.

### 5.2 Method Naming Inconsistency in Scheduler

`TaskScheduler` exposes both sync and async task retrieval with similar names:
- `get_task(task_id)` - synchronous, active tasks only
- `get_task_async(task_id)` - asynchronous, includes inactive tasks

The suffix `_async` is not a Python convention and creates confusion. The sync method should be `get_active_task` and the async one should be `get_task`.

### 5.3 `SummarizationContext.channel_ids` vs `channel_id`

Models and methods use singular `channel_id: str` and plural `channel_ids: List[str]` inconsistently, sometimes within the same method call. `_execute_combined_mode` tracks `channels_with_content` as a list of IDs and uses `task.channel_id` (singular) as the primary channel for storage, while `task.scheduled_task.channel_ids` (plural) holds all channels for processing.

### 5.4 Emoji in Log Messages

`src/main.py:374,435` uses Unicode characters in log messages:

```python
self.logger.info("✓ Prompt resolver initialized successfully")
```

These characters can cause encoding issues in log aggregation systems and are not searchable as plain text.

---

## 6. Error Handling Assessment

### 6.1 Strengths

The exception hierarchy is well-designed. `SummaryBotException` includes `error_code`, `user_message`, `context`, `retryable`, and `to_log_string()`. Exceptions serialize cleanly to dicts for structured logging.

The resilient summarization engine (`ResilientSummarizationEngine`) correctly distinguishes between `RateLimitError`, `NetworkError`, `TimeoutError`, and `ModelUnavailableError`, applying appropriate backoff and escalation strategies.

### 6.2 Swallowed Exceptions (305 bare `except Exception` clauses)

**Severity: HIGH**

The codebase has 305 occurrences of `except Exception`. A significant portion catch and log, then continue - which is appropriate for non-critical operations. However, several patterns are problematic:

In `executor.py:309`:
```python
except Exception as e:
    logger.exception(f"Failed to summarize channel {channel_id}: {e}")
    results.append({"channel_id": channel_id, "success": False, "error": str(e)})
```

This silently continues past all failure types, including potential programming errors that should surface. Structured exception types should be caught specifically.

In `discord_bot/bot.py:104`:
```python
except Exception as e:
    logger.error(f"Failed to start bot: {e}", exc_info=True)
    self._is_running = False
    raise
```

This pattern (catch, log, re-raise) correctly uses `exc_info=True` to preserve the traceback.

### 6.3 Permission System Fails Open on Error

**Severity: HIGH**

`PermissionManager.get_user_permissions` (lines 256-266) catches all exceptions and returns `PermissionLevel.NONE`. But `PermissionManager.check_channel_access` (lines 116-122) catches all exceptions and returns `False` (deny), while `check_command_permission` (lines 187-193) catches and returns `False`. The behavior is inconsistent - channel access fails closed but the raw permission object fails to NONE which may have different downstream implications.

More critically, `get_user_permissions` only checks the in-memory config's allowed_users list and never actually validates Discord roles (documented at lines 246-250 as "Note: Role-based permissions would require Discord member object"). The permission system is partially unimplemented.

### 6.4 Missing Error Propagation in Cleanup Task

`execute_cleanup_task` in `executor.py` (lines 501-554) has a placeholder implementation:

```python
# TODO: Implement actual cleanup logic with database
items_deleted = 0
# Placeholder - would actually delete items
items_deleted = 0
```

The variable is assigned twice and the actual cleanup is never performed. Cleanup tasks complete as `success=True` without doing any work.

---

## 7. Technical Debt Inventory

| ID | Location | Description | Severity | Effort |
|---|---|---|---|---|
| TD-001 | `src/config/manager.py:73` | `asyncio.Lock()` instantiated inline (not a real lock) | CRITICAL | Low |
| TD-002 | `src/webhook_service/endpoints.py:301-326` | Core webhook summarization endpoint raises HTTP 501 | HIGH | High |
| TD-003 | `src/scheduling/executor.py:520-529` | Cleanup task implementation is empty stub | HIGH | Medium |
| TD-004 | `src/config/settings.py:23` + `src/models/summary.py:23` | Duplicate `SummaryLength` enum | HIGH | Medium |
| TD-005 | `src/config/settings.py:39` + `src/models/summary.py:476` | Duplicate `SummaryOptions` class | HIGH | High |
| TD-006 | `src/archive/generator.py:46` + `src/models/summary_job.py:22` + `src/dashboard/models.py:970` | Duplicate `JobStatus` enum | MEDIUM | Low |
| TD-007 | Dashboard routes (~30 locations) | Guild config fetch fallback duplicated without helper | HIGH | Low |
| TD-008 | `src/dashboard/routes/summaries.py` (2732 lines) | Route file exceeds project limit by 5.5x | HIGH | High |
| TD-009 | `src/permissions/manager.py:246-250` | Role-based permissions not implemented | HIGH | High |
| TD-010 | `src/scheduling/persistence.py:389-401` | `DatabaseTaskPersistence` stub raises immediately | MEDIUM | Low (remove) |
| TD-011 | `src/main.py:14-51` | 8 debug `print()` statements at module load | LOW | Low |
| TD-012 | Multiple files (10+ sites) | `limit=10000` workaround instead of COUNT query | MEDIUM | Medium |
| TD-013 | `src/webhook_service/endpoints.py:306` | `claude_model=` kwarg used on class that doesn't have that field | HIGH | Low |
| TD-014 | `src/summarization/engine.py:494` | `ResilientSummarizationEngine` instantiated on every call | MEDIUM | Low |
| TD-015 | `src/discord_bot/commands.py:30-619` | 589-line method with 15 nested closures | HIGH | High |

---

## 8. Recommendations (Prioritized)

### Priority 1: Critical Fixes (Within 1 Sprint)

**P1-A: Fix the asyncio.Lock bug** (`src/config/manager.py`)

The inline `asyncio.Lock()` provides zero mutual exclusion. Add `self._file_write_lock = asyncio.Lock()` to `ConfigManager.__init__` and use `async with self._file_write_lock:` in `save_config`. This is a correctness defect, not a style issue.

**P1-B: Consolidate duplicate SummaryLength and SummaryOptions**

Remove `SummaryLength` from `src/config/settings.py` and import from `src/models/summary.py` everywhere. Similarly, the `GuildConfig.default_summary_options` type should reference `models.SummaryOptions` and the config-layer class should be removed. The repository layer migration logic at `config_repository.py:78-81` can then live in `SummaryOptions.from_dict()` where it belongs.

**P1-C: Fix the webhook SummaryOptions field access** (`src/webhook_service/endpoints.py:306`)

`SummaryOptions(claude_model=...)` on the model-layer `SummaryOptions` will silently fail (dataclass silently ignores unknown kwargs in Python) or raise `TypeError`. The field should be `summarization_model=`.

**P1-D: Extract the guild config helper function** (Dashboard routes)

Create `async def _get_guild_config(guild_id: str, config_repo, config_manager) -> Optional[GuildConfig]` in a shared location (e.g., `src/dashboard/utils/`) and replace all 30 repetitions with a single call site.

### Priority 2: High-Impact Refactoring (Within 2 Sprints)

**P2-A: Split `SummarizeCommandHandler`**

Decompose into:
- `SingleChannelSummarizeHandler` - current-channel and explicit-channel summarization
- `CategorySummarizeHandler` - category resolution and multi-channel aggregation
- A shared `MessageFetchCoordinator` for Discord API interaction

**P2-B: Decompose `summaries.py` and `archive.py` routes**

Both files exceed 2000 lines. Group logically related routes into service classes or sub-routers. `summaries.py` should be split into at minimum `summary_list_routes.py`, `summary_detail_routes.py`, and `summary_job_routes.py`.

**P2-C: Replace the dashboard global state pattern**

Replace the module-level globals in `src/dashboard/routes/__init__.py` with FastAPI's dependency injection via `Depends()`. Create a `ServiceContainer` Pydantic settings object passed via `app.state` and resolved through `Request.app.state` in dependencies.

**P2-D: Consolidate `JobStatus` enum**

Remove the enum from `src/archive/generator.py` and `src/dashboard/models.py`. Import from `src/models/summary_job.py` as the single source of truth.

**P2-E: Implement role-based permission checking**

`PermissionManager.get_user_permissions` acknowledges that Discord role checking requires the `discord.Member` object but was never implemented. The `validate_discord_member_permissions` method exists but is only called from one external entry point. The permission manager must be wired to the Discord client or accept a member object to complete the security model.

### Priority 3: Architecture Improvement (Next Quarter)

**P3-A: Resolve circular imports structurally**

The 7 inline imports in `engine.py` alone indicate circular dependencies. Introduce an `interfaces` or `protocols` package with `Protocol` classes (Python's structural subtyping) that break the cycles. This eliminates lazy imports and makes the dependency graph explicit.

**P3-B: Replace `_create_trigger` if-elif chain with registry**

```python
TRIGGER_FACTORIES: Dict[ScheduleType, Callable[[ScheduledTask], BaseTrigger]] = {
    ScheduleType.DAILY: _create_daily_trigger,
    ScheduleType.WEEKLY: _create_weekly_trigger,
    ...
}
```

**P3-C: Remove `DatabaseTaskPersistence` stub**

Delete `src/scheduling/persistence.py:389-401`. It is dead code that raises on construction. When database persistence is implemented, it should be a complete implementation, not a stub.

**P3-D: Replace `limit=10000` with COUNT queries**

Every use of `find_by_guild(guild_id=guild_id, limit=10000)` followed by `len(result)` should be replaced with a `count_by_guild(guild_id)` repository method that issues a `SELECT COUNT(*) ...` query. This eliminates loading thousands of objects to count them.

**P3-E: Remove startup debug print statements**

Replace all `print()` calls in `src/main.py` and `src/__main__.py` with `logger.debug()` calls. Configure the logging system before any module imports that might fail to capture startup diagnostics through the structured log pipeline.

---

## Appendix: Files Examined

The following files were read in full or in substantial part during this review:

**Core**
- `src/main.py`, `src/__main__.py`

**Discord Bot**
- `src/discord_bot/bot.py`, `src/discord_bot/commands.py`, `src/discord_bot/events.py`

**Command Handlers**
- `src/command_handlers/base.py`, `src/command_handlers/summarize.py` (structure examined)

**Summarization**
- `src/summarization/engine.py`, `src/summarization/claude_client.py`, `src/summarization/prompt_builder.py`

**Scheduling**
- `src/scheduling/scheduler.py`, `src/scheduling/executor.py`, `src/scheduling/persistence.py`, `src/scheduling/tasks.py`

**Configuration**
- `src/config/settings.py`, `src/config/manager.py`, `src/config/constants.py`, `src/config/environment.py`

**Data Layer**
- `src/data/sqlite/connection.py`, `src/data/sqlite/config_repository.py`, `src/data/sqlite/summary_repository.py`, `src/data/repositories/__init__.py`

**Dashboard**
- `src/dashboard/routes/__init__.py`, `src/dashboard/routes/guilds.py`, `src/dashboard/auth.py`, `src/dashboard/utils/scope_resolver.py`

**Models**
- `src/models/summary.py`, `src/models/message.py`, `src/models/task.py`, `src/models/stored_summary.py`

**Permissions**
- `src/permissions/manager.py`, `src/permissions/validators.py`, `src/permissions/cache.py`

**Services**
- `src/services/summary_push.py`, `src/webhook_service/server.py`, `src/webhook_service/endpoints.py`

**Exceptions**
- `src/exceptions/base.py`, `src/exceptions/discord_errors.py`, `src/exceptions/summarization.py`

**Archive**
- `src/archive/generator.py` (partial)

---

*Report generated by V3 QE Code Reviewer - Agentic QE v3 - 2026-03-13*
