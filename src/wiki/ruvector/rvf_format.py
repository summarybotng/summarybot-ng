"""
RVF (RuVector Format) encoder/decoder for knowledge unit export.

ADR-117: Binary format optimized for vector data with metadata.
"""

import struct
import zlib
import io
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, BinaryIO, Iterator
import logging

logger = logging.getLogger(__name__)

# Magic number and version
RVF_MAGIC = b'RVF1'
RVF_VERSION = 1

# Unit type mapping
UNIT_TYPE_TO_INT = {
    'claim': 0,
    'decision': 1,
    'question': 2,
    'action_item': 3,
    'context': 4,
    'definition': 5,
    'reference': 6,
}

INT_TO_UNIT_TYPE = {v: k for k, v in UNIT_TYPE_TO_INT.items()}


@dataclass
class RvfHeader:
    """RVF file header (64 bytes)."""
    magic: bytes = RVF_MAGIC
    version: int = RVF_VERSION
    flags: int = 0
    embedding_dim: int = 1536
    unit_count: int = 0
    guild_id: str = ""
    created_at: int = 0  # Unix milliseconds
    checksum: int = 0


class RvfEncoder:
    """
    Encodes knowledge units to RVF binary format.

    Format:
    - 64-byte header with metadata and checksum
    - Variable-length records for each unit
    """

    HEADER_SIZE = 64

    def __init__(self, embedding_dim: int = 1536):
        self.embedding_dim = embedding_dim

    def encode(
        self,
        units: List[Dict[str, Any]],
        guild_id: str,
        include_embeddings: bool = False
    ) -> bytes:
        """
        Encode knowledge units to RVF binary format.

        Args:
            units: List of knowledge unit dictionaries
            guild_id: Guild ID for the export
            include_embeddings: Whether to include embedding vectors

        Returns:
            RVF binary data
        """
        # Encode all records first to calculate checksum
        records = b''
        for unit in units:
            records += self._encode_record(unit, include_embeddings)

        # Calculate checksum
        checksum = zlib.crc32(records) & 0xFFFFFFFF

        # Create header
        header = self._encode_header(
            guild_id=guild_id,
            unit_count=len(units),
            embedding_dim=self.embedding_dim if include_embeddings else 0,
            checksum=checksum
        )

        return header + records

    def encode_streaming(
        self,
        units: Iterator[Dict[str, Any]],
        guild_id: str,
        include_embeddings: bool = False
    ) -> Iterator[bytes]:
        """
        Encode knowledge units as a stream (for large exports).

        Note: Streaming mode cannot include checksum in header.
        Sets checksum to 0 and flags bit 0 to indicate streaming mode.

        Yields:
            Chunks of RVF binary data
        """
        # Yield placeholder header first (will have checksum=0)
        unit_count = 0

        # Buffer to count units
        buffered_records = []

        for unit in units:
            record = self._encode_record(unit, include_embeddings)
            buffered_records.append(record)
            unit_count += 1

            # Yield in batches of 100 records
            if len(buffered_records) >= 100:
                if unit_count == 100:
                    # First batch - yield header
                    header = self._encode_header(
                        guild_id=guild_id,
                        unit_count=0,  # Unknown in streaming mode
                        embedding_dim=self.embedding_dim if include_embeddings else 0,
                        checksum=0,
                        flags=1  # Streaming mode flag
                    )
                    yield header

                for rec in buffered_records:
                    yield rec
                buffered_records = []

        # Yield remaining records
        if unit_count > 0 and unit_count < 100:
            # Small export - yield header with count
            header = self._encode_header(
                guild_id=guild_id,
                unit_count=unit_count,
                embedding_dim=self.embedding_dim if include_embeddings else 0,
                checksum=0,
                flags=1
            )
            yield header

        for rec in buffered_records:
            yield rec

    def _encode_header(
        self,
        guild_id: str,
        unit_count: int,
        embedding_dim: int,
        checksum: int,
        flags: int = 0
    ) -> bytes:
        """Encode 64-byte RVF header."""
        buffer = io.BytesIO()

        # Magic (4 bytes)
        buffer.write(RVF_MAGIC)

        # Version (2 bytes)
        buffer.write(struct.pack('<H', RVF_VERSION))

        # Flags (2 bytes)
        buffer.write(struct.pack('<H', flags))

        # Embedding dimension (4 bytes)
        buffer.write(struct.pack('<I', embedding_dim))

        # Unit count (4 bytes)
        buffer.write(struct.pack('<I', unit_count))

        # Guild ID length + string (2 + variable bytes)
        guild_id_bytes = guild_id.encode('utf-8')
        buffer.write(struct.pack('<H', len(guild_id_bytes)))
        buffer.write(guild_id_bytes)

        # Created at (8 bytes) - Unix milliseconds
        created_at = int(datetime.utcnow().timestamp() * 1000)
        buffer.write(struct.pack('<Q', created_at))

        # Checksum (4 bytes)
        buffer.write(struct.pack('<I', checksum))

        # Pad to 64 bytes
        current_size = buffer.tell()
        if current_size < self.HEADER_SIZE:
            buffer.write(b'\x00' * (self.HEADER_SIZE - current_size))

        return buffer.getvalue()[:self.HEADER_SIZE]

    def _encode_record(self, unit: Dict[str, Any], include_embeddings: bool) -> bytes:
        """Encode a single knowledge unit record."""
        buffer = io.BytesIO()

        # Reserve 4 bytes for record length (will fill in at end)
        buffer.write(b'\x00\x00\x00\x00')

        # Unit ID (2 + variable bytes)
        unit_id = str(unit.get('id', ''))
        unit_id_bytes = unit_id.encode('utf-8')
        buffer.write(struct.pack('<H', len(unit_id_bytes)))
        buffer.write(unit_id_bytes)

        # Unit type (1 byte)
        unit_type = unit.get('unit_type', 'context')
        unit_type_int = UNIT_TYPE_TO_INT.get(unit_type, 4)  # Default to context
        buffer.write(struct.pack('<B', unit_type_int))

        # Content (4 + variable bytes)
        content = str(unit.get('content', ''))
        content_bytes = content.encode('utf-8')
        buffer.write(struct.pack('<I', len(content_bytes)))
        buffer.write(content_bytes)

        # Source ID (2 + variable bytes)
        source_id = str(unit.get('source_id', ''))
        source_id_bytes = source_id.encode('utf-8')
        buffer.write(struct.pack('<H', len(source_id_bytes)))
        buffer.write(source_id_bytes)

        # Source channel (2 + variable bytes)
        source_channel = unit.get('source_channel') or ''
        source_channel_bytes = source_channel.encode('utf-8')
        buffer.write(struct.pack('<H', len(source_channel_bytes)))
        buffer.write(source_channel_bytes)

        # Source date (4 bytes) - Days since Unix epoch
        source_date = unit.get('source_date')
        if source_date:
            if isinstance(source_date, str):
                try:
                    dt = datetime.fromisoformat(source_date.replace('Z', '+00:00'))
                    days = (dt.date() - date(1970, 1, 1)).days
                except:
                    days = 0
            elif isinstance(source_date, (date, datetime)):
                if isinstance(source_date, datetime):
                    source_date = source_date.date()
                days = (source_date - date(1970, 1, 1)).days
            else:
                days = 0
        else:
            days = 0
        buffer.write(struct.pack('<I', days))

        # Confidence/score (4 bytes)
        confidence = float(unit.get('score', unit.get('confidence', 0.0)))
        buffer.write(struct.pack('<f', confidence))

        # Has embedding (1 byte)
        embedding = unit.get('embedding') if include_embeddings else None
        has_embedding = embedding is not None and len(embedding) > 0
        buffer.write(struct.pack('<B', 1 if has_embedding else 0))

        # Embedding (1536 * 4 = 6144 bytes if present)
        if has_embedding and embedding:
            # Ensure we have exactly embedding_dim floats
            if len(embedding) < self.embedding_dim:
                embedding = list(embedding) + [0.0] * (self.embedding_dim - len(embedding))
            elif len(embedding) > self.embedding_dim:
                embedding = embedding[:self.embedding_dim]

            for val in embedding:
                buffer.write(struct.pack('<f', float(val)))

        # Get full record and update length
        record = buffer.getvalue()
        record_length = len(record)

        # Replace first 4 bytes with actual length
        record = struct.pack('<I', record_length) + record[4:]

        return record


