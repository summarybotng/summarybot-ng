# Performance & Scalability Analysis Report

**Project:** SummaryBot NG
**Analyzed by:** QE Performance Reviewer (V3)
**Date:** 2026-03-11
**Report ID:** PERF-003-R2 (Revision 2 -- Deep Analysis)
**Scope:** Full codebase performance review across 10 analysis categories
**Files Analyzed:** 29 source files across 12 modules (~11,500+ lines)

---

## Executive Summary

SummaryBot NG exhibits several systemic performance issues that will degrade significantly under load. The most critical problems are concentrated in the data access layer (`src/data/sqlite.py`), where a global write lock serializes all database writes, a hardcoded connection pool of 1 prevents concurrent reads, and batch operations are implemented as sequential single-row inserts. The in-memory cache uses O(n) eviction and lacks hit/miss tracking, making it impossible to measure effectiveness. The infrastructure target (Fly.io with 512MB RAM, 1 shared vCPU) is extremely constrained, yet no resource budgeting or backpressure mechanisms exist.

The codebase has a well-structured async foundation using aiohttp and aiosqlite, but several components undermine concurrency through synchronous file I/O, hardcoded sleep delays, and sequential processing loops. The PostgreSQL backend is entirely unimplemented (every method raises `NotImplementedError`), leaving SQLite as the only viable database -- a significant scalability ceiling.

**Key risk areas:**
- Database write serialization will become the primary bottleneck beyond ~50 concurrent users
- Memory cache has no distributed option (Redis backend unimplemented despite Redis being deployed)
- Message batch ingestion is O(n) individual INSERTs instead of bulk operations
- Health checks make paid API calls to Claude, adding latency and cost
- Archive scanning uses synchronous file I/O in an async context
- At peak load (3 concurrent summarizations), memory usage could reach 78% of the 512MB limit

**Overall Performance Score: 4.2 / 10**

---

## Performance Hotspot Table

| # | File:Line | Component | Severity | Issue | Est. Impact |
|---|-----------|-----------|----------|-------|-------------|
| 1 | `src/data/sqlite.py:95-117` | Global write lock | **CRITICAL** | `_global_write_lock` serializes ALL writes across all connections; pool_size hardcoded to 1 | All write throughput limited to 1 concurrent op; reads also serialize |
| 2 | `src/data/sqlite.py:2070-2099` | `store_batch()` | **CRITICAL** | Messages inserted one-by-one in loop instead of batch INSERT via `executemany()` | 10-100x slower than bulk insert for large batches |
| 3 | `src/archive/backfill.py:306-336` | Sequential backfill | **CRITICAL** | Sequential date processing with fixed 0.5s sleep; no parallelism despite semaphore existing | 365-day backfill takes minimum 182.5s of sleep alone |
| 4 | `src/data/sqlite.py:1280-1340` | `find_by_guild()` | **HIGH** | `json_extract()` and `json_array_length()` in WHERE clauses bypasses all indexes | Full table scan on every filtered query |
| 5 | `src/data/sqlite.py:1374-1379` | Tag filtering | **HIGH** | Tags filtered in Python after fetching ALL rows from SQL with no LIMIT | Unbounded memory consumption; 100K summaries = 200MB |
| 6 | `src/summarization/cache.py:71-72` | `MemoryCache.set()` | **HIGH** | O(n) eviction via `min()` over all keys when cache is full | Cache set degrades linearly with cache size |
| 7 | `src/summarization/cache.py:212` | `invalidate_guild()` | **HIGH** | Calls `self.backend.clear()` -- clears ALL cache entries for any guild invalidation | Single guild change nukes entire cache |
| 8 | `src/webhook_service/server.py` | Health check endpoint | **HIGH** | Calls `summarization_engine.health_check()` which invokes Claude API with real tokens | Health probes incur API cost ($4-8/mo) and 1-3s latency |
| 9 | `src/permissions/cache.py:91,110,124` | Lock contention | **HIGH** | Every cache get/set/delete acquires asyncio.Lock even for read-only operations | Serializes all permission checks under load |
| 10 | `src/message_processing/fetcher.py:79-87` | Rate limit delay | **MEDIUM** | Fixed 0.1s sleep per message (not per API call) | 1000 messages = 100s of pure sleep |
| 11 | `src/archive/scanner.py:327` | Sync file I/O | **MEDIUM** | Synchronous `open()` in async context blocks event loop | All async operations stall during file reads |
| 12 | `src/archive/scanner.py:264-321` | Sync filesystem scan | **MEDIUM** | Synchronous `glob("**/*.meta.json")` with nested loops | Blocks event loop for entire scan duration |
| 13 | `src/archive/scanner.py:382-422` | Double scan | **MEDIUM** | `get_backfill_candidates()` re-scans data already scanned by `analyze_backfill()` | Redundant filesystem traversal |
| 14 | `src/archive/locking.py:255` | Lock cleanup scan | **MEDIUM** | `glob("**/*.meta.json")` scans entire archive tree | O(files) filesystem scan on cleanup |
| 15 | `src/summarization/claude_client.py:176` | HTTP client churn | **MEDIUM** | Creates new httpx client per `get_available_models()` call | Connection setup overhead on every call |
| 16 | `src/summarization/claude_client.py:506-511` | Health check API call | **MEDIUM** | Makes actual API call with `max_tokens=5` for health check | Wastes API quota; adds latency |
| 17 | `src/message_processing/processor.py:113-126` | Sequential processing | **MEDIUM** | Messages processed one-by-one in loop; no batching | No parallelism for content extraction |
| 18 | `src/scheduling/scheduler.py:732-744` | Sequential persistence | **MEDIUM** | `_persist_all_tasks()` saves each task individually | N tasks = N serialized DB writes |
| 19 | `src/data/sqlite.py:173-216` | Write retry masking | **MEDIUM** | Exponential backoff up to 15.5s masks real contention | Slow writes appear successful but add latency |
| 20 | `src/services/summary_push.py:142-149` | Sequential push | **MEDIUM** | Channel pushes done sequentially in loop | One slow channel delays all others |
| 21 | `src/summarization/cache.py:111-125` | No hit tracking | **MEDIUM** | `hit_ratio: "N/A"` -- no observability into cache performance | Cannot validate caching effectiveness |
| 22 | `src/data/postgresql.py` (entire file) | PostgreSQL stub | **MEDIUM** | Every method raises `NotImplementedError` | No path to horizontal DB scaling |
| 23 | `src/archive/backfill.py:336` | Fixed delay | **LOW** | 0.5s sleep between generations regardless of rate state | Unnecessary latency accumulation |
| 24 | `src/summarization/optimization.py:261` | Import in function | **LOW** | `import hashlib` inside function body | Minor per-call import overhead |
| 25 | `src/message_processing/processor.py:126` | Print logging | **LOW** | Uses `print()` instead of logger | No structured logging; lost in production |
| 26 | `src/summarization/engine.py:402-403` | Duplicate scans | **LOW** | `min()`/`max()` over timestamps called separately (2x O(n)) | Could be single pass |
| 27 | `src/config/settings.py` | JWT default | **LOW** | `jwt_secret = "change-this-in-production"` hardcoded | Security risk if not overridden |

