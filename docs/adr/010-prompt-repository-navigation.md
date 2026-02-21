# ADR-010: Prompt Repository Navigation

## Status

Proposed

## Context

SummaryBot-ng supports custom prompts loaded from GitHub repositories for summary generation. Users can configure per-server prompt repositories in the server setup, allowing teams to customize how summaries are generated.

Currently, there's no easy way for users to:
1. Navigate from server setup to the configured prompt repository
2. Navigate from a specific summary to the prompt configuration that generated it
3. Understand what drove the output they're seeing

This creates confusion when users want to:
- Understand why a summary looks the way it does
- Modify their prompt configuration
- Debug unexpected summary output
- Share their prompt configuration with others

## Decision

Add navigation links to GitHub prompt repositories in two key locations:

### 1. Server Setup (Prompt Configuration Section)

In the guild configuration page, the prompt configuration section will display:
- **Repository URL** (clickable link to GitHub)
- **Branch/Ref** being used
- **Prompt file path** within the repository
- **Last sync status** with timestamp
- **Quick actions**: "View on GitHub", "Edit on GitHub", "Refresh Cache"

### 2. Summary Detail View

Each summary will show its prompt provenance in the metadata section:
- **Prompt source badge**: "Custom", "Default", or "Cached"
- **Repository link** (if custom prompt was used)
- **File path** (clickable to specific file on GitHub)
- **Version/commit** that was used (if available)
- **Staleness indicator** if prompt may have changed since generation

## Implementation

### Phase 1: Backend Prompt Metadata Enhancement

**File: `src/models/summary.py`**
- Extend `SummaryMetadata` to include prompt provenance:
  ```python
  @dataclass
  class PromptSource:
      source: str  # "custom", "cached", "default", "fallback"
      file_path: Optional[str] = None
      tried_paths: List[str] = field(default_factory=list)
      repo_url: Optional[str] = None
      github_file_url: Optional[str] = None  # Direct link to file on GitHub
      version: Optional[str] = None  # Commit SHA or timestamp
      is_stale: bool = False  # True if prompt may have changed since
      # Path resolution details (for parameterized paths)
      path_template: Optional[str] = None  # e.g., "prompts/{perspective}/{type}.md"
      resolved_variables: Dict[str, str] = field(default_factory=dict)  # Variables that drove selection
  ```

Note: The existing `ResolvedPrompt` in `src/prompts/models.py` already tracks `file_path`, `tried_paths`, and `github_file_url`. The `path_template` and `resolved_variables` need to be propagated from the PATH parser through to the summary metadata.

**File: `src/summarization/prompts.py`**
- Update prompt loading to capture and store provenance metadata
- Generate GitHub file URLs from repo URL + path + ref/branch
- Track which paths were tried before finding a prompt

### Phase 2: Server Setup UI Enhancement

**File: `src/frontend/src/pages/GuildSetup.tsx`**
- Add prompt configuration card with:
  - Current prompt repository URL (with "View on GitHub" link)
  - Branch/ref selector
  - Prompt file path display
  - Sync status and last refresh time
  - "Edit on GitHub" button (opens file in GitHub editor)
  - "Refresh Cache" button

**File: `src/dashboard/routes/guilds.py`**
- Add endpoint to get prompt configuration details
- Add endpoint to refresh prompt cache

### Phase 3: Summary Detail View Enhancement

**File: `src/frontend/src/components/summaries/SummaryDetail.tsx`**
- Add prompt provenance section to metadata display:
  - Source badge ("Custom Prompt", "Default Prompt", "Cached")
  - Repository link (if custom)
  - File path with GitHub link
  - Version indicator
  - Staleness warning if applicable

**File: `src/frontend/src/types/index.ts`**
- Extend `PromptSource` interface to include path resolution details:
  ```typescript
  export interface PromptSource {
    source: "custom" | "cached" | "default" | "fallback";
    file_path: string | null;
    tried_paths: string[];
    repo_url: string | null;
    github_file_url: string | null;
    version: string;
    is_stale: boolean;
    // Path resolution details
    path_template: string | null;  // e.g., "prompts/{perspective}/{type}.md"
    resolved_variables: Record<string, string>;  // Variables that drove selection
  }
  ```

## API Changes

