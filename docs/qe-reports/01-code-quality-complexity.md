# Code Quality & Complexity Analysis Report

**Project:** summarybot-ng (Discord Summarization Bot)
**Analyzed by:** QE Code Complexity Analyzer v3
**Date:** 2026-03-11
**Scope:** All source files in `src/` (~40,310 LOC across 140+ Python files)

---

## Executive Summary

The summarybot-ng codebase is a well-structured Discord summarization bot with clean separation of concerns across 17+ modules. However, the analysis reveals **several critical complexity hotspots** that threaten maintainability and testability:

1. **`src/data/sqlite.py` (2,525 LOC)** is a God File containing 10 repository classes -- the single most urgent refactoring target.
2. **`src/command_handlers/summarize.py` (1,116 LOC)** has deeply nested Discord interaction handlers with cyclomatic complexity exceeding 25 in the main entry method.
3. **`src/scheduling/executor.py` (1,132 LOC)** mixes task execution, delivery logic, storage, and error tracking into one oversized class.
4. **Systematic code duplication** in the push service (`summary_push.py`) where `_push_to_channel` and `_push_result_to_channel` are near-identical 90-line methods.
5. **`find_by_guild` method (183 lines, 28+ parameters)** in `SQLiteStoredSummaryRepository` represents the worst Long Parameter List smell in the codebase.

**Overall Quality Score: 5.5 / 10**

The architectural decisions (ADR system, repository pattern, clean exception hierarchy) are solid. But the implementation has accrued significant complexity debt through oversized files, duplicated patterns, and methods that try to do too much. The project would benefit significantly from targeted refactoring of the top 5 hotspots.

---

## 1. Complexity Hotspot Table

### 1.1 Cyclomatic Complexity (Functions with CC > 10)

| File | Function/Method | Cyclomatic | Cognitive | Lines | Severity |
|------|----------------|-----------|-----------|-------|----------|
| `src/command_handlers/summarize.py:111` | `handle_summarize_interaction` | **28** | **38** | 164 | CRITICAL |
| `src/summarization/engine.py:88` | `ResilientSummarizationEngine.generate_with_retry` | **25** | **35** | 234 | CRITICAL |
| `src/data/sqlite.py:1196` | `SQLiteStoredSummaryRepository.find_by_guild` | **24** | **30** | 183 | CRITICAL |
| `src/summarization/response_parser.py:188` | `ResponseParser._parse_json_response` | **22** | **32** | 260 | CRITICAL |
| `src/data/sqlite.py:1383` | `SQLiteStoredSummaryRepository.count_by_guild` | **20** | **25** | 116 | CRITICAL |
| `src/scheduling/executor.py:287` | `TaskExecutor._execute_combined_mode` | **18** | **24** | 166 | HIGH |
| `src/scheduling/scheduler.py:534` | `TaskScheduler._execute_scheduled_task` | **17** | **22** | 151 | HIGH |
| `src/scheduling/scheduler.py:444` | `TaskScheduler._create_trigger` | **16** | **18** | 89 | HIGH |
| `src/scheduling/executor.py:175` | `TaskExecutor._execute_individual_mode` | **15** | **20** | 112 | HIGH |
| `src/archive/generator.py:449` | `RetrospectiveGenerator._generate_period` | **14** | **18** | 158 | HIGH |
| `src/summarization/response_parser.py:503` | `ResponseParser._parse_freeform_response` | **14** | **22** | 118 | HIGH |
| `src/archive/generator.py:611` | `RetrospectiveGenerator._save_to_database` | **13** | **18** | 106 | HIGH |
| `src/services/summary_push.py:189` | `SummaryPushService._push_to_channel` | **12** | **15** | 93 | MEDIUM |
| `src/services/summary_push.py:585` | `SummaryPushService._push_result_to_channel` | **12** | **15** | 92 | MEDIUM |
| `src/services/summary_push.py:283` | `SummaryPushService._send_embed` | **11** | **14** | 41 | MEDIUM |
| `src/services/summary_push.py:398` | `SummaryPushService._send_markdown` | **11** | **16** | 74 | MEDIUM |
| `src/data/sqlite.py:623` | `SQLiteTaskRepository._row_to_task` | **11** | **12** | 58 | MEDIUM |
| `src/command_handlers/summarize.py:332` | `SummarizeCommandHandler.handle_summarize` | **11** | **14** | 70+ | MEDIUM |
| `src/summarization/engine.py:352` | `SummarizationEngine.summarize_messages` | **11** | **16** | 252 | MEDIUM |