---

## 1. Database Query Analysis

### 1.1 Global Write Lock Serialization (CRITICAL)

**File:** `src/data/sqlite.py:95-117`

The SQLite implementation uses a single `asyncio.Lock` (`_global_write_lock`) that serializes ALL write operations across every repository and every connection. Combined with `pool_size=1`, even read operations cannot execute concurrently:

```python
# Line 97: Module-level write lock shared across ALL SQLiteConnection instances
_global_write_lock: Optional[asyncio.Lock] = None

# Line 116-117
class SQLiteConnection(DatabaseConnection):
    def __init__(self, db_path: str, pool_size: int = 1):
```

**Impact:** When a scheduled summary task writes results while a backfill job writes and a dashboard user saves config, ALL operations serialize through one lock and one connection. Under concurrent load, write operations queue up with exponential backoff retries (0.5s to 8s per retry, up to 15.5s total).

The `DatabaseConfig.pool_size=10` default in `src/config/settings.py` is misleading since the SQLite adapter ignores it.

**Recommendation:**
- Use WAL mode (verify enabled) with separate read pool (3-5 connections) and 1 dedicated write connection
- Replace global lock with write-connection queue pattern
- Consider write-ahead batching for high-throughput paths

### 1.2 Batch Insert Anti-Pattern (CRITICAL)

**File:** `src/data/sqlite.py:2070-2099`

`store_batch()` inserts messages one-by-one in a loop. Each insert acquires the global write lock, executes, and releases. For a batch of 1000 messages, this means 1000 lock acquire/release cycles instead of 1.

**Impact estimate:**

| Batch Size | Individual INSERT | executemany() | Speedup |
|-----------|------------------|---------------|---------|
| 100 | ~3s | ~0.1s | 30x |
| 1,000 | ~30s | ~0.5s | 60x |
| 10,000 | ~300s (5 min) | ~2s | 150x |

`BotConfig.max_message_batch = 10000` (in settings.py) allows batches this large.

**Recommendation:** Use `executemany()` with a single lock acquisition, wrapping the entire batch in one transaction.

### 1.3 JSON Query Filtering (HIGH)

**File:** `src/data/sqlite.py:1280-1340`

The `find_by_guild()` method applies filters using `json_extract()` and `json_array_length(json_extract(...))` in WHERE clauses. With 30+ optional filter parameters, these functions are evaluated per-row and cannot use B-tree indexes.

**Impact estimate:** At 100K summaries, filtered queries take 500ms-2s. At 1M summaries, expect 5-20s query times.

### 1.4 In-Memory Tag Filtering (HIGH)

**File:** `src/data/sqlite.py:1374-1379`

Tags are filtered in Python after fetching all rows from SQL:

```python
summaries = [s for s in summaries if any(tag in s.tags for tag in tags)]
```

With no LIMIT clause on the initial query, the entire summaries table loads into memory before discarding most results.

**Impact:** On 512MB RAM with 100K summaries averaging 2KB each, a single tag-filtered query could consume 200MB -- nearly half of available RAM.

**Recommendation:** Create a `summary_tags` junction table with proper indexes, or at minimum add LIMIT to the initial query.

### 1.5 FTS Index Update Overhead (MEDIUM)

Every summary save triggers two FTS operations: DELETE followed by INSERT. Combined with the global write lock, this doubles the write cost for every summary operation.

**Recommendation:** Batch FTS updates using periodic rebuild rather than per-operation updates.

### 1.6 Index Coverage Assessment

**Files:** `src/data/migrations/001_initial_schema.sql`, `016_summary_navigation_search.sql`

**Positive findings:**
- Composite index on `(guild_id, channel_id)` for summaries (good)
- Composite index on time ranges (good)
- Partial index on active tasks: `WHERE is_active = 1` (excellent)
- FTS5 with porter stemmer and unicode61 tokenizer (appropriate)
- Navigation index on `(guild_id, source, created_at)` (good)

**Missing indexes:**
- No composite index on `(guild_id, status)` for filtered status queries
- No index on `(guild_id, error_type, created_at)` for error dashboard
- No composite index on `(guild_id, archive_period)` for force-regenerate deduplication
- No covering indexes for common SELECT patterns

### 1.7 SQL Injection Vector (INFORMATIONAL)

**File:** `src/data/sqlite.py:297-334`

The `find_summaries` method uses f-string interpolation for ORDER BY:

```python
query = f"... ORDER BY {criteria.order_by} {criteria.order_direction} ..."
```

While parameters are used for WHERE clause values, `order_by` and `order_direction` could be injection vectors if not validated upstream.

---

## 2. Caching Assessment

### 2.1 Three Independent Cache Implementations

| Cache | File | Max Size | TTL | Hit Tracking | Eviction |
|-------|------|----------|-----|--------------|----------|
| `MemoryCache` (summaries) | `src/summarization/cache.py` | 1,000 | 3,600s | None (`"N/A"`) | O(n) min scan |
| `PermissionCache` | `src/permissions/cache.py` | 10,000 | 3,600s | Yes (hits/misses) | O(n) min scan |
| `PromptCacheManager` | `src/prompts/cache.py` | 1,000 | 300s | No counters | O(n) min scan |

No unified cache abstraction exists. Each implements its own eviction, TTL, and stats independently.

### 2.2 O(n) Cache Eviction (HIGH)

**File:** `src/summarization/cache.py:71-72`

When the cache reaches `max_size`, eviction uses:

```python
oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k]["created_at"])
```

This is O(n) on every set operation when the cache is full. Both `MemoryCache` and `PromptCacheManager` share this anti-pattern.

**Recommendation:** Replace with `collections.OrderedDict` for O(1) LRU eviction.

### 2.3 Guild Invalidation Clears Entire Cache (HIGH)

**File:** `src/summarization/cache.py:212`

`invalidate_guild()` calls `self.backend.clear()` with no pattern argument, wiping ALL cached summaries across ALL guilds. A single event in any guild destroys the cache for every guild.

**Recommendation:** Add guild_id to cache key structure and implement prefix-based clearing.

### 2.4 No Hit/Miss Tracking (MEDIUM)

**File:** `src/summarization/cache.py:124`

The summary cache -- the most important cache -- reports `"hit_ratio": "N/A"`. Without tracking, it is impossible to assess whether caching is effective or properly sized.

The `PermissionCache` has proper hit/miss counters, demonstrating the pattern is known but not applied consistently.

### 2.5 Redis Backend Not Implemented (MEDIUM)

**File:** `src/summarization/cache.py:319-325`

Redis is configured in `docker-compose.yml` (256MB, allkeys-lru) and `redis` is in `requirements.txt`, but the backend raises `ValueError`:

```python
raise ValueError("Redis cache backend is not yet implemented.")
```

This means: no cache persistence across restarts, no shared cache in multi-instance deployments, and 512MB RAM must hold both application state AND cache.

### 2.6 Cache Key Granularity (LOW)

**File:** `src/summarization/cache.py:247-259`

Timestamps rounded to the nearest hour for cache keys. Reasonable tradeoff, but summaries at 2:01 and 2:59 share a key despite covering different message ranges.

### 2.7 Positive Pattern: Stale-While-Revalidate

The `PromptCacheManager` (`src/prompts/cache.py:237-285`) implements stale-while-revalidate, serving stale data immediately while refreshing in background. This pattern should be adopted by the summary cache.

---

## 3. Concurrency & Async Analysis

### 3.1 Backfill Sequential Processing (CRITICAL)

**File:** `src/archive/backfill.py:306-336`

A 365-day backfill processes dates one-by-one with a mandatory 0.5s sleep:

```python
for target_date in job.dates:
    # ... process one date ...
    await asyncio.sleep(0.5)
```

The `RetrospectiveGenerator` (`src/archive/generator.py:197-202`) correctly initializes a semaphore (`asyncio.Semaphore(max_concurrent)`) but the `run_job` method still processes periods sequentially. The concurrency primitive exists but is never applied.

**Recommendation:** Use `asyncio.gather()` with the semaphore to process up to `max_concurrent` periods in parallel. This would reduce a 365-day backfill from ~30 minutes to ~5 minutes.

### 3.2 Permission Cache Lock Contention (HIGH)

**File:** `src/permissions/cache.py:91, 110, 124`

Every `get()`, `set()`, and `delete()` acquires the same `asyncio.Lock`. During multi-channel scheduled tasks checking permissions for 20 channels, each check serializes.

**Recommendation:** Remove the lock for reads (Python dicts are thread-safe for single-threaded asyncio reads), or use a reader-writer pattern.

### 3.3 Message Fetcher Per-Message Sleep (MEDIUM)

**File:** `src/message_processing/fetcher.py:79-87`

The 0.1s rate limit delay is applied per-message, not per-API-call. Discord.py's `history()` fetches ~100 messages per API call. Sleeping 0.1s per message means:

| Messages | Sleep Time | Should Be |
|----------|-----------|-----------|
| 100 | 10s | 0.1s (1 API call) |
| 1,000 | 100s | 1s (10 API calls) |
| 10,000 | 1,000s (16.7 min) | 10s (100 API calls) |

### 3.4 Synchronous File I/O in Async Context (MEDIUM)

**Files:** `src/archive/scanner.py:264-327`, `src/archive/locking.py:255`

`_parse_meta_file()` uses synchronous `open()`, `scan_all_sources()` uses synchronous `glob()` and nested loops, and `cleanup_expired_locks()` uses `glob("**/*.meta.json")`. All block the event loop.

**Impact:** During archive scans, ALL other async operations (Discord messages, webhooks, scheduled tasks) stall.

**Recommendation:** Use `aiofiles` or `asyncio.to_thread()` for all file I/O.

### 3.5 Sequential Summary Push (MEDIUM)

**File:** `src/services/summary_push.py:142-149`

Pushing summaries to multiple Discord channels is done sequentially. If one channel is slow or rate-limited, all subsequent channels wait.

**Recommendation:** Use `asyncio.gather()` with `return_exceptions=True`.

### 3.6 Hardcoded Concurrency Limits (MEDIUM)

**Files:** `src/summarization/engine.py:639`, `src/archive/generator.py`

Multiple hardcoded semaphore limits (`asyncio.Semaphore(3)`) are not configurable and do not adapt to available resources. On 512MB/1vCPU, 3 concurrent summarizations could exhaust memory.

### 3.7 Sequential Task Persistence (MEDIUM)

**File:** `src/scheduling/scheduler.py:732-744`

`_persist_all_tasks()` saves each task individually through the global write lock. 50 tasks = 50 serialized DB writes.

---

## 4. Memory Management

### 4.1 Unbounded In-Memory Tag Filtering (HIGH)

**File:** `src/data/sqlite.py:1374-1379`

Already covered in database section. With no LIMIT clause, fetches entire table into memory before Python-side filtering. On 512MB RAM, this is a crash risk.

### 4.2 Full Message List Accumulation

**File:** `src/message_processing/fetcher.py:79-87`

All messages for a time range accumulate in a list. For 10,000+ messages in a busy channel, Discord.py `Message` objects include embeds, attachments, and reaction metadata.

### 4.3 Source Content Duplication

**File:** `src/summarization/engine.py:597, 809-837`

`_format_source_content()` formats ALL source messages into a single string stored alongside the summary. For large channels, this could be megabytes per summary.

### 4.4 In-Memory Job Storage

**Files:** `src/archive/backfill.py:155`, `src/archive/generator.py:201`

All backfill and retrospective jobs stored in dictionaries in memory. A 3-year job (1095 dates) stays in memory indefinitely until process restart.

### 4.5 Cache Memory Without Byte Limits

**File:** `src/summarization/cache.py:47`

`MemoryCache` has `max_size=1000` entry limit but no byte-size cap. 1000 summaries at 5KB average = 5MB (manageable), but size per entry is unpredictable.

**Recommendation:** Add `max_bytes` limit for the 512MB target environment.

### 4.6 Memory Budget Assessment (512MB Target)

| Component | Est. Memory | Notes |
|-----------|------------|-------|
| Python runtime | 40-60MB | Base interpreter + loaded modules |
| Discord.py + gateway | 30-50MB | Cached guilds, channels, members |
| SQLite connections | 10-20MB | Page cache, statement cache |
| In-memory caches (3x) | 1-15MB | Depends on cache fill |
| Message batches (active) | 5-50MB | Per concurrent summarization |
| FastAPI/uvicorn | 20-40MB | ASGI server + middleware |
| APScheduler | 5-10MB | Job store + execution context |
| **Total at rest** | **111-245MB** | **22-48% of 512MB** |
| **Peak (3 concurrent summaries)** | **260-400MB** | **51-78% -- OOM risk** |

---

## 5. API Call Efficiency

### 5.1 Resilient Engine Retry Strategy (POSITIVE)

**File:** `src/summarization/engine.py:46-321`

The `ResilientSummarizationEngine` implements a well-designed retry strategy:
- Model escalation chain (Haiku -> Sonnet -> Opus)
- Token increase on truncation
- JSON hint injection on parse failures
- Cost cap ($0.50 default) and attempt limit (7 default)
- Proper exponential backoff for rate limits

