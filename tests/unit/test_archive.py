"""
Tests for the archive module.

Tests core functionality of ADR-006: Retrospective Summary Archive.
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import json

from src.archive import (
    SourceType,
    ArchiveSource,
    SourceRegistry,
    PeriodInfo,
    SummaryStatistics,
    GenerationInfo,
    SummaryWriter,
    CostTracker,
    PricingTable,
    CostEntry,
    LockManager,
    SummaryStatus,
)


class TestArchiveSource:
    """Tests for ArchiveSource model."""

    def test_discord_source_key(self):
        source = ArchiveSource(
            source_type=SourceType.DISCORD,
            server_id="123456789",
            server_name="My Community",
            channel_id="987654321",
            channel_name="general",
        )
        assert source.source_key == "discord:123456789"

    def test_whatsapp_source_key(self):
        source = ArchiveSource(
            source_type=SourceType.WHATSAPP,
            server_id="group_abc123",
            server_name="Family Chat",
        )
        assert source.source_key == "whatsapp:group_abc123"

    def test_folder_name_sanitization(self):
        source = ArchiveSource(
            source_type=SourceType.DISCORD,
            server_id="123",
            server_name="My Server! (Test)",
        )
        # Should sanitize special characters
        assert "_" not in source.folder_name or source.folder_name.endswith("_123")

    def test_archive_path_with_channel(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_root = Path(tmpdir)
            source = ArchiveSource(
                source_type=SourceType.DISCORD,
                server_id="123",
                server_name="server",
                channel_id="456",
                channel_name="general",
            )
            path = source.get_archive_path(archive_root)
            assert "channels" in str(path)
            assert "summaries" in str(path)

    def test_archive_path_without_channel(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_root = Path(tmpdir)
            source = ArchiveSource(
                source_type=SourceType.WHATSAPP,
                server_id="group_123",
                server_name="family",
            )
            path = source.get_archive_path(archive_root)
            assert "channels" not in str(path)
            assert "summaries" in str(path)

    def test_serialization_roundtrip(self):
        source = ArchiveSource(
            source_type=SourceType.SLACK,
            server_id="T01ABC",
            server_name="Workspace",
            channel_id="C01XYZ",
            channel_name="engineering",
        )
        data = source.to_dict()
        restored = ArchiveSource.from_dict(data)
        assert restored.source_key == source.source_key
        assert restored.channel_id == source.channel_id


class TestSourceRegistry:
    """Tests for SourceRegistry."""

    def test_register_and_get_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = SourceRegistry(Path(tmpdir))
            source = ArchiveSource(
                source_type=SourceType.DISCORD,
                server_id="123",
                server_name="test",
            )
            registry.register_source(source)

            retrieved = registry.get_source("discord:123")
            assert retrieved is not None
            assert retrieved.server_name == "test"

    def test_list_sources_by_type(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = SourceRegistry(Path(tmpdir))

            registry.create_source_from_discord("1", "Discord 1")
            registry.create_source_from_discord("2", "Discord 2")
            registry.create_source_from_whatsapp("3", "WhatsApp 1")

            discord_sources = registry.list_sources(SourceType.DISCORD)
            assert len(discord_sources) == 2

            whatsapp_sources = registry.list_sources(SourceType.WHATSAPP)
            assert len(whatsapp_sources) == 1


class TestPeriodInfo:
    """Tests for PeriodInfo model."""

    def test_period_serialization(self):
        period = PeriodInfo(
            start=datetime(2026, 2, 14, 0, 0),
            end=datetime(2026, 2, 14, 23, 59, 59),
            timezone="America/New_York",
            duration_hours=24,
            dst_transition=None,
        )
        data = period.to_dict()
        restored = PeriodInfo.from_dict(data)
        assert restored.timezone == "America/New_York"
        assert restored.duration_hours == 24

    def test_dst_transition_spring(self):
        period = PeriodInfo(
            start=datetime(2026, 3, 8, 0, 0),
            end=datetime(2026, 3, 8, 23, 59, 59),
            timezone="America/New_York",
            duration_hours=23,
            dst_transition="spring_forward",
        )
        assert period.dst_transition == "spring_forward"


class TestCostTracker:
    """Tests for CostTracker."""

    def test_record_and_retrieve_cost(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "cost-ledger.json"
            tracker = CostTracker(ledger_path)

            entry = CostEntry(
                source_key="discord:123",
                summary_id="sum_abc",
                timestamp=datetime.utcnow(),
                model="anthropic/claude-3-haiku",
                tokens_input=1000,
                tokens_output=200,
                cost_usd=0.0015,
                pricing_version="2026-02-01",
            )
            tracker.record_cost(entry)

            source_cost = tracker.get_source_cost("discord:123")
            assert source_cost is not None
            assert source_cost.total_cost_usd > 0

    def test_cost_estimate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "cost-ledger.json"
            tracker = CostTracker(ledger_path)

            estimate = tracker.estimate_backfill_cost(
                source_key="discord:123",
                periods=30,
                model="anthropic/claude-3-haiku",
            )
            assert estimate.periods == 30
            assert estimate.estimated_cost_usd > 0


class TestPricingTable:
    """Tests for PricingTable."""

    def test_static_pricing_lookup(self):
        pricing = PricingTable()
        input_rate, output_rate, version = pricing.get_pricing("anthropic/claude-3-haiku")
        assert input_rate > 0
        assert output_rate > 0

    def test_cost_calculation(self):
        pricing = PricingTable()
        cost, version = pricing.calculate_cost(
            model="anthropic/claude-3-haiku",
            tokens_input=1000,
            tokens_output=200,
        )
        # Haiku: 0.00025 input, 0.00125 output per 1k
        # Expected: (1000/1000 * 0.00025) + (200/1000 * 0.00125) = 0.0005
        assert cost > 0
        assert cost < 0.01  # Sanity check


class TestLockManager:
    """Tests for LockManager."""

    @pytest.mark.asyncio
    async def test_acquire_and_release_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_path = Path(tmpdir) / "test.meta.json"
            lock_manager = LockManager(lock_ttl_seconds=60)

            # Acquire lock
            job_id = await lock_manager.acquire_lock(meta_path)
            assert job_id is not None

            # Verify lock exists
            lock = await lock_manager.check_lock(meta_path)
            assert lock is not None
            assert lock.job_id == job_id

            # Release lock
            await lock_manager.release_lock(meta_path, SummaryStatus.COMPLETE)

            # Lock should be gone
            lock = await lock_manager.check_lock(meta_path)
            assert lock is None

    @pytest.mark.asyncio
    async def test_lock_prevents_double_acquisition(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_path = Path(tmpdir) / "test.meta.json"
            lock_manager = LockManager(lock_ttl_seconds=60)

            # First acquire succeeds
            job1 = await lock_manager.acquire_lock(meta_path)
            assert job1 is not None

            # Second acquire fails
            job2 = await lock_manager.acquire_lock(meta_path)
            assert job2 is None

    @pytest.mark.asyncio
    async def test_expired_lock_can_be_taken(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_path = Path(tmpdir) / "test.meta.json"
            lock_manager = LockManager(lock_ttl_seconds=1)  # 1 second TTL

            # Acquire lock
            job1 = await lock_manager.acquire_lock(meta_path)
            assert job1 is not None

            # Wait for expiration
            import asyncio
            await asyncio.sleep(1.5)

            # New acquire should succeed
            job2 = await lock_manager.acquire_lock(meta_path)
            assert job2 is not None
            assert job2 != job1


class TestSummaryWriter:
    """Tests for SummaryWriter."""

    def test_write_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_root = Path(tmpdir)
            writer = SummaryWriter(archive_root)

            source = ArchiveSource(
                source_type=SourceType.DISCORD,
                server_id="123",
                server_name="Test Server",
                channel_id="456",
                channel_name="general",
            )

            period = PeriodInfo(
                start=datetime(2026, 2, 14, 0, 0),
                end=datetime(2026, 2, 14, 23, 59, 59),
                timezone="UTC",
            )

            statistics = SummaryStatistics(
                message_count=50,
                participant_count=10,
            )

            generation = GenerationInfo(
                prompt_version="1.0.0",
                prompt_checksum="sha256:abc123",
                model="anthropic/claude-3-haiku",
                options={},
                duration_seconds=2.5,
                tokens_input=1000,
                tokens_output=200,
                cost_usd=0.0015,
                pricing_version="2026-02-01",
                api_key_used="default",
            )

            md_path = writer.write_summary(
                source=source,
                period=period,
                content="## Overview\n\nTest summary content.",
                statistics=statistics,
                generation=generation,
            )

            # Verify file was created
            assert md_path.exists()

            # Verify metadata was created
            meta_path = md_path.with_suffix(".meta.json")
            assert meta_path.exists()

            # Verify content
            content = md_path.read_text()
            assert "Test Server" in content
            assert "Discord" in content

    def test_write_incomplete_marker(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_root = Path(tmpdir)
            writer = SummaryWriter(archive_root)

            source = ArchiveSource(
                source_type=SourceType.WHATSAPP,
                server_id="group_123",
                server_name="Family",
            )

            period = PeriodInfo(
                start=datetime(2026, 2, 14, 0, 0),
                end=datetime(2026, 2, 14, 23, 59, 59),
                timezone="UTC",
            )

            meta_path = writer.write_incomplete_marker(
                source=source,
                period=period,
                reason_code="NO_MESSAGES",
                reason_message="No messages found in this period",
            )

            assert meta_path.exists()

            # Verify content
            with open(meta_path) as f:
                data = json.load(f)

            assert data["status"] == "incomplete"
            assert data["incomplete_reason"]["code"] == "NO_MESSAGES"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