### 1.2 File-Level Complexity

| File | LOC | Classes | Methods | Avg CC | Max CC | Rating |
|------|-----|---------|---------|--------|--------|--------|
| `src/data/sqlite.py` | 2,525 | 10 | 65+ | 6.2 | 24 | CRITICAL |
| `src/command_handlers/summarize.py` | 1,116 | 1 | 12+ | 9.8 | 28 | CRITICAL |
| `src/scheduling/executor.py` | 1,132 | 2 | 18+ | 7.4 | 18 | HIGH |
| `src/dashboard/models.py` | 1,058 | 45+ | 10+ | 2.1 | 5 | LOW |
| `src/data/base.py` | 1,059 | 12 | 50+ | 1.0 | 1 | LOW |
| `src/services/summary_push.py` | 963 | 3 | 14 | 6.8 | 12 | HIGH |
| `src/archive/generator.py` | 850 | 5 | 16 | 5.9 | 14 | MEDIUM |
| `src/summarization/engine.py` | 837 | 3 | 11 | 8.1 | 25 | CRITICAL |
| `src/summarization/response_parser.py` | 829 | 3 | 15 | 7.3 | 22 | HIGH |
| `src/scheduling/scheduler.py` | 768 | 1 | 18 | 5.2 | 17 | MEDIUM |

---

## 2. Code Smells Catalog

### 2.1 CRITICAL Severity

#### CS-01: God File -- `src/data/sqlite.py` (2,525 LOC)
- **Location:** Entire file
- **Description:** Contains 10 separate repository classes (`SQLiteSummaryRepository`, `SQLiteConfigRepository`, `SQLiteTaskRepository`, `SQLiteFeedRepository`, `SQLiteWebhookRepository`, `SQLiteErrorRepository`, `SQLiteStoredSummaryRepository`, `SQLiteIngestRepository`, `SQLiteSummaryJobRepository`, and the connection/transaction infrastructure). This single file handles ALL data access for the entire application.
- **Impact:** Impossible to work on one repository without risk of merge conflicts. Changes to connection handling affect all repositories. File is too large to hold in working memory.
- **Recommendation:** Split into one file per repository class (e.g., `sqlite_summary.py`, `sqlite_config.py`, `sqlite_task.py`, etc.) with shared infrastructure in `sqlite_connection.py`.

#### CS-02: Long Parameter List -- `SQLiteStoredSummaryRepository.find_by_guild`
- **Location:** `src/data/sqlite.py:1196` (28 parameters)
- **Description:** The `find_by_guild` method accepts 28 optional parameters across 6 ADR extensions (ADR-008, ADR-017, ADR-018, ADR-021, ADR-026). Each ADR added more parameters without refactoring.
- **Impact:** Method signature is unreadable. Adding new filters requires modifying this already-enormous method. Testing all parameter combinations is combinatorially impossible.
- **Recommendation:** Introduce a `StoredSummaryFilter` data class to encapsulate filter criteria. Method signature becomes `find_by_guild(self, guild_id, filters: StoredSummaryFilter)`.

#### CS-03: Duplicated Logic -- `count_by_guild` mirrors `find_by_guild`
- **Location:** `src/data/sqlite.py:1383` (mirrors lines 1196-1381)
- **Description:** `count_by_guild` has 23 parameters and duplicates ~120 lines of filter-building logic from `find_by_guild`. Every filter added to one must be manually replicated in the other.
- **Impact:** High risk of filters diverging between count and list operations. Maintenance burden doubles.
- **Recommendation:** Extract shared `_build_filter_conditions(filters: StoredSummaryFilter)` method that both `find_by_guild` and `count_by_guild` call.

#### CS-04: God Method -- `handle_summarize_interaction`
- **Location:** `src/command_handlers/summarize.py:111` (164 lines, CC=28)
- **Description:** Single method handles: category routing, cross-channel permission checks (guild config lookup, role verification, Discord permission checks, bot permission checks), parameter defaulting, and dispatch to 3 different handler methods. Contains 5 levels of nesting.
- **Impact:** Extremely difficult to test. Every code path requires mocking complex Discord interaction objects. High cognitive load to understand.
- **Recommendation:** Extract permission checking into separate method. Extract category routing into separate method. The main method should be a simple dispatcher of <30 lines.

