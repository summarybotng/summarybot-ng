# ADR-030: Email Delivery Destination

**Status:** Proposed
**Date:** 2026-03-03
**Depends on:** ADR-005 (Summary Delivery Destinations)

---

## 1. Context

Currently, summaries can be delivered to:
- **Dashboard** — Stored for viewing and manual push (ADR-005)
- **Discord Channel** — Posted directly with embed/template formatting (ADR-014)
- **Webhook** — Sent to external services as JSON

However, many stakeholders need summaries delivered outside of Discord:

1. **Team members without Discord access** — Executives, external partners, or contractors who aren't in the Discord server
2. **Mobile reading** — Email provides a better reading experience for long summaries on mobile devices
3. **Permanent record** — Email creates a searchable, archivable record in the recipient's inbox
4. **Digest workflows** — Some teams prefer email-based workflows for daily/weekly digests
5. **Compliance requirements** — Some organizations require email-based communication trails

The `DestinationType.EMAIL` enum value already exists in `src/models/task.py` but is not implemented.

---

## 2. Decision

Implement email delivery as a fully supported destination type using `aiosmtplib` for async SMTP operations. Summaries will be rendered as both HTML and plain text for maximum compatibility.

### 2.1 Email Delivery Service

```python
# src/services/email_delivery.py

class EmailDeliveryService:
    """Handles email delivery of summaries."""

    def __init__(self, smtp_config: SMTPConfig):
        self.config = smtp_config

    async def send_summary(
        self,
        summary: SummaryResult,
        recipients: List[str],
        subject: Optional[str] = None,
        context: Optional[PushContext] = None,
    ) -> EmailDeliveryResult:
        """Send summary to email recipients."""
        ...
```

### 2.2 SMTP Configuration

Add SMTP configuration via environment variables:

```python
# src/config/settings.py

@dataclass
class SMTPConfig:
    """SMTP configuration for email delivery."""
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    use_tls: bool = True
    from_address: str = ""
    from_name: str = "SummaryBot"
    enabled: bool = False
```

Environment variables:
- `SMTP_HOST` — SMTP server hostname (e.g., `smtp.sendgrid.net`)
- `SMTP_PORT` — SMTP port (default: 587)
- `SMTP_USERNAME` — SMTP authentication username
- `SMTP_PASSWORD` — SMTP authentication password
- `SMTP_USE_TLS` — Enable TLS (default: true)
- `SMTP_FROM_ADDRESS` — Sender email address
- `SMTP_FROM_NAME` — Sender display name (default: "SummaryBot")

### 2.3 Email Templates

Create HTML and plain text templates for email rendering:

```
src/templates/email/
├── summary.html      # Rich HTML template with styling
└── summary.txt       # Plain text fallback
```

The HTML template will include:
- Responsive design for mobile
- Styled sections matching Discord embed structure
- Key points, action items, decisions with citations
- Participant summary
- Footer with timestamp and source info

### 2.4 Destination Model Updates

Extend the `Destination` model for email-specific options:

```python
@dataclass
class Destination(BaseModel):
    type: DestinationType
    target: str  # For EMAIL: comma-separated email addresses
    format: str = "embed"
    enabled: bool = True

    # Email-specific options
    email_subject_template: Optional[str] = None  # Custom subject line
    email_include_attachments: bool = False  # Future: PDF attachment
```

---

## 3. API Changes

### 3.1 Schedule Creation

The existing schedule creation API already supports the `destinations` array. Email destinations use:

```json
{
  "destinations": [
    {
      "type": "email",
      "target": "team@example.com, manager@example.com",
      "format": "html",
      "enabled": true
    }
  ]
}
```

### 3.2 Validation

Email addresses are validated on schedule creation:
- Must be valid email format
- Multiple recipients separated by commas
- Maximum 10 recipients per destination (rate limit protection)

---

## 4. Executor Integration

Add `_deliver_to_email()` method to `TaskExecutor`:

