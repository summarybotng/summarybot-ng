"""
Google Drive import service for WhatsApp exports (ADR-082).

Uses shared folder approach: each guild gets an upload folder that users
can drop files into. Service account scans folders and processes new files.
"""

import io
import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.utils.time import utc_now_naive

logger = logging.getLogger(__name__)

# Max file size: 50MB
MAX_FILE_SIZE = 50 * 1024 * 1024

# Root folder name for uploads
UPLOAD_ROOT_FOLDER = os.environ.get("DRIVE_UPLOAD_ROOT_FOLDER", "SummaryBot Uploads")

# Allowed file extensions
ALLOWED_EXTENSIONS = ('.txt', '.zip')


@dataclass
class DriveFile:
    """Metadata for a file from Google Drive."""
    id: str
    name: str
    mime_type: str
    size: int
    created_time: Optional[datetime] = None


@dataclass
class DriveImportResult:
    """Result of a Drive import operation."""
    success: bool
    file_content: Optional[bytes] = None
    file_name: Optional[str] = None
    file_size: int = 0
    error: Optional[str] = None


class DriveFolderScanner:
    """
    Scans shared upload folders for new WhatsApp exports.

    Uses service account credentials (same as ADR-007 sync).
    """

    def __init__(self, db_connection=None):
        self.db = db_connection
        self._drive = None
        self._root_folder_id = None

    def _get_service_account_creds(self):
        """Get service account credentials from environment."""
        key_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY")
        if not key_json:
            raise ValueError(
                "GOOGLE_SERVICE_ACCOUNT_KEY not configured. "
                "Set it to the JSON contents of the service account key file."
            )

        try:
            from google.oauth2 import service_account
            key_data = json.loads(key_json)
            return service_account.Credentials.from_service_account_info(
                key_data,
                scopes=['https://www.googleapis.com/auth/drive']
            )
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid service account key JSON: {e}")

    @property
    def drive(self):
        """Lazy-load Drive API service."""
        if self._drive is None:
            try:
                from googleapiclient.discovery import build
                creds = self._get_service_account_creds()
                self._drive = build('drive', 'v3', credentials=creds)
            except ImportError:
                raise ImportError(
                    "Google API libraries not installed. "
                    "Run: pip install google-api-python-client google-auth"
                )
        return self._drive

    async def get_or_create_root_folder(self) -> str:
        """Get or create the root uploads folder."""
        if self._root_folder_id:
            return self._root_folder_id

        # Search for existing folder
        results = self.drive.files().list(
            q=f"name='{UPLOAD_ROOT_FOLDER}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id, name)"
        ).execute()

        if results.get('files'):
            self._root_folder_id = results['files'][0]['id']
            return self._root_folder_id

        # Create root folder
        folder_metadata = {
            'name': UPLOAD_ROOT_FOLDER,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = self.drive.files().create(
            body=folder_metadata,
            fields='id'
        ).execute()

        self._root_folder_id = folder['id']
        logger.info(f"Created root upload folder: {self._root_folder_id}")
        return self._root_folder_id

    async def get_or_create_guild_folder(self, guild_id: str) -> str:
        """Get or create upload folder for a guild."""
        # Check database first
        if self.db:
            row = await self.db.fetch_one(
                "SELECT folder_id FROM guild_drive_folders WHERE guild_id = ?",
                (guild_id,)
            )
            if row:
                return row["folder_id"]

        root_id = await self.get_or_create_root_folder()

        # Search for existing guild folder
        folder_name = f"guild_{guild_id}"
        results = self.drive.files().list(
            q=f"name='{folder_name}' and '{root_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id, name)"
        ).execute()

        if results.get('files'):
            folder_id = results['files'][0]['id']
        else:
            # Create guild folder
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [root_id]
            }
            folder = self.drive.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()
            folder_id = folder['id']
            logger.info(f"Created guild upload folder: {folder_id} for {guild_id}")

            # Create /processed subfolder
            processed_metadata = {
                'name': 'processed',
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [folder_id]
            }
            self.drive.files().create(body=processed_metadata, fields='id').execute()

        # Store in database
        if self.db:
            await self.db.execute(
                """
                INSERT OR REPLACE INTO guild_drive_folders (guild_id, folder_id, folder_name, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (guild_id, folder_id, folder_name, utc_now_naive().isoformat())
            )

        return folder_id

    async def get_processed_folder(self, guild_id: str) -> str:
        """Get the /processed subfolder for a guild."""
        guild_folder_id = await self.get_or_create_guild_folder(guild_id)

        results = self.drive.files().list(
            q=f"name='processed' and '{guild_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id)"
        ).execute()

        if results.get('files'):
            return results['files'][0]['id']

        # Create if missing
        metadata = {
            'name': 'processed',
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [guild_folder_id]
        }
        folder = self.drive.files().create(body=metadata, fields='id').execute()
        return folder['id']

    async def make_folder_shareable(self, folder_id: str) -> str:
        """Make folder shareable (anyone with link can upload)."""
        try:
            # Set permission: anyone with link can be a writer
            permission = {
                'type': 'anyone',
                'role': 'writer',
            }
            self.drive.permissions().create(
                fileId=folder_id,
                body=permission
            ).execute()
            logger.info(f"Made folder {folder_id} shareable")
        except Exception as e:
            logger.warning(f"Could not set folder permissions: {e}")

        return f"https://drive.google.com/drive/folders/{folder_id}"

    async def get_upload_link(self, guild_id: str) -> Dict[str, str]:
        """Get the shareable upload link for a guild."""
        folder_id = await self.get_or_create_guild_folder(guild_id)
        folder_url = await self.make_folder_shareable(folder_id)

        return {
            "folder_url": folder_url,
            "folder_id": folder_id,
            "instructions": (
                "Upload your WhatsApp export (.txt or .zip) to this folder. "
                "Files are automatically imported within 5 minutes."
            )
        }

    async def scan_guild_folder(self, guild_id: str) -> List[DriveFile]:
        """Find new files in guild's upload folder (not in /processed)."""
        folder_id = await self.get_or_create_guild_folder(guild_id)
        processed_folder_id = await self.get_processed_folder(guild_id)

        # List files directly in guild folder (not in processed)
        results = self.drive.files().list(
            q=f"'{folder_id}' in parents and mimeType!='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id, name, mimeType, size, createdTime)"
        ).execute()

        files = []
        for f in results.get('files', []):
            # Only include valid file types
            if f['name'].lower().endswith(ALLOWED_EXTENSIONS):
                files.append(DriveFile(
                    id=f['id'],
                    name=f['name'],
                    mime_type=f.get('mimeType', ''),
                    size=int(f.get('size', 0)),
                    created_time=f.get('createdTime')
                ))

        return files

    async def download_file(self, file_id: str) -> DriveImportResult:
        """Download a file from Drive."""
        try:
            from googleapiclient.http import MediaIoBaseDownload

            # Get file metadata
            file_meta = self.drive.files().get(
                fileId=file_id,
                fields="id, name, mimeType, size"
            ).execute()

            file_size = int(file_meta.get('size', 0))
            file_name = file_meta.get('name', 'unknown')

            # Check size limit
            if file_size > MAX_FILE_SIZE:
                return DriveImportResult(
                    success=False,
                    error=f"File too large ({file_size // 1024 // 1024}MB). Maximum is 50MB."
                )

            # Download
            request = self.drive.files().get_media(fileId=file_id)
            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    logger.debug(f"Download progress: {int(status.progress() * 100)}%")

            content = buffer.getvalue()

            return DriveImportResult(
                success=True,
                file_content=content,
                file_name=file_name,
                file_size=len(content)
            )

        except Exception as e:
            logger.error(f"Failed to download file {file_id}: {e}")
            return DriveImportResult(
                success=False,
                error=f"Download failed: {str(e)}"
            )

    async def move_to_processed(self, file_id: str, guild_id: str) -> bool:
        """Move a file to the /processed folder."""
        try:
            guild_folder_id = await self.get_or_create_guild_folder(guild_id)
            processed_folder_id = await self.get_processed_folder(guild_id)

            self.drive.files().update(
                fileId=file_id,
                addParents=processed_folder_id,
                removeParents=guild_folder_id,
                fields='id, parents'
            ).execute()

            logger.info(f"Moved file {file_id} to processed folder")
            return True

        except Exception as e:
            logger.error(f"Failed to move file {file_id} to processed: {e}")
            return False

    async def log_import(
        self,
        guild_id: str,
        drive_file_id: str,
        drive_file_name: str,
        file_size: int,
        status: str = "pending",
        import_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> str:
        """Log a Drive import operation."""
        if not self.db:
            return ""

        log_id = f"dil_{uuid.uuid4().hex[:12]}"

        await self.db.execute(
            """
            INSERT INTO drive_import_log (
                id, guild_id, drive_file_id, drive_file_name,
                file_size_bytes, import_id, status, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (log_id, guild_id, drive_file_id, drive_file_name,
             file_size, import_id, status, error_message)
        )

        return log_id

    async def update_import_log(
        self,
        log_id: str,
        status: str,
        import_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update a Drive import log entry."""
        if not self.db:
            return

        if status in ("completed", "failed"):
            await self.db.execute(
                """
                UPDATE drive_import_log
                SET status = ?, import_id = ?, error_message = ?, completed_at = ?
                WHERE id = ?
                """,
                (status, import_id, error_message, utc_now_naive().isoformat(), log_id)
            )
        else:
            await self.db.execute(
                """
                UPDATE drive_import_log
                SET status = ?, import_id = ?, error_message = ?
                WHERE id = ?
                """,
                (status, import_id, error_message, log_id)
            )


async def get_guilds_with_drive_folders(db) -> List[str]:
    """Get all guild IDs that have Drive upload folders configured."""
    rows = await db.fetch_all("SELECT guild_id FROM guild_drive_folders")
    return [row["guild_id"] for row in rows]


async def scan_all_guild_folders(db, whatsapp_importer):
    """
    Scan all guild upload folders for new files.

    This should be called periodically (e.g., every 5 minutes) by the scheduler.
    """
    scanner = DriveFolderScanner(db_connection=db)
    guilds = await get_guilds_with_drive_folders(db)

    total_imported = 0

    for guild_id in guilds:
        try:
            new_files = await scanner.scan_guild_folder(guild_id)

            for file in new_files:
                log_id = await scanner.log_import(
                    guild_id=guild_id,
                    drive_file_id=file.id,
                    drive_file_name=file.name,
                    file_size=file.size,
                    status="downloading"
                )

                # Download file
                result = await scanner.download_file(file.id)

                if not result.success:
                    await scanner.update_import_log(
                        log_id, "failed", error_message=result.error
                    )
                    continue

                # Process as WhatsApp import
                try:
                    await scanner.update_import_log(log_id, "processing")

                    import_result = await whatsapp_importer.import_file(
                        guild_id=guild_id,
                        content=result.file_content,
                        filename=result.file_name,
                        source="google_drive"
                    )

                    await scanner.update_import_log(
                        log_id, "completed",
                        import_id=import_result.import_id if import_result else None
                    )

                    # Move to processed folder
                    await scanner.move_to_processed(file.id, guild_id)

                    total_imported += 1
                    logger.info(f"Imported {file.name} for guild {guild_id}")

                except Exception as e:
                    logger.error(f"Failed to process {file.name}: {e}")
                    await scanner.update_import_log(
                        log_id, "failed", error_message=str(e)
                    )

        except Exception as e:
            logger.error(f"Error scanning guild {guild_id}: {e}")

    return total_imported
