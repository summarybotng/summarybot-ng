"""
Dashboard data models and Pydantic schemas.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


# ============================================================================
# Enums
# ============================================================================

class GuildRole(str, Enum):
    """User's role in a guild."""
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class ConfigStatus(str, Enum):
    """Guild configuration status."""
    CONFIGURED = "configured"
    NEEDS_SETUP = "needs_setup"
    INACTIVE = "inactive"


# ============================================================================
# Data Classes (Internal)
# ============================================================================

@dataclass
class DashboardUser:
    """Authenticated dashboard user."""
    id: str
    username: str
    discriminator: Optional[str]
    avatar: Optional[str]

    @property
    def avatar_url(self) -> Optional[str]:
        """Get full avatar URL."""
        if self.avatar:
            return f"https://cdn.discordapp.com/avatars/{self.id}/{self.avatar}.png"
        return None


@dataclass
class DashboardGuild:
    """Guild the user can manage."""
    id: str
    name: str
    icon: Optional[str]
    owner: bool
    permissions: int

    @property
    def icon_url(self) -> Optional[str]:
        """Get full icon URL."""
        if self.icon:
            return f"https://cdn.discordapp.com/icons/{self.id}/{self.icon}.png"
        return None

    def can_manage(self) -> bool:
        """Check if user can manage this guild."""
        ADMINISTRATOR = 0x8
        MANAGE_GUILD = 0x20
        return bool(self.permissions & (ADMINISTRATOR | MANAGE_GUILD)) or self.owner


@dataclass
class DashboardSession:
    """Dashboard user session."""
    id: str
    discord_user_id: str
    discord_username: str
    discord_discriminator: Optional[str]
    discord_avatar: Optional[str]
    discord_access_token: str  # Encrypted
    discord_refresh_token: str  # Encrypted
    token_expires_at: datetime
    manageable_guild_ids: List[str]
    jwt_token_hash: str
    created_at: datetime
    last_activity: datetime
    expires_at: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


# ============================================================================
# Pydantic Schemas (API)
# ============================================================================

# --- Auth ---

class AuthLoginResponse(BaseModel):
    """Response for login initiation."""
    redirect_url: str


class AuthCallbackRequest(BaseModel):
    """Request for OAuth callback."""
    code: str


class UserResponse(BaseModel):
    """User information."""
    id: str
    username: str
    avatar_url: Optional[str]


class GuildBriefResponse(BaseModel):
    """Brief guild info for auth response."""
    id: str
    name: str
    icon_url: Optional[str]
    role: GuildRole


class AuthCallbackResponse(BaseModel):
    """Response for OAuth callback."""
    token: str
    user: UserResponse
    guilds: List[GuildBriefResponse]


class AuthRefreshResponse(BaseModel):
    """Response for token refresh."""
    token: str
    guilds: Optional[List[str]] = None


# --- Guilds ---

class GuildListItem(BaseModel):
    """Guild item in list."""
    id: str
    name: str
    icon_url: Optional[str]
    member_count: int
    summary_count: int
    last_summary_at: Optional[datetime]
    config_status: ConfigStatus


class GuildsResponse(BaseModel):
    """Response for guild list."""
    guilds: List[GuildListItem]


class ChannelResponse(BaseModel):
    """Channel information."""
    id: str
    name: str
    type: str
    category: Optional[str]
    enabled: bool


class CategoryResponse(BaseModel):
    """Category information."""
    id: str
    name: str
    channel_count: int


class SummaryOptionsResponse(BaseModel):
    """Summary options."""
    summary_length: str = "detailed"
    perspective: str = "general"
    include_action_items: bool = True
    include_technical_terms: bool = True


class GuildConfigResponse(BaseModel):
    """Guild configuration."""
    enabled_channels: List[str]
    excluded_channels: List[str]
    default_options: SummaryOptionsResponse


