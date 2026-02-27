# ADR-023: Handling Invalid JSON Responses from LLM

## Status
Implemented

## Date
2026-02-27

## Context

When generating summaries, Claude is instructed to return structured JSON with nested objects for citations (ADR-004). Occasionally, the model returns syntactically invalid JSON that fails to parse, resulting in "[Unable to parse summary format]" errors.

### Problem Analysis

**Error Example:**
```
JSON parse error: Expecting ',' delimiter: line 9 column 89 (char 657)
```

**Root Cause:** Claude fails to properly escape special characters when embedding Discord message content into JSON string fields.

**Common Failure Patterns:**
1. Unescaped quotes: `"text": "User said "hello" to everyone"`
2. Unescaped newlines: Literal line breaks inside string values
3. Invalid Unicode: Malformed emoji sequences
4. Trailing commas: `{"key": "value",}` (invalid in JSON)
5. Missing commas: `{"a": 1 "b": 2}` (missing comma between properties)

**Current JSON Schema Complexity:**
```json
{
  "summary_text": "...",
  "key_points": [
    {"text": "...", "references": [1,2], "confidence": 0.95}
  ],
  "action_items": [
    {"text": "...", "references": [3], "assignee": "...", "priority": "high"}
  ],
  "participants": [
    {"name": "...", "key_contributions": [{"text": "...", "references": [4]}]}
  ],
  "sources": [...]
}
```

The deeply nested structure (objects in arrays in objects) increases the probability of syntax errors.

### Frequency

Based on production data, approximately 2-5% of summaries fail JSON parsing. This is separate from truncation errors (addressed in ADR-022).

## Options Considered

### Option 1: JSON Repair Library

**Approach:** Use a JSON repair library to automatically fix common syntax errors before parsing.

**Libraries:**
- `json-repair` (Python): Fixes quotes, commas, truncation
- `demjson3`: Lenient JSON parser
- Custom regex-based repair

**Implementation:**
```python
from json_repair import repair_json

def parse_with_repair(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        repaired = repair_json(content)
        return json.loads(repaired)
```

**Pros:**
- Simple to implement
- No additional API calls
- Handles multiple error types
- Fast (milliseconds)

**Cons:**
- May incorrectly "repair" valid content
- Can't fix semantic errors (wrong structure)
- New dependency
- Repair heuristics may not match Claude's intent

**Risk:** Low - repairs are deterministic and logged

### Option 2: Retry with Explicit JSON Reminder

**Approach:** On parse failure, retry the API call with an additional instruction emphasizing valid JSON.

**Implementation:**
```python
if json_parse_error:
    retry_prompt = original_prompt + "\n\nCRITICAL: Your previous response had invalid JSON. Ensure all quotes are escaped and the response is valid JSON."
    response = await claude_client.create_summary(retry_prompt, ...)
```

**Pros:**
- Uses Claude's intelligence to fix its own error
- May produce better overall output
- No new dependencies

**Cons:**
- Additional API cost (~$0.01-0.05 per retry)
- Additional latency (3-10 seconds)
- No guarantee of success
- May change summary content, not just fix syntax

**Risk:** Medium - retry may still fail or produce different content

### Option 3: Claude Structured Outputs (Tool Use)

**Approach:** Use Claude's tool_use feature to force valid JSON output at the API level.

**Implementation:**
```python
tools = [{
    "name": "submit_summary",
    "description": "Submit the structured summary",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary_text": {"type": "string"},
            "key_points": {"type": "array", "items": {...}},
            ...
        },
        "required": ["summary_text", "key_points"]
    }
}]

response = await client.messages.create(
    model="claude-3-sonnet",
    tools=tools,
    tool_choice={"type": "tool", "name": "submit_summary"},
    ...
)
```

**Pros:**
- Guarantees valid JSON structure
- Schema validation at API level
- No parsing errors possible
- Industry best practice for structured output

**Cons:**
- Requires significant refactor of prompt system
- Tool use has different token economics
- May constrain Claude's natural language in summaries
- Schema must be defined in code, not markdown prompts

**Risk:** Medium - significant refactor required

### Option 4: Simplify JSON Schema

**Approach:** Reduce nesting depth and complexity of the required JSON structure.

**Current (3 levels deep):**
```json
{"participants": [{"key_contributions": [{"text": "...", "references": [...]}]}]}
```

**Simplified (2 levels deep):**
```json
{"participants": [{"name": "...", "contributions": "...", "refs": [1,2]}]}
```

**Pros:**
- Fewer places for syntax errors
- Easier for Claude to generate correctly
- Simpler parsing code

**Cons:**
- Loss of citation granularity (ADR-004 feature)
- May reduce summary quality
- Requires prompt and parser changes

**Risk:** Low-Medium - trades features for reliability

### Option 5: Hybrid Approach (Recommended)

**Approach:** Combine multiple strategies in a fallback chain:

