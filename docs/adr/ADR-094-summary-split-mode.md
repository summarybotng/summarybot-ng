# ADR-094: Summary Split Mode for Multi-Channel Summaries

## Status
Accepted

## Context
When creating summaries for multiple channels (via category or server scope), all messages are currently consolidated into a single unified summary. Users want the option to generate separate summaries instead, as single-channel summaries retain better focus and are easier to consume.

## Decision
Add a "Split Mode" option to the summary wizard that controls how multi-channel summaries are generated:

### Split Modes
1. **By Channel** (default) - Generate individual summary per channel
2. **By Category** - Generate one summary per Discord category (server scope only)
3. **Consolidated** - Single summary covering all selected channels (legacy behavior)

### UI Changes
- New dropdown in WhatStep.tsx below scope selector
- Only shown when scope is "category" or "guild" (multiple channels)
- Default to "By Channel" for maximum focus retention

### Backend Changes
- `summaries.py`: When `split_mode != "consolidated"`, create multiple jobs
- Each job generates one summary for its subset of channels
- Jobs linked via `batch_id` for progress tracking

### Job Tracking
- Show batch progress: "Generating 5 of 12 summaries..."
- All summaries in batch share same time range and options
- Individual jobs can succeed/fail independently

## Consequences

### Positive
- Single-channel summaries retain focus on specific topics
- Users can choose granularity that fits their needs
- Better for archival and searchability

### Negative
- More API calls for split summaries (higher cost)
- Longer total generation time for large batches
- UI complexity increase

## Implementation

### Phase 1: Core Split Mode
1. Add `splitMode` to WizardState
2. Update WhatStep.tsx with split mode selector
3. Backend generates multiple jobs for split modes

### Phase 2: Batch Progress
1. Add `batch_id` to job tracking
2. Update Jobs UI to show batch progress
3. Add batch-level controls (cancel all, retry failed)
