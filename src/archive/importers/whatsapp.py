"""
WhatsApp chat history importer.

Supports two formats:
1. WhatsApp native export (.txt files)
2. Reader bot JSON export (from ADR-001)

Phase 6: WhatsApp Import
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

    def to_dict(self) -> Dict[str, Any]:
        return {
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
    DATETIME_PATTERNS = [
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
    ]

    def __init__(self, archive_root: Path):
        """
        Initialize WhatsApp importer.

        Args:
            archive_root: Root path of the archive
        """
        self.archive_root = archive_root

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
        )

        logger.info(f"Imported {len(messages)} messages from reader bot export")
        return result

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
            # Try DD/MM/YYYY first
            try:
                if len(parts[2]) == 4:
                    day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                elif len(parts[2]) == 2:
                    day, month, year = int(parts[0]), int(parts[1]), 2000 + int(parts[2])
                else:
                    raise ValueError("Unknown year format")

                # Validate
                if month > 12:
                    # Probably MM/DD/YYYY
                    day, month = month, day

            except ValueError:
                raise ValueError(f"Cannot parse date: {date_str}")

        else:
            raise ValueError(f"Cannot parse date: {date_str}")

        # Parse time
        time_str = time_str.strip()
        is_pm = 'PM' in time_str.upper()
        is_am = 'AM' in time_str.upper()
        time_str = re.sub(r'\s*[AP]M', '', time_str, flags=re.IGNORECASE)

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

    async def get_messages_for_period(
        self,
        group_id: str,
        start: datetime,
        end: datetime,
    ) -> List[Dict[str, Any]]:
        """
        Get imported messages for a time period.

        Args:
            group_id: Group identifier
            start: Period start
            end: Period end

        Returns:
            List of message dictionaries
        """
        # Find group directory
        sources_dir = self.archive_root / "sources" / "whatsapp"
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

        # Load all messages from all imports
        all_messages = []
        for msg_file in imports_dir.glob("*_messages.json"):
            with open(msg_file, 'r') as f:
                messages = json.load(f)

            for msg in messages:
                msg_time = datetime.fromisoformat(msg["timestamp"])
                if start <= msg_time <= end:
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
