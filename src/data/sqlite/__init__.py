"""
SQLite implementation of data repositories.

CS-001: Split sqlite.py into per-repository modules for maintainability.

This package provides SQLite implementations using aiosqlite with:
- Connection pooling and transaction management
- Async database operations
- Repository pattern for data access

MIGRATION STATUS: COMPLETE
All 11 classes have been extracted from the monolithic sqlite.py:
- connection.py: SQLiteConnection, SQLiteTransaction (224 LOC)
- filters.py: StoredSummaryFilter (43 LOC)
- summary_repository.py: SQLiteSummaryRepository (201 LOC)
- config_repository.py: SQLiteConfigRepository (91 LOC)
- task_repository.py: SQLiteTaskRepository (222 LOC)
- feed_repository.py: SQLiteFeedRepository (112 LOC)
- webhook_repository.py: SQLiteWebhookRepository (99 LOC)
- error_repository.py: SQLiteErrorRepository (191 LOC)
- stored_summary_repository.py: SQLiteStoredSummaryRepository (922 LOC)
- ingest_repository.py: SQLiteIngestRepository (281 LOC)
- summary_job_repository.py: SQLiteSummaryJobRepository (224 LOC)

The _sqlite_legacy.py file can be removed once all imports are verified.
"""

# Connection infrastructure
from .connection import SQLiteConnection, SQLiteTransaction

# Filter dataclasses
from .filters import StoredSummaryFilter

# All repositories - fully extracted
from .summary_repository import SQLiteSummaryRepository
from .config_repository import SQLiteConfigRepository
from .task_repository import SQLiteTaskRepository
from .feed_repository import SQLiteFeedRepository
from .webhook_repository import SQLiteWebhookRepository
from .error_repository import SQLiteErrorRepository
from .stored_summary_repository import SQLiteStoredSummaryRepository
from .ingest_repository import SQLiteIngestRepository
from .summary_job_repository import SQLiteSummaryJobRepository
from .prompt_template_repository import SQLitePromptTemplateRepository
from .audit_repository import SQLiteAuditRepository
from .slack_repository import SQLiteSlackRepository
from .wiki_repository import SQLiteWikiRepository
from .issue_repository import SQLiteIssueRepository
from .coverage_repository import SQLiteCoverageRepository
from .channel_settings_repository import SQLiteChannelSettingsRepository, ChannelSettings

__all__ = [
    # Connection
    'SQLiteConnection',
    'SQLiteTransaction',
    # Filters
    'StoredSummaryFilter',
    # Repositories
    'SQLiteSummaryRepository',
    'SQLiteConfigRepository',
    'SQLiteTaskRepository',
    'SQLiteFeedRepository',
    'SQLiteWebhookRepository',
    'SQLiteErrorRepository',
    'SQLiteStoredSummaryRepository',
    'SQLiteIngestRepository',
    'SQLiteSummaryJobRepository',
    'SQLitePromptTemplateRepository',
    'SQLiteAuditRepository',
    'SQLiteSlackRepository',
    'SQLiteWikiRepository',
    'SQLiteIssueRepository',
    'SQLiteCoverageRepository',
    'SQLiteChannelSettingsRepository',
    'ChannelSettings',
]
