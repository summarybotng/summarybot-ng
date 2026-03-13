"""
Unit tests for database migrations.

Tests cover:
- Schema creation
- Migration runner
- Schema validation
- Table structure verification
"""

import pytest
import pytest_asyncio
from datetime import datetime

from src.data.sqlite import SQLiteConnection


class TestDatabaseSchema:
    """Test database schema creation and structure."""

    @pytest.mark.asyncio
    async def test_summaries_table_exists(self, in_memory_db: SQLiteConnection):
        """Test that summaries table exists."""
        result = await in_memory_db.fetch_one("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='summaries'
        """)

        assert result is not None
        assert result["name"] == "summaries"

    @pytest.mark.asyncio
    async def test_summaries_table_structure(self, in_memory_db: SQLiteConnection):
        """Test summaries table has correct columns."""
        columns = await in_memory_db.fetch_all("PRAGMA table_info(summaries)")

        column_names = [col["name"] for col in columns]

        expected_columns = [
            "id", "channel_id", "guild_id", "start_time", "end_time",
            "message_count", "summary_text", "key_points", "action_items",
            "technical_terms", "participants", "metadata", "created_at", "context"
        ]

        for col in expected_columns:
            assert col in column_names, f"Column {col} not found in summaries table"

    @pytest.mark.asyncio
    async def test_guild_configs_table_exists(self, in_memory_db: SQLiteConnection):
        """Test that guild_configs table exists."""
        result = await in_memory_db.fetch_one("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='guild_configs'
        """)

        assert result is not None
        assert result["name"] == "guild_configs"

    @pytest.mark.asyncio
    async def test_guild_configs_table_structure(self, in_memory_db: SQLiteConnection):
        """Test guild_configs table has correct columns."""
        columns = await in_memory_db.fetch_all("PRAGMA table_info(guild_configs)")

        column_names = [col["name"] for col in columns]

        expected_columns = [
            "guild_id", "enabled_channels", "excluded_channels",
            "default_summary_options", "permission_settings",
            "webhook_enabled", "webhook_secret"
        ]

        for col in expected_columns:
            assert col in column_names, f"Column {col} not found in guild_configs table"

    @pytest.mark.asyncio
    async def test_scheduled_tasks_table_exists(self, in_memory_db: SQLiteConnection):
        """Test that scheduled_tasks table exists."""
        result = await in_memory_db.fetch_one("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='scheduled_tasks'
        """)

        assert result is not None
        assert result["name"] == "scheduled_tasks"

    @pytest.mark.asyncio
    async def test_scheduled_tasks_table_structure(self, in_memory_db: SQLiteConnection):
        """Test scheduled_tasks table has correct columns."""
        columns = await in_memory_db.fetch_all("PRAGMA table_info(scheduled_tasks)")

        column_names = [col["name"] for col in columns]

        expected_columns = [
            "id", "name", "channel_id", "guild_id", "schedule_type",
            "schedule_time", "schedule_days", "cron_expression",
            "destinations", "summary_options", "is_active",
            "created_at", "created_by", "last_run", "next_run",
            "run_count", "failure_count", "max_failures", "retry_delay_minutes"
        ]

        for col in expected_columns:
            assert col in column_names, f"Column {col} not found in scheduled_tasks table"

    @pytest.mark.asyncio
    async def test_task_results_table_exists(self, in_memory_db: SQLiteConnection):
        """Test that task_results table exists."""
        result = await in_memory_db.fetch_one("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='task_results'
        """)

        assert result is not None
        assert result["name"] == "task_results"

    @pytest.mark.asyncio
    async def test_task_results_table_structure(self, in_memory_db: SQLiteConnection):
        """Test task_results table has correct columns."""
        columns = await in_memory_db.fetch_all("PRAGMA table_info(task_results)")

        column_names = [col["name"] for col in columns]

        expected_columns = [
            "execution_id", "task_id", "status", "started_at", "completed_at",
            "summary_id", "error_message", "error_details",
            "delivery_results", "execution_time_seconds"
        ]

        for col in expected_columns:
            assert col in column_names, f"Column {col} not found in task_results table"


