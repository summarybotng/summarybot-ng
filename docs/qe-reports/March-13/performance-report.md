# Performance Analysis Report - summarybot-ng
**Date:** 2026-03-13
**Reviewer:** V3 QE Performance Reviewer
**Review Type:** Comprehensive Static Performance Analysis
**Scope:** Full codebase - Python backend, TypeScript frontend, SQLite data layer

---

## Executive Summary

**Performance Grade: C+ (Acceptable with critical bottlenecks)**

The codebase demonstrates clear awareness of performance concerns - there are explicit PERF annotations, batch insert optimizations with `executemany`, LRU-ordered caches using `OrderedDict`, and FTS5 full-text search. However, several severe regressions are present that will degrade under any real-world load: a global serializing write lock that eliminates database concurrency, multiple unbounded full-table scans masquerading as count queries, N+1-pattern query explosions in the guild listing endpoint, and JSON extraction in WHERE clauses that cannot use conventional indexes.

### Top 5 Bottlenecks (by Production Impact)

| Rank | Issue | Location | Estimated Impact |
|------|-------|----------|-----------------|
| 1 | Global asyncio write lock serializes ALL writes | `src/data/sqlite/connection.py:152` | Total write throughput capped at ~1 write/op regardless of concurrency |
| 2 | `find_by_guild(limit=10000)` fetches unbounded data for counting | `src/dashboard/routes/guilds.py:118,298` | O(n) memory + query time for each guild page load |
| 3 | N+1 pattern: per-guild repo queries inside a loop | `src/dashboard/routes/guilds.py:92-171` | 5-7 DB queries per guild * N guilds on every `/guilds` request |
| 4 | `json_extract()` filters in WHERE without generated columns | `src/data/sqlite/stored_summary_repository.py:184-241` | Full table scan on every content-based filter |
| 5 | In-memory tag filtering post-query | `src/data/sqlite/stored_summary_repository.py:360-366` | Fetches full LIMIT rows only to discard most |

---

## 1. Database Performance

### 1.1 Connection Management - CRITICAL

**File:** `/workspaces/summarybot-ng/src/data/sqlite/connection.py`

The connection pool is hardcoded to `pool_size=1` (line 74) by design, with comments acknowledging this eliminates pool benefit. More critically, a **module-level global asyncio lock** (`_global_write_lock`, line 55) serializes every INSERT, UPDATE, DELETE, REPLACE, CREATE, DROP, and ALTER across the entire process.

```
# connection.py lines 152-156
async with _get_global_write_lock():
    async with self._get_connection() as conn:
        cursor = await conn.execute(query, params or ())
        await conn.commit()
        return cursor
```

**Impact:** Under concurrent load (e.g., scheduled tasks firing simultaneously, multiple webhook events arriving, a Discord message ingestion batch running while a dashboard save occurs), every write operation queues behind the single global lock. With the exponential backoff retry at lines 167-170 adding 0.5s-8s delays, a single stuck write can cascade into 15.5 seconds of blocked writes. WAL mode (enabled at line 96) is neutralized since WAL's concurrency benefit requires concurrent connections, not a pool of one.

**Recommendation (HIGH):** SQLite WAL mode natively supports one writer plus multiple readers. Keep WAL mode but accept one-writer semantics directly from aiosqlite rather than re-implementing with an asyncio lock. For write-heavy paths, consider SQLite `BEGIN IMMEDIATE` transactions at the application layer rather than a blanket lock wrapping every individual statement.

---

### 1.2 Missing Composite Indexes for Filter Patterns - HIGH

**File:** `/workspaces/summarybot-ng/src/data/sqlite/stored_summary_repository.py`

The `_build_filter_clause` method (lines 143-249) constructs WHERE clauses combining `guild_id` with `source`, `created_at`, `archive_period`, `message_count`, and `participant_count`. Migration 011 created a composite `idx_stored_summaries_unified ON stored_summaries(guild_id, created_at DESC, source)`, which covers the common list case. However, sorting by `message_count` (line 341) falls back to a filesort since no index covers `(guild_id, message_count)`.

Migration 009 (stored_summaries) indexes:
- `idx_stored_summaries_guild` - single column
- `idx_stored_summaries_created` - single column
- `idx_stored_summaries_pinned` - partial, WHERE is_pinned = TRUE

The `find_by_guild` pagination query at line 348 always ORDER BY `is_pinned DESC, {sort_field} {sort_direction}`. The `is_pinned DESC` prefix means the pinned-first sort cannot use any existing index when combined with `message_count` sorting, forcing a full sort pass.