This is one of the strongest performance patterns in the codebase.

### 5.2 Health Check Makes Paid API Calls (HIGH)

**Files:** `src/webhook_service/server.py`, `src/summarization/claude_client.py:506-511`

The webhook health endpoint calls the Claude API with `max_tokens=5` and triggers the full fallback chain across 6 models. With health probes every 10-30 seconds:

- **Cost:** ~$0.0001 per check x 3-6/min = $4-8/month
- **Latency:** 1-3 seconds per probe
- **Availability:** If Claude API is slow, health checks fail, potentially triggering container restarts

**Recommendation:** Health checks should verify local state only. Implement a separate deep-health endpoint.

### 5.3 HTTP Client Churn (MEDIUM)

**File:** `src/summarization/claude_client.py:176`

`get_available_models()` creates a new `httpx.AsyncClient` per call instead of reusing the existing client.

### 5.4 Blunt Rate Limiting (MEDIUM)

**File:** `src/summarization/claude_client.py:139`

The 0.1s minimum between requests limits throughput to 10 req/s regardless of actual API rate limits.

**Recommendation:** Use adaptive rate limiting with response headers (`x-ratelimit-remaining`, `retry-after`) and token bucket algorithm.

### 5.5 Incomplete Cost Table (LOW)

The model cost estimation table only covers older Claude models. Missing entries for Claude 3.5 and later mean cost tracking reports $0 for newer models.

---

## 6. I/O Bottleneck Analysis

### 6.1 Per-Message Rate Limiting (MEDIUM)

**File:** `src/message_processing/fetcher.py:84-85`

The 0.1s per-message delay is the dominant cost in message fetching. 10,000 messages = 16.7 minutes of pure sleep.

### 6.2 Synchronous Archive Scanning (MEDIUM)

**File:** `src/archive/scanner.py:264-321`

Synchronous filesystem traversal with nested loops and `glob("**/*.meta.json")` blocks the event loop.

### 6.3 Feed Generation on Every Request (MEDIUM)

**File:** `src/webhook_service/server.py`

RSS/Atom feed serving performs a database query and feed generation on every HTTP request with no server-side caching.

**Recommendation:** Cache generated feeds with 60-300 second TTL.

### 6.4 Sequential Task Persistence (MEDIUM)

Already covered. N tasks = N serialized DB writes through the global lock.

---

## 7. Scalability Assessment

### 7.1 Vertical Scaling Ceiling

| Resource | Current | Maximum Practical | Bottleneck |
|----------|---------|-------------------|------------|
| DB Connections | 1 (hardcoded) | 1 (SQLite write lock) | Global write lock |
| RAM | 512MB | 512MB (Fly.io plan) | In-memory cache + message batches |
| CPU | 1 shared vCPU | 1 (single region) | Summarization + message processing |
| Storage | 1GB volume | 1GB (Fly.io volume) | SQLite DB + archive files |
| Concurrency | ~10 users | ~50 users | DB serialization + API rate limits |

### 7.2 Horizontal Scaling Blockers

| Blocker | File | Impact |
|---------|------|--------|
| SQLite single-writer | `src/data/sqlite.py` | Cannot share DB across instances |
| In-memory caches (3x) | Multiple cache files | No shared cache state |
| File-based locking | `src/archive/locking.py` | Single-machine only |
| APScheduler in-process | `src/scheduling/scheduler.py` | Jobs run in single process |
| PostgreSQL not implemented | `src/data/postgresql.py` | No multi-instance DB option |
| In-memory job tracking | `src/archive/backfill.py:155` | Jobs lost on crash |

### 7.3 Growth Projections

| Metric | 10 guilds | 100 guilds | 1000 guilds |
|--------|-----------|------------|-------------|
| Summaries/day | ~100 | ~1,000 | ~10,000 |
| DB size/month | ~50MB | ~500MB | 5GB (exceeds volume) |
| API cost/month | ~$15 | ~$150 | ~$1,500 |
| Peak write ops/sec | ~2 | ~20 (lock contention) | ~200 (unusable) |
| Memory pressure | Low | Moderate | Critical (OOM) |

### 7.4 Single Points of Failure

1. **SQLite database file** -- single copy on 1GB volume, no replication
2. **Claude API** -- no fallback provider (OpenRouter proxy helps but single-provider)
3. **Single region deployment** (yyz) -- no geographic redundancy
4. **In-process scheduler** -- process crash stops all scheduled tasks
5. **In-memory caches** -- process restart loses all cached data

---

## 8. Resource Utilization

### 8.1 CPU Budget (1 shared vCPU)

| Component | Est. CPU Usage | Notes |
|-----------|---------------|-------|
| Discord.py event loop | 5-15% idle, 30%+ active | Message events, command handling |
| Summarization (Claude API) | <5% (I/O bound) | Mostly waiting on API responses |
| SQLite operations | 10-30% under load | JSON parsing, FTS updates |
| Message processing | 5-20% | Content extraction, cleaning |
| FastAPI/webhook | 2-10% | HTTP request handling |
| APScheduler | 1-5% | Cron tick + job dispatch |
| **Total peak** | **~80-110%** | **CPU-bound risk under load** |

