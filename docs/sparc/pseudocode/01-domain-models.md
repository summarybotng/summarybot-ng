# Pseudocode: Domain Models

**SPARC Phase**: Pseudocode
**Module**: `v3/src/domain/models/`

---

## 1. Workspace Model

```pseudocode
ENTITY Workspace:
    id: UUID
    name: String[1..100]
    owner_id: UUID
    connections: List<PlatformConnection>
    settings: WorkspaceSettings
    created_at: DateTime
    updated_at: DateTime

    INVARIANT: connections.length >= 1  # Must have at least one platform
    INVARIANT: name.trim().length >= 1

    FUNCTION add_connection(connection: PlatformConnection):
        IF connections.any(c => c.platform == connection.platform AND c.platform_id == connection.platform_id):
            RAISE DuplicateConnectionError
        connections.append(connection)
        updated_at = NOW()

    FUNCTION remove_connection(platform: Platform, platform_id: String):
        IF connections.length == 1:
            RAISE LastConnectionError("Cannot remove last connection")
        connections.remove_where(c => c.platform == platform AND c.platform_id == platform_id)
        updated_at = NOW()

    FUNCTION has_platform(platform: Platform) -> Boolean:
        RETURN connections.any(c => c.platform == platform)

    FUNCTION get_connection(platform: Platform) -> Optional<PlatformConnection>:
        RETURN connections.find(c => c.platform == platform)
```

## 2. Platform Connection

```pseudocode
VALUE_OBJECT PlatformConnection:
    id: UUID
    platform: Platform  # DISCORD | SLACK | WHATSAPP
    platform_id: String  # guild_id, team_id, group_id
    platform_name: String
    access_token: EncryptedString  # Encrypted at rest
    refresh_token: Optional<EncryptedString>
    token_expires_at: Optional<DateTime>
    connected_at: DateTime
    connected_by: UUID  # User who connected

    FUNCTION is_token_expired() -> Boolean:
        IF token_expires_at IS NULL:
            RETURN FALSE
        RETURN NOW() > token_expires_at

    FUNCTION needs_refresh() -> Boolean:
        IF token_expires_at IS NULL:
            RETURN FALSE
        RETURN NOW() > (token_expires_at - 5.minutes)
```

## 3. Summary Model

```pseudocode
ENTITY Summary:
    id: UUID
    workspace_id: UUID
    channel_ids: List<String>[1..*]  # At least one channel

    # Content
    content: String[1..50000]
    key_points: List<String>[0..20]
    action_items: List<ActionItem>
    participants: List<Participant>

    # Metadata
    message_count: Integer[1..*]
    start_time: DateTime
    end_time: DateTime
    generation_options: GenerationOptions

    # Cost tracking
    input_tokens: Integer
    output_tokens: Integer
    cost_usd: Decimal[0..]
    model_used: String

    # Lifecycle
    status: SummaryStatus  # DRAFT | PUBLISHED | ARCHIVED
    created_at: DateTime
    published_at: Optional<DateTime>

    INVARIANT: end_time > start_time
    INVARIANT: message_count >= 1

    COMPUTED duration_hours -> Float:
        RETURN (end_time - start_time).total_seconds() / 3600

    COMPUTED has_pending_actions -> Boolean:
        RETURN action_items.any(item => NOT item.completed)

    FUNCTION publish():
        IF status != DRAFT:
            RAISE InvalidStateTransition
        status = PUBLISHED
        published_at = NOW()

    FUNCTION archive():
        IF status == ARCHIVED:
            RAISE InvalidStateTransition
        status = ARCHIVED
```

## 4. Action Item

```pseudocode
VALUE_OBJECT ActionItem:
    id: UUID
    content: String[1..500]
    assignee: Optional<String>
    deadline: Optional<DateTime>
    priority: Priority  # LOW | MEDIUM | HIGH | URGENT
    completed: Boolean = FALSE
    completed_at: Optional<DateTime>
    extracted_from: String  # Original message snippet

    FUNCTION mark_complete():
        IF completed:
            RETURN  # Idempotent
        completed = TRUE
        completed_at = NOW()

    FUNCTION is_overdue() -> Boolean:
        IF deadline IS NULL OR completed:
            RETURN FALSE
        RETURN NOW() > deadline
```

