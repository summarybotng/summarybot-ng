# ADR-033: Custom Perspectives

## Status
Proposed

## Context

The current perspective system has limitations:

1. **Static perspectives**: Perspectives are hardcoded markdown files in `src/prompts/defaults/{perspective}/{length}.md`
2. **Limited options**: Only five built-in perspectives (general, developer, marketing, executive, support)
3. **No customization**: Users cannot modify prompts to better fit their domain or needs
4. **No guild-level control**: All guilds share the same perspective definitions

Users need:
- Ability to create domain-specific perspectives (e.g., "Legal Review", "HR Summary", "Sales Pipeline")
- Ability to clone and modify built-in perspectives as a starting point
- Guild-level ownership of custom perspectives
- Testing/preview before using in production summaries

## Decision

### 1. Custom Perspective Model

#### 1.1 Data Model

```python
class CustomPerspective(BaseModel):
    """User-created or cloned perspective for a guild."""
    id: str                             # e.g., "cust_abc123"
    guild_id: str
    name: str                           # Display name, e.g., "Legal Review"
    slug: str                           # URL-safe identifier, e.g., "legal-review"
    description: str                    # Explains when to use this perspective
    based_on: Optional[str] = None      # Parent perspective if cloned
    prompts: Dict[str, str]             # {"brief": "...", "detailed": "...", "comprehensive": "..."}
    created_at: datetime
    created_by: str                     # User ID who created
    updated_at: datetime
    is_active: bool = True              # Soft delete support
    current_version: int = 1            # Active version number
    version_count: int = 1              # Total versions created


class CustomPerspectiveCreate(BaseModel):
    """Request to create a new custom perspective."""
    name: str
    slug: Optional[str] = None          # Auto-generated from name if not provided
    description: str
    prompts: Dict[str, str]             # At least one length required


class CustomPerspectiveClone(BaseModel):
    """Request to clone a built-in perspective."""
    source_perspective: str             # e.g., "developer"
    name: str                           # New display name
    slug: Optional[str] = None          # Auto-generated if not provided
    description: Optional[str] = None   # Defaults to source description


class CustomPerspectiveUpdate(BaseModel):
    """Request to update a custom perspective."""
    name: Optional[str] = None
    description: Optional[str] = None
    prompts: Optional[Dict[str, str]] = None
    is_active: Optional[bool] = None
    change_summary: Optional[str] = None  # Optional edit message for version history
```

#### 1.2 Database Schema

```sql
CREATE TABLE custom_perspectives (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    description TEXT,
    based_on TEXT,                      -- NULL for from-scratch, perspective name if cloned
    prompts TEXT NOT NULL,              -- JSON: {"brief": "...", "detailed": "...", "comprehensive": "..."}
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    current_version INTEGER DEFAULT 1,  -- Active version number
    version_count INTEGER DEFAULT 1,    -- Total versions created
    UNIQUE(guild_id, slug)
);

CREATE INDEX idx_custom_perspectives_guild ON custom_perspectives(guild_id);
CREATE INDEX idx_custom_perspectives_active ON custom_perspectives(guild_id, is_active);
```

### 2. API Endpoints

#### 2.1 List Perspectives

```python
@router.get("/guilds/{guild_id}/perspectives")
async def list_perspectives(
    guild_id: str,
    include_builtin: bool = True,
    include_inactive: bool = False,
    user: dict = Depends(get_current_user)
) -> PerspectiveListResponse:
    """List all available perspectives for a guild.

    Returns built-in perspectives plus guild-specific custom ones,
    grouped by category.
    """
    pass


class PerspectiveListResponse(BaseModel):
    builtin: List[PerspectiveSummary]   # Standard perspectives
    custom: List[PerspectiveSummary]    # Guild-specific perspectives


class PerspectiveSummary(BaseModel):
    id: str                             # "developer" for builtin, "cust_abc123" for custom
    name: str
    description: str
    is_builtin: bool
    is_active: bool
    available_lengths: List[str]        # ["brief", "detailed", "comprehensive"]
```

#### 2.2 Clone Built-in Perspective

