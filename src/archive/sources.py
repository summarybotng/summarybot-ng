"""
Platform-agnostic source registry and management.

Provides a unified interface for managing sources across Discord, WhatsApp,
Slack, and Telegram platforms.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from .models import (
    SourceType,
    ArchiveSource,
    SourceManifest,
    ArchiveManifest,
)

logger = logging.getLogger(__name__)


class SourceRegistry:
    """
    Registry for managing archive sources across platforms.

    Handles source registration, manifest management, and provides
    a unified interface for querying sources.
    """

    def __init__(self, archive_root: Path):
        """
        Initialize the source registry.

        Args:
            archive_root: Root path of the archive
        """
        self.archive_root = archive_root
        self._sources: Dict[str, ArchiveSource] = {}
        self._manifests: Dict[str, SourceManifest] = {}

    def register_source(self, source: ArchiveSource) -> None:
        """
        Register a new source.

        Args:
            source: Source to register
        """
        key = source.source_key
        self._sources[key] = source
        logger.info(f"Registered source: {key}")

    def get_source(self, source_key: str) -> Optional[ArchiveSource]:
        """
        Get a source by its key.

        Args:
            source_key: Source key (e.g., "discord:123456789")

        Returns:
            Source if found, None otherwise
        """
        return self._sources.get(source_key)

    def list_sources(
        self,
        source_type: Optional[SourceType] = None
    ) -> List[ArchiveSource]:
        """
        List all registered sources.

        Args:
            source_type: Optional filter by source type

        Returns:
            List of sources
        """
        sources = list(self._sources.values())
        if source_type:
            sources = [s for s in sources if s.source_type == source_type]
        return sources

    def get_manifest(self, source_key: str) -> Optional[SourceManifest]:
        """
        Get the manifest for a source.

        Args:
            source_key: Source key

        Returns:
            Source manifest if found
        """
        if source_key in self._manifests:
            return self._manifests[source_key]

        # Try to load from disk
        source = self._sources.get(source_key)
        if not source:
            return None

        manifest_path = self._get_manifest_path(source)
        if manifest_path.exists():
            manifest = self._load_manifest(manifest_path, source)
            self._manifests[source_key] = manifest
            return manifest

        return None

    def save_manifest(self, source_key: str, manifest: SourceManifest) -> None:
        """
        Save a source manifest.

        Args:
            source_key: Source key
            manifest: Manifest to save
        """
        source = self._sources.get(source_key)
        if not source:
            raise ValueError(f"Source not found: {source_key}")

        manifest_path = self._get_manifest_path(source)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest.save(manifest_path)
        self._manifests[source_key] = manifest
        logger.info(f"Saved manifest for {source_key}")

    def create_source_from_discord(
        self,
        guild_id: str,
        guild_name: str,
        channel_id: Optional[str] = None,
        channel_name: Optional[str] = None
    ) -> ArchiveSource:
        """
        Create and register a Discord source.

        Args:
            guild_id: Discord guild ID
            guild_name: Guild name
            channel_id: Optional channel ID
            channel_name: Optional channel name

        Returns:
            Created source
        """
        source = ArchiveSource(
            source_type=SourceType.DISCORD,
            server_id=guild_id,
            server_name=guild_name,
            channel_id=channel_id,
            channel_name=channel_name,
        )
        self.register_source(source)
        return source

    def create_source_from_whatsapp(
        self,
        group_id: str,
        group_name: str
    ) -> ArchiveSource:
        """
        Create and register a WhatsApp source.

        Args:
            group_id: WhatsApp group ID
            group_name: Group name

        Returns:
            Created source
        """
        source = ArchiveSource(
            source_type=SourceType.WHATSAPP,
            server_id=group_id,
            server_name=group_name,
        )
        self.register_source(source)
        return source

    def create_source_from_slack(
        self,
        workspace_id: str,
        workspace_name: str,
        channel_id: Optional[str] = None,
        channel_name: Optional[str] = None
    ) -> ArchiveSource:
        """
        Create and register a Slack source.

        Args:
            workspace_id: Slack workspace ID
            workspace_name: Workspace name
            channel_id: Optional channel ID
            channel_name: Optional channel name

        Returns:
            Created source
        """
        source = ArchiveSource(
            source_type=SourceType.SLACK,
            server_id=workspace_id,
            server_name=workspace_name,
            channel_id=channel_id,
            channel_name=channel_name,
        )
        self.register_source(source)
        return source

    def create_source_from_telegram(
        self,
        chat_id: str,
        chat_name: str
    ) -> ArchiveSource:
        """
        Create and register a Telegram source.

        Args:
            chat_id: Telegram chat ID
            chat_name: Chat name

        Returns:
            Created source
        """
        source = ArchiveSource(
            source_type=SourceType.TELEGRAM,
            server_id=chat_id,
            server_name=chat_name,
        )
        self.register_source(source)
        return source

    def discover_sources(self) -> List[ArchiveSource]:
        """
        Discover existing sources from archive directory structure.

        Returns:
            List of discovered sources
        """
        discovered = []
        sources_path = self.archive_root / "sources"

        if not sources_path.exists():
            return discovered

        for source_type_dir in sources_path.iterdir():
            if not source_type_dir.is_dir():
                continue

            try:
                source_type = SourceType(source_type_dir.name)
            except ValueError:
                logger.warning(f"Unknown source type directory: {source_type_dir.name}")
                continue

            for server_dir in source_type_dir.iterdir():
                if not server_dir.is_dir():
                    continue

                # Parse folder name: {server_name}_{server_id}
                folder_name = server_dir.name
                if '_' not in folder_name:
                    continue

                # Find the last underscore (ID is always last)
                last_underscore = folder_name.rfind('_')
                server_name = folder_name[:last_underscore]
                server_id = folder_name[last_underscore + 1:]

                # Check for channels subdirectory
                channels_dir = server_dir / "channels"
                if channels_dir.exists():
                    for channel_dir in channels_dir.iterdir():
                        if not channel_dir.is_dir():
                            continue

                        channel_folder = channel_dir.name
                        if '_' in channel_folder:
                            last_us = channel_folder.rfind('_')
                            channel_name = channel_folder[:last_us]
                            channel_id = channel_folder[last_us + 1:]

                            source = ArchiveSource(
                                source_type=source_type,
                                server_id=server_id,
                                server_name=server_name,
                                channel_id=channel_id,
                                channel_name=channel_name,
                            )
                            self.register_source(source)
                            discovered.append(source)
                else:
                    # Single-channel source (e.g., WhatsApp)
                    source = ArchiveSource(
                        source_type=source_type,
                        server_id=server_id,
                        server_name=server_name,
                    )
                    self.register_source(source)
                    discovered.append(source)

        logger.info(f"Discovered {len(discovered)} sources from archive")
        return discovered

    def get_archive_manifest(self) -> ArchiveManifest:
        """
        Get or create the global archive manifest.

        Returns:
            Archive manifest
        """
        manifest_path = self.archive_root / "manifest.json"

        if manifest_path.exists():
            return ArchiveManifest.load(manifest_path)

        # Create new manifest
        manifest = ArchiveManifest()
        return manifest

    def save_archive_manifest(self, manifest: ArchiveManifest) -> None:
        """
        Save the global archive manifest.

        Args:
            manifest: Manifest to save
        """
        manifest.last_updated = datetime.utcnow()
        manifest_path = self.archive_root / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest.save(manifest_path)

    def update_archive_manifest(self) -> None:
        """
        Update the global archive manifest with current source info.
        """
        manifest = self.get_archive_manifest()
        manifest.sources = []

        for source in self._sources.values():
            source_info = {
                "source_type": source.source_type.value,
                "server_id": source.server_id,
                "server_name": source.server_name,
                "folder": f"{source.source_type.value}/{source.folder_name}",
            }

            # Count summaries if directory exists
            archive_path = source.get_archive_path(self.archive_root)
            if archive_path.exists():
                summary_count = len(list(archive_path.glob("**/*.md")))
                source_info["summary_count"] = summary_count

            manifest.sources.append(source_info)

        self.save_archive_manifest(manifest)

    def _get_manifest_path(self, source: ArchiveSource) -> Path:
        """Get the manifest path for a source."""
        base = self.archive_root / "sources" / source.source_type.value / source.folder_name

        if source.source_type == SourceType.DISCORD:
            return base / "server-manifest.json"
        elif source.source_type == SourceType.WHATSAPP:
            return base / "group-manifest.json"
        elif source.source_type == SourceType.SLACK:
            return base / "workspace-manifest.json"
        else:
            return base / "chat-manifest.json"

    def _load_manifest(self, path: Path, source: ArchiveSource) -> SourceManifest:
        """Load a source manifest from disk."""
        import json
        with open(path, 'r') as f:
            data = json.load(f)

        cost_tracking = data.get("cost_tracking", {})
        api_keys = data.get("api_keys", {})
        prompt_versions = data.get("prompt_versions", {})
        current_prompt = prompt_versions.get("current", {})

        return SourceManifest(
            source_type=SourceType(data["source_type"]),
            server_id=data["server_id"],
            server_name=data["server_name"],
            default_timezone=data.get("default_timezone", "UTC"),
            default_granularity=data.get("default_granularity", "daily"),
            prompt_version_current=current_prompt.get("version"),
            prompt_checksum_current=current_prompt.get("checksum"),
            prompt_updated_at=datetime.fromisoformat(current_prompt["updated_at"]) if current_prompt.get("updated_at") else None,
            cost_tracking_enabled=cost_tracking.get("enabled", True),
            budget_monthly_usd=cost_tracking.get("budget_monthly_usd"),
            alert_threshold_percent=cost_tracking.get("alert_threshold_percent", 80),
            priority=cost_tracking.get("priority", 2),
            openrouter_key_ref=api_keys.get("openrouter_key_ref"),
            use_server_key=api_keys.get("use_server_key", False),
            fallback_to_default=api_keys.get("fallback_to_default", True),
        )
