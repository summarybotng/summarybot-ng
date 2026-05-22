"""
WhatsApp Import Management routes (ADR-081).

Provides REST endpoints for:
- Import upload and tracking
- Import listing and filtering
- Sanitized message viewing
- Participant management
- Import deletion
"""

import hashlib
import json
import logging
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ...data.sqlite.whatsapp_import_repository import (
    SQLiteWhatsAppImportRepository,
    generate_import_id,
)
from ...models.whatsapp_import import (
    ImportStatus,
    WhatsAppImport,
    ImportUploadResult,
)
from ...logging.audit_service import audit_log
from ...utils.time import utc_now_naive

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp Imports"])


# -------------------------------------------------------------------------
# Dependency Injection
# -------------------------------------------------------------------------

async def get_whatsapp_import_repository() -> SQLiteWhatsAppImportRepository:
    """Get WhatsApp import repository."""
    try:
        from ...data.repositories import get_whatsapp_import_repository as _get_repo
        return await _get_repo()
    except RuntimeError:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Database connection not available"}
        )


# -------------------------------------------------------------------------
# Response Models
# -------------------------------------------------------------------------

class ImporterInfo(BaseModel):
    """Information about who imported."""
    id: str
    name: str
    avatar: Optional[str] = None


class ImportSummaryResponse(BaseModel):
    """Summary view of an import."""
    id: str
    chat_id: str
    chat_name: str
    imported_by: ImporterInfo
    imported_at: str
    original_filename: str
    date_range: Dict[str, str]
    message_count: int
    participant_count: int
    status: str
    error_message: Optional[str] = None


class ImportDetailResponse(BaseModel):
    """Detailed view of an import."""
    id: str
    chat_id: str
    chat_name: str
    imported_by: ImporterInfo
    imported_at: str
    original_filename: str
    file_size_bytes: int
    format: str
    date_range: Dict[str, str]
    message_count: int
    participant_count: int
    status: str
    error_message: Optional[str] = None
    processed_at: Optional[str] = None
    participants: List[Dict[str, Any]] = []


class ChatSummaryResponse(BaseModel):
    """Summary of a WhatsApp chat."""
    chat_id: str
    chat_name: str
    import_count: int
    total_messages: int
    coverage: Dict[str, Optional[str]]


class ListImportsResponse(BaseModel):
    """Response for listing imports."""
    imports: List[ImportSummaryResponse]
    total: int
    chats: List[ChatSummaryResponse]


class UploadImportResponse(BaseModel):
    """Response after uploading an import."""
    import_id: str
    status: str
    message_count: int
    participant_count: int
    date_range: Dict[str, str]
    duplicate_of: Optional[str] = None
    message: str


class SanitizedMessage(BaseModel):
    """A sanitized message for viewing."""
    id: str
    timestamp: str
    sender: str  # Pseudonym only
    content: str
    is_system: bool = False
    has_attachment: bool = False
    attachment_type: Optional[str] = None


class ViewMessagesResponse(BaseModel):
    """Response for viewing messages."""
    messages: List[SanitizedMessage]
    total: int
    page: int
    per_page: int
    participants: List[Dict[str, Any]]


class ParticipantResponse(BaseModel):
    """Participant information."""
    id: str
    pseudonym: str
    preferred_name: Optional[str] = None
    message_count: int
    alias_count: int


class ListParticipantsResponse(BaseModel):
    """Response for listing participants."""
    participants: List[ParticipantResponse]
    total: int


class MergeParticipantsRequest(BaseModel):
    """Request to merge two participants."""
    source_id: str
    target_id: str


