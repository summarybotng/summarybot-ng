# ADR-064: Wiki Navigation Filters

## Status
Implemented

## Context

Currently, wiki pages are listed without filtering options. As wikis grow with more pages and sources, users need ways to:
- Find pages with the most authoritative content (multiple sources)
- See what's recently changed vs. established knowledge
- Filter by quality ratings
- Understand which AI model generated the synthesis

## Decision

Add comprehensive filtering to wiki navigation with the following filter dimensions:

### Filter Dimensions

| Filter | Type | Options |
|--------|------|---------|
| **Source Count** | Range | 1, 2-5, 5-10, 10+ |
| **Created Date** | Date Range | Today, This Week, This Month, Custom |
| **Updated Date** | Date Range | Today, This Week, This Month, Custom |
| **Rating** | Range | Unrated, 1-2★, 3-4★, 5★ |
| **Synthesis Model** | Multi-select | haiku, sonnet, opus, heuristic |
| **Has Synthesis** | Boolean | Yes, No, Any |
| **Confidence** | Range | Low (<50%), Medium (50-80%), High (>80%) |

---

## Data Model Changes

### WikiPage Table Extension

```sql
-- ADR-064: Add rating and model tracking
ALTER TABLE wiki_pages ADD COLUMN rating INTEGER;  -- 1-5 stars, NULL = unrated
ALTER TABLE wiki_pages ADD COLUMN rating_count INTEGER DEFAULT 0;
ALTER TABLE wiki_pages ADD COLUMN synthesis_model TEXT;  -- Model used for synthesis
```

### WikiPageSummary Model Update

```python
@dataclass
class WikiPageSummary:
    id: str
    path: str
    title: str
    topics: List[str]
    updated_at: Optional[datetime]
    created_at: Optional[datetime]  # NEW
    inbound_links: int
    confidence: int
    source_count: int  # NEW: len(source_refs)
    rating: Optional[float]  # NEW: Average rating
    rating_count: int  # NEW: Number of ratings
    has_synthesis: bool  # NEW
    synthesis_model: Optional[str]  # NEW
```

---

## API Changes

### Updated List Pages Endpoint

```
GET /guilds/{guild_id}/wiki/pages
```

**New Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `min_sources` | int | Minimum source count |
| `max_sources` | int | Maximum source count |
| `created_after` | datetime | Created after date |
| `created_before` | datetime | Created before date |
| `updated_after` | datetime | Updated after date |
| `updated_before` | datetime | Updated before date |
| `min_rating` | float | Minimum average rating |
| `has_synthesis` | bool | Filter by synthesis presence |
| `synthesis_model` | string[] | Filter by model(s) |
| `min_confidence` | int | Minimum confidence score |
| `sort_by` | string | Sort field |
| `sort_order` | string | asc/desc |

**Sort Options:**
- `updated_at` (default)
- `created_at`
- `rating`
- `source_count`
- `confidence`
- `title`

### Response Enhancement

```json
{
  "total": 150,
  "filtered": 42,
  "pages": [...],
  "facets": {
    "source_count": { "1": 20, "2-5": 50, "5-10": 30, "10+": 10 },
    "rating": { "unrated": 80, "1-2": 5, "3-4": 20, "5": 15 },
    "synthesis_model": { "haiku": 60, "sonnet": 30, "heuristic": 30 },
    "has_synthesis": { "true": 100, "false": 50 }
  }
}
```

---

## Frontend Implementation

### Filter Panel Component

```tsx
function WikiFilterPanel({
  filters,
  onFilterChange,
  facets
}: WikiFilterPanelProps) {
  return (
    <div className="space-y-4 p-4 border rounded-lg">
      {/* Source Count */}
      <div>
        <Label>Sources</Label>
        <div className="flex gap-2 mt-2">
          <Badge variant={filters.minSources === 1 ? "default" : "outline"}
                 onClick={() => onFilterChange({ minSources: 1, maxSources: 1 })}>
            1 ({facets.source_count["1"]})
          </Badge>
          <Badge variant={filters.minSources === 2 ? "default" : "outline"}
                 onClick={() => onFilterChange({ minSources: 2, maxSources: 5 })}>
            2-5 ({facets.source_count["2-5"]})
          </Badge>
          <Badge variant={filters.minSources === 5 ? "default" : "outline"}
                 onClick={() => onFilterChange({ minSources: 5, maxSources: 10 })}>
            5-10 ({facets.source_count["5-10"]})
          </Badge>
          <Badge variant={filters.minSources === 10 ? "default" : "outline"}
                 onClick={() => onFilterChange({ minSources: 10 })}>
            10+ ({facets.source_count["10+"]})
          </Badge>
        </div>
      </div>

      {/* Date Filters */}
      <div>
        <Label>Updated</Label>
        <Select value={filters.updatedPreset} onValueChange={handleDateChange}>
          <SelectItem value="any">Any time</SelectItem>
          <SelectItem value="today">Today</SelectItem>
          <SelectItem value="week">This week</SelectItem>
          <SelectItem value="month">This month</SelectItem>
          <SelectItem value="custom">Custom range</SelectItem>
        </Select>
      </div>

      {/* Rating Filter */}
      <div>
        <Label>Rating</Label>
        <Slider
          min={0}
          max={5}
          step={1}
          value={[filters.minRating || 0]}
          onValueChange={([v]) => onFilterChange({ minRating: v })}
        />
        <span className="text-sm text-muted-foreground">
          {filters.minRating ? `${filters.minRating}+ stars` : "Any rating"}
        </span>
      </div>

      {/* Synthesis Model */}
      <div>
        <Label>Synthesis Model</Label>
        <div className="flex gap-2 mt-2 flex-wrap">
          {["haiku", "sonnet", "opus", "heuristic"].map(model => (
            <Badge
              key={model}
              variant={filters.synthesisModels?.includes(model) ? "default" : "outline"}
              onClick={() => toggleModel(model)}
            >
              {model} ({facets.synthesis_model[model] || 0})
            </Badge>
          ))}
        </div>
      </div>

      {/* Has Synthesis */}
      <div className="flex items-center gap-2">
        <Checkbox
          checked={filters.hasSynthesis === true}
          onCheckedChange={(v) => onFilterChange({ hasSynthesis: v || undefined })}
        />
        <Label>Has AI synthesis</Label>
      </div>

      {/* Clear Filters */}
      <Button variant="ghost" size="sm" onClick={() => onFilterChange({})}>
        Clear all filters
      </Button>
    </div>
  );
}
```

