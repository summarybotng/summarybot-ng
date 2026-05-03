"""
SQLite implementation of WhatsApp import repository (ADR-081).

Provides import tracking, participant identity management,
and message fingerprinting for deduplication.
"""

import json
import logging
import hashlib
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .connection import SQLiteConnection
from ...models.whatsapp_import import (
    WhatsAppImport,
    WhatsAppParticipant,
    WhatsAppIdentityMerge,
    WhatsAppMessageFingerprint,
    ChatCoverage,
    ImportStatus,
)
from ...services.anonymization.phone_anonymizer import (
    hash_phone_number,
    hash_to_pseudonym,
    COMBINED_PHONE_PATTERN,
)
from ...utils.time import utc_now_naive

logger = logging.getLogger(__name__)


def generate_import_id() -> str:
    """Generate a unique import ID."""
    return f"imp_{uuid.uuid4().hex[:12]}"


def generate_participant_id() -> str:
    """Generate a unique participant ID."""
    return f"part_{uuid.uuid4().hex[:12]}"


def generate_merge_id() -> str:
    """Generate a unique merge ID."""
    return f"merge_{uuid.uuid4().hex[:12]}"


class SQLiteWhatsAppImportRepository:
    """SQLite repository for WhatsApp import management."""

    def __init__(self, connection: SQLiteConnection, salt: str = "summarybot-default-salt"):
        self.connection = connection
        self.salt = salt

    # ==================== Import CRUD ====================

    async def create_import(self, import_record: WhatsAppImport) -> str:
        """Create a new import record."""
        query = """
        INSERT INTO whatsapp_imports (
            id, guild_id, chat_id, chat_name,
            imported_by, imported_at,
            original_filename, file_hash, file_size_bytes, format,
            date_range_start, date_range_end,
            message_count, participant_count,
            status, anonymization_version, participants_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            import_record.id,
            import_record.guild_id,
            import_record.chat_id,
            import_record.chat_name,
            import_record.imported_by,
            import_record.imported_at.isoformat(),
            import_record.original_filename,
            import_record.file_hash,
            import_record.file_size_bytes,
            import_record.format,
            import_record.date_range_start.isoformat(),
            import_record.date_range_end.isoformat(),
            import_record.message_count,
            import_record.participant_count,
            import_record.status.value if isinstance(import_record.status, ImportStatus) else import_record.status,
            import_record.anonymization_version,
            import_record.participants_json,
        )
        await self.connection.execute(query, params)
        return import_record.id

    async def get_import(self, import_id: str) -> Optional[WhatsAppImport]:
        """Get an import by ID."""
        query = "SELECT * FROM whatsapp_imports WHERE id = ?"
        row = await self.connection.fetch_one(query, (import_id,))
        return self._row_to_import(row) if row else None

    async def get_imports_for_guild(
        self,
        guild_id: str,
        chat_id: Optional[str] = None,
        include_deleted: bool = False,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[WhatsAppImport], int]:
        """Get imports for a guild with optional filters."""
        conditions = ["guild_id = ?"]
        params: List[Any] = [guild_id]

        if chat_id:
            conditions.append("chat_id = ?")
            params.append(chat_id)

        if not include_deleted:
            conditions.append("deleted_at IS NULL")

        if status:
            conditions.append("status = ?")
            params.append(status)

        where_clause = " AND ".join(conditions)

        # Count query
        count_query = f"SELECT COUNT(*) as count FROM whatsapp_imports WHERE {where_clause}"
        count_row = await self.connection.fetch_one(count_query, tuple(params))
        total = count_row["count"] if count_row else 0

        # Data query
        query = f"""
        SELECT * FROM whatsapp_imports
        WHERE {where_clause}
        ORDER BY imported_at DESC
        LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        rows = await self.connection.fetch_all(query, tuple(params))

        return [self._row_to_import(row) for row in rows], total

    async def migrate_legacy_imports(self, guild_id: str) -> int:
        """
        One-time migration: Create import records from stored summaries.

        WhatsApp data may exist as stored summaries with archive_source_key
        like 'whatsapp:chat-name'. This creates import records to track them.

        Returns the number of imports created.
        """
        # First try ingest_batches (original approach)
        query = """
        SELECT * FROM ingest_batches
        WHERE source_type = 'whatsapp'
        """
        rows = await self.connection.fetch_all(query, ())

        migrated = 0
        for row in rows:
            check_query = "SELECT 1 FROM whatsapp_imports WHERE id = ?"
            exists = await self.connection.fetch_one(check_query, (row["id"],))
            if exists:
                continue

            import_record = self._legacy_row_to_import(row, guild_id)
            await self.create_import(import_record)
            migrated += 1
            logger.info(f"Migrated legacy batch {row['id']} to whatsapp_imports")

        # Also check stored_summaries for whatsapp source keys
        summary_query = """
        SELECT
            archive_source_key,
            MIN(summary_json) as first_summary,
            MIN(created_at) as earliest,
            MAX(created_at) as latest,
            COUNT(*) as summary_count
        FROM stored_summaries
        WHERE archive_source_key LIKE 'whatsapp:%'
        AND guild_id = ?
        GROUP BY archive_source_key
        """
        summary_rows = await self.connection.fetch_all(summary_query, (guild_id,))

        for row in summary_rows:
            source_key = row["archive_source_key"]
            chat_id = source_key.replace("whatsapp:", "")

            # Check if import already exists for this chat
            check_query = "SELECT 1 FROM whatsapp_imports WHERE guild_id = ? AND chat_id = ? LIMIT 1"
            exists = await self.connection.fetch_one(check_query, (guild_id, chat_id))
            if exists:
                continue

            # Create import record from summary data
            import_id = f"legacy_{chat_id}_{guild_id}"
            earliest = datetime.fromisoformat(row["earliest"]) if row["earliest"] else datetime.now()
            latest = datetime.fromisoformat(row["latest"]) if row["latest"] else datetime.now()

            import_record = WhatsAppImport(
                id=import_id,
                guild_id=guild_id,
                chat_id=chat_id,
                chat_name=chat_id.replace("-", " ").title(),
                imported_by="system",
                imported_at=earliest,
                original_filename=f"legacy_{chat_id}.txt",
                file_hash="",
                file_size_bytes=0,
                format="whatsapp_txt",
                date_range_start=earliest,
                date_range_end=latest,
                message_count=0,  # Unknown for legacy
                participant_count=0,
                status=ImportStatus.COMPLETED,
                error_message=None,
                processed_at=earliest,
                anonymization_version=1,
                participants_json=None,
                deleted_at=None,
                deleted_by=None,
                created_at=earliest,
            )

            await self.create_import(import_record)
            migrated += 1
            logger.info(f"Created import record for {source_key} ({row['summary_count']} summaries)")

        return migrated

    async def update_import_status(
        self,
        import_id: str,
        status: ImportStatus,
        error_message: Optional[str] = None,
        processed_at: Optional[datetime] = None,
    ) -> None:
        """Update import status."""
        query = """
        UPDATE whatsapp_imports
        SET status = ?, error_message = ?, processed_at = ?
        WHERE id = ?
        """
        params = (
            status.value,
            error_message,
            processed_at.isoformat() if processed_at else None,
            import_id,
        )
        await self.connection.execute(query, params)

    async def update_import_participants(
        self,
        import_id: str,
        participants_json: str,
        participant_count: int,
    ) -> None:
        """Update import participant information."""
        query = """
        UPDATE whatsapp_imports
        SET participants_json = ?, participant_count = ?
        WHERE id = ?
        """
        await self.connection.execute(query, (participants_json, participant_count, import_id))

    async def soft_delete_import(self, import_id: str, deleted_by: str) -> bool:
        """Soft delete an import."""
        query = """
        UPDATE whatsapp_imports
        SET deleted_at = ?, deleted_by = ?
        WHERE id = ? AND deleted_at IS NULL
        """
        result = await self.connection.execute(
            query, (utc_now_naive().isoformat(), deleted_by, import_id)
        )
        return result.rowcount > 0 if hasattr(result, 'rowcount') else True

    async def check_duplicate_file(
        self, file_hash: str, guild_id: str, chat_id: str
    ) -> Optional[str]:
        """Check if a file with this hash was already imported."""
        query = """
        SELECT id FROM whatsapp_imports
        WHERE file_hash = ? AND guild_id = ? AND chat_id = ?
        AND deleted_at IS NULL
        LIMIT 1
        """
        row = await self.connection.fetch_one(query, (file_hash, guild_id, chat_id))
        return row["id"] if row else None

    # ==================== Participant CRUD ====================

    async def create_participant(self, participant: WhatsAppParticipant) -> str:
        """Create a new participant."""
        query = """
        INSERT INTO whatsapp_participants (
            id, guild_id, chat_id, phone_hash, pseudonym,
            aliases_json, preferred_name,
            first_seen_import_id, message_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            participant.id,
            participant.guild_id,
            participant.chat_id,
            participant.phone_hash,
            participant.pseudonym,
            json.dumps(participant.aliases),
            participant.preferred_name,
            participant.first_seen_import_id,
            participant.message_count,
        )
        await self.connection.execute(query, params)
        return participant.id

    async def get_participant(self, participant_id: str) -> Optional[WhatsAppParticipant]:
        """Get a participant by ID."""
        query = "SELECT * FROM whatsapp_participants WHERE id = ?"
        row = await self.connection.fetch_one(query, (participant_id,))
        return self._row_to_participant(row) if row else None

    async def get_participant_by_phone_hash(
        self, guild_id: str, chat_id: str, phone_hash: str
    ) -> Optional[WhatsAppParticipant]:
        """Get a participant by phone hash."""
        query = """
        SELECT * FROM whatsapp_participants
        WHERE guild_id = ? AND chat_id = ? AND phone_hash = ?
        """
        row = await self.connection.fetch_one(query, (guild_id, chat_id, phone_hash))
        return self._row_to_participant(row) if row else None

    async def get_participants_for_chat(
        self,
        guild_id: str,
        chat_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[WhatsAppParticipant], int]:
        """Get participants for a chat."""
        count_query = """
        SELECT COUNT(*) as count FROM whatsapp_participants
        WHERE guild_id = ? AND chat_id = ?
        """
        count_row = await self.connection.fetch_one(count_query, (guild_id, chat_id))
        total = count_row["count"] if count_row else 0

        query = """
        SELECT * FROM whatsapp_participants
        WHERE guild_id = ? AND chat_id = ?
        ORDER BY message_count DESC
        LIMIT ? OFFSET ?
        """
        rows = await self.connection.fetch_all(query, (guild_id, chat_id, limit, offset))

        return [self._row_to_participant(row) for row in rows], total

    async def find_participant_by_alias(
        self, guild_id: str, chat_id: str, alias: str
    ) -> Optional[WhatsAppParticipant]:
        """Find a participant by alias (exact match)."""
        # SQLite JSON search
        query = """
        SELECT * FROM whatsapp_participants
        WHERE guild_id = ? AND chat_id = ?
        AND (
            aliases_json LIKE ?
            OR aliases_json LIKE ?
            OR aliases_json LIKE ?
        )
        LIMIT 1
        """
        # Match: ["alias"], [..., "alias"], ["alias", ...]
        escaped_alias = alias.replace('"', '\\"')
        params = (
            guild_id,
            chat_id,
            f'%"{escaped_alias}"%',
            f'%"{escaped_alias}"%',
            f'%"{escaped_alias}"%',
        )
        row = await self.connection.fetch_one(query, params)
        return self._row_to_participant(row) if row else None

    async def add_alias_to_participant(
        self, participant_id: str, alias: str
    ) -> None:
        """Add an alias to a participant."""
        # Get current aliases
        participant = await self.get_participant(participant_id)
        if not participant:
            return

        if alias not in participant.aliases:
            participant.aliases.append(alias)
            query = """
            UPDATE whatsapp_participants
            SET aliases_json = ?, updated_at = ?
            WHERE id = ?
            """
            await self.connection.execute(
                query,
                (json.dumps(participant.aliases), utc_now_naive().isoformat(), participant_id)
            )

    async def update_participant_message_count(
        self, participant_id: str, increment: int = 1
    ) -> None:
        """Increment participant message count."""
        query = """
        UPDATE whatsapp_participants
        SET message_count = message_count + ?, updated_at = ?
        WHERE id = ?
        """
        await self.connection.execute(
            query, (increment, utc_now_naive().isoformat(), participant_id)
        )

    async def update_participant_preferred_name(
        self, participant_id: str, preferred_name: Optional[str]
    ) -> None:
        """Update participant preferred name."""
        query = """
        UPDATE whatsapp_participants
        SET preferred_name = ?, updated_at = ?
        WHERE id = ?
        """
        await self.connection.execute(
            query, (preferred_name, utc_now_naive().isoformat(), participant_id)
        )

    # ==================== Identity Resolution ====================

    async def resolve_identity(
        self,
        guild_id: str,
        chat_id: str,
        sender_name: str,
        import_id: str,
    ) -> WhatsAppParticipant:
        """
        Resolve sender to a canonical participant identity.

        Strategy:
        1. If sender looks like a phone number, hash and find/create by phone
        2. Otherwise, look for exact alias match
        3. If no match, create new participant
        """
        # Check if sender is a phone number
        if COMBINED_PHONE_PATTERN.match(sender_name):
            phone_hash = hash_phone_number(sender_name, self.salt)
            participant = await self.get_participant_by_phone_hash(
                guild_id, chat_id, phone_hash
            )
            if participant:
                # Add alias if not present
                if sender_name not in participant.aliases:
                    await self.add_alias_to_participant(participant.id, sender_name)
                return participant

            # Create new participant with phone hash
            pseudonym = hash_to_pseudonym(phone_hash)
            new_participant = WhatsAppParticipant(
                id=generate_participant_id(),
                guild_id=guild_id,
                chat_id=chat_id,
                phone_hash=phone_hash,
                pseudonym=pseudonym,
                aliases=[sender_name],
                first_seen_import_id=import_id,
                message_count=0,
            )
            await self.create_participant(new_participant)
            return new_participant

        # Not a phone number - look for alias match
        participant = await self.find_participant_by_alias(guild_id, chat_id, sender_name)
        if participant:
            return participant

        # Create new participant without phone hash
        # Generate pseudonym from sender name hash
        name_hash = hashlib.sha256(f"{guild_id}:{chat_id}:{sender_name}".encode()).hexdigest()[:8]
        pseudonym = hash_to_pseudonym(name_hash)

        new_participant = WhatsAppParticipant(
            id=generate_participant_id(),
            guild_id=guild_id,
            chat_id=chat_id,
            phone_hash=None,
            pseudonym=pseudonym,
            aliases=[sender_name],
            first_seen_import_id=import_id,
            message_count=0,
        )
        await self.create_participant(new_participant)
        return new_participant

    async def merge_participants(
        self,
        source_id: str,
        target_id: str,
        merged_by: str,
        reason: str = "manual",
    ) -> Optional[WhatsAppIdentityMerge]:
        """
        Merge source participant into target.

        - Combines aliases
        - Adds message counts
        - Updates fingerprints to point to target
        - Creates merge record for audit/undo
        """
        source = await self.get_participant(source_id)
        target = await self.get_participant(target_id)

        if not source or not target:
            return None

        if source.guild_id != target.guild_id or source.chat_id != target.chat_id:
            raise ValueError("Cannot merge participants from different chats")

        # Create merge record
        merge = WhatsAppIdentityMerge(
            id=generate_merge_id(),
            guild_id=source.guild_id,
            chat_id=source.chat_id,
            source_participant_id=source_id,
            target_participant_id=target_id,
            merged_by=merged_by,
            merged_at=utc_now_naive(),
            reason=reason,
            source_data_json=json.dumps({
                "pseudonym": source.pseudonym,
                "aliases": source.aliases,
                "phone_hash": source.phone_hash,
                "message_count": source.message_count,
            }),
        )

        # Insert merge record
        query = """
        INSERT INTO whatsapp_identity_merges (
            id, guild_id, chat_id,
            source_participant_id, target_participant_id,
            merged_by, merged_at, reason, source_data_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        await self.connection.execute(query, (
            merge.id,
            merge.guild_id,
            merge.chat_id,
            merge.source_participant_id,
            merge.target_participant_id,
            merge.merged_by,
            merge.merged_at.isoformat(),
            merge.reason,
            merge.source_data_json,
        ))

        # Merge aliases
        combined_aliases = list(set(target.aliases + source.aliases))
        query = """
        UPDATE whatsapp_participants
        SET aliases_json = ?,
            message_count = message_count + ?,
            phone_hash = COALESCE(phone_hash, ?),
            updated_at = ?
        WHERE id = ?
        """
        await self.connection.execute(query, (
            json.dumps(combined_aliases),
            source.message_count,
            source.phone_hash,
            utc_now_naive().isoformat(),
            target_id,
        ))

        # Update fingerprints
        query = """
        UPDATE whatsapp_message_fingerprints
        SET participant_id = ?
        WHERE participant_id = ?
        """
        await self.connection.execute(query, (target_id, source_id))

        # Delete source participant
        query = "DELETE FROM whatsapp_participants WHERE id = ?"
        await self.connection.execute(query, (source_id,))

        return merge

    # ==================== Fingerprinting ====================

    async def add_fingerprint(
        self,
        fingerprint: str,
        import_id: str,
        participant_id: str,
        message_timestamp: datetime,
    ) -> bool:
        """
        Add a message fingerprint. Returns False if duplicate.
        """
        query = """
        INSERT OR IGNORE INTO whatsapp_message_fingerprints (
            fingerprint, import_id, participant_id, message_timestamp
        ) VALUES (?, ?, ?, ?)
        """
        result = await self.connection.execute(
            query, (fingerprint, import_id, participant_id, message_timestamp.isoformat())
        )
        # If no rows inserted, it's a duplicate
        return result.rowcount > 0 if hasattr(result, 'rowcount') else True

    async def check_fingerprint_exists(self, fingerprint: str) -> bool:
        """Check if a fingerprint already exists."""
        query = "SELECT 1 FROM whatsapp_message_fingerprints WHERE fingerprint = ? LIMIT 1"
        row = await self.connection.fetch_one(query, (fingerprint,))
        return row is not None

    async def get_fingerprints_for_import(self, import_id: str) -> List[str]:
        """Get all fingerprints for an import."""
        query = "SELECT fingerprint FROM whatsapp_message_fingerprints WHERE import_id = ?"
        rows = await self.connection.fetch_all(query, (import_id,))
        return [row["fingerprint"] for row in rows]

    # ==================== Coverage ====================

    async def get_chat_coverage(self, guild_id: str, chat_id: str) -> ChatCoverage:
        """Calculate coverage for a chat."""
        query = """
        SELECT
            chat_name,
            MIN(date_range_start) as earliest,
            MAX(date_range_end) as latest,
            SUM(message_count) as total_messages,
            COUNT(*) as import_count
        FROM whatsapp_imports
        WHERE guild_id = ? AND chat_id = ?
        AND deleted_at IS NULL AND status = 'completed'
        GROUP BY chat_id
        """
        row = await self.connection.fetch_one(query, (guild_id, chat_id))

        if not row:
            return ChatCoverage(
                chat_id=chat_id,
                chat_name="",
                earliest=None,
                latest=None,
                total_messages=0,
                import_count=0,
            )

        # TODO: Calculate gaps between imports
        return ChatCoverage(
            chat_id=chat_id,
            chat_name=row["chat_name"] or "",
            earliest=datetime.fromisoformat(row["earliest"]) if row["earliest"] else None,
            latest=datetime.fromisoformat(row["latest"]) if row["latest"] else None,
            total_messages=row["total_messages"] or 0,
            import_count=row["import_count"] or 0,
        )

    async def get_chats_for_guild(self, guild_id: str) -> List[ChatCoverage]:
        """Get all chats with coverage info for a guild."""
        query = """
        SELECT
            chat_id,
            chat_name,
            MIN(date_range_start) as earliest,
            MAX(date_range_end) as latest,
            SUM(message_count) as total_messages,
            COUNT(*) as import_count
        FROM whatsapp_imports
        WHERE guild_id = ?
        AND deleted_at IS NULL AND status = 'completed'
        GROUP BY chat_id
        ORDER BY MAX(imported_at) DESC
        """
        rows = await self.connection.fetch_all(query, (guild_id,))

        return [
            ChatCoverage(
                chat_id=row["chat_id"],
                chat_name=row["chat_name"] or "",
                earliest=datetime.fromisoformat(row["earliest"]) if row["earliest"] else None,
                latest=datetime.fromisoformat(row["latest"]) if row["latest"] else None,
                total_messages=row["total_messages"] or 0,
                import_count=row["import_count"] or 0,
            )
            for row in rows
        ]

    # ==================== Message Storage ====================

    async def store_messages(
        self,
        import_id: str,
        messages: List[Dict[str, Any]],
        participant_map: Dict[str, str],  # sender_name -> pseudonym
    ) -> int:
        """
        Store messages in ingest_messages table.

        Args:
            import_id: The import ID (used as batch_id)
            messages: List of parsed messages
            participant_map: Mapping of sender names to pseudonyms

        Returns:
            Number of messages stored
        """
        # Store messages in ingest_messages (compatible with existing queries)
        query = """
        INSERT OR IGNORE INTO ingest_messages (
            id, batch_id, source_type, channel_id, sender_id, sender_name,
            timestamp, content, has_attachments, attachments_json,
            reply_to_id, is_forwarded, is_edited, is_deleted, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params_list = []
        for msg in messages:
            sender = msg.get("sender", "Unknown")
            pseudonym = participant_map.get(sender, sender)

            msg_id = f"wa_{import_id}_{msg.get('message_id', uuid.uuid4().hex[:8])}"

            params = (
                msg_id,
                import_id,  # batch_id = import_id
                "whatsapp",
                msg.get("chat_id", ""),
                pseudonym,  # sender_id = pseudonym
                pseudonym,  # sender_name = pseudonym
                msg.get("timestamp", "").isoformat() if hasattr(msg.get("timestamp"), "isoformat") else str(msg.get("timestamp", "")),
                msg.get("content", ""),
                1 if msg.get("attachment") else 0,
                json.dumps([{"filename": msg["attachment"]}]) if msg.get("attachment") else "[]",
                msg.get("reply_to"),
                0,  # is_forwarded
                0,  # is_edited
                0,  # is_deleted
                json.dumps({"is_system": msg.get("is_system", False)}),
            )
            params_list.append(params)

        if params_list:
            await self.connection.executemany(query, params_list)

        return len(params_list)

    async def get_messages_for_import(
        self,
        import_id: str,
        page: int = 1,
        per_page: int = 50,
        search: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get messages for an import with pagination."""
        base_conditions = "batch_id = ?"
        params: List[Any] = [import_id]

        if search:
            base_conditions += " AND content LIKE ?"
            params.append(f"%{search}%")

        # Count
        count_query = f"SELECT COUNT(*) as count FROM ingest_messages WHERE {base_conditions}"
        count_row = await self.connection.fetch_one(count_query, tuple(params))
        total = count_row["count"] if count_row else 0

        # Fetch
        offset = (page - 1) * per_page
        data_query = f"""
        SELECT id, timestamp, sender_name, content, metadata, has_attachments
        FROM ingest_messages
        WHERE {base_conditions}
        ORDER BY timestamp ASC
        LIMIT ? OFFSET ?
        """
        params.extend([per_page, offset])
        rows = await self.connection.fetch_all(data_query, tuple(params))

        messages = []
        for row in rows:
            metadata = {}
            if row.get("metadata"):
                try:
                    metadata = json.loads(row["metadata"])
                except json.JSONDecodeError:
                    pass

            messages.append({
                "id": row["id"],
                "timestamp": row["timestamp"],
                "sender": row["sender_name"],
                "content": row["content"] or "",
                "is_system": metadata.get("is_system", False),
                "has_attachment": bool(row.get("has_attachments")),
            })

        return messages, total

    # ==================== Helper Methods ====================

    def _legacy_row_to_import(self, row: Dict[str, Any], guild_id: str) -> WhatsAppImport:
        """Convert a legacy ingest_batches row to WhatsAppImport."""
        # Parse raw_payload for additional details
        participants_json = None
        try:
            raw_payload = json.loads(row.get("raw_payload") or "{}")
            participants = raw_payload.get("participants", [])
            participants_json = json.dumps(participants)
        except json.JSONDecodeError:
            pass

        return WhatsAppImport(
            id=row["id"],
            guild_id=guild_id,
            chat_id=row["channel_id"],
            chat_name=row.get("channel_name") or row["channel_id"],
            imported_by="system",  # Legacy imports don't track importer
            imported_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else datetime.now(),
            original_filename=f"legacy_import_{row['id']}.txt",
            file_hash="",
            file_size_bytes=0,
            format="whatsapp_txt",
            date_range_start=datetime.fromisoformat(row["time_range_start"]) if row.get("time_range_start") else datetime.now(),
            date_range_end=datetime.fromisoformat(row["time_range_end"]) if row.get("time_range_end") else datetime.now(),
            message_count=row.get("message_count") or 0,
            participant_count=0,
            status=ImportStatus.COMPLETED if row.get("processed") else ImportStatus.PROCESSING,
            error_message=None,
            processed_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else None,
            anonymization_version=1,
            participants_json=participants_json,
            deleted_at=None,
            deleted_by=None,
            created_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else None,
        )

    def _row_to_import(self, row: Dict[str, Any]) -> WhatsAppImport:
        """Convert a database row to WhatsAppImport."""
        return WhatsAppImport(
            id=row["id"],
            guild_id=row["guild_id"],
            chat_id=row["chat_id"],
            chat_name=row["chat_name"],
            imported_by=row["imported_by"],
            imported_at=datetime.fromisoformat(row["imported_at"]),
            original_filename=row["original_filename"],
            file_hash=row["file_hash"],
            file_size_bytes=row["file_size_bytes"],
            format=row["format"],
            date_range_start=datetime.fromisoformat(row["date_range_start"]),
            date_range_end=datetime.fromisoformat(row["date_range_end"]),
            message_count=row["message_count"],
            participant_count=row["participant_count"],
            status=ImportStatus(row["status"]),
            error_message=row.get("error_message"),
            processed_at=datetime.fromisoformat(row["processed_at"]) if row.get("processed_at") else None,
            anonymization_version=row.get("anonymization_version", 1),
            participants_json=row.get("participants_json"),
            deleted_at=datetime.fromisoformat(row["deleted_at"]) if row.get("deleted_at") else None,
            deleted_by=row.get("deleted_by"),
            created_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else None,
        )

    def _row_to_participant(self, row: Dict[str, Any]) -> WhatsAppParticipant:
        """Convert a database row to WhatsAppParticipant."""
        aliases = []
        if row.get("aliases_json"):
            try:
                aliases = json.loads(row["aliases_json"])
            except json.JSONDecodeError:
                pass

        return WhatsAppParticipant(
            id=row["id"],
            guild_id=row["guild_id"],
            chat_id=row["chat_id"],
            phone_hash=row.get("phone_hash"),
            pseudonym=row["pseudonym"],
            aliases=aliases,
            preferred_name=row.get("preferred_name"),
            first_seen_import_id=row.get("first_seen_import_id"),
            message_count=row.get("message_count", 0),
            created_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row.get("updated_at") else None,
        )