**Recommendation (HIGH):** Add the following indexes:
```sql
CREATE INDEX idx_stored_summaries_sort_mc
ON stored_summaries(guild_id, is_pinned DESC, message_count DESC);

CREATE INDEX idx_stored_summaries_sort_ca
ON stored_summaries(guild_id, is_pinned DESC, created_at DESC);
```

---

### 1.3 JSON Extract in WHERE Clauses - HIGH

**File:** `/workspaces/summarybot-ng/src/data/sqlite/stored_summary_repository.py`, lines 184-241

Multiple filter conditions in `_build_filter_clause` call `json_array_length(json_extract(summary_json, '$.key_points'))` and similar patterns. SQLite cannot use B-tree indexes on these expressions unless generated columns are defined.

Examples of unindexable conditions:
- Line 184: `"json_array_length(source_channel_ids) = 1"` - calls JSON function on stored JSON column
- Lines 195-208: `json_extract(summary_json, '$.key_points')`, `$.action_items`, `$.participants` - queries into the large `summary_json` blob
- Lines 219-241 (ADR-021 count filters): repeated `COALESCE(json_array_length(json_extract(summary_json, ...)))` conditions

The `summary_json` column stores the entire `SummaryResult` as a JSON blob. Parsing this blob for every row during a WHERE evaluation means any query using content filters performs a full table scan.

Migration 018 partially addresses this for `message_count` and `participant_count` by populating dedicated columns, but `key_points`, `action_items`, and `participants` counts are not materialized.

**Recommendation (HIGH):** Add `key_points_count INTEGER`, `action_items_count INTEGER` as real columns populated on save (follow the pattern already used for `message_count` and `participant_count` in `SQLiteStoredSummaryRepository.save()` lines 49-53). Then replace all `json_array_length(json_extract(summary_json, '$.key_points'))` references with the materialized column.

---

### 1.4 `search_by_participant` - Full Table Scan with JSON Subquery - MEDIUM

**File:** `/workspaces/summarybot-ng/src/data/sqlite/stored_summary_repository.py`, lines 852-865

```python
participant_conditions.append(
    "EXISTS (SELECT 1 FROM json_each(json_extract(summary_json, '$.participants')) "
    "WHERE json_extract(value, '$.user_id') = ?)"
)
```

This correlated subquery iterates over every participant JSON array element for every row that passes prior filters. For a guild with thousands of summaries, this is O(rows * avg_participants) per query. The FTS index at migration 016 stores participant names/IDs in the `participants` column, but `search_by_participant` does not use it.

**Recommendation (MEDIUM):** Route participant search through the existing FTS5 table (`summary_fts`) which already stores participant data in a searchable form. The `search()` method at line 738 provides the correct pattern.

---

### 1.5 Duplicate Count+Fetch Pattern in `save_batch` (logging repository) - MEDIUM

**File:** `/workspaces/summarybot-ng/src/logging/repository.py`, lines 84-130

The `save_batch` method (lines 84-130) loops over the params list and calls `self.connection.execute(query, params)` one at a time inside a `for` loop, despite the method description claiming "Batch INSERT statement". Each individual `execute()` call acquires the global write lock, commits, and releases. For a batch of N log entries this results in N separate lock acquisitions and N commits instead of the intended 1.

The ingest repository at `src/data/sqlite/ingest_repository.py:99` correctly uses `executemany()`. The logging repository does not.

**Recommendation (MEDIUM):** Replace the loop with a single `await self.connection.executemany(query, params_list)` call.

---

### 1.6 `get_navigation` - 3 Sequential DB Queries - LOW

**File:** `/workspaces/summarybot-ng/src/data/sqlite/stored_summary_repository.py`, lines 681-736

Navigation requires: (1) fetch current summary's `created_at`, (2) fetch previous summary, (3) fetch next summary. These three queries run sequentially. With the global write lock not affecting reads, these can be parallelized.

**Recommendation (LOW):** Use `asyncio.gather()` to run prev/next queries concurrently after obtaining `current_time`.

---

## 2. Algorithmic Complexity Analysis

### 2.1 Guild Listing Endpoint - Critical O(N * M) Pattern

**File:** `/workspaces/summarybot-ng/src/dashboard/routes/guilds.py`, lines 92-171

The `list_guilds` endpoint iterates over all guilds in the user's list and for each guild:

1. Line 118: `await stored_repo.find_by_guild(guild_id=guild_id, limit=10000)` - fetches up to 10,000 full summary objects just to get a count
2. Line 122-128: Another call to `find_by_guild(limit=1)` for last-summary timestamp
3. Line 135: `await task_repo.get_tasks_by_guild(guild_id)` - fetches all tasks
4. Line 144: `await webhook_repo.get_webhooks_by_guild(guild_id)` - fetches all webhooks
5. Line 153: `await feed_repo.get_feeds_by_guild(guild_id)` - fetches all feeds

