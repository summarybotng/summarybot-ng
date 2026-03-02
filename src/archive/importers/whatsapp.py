"""
WhatsApp chat history importer.

Supports two formats:
1. WhatsApp native export (.txt files)
2. Reader bot JSON export (from ADR-001)

Phase 6: WhatsApp Import
ADR-028: PII Anonymization for phone numbers
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.services.anonymization import PhoneAnonymizer
from src.services.anonymization.phone_anonymizer import create_guild_anonymizer

logger = logging.getLogger(__name__)


@dataclass
class WhatsAppMessage:
    """Parsed WhatsApp message."""
    message_id: str
    timestamp: datetime
    sender: str
    content: str
    is_system: bool = False
    attachment: Optional[str] = None
    reply_to: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "timestamp": self.timestamp.isoformat(),
            "sender": self.sender,
            "content": self.content,
            "is_system": self.is_system,
            "attachment": self.attachment,
            "reply_to": self.reply_to,
        }


@dataclass
class WhatsAppImportResult:
    """Result of a WhatsApp import."""
    import_id: str
    filename: str
    format: str  # "whatsapp_txt" or "reader_bot"
    imported_at: datetime
    date_range: Tuple[date, date]
    message_count: int
    participant_count: int
    messages: List[WhatsAppMessage] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    gaps: List[Dict] = field(default_factory=list)
    anonymization: Optional[Dict[str, Any]] = None  # ADR-028: Anonymization metadata

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "import_id": self.import_id,
            "filename": self.filename,
            "format": self.format,
            "imported_at": self.imported_at.isoformat(),
            "date_range": {
                "start": self.date_range[0].isoformat(),
                "end": self.date_range[1].isoformat(),
            },
            "message_count": self.message_count,
            "participant_count": self.participant_count,
            "errors": self.errors,
            "gaps": self.gaps,
        }
        if self.anonymization:
            result["anonymization"] = self.anonymization
        return result


class WhatsAppImporter:
    """
    Imports WhatsApp chat history from various formats.

    Supports:
    - Native WhatsApp export (.txt)
    - Reader bot JSON export
    """

    # Regex patterns for WhatsApp text export
    # Format: [DD/MM/YYYY, HH:MM:SS] Sender: Message
    # or: DD/MM/YYYY, HH:MM - Sender: Message
    # or: YYYY-MM-DD, HH:MM a.m./p.m. - Sender: Message (Canadian/ISO format)
    DATETIME_PATTERNS = [
        # YYYY-MM-DD, HH:MM a.m./p.m. - (Canadian/ISO format with periods in am/pm)
        r'(\d{4}-\d{2}-\d{2}),\s*(\d{1,2}:\d{2}(?:\s*[ap]\.m\.)?)\s*-',
        # [DD/MM/YYYY, HH:MM:SS]
        r'\[(\d{1,2}/\d{1,2}/\d{2,4}),\s*(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)\]',
        # DD/MM/YYYY, HH:MM -
        r'(\d{1,2}/\d{1,2}/\d{2,4}),\s*(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)\s*-',
        # MM/DD/YY, HH:MM -
        r'(\d{1,2}/\d{1,2}/\d{2}),\s*(\d{1,2}:\d{2}(?:\s*[AP]M)?)\s*-',
    ]

    # System message patterns
    SYSTEM_PATTERNS = [
        r"Messages and calls are end-to-end encrypted",
        r"created group",
        r"added you",
        r"changed the subject",
        r"changed this group's icon",
        r"left$",
        r"was removed$",
        r"joined using this group's invite link",
        r"security code.*changed",
        r"Tap to learn more",
    ]

    def __init__(
        self,
        archive_root: Path,
        guild_id: Optional[str] = None,
        anonymize: bool = True,
    ):
        """
        Initialize WhatsApp importer.

        Args:
            archive_root: Root path of the archive
            guild_id: Guild ID for anonymization salt (ADR-028)
            anonymize: Whether to anonymize phone numbers (default True)
        """
        self.archive_root = archive_root
        self.guild_id = guild_id
        self.anonymize = anonymize
        self._anonymizer: Optional[PhoneAnonymizer] = None

        if anonymize and guild_id:
            self._anonymizer = create_guild_anonymizer(guild_id)

    def _get_anonymizer(self, group_id: str) -> Optional[PhoneAnonymizer]:
        """Get anonymizer, creating one if needed."""
        if not self.anonymize:
            return None
        if self._anonymizer:
            return self._anonymizer
        # Create anonymizer using group_id as fallback salt
        return create_guild_anonymizer(self.guild_id or group_id)

    async def import_txt_export(
        self,
        file_path: Path,
        group_id: str,
        group_name: str,
    ) -> WhatsAppImportResult:
        """
        Import from WhatsApp native text export.

        Args:
            file_path: Path to the .txt export file
            group_id: Group identifier
            group_name: Group name

        Returns:
            Import result with parsed messages
        """
        import_id = f"imp_{uuid.uuid4().hex[:12]}"
        messages: List[WhatsAppMessage] = []
        errors: List[str] = []
        participants = set()

        try:
            content = file_path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            content = file_path.read_text(encoding='utf-8-sig')

        lines = content.split('\n')
        current_message = None
        msg_counter = 0

        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue

            # Try to parse as new message
            parsed = self._parse_message_line(line, msg_counter)

            if parsed:
                # Save previous message
                if current_message:
                    messages.append(current_message)

                timestamp, sender, text = parsed
                msg_counter += 1

                # Check if system message
                is_system = any(re.search(p, text, re.IGNORECASE) for p in self.SYSTEM_PATTERNS)

                if not is_system:
                    participants.add(sender)

                current_message = WhatsAppMessage(
                    message_id=f"wa_{msg_counter}",
                    timestamp=timestamp,
                    sender=sender,
                    content=text,
                    is_system=is_system,
                )

            elif current_message:
                # Continuation of previous message
                current_message.content += f"\n{line}"

            else:
                # Orphan line at start
                if line and not any(p in line.lower() for p in ["end-to-end encrypted"]):
                    errors.append(f"Line {line_num}: Could not parse: {line[:50]}...")

        # Don't forget last message
        if current_message:
            messages.append(current_message)

        # ADR-028: Apply anonymization to phone numbers
        anonymization_metadata = None
        anonymizer = self._get_anonymizer(group_id)
        if anonymizer and messages:
            messages, anonymization_metadata = self._anonymize_messages(messages, anonymizer)
            # Update participants set with anonymized names
            participants = {m.sender for m in messages if not m.is_system}
            logger.info(f"Anonymized {anonymization_metadata.get('participant_count', 0)} phone-based participants")

        # Calculate date range
        if messages:
            dates = [m.timestamp.date() for m in messages]
            date_range = (min(dates), max(dates))
        else:
            date_range = (date.today(), date.today())

        # Save to archive
        await self._save_import(
            group_id=group_id,
            group_name=group_name,
            import_id=import_id,
            messages=messages,
            format_type="whatsapp_txt",
            filename=file_path.name,
        )

        result = WhatsAppImportResult(
            import_id=import_id,
            filename=file_path.name,
            format="whatsapp_txt",
            imported_at=datetime.utcnow(),
            date_range=date_range,
            message_count=len(messages),
            participant_count=len(participants),
            messages=messages,
            errors=errors,
            anonymization=anonymization_metadata,
        )

        logger.info(f"Imported {len(messages)} messages from {file_path.name}")
        return result

    async def import_reader_bot_json(
        self,
        file_path: Path,
        group_id: str,
        group_name: str,
    ) -> WhatsAppImportResult:
        """
        Import from reader bot JSON export.

        Args:
            file_path: Path to the JSON export file
            group_id: Group identifier
            group_name: Group name

        Returns:
            Import result with parsed messages
        """
        import_id = f"imp_{uuid.uuid4().hex[:12]}"

        with open(file_path, 'r') as f:
            data = json.load(f)

        messages: List[WhatsAppMessage] = []
        participants = set()

        for msg_data in data.get("messages", []):
            msg = WhatsAppMessage(
                message_id=msg_data.get("id", f"wa_{len(messages)}"),
                timestamp=datetime.fromisoformat(msg_data["timestamp"]),
                sender=msg_data["sender"],
                content=msg_data.get("content", ""),
                is_system=msg_data.get("is_system", False),
                attachment=msg_data.get("attachment"),
                reply_to=msg_data.get("reply_to"),
            )
            messages.append(msg)
            if not msg.is_system:
                participants.add(msg.sender)

        # ADR-028: Apply anonymization to phone numbers
        anonymization_metadata = None
        anonymizer = self._get_anonymizer(group_id)
        if anonymizer and messages:
            messages, anonymization_metadata = self._anonymize_messages(messages, anonymizer)
            # Update participants set with anonymized names
            participants = {m.sender for m in messages if not m.is_system}
            logger.info(f"Anonymized {anonymization_metadata.get('participant_count', 0)} phone-based participants")

        # Calculate date range
        if messages:
            dates = [m.timestamp.date() for m in messages]
            date_range = (min(dates), max(dates))
        else:
            date_range = (date.today(), date.today())

        # Save to archive
        await self._save_import(
            group_id=group_id,
            group_name=group_name,
            import_id=import_id,
            messages=messages,
            format_type="reader_bot",
            filename=file_path.name,
        )

        result = WhatsAppImportResult(
            import_id=import_id,
            filename=file_path.name,
            format="reader_bot",
            imported_at=datetime.utcnow(),
            date_range=date_range,
            message_count=len(messages),
            participant_count=len(participants),
            messages=messages,
            errors=[],
            anonymization=anonymization_metadata,
        )

        logger.info(f"Imported {len(messages)} messages from reader bot export")
        return result

    def _anonymize_messages(
        self,
        messages: List[WhatsAppMessage],
        anonymizer: PhoneAnonymizer,
    ) -> Tuple[List[WhatsAppMessage], Dict[str, Any]]:
        """
        Anonymize phone numbers in messages (ADR-028).

        Args:
            messages: List of WhatsAppMessage objects
            anonymizer: PhoneAnonymizer instance

        Returns:
            Tuple of (anonymized_messages, anonymization_metadata)
        """
        from dataclasses import replace

        participant_info: Dict[str, Dict[str, Any]] = {}
        anonymized = []

        for msg in messages:
            # Anonymize sender if it looks like a phone number
            new_sender = msg.sender
            if not msg.is_system:
                display_name, phone_hash = anonymizer.anonymize_sender(msg.sender)
                new_sender = display_name

                # Track participant info
                if phone_hash:  # Was a phone number
                    if display_name not in participant_info:
                        participant_info[display_name] = {
                            "hash": phone_hash,
                            "message_count": 0,
                        }
                    participant_info[display_name]["message_count"] += 1

            # Anonymize content (phone numbers mentioned in text)
            new_content = msg.content
            if msg.content:
                result = anonymizer.anonymize_text(msg.content)
                new_content = result.anonymized_text

            # Create new message with anonymized data
            anonymized.append(WhatsAppMessage(
                message_id=msg.message_id,
                timestamp=msg.timestamp,
                sender=new_sender,
                content=new_content,
                is_system=msg.is_system,
                attachment=msg.attachment,
                reply_to=msg.reply_to,
            ))

        # Build metadata
        metadata = {
            "version": 1,
            "participant_count": len(participant_info),
            "participants": participant_info,
        }

        return anonymized, metadata

    def _parse_message_line(
        self,
        line: str,
        fallback_id: int,
    ) -> Optional[Tuple[datetime, str, str]]:
        """
        Parse a message line from WhatsApp export.

        Returns:
            Tuple of (timestamp, sender, content) or None if not a message start
        """
        for pattern in self.DATETIME_PATTERNS:
            match = re.match(pattern, line)
            if match:
                date_str, time_str = match.groups()

                # Parse datetime
                try:
                    timestamp = self._parse_datetime(date_str, time_str)
                except ValueError:
                    continue

                # Get rest of line after datetime
                rest = line[match.end():].strip()

                # Remove leading dash or colon
                rest = re.sub(r'^[\s\-:]+', '', rest)

                # Split sender and content
                if ': ' in rest:
                    sender, content = rest.split(': ', 1)
                    return (timestamp, sender.strip(), content.strip())
                else:
                    # System message (no sender)
                    return (timestamp, "System", rest)

        return None

    def _parse_datetime(self, date_str: str, time_str: str) -> datetime:
        """Parse datetime from various WhatsApp formats."""
        # Normalize date separators
        date_str = date_str.replace('.', '/').replace('-', '/')

        # Parse date
        parts = date_str.split('/')
        if len(parts) == 3:
            try:
                # Check for YYYY/MM/DD format (year first - 4 digit first part)
                if len(parts[0]) == 4:
                    year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
                # DD/MM/YYYY or MM/DD/YYYY format
                elif len(parts[2]) == 4:
                    day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                elif len(parts[2]) == 2:
                    day, month, year = int(parts[0]), int(parts[1]), 2000 + int(parts[2])
                else:
                    raise ValueError("Unknown year format")

                # Validate month (swap if needed for MM/DD/YYYY)
                if month > 12:
                    day, month = month, day

            except ValueError:
                raise ValueError(f"Cannot parse date: {date_str}")

        else:
            raise ValueError(f"Cannot parse date: {date_str}")

        # Parse time - handle both "AM/PM" and "a.m./p.m." formats
        time_str = time_str.strip()
        # Normalize a.m./p.m. to AM/PM
        time_str_upper = time_str.upper().replace('.', '')
        is_pm = 'PM' in time_str_upper
        is_am = 'AM' in time_str_upper
        # Remove AM/PM variants (with or without periods)
        time_str = re.sub(r'\s*[ap]\.?m\.?', '', time_str, flags=re.IGNORECASE)

        time_parts = time_str.split(':')
        hour = int(time_parts[0])
        minute = int(time_parts[1]) if len(time_parts) > 1 else 0
        second = int(time_parts[2]) if len(time_parts) > 2 else 0

        if is_pm and hour < 12:
            hour += 12
        elif is_am and hour == 12:
            hour = 0

        return datetime(year, month, day, hour, minute, second)

    async def _save_import(
        self,
        group_id: str,
        group_name: str,
        import_id: str,
        messages: List[WhatsAppMessage],
        format_type: str,
        filename: str,
    ) -> None:
        """Save imported messages to archive."""
        # Create directory structure
        safe_name = re.sub(r'[^\w\-]', '-', group_name.lower())
        group_dir = self.archive_root / "sources" / "whatsapp" / f"{safe_name}_{group_id}"
        imports_dir = group_dir / "imports"
        imports_dir.mkdir(parents=True, exist_ok=True)

        # Save messages
        messages_file = imports_dir / f"{import_id}_messages.json"
        with open(messages_file, 'w') as f:
            json.dump([m.to_dict() for m in messages], f, indent=2)

        # Update import manifest
        manifest_file = imports_dir / "import-manifest.json"
        if manifest_file.exists():
            with open(manifest_file, 'r') as f:
                manifest = json.load(f)
        else:
            manifest = {"imports": [], "coverage": {"earliest": None, "latest": None, "gaps": []}}

        # Calculate date range
        if messages:
            dates = sorted(set(m.timestamp.date() for m in messages))
            earliest = dates[0].isoformat()
            latest = dates[-1].isoformat()
        else:
            earliest = latest = None

        manifest["imports"].append({
            "import_id": import_id,
            "filename": filename,
            "format": format_type,
            "imported_at": datetime.utcnow().isoformat(),
            "date_range": {"start": earliest, "end": latest},
            "message_count": len(messages),
            "participant_count": len(set(m.sender for m in messages if not m.is_system)),
        })

        # Update coverage
        all_dates = []
        for imp in manifest["imports"]:
            if imp["date_range"]["start"]:
                all_dates.append(date.fromisoformat(imp["date_range"]["start"]))
            if imp["date_range"]["end"]:
                all_dates.append(date.fromisoformat(imp["date_range"]["end"]))

        if all_dates:
            manifest["coverage"]["earliest"] = min(all_dates).isoformat()
            manifest["coverage"]["latest"] = max(all_dates).isoformat()

        with open(manifest_file, 'w') as f:
            json.dump(manifest, f, indent=2)

    def _message_fingerprint(self, msg: Dict[str, Any]) -> str:
        """
        Generate a fingerprint for deduplication.

        WhatsApp doesn't have guaranteed unique message IDs, so we use
        timestamp + sender + first 50 chars of content as a fingerprint.

        Args:
            msg: Message dictionary with timestamp, sender, content

        Returns:
            Fingerprint string for deduplication
        """
        timestamp = msg.get("timestamp", "")
        sender = msg.get("sender", "")
        content = msg.get("content", "")[:50]
        return f"{timestamp}|{sender}|{content}"

    async def get_messages_for_period(
        self,
        group_id: str,
        start: datetime,
        end: datetime,
    ) -> List[Dict[str, Any]]:
        """
        Get imported messages for a time period.

        Deduplicates messages from overlapping imports using a fingerprint
        of timestamp + sender + content[:50].

        Args:
            group_id: Group identifier
            start: Period start
            end: Period end

        Returns:
            List of unique message dictionaries
        """
        # Find group directory
        sources_dir = self.archive_root / "sources" / "whatsapp"
        if not sources_dir.exists():
            return []

        group_dir = None
        for d in sources_dir.iterdir():
            if d.is_dir() and d.name.endswith(f"_{group_id}"):
                group_dir = d
                break

        if not group_dir:
            return []

        imports_dir = group_dir / "imports"
        if not imports_dir.exists():
            return []

        # Load all messages from all imports, deduplicating
        all_messages = []
        seen_fingerprints: set = set()

        # Convert start/end to naive datetimes for comparison (WhatsApp messages are naive)
        start_naive = start.replace(tzinfo=None) if start.tzinfo else start
        end_naive = end.replace(tzinfo=None) if end.tzinfo else end

        for msg_file in imports_dir.glob("*_messages.json"):
            with open(msg_file, 'r') as f:
                messages = json.load(f)

            for msg in messages:
                msg_time = datetime.fromisoformat(msg["timestamp"])
                # Also strip timezone from parsed time if present
                msg_time_naive = msg_time.replace(tzinfo=None) if msg_time.tzinfo else msg_time
                if start_naive <= msg_time_naive <= end_naive:
                    # Deduplicate using fingerprint
                    fingerprint = self._message_fingerprint(msg)
                    if fingerprint in seen_fingerprints:
                        continue
                    seen_fingerprints.add(fingerprint)

                    all_messages.append({
                        "id": msg["message_id"],
                        "author_id": msg["sender"],
                        "author_name": msg["sender"],
                        "content": msg["content"],
                        "timestamp": msg["timestamp"],
                        "is_system": msg.get("is_system", False),
                    })

        # Sort by timestamp
        all_messages.sort(key=lambda m: m["timestamp"])

        if len(seen_fingerprints) < len(all_messages) + (len(all_messages) - len(seen_fingerprints)):
            # Log if we deduplicated anything (for debugging)
            logger.debug(f"Deduplicated WhatsApp messages: {len(all_messages)} unique from imports")

        return all_messages

    async def get_coverage(self, group_id: str) -> Optional[Dict[str, Any]]:
        """
        Get import coverage for a group.

        Args:
            group_id: Group identifier

        Returns:
            Coverage information or None
        """
        sources_dir = self.archive_root / "sources" / "whatsapp"

        for d in sources_dir.iterdir():
            if d.is_dir() and d.name.endswith(f"_{group_id}"):
                manifest_file = d / "imports" / "import-manifest.json"
                if manifest_file.exists():
                    with open(manifest_file, 'r') as f:
                        manifest = json.load(f)
                    return manifest.get("coverage")

        return None
