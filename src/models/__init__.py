"""
Data models module for Summary Bot NG.

This module provides data models and DTOs for all domain objects 
with serialization support.
"""

from .base import BaseModel, SerializableModel
from .summary import (
    SummaryResult, SummaryOptions, ActionItem, TechnicalTerm, 
    Participant, SummarizationContext
)
from .message import (
    ProcessedMessage, MessageReference, AttachmentInfo, ThreadInfo,
    CodeBlock, MessageMention, SourceType, MessageType
)
from .ingest import (
    IngestDocument, IngestMessage, IngestParticipant, IngestAttachment,
    IngestResponse, IngestBatch, ChannelType, ParticipantRole
)
from .reference import (
    SummaryReference, ReferencedClaim, PositionIndex,
    build_deduped_reference_index
)
from .user import User, UserPermissions
from .task import ScheduledTask, TaskResult, TaskStatus, Destination, DestinationType
from .stored_summary import StoredSummary, PushDelivery
from .webhook import WebhookRequest, WebhookResponse, WebhookDelivery
from .feed import FeedConfig, FeedType
from .error_log import ErrorLog, ErrorType, ErrorSeverity

__all__ = [
    # Base models
    'BaseModel',
    'SerializableModel',
    
    # Summary models
    'SummaryResult',
    'SummaryOptions', 
    'ActionItem',
    'TechnicalTerm',
    'Participant',
    'SummarizationContext',
    
    # Message models
    'ProcessedMessage',
    'MessageReference',
    'AttachmentInfo',
    'ThreadInfo',
    'CodeBlock',
    'MessageMention',
    'SourceType',
    'MessageType',

    # Ingest models (ADR-002)
    'IngestDocument',
    'IngestMessage',
    'IngestParticipant',
    'IngestAttachment',
    'IngestResponse',
    'IngestBatch',
    'ChannelType',
    'ParticipantRole',

    # Reference models (ADR-004)
    'SummaryReference',
    'ReferencedClaim',
    'PositionIndex',
    'build_deduped_reference_index',
    
    # User models
    'User',
    'UserPermissions',
    
    # Task models
    'ScheduledTask',
    'TaskResult',
    'TaskStatus',
    'Destination',
    'DestinationType',

    # Stored summary models (ADR-005)
    'StoredSummary',
    'PushDelivery',
    
    # Webhook models
    'WebhookRequest',
    'WebhookResponse',
    'WebhookDelivery',

    # Feed models
    'FeedConfig',
    'FeedType',

    # Error log models
    'ErrorLog',
    'ErrorType',
    'ErrorSeverity',
]