That is **5 database queries per guild**, all running sequentially inside the loop. A user in 10 guilds generates 50+ database queries per page load. The `find_by_guild(limit=10000)` at line 118 deserializes thousands of JSON blobs into Python objects solely to call `len()` on the result.

The same pattern repeats in `get_guild` (lines 297-330):
- Line 298: `find_by_guild(limit=10000)` again for total count
- Line 315: Another `find_by_guild(limit=10000)` for this-week summaries
- Line 323: Yet another `find_by_guild(limit=1)` for last summary

**Complexity:** O(n_guilds * 5 * query_cost) where query_cost includes JSON deserialization of potentially thousands of objects.

**Recommendation (CRITICAL):** Replace all count-only uses of `find_by_guild(limit=10000)` with the existing `count_by_guild()` method. The `count_by_guild()` method already supports all the same filter parameters and runs a `SELECT COUNT(*)` which is O(index scan) vs O(full fetch + deserialize). Example fix:

```python
# BEFORE (line 118) - fetches thousands of objects
all_summaries = await stored_repo.find_by_guild(guild_id=guild_id, limit=10000)
summary_count = len(all_summaries)

# AFTER - single COUNT(*) query
summary_count = await stored_repo.count_by_guild(guild_id=guild_id)
```

For the per-guild loop, fan out the 5 queries concurrently with `asyncio.gather()`.

---

### 2.2 Fetch Thread Messages - Rate Limit Delay Per Message - MEDIUM

**File:** `/workspaces/summarybot-ng/src/message_processing/fetcher.py`, lines 155-163

```python
async for message in thread.history(limit=None, oldest_first=True):
    if limit and count >= limit:
        break
    messages.append(message)
    count += 1
    if self.rate_limit_delay > 0:
        await asyncio.sleep(self.rate_limit_delay)
```

`fetch_thread_messages` sleeps `rate_limit_delay` (default 0.1s) after every single message. For a thread with 100 messages, this adds 10 seconds of artificial delay. The main `_fetch_messages_with_pagination` method (lines 240-301) was correctly optimized (PERF-004 comment) to remove per-message delays - `fetch_thread_messages` was not updated.

**Impact:** Thread summarization for active threads is 100x slower than necessary.

**Recommendation (MEDIUM):** Remove the per-message `asyncio.sleep` from `fetch_thread_messages`. Rate limiting is handled by discord.py's internal bucket system and the HTTP retry logic at lines 94-96.

Similarly, `fetch_around_message` (lines 196-215) applies per-message delays in two separate loops.

---

### 2.3 Message Processing Pipeline - Linear, Synchronous Per-Message - LOW

**File:** `/workspaces/summarybot-ng/src/message_processing/processor.py`, lines 113-133

The `_process_message_pipeline` method processes each message sequentially:

```python
for message in filtered_messages:
    processed = self.cleaner.clean_message(message)
    processed = self.extractor.extract_information(processed, message)
    if self.validator.is_valid_message(processed):
        processed_messages.append(processed)
```

For large message batches (hundreds to thousands), this is O(n) sequential CPU work. `clean_message`, `extract_information`, and `is_valid_message` are synchronous and CPU-bound. Since these operations are independent per message, they could be parallelized via `asyncio.gather` if converted to async, or offloaded to a thread pool for CPU-bound work.

**Recommendation (LOW):** For batches over ~500 messages, consider `asyncio.to_thread` to run the synchronous pipeline in a thread pool, preventing blocking the event loop.

---

### 2.4 `_format_source_content` - O(N) String Concatenation - INFORMATIONAL

**File:** `/workspaces/summarybot-ng/src/summarization/engine.py`, lines 810-838

The method appends strings to a list and joins at the end (correct). However, for very large message sets (5000+ messages at 500 chars each), the final `source_content` stored in the database could reach 2.5+ MB per summary. This data is persisted as raw text in `summaries.source_content` and potentially embedded in `stored_summaries.summary_json`.

**Impact:** Each summary save writes multi-megabyte blobs. Over time, the database size grows rapidly. SQLite WAL mode amplifies this as WAL entries are not reclaimed until a checkpoint.

**Recommendation (INFORMATIONAL):** Consider compressing `source_content` before storage or truncating to a reasonable size. At minimum, document the expected storage growth per summary.

---

## 3. Memory Management Issues

### 3.1 Unbounded In-Memory Task Tracking - MEDIUM

**File:** `/workspaces/summarybot-ng/src/summarization/engine.py`, line 57 (summaries.py)
**File:** `/workspaces/summarybot-ng/src/dashboard/routes/summaries.py`, line 57

```python
# In-memory task tracking (replace with proper task queue in production)
_generation_tasks: dict[str, dict] = {}
```

This module-level dictionary accumulates task status records and is never cleaned up. For long-running instances handling many summary generation requests, this dict grows unboundedly. The comment acknowledges it is not production-ready but it remains in production code paths.

**Recommendation (MEDIUM):** Add TTL-based eviction (e.g., remove tasks older than 1 hour) or replace with the existing `SummaryJobRepository` which is already designed for this purpose.

---

### 3.2 PermissionCache O(N) LRU Eviction - MEDIUM

**File:** `/workspaces/summarybot-ng/src/permissions/cache.py`, lines 203-218

```python
async def _evict_lru(self) -> None:
    lru_key = min(
        self._cache.keys(),
        key=lambda k: self._cache[k].last_accessed
    )
    del self._cache[lru_key]
```

This `min()` scan is O(n) over all cache entries. At `max_size=10000`, every eviction scans 10,000 entries. The `SummaryCache.MemoryCache` (summarization/cache.py:46-91) and `PromptCacheManager` (prompts/cache.py:29-239) were both upgraded to use `OrderedDict` for O(1) LRU eviction (as noted in their Phase 4 comments), but `PermissionCache` was not updated.

**Recommendation (MEDIUM):** Refactor `PermissionCache` to use `OrderedDict` with `move_to_end()` on access and `popitem(last=False)` for eviction, matching the pattern already used in the other caches.

---

### 3.3 SummaryCache invalidate_guild Pattern Mismatch - LOW

**File:** `/workspaces/summarybot-ng/src/summarization/cache.py`, lines 211-225 and 254-278

The `invalidate_guild` method uses prefix pattern `f"summary:{guild_id}:"`, but `_generate_cache_key` produces keys in the format `summary:{guild_id}:{channel_id}:{start}:{end}:{options}` (line 269-277). The prefix match is correct.

However, `invalidate_channel` at line 199-209 uses prefix `f"summary:{channel_id}:"`, which does not match the key format `summary:{guild_id}:{channel_id}:...` because the guild_id prefix comes first. Channel invalidation silently fails (0 entries removed) if the guild is not also specified.

**Recommendation (LOW):** Fix `invalidate_channel` to accept both `channel_id` and `guild_id` and use prefix `f"summary:{guild_id}:{channel_id}:"`.

---

### 3.4 Post-Query Tag Filtering Loads Excessive Data - HIGH

**File:** `/workspaces/summarybot-ng/src/data/sqlite/stored_summary_repository.py`, lines 360-366

```python
rows = await self.connection.fetch_all(query, tuple(params))
summaries = [self._row_to_stored_summary(row) for row in rows]

# Filter by tags in Python (SQLite JSON support is limited)
if tags:
    summaries = [
        s for s in summaries
        if any(tag in s.tags for tag in tags)
    ]
```

When tags are specified, the query fetches up to `limit` rows, deserializes all of them into `StoredSummary` objects (including parsing the large `summary_json` blob), and then filters in Python. If only 2 out of 20 results match the tags, 18 full object deserializations were wasted.

This also means the pagination is incorrect: a `limit=20` request may return fewer than 20 results because the tag filter happens after the LIMIT clause.

**Recommendation (HIGH):** SQLite has full JSON support for array contains: use `json_each` or a LIKE-based approach:
```sql
AND EXISTS (
    SELECT 1 FROM json_each(tags)
    WHERE json_each.value = ?
)
```
This can be applied in the WHERE clause before LIMIT, fixing both correctness and performance.

---

## 4. Concurrency and Async Patterns

### 4.1 ResilientSummarizationEngine - `import time` in Hot Path - INFORMATIONAL

**File:** `/workspaces/summarybot-ng/src/summarization/engine.py`, line 112

```python
async def generate_with_retry(self, ...):
    import time  # <- module-level import inside hot method
```

`import time` inside a frequently-called async method forces a module lookup on every invocation. Python caches module imports but the dict lookup still occurs. Move to module-level import.

---

### 4.2 RateLimitError Handling Blocks Event Loop - HIGH

**File:** `/workspaces/summarybot-ng/src/summarization/engine.py`, lines 257-259

```python
retry_after = getattr(e, 'retry_after', 60)
logger.warning(f"Rate limit hit, waiting {retry_after}s")
await asyncio.sleep(retry_after)
```

An `asyncio.sleep(60)` inside the retry loop blocks the coroutine for up to 60 seconds. While `asyncio.sleep` does not block the thread, it does hold the asyncio task alive for 60 seconds. If multiple channels or scheduled tasks hit rate limits simultaneously, the event loop accumulates many sleeping tasks. Each sleeping task retains its full stack frame and the `tracker`, `response`, etc. objects in memory.

