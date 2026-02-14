"""
Retrospective Summary Archive module.

Provides historical backfill, cost tracking, and portable Markdown archives
for Discord, WhatsApp, Slack, and Telegram summaries.

Implements ADR-006: Retrospective Summary Archive.
"""

from .models import (
    SourceType,
    ArchiveSource,
    ArchiveManifest,
    SourceManifest,
    SummaryMetadata,
    SummaryStatistics,
    SummaryStatus,
    GenerationInfo,
    GenerationLock,
    PeriodInfo,
    BackfillInfo,
    IncompleteInfo,
    CostEntry,
)
from .sources import SourceRegistry
from .cost_tracker import CostTracker, PricingTable, CostEstimate
from .locking import LockManager
from .writer import SummaryWriter, get_summary_path, summary_exists
from .api_keys import ApiKeyResolver, ResolvedKey, KeyStatus
from .scanner import ArchiveScanner, ScanResult, GapInfo
from .backfill import BackfillManager, BackfillJob, BackfillReport
from .retention import RetentionManager, RetentionConfig
from .generator import RetrospectiveGenerator, GenerationJob
from .importers.whatsapp import WhatsAppImporter, WhatsAppImportResult
from .sync import SyncProvider, GoogleDriveSync, GoogleDriveConfig

__all__ = [
    # Models
    "SourceType",
    "ArchiveSource",
    "ArchiveManifest",
    "SourceManifest",
    "SummaryMetadata",
    "SummaryStatistics",
    "SummaryStatus",
    "GenerationInfo",
    "GenerationLock",
    "PeriodInfo",
    "BackfillInfo",
    "IncompleteInfo",
    "CostEntry",
    # Registry
    "SourceRegistry",
    # Cost tracking
    "CostTracker",
    "PricingTable",
    "CostEstimate",
    # Locking
    "LockManager",
    # Writer
    "SummaryWriter",
    "get_summary_path",
    "summary_exists",
    # API Keys
    "ApiKeyResolver",
    "ResolvedKey",
    "KeyStatus",
    # Scanner
    "ArchiveScanner",
    "ScanResult",
    "GapInfo",
    # Backfill
    "BackfillManager",
    "BackfillJob",
    "BackfillReport",
    # Retention
    "RetentionManager",
    "RetentionConfig",
    # Generator
    "RetrospectiveGenerator",
    "GenerationJob",
    # Importers
    "WhatsAppImporter",
    "WhatsAppImportResult",
    # Sync
    "SyncProvider",
    "GoogleDriveSync",
    "GoogleDriveConfig",
]
