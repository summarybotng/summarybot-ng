# Code Complexity Analysis Report
## summarybot-ng
**Date:** 2026-03-13
**Analyst:** V3 QE Code Complexity Analyzer
**Scope:** Full codebase — Python backend (`src/`) + TypeScript frontend (`src/frontend/`)

---

## Executive Summary

**Overall Complexity Grade: C+ (Moderate-High Risk)**

The summarybot-ng codebase spans approximately 37,500 lines of Python and 8,300 lines of TypeScript. It is structurally well-organized into bounded modules with clear domain responsibilities. However, the complexity is concentrated in a small number of critical functions that present significant testability, maintainability, and defect risk. Two route handler functions in the dashboard API exceed cyclomatic complexity of 55, which is firmly in the "untestable without decomposition" range. The response parser has a function approaching CC=60 with nine levels of nesting. Several of the most complex functions are also the hottest code paths in production (AI summary generation, response parsing, scheduled task execution).

**Key findings:**
- 6 functions with cyclomatic complexity (CC) > 20 (critical threshold)
- 17 functions with CC > 10 (high threshold)
- The single file `dashboard/routes/summaries.py` at 2,732 lines contains functions with CC ranging from 59 down to 1, indicating severe responsibility concentration
- Maximum measured nesting depth: 10 levels (in `executor.py`, `summarize.py`, and `claude_client.py`)
- 12 Python source files exceed 500 lines; 3 exceed 800 lines
- The frontend `Archive.tsx` at 1,806 lines embeds 8 component definitions and 14 state variables in a single file
- Test coverage exists (87 test files) but the highest-complexity functions are the hardest to reach with unit tests

---

## Complexity Hotspots Table

Functions sorted by cyclomatic complexity (CC). Cognitive complexity is estimated based on nesting depth, branching structure, and control flow interruptions.

| # | File | Class | Function | Line | LOC | CC | Est. Cognitive CC | Severity |
|---|------|-------|----------|------|-----|----|--------------------|----------|
| 1 | `dashboard/routes/summaries.py` | — | `generate_summary` | 389 | 385 | **59** | ~70 | CRITICAL |
| 2 | `summarization/response_parser.py` | `ResponseParser` | `_parse_json_response` | 189 | 260 | **58** | ~65 | CRITICAL |
| 3 | `dashboard/routes/summaries.py` | — | `regenerate_stored_summary` | 1408 | 304 | **56** | ~60 | CRITICAL |
| 4 | `dashboard/routes/summaries.py` | — | `run_generation` (nested) | 522 | 244 | **35** | ~40 | CRITICAL |
| 5 | `summarization/response_parser.py` | `ResponseParser` | `_parse_freeform_response` | 504 | 118 | **31** | ~35 | CRITICAL |
| 6 | `dashboard/routes/summaries.py` | — | `run_regeneration` (nested) | 1543 | 161 | **30** | ~35 | CRITICAL |
| 7 | `command_handlers/summarize.py` | `SummarizeCommandHandler` | `handle_category_individual_summary` | 842 | 199 | **28** | ~32 | HIGH |
| 8 | `dashboard/routes/summaries.py` | — | `get_stored_summary` | 994 | 172 | **28** | ~30 | HIGH |
| 9 | `summarization/engine.py` | `SummarizationEngine` | `summarize_messages` | 353 | 270 | **23** | ~28 | HIGH |
| 10 | `scheduling/scheduler.py` | `TaskScheduler` | `_execute_scheduled_task` | 535 | 151 | **21** | ~25 | HIGH |
| 11 | `scheduling/executor.py` | `TaskExecutor` | `_execute_combined_mode` | 331 | 169 | **20** | ~22 | HIGH |
| 12 | `command_handlers/summarize.py` | `SummarizeCommandHandler` | `handle_summarize_interaction` | 112 | 164 | **20** | ~24 | HIGH |
| 13 | `command_handlers/summarize.py` | `SummarizeCommandHandler` | `handle_category_combined_summary` | 720 | 121 | **20** | ~22 | HIGH |
| 14 | `dashboard/routes/summaries.py` | — | `get_summary` | 184 | 151 | **20** | ~22 | HIGH |
| 15 | `scheduling/scheduler.py` | `TaskScheduler` | `_create_trigger` | 445 | 89 | **19** | ~20 | HIGH |
| 16 | `dashboard/routes/summaries.py` | — | `bulk_regenerate_summaries` | 1908 | 129 | **19** | ~20 | HIGH |
| 17 | `command_handlers/summarize.py` | `SummarizeCommandHandler` | `handle_summarize` | 334 | 180 | **17** | ~20 | HIGH |
| 18 | `summarization/claude_client.py` | `ClaudeClient` | `create_summary` | 268 | 147 | **16** | ~18 | MEDIUM-HIGH |
| 19 | `summarization/engine.py` | `ResilientSummarizationEngine` | `generate_with_retry` | 89 | 234 | **15** | ~20 | MEDIUM-HIGH |
| 20 | `summarization/response_parser.py` | `ResponseParser` | `_enhance_with_message_analysis` | 623 | 60 | **15** | ~16 | MEDIUM-HIGH |
| 21 | `scheduling/executor.py` | `TaskExecutor` | `_resolve_scope_channels_runtime` | 149 | 59 | **15** | ~16 | MEDIUM-HIGH |
| 22 | `scheduling/executor.py` | `TaskExecutor` | `_execute_individual_mode` | 218 | 112 | **14** | ~16 | MEDIUM-HIGH |
| 23 | `dashboard/routes/summaries.py` | — | `list_stored_summaries` | 830 | 152 | **14** | ~16 | MEDIUM-HIGH |
| 24 | `summarization/claude_client.py` | `ClaudeClient` | `create_summary_with_fallback` | 416 | 90 | **8** | ~10 | MEDIUM |