```python
# src/scheduling/executor.py

async def _deliver_to_email(
    self,
    summary: SummaryResult,
    destination: Destination,
    task: SummaryTask,
) -> Dict[str, Any]:
    """Deliver summary via email.

    Args:
        summary: Summary to deliver
        destination: Email destination with recipients
        task: Original summary task for context

    Returns:
        Delivery result dict
    """
    from ..services.email_delivery import get_email_service

    service = get_email_service()
    if not service.is_configured():
        return {
            "destination_type": "email",
            "target": destination.target,
            "success": False,
            "error": "SMTP not configured"
        }

    recipients = [r.strip() for r in destination.target.split(",")]

    result = await service.send_summary(
        summary=summary,
        recipients=recipients,
        context=self._build_push_context(task, summary),
    )

    return {
        "destination_type": "email",
        "target": destination.target,
        "success": result.success,
        "message": f"Sent to {len(recipients)} recipient(s)",
        "error": result.error if not result.success else None,
    }
```

Update `_deliver_summary()` to handle `DestinationType.EMAIL`:

```python
elif destination.type == DestinationType.EMAIL:
    result = await self._deliver_to_email(
        summary=summary,
        destination=destination,
        task=task
    )
    delivery_results.append(result)
```

---

## 5. UI Integration

### 5.1 ScheduleForm Updates

Add email option to the destination picker in `ScheduleForm.tsx`:

```tsx
// Email Option
<div className="space-y-2 rounded-md border p-3">
  <div className="flex items-start space-x-3">
    <Checkbox
      id="dest-email"
      checked={formData.destinations.email}
      onCheckedChange={(checked) =>
        onChange({
          ...formData,
          destinations: { ...formData.destinations, email: checked as boolean },
        })
      }
    />
    <div className="space-y-1 flex-1">
      <label htmlFor="dest-email" className="text-sm font-medium cursor-pointer flex items-center gap-2">
        <Mail className="h-4 w-4" />
        Email
      </label>
      <p className="text-xs text-muted-foreground">
        Send to email addresses
      </p>
    </div>
  </div>
  {formData.destinations.email && (
    <Input
      className="mt-2"
      placeholder="team@example.com, manager@example.com"
      value={formData.destinations.email_addresses}
      onChange={(e) =>
        onChange({
          ...formData,
          destinations: { ...formData.destinations, email_addresses: e.target.value },
        })
      }
    />
  )}
</div>
```

### 5.2 Form Data Updates

```typescript
// ScheduleFormData type
destinations: {
  dashboard: boolean;
  discord_channel: boolean;
  discord_channel_id: string;
  webhook: boolean;
  webhook_url: string;
  email: boolean;           // NEW
  email_addresses: string;  // NEW
};
```

---

## 6. Security Considerations

### 6.1 SMTP Credentials

- SMTP credentials stored only in environment variables
- Never logged or exposed in API responses
- Password field redacted in config serialization

### 6.2 Rate Limiting

- Maximum 10 recipients per email destination
- Rate limit: 50 emails per hour per guild (configurable)
- Exponential backoff on SMTP failures

### 6.3 Email Validation

- Validate email format before saving schedule
- Reject obviously invalid addresses
- Log delivery failures for monitoring

### 6.4 Content Safety

- Sanitize summary content before rendering to HTML
- Escape user-generated content to prevent XSS in email clients
- No external image loading (prevents tracking pixels in summaries)

---

## 7. File-by-File Change Map

| # | File | Action | Risk | Description |
|---|------|--------|------|-------------|
| 1 | `src/config/settings.py` | **M** | Low | Add `SMTPConfig` dataclass |
| 2 | `src/config/environment.py` | **M** | Low | Load SMTP config from env vars |
| 3 | `src/services/email_delivery.py` | **N** | Medium | New email delivery service |
| 4 | `src/templates/email/summary.html` | **N** | Low | HTML email template |
| 5 | `src/templates/email/summary.txt` | **N** | Low | Plain text email template |
| 6 | `src/scheduling/executor.py` | **M** | Medium | Add `_deliver_to_email()` method |
| 7 | `src/models/task.py` | **M** | Low | Add email-specific destination options |
| 8 | `src/frontend/.../ScheduleForm.tsx` | **M** | Low | Add email destination UI |
| 9 | `src/frontend/src/types/index.ts` | **M** | Low | Add email destination types |
| 10 | `tests/unit/test_email_delivery.py` | **N** | — | Unit tests for email service |