### GET /api/v1/guilds/{guild_id}/prompt-config
Returns prompt configuration details:
```json
{
  "repo_url": "https://github.com/org/prompts",
  "branch": "main",
  "file_path": "summarybot/system.md",
  "github_file_url": "https://github.com/org/prompts/blob/main/summarybot/system.md",
  "last_synced": "2026-02-21T12:00:00Z",
  "sync_status": "ok",
  "is_custom": true
}
```

### POST /api/v1/guilds/{guild_id}/prompt-config/refresh
Forces a refresh of cached prompt from GitHub.

### Summary Metadata Extension
Summary responses will include prompt source in metadata:
```json
{
  "metadata": {
    "prompt_source": {
      "source": "custom",
      "repo_url": "https://github.com/org/prompts",
      "github_file_url": "https://github.com/org/prompts/blob/abc123/prompts/developer/detailed.md",
      "file_path": "prompts/developer/detailed.md",
      "path_template": "prompts/{perspective}/{summary_type}.md",
      "resolved_variables": {
        "perspective": "developer",
        "summary_type": "detailed",
        "category": "discussion"
      },
      "tried_paths": [
        "prompts/developer/detailed.md"
      ],
      "version": "abc123",
      "is_stale": false
    }
  }
}
```

The `path_template` and `resolved_variables` fields help users understand **why** a particular prompt file was selected. For example, if a summary looks different than expected, the user can see that `perspective=developer` caused the selection of `prompts/developer/detailed.md` rather than `prompts/general/detailed.md`.

## UI/UX Design

### Server Setup - Prompt Configuration Card

```
┌─────────────────────────────────────────────────────────┐
│ Prompt Configuration                           [Custom] │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Repository:  github.com/myorg/prompts  [View] [Edit]    │
│ Branch:      main                                       │
│ File:        summarybot/system.md                       │
│                                                         │
│ Last synced: 2 hours ago ✓                [Refresh]     │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Summary Detail - Prompt Provenance

```
┌─────────────────────────────────────────────────────────┐
│ How This Summary Was Generated                          │
├─────────────────────────────────────────────────────────┤
│ Model:     Claude 3.5 Sonnet                            │
│ Length:    Detailed                                     │
│ Perspective: Developer                                  │
│                                                         │
│ Prompt:    Custom [View on GitHub ↗]                    │
│            prompts/developer/detailed.md                │
│            Version: abc123 (2 days ago)                 │
│                                                         │
│ Path Resolution:                                        │
│   Template: prompts/{perspective}/{summary_type}.md     │
│   Variables: perspective=developer, summary_type=detailed│
│   Tried: 1 path (matched first)                         │
└─────────────────────────────────────────────────────────┘
```

When multiple paths were tried before finding a match:
```
┌─────────────────────────────────────────────────────────┐
│ Path Resolution:                                        │
│   Template: prompts/{channel}/{type}.md                 │
│   Variables: channel=general, type=brief                │
│   Tried 3 paths:                                        │
│     ✗ prompts/general/brief.md (not found)              │
│     ✗ prompts/default/brief.md (not found)              │
│     ✓ prompts/fallback.md (used)                        │
└─────────────────────────────────────────────────────────┘
```

## Data Model

### GuildPromptConfig (existing, enhanced)
```python
@dataclass
class GuildPromptConfig:
    guild_id: str
    repo_url: Optional[str] = None
    branch: str = "main"
    file_path: str = "summarybot/system.md"
    last_synced: Optional[datetime] = None
    sync_status: str = "pending"  # "ok", "error", "stale"
    cached_content: Optional[str] = None
    version: Optional[str] = None  # Commit SHA
```

## Security Considerations

1. **GitHub URLs**: Only allow HTTPS GitHub URLs
2. **Rate limiting**: Respect GitHub API rate limits for prompt fetching
3. **Caching**: Cache prompts locally to avoid excessive API calls
4. **Validation**: Validate repository URLs before displaying as links

## Consequences

### Positive
- Users can easily understand what prompts generate their summaries
- Direct navigation to edit prompts improves workflow
- Transparency about prompt versioning and staleness
- Better debugging when summaries don't look as expected

### Negative
- Additional metadata storage per summary
- Need to handle cases where repository becomes unavailable
- UI complexity increase in settings and detail views

### Neutral
- GitHub-specific integration (could extend to GitLab later)
- Requires prompt loading code to track provenance

## References

- ADR-004: Grounded Summary References (similar provenance concept)
- ADR-005: Summary Delivery Destinations
- Existing `GuildPromptConfig` model in `src/dashboard/models.py`