### 8.2 Disk I/O

- SQLite WAL mode generates write-ahead log files that can grow to 10-100MB during heavy write periods
- Archive file generation writes HTML/JSON to disk synchronously
- No I/O scheduling or prioritization
- 1GB volume could fill in ~2 months at 100 guilds

---

## 9. Message Processing Pipeline

### 9.1 Pipeline Flow Analysis

```
Discord Message -> Fetcher (0.1s/msg delay) -> Processor (sequential) -> Optimizer -> Engine -> Claude API -> Cache -> DB -> Response
```

**Critical path latency breakdown (100 messages):**

| Stage | Latency | Bottleneck |
|-------|---------|------------|
| Message fetch | 10s (100 x 0.1s) | Fixed per-message rate delay |
| Processing | 0.5-1s | Sequential loop |
| Optimization | 0.1-0.5s | Dedup + scoring |
| Claude API call | 3-15s | Model inference |
| Cache write | <10ms | Memory cache |
| DB write | 50-200ms | Global write lock |
| **Total** | **~14-27s** | **Fetch delay dominates** |

### 9.2 Pipeline Weaknesses

1. **No backpressure:** Summarization requests queue unboundedly in memory if they arrive faster than processing capacity
2. **No priority queue:** Scheduled background summaries block interactive user requests
3. **No progress reporting:** Long-running summarizations provide no intermediate status
4. **No circuit breaker:** If Claude API fails repeatedly, requests continue to queue and retry (cost caps exist but no request rejection)
5. **Sequential message processing:** `processor.py:113-126` processes messages one-by-one with no batching
6. **Error logging via print:** `processor.py:126` uses `print()` instead of structured logger

---

## 10. Infrastructure Review

### 10.1 Fly.io Configuration

**File:** `fly.toml`

| Setting | Value | Assessment |
|---------|-------|------------|
| RAM | 512MB | Insufficient for 3+ concurrent summarizations (78% at peak) |
| CPU | 1 shared vCPU | Adequate for low load, insufficient for spikes |
| Volume | 1GB | Will fill in ~2 months at 100 guilds |
| Regions | 1 (yyz) | No geographic redundancy |
| Hard conn limit | 100 | Reasonable for single instance |
| Soft conn limit | 80 | Good backpressure threshold |

### 10.2 Docker Configuration

**Files:** `Dockerfile`, `docker-compose.yml`

**Positive:**
- Multi-stage build reduces image size
- Non-root user for security
- Python 3.11-slim base (appropriate)

**Concerns:**
- No resource limits on bot container in docker-compose
- Redis configured (256MB, allkeys-lru) but unused by application code
- No health check defined in Dockerfile

### 10.3 Dependency Concerns

**File:** `requirements.txt`

| Dependency | Concern |
|------------|---------|
| APScheduler 3.x | Version 4.x has native async support; 3.x uses thread-based execution |
| aiosqlite | Thin async wrapper; still single-writer limited |
| redis (package) | Installed but backend not implemented |
| No asyncpg | PostgreSQL support impossible without this |

### 10.4 Cold Start Performance

Startup loads all persisted tasks from DB (`scheduler.py:686-720`) and schedules each via APScheduler. This is O(n) in active tasks. Each task individually scheduled via `schedule_task()` creates a write-read-write cycle.

---

## Optimization Recommendations (Prioritized by Impact)

### Priority 1: CRITICAL -- Implement before scaling beyond 20 guilds

| # | Recommendation | Files Affected | Effort | Impact |
|---|---------------|----------------|--------|--------|
| 1.1 | **Implement batch INSERT with `executemany()`** in `store_batch()` | `src/data/sqlite.py:2070-2099` | Low (2-4h) | 10-100x faster batch ingestion |
| 1.2 | **Separate read pool from write lock** -- allow 3-5 concurrent read connections | `src/data/sqlite.py:95-117` | Medium (1-2d) | Concurrent reads; unblocks dashboard + queries |
| 1.3 | **Parallelize backfill** using existing semaphore with `asyncio.gather()` | `src/archive/backfill.py:306-336`, `src/archive/generator.py:354` | Low (4-8h) | 3-10x faster backfill; semaphore already exists |
| 1.4 | **Move tag filtering to SQL** using junction table | `src/data/sqlite.py:1374-1379`, migrations | Medium (1-2d) | Eliminates unbounded memory load |
| 1.5 | **Fix health check** to not call Claude API | `src/webhook_service/server.py`, `src/summarization/claude_client.py:506-511` | Low (1-2h) | Saves $4-8/month, eliminates probe latency |

### Priority 2: HIGH -- Implement before scaling beyond 50 guilds

