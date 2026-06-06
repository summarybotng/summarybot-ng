# Pseudocode: Summary Service

**SPARC Phase**: Pseudocode
**Module**: `v3/src/services/summary_service.py`

---

## 1. Service Interface

```pseudocode
SERVICE SummaryService:
    DEPENDENCIES:
        summary_repo: SummaryRepository
        message_fetcher: MessageFetcher
        llm_generator: SummaryGenerator
        rate_limiter: GlobalRateLimiter  # LEG-001
        event_bus: EventBus
        cost_tracker: CostTracker

    CONFIG:
        min_messages: Integer = 5
        max_messages: Integer = 10000
        default_model: String = "anthropic/claude-sonnet-4"
```

## 2. Generate Summary

```pseudocode
FUNCTION generate(request: GenerateRequest) -> Result<Summary, GenerationError>:

    # Step 1: Validate request
    validation_result = validate_request(request)
    IF validation_result.is_error:
        RETURN Error(validation_result.error)

    # Step 2: Acquire rate limit token (LEG-001)
    TRY:
        AWAIT rate_limiter.acquire(priority=request.priority)
    CATCH CircuitOpenError as e:
        RETURN Error(RateLimitedError(
            retry_after=e.retry_after,
            reason="LLM rate limit circuit open"
        ))

    # Step 3: Fetch messages from platform
    messages = []
    FOR channel_id IN request.channel_ids:
        TRY:
            channel_messages = AWAIT message_fetcher.fetch(
                channel_id=channel_id,
                since=request.since,
                until=request.until
            )
            messages.extend(channel_messages)
        CATCH PlatformError as e:
            LOG.warning(f"Failed to fetch channel {channel_id}: {e}")
            CONTINUE  # Partial success allowed

    # Step 4: Validate message count
    IF messages.length < min_messages:
        RETURN Error(InsufficientMessagesError(
            found=messages.length,
            required=min_messages
        ))

    IF messages.length > max_messages:
        messages = truncate_messages(messages, max_messages)
        LOG.info(f"Truncated to {max_messages} messages")

    # Step 5: Prepare prompt
    prompt = build_prompt(
        messages=messages,
        options=request.options
    )

    # Step 6: Generate via LLM
    TRY:
        generation_result = AWAIT llm_generator.generate(
            prompt=prompt,
            model=request.model OR default_model,
            options=GenerationOptions(
                max_tokens=calculate_max_tokens(request.options.length),
                temperature=0.3
            )
        )
    CATCH RateLimitError as e:
        rate_limiter.record_rate_limit(e.retry_after)
        RETURN Error(RateLimitedError(retry_after=e.retry_after))
    CATCH LLMError as e:
        RETURN Error(GenerationFailedError(reason=str(e)))

    # Step 7: Parse LLM response
    parsed = parse_summary_response(generation_result.content)
    IF parsed.is_error:
        RETURN Error(ParseError(raw=generation_result.content))

    # Step 8: Create domain object
    summary = Summary(
        id=generate_uuid(),
        workspace_id=request.workspace_id,
        channel_ids=request.channel_ids,
        content=parsed.content,
        key_points=parsed.key_points,
        action_items=parsed.action_items,
        participants=extract_participants(messages),
        message_count=messages.length,
        start_time=request.since,
        end_time=request.until,
        generation_options=request.options,
        input_tokens=generation_result.input_tokens,
        output_tokens=generation_result.output_tokens,
        cost_usd=generation_result.cost_usd,
        model_used=generation_result.model,
        status=SummaryStatus.DRAFT
    )

    # Step 9: Persist
    AWAIT summary_repo.save(summary)

    # Step 10: Track cost
    cost_tracker.record(
        workspace_id=request.workspace_id,
        cost_usd=summary.cost_usd,
        tokens=summary.input_tokens + summary.output_tokens
    )

    # Step 11: Emit event
    AWAIT event_bus.publish(SummaryGenerated(
        summary_id=summary.id,
        workspace_id=summary.workspace_id,
        channel_ids=summary.channel_ids,
        generated_at=summary.created_at,
        cost_usd=summary.cost_usd,
        triggered_by=request.trigger_type
    ))

    RETURN Ok(summary)
```

## 3. Prompt Building

```pseudocode
FUNCTION build_prompt(messages: List<Message>, options: SummaryOptions) -> String:

    # Group messages by author
    grouped = group_by(messages, m => m.author_id)

    # Calculate participation stats
    stats = calculate_stats(messages, grouped)

    # Select prompt template based on options
    template = get_template(
        length=options.length,      # brief | detailed | comprehensive
        perspective=options.perspective  # general | developer | executive
    )

    # Format messages for context
    formatted_messages = []
    FOR msg IN messages:
        formatted_messages.append(format_message(msg))

    # Build final prompt
    prompt = template.render(
        messages=formatted_messages,
        stats=stats,
        channel_names=get_channel_names(messages),
        time_range=f"{options.since} to {options.until}",
        instructions=get_perspective_instructions(options.perspective)
    )

    RETURN prompt


FUNCTION get_template(length: String, perspective: String) -> Template:
    # Template selection matrix
    TEMPLATES = {
        ("brief", "general"): BRIEF_GENERAL_TEMPLATE,
        ("brief", "developer"): BRIEF_DEVELOPER_TEMPLATE,
        ("detailed", "general"): DETAILED_GENERAL_TEMPLATE,
        ("detailed", "developer"): DETAILED_DEVELOPER_TEMPLATE,
        ("comprehensive", "general"): COMPREHENSIVE_GENERAL_TEMPLATE,
        # ... etc
    }
    RETURN TEMPLATES.get((length, perspective), DETAILED_GENERAL_TEMPLATE)


FUNCTION calculate_max_tokens(length: String) -> Integer:
    MATCH length:
        "brief" => 1000
        "detailed" => 2500
        "comprehensive" => 4000
        _ => 2500
```

