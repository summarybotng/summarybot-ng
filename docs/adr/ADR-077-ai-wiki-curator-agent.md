# ADR-077: AI Wiki Curator Agent

## Status
Proposed

## Context
The compounding wiki accumulates content through automated ingest from summaries. While this builds knowledge over time, several curation challenges emerge:

1. **Low-quality pages** - Topics with sparse content or single sources lack depth
2. **Duplicate topics** - Similar concepts may spawn separate pages (e.g., "auth" vs "authentication")
3. **Stale content** - Outdated information persists without review
4. **Missing cross-references** - Related pages aren't linked effectively
5. **Contradictions** - Conflicting information across sources needs resolution
6. **Synthesis quality** - Auto-generated syntheses may need refinement

Manual curation doesn't scale. An AI agent with wiki-specific skills can proficiently maintain quality.

## Decision

### 1. Wiki Curator Agent

Introduce a specialized AI agent (`wiki-curator`) that runs periodically or on-demand to curate wiki content.

```python
class WikiCuratorAgent:
    """AI agent for wiki curation with specialized skills."""

    skills = [
        "topic_merger",        # Merge similar/duplicate topics
        "quality_assessor",    # Score page quality, flag issues
        "cross_linker",        # Improve cross-references
        "contradiction_resolver",  # Detect and resolve conflicts
        "content_pruner",      # Remove stale/redundant content
        "synthesis_improver",  # Enhance synthesis quality
        "gap_detector",        # Identify missing topics
    ]
```

### 2. Curation Skills

#### 2.1 Topic Merger
- Detect semantically similar pages (e.g., "API auth" + "authentication" + "oauth")
- Propose merges with consolidated content
- Preserve source references from both pages
- Update all cross-references to point to merged page

#### 2.2 Quality Assessor
- Score pages on: source count, recency, synthesis quality, link density
- Flag pages below threshold for review or deletion
- Identify pages ready for promotion (high quality, many sources)

#### 2.3 Cross-Linker
- Analyze content for unlinked topic mentions
- Add bidirectional links between related pages
- Build topic clusters for navigation

#### 2.4 Contradiction Resolver
- Detect conflicting statements across sources
- Present contradictions with context for resolution
- Auto-resolve when newer source supersedes older

#### 2.5 Content Pruner
- Remove duplicate key points (same content from multiple ingests)
- Archive pages with no recent activity and few sources
- Clean up orphan pages with no inbound links

#### 2.6 Synthesis Improver
- Re-synthesize pages with low ratings
- Add focus areas based on page topics
- Improve markdown formatting and structure

#### 2.7 Gap Detector
- Identify frequently mentioned but non-existent topics
- Suggest new pages based on conversation patterns
- Detect expertise gaps (topics without expert associations)

### 3. Curation Modes

#### 3.1 Scheduled Curation
```yaml
curation_schedule:
  daily:
    - quality_assessment
    - cross_linking
  weekly:
    - topic_merging
    - contradiction_detection
  monthly:
    - content_pruning
    - gap_analysis
```

#### 3.2 On-Demand Curation
- Triggered via dashboard: "Curate Wiki" button
- Scoped to specific categories or pages
- Progress tracking with preview before applying changes

#### 3.3 Real-Time Hints
- After ingest, suggest potential merges
- Flag contradictions immediately
- Recommend cross-links as content is added

### 4. Curation Actions

All curation actions are logged and reversible:

```python
@dataclass
class CurationAction:
    action_type: str  # merge, link, prune, resolve, improve
    target_pages: List[str]
    proposed_change: str
    confidence: float  # 0-1
    requires_approval: bool
    applied_at: Optional[datetime]
    applied_by: Optional[str]  # user or "auto"
```

### 5. Approval Workflow

| Confidence | Action |
|------------|--------|
| > 0.9 | Auto-apply (with undo option) |
| 0.7 - 0.9 | Queue for batch approval |
| < 0.7 | Manual review required |

### 6. Database Schema

```sql
CREATE TABLE wiki_curation_queue (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    target_pages TEXT NOT NULL,  -- JSON array
    proposed_change TEXT NOT NULL,
    confidence REAL NOT NULL,
    status TEXT DEFAULT 'pending',  -- pending, approved, rejected, applied
    created_at TEXT DEFAULT (datetime('now')),
    reviewed_by TEXT,
    reviewed_at TEXT,
    applied_at TEXT,
    FOREIGN KEY (guild_id) REFERENCES guilds(id)
);

CREATE TABLE wiki_curation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    target_pages TEXT NOT NULL,
    change_summary TEXT NOT NULL,
    applied_by TEXT NOT NULL,
    applied_at TEXT DEFAULT (datetime('now')),
    rollback_data TEXT,  -- JSON for undo
    FOREIGN KEY (guild_id) REFERENCES guilds(id)
);
```

### 7. API Endpoints

```
POST /guilds/{guild_id}/wiki/curate
  - Trigger curation run with specified skills

GET /guilds/{guild_id}/wiki/curation/queue
  - List pending curation actions

POST /guilds/{guild_id}/wiki/curation/{action_id}/approve
POST /guilds/{guild_id}/wiki/curation/{action_id}/reject
  - Approve/reject proposed changes

POST /guilds/{guild_id}/wiki/curation/{action_id}/rollback
  - Undo applied curation action
```

### 8. UI Integration

- "Curation" tab in wiki showing:
  - Pending actions queue with approve/reject
  - Recent curation activity log
  - Quality metrics dashboard
  - "Run Curation" button with skill selection
- Page-level indicators:
  - Quality score badge
  - "Merge suggestion" alerts
  - Contradiction warnings

## Consequences

### Positive
- Automated wiki quality maintenance at scale
- Reduced duplicate and low-quality content
- Better cross-linking and discoverability
- Consistent synthesis quality
- Audit trail for all changes

### Negative
- Additional LLM costs for curation analysis
- Potential for incorrect auto-merges (mitigated by approval workflow)
- Complexity in rollback for multi-page operations

## Implementation Phases

### Phase 1: Foundation
- Curation queue and logging tables
- Quality assessor skill
- Basic API endpoints
- UI for viewing suggestions

### Phase 2: Core Skills
- Topic merger with semantic similarity
- Cross-linker
- Content pruner

### Phase 3: Advanced
- Contradiction resolver
- Gap detector
- Scheduled curation jobs
- Auto-apply with confidence thresholds

## References
- ADR-056: Compounding Wiki Architecture
- ADR-063: Wiki Synthesis
- ADR-076: Continuous Wiki Synthesis
