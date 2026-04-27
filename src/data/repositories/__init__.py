"""
Concrete repository implementations.

This module provides concrete repository classes that can be used
throughout the application.
"""

from typing import Optional
from ..base import SummaryRepository, ConfigRepository, TaskRepository, FeedRepository, WebhookRepository, ErrorRepository, StoredSummaryRepository, SummaryJobRepository, IngestRepository, PromptTemplateRepository
from ..sqlite import (
    SQLiteConnection,
    SQLiteSummaryRepository,
    SQLiteConfigRepository,
    SQLiteTaskRepository,
    SQLiteFeedRepository,
    SQLiteWebhookRepository,
    SQLiteErrorRepository,
    SQLiteStoredSummaryRepository,
    SQLiteSummaryJobRepository,
    SQLiteIngestRepository,
    SQLitePromptTemplateRepository,
    SQLiteAuditRepository,
    SQLiteSlackRepository,
    SQLiteWikiRepository,
    SQLiteIssueRepository,
)
from .google_admin_groups import GoogleAdminGroupsRepository


class RepositoryFactory:
    """Factory for creating repository instances."""

    def __init__(self, backend: str = "sqlite", **config):
        """
        Initialize repository factory.

        Args:
            backend: Database backend to use ('sqlite' or 'postgresql')
            **config: Backend-specific configuration options
        """
        self.backend = backend
        self.config = config
        self._connection: Optional[SQLiteConnection] = None

    async def get_connection(self) -> SQLiteConnection:
        """Get or create database connection."""
        if self._connection is None:
            if self.backend == "sqlite":
                db_path = self.config.get("db_path", "data/summarybot.db")
                # Default to pool_size=1 to prevent SQLite locking issues
                # aiosqlite uses worker threads, and multiple connections cause lock contention
                pool_size = self.config.get("pool_size", 1)
                self._connection = SQLiteConnection(db_path, pool_size)
                await self._connection.connect()
            elif self.backend == "postgresql":
                raise NotImplementedError("PostgreSQL support is not yet implemented")
            else:
                raise ValueError(f"Unsupported backend: {self.backend}")

        return self._connection

    async def get_summary_repository(self) -> SummaryRepository:
        """Create and return a summary repository instance."""
        connection = await self.get_connection()

        if self.backend == "sqlite":
            return SQLiteSummaryRepository(connection)
        elif self.backend == "postgresql":
            raise NotImplementedError("PostgreSQL support is not yet implemented")
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")

    async def get_config_repository(self) -> ConfigRepository:
        """Create and return a config repository instance."""
        connection = await self.get_connection()

        if self.backend == "sqlite":
            return SQLiteConfigRepository(connection)
        elif self.backend == "postgresql":
            raise NotImplementedError("PostgreSQL support is not yet implemented")
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")

    async def get_task_repository(self) -> TaskRepository:
        """Create and return a task repository instance."""
        connection = await self.get_connection()

        if self.backend == "sqlite":
            return SQLiteTaskRepository(connection)
        elif self.backend == "postgresql":
            raise NotImplementedError("PostgreSQL support is not yet implemented")
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")

    async def get_webhook_repository(self) -> WebhookRepository:
        """Create and return a webhook repository instance."""
        connection = await self.get_connection()

        if self.backend == "sqlite":
            return SQLiteWebhookRepository(connection)
        elif self.backend == "postgresql":
            raise NotImplementedError("PostgreSQL support is not yet implemented")
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")

    async def get_feed_repository(self) -> FeedRepository:
        """Create and return a feed repository instance."""
        connection = await self.get_connection()

        if self.backend == "sqlite":
            return SQLiteFeedRepository(connection)
        elif self.backend == "postgresql":
            raise NotImplementedError("PostgreSQL support is not yet implemented")
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")

    async def get_error_repository(self) -> ErrorRepository:
        """Create and return an error log repository instance."""
        connection = await self.get_connection()

        if self.backend == "sqlite":
            return SQLiteErrorRepository(connection)
        elif self.backend == "postgresql":
            raise NotImplementedError("PostgreSQL support is not yet implemented")
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")

    async def get_stored_summary_repository(self) -> StoredSummaryRepository:
        """Create and return a stored summary repository instance (ADR-005)."""
        connection = await self.get_connection()

        if self.backend == "sqlite":
            return SQLiteStoredSummaryRepository(connection)
        elif self.backend == "postgresql":
            raise NotImplementedError("PostgreSQL support is not yet implemented")
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")

    async def get_ingest_repository(self) -> IngestRepository:
        """Create and return an ingest repository instance (ADR-002)."""
        connection = await self.get_connection()

        if self.backend == "sqlite":
            return SQLiteIngestRepository(connection)
        elif self.backend == "postgresql":
            raise NotImplementedError("PostgreSQL support is not yet implemented")
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")

    async def get_summary_job_repository(self) -> SummaryJobRepository:
        """Create and return a summary job repository instance (ADR-013)."""
        connection = await self.get_connection()

        if self.backend == "sqlite":
            return SQLiteSummaryJobRepository(connection)
        elif self.backend == "postgresql":
            raise NotImplementedError("PostgreSQL support is not yet implemented")
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")

    async def get_prompt_template_repository(self) -> PromptTemplateRepository:
        """Create and return a prompt template repository instance (ADR-034)."""
        connection = await self.get_connection()

        if self.backend == "sqlite":
            return SQLitePromptTemplateRepository(connection)
        elif self.backend == "postgresql":
            raise NotImplementedError("PostgreSQL support is not yet implemented")
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")

    async def get_audit_repository(self) -> SQLiteAuditRepository:
        """Create and return an audit log repository instance (ADR-045)."""
        connection = await self.get_connection()

        if self.backend == "sqlite":
            return SQLiteAuditRepository(connection)
        elif self.backend == "postgresql":
            raise NotImplementedError("PostgreSQL support is not yet implemented")
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")

    async def get_slack_repository(self) -> SQLiteSlackRepository:
        """Create and return a Slack repository instance (ADR-043)."""
        connection = await self.get_connection()

        if self.backend == "sqlite":
            return SQLiteSlackRepository(connection)
        elif self.backend == "postgresql":
            raise NotImplementedError("PostgreSQL support is not yet implemented")
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")

    async def get_google_admin_groups_repository(self) -> GoogleAdminGroupsRepository:
        """Create and return a Google admin groups repository instance (ADR-050)."""
        connection = await self.get_connection()

        if self.backend == "sqlite":
            return GoogleAdminGroupsRepository(connection)
        elif self.backend == "postgresql":
            raise NotImplementedError("PostgreSQL support is not yet implemented")
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")

    async def get_wiki_repository(self) -> SQLiteWikiRepository:
        """Create and return a wiki repository instance (ADR-056)."""
        connection = await self.get_connection()

        if self.backend == "sqlite":
            return SQLiteWikiRepository(connection)
        elif self.backend == "postgresql":
            raise NotImplementedError("PostgreSQL support is not yet implemented")
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")

    async def get_issue_repository(self) -> SQLiteIssueRepository:
        """Create and return an issue repository instance (ADR-070)."""
        connection = await self.get_connection()

        if self.backend == "sqlite":
            return SQLiteIssueRepository(connection)
        elif self.backend == "postgresql":
            raise NotImplementedError("PostgreSQL support is not yet implemented")
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")

    async def close(self) -> None:
        """Close database connections."""
        if self._connection:
            await self._connection.disconnect()
            self._connection = None