```python
@router.post("/guilds/{guild_id}/perspectives/clone")
async def clone_perspective(
    guild_id: str,
    request: CustomPerspectiveClone,
    user: dict = Depends(get_current_user)
) -> CustomPerspective:
    """Clone a built-in perspective for customization.

    Creates a copy of all prompt templates from the source perspective
    that can then be modified.
    """
    pass
```

#### 2.3 Create Custom Perspective

```python
@router.post("/guilds/{guild_id}/perspectives")
async def create_perspective(
    guild_id: str,
    request: CustomPerspectiveCreate,
    user: dict = Depends(get_current_user)
) -> CustomPerspective:
    """Create a new custom perspective from scratch.

    At minimum, one prompt length must be provided.
    Missing lengths will fall back to the 'general' built-in.
    """
    pass
```

#### 2.4 Update Custom Perspective

```python
@router.put("/guilds/{guild_id}/perspectives/{perspective_id}")
async def update_perspective(
    guild_id: str,
    perspective_id: str,
    request: CustomPerspectiveUpdate,
    user: dict = Depends(get_current_user)
) -> CustomPerspective:
    """Update a custom perspective.

    Cannot modify built-in perspectives.
    """
    pass
```

#### 2.5 Delete Custom Perspective

```python
@router.delete("/guilds/{guild_id}/perspectives/{perspective_id}")
async def delete_perspective(
    guild_id: str,
    perspective_id: str,
    user: dict = Depends(get_current_user)
) -> None:
    """Delete (soft-delete) a custom perspective.

    Cannot delete built-in perspectives.
    Existing summaries using this perspective are unaffected.
    """
    pass
```

#### 2.6 Preview/Test Perspective

```python
@router.post("/guilds/{guild_id}/perspectives/{perspective_id}/preview")
async def preview_perspective(
    guild_id: str,
    perspective_id: str,
    request: PerspectivePreviewRequest,
    user: dict = Depends(get_current_user)
) -> PerspectivePreviewResponse:
    """Test a perspective with sample content.

    Generates a summary using the perspective against provided
    sample messages, allowing users to evaluate prompt quality.
    """
    pass


class PerspectivePreviewRequest(BaseModel):
    sample_messages: Optional[List[str]] = None   # Custom test content
    use_recent_channel: Optional[str] = None      # Use recent messages from channel
    length: str = "brief"


class PerspectivePreviewResponse(BaseModel):
    prompt_used: str                    # The actual prompt sent
    summary: str                        # Generated summary
    token_count: int
    generation_time_ms: int
```

### 3. Integration Points

#### 3.1 Prompt Resolver

The prompt resolver checks custom perspectives before falling back to built-in:

```python
class PromptResolver:
    """Resolves perspective + length to actual prompt text."""

    async def get_prompt(
        self,
        guild_id: str,
        perspective: str,
        length: str
    ) -> str:
        # Check if perspective is a custom ID (starts with "cust_")
        if perspective.startswith("cust_"):
            custom = await self.custom_repo.get(guild_id, perspective)
            if custom and custom.is_active:
                if length in custom.prompts:
                    return custom.prompts[length]
                # Fall back to general for missing lengths
                return self.default_provider.get("general", length)
            raise PerspectiveNotFoundError(perspective)

        # Check guild-specific custom by slug
        custom = await self.custom_repo.get_by_slug(guild_id, perspective)
        if custom and custom.is_active:
            if length in custom.prompts:
                return custom.prompts[length]
            return self.default_provider.get("general", length)

        # Fall back to built-in
        return self.default_provider.get(perspective, length)
```

#### 3.2 Summary Options

Summary generation accepts custom perspective identifiers:

```python
class SummaryOptions(BaseModel):
    perspective: str = "general"        # Can be builtin name or custom ID/slug
    length: str = "brief"
    # ... other options
```

#### 3.3 Scheduled Tasks

Scheduled summary tasks can specify custom perspectives:

```python
class ScheduledSummaryConfig(BaseModel):
    channel_id: str
    schedule: str                       # Cron expression
    perspective: str = "general"        # Supports custom perspective IDs
    length: str = "brief"
    # ... other config
```

### 4. Frontend Components

#### 4.1 Perspective Selector