### 2.2 HIGH Severity

#### CS-05: Duplicated Methods -- `_push_to_channel` / `_push_result_to_channel`
- **Location:** `src/services/summary_push.py:189` and `src/services/summary_push.py:585`
- **Description:** These two methods are structurally identical (~90 lines each). Both: get channel from client, check send permission, send custom intro, dispatch by format (embed/markdown/plain), handle Forbidden and generic exceptions. The only difference is the input type (`StoredSummary` vs `SummaryResult`).
- **Impact:** Any bug fix or enhancement must be applied twice. Already diverging slightly in error handling.
- **Recommendation:** Create a shared `_push_content_to_channel(channel, summary_result, format, ...)` method that both call after extracting the `SummaryResult`.

#### CS-06: Duplicated Push Methods -- `push_to_channels` / `push_summary_to_channels`
- **Location:** `src/services/summary_push.py:87` and `src/services/summary_push.py:491`
- **Description:** Two 90+ line methods with identical structure: load summary, build section options dict, iterate channels, track deliveries, track errors, return results. Only the loading source differs (stored_summary_repo vs summary_repo).
- **Impact:** Four push-related methods contain approximately 360 lines of nearly duplicated code.
- **Recommendation:** Create a unified push method that accepts a `SummaryResult` directly, with two thin wrappers for loading from different sources.

#### CS-07: Feature Envy -- `TaskExecutor._execute_combined_mode`
- **Location:** `src/scheduling/executor.py:287` (166 lines)
- **Description:** This method reaches deeply into Discord client internals (`get_channel`, `channel.name`), message processing (`process_channel_messages`), summarization engine, error tracking, and delivery. It envies the functionality of 5+ other modules.
- **Impact:** Tightly couples scheduling to Discord, summarization, and storage. Cannot test without mocking 5+ external dependencies.
- **Recommendation:** Introduce a `SummarizationOrchestrator` service that coordinates message fetching, summarization, and storage. The executor should call this orchestrator, not directly invoke all subsystems.

#### CS-08: Long Method -- `generate_with_retry`
- **Location:** `src/summarization/engine.py:88` (234 lines, CC=25)
- **Description:** The retry loop contains: option construction, API calls, response parsing, quality detection, retry strategy determination, model escalation, token increase, prompt hints, and 5 different exception handlers. All in a single while loop.
- **Impact:** Very difficult to understand the retry flow. Adding new error types requires modifying this already-complex method.
- **Recommendation:** Extract each exception handler into a named method. Extract the quality-check-and-retry-decision block into its own method. The main loop should be ~50 lines.

#### CS-09: Excessive Constructor Parameters -- `RetrospectiveGenerator.__init__`
- **Location:** `src/archive/generator.py:164` (9 parameters)
- **Description:** Constructor takes 9 parameters including 3 optional repositories. This indicates the class has too many responsibilities.
- **Impact:** Difficult to instantiate in tests. Complex dependency graph.
- **Recommendation:** Consider introducing a `GeneratorConfig` dataclass for options and a `GeneratorDependencies` container for services.

#### CS-10: Deep Nesting -- `_parse_freeform_response`
- **Location:** `src/summarization/response_parser.py:503` (CC=14, nesting depth 5)
- **Description:** Contains a character-by-character JSON extraction loop (lines 566-583) with 5 levels of nesting: for loop > if char check > if in_json check > if current_chunk > if chunk_text length check.
- **Impact:** Very hard to follow the logic. The character-by-character approach is fragile.
- **Recommendation:** Extract the JSON-stripping logic into a dedicated `_extract_text_outside_json(content)` helper method.

### 2.3 MEDIUM Severity

#### CS-11: Shotgun Surgery -- ADR Parameter Accumulation
- **Location:** `src/data/sqlite.py:1196-1500` (find_by_guild + count_by_guild), `src/dashboard/routes/summaries.py`
- **Description:** Each new ADR (ADR-008, 017, 018, 021, 026) adds 2-6 parameters to `find_by_guild`, `count_by_guild`, AND the dashboard route handlers. Adding a single filter requires changes in 3+ locations.
- **Impact:** High cost of adding new features. Risk of inconsistency.
- **Recommendation:** Filter criteria objects (as recommended in CS-02) would centralize this.