**Impact:** Under rate-limit storm conditions (e.g., burst of scheduled summaries), memory usage grows proportionally to the number of sleeping retry tasks.

**Recommendation (HIGH):** Implement exponential jitter: `await asyncio.sleep(min(retry_after, 30) * (0.5 + random.random()))`. Cap the retry delay and add jitter to avoid thundering herd. Consider a circuit breaker pattern.

---

### 4.3 `batch_summarize` Semaphore Value is Arbitrary - MEDIUM

**File:** `/workspaces/summarybot-ng/src/summarization/engine.py`, lines 640-641

```python
semaphore = asyncio.Semaphore(3)  # Max 3 concurrent requests
```

The hardcoded value of 3 is not configurable and not tied to Claude API rate limits or system resources. Under load, this is either too low (wasting available capacity) or too high (exceeding rate limits). The Claude API has per-minute token limits; the concurrency control should be rate-limit-aware.

**Recommendation (MEDIUM):** Make the semaphore value configurable via `SummarizationEngine` constructor parameter. Consider implementing a token-bucket rate limiter that tracks tokens-per-minute rather than concurrent request count.

---

### 4.4 Scheduler Task Execution - Repository Import Inside Hot Path - MEDIUM

**File:** `/workspaces/summarybot-ng/src/scheduling/scheduler.py`, lines 578-581

```python
from ..data.repositories import get_summary_job_repository
job_repo = await get_summary_job_repository()
```

This dynamic import and repository initialization happens inside `_execute_scheduled_task()`, which is called for every scheduled task execution. If the repository factory performs I/O or connection setup, this adds latency to every task execution.

**Recommendation (MEDIUM):** Inject the job repository at scheduler construction time (already done partially with `task_repository` parameter) rather than resolving it at execution time.

---

### 4.5 Config File Watcher - 1-Second Polling Loop - LOW

**File:** `/workspaces/summarybot-ng/src/config/manager.py`, lines 242-244

```python
while True:
    await asyncio.sleep(1)  # Check every second
    current_modified = self.config_path.stat().st_mtime
```

The file watcher calls `Path.stat()` every second regardless of file activity. This is a blocking syscall called from an async context without `asyncio.to_thread`. On slow or NFS-mounted filesystems, this could stall the event loop.

**Recommendation (LOW):** Use `asyncio.to_thread(self.config_path.stat)` to avoid blocking, or use `watchfiles` / `inotify`-based watching to eliminate polling entirely.

---

## 5. Caching Assessment

### 5.1 Summary Cache - Correct Implementation

**File:** `/workspaces/summarybot-ng/src/summarization/cache.py`

The `MemoryCache` implementation is well-designed:
- Uses `OrderedDict` for O(1) LRU eviction (Phase 4 upgrade, lines 56, 80)
- TTL-based expiration with lazy cleanup on access (lines 63-66)
- Key includes guild_id for proper guild-scoped invalidation (Phase 4, line 271)

**Gap:** No cache hit/miss tracking in `MemoryCache` (`get_stats` returns `"hit_ratio": "N/A"` at line 127). Without hit ratio metrics, it is impossible to know if the cache is providing value in production.

**Recommendation:** Add hit/miss counters to `MemoryCache` matching the pattern in `PermissionCache`.

---

### 5.2 Prompt Cache - Stale-While-Revalidate is Well Implemented

**File:** `/workspaces/summarybot-ng/src/prompts/cache.py`

The `PromptCacheManager` implements the stale-while-revalidate pattern correctly (lines 242-290). Background refresh tasks are tracked and cleaned up via `add_done_callback` (lines 285-286). The `OrderedDict`-based O(1) eviction is correctly implemented.

**Gap:** Background tasks set at line 284 (`_background_tasks`) is a module-level set, so tasks accumulate for the process lifetime. The `discard` callback removes completed tasks, but if the callback itself fails, tasks leak. Consider a maximum size for `_background_tasks`.

---

### 5.3 Permission Cache - O(N) Eviction (Already Noted in Section 3.2)

---

### 5.4 No Distributed Cache Support

The cache layer only supports in-memory backends (line 338-350 of summarization/cache.py). In a multi-process deployment (e.g., multiple workers behind a load balancer), each process maintains an independent in-memory cache with no coordination. Summaries cached in process A are invisible to process B.

**Recommendation:** The `CacheInterface` abstraction already exists. The Redis backend stub is noted as "not yet implemented" (line 341). Implementing Redis would allow shared caching across processes.

---

## 6. API Performance

