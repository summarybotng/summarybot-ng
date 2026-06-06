# Pseudocode: Delivery Adapters

**SPARC Phase**: Pseudocode
**Module**: `v3/src/adapters/delivery/`

---

## 1. Adapter Interface

```pseudocode
ABSTRACT CLASS DeliveryAdapter:
    """Base class for all delivery adapters."""

    @property
    @abstractmethod
    FUNCTION destination_type() -> DestinationType

    @abstractmethod
    ASYNC FUNCTION deliver(
        summary: Summary,
        target: String,
        options: DeliveryOptions
    ) -> DeliveryResult

    @abstractmethod
    ASYNC FUNCTION validate_target(target: String) -> ValidationResult

    FUNCTION format_summary(summary: Summary, format: OutputFormat) -> String:
        """Format summary for delivery."""
        MATCH format:
            OutputFormat.MARKDOWN:
                RETURN format_as_markdown(summary)
            OutputFormat.HTML:
                RETURN format_as_html(summary)
            OutputFormat.PLAIN:
                RETURN format_as_plain_text(summary)
            OutputFormat.EMBED:
                RETURN format_as_embed_json(summary)


DATACLASS DeliveryResult:
    destination_type: DestinationType
    target: String
    success: Boolean
    delivered_at: DateTime
    message_id: Optional<String>  # Platform-specific message ID
    error: Optional<String>
    metadata: Dict<String, Any>
```

## 2. Discord Delivery

```pseudocode
CLASS DiscordDeliveryAdapter(DeliveryAdapter):
    """Deliver summaries to Discord channels."""

    PROPERTIES:
        bot_token: String
        http_client: AsyncHTTPClient
        rate_limiter: RateLimiter

    CONST:
        BASE_URL = "https://discord.com/api/v10"
        MAX_EMBED_LENGTH = 4096
        MAX_FIELD_LENGTH = 1024

    destination_type = DestinationType.DISCORD_CHANNEL


    ASYNC FUNCTION deliver(
        summary: Summary,
        target: String,  # channel_id
        options: DeliveryOptions
    ) -> DeliveryResult:
        """Deliver summary as Discord embed."""

        # Build embed(s)
        embeds = build_embeds(summary, options)

        # Send via Discord API
        TRY:
            AWAIT rate_limiter.acquire("discord")

            response = AWAIT http_client.post(
                f"{BASE_URL}/channels/{target}/messages",
                headers={
                    "Authorization": f"Bot {bot_token}",
                    "Content-Type": "application/json"
                },
                json={"embeds": embeds}
            )

            IF response.status_code == 200:
                data = response.json()
                RETURN DeliveryResult(
                    destination_type=destination_type,
                    target=target,
                    success=TRUE,
                    delivered_at=NOW(),
                    message_id=data["id"],
                    metadata={"channel_id": target}
                )
            ELIF response.status_code == 429:
                retry_after = response.json().get("retry_after", 5)
                RAISE RateLimitError(retry_after=retry_after)
            ELSE:
                RETURN DeliveryResult(
                    destination_type=destination_type,
                    target=target,
                    success=FALSE,
                    delivered_at=NOW(),
                    error=f"Discord API error: {response.status_code}"
                )

        CATCH HTTPError as e:
            RETURN DeliveryResult(
                destination_type=destination_type,
                target=target,
                success=FALSE,
                delivered_at=NOW(),
                error=str(e)
            )


    FUNCTION build_embeds(summary: Summary, options: DeliveryOptions) -> List<Dict>:
        """Build Discord embed objects."""

        embeds = []

        # Main summary embed
        main_embed = {
            "title": f"📋 Summary: {format_date_range(summary.start_time, summary.end_time)}",
            "description": truncate(summary.content, MAX_EMBED_LENGTH),
            "color": 0x5865F2,  # Discord blurple
            "timestamp": summary.created_at.isoformat(),
            "footer": {
                "text": f"{summary.message_count} messages analyzed"
            }
        }

        # Add key points as fields
        IF summary.key_points.length > 0:
            main_embed["fields"] = []
            FOR i, point IN enumerate(summary.key_points[:5]):  # Max 5
                main_embed["fields"].append({
                    "name": f"Key Point {i+1}",
                    "value": truncate(point, MAX_FIELD_LENGTH),
                    "inline": FALSE
                })

        embeds.append(main_embed)

        # Action items in separate embed if present
        IF summary.action_items.length > 0 AND options.include_actions:
            action_embed = build_action_items_embed(summary.action_items)
            embeds.append(action_embed)

        RETURN embeds


    ASYNC FUNCTION validate_target(target: String) -> ValidationResult:
        """Validate Discord channel exists and bot has access."""

        TRY:
            response = AWAIT http_client.get(
                f"{BASE_URL}/channels/{target}",
                headers={"Authorization": f"Bot {bot_token}"}
            )

            IF response.status_code == 200:
                channel = response.json()
                RETURN ValidationResult(
                    valid=TRUE,
                    name=channel.get("name"),
                    metadata={"type": channel.get("type")}
                )
            ELIF response.status_code == 404:
                RETURN ValidationResult(valid=FALSE, error="Channel not found")
            ELIF response.status_code == 403:
                RETURN ValidationResult(valid=FALSE, error="Bot lacks access to channel")
            ELSE:
                RETURN ValidationResult(valid=FALSE, error=f"Unexpected status: {response.status_code}")

        CATCH HTTPError as e:
            RETURN ValidationResult(valid=FALSE, error=str(e))
```