class UpdateParticipantRequest(BaseModel):
    """Request to update participant."""
    preferred_name: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response."""
    code: str
    message: str


# -------------------------------------------------------------------------
# Import Endpoints
# -------------------------------------------------------------------------

@router.post(
    "/guilds/{guild_id}/imports",
    response_model=UploadImportResponse,
    summary="Upload WhatsApp import",
    description="Upload a WhatsApp chat export file (.txt or .zip).",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid file"},
        409: {"model": ErrorResponse, "description": "Duplicate file"},
    },
)
async def upload_import(
    guild_id: str,
    file: UploadFile = File(...),
    chat_id: Optional[str] = Query(None, description="Chat ID (auto-derived if not provided)"),
    chat_name: Optional[str] = Query(None, description="Chat name (auto-derived if not provided)"),
    user: dict = Depends(get_current_user),
    repo: SQLiteWhatsAppImportRepository = Depends(get_whatsapp_import_repository),
):
    """
    Upload a WhatsApp chat export.

    Supports:
    - .txt files (WhatsApp native export)
    - .zip files (containing .txt export)

    The file is processed to:
    1. Parse messages and extract participants
    2. Resolve participant identities
    3. Check for duplicate messages
    4. Store with attribution to the uploading user
    """
    from ...archive.importers.whatsapp import WhatsAppImporter

    user_id = user.get("sub") or user.get("id")

    # Read file content
    content = await file.read()
    file_hash = hashlib.sha256(content).hexdigest()
    file_size = len(content)
    original_filename = file.filename or "upload.txt"

    # Check for duplicate file
    duplicate_id = None
    if chat_id:
        duplicate_id = await repo.check_duplicate_file(file_hash, guild_id, chat_id)
        if duplicate_id:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "DUPLICATE_FILE",
                    "message": f"This file was already imported (ID: {duplicate_id})",
                    "duplicate_of": duplicate_id,
                },
            )

    # Save to temp file for processing
    with tempfile.NamedTemporaryFile(delete=False, suffix=original_filename) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    extracted_path = None

    try:
        # Handle .zip files
        file_to_process = tmp_path
        if original_filename.lower().endswith('.zip'):
            try:
                with zipfile.ZipFile(tmp_path, 'r') as zip_ref:
                    txt_files = [
                        f for f in zip_ref.namelist()
                        if f.lower().endswith('.txt') and not f.startswith('__MACOSX')
                    ]
                    if not txt_files:
                        raise HTTPException(
                            status_code=400,
                            detail={"code": "NO_TXT_FILE", "message": "No .txt file found in ZIP"},
                        )
                    txt_filename = txt_files[0]
                    extract_dir = Path(tempfile.mkdtemp())
                    zip_ref.extract(txt_filename, extract_dir)
                    extracted_path = extract_dir / txt_filename
                    file_to_process = extracted_path
            except zipfile.BadZipFile:
                raise HTTPException(
                    status_code=400,
                    detail={"code": "INVALID_ZIP", "message": "Invalid ZIP file"},
                )

        # Parse the WhatsApp export
        importer = WhatsAppImporter(Path("/tmp"))  # Archive root not used for parsing
        messages, parse_errors = importer.parse_txt_file(file_to_process)

        if not messages:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "NO_MESSAGES",
                    "message": "No messages could be parsed from file",
                    "errors": parse_errors[:5],
                },
            )

        # Extract date range
        timestamps = [m.timestamp for m in messages]
        date_range_start = min(timestamps)
        date_range_end = max(timestamps)

        # Extract unique senders
        senders = set(m.sender for m in messages if not m.is_system)

        # Derive chat_id and chat_name if not provided
        if not chat_id or not chat_name:
            derived_name = _derive_chat_name(original_filename)
            chat_id = chat_id or _derive_chat_id(derived_name)
            chat_name = chat_name or derived_name

        # Check for duplicate after deriving chat_id
        if not duplicate_id:
            duplicate_id = await repo.check_duplicate_file(file_hash, guild_id, chat_id)
            if duplicate_id:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "DUPLICATE_FILE",
                        "message": f"This file was already imported (ID: {duplicate_id})",
                        "duplicate_of": duplicate_id,
                    },
                )

        # Create import record
        import_id = generate_import_id()
        import_record = WhatsAppImport(
            id=import_id,
            guild_id=guild_id,
            chat_id=chat_id,
            chat_name=chat_name,
            imported_by=user_id,
            imported_at=utc_now_naive(),
            original_filename=original_filename,
            file_hash=file_hash,
            file_size_bytes=file_size,
            format="whatsapp_txt",
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            message_count=len(messages),
            participant_count=len(senders),
            status=ImportStatus.PROCESSING,
        )

        await repo.create_import(import_record)

        # Process participants and messages (identity resolution)
        participants_summary = []
        participant_map: Dict[str, str] = {}  # sender_name -> pseudonym
        duplicates_skipped = 0

        for sender_name in senders:
            participant = await repo.resolve_identity(
                guild_id, chat_id, sender_name, import_id
            )
            participant_map[sender_name] = participant.pseudonym
            sender_messages = [m for m in messages if m.sender == sender_name]
            await repo.update_participant_message_count(
                participant.id, len(sender_messages)
            )
            participants_summary.append({
                "pseudonym": participant.pseudonym,
                "message_count": len(sender_messages),
            })

            # Add fingerprints for deduplication
            for msg in sender_messages:
                fingerprint = _create_fingerprint(msg.timestamp, participant.id, msg.content)
                is_new = await repo.add_fingerprint(
                    fingerprint, import_id, participant.id, msg.timestamp
                )
                if not is_new:
                    duplicates_skipped += 1

        # Store messages in database (with pseudonyms)
        message_dicts = [
            {
                "message_id": m.message_id,
                "timestamp": m.timestamp,
                "sender": m.sender,
                "content": m.content,
                "is_system": m.is_system,
                "attachment": m.attachment,
                "reply_to": m.reply_to,
                "chat_id": chat_id,
            }
            for m in messages
        ]
        await repo.store_messages(import_id, message_dicts, participant_map)

        # Update import with participant info
        await repo.update_import_participants(
            import_id,
            json.dumps(participants_summary),
            len(senders),
        )

        # Mark as completed
        await repo.update_import_status(
            import_id,
            ImportStatus.COMPLETED,
            processed_at=utc_now_naive(),
        )

        # Audit log
        await audit_log(
            "whatsapp.import.uploaded",
            user_id=user_id,
            guild_id=guild_id,
            resource_type="whatsapp_import",
            resource_id=import_id,
            details={
                "filename": original_filename,
                "message_count": len(messages),
                "participant_count": len(senders),
                "duplicates_skipped": duplicates_skipped,
            },
        )

        return UploadImportResponse(
            import_id=import_id,
            status="completed",
            message_count=len(messages),
            participant_count=len(senders),
            date_range={
                "start": date_range_start.isoformat(),
                "end": date_range_end.isoformat(),
            },
            message=f"Imported {len(messages)} messages from {len(senders)} participants"
            + (f" ({duplicates_skipped} duplicates skipped)" if duplicates_skipped else ""),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to process WhatsApp import: {e}")
        raise HTTPException(
            status_code=500,
            detail={"code": "PROCESSING_ERROR", "message": str(e)},
        )
    finally:
        # Cleanup temp files
        tmp_path.unlink(missing_ok=True)
        if extracted_path:
            extracted_path.unlink(missing_ok=True)


@router.get(
    "/guilds/{guild_id}/imports",
    response_model=ListImportsResponse,
    summary="List WhatsApp imports",
    description="Get all WhatsApp imports for a guild.",
)
async def list_imports(
    guild_id: str,
    chat_id: Optional[str] = Query(None, description="Filter by chat ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    repo: SQLiteWhatsAppImportRepository = Depends(get_whatsapp_import_repository),
):
    """List all WhatsApp imports for a guild."""
    offset = (page - 1) * per_page

    imports, total = await repo.get_imports_for_guild(
        guild_id,
        chat_id=chat_id,
        status=status,
        limit=per_page,
        offset=offset,
    )

    # Get chat summaries
    chats = await repo.get_chats_for_guild(guild_id)

    return ListImportsResponse(
        imports=[
            ImportSummaryResponse(
                id=imp.id,
                chat_id=imp.chat_id,
                chat_name=imp.chat_name,
                imported_by=ImporterInfo(
                    id=imp.imported_by,
                    name=_get_user_name(imp.imported_by),
                ),
                imported_at=imp.imported_at.isoformat(),
                original_filename=imp.original_filename,
                date_range={
                    "start": imp.date_range_start.isoformat(),
                    "end": imp.date_range_end.isoformat(),
                },
                message_count=imp.message_count,
                participant_count=imp.participant_count,
                status=imp.status.value if isinstance(imp.status, ImportStatus) else imp.status,
                error_message=imp.error_message,
            )
            for imp in imports
        ],
        total=total,
        chats=[
            ChatSummaryResponse(
                chat_id=chat.chat_id,
                chat_name=chat.chat_name,
                import_count=chat.import_count,
                total_messages=chat.total_messages,
                coverage={
                    "earliest": chat.earliest.isoformat() if chat.earliest else None,
                    "latest": chat.latest.isoformat() if chat.latest else None,
                },
            )
            for chat in chats
        ],
    )


@router.get(
    "/guilds/{guild_id}/imports/{import_id}",
    response_model=ImportDetailResponse,
    summary="Get import details",
    description="Get detailed information about a specific import.",
    responses={404: {"model": ErrorResponse}},
)
async def get_import(
    guild_id: str,
    import_id: str,
    user: dict = Depends(get_current_user),
    repo: SQLiteWhatsAppImportRepository = Depends(get_whatsapp_import_repository),
):
    """Get detailed information about an import."""
    imp = await repo.get_import(import_id)

    if not imp or imp.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Import not found"},
        )

    if imp.deleted_at:
        raise HTTPException(
            status_code=404,
            detail={"code": "DELETED", "message": "Import has been deleted"},
        )

    # Parse participants
    participants = []
    if imp.participants_json:
        try:
            participants = json.loads(imp.participants_json)
        except json.JSONDecodeError:
            pass

    return ImportDetailResponse(
        id=imp.id,
        chat_id=imp.chat_id,
        chat_name=imp.chat_name,
        imported_by=ImporterInfo(
            id=imp.imported_by,
            name=_get_user_name(imp.imported_by),
        ),
        imported_at=imp.imported_at.isoformat(),
        original_filename=imp.original_filename,
        file_size_bytes=imp.file_size_bytes,
        format=imp.format,
        date_range={
            "start": imp.date_range_start.isoformat(),
            "end": imp.date_range_end.isoformat(),
        },
        message_count=imp.message_count,
        participant_count=imp.participant_count,
        status=imp.status.value if isinstance(imp.status, ImportStatus) else imp.status,
        error_message=imp.error_message,
        processed_at=imp.processed_at.isoformat() if imp.processed_at else None,
        participants=participants,
    )


@router.delete(
    "/guilds/{guild_id}/imports/{import_id}",
    summary="Delete import",
    description="Soft delete a WhatsApp import.",
    responses={404: {"model": ErrorResponse}},
)
async def delete_import(
    guild_id: str,
    import_id: str,
    user: dict = Depends(get_current_user),
    repo: SQLiteWhatsAppImportRepository = Depends(get_whatsapp_import_repository),
):
    """Soft delete an import."""
    user_id = user.get("sub") or user.get("id")

    imp = await repo.get_import(import_id)
    if not imp or imp.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Import not found"},
        )

    success = await repo.soft_delete_import(import_id, user_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail={"code": "ALREADY_DELETED", "message": "Import already deleted"},
        )

    await audit_log(
        "whatsapp.import.deleted",
        user_id=user_id,
        guild_id=guild_id,
        resource_type="whatsapp_import",
        resource_id=import_id,
    )

    return {"success": True, "message": "Import deleted"}


# -------------------------------------------------------------------------
# Message Viewing Endpoints
# -------------------------------------------------------------------------

@router.get(
    "/guilds/{guild_id}/imports/{import_id}/messages",
    response_model=ViewMessagesResponse,
    summary="View import messages",
    description="View sanitized messages from an import (pseudonyms only).",
    responses={404: {"model": ErrorResponse}},
)
async def view_import_messages(
    guild_id: str,
    import_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None, description="Search in message content"),
    user: dict = Depends(get_current_user),
    repo: SQLiteWhatsAppImportRepository = Depends(get_whatsapp_import_repository),
):
    """
    View sanitized messages from an import.

    Messages are displayed with pseudonyms only - no phone numbers
    or original contact names are exposed.
    """
    imp = await repo.get_import(import_id)
    if not imp or imp.guild_id != guild_id or imp.deleted_at:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Import not found"},
        )

    # Get messages using repository method
    messages, total = await repo.get_messages_for_import(
        import_id, page=page, per_page=per_page, search=search
    )

    # Get participants
    participants, _ = await repo.get_participants_for_chat(
        guild_id, imp.chat_id, limit=100
    )

    return ViewMessagesResponse(
        messages=[
            SanitizedMessage(
                id=m["id"],
                timestamp=m["timestamp"],
                sender=m["sender"],
                content=m["content"],
                is_system=m["is_system"],
                has_attachment=m["has_attachment"],
            )
            for m in messages
        ],
        total=total,
        page=page,
        per_page=per_page,
        participants=[p.to_dict() for p in participants],
    )


# -------------------------------------------------------------------------
# Participant Endpoints
# -------------------------------------------------------------------------

@router.get(
    "/guilds/{guild_id}/chats/{chat_id}/participants",
    response_model=ListParticipantsResponse,
    summary="List participants",
    description="List all participants in a WhatsApp chat.",
)
async def list_participants(
    guild_id: str,
    chat_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    user: dict = Depends(get_current_user),
    repo: SQLiteWhatsAppImportRepository = Depends(get_whatsapp_import_repository),
):
    """List participants in a chat."""
    offset = (page - 1) * per_page

    participants, total = await repo.get_participants_for_chat(
        guild_id, chat_id, limit=per_page, offset=offset
    )

    return ListParticipantsResponse(
        participants=[
            ParticipantResponse(
                id=p.id,
                pseudonym=p.pseudonym,
                preferred_name=p.preferred_name,
                message_count=p.message_count,
                alias_count=len(p.aliases),
            )
            for p in participants
        ],
        total=total,
    )


@router.patch(
    "/guilds/{guild_id}/participants/{participant_id}",
    summary="Update participant",
    description="Update participant preferred name.",
    responses={404: {"model": ErrorResponse}},
)
async def update_participant(
    guild_id: str,
    participant_id: str,
    request: UpdateParticipantRequest,
    user: dict = Depends(get_current_user),
    repo: SQLiteWhatsAppImportRepository = Depends(get_whatsapp_import_repository),
):
    """Update participant preferred name."""
    participant = await repo.get_participant(participant_id)
    if not participant or participant.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Participant not found"},
        )

    await repo.update_participant_preferred_name(
        participant_id, request.preferred_name
    )

    user_id = user.get("sub") or user.get("id")
    await audit_log(
        "whatsapp.participant.updated",
        user_id=user_id,
        guild_id=guild_id,
        resource_type="whatsapp_participant",
        resource_id=participant_id,
        details={"preferred_name": request.preferred_name},
    )

    return {"success": True}


@router.post(
    "/guilds/{guild_id}/chats/{chat_id}/participants/merge",
    summary="Merge participants",
    description="Merge two participant identities into one.",
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
async def merge_participants(
    guild_id: str,
    chat_id: str,
    request: MergeParticipantsRequest,
    user: dict = Depends(get_current_user),
    repo: SQLiteWhatsAppImportRepository = Depends(get_whatsapp_import_repository),
):
    """
    Merge two participant identities.

    The source participant is merged into the target:
    - Aliases are combined
    - Message counts are summed
    - Fingerprints are updated to point to target
    - Source participant is deleted
    """
    user_id = user.get("sub") or user.get("id")

    try:
        merge = await repo.merge_participants(
            request.source_id,
            request.target_id,
            merged_by=user_id,
            reason="manual",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_MERGE", "message": str(e)},
        )

    if not merge:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "One or both participants not found"},
        )

    await audit_log(
        "whatsapp.participant.merged",
        user_id=user_id,
        guild_id=guild_id,
        resource_type="whatsapp_participant",
        resource_id=merge.target_participant_id,
        details={
            "source_id": merge.source_participant_id,
            "merge_id": merge.id,
        },
    )

    return {
        "success": True,
        "merge_id": merge.id,
        "message": "Participants merged successfully",
    }


# -------------------------------------------------------------------------
# Migration Endpoints
# -------------------------------------------------------------------------

@router.post(
    "/guilds/{guild_id}/migrate-legacy",
    summary="Migrate legacy imports",
    description="One-time migration: Move legacy imports from ingest_batches to whatsapp_imports.",
)
async def migrate_legacy_imports(
    guild_id: str,
    user: dict = Depends(get_current_user),
    repo: SQLiteWhatsAppImportRepository = Depends(get_whatsapp_import_repository),
):
    """
    Migrate legacy WhatsApp imports from ingest_batches to the new whatsapp_imports table.

    This is a one-time operation that copies existing imports to the new management system.
    """
    migrated = await repo.migrate_legacy_imports(guild_id)

    await audit_log(
        guild_id=guild_id,
        action="whatsapp_legacy_migration",
        actor_id=user.get("sub") or user.get("id"),
        details={"migrated_count": migrated},
    )

    return {
        "migrated": migrated,
        "message": f"Migrated {migrated} legacy imports to new system",
    }


# -------------------------------------------------------------------------
# Google Drive Import Endpoints (ADR-082 - Shared Folder Approach)
# -------------------------------------------------------------------------

class DriveUploadLinkResponse(BaseModel):
    """Response with shared upload folder link."""
    folder_url: str
    folder_id: str
    instructions: str


class DrivePendingImport(BaseModel):
    """A pending file in the upload folder."""
    file_id: str
    file_name: str
    file_size: int
    created_at: Optional[str] = None


class DrivePendingResponse(BaseModel):
    """Response for pending Drive imports."""
    pending: List[DrivePendingImport]
    last_scan: Optional[str] = None


async def get_drive_folder_scanner():
    """Get Drive folder scanner service."""
    from . import get_database_connection
    from ...archive.sync.drive_import import DriveFolderScanner

    conn = await get_database_connection()
    return DriveFolderScanner(db_connection=conn)


@router.get(
    "/guilds/{guild_id}/drive/upload-link",
    response_model=DriveUploadLinkResponse,
    summary="Get Google Drive upload folder link",
    description="Get a shareable link to upload WhatsApp exports via Google Drive.",
)
async def get_drive_upload_link(
    guild_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Get the shared Google Drive upload folder link for this guild.

    Files dropped in this folder are automatically imported within 5 minutes.
    No OAuth required - just drop files and they'll be processed.
    """
    try:
        scanner = await get_drive_folder_scanner()
        result = await scanner.get_upload_link(guild_id)

        user_id = user.get("sub") or user.get("id")
        await audit_log(
            "whatsapp.drive.upload_link_requested",
            user_id=user_id,
            guild_id=guild_id,
            resource_type="drive_folder",
            resource_id=result["folder_id"],
        )

        return DriveUploadLinkResponse(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=503,
            detail={"code": "DRIVE_NOT_CONFIGURED", "message": str(e)},
        )
    except Exception as e:
        logger.exception(f"Failed to get Drive upload link: {e}")
        raise HTTPException(
            status_code=500,
            detail={"code": "DRIVE_ERROR", "message": "Failed to create upload folder"},
        )


