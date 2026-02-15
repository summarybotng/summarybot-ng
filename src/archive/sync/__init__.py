"""
Archive sync providers.

Supports syncing archives to external storage providers.
ADR-007: Per-server Google Drive sync with fallback.
"""

from .base import SyncProvider, SyncConfig, SyncStatus, SyncResult
from .google_drive import GoogleDriveSync, GoogleDriveConfig
from .service import (
    ArchiveSyncService,
    GlobalSyncConfig,
    ServerSyncConfig,
    get_sync_service,
)
from .oauth import (
    GoogleOAuthFlow,
    SecureTokenStore,
    OAuthTokens,
    get_oauth_flow,
    get_token_store,
)

__all__ = [
    # Base
    "SyncProvider",
    "SyncConfig",
    "SyncStatus",
    "SyncResult",
    # Google Drive
    "GoogleDriveSync",
    "GoogleDriveConfig",
    # Service
    "ArchiveSyncService",
    "GlobalSyncConfig",
    "ServerSyncConfig",
    "get_sync_service",
    # OAuth
    "GoogleOAuthFlow",
    "SecureTokenStore",
    "OAuthTokens",
    "get_oauth_flow",
    "get_token_store",
]
