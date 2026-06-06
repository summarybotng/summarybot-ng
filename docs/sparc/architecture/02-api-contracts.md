# Architecture: API Contracts

**SPARC Phase**: Architecture
**Module**: `v3/src/api/`

---

## Base URL

```
Production: https://api.summarybot.io/v3
Development: http://localhost:8000/v3
```

## Authentication

All endpoints except `/auth/*` require Bearer token:

```http
Authorization: Bearer <access_token>
```

---

## Auth Endpoints

### POST /auth/oauth/{provider}/url

Get OAuth authorization URL.

```yaml
Request:
  provider: discord | slack | google
  redirect_uri: string
  state: string (optional, generated if omitted)

Response 200:
  url: string
  state: string
```

### POST /auth/oauth/{provider}/callback

Handle OAuth callback.

```yaml
Request:
  code: string
  state: string

Response 200:
  user:
    id: uuid
    name: string
    email: string?
    avatar_url: string?
  workspaces:
    - id: uuid
      name: string
      platform: discord | slack | whatsapp
  access_token: string
  refresh_token: string
  expires_in: integer (seconds)

Response 401:
  error: "invalid_code" | "invalid_state" | "provider_error"
  message: string
```

### POST /auth/refresh

Refresh access token.

```yaml
Request:
  refresh_token: string

Response 200:
  access_token: string
  expires_in: integer

Response 401:
  error: "invalid_token" | "expired_token"
```

### POST /auth/logout

Revoke refresh token.

```yaml
Request:
  refresh_token: string

Response 204: (no content)
```

---

## Workspace Endpoints

### GET /workspaces

List user's workspaces.

```yaml
Response 200:
  items:
    - id: uuid
      name: string
      owner_id: uuid
      connections:
        - platform: discord | slack | whatsapp
          platform_id: string
          platform_name: string
          connected_at: datetime
      created_at: datetime
  total: integer
```

### GET /workspaces/{workspace_id}

Get workspace details.

```yaml
Response 200:
  id: uuid
  name: string
  owner_id: uuid
  connections: [...]
  settings:
    default_summary_type: brief | detailed | comprehensive
    default_perspective: general | developer | executive
    timezone: string
  stats:
    total_summaries: integer
    total_schedules: integer
    total_cost_usd: decimal
  created_at: datetime

Response 404:
  error: "workspace_not_found"
```

### GET /workspaces/{workspace_id}/channels

List channels in workspace.

```yaml
Query:
  platform: discord | slack (optional)

Response 200:
  items:
    - id: string
      name: string
      type: text | voice | category
      platform: discord | slack
      category_id: string?
      category_name: string?
```

---

## Summary Endpoints

### POST /workspaces/{workspace_id}/summaries/generate

Generate a new summary.

```yaml
Request:
  channel_ids: string[] (at least 1)
  since: datetime
  until: datetime
  options:
    length: brief | detailed | comprehensive (default: detailed)
    perspective: general | developer | executive | marketing (default: general)
    model: string (optional, e.g., "anthropic/claude-sonnet-4")
  priority: manual | normal | low (default: normal)

Response 202:
  job_id: uuid
  status: pending
  estimated_seconds: integer?

Response 400:
  error: "invalid_date_range" | "no_channels" | "insufficient_messages"
  message: string

Response 429:
  error: "rate_limited"
  retry_after: integer (seconds)
```

### GET /workspaces/{workspace_id}/summaries

List summaries.

```yaml
Query:
  limit: integer (default: 50, max: 100)
  offset: integer (default: 0)
  channel_id: string (optional, filter)
  since: datetime (optional)
  until: datetime (optional)
  status: draft | published | archived (optional)

Response 200:
  items:
    - id: uuid
      channel_ids: string[]
      content: string (truncated to 500 chars)
      key_points: string[]
      message_count: integer
      start_time: datetime
      end_time: datetime
      status: draft | published | archived
      cost_usd: decimal
      created_at: datetime
  total: integer
  limit: integer
  offset: integer
```

### GET /workspaces/{workspace_id}/summaries/{summary_id}

