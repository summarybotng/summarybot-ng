# Data Module - Summary Bot NG

## Overview

The data module provides a comprehensive data access layer for Summary Bot NG with support for multiple database backends. It implements the Repository pattern with abstract interfaces and concrete implementations for SQLite and PostgreSQL (stub).

## Features

- **Repository Pattern**: Clean separation of data access logic from business logic
- **Multiple Backends**: SQLite (fully implemented), PostgreSQL (stub for future expansion)
- **Async Operations**: All database operations use async/await for non-blocking I/O
- **Connection Pooling**: Built-in connection pooling for optimal performance
- **Transaction Support**: Proper transaction handling with commit/rollback
- **Database Migrations**: Automated schema migrations with version tracking
- **Type Safety**: Full type hints and dataclass-based models
- **Comprehensive Indexing**: Optimized database indexes for common queries

## Architecture

```
data/
├── __init__.py              # Public API exports
├── base.py                  # Abstract repository interfaces
├── sqlite.py                # SQLite implementation
├── postgresql.py            # PostgreSQL stub
├── migrations/              # Database migrations
│   ├── __init__.py
│   └── 001_initial_schema.sql
└── repositories/            # Repository factory
    └── __init__.py
```

## Core Components

### Abstract Interfaces (base.py)

#### SummaryRepository
Manages summary data persistence:
- `save_summary(summary)` - Save or update a summary
- `get_summary(summary_id)` - Retrieve summary by ID
- `find_summaries(criteria)` - Search summaries with filters
- `delete_summary(summary_id)` - Delete a summary
- `count_summaries(criteria)` - Count matching summaries
- `get_summaries_by_channel(channel_id, limit)` - Get recent channel summaries

#### ConfigRepository
Manages guild configuration data:
- `save_guild_config(config)` - Save or update guild config
- `get_guild_config(guild_id)` - Get guild configuration
- `delete_guild_config(guild_id)` - Delete guild config
- `get_all_guild_configs()` - Get all guild configurations

#### TaskRepository
Manages scheduled tasks and execution results:
- `save_task(task)` - Save or update a scheduled task
- `get_task(task_id)` - Get task by ID
- `get_tasks_by_guild(guild_id)` - Get all tasks for a guild
- `get_active_tasks()` - Get all active tasks
- `delete_task(task_id)` - Delete a task
- `save_task_result(result)` - Save task execution result
- `get_task_results(task_id, limit)` - Get task execution history

#### DatabaseConnection
Abstract database connection interface:
- `connect()` - Establish connection
- `disconnect()` - Close connection
- `execute(query, params)` - Execute query
- `fetch_one(query, params)` - Fetch single row
- `fetch_all(query, params)` - Fetch multiple rows
- `begin_transaction()` - Start transaction

### SQLite Implementation (sqlite.py)

#### SQLiteConnection
- Connection pooling with configurable pool size (default: 5)
- WAL mode for better concurrency
- Foreign key support enabled
- Row factory for dict-like row access
- Context manager support for safe connection handling

#### Repository Implementations
- `SQLiteSummaryRepository` - Full summary CRUD operations
- `SQLiteConfigRepository` - Guild configuration management
- `SQLiteTaskRepository` - Scheduled task management with execution tracking

### Repository Factory (repositories/__init__.py)

Provides a factory pattern for creating repository instances:

```python
from src.data import initialize_repositories, get_summary_repository

# Initialize repositories
initialize_repositories(backend="sqlite", db_path="data/summarybot.db", pool_size=5)

# Get repository instances
summary_repo = await get_summary_repository()
config_repo = await get_config_repository()
task_repo = await get_task_repository()
```

### Database Migrations (migrations/)

Automated database migration system:
- Version-based migrations (001_*.sql, 002_*.sql, etc.)
- Automatic schema version tracking
- Support for rollback and reset operations
- Migration history logging

## Usage Examples

### Basic Setup

```python
from src.data import initialize_repositories, run_migrations

# Run migrations first
await run_migrations("data/summarybot.db")

# Initialize repositories
initialize_repositories(backend="sqlite", db_path="data/summarybot.db")
```

### Working with Summaries

```python
from src.data import get_summary_repository, SearchCriteria
from src.models.summary import SummaryResult, SummarizationContext

# Get repository
repo = await get_summary_repository()

# Create and save a summary
context = SummarizationContext(
    channel_name="general",
    guild_name="My Server",
    total_participants=5,
    time_span_hours=2.5
)

summary = SummaryResult(
    channel_id="123456789",
    guild_id="987654321",
    message_count=100,
    key_points=["Point 1", "Point 2"],
    summary_text="Detailed summary here...",
    context=context
)

summary_id = await repo.save_summary(summary)

# Retrieve summary
retrieved = await repo.get_summary(summary_id)

# Search summaries
criteria = SearchCriteria(
    guild_id="987654321",
    channel_id="123456789",
    limit=10
)
results = await repo.find_summaries(criteria)

# Get recent summaries for a channel
recent = await repo.get_summaries_by_channel("123456789", limit=5)

# Delete summary
await repo.delete_summary(summary_id)
```

