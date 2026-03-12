"""
Request validation models using Pydantic.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator, validator, HttpUrl
from src.utils.time import utc_now_naive


class SummaryType(str, Enum):
    """Summary type options."""
    BRIEF = "brief"
    DETAILED = "detailed"
    COMPREHENSIVE = "comprehensive"
    TECHNICAL = "technical"
    EXECUTIVE = "executive"


class OutputFormat(str, Enum):
    """Output format options."""
    JSON = "json"
    MARKDOWN = "markdown"
    HTML = "html"
    PLAIN_TEXT = "plain_text"


class ScheduleFrequency(str, Enum):
    """Schedule frequency options."""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class TimeRangeModel(BaseModel):
    """Time range for message retrieval."""
    start: datetime = Field(..., description="Start time for message retrieval")
    end: datetime = Field(..., description="End time for message retrieval")

    @model_validator(mode='after')
    def validate_time_range(self):
        """Validate end time is after start time."""
        if self.end <= self.start:
            raise ValueError("end time must be after start time")
        return self

    @field_validator("start", "end")
    @classmethod
    def not_future(cls, v):
        """Validate time is not in the future."""
        if v > utc_now_naive():
            raise ValueError("time cannot be in the future")
        return v


class SummaryRequestModel(BaseModel):
    """Request model for creating a summary."""

    channel_id: str = Field(..., description="Discord channel ID", min_length=1)
    guild_id: Optional[str] = Field(None, description="Discord guild ID")

    time_range: Optional[TimeRangeModel] = Field(
        None,
        description="Time range for messages (optional, defaults to last 24 hours)"
    )

    summary_type: SummaryType = Field(
        SummaryType.DETAILED,
        description="Type of summary to generate"
    )

    output_format: OutputFormat = Field(
        OutputFormat.JSON,
        description="Output format for the summary"
    )

    max_length: int = Field(
        4000,
        description="Maximum summary length in tokens",
        ge=100,
        le=10000
    )

    include_threads: bool = Field(
        True,
        description="Include thread messages in summary"
    )

    exclude_bots: bool = Field(
        True,
        description="Exclude bot messages from summary"
    )

    include_technical_terms: bool = Field(
        True,
        description="Extract and define technical terms"
    )

    include_action_items: bool = Field(
        True,
        description="Extract action items from messages"
    )

    webhook_url: Optional[HttpUrl] = Field(
        None,
        description="Webhook URL for async result delivery"
    )

    custom_prompt: Optional[str] = Field(
        None,
        description="Custom prompt for summarization",
        max_length=2000
    )

    model: Optional[str] = Field(
        None,
        description="Claude model to use (defaults to configured model)"
    )

    temperature: float = Field(
        0.3,
        description="Model temperature for randomness",
        ge=0.0,
        le=1.0
    )

    class Config:
        schema_extra = {
            "example": {
                "channel_id": "123456789012345678",
                "guild_id": "987654321098765432",
                "summary_type": "detailed",
                "output_format": "json",
                "max_length": 4000,
                "include_threads": True,
                "exclude_bots": True,
                "include_technical_terms": True,
                "include_action_items": True
            }
        }


class ActionItemModel(BaseModel):
    """Action item in summary."""
    description: str
    assignee: Optional[str] = None
    priority: str = "medium"
    deadline: Optional[datetime] = None


class TechnicalTermModel(BaseModel):
    """Technical term definition."""
    term: str
    definition: str
    context: Optional[str] = None


class ParticipantModel(BaseModel):
    """Conversation participant."""
    user_id: str
    display_name: str
    message_count: int
    key_contributions: List[str] = []


class SummaryResponseModel(BaseModel):
    """Response model for summary results."""

    id: str = Field(..., description="Unique summary identifier")
    channel_id: str
    guild_id: Optional[str] = None

    summary_text: str = Field(..., description="Generated summary content")

    key_points: List[str] = Field(default=[], description="Key points extracted")
    action_items: List[ActionItemModel] = Field(default=[], description="Action items")
    technical_terms: List[TechnicalTermModel] = Field(default=[], description="Technical terms")
    participants: List[ParticipantModel] = Field(default=[], description="Participants")

    message_count: int = Field(..., description="Number of messages summarized")
    start_time: datetime
    end_time: datetime

    created_at: datetime = Field(..., description="Summary creation timestamp")

    metadata: Dict[str, Any] = Field(
        default={},
        description="Additional metadata (tokens, cost, etc.)"
    )

    class Config:
        schema_extra = {
            "example": {
                "id": "sum_1234567890",
                "channel_id": "123456789012345678",
                "summary_text": "The team discussed the new API endpoint...",
                "key_points": [
                    "New API endpoint requires authentication",
                    "Rate limiting to be implemented"
                ],
                "action_items": [
                    {
                        "description": "Implement JWT authentication",
                        "assignee": "user123",
                        "priority": "high"
                    }
                ],
                "technical_terms": [
                    {
                        "term": "JWT",
                        "definition": "JSON Web Token for authentication"
                    }
                ],
                "participants": [
                    {
                        "user_id": "123",
                        "display_name": "Alice",
                        "message_count": 15,
                        "key_contributions": ["Proposed JWT implementation"]
                    }
                ],
                "message_count": 42,
                "start_time": "2024-01-01T00:00:00Z",
                "end_time": "2024-01-01T23:59:59Z",
                "created_at": "2024-01-02T00:00:00Z",
                "metadata": {
                    "input_tokens": 1500,
                    "output_tokens": 500,
                    "total_tokens": 2000
                }
            }
        }


class ScheduleRequestModel(BaseModel):
    """Request model for scheduling summaries."""

    channel_id: str = Field(..., description="Discord channel ID")
    guild_id: Optional[str] = Field(None, description="Discord guild ID")

    frequency: ScheduleFrequency = Field(
        ...,
        description="Schedule frequency"
    )

    summary_type: SummaryType = Field(
        SummaryType.DETAILED,
        description="Type of summary to generate"
    )

    webhook_url: Optional[HttpUrl] = Field(
        None,
        description="Webhook URL for results"
    )

    enabled: bool = Field(
        True,
        description="Whether schedule is active"
    )

    class Config:
        schema_extra = {
            "example": {
                "channel_id": "123456789012345678",
                "frequency": "daily",
                "summary_type": "detailed",
                "webhook_url": "https://example.com/webhook",
                "enabled": True
            }
        }


class ScheduleResponseModel(BaseModel):
    """Response model for schedule operations."""

    schedule_id: str = Field(..., description="Schedule identifier")
    channel_id: str
    guild_id: Optional[str] = None

    frequency: ScheduleFrequency
    summary_type: SummaryType

    next_run: datetime = Field(..., description="Next scheduled run time")

    enabled: bool
    created_at: datetime

    class Config:
        schema_extra = {
            "example": {
                "schedule_id": "sch_1234567890",
                "channel_id": "123456789012345678",
                "frequency": "daily",
                "summary_type": "detailed",
                "next_run": "2024-01-02T00:00:00Z",
                "enabled": True,
                "created_at": "2024-01-01T00:00:00Z"
            }
        }


class ErrorResponseModel(BaseModel):
    """Error response model."""

    error: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    request_id: Optional[str] = Field(None, description="Request ID for tracking")

    class Config:
        schema_extra = {
            "example": {
                "error": "VALIDATION_ERROR",
                "message": "Invalid channel ID format",
                "details": {
                    "field": "channel_id",
                    "expected": "numeric string"
                },
                "request_id": "req_1234567890"
            }
        }
