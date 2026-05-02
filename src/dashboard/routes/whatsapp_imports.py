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
    from . import get_database_connection
    conn = await get_database_connection()
    return SQLiteWhatsAppImportRepository(conn)


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
        messages, parse_errors = importer._parse_txt_file(file_to_process)

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
