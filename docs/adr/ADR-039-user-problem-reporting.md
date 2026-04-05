# ADR-039: User Problem Reporting System

## Status
Proposed

## Context

Users need a way to report problems with summaries, feeds, and system behavior. Currently:
- No structured way to report issues
- No feedback loop for quality improvement
- Problems may go unnoticed until they become widespread
- Difficult to correlate user reports with system logs

Users should be able to report:
1. **Summary Quality Issues**: Incorrect summaries, missing information, wrong perspective
2. **Generation Failures**: Summaries that should have been generated but weren't
3. **Parameter Mismatches**: Requested parameters not reflected in output (as in ADR-038)
4. **Feed Issues**: Missing items, incorrect filtering, stale content
5. **General Bugs**: UI glitches, unexpected errors, performance problems

## Decision

Implement a comprehensive user problem reporting system with the following components:

### 1. Report Types

```typescript
type ProblemCategory =
  | "summary_quality"      // Summary doesn't match expectations
  | "missing_summary"      // Expected summary wasn't generated
  | "parameter_mismatch"   // Perspective/length not applied correctly
  | "feed_issue"           // Feed content problems
  | "schedule_failure"     // Scheduled task didn't run
  | "ui_bug"               // Dashboard issues
  | "performance"          // Slow or unresponsive
  | "other";               // Catch-all

interface ProblemReport {
  id: string;
  category: ProblemCategory;
  severity: "low" | "medium" | "high" | "critical";

  // Context
  guild_id: string;
  user_id: string;
  resource_type: "summary" | "feed" | "schedule" | "system";
  resource_id?: string;

  // User input
  description: string;
  expected_behavior: string;
  actual_behavior: string;
  steps_to_reproduce?: string;

  // Auto-captured
  timestamp: string;
  browser_info?: string;
  page_url?: string;
  request_id?: string;

  // System correlation
  related_logs?: string[];
  related_errors?: string[];
  system_state?: Record<string, unknown>;

  // Resolution
  status: "open" | "investigating" | "resolved" | "wont_fix";
  resolution_notes?: string;
  resolved_at?: string;
  resolved_by?: string;
}
```

### 2. Report Submission UI

Add a "Report Problem" button accessible from:
- Summary detail view (for summary-specific issues)
- Feed preview sheet (for feed-specific issues)
- Schedule list (for schedule-specific issues)
- Global help menu (for general issues)

```tsx
function ReportProblemDialog({ resourceType, resourceId }: Props) {
  return (
    <Dialog>
      <DialogContent>
        <DialogTitle>Report a Problem</DialogTitle>

        <Select name="category">
          <SelectItem value="summary_quality">Summary Quality Issue</SelectItem>
          <SelectItem value="parameter_mismatch">Wrong Perspective/Length</SelectItem>
          <SelectItem value="feed_issue">Feed Content Problem</SelectItem>
          <SelectItem value="other">Other Issue</SelectItem>
        </Select>

        <Select name="severity">
          <SelectItem value="low">Low - Minor inconvenience</SelectItem>
          <SelectItem value="medium">Medium - Feature not working correctly</SelectItem>
          <SelectItem value="high">High - Major functionality broken</SelectItem>
          <SelectItem value="critical">Critical - Data loss or security</SelectItem>
        </Select>

        <Textarea
          name="description"
          placeholder="Describe the problem..."
        />

        <Textarea
          name="expected"
          placeholder="What did you expect to happen?"
        />

        <Textarea
          name="actual"
          placeholder="What actually happened?"
        />

        {/* Auto-populated context */}
        <input type="hidden" name="resource_type" value={resourceType} />
        <input type="hidden" name="resource_id" value={resourceId} />
        <input type="hidden" name="page_url" value={window.location.href} />

        <Button type="submit">Submit Report</Button>
      </DialogContent>
    </Dialog>
  );
}
```

### 3. Context Capture

Automatically capture relevant context when a report is filed:

```python
class ProblemReportService:
    async def create_report(
        self,
        report: ProblemReportCreate,
        user: User
    ) -> ProblemReport:
        # Auto-enrich with system context
        context = await self._capture_context(report)

        # Find related logs
        if report.resource_type == "summary" and report.resource_id:
            summary = await self.summary_repo.get(report.resource_id)
            context["summary_metadata"] = summary.metadata
            context["generation_logs"] = await self._get_generation_logs(
                summary.created_at,
                summary.guild_id
            )

        # Find related errors
        errors = await self.error_repo.find_recent(
            guild_id=report.guild_id,
            since=datetime.utcnow() - timedelta(hours=1)
        )
        context["related_errors"] = [e.id for e in errors]

        # Check for known issues
        known_issues = await self._check_known_issues(report)
        if known_issues:
            context["known_issues"] = known_issues

        return await self.repo.create(
            **report.dict(),
            user_id=user.id,
            system_state=context
        )
```

### 4. API Endpoints