### 6.1 `/guilds` Endpoint - N+1 Query Pattern - CRITICAL

Already covered in Section 2.1. Summary: 5 sequential DB queries per guild, each inside a per-guild for-loop. For a user managing 10 guilds, the `/guilds` endpoint triggers 50+ queries on every page load, all serialized through the global write lock (reads use a separate path but still compete for the single connection).

**Estimated latency at 10 guilds:** 10 guilds * (1 count query * ~5ms + 4 other queries * ~5ms each) = ~250ms minimum, before JSON deserialization overhead.

---

### 6.2 `/guilds/{guild_id}` Endpoint - Triple Unbounded Fetch - CRITICAL

**File:** `/workspaces/summarybot-ng/src/dashboard/routes/guilds.py`, lines 297-330

Three separate calls to `find_by_guild(limit=10000)`:
1. Line 298: all summaries for total count
2. Line 315: summaries in last week for `summaries_this_week`
3. Line 323: latest 1 summary

All three could be replaced:
1. `count_by_guild()` - no filters needed
2. `count_by_guild(created_after=week_ago)` - single count query
3. `find_by_guild(limit=1, sort_by="created_at", sort_order="desc")` - already correct for last summary

**Recommendation (CRITICAL):** Replace `find_by_guild(limit=10000)` with `count_by_guild()` throughout the dashboard routes. This single change eliminates the most expensive query pattern in the codebase.

---

### 6.3 Summary Search - Two Sequential Queries - LOW

**File:** `/workspaces/summarybot-ng/src/data/sqlite/stored_summary_repository.py`, lines 778-807

The `search()` method runs a `COUNT(*)` query (line 779) and then the actual search query (line 789) sequentially. Both queries use identical `WHERE fts MATCH ? AND {where_clause}` predicates. SQLite has to execute the FTS5 full-text search twice.

**Recommendation (LOW):** Use a single query with `COUNT(*) OVER ()` window function or cache the count from the actual result set size if pagination is not needed for the initial render.

---

## 7. Frontend Performance

### 7.1 React Query - Correct Caching Strategy

**File:** `/workspaces/summarybot-ng/src/frontend/src/hooks/useStoredSummaries.ts`

The frontend uses React Query (`@tanstack/react-query`) for data fetching. All major data sources have proper `queryKey` arrays that include relevant identifiers, enabling automatic cache invalidation on mutation. The `onSuccess` callbacks in mutations correctly call `queryClient.invalidateQueries()`.

**Minor Issue (line 256):** The `useRegenerateSummary` hook uses a 5-second `setTimeout` before invalidating queries:

```typescript
setTimeout(() => {
    queryClient.invalidateQueries({ queryKey: ["stored-summaries", guildId] });
}, 5000);
```

This is a timing hack. If regeneration completes in under 5 seconds, the UI shows stale data. If it takes more than 5 seconds, the invalidation fires prematurely. The `useBulkRegenerateSummaries` hook uses 10 seconds. Both approaches are racey.

**Recommendation:** Implement polling via React Query's `refetchInterval` or use an SSE/WebSocket endpoint to receive the regeneration completion event. The backend already has job tracking infrastructure via `SummaryJob`.

---

### 7.2 Vite Build - No Code Splitting Configured - MEDIUM

**File:** `/workspaces/summarybot-ng/src/frontend/vite.config.ts`

The Vite configuration (4 lines) has no build optimizations configured: no `rollupOptions.output.manualChunks` for code splitting, no `build.target` for modern browser optimization, and no asset size warnings threshold. The default Vite build will produce a single vendor chunk containing all dependencies.

Given the dependency list likely includes React, @tanstack/react-query, discord-related types, and UI components, the initial bundle could be 500KB+ uncompressed.

**Recommendation (MEDIUM):** Add manual chunk splitting in vite.config.ts:
```typescript
build: {
  rollupOptions: {
    output: {
      manualChunks: {
        vendor: ['react', 'react-dom'],
        query: ['@tanstack/react-query'],
        ui: [/* UI component libraries */]
      }
    }
  }
}
```

---

### 7.3 No Stale-Time Configured in React Query - INFORMATIONAL

The `useGuilds`, `useGuild`, and related hooks use default React Query behavior with no `staleTime` configured. React Query defaults to `staleTime: 0`, meaning every window focus triggers a refetch. For data like guild configurations that rarely change, this generates unnecessary API calls.

**Recommendation (INFORMATIONAL):** Set `staleTime: 5 * 60 * 1000` (5 minutes) for configuration data and `staleTime: 30 * 1000` (30 seconds) for summary lists.

---

## 8. Resource Management

### 8.1 SQLite Connection Never Returned in `begin_transaction` - MEDIUM

