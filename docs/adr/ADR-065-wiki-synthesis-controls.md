# ADR-065: Wiki Synthesis Rating & Regeneration Controls

## Status
Proposed

## Context

Currently, wiki page synthesis:
- Cannot be rated by users
- Uses fixed parameters for regeneration
- Doesn't let users control model or temperature
- Provides no feedback mechanism for quality

Users need the ability to:
1. Rate synthesis quality (for feedback and filtering)
2. Control regeneration parameters (like they can for summaries)
3. See which model generated the current synthesis
4. Request regeneration with different settings

## Decision

Add rating and regeneration controls to wiki synthesis, mirroring the summary generation UX.

---

## Rating System

### User Rating Flow

```
┌─────────────────────────────────────────────────────────────┐
│  Synthesis                                           ⭐⭐⭐⭐☆ │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  # Authentication                                           │
│                                                             │
│  Our system uses JWT tokens with 15-minute expiry...        │
│                                                             │
│  ## Key Points                                              │
│  - Access tokens: 15 minute expiry                          │
│  - Refresh tokens: 7 day expiry                             │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Rate this synthesis:  ☆ ☆ ☆ ☆ ☆                      │  │
│  │                                                       │  │
│  │ What could be improved? (optional)                    │  │
│  │ ┌─────────────────────────────────────────────────┐  │  │
│  │ │ Missing context about refresh token rotation... │  │  │
│  │ └─────────────────────────────────────────────────┘  │  │
│  │                                    [Submit Rating]    │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  Synthesized by claude-3-haiku • 2 hours ago • 3 sources   │
└─────────────────────────────────────────────────────────────┘
```

### Rating Data Model

```sql
-- ADR-065: Synthesis ratings
CREATE TABLE IF NOT EXISTS wiki_synthesis_ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    page_path TEXT NOT NULL,
    user_id TEXT NOT NULL,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    feedback TEXT,
    synthesis_model TEXT,
    synthesis_version INTEGER,  -- Track which synthesis version was rated
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (guild_id, page_path, user_id)  -- One rating per user per page
);

-- Update wiki_pages to track aggregate rating
ALTER TABLE wiki_pages ADD COLUMN rating_sum INTEGER DEFAULT 0;
ALTER TABLE wiki_pages ADD COLUMN rating_count INTEGER DEFAULT 0;
-- rating = rating_sum / rating_count (computed)
```

---

## Regeneration Controls

### Regeneration Dialog

```tsx
function SynthesisRegenerateDialog({ page, onRegenerate }: Props) {
  const [model, setModel] = useState("auto");
  const [temperature, setTemperature] = useState(0.3);
  const [maxTokens, setMaxTokens] = useState(2000);
  const [focusAreas, setFocusAreas] = useState<string[]>([]);

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <RefreshCw className="h-4 w-4 mr-1" />
          Regenerate
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Regenerate Synthesis</DialogTitle>
          <DialogDescription>
            Customize how the synthesis is generated
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Model Selection */}
          <div>
            <Label>Model</Label>
            <Select value={model} onValueChange={setModel}>
              <SelectItem value="auto">Auto (Recommended)</SelectItem>
              <SelectItem value="haiku">Haiku (Fast, economical)</SelectItem>
              <SelectItem value="sonnet">Sonnet (Balanced)</SelectItem>
              <SelectItem value="opus">Opus (Most capable)</SelectItem>
            </Select>
            <p className="text-xs text-muted-foreground mt-1">
              Auto selects based on page complexity
            </p>
          </div>

          {/* Temperature */}
          <div>
            <Label>Creativity</Label>
            <Slider
              min={0}
              max={1}
              step={0.1}
              value={[temperature]}
              onValueChange={([v]) => setTemperature(v)}
            />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>Precise (0.0)</span>
              <span>{temperature}</span>
              <span>Creative (1.0)</span>
            </div>
          </div>

          {/* Max Length */}
          <div>
            <Label>Maximum Length</Label>
            <Select value={String(maxTokens)} onValueChange={(v) => setMaxTokens(Number(v))}>
              <SelectItem value="1000">Short (~500 words)</SelectItem>
              <SelectItem value="2000">Medium (~1000 words)</SelectItem>
              <SelectItem value="4000">Long (~2000 words)</SelectItem>
            </Select>
          </div>

          {/* Focus Areas */}
          <div>
            <Label>Focus Areas (optional)</Label>
            <div className="flex flex-wrap gap-2 mt-2">
              {["Key decisions", "Technical details", "Action items", "Conflicts"].map(area => (
                <Badge
                  key={area}
                  variant={focusAreas.includes(area) ? "default" : "outline"}
                  className="cursor-pointer"
                  onClick={() => toggleFocusArea(area)}
                >
                  {area}
                </Badge>
              ))}
            </div>
          </div>

          {/* Custom Instructions */}
          <div>
            <Label>Custom Instructions (optional)</Label>
            <Textarea
              placeholder="E.g., 'Focus on security implications' or 'Include more code examples'"
              className="mt-1"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={handleRegenerate}>
            <Sparkles className="h-4 w-4 mr-1" />
            Regenerate
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

---

## API Changes

### Rate Synthesis Endpoint

```
POST /guilds/{guild_id}/wiki/pages/{path}/rate
```

**Request:**
```json
{
  "rating": 4,
  "feedback": "Good overview but missing refresh token rotation details"
}
```

**Response:**
```json
{
  "success": true,
  "average_rating": 4.2,
  "rating_count": 5
}
```

### Regenerate Synthesis Endpoint (Updated)

```
POST /guilds/{guild_id}/wiki/pages/{path}/synthesize
```

**Request (Updated):**
```json
{
  "model": "sonnet",
  "temperature": 0.3,
  "max_tokens": 2000,
  "focus_areas": ["technical details", "conflicts"],
  "custom_instructions": "Focus on security implications"
}
```

**Response (Updated):**
```json
{
  "success": true,
  "synthesis_length": 1250,
  "source_count": 5,
  "conflicts_found": 1,
  "model_used": "claude-3-5-sonnet-20241022",
  "input_tokens": 3200,
  "output_tokens": 890
}
```

---

## Synthesis Metadata Display

### Footer Information

```tsx
function SynthesisFooter({ page }: { page: WikiPage }) {
  return (
    <div className="flex items-center justify-between text-sm text-muted-foreground border-t pt-4 mt-4">
      <div className="flex items-center gap-4">
        {/* Model */}
        <span className="flex items-center gap-1">
          <Cpu className="h-3 w-3" />
          {page.synthesis_model || "heuristic"}
        </span>

        {/* Timestamp */}
        <span className="flex items-center gap-1">
          <Clock className="h-3 w-3" />
          {formatRelative(page.synthesis_updated_at)}
        </span>

        {/* Sources */}
        <span className="flex items-center gap-1">
          <FileText className="h-3 w-3" />
          {page.synthesis_source_count} sources
        </span>
      </div>

      <div className="flex items-center gap-2">
        {/* Current Rating */}
        {page.rating_count > 0 && (
          <span className="flex items-center gap-1">
            <Star className="h-3 w-3 fill-yellow-400 text-yellow-400" />
            {(page.rating_sum / page.rating_count).toFixed(1)}
            <span className="text-xs">({page.rating_count})</span>
          </span>
        )}

        {/* Rate Button */}
        <RateSynthesisButton page={page} />

        {/* Regenerate */}
        <SynthesisRegenerateDialog page={page} />
      </div>
    </div>
  );
}
```

---

## Synthesis Generation Updates

### Updated Synthesis Function

```python
@dataclass
class SynthesisOptions:
    """Options for synthesis generation."""
    model: str = "auto"  # auto, haiku, sonnet, opus
    temperature: float = 0.3
    max_tokens: int = 2000
    focus_areas: List[str] = field(default_factory=list)
    custom_instructions: Optional[str] = None