#### CS-12: Primitive Obsession -- Channel IDs as strings everywhere
- **Location:** Throughout codebase (all modules)
- **Description:** Discord channel IDs, guild IDs, and user IDs are passed as bare `str` types. Methods like `_push_to_channel` accept `channel_id: str` then immediately do `int(channel_id)`.
- **Impact:** No type safety distinguishing channel IDs from guild IDs from arbitrary strings. Runtime `int()` conversions scattered everywhere.
- **Recommendation:** Introduce thin wrapper types: `ChannelId`, `GuildId`, `UserId` (even just `NewType` aliases) to prevent misuse.

#### CS-13: Dead/Placeholder Code -- `execute_cleanup_task`
- **Location:** `src/scheduling/executor.py:456`
- **Description:** Contains `TODO: Implement actual cleanup logic with database` comment and sets `items_deleted = 0` twice. The method has been a placeholder since initial development.
- **Impact:** Dead code adds confusion. Users may schedule cleanup tasks that do nothing.
- **Recommendation:** Implement or remove. If not needed, raise `NotImplementedError`.

#### CS-14: Inconsistent Error Handling Pattern
- **Location:** `src/scheduling/executor.py:221`, `src/scheduling/executor.py:339`
- **Description:** Bare `except:` clauses (with `pass`) at lines 221 and 339 silently swallow all exceptions when getting channel names. While pragmatic, this masks potential issues.
- **Impact:** Debugging becomes difficult when channel name resolution fails silently.
- **Recommendation:** Catch specific `discord.NotFound` and `discord.Forbidden` exceptions, log at debug level.

#### CS-15: Data Clumps -- Section Options
- **Location:** `src/services/summary_push.py:87-99`, `src/services/summary_push.py:491-503`
- **Description:** The four boolean parameters (`include_key_points`, `include_action_items`, `include_participants`, `include_technical_terms`) always travel together through 6+ methods.
- **Impact:** Adding a new section option requires modifying every method in the chain.
- **Recommendation:** Create a `SectionOptions` dataclass.

#### CS-16: Method Count in Single Class -- `SummaryPushService`
- **Location:** `src/services/summary_push.py:66` (964 lines, 14 methods)
- **Description:** The class handles three different push mechanisms: direct push, history push, and template-based push. Each has its own send/track/error pattern.
- **Impact:** Class violates Single Responsibility Principle. Difficult to understand which push method to use.
- **Recommendation:** Split into `DirectPushService`, `TemplatePushService`, and a shared `PushDeliveryTracker`.

### 2.4 LOW Severity

#### CS-17: Magic Numbers
- **Location:** `src/summarization/response_parser.py:692-694` (limits: 2000, 10, 20, 15)
- **Description:** Content truncation limits are hardcoded without named constants.
- **Recommendation:** Move to `config/constants.py`.

#### CS-18: Unused Import Patterns
- **Location:** `src/scheduling/executor.py:771-783` (late imports)
- **Description:** Multiple inline `from ..` imports inside methods, suggesting circular dependency workarounds.
- **Recommendation:** Refactor module boundaries to eliminate circular imports.

#### CS-19: String-Based Dispatch -- `_create_trigger`
- **Location:** `src/scheduling/scheduler.py:444`
- **Description:** Long if/elif chain matching `ScheduleType` enum values. Could use a dispatch table.
- **Recommendation:** Create `TRIGGER_FACTORIES: Dict[ScheduleType, Callable]` mapping.

---

## 3. Module Coupling Analysis

### 3.1 Dependency Heat Map

| Module (depends on ->) | models | data | config | exceptions | logging | services | summarization | discord_bot | scheduling | archive | dashboard |
|------------------------|--------|------|--------|------------|---------|----------|---------------|-------------|------------|---------|-----------|
| **data** | **HIGH** | - | MED | LOW | - | - | - | - | - | - | - |
| **scheduling** | **HIGH** | MED | MED | MED | MED | MED | **HIGH** | **HIGH** | - | - | LOW |
| **services** | **HIGH** | MED | - | MED | MED | - | - | - | - | - | - |
| **command_handlers** | MED | - | MED | MED | - | - | **HIGH** | - | MED | - | - |
| **summarization** | MED | - | LOW | MED | LOW | - | - | - | - | - | - |
| **archive** | MED | MED | - | LOW | LOW | - | MED | - | - | - | - |
| **dashboard** | MED | MED | - | LOW | LOW | MED | - | - | MED | - | - |