## 3. Email Delivery

```pseudocode
CLASS EmailDeliveryAdapter(DeliveryAdapter):
    """Deliver summaries via email."""

    PROPERTIES:
        smtp_client: SMTPClient
        from_address: String
        template_engine: TemplateEngine

    destination_type = DestinationType.EMAIL


    ASYNC FUNCTION deliver(
        summary: Summary,
        target: String,  # email address
        options: DeliveryOptions
    ) -> DeliveryResult:
        """Send summary via email."""

        # Validate email format
        IF NOT is_valid_email(target):
            RETURN DeliveryResult(
                destination_type=destination_type,
                target=target,
                success=FALSE,
                delivered_at=NOW(),
                error="Invalid email address"
            )

        # Render email template
        html_body = template_engine.render("summary_email.html", {
            summary: summary,
            options: options,
            unsubscribe_url: generate_unsubscribe_url(target)
        })

        text_body = format_as_plain_text(summary)

        # Build email
        message = EmailMessage(
            from_address=from_address,
            to_address=target,
            subject=f"Summary: {format_date_range(summary.start_time, summary.end_time)}",
            html_body=html_body,
            text_body=text_body,
            headers={
                "List-Unsubscribe": generate_unsubscribe_url(target)
            }
        )

        # Send
        TRY:
            message_id = AWAIT smtp_client.send(message)
            RETURN DeliveryResult(
                destination_type=destination_type,
                target=target,
                success=TRUE,
                delivered_at=NOW(),
                message_id=message_id
            )
        CATCH SMTPError as e:
            RETURN DeliveryResult(
                destination_type=destination_type,
                target=target,
                success=FALSE,
                delivered_at=NOW(),
                error=str(e)
            )


    ASYNC FUNCTION validate_target(target: String) -> ValidationResult:
        IF is_valid_email(target):
            RETURN ValidationResult(valid=TRUE)
        RETURN ValidationResult(valid=FALSE, error="Invalid email format")
```

## 4. Webhook Delivery

