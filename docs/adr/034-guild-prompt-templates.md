# ADR-034: Guild Prompt Templates

**Status:** Proposed
**Date:** 2026-04-03
**Depends on:** ADR-010 (Prompt Repository Navigation)

---

## 1. Context

Currently, prompt customization is available through:
- **System defaults** — Built-in prompts by category (discussion, meeting) and perspective/length (developer/detailed)
- **GitHub repos** — Guilds can point to a GitHub repository with custom prompts (ADR-010)

However, the GitHub approach has limitations:
1. **Technical barrier** — Requires Git knowledge and repository setup
2. **No reuse visibility** — Users can't easily see which prompts are used by which schedules
3. **No in-dashboard editing** — Changes require commits to external repo

Users want to:
1. Create custom prompts without leaving the dashboard
2. Reuse the same prompt across multiple schedules
3. Start from system defaults and customize
4. See which schedules use which prompts

---

## 2. Decision

Implement a guild-level prompt template library stored in the database, accessible via dashboard UI.

### 2.1 Prompt Resolution Priority

```
1. Schedule's linked template (guild library)     ← NEW
2. Guild's GitHub repo prompts (existing)
3. System defaults
```

### 2.2 Data Model

```python
# src/models/prompt_template.py

@dataclass
class GuildPromptTemplate(BaseModel):
    """A reusable prompt template owned by a guild."""
    id: str = field(default_factory=generate_id)
    guild_id: str = ""
    name: str = ""                              # "Developer Standup", "Executive Weekly"
    description: Optional[str] = None           # Help text for users
    content: str = ""                           # The actual prompt text
    based_on_default: Optional[str] = None      # "developer/detailed" if seeded from default
    created_by: str = ""
    created_at: datetime = field(default_factory=utc_now_naive)
    updated_at: datetime = field(default_factory=utc_now_naive)
```

### 2.3 Database Schema

```sql
-- src/data/migrations/019_guild_prompt_templates.sql

CREATE TABLE IF NOT EXISTS guild_prompt_templates (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    content TEXT NOT NULL,
    based_on_default TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(guild_id, name)
);

CREATE INDEX idx_prompt_templates_guild ON guild_prompt_templates(guild_id);

-- Link schedules to templates
ALTER TABLE scheduled_tasks ADD COLUMN prompt_template_id TEXT
    REFERENCES guild_prompt_templates(id) ON DELETE SET NULL;
```

### 2.4 API Endpoints

```
GET    /api/v1/guilds/{guild_id}/prompt-templates          List templates
POST   /api/v1/guilds/{guild_id}/prompt-templates          Create template
GET    /api/v1/guilds/{guild_id}/prompt-templates/{id}     Get template
PATCH  /api/v1/guilds/{guild_id}/prompt-templates/{id}     Update template
DELETE /api/v1/guilds/{guild_id}/prompt-templates/{id}     Delete template
POST   /api/v1/guilds/{guild_id}/prompt-templates/{id}/duplicate   Duplicate
GET    /api/v1/guilds/{guild_id}/prompt-templates/{id}/usage       Get linked schedules
```

### 2.5 Template Features

1. **Create from default** — Seed new template from system default (e.g., "developer/detailed")
2. **Duplicate** — Copy existing template with new name
3. **Usage tracking** — Show which schedules use each template
4. **Delete protection** — Show linked schedules before allowing deletion
5. **"Based on" indicator** — Display which default the template originated from

### 2.6 Schedule Integration

Update schedule form to include template selector:

```typescript
// Schedule form dropdown options:
// - "Use default prompt"
// - "Developer Standup" (3 schedules)
// - "Executive Weekly" (1 schedule)
// - "Support Digest" (2 schedules)
// - [Manage Templates →]
```

### 2.7 Execution Pipeline

