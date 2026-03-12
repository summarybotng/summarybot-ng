"""
Response formatting utilities for webhook service.
"""

import json
from typing import Dict, Any, List
from datetime import datetime
from enum import Enum

from ..models.summary import SummaryResult, ActionItem, TechnicalTerm, Participant
from src.utils.time import utc_now_naive


class OutputFormat(str, Enum):
    """Output format options."""
    JSON = "json"
    MARKDOWN = "markdown"
    HTML = "html"
    PLAIN_TEXT = "plain_text"


class ResponseFormatter:
    """Utility class for formatting API responses."""

    @staticmethod
    def format_summary(
        summary: SummaryResult,
        output_format: OutputFormat = OutputFormat.JSON
    ) -> str:
        """Format summary result based on output format.

        Args:
            summary: Summary result to format
            output_format: Desired output format

        Returns:
            Formatted summary string
        """
        if output_format == OutputFormat.JSON:
            return ResponseFormatter._format_json(summary)
        elif output_format == OutputFormat.MARKDOWN:
            return ResponseFormatter._format_markdown(summary)
        elif output_format == OutputFormat.HTML:
            return ResponseFormatter._format_html(summary)
        elif output_format == OutputFormat.PLAIN_TEXT:
            return ResponseFormatter._format_plain_text(summary)
        else:
            return ResponseFormatter._format_json(summary)

    @staticmethod
    def _format_json(summary: SummaryResult) -> str:
        """Format summary as JSON."""
        return json.dumps(summary.to_dict(), indent=2, default=str)

    @staticmethod
    def _format_markdown(summary: SummaryResult) -> str:
        """Format summary as Markdown."""
        return summary.to_markdown()

    @staticmethod
    def _format_html(summary: SummaryResult) -> str:
        """Format summary as HTML.

        Args:
            summary: Summary result

        Returns:
            HTML formatted string
        """
        html = ['<!DOCTYPE html>', '<html>', '<head>']
        html.append('<meta charset="utf-8">')
        html.append('<title>Summary Report</title>')
        html.append('<style>')
        html.append('body { font-family: Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; }')
        html.append('h1 { color: #333; border-bottom: 2px solid #4A90E2; }')
        html.append('h2 { color: #4A90E2; margin-top: 30px; }')
        html.append('.metadata { background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0; }')
        html.append('.key-points, .action-items, .technical-terms { margin: 20px 0; }')
        html.append('li { margin: 10px 0; }')
        html.append('.participant { margin: 15px 0; padding: 10px; background: #f9f9f9; border-left: 3px solid #4A90E2; }')
        html.append('</style>')
        html.append('</head>')
        html.append('<body>')

        # Title
        channel_name = summary.context.channel_name if summary.context else "Unknown Channel"
        html.append(f'<h1>📋 Summary: #{channel_name}</h1>')

        # Metadata
        html.append('<div class="metadata">')
        html.append(f'<strong>Time Period:</strong> {summary.start_time.strftime("%Y-%m-%d %H:%M")} - {summary.end_time.strftime("%Y-%m-%d %H:%M")}<br>')
        html.append(f'<strong>Messages:</strong> {summary.message_count} | ')
        html.append(f'<strong>Participants:</strong> {len(summary.participants)}<br>')
        html.append(f'<strong>Generated:</strong> {summary.created_at.strftime("%Y-%m-%d at %H:%M UTC")}')
        html.append('</div>')

        # Summary text
        html.append('<h2>📖 Summary</h2>')
        html.append(f'<p>{summary.summary_text}</p>')

        # Key points
        if summary.key_points:
            html.append('<h2>🎯 Key Points</h2>')
            html.append('<ul class="key-points">')
            for point in summary.key_points:
                html.append(f'<li>{point}</li>')
            html.append('</ul>')

        # Action items
        if summary.action_items:
            html.append('<h2>📝 Action Items</h2>')
            html.append('<ul class="action-items">')
            for item in summary.action_items:
                priority_color = {
                    "high": "🔴",
                    "medium": "🟡",
                    "low": "🟢"
                }.get(item.priority.value if hasattr(item.priority, 'value') else item.priority, "⚪")

                assignee = f" (@{item.assignee})" if item.assignee else ""
                deadline = f" - Due: {item.deadline.strftime('%Y-%m-%d')}" if item.deadline else ""

                html.append(f'<li>{priority_color} {item.description}{assignee}{deadline}</li>')
            html.append('</ul>')

        # Technical terms
        if summary.technical_terms:
            html.append('<h2>🔧 Technical Terms</h2>')
            html.append('<ul class="technical-terms">')
            for term in summary.technical_terms:
                html.append(f'<li><strong>{term.term}:</strong> {term.definition}</li>')
            html.append('</ul>')

        # Participants
        if summary.participants:
            html.append('<h2>👥 Participants</h2>')
            sorted_participants = sorted(
                summary.participants,
                key=lambda p: p.message_count,
                reverse=True
            )
            for participant in sorted_participants:
                html.append(f'<div class="participant">')
                html.append(f'<strong>{participant.display_name}</strong> ({participant.message_count} messages)')
                if participant.key_contributions:
                    html.append('<br>Key contributions:')
                    html.append('<ul>')
                    for contribution in participant.key_contributions:
                        html.append(f'<li>{contribution}</li>')
                    html.append('</ul>')
                html.append('</div>')

        # Footer
        html.append('<hr>')
        html.append(f'<p style="color: #666; font-size: 0.9em;">Summary ID: {summary.id} | Generated by Summary Bot NG</p>')

        html.append('</body>')
        html.append('</html>')

        return '\n'.join(html)

    @staticmethod
    def _format_plain_text(summary: SummaryResult) -> str:
        """Format summary as plain text.

        Args:
            summary: Summary result

        Returns:
            Plain text formatted string
        """
        lines = []

        # Title
        channel_name = summary.context.channel_name if summary.context else "Unknown Channel"
        lines.append(f"SUMMARY: #{channel_name}")
        lines.append("=" * 60)
        lines.append("")

        # Metadata
        lines.append(f"Time Period: {summary.start_time.strftime('%Y-%m-%d %H:%M')} - {summary.end_time.strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"Messages: {summary.message_count} | Participants: {len(summary.participants)}")
        lines.append("")

        # Summary
        lines.append("SUMMARY")
        lines.append("-" * 60)
        lines.append(summary.summary_text)
        lines.append("")

        # Key points
        if summary.key_points:
            lines.append("KEY POINTS")
            lines.append("-" * 60)
            for i, point in enumerate(summary.key_points, 1):
                lines.append(f"{i}. {point}")
            lines.append("")

        # Action items
        if summary.action_items:
            lines.append("ACTION ITEMS")
            lines.append("-" * 60)
            for i, item in enumerate(summary.action_items, 1):
                assignee = f" (@{item.assignee})" if item.assignee else ""
                deadline = f" - Due: {item.deadline.strftime('%Y-%m-%d')}" if item.deadline else ""
                lines.append(f"{i}. {item.description}{assignee}{deadline}")
            lines.append("")

        # Technical terms
        if summary.technical_terms:
            lines.append("TECHNICAL TERMS")
            lines.append("-" * 60)
            for term in summary.technical_terms:
                lines.append(f"{term.term}: {term.definition}")
            lines.append("")

        # Participants
        if summary.participants:
            lines.append("PARTICIPANTS")
            lines.append("-" * 60)
            sorted_participants = sorted(
                summary.participants,
                key=lambda p: p.message_count,
                reverse=True
            )
            for participant in sorted_participants:
                lines.append(f"{participant.display_name} ({participant.message_count} messages)")
                if participant.key_contributions:
                    for contribution in participant.key_contributions:
                        lines.append(f"  - {contribution}")
            lines.append("")

        # Footer
        lines.append("-" * 60)
        lines.append(f"Summary ID: {summary.id}")
        lines.append(f"Generated: {summary.created_at.strftime('%Y-%m-%d at %H:%M UTC')}")

        return "\n".join(lines)

    @staticmethod
    def format_error(
        error_code: str,
        message: str,
        details: Dict[str, Any] = None,
        request_id: str = None
    ) -> Dict[str, Any]:
        """Format error response.

        Args:
            error_code: Error code
            message: Error message
            details: Additional error details
            request_id: Request ID for tracking

        Returns:
            Formatted error dictionary
        """
        error_response = {
            "error": error_code,
            "message": message,
            "timestamp": utc_now_naive().isoformat()
        }

        if details:
            error_response["details"] = details

        if request_id:
            error_response["request_id"] = request_id

        return error_response

    @staticmethod
    def format_success(
        data: Any,
        message: str = "Success",
        request_id: str = None
    ) -> Dict[str, Any]:
        """Format success response.

        Args:
            data: Response data
            message: Success message
            request_id: Request ID for tracking

        Returns:
            Formatted success dictionary
        """
        response = {
            "success": True,
            "message": message,
            "timestamp": utc_now_naive().isoformat(),
            "data": data
        }

        if request_id:
            response["request_id"] = request_id

        return response