## 5. Schedule Model

```pseudocode
ENTITY Schedule:
    id: UUID
    workspace_id: UUID
    name: String[1..100]

    # Scope
    scope: ScheduleScope  # WORKSPACE | CATEGORY | CHANNEL
    channel_ids: Optional<List<String>>  # For CHANNEL scope
    category_id: Optional<String>  # For CATEGORY scope

    # Timing
    frequency: Frequency  # DAILY | WEEKLY | MONTHLY
    cron_expression: String  # "0 9 * * 1" for Monday 9am
    timezone: String  # "America/New_York"

    # Options
    summary_options: SummaryOptions
    lookback_hours: Integer[1..168]  # Max 1 week
    min_messages: Integer[1..] = 5

    # Delivery
    destinations: List<DeliveryDestination>[1..*]

    # State
    enabled: Boolean = TRUE
    last_run_at: Optional<DateTime>
    next_run_at: DateTime
    run_count: Integer = 0
    failure_count: Integer = 0
    max_failures: Integer = 3

    created_at: DateTime
    created_by: UUID

    FUNCTION calculate_time_range() -> (DateTime, DateTime):
        until = NOW()
        since = until - lookback_hours.hours
        RETURN (since, until)

    FUNCTION calculate_next_run():
        next_run_at = CRON_NEXT(cron_expression, timezone, FROM: NOW())

    FUNCTION record_success():
        last_run_at = NOW()
        run_count += 1
        failure_count = 0  # Reset on success
        calculate_next_run()

    FUNCTION record_failure():
        failure_count += 1
        IF failure_count >= max_failures:
            enabled = FALSE
        ELSE:
            calculate_next_run()

    FUNCTION is_due() -> Boolean:
        RETURN enabled AND NOW() >= next_run_at
```

## 6. User Model

```pseudocode
ENTITY User:
    id: UUID
    name: String[1..100]
    email: Optional<Email>
    avatar_url: Optional<URL>

    # Multi-provider identity
    identities: List<UserIdentity>[1..*]

    # Preferences
    preferences: UserPreferences

    # State
    created_at: DateTime
    last_login_at: Optional<DateTime>

    FUNCTION add_identity(provider: AuthProvider, provider_id: String, metadata: Dict):
        IF identities.any(i => i.provider == provider AND i.provider_id == provider_id):
            RAISE DuplicateIdentityError
        identities.append(UserIdentity(
            provider=provider,
            provider_id=provider_id,
            metadata=metadata,
            linked_at=NOW()
        ))

    FUNCTION has_identity(provider: AuthProvider) -> Boolean:
        RETURN identities.any(i => i.provider == provider)

    FUNCTION get_identity(provider: AuthProvider) -> Optional<UserIdentity>:
        RETURN identities.find(i => i.provider == provider)

VALUE_OBJECT UserIdentity:
    provider: AuthProvider  # DISCORD | SLACK | GOOGLE | EMAIL
    provider_id: String
    provider_username: Optional<String>
    metadata: Dict
    linked_at: DateTime
```

## 7. Domain Events

```pseudocode
EVENT SummaryGenerated:
    summary_id: UUID
    workspace_id: UUID
    channel_ids: List<String>
    generated_at: DateTime
    cost_usd: Decimal
    triggered_by: TriggerType  # MANUAL | SCHEDULED | API

EVENT SummaryPublished:
    summary_id: UUID
    workspace_id: UUID
    published_at: DateTime

EVENT ScheduleExecuted:
    schedule_id: UUID
    workspace_id: UUID
    summary_id: UUID
    executed_at: DateTime
    success: Boolean
    error: Optional<String>

EVENT WorkspaceConnected:
    workspace_id: UUID
    platform: Platform
    platform_id: String
    connected_by: UUID
    connected_at: DateTime

EVENT RateLimitHit:
    provider: String
    retry_after_seconds: Integer
    occurred_at: DateTime
    affected_job_id: Optional<UUID>
```

---

*Next: `02-summary-service.md`*