1. **First:** Try normal JSON parsing
2. **Second:** Apply JSON repair library
3. **Third:** Retry API call with JSON reminder (if repair fails)
4. **Fallback:** Use freeform parser (existing behavior)

**Implementation:**
```python
MAX_JSON_RETRIES = 1

async def parse_response(content: str, metadata: dict) -> ParsedSummary:
    # Step 1: Try normal parse
    try:
        return json.loads(extract_json(content))
    except JSONDecodeError as e:
        metadata["warnings"].append(f"JSON parse error: {e}")

    # Step 2: Try repair
    try:
        repaired = repair_json(extract_json(content))
        metadata["json_repaired"] = True
        return json.loads(repaired)
    except Exception as e:
        metadata["warnings"].append(f"JSON repair failed: {e}")

    # Step 3: Retry API (only if not already retried)
    if not metadata.get("json_retry_attempted"):
        metadata["json_retry_attempted"] = True
        return None  # Signal to retry

    # Step 4: Freeform fallback
    return parse_freeform(content)
```

**Pros:**
- Multiple layers of recovery
- Minimizes API retries (costly)
- Graceful degradation
- Logged for monitoring

**Cons:**
- More complex code path
- Multiple fallback behaviors to test
- New dependency (json-repair)

**Risk:** Low - each layer is independent and logged

## Decision

**Recommended: Option 5 (Hybrid Approach)**

The hybrid approach provides defense in depth:

| Layer | Cost | Latency | Success Rate |
|-------|------|---------|--------------|
| JSON Repair | Free | <10ms | ~80% of errors |
| API Retry | ~$0.02 | 3-5s | ~90% of remaining |
| Freeform | Free | <10ms | 100% (degraded) |

### Implementation Priority

1. **Phase 1:** Add `json-repair` library with repair-before-parse
2. **Phase 2:** Add retry-on-parse-error (similar to ADR-022 truncation retry)
3. **Phase 3 (Future):** Evaluate migration to tool_use for guaranteed structure

### Parsing Difficulty Tracking

Store parsing metadata on each summary to enable monitoring, debugging, and identifying problematic content patterns.

**New metadata field: `parsing_recovery`**

```json
{
  "metadata": {
    "parsing_recovery": {
      "had_errors": true,
      "initial_error": "Expecting ',' delimiter: line 9 column 89",
      "recovery_steps": ["json_repair", "api_retry"],
      "successful_step": "json_repair",
      "total_attempts": 2,
      "recovery_latency_ms": 45
    }
  }
}
```

**Field Definitions:**

| Field | Type | Description |
|-------|------|-------------|
| `had_errors` | boolean | Whether any parsing errors occurred |
| `initial_error` | string | First error message encountered |
| `recovery_steps` | string[] | Steps attempted: `json_repair`, `api_retry`, `freeform_fallback` |
| `successful_step` | string | Which step ultimately succeeded (or `none` if all failed) |
| `total_attempts` | int | Number of parse attempts made |
| `recovery_latency_ms` | int | Time spent in recovery (excludes initial parse) |

**Example Values:**

Clean parse (no issues):
```json
{"parsing_recovery": null}
```

Repaired successfully:
```json
{
  "parsing_recovery": {
    "had_errors": true,
    "initial_error": "Expecting ',' delimiter: line 12 column 45",
    "recovery_steps": ["json_repair"],
    "successful_step": "json_repair",
    "total_attempts": 2,
    "recovery_latency_ms": 8
  }
}
```

Required API retry:
```json
{
  "parsing_recovery": {
    "had_errors": true,
    "initial_error": "Unterminated string starting at: line 5",
    "recovery_steps": ["json_repair", "api_retry"],
    "successful_step": "api_retry",
    "total_attempts": 3,
    "recovery_latency_ms": 4250
  }
}
```

Fell back to freeform:
```json
{
  "parsing_recovery": {
    "had_errors": true,
    "initial_error": "Invalid control character at: line 3",
    "recovery_steps": ["json_repair", "api_retry", "freeform_fallback"],
    "successful_step": "freeform_fallback",
    "total_attempts": 4,
    "recovery_latency_ms": 5102
  }
}
```

**Queryable Patterns:**

```sql
-- Find all summaries that required recovery
SELECT * FROM stored_summaries
WHERE metadata->'parsing_recovery'->>'had_errors' = 'true';

-- Count by recovery step
SELECT
  metadata->'parsing_recovery'->>'successful_step' as recovery_method,
  COUNT(*)
FROM stored_summaries
WHERE metadata->'parsing_recovery' IS NOT NULL
GROUP BY 1;

-- Find summaries that fell back to freeform (degraded quality)
SELECT * FROM stored_summaries
WHERE metadata->'parsing_recovery'->>'successful_step' = 'freeform_fallback';

-- Average recovery latency by step
SELECT
  metadata->'parsing_recovery'->>'successful_step' as method,
  AVG((metadata->'parsing_recovery'->>'recovery_latency_ms')::int) as avg_latency_ms
FROM stored_summaries
WHERE metadata->'parsing_recovery'->>'had_errors' = 'true'
GROUP BY 1;
```