@router.get(
    "/guilds/{guild_id}/drive/pending",
    response_model=DrivePendingResponse,
    summary="List pending Drive imports",
    description="List files waiting to be processed from the upload folder.",
)
async def list_pending_drive_imports(
    guild_id: str,
    user: dict = Depends(get_current_user),
):
    """
    List files that have been uploaded to Drive but not yet processed.

    The scanner runs every 5 minutes, so recently uploaded files may appear here.
    """
    try:
        scanner = await get_drive_folder_scanner()
        files = await scanner.scan_guild_folder(guild_id)

        return DrivePendingResponse(
            pending=[
                DrivePendingImport(
                    file_id=f.id,
                    file_name=f.name,
                    file_size=f.size,
                    created_at=f.created_time.isoformat() if f.created_time else None,
                )
                for f in files
            ],
            last_scan=None,  # TODO: Track last scan time
        )

    except Exception as e:
        logger.exception(f"Failed to list pending Drive imports: {e}")
        raise HTTPException(
            status_code=500,
            detail={"code": "DRIVE_ERROR", "message": "Failed to check pending files"},
        )


@router.post(
    "/guilds/{guild_id}/drive/scan",
    summary="Trigger manual Drive folder scan",
    description="Manually trigger a scan of the upload folder (normally runs every 5 min).",
)
async def trigger_drive_scan(
    guild_id: str,
    user: dict = Depends(get_current_user),
    repo: SQLiteWhatsAppImportRepository = Depends(get_whatsapp_import_repository),
):
    """
    Manually trigger a scan of the Drive upload folder.

    Useful if you just uploaded files and don't want to wait for the next scheduled scan.
    """
    user_id = user.get("sub") or user.get("id")

    try:
        scanner = await get_drive_folder_scanner()
        files = await scanner.scan_guild_folder(guild_id)

        imported_count = 0
        errors = []

        for file in files:
            try:
                # Log the import
                log_id = await scanner.log_import(
                    guild_id=guild_id,
                    drive_file_id=file.id,
                    drive_file_name=file.name,
                    file_size=file.size,
                    status="downloading",
                )

                # Download
                result = await scanner.download_file(file.id)
                if not result.success:
                    await scanner.update_import_log(log_id, "failed", error_message=result.error)
                    errors.append(f"{file.name}: {result.error}")
                    continue

                await scanner.update_import_log(log_id, "processing")

                # Process the file using existing import logic
                content = result.file_content
                file_hash = hashlib.sha256(content).hexdigest()
                logger.info(f"Processing {file.name}: size={len(content)} bytes, hash={file_hash[:12]}...")

                chat_name = _derive_chat_name(result.file_name)
                chat_id = _derive_chat_id(chat_name)
                logger.info(f"Derived chat: name='{chat_name}', id='{chat_id}'")

                # Check duplicate
                duplicate_id = await repo.check_duplicate_file(file_hash, guild_id, chat_id)
                if duplicate_id:
                    logger.info(f"File {file.name} is duplicate of {duplicate_id}, skipping")
                    await scanner.update_import_log(log_id, "failed", error_message=f"Duplicate of {duplicate_id}")
                    await scanner.move_to_processed(file.id, guild_id)
                    continue

                # Parse and import
                from ...archive.importers.whatsapp import WhatsAppImporter

                with tempfile.NamedTemporaryFile(delete=False, suffix=result.file_name) as tmp:
                    tmp.write(content)
                    tmp_path = Path(tmp.name)

                extracted_path = None
                try:
                    # Handle zip files
                    file_to_process = tmp_path
                    if result.file_name.lower().endswith('.zip'):
                        try:
                            with zipfile.ZipFile(tmp_path, 'r') as zip_ref:
                                all_files = zip_ref.namelist()
                                logger.info(f"Zip contains {len(all_files)} files: {all_files[:5]}...")
                                txt_files = [
                                    f for f in all_files
                                    if f.lower().endswith('.txt') and not f.startswith('__MACOSX')
                                ]
                                if not txt_files:
                                    logger.warning(f"No .txt files found in zip {file.name}")
                                    await scanner.update_import_log(log_id, "failed", error_message="No .txt file in zip")
                                    await scanner.move_to_processed(file.id, guild_id)
                                    continue
                                txt_filename = txt_files[0]
                                logger.info(f"Extracting {txt_filename} from zip")
                                extract_dir = Path(tempfile.mkdtemp())
                                zip_ref.extract(txt_filename, extract_dir)
                                extracted_path = extract_dir / txt_filename
                                file_to_process = extracted_path
                        except zipfile.BadZipFile:
                            logger.error(f"Invalid zip file: {file.name}")
                            await scanner.update_import_log(log_id, "failed", error_message="Invalid zip file")
                            await scanner.move_to_processed(file.id, guild_id)
                            continue

                    # Use the importer
                    importer = WhatsAppImporter(archive_root=Path("/tmp"), guild_id=guild_id)
                    import_result = await importer.import_txt_export(
                        file_path=file_to_process,
                        group_id=chat_id,
                        group_name=chat_name,
                    )

                    if not import_result.messages:
                        logger.warning(f"No messages parsed from {file.name}")
                        await scanner.update_import_log(log_id, "failed", error_message="No messages found")
                        await scanner.move_to_processed(file.id, guild_id)  # Move to processed so it doesn't retry
                        continue

                    logger.info(f"Parsed {len(import_result.messages)} messages from {file.name}")

                    # Create import record (status=PROCESSING until messages are stored)
                    import_id = generate_import_id()
                    timestamps = [m.timestamp for m in import_result.messages]
                    senders = set(m.sender for m in import_result.messages if not m.is_system)

                    import_record = WhatsAppImport(
                        id=import_id,
                        guild_id=guild_id,
                        chat_id=chat_id,
                        chat_name=chat_name,
                        imported_by=f"drive:{user_id}",
                        imported_at=utc_now_naive(),
                        original_filename=result.file_name,
                        file_hash=file_hash,
                        file_size_bytes=result.file_size,
                        format="whatsapp_txt",
                        date_range_start=min(timestamps),
                        date_range_end=max(timestamps),
                        message_count=len(import_result.messages),
                        participant_count=len(senders),
                        status=ImportStatus.PROCESSING,  # Set to PROCESSING until messages stored
                    )
                    await repo.create_import(import_record)

                    # Also create ingest_batches record (required by FK on ingest_messages)
                    from ...data.repositories import get_ingest_repository
                    ingest_repo = await get_ingest_repository()
                    await ingest_repo.connection.execute(
                        """
                        INSERT INTO ingest_batches (
                            id, source_type, channel_id, channel_name, channel_type,
                            message_count, time_range_start, time_range_end, raw_payload, processed
                        )
                        VALUES (?, 'whatsapp', ?, ?, 'whatsapp_chat', ?, ?, ?, '{}', 1)
                        """,
                        (import_id, chat_id, chat_name, len(import_result.messages),
                         min(timestamps).isoformat(), max(timestamps).isoformat())
                    )

                    # Process participants
                    participant_map = {}
                    for sender_name in senders:
                        participant = await repo.resolve_identity(guild_id, chat_id, sender_name, import_id)
                        participant_map[sender_name] = participant.pseudonym

                    # Store messages
                    message_dicts = [
                        {
                            "message_id": m.message_id,
                            "timestamp": m.timestamp,
                            "sender": m.sender,
                            "content": m.content,
                            "is_system": m.is_system,
                            "attachment": m.attachment,
                            "reply_to": m.reply_to,
                            "chat_id": chat_id,
                        }
                        for m in import_result.messages
                    ]
                    await repo.store_messages(import_id, message_dicts, participant_map)

                    # Update status to COMPLETED after messages stored
                    await repo.update_import_status(import_id, ImportStatus.COMPLETED, processed_at=utc_now_naive())

                    await scanner.update_import_log(log_id, "completed", import_id=import_id)
                    await scanner.move_to_processed(file.id, guild_id)
                    imported_count += 1
                    logger.info(f"Successfully imported {file.name}: {len(import_result.messages)} messages")

                finally:
                    tmp_path.unlink(missing_ok=True)
                    if extracted_path:
                        extracted_path.unlink(missing_ok=True)

            except Exception as e:
                logger.exception(f"Failed to import {file.name}: {e}")
                errors.append(f"{file.name}: {str(e)}")
                # Mark import as FAILED if record was created
                if 'import_id' in locals() and import_id:
                    try:
                        await repo.update_import_status(
                            import_id, ImportStatus.FAILED, error_message=str(e)
                        )
                    except Exception:
                        pass  # Ignore errors during cleanup

        await audit_log(
            "whatsapp.drive.manual_scan",
            user_id=user_id,
            guild_id=guild_id,
            resource_type="drive_folder",
            details={"imported": imported_count, "errors": len(errors)},
        )

        return {
            "scanned": len(files),
            "imported": imported_count,
            "errors": errors,
            "message": f"Imported {imported_count} of {len(files)} files",
        }

    except Exception as e:
        logger.exception(f"Drive scan failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={"code": "SCAN_FAILED", "message": str(e)},
        )


