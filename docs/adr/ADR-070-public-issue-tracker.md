# ADR-070: Public Issue Tracker

## Status
Proposed (2026-04-27)

## Context

SummaryBot NG is becoming a public service. Users need a way to report bugs, request features, and provide feedback about the system. A lightweight issue tracker integrated into the dashboard will improve user experience and help maintainers collect actionable feedback.

### Requirements

1. **Low friction**: Users should be able to report issues quickly
2. **GitHub integration**: Issues should flow to the project's GitHub repo by default
3. **No GitHub required**: Users without GitHub accounts should still be able to submit issues
4. **Privacy-aware**: Email collection only when necessary, stored securely
5. **Admin workflow**: Local issues can be triaged and replicated to GitHub later

---

## Decision

### MVP Issue Tracker

Implement a minimal issue submission system with two paths:

#### Path A: GitHub Direct (Default)
- User clicks "Report Issue" in dashboard
- Opens GitHub issue template with pre-filled context
- User completes and submits via GitHub

#### Path B: Local Collection (No GitHub)
- User indicates they don't have GitHub
- Collects: title, description, issue type (bug/feature/question)
- Optionally collects email for follow-up
- Stores in guild's workspace (SQLite)
- Admin can later replicate to GitHub

### Configuration

```python
# Default issue tracker target
ISSUE_TRACKER_URL = "https://github.com/summarybotng/summarybot-ng/issues"
ISSUE_TRACKER_ENABLED = True
```

### Database Schema

```sql
-- Migration: 049_local_issues.sql
CREATE TABLE IF NOT EXISTS local_issues (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    guild_id TEXT NOT NULL,

    -- Issue content
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    issue_type TEXT NOT NULL CHECK (issue_type IN ('bug', 'feature', 'question')),

    -- Reporter info (optional)
    reporter_email TEXT,
    reporter_discord_id TEXT,

    -- Context (auto-captured)
    page_url TEXT,
    browser_info TEXT,
    app_version TEXT,

    -- Lifecycle
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'triaged', 'replicated', 'closed')),
    github_issue_url TEXT,  -- Set when replicated
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (guild_id) REFERENCES guild_configs(guild_id)
);

CREATE INDEX idx_local_issues_guild ON local_issues(guild_id);
CREATE INDEX idx_local_issues_status ON local_issues(status);
```

### API Endpoints

```
POST /api/v1/issues
  - Submit a local issue
  - Body: { title, description, issue_type, email?, page_url? }
  - Returns: { id, github_url? }

GET /api/v1/issues
  - List local issues (admin only)
  - Query: ?status=open&guild_id=xxx

GET /api/v1/issues/{id}
  - Get issue details (admin only)

POST /api/v1/issues/{id}/replicate
  - Replicate to GitHub (admin only)
  - Returns: { github_issue_url }

PATCH /api/v1/issues/{id}
  - Update issue status (admin only)
```

### Frontend Components

#### ReportIssueButton
Floating action button or menu item in dashboard header.

```tsx
function ReportIssueButton() {
  const [showDialog, setShowDialog] = useState(false);

  return (
    <>
      <Button variant="ghost" size="sm" onClick={() => setShowDialog(true)}>
        <Bug className="h-4 w-4 mr-1" />
        Report Issue
      </Button>
      <ReportIssueDialog open={showDialog} onClose={() => setShowDialog(false)} />
    </>
  );
}
```

#### ReportIssueDialog
Two-step flow:

1. **Step 1: Choose method**
   - "Report on GitHub" (opens new tab with pre-filled template)
   - "I don't have GitHub" (proceeds to local form)

2. **Step 2: Local form** (if no GitHub)
   - Issue type: Bug / Feature / Question
   - Title (required)
   - Description (required, markdown supported)
   - Email (optional): "Enter your email if you'd like updates"
   - Submit

#### GitHub Issue Template URL

```typescript
function buildGitHubIssueUrl(context: IssueContext): string {
  const params = new URLSearchParams({
    template: context.type === 'bug' ? 'bug_report.md' : 'feature_request.md',
    title: context.title || '',
    body: `
**Page:** ${context.pageUrl || 'N/A'}
**App Version:** ${context.appVersion || 'unknown'}
**Browser:** ${context.browser || 'unknown'}

---

${context.description || ''}
    `.trim(),
  });

  return `${ISSUE_TRACKER_URL}/new?${params}`;
}
```

### Admin Panel (Phase 2)

Add an "Issues" tab to the admin section:

- List local issues with filters (status, type, date)
- View issue details
- Replicate to GitHub with one click
- Mark as closed/triaged

---

## Implementation

### Phase 1: MVP (This PR)

1. **Database**: Add `local_issues` table
2. **API**: `POST /issues` endpoint for submission
3. **Frontend**: ReportIssueButton + ReportIssueDialog
4. **GitHub link**: Pre-filled issue URL generation

### Phase 2: Admin Workflow

1. **API**: GET/PATCH endpoints for issue management
2. **API**: POST replicate endpoint (uses GitHub API)
3. **Frontend**: Admin issues list and detail views

### Phase 3: Enhanced Context

1. Auto-capture error context when reporting from error states
2. Screenshot attachment support
3. Issue templates per type

---

## File Structure

```
src/
  dashboard/
    routes/
      issues.py          # Issue API endpoints
  data/
    migrations/
      049_local_issues.sql
    sqlite/
      issue_repository.py
  frontend/src/
    components/
      issues/
        ReportIssueButton.tsx
        ReportIssueDialog.tsx
        IssueList.tsx      # Phase 2
```

---

## Consequences

### Positive

- Users can report issues without leaving the app
- No GitHub account required for basic feedback
- Maintainers get structured, contextual bug reports
- Local storage enables offline-first issue collection

### Negative

- Two-path system adds complexity
- Local issues require admin attention to replicate
- Email storage requires privacy policy update

### Mitigations

- Clear UX directing most users to GitHub path
- Admin dashboard makes triage efficient
- Minimal email collection, clear opt-in language

---

## Security Considerations

1. **Rate limiting**: Prevent spam submissions
2. **Input sanitization**: Markdown content sanitized before display
3. **Email privacy**: Stored encrypted, visible only to admins
4. **CSRF protection**: Issue submission requires valid session

---

## References

- GitHub Issue Templates: https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests
- Project Issues: https://github.com/summarybotng/summarybot-ng/issues