class RvfDecoder:
    """
    Decodes RVF binary format to knowledge units.
    """

    HEADER_SIZE = 64

    def decode(self, data: bytes) -> tuple[RvfHeader, List[Dict[str, Any]]]:
        """
        Decode RVF binary data to header and units.

        Args:
            data: RVF binary data

        Returns:
            Tuple of (header, list of unit dictionaries)
        """
        buffer = io.BytesIO(data)

        # Decode header
        header = self._decode_header(buffer)

        # Decode records
        units = []
        while buffer.tell() < len(data):
            unit = self._decode_record(buffer, header.embedding_dim)
            if unit:
                units.append(unit)

        return header, units

    def _decode_header(self, buffer: BinaryIO) -> RvfHeader:
        """Decode RVF header from buffer."""
        header = RvfHeader()

        # Magic (4 bytes)
        header.magic = buffer.read(4)
        if header.magic != RVF_MAGIC:
            raise ValueError(f"Invalid RVF magic: {header.magic}")

        # Version (2 bytes)
        header.version = struct.unpack('<H', buffer.read(2))[0]

        # Flags (2 bytes)
        header.flags = struct.unpack('<H', buffer.read(2))[0]

        # Embedding dimension (4 bytes)
        header.embedding_dim = struct.unpack('<I', buffer.read(4))[0]

        # Unit count (4 bytes)
        header.unit_count = struct.unpack('<I', buffer.read(4))[0]

        # Guild ID (2 + variable bytes)
        guild_id_len = struct.unpack('<H', buffer.read(2))[0]
        header.guild_id = buffer.read(guild_id_len).decode('utf-8')

        # Created at (8 bytes)
        header.created_at = struct.unpack('<Q', buffer.read(8))[0]

        # Checksum (4 bytes)
        header.checksum = struct.unpack('<I', buffer.read(4))[0]

        # Skip to end of header
        buffer.seek(self.HEADER_SIZE)

        return header

    def _decode_record(self, buffer: BinaryIO, embedding_dim: int) -> Optional[Dict[str, Any]]:
        """Decode a single knowledge unit record."""
        try:
            # Record length (4 bytes)
            record_length_data = buffer.read(4)
            if len(record_length_data) < 4:
                return None
            record_length = struct.unpack('<I', record_length_data)[0]

            # Unit ID (2 + variable bytes)
            unit_id_len = struct.unpack('<H', buffer.read(2))[0]
            unit_id = buffer.read(unit_id_len).decode('utf-8')

            # Unit type (1 byte)
            unit_type_int = struct.unpack('<B', buffer.read(1))[0]
            unit_type = INT_TO_UNIT_TYPE.get(unit_type_int, 'context')

            # Content (4 + variable bytes)
            content_len = struct.unpack('<I', buffer.read(4))[0]
            content = buffer.read(content_len).decode('utf-8')

            # Source ID (2 + variable bytes)
            source_id_len = struct.unpack('<H', buffer.read(2))[0]
            source_id = buffer.read(source_id_len).decode('utf-8')

            # Source channel (2 + variable bytes)
            source_channel_len = struct.unpack('<H', buffer.read(2))[0]
            source_channel = buffer.read(source_channel_len).decode('utf-8') if source_channel_len > 0 else None

            # Source date (4 bytes)
            days = struct.unpack('<I', buffer.read(4))[0]
            source_date = (date(1970, 1, 1) + timedelta(days=days)).isoformat() if days > 0 else None

            # Confidence (4 bytes)
            confidence = struct.unpack('<f', buffer.read(4))[0]

            # Has embedding (1 byte)
            has_embedding = struct.unpack('<B', buffer.read(1))[0] == 1

            # Embedding
            embedding = None
            if has_embedding and embedding_dim > 0:
                embedding = []
                for _ in range(embedding_dim):
                    val = struct.unpack('<f', buffer.read(4))[0]
                    embedding.append(val)

            return {
                'id': unit_id,
                'unit_type': unit_type,
                'content': content,
                'source_id': source_id,
                'source_channel': source_channel,
                'source_date': source_date,
                'score': confidence,
                'embedding': embedding,
            }

        except Exception as e:
            logger.warning(f"Failed to decode RVF record: {e}")
            return None


# Convenience functions
def encode_units_to_rvf(
    units: List[Dict[str, Any]],
    guild_id: str,
    include_embeddings: bool = False
) -> bytes:
    """Encode knowledge units to RVF format."""
    encoder = RvfEncoder()
    return encoder.encode(units, guild_id, include_embeddings)


def decode_rvf_to_units(data: bytes) -> tuple[RvfHeader, List[Dict[str, Any]]]:
    """Decode RVF data to knowledge units."""
    decoder = RvfDecoder()
    return decoder.decode(data)