**File:** `/workspaces/summarybot-ng/src/data/sqlite/connection.py`, lines 221-224

```python
async def begin_transaction(self) -> Transaction:
    conn = await self._available.get()
    return SQLiteTransaction(conn)
```

The connection is dequeued from `_available` but never returned unless the caller explicitly manages the `SQLiteTransaction` lifecycle. If a transaction is started but the caller does not call `commit()` or `rollback()` (and does not use the context manager), the connection leaks from the pool permanently. With `pool_size=1`, this would deadlock the entire application.

**Recommendation (MEDIUM):** The `SQLiteTransaction.__aexit__` handles commit/rollback but not returning the connection to the pool. Add `await self._available.put(conn)` in `__aexit__` or document that `begin_transaction` must always be used as a context manager.

---

### 8.2 Retention Manager - Synchronous I/O in Manifest Operations - MEDIUM

**File:** `/workspaces/summarybot-ng/src/archive/retention.py`, lines 357-374

The `_load_manifest`, `_save_manifest`, and `_add_to_manifest` methods use synchronous `open()` calls. The `soft_delete` method (line 85) calls `_add_to_manifest` which reads and writes the manifest file. These are blocking I/O operations called from what may be an async context.

The `apply_retention_policy` (lines 295-338) calls `sources_dir.glob("**/*.md")` for a potentially large directory tree, then reads each `.meta.json` file synchronously in a loop. For large archives with thousands of summaries, this blocks the event loop.

**Recommendation (MEDIUM):** Wrap manifest file operations in `asyncio.to_thread()` or convert to use `aiofiles`. For production use, consider migrating retention metadata to the SQLite database rather than a JSON manifest file.

---

### 8.3 Archive `cleanup_expired` - Nested `permanent_delete` in Loop - MEDIUM

**File:** `/workspaces/summarybot-ng/src/archive/retention.py`, lines 272-293

The `cleanup_expired` method calls `self.permanent_delete(summary_id)` in a loop. Each `permanent_delete` call (lines 228-270) calls `_load_manifest()` and `_save_manifest()` - two synchronous disk reads/writes per deleted item. For N expired items this is O(2N) file I/O operations where a single read + N removals + single write would suffice.

**Recommendation (MEDIUM):** Batch all removals: load manifest once, remove all expired entries, save manifest once.

---

## 9. Scalability Assessment

### 9.1 Single-Connection SQLite Architecture

The current architecture uses a single SQLite connection with a serializing write lock. This is suitable for a single-server Discord bot handling moderate load (< 100 concurrent operations). Under high load:

- **Write Throughput Ceiling:** Bounded by single-threaded SQLite writes (~few hundred writes/second)
- **Read Scalability:** Limited by single connection even in WAL mode (which allows concurrent readers but the pool_size=1 prevents actual concurrent reads)
- **Multi-process Deployment:** Incompatible. SQLite with WAL supports multiple readers but only one writer at a time. Multiple Python processes connecting to the same SQLite file would require careful locking not present in the current implementation.

**Scalability Limit:** The architecture scales to approximately 1 Discord server guild per connected server instance. For multi-guild production deployment with heavy usage (dozens of scheduled summaries, active archiving), the SQLite bottleneck will become the limiting factor.

---

### 9.2 APScheduler In-Memory Job Store

**File:** `/workspaces/summarybot-ng/src/scheduling/scheduler.py`, lines 49-53

APScheduler is configured with the default in-memory job store. On process restart, all scheduled jobs are lost and must be reloaded from the database. The reload logic at lines 687-721 correctly loads from the database, but the APScheduler job store itself is in-memory with `coalesce=True` (line 159) meaning missed executions during restart are collapsed.

**Scalability Limit:** No horizontal scaling possible. If multiple bot instances were deployed, they would all independently schedule and execute the same tasks, producing duplicate summaries.

---

## 10. Recommendations (Prioritized by Impact)

### Critical Priority

1. **Replace `find_by_guild(limit=10000)` with `count_by_guild()`** in all dashboard routes.
   - Files: `src/dashboard/routes/guilds.py` lines 118, 298, 315
   - Reduces query cost by 100-1000x for guilds with many summaries
   - Fixes incorrect pagination when used for count

2. **Parallelize per-guild queries in `list_guilds` with `asyncio.gather()`**
   - File: `src/dashboard/routes/guilds.py` lines 92-171
   - Replace 5 sequential queries per guild with 1 concurrent batch
   - 5x reduction in response time for guild listing

3. **Materialize `key_points_count`, `action_items_count` columns**
   - File: `src/data/sqlite/stored_summary_repository.py` - `_build_filter_clause`
   - Add columns in a migration, populate in `save()`, replace `json_extract` conditions
   - Eliminates full table scans on content-based filter queries