class GuildStatsResponse(BaseModel):
    """Guild statistics."""
    total_summaries: int
    summaries_this_week: int
    active_schedules: int
    last_summary_at: Optional[datetime]


class GuildDetailResponse(BaseModel):
    """Full guild details."""
    id: str
    name: str
    icon_url: Optional[str]
    member_count: int
    channels: List[ChannelResponse]
    categories: List[CategoryResponse]
    config: GuildConfigResponse
    stats: GuildStatsResponse


class ConfigUpdateRequest(BaseModel):
    """Request to update guild config."""
    enabled_channels: Optional[List[str]] = None
    excluded_channels: Optional[List[str]] = None
    default_options: Optional[SummaryOptionsResponse] = None


class ChannelSyncResponse(BaseModel):
    """Response for channel sync."""
    success: bool
    channels_added: int
    channels_removed: int
    channels: List[ChannelResponse]


# --- Summaries ---

class SummaryListItem(BaseModel):
    """Summary item in list."""
    id: str
    channel_id: str
    channel_name: str
    start_time: datetime
    end_time: datetime
    message_count: int
    created_at: datetime
    summary_length: str = "detailed"  # Default for backwards compatibility
    preview: str = ""  # Default for backwards compatibility


class SummariesResponse(BaseModel):
    """Response for summary list."""
    summaries: List[SummaryListItem]
    total: int
    limit: int
    offset: int


class ActionItemResponse(BaseModel):
    """Action item in summary."""
    text: str
    assignee: Optional[str]
    priority: str


class TechnicalTermResponse(BaseModel):
    """Technical term in summary."""
    term: str
    definition: str
    category: Optional[str] = None


class ParticipantResponse(BaseModel):
    """Participant in summary."""
    user_id: str = ""
    display_name: str = ""
    message_count: int = 0
    key_contributions: List[str] = []


class SummaryWarning(BaseModel):
    """Warning about summary generation."""
    code: str  # e.g., "model_fallback", "partial_content", "rate_limited"
    message: str
    details: Optional[Dict[str, Any]] = None


class PromptSourceResponse(BaseModel):
    """Information about where the system prompt came from."""
    source: str  # "custom", "cached", "default", "fallback"
    file_path: Optional[str] = None  # File path that was used
    tried_paths: List[str] = []  # All paths tried in resolution order
    repo_url: Optional[str] = None  # GitHub repo URL (if custom)
    github_file_url: Optional[str] = None  # Direct link to file on GitHub
    version: str = "v1"  # PATH file schema version
    is_stale: bool = False  # Whether cache was stale


class SummaryMetadataResponse(BaseModel):
    """Summary metadata."""
    summary_length: str = "detailed"
    perspective: str = "general"
    model_used: Optional[str] = None  # Actual model that generated the summary
    model_requested: Optional[str] = None  # Originally requested model (may differ due to fallback)
    tokens_used: Optional[int] = None
    generation_time_seconds: Optional[float] = None
    warnings: List[SummaryWarning] = []  # Any warnings during generation
    prompt_source: Optional[PromptSourceResponse] = None  # Prompt resolution info


class SummaryDetailResponse(BaseModel):
    """Full summary details."""
    id: str
    channel_id: str
    channel_name: str
    start_time: datetime
    end_time: datetime
    message_count: int
    summary_text: str
    key_points: List[str]
    action_items: List[ActionItemResponse]
    technical_terms: List[TechnicalTermResponse]
    participants: List[ParticipantResponse]
    metadata: SummaryMetadataResponse
    created_at: datetime
    has_prompt_data: bool = False  # Whether prompt/source content is available


class SummaryPromptResponse(BaseModel):
    """Prompt and source content for a summary."""
    summary_id: str
    prompt_system: Optional[str] = None  # System prompt sent to LLM
    prompt_user: Optional[str] = None  # User prompt with formatted messages
    prompt_template_id: Optional[str] = None  # Custom template ID if used
    source_content: Optional[str] = None  # Original messages in readable format


