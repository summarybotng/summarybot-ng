"""
Webhook-related models.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from enum import Enum

from .base import BaseModel, generate_id
from src.utils.time import utc_now_naive


class WebhookEvent(Enum):
    """Types of webhook events."""
    SUMMARY_REQUESTED = "summary.requested"
    SUMMARY_COMPLETED = "summary.completed" 
    SUMMARY_FAILED = "summary.failed"
    TASK_SCHEDULED = "task.scheduled"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"


class WebhookStatus(Enum):
    """Webhook delivery status."""
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


@dataclass
class WebhookRequest(BaseModel):
    """Incoming webhook request."""
    id: str = field(default_factory=generate_id)
    action: str = ""  # summarize, schedule, get_summary, etc.
    guild_id: Optional[str] = None
    channel_id: Optional[str] = None
    user_id: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    raw_body: str = ""
    source_ip: Optional[str] = None
    user_agent: Optional[str] = None
    received_at: datetime = field(default_factory=datetime.utcnow)
    processed: bool = False

    @property
    def api_key(self) -> Optional[str]:
        """Get API key from request (convenience property for validators)."""
        return self.get_auth_token()

    def get_auth_token(self) -> Optional[str]:
        """Extract authentication token from headers."""
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        
        # Check for API key in headers
        api_key = self.headers.get("X-API-Key")
        if api_key:
            return api_key
        
        # Check in parameters
        return self.parameters.get("api_key")
    
    def get_signature(self) -> Optional[str]:
        """Get webhook signature for verification."""
        return self.headers.get("X-Signature") or self.headers.get("X-Hub-Signature-256")
    
    def validate_required_fields(self, required_fields: List[str]) -> List[str]:
        """Validate that required fields are present."""
        missing = []
        for field in required_fields:
            if field not in self.parameters or not self.parameters[field]:
                missing.append(field)
        return missing
    
    def to_log_dict(self) -> Dict[str, Any]:
        """Convert to dictionary suitable for logging."""
        return {
            "id": self.id,
            "action": self.action,
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "user_id": self.user_id,
            "source_ip": self.source_ip,
            "user_agent": self.user_agent,
            "received_at": self.received_at,
            "processed": self.processed,
            "has_auth_token": self.get_auth_token() is not None,
            "has_signature": self.get_signature() is not None
        }


@dataclass
class WebhookResponse(BaseModel):
    """Response to a webhook request."""
    request_id: str
    success: bool
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    error_code: Optional[str] = None
    processing_time_ms: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_http_response(self) -> Dict[str, Any]:
        """Convert to HTTP response format."""
        response = {
            "success": self.success,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "request_id": self.request_id
        }
        
        if self.success and self.data:
            response["data"] = self.data
        
        if not self.success and self.error_code:
            response["error_code"] = self.error_code
        
        if self.processing_time_ms is not None:
            response["processing_time_ms"] = self.processing_time_ms
        
        return response
    
    @classmethod
    def success_response(cls, request_id: str, data: Dict[str, Any] = None, 
                        message: str = "Success") -> 'WebhookResponse':
        """Create a success response."""
        return cls(
            request_id=request_id,
            success=True,
            message=message,
            data=data or {}
        )
    
    @classmethod
    def error_response(cls, request_id: str, message: str, error_code: str = None) -> 'WebhookResponse':
        """Create an error response."""
        return cls(
            request_id=request_id,
            success=False,
            message=message,
            error_code=error_code
        )


@dataclass
class WebhookDelivery(BaseModel):
    """Outgoing webhook delivery."""
    event: WebhookEvent
    url: str
    id: str = field(default_factory=generate_id)
    payload: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    status: WebhookStatus = WebhookStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    scheduled_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    response_status: Optional[int] = None
    response_body: Optional[str] = None
    response_headers: Dict[str, str] = field(default_factory=dict)
    attempt_count: int = 0
    max_attempts: int = 3
    retry_delay_seconds: int = 60
    error_message: Optional[str] = None
    
    def should_retry(self) -> bool:
        """Check if delivery should be retried."""
        if self.status in [WebhookStatus.DELIVERED, WebhookStatus.CANCELLED]:
            return False
        
        return self.attempt_count < self.max_attempts
    
    def calculate_next_retry(self) -> datetime:
        """Calculate next retry time with exponential backoff."""
        delay = self.retry_delay_seconds * (2 ** (self.attempt_count - 1))
        return utc_now_naive() + timedelta(seconds=delay)
    
    def mark_attempt(self) -> None:
        """Mark delivery attempt."""
        self.attempt_count += 1
        self.status = WebhookStatus.RETRYING if self.attempt_count > 1 else WebhookStatus.PENDING
    
    def mark_delivered(self, response_status: int, response_body: str = "", 
                      response_headers: Dict[str, str] = None) -> None:
        """Mark delivery as successful."""
        self.status = WebhookStatus.DELIVERED
        self.delivered_at = utc_now_naive()
        self.response_status = response_status
        self.response_body = response_body
        self.response_headers = response_headers or {}
    
    def mark_failed(self, error_message: str, response_status: int = None,
                   response_body: str = "") -> None:
        """Mark delivery as failed."""
        self.status = WebhookStatus.FAILED
        self.error_message = error_message
        self.response_status = response_status
        self.response_body = response_body
        
        if not self.should_retry():
            self.status = WebhookStatus.CANCELLED
    
    def get_payload_for_event(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Get formatted payload for the webhook event."""
        base_payload = {
            "event": self.event.value,
            "timestamp": utc_now_naive().isoformat(),
            "delivery_id": self.id,
            "data": data
        }
        
        # Add event-specific formatting
        if self.event == WebhookEvent.SUMMARY_COMPLETED:
            if "summary" in data:
                summary = data["summary"]
                base_payload["summary"] = {
                    "id": summary.get("id"),
                    "channel_id": summary.get("channel_id"),
                    "message_count": summary.get("message_count"),
                    "key_points": summary.get("key_points", []),
                    "action_items": summary.get("action_items", []),
                    "summary_text": summary.get("summary_text"),
                    "created_at": summary.get("created_at")
                }
        
        return base_payload
    
    def to_status_dict(self) -> Dict[str, Any]:
        """Get status information for monitoring."""
        return {
            "id": self.id,
            "event": self.event.value,
            "url": self.url,
            "status": self.status.value,
            "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts,
            "created_at": self.created_at,
            "delivered_at": self.delivered_at,
            "response_status": self.response_status,
            "error_message": self.error_message,
            "should_retry": self.should_retry()
        }