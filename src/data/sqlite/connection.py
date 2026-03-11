"""
SQLite connection and transaction management.

This module provides the core database connection infrastructure
for SQLite using aiosqlite.
"""

import asyncio
import logging
import aiosqlite
from typing import List, Optional, Dict, Any
from pathlib import Path
from contextlib import asynccontextmanager

from ..base import DatabaseConnection, Transaction

logger = logging.getLogger(__name__)


class SQLiteTransaction(Transaction):
    """SQLite transaction implementation."""

    def __init__(self, connection: aiosqlite.Connection):
        self.connection = connection
        self._active = False

    async def commit(self) -> None:
        """Commit the transaction."""
        if self._active:
            await self.connection.commit()
            self._active = False

    async def rollback(self) -> None:
        """Rollback the transaction."""
        if self._active:
            await self.connection.rollback()
            self._active = False

    async def __aenter__(self) -> 'SQLiteTransaction':
        """Enter transaction context."""
        await self.connection.execute("BEGIN")
        self._active = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit transaction context."""
        if exc_type is not None:
            await self.rollback()
        else:
            await self.commit()


# Module-level write lock - shared across all SQLiteConnection instances
# to prevent concurrent writes from causing database lock errors
_global_write_lock: Optional[asyncio.Lock] = None


def _get_global_write_lock() -> asyncio.Lock:
    """Get the global write lock, creating it if necessary."""
    global _global_write_lock
    if _global_write_lock is None:
        _global_write_lock = asyncio.Lock()
    return _global_write_lock


class SQLiteConnection(DatabaseConnection):
    """SQLite database connection with single-connection mode for safety.

    Note: Pool size of 1 is used to prevent database locking issues.
    aiosqlite uses worker threads per connection, and multiple connections
    can cause database lock errors even with asyncio locks.
    """

    def __init__(self, db_path: str, pool_size: int = 1):
        self.db_path = db_path
        self.pool_size = pool_size
        self._connections: List[aiosqlite.Connection] = []
        self._available: asyncio.Queue = asyncio.Queue(maxsize=pool_size)
        self._lock = asyncio.Lock()
        self._initialized = False

    async def connect(self) -> None:
        """Establish database connection pool."""
        async with self._lock:
            if self._initialized:
                return

            # Ensure database directory exists
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

            # Create connection pool
            for _ in range(self.pool_size):
                conn = await aiosqlite.connect(self.db_path)
                conn.row_factory = aiosqlite.Row
                # Enable WAL mode for better concurrency
                await conn.execute("PRAGMA journal_mode=WAL")
                # Enable foreign keys
                await conn.execute("PRAGMA foreign_keys=ON")
                # Set busy timeout to wait for locks (5 seconds)
                await conn.execute("PRAGMA busy_timeout=5000")
                self._connections.append(conn)
                await self._available.put(conn)

            self._initialized = True

    async def disconnect(self) -> None:
        """Close all database connections."""
        async with self._lock:
            if not self._initialized:
                return

            # Close all connections
            for conn in self._connections:
                await conn.close()

            self._connections.clear()
            self._initialized = False

    @asynccontextmanager
    async def _get_connection(self):
        """Get a connection from the pool."""
        if not self._initialized:
            await self.connect()

        conn = await self._available.get()
        try:
            yield conn
        finally:
            await self._available.put(conn)

    async def execute(self, query: str, params: Optional[tuple] = None, max_retries: int = 5) -> Any:
        """Execute a database query with retry for lock errors.

        Uses a write lock to serialize write operations (INSERT, UPDATE, DELETE)
        to prevent SQLite locking issues with concurrent writes.

        Args:
            query: SQL query to execute
            params: Query parameters
            max_retries: Maximum retry attempts for transient errors
        """
        # Check if this is a write operation
        query_upper = query.strip().upper()
        is_write = query_upper.startswith(('INSERT', 'UPDATE', 'DELETE', 'REPLACE', 'CREATE', 'DROP', 'ALTER'))

        last_error = None
        for attempt in range(max_retries):
            try:
                if is_write:
                    # Serialize writes to prevent concurrent write conflicts
                    # Use global lock to coordinate across all SQLiteConnection instances
                    async with _get_global_write_lock():
                        async with self._get_connection() as conn:
                            cursor = await conn.execute(query, params or ())
                            await conn.commit()
                            return cursor
                else:
                    # Reads can proceed concurrently
                    async with self._get_connection() as conn:
                        cursor = await conn.execute(query, params or ())
                        await conn.commit()
                        return cursor
            except Exception as e:
                error_str = str(e).lower()
                if 'locked' in error_str or 'busy' in error_str:
                    last_error = e
                    # Longer waits: 0.5s, 1s, 2s, 4s, 8s = 15.5s total
                    wait_time = 0.5 * (2 ** attempt)
                    logger.warning(f"Database locked, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    raise
        # All retries failed
        raise last_error

    async def executemany(self, query: str, params_list: List[tuple], max_retries: int = 5) -> Any:
        """Execute a database query with multiple parameter sets.

        PERF-002: Use executemany for batch operations.

        Args:
            query: SQL query to execute
            params_list: List of parameter tuples
            max_retries: Maximum retry attempts for transient errors
        """
        last_error = None
        for attempt in range(max_retries):
            try:
                async with _get_global_write_lock():
                    async with self._get_connection() as conn:
                        cursor = await conn.executemany(query, params_list)
                        await conn.commit()
                        return cursor
            except Exception as e:
                error_str = str(e).lower()
                if 'locked' in error_str or 'busy' in error_str:
                    last_error = e
                    wait_time = 0.5 * (2 ** attempt)
                    logger.warning(f"Database locked, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    raise
        raise last_error

    async def fetch_one(self, query: str, params: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
        """Fetch a single row from the database."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(query, params or ())
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

    async def fetch_all(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """Fetch all rows from the database."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(query, params or ())
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def begin_transaction(self) -> Transaction:
        """Begin a new database transaction."""
        conn = await self._available.get()
        return SQLiteTransaction(conn)
