"""
Google Drive sync provider.

Phase 9: Google Drive Sync
"""

import asyncio
import json
import logging
import mimetypes
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import SyncProvider, SyncConfig, SyncResult, SyncStatus

logger = logging.getLogger(__name__)


@dataclass
class GoogleDriveConfig(SyncConfig):
    """Configuration for Google Drive sync."""
    folder_id: str = ""
    credentials_path: str = ""
    create_folders: bool = True
    preserve_structure: bool = True


class GoogleDriveSync(SyncProvider):
    """
    Google Drive sync provider.

    Syncs archive files to Google Drive using the Google Drive API.
    """

    def __init__(self, config: GoogleDriveConfig):
        """
        Initialize Google Drive sync.

        Args:
            config: Google Drive configuration
        """
        self.config = config
        self._service = None
        self._folder_cache: Dict[str, str] = {}

    async def _get_service(self):
        """Get or create Google Drive service."""
        if self._service is not None:
            return self._service

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            credentials = service_account.Credentials.from_service_account_file(
                self.config.credentials_path,
                scopes=['https://www.googleapis.com/auth/drive.file']
            )

            self._service = build('drive', 'v3', credentials=credentials)
            return self._service

        except ImportError:
            logger.error("Google API libraries not installed. Run: pip install google-api-python-client google-auth")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize Google Drive service: {e}")
            raise

    async def sync(self, source_path: Path) -> SyncResult:
        """
        Sync local files to Google Drive.

        Args:
            source_path: Local path to sync

        Returns:
            Sync result
        """
        result = SyncResult(status=SyncStatus.IN_PROGRESS)

        if not self.config.enabled:
            result.status = SyncStatus.SUCCESS
            return result

        try:
            service = await self._get_service()

            # Get list of local files
            local_files = list(source_path.glob("**/*"))
            local_files = [f for f in local_files if f.is_file()]

            for local_file in local_files:
                try:
                    # Calculate relative path
                    rel_path = local_file.relative_to(source_path)

                    # Create parent folders if needed
                    parent_id = self.config.folder_id
                    if self.config.preserve_structure and len(rel_path.parts) > 1:
                        parent_id = await self._ensure_folders(
                            service, rel_path.parent.parts
                        )

                    # Upload file
                    await self._upload_file(service, local_file, parent_id)
                    result.files_synced += 1
                    result.bytes_uploaded += local_file.stat().st_size

                except Exception as e:
                    logger.error(f"Failed to sync {local_file}: {e}")
                    result.files_failed += 1
                    result.errors.append(f"{local_file}: {str(e)}")

            result.status = SyncStatus.SUCCESS if result.files_failed == 0 else SyncStatus.PARTIAL
            result.completed_at = datetime.utcnow()

        except Exception as e:
            logger.error(f"Sync failed: {e}")
            result.status = SyncStatus.FAILED
            result.errors.append(str(e))
            result.completed_at = datetime.utcnow()

        return result

    async def download(self, remote_path: str, local_path: Path) -> bool:
        """
        Download a file from Google Drive.

        Args:
            remote_path: Remote file ID or path
            local_path: Local destination path

        Returns:
            True if successful
        """
        try:
            service = await self._get_service()

            # Get file content
            request = service.files().get_media(fileId=remote_path)
            content = request.execute()

            # Write to local file
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(content)

            return True

        except Exception as e:
            logger.error(f"Failed to download {remote_path}: {e}")
            return False

    async def delete(self, remote_path: str) -> bool:
        """
        Delete a file from Google Drive.

        Args:
            remote_path: Remote file ID

        Returns:
            True if successful
        """
        try:
            service = await self._get_service()
            service.files().delete(fileId=remote_path).execute()
            return True

        except Exception as e:
            logger.error(f"Failed to delete {remote_path}: {e}")
            return False

    async def list_files(self, remote_path: str) -> List[Dict[str, Any]]:
        """
        List files in a Google Drive folder.

        Args:
            remote_path: Folder ID

        Returns:
            List of file info dictionaries
        """
        try:
            service = await self._get_service()

            results = []
            page_token = None

            while True:
                response = service.files().list(
                    q=f"'{remote_path}' in parents",
                    spaces='drive',
                    fields='nextPageToken, files(id, name, mimeType, size, modifiedTime)',
                    pageToken=page_token
                ).execute()

                for file in response.get('files', []):
                    results.append({
                        "id": file['id'],
                        "name": file['name'],
                        "mime_type": file['mimeType'],
                        "size": int(file.get('size', 0)),
                        "modified_at": file.get('modifiedTime'),
                    })

                page_token = response.get('nextPageToken')
                if not page_token:
                    break

            return results

        except Exception as e:
            logger.error(f"Failed to list files in {remote_path}: {e}")
            return []

    async def get_status(self) -> Dict[str, Any]:
        """
        Get Google Drive quota and status.

        Returns:
            Status information
        """
        try:
            service = await self._get_service()

            about = service.about().get(fields='storageQuota').execute()
            quota = about.get('storageQuota', {})

            return {
                "provider": "google_drive",
                "enabled": self.config.enabled,
                "folder_id": self.config.folder_id,
                "quota": {
                    "limit": int(quota.get('limit', 0)),
                    "usage": int(quota.get('usage', 0)),
                    "usage_in_drive": int(quota.get('usageInDrive', 0)),
                },
            }

        except Exception as e:
            return {
                "provider": "google_drive",
                "enabled": self.config.enabled,
                "error": str(e),
            }

    async def _ensure_folders(
        self,
        service,
        folder_parts: tuple
    ) -> str:
        """
        Ensure folder structure exists, creating if necessary.

        Args:
            service: Google Drive service
            folder_parts: Tuple of folder names

        Returns:
            ID of the deepest folder
        """
        parent_id = self.config.folder_id

        for folder_name in folder_parts:
            cache_key = f"{parent_id}/{folder_name}"

            if cache_key in self._folder_cache:
                parent_id = self._folder_cache[cache_key]
                continue

            # Check if folder exists
            query = f"name='{folder_name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
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
                    'name': folder_name,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [parent_id]
                }
                folder = service.files().create(
                    body=file_metadata,
                    fields='id'
                ).execute()
                folder_id = folder['id']
                logger.info(f"Created folder: {folder_name}")

            self._folder_cache[cache_key] = folder_id
            parent_id = folder_id

        return parent_id

    async def _upload_file(
        self,
        service,
        local_path: Path,
        parent_id: str
    ) -> str:
        """
        Upload a file to Google Drive.

        Args:
            service: Google Drive service
            local_path: Local file path
            parent_id: Parent folder ID

        Returns:
            Uploaded file ID
        """
        from googleapiclient.http import MediaFileUpload

        # Check if file already exists
        query = f"name='{local_path.name}' and '{parent_id}' in parents and trashed=false"
        response = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, modifiedTime)'
        ).execute()

        existing_files = response.get('files', [])
        mime_type = mimetypes.guess_type(str(local_path))[0] or 'application/octet-stream'
        media = MediaFileUpload(str(local_path), mimetype=mime_type)

        if existing_files:
            # Update existing file
            file_id = existing_files[0]['id']

            # Check if local file is newer
            if self.config.conflict_strategy == "local_wins":
                file = service.files().update(
                    fileId=file_id,
                    media_body=media
                ).execute()
                return file['id']
            else:
                # Skip if remote wins or newest (need to compare)
                return file_id
        else:
            # Create new file
            file_metadata = {
                'name': local_path.name,
                'parents': [parent_id]
            }
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            return file['id']