async def synthesize_wiki_page(
    page_title: str,
    page_content: str,
    source_refs: List[str],
    claude_client: Optional["ClaudeClient"] = None,
    options: Optional[SynthesisOptions] = None,
) -> SynthesisResult:
    """Generate synthesis with configurable options."""

    options = options or SynthesisOptions()

    # Build custom system prompt based on options
    system_prompt = SYNTHESIS_SYSTEM_PROMPT

    if options.focus_areas:
        system_prompt += f"\n\nFocus especially on: {', '.join(options.focus_areas)}"

    if options.custom_instructions:
        system_prompt += f"\n\nAdditional instructions: {options.custom_instructions}"

    # Select model
    model = _select_model(options.model, len(page_content))

    claude_options = ClaudeOptions(
        model=model,
        max_tokens=options.max_tokens,
        temperature=options.temperature,
    )

    # Generate...
    response = await claude_client.create_summary_with_fallback(...)

    return SynthesisResult(
        synthesis=response.content,
        source_count=len(source_refs),
        conflicts_found=conflicts,
        topics_extracted=topics,
        confidence=confidence,
        model_used=response.model,  # Track actual model
    )


def _select_model(preference: str, content_length: int) -> str:
    """Select model based on preference and content complexity."""
    if preference != "auto":
        return MODEL_MAP.get(preference, DEFAULT_MODEL)

    # Auto-select based on content length
    if content_length < 2000:
        return "claude-3-haiku-20240307"
    elif content_length < 8000:
        return "claude-3-5-sonnet-20241022"
    else:
        return "claude-3-opus-20240229"
```

---

## Implementation Order

```
1. 066_synthesis_ratings.sql - Rating table + columns
2. src/wiki/models.py - Add SynthesisOptions, update SynthesisResult
3. src/wiki/synthesis.py - Add options support
4. src/data/sqlite/wiki_repository.py - Rating CRUD
5. src/dashboard/routes/wiki.py - Rate endpoint, update synthesize
6. src/frontend/src/pages/Wiki.tsx - Rating UI
7. src/frontend/src/pages/Wiki.tsx - Regenerate dialog
8. src/frontend/src/pages/Wiki.tsx - Synthesis footer
```

---

## Consequences

### Positive
- Users can provide feedback on synthesis quality
- Ratings help identify pages needing improvement
- Custom regeneration gives control when needed
- Model transparency builds trust
- Focus areas improve targeted synthesis

### Negative
- Additional API complexity
- More database writes for ratings
- Users may regenerate excessively (cost)

### Mitigations
- Rate limit regeneration (e.g., 3 per hour per page)
- Cache synthesis by options hash
- Default to economical models unless specified
- Aggregate ratings to reduce storage

---

## References

- [ADR-063: Wiki Page Tabs](./ADR-063-wiki-page-tabs.md)
- [ADR-038: Multi-Perspective Summaries](./ADR-038-multi-perspective-summaries.md)
