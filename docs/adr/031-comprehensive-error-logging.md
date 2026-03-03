# ADR-031: Comprehensive Error Logging

## Status
Implemented

## Context

Currently, errors in various services (email delivery, SMTP connections, API calls) are not consistently logged or surfaced to application logs. This makes debugging production issues difficult because:

1. SMTP connection failures don't include enough context (host, port, TLS settings)
2. Service initialization errors may be silently swallowed
3. API endpoint errors return messages to clients but don't always log server-side
4. Background task failures (scheduling, webhooks) may not be visible in logs

When users report "Failed to send email" or similar errors, we need comprehensive server-side logs to diagnose the issue.

## Decision

Implement comprehensive error logging across all services with the following standards:

### 1. Logging Levels

- **ERROR**: Failures that prevent operations from completing (SMTP connection failed, database errors)
- **WARNING**: Recoverable issues or degraded functionality (rate limits, retries)
- **INFO**: Significant state changes (service initialization, configuration loaded)
- **DEBUG**: Detailed operational info (individual email sent, API call timing)

### 2. Error Context Requirements

All error logs MUST include:
- **Service name**: Which service generated the error
- **Operation**: What was being attempted
- **Context**: Relevant parameters (sanitized - no secrets)
- **Error details**: Exception type and message
- **Correlation ID**: Request ID or task ID for tracing

### 3. Service-Specific Requirements

#### Email Delivery (ADR-030)
```python
# On initialization
logger.info(f"Email service initialized: enabled={config.enabled}, host={config.host}, port={config.port}, configured={config.is_configured()}")

# On send attempt
logger.info(f"Sending email to {len(recipients)} recipients for guild {guild_id}")

# On failure
logger.error(f"SMTP error connecting to {host}:{port} (TLS={use_tls}, STARTTLS={use_starttls}): {error}")
```

#### API Endpoints
```python
# Log all 4xx/5xx responses with context
logger.warning(f"API error {status_code} on {method} {path}: {error_code} - {message}")
```

#### Background Tasks
```python
# Log task start/completion/failure
logger.info(f"Task {task_id} started: {description}")
logger.error(f"Task {task_id} failed after {duration}s: {error}")
```

### 4. Sensitive Data Handling

NEVER log:
- Passwords or API keys
- Email content (only metadata like recipient count)
- Personal user data beyond IDs
- Full authentication tokens

DO log (sanitized):
- Host/port configurations
- User/guild IDs
- Operation types
- Error messages (unless they contain secrets)

### 5. Implementation Checklist

- [x] Email service: Log initialization with config status
- [x] Email service: Log SMTP connection errors with context
- [x] API routes: Add middleware for error logging (`src/dashboard/middleware.py`)
- [x] Scheduling executor: Log delivery attempts and failures
- [x] Discord bot: Log command errors (`src/discord_bot/events.py`)
- [x] Webhook handlers: Log incoming request errors

## Implementation

### Email Service Updates

```python
# In get_email_service()
logger.info(
    f"Email service initialized: enabled={config.enabled}, "
    f"host={config.host}, port={config.port}, "
    f"from={config.from_address}, configured={config.is_configured()}"
)

# In send_summary()
except Exception as e:
    logger.exception(f"SMTP error connecting to {self.config.host}:{self.config.port}: {e}")
```

### API Error Logging Middleware

Implemented in `src/dashboard/middleware.py`:

```python
class ErrorLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        try:
            response = await call_next(request)
            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code >= 500:
                logger.error(f"[{request_id}] HTTP {response.status_code} {request.method} {request.url.path} ({duration_ms}ms)")
            elif response.status_code >= 400:
                logger.warning(f"[{request_id}] HTTP {response.status_code} {request.method} {request.url.path} ({duration_ms}ms)")

            return response
        except Exception as e:
            logger.exception(f"[{request_id}] Unhandled error on {request.method} {request.url.path}")
            raise
```

### Scheduling Executor Delivery Logging

```python
# Before each delivery attempt
logger.info(f"Delivering summary {summary.id} to {destination.type.value}: target={destination.target}")

# On delivery failure
logger.error(f"Delivery failed: destination={destination.type.value}, target={destination.target}, error={e}")
```

### Discord Bot Command Error Handler

Already implemented in `src/discord_bot/events.py`:

```python
async def on_application_command_error(self, interaction, error):
    context = create_error_context(
        user_id=str(interaction.user.id),
        guild_id=str(interaction.guild_id),
        command=interaction.command.name
    )
    logger.error(f"Command error: {error}", extra={"context": context.to_dict()})
```

### Webhook Handler Logging

```python
# On webhook test success/failure
logger.info(f"Webhook test success: webhook_id={webhook_id}, status={response.status_code}")
logger.warning(f"Webhook test failed: webhook_id={webhook_id}, status={response.status_code}")

# On webhook creation/deletion
logger.info(f"Webhook created: webhook_id={webhook_id}, guild_id={guild_id}, created_by={user['sub']}")
logger.info(f"Webhook deleted: webhook_id={webhook_id}, guild_id={guild_id}")
```

## Consequences

### Positive
- Faster debugging of production issues
- Better visibility into service health
- Easier correlation of user reports to server logs
- Consistent logging format across services

### Negative
- Slightly increased log volume
- Need to ensure sensitive data is never logged
- Log storage costs may increase

## Related ADRs

- ADR-030: Email Delivery Destination (email service logging)
- ADR-024: Service Resilience (retry logging)
