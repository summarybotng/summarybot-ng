"""
Email Delivery Service for ADR-030: Email Delivery Destination.

This module handles sending summaries via email using aiosmtplib.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Optional, Dict, Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..models.summary import SummaryResult
from src.utils.time import utc_now_naive

logger = logging.getLogger(__name__)

# Email validation regex (simplified but effective)
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# Rate limiting
MAX_RECIPIENTS_PER_DESTINATION = 10
MAX_EMAILS_PER_HOUR = 50


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

    def is_configured(self) -> bool:
        """Check if SMTP is properly configured."""
        return bool(
            self.enabled
            and self.host
            and self.from_address
        )


@dataclass
class EmailDeliveryResult:
    """Result of email delivery attempt."""
    success: bool
    recipients_sent: List[str] = field(default_factory=list)
    recipients_failed: List[str] = field(default_factory=list)
    error: Optional[str] = None
    message_id: Optional[str] = None


@dataclass
class EmailContext:
    """Context for rendering email templates."""
    guild_name: str = ""
    channel_names: List[str] = field(default_factory=list)
    category_name: Optional[str] = None
    is_server_wide: bool = False
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    message_count: int = 0
    participant_count: int = 0
    schedule_name: Optional[str] = None


class EmailDeliveryService:
    """Handles email delivery of summaries.

    ADR-030: Email Delivery Destination.
    """

    def __init__(self, config: SMTPConfig):
        """Initialize email service with SMTP config.

        Args:
            config: SMTP configuration
        """
        self.config = config
        self._template_env: Optional[Environment] = None
        self._send_count: Dict[str, int] = {}  # guild_id -> count this hour
        self._send_count_reset: Optional[datetime] = None

    def is_configured(self) -> bool:
        """Check if email delivery is configured."""
        return self.config.is_configured()

    def _get_template_env(self) -> Environment:
        """Get or create Jinja2 template environment."""
        if self._template_env is None:
            # Look for templates in src/templates/email/
            template_dir = Path(__file__).parent.parent / "templates" / "email"
            if not template_dir.exists():
                template_dir.mkdir(parents=True, exist_ok=True)

            self._template_env = Environment(
                loader=FileSystemLoader(str(template_dir)),
                autoescape=select_autoescape(["html", "xml"]),
            )
        return self._template_env

    def validate_email(self, email: str) -> bool:
        """Validate a single email address.

        Args:
            email: Email address to validate

        Returns:
            True if valid, False otherwise
        """
        if not email or not isinstance(email, str):
            return False
        return bool(EMAIL_REGEX.match(email.strip()))

    def parse_recipients(self, target: str) -> List[str]:
        """Parse comma-separated recipient list.

        Args:
            target: Comma-separated email addresses

        Returns:
            List of valid email addresses
        """
        if not target:
            return []

        recipients = []
        for email in target.split(","):
            email = email.strip()
            if self.validate_email(email):
                recipients.append(email)
            else:
                logger.warning(f"Invalid email address skipped: {email}")

        return recipients[:MAX_RECIPIENTS_PER_DESTINATION]

    def _check_rate_limit(self, guild_id: str) -> bool:
        """Check if we're within rate limits.

        Args:
            guild_id: Guild ID to check

        Returns:
            True if within limits, False if rate limited
        """
        now = utc_now_naive()

        # Reset counter every hour
        if self._send_count_reset is None or (now - self._send_count_reset).total_seconds() > 3600:
            self._send_count = {}
            self._send_count_reset = now

        current_count = self._send_count.get(guild_id, 0)
        return current_count < MAX_EMAILS_PER_HOUR

    def _increment_send_count(self, guild_id: str, count: int = 1) -> None:
        """Increment send count for rate limiting.

        Args:
            guild_id: Guild ID
            count: Number to increment by
        """
        current = self._send_count.get(guild_id, 0)
        self._send_count[guild_id] = current + count

    def render_html(
        self,
        summary: SummaryResult,
        context: EmailContext,
    ) -> str:
        """Render summary as HTML email.

        Args:
            summary: Summary to render
            context: Email context

        Returns:
            HTML string
        """
        try:
            env = self._get_template_env()
            template = env.get_template("summary.html")
            return template.render(
                summary=summary,
                context=context,
                now=utc_now_naive(),
            )
        except Exception as e:
            logger.warning(f"Failed to render HTML template, using fallback: {e}")
            return self._render_html_fallback(summary, context)

    def _render_html_fallback(
        self,
        summary: SummaryResult,
        context: EmailContext,
    ) -> str:
        """Fallback HTML rendering if template fails."""
        # Build scope string
        if context.is_server_wide:
            scope = f"Server-wide Summary"
        elif context.category_name:
            scope = f"Category: {context.category_name}"
        elif context.channel_names:
            scope = ", ".join(context.channel_names)
        else:
            scope = "Summary"

        # Build date range
        date_range = ""
        if context.start_time and context.end_time:
            date_range = f"{context.start_time.strftime('%b %d, %Y %I:%M %p')} - {context.end_time.strftime('%b %d, %Y %I:%M %p')} UTC"

        # Build key points
        key_points_html = ""
        if summary.key_points:
            points = "\n".join(f"<li>{self._escape_html(p)}</li>" for p in summary.key_points[:10])
            key_points_html = f"<h2>Key Points</h2><ul>{points}</ul>"

        # Build action items
        action_items_html = ""
        if summary.action_items:
            items = []
            for item in summary.action_items[:10]:
                if hasattr(item, 'description'):
                    items.append(f"<li>{self._escape_html(item.description)}</li>")
                else:
                    items.append(f"<li>{self._escape_html(str(item))}</li>")
            action_items_html = f"<h2>Action Items</h2><ul>{''.join(items)}</ul>"

        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self._escape_html(scope)}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #5865F2; border-bottom: 2px solid #5865F2; padding-bottom: 10px; }}
        h2 {{ color: #4752C4; margin-top: 24px; }}
        .meta {{ color: #666; font-size: 14px; margin-bottom: 20px; }}
        ul {{ padding-left: 20px; }}
        li {{ margin-bottom: 8px; }}
        .summary-text {{ background: #f5f5f5; padding: 16px; border-radius: 8px; margin: 16px 0; }}
        .footer {{ margin-top: 32px; padding-top: 16px; border-top: 1px solid #ddd; font-size: 12px; color: #666; }}
    </style>
</head>
<body>
    <h1>{self._escape_html(scope)}</h1>
    <div class="meta">
        {f'<p>{date_range}</p>' if date_range else ''}
        <p>{context.message_count} messages from {context.participant_count} participants</p>
    </div>

    {f'<div class="summary-text">{self._escape_html(summary.summary_text)}</div>' if summary.summary_text else ''}

    {key_points_html}
    {action_items_html}

    <div class="footer">
        <p>Generated by SummaryBot at {utc_now_naive().strftime('%Y-%m-%d %H:%M UTC')}</p>
    </div>
</body>
</html>
"""

    def render_plain_text(
        self,
        summary: SummaryResult,
        context: EmailContext,
    ) -> str:
        """Render summary as plain text email.

        Args:
            summary: Summary to render
            context: Email context

        Returns:
            Plain text string
        """
        try:
            env = self._get_template_env()
            template = env.get_template("summary.txt")
            return template.render(
                summary=summary,
                context=context,
                now=utc_now_naive(),
            )
        except Exception as e:
            logger.warning(f"Failed to render text template, using fallback: {e}")
            return self._render_text_fallback(summary, context)

    def _render_text_fallback(
        self,
        summary: SummaryResult,
        context: EmailContext,
    ) -> str:
        """Fallback plain text rendering if template fails."""
        lines = []

        # Header
        if context.is_server_wide:
            lines.append("SERVER-WIDE SUMMARY")
        elif context.category_name:
            lines.append(f"CATEGORY: {context.category_name}")
        elif context.channel_names:
            lines.append(f"CHANNELS: {', '.join(context.channel_names)}")
        else:
            lines.append("SUMMARY")

        lines.append("=" * 50)
        lines.append("")

        # Date range
        if context.start_time and context.end_time:
            lines.append(f"Period: {context.start_time.strftime('%b %d, %Y %I:%M %p')} - {context.end_time.strftime('%b %d, %Y %I:%M %p')} UTC")

        lines.append(f"Messages: {context.message_count} | Participants: {context.participant_count}")
        lines.append("")

        # Summary text
        if summary.summary_text:
            lines.append("OVERVIEW")
            lines.append("-" * 30)
            lines.append(summary.summary_text)
            lines.append("")

        # Key points
        if summary.key_points:
            lines.append("KEY POINTS")
            lines.append("-" * 30)
            for i, point in enumerate(summary.key_points[:10], 1):
                lines.append(f"  {i}. {point}")
            lines.append("")

        # Action items
        if summary.action_items:
            lines.append("ACTION ITEMS")
            lines.append("-" * 30)
            for i, item in enumerate(summary.action_items[:10], 1):
                if hasattr(item, 'description'):
                    lines.append(f"  [ ] {item.description}")
                else:
                    lines.append(f"  [ ] {item}")
            lines.append("")

        # Footer
        lines.append("-" * 50)
        lines.append(f"Generated by SummaryBot at {utc_now_naive().strftime('%Y-%m-%d %H:%M UTC')}")

        return "\n".join(lines)

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        if not text:
            return ""
        return (
            text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )

    def build_subject(
        self,
        summary: SummaryResult,
        context: EmailContext,
        custom_subject: Optional[str] = None,
    ) -> str:
        """Build email subject line.

        Args:
            summary: Summary result
            context: Email context
            custom_subject: Optional custom subject template

        Returns:
            Subject line string
        """
        if custom_subject:
            return custom_subject

        # Build scope
        if context.is_server_wide:
            scope = "Server Summary"
        elif context.category_name:
            scope = f"{context.category_name} Summary"
        elif context.channel_names:
            if len(context.channel_names) == 1:
                scope = f"#{context.channel_names[0]} Summary"
            else:
                scope = f"{len(context.channel_names)} Channels Summary"
        else:
            scope = "Summary"

        # Add date
        if context.end_time:
            date_str = context.end_time.strftime("%b %d")
            return f"[SummaryBot] {scope} - {date_str}"

        return f"[SummaryBot] {scope}"

    async def send_summary(
        self,
        summary: SummaryResult,
        recipients: List[str],
        context: Optional[EmailContext] = None,
        subject: Optional[str] = None,
        guild_id: Optional[str] = None,
    ) -> EmailDeliveryResult:
        """Send summary to email recipients.

        Args:
            summary: Summary to send
            recipients: List of email addresses
            context: Email rendering context
            subject: Optional custom subject
            guild_id: Guild ID for rate limiting

        Returns:
            EmailDeliveryResult with delivery status
        """
        if not self.is_configured():
            return EmailDeliveryResult(
                success=False,
                error="SMTP not configured",
            )

        if not recipients:
            return EmailDeliveryResult(
                success=False,
                error="No valid recipients",
            )

        # Check rate limit
        if guild_id and not self._check_rate_limit(guild_id):
            return EmailDeliveryResult(
                success=False,
                error=f"Rate limit exceeded ({MAX_EMAILS_PER_HOUR} emails/hour)",
            )

        # Default context
        if context is None:
            context = EmailContext(
                message_count=summary.message_count,
                participant_count=len(summary.participants) if summary.participants else 0,
                start_time=summary.start_time,
                end_time=summary.end_time,
            )

        # Build email
        subject_line = self.build_subject(summary, context, subject)
        html_content = self.render_html(summary, context)
        text_content = self.render_plain_text(summary, context)

        # Create multipart message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject_line
        msg["From"] = f"{self.config.from_name} <{self.config.from_address}>"
        msg["To"] = ", ".join(recipients)

        # Attach plain text and HTML parts
        msg.attach(MIMEText(text_content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        # Send via SMTP
        try:
            import aiosmtplib

            sent_recipients = []
            failed_recipients = []

            # For port 465, use implicit TLS (use_tls=True)
            # For port 587, use STARTTLS (start_tls=True)
            use_implicit_tls = self.config.port == 465
            use_starttls = self.config.use_tls and self.config.port != 465

            async with aiosmtplib.SMTP(
                hostname=self.config.host,
                port=self.config.port,
                use_tls=use_implicit_tls,
                start_tls=use_starttls,
            ) as smtp:
                # Authenticate if credentials provided
                if self.config.username and self.config.password:
                    await smtp.login(self.config.username, self.config.password)

                # Send to all recipients
                for recipient in recipients:
                    try:
                        await smtp.sendmail(
                            self.config.from_address,
                            recipient,
                            msg.as_string(),
                        )
                        sent_recipients.append(recipient)
                    except Exception as e:
                        logger.error(f"Failed to send to {recipient}: {e}")
                        failed_recipients.append(recipient)

            # Update rate limit counter
            if guild_id:
                self._increment_send_count(guild_id, len(sent_recipients))

            success = len(sent_recipients) > 0
            error = None
            if failed_recipients:
                error = f"Failed to send to: {', '.join(failed_recipients)}"

            logger.info(
                f"Email delivery: {len(sent_recipients)} sent, {len(failed_recipients)} failed"
            )

            return EmailDeliveryResult(
                success=success,
                recipients_sent=sent_recipients,
                recipients_failed=failed_recipients,
                error=error,
            )

        except ImportError:
            logger.error("aiosmtplib not installed. Run: pip install aiosmtplib")
            return EmailDeliveryResult(
                success=False,
                error="aiosmtplib not installed",
            )
        except Exception as e:
            logger.exception(f"SMTP error connecting to {self.config.host}:{self.config.port}: {e}")
            return EmailDeliveryResult(
                success=False,
                error=f"SMTP connection failed: {e}",
            )


# Module-level singleton
_email_service: Optional[EmailDeliveryService] = None


def get_email_service() -> EmailDeliveryService:
    """Get the email delivery service singleton.

    Returns:
        EmailDeliveryService instance
    """
    global _email_service
    if _email_service is None:
        # Load config from environment
        import os
        config = SMTPConfig(
            host=os.getenv("SMTP_HOST", ""),
            port=int(os.getenv("SMTP_PORT", "587")),
            username=os.getenv("SMTP_USERNAME", ""),
            password=os.getenv("SMTP_PASSWORD", ""),
            use_tls=os.getenv("SMTP_USE_TLS", "true").lower() == "true",
            from_address=os.getenv("SMTP_FROM_ADDRESS", ""),
            from_name=os.getenv("SMTP_FROM_NAME", "SummaryBot"),
            enabled=os.getenv("SMTP_ENABLED", "false").lower() == "true",
        )
        _email_service = EmailDeliveryService(config)
        logger.info(
            f"Email service initialized: enabled={config.enabled}, "
            f"host={config.host}, port={config.port}, "
            f"from={config.from_address}, configured={config.is_configured()}"
        )
    return _email_service


def configure_email_service(config: SMTPConfig) -> EmailDeliveryService:
    """Configure the email delivery service.

    Args:
        config: SMTP configuration

    Returns:
        Configured EmailDeliveryService
    """
    global _email_service
    _email_service = EmailDeliveryService(config)
    return _email_service
