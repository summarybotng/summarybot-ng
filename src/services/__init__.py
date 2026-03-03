"""
Services module for Summary Bot NG.

This module provides reusable service classes that handle business logic
across multiple components.
"""

from .summary_push import SummaryPushService
from .email_delivery import (
    EmailDeliveryService,
    EmailDeliveryResult,
    EmailContext,
    SMTPConfig,
    get_email_service,
    configure_email_service,
)

__all__ = [
    'SummaryPushService',
    # ADR-030: Email delivery
    'EmailDeliveryService',
    'EmailDeliveryResult',
    'EmailContext',
    'SMTPConfig',
    'get_email_service',
    'configure_email_service',
]