### 3.2 Coupling Concerns

**Most Coupled Module: `scheduling/executor.py`**
- Imports from 8 different modules: `models.task`, `models.summary`, `models.stored_summary`, `models.error_log`, `models.push_template`, `exceptions`, `logging`, `dashboard.models`
- Additionally has 6 late imports from: `services.push_message_builder`, `data.push_template_repository`, `services.email_delivery`, `data.repositories`, `models.stored_summary`
- **Afferent coupling (Ca):** 2 (scheduler, tasks use it)
- **Efferent coupling (Ce):** 12+ (it uses 12+ other modules)
- **Instability:** 0.86 (highly unstable -- changes in any dependency break this)

**Most Depended-Upon Module: `models/`**
- 11 model files imported by virtually every other module
- Well-designed as mostly data classes with minimal logic
- **Afferent coupling:** Very high (good -- stable abstractions)
- **Instability:** Low (good -- appropriately stable)

**Circular Dependency Workarounds:**
- `scheduling/executor.py` uses 6 late imports (`from ..X import Y` inside methods) to avoid circular imports
- `archive/generator.py` uses `TYPE_CHECKING` guard for `StoredSummaryRepository`
- These indicate architectural boundaries that need cleaner separation

### 3.3 Cohesion Assessment

| Class | Responsibility Count | Cohesion | Assessment |
|-------|---------------------|----------|------------|
| `SQLiteStoredSummaryRepository` | 4 (CRUD, search, FTS, navigation) | MEDIUM | Acceptable -- repository pattern |
| `TaskExecutor` | 5 (execute, resolve, deliver, store, track errors) | **LOW** | Should delegate delivery/storage |
| `SummarizationEngine` | 4 (summarize, batch, estimate, health) | MEDIUM | Acceptable |
| `SummaryPushService` | 4 (direct push, history push, template push, permission check) | **LOW** | Split into focused services |
| `RetrospectiveGenerator` | 4 (create, run, persist, generate period) | MEDIUM | Acceptable |
| `TaskScheduler` | 5 (schedule, cancel, execute, persist, stats) | MEDIUM | Normal for scheduler |
| `ResponseParser` | 4 (parse JSON, parse markdown, parse freeform, enhance) | HIGH | Well-focused |
| `ConfigCommandHandler` | 2 (view, modify config) | HIGH | Well-focused |

---

## 4. Nesting Depth Analysis

Functions with nesting depth > 3 levels:

| File | Function | Max Depth | Lines | Issue |
|------|----------|-----------|-------|-------|
| `src/command_handlers/summarize.py:111` | `handle_summarize_interaction` | **5** | 164 | Permission checks nested inside try/category/if blocks |
| `src/summarization/response_parser.py:503` | `_parse_freeform_response` | **5** | 118 | Character-by-character JSON extraction loop |
| `src/summarization/response_parser.py:188` | `_parse_json_response` | **4** | 260 | Key point extraction with type checking |
| `src/scheduling/executor.py:175` | `_execute_individual_mode` | **4** | 112 | Channel iteration with try/except inside loop |
| `src/scheduling/executor.py:287` | `_execute_combined_mode` | **4** | 166 | Channel fetching loop with error handling |
| `src/scheduling/scheduler.py:534` | `_execute_scheduled_task` | **4** | 151 | Job persistence try/except inside try/finally |
| `src/archive/generator.py:449` | `_generate_period` | **4** | 158 | Lock acquisition with cost tracking |
| `src/services/summary_push.py:772` | `push_with_template` | **4** | 150 | Template push with error tracking branches |

---

## 5. Testability Assessment

| Module | Testability Score | Blockers |
|--------|------------------|----------|
| `models/` | **9/10** | Mostly dataclasses, highly testable |
| `exceptions/` | **9/10** | Simple exception hierarchy |
| `config/` | **8/10** | Mostly configuration dataclasses |
| `summarization/response_parser.py` | **7/10** | Pure parsing logic, testable with string inputs |
| `summarization/engine.py` | **5/10** | Requires mocking ClaudeClient, cache, prompt resolver |
| `data/sqlite.py` | **5/10** | Requires database setup; 2500 LOC makes unit testing painful |
| `services/summary_push.py` | **4/10** | Requires mocking Discord client, repositories, error tracker |
| `scheduling/executor.py` | **3/10** | Requires mocking 5+ dependencies; complex Discord interactions |
| `command_handlers/summarize.py` | **2/10** | Deeply coupled to Discord interaction model |
| `scheduling/scheduler.py` | **3/10** | Requires APScheduler mock + task repository + persistence |