**Cyclomatic Complexity thresholds used:** Low (1–5), Medium (6–10), High (11–20), Critical (>20)

---

## Module-Level Complexity Scores

Scores are based on total lines, function count, and average CC of functions within each module. Modules with more than one CRITICAL function are flagged.

| Module | Total LOC | Files | Functions (approx) | Avg CC (est.) | CRITICAL fns | Grade |
|--------|-----------|-------|-------------------|---------------|--------------|-------|
| `dashboard` | 11,026 | 16 | ~65 | 12 | 4 | **F** |
| `summarization` | 3,898 | 8 | ~35 | 14 | 2 | **D** |
| `command_handlers` | 3,475 | 7 | ~30 | 11 | 1 | **D** |
| `scheduling` | 2,871 | 7 | ~25 | 10 | 1 | **C** |
| `archive` | 7,632 | 14 | ~60 | 7 | 0 | **C+** |
| `data` | 4,529 | 15 | ~80 | 4 | 0 | **B** |
| `services` | 2,505 | 5 | ~25 | 6 | 0 | **B** |
| `models` | 3,718 | 13 | ~70 | 3 | 0 | **A** |
| `permissions` | 1,445 | 4 | ~20 | 6 | 0 | **B** |
| `config` | 1,025 | 5 | ~20 | 4 | 0 | **B+** |
| `message_processing` | 1,015 | 7 | ~30 | 5 | 0 | **B** |
| `discord_bot` | 1,758 | 5 | ~25 | 5 | 0 | **B** |
| `logging` | 1,876 | 8 | ~30 | 4 | 0 | **A-** |
| `prompts` | 2,549 | 9 | ~35 | 5 | 0 | **B** |
| `exceptions` | 1,090 | 6 | ~25 | 2 | 0 | **A** |
| `webhook_service` | 2,360 | 6 | ~30 | 6 | 0 | **B** |
| `feeds` | 894 | 4 | ~20 | 5 | 0 | **B** |

**Frontend:**

| Module | Total LOC | Components | State vars (est.) | Grade |
|--------|-----------|------------|-------------------|-------|
| `pages/Archive.tsx` | 1,806 | 8 embedded | ~14 | **D** |
| `pages/Summaries.tsx` | 497 | 1 | ~10 | **C** |
| `pages/Schedules.tsx` | 380 | 1 | ~8 | **C** |
| `hooks/useArchive.ts` | 510 | — | — | **C** |
| `hooks/useStoredSummaries.ts` | 341 | — | — | **C** |