```typescript
interface PerspectiveSelectorProps {
  guildId: string;
  value: string;
  onChange: (perspectiveId: string) => void;
}

function PerspectiveSelector({ guildId, value, onChange }: PerspectiveSelectorProps) {
  const { data: perspectives } = usePerspectives(guildId);

  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger>
        <SelectValue placeholder="Select perspective" />
      </SelectTrigger>
      <SelectContent>
        <SelectGroup>
          <SelectLabel>Built-in</SelectLabel>
          {perspectives?.builtin.map(p => (
            <SelectItem key={p.id} value={p.id}>
              {p.name}
            </SelectItem>
          ))}
        </SelectGroup>
        {perspectives?.custom.length > 0 && (
          <SelectGroup>
            <SelectLabel>Custom</SelectLabel>
            {perspectives?.custom.map(p => (
              <SelectItem key={p.id} value={p.id}>
                {p.name}
              </SelectItem>
            ))}
          </SelectGroup>
        )}
      </SelectContent>
    </Select>
  );
}
```

#### 4.2 Perspective Editor

```typescript
function PerspectiveEditor({
  guildId,
  perspectiveId,
  onSave,
  onCancel
}: PerspectiveEditorProps) {
  const { data: perspective } = usePerspective(guildId, perspectiveId);
  const [prompts, setPrompts] = useState<Record<string, string>>({});
  const [activeTab, setActiveTab] = useState<string>('brief');

  return (
    <div className="perspective-editor">
      <div className="editor-header">
        <Input
          label="Name"
          value={perspective?.name ?? ''}
          onChange={handleNameChange}
        />
        <Textarea
          label="Description"
          value={perspective?.description ?? ''}
          onChange={handleDescriptionChange}
          placeholder="Describe when to use this perspective"
        />
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="brief">Brief</TabsTrigger>
          <TabsTrigger value="detailed">Detailed</TabsTrigger>
          <TabsTrigger value="comprehensive">Comprehensive</TabsTrigger>
        </TabsList>

        {['brief', 'detailed', 'comprehensive'].map(length => (
          <TabsContent key={length} value={length}>
            <div className="prompt-editor">
              <Label>Prompt Template</Label>
              <Textarea
                value={prompts[length] ?? ''}
                onChange={(e) => setPrompts(p => ({ ...p, [length]: e.target.value }))}
                rows={12}
                placeholder="Enter the system prompt for this perspective and length..."
                className="font-mono"
              />
              <p className="text-sm text-muted-foreground">
                Available variables: {'{messages}'}, {'{channel_name}'}, {'{date_range}'}
              </p>
            </div>
          </TabsContent>
        ))}
      </Tabs>

      <div className="editor-footer">
        <Button variant="outline" onClick={onCancel}>Cancel</Button>
        <Button variant="secondary" onClick={handlePreview}>
          Preview
        </Button>
        <Button onClick={handleSave}>Save</Button>
      </div>
    </div>
  );
}
```

#### 4.3 Clone Dialog

```typescript
function ClonePerspectiveDialog({
  guildId,
  sourcePerspective,
  onSuccess,
  onClose
}: ClonePerspectiveDialogProps) {
  const [name, setName] = useState(`${sourcePerspective.name} (Copy)`);
  const [description, setDescription] = useState(sourcePerspective.description);

  const handleClone = async () => {
    const cloned = await clonePerspective(guildId, {
      source_perspective: sourcePerspective.id,
      name,
      description,
    });
    onSuccess(cloned);
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogHeader>
        <DialogTitle>Clone Perspective</DialogTitle>
        <DialogDescription>
          Create a customizable copy of "{sourcePerspective.name}"
        </DialogDescription>
      </DialogHeader>

      <DialogContent>
        <Input
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <Textarea
          label="Description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </DialogContent>

      <DialogFooter>
        <Button variant="outline" onClick={onClose}>Cancel</Button>
        <Button onClick={handleClone}>Clone & Edit</Button>
      </DialogFooter>
    </Dialog>
  );
}
```

### 5. Prompt Template Format

Custom prompts support the same template variables as built-in prompts:

```markdown
# Example Custom Perspective: Legal Review

You are a legal review assistant analyzing team communications.

Focus on:
- Contractual commitments or obligations mentioned
- Compliance concerns or regulatory references
- Risk factors discussed
- Legal terminology or concepts
- Action items with legal implications

Messages to analyze:
{messages}

Channel: {channel_name}
Date range: {date_range}

Provide a summary highlighting legal considerations and potential risks.
Format action items with responsible parties and deadlines when mentioned.
```

### 6. Validation Rules

1. **Slug uniqueness**: Slugs must be unique within a guild
2. **Reserved slugs**: Cannot use built-in perspective names as slugs
3. **Prompt length**: Prompts must be between 50 and 10,000 characters
4. **At least one prompt**: Custom perspectives must define at least one length
5. **Name length**: Name must be 2-100 characters
6. **Description length**: Description must be 10-500 characters

### 7. Version History

#### 7.1 Version Tracking Model

Each edit to a custom perspective creates a new version:

```python
class PerspectiveVersion(BaseModel):
    """Immutable snapshot of a perspective at a point in time."""
    id: str                             # e.g., "ver_xyz789"
    perspective_id: str                 # Parent perspective
    version_number: int                 # Auto-incrementing per perspective
    name: str
    description: str
    prompts: Dict[str, str]
    created_at: datetime
    created_by: str                     # User who made this edit
    change_summary: Optional[str]       # Optional edit message


class CustomPerspective(BaseModel):
    # ... existing fields ...
    current_version: int                # Points to active version
    version_count: int                  # Total versions created
```

#### 7.2 Version History Schema

```sql
CREATE TABLE perspective_versions (
    id TEXT PRIMARY KEY,
    perspective_id TEXT NOT NULL,
    version_number INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    prompts TEXT NOT NULL,              -- JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT NOT NULL,
    change_summary TEXT,
    FOREIGN KEY (perspective_id) REFERENCES custom_perspectives(id) ON DELETE CASCADE,
    UNIQUE(perspective_id, version_number)
);

CREATE INDEX idx_perspective_versions_parent ON perspective_versions(perspective_id);
```

#### 7.3 Version API Endpoints

```python
@router.get("/guilds/{guild_id}/perspectives/{perspective_id}/versions")
async def list_versions(
    guild_id: str,
    perspective_id: str,
    limit: int = 20,
    offset: int = 0,
    user: dict = Depends(get_current_user)
) -> PerspectiveVersionListResponse:
    """List version history for a perspective."""
    pass


@router.get("/guilds/{guild_id}/perspectives/{perspective_id}/versions/{version_number}")
async def get_version(
    guild_id: str,
    perspective_id: str,
    version_number: int,
    user: dict = Depends(get_current_user)
) -> PerspectiveVersion:
    """Get a specific historical version."""
    pass


@router.post("/guilds/{guild_id}/perspectives/{perspective_id}/versions/{version_number}/restore")
async def restore_version(
    guild_id: str,
    perspective_id: str,
    version_number: int,
    user: dict = Depends(get_current_user)
) -> CustomPerspective:
    """Restore a previous version as the current version.

    Creates a new version with the restored content (does not
    delete intermediate versions).
    """
    pass


@router.get("/guilds/{guild_id}/perspectives/{perspective_id}/versions/compare")
async def compare_versions(
    guild_id: str,
    perspective_id: str,
    from_version: int,
    to_version: int,
    user: dict = Depends(get_current_user)
) -> VersionComparisonResponse:
    """Compare two versions showing diffs."""
    pass


class VersionComparisonResponse(BaseModel):
    from_version: PerspectiveVersion
    to_version: PerspectiveVersion
    changes: Dict[str, FieldDiff]       # {"name": {...}, "prompts.brief": {...}}


class FieldDiff(BaseModel):
    field: str
    old_value: Optional[str]
    new_value: Optional[str]
    change_type: str                    # "added", "removed", "modified"
```

#### 7.4 Summary Linkage

Summaries record which perspective version was used:

```python
class StoredSummary(BaseModel):
    # ... existing fields ...
    perspective_id: Optional[str]       # Custom perspective ID if used
    perspective_version: Optional[int]  # Version number at generation time
```