---

## 6. Refactoring Recommendations (Prioritized by Impact)

### Priority 1: CRITICAL (Do First)

#### R-01: Split `sqlite.py` into per-repository modules
- **File:** `src/data/sqlite.py` (2,525 LOC)
- **Effort:** Medium (4-6 hours)
- **Impact:** Eliminates God File. Enables parallel work on different repositories. Reduces merge conflicts.
- **Approach:**
  1. Create `src/data/sqlite/` package
  2. Move `SQLiteConnection`, `SQLiteTransaction` to `src/data/sqlite/connection.py`
  3. Move each repository class to its own file (9 files)
  4. Create `__init__.py` that re-exports all classes for backward compatibility
- **Risk:** Low -- purely structural change, no logic changes needed.

#### R-02: Introduce `StoredSummaryFilter` dataclass
- **File:** `src/data/sqlite.py:1196` and `src/data/sqlite.py:1383`
- **Effort:** Medium (3-4 hours)
- **Impact:** Eliminates 28-parameter method. Eliminates ~120 lines of duplicated filter logic. Makes adding new filters trivial.
- **Approach:**
  1. Create `StoredSummaryFilter` in `src/models/stored_summary.py`
  2. Move all filter parameters into the dataclass
  3. Create `_build_where_clause(filter)` shared method
  4. Update `find_by_guild` and `count_by_guild` signatures
  5. Update dashboard routes to construct filter objects

#### R-03: Extract `handle_summarize_interaction` sub-methods
- **File:** `src/command_handlers/summarize.py:111`
- **Effort:** Low (2-3 hours)
- **Impact:** Reduces CC from 28 to ~8. Enables focused unit testing of permission logic.
- **Approach:**
  1. Extract `_check_cross_channel_permission(interaction, channel)` (lines 174-232)
  2. Extract `_dispatch_summarize(interaction, target_channel, messages, hours, minutes, length, perspective)` (lines 234-263)
  3. Main method becomes: try category, check permissions, dispatch.

### Priority 2: HIGH (Do Soon)

#### R-04: Eliminate push service duplication
- **File:** `src/services/summary_push.py`
- **Effort:** Medium (3-4 hours)
- **Impact:** Eliminates ~360 lines of near-duplicate code across 4 methods. Reduces maintenance burden by 50%.
- **Approach:**
  1. Create `_send_to_channel(channel, summary_result, format, options)` shared method
  2. Create `_push_loop(summary_result, channel_ids, format, options, ...)` shared iteration
  3. Thin wrappers for stored vs history vs template push

#### R-05: Extract delivery logic from `TaskExecutor`
- **File:** `src/scheduling/executor.py`
- **Effort:** Medium (4-5 hours)
- **Impact:** Reduces coupling from 12+ modules to ~5. Improves testability from 3/10 to 6/10.
- **Approach:**
  1. Create `SummaryDeliveryService` handling Discord, webhook, email, and storage delivery
  2. `TaskExecutor` calls delivery service after summarization
  3. Move lines 585-1100+ into the new service

#### R-06: Decompose `generate_with_retry`
- **File:** `src/summarization/engine.py:88`
- **Effort:** Low (2 hours)
- **Impact:** Reduces CC from 25 to ~10. Each exception type gets a named handler.
- **Approach:**
  1. Extract `_handle_quality_issue(response, parsed, tracker, ...)`
  2. Extract `_handle_rate_limit(error, tracker, ...)`
  3. Extract `_handle_network_error(error, tracker, ...)`
  4. Main loop becomes clear: try API call, check quality, handle errors.

### Priority 3: MEDIUM (Plan For)

#### R-07: Introduce `SectionOptions` dataclass
- **File:** `src/services/summary_push.py`, `src/command_handlers/summarize.py`
- **Effort:** Low (1-2 hours)
- **Impact:** Eliminates Data Clump smell. Makes section filtering extensible.

