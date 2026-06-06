# Pseudocode: Schedule Executor

**SPARC Phase**: Pseudocode
**Module**: `v3/src/services/schedule_service.py`

---

## 1. Schedule Service

```pseudocode
SERVICE ScheduleService:
    DEPENDENCIES:
        schedule_repo: ScheduleRepository
        summary_service: SummaryService
        delivery_service: DeliveryService
        channel_resolver: ChannelResolver
        event_bus: EventBus
        rate_limiter: GlobalRateLimiter

    CONFIG:
        tick_interval: Integer = 60  # Seconds between checks
        max_concurrent: Integer = 3   # Max concurrent executions
        stale_threshold: Integer = 300  # 5 min stale detection

    STATE:
        running: Boolean = FALSE
        active_executions: Set<UUID>
        semaphore: AsyncSemaphore(max_concurrent)
```

## 2. Scheduler Loop

```pseudocode
ASYNC FUNCTION start():
    """Start the scheduler main loop."""

    IF running:
        LOG.warning("Scheduler already running")
        RETURN

    running = TRUE
    LOG.info("Scheduler started")

    WHILE running:
        TRY:
            AWAIT tick()
        CATCH Exception as e:
            LOG.error(f"Scheduler tick error: {e}")
            # Continue running despite errors

        AWAIT sleep(tick_interval)

    LOG.info("Scheduler stopped")


ASYNC FUNCTION stop():
    """Stop the scheduler gracefully."""
    running = FALSE

    # Wait for active executions to complete (with timeout)
    IF active_executions.length > 0:
        LOG.info(f"Waiting for {active_executions.length} active executions")
        AWAIT wait_for_completion(timeout=60)


ASYNC FUNCTION tick():
    """Process one scheduler tick."""

    now = NOW()

    # Step 1: Get due schedules
    due_schedules = AWAIT schedule_repo.get_due(now)

    IF due_schedules.length == 0:
        RETURN

    LOG.info(f"Found {due_schedules.length} due schedules")

    # Step 2: Execute each (with concurrency limit)
    tasks = []
    FOR schedule IN due_schedules:
        IF schedule.id IN active_executions:
            LOG.debug(f"Schedule {schedule.id} already executing, skipping")
            CONTINUE

        task = spawn(execute_with_semaphore(schedule))
        tasks.append(task)

    # Step 3: Wait for all to complete
    AWAIT gather(tasks, return_exceptions=TRUE)
```

## 3. Schedule Execution

```pseudocode
ASYNC FUNCTION execute_with_semaphore(schedule: Schedule):
    """Execute schedule with concurrency control."""

    ASYNC WITH semaphore:
        active_executions.add(schedule.id)
        TRY:
            AWAIT execute(schedule)
        FINALLY:
            active_executions.remove(schedule.id)


ASYNC FUNCTION execute(schedule: Schedule) -> ExecutionResult:
    """Execute a single schedule."""

    LOG.info(f"Executing schedule {schedule.id}: {schedule.name}")
    start_time = NOW()

    # Step 1: Calculate time range
    since, until = schedule.calculate_time_range()

    # Step 2: Resolve channels based on scope
    TRY:
        channel_ids = AWAIT resolve_channels(schedule)
    CATCH ChannelResolutionError as e:
        AWAIT record_failure(schedule, f"Channel resolution failed: {e}")
        RETURN ExecutionResult.FAILED

    IF channel_ids.length == 0:
        LOG.warning(f"No channels found for schedule {schedule.id}")
        AWAIT record_failure(schedule, "No channels in scope")
        RETURN ExecutionResult.FAILED

    # Step 3: Check for minimum messages
    message_count = AWAIT get_message_count(schedule.workspace_id, channel_ids, since, until)
    IF message_count < schedule.min_messages:
        LOG.info(f"Insufficient messages ({message_count} < {schedule.min_messages}), skipping")
        AWAIT record_skip(schedule, "insufficient_messages")
        RETURN ExecutionResult.SKIPPED

    # Step 4: Generate summary
    TRY:
        summary = AWAIT summary_service.generate(GenerateRequest(
            workspace_id=schedule.workspace_id,
            channel_ids=channel_ids,
            since=since,
            until=until,
            options=schedule.summary_options,
            trigger_type=TriggerType.SCHEDULED,
            priority=Priority.LOW
        ))
    CATCH RateLimitedError as e:
        LOG.warning(f"Rate limited, will retry next tick: {e}")
        # Don't count as failure - will retry naturally
        RETURN ExecutionResult.RATE_LIMITED
    CATCH InsufficientMessagesError as e:
        AWAIT record_skip(schedule, "insufficient_messages")
        RETURN ExecutionResult.SKIPPED
    CATCH GenerationError as e:
        AWAIT record_failure(schedule, str(e))
        RETURN ExecutionResult.FAILED

    # Step 5: Deliver to destinations
    delivery_results = AWAIT deliver_to_destinations(summary, schedule.destinations)

    # Step 6: Record success
    AWAIT record_success(schedule, summary.id)

    # Step 7: Emit event
    AWAIT event_bus.publish(ScheduleExecuted(
        schedule_id=schedule.id,
        workspace_id=schedule.workspace_id,
        summary_id=summary.id,
        executed_at=NOW(),
        success=TRUE,
        duration_seconds=(NOW() - start_time).total_seconds(),
        delivery_results=delivery_results
    ))

    RETURN ExecutionResult.SUCCESS
```