This enables:
- Understanding why summaries differ after prompt changes
- Reproducing historical summaries with the same prompt
- Auditing prompt evolution over time

#### 7.5 Version Retention Policy

```python
class VersionRetentionPolicy(BaseModel):
    """Guild-level settings for version history."""
    max_versions_per_perspective: int = 50      # Keep last N versions
    min_retention_days: int = 90                # Always keep versions < N days old
    auto_cleanup_enabled: bool = True


async def cleanup_old_versions(guild_id: str, policy: VersionRetentionPolicy):
    """Remove old versions per retention policy.

    Never deletes versions that are:
    - Referenced by existing summaries
    - Within min_retention_days
    - The current active version
    """
    pass
```

#### 7.6 Frontend Version History UI

```typescript
function PerspectiveVersionHistory({
  guildId,
  perspectiveId
}: VersionHistoryProps) {
  const { data: versions } = usePerspectiveVersions(guildId, perspectiveId);
  const [comparing, setComparing] = useState<[number, number] | null>(null);

  return (
    <div className="version-history">
      <h3>Version History</h3>

      <div className="version-list">
        {versions?.map((version, idx) => (
          <div key={version.id} className="version-item">
            <div className="version-header">
              <span className="version-number">v{version.version_number}</span>
              <span className="version-date">
                {formatRelative(version.created_at)}
              </span>
              <span className="version-author">{version.created_by}</span>
            </div>

            {version.change_summary && (
              <p className="change-summary">{version.change_summary}</p>
            )}

            <div className="version-actions">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setComparing([version.version_number, versions[0].version_number])}
              >
                Compare to Current
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleRestore(version.version_number)}
              >
                Restore
              </Button>
            </div>
          </div>
        ))}
      </div>

      {comparing && (
        <VersionCompareModal
          guildId={guildId}
          perspectiveId={perspectiveId}
          fromVersion={comparing[0]}
          toVersion={comparing[1]}
          onClose={() => setComparing(null)}
        />
      )}
    </div>
  );
}
```

## Implementation Plan

### Phase 1: Data Layer
1. Create `custom_perspectives` table
2. Create `perspective_versions` table
3. Implement `CustomPerspectiveRepository`
4. Implement `PerspectiveVersionRepository`
5. Add migrations for schema

### Phase 2: API Endpoints
1. Implement CRUD endpoints
2. Add clone endpoint
3. Implement preview/test endpoint
4. Add perspective listing (builtin + custom)
5. Implement version history endpoints
6. Add version compare/restore endpoints

### Phase 3: Prompt Integration
1. Create `PromptResolver` service
2. Update summary generation to use resolver
3. Record perspective version in stored summaries
4. Update scheduled tasks to support custom perspectives

### Phase 4: Frontend
1. Build perspective selector component
2. Create perspective editor UI
3. Add clone dialog
4. Integrate preview functionality
5. Add perspectives section to guild settings
6. Build version history panel
7. Add version comparison modal

## Security Considerations

1. **Guild isolation**: Custom perspectives are strictly scoped to their guild
2. **Prompt injection**: Prompts are used as system prompts, not user input
3. **Ownership verification**: Only guild admins can create/edit perspectives
4. **Rate limiting**: Limit preview requests to prevent abuse
5. **Content validation**: Validate prompt content for reasonable length/format
6. **Version access**: Version history inherits parent perspective permissions
7. **Retention policy**: Prevents unbounded version growth while preserving audit trail

## Consequences

### Positive
- Users can create domain-specific summarization approaches
- Clone workflow lowers barrier to customization
- Guild-level control over available perspectives
- Preview functionality enables iteration before production use
- Version history enables safe experimentation and rollback
- Summary-to-version linkage provides audit trail for prompt evolution

### Negative
- Additional database storage per guild (perspectives + versions)
- More complex prompt resolution logic
- Need to handle orphaned perspectives in summaries
- Custom prompts may produce inconsistent results if poorly written
- Version storage grows with each edit (mitigated by retention policy)

## Related ADRs

- ADR-008: Unified Summary Experience (perspective selection)
- ADR-010: Prompt Repository Navigation (default prompts)
- ADR-032: Email Content Templates (field selection patterns)