# Singleton instance for easy access
_default_factory: Optional[RepositoryFactory] = None


def initialize_repositories(backend: str = "sqlite", **config) -> RepositoryFactory:
    """
    Initialize the default repository factory.

    Args:
        backend: Database backend to use
        **config: Backend-specific configuration

    Returns:
        Initialized repository factory
    """
    global _default_factory
    _default_factory = RepositoryFactory(backend, **config)
    return _default_factory


def get_repository_factory() -> RepositoryFactory:
    """
    Get the default repository factory instance.

    Returns:
        The default repository factory

    Raises:
        RuntimeError: If repositories have not been initialized
    """
    if _default_factory is None:
        raise RuntimeError(
            "Repositories not initialized. Call initialize_repositories() first."
        )
    return _default_factory


async def get_summary_repository() -> SummaryRepository:
    """Get the default summary repository instance."""
    factory = get_repository_factory()
    return await factory.get_summary_repository()


async def get_config_repository() -> ConfigRepository:
    """Get the default config repository instance."""
    factory = get_repository_factory()
    return await factory.get_config_repository()


async def get_task_repository() -> TaskRepository:
    """Get the default task repository instance."""
    factory = get_repository_factory()
    return await factory.get_task_repository()


async def get_webhook_repository() -> WebhookRepository:
    """Get the default webhook repository instance."""
    factory = get_repository_factory()
    return await factory.get_webhook_repository()


async def get_feed_repository() -> FeedRepository:
    """Get the default feed repository instance."""
    factory = get_repository_factory()
    return await factory.get_feed_repository()


async def get_error_repository() -> ErrorRepository:
    """Get the default error log repository instance."""
    factory = get_repository_factory()
    return await factory.get_error_repository()


async def get_stored_summary_repository() -> StoredSummaryRepository:
    """Get the default stored summary repository instance (ADR-005)."""
    factory = get_repository_factory()
    return await factory.get_stored_summary_repository()


async def get_ingest_repository() -> IngestRepository:
    """Get the default ingest repository instance (ADR-002)."""
    factory = get_repository_factory()
    return await factory.get_ingest_repository()


async def get_summary_job_repository() -> SummaryJobRepository:
    """Get the default summary job repository instance (ADR-013)."""
    factory = get_repository_factory()
    return await factory.get_summary_job_repository()


async def get_prompt_template_repository() -> PromptTemplateRepository:
    """Get the default prompt template repository instance (ADR-034)."""
    factory = get_repository_factory()
    return await factory.get_prompt_template_repository()


async def get_audit_repository() -> SQLiteAuditRepository:
    """Get the default audit log repository instance (ADR-045)."""
    factory = get_repository_factory()
    return await factory.get_audit_repository()


async def get_slack_repository() -> SQLiteSlackRepository:
    """Get the default Slack repository instance (ADR-043)."""
    factory = get_repository_factory()
    return await factory.get_slack_repository()


async def get_google_admin_groups_repository() -> GoogleAdminGroupsRepository:
    """Get the default Google admin groups repository instance (ADR-050)."""
    factory = get_repository_factory()
    return await factory.get_google_admin_groups_repository()


async def get_wiki_repository() -> SQLiteWikiRepository:
    """Get the default wiki repository instance (ADR-056)."""
    factory = get_repository_factory()
    return await factory.get_wiki_repository()


async def get_issue_repository() -> SQLiteIssueRepository:
    """Get the default issue repository instance (ADR-070)."""
    factory = get_repository_factory()
    return await factory.get_issue_repository()
