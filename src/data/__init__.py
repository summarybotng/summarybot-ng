"""
Data access layer for Summary Bot NG.

This module provides database operations and data persistence with support
for multiple backends (SQLite, PostgreSQL).

Public Interface:
    - Repository classes for data operations
    - Database connection management
    - Migration utilities
    - Factory pattern for repository creation

Example Usage:
    ```python
    from src.data import initialize_repositories, get_summary_repository
    from src.data.migrations import run_migrations

    # Initialize database and run migrations
    await run_migrations("data/summarybot.db")

    # Initialize repositories
    initialize_repositories(backend="sqlite", db_path="data/summarybot.db")

    # Use repositories
    summary_repo = await get_summary_repository()
    await summary_repo.save_summary(summary_result)
    ```
"""

# Abstract base classes
from .base import (
    SummaryRepository,
    ConfigRepository,
    TaskRepository,
    FeedRepository,
    WebhookRepository,
    ErrorRepository,
    IngestRepository,
    StoredSummaryRepository,
    DatabaseConnection,
    Transaction,
    SearchCriteria
)

# SQLite implementations
from .sqlite import (
    SQLiteConnection,
    SQLiteSummaryRepository,
    SQLiteConfigRepository,
    SQLiteTaskRepository,
    SQLiteFeedRepository,
    SQLiteWebhookRepository,
    SQLiteErrorRepository,
    SQLiteStoredSummaryRepository,
    SQLiteIngestRepository,
    SQLiteTransaction
)

# Repository factory
from .repositories import (
    RepositoryFactory,
    initialize_repositories,
    get_repository_factory,
    get_summary_repository,
    get_config_repository,
    get_task_repository,
    get_feed_repository,
    get_webhook_repository,
    get_error_repository,
    get_stored_summary_repository,
    get_ingest_repository
)

# Migration utilities
from .migrations import (
    MigrationRunner,
    run_migrations,
    reset_database
)

__all__ = [
    # Abstract interfaces
    "SummaryRepository",
    "ConfigRepository",
    "TaskRepository",
    "FeedRepository",
    "WebhookRepository",
    "ErrorRepository",
    "IngestRepository",
    "StoredSummaryRepository",
    "DatabaseConnection",
    "Transaction",
    "SearchCriteria",

    # SQLite implementations
    "SQLiteConnection",
    "SQLiteSummaryRepository",
    "SQLiteConfigRepository",
    "SQLiteTaskRepository",
    "SQLiteFeedRepository",
    "SQLiteWebhookRepository",
    "SQLiteErrorRepository",
    "SQLiteStoredSummaryRepository",
    "SQLiteIngestRepository",
    "SQLiteTransaction",

    # Repository factory
    "RepositoryFactory",
    "initialize_repositories",
    "get_repository_factory",
    "get_summary_repository",
    "get_config_repository",
    "get_task_repository",
    "get_feed_repository",
    "get_webhook_repository",
    "get_error_repository",
    "get_stored_summary_repository",
    "get_ingest_repository",

    # Migrations
    "MigrationRunner",
    "run_migrations",
    "reset_database",
]

# Module version
__version__ = "1.0.0"