```pseudocode
CLASS WebhookDeliveryAdapter(DeliveryAdapter):
    """Deliver summaries to webhook endpoints."""

    PROPERTIES:
        http_client: AsyncHTTPClient
        signing_key: Optional<String>

    destination_type = DestinationType.WEBHOOK


    ASYNC FUNCTION deliver(
        summary: Summary,
        target: String,  # webhook URL
        options: DeliveryOptions
    ) -> DeliveryResult:
        """POST summary to webhook URL."""

        # Build payload
        payload = {
            "event": "summary.generated",
            "timestamp": NOW().isoformat(),
            "data": {
                "summary_id": str(summary.id),
                "workspace_id": str(summary.workspace_id),
                "content": summary.content,
                "key_points": summary.key_points,
                "action_items": [item.to_dict() FOR item IN summary.action_items],
                "message_count": summary.message_count,
                "start_time": summary.start_time.isoformat(),
                "end_time": summary.end_time.isoformat(),
                "cost_usd": float(summary.cost_usd)
            }
        }

        # Sign payload if signing key configured
        headers = {"Content-Type": "application/json"}
        IF signing_key:
            signature = compute_hmac_sha256(json.dumps(payload), signing_key)
            headers["X-Signature-256"] = f"sha256={signature}"

        # Send request
        TRY:
            response = AWAIT http_client.post(
                target,
                headers=headers,
                json=payload,
                timeout=30
            )

            success = response.status_code >= 200 AND response.status_code < 300

            RETURN DeliveryResult(
                destination_type=destination_type,
                target=target,
                success=success,
                delivered_at=NOW(),
                error=NULL IF success ELSE f"HTTP {response.status_code}",
                metadata={"status_code": response.status_code}
            )

        CATCH TimeoutError:
            RETURN DeliveryResult(
                destination_type=destination_type,
                target=target,
                success=FALSE,
                delivered_at=NOW(),
                error="Request timeout"
            )
        CATCH HTTPError as e:
            RETURN DeliveryResult(
                destination_type=destination_type,
                target=target,
                success=FALSE,
                delivered_at=NOW(),
                error=str(e)
            )


    ASYNC FUNCTION validate_target(target: String) -> ValidationResult:
        IF NOT is_valid_url(target):
            RETURN ValidationResult(valid=FALSE, error="Invalid URL")

        IF NOT target.startswith("https://"):
            RETURN ValidationResult(valid=FALSE, error="HTTPS required")

        RETURN ValidationResult(valid=TRUE)
```

## 5. Confluence Delivery

```pseudocode
CLASS ConfluenceDeliveryAdapter(DeliveryAdapter):
    """Publish summaries to Confluence pages."""

    PROPERTIES:
        api_client: ConfluenceAPIClient
        space_key: String

    destination_type = DestinationType.CONFLUENCE


    ASYNC FUNCTION deliver(
        summary: Summary,
        target: String,  # parent page ID or space key
        options: DeliveryOptions
    ) -> DeliveryResult:
        """Create or update Confluence page."""

        # Build page title
        title = f"Summary: {format_date_range(summary.start_time, summary.end_time)}"

        # Convert summary to Confluence storage format
        content = convert_to_confluence_storage(summary)

        # Check if page exists
        existing = AWAIT api_client.find_page_by_title(space_key, title)

        TRY:
            IF existing:
                # Update existing page
                page = AWAIT api_client.update_page(
                    page_id=existing.id,
                    title=title,
                    content=content,
                    version=existing.version + 1
                )
            ELSE:
                # Create new page
                page = AWAIT api_client.create_page(
                    space_key=space_key,
                    parent_id=target IF target != space_key ELSE NULL,
                    title=title,
                    content=content
                )

            RETURN DeliveryResult(
                destination_type=destination_type,
                target=target,
                success=TRUE,
                delivered_at=NOW(),
                message_id=page.id,
                metadata={
                    "page_url": page.url,
                    "space_key": space_key
                }
            )

        CATCH ConfluenceAPIError as e:
            RETURN DeliveryResult(
                destination_type=destination_type,
                target=target,
                success=FALSE,
                delivered_at=NOW(),
                error=str(e)
            )


    FUNCTION convert_to_confluence_storage(summary: Summary) -> String:
        """Convert summary to Confluence storage format (XHTML-like)."""

        parts = []

        # Summary content
        parts.append(f"<p>{escape_html(summary.content)}</p>")

        # Key points
        IF summary.key_points.length > 0:
            parts.append("<h2>Key Points</h2>")
            parts.append("<ul>")
            FOR point IN summary.key_points:
                parts.append(f"<li>{escape_html(point)}</li>")
            parts.append("</ul>")

        # Action items with status macro
        IF summary.action_items.length > 0:
            parts.append("<h2>Action Items</h2>")
            parts.append("<ac:task-list>")
            FOR item IN summary.action_items:
                status = "complete" IF item.completed ELSE "incomplete"
                parts.append(f"""
                    <ac:task>
                        <ac:task-status>{status}</ac:task-status>
                        <ac:task-body>{escape_html(item.content)}</ac:task-body>
                    </ac:task>
                """)
            parts.append("</ac:task-list>")

        # Metadata panel
        parts.append("""
            <ac:structured-macro ac:name="panel">
                <ac:parameter ac:name="title">Metadata</ac:parameter>
                <ac:rich-text-body>
                    <p>
                        <strong>Messages:</strong> {summary.message_count}<br/>
                        <strong>Period:</strong> {summary.start_time} to {summary.end_time}<br/>
                        <strong>Generated:</strong> {summary.created_at}
                    </p>
                </ac:rich-text-body>
            </ac:structured-macro>
        """)

        RETURN "".join(parts)


    ASYNC FUNCTION validate_target(target: String) -> ValidationResult:
        TRY:
            # Check if space/page exists
            IF "/" IN target:
                space, page_id = target.split("/", 1)
                page = AWAIT api_client.get_page(page_id)
                RETURN ValidationResult(
                    valid=TRUE,
                    name=page.title,
                    metadata={"type": "page"}
                )
            ELSE:
                space = AWAIT api_client.get_space(target)
                RETURN ValidationResult(
                    valid=TRUE,
                    name=space.name,
                    metadata={"type": "space"}
                )
        CATCH NotFoundError:
            RETURN ValidationResult(valid=FALSE, error="Space or page not found")
```