## Consequences

### Positive
- Significantly reduces "[Unable to parse summary format]" errors
- Multiple recovery mechanisms
- Maintains citation features (ADR-004)
- Logged for monitoring and debugging
- `parsing_recovery` metadata enables:
  - Identifying problematic content patterns
  - Measuring recovery success rates
  - Tracking degraded summaries (freeform fallback)
  - Cost analysis of API retries

### Negative
- New dependency (`json-repair`)
- More complex parsing code path
- Potential for API retry costs (estimated <$5/month based on error rate)

### Neutral
- Freeform fallback behavior unchanged
- No changes to prompt templates

## Implementation

### Files to Change
- `src/summarization/response_parser.py` - Add repair step, retry signal, and `parsing_recovery` tracking
- `src/summarization/engine.py` - Handle retry signal for JSON errors, populate recovery metadata
- `src/models/summary.py` - Add `ParsingRecovery` dataclass (optional, can use dict)
- `requirements.txt` - Add `json-repair` dependency

### Updated Implementation with Tracking

```python
import time
from json_repair import repair_json
from dataclasses import dataclass, asdict
from typing import Optional, List

@dataclass
class ParsingRecovery:
    """Tracks parsing difficulty for a summary."""
    had_errors: bool = False
    initial_error: Optional[str] = None
    recovery_steps: List[str] = None
    successful_step: Optional[str] = None
    total_attempts: int = 1
    recovery_latency_ms: int = 0

    def __post_init__(self):
        if self.recovery_steps is None:
            self.recovery_steps = []

    def to_dict(self) -> dict:
        return asdict(self) if self.had_errors else None


async def parse_response_with_tracking(content: str, metadata: dict) -> ParsedSummary:
    recovery = ParsingRecovery()
    recovery_start = None

    # Step 1: Try normal parse
    json_str = extract_json(content)
    try:
        data = json.loads(json_str)
        metadata["parsing_recovery"] = recovery.to_dict()  # None for clean parse
        return build_summary(data)
    except JSONDecodeError as e:
        recovery.had_errors = True
        recovery.initial_error = str(e)
        recovery.total_attempts = 1
        recovery_start = time.monotonic()

    # Step 2: Try repair
    recovery.recovery_steps.append("json_repair")
    recovery.total_attempts += 1
    try:
        repaired = repair_json(json_str)
        data = json.loads(repaired)
        recovery.successful_step = "json_repair"
        recovery.recovery_latency_ms = int((time.monotonic() - recovery_start) * 1000)
        metadata["parsing_recovery"] = recovery.to_dict()
        metadata["json_repaired"] = True
        return build_summary(data)
    except Exception as e:
        metadata["warnings"].append(f"JSON repair failed: {e}")

    # Step 3: Signal retry needed (engine handles actual retry)
    if not metadata.get("json_retry_attempted"):
        recovery.recovery_steps.append("api_retry")
        recovery.total_attempts += 1
        metadata["parsing_recovery_pending"] = recovery  # Pass to engine
        return None  # Signal retry

    # Step 4: Freeform fallback
    recovery.recovery_steps.append("freeform_fallback")
    recovery.successful_step = "freeform_fallback"
    recovery.total_attempts += 1
    recovery.recovery_latency_ms = int((time.monotonic() - recovery_start) * 1000)
    metadata["parsing_recovery"] = recovery.to_dict()
    return parse_freeform(content)
```

### Monitoring

Log messages to watch for:
```
WARNING - JSON parse error: {error}. Attempting repair...
INFO - JSON repair successful
WARNING - JSON repair failed. Retrying API call...
INFO - JSON retry successful
WARNING - JSON retry failed. Falling back to freeform parser.
```

### Metrics to Track
- `json_parse_errors_total` - Count of initial parse failures
- `json_repair_success_total` - Count of successful repairs
- `json_retry_success_total` - Count of successful API retries
- `json_fallback_freeform_total` - Count of freeform fallbacks

## Alternatives Not Chosen

### Pre-escape Message Content
**Rejected:** Would require escaping before sending to Claude, then un-escaping in output. Complex and error-prone.

### Switch to Markdown Output
**Rejected:** Would lose structured citation data (ADR-004). Markdown parsing is also error-prone.

### Always Use Tool Use
**Rejected:** Significant refactor for uncertain benefit. Consider for Phase 3.

## References

- ADR-004: Grounded Summary References (citation requirements)
- ADR-022: Auto-Retry Truncated LLM Responses
- [json-repair library](https://github.com/mangiucugna/json_repair)
- [Claude Tool Use Documentation](https://docs.anthropic.com/claude/docs/tool-use)