class TestPrimaryKeys:
    """Test primary key constraints."""

    @pytest.mark.asyncio
    async def test_summaries_primary_key(self, in_memory_db: SQLiteConnection):
        """Test summaries table primary key constraint."""
        # Insert a summary
        await in_memory_db.execute("""
            INSERT INTO summaries (
                id, channel_id, guild_id, start_time, end_time,
                message_count, summary_text, key_points, action_items,
                technical_terms, participants, metadata, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "test-id", "ch1", "g1", "2024-01-01T00:00:00",
            "2024-01-01T01:00:00", 10, "Test", "[]", "[]",
            "[]", "[]", "{}", "2024-01-01T01:00:00"
        ))

        # Try to insert duplicate - should fail
        with pytest.raises(Exception):
            await in_memory_db.execute("""
                INSERT INTO summaries (
                    id, channel_id, guild_id, start_time, end_time,
                    message_count, summary_text, key_points, action_items,
                    technical_terms, participants, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "test-id", "ch2", "g2", "2024-01-01T00:00:00",
                "2024-01-01T01:00:00", 5, "Test2", "[]", "[]",
                "[]", "[]", "{}", "2024-01-01T01:00:00"
            ))

    @pytest.mark.asyncio
    async def test_guild_configs_primary_key(self, in_memory_db: SQLiteConnection):
        """Test guild_configs table primary key constraint."""
        # Insert a config
        await in_memory_db.execute("""
            INSERT INTO guild_configs (
                guild_id, enabled_channels, excluded_channels,
                default_summary_options, permission_settings
            ) VALUES (?, ?, ?, ?, ?)
        """, ("guild-1", "[]", "[]", "{}", "{}"))

        # Try to insert duplicate - should fail
        with pytest.raises(Exception):
            await in_memory_db.execute("""
                INSERT INTO guild_configs (
                    guild_id, enabled_channels, excluded_channels,
                    default_summary_options, permission_settings
                ) VALUES (?, ?, ?, ?, ?)
            """, ("guild-1", "[]", "[]", "{}", "{}"))


class TestForeignKeys:
    """Test foreign key constraints."""

    @pytest.mark.asyncio
    async def test_task_results_foreign_key(self, in_memory_db: SQLiteConnection):
        """Test task_results has foreign key to scheduled_tasks."""
        # Check foreign keys are enabled
        fk_status = await in_memory_db.fetch_one("PRAGMA foreign_keys")
        assert fk_status["foreign_keys"] == 1

        # Get foreign key info for task_results
        foreign_keys = await in_memory_db.fetch_all("PRAGMA foreign_key_list(task_results)")

        # Should have foreign key to scheduled_tasks
        assert len(foreign_keys) > 0
        fk = foreign_keys[0]
        assert fk["table"] == "scheduled_tasks"
        assert fk["from"] == "task_id"


class TestDataTypes:
    """Test column data types."""

    @pytest.mark.asyncio
    async def test_summaries_data_types(self, in_memory_db: SQLiteConnection):
        """Test summaries table column data types."""
        columns = await in_memory_db.fetch_all("PRAGMA table_info(summaries)")

        # Create a mapping of column names to types
        type_map = {col["name"]: col["type"] for col in columns}

        # Check critical data types
        assert type_map["id"] == "TEXT"
        assert type_map["message_count"] == "INTEGER"
        assert type_map["summary_text"] == "TEXT"

    @pytest.mark.asyncio
    async def test_scheduled_tasks_data_types(self, in_memory_db: SQLiteConnection):
        """Test scheduled_tasks table column data types."""
        columns = await in_memory_db.fetch_all("PRAGMA table_info(scheduled_tasks)")

        type_map = {col["name"]: col["type"] for col in columns}

        assert type_map["id"] == "TEXT"
        assert type_map["is_active"] == "INTEGER"
        assert type_map["run_count"] == "INTEGER"


class TestDefaultValues:
    """Test default column values."""

    @pytest.mark.asyncio
    async def test_guild_config_defaults(self, in_memory_db: SQLiteConnection):
        """Test guild_configs table default values."""
        columns = await in_memory_db.fetch_all("PRAGMA table_info(guild_configs)")

        # Find webhook_enabled column
        webhook_col = next(col for col in columns if col["name"] == "webhook_enabled")

        # Default should be 0 (False)
        assert webhook_col["dflt_value"] == "0"

    @pytest.mark.asyncio
    async def test_scheduled_tasks_defaults(self, in_memory_db: SQLiteConnection):
        """Test scheduled_tasks table default values."""
        columns = await in_memory_db.fetch_all("PRAGMA table_info(scheduled_tasks)")

        # Check defaults
        is_active_col = next(col for col in columns if col["name"] == "is_active")
        run_count_col = next(col for col in columns if col["name"] == "run_count")
        max_failures_col = next(col for col in columns if col["name"] == "max_failures")

        assert is_active_col["dflt_value"] == "1"  # Default active
        assert run_count_col["dflt_value"] == "0"
        assert max_failures_col["dflt_value"] == "3"


