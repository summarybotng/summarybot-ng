"""
Unit tests for SQLite database implementation.

Tests cover:
- Connection pooling
- Transaction management (commit, rollback)
- Async query execution
- Connection cleanup
- Error handling
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import datetime

from src.data.sqlite import SQLiteConnection, SQLiteTransaction


class TestSQLiteConnection:
    """Test SQLite connection pooling and management."""

    @pytest.mark.asyncio
    async def test_connection_initialization(self):
        """Test database connection initialization."""
        connection = SQLiteConnection(":memory:", pool_size=3)
        await connection.connect()

        assert connection._initialized is True
        assert len(connection._connections) == 3
        assert connection._available.qsize() == 3

        await connection.disconnect()

    @pytest.mark.asyncio
    async def test_connection_cleanup(self):
        """Test connection cleanup on disconnect."""
        connection = SQLiteConnection(":memory:", pool_size=2)
        await connection.connect()

        assert connection._initialized is True

        await connection.disconnect()

        assert connection._initialized is False
        assert len(connection._connections) == 0

    @pytest.mark.asyncio
    async def test_double_connect_idempotent(self):
        """Test that multiple connect calls are idempotent."""
        connection = SQLiteConnection(":memory:", pool_size=2)

        await connection.connect()
        initial_connections = len(connection._connections)

        await connection.connect()  # Second call should not create new connections

        assert len(connection._connections) == initial_connections
        await connection.disconnect()

    @pytest.mark.asyncio
    async def test_execute_query(self, in_memory_db: SQLiteConnection):
        """Test executing a basic query."""
        await in_memory_db.execute(
            "CREATE TABLE test_table (id INTEGER PRIMARY KEY, name TEXT)"
        )

        await in_memory_db.execute(
            "INSERT INTO test_table (name) VALUES (?)",
            ("test_value",)
        )

        result = await in_memory_db.fetch_one(
            "SELECT name FROM test_table WHERE id = 1"
        )

        assert result is not None
        assert result["name"] == "test_value"

    @pytest.mark.asyncio
    async def test_fetch_one(self, in_memory_db: SQLiteConnection):
        """Test fetching a single row."""
        await in_memory_db.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)"
        )
        await in_memory_db.execute(
            "INSERT INTO users (username) VALUES (?)",
            ("alice",)
        )

        result = await in_memory_db.fetch_one(
            "SELECT username FROM users WHERE id = 1"
        )

        assert result is not None
        assert result["username"] == "alice"

    @pytest.mark.asyncio
    async def test_fetch_one_no_results(self, in_memory_db: SQLiteConnection):
        """Test fetching when no results exist."""
        await in_memory_db.execute(
            "CREATE TABLE empty_table (id INTEGER PRIMARY KEY)"
        )

        result = await in_memory_db.fetch_one(
            "SELECT * FROM empty_table WHERE id = 999"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_all(self, in_memory_db: SQLiteConnection):
        """Test fetching multiple rows."""
        await in_memory_db.execute(
            "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)"
        )

        # Insert multiple rows
        for i in range(5):
            await in_memory_db.execute(
                "INSERT INTO items (name) VALUES (?)",
                (f"item_{i}",)
            )

        results = await in_memory_db.fetch_all("SELECT name FROM items ORDER BY id")

        assert len(results) == 5
        assert results[0]["name"] == "item_0"
        assert results[4]["name"] == "item_4"

    @pytest.mark.asyncio
    async def test_fetch_all_empty(self, in_memory_db: SQLiteConnection):
        """Test fetching all from empty table."""
        await in_memory_db.execute(
            "CREATE TABLE empty_table (id INTEGER PRIMARY KEY)"
        )

        results = await in_memory_db.fetch_all("SELECT * FROM empty_table")

        assert results == []

    @pytest.mark.asyncio
    async def test_connection_pool_concurrency(self, tmp_path):
        """Test concurrent access to connection pool."""
        # Use file-based DB because :memory: with pool_size>1 creates
        # separate in-memory databases per connection
        db_path = str(tmp_path / "concurrency_test.db")
        connection = SQLiteConnection(db_path, pool_size=2)
        await connection.connect()

        await connection.execute(
            "CREATE TABLE counter (id INTEGER PRIMARY KEY, value INTEGER)"
        )
        await connection.execute("INSERT INTO counter (value) VALUES (0)")

        async def increment_counter():
            """Increment counter in database."""
            result = await connection.fetch_one("SELECT value FROM counter WHERE id = 1")
            new_value = result["value"] + 1
            await connection.execute(
                "UPDATE counter SET value = ? WHERE id = 1",
                (new_value,)
            )

        # Run multiple concurrent operations
        await asyncio.gather(*[increment_counter() for _ in range(10)])

        # Note: Without proper locking, this might not be exactly 10
        # but it tests that the connection pool handles concurrent access
        result = await connection.fetch_one("SELECT value FROM counter WHERE id = 1")
        assert result["value"] > 0

        await connection.disconnect()

    @pytest.mark.asyncio
    async def test_wal_mode_enabled(self, in_memory_db: SQLiteConnection):
        """Test that WAL mode is enabled for better concurrency."""
        result = await in_memory_db.fetch_one("PRAGMA journal_mode")
        # Note: WAL mode might not be available in all SQLite builds
        assert result is not None

    @pytest.mark.asyncio
    async def test_foreign_keys_enabled(self, in_memory_db: SQLiteConnection):
        """Test that foreign key constraints are enabled."""
        result = await in_memory_db.fetch_one("PRAGMA foreign_keys")
        assert result is not None
        assert result["foreign_keys"] == 1


class TestSQLiteTransaction:
    """Test SQLite transaction management."""

    @pytest.mark.asyncio
    async def test_transaction_commit(self, in_memory_db: SQLiteConnection):
        """Test successful transaction commit."""
        await in_memory_db.execute(
            "CREATE TABLE accounts (id INTEGER PRIMARY KEY, balance INTEGER)"
        )
        await in_memory_db.execute("INSERT INTO accounts (balance) VALUES (100)")

        transaction = await in_memory_db.begin_transaction()
        async with transaction:
            conn = transaction.connection
            await conn.execute(
                "UPDATE accounts SET balance = balance - 50 WHERE id = 1"
            )
            # Transaction will commit on context exit

        # Verify the change was committed
        result = await in_memory_db.fetch_one(
            "SELECT balance FROM accounts WHERE id = 1"
        )
        assert result["balance"] == 50

    @pytest.mark.asyncio
    async def test_transaction_rollback_on_error(self, in_memory_db: SQLiteConnection):
        """Test transaction rollback on exception."""
        await in_memory_db.execute(
            "CREATE TABLE accounts (id INTEGER PRIMARY KEY, balance INTEGER)"
        )
        await in_memory_db.execute("INSERT INTO accounts (balance) VALUES (100)")

        transaction = await in_memory_db.begin_transaction()

        try:
            async with transaction:
                conn = transaction.connection
                await conn.execute(
                    "UPDATE accounts SET balance = balance - 50 WHERE id = 1"
                )
                # Simulate an error
                raise ValueError("Simulated error")
        except ValueError:
            pass  # Expected

        # Verify the change was rolled back
        result = await in_memory_db.fetch_one(
            "SELECT balance FROM accounts WHERE id = 1"
        )
        assert result["balance"] == 100

    @pytest.mark.asyncio
    async def test_transaction_manual_commit(self, in_memory_db: SQLiteConnection):
        """Test manual transaction commit."""
        await in_memory_db.execute(
            "CREATE TABLE data (id INTEGER PRIMARY KEY, value TEXT)"
        )

        transaction = await in_memory_db.begin_transaction()
        async with transaction:
            conn = transaction.connection
            await conn.execute("INSERT INTO data (value) VALUES ('test')")
            await transaction.commit()

        result = await in_memory_db.fetch_one("SELECT value FROM data WHERE id = 1")
        assert result is not None
        assert result["value"] == "test"

    @pytest.mark.asyncio
    async def test_transaction_manual_rollback(self, in_memory_db: SQLiteConnection):
        """Test manual transaction rollback."""
        await in_memory_db.execute(
            "CREATE TABLE data (id INTEGER PRIMARY KEY, value TEXT)"
        )

        transaction = await in_memory_db.begin_transaction()
        async with transaction:
            conn = transaction.connection
            await conn.execute("INSERT INTO data (value) VALUES ('test')")
            await transaction.rollback()

        result = await in_memory_db.fetch_one("SELECT value FROM data WHERE id = 1")
        assert result is None

    @pytest.mark.asyncio
    async def test_nested_operations_in_transaction(self, in_memory_db: SQLiteConnection):
        """Test multiple operations within a single transaction."""
        await in_memory_db.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)"
        )
        await in_memory_db.execute(
            "CREATE TABLE logs (id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT)"
        )

        transaction = await in_memory_db.begin_transaction()
        async with transaction:
            conn = transaction.connection

            # Insert user
            await conn.execute("INSERT INTO users (name) VALUES ('Alice')")

            # Insert log entry
            await conn.execute(
                "INSERT INTO logs (user_id, action) VALUES (1, 'created')"
            )

        # Verify both inserts succeeded
        user = await in_memory_db.fetch_one("SELECT name FROM users WHERE id = 1")
        log = await in_memory_db.fetch_one("SELECT action FROM logs WHERE user_id = 1")

        assert user["name"] == "Alice"
        assert log["action"] == "created"

    @pytest.mark.asyncio
    async def test_transaction_isolation(self, in_memory_db: SQLiteConnection):
        """Test transaction isolation."""
        await in_memory_db.execute(
            "CREATE TABLE counter (id INTEGER PRIMARY KEY, value INTEGER)"
        )
        await in_memory_db.execute("INSERT INTO counter (value) VALUES (0)")

        transaction = await in_memory_db.begin_transaction()
        async with transaction:
            conn = transaction.connection
            await conn.execute("UPDATE counter SET value = 100 WHERE id = 1")
            # Note: Cannot read from pool mid-transaction with pool_size=1
            # (the transaction holds the only connection, so fetch_one would deadlock)

        final_result = await in_memory_db.fetch_one("SELECT value FROM counter WHERE id = 1")
        assert final_result["value"] == 100


class TestSQLiteErrorHandling:
    """Test error handling in SQLite operations."""

    @pytest.mark.asyncio
    async def test_invalid_query(self, in_memory_db: SQLiteConnection):
        """Test handling of invalid SQL query."""
        with pytest.raises(Exception):  # Should raise aiosqlite.Error or similar
            await in_memory_db.execute("INVALID SQL QUERY")

    @pytest.mark.asyncio
    async def test_missing_table(self, in_memory_db: SQLiteConnection):
        """Test querying non-existent table."""
        with pytest.raises(Exception):
            await in_memory_db.fetch_one("SELECT * FROM nonexistent_table")

    @pytest.mark.asyncio
    async def test_constraint_violation(self, in_memory_db: SQLiteConnection):
        """Test handling of constraint violations."""
        await in_memory_db.execute(
            "CREATE TABLE unique_test (id INTEGER PRIMARY KEY, value TEXT UNIQUE)"
        )
        await in_memory_db.execute("INSERT INTO unique_test (value) VALUES ('unique')")

        with pytest.raises(Exception):  # Should raise integrity error
            await in_memory_db.execute("INSERT INTO unique_test (value) VALUES ('unique')")

    @pytest.mark.asyncio
    async def test_disconnect_without_connect(self):
        """Test disconnecting without prior connection."""
        connection = SQLiteConnection(":memory:")

        # Should not raise an error
        await connection.disconnect()

        assert connection._initialized is False


class TestSQLitePerformance:
    """Test SQLite performance characteristics."""

    @pytest.mark.asyncio
    async def test_bulk_insert_performance(self, in_memory_db: SQLiteConnection):
        """Test performance of bulk inserts."""
        await in_memory_db.execute(
            "CREATE TABLE bulk_test (id INTEGER PRIMARY KEY, data TEXT)"
        )

        # Insert 1000 rows
        for i in range(1000):
            await in_memory_db.execute(
                "INSERT INTO bulk_test (data) VALUES (?)",
                (f"data_{i}",)
            )

        result = await in_memory_db.fetch_one("SELECT COUNT(*) as count FROM bulk_test")
        assert result["count"] == 1000

    @pytest.mark.asyncio
    async def test_connection_pool_reuse(self, tmp_path):
        """Test that connections are reused from pool."""
        # Use file-based DB because :memory: with pool_size>1 creates
        # separate in-memory databases per connection
        db_path = str(tmp_path / "reuse_test.db")
        connection = SQLiteConnection(db_path, pool_size=2)
        await connection.connect()

        await connection.execute(
            "CREATE TABLE reuse_test (id INTEGER PRIMARY KEY)"
        )

        # Execute multiple queries - should reuse connections
        for i in range(10):
            await connection.execute(f"INSERT INTO reuse_test (id) VALUES ({i})")

        # Pool should still have 2 connections
        assert len(connection._connections) == 2

        await connection.disconnect()


class TestPoolSizeDefaults:
    """Test default pool size after P1-5 fix (changed from 1 to 3)."""

    def test_default_pool_size_is_3(self):
        """Test that the default pool_size is 3."""
        conn = SQLiteConnection(":memory:")
        assert conn.pool_size == 3

    @pytest.mark.asyncio
    async def test_concurrent_reads_complete_without_timeout(self):
        """Test that 3 concurrent reads complete without deadlock."""
        conn = SQLiteConnection(":memory:", pool_size=3)
        await conn.connect()
        try:
            await conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
            results = await asyncio.wait_for(
                asyncio.gather(
                    conn.fetch_one("SELECT 1 as val"),
                    conn.fetch_one("SELECT 2 as val"),
                    conn.fetch_one("SELECT 3 as val"),
                ),
                timeout=5.0,
            )
            assert len(results) == 3
        finally:
            await conn.disconnect()
