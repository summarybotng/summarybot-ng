# ADR-048: Insufficient Content Handling - Skip vs Fail

**Status:** Implemented
**Date:** 2026-04-22
**Related:** ADR-042 (Intelligent Job Retry)

---

## 1. Context

### The Problem

When a scheduled summary task runs but finds insufficient messages to summarize (e.g., 0-2 messages in the period), the system was treating this as a **failure**:

```python
except InsufficientContentError as e:
    task.mark_failed(f"Not enough messages to summarize: {e.message}")
```

This caused several issues:

1. **Failure count incremented** - Each "insufficient content" run counted against `max_failures`
2. **Task auto-disabled** - After 3 runs with no messages, the schedule was disabled
3. **False alarms** - Quiet channels (e.g., weekends, holidays) would disable their schedules
4. **Manual re-enabling required** - Admins had to manually re-enable perfectly valid schedules

### Real-World Scenario

```
Day 1: Daily summary runs, channel has 50 messages → Success
Day 2: Daily summary runs, channel has 30 messages → Success
Day 3 (Saturday): Channel has 2 messages → "Failure" (failure_count = 1)
Day 4 (Sunday): Channel has 0 messages → "Failure" (failure_count = 2)
Day 5 (Monday holiday): Channel has 1 message → "Failure" (failure_count = 3)
→ Schedule DISABLED! Admin must manually re-enable on Tuesday.
```

This is incorrect behavior. A quiet period is not a system failure.

---

## 2. Decision

**Insufficient content should be treated as a SKIP, not a FAILURE.**

### 2.1 New Task Method

Added `mark_run_skipped()` to `ScheduledTask`:

```python
def mark_run_skipped(self) -> None:
    """Mark that a run was skipped (e.g., insufficient content).

    Unlike mark_run_failed(), this does NOT increment failure_count
    and does NOT disable the task. The task simply schedules its next run.
    """
    self.next_run = self.calculate_next_run()
```

### 2.2 Executor Changes

```python
except InsufficientContentError as e:
    # Not enough messages is NOT a failure - it's a skip
    logger.info(f"Skipping task {task.scheduled_task.id}: insufficient content")
    task.mark_skipped()

    return TaskExecutionResult(
        task_id=task.scheduled_task.id,
        success=True,  # Not a failure - just nothing to summarize
        error_message=f"Skipped: {e.user_message}",
        error_details={"skipped": True, "reason": "insufficient_content"},
    )
```

### 2.3 Key Changes

| Aspect | Before | After |
|--------|--------|-------|
| `failure_count` | Incremented | Unchanged |
| `is_active` | May disable after max_failures | Never disabled |
| `next_run` | Retry delay | Normal schedule |
| `success` field | `False` | `True` |
| Error tracking | Logged as error | Logged as info |

---

## 3. Consequences

### Positive
- Schedules survive quiet periods (weekends, holidays, low-activity channels)
- No manual intervention needed to re-enable valid schedules
- Clearer distinction between "nothing to do" vs "system error"
- Better user experience for infrequent channels

### Negative
- None identified

### Edge Cases Handled

1. **Empty channel forever**: Schedule keeps running, skipping each time. This is fine - admin can disable if unwanted.

2. **Channel deleted**: This throws `ChannelAccessError`, which IS a real failure and counts toward max_failures.

3. **API errors**: Claude API failures are still real failures that count toward max_failures.

---

## 4. Files Changed

| File | Change |
|------|--------|
| `src/models/task.py` | Added `mark_run_skipped()` method |
| `src/scheduling/executor.py` | Use `mark_skipped()` for `InsufficientContentError` |

---

## 5. Testing

### Scenario: Quiet Weekend

```python
# Friday: 50 messages
task.execute()  # Success, generates summary

# Saturday: 2 messages (below minimum)
task.execute()  # Skipped, next_run = Sunday
assert task.failure_count == 0
assert task.is_active == True

# Sunday: 0 messages
task.execute()  # Skipped, next_run = Monday
assert task.failure_count == 0
assert task.is_active == True

# Monday: 100 messages
task.execute()  # Success, generates summary
```

### Scenario: Real API Failure

```python
# Claude API is down
task.execute()  # Failure (ClaudeAPIError)
assert task.failure_count == 1

# Still down
task.execute()  # Failure
assert task.failure_count == 2

# Still down
task.execute()  # Failure
assert task.failure_count == 3
assert task.is_active == False  # Correctly disabled
```

---

## 6. Related ADRs

- **ADR-042 (Intelligent Job Retry)**: Defines retry backoff for real failures
- **ADR-045 (Audit Logging)**: Skipped runs can optionally be logged as system events