#### R-08: Clean up circular dependency workarounds
- **Files:** `src/scheduling/executor.py`, `src/archive/generator.py`
- **Effort:** Medium (3-4 hours)
- **Impact:** Removes 6 late imports. Cleaner module boundaries.
- **Approach:** Introduce interface/protocol classes or dependency injection.

#### R-09: Implement or remove cleanup task placeholder
- **File:** `src/scheduling/executor.py:456`
- **Effort:** Low (1 hour)
- **Impact:** Removes dead code confusion.

#### R-10: Dispatch table for `_create_trigger`
- **File:** `src/scheduling/scheduler.py:444`
- **Effort:** Low (1 hour)
- **Impact:** Reduces CC from 16 to ~3. More extensible.

---

## 7. Positive Findings

The analysis also revealed several areas of good practice:

1. **Clean Abstract Repository Pattern** (`src/data/base.py`, 1,059 LOC): Well-defined abstract interfaces for all repositories. Each has clear method signatures with proper docstrings. This is exemplary use of the repository pattern.

2. **Comprehensive Exception Hierarchy** (`src/exceptions/`, 6 files): Domain-specific exceptions with error codes, user-friendly messages, and context dictionaries. The `create_error_context` helper is a nice pattern.

3. **ADR-Driven Architecture**: The codebase uses Architecture Decision Records (26+ ADRs) to document design decisions. Code references specific ADRs in comments, making it easy to trace why code is structured a certain way.

4. **Well-Structured Data Models** (`src/models/`, 3,711 LOC): Models are clean dataclasses with proper serialization methods (`to_dict`, `from_dict`). Good separation of concern.

5. **Prompt Builder Modularity** (`src/summarization/prompt_builder.py`): Good separation of prompt construction from API calls and response parsing.

6. **Error Tracking System** (`src/logging/error_tracker.py`): Centralized error capture with severity and type classification.

---

## 8. Metrics Summary

| Metric | Value | Assessment |
|--------|-------|------------|
| Total LOC | 40,310 | Large but manageable |
| Files > 500 LOC | 14 | Too many oversized files |
| Files > 1000 LOC | 4 | Urgent refactoring targets |
| Functions with CC > 10 | 19 | Needs attention |
| Functions with CC > 20 | 5 | Critical -- refactor immediately |
| Max nesting depth | 5 | Over threshold (max 3 recommended) |
| Longest method | 260 lines | `_parse_json_response` |
| Largest parameter list | 28 params | `find_by_guild` |
| Duplicated method pairs | 3 | ~540 lines of duplication |
| Modules with circular deps | 3 | Needs architectural cleanup |
| Average file complexity | 4.8 | MEDIUM (acceptable) |
| Worst-case complexity | 28 | CRITICAL |

**Overall Quality Score: 5.5 / 10**

| Category | Score | Weight | Weighted |
|----------|-------|--------|----------|
| Architecture & Design | 7/10 | 25% | 1.75 |
| Code Organization | 5/10 | 20% | 1.00 |
| Complexity Management | 4/10 | 20% | 0.80 |
| Duplication | 4/10 | 15% | 0.60 |
| Testability | 5/10 | 10% | 0.50 |
| Documentation | 8/10 | 10% | 0.80 |
| **TOTAL** | | **100%** | **5.45** |

---

## Appendix A: Files Analyzed

All 140+ Python files in `src/` were considered. The following were read in full for detailed analysis:

- `src/data/sqlite.py` (2,525 LOC) -- full read
- `src/data/base.py` (1,059 LOC) -- full read
- `src/command_handlers/summarize.py` (1,116 LOC) -- full read
- `src/scheduling/executor.py` (1,132 LOC) -- full read (600 lines)
- `src/scheduling/scheduler.py` (768 LOC) -- full read
- `src/archive/generator.py` (850 LOC) -- full read
- `src/summarization/engine.py` (837 LOC) -- full read
- `src/summarization/response_parser.py` (829 LOC) -- full read
- `src/summarization/prompt_builder.py` (598 LOC) -- partial read
- `src/services/summary_push.py` (963 LOC) -- full read
- `src/dashboard/auth.py` (744 LOC) -- partial read
- `src/dashboard/models.py` (1,058 LOC) -- partial read
- `src/command_handlers/config.py` (543 LOC) -- partial read
- `src/command_handlers/schedule.py` (505 LOC) -- partial read