| # | Recommendation | Files Affected | Effort | Impact |
|---|---------------|----------------|--------|--------|
| 2.1 | **Replace O(n) cache eviction** with `OrderedDict` LRU (all 3 caches) | `src/summarization/cache.py:71-72`, `src/prompts/cache.py:223-235` | Low (2-4h) | O(1) eviction instead of O(n) |
| 2.2 | **Fix guild cache invalidation** to use prefix matching | `src/summarization/cache.py:212` | Low (2-4h) | Cache survives per-guild changes |
| 2.3 | **Fix message fetcher rate limiting** -- sleep per-batch, not per-message | `src/message_processing/fetcher.py:79-87` | Low (2-4h) | 100x faster message fetching |
| 2.4 | **Add cache hit-rate tracking** to summary cache | `src/summarization/cache.py:111-125` | Low (2-4h) | Enables cache tuning and validation |
| 2.5 | **Implement Redis cache backend** | `src/summarization/cache.py:319-325` | Medium (2-3d) | Persistent cache, multi-instance ready |
| 2.6 | **Denormalize JSON-filtered columns** into indexed columns | `src/data/sqlite.py:1280-1340`, migrations | Medium (2-3d) | Index-backed filtering |

### Priority 3: MEDIUM -- Implement before scaling beyond 100 guilds

| # | Recommendation | Files Affected | Effort | Impact |
|---|---------------|----------------|--------|--------|
| 3.1 | **Make async file I/O** in archive scanner and lock cleanup | `src/archive/scanner.py:264-327`, `src/archive/locking.py:255` | Low (4-8h) | Unblocks event loop during scans |
| 3.2 | **Implement PostgreSQL backend** | `src/data/postgresql.py` | High (1-2w) | Horizontal scaling path |
| 3.3 | **Batch task persistence** | `src/scheduling/scheduler.py:732-744` | Low (4-8h) | Reduced write lock contention |
| 3.4 | **Cache RSS/Atom feeds server-side** | `src/webhook_service/server.py` | Low (2-4h) | Eliminates redundant DB queries |
| 3.5 | **Implement backpressure** for summarization queue | `src/summarization/engine.py` | Medium (1-2d) | Prevents OOM under load |
| 3.6 | **Parallelize summary push** to Discord channels | `src/services/summary_push.py:142-149` | Low (2-4h) | One slow channel no longer delays all |
| 3.7 | **Add missing database indexes** | Migration SQL | Low (2-4h) | Faster error dashboard and dedup checks |
| 3.8 | **Cache model availability list** for 5 minutes | `src/summarization/claude_client.py:162-193` | Low (1-2h) | Eliminates redundant HTTP calls |
| 3.9 | **Remove permission cache lock for reads** | `src/permissions/cache.py:91` | Low (1-2h) | Reduces serialization under load |

### Priority 4: LOW -- Quality improvements

| # | Recommendation | Files Affected | Effort | Impact |
|---|---------------|----------------|--------|--------|
| 4.1 | **Configurable concurrency limits** tied to resource availability | `src/summarization/engine.py:639`, `src/archive/generator.py` | Low (2-4h) | Resource-aware execution |
| 4.2 | **Unified cache abstraction** across all 3 cache implementations | Multiple files | Medium (1-2d) | Consistent behavior and observability |
| 4.3 | **Streaming message processing** instead of list accumulation | `src/message_processing/fetcher.py` | Medium (1-2d) | Reduced peak memory |
| 4.4 | **Combine min/max timestamp** into single pass | `src/summarization/engine.py:402-403` | Trivial (30m) | Minor efficiency gain |
| 4.5 | **Move hashlib import** to module level | `src/summarization/optimization.py:261` | Trivial (5m) | Eliminates per-call import |
| 4.6 | **Replace print() with logger** | `src/message_processing/processor.py:126` | Trivial (30m) | Proper structured logging |
| 4.7 | **Reuse httpx client** for model listing | `src/summarization/claude_client.py:176` | Trivial (30m) | Eliminates connection churn |
| 4.8 | **Add byte-size limit** to memory cache | `src/summarization/cache.py` | Low (2-4h) | Prevents memory pressure |

---

## Performance Score

| Category | Score (1-10) | Weight | Weighted |
|----------|-------------|--------|----------|
| Database Performance | 3.0 | 25% | 0.75 |
| API Call Efficiency | 5.0 | 15% | 0.75 |
| Caching Strategy | 3.0 | 15% | 0.45 |
| Async/Concurrency | 4.5 | 15% | 0.68 |
| Memory Management | 4.0 | 10% | 0.40 |
| I/O Efficiency | 4.0 | 5% | 0.20 |
| Scalability | 3.0 | 10% | 0.30 |
| Infrastructure | 5.0 | 5% | 0.25 |
| **Overall** | | **100%** | **3.78** |

**Adjusted Score (accounting for well-structured async foundation, good index coverage, and excellent retry/escalation strategy): 4.2 / 10**

The score reflects a codebase with sound architectural intentions (async-first, repository pattern, caching layer, resilient retry) that is undermined by implementation-level performance issues (serial writes, O(n) algorithms, missing backends, synchronous I/O in async context) and heavily constrained infrastructure (512MB RAM, 1 shared vCPU, 1GB disk). The gap between architectural potential and implementation reality is the primary concern.

---

## Weighted Finding Score

| Severity | Count | Weight | Subtotal |
|----------|-------|--------|----------|
| CRITICAL | 3 | 3.0 | 9.0 |
| HIGH | 6 | 2.0 | 12.0 |
| MEDIUM | 12 | 1.0 | 12.0 |
| LOW | 5 | 0.5 | 2.5 |
| INFORMATIONAL | 1 | 0.25 | 0.25 |
| **Total** | **27** | | **35.75** |