class TimeRangeRequest(BaseModel):
    """Time range for summary generation."""
    type: str = "hours"  # hours, days, custom
    value: Optional[int] = 24
    start: Optional[datetime] = None
    end: Optional[datetime] = None


class SummaryScope(str, Enum):
    """Scope for summary generation."""
    CHANNEL = "channel"      # Specific channel(s)
    CATEGORY = "category"    # All channels in a category
    GUILD = "guild"          # All enabled channels in the guild


class GenerateSummaryRequest(BaseModel):
    """Request to generate summary."""
    scope: SummaryScope = SummaryScope.CHANNEL  # Default to channel for backwards compatibility
    channel_ids: Optional[List[str]] = None     # Required for CHANNEL scope
    category_id: Optional[str] = None           # Required for CATEGORY scope
    time_range: TimeRangeRequest
    options: Optional[SummaryOptionsResponse] = None


class GenerateSummaryResponse(BaseModel):
    """Response for summary generation."""
    task_id: str
    status: str = "processing"


class TaskStatusResponse(BaseModel):
    """Response for task status check."""
    task_id: str
    status: str
    summary_id: Optional[str] = None
    error: Optional[str] = None


# --- Schedules ---

class DestinationResponse(BaseModel):
    """Delivery destination."""
    type: str
    target: str
    format: str = "embed"


class ScheduleListItem(BaseModel):
    """Schedule item in list."""
    id: str
    name: str
    channel_ids: List[str]
    schedule_type: str
    schedule_time: str
    schedule_days: Optional[List[int]]
    timezone: str = "UTC"
    is_active: bool
    destinations: List[DestinationResponse]
    summary_options: SummaryOptionsResponse
    last_run: Optional[datetime]
    next_run: Optional[datetime]
    run_count: int
    failure_count: int


class SchedulesResponse(BaseModel):
    """Response for schedule list."""
    schedules: List[ScheduleListItem]


class ScheduleCreateRequest(BaseModel):
    """Request to create schedule."""
    name: str
    channel_ids: List[str]
    schedule_type: str = "daily"
    schedule_time: str = "09:00"
    schedule_days: Optional[List[int]] = None
    timezone: str = "UTC"
    destinations: List[DestinationResponse]
    summary_options: Optional[SummaryOptionsResponse] = None


class ScheduleUpdateRequest(BaseModel):
    """Request to update schedule."""
    name: Optional[str] = None
    channel_ids: Optional[List[str]] = None
    schedule_type: Optional[str] = None
    schedule_time: Optional[str] = None
    schedule_days: Optional[List[int]] = None
    timezone: Optional[str] = None
    is_active: Optional[bool] = None
    destinations: Optional[List[DestinationResponse]] = None
    summary_options: Optional[SummaryOptionsResponse] = None


class ScheduleRunResponse(BaseModel):
    """Response for immediate schedule run."""
    execution_id: str
    status: str = "started"


class ExecutionHistoryItem(BaseModel):
    """Execution history item."""
    execution_id: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    summary_id: Optional[str]
    delivery_results: List[Dict[str, Any]]


class ExecutionHistoryResponse(BaseModel):
    """Response for execution history."""
    executions: List[ExecutionHistoryItem]


# --- Webhooks ---

class WebhookListItem(BaseModel):
    """Webhook item in list."""
    id: str
    name: str
    url_preview: str
    type: str
    enabled: bool
    last_delivery: Optional[datetime]
    last_status: Optional[str]
    created_at: datetime


class WebhooksResponse(BaseModel):
    """Response for webhook list."""
    webhooks: List[WebhookListItem]


class WebhookCreateRequest(BaseModel):
    """Request to create webhook."""
    name: str
    url: str
    type: str = "generic"
    headers: Optional[Dict[str, str]] = None


class WebhookUpdateRequest(BaseModel):
    """Request to update webhook."""
    name: Optional[str] = None
    url: Optional[str] = None
    type: Optional[str] = None
    enabled: Optional[bool] = None
    headers: Optional[Dict[str, str]] = None