# -------------------------------------------------------------------------
# PII Scrubbing (Issue #85a8d4d4)
# -------------------------------------------------------------------------

@router.post(
    "/guilds/{guild_id}/scrub-pii",
    summary="Scrub PII from WhatsApp messages",
    description="Retroactively anonymize phone numbers in existing WhatsApp message content.",
    responses={
        403: {"description": "No permission"},
    },
)
async def scrub_whatsapp_pii(
    guild_id: str = Path(..., description="Discord guild ID"),
    import_id: Optional[str] = Body(None, description="Specific import ID to scrub (optional)"),
    user: dict = Depends(get_current_user),
):
    """
    Scrub phone numbers from existing WhatsApp messages.

    This endpoint retroactively anonymizes phone numbers that may have been
    stored in message content before PII scrubbing was implemented.

    Admin only.
    """
    _check_guild_access(guild_id, user)
    require_guild_admin(guild_id, user)

    repo = await get_whatsapp_import_repository(guild_id)

    result = await repo.scrub_existing_messages_pii(import_id=import_id)

    user_id = user.get("id", "unknown")
    await audit_log(
        "whatsapp.pii.scrub",
        user_id=user_id,
        guild_id=guild_id,
        resource_type="whatsapp_messages",
        details={
            "import_id": import_id,
            "messages_updated": result["messages_updated"],
            "phones_scrubbed": result["phones_scrubbed"],
        },
    )

    return {
        "success": True,
        "messages_updated": result["messages_updated"],
        "phones_scrubbed": result["phones_scrubbed"],
        "message": f"Scrubbed {result['phones_scrubbed']} phone numbers from {result['messages_updated']} messages",
    }