---

## Deeply Nested Code Instances

Nesting depth is measured by indentation level (4 spaces per level). Depth >= 5 indicates code in a `try/except` inside a `for` loop inside an `if` inside a method, which makes reasoning and testing extremely difficult.

| File | Max Depth | Approximate Location | Description |
|------|-----------|----------------------|-------------|
| `summarization/response_parser.py` | **9** | Line 624 | `_enhance_with_message_analysis` — nested for loops over references inside try/except blocks |
| `scheduling/executor.py` | **10** | Line 721 | `_send_failure_notification` — nested exception handler inside conditional inside loop |
| `command_handlers/summarize.py` | **10** | Line 683 | `_fetch_and_process_messages` — channel ID processing inside multiple try/except/if layers |
| `summarization/claude_client.py` | **10** | Line 417 | `create_summary_with_fallback` — model iteration inside try/except inside for loop |
| `dashboard/routes/summaries.py` | **8** | Line 561 | `run_generation` (nested async) — reference building inside nested conditionals |
| `summarization/engine.py` | **7** | Line 354 | `summarize_messages` — prompt context building inside nested try/except |
| `scheduling/scheduler.py` | **6** | Line 285 | `get_scheduled_tasks` — task loading with nested exception and filter |

### Specific Instances Requiring Immediate Attention

**1. `response_parser.py::_parse_json_response` (depth 6+)**
The `_parse_json_response` function contains a loop over key points, which itself branches on `isinstance` checks, then accesses a position index with multiple conditional paths. The key points normalization section (lines 292–320) reaches 6 levels of nesting while simultaneously handling four different data shapes from the LLM response.

**2. `summarize.py::handle_category_individual_summary` (depth 5–6)**
Per-channel iteration that builds context and generates summaries contains try/except blocks inside for loops, with additional inline exception blocks for Discord API calls. This pattern is repeated in `executor.py::_execute_individual_mode` — the two implementations are nearly parallel but not shared.

**3. `executor.py::_execute_combined_mode` (depth 5)**
Two separate loops over channel IDs with nested exception handling for `InsufficientContentError` and generic exceptions. Channel name resolution inside the loop adds another layer. The aggregate min-message check after the loop uses a different code path than the per-channel check.

---

## Long Methods List

Methods with more than 50 lines of code (excluding docstrings).

| File | Class | Method | LOC |
|------|-------|--------|-----|
| `dashboard/routes/summaries.py` | — | `generate_summary` | **385** |
| `summarization/engine.py` | `SummarizationEngine` | `summarize_messages` | **270** |
| `summarization/response_parser.py` | `ResponseParser` | `_parse_json_response` | **260** |
| `dashboard/routes/summaries.py` | — | `regenerate_stored_summary` | **304** |
| `scheduling/engine.py` | `ResilientSummarizationEngine` | `generate_with_retry` | **234** |
| `dashboard/routes/summaries.py` | — | `run_generation` | **244** |
| `command_handlers/summarize.py` | `SummarizeCommandHandler` | `handle_category_individual_summary` | **199** |
| `command_handlers/summarize.py` | `SummarizeCommandHandler` | `handle_summarize` | **180** |
| `dashboard/routes/summaries.py` | — | `get_stored_summary` | **172** |
| `scheduling/executor.py` | `TaskExecutor` | `_execute_combined_mode` | **169** |
| `command_handlers/summarize.py` | `SummarizeCommandHandler` | `handle_summarize_interaction` | **164** |
| `dashboard/routes/summaries.py` | — | `run_regeneration` | **161** |
| `scheduling/scheduler.py` | `TaskScheduler` | `_execute_scheduled_task` | **151** |
| `summarization/claude_client.py` | `ClaudeClient` | `create_summary` | **147** |
| `command_handlers/summarize.py` | `SummarizeCommandHandler` | `handle_category_combined_summary` | **121** |
| `summarization/response_parser.py` | `ResponseParser` | `_parse_freeform_response` | **118** |
| `scheduling/executor.py` | `TaskExecutor` | `_execute_individual_mode` | **112** |
| `summarization/engine.py` | `SummarizationEngine` | `health_check` | **70** |
| `command_handlers/summarize.py` | `SummarizeCommandHandler` | `handle_quick_summary` | **85** |

