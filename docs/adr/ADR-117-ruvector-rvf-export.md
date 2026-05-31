# ADR-117: RuVector RVF File Export

**Status:** Accepted
**Date:** 2026-05-31
**Depends on:** ADR-092 (RuVector Explorer Dashboard), ADR-057 (RuVector Semantic Store)

## Context

The RuVector Explorer (ADR-092) provides a "Browse Units" tab that displays knowledge units extracted from summaries. Users can view statistics, search semantically, and browse all units. However, there is no way to export this knowledge data for:

1. **Offline analysis** - Users may want to analyze units in external tools (Jupyter, Excel, custom scripts)
2. **Backup/archival** - Knowledge stores should be exportable for disaster recovery
3. **Cross-system sharing** - Units could be imported into other RuVector-compatible systems
4. **ML/AI training** - Embeddings and unit data are valuable for fine-tuning or evaluation

The existing API endpoints return JSON, but this is inefficient for large exports with high-dimensional embeddings (1536 floats per unit).

## Decision

Introduce the **RVF (RuVector Format)** file format and add a download button to the Browse Units tab that exports knowledge units as `.rvf` files.

### RVF File Format Specification

RVF is a binary format optimized for vector data with metadata. It uses a header + records structure:

```
┌─────────────────────────────────────────────────────────────┐
│ Header (64 bytes)                                           │
├─────────────────────────────────────────────────────────────┤
│ Magic Number     │ 4 bytes  │ "RVF1" (0x52 0x56 0x46 0x31) │
│ Version          │ 2 bytes  │ uint16 (1)                   │
│ Flags            │ 2 bytes  │ uint16 (reserved)            │
│ Embedding Dim    │ 4 bytes  │ uint32 (1536 default)        │
│ Unit Count       │ 4 bytes  │ uint32                       │
│ Guild ID Length  │ 2 bytes  │ uint16                       │
│ Guild ID         │ variable │ UTF-8 string                 │
│ Created At       │ 8 bytes  │ int64 (Unix ms)              │
│ Checksum         │ 4 bytes  │ CRC32 of records             │
│ Reserved         │ padding  │ To 64-byte boundary          │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Records (variable length each)                              │
├─────────────────────────────────────────────────────────────┤
│ Record Length    │ 4 bytes  │ uint32 (total record bytes)  │
│ Unit ID Length   │ 2 bytes  │ uint16                       │
│ Unit ID          │ variable │ UTF-8 string                 │
│ Unit Type        │ 1 byte   │ enum (0-6)                   │
│ Content Length   │ 4 bytes  │ uint32                       │
│ Content          │ variable │ UTF-8 string                 │
│ Source ID Length │ 2 bytes  │ uint16                       │
│ Source ID        │ variable │ UTF-8 string                 │
│ Source Channel   │ 2 + var  │ length-prefixed UTF-8        │
│ Source Date      │ 4 bytes  │ uint32 (Unix days from epoch)│
│ Confidence       │ 4 bytes  │ float32                      │
│ Has Embedding    │ 1 byte   │ bool                         │
│ Embedding        │ 6144 b   │ float32[1536] (if present)   │
└─────────────────────────────────────────────────────────────┘
```

#### Unit Type Enum
| Value | Type |
|-------|------|
| 0 | claim |
| 1 | decision |
| 2 | question |
| 3 | action_item |
| 4 | context |
| 5 | definition |
| 6 | reference |

### Export Options

The download dialog offers these options:

| Option | Default | Description |
|--------|---------|-------------|
| Include Embeddings | No | Include 1536-dim vectors (increases file size ~6KB/unit) |
| Unit Types | All | Filter by specific unit types |
| Date Range | All | Filter by source date |
| Format | RVF | RVF binary or JSON fallback |

### File Size Estimates

| Units | Without Embeddings | With Embeddings |
|-------|-------------------|-----------------|
| 1,000 | ~200 KB | ~6.2 MB |
| 10,000 | ~2 MB | ~62 MB |
| 100,000 | ~20 MB | ~620 MB |