### Working with Configurations

```python
from src.data import get_config_repository
from src.config.settings import GuildConfig, SummaryOptions, PermissionSettings
from src.models.summary import SummaryLength

# Get repository
repo = await get_config_repository()

# Create guild configuration
config = GuildConfig(
    guild_id="123456789",
    enabled_channels=["channel1", "channel2"],
    excluded_channels=["spam"],
    default_summary_options=SummaryOptions(
        summary_length=SummaryLength.DETAILED,
        include_bots=False
    ),
    permission_settings=PermissionSettings(
        allowed_roles=["admin", "moderator"],
        require_permissions=True
    ),
    webhook_enabled=True,
    webhook_secret="secret123"
)

# Save configuration
await repo.save_guild_config(config)

# Retrieve configuration
guild_config = await repo.get_guild_config("123456789")

# Get all configurations
all_configs = await repo.get_all_guild_configs()

# Delete configuration
await repo.delete_guild_config("123456789")
```

### Working with Scheduled Tasks

```python
from src.data import get_task_repository
from src.models.task import (
    ScheduledTask,
    TaskResult,
    Destination,
    ScheduleType,
    DestinationType,
    TaskStatus
)

# Get repository
repo = await get_task_repository()

# Create scheduled task
task = ScheduledTask(
    name="Daily Summary",
    channel_id="123456789",
    guild_id="987654321",
    schedule_type=ScheduleType.DAILY,
    schedule_time="09:00",
    destinations=[
        Destination(
            type=DestinationType.DISCORD_CHANNEL,
            target="summary-channel",
            format="embed"
        )
    ],
    created_by="user123"
)

# Calculate and set next run time
task.next_run = task.calculate_next_run()

# Save task
task_id = await repo.save_task(task)

# Get task
retrieved_task = await repo.get_task(task_id)

# Get all tasks for a guild
guild_tasks = await repo.get_tasks_by_guild("987654321")

# Get all active tasks
active_tasks = await repo.get_active_tasks()

# Save execution result
result = TaskResult(
    task_id=task_id,
    status=TaskStatus.COMPLETED
)
result.mark_completed("summary_id_123")

await repo.save_task_result(result)

# Get execution history
history = await repo.get_task_results(task_id, limit=10)

# Delete task
await repo.delete_task(task_id)
```

### Transaction Handling

```python
from src.data import get_repository_factory

factory = get_repository_factory()
connection = await factory.get_connection()

# Use transactions for atomic operations
async with await connection.begin_transaction() as tx:
    try:
        # Multiple operations here
        await repo1.save_summary(summary1)
        await repo2.save_config(config1)
        # Transaction will auto-commit on success
    except Exception as e:
        # Transaction will auto-rollback on error
        raise
```

### Advanced Search

```python
from datetime import timedelta
from src.data import SearchCriteria
from src.utils.time import utc_now_naive

# Create search criteria with time range
criteria = SearchCriteria(
    guild_id="987654321",
    channel_id="123456789",
    start_time=utc_now_naive() - timedelta(days=7),
    end_time=utc_now_naive(),
    limit=50,
    offset=0,
    order_by="created_at",
    order_direction="DESC"
)

summaries = await repo.find_summaries(criteria)
count = await repo.count_summaries(criteria)
```

## Database Schema

### Summaries Table
```sql
CREATE TABLE summaries (
    id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    message_count INTEGER NOT NULL,
    summary_text TEXT NOT NULL,
    key_points TEXT NOT NULL,        -- JSON array
    action_items TEXT NOT NULL,      -- JSON array
    technical_terms TEXT NOT NULL,   -- JSON array
    participants TEXT NOT NULL,      -- JSON array
    metadata TEXT NOT NULL,          -- JSON object
    created_at TEXT NOT NULL,
    context TEXT NOT NULL            -- JSON object
);
```

**Indexes:**
- `idx_summaries_guild_id` - Guild ID lookup
- `idx_summaries_channel_id` - Channel ID lookup
- `idx_summaries_created_at` - Time-based queries
- `idx_summaries_guild_channel` - Combined guild/channel lookup
- `idx_summaries_time_range` - Time range queries

### Guild Configs Table
```sql
CREATE TABLE guild_configs (
    guild_id TEXT PRIMARY KEY,
    enabled_channels TEXT NOT NULL,       -- JSON array
    excluded_channels TEXT NOT NULL,      -- JSON array
    default_summary_options TEXT NOT NULL, -- JSON object
    permission_settings TEXT NOT NULL,    -- JSON object
    webhook_enabled INTEGER NOT NULL DEFAULT 0,
    webhook_secret TEXT
);
```

### Scheduled Tasks Table
```sql
CREATE TABLE scheduled_tasks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    schedule_type TEXT NOT NULL,
    schedule_time TEXT,
    schedule_days TEXT NOT NULL,      -- JSON array
    cron_expression TEXT,
    destinations TEXT NOT NULL,       -- JSON array
    summary_options TEXT NOT NULL,    -- JSON object
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    last_run TEXT,
    next_run TEXT,
    run_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    max_failures INTEGER NOT NULL DEFAULT 3,
    retry_delay_minutes INTEGER NOT NULL DEFAULT 5
);
```