---

## Large Files List

Files exceeding 300 lines (the project's stated threshold is 500 lines per `CLAUDE.md`).

| File | Lines | Status | Notes |
|------|-------|--------|-------|
| `dashboard/routes/summaries.py` | **2,732** | CRITICAL | Exceeds 500-line limit by 5.5x; single file contains 27 distinct route handlers |
| `data/base.py` | 1,059 | CRITICAL | Abstract repository definitions mixed with concrete logic |
| `dashboard/models.py` | 1,058 | CRITICAL | Pydantic model file; many small classes but total is very large |
| `services/summary_push.py` | 905 | CRITICAL | Push service with multiple delivery strategies embedded |
| `archive/generator.py` | 872 | HIGH | Retrospective generation logic |
| `summarization/engine.py` | 838 | HIGH | Two classes in one file |
| `summarization/response_parser.py` | 830 | HIGH | Response parsing with 3 fallback parsers |
| `dashboard/auth.py` | 771 | HIGH | Authentication + session management in one module |
| `scheduling/scheduler.py` | 769 | HIGH | 15+ methods; could split persistence concern |
| `scheduling/executor.py` | 761 | HIGH | Task execution + delivery wiring |
| `discord_bot/commands.py` | 691 | MEDIUM | All command registrations in one file |
| `summarization/claude_client.py` | 668 | MEDIUM | API client + model mapping + fallback logic |
| `main.py` | 683 | MEDIUM | Application orchestration (acceptable for entry point) |
| `summarization/prompt_builder.py` | 598 | MEDIUM | 6 prompt template methods + builder logic |
| `archive/models.py` | 598 | MEDIUM | Archive-specific data models |
| **Frontend** | | | |
| `frontend/src/pages/Archive.tsx` | **1,806** | CRITICAL | 8 component definitions, 1 page component, 14+ state variables |
| `frontend/src/hooks/useArchive.ts` | 510 | HIGH | 15+ hook functions in one file |

---

## Large Classes / High Method Count

| Class | File | Method Count | Notes |
|-------|------|--------------|-------|
| `SummarizeCommandHandler` | `command_handlers/summarize.py` | **13** | Handles channel, category, individual, combined, quick, scheduled, and estimated cost flows |
| `SummarizationEngine` | `summarization/engine.py` | **8** | Two classes in same file makes responsibility unclear |
| `TaskScheduler` | `scheduling/scheduler.py` | **17** | Both scheduling API and persistence co-located |
| `TaskExecutor` | `scheduling/executor.py` | **11** | Execution + delivery + error tracking all in one class |
| `ClaudeClient` | `summarization/claude_client.py` | **14** | Model normalization, fallback, rate limiting, cost estimation |
| `ResponseParser` | `summarization/response_parser.py` | ~10 | Three distinct fallback parsers + citation resolution embedded |

---

## Dependency Coupling Analysis

### Python Backend Import Coupling

**High Coupling (7+ direct imports):**

- `main.py` imports from 15 distinct modules at startup — this is the composition root, which is expected, but the inline fallback logic (`emergency_server`) adds accidental complexity.
- `dashboard/routes/summaries.py` has 47 symbols imported from `dashboard/models` plus 7 route helper functions (`get_discord_bot`, `get_summarization_engine`, etc.) — all global singletons accessed via module-level functions.
- `scheduling/executor.py` imports from `delivery/*` (4 strategies), `models/*` (5 models), `logging/*`, `exceptions/*` — a wide fan-in that makes the executor hard to unit test.

**Circular Risk:**
- `summarization/engine.py` imports from `logging.error_tracker` (inside the method body at runtime to avoid circular dependency on line 566) — deferred import is a smell indicating hidden coupling.
- `config/manager.py` imports from `config/settings` which imports from `config/constants` — three-level chain but acceptable.
- `data/repositories/__init__.py` is used as a global singleton factory by both `main.py` and `dashboard/routes` — shared mutable state without DI boundary.

**Cross-Domain Leakage:**
- `dashboard/routes/summaries.py` directly instantiates `StoredSummary`, `SummaryJob`, `SummaryResult` models from multiple source modules — the route layer reaches into 5 domain modules instead of going through a service layer.
- `scheduling/executor.py` accesses `dashboard/models.SummaryScope` — scheduling domain depends on dashboard domain, which is an inverted dependency.

### Frontend Coupling

- `pages/Archive.tsx` defines `GenerateDialog`, `ImportDialog`, `JobsView`, `SourceCard`, `StatBox`, `CostsView`, `EmptyState`, `SourcesSkeleton` all inline — none of these are exported or reusable.
- `hooks/useArchive.ts` at 510 lines contains 15+ data-fetching functions that could be separated by concern (sources vs. jobs vs. costs vs. generation).
- `types/index.ts` at 398 lines serves as a single shared type barrel — acceptable but grows unbounded.

---

## Refactoring Recommendations (Prioritized by Impact)

### Priority 1 — Critical: Split `dashboard/routes/summaries.py`

**Impact: High | Effort: Medium | Risk: Low**

At 2,732 lines with 27+ route handlers and some functions exceeding CC=59, this file is the single highest-complexity item in the codebase. The `generate_summary` function (385 LOC, CC=59) does API request validation, permission checking, background task spawning, error tracking, and response formatting all inline.

**Recommended decomposition:**
```
dashboard/routes/
  summaries/
    __init__.py          (router assembly)
    list.py              (list_summaries, list_stored_summaries)
    detail.py            (get_summary, get_stored_summary, get_summary_prompt)
    generate.py          (generate_summary, get_task_status)
    regenerate.py        (regenerate_stored_summary, bulk_regenerate_summaries)
    push.py              (push_to_channel, push_summary_to_channel)
    email.py             (send_summary_to_email)
    jobs.py              (list_jobs, get_job, cancel_job, retry_job)
    search.py            (search_summaries, search_by_participant)
```

The `run_generation` and `run_regeneration` nested async functions (CC=35 and CC=30 respectively) should be extracted into a `SummaryGenerationService` class to enable unit testing without the FastAPI context.

---

### Priority 2 — Critical: Decompose `ResponseParser._parse_json_response`

**Impact: High | Effort: Medium | Risk: Medium**

CC=58, 260 LOC, max nesting depth 6. This function handles JSON extraction, JSON repair, four different data format variants for each field, citation reference resolution, and action item building.

**Recommended decomposition:**
```python
class ResponseParser:
    def _parse_json_response(self, content, metadata, position_index=None):
        json_data = self._extract_and_repair_json(content, metadata)
        if not json_data:
            return None
        return self._build_parsed_summary(json_data, metadata, position_index)

    def _extract_and_repair_json(self, content, metadata) -> Optional[dict]:
        """JSON extraction + ADR-023 repair. Single responsibility."""

    def _build_parsed_summary(self, data, metadata, position_index) -> ParsedSummary:
        """Structured field extraction. Delegates to field-specific parsers."""

    def _extract_key_points(self, data, position_index) -> Tuple[List[str], List[ReferencedClaim]]:
        """Handle all key_points format variants."""

    def _extract_action_items(self, data, position_index) -> Tuple[List[ActionItem], List[ReferencedClaim]]:
        """Handle action item format variants."""
```

---

### Priority 3 — High: Extract `SummarizationEngine.summarize_messages`

**Impact: High | Effort: Medium | Risk: Low**

CC=23, 270 LOC. This method does custom prompt resolution, prompt building, token optimization, resilient generation, metadata assembly, fallback warning, and cache storage in one linear sequence. The deep `try/except` block starting at line 416 wraps 190 lines of logic.

**Recommended decomposition:**
```python
async def summarize_messages(self, messages, options, context, ...):
    self._validate_inputs(messages, options)
    cached = await self._check_cache(messages, options, channel_id)
    if cached:
        return cached

    prompt_data = await self._build_prompt(messages, options, context, guild_id)
    response, parsed, tracker = await self._generate_with_resilience(
        prompt_data, options, messages, context
    )
    result = self._assemble_result(response, parsed, tracker, ...)
    await self._post_process(result, response, context)  # fallback warning, cache, logging
    return result
```

---

### Priority 4 — High: Eliminate `_execute_individual_mode` / `handle_category_individual_summary` duplication

**Impact: Medium | Effort: Low | Risk: Low**

`scheduling/executor.py::_execute_individual_mode` (CC=14, 112 LOC) and `command_handlers/summarize.py::handle_category_individual_summary` (CC=28, 199 LOC) implement nearly identical patterns: iterate channels, fetch messages, check min_messages, generate summary, deliver to channel. The command handler version additionally handles Discord interaction responses, but the core loop is duplicated.

**Recommended approach:** Create a `CategorySummaryService` in `services/` that provides the per-channel iteration logic, callable from both the command handler and the task executor.

---

### Priority 5 — High: Split `TaskScheduler` (persistence vs. scheduling)

**Impact: Medium | Effort: Low | Risk: Low**

`scheduling/scheduler.py` at 769 lines with 17 methods conflates APScheduler job management with persistence (database + file fallback) and task state tracking. The `_load_persisted_tasks`, `_persist_task`, `_persist_all_tasks` methods should be extracted into `TaskPersistenceCoordinator` — the scheduler then depends on the interface, not the implementation.

---

### Priority 6 — High: Decompose `ClaudeClient`

**Impact: Medium | Effort: Medium | Risk: Medium**

`ClaudeClient` at 668 lines handles model name normalization (OpenRouter vs. direct), fallback model selection, rate limiting, request parameter building, response processing, and cost calculation. These are four distinct concerns.

**Recommended extraction:**
- `ModelNameNormalizer` — `_normalize_model_name`, `_extract_retry_after`
- `ModelFallbackSelector` — `get_available_models`, `find_available_model`, `COMPREHENSIVE_MODEL_FALLBACKS`
- `CostCalculator` — `estimate_cost`, `MODEL_COSTS`
- Keep `ClaudeClient` as thin coordinator using these collaborators

---

### Priority 7 — Medium: Split `Archive.tsx` frontend page

**Impact: Medium | Effort: Low | Risk: Low**

`Archive.tsx` at 1,806 lines defines 8 separate component functions (`GenerateDialog`, `ImportDialog`, `JobsView`, `SourceCard`, `StatBox`, `CostsView`, `EmptyState`, `SourcesSkeleton`) inline in the same file. These should each be extracted to `components/archive/`:

```
components/archive/
  SourceCard.tsx
  GenerateDialog.tsx
  ImportDialog.tsx
  JobsView.tsx
  CostsView.tsx
  EmptyState.tsx
```

The 14 `useState` calls in `Archive` and `GenerateDialog` combined suggest state can be colocated with the dialogs rather than bubbling to the page level.

---

### Priority 8 — Medium: Reduce `_create_trigger` nesting

**Impact: Low | Effort: Low | Risk: Low**

`TaskScheduler._create_trigger` (CC=19, 89 LOC) is a large if/elif chain for schedule type mapping. Replace with a dispatch dictionary:

```python
_TRIGGER_FACTORIES = {
    ScheduleType.ONCE: _build_date_trigger,
    ScheduleType.FIFTEEN_MINUTES: lambda task: IntervalTrigger(minutes=15, ...),
    ScheduleType.DAILY: _build_cron_trigger,
    # ...
}

def _create_trigger(self, task):
    factory = self._TRIGGER_FACTORIES.get(task.schedule_type)
    if not factory:
        raise ValueError(f"Unsupported schedule type: {task.schedule_type}")
    return factory(task)
```

---

### Priority 9 — Medium: Remove deferred imports inside methods

**Impact: Low | Effort: Low | Risk: Low**

Several files use `import` statements inside function bodies to avoid circular dependencies (`engine.py` lines 444, 566; `claude_client.py` lines 185, 260, 294). These indicate circular dependencies that should be resolved at the module boundary. The primary offender is `summarization/engine.py` importing from `logging/error_tracker` inside `summarize_messages`.

**Recommended fix:** Inject an optional `error_tracker` dependency into `SummarizationEngine.__init__` rather than importing it at call time.

---

### Priority 10 — Low: Frontend `useArchive.ts` decomposition

**Impact: Low | Effort: Low | Risk: Low**

`hooks/useArchive.ts` at 510 lines contains hooks for sources, jobs, cost reports, generation, import, and cancellation. Split into:
- `useArchiveSources.ts`
- `useArchiveJobs.ts`
- `useArchiveCosts.ts`
- `useArchiveGeneration.ts`

---

## Testability Impact Summary

The following table maps complexity metrics to testability difficulty:

| Function | CC | LOC | Nesting | Estimated Test Cases Required | Testability Rating |
|----------|----|-----|---------|------------------------------|-------------------|
| `generate_summary` | 59 | 385 | 7 | 40+ | Very Difficult |
| `_parse_json_response` | 58 | 260 | 6 | 35+ | Very Difficult |
| `regenerate_stored_summary` | 56 | 304 | 6 | 35+ | Very Difficult |
| `summarize_messages` | 23 | 270 | 7 | 15+ | Difficult |
| `_execute_scheduled_task` | 21 | 151 | 6 | 12+ | Difficult |
| `handle_summarize_interaction` | 20 | 164 | 6 | 12+ | Difficult |
| `generate_with_retry` | 15 | 234 | 5 | 10+ | Moderate |
| `create_summary` | 16 | 147 | 5 | 10+ | Moderate |

Functions with CC > 10 require a minimum of CC test cases (one per path) to achieve statement coverage. At CC=59, `generate_summary` technically requires 59 test paths for branch coverage — in practice, this means the function cannot be adequately tested without first being decomposed.

---

## Quality Gate Thresholds (Recommended)

To prevent further complexity accumulation, enforce the following in CI:

| Metric | Warning Threshold | Failure Threshold |
|--------|------------------|-------------------|
| Cyclomatic Complexity (per function) | 10 | 20 |
| Cognitive Complexity (per function) | 15 | 25 |
| Lines per function | 50 | 80 |
| Lines per file | 300 | 500 |
| Nesting depth | 4 | 6 |
| Parameters per function | 5 | 7 |

Recommended tooling: `radon` for Python CC (already installable via pip), `flake8-cognitive-complexity` for cognitive complexity, and ESLint `complexity` rule for TypeScript.

---

## Appendix: File Inventory by Complexity

### Python files by size

| File | Lines |
|------|-------|
| `dashboard/routes/summaries.py` | 2,732 |
| `command_handlers/summarize.py` | 1,118 |
| `data/base.py` | 1,059 |
| `dashboard/models.py` | 1,058 |
| `services/summary_push.py` | 905 |
| `archive/generator.py` | 872 |
| `summarization/engine.py` | 838 |
| `summarization/response_parser.py` | 830 |
| `dashboard/auth.py` | 771 |
| `scheduling/scheduler.py` | 769 |
| `scheduling/executor.py` | 761 |
| `discord_bot/commands.py` | 691 |
| `main.py` | 683 |
| `summarization/claude_client.py` | 668 |
| `summarization/prompt_builder.py` | 598 |
| `archive/models.py` | 598 |
| `webhook_service/server.py` | 597 |
| `services/push_message_builder.py` | 594 |
| `services/email_delivery.py` | 591 |
| `models/summary.py` | 549 |
| `command_handlers/prompt_config.py` | 547 |
| `command_handlers/config.py` | 543 |
| `webhook_service/endpoints.py` | 530 |
| `archive/cost_tracker.py` | 525 |
| `archive/backfill.py` | 515 |
| `command_handlers/schedule.py` | 507 |

### Frontend files by size

| File | Lines |
|------|-------|
| `pages/Archive.tsx` | 1,806 |
| `hooks/useArchive.ts` | 510 |
| `pages/Webhooks.tsx` | 529 |
| `pages/Summaries.tsx` | 497 |
| `pages/Errors.tsx` | 443 |
| `hooks/useStoredSummaries.ts` | 341 |
| `types/index.ts` | 398 |

---

*Report generated by V3 QE Code Complexity Analyzer — Agentic QE v3*
*Analysis method: AST-based cyclomatic complexity (Python `ast` module), manual cognitive complexity estimation, line count analysis, nesting depth scan*