## 6. Delivery Service (Orchestrator)

```pseudocode
SERVICE DeliveryService:
    """Orchestrates delivery to multiple destinations."""

    PROPERTIES:
        adapters: Dict<DestinationType, DeliveryAdapter>
        retry_config: RetryConfig
        event_bus: EventBus

    ASYNC FUNCTION deliver(
        summary: Summary,
        destinations: List<DeliveryDestination>
    ) -> List<DeliveryResult>:
        """Deliver to all destinations with retries."""

        results = []

        FOR dest IN destinations:
            adapter = adapters.get(dest.type)
            IF adapter IS NULL:
                results.append(DeliveryResult(
                    destination_type=dest.type,
                    target=dest.target,
                    success=FALSE,
                    delivered_at=NOW(),
                    error=f"No adapter for {dest.type}"
                ))
                CONTINUE

            # Deliver with retry
            result = AWAIT deliver_with_retry(adapter, summary, dest)
            results.append(result)

            # Emit event
            AWAIT event_bus.publish(DeliveryCompleted(
                summary_id=summary.id,
                destination_type=dest.type,
                target=dest.target,
                success=result.success,
                error=result.error
            ))

        RETURN results


    ASYNC FUNCTION deliver_with_retry(
        adapter: DeliveryAdapter,
        summary: Summary,
        dest: DeliveryDestination
    ) -> DeliveryResult:
        """Deliver with exponential backoff retry."""

        last_error = NULL

        FOR attempt IN range(retry_config.max_attempts):
            TRY:
                result = AWAIT adapter.deliver(
                    summary=summary,
                    target=dest.target,
                    options=dest.options
                )

                IF result.success:
                    RETURN result

                last_error = result.error

            CATCH RateLimitError as e:
                AWAIT sleep(e.retry_after)
                CONTINUE

            CATCH Exception as e:
                last_error = str(e)

            # Exponential backoff
            IF attempt < retry_config.max_attempts - 1:
                delay = retry_config.base_delay * (2 ** attempt)
                AWAIT sleep(delay)

        RETURN DeliveryResult(
            destination_type=dest.type,
            target=dest.target,
            success=FALSE,
            delivered_at=NOW(),
            error=f"Failed after {retry_config.max_attempts} attempts: {last_error}"
        )
```

---

*Pseudocode phase complete. Next: Architecture phase.*
