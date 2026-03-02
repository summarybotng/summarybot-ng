"""
Tests for WhatsApp importer deduplication.
"""

import json
import pytest
import tempfile
from datetime import datetime
from pathlib import Path

from src.archive.importers.whatsapp import WhatsAppImporter


class TestMessageFingerprint:
    """Tests for message fingerprinting."""

    def test_fingerprint_includes_timestamp_sender_content(self):
        """Fingerprint should include timestamp, sender, and content prefix."""
        importer = WhatsAppImporter(Path("/tmp"))
        msg = {
            "timestamp": "2025-01-15T10:30:00",
            "sender": "Alice",
            "content": "Hello, this is a test message with some content",
        }
        fp = importer._message_fingerprint(msg)
        assert "2025-01-15T10:30:00" in fp
        assert "Alice" in fp
        assert "Hello, this is a test message with some con" in fp  # First 50 chars

    def test_fingerprint_truncates_long_content(self):
        """Content should be truncated to 50 chars."""
        importer = WhatsAppImporter(Path("/tmp"))
        msg = {
            "timestamp": "2025-01-15T10:30:00",
            "sender": "Alice",
            "content": "x" * 100,
        }
        fp = importer._message_fingerprint(msg)
        # Should only include first 50 chars
        assert fp.count("x") == 50

    def test_identical_messages_same_fingerprint(self):
        """Identical messages should have the same fingerprint."""
        importer = WhatsAppImporter(Path("/tmp"))
        msg1 = {"timestamp": "2025-01-15T10:30:00", "sender": "Alice", "content": "Hello"}
        msg2 = {"timestamp": "2025-01-15T10:30:00", "sender": "Alice", "content": "Hello"}
        assert importer._message_fingerprint(msg1) == importer._message_fingerprint(msg2)

    def test_different_timestamp_different_fingerprint(self):
        """Different timestamps should produce different fingerprints."""
        importer = WhatsAppImporter(Path("/tmp"))
        msg1 = {"timestamp": "2025-01-15T10:30:00", "sender": "Alice", "content": "Hello"}
        msg2 = {"timestamp": "2025-01-15T10:31:00", "sender": "Alice", "content": "Hello"}
        assert importer._message_fingerprint(msg1) != importer._message_fingerprint(msg2)

    def test_different_sender_different_fingerprint(self):
        """Different senders should produce different fingerprints."""
        importer = WhatsAppImporter(Path("/tmp"))
        msg1 = {"timestamp": "2025-01-15T10:30:00", "sender": "Alice", "content": "Hello"}
        msg2 = {"timestamp": "2025-01-15T10:30:00", "sender": "Bob", "content": "Hello"}
        assert importer._message_fingerprint(msg1) != importer._message_fingerprint(msg2)


class TestDeduplication:
    """Tests for message deduplication during retrieval."""

    @pytest.fixture
    def archive_root(self):
        """Create a temporary archive root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def setup_overlapping_imports(self, archive_root):
        """Set up two imports with overlapping date ranges."""
        group_id = "test-group"
        group_dir = archive_root / "sources" / "whatsapp" / f"test_{group_id}"
        imports_dir = group_dir / "imports"
        imports_dir.mkdir(parents=True)

        # Import 1: Jan 1-15
        import1_messages = [
            {"message_id": "wa_1", "timestamp": "2025-01-05T10:00:00", "sender": "Alice", "content": "Message 1", "is_system": False},
            {"message_id": "wa_2", "timestamp": "2025-01-10T10:00:00", "sender": "Bob", "content": "Message 2", "is_system": False},
            {"message_id": "wa_3", "timestamp": "2025-01-12T10:00:00", "sender": "Alice", "content": "Message 3", "is_system": False},
        ]
        with open(imports_dir / "imp_001_messages.json", "w") as f:
            json.dump(import1_messages, f)

        # Import 2: Jan 10-20 (overlaps Jan 10-15)
        import2_messages = [
            {"message_id": "wa_2", "timestamp": "2025-01-10T10:00:00", "sender": "Bob", "content": "Message 2", "is_system": False},  # DUPLICATE
            {"message_id": "wa_3", "timestamp": "2025-01-12T10:00:00", "sender": "Alice", "content": "Message 3", "is_system": False},  # DUPLICATE
            {"message_id": "wa_4", "timestamp": "2025-01-18T10:00:00", "sender": "Charlie", "content": "Message 4", "is_system": False},
        ]
        with open(imports_dir / "imp_002_messages.json", "w") as f:
            json.dump(import2_messages, f)

        return group_id

    @pytest.mark.asyncio
    async def test_deduplicates_overlapping_messages(self, archive_root, setup_overlapping_imports):
        """Messages from overlapping imports should be deduplicated."""
        group_id = setup_overlapping_imports
        importer = WhatsAppImporter(archive_root)

        messages = await importer.get_messages_for_period(
            group_id=group_id,
            start=datetime(2025, 1, 1),
            end=datetime(2025, 1, 31),
        )

        # Should have 4 unique messages, not 6
        assert len(messages) == 4

        # Verify content
        contents = [m["content"] for m in messages]
        assert contents == ["Message 1", "Message 2", "Message 3", "Message 4"]

    @pytest.mark.asyncio
    async def test_preserves_order_after_dedup(self, archive_root, setup_overlapping_imports):
        """Messages should be sorted by timestamp after deduplication."""
        group_id = setup_overlapping_imports
        importer = WhatsAppImporter(archive_root)

        messages = await importer.get_messages_for_period(
            group_id=group_id,
            start=datetime(2025, 1, 1),
            end=datetime(2025, 1, 31),
        )

        timestamps = [m["timestamp"] for m in messages]
        assert timestamps == sorted(timestamps)

    @pytest.mark.asyncio
    async def test_no_messages_when_group_not_found(self, archive_root):
        """Should return empty list when group doesn't exist."""
        importer = WhatsAppImporter(archive_root)

        messages = await importer.get_messages_for_period(
            group_id="nonexistent",
            start=datetime(2025, 1, 1),
            end=datetime(2025, 1, 31),
        )

        assert messages == []