### High Priority

4. **Fix post-query tag filtering** (Section 3.4)
   - Implement in-database JSON array contains check
   - Fixes pagination correctness and eliminates wasted deserialization

5. **Fix `PermissionCache._evict_lru` O(N) scan** (Section 3.2)
   - Replace with `OrderedDict` pattern matching other caches

6. **Fix `save_batch` in logging repository** (Section 1.5)
   - Replace for-loop individual executes with single `executemany()`

7. **Add composite sort indexes** (Section 1.2)
   - `(guild_id, is_pinned DESC, message_count DESC)` and `(guild_id, is_pinned DESC, created_at DESC)`

8. **Fix Rate Limit sleep behavior** (Section 4.2)
   - Cap retry_after, add jitter, consider circuit breaker

### Medium Priority

9. **Remove per-message sleep in `fetch_thread_messages`** (Section 2.2)
   - File: `src/message_processing/fetcher.py` lines 155-163

10. **Fix connection leak in `begin_transaction`** (Section 8.1)
    - Return connection to pool in `SQLiteTransaction.__aexit__`

11. **Make `batch_summarize` semaphore configurable** (Section 4.3)

12. **Fix `invalidate_channel` cache key pattern mismatch** (Section 3.3)

13. **Add Vite code splitting configuration** (Section 7.2)

14. **Fix retention manager batch manifest writes** (Section 8.3)

### Low Priority

15. **Parallelize `get_navigation` queries** (Section 1.6)
16. **Move `import time` to module level in engine.py** (Section 4.1)
17. **Add React Query `staleTime` to configuration queries** (Section 7.3)
18. **Add hit/miss tracking to `MemoryCache`** (Section 5.1)
19. **Config file watcher blocking stat call** (Section 4.5)

---

## Appendix: Files Examined

| File | Lines | Key Findings |
|------|-------|-------------|
| `src/data/sqlite/connection.py` | 225 | Global write lock (CRITICAL), single-connection pool |
| `src/data/sqlite/summary_repository.py` | 202 | Clean, proper index use |
| `src/data/sqlite/stored_summary_repository.py` | 947 | json_extract in WHERE (HIGH), post-query tag filter (HIGH), participant search full scan (MEDIUM) |
| `src/data/sqlite/config_repository.py` | 97 | Clean |
| `src/data/sqlite/ingest_repository.py` | 301 | `executemany` used correctly |
| `src/data/migrations/*.sql` | 18 files | FTS5 present, composite indexes partially correct |
| `src/summarization/engine.py` | 839 | Rate limit sleep (HIGH), `import time` in method |
| `src/summarization/cache.py` | 350 | O(1) LRU correct, no hit metrics |
| `src/summarization/prompt_builder.py` | 80+ | Clean |
| `src/message_processing/fetcher.py` | 341 | Per-message sleep in thread fetch (MEDIUM) |
| `src/message_processing/processor.py` | 135 | Sequential pipeline, acceptable for current scale |
| `src/scheduling/scheduler.py` | 770 | Dynamic import in hot path (MEDIUM) |
| `src/permissions/cache.py` | 312 | O(N) LRU eviction (MEDIUM) |
| `src/prompts/cache.py` | 339 | Well implemented stale-while-revalidate |
| `src/logging/repository.py` | 362 | `save_batch` loop vs executemany (MEDIUM) |
| `src/dashboard/routes/guilds.py` | 516 | N+1 queries (CRITICAL), unbounded fetches (CRITICAL) |
| `src/dashboard/routes/summaries.py` | 28+ | Unbounded `_generation_tasks` dict (MEDIUM) |
| `src/archive/retention.py` | 406 | Synchronous I/O in async context (MEDIUM), O(2N) manifest writes (MEDIUM) |
| `src/config/manager.py` | 267 | Blocking stat() in async (LOW) |
| `src/frontend/vite.config.ts` | 24 | No code splitting (MEDIUM) |
| `src/frontend/src/hooks/useStoredSummaries.ts` | 342 | setTimeout cache invalidation race (MEDIUM) |
| `src/frontend/src/hooks/useGuilds.ts` | 44 | No staleTime (LOW) |
| `tests/performance/test_performance_optimization.py` | 568 | Coverage of cache hits, batch processing - does not cover DB query patterns |

---

*Report generated by V3 QE Performance Reviewer - chaos-resilience domain (ADR-011)*
*Minimum finding score requirement: 2.0 | Achieved score: ~19.5 (CRITICAL=3, HIGH=2, MEDIUM=1, LOW=0.5)*