## 4. Response Parsing

```pseudocode
FUNCTION parse_summary_response(raw: String) -> Result<ParsedSummary, ParseError>:

    # Expect structured output with XML-like tags
    TRY:
        summary_text = extract_tag(raw, "summary")
        key_points_raw = extract_tag(raw, "key_points")
        action_items_raw = extract_tag(raw, "action_items")
    CATCH ExtractionError as e:
        # Fallback: treat entire response as summary
        RETURN Ok(ParsedSummary(
            content=raw.trim(),
            key_points=[],
            action_items=[]
        ))

    # Parse key points
    key_points = []
    FOR line IN key_points_raw.split("\n"):
        line = line.strip()
        IF line.starts_with("- ") OR line.starts_with("* "):
            key_points.append(line[2:])
        ELIF line.length > 0:
            key_points.append(line)

    # Parse action items
    action_items = []
    FOR line IN action_items_raw.split("\n"):
        parsed_item = parse_action_item(line)
        IF parsed_item IS NOT NULL:
            action_items.append(parsed_item)

    RETURN Ok(ParsedSummary(
        content=summary_text.trim(),
        key_points=key_points[:20],  # Max 20
        action_items=action_items
    ))


FUNCTION parse_action_item(line: String) -> Optional<ActionItem>:
    # Expected formats:
    # "- [ ] Task description @assignee by 2026-06-10"
    # "- Task description (HIGH)"

    line = line.strip()
    IF line.length == 0:
        RETURN NULL

    # Extract checkbox
    completed = FALSE
    IF line.starts_with("- [x]") OR line.starts_with("- [X]"):
        completed = TRUE
        line = line[5:].strip()
    ELIF line.starts_with("- [ ]"):
        line = line[5:].strip()
    ELIF line.starts_with("- "):
        line = line[2:].strip()
    ELSE:
        RETURN NULL

    # Extract assignee (@mention)
    assignee = NULL
    assignee_match = regex_search(r"@(\w+)", line)
    IF assignee_match:
        assignee = assignee_match.group(1)
        line = line.replace(assignee_match.group(0), "").strip()

    # Extract deadline
    deadline = NULL
    deadline_match = regex_search(r"by (\d{4}-\d{2}-\d{2})", line)
    IF deadline_match:
        deadline = parse_date(deadline_match.group(1))
        line = line.replace(deadline_match.group(0), "").strip()

    # Extract priority
    priority = Priority.MEDIUM
    FOR p IN [Priority.URGENT, Priority.HIGH, Priority.LOW]:
        IF f"({p.name})" IN line.upper():
            priority = p
            line = regex_replace(rf"\({p.name}\)", "", line, flags=IGNORECASE).strip()

    RETURN ActionItem(
        id=generate_uuid(),
        content=line,
        assignee=assignee,
        deadline=deadline,
        priority=priority,
        completed=completed,
        extracted_from=line[:100]
    )
```

## 5. Batch Generation (for Jobs)

```pseudocode
FUNCTION generate_batch(job: GenerationJob) -> BatchResult:
    """Generate summaries for multiple periods (retrospective jobs)."""

    results = BatchResult()
    periods = calculate_periods(job.date_range, job.granularity)

    FOR period IN periods:
        # Check budget
        IF job.max_cost_usd AND results.total_cost >= job.max_cost_usd:
            results.add_skipped(period, reason="budget_exceeded")
            CONTINUE

        # Check if exists (skip_existing mode)
        IF job.skip_existing:
            existing = AWAIT summary_repo.find_by_period(
                workspace_id=job.workspace_id,
                channel_ids=job.channel_ids,
                start_time=period.start,
                end_time=period.end
            )
            IF existing IS NOT NULL:
                results.add_skipped(period, reason="exists")
                CONTINUE

        # Generate
        request = GenerateRequest(
            workspace_id=job.workspace_id,
            channel_ids=job.channel_ids,
            since=period.start,
            until=period.end,
            options=job.summary_options,
            priority=Priority.LOW,  # Jobs yield to manual requests
            trigger_type=TriggerType.SCHEDULED
        )

        result = AWAIT generate(request)

        IF result.is_ok:
            results.add_success(period, result.value)
        ELSE:
            IF result.error IS RateLimitedError:
                # Don't fail entire job, pause and retry
                AWAIT sleep(result.error.retry_after)
                # Retry once
                retry_result = AWAIT generate(request)
                IF retry_result.is_ok:
                    results.add_success(period, retry_result.value)
                ELSE:
                    results.add_failed(period, retry_result.error)
            ELSE:
                results.add_failed(period, result.error)

        # Yield between periods
        AWAIT sleep(0.5)

    RETURN results
```

---

*Next: `03-rate-limiter.md` (LEG-001)*
