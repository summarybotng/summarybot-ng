"""
Slack file handling (ADR-043 Section 6.2).

Manages file downloads from Slack with URL expiration handling.
Slack file URLs require authentication and expire after some time.
"""

import os
import logging
import hashlib
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

from .models import SlackWorkspace
from .token_store import SecureSlackTokenStore

logger = logging.getLogger(__name__)

# File handling configuration
DEFAULT_DOWNLOAD_DIR = "data/slack_files"
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB max download
URL_EXPIRATION_HOURS = 24  # Assume URLs expire in 24h


@dataclass
class SlackFile:
    """Represents a Slack file with download metadata."""
    file_id: str
    workspace_id: str
    filename: str
    title: Optional[str] = None
    mimetype: Optional[str] = None
    filetype: Optional[str] = None
    size_bytes: int = 0
    permalink: Optional[str] = None
    url_private: Optional[str] = None
    url_private_download: Optional[str] = None
    local_path: Optional[str] = None
    downloaded_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_external: bool = False
    user_id: Optional[str] = None
    channel_id: Optional[str] = None

    def is_downloadable(self) -> bool:
        """Check if file can be downloaded."""
        return (
            self.url_private_download is not None and
            self.size_bytes <= MAX_FILE_SIZE_BYTES and
            not self.is_external
        )

    def is_expired(self) -> bool:
        """Check if download URL has expired."""
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at

    def needs_redownload(self) -> bool:
        """Check if file needs to be redownloaded."""
        if not self.local_path:
            return True
        if not os.path.exists(self.local_path):
            return True
        if self.is_expired():
            return True
        return False