class SyncManager:
    """
    Manages sync across multiple providers and sources.
    """

    def __init__(self, archive_root: Path):
        """
        Initialize sync manager.

        Args:
            archive_root: Root path of the archive
        """
        self.archive_root = archive_root
        self._providers: Dict[str, SyncProvider] = {}
        self._source_configs: Dict[str, Dict[str, SyncConfig]] = {}

    def register_provider(
        self,
        name: str,
        provider: SyncProvider
    ) -> None:
        """Register a sync provider."""
        self._providers[name] = provider

    def configure_source(
        self,
        source_key: str,
        provider_name: str,
        config: SyncConfig
    ) -> None:
        """Configure sync for a source."""
        if source_key not in self._source_configs:
            self._source_configs[source_key] = {}
        self._source_configs[source_key][provider_name] = config

    async def sync_source(
        self,
        source_key: str,
        provider_name: Optional[str] = None
    ) -> Dict[str, SyncResult]:
        """
        Sync a source to configured providers.

        Args:
            source_key: Source to sync
            provider_name: Optional specific provider

        Returns:
            Results by provider name
        """
        results = {}
        configs = self._source_configs.get(source_key, {})

        # Parse source path from key
        parts = source_key.split(":")
        if len(parts) != 2:
            return results

        source_type, server_id = parts

        # Find source directory
        sources_dir = self.archive_root / "sources" / source_type
        source_dir = None

        for d in sources_dir.iterdir():
            if d.is_dir() and d.name.endswith(f"_{server_id}"):
                source_dir = d
                break

        if not source_dir:
            return results

        for prov_name, config in configs.items():
            if provider_name and prov_name != provider_name:
                continue

            if not config.enabled:
                continue

            provider = self._providers.get(prov_name)
            if not provider:
                continue

            result = await provider.sync(source_dir)
            results[prov_name] = result

        return results

    async def sync_all(self) -> Dict[str, Dict[str, SyncResult]]:
        """
        Sync all configured sources.

        Returns:
            Results by source key and provider
        """
        all_results = {}

        for source_key in self._source_configs:
            results = await self.sync_source(source_key)
            if results:
                all_results[source_key] = results

        return all_results