class TestSchemaIntegrity:
    """Test overall schema integrity."""

    @pytest.mark.asyncio
    async def test_all_tables_created(self, in_memory_db: SQLiteConnection):
        """Test that all required tables are created."""
        tables = await in_memory_db.fetch_all("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
        """)

        table_names = [table["name"] for table in tables]

        expected_tables = [
            "summaries",
            "guild_configs",
            "scheduled_tasks",
            "task_results"
        ]

        for table in expected_tables:
            assert table in table_names, f"Table {table} not found"

    @pytest.mark.asyncio
    async def test_no_extra_tables(self, in_memory_db: SQLiteConnection):
        """Test that no unexpected tables exist."""
        tables = await in_memory_db.fetch_all("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
        """)

        table_names = [table["name"] for table in tables]

        expected_tables = [
            "summaries",
            "guild_configs",
            "scheduled_tasks",
            "task_results",
            "stored_summaries"
        ]

        # All tables should be expected
        for table in table_names:
            assert table in expected_tables, f"Unexpected table {table} found"

    @pytest.mark.asyncio
    async def test_schema_consistency(self, in_memory_db: SQLiteConnection):
        """Test schema consistency across connections."""
        # Get schema from connection
        schema1 = await in_memory_db.fetch_all("""
            SELECT sql FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)

        # Verify all table definitions are present
        assert len(schema1) == 5


class TestMigrationScenarios:
    """Test various migration scenarios."""

    @pytest.mark.asyncio
    async def test_insert_after_schema_creation(self, in_memory_db: SQLiteConnection):
        """Test inserting data after schema creation."""
        # Insert into summaries
        await in_memory_db.execute("""
            INSERT INTO summaries (
                id, channel_id, guild_id, start_time, end_time,
                message_count, summary_text, key_points, action_items,
                technical_terms, participants, metadata, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "test-1", "ch1", "g1", "2024-01-01T00:00:00",
            "2024-01-01T01:00:00", 10, "Test summary",
            "[]", "[]", "[]", "[]", "{}", "2024-01-01T01:00:00"
        ))

        # Verify insertion
        result = await in_memory_db.fetch_one("SELECT * FROM summaries WHERE id = 'test-1'")
        assert result is not None
        assert result["id"] == "test-1"

    @pytest.mark.asyncio
    async def test_complex_insert_with_json(self, in_memory_db: SQLiteConnection):
        """Test inserting complex JSON data."""
        import json

        complex_data = {
            "key_points": ["Point 1", "Point 2"],
            "action_items": [{"description": "Task 1", "priority": "high"}],
            "metadata": {"version": "1.0", "source": "test"}
        }

        await in_memory_db.execute("""
            INSERT INTO summaries (
                id, channel_id, guild_id, start_time, end_time,
                message_count, summary_text, key_points, action_items,
                technical_terms, participants, metadata, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "test-json", "ch1", "g1", "2024-01-01T00:00:00",
            "2024-01-01T01:00:00", 10, "Test",
            json.dumps(complex_data["key_points"]),
            json.dumps(complex_data["action_items"]),
            "[]", "[]",
            json.dumps(complex_data["metadata"]),
            "2024-01-01T01:00:00"
        ))

        # Verify data can be retrieved and parsed
        result = await in_memory_db.fetch_one("SELECT * FROM summaries WHERE id = 'test-json'")
        assert result is not None

        key_points = json.loads(result["key_points"])
        assert len(key_points) == 2

    @pytest.mark.asyncio
    async def test_cascading_relationships(self, in_memory_db: SQLiteConnection):
        """Test relationships between tables."""
        # Create a scheduled task
        await in_memory_db.execute("""
            INSERT INTO scheduled_tasks (
                id, name, channel_id, guild_id, schedule_type,
                schedule_days, destinations, summary_options,
                created_at, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "task-1", "Test Task", "ch1", "g1", "daily",
            "[]", "[]", "{}", "2024-01-01T00:00:00", "admin"
        ))

        # Create a task result
        await in_memory_db.execute("""
            INSERT INTO task_results (
                execution_id, task_id, status, started_at, delivery_results
            ) VALUES (?, ?, ?, ?, ?)
        """, ("exec-1", "task-1", "completed", "2024-01-01T00:00:00", "[]"))

        # Verify relationship
        result = await in_memory_db.fetch_one("""
            SELECT tr.*, st.name
            FROM task_results tr
            JOIN scheduled_tasks st ON tr.task_id = st.id
            WHERE tr.execution_id = 'exec-1'
        """)

        assert result is not None
        assert result["name"] == "Test Task"


class TestIndexPerformance:
    """Test database index performance considerations."""

    @pytest.mark.asyncio
    async def test_query_without_index(self, in_memory_db: SQLiteConnection):
        """Test query performance baseline."""
        # Insert test data
        for i in range(100):
            await in_memory_db.execute("""
                INSERT INTO summaries (
                    id, channel_id, guild_id, start_time, end_time,
                    message_count, summary_text, key_points, action_items,
                    technical_terms, participants, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                f"summary-{i}", f"channel-{i % 10}", f"guild-{i % 5}",
                "2024-01-01T00:00:00", "2024-01-01T01:00:00",
                10, "Test", "[]", "[]", "[]", "[]", "{}", "2024-01-01T01:00:00"
            ))

        # Query should work (though might be slow without index)
        results = await in_memory_db.fetch_all("""
            SELECT * FROM summaries WHERE guild_id = 'guild-1'
        """)

        assert len(results) > 0