**Totals:** 6 files modified, 4 files created.

---

## 8. Implementation Plan

### Phase 1: Backend Infrastructure (1 day)
- [ ] Add `SMTPConfig` to settings
- [ ] Load SMTP config from environment
- [ ] Create `EmailDeliveryService` with `aiosmtplib`
- [ ] Create HTML and plain text templates

### Phase 2: Executor Integration (0.5 day)
- [ ] Add `_deliver_to_email()` to `TaskExecutor`
- [ ] Handle `DestinationType.EMAIL` in delivery routing
- [ ] Add error handling and logging

### Phase 3: Frontend (0.5 day)
- [ ] Add email option to `ScheduleForm.tsx`
- [ ] Update form data types
- [ ] Add email validation

### Phase 4: Testing (0.5 day)
- [ ] Unit tests for email rendering
- [ ] Integration test with Mailtrap SMTP
- [ ] E2E test: create schedule with email, trigger, verify delivery

---

## 9. Testing Strategy

### 9.1 Unit Tests

```python
# tests/unit/test_email_delivery.py

class TestEmailDeliveryService:
    def test_render_html_template(self):
        """HTML template renders correctly with summary data."""

    def test_render_plain_text_template(self):
        """Plain text template renders correctly."""

    def test_validate_email_addresses(self):
        """Invalid email addresses are rejected."""

    def test_multiple_recipients(self):
        """Multiple comma-separated recipients are parsed correctly."""
```

### 9.2 Integration Testing

Use Mailtrap (https://mailtrap.io) or similar SMTP testing service:

```bash
# .env.test
SMTP_HOST=sandbox.smtp.mailtrap.io
SMTP_PORT=2525
SMTP_USERNAME=<mailtrap_user>
SMTP_PASSWORD=<mailtrap_pass>
SMTP_FROM_ADDRESS=summarybot@test.local
```

---

## 10. Future Enhancements

| Enhancement | Description |
|-------------|-------------|
| **PDF Attachments** | Attach summary as PDF for offline reading |
| **Per-Guild SMTP** | Allow guilds to configure their own SMTP (white-label) |
| **Digest Mode** | Combine multiple summaries into daily/weekly digest emails |
| **Unsubscribe Links** | Allow recipients to opt out of specific schedules |
| **Delivery Tracking** | Track email opens/clicks (optional, privacy-conscious) |
| **Template Customization** | Per-guild email template customization |

---

## 11. Consequences

### Positive
- **Broader reach** — Summaries accessible to non-Discord users
- **Better mobile experience** — Email is often easier to read on mobile
- **Compliance friendly** — Creates email audit trail
- **Existing infrastructure** — Uses well-understood SMTP protocol

### Negative
- **Additional configuration** — Requires SMTP setup
- **Delivery reliability** — Email delivery can be unreliable (spam filters, etc.)
- **Credential management** — SMTP credentials need secure handling

### Trade-offs
- **HTML vs Plain Text** — We send both (multipart) for maximum compatibility
- **Rate Limiting** — Conservative limits to prevent abuse, may need adjustment

---

## 12. Dependencies

- `aiosmtplib` — Async SMTP client for Python
- `jinja2` — Template rendering (already in project)
- `email-validator` — Email address validation

---

## 13. References

- [ADR-005: Summary Delivery Destinations](./005-summary-delivery-destinations.md)
- [ADR-014: Discord Push Templates](./014-discord-push-templates.md)
- [aiosmtplib Documentation](https://aiosmtplib.readthedocs.io/)
- [Mailtrap Testing Service](https://mailtrap.io/)
