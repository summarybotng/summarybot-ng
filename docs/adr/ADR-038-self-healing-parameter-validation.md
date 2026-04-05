# ADR-038: Self-Healing Parameter Validation

## Status
Proposed

## Context

The system allows users to select parameters (perspective, summary_length, etc.) that may not have corresponding implementations. For example:
- A "security" perspective can be selected, but no `security/*.md` prompts exist
- The system falls back to `discussion.md` but tags the output as "security"
- This creates a mismatch between what was requested and what was actually used

This type of silent fallback without validation or notification leads to:
1. User confusion when output doesn't match expectations
2. Difficult debugging
3. Incorrect metadata tagging
4. Trust erosion in the system

## Decision

Implement a self-healing parameter validation system with the following components:

### 1. Pre-Execution Validation

Before generating a summary, validate that requested parameters have valid implementations:

```python
class ParameterValidator:
    async def validate_request(self, options: SummaryOptions) -> ValidationResult:
        issues = []

        # Check perspective exists
        if options.perspective:
            if not self.prompt_provider.has_perspective(options.perspective):
                issues.append(ValidationIssue(
                    field="perspective",
                    requested=options.perspective,
                    available=self.prompt_provider.list_perspectives(),
                    severity="warning",
                    auto_fix="general"
                ))

        # Check prompt template exists
        if options.prompt_template_id:
            template = await self.repo.get_template(options.prompt_template_id)
            if not template:
                issues.append(ValidationIssue(
                    field="prompt_template_id",
                    requested=options.prompt_template_id,
                    severity="error",
                    auto_fix=None
                ))

        return ValidationResult(valid=len(issues) == 0, issues=issues)
```

### 2. Post-Execution Verification

After generation, verify the output matches expectations:

```python
class OutputVerifier:
    def verify_generation(
        self,
        request: SummaryOptions,
        result: SummaryResult
    ) -> VerificationResult:
        discrepancies = []

        # Check prompt actually used
        if result.metadata.get("prompt_path"):
            expected_path = f"{request.perspective}/{request.summary_length}.md"
            actual_path = result.metadata["prompt_path"]
            if expected_path not in actual_path:
                discrepancies.append(PromptMismatch(
                    expected=expected_path,
                    actual=actual_path,
                    reason="Fallback prompt used"
                ))

        return VerificationResult(
            matches_request=len(discrepancies) == 0,
            discrepancies=discrepancies
        )
```

### 3. Automatic Healing Actions

```python
class SelfHealingService:
    async def heal(self, issue: ValidationIssue) -> HealingResult:
        if issue.field == "perspective" and issue.auto_fix:
            # Auto-correct to valid perspective
            return HealingResult(
                action="substituted",
                original=issue.requested,
                corrected=issue.auto_fix,
                notification=f"Perspective '{issue.requested}' not available, using '{issue.auto_fix}'"
            )

        if issue.severity == "error":
            # Cannot auto-heal, reject request
            return HealingResult(
                action="rejected",
                reason=f"Invalid {issue.field}: {issue.requested}"
            )
```

### 4. Audit Trail

All validations, fallbacks, and healing actions are logged:

```python
@dataclass
class ParameterAuditEntry:
    timestamp: datetime
    request_id: str
    guild_id: str
    field: str
    requested_value: Any
    actual_value: Any
    action: str  # "validated", "healed", "rejected"
    notification_sent: bool
```

### 5. Metadata Enhancement

Store validation results in summary metadata:

```json
{
  "perspective": "security",
  "perspective_validated": false,
  "perspective_fallback": "general",
  "prompt_path": "defaults/discussion.md",
  "validation_warnings": [
    "Requested perspective 'security' not found, used fallback"
  ]
}
```

### 6. Real-time Notifications

When fallbacks occur, notify users via:
- Dashboard toast notifications
- Summary metadata badges (e.g., "⚠️ Fallback prompt used")
- Error log entries viewable in Errors page

## Implementation Phases

### Phase 1: Validation Infrastructure
- [ ] Create `ParameterValidator` service
- [ ] Add `has_perspective()` to prompt provider
- [ ] Create validation result types

### Phase 2: Pre-Execution Checks
- [ ] Validate perspective before generation
- [ ] Validate prompt_template_id before generation
- [ ] Add validation to scheduled task execution

### Phase 3: Post-Execution Verification
- [ ] Store prompt path in metadata
- [ ] Compare expected vs actual prompt
- [ ] Log discrepancies

### Phase 4: Healing & Notifications
- [ ] Implement auto-fix for missing perspectives
- [ ] Add toast notifications in dashboard
- [ ] Add warning badges to summaries with fallbacks

### Phase 5: Audit & Reporting
- [ ] Create audit log for parameter issues
- [ ] Add metrics for fallback frequency
- [ ] Dashboard page for viewing parameter health

## Consequences

### Positive
- Users know when their requests can't be fulfilled exactly
- Clear audit trail for debugging
- Automatic correction prevents silent failures
- Improved trust in system behavior

### Negative
- Additional validation overhead
- More complex error handling
- Need to maintain validation rules

### Neutral
- Requires UI updates for notifications
- May surface previously hidden issues

## Related ADRs
- ADR-034: Guild Prompt Templates
- ADR-035: Summary Generation Options
- ADR-039: User Problem Reporting (companion ADR)

## Notes

The security perspective issue discovered:
- User selected "security" perspective
- No `/prompts/defaults/security/` directory exists
- System fell back to `discussion.md`
- Summary tagged as "security" despite using generic prompt
- No notification to user about the fallback

This ADR addresses this class of problems systematically.
