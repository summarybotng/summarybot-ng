"""
Delivery strategies for scheduled task execution (CS-008).

This module provides a strategy pattern for delivering summaries to various
destinations (Discord channel, Discord DM, webhook, email, dashboard).
"""

from .base import DeliveryStrategy, DeliveryResult
from .discord import DiscordDeliveryStrategy
from .discord_dm import DiscordDMDeliveryStrategy
from .webhook import WebhookDeliveryStrategy
from .email import EmailDeliveryStrategy
from .dashboard import DashboardDeliveryStrategy

__all__ = [
    'DeliveryStrategy',
    'DeliveryResult',
    'DiscordDeliveryStrategy',
    'DiscordDMDeliveryStrategy',
    'WebhookDeliveryStrategy',
    'EmailDeliveryStrategy',
    'DashboardDeliveryStrategy',
]