### URL State Management

Filters persist in URL for shareability:
```
/guilds/123/wiki?min_sources=5&updated_after=2024-01-01&min_rating=4&sort_by=rating
```

---

## Repository Changes

```python
async def list_pages(
    self,
    guild_id: str,
    category: Optional[str] = None,
    min_sources: Optional[int] = None,
    max_sources: Optional[int] = None,
    created_after: Optional[datetime] = None,
    created_before: Optional[datetime] = None,
    updated_after: Optional[datetime] = None,
    updated_before: Optional[datetime] = None,
    min_rating: Optional[float] = None,
    has_synthesis: Optional[bool] = None,
    synthesis_models: Optional[List[str]] = None,
    min_confidence: Optional[int] = None,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> List[WikiPageSummary]:
    """List pages with filtering and sorting."""

    query = "SELECT * FROM wiki_pages WHERE guild_id = ?"
    params = [guild_id]

    if min_sources is not None:
        query += " AND json_array_length(source_refs) >= ?"
        params.append(min_sources)

    if max_sources is not None:
        query += " AND json_array_length(source_refs) <= ?"
        params.append(max_sources)

    if created_after:
        query += " AND created_at >= ?"
        params.append(created_after.isoformat())

    if updated_after:
        query += " AND updated_at >= ?"
        params.append(updated_after.isoformat())

    if min_rating is not None:
        query += " AND rating >= ?"
        params.append(min_rating)

    if has_synthesis is not None:
        if has_synthesis:
            query += " AND synthesis IS NOT NULL"
        else:
            query += " AND synthesis IS NULL"

    if synthesis_models:
        placeholders = ",".join("?" * len(synthesis_models))
        query += f" AND synthesis_model IN ({placeholders})"
        params.extend(synthesis_models)

    # Sorting
    valid_sort_fields = ["updated_at", "created_at", "rating", "confidence", "title"]
    if sort_by in valid_sort_fields:
        query += f" ORDER BY {sort_by} {sort_order.upper()}"

    query += " LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = await self.connection.fetch_all(query, tuple(params))
    return [self._row_to_page_summary(row) for row in rows]
```

---

## Implementation Order

```
1. 065_wiki_filters.sql - Add rating/model columns
2. src/wiki/models.py - Update WikiPageSummary
3. src/data/sqlite/wiki_repository.py - Add filter parameters
4. src/dashboard/routes/wiki.py - Update list endpoint
5. src/frontend/src/pages/Wiki.tsx - Add filter panel
6. src/frontend/src/pages/Wiki.tsx - URL state sync
```

---

## Consequences

### Positive
- Users can quickly find high-quality, well-sourced pages
- Filtering by date helps track knowledge evolution
- Model filtering enables quality comparison
- Faceted counts guide exploration

### Negative
- More complex queries may impact performance
- Additional database columns
- More frontend complexity

### Mitigations
- Index on rating, updated_at, created_at, synthesis_model
- Lazy-load facet counts
- Cache common filter combinations

---

## Implementation Notes (Added 2026-04-26)

### Links Tooltip
The "Links" stat card now shows a tooltip on hover displaying:
- `{inbound_links} inbound · {outbound_links} outbound`

This helps users understand the link breakdown without cluttering the UI.

### Related Pages Section
A new "Related Pages" section appears at the bottom of wiki pages showing:
- **Links to:** Pages this page references (outbound links)
- **Linked from:** Pages that reference this page (inbound links)

All links are clickable for easy navigation between related wiki pages.

### API Changes
- Added `linked_pages_from` and `linked_pages_to` to `WikiPageDetailResponse`
- Added `get_sources_by_ids()` method to wiki repository

---

## References

- [ADR-056: Compounding Wiki - Standard](./ADR-056-compounding-wiki-standard.md)
- [ADR-063: Wiki Page Tabs](./ADR-063-wiki-page-tabs.md)