Minimum threshold (BMAD-001): 2.0 -- **EXCEEDED** (35.75)

---

## Files Examined and Patterns Checked

### Source Files (29 files, ~11,500+ lines)

| File | Lines | Category |
|------|-------|----------|
| `src/data/sqlite.py` | 2525 | Database |
| `src/data/postgresql.py` | ~300 | Database |
| `src/data/base.py` | 1060 | Database |
| `src/data/migrations/001_initial_schema.sql` | ~150 | Database |
| `src/data/migrations/016_summary_navigation_search.sql` | ~50 | Database |
| `src/summarization/engine.py` | ~900 | Summarization |
| `src/summarization/cache.py` | 331 | Caching |
| `src/summarization/claude_client.py` | ~550 | API |
| `src/summarization/optimization.py` | 297 | Optimization |
| `src/scheduling/executor.py` | 1132 | Scheduling |
| `src/scheduling/scheduler.py` | ~750 | Scheduling |
| `src/scheduling/tasks.py` | ~100 | Scheduling |
| `src/archive/scanner.py` | ~350 | Archive |
| `src/archive/generator.py` | ~800 | Archive |
| `src/archive/backfill.py` | ~450 | Archive |
| `src/archive/locking.py` | ~320 | Archive |
| `src/webhook_service/server.py` | ~600 | Webhook |
| `src/message_processing/processor.py` | ~200 | Processing |
| `src/message_processing/fetcher.py` | ~250 | Processing |
| `src/config/settings.py` | ~300 | Config |
| `src/services/email_delivery.py` | ~200 | Services |
| `src/services/summary_push.py` | ~200 | Services |
| `src/dashboard/router.py` | ~100 | Dashboard |
| `src/discord_bot/bot.py` | ~200 | Discord |
| `src/logging/repository.py` | ~150 | Logging |
| `src/permissions/cache.py` | ~250 | Caching |
| `src/prompts/cache.py` | ~300 | Caching |
| `Dockerfile` | ~50 | Infrastructure |
| `docker-compose.yml` | ~80 | Infrastructure |
| `fly.toml` | ~50 | Infrastructure |
| `requirements.txt` | ~40 | Dependencies |

### Patterns Checked

- [x] O(n^2) or worse algorithms -- Found: O(n) eviction anti-pattern in 3 caches
- [x] N+1 query patterns -- None found (queries are well-batched except store_batch)
- [x] Missing database indexes -- Found: 3 missing composite indexes
- [x] Batch INSERT vs individual INSERT -- Found: CRITICAL anti-pattern in store_batch
- [x] Connection pooling -- Found: pool_size=1 bottleneck with global write lock
- [x] Memory accumulation -- Found: in-memory job storage, full message lists, unbounded tag filtering
- [x] Unbounded collections -- Found: `_jobs` dict grows without cleanup
- [x] Sync I/O blocking async -- Found: filesystem glob and file reads in scanner
- [x] Cache effectiveness -- Found: no hit-rate tracking, guild invalidation bug, O(n) eviction
- [x] Rate limiting -- Found: per-message instead of per-batch
- [x] Retry storms -- None found (cost caps and attempt limits well-designed)
- [x] Resource leaks -- Minor: transaction connection return path
- [x] Thread safety -- Good: asyncio Lock usage, `_executing_tasks` guard
- [x] Deadlock potential -- Low risk: single lock pattern, no lock nesting
- [x] Cold start cost -- Moderate: sequential task loading on startup
- [x] Memory budget -- Assessed: 51-78% at peak on 512MB target
- [x] Disk budget -- Assessed: 1GB volume fills in ~2 months at 100 guilds
- [x] API cost leaks -- Found: health check API calls at $4-8/month

---

## Conclusion

SummaryBot NG has a solid async architectural foundation and an excellent API retry/escalation strategy. The primary performance risks are concentrated in three areas:

1. **Database layer**: The global write lock, individual batch inserts, and JSON-based filtering create a scaling ceiling around 50 guilds. Implementing `executemany()`, separating read/write pools, and denormalizing JSON fields would provide the most immediate throughput improvement.

2. **Caching layer**: Three independent O(n)-eviction caches with no distributed option and a guild invalidation bug that clears the entire cache. Implementing LRU eviction, fixing guild invalidation, and completing the Redis backend would enable multi-instance deployment.

3. **Concurrency gaps**: Sequential processing patterns in backfill, message fetching, summary push, and task persistence underutilize the async runtime. Applying `asyncio.gather()` with existing semaphores and fixing the per-message rate delay would yield 3-100x improvements in these paths.

For a single-instance bot serving 1-20 guilds, the current architecture is viable with the Priority 1 fixes. Scaling beyond 50 guilds requires Priority 2 fixes. Scaling beyond 100 guilds requires the PostgreSQL implementation and distributed caching (Priority 3).

---

*Report generated by QE Performance Reviewer V3 -- chaos-resilience domain (ADR-011)*
*Revision 2: Deep analysis with 27 findings across 10 categories*