class SlackFileHandler:
    """Handles Slack file downloads with authentication and expiration (ADR-043).

    Slack files require Bearer token authentication for download.
    URLs can expire, so we track expiration and support re-downloading.
    """

    def __init__(
        self,
        workspace: SlackWorkspace,
        download_dir: str = DEFAULT_DOWNLOAD_DIR,
        max_file_size: int = MAX_FILE_SIZE_BYTES,
    ):
        """Initialize file handler.

        Args:
            workspace: SlackWorkspace with encrypted bot token
            download_dir: Directory for downloaded files
            max_file_size: Maximum file size to download
        """
        self.workspace = workspace
        self.workspace_id = workspace.workspace_id
        self._token = SecureSlackTokenStore.decrypt_token(workspace.encrypted_bot_token)
        self.download_dir = Path(download_dir) / workspace.workspace_id
        self.max_file_size = max_file_size
        self._http_client: Optional[httpx.AsyncClient] = None

        # Ensure download directory exists
        self.download_dir.mkdir(parents=True, exist_ok=True)

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=60.0,  # Longer timeout for file downloads
                headers={"Authorization": f"Bearer {self._token}"},
            )
        return self._http_client

    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def parse_file(self, file_data: Dict[str, Any]) -> SlackFile:
        """Parse Slack file API response into SlackFile.

        Args:
            file_data: File object from Slack API

        Returns:
            SlackFile object
        """
        # Estimate URL expiration
        expires_at = datetime.utcnow() + timedelta(hours=URL_EXPIRATION_HOURS)

        return SlackFile(
            file_id=file_data.get("id", ""),
            workspace_id=self.workspace_id,
            filename=file_data.get("name", "unknown"),
            title=file_data.get("title"),
            mimetype=file_data.get("mimetype"),
            filetype=file_data.get("filetype"),
            size_bytes=file_data.get("size", 0),
            permalink=file_data.get("permalink"),
            url_private=file_data.get("url_private"),
            url_private_download=file_data.get("url_private_download"),
            is_external=file_data.get("is_external", False),
            user_id=file_data.get("user"),
            expires_at=expires_at,
        )

    def _get_local_path(self, file: SlackFile) -> Path:
        """Generate local file path for a Slack file.

        Uses file_id as directory to handle filename conflicts.

        Args:
            file: SlackFile to generate path for

        Returns:
            Path object for local storage
        """
        # Create subdirectory using first 2 chars of file_id for distribution
        subdir = file.file_id[:2] if len(file.file_id) >= 2 else "00"
        file_dir = self.download_dir / subdir / file.file_id

        # Sanitize filename
        safe_filename = "".join(
            c for c in file.filename
            if c.isalnum() or c in ".-_"
        )
        if not safe_filename:
            safe_filename = "file"

        return file_dir / safe_filename

    async def download_file(self, file: SlackFile) -> Optional[str]:
        """Download a Slack file to local storage.

        Args:
            file: SlackFile to download

        Returns:
            Local file path if successful, None otherwise
        """
        if not file.is_downloadable():
            logger.warning(f"File {file.file_id} is not downloadable")
            return None

        if file.size_bytes > self.max_file_size:
            logger.warning(
                f"File {file.file_id} exceeds max size: "
                f"{file.size_bytes} > {self.max_file_size}"
            )
            return None

        local_path = self._get_local_path(file)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        client = await self._get_http_client()

        try:
            # Stream download to avoid memory issues with large files
            async with client.stream("GET", file.url_private_download) as response:
                if response.status_code != 200:
                    logger.error(
                        f"Failed to download file {file.file_id}: "
                        f"HTTP {response.status_code}"
                    )
                    return None

                # Check content-length
                content_length = int(response.headers.get("content-length", 0))
                if content_length > self.max_file_size:
                    logger.warning(f"File {file.file_id} actual size exceeds limit")
                    return None

                # Write to file
                with open(local_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)

            # Update file metadata
            file.local_path = str(local_path)
            file.downloaded_at = datetime.utcnow()

            logger.info(
                f"Downloaded Slack file {file.file_id}: {file.filename} "
                f"({file.size_bytes} bytes)"
            )

            return str(local_path)

        except Exception as e:
            logger.error(f"Error downloading file {file.file_id}: {e}")
            # Clean up partial download
            if local_path.exists():
                local_path.unlink()
            return None

    async def download_files_batch(
        self,
        files: List[SlackFile],
        concurrency: int = 3,
    ) -> Dict[str, Optional[str]]:
        """Download multiple files concurrently.

        Args:
            files: List of SlackFile objects to download
            concurrency: Max concurrent downloads

        Returns:
            Dict mapping file_id to local path (or None if failed)
        """
        semaphore = asyncio.Semaphore(concurrency)
        results = {}

        async def download_with_semaphore(file: SlackFile):
            async with semaphore:
                return file.file_id, await self.download_file(file)

        tasks = [download_with_semaphore(f) for f in files if f.is_downloadable()]
        for coro in asyncio.as_completed(tasks):
            file_id, path = await coro
            results[file_id] = path

        return results

    async def get_file_info(self, file_id: str) -> Optional[SlackFile]:
        """Fetch file info from Slack API.

        Args:
            file_id: Slack file ID

        Returns:
            SlackFile if found, None otherwise
        """
        from .client import SlackClient, SlackAPIError

        # Create temporary client for API call
        client = SlackClient(self.workspace)

        try:
            data = await client._request("files.info", params={"file": file_id})
            file_data = data.get("file", {})
            return self.parse_file(file_data)
        except SlackAPIError as e:
            logger.error(f"Failed to get file info for {file_id}: {e}")
            return None
        finally:
            await client.close()

    def cleanup_expired_files(self, max_age_days: int = 30) -> int:
        """Remove old downloaded files.

        Args:
            max_age_days: Remove files older than this many days

        Returns:
            Number of files removed
        """
        cutoff = datetime.utcnow() - timedelta(days=max_age_days)
        removed = 0

        for file_path in self.download_dir.rglob("*"):
            if not file_path.is_file():
                continue

            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if mtime < cutoff:
                    file_path.unlink()
                    removed += 1
            except Exception as e:
                logger.warning(f"Failed to remove old file {file_path}: {e}")

        if removed:
            logger.info(f"Cleaned up {removed} expired Slack files")

        return removed