# -------------------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------------------

def _derive_chat_name(filename: str) -> str:
    """Derive chat name from filename."""
    import re

    name = filename

    # Remove extension
    for ext in ['.zip', '.txt', '.json']:
        if name.lower().endswith(ext):
            name = name[:-len(ext)]

    # Remove WhatsApp prefix patterns
    patterns = [
        r'^WhatsApp Chat with\s+',
        r'^WhatsApp Chat -\s+',
        r'^Chat with\s+',
    ]
    for pattern in patterns:
        name = re.sub(pattern, '', name, flags=re.IGNORECASE)

    return name.strip() or "Unknown Chat"


def _derive_chat_id(chat_name: str) -> str:
    """Derive chat ID from chat name."""
    import re

    # Slugify
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', chat_name.lower()).strip('-')

    # Add hash for uniqueness
    name_hash = hashlib.md5(chat_name.encode()).hexdigest()[:6]

    return f"{slug[:30]}-{name_hash}"


def _create_fingerprint(timestamp: datetime, participant_id: str, content: str) -> str:
    """Create a message fingerprint for deduplication."""
    timestamp_str = timestamp.strftime("%Y%m%d%H%M%S")
    content_hash = hashlib.md5((content or "").encode()).hexdigest()[:8]
    return f"{timestamp_str}|{participant_id}|{content_hash}"


def _get_user_name(user_id: str) -> str:
    """Get user display name from ID."""
    # TODO: Look up actual user name from database
    return user_id[:8] + "..."
