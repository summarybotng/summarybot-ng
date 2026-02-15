"""
Archive sync service.

ADR-007: Per-server Google Drive sync with fallback.
- Phase 1: Global fallback from environment variables
- Phase 2: Per-server OAuth configuration
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import SyncConfig, SyncResult, SyncStatus
from .google_drive import GoogleDriveSync, GoogleDriveConfig

logger = logging.getLogger(__name__)


@dataclass
class ServerSyncConfig:
    """Per-server sync configuration (stored in server-manifest.json)."""
    enabled: bool = False
    folder_id: str = ""
    folder_name: str = ""
    oauth_token_id: str = ""
    configured_by: str = ""
    configured_at: Optional[datetime] = None
    last_sync: Optional[datetime] = None
    sync_on_generation: bool = True
    include_metadata: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "folder_id": self.folder_id,
            "folder_name": self.folder_name,
            "oauth_token_id": self.oauth_token_id,
            "configured_by": self.configured_by,
            "configured_at": self.configured_at.isoformat() if self.configured_at else None,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "sync_on_generation": self.sync_on_generation,
            "include_metadata": self.include_metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServerSyncConfig":
        configured_at = None
        if data.get("configured_at"):
            configured_at = datetime.fromisoformat(data["configured_at"])
        last_sync = None
        if data.get("last_sync"):
            last_sync = datetime.fromisoformat(data["last_sync"])

        return cls(
            enabled=data.get("enabled", False),
            folder_id=data.get("folder_id", ""),
            folder_name=data.get("folder_name", ""),
            oauth_token_id=data.get("oauth_token_id", ""),
            configured_by=data.get("configured_by", ""),
            configured_at=configured_at,
            last_sync=last_sync,
            sync_on_generation=data.get("sync_on_generation", True),
            include_metadata=data.get("include_metadata", True),
        )


@dataclass
class GlobalSyncConfig:
    """Global sync configuration from environment variables."""
    enabled: bool = False
    folder_id: str = ""
    credentials_path: str = ""
    create_server_subfolders: bool = True
    subfolder_naming: str = "{server_name}_{server_id}"
    sync_on_generation: bool = True
    sync_frequency: str = "on_generation"  # "on_generation", "hourly", "daily"

    @classmethod
    def from_env(cls) -> "GlobalSyncConfig":
        """Load configuration from environment variables."""
        return cls(
            enabled=os.environ.get("ARCHIVE_GOOGLE_DRIVE_ENABLED", "").lower() == "true",
            folder_id=os.environ.get("ARCHIVE_GOOGLE_DRIVE_FOLDER_ID", ""),
            credentials_path=os.environ.get("ARCHIVE_GOOGLE_DRIVE_CREDENTIALS_PATH", ""),
            create_server_subfolders=os.environ.get(
                "ARCHIVE_GOOGLE_DRIVE_CREATE_SUBFOLDERS", "true"
            ).lower() == "true",
            subfolder_naming=os.environ.get(
                "ARCHIVE_GOOGLE_DRIVE_SUBFOLDER_NAMING",
                "{server_name}_{server_id}"
            ),
            sync_on_generation=os.environ.get(
                "ARCHIVE_SYNC_ON_GENERATION", "true"
            ).lower() == "true",
            sync_frequency=os.environ.get("ARCHIVE_SYNC_FREQUENCY", "on_generation"),
        )

    def is_configured(self) -> bool:
        """Check if sync is properly configured."""
        return (
            self.enabled
            and bool(self.folder_id)
            and bool(self.credentials_path)
            and Path(self.credentials_path).exists()
        )


@dataclass
class SyncState:
    """Current state of sync for a source."""
    source_key: str
    last_sync: Optional[datetime] = None
    last_status: SyncStatus = SyncStatus.PENDING
    files_synced: int = 0
    total_bytes: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_key": self.source_key,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "last_status": self.last_status.value,
            "files_synced": self.files_synced,
            "total_bytes": self.total_bytes,
            "errors": self.errors[:5],  # Limit to last 5 errors
        }


class ArchiveSyncService:
    """
    Service for managing archive sync to Google Drive.

    Handles:
    - Global fallback configuration from environment
    - Per-source sync state tracking
    - Auto-sync after summary generation
    - Manual sync triggers
    """

    def __init__(self, archive_root: Path):
        """
        Initialize sync service.

        Args:
            archive_root: Root path of the archive
        """
        self.archive_root = archive_root
        self.config = GlobalSyncConfig.from_env()
        self._sync_states: Dict[str, SyncState] = {}
        self._provider: Optional[GoogleDriveSync] = None
        self._folder_cache: Dict[str, str] = {}
        self._lock = asyncio.Lock()

        logger.info(
            f"ArchiveSyncService initialized: enabled={self.config.enabled}, "
            f"configured={self.config.is_configured()}"
        )

    def is_enabled(self) -> bool:
        """Check if sync is enabled and configured."""
        return self.config.is_configured()

    def get_status(self) -> Dict[str, Any]:
        """Get overall sync service status."""
        return {
            "enabled": self.config.enabled,
            "configured": self.config.is_configured(),
            "folder_id": self.config.folder_id[:10] + "..." if self.config.folder_id else None,
            "sync_on_generation": self.config.sync_on_generation,
            "sync_frequency": self.config.sync_frequency,
            "create_subfolders": self.config.create_server_subfolders,
            "sources_synced": len(self._sync_states),
        }

    def get_source_status(self, source_key: str) -> Optional[Dict[str, Any]]:
        """Get sync status for a specific source."""
        state = self._sync_states.get(source_key)
        return state.to_dict() if state else None

    def list_sync_states(self) -> List[Dict[str, Any]]:
        """List all sync states."""
        return [state.to_dict() for state in self._sync_states.values()]

    async def _get_provider(self) -> Optional[GoogleDriveSync]:
        """Get or create the Google Drive sync provider."""
        if not self.config.is_configured():
            return None

        if self._provider is None:
            drive_config = GoogleDriveConfig(
                enabled=True,
                folder_id=self.config.folder_id,
                credentials_path=self.config.credentials_path,
                create_folders=True,
                preserve_structure=True,
            )
            self._provider = GoogleDriveSync(drive_config)

        return self._provider

    async def _get_or_create_subfolder(
        self,
        provider: GoogleDriveSync,
        server_name: str,
        server_id: str,
        source_type: str,
    ) -> str:
        """Get or create a server-specific subfolder."""
        if not self.config.create_server_subfolders:
            return self.config.folder_id

        # Generate subfolder name
        subfolder_name = self.config.subfolder_naming.format(
            server_name=self._sanitize_folder_name(server_name),
            server_id=server_id,
            source_type=source_type,
        )

        cache_key = f"{self.config.folder_id}/{subfolder_name}"
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]

        try:
            service = await provider._get_service()

            # Check if folder exists
            query = (
                f"name='{subfolder_name}' and "
                f"'{self.config.folder_id}' in parents and "
                f"mimeType='application/vnd.google-apps.folder' and "
                f"trashed=false"
            )
            response = service.files().list(
                q=query,
                spaces='drive',
                fields='files(id)'
            ).execute()

            files = response.get('files', [])

            if files:
                folder_id = files[0]['id']
            else:
                # Create folder
                file_metadata = {
                    'name': subfolder_name,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [self.config.folder_id]
                }
                folder = service.files().create(
                    body=file_metadata,
                    fields='id'
                ).execute()
                folder_id = folder['id']
                logger.info(f"Created server subfolder: {subfolder_name}")

            self._folder_cache[cache_key] = folder_id
            return folder_id

        except Exception as e:
            logger.error(f"Failed to create subfolder {subfolder_name}: {e}")
            return self.config.folder_id

    def _sanitize_folder_name(self, name: str) -> str:
        """Sanitize a name for use as a folder name."""
        # Remove characters not allowed in folder names
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '_')
        # Limit length
        return name[:50]

    async def sync_source(
        self,
        source_key: str,
        source_path: Path,
        server_name: str = "",
    ) -> SyncResult:
        """
        Sync a source's archive to Google Drive.

        Args:
            source_key: Source identifier (e.g., "discord:123456789")
            source_path: Local path to the source's archive
            server_name: Server name for subfolder creation

        Returns:
            Sync result
        """
        async with self._lock:
            # Initialize state if needed
            if source_key not in self._sync_states:
                self._sync_states[source_key] = SyncState(source_key=source_key)

            state = self._sync_states[source_key]

            provider = await self._get_provider()
            if not provider:
                result = SyncResult(
                    status=SyncStatus.FAILED,
                    errors=["Google Drive sync not configured"]
                )
                state.last_status = SyncStatus.FAILED
                state.errors = result.errors
                return result

            try:
                # Parse source key
                parts = source_key.split(":")
                source_type = parts[0] if parts else "unknown"
                server_id = parts[1] if len(parts) > 1 else ""

                # Get target folder (with subfolder if configured)
                target_folder_id = await self._get_or_create_subfolder(
                    provider,
                    server_name or server_id,
                    server_id,
                    source_type,
                )

                # Create a config for this specific sync
                sync_config = GoogleDriveConfig(
                    enabled=True,
                    folder_id=target_folder_id,
                    credentials_path=self.config.credentials_path,
                    create_folders=True,
                    preserve_structure=True,
                )

                # Create provider with target folder
                sync_provider = GoogleDriveSync(sync_config)
                result = await sync_provider.sync(source_path)

                # Update state
                state.last_sync = datetime.utcnow()
                state.last_status = result.status
                state.files_synced = result.files_synced
                state.total_bytes += result.bytes_uploaded
                if result.errors:
                    state.errors = result.errors

                logger.info(
                    f"Sync completed for {source_key}: "
                    f"status={result.status.value}, files={result.files_synced}"
                )

                return result

            except Exception as e:
                logger.error(f"Sync failed for {source_key}: {e}")
                result = SyncResult(
                    status=SyncStatus.FAILED,
                    errors=[str(e)]
                )
                state.last_status = SyncStatus.FAILED
                state.errors = [str(e)]
                return result

    async def sync_all(self) -> Dict[str, SyncResult]:
        """
        Sync all discovered sources.

        Returns:
            Results by source key
        """
        results = {}
        sources_dir = self.archive_root / "sources"

        if not sources_dir.exists():
            return results

        for source_type_dir in sources_dir.iterdir():
            if not source_type_dir.is_dir():
                continue

            source_type = source_type_dir.name

            for server_dir in source_type_dir.iterdir():
                if not server_dir.is_dir():
                    continue

                # Parse folder name
                folder_name = server_dir.name
                if '_' not in folder_name:
                    continue

                last_underscore = folder_name.rfind('_')
                server_name = folder_name[:last_underscore]
                server_id = folder_name[last_underscore + 1:]

                source_key = f"{source_type}:{server_id}"
                result = await self.sync_source(
                    source_key=source_key,
                    source_path=server_dir,
                    server_name=server_name,
                )
                results[source_key] = result

        return results

    async def get_drive_status(self) -> Dict[str, Any]:
        """Get Google Drive quota and status."""
        provider = await self._get_provider()
        if not provider:
            return {
                "connected": False,
                "error": "Google Drive sync not configured",
            }

        try:
            status = await provider.get_status()
            status["connected"] = True
            return status
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
            }

    # ==================== Per-Server Configuration (Phase 2) ====================

    def _get_manifest_path(self, source_type: str, server_id: str) -> Path:
        """Get path to server manifest file."""
        sources_dir = self.archive_root / "sources" / source_type

        # Find the server directory
        if sources_dir.exists():
            for d in sources_dir.iterdir():
                if d.is_dir() and d.name.endswith(f"_{server_id}"):
                    return d / "server-manifest.json"

        # Create default path
        return sources_dir / f"unknown_{server_id}" / "server-manifest.json"

    async def get_server_config(self, server_id: str, source_type: str = "discord") -> Optional[ServerSyncConfig]:
        """
        Get sync configuration for a server.

        Args:
            server_id: Discord server ID
            source_type: Source type (default: discord)

        Returns:
            Server sync config if configured
        """
        manifest_path = self._get_manifest_path(source_type, server_id)

        if not manifest_path.exists():
            return None

        try:
            with open(manifest_path, 'r') as f:
                data = json.load(f)

            sync_data = data.get("sync", {}).get("google_drive", {})
            if not sync_data:
                return None

            return ServerSyncConfig.from_dict(sync_data)

        except Exception as e:
            logger.error(f"Failed to load server config for {server_id}: {e}")
            return None

    async def save_server_config(
        self,
        server_id: str,
        config: ServerSyncConfig,
        source_type: str = "discord"
    ) -> bool:
        """
        Save sync configuration for a server.

        Args:
            server_id: Discord server ID
            config: Sync configuration
            source_type: Source type (default: discord)

        Returns:
            True if saved successfully
        """
        manifest_path = self._get_manifest_path(source_type, server_id)

        try:
            # Load existing manifest or create new
            manifest_path.parent.mkdir(parents=True, exist_ok=True)

            data = {}
            if manifest_path.exists():
                with open(manifest_path, 'r') as f:
                    data = json.load(f)

            # Update sync config
            if "sync" not in data:
                data["sync"] = {}
            data["sync"]["google_drive"] = config.to_dict()

            # Write back
            with open(manifest_path, 'w') as f:
                json.dump(data, f, indent=2)

            logger.info(f"Saved server sync config for {server_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to save server config for {server_id}: {e}")
            return False

    async def delete_server_config(self, server_id: str, source_type: str = "discord") -> bool:
        """
        Delete sync configuration for a server.

        Args:
            server_id: Discord server ID
            source_type: Source type

        Returns:
            True if deleted
        """
        manifest_path = self._get_manifest_path(source_type, server_id)

        if not manifest_path.exists():
            return False

        try:
            with open(manifest_path, 'r') as f:
                data = json.load(f)

            if "sync" in data and "google_drive" in data["sync"]:
                del data["sync"]["google_drive"]

                with open(manifest_path, 'w') as f:
                    json.dump(data, f, indent=2)

                logger.info(f"Deleted server sync config for {server_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to delete server config for {server_id}: {e}")
            return False

    async def resolve_sync_config(
        self,
        server_id: str,
        source_type: str = "discord"
    ) -> tuple[Optional[GoogleDriveConfig], str]:
        """
        Resolve which sync config to use (server-specific or fallback).

        Args:
            server_id: Discord server ID
            source_type: Source type

        Returns:
            Tuple of (GoogleDriveConfig, config_source) where config_source is
            "server", "fallback", or "none"
        """
        # Check server-specific config first
        server_config = await self.get_server_config(server_id, source_type)

        if server_config and server_config.enabled:
            # Get OAuth tokens for this server
            from .oauth import get_oauth_flow

            oauth_flow = get_oauth_flow(self.archive_root)
            tokens = await oauth_flow.get_valid_tokens(server_config.oauth_token_id)

            if tokens:
                # Create a custom Google Drive sync with OAuth
                return GoogleDriveConfig(
                    enabled=True,
                    folder_id=server_config.folder_id,
                    credentials_path="",  # Not needed for OAuth
                    create_folders=True,
                    preserve_structure=True,
                ), "server"

        # Fall back to global config
        if self.config.is_configured():
            return GoogleDriveConfig(
                enabled=True,
                folder_id=self.config.folder_id,
                credentials_path=self.config.credentials_path,
                create_folders=True,
                preserve_structure=True,
            ), "fallback"

        return None, "none"

    async def is_server_configured(self, server_id: str, source_type: str = "discord") -> bool:
        """Check if a server has custom sync configuration."""
        config = await self.get_server_config(server_id, source_type)
        return config is not None and config.enabled

    async def list_configured_servers(self) -> List[Dict[str, Any]]:
        """List all servers with custom sync configuration."""
        servers = []
        sources_dir = self.archive_root / "sources"

        if not sources_dir.exists():
            return servers

        for source_type_dir in sources_dir.iterdir():
            if not source_type_dir.is_dir():
                continue

            source_type = source_type_dir.name

            for server_dir in source_type_dir.iterdir():
                if not server_dir.is_dir():
                    continue

                manifest_path = server_dir / "server-manifest.json"
                if manifest_path.exists():
                    try:
                        with open(manifest_path, 'r') as f:
                            data = json.load(f)

                        sync_config = data.get("sync", {}).get("google_drive", {})
                        if sync_config.get("enabled"):
                            folder_name = server_dir.name
                            last_underscore = folder_name.rfind('_')
                            server_name = folder_name[:last_underscore] if last_underscore > 0 else folder_name
                            server_id = folder_name[last_underscore + 1:] if last_underscore > 0 else ""

                            servers.append({
                                "server_id": server_id,
                                "server_name": server_name,
                                "source_type": source_type,
                                "folder_name": sync_config.get("folder_name", ""),
                                "configured_at": sync_config.get("configured_at"),
                                "last_sync": sync_config.get("last_sync"),
                            })

                    except Exception:
                        pass

        return servers


# Singleton instance
_sync_service: Optional[ArchiveSyncService] = None


def get_sync_service(archive_root: Path) -> ArchiveSyncService:
    """Get or create the sync service singleton."""
    global _sync_service
    if _sync_service is None:
        _sync_service = ArchiveSyncService(archive_root)
    return _sync_service