## 4. Channel Resolution

```pseudocode
ASYNC FUNCTION resolve_channels(schedule: Schedule) -> List<String>:
    """Resolve channel IDs based on schedule scope."""

    MATCH schedule.scope:
        ScheduleScope.CHANNEL:
            # Direct channel IDs specified
            RETURN schedule.channel_ids

        ScheduleScope.CATEGORY:
            # Get all channels in category
            RETURN AWAIT channel_resolver.get_channels_in_category(
                workspace_id=schedule.workspace_id,
                category_id=schedule.category_id
            )

        ScheduleScope.WORKSPACE:
            # Get all text channels in workspace
            RETURN AWAIT channel_resolver.get_all_text_channels(
                workspace_id=schedule.workspace_id,
                exclude_muted=TRUE
            )

        _:
            RAISE ChannelResolutionError(f"Unknown scope: {schedule.scope}")
```

## 5. Delivery

```pseudocode
ASYNC FUNCTION deliver_to_destinations(
    summary: Summary,
    destinations: List<DeliveryDestination>
) -> List<DeliveryResult>:
    """Deliver summary to all configured destinations."""

    results = []

    FOR dest IN destinations:
        TRY:
            result = AWAIT delivery_service.deliver(
                summary=summary,
                destination=dest
            )
            results.append(result)
        CATCH DeliveryError as e:
            LOG.error(f"Delivery to {dest.type}:{dest.target} failed: {e}")
            results.append(DeliveryResult(
                destination=dest,
                success=FALSE,
                error=str(e)
            ))

    RETURN results


SERVICE DeliveryService:
    DEPENDENCIES:
        adapters: Dict<DestinationType, DeliveryAdapter>

    ASYNC FUNCTION deliver(
        summary: Summary,
        destination: DeliveryDestination
    ) -> DeliveryResult:
        """Deliver summary to a single destination."""

        adapter = adapters.get(destination.type)
        IF adapter IS NULL:
            RAISE DeliveryError(f"No adapter for {destination.type}")

        RETURN AWAIT adapter.deliver(
            summary=summary,
            target=destination.target,
            options=destination.options
        )
```

## 6. Failure Handling

```pseudocode
ASYNC FUNCTION record_success(schedule: Schedule, summary_id: UUID):
    """Record successful execution."""

    schedule.record_success()
    AWAIT schedule_repo.save(schedule)

    LOG.info(f"Schedule {schedule.id} executed successfully, next run: {schedule.next_run_at}")


ASYNC FUNCTION record_failure(schedule: Schedule, error: String):
    """Record failed execution."""

    schedule.record_failure()
    AWAIT schedule_repo.save(schedule)

    IF NOT schedule.enabled:
        LOG.warning(f"Schedule {schedule.id} disabled after {schedule.max_failures} failures")
        AWAIT event_bus.publish(ScheduleDisabled(
            schedule_id=schedule.id,
            reason=f"Max failures exceeded: {error}"
        ))
    ELSE:
        LOG.warning(f"Schedule {schedule.id} failed ({schedule.failure_count}/{schedule.max_failures}): {error}")


ASYNC FUNCTION record_skip(schedule: Schedule, reason: String):
    """Record skipped execution (not a failure)."""

    # Update next_run without counting as failure
    schedule.calculate_next_run()
    AWAIT schedule_repo.save(schedule)

    LOG.info(f"Schedule {schedule.id} skipped: {reason}")
```

## 7. Stale Detection

```pseudocode
ASYNC FUNCTION detect_stale_executions():
    """Detect and recover from stale executions."""

    FOR schedule_id IN active_executions:
        start_time = execution_start_times.get(schedule_id)
        IF start_time AND (NOW() - start_time).seconds > stale_threshold:
            LOG.warning(f"Stale execution detected: {schedule_id}")
            active_executions.remove(schedule_id)

            # Mark for retry on next tick
            schedule = AWAIT schedule_repo.get_by_id(schedule_id)
            IF schedule:
                schedule.next_run_at = NOW()
                AWAIT schedule_repo.save(schedule)
```

## 8. Manual Execution

```pseudocode
ASYNC FUNCTION execute_now(schedule_id: UUID, user_id: UUID) -> ExecutionResult:
    """Manually trigger a schedule execution."""

    schedule = AWAIT schedule_repo.get_by_id(schedule_id)
    IF schedule IS NULL:
        RAISE ScheduleNotFoundError(schedule_id)

    # Override priority for manual execution
    original_trigger = "MANUAL"

    LOG.info(f"Manual execution of schedule {schedule_id} by user {user_id}")

    # Execute immediately (bypass semaphore for manual)
    result = AWAIT execute(schedule)

    RETURN result
```

---

*Next: `05-auth-service.md`*