class WebhookTestResponse(BaseModel):
    """Response for webhook test."""
    success: bool
    response_code: Optional[int]
    response_time_ms: Optional[int]
    error: Optional[str] = None


# --- Feeds ---

class FeedListItem(BaseModel):
    """Feed item in list."""
    id: str
    channel_id: Optional[str]
    channel_name: Optional[str]
    feed_type: str
    is_public: bool
    url: str
    title: str
    created_at: datetime
    last_accessed: Optional[datetime]
    access_count: int


class FeedsResponse(BaseModel):
    """Response for feed list."""
    feeds: List[FeedListItem]


class FeedCreateRequest(BaseModel):
    """Request to create feed."""
    channel_id: Optional[str] = None
    feed_type: str = "rss"
    is_public: bool = False
    title: Optional[str] = None
    description: Optional[str] = None
    max_items: int = Field(default=50, ge=1, le=100)
    include_full_content: bool = True


class FeedUpdateRequest(BaseModel):
    """Request to update feed."""
    title: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None
    max_items: Optional[int] = Field(default=None, ge=1, le=100)
    include_full_content: Optional[bool] = None


class FeedDetailResponse(BaseModel):
    """Full feed details."""
    id: str
    guild_id: str
    channel_id: Optional[str]
    channel_name: Optional[str]
    feed_type: str
    is_public: bool
    url: str
    token: Optional[str]  # Only shown to creator
    title: str
    description: str
    max_items: int
    include_full_content: bool
    created_at: datetime
    created_by: str
    last_accessed: Optional[datetime]
    access_count: int


class FeedTokenResponse(BaseModel):
    """Response for token regeneration."""
    token: str
    url: str


# --- Settings ---

class SettingsUpdateRequest(BaseModel):
    """Request to update settings."""
    default_options: SummaryOptionsResponse


# --- Errors ---

class ErrorDetail(BaseModel):
    """Error detail."""
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """Error response."""
    error: ErrorDetail


# --- Error Logs (Operational Errors) ---

class ErrorLogItem(BaseModel):
    """Error log item for list display."""
    id: str
    guild_id: Optional[str] = None
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    error_type: str
    severity: str
    error_code: Optional[str] = None
    message: str
    operation: str = ""
    created_at: datetime
    is_resolved: bool = False


class ErrorLogDetail(BaseModel):
    """Full error log details."""
    id: str
    guild_id: Optional[str] = None
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    error_type: str
    severity: str
    error_code: Optional[str] = None
    message: str
    details: Dict[str, Any] = {}
    operation: str = ""
    user_id: Optional[str] = None
    stack_trace: Optional[str] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None


class ErrorLogsResponse(BaseModel):
    """Response for error logs list."""
    errors: List[ErrorLogItem]
    total: int
    unresolved_count: int


class ErrorCountsResponse(BaseModel):
    """Response for error counts by type."""
    counts: Dict[str, int]
    total: int
    period_hours: int


class ResolveErrorRequest(BaseModel):
    """Request to resolve an error."""
    notes: Optional[str] = None


class BulkResolveRequest(BaseModel):
    """Request to bulk resolve errors by type."""
    error_type: str  # e.g., "discord_permission", "api_error"
    notes: Optional[str] = None


class BulkResolveResponse(BaseModel):
    """Response for bulk resolve operation."""
    resolved_count: int


class ErrorRetryResponse(BaseModel):
    """Response for error retry request."""
    error_id: str
    retryable: bool
    retry_context: Optional[Dict[str, Any]] = None  # Context needed to retry
    message: str


class ErrorExportFormat(str, Enum):
    """Export format options."""
    CSV = "csv"
    JSON = "json"


class ErrorExportResponse(BaseModel):
    """Response for error export."""
    format: str
    count: int
    data: str  # CSV string or JSON string