```python
@router.post("/guilds/{guild_id}/reports", response_model=ProblemReport)
async def create_problem_report(
    guild_id: str,
    body: ProblemReportCreate,
    user: dict = Depends(get_current_user)
):
    """Submit a problem report."""
    return await report_service.create_report(body, user)

@router.get("/guilds/{guild_id}/reports", response_model=ProblemReportList)
async def list_problem_reports(
    guild_id: str,
    status: Optional[str] = None,
    category: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """List problem reports for a guild."""
    return await report_service.list_reports(guild_id, status, category)

@router.patch("/guilds/{guild_id}/reports/{report_id}")
async def update_problem_report(
    guild_id: str,
    report_id: str,
    body: ProblemReportUpdate,
    user: dict = Depends(get_current_user)
):
    """Update report status/resolution."""
    return await report_service.update_report(report_id, body, user)
```

### 5. Dashboard Integration

Add a "Reports" page to the dashboard:

```tsx
function ReportsPage() {
  return (
    <Page>
      <PageHeader>
        <h1>Problem Reports</h1>
        <Button onClick={openNewReport}>
          <Plus /> New Report
        </Button>
      </PageHeader>

      <Tabs defaultValue="open">
        <TabsList>
          <TabsTrigger value="open">Open ({openCount})</TabsTrigger>
          <TabsTrigger value="investigating">Investigating</TabsTrigger>
          <TabsTrigger value="resolved">Resolved</TabsTrigger>
        </TabsList>

        <TabsContent value="open">
          <ReportsList status="open" />
        </TabsContent>
        {/* ... */}
      </Tabs>
    </Page>
  );
}
```

### 6. Quick Report from Summary

Add a flag icon to summary cards for quick reporting:

```tsx
function SummaryCard({ summary }: Props) {
  return (
    <Card>
      {/* ... summary content ... */}

      <CardFooter>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => openQuickReport(summary)}
        >
          <Flag className="h-4 w-4" />
          Report Issue
        </Button>
      </CardFooter>
    </Card>
  );
}
```

### 7. Notification & Escalation

```python
class ReportNotificationService:
    async def notify_on_report(self, report: ProblemReport):
        # Notify guild admins via Discord webhook (if configured)
        if report.severity in ("high", "critical"):
            await self._notify_admins(report)

        # Track in metrics
        self.metrics.increment(
            "problem_reports_created",
            tags={
                "category": report.category,
                "severity": report.severity,
                "guild_id": report.guild_id
            }
        )

    async def escalate_if_needed(self, report: ProblemReport):
        # Auto-escalate if multiple similar reports
        similar = await self.repo.find_similar(report)
        if len(similar) >= 3:
            await self._create_incident(report, similar)
```

### 8. Analytics

Track reporting patterns to identify systemic issues:

```python
class ReportAnalytics:
    async def get_trends(self, guild_id: str) -> ReportTrends:
        return {
            "by_category": await self._count_by_category(guild_id),
            "by_severity": await self._count_by_severity(guild_id),
            "resolution_time_avg": await self._avg_resolution_time(guild_id),
            "top_issues": await self._get_top_issues(guild_id),
            "repeat_issues": await self._get_repeat_issues(guild_id)
        }
```

## Implementation Phases

### Phase 1: Core Infrastructure
- [ ] Create `problem_reports` database table
- [ ] Implement `ProblemReportRepository`
- [ ] Create API endpoints
- [ ] Add report types and schemas

### Phase 2: UI Components
- [ ] Create `ReportProblemDialog` component
- [ ] Add "Report Issue" button to summaries
- [ ] Add "Report Issue" button to feeds
- [ ] Create Reports dashboard page

### Phase 3: Context Capture
- [ ] Auto-capture browser info
- [ ] Link reports to related logs
- [ ] Link reports to related errors
- [ ] Capture summary metadata

### Phase 4: Notifications
- [ ] Email notifications for critical reports
- [ ] Discord webhook notifications
- [ ] In-app notification for report updates

### Phase 5: Analytics
- [ ] Report trends dashboard
- [ ] Pattern detection
- [ ] Auto-escalation rules

## Consequences

### Positive
- Users have a clear path to report problems
- Problems are tracked systematically
- Correlation with system logs aids debugging
- Pattern detection identifies systemic issues

### Negative
- Additional database storage for reports
- Need to monitor and respond to reports
- Potential for spam/abuse

### Neutral
- Requires ongoing triage process
- May surface issues that were previously unnoticed

## Related ADRs
- ADR-038: Self-Healing Parameter Validation
- ADR-027: Error Repository (related error tracking)

## Database Schema

```sql
CREATE TABLE problem_reports (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,

    category TEXT NOT NULL,
    severity TEXT NOT NULL,

    resource_type TEXT,
    resource_id TEXT,

    description TEXT NOT NULL,
    expected_behavior TEXT,
    actual_behavior TEXT,
    steps_to_reproduce TEXT,

    browser_info TEXT,
    page_url TEXT,
    request_id TEXT,
    system_state JSON,

    related_errors JSON,  -- Array of error IDs
    related_logs JSON,    -- Array of log references

    status TEXT DEFAULT 'open',
    resolution_notes TEXT,
    resolved_at TIMESTAMP,
    resolved_by TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (guild_id) REFERENCES guilds(id)
);

CREATE INDEX idx_reports_guild_status ON problem_reports(guild_id, status);
CREATE INDEX idx_reports_category ON problem_reports(category);
CREATE INDEX idx_reports_resource ON problem_reports(resource_type, resource_id);
```
