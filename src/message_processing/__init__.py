"""
Message processing module for Discord and WhatsApp message handling.

This module provides message fetching, filtering, and preprocessing
for summarization across multiple data sources (ADR-002).
"""

from .fetcher import MessageFetcher
from .filter import MessageFilter
from .cleaner import MessageCleaner
from .extractor import MessageExtractor
from .validator import MessageValidator
from .processor import MessageProcessor
from .whatsapp_processor import WhatsAppMessageProcessor, ThreadReconstructor

__all__ = [
    'MessageFetcher',
    'MessageFilter',
    'MessageCleaner',
    'MessageExtractor',
    'MessageValidator',
    'MessageProcessor',
    # ADR-002: WhatsApp support
    'WhatsAppMessageProcessor',
    'ThreadReconstructor',
]