```python
# src/summarization/engine.py - Updated prompt resolution

async def _resolve_prompt(self, guild_id: str, template_id: Optional[str], context: PromptContext) -> str:
    # Priority 1: Schedule's linked template
    if template_id:
        template = await self.template_repo.get_template(template_id)
        if template:
            return template.content

    # Priority 2: Guild's GitHub repo (existing)
    if self.prompt_resolver:
        resolved = await self.prompt_resolver.resolve_prompt(guild_id, context)
        if resolved.source != PromptSource.DEFAULT:
            return resolved.content

    # Priority 3: System defaults (via prompt_builder)
    return None  # Let prompt_builder use defaults
```

---

## 3. Implementation Plan

### Phase 1: Backend Foundation
1. Create migration `019_guild_prompt_templates.sql`
2. Add `GuildPromptTemplate` model
3. Add `PromptTemplateRepository` with CRUD + usage query
4. Update `ScheduledTask` model with `prompt_template_id`
5. Update `TaskRepository` to handle new field

### Phase 2: API Layer
1. Create `/prompt-templates` routes
2. Add request/response models to `dashboard/models.py`
3. Update schedule routes to include template info
4. Register routes in `dashboard/router.py`

### Phase 3: Execution Integration
1. Wire `PromptTemplateRepository` into `SummarizationEngine`
2. Update prompt resolution to check template first
3. Pass `prompt_template_id` through execution pipeline

### Phase 4: Frontend
1. Add TypeScript types for templates
2. Create `usePromptTemplates` hook
3. Create `PromptTemplates` management page
4. Create `PromptTemplateEditor` component
5. Update `ScheduleForm` with template selector
6. Add navigation link in sidebar

---

## 4. Consequences

### Positive
- **Accessible** — Non-technical admins can create prompts in dashboard
- **Reusable** — Same prompt used across multiple schedules
- **Traceable** — Clear visibility of template usage
- **Maintainable** — Update once, all linked schedules benefit
- **Coexists** — GitHub repo system continues to work

### Negative
- **New table** — Additional database complexity
- **UI surface** — New page to maintain
- **Migration** — Existing schedules need no changes (optional feature)

### Neutral
- Templates are guild-scoped (not user-scoped or global)
- No versioning/history (can add later if needed)

---

## 5. Files to Create/Modify

### New Files
| File | Purpose |
|------|---------|
| `src/data/migrations/019_guild_prompt_templates.sql` | Database schema |
| `src/models/prompt_template.py` | Data model |
| `src/data/sqlite/prompt_template_repository.py` | Repository |
| `src/dashboard/routes/prompt_templates.py` | API routes |
| `src/frontend/src/pages/PromptTemplates.tsx` | Management page |
| `src/frontend/src/hooks/usePromptTemplates.ts` | API hook |
| `src/frontend/src/components/prompts/PromptTemplateEditor.tsx` | Editor |

### Modified Files
| File | Changes |
|------|---------|
| `src/models/task.py` | Add `prompt_template_id` |
| `src/models/__init__.py` | Export new model |
| `src/dashboard/models.py` | Add API models |
| `src/data/sqlite/task_repository.py` | Handle template ID |
| `src/dashboard/routes/schedules.py` | Include template in responses |
| `src/summarization/engine.py` | Check template first |
| `src/dashboard/router.py` | Register new routes |
| `src/frontend/src/types/index.ts` | Add TypeScript types |
| `src/frontend/src/components/schedules/ScheduleForm.tsx` | Template selector |
| `src/frontend/src/components/layout/GuildSidebar.tsx` | Nav link |
| `src/frontend/src/App.tsx` | Route for new page |

---

## 6. Verification

### Unit Tests
- Template CRUD operations
- Usage counting query
- Duplicate with name conflict handling
- Delete with usage check

### Integration Tests
- Create template, link to schedule, run schedule
- Update template, verify next run uses new content
- Delete template, verify schedule falls back to default

### Manual Testing
1. Create template from "developer/detailed" default
2. Assign to 2 schedules
3. Run both schedules, verify same prompt used
4. Edit template content
5. Run schedules again, verify updated prompt
6. Try to delete → see usage warning
7. Duplicate template, modify, assign to third schedule
