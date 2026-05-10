# ADR-092: RuVector Explorer Dashboard

**Status:** Accepted
**Date:** 2026-05-10
**Depends on:** ADR-057 (RuVector Semantic Store), ADR-090 (Inline KU Extraction)

## Context

ADR-090 implemented inline knowledge unit (KU) extraction during summarization, with a backfill job that populated ~39,000 KUs into RuVector for the Agentics Foundation guild. However, there was no dedicated UI to explore, search, and visualize this knowledge store.

Existing access methods were limited to:
1. REST API endpoints (`/ruvector/guilds/{id}/search`, `/ruvector/guilds/{id}/stats`)
2. Direct database queries via `flyctl ssh console`
3. Wiki page-level "Re-extract KUs" button (deprecated per ADR-090)

Users needed a way to:
- See statistics about their knowledge store
- Semantically search across all extracted knowledge
- Browse units by type
- Understand the distribution of knowledge types

## Decision

Add a **RuVector Explorer** page to the dashboard at `/guilds/{id}/ruvector` that provides:

### 1. Statistics Overview
Four summary cards showing:
- **Total Units** - Count of knowledge units stored
- **Edges** - Relationship count between units
- **Embeddings** - Percentage of units with vector embeddings
- **Signals** - Feedback signals collected

### 2. Semantic Search Tab
- Natural language search input
- Unit type filter (claims, decisions, questions, etc.)
- Results ranked by embedding similarity
- Search latency displayed

### 3. Browse Tab
- List all units without semantic search
- Filter by unit type
- Configurable result limit (25-200)

### 4. Breakdown Charts
- **Units by Type** - Horizontal bar chart showing distribution
- **Edges by Type** - Relationship type distribution

## Implementation

### New Files

| File | Purpose |
|------|---------|
| `src/frontend/src/pages/RuVectorExplorer.tsx` | Main explorer page component |

### Modified Files

| File | Change |
|------|--------|
| `src/frontend/src/App.tsx` | Add `/ruvector` route |
| `src/frontend/src/components/layout/GuildSidebar.tsx` | Add navigation link |

### API Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `GET /ruvector/guilds/{id}/stats` | Statistics for overview cards |
| `GET /ruvector/guilds/{id}/search?q=...` | Semantic search |
| `GET /ruvector/guilds/{id}/units` | Browse without search |

### Component Structure

```
RuVectorExplorer
├── StatsOverview (4 summary cards)
├── Tabs
│   ├── SearchTab (semantic search)
│   └── BrowseTab (list all)
├── UnitTypeBreakdown (bar chart)
└── EdgeTypeBreakdown (bar chart)
```

### Unit Type Icons

| Type | Icon | Color |
|------|------|-------|
| claim | Lightbulb | Yellow |
| decision | CheckSquare | Green |
| question | HelpCircle | Blue |
| action_item | Zap | Orange |
| context | MessageSquare | Purple |
| definition | BookOpen | Indigo |
| reference | Link | Cyan |

## Navigation

Added to sidebar between "Wiki" and "Coverage":
```
Wiki → RuVector → Coverage
```

Uses Database icon to represent the semantic knowledge store.

## Consequences

### Positive
- Users can explore extracted knowledge without API calls or SSH
- Semantic search enables finding related information across channels
- Type distribution shows what kinds of knowledge are being captured
- Low barrier to understanding RuVector's value

### Negative
- Additional frontend bundle size (~15KB gzipped)
- One more page to maintain

### Neutral
- No backend changes required (uses existing API)
- Embeddings percentage may show 0% until embedding service is configured

## Future Enhancements

1. **Knowledge Graph Visualization** - D3/vis.js network graph of units and edges
2. **Unit Detail Panel** - Click to see related units, source summary, edges
3. **Embedding 2D/3D Scatter** - t-SNE/UMAP reduction for visual clustering
4. **Export** - Download units as JSON/CSV
5. **Bulk Operations** - Select and delete, re-embed, etc.

## References

- ADR-057: RuVector Semantic Knowledge Store
- ADR-090: Inline KU Extraction (Backfill Integration)
- `/ruvector/guilds/{id}/search` API specification