Get full summary.

```yaml
Response 200:
  id: uuid
  workspace_id: uuid
  channel_ids: string[]
  content: string (full)
  key_points: string[]
  action_items:
    - id: uuid
      content: string
      assignee: string?
      deadline: datetime?
      priority: low | medium | high | urgent
      completed: boolean
  participants:
    - user_id: string
      username: string
      message_count: integer
  message_count: integer
  start_time: datetime
  end_time: datetime
  generation_options:
    length: string
    perspective: string
    model: string
  input_tokens: integer
  output_tokens: integer
  cost_usd: decimal
  status: draft | published | archived
  created_at: datetime
  published_at: datetime?

Response 404:
  error: "summary_not_found"
```

### PATCH /workspaces/{workspace_id}/summaries/{summary_id}

Update summary.

```yaml
Request:
  status: published | archived (optional)
  action_items:
    - id: uuid
      completed: boolean

Response 200:
  (full summary object)
```

### DELETE /workspaces/{workspace_id}/summaries/{summary_id}

Delete summary.

```yaml
Response 204: (no content)

Response 404:
  error: "summary_not_found"
```

---

## Schedule Endpoints

### POST /workspaces/{workspace_id}/schedules

Create schedule.

```yaml
Request:
  name: string
  scope: workspace | category | channel
  channel_ids: string[]? (required if scope=channel)
  category_id: string? (required if scope=category)
  frequency: daily | weekly | monthly
  cron_expression: string (e.g., "0 9 * * 1-5")
  timezone: string (e.g., "America/New_York")
  lookback_hours: integer (1-168)
  min_messages: integer (default: 5)
  summary_options:
    length: brief | detailed | comprehensive
    perspective: general | developer | executive
  destinations:
    - type: discord_channel | email | webhook | confluence
      target: string
      options: object?
  enabled: boolean (default: true)

Response 201:
  id: uuid
  name: string
  next_run_at: datetime
  ...

Response 400:
  error: "invalid_cron" | "invalid_scope" | "no_destinations"
```

### GET /workspaces/{workspace_id}/schedules

List schedules.

```yaml
Response 200:
  items:
    - id: uuid
      name: string
      scope: workspace | category | channel
      frequency: daily | weekly | monthly
      cron_expression: string
      timezone: string
      enabled: boolean
      last_run_at: datetime?
      next_run_at: datetime
      run_count: integer
      failure_count: integer
```

### POST /workspaces/{workspace_id}/schedules/{schedule_id}/execute

Execute schedule immediately.

```yaml
Response 202:
  job_id: uuid
  status: pending
```

### DELETE /workspaces/{workspace_id}/schedules/{schedule_id}

Delete schedule.

```yaml
Response 204: (no content)
```

---

## Job Endpoints

### GET /workspaces/{workspace_id}/jobs/{job_id}

Get job status.

```yaml
Response 200:
  id: uuid
  type: summary_generation | schedule_execution
  status: pending | running | completed | failed | rate_limited
  progress:
    total: integer
    completed: integer
    failed: integer
    percent: float
  result:
    summary_id: uuid? (if completed)
    error: string? (if failed)
    failure_reason: rate_limited | quota_exceeded | invalid_request | service_unavailable
  created_at: datetime
  started_at: datetime?
  completed_at: datetime?

Response 404:
  error: "job_not_found"
```

---

## Error Responses

All error responses follow this format:

```yaml
Response 4xx/5xx:
  error: string (machine-readable code)
  message: string (human-readable)
  details: object? (optional additional info)
  request_id: string (for support)
```

### Common Error Codes

| HTTP | Error Code | Description |
|------|------------|-------------|
| 400 | invalid_request | Malformed request body |
| 401 | unauthorized | Missing or invalid token |
| 403 | forbidden | No access to resource |
| 404 | not_found | Resource doesn't exist |
| 429 | rate_limited | Too many requests |
| 500 | internal_error | Server error |
| 503 | service_unavailable | Temporary outage |

---

*Next: `03-database-schema.md`*