## Implementation

### API Endpoint

```
GET /ruvector/guilds/{guild_id}/export
  ?format=rvf|json
  &include_embeddings=true|false
  &unit_types=claim,decision
  &start_date=2025-01-01
  &end_date=2025-12-31

Response: application/octet-stream (RVF) or application/json
Content-Disposition: attachment; filename="knowledge_{guild_id}_{timestamp}.rvf"
```

### Backend Changes

| File | Change |
|------|--------|
| `src/dashboard/routes/ruvector.py` | Add `/export` endpoint with streaming response |
| `src/wiki/ruvector/rvf_format.py` | New file: RVF encoder/decoder classes |

### Frontend Changes

| File | Change |
|------|--------|
| `src/frontend/src/pages/RuVectorExplorer.tsx` | Add download button to Browse tab |
| `src/frontend/src/components/ruvector/ExportDialog.tsx` | New file: Export options dialog |

### RVF Encoder (Python)

```python
import struct
import zlib
from typing import List, Optional
from dataclasses import dataclass

@dataclass
class RvfHeader:
    magic: bytes = b'RVF1'
    version: int = 1
    flags: int = 0
    embedding_dim: int = 1536
    unit_count: int = 0
    guild_id: str = ""
    created_at: int = 0
    checksum: int = 0

class RvfEncoder:
    UNIT_TYPES = {
        'claim': 0, 'decision': 1, 'question': 2,
        'action_item': 3, 'context': 4, 'definition': 5, 'reference': 6
    }

    def encode(self, units: List[dict], guild_id: str,
               include_embeddings: bool = False) -> bytes:
        """Encode knowledge units to RVF binary format."""
        records = b''
        for unit in units:
            records += self._encode_record(unit, include_embeddings)

        header = self._encode_header(
            guild_id=guild_id,
            unit_count=len(units),
            embedding_dim=1536 if include_embeddings else 0,
            checksum=zlib.crc32(records)
        )

        return header + records
```

### Frontend Download Button

```tsx
// In RuVectorExplorer.tsx Browse tab
<Button
  onClick={() => setExportDialogOpen(true)}
  variant="outline"
  className="gap-2"
>
  <Download className="h-4 w-4" />
  Export RVF
</Button>
```

## Security Considerations

1. **Rate limiting** - Export endpoint should be rate-limited (1 request/minute)
2. **Size limits** - Maximum 100,000 units per export to prevent OOM
3. **Authentication** - Requires valid guild access via existing auth flow
4. **Audit logging** - Log exports to guild audit trail

## Testing

1. **Unit tests** - RVF encoder/decoder round-trip validation
2. **Integration tests** - Export endpoint with various filters
3. **Load tests** - Export of 50,000 units with embeddings
4. **Compatibility tests** - RVF files readable by reference decoder

## Future Extensions

1. **RVF Import** - Upload RVF files to restore or merge knowledge stores
2. **Streaming export** - For very large exports (>100K units)
3. **Compression** - Optional gzip compression for RVF files
4. **Incremental export** - Export only units newer than a given timestamp
5. **Edge export** - Include relationship edges in RVF v2

## Alternatives Considered

### 1. JSON Export Only
- **Pros**: Simple, human-readable
- **Cons**: Inefficient for embeddings (base64 or float arrays bloat file 3x)

### 2. Parquet Format
- **Pros**: Industry standard, columnar compression
- **Cons**: Heavy dependency, overkill for typical export sizes

### 3. SQLite Dump
- **Pros**: Portable, queryable
- **Cons**: Includes schema overhead, not optimized for vectors

## References

- [ADR-057: Compounding Wiki with RuVector](./ADR-057-compounding-wiki-ruvector.md)
- [ADR-092: RuVector Explorer Dashboard](./ADR-092-ruvector-explorer-page.md)
- [RuVector Knowledge System Documentation](../ruvector-knowledge-system.md)
