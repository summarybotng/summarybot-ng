"""
Delivery strategies for scheduled task execution (CS-008).

This module provides a strategy pattern for delivering summaries to various
destinations (Discord, webhook, email, dashboard).
"""

from .base import DeliveryStrategy, DeliveryResult
from .discord import DiscordDeliveryStrategy
from .webhook import WebhookDeliveryStrategy
from .email import EmailDeliveryStrategy
from .dashboard import DashboardDeliveryStrategy

__all__ = [
    'DeliveryStrategy',
    'DeliveryResult',
    'DiscordDeliveryStrategy',
    'WebhookDeliveryStrategy',
    'EmailDeliveryStrategy',
    'DashboardDeliveryStrategy',
]