**Indexes:**
- `idx_scheduled_tasks_guild_id` - Guild lookup
- `idx_scheduled_tasks_channel_id` - Channel lookup
- `idx_scheduled_tasks_is_active` - Active task filtering
- `idx_scheduled_tasks_next_run` - Task scheduling
- `idx_scheduled_tasks_active_next_run` - Combined active/next_run (partial index)

### Task Results Table
```sql
CREATE TABLE task_results (
    execution_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    summary_id TEXT,
    error_message TEXT,
    error_details TEXT,           -- JSON object
    delivery_results TEXT NOT NULL, -- JSON array
    execution_time_seconds REAL,
    FOREIGN KEY (task_id) REFERENCES scheduled_tasks(id) ON DELETE CASCADE
);
```

**Indexes:**
- `idx_task_results_task_id` - Task lookup
- `idx_task_results_started_at` - Time-based queries
- `idx_task_results_status` - Status filtering
- `idx_task_results_summary_id` - Summary reference lookup

## Performance Considerations

### Connection Pooling
- Default pool size: 5 connections
- Configurable via `initialize_repositories(pool_size=N)`
- Connections are reused across requests
- Automatic connection lifecycle management

### Database Optimization
- **WAL Mode**: Write-Ahead Logging for better concurrency
- **Foreign Keys**: Enabled for referential integrity
- **Indexes**: Comprehensive indexing on frequently queried columns
- **JSON Storage**: Efficient storage of complex data structures

### Query Optimization
- Use `SearchCriteria` for efficient filtering
- Leverage indexes for guild_id, channel_id, and time-based queries
- Use pagination (limit/offset) for large result sets
- Partial indexes on frequently filtered combinations

## Testing

### Running Tests

```bash
# Run all data module tests
python -m pytest tests/test_data_example.py -v

# Run with coverage
python -m pytest tests/test_data_example.py --cov=src.data

# Run specific test
python -m pytest tests/test_data_example.py::test_summary_repository -v
```

### Example Test
```python
@pytest.mark.asyncio
async def test_summary_repository():
    # Setup
    await run_migrations("test.db")
    initialize_repositories(backend="sqlite", db_path="test.db")

    # Test operations
    repo = await get_summary_repository()
    summary = SummaryResult(...)

    # Save and retrieve
    summary_id = await repo.save_summary(summary)
    retrieved = await repo.get_summary(summary_id)

    assert retrieved.id == summary_id
```

## Migration Management

### Creating Migrations

1. Create a new SQL file in `src/data/migrations/`
2. Name it with incremental version: `002_add_new_feature.sql`
3. Write SQL statements separated by semicolons
4. Run migrations: `await run_migrations(db_path)`

### Migration Example

```sql
-- 002_add_summary_tags.sql
ALTER TABLE summaries ADD COLUMN tags TEXT DEFAULT '[]';

CREATE INDEX idx_summaries_tags ON summaries(tags);

INSERT INTO schema_version (version, applied_at, description)
VALUES (2, datetime('now'), 'Add tags support to summaries');
```

### Resetting Database

```python
from src.data.migrations import reset_database

# WARNING: This will delete all data
await reset_database("data/summarybot.db")
```

## Future Enhancements

### PostgreSQL Support
The PostgreSQL stub is ready for implementation:

1. Add `asyncpg` to requirements
2. Implement connection pooling with `asyncpg.create_pool()`
3. Convert SQL to PostgreSQL syntax
4. Use JSONB instead of JSON TEXT
5. Use proper timestamp types
6. Add PostgreSQL-specific optimizations

### Planned Features
- Query result caching
- Soft delete support
- Audit logging
- Data archiving
- Full-text search
- Database replication support

## Dependencies

- `aiosqlite` - Async SQLite driver
- Python 3.11+ - For async/await support
- `dataclasses` - Model definitions
- `typing` - Type hints

## Error Handling

The data module uses standard Python exceptions:

```python
try:
    summary = await repo.get_summary(summary_id)
    if summary is None:
        # Handle not found
        pass
except Exception as e:
    # Handle database errors
    logger.error(f"Database error: {e}")
```

## Best Practices

1. **Always run migrations** before initializing repositories
2. **Use SearchCriteria** for complex queries instead of custom SQL
3. **Leverage connection pooling** - don't create new connections per request
4. **Use transactions** for multi-step operations
5. **Handle None returns** - repositories return None for not-found cases
6. **Close connections** properly when shutting down
7. **Use type hints** for better IDE support and type safety

## Support

For issues or questions about the data module:
- Check the test file: `tests/test_data_example.py`
- Review the specification: `specs/phase_3_modules.md` (Section 5.1)
- See the base interfaces: `src/data/base.py`

## Version History

- **v1.0.0** - Initial implementation with SQLite support
  - Repository pattern with abstract interfaces
  - Full SQLite implementation
  - Connection pooling
  - Database migrations
  - Comprehensive test coverage
