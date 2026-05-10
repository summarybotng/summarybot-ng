# ADR-093: RuVector Knowledge Graph Visualization

**Status:** Proposed
**Date:** 2026-05-10
**Depends on:** ADR-057 (RuVector), ADR-090 (Inline KU), ADR-092 (RuVector Explorer)

## Context

RuVector stores ~39,000 knowledge units with relationships (edges) between them. ADR-092 added a RuVector Explorer with search and browse capabilities, but users cannot visualize the **structure** of their knowledge:

- Which topics cluster together?
- How are decisions connected to their context?
- What questions remain unanswered?
- How do knowledge units relate across channels?

The existing `wiki_knowledge_edges` table stores relationships:
- `relates_to` - semantic similarity
- `supports` - evidence relationship
- `contradicts` - opposing views
- `answers` - question→answer links
- `follows_from` - temporal/logical sequence

## Decision

Add a **Knowledge Graph** tab to the RuVector Explorer that visualizes units and edges as an interactive network graph.

### Visualization Library

**Selected: React Flow** (https://reactflow.dev/)
- Already in the React ecosystem
- Lightweight (~45KB gzipped)
- Built-in pan/zoom, selection, minimap
- Custom node/edge rendering
- Good performance up to ~1000 nodes

**Alternatives considered:**
- D3.js: Too low-level, requires more code
- vis.js: Heavier, less React-native
- Cytoscape.js: Overkill for our needs
- Sigma.js: Better for huge graphs, but more complex

### Graph Features

1. **Node Types** - Different shapes/colors per unit type:
   | Type | Shape | Color |
   |------|-------|-------|
   | claim | circle | yellow |
   | decision | diamond | green |
   | question | hexagon | blue |
   | action_item | triangle | orange |
   | context | rectangle | purple |
   | definition | octagon | indigo |
   | reference | pill | cyan |

2. **Edge Types** - Different line styles:
   | Type | Style | Color |
   |------|-------|-------|
   | relates_to | dashed | gray |
   | supports | solid | green |
   | contradicts | dotted | red |
   | answers | solid arrow | blue |
   | follows_from | solid arrow | purple |

3. **Interactions**:
   - Click node: Show unit details in sidebar
   - Hover edge: Show relationship type
   - Double-click: Focus on node and neighbors
   - Search highlight: Find nodes matching query
   - Filter by type: Show/hide unit types
   - Filter by channel: Show units from specific channels

4. **Layout Algorithms**:
   - Force-directed (default): Natural clustering
   - Hierarchical: For follows_from relationships
   - Radial: Centered on selected node

5. **Controls**:
   - Zoom slider
   - Minimap toggle
   - Layout selector
   - Node limit (50/100/200/500)
   - Reset view button

### API Endpoint

New endpoint to fetch graph data efficiently:

```
GET /ruvector/guilds/{guild_id}/graph
  ?limit=100          # Max nodes
  &center_unit_id=... # Optional: center on specific unit
  &unit_types=claim,decision  # Filter by types
  &channel=...        # Filter by channel
  &depth=2            # Traversal depth from center
```

Response:
```json
{
  "nodes": [
    {
      "id": "ku_123",
      "content": "...",
      "unit_type": "claim",
      "source_channel": "#general",
      "source_date": "2026-05-01"
    }
  ],
  "edges": [
    {
      "id": "edge_1",
      "source": "ku_123",
      "target": "ku_456",
      "edge_type": "supports",
      "weight": 0.85
    }
  ],
  "total_nodes": 500,
  "total_edges": 1200
}
```

### Implementation Plan

#### Phase 1: Basic Graph

| File | Changes |
|------|---------|
| `src/frontend/package.json` | Add `reactflow` dependency |
| `src/frontend/src/pages/RuVectorExplorer.tsx` | Add Graph tab |
| `src/frontend/src/components/ruvector/KnowledgeGraph.tsx` | New graph component |
| `src/dashboard/routes/ruvector.py` | Add `/graph` endpoint |

#### Phase 2: Interactions

| File | Changes |
|------|---------|
| `src/frontend/src/components/ruvector/GraphControls.tsx` | Zoom, layout, filters |
| `src/frontend/src/components/ruvector/NodeDetail.tsx` | Side panel for selected node |
| `src/frontend/src/components/ruvector/GraphLegend.tsx` | Type legend |

#### Phase 3: Performance

- Virtualization for large graphs
- WebGL rendering option via `@react-flow/node-resizer`
- Lazy loading of distant nodes
- Caching of graph data

### Database Query

Efficient query to fetch graph with edges:

```sql
-- Get top N units by recency
WITH top_units AS (
  SELECT id, content, unit_type, source_channel, source_date
  FROM wiki_knowledge_units
  WHERE guild_id = ?
  ORDER BY created_at DESC
  LIMIT ?
)
-- Get edges between these units
SELECT
  e.id,
  e.from_unit_id as source,
  e.to_unit_id as target,
  e.edge_type,
  e.weight
FROM wiki_knowledge_edges e
WHERE e.guild_id = ?
  AND e.from_unit_id IN (SELECT id FROM top_units)
  AND e.to_unit_id IN (SELECT id FROM top_units)
```

## Consequences

### Positive
- Users can explore knowledge structure visually
- Clusters reveal emergent topics
- Orphan units (no edges) highlight gaps
- Questions without answers are visible
- Cross-channel connections become apparent

### Negative
- Additional frontend dependency (~45KB)
- Graph rendering can be CPU-intensive for large datasets
- Layout algorithms may produce different results on each load

### Neutral
- Requires edge data to be meaningful (backfill edges separately)
- Graph is read-only initially (no editing)

## Future Enhancements

1. **Edge Creation** - Manually connect related units
2. **Cluster Labels** - Auto-generate topic names for clusters
3. **Time Animation** - Replay graph growth over time
4. **Export** - Download as SVG/PNG/JSON
5. **Embedding 2D Projection** - Position nodes by t-SNE/UMAP of embeddings

## References

- React Flow: https://reactflow.dev/
- ADR-057: RuVector Semantic Store
- ADR-092: RuVector Explorer
- `wiki_knowledge_edges` table schema
