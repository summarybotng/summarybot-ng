"""
Dashboard data models and Pydantic schemas.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, model_validator


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
    """Guild the user is a member of."""
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
        """Check if user can manage this guild (admin-level access)."""
        ADMINISTRATOR = 0x8
        MANAGE_GUILD = 0x20
        return bool(self.permissions & (ADMINISTRATOR | MANAGE_GUILD)) or self.owner

    def get_role(self) -> "GuildRole":
        """Get user's role in this guild."""
        if self.owner:
            return GuildRole.OWNER
        if self.can_manage():
            return GuildRole.ADMIN
        return GuildRole.MEMBER


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
    state: str


class AuthCallbackRequest(BaseModel):
    """Request for OAuth callback."""
    code: str
    state: str


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
    schedule_count: int = 0
    webhook_count: int = 0
    feed_count: int = 0


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
    min_messages: int = 5  # Minimum messages required; set to 1 for low-activity channels


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
    # Breakdown by source type
    realtime_count: int = 0
    archive_count: int = 0
    scheduled_count: int = 0
    manual_count: int = 0


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
    # Extended metadata fields
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    generation_time_ms: Optional[float] = None  # Alias for generation_time_seconds * 1000
    summary_type: Optional[str] = None  # Legacy alias for summary_length
    grounded: Optional[bool] = None
    reference_count: Optional[int] = None
    channel_name: Optional[str] = None
    guild_name: Optional[str] = None
    time_span_hours: Optional[float] = None
    total_participants: Optional[int] = None
    api_version: Optional[str] = None
    cache_status: Optional[str] = None
    # ADR-024: Retry attempt tracking for resilient generation
    generation_attempts: Optional[Dict[str, Any]] = None
    # Pass through any additional unknown fields
    model_config = {"extra": "allow"}


class SummaryReferenceResponse(BaseModel):
    """A source reference from the original conversation (ADR-004)."""
    id: int
    author: str
    timestamp: datetime
    content: str
    message_id: Optional[str] = None


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
    references: List[SummaryReferenceResponse] = Field(default_factory=list)  # ADR-004 source references


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
    prompt_template_id: Optional[str] = None  # ADR-034: Custom template ID


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
    # ADR-011: Scope-based channel selection
    scope: str = "channel"  # channel, category, guild
    channel_ids: List[str]  # Resolved channel IDs at response time
    category_id: Optional[str] = None
    category_name: Optional[str] = None  # Resolved for display
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
    # ADR-034: Guild prompt templates
    prompt_template_id: Optional[str] = None
    prompt_template_name: Optional[str] = None  # Resolved for display


class SchedulesResponse(BaseModel):
    """Response for schedule list."""
    schedules: List[ScheduleListItem]


class ScheduleCreateRequest(BaseModel):
    """Request to create schedule."""
    name: str
    # ADR-011: Scope-based channel selection
    scope: SummaryScope = SummaryScope.CHANNEL  # Default for backwards compatibility
    channel_ids: Optional[List[str]] = None     # Required for CHANNEL scope
    category_id: Optional[str] = None           # Required for CATEGORY scope
    # GUILD scope needs no additional fields
    schedule_type: str = "daily"
    schedule_time: str = "09:00"
    schedule_days: Optional[List[int]] = None
    timezone: str = "UTC"
    destinations: List[DestinationResponse]
    summary_options: Optional[SummaryOptionsResponse] = None
    # ADR-034: Guild prompt templates
    prompt_template_id: Optional[str] = None


class ScheduleUpdateRequest(BaseModel):
    """Request to update schedule."""
    name: Optional[str] = None
    # ADR-011: Scope-based channel selection
    scope: Optional[SummaryScope] = None
    channel_ids: Optional[List[str]] = None
    category_id: Optional[str] = None
    schedule_type: Optional[str] = None
    schedule_time: Optional[str] = None
    schedule_days: Optional[List[int]] = None
    timezone: Optional[str] = None
    is_active: Optional[bool] = None
    destinations: Optional[List[DestinationResponse]] = None
    summary_options: Optional[SummaryOptionsResponse] = None
    # ADR-034: Guild prompt templates
    prompt_template_id: Optional[str] = None


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

# ADR-037: Filter criteria for feeds
class FeedCriteriaRequest(BaseModel):
    """Filter criteria for feed content (ADR-037)."""
    source: Optional[str] = None  # realtime, scheduled, archive, manual, all
    archived: Optional[bool] = None
    created_after: Optional[str] = None  # ISO date
    created_before: Optional[str] = None  # ISO date
    archive_period: Optional[str] = None  # YYYY-MM-DD
    channel_mode: Optional[str] = None  # all, single, multi
    channel_ids: Optional[List[str]] = None
    has_grounding: Optional[bool] = None
    has_key_points: Optional[bool] = None
    has_action_items: Optional[bool] = None
    has_participants: Optional[bool] = None
    min_message_count: Optional[int] = None
    max_message_count: Optional[int] = None
    min_key_points: Optional[int] = None
    max_key_points: Optional[int] = None
    min_action_items: Optional[int] = None
    max_action_items: Optional[int] = None
    min_participants: Optional[int] = None
    max_participants: Optional[int] = None
    platform: Optional[str] = None
    summary_length: Optional[str] = None
    perspective: Optional[str] = None


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
    # ADR-037: Include criteria summary
    criteria: Optional[FeedCriteriaRequest] = None


class FeedsResponse(BaseModel):
    """Response for feed list."""
    feeds: List[FeedListItem]


class FeedCreateRequest(BaseModel):
    """Request to create feed."""
    channel_id: Optional[str] = None  # Deprecated: use criteria.channel_ids
    feed_type: str = "rss"
    is_public: bool = False
    title: Optional[str] = None
    description: Optional[str] = None
    max_items: int = Field(default=50, ge=1, le=100)
    include_full_content: bool = True
    # ADR-037: Filter criteria
    criteria: Optional[FeedCriteriaRequest] = None


class FeedUpdateRequest(BaseModel):
    """Request to update feed."""
    title: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None
    max_items: Optional[int] = Field(default=None, ge=1, le=100)
    include_full_content: Optional[bool] = None
    # ADR-037: Filter criteria
    criteria: Optional[FeedCriteriaRequest] = None


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
    # ADR-037: Filter criteria
    criteria: Optional[FeedCriteriaRequest] = None


# ADR-037: Feed preview response
class FeedPreviewItem(BaseModel):
    """Summary item in feed preview."""
    id: str
    title: str
    channel_name: Optional[str] = None
    created_at: Optional[datetime] = None
    message_count: int = 0
    preview: str = ""
    has_action_items: bool = False
    has_key_points: bool = False
    source: Optional[str] = None
    perspective: Optional[str] = None
    summary_length: Optional[str] = None


class FeedPreviewResponse(BaseModel):
    """Response for feed preview."""
    feed_id: str
    title: str
    description: str
    feed_type: str
    item_count: int
    last_updated: Optional[datetime]
    items: List[FeedPreviewItem]
    criteria: Optional[FeedCriteriaRequest] = None
    has_more: bool = False


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


# ============================================================================
# Stored Summaries (ADR-005)
# ============================================================================

class StoredSummaryListItem(BaseModel):
    """Stored summary item in list (ADR-005, ADR-008, ADR-009, ADR-017)."""
    id: str
    title: str
    source_channel_ids: List[str]
    schedule_id: Optional[str] = None
    schedule_name: Optional[str] = None  # ADR-009: For navigation
    created_at: datetime
    viewed_at: Optional[datetime] = None
    pushed_at: Optional[datetime] = None
    pushed_to_channels: List[str] = []
    is_pinned: bool = False
    is_archived: bool = False
    tags: List[str] = []
    key_points_count: int = 0
    action_items_count: int = 0
    message_count: int = 0
    participant_count: int = 0  # ADR-017: Quick participant count
    has_references: bool = False
    # ADR-008: Source tracking
    source: str = "realtime"  # realtime, archive, scheduled, manual, imported
    archive_period: Optional[str] = None
    archive_granularity: Optional[str] = None
    # Summary generation details
    summary_length: Optional[str] = None  # brief, detailed, comprehensive
    perspective: Optional[str] = None  # general, developer, marketing, etc.
    model_used: Optional[str] = None  # e.g., claude-3-5-sonnet
    # ADR-017: Data integrity status
    has_source_channels: bool = True  # False if source_channel_ids empty
    has_participants: bool = True  # False if participants list empty
    has_grounding: bool = False  # True if reference_index populated
    has_time_range: bool = True  # False if start_time/end_time missing
    can_regenerate: bool = True  # True if enough data for regeneration


class StoredSummaryListResponse(BaseModel):
    """Response for stored summary list."""
    items: List[StoredSummaryListItem]
    total: int
    page: int
    limit: int


class StoredSummaryDetailResponse(BaseModel):
    """Full stored summary details (ADR-005, ADR-008)."""
    id: str
    title: str
    guild_id: str
    source_channel_ids: List[str]
    schedule_id: Optional[str] = None
    created_at: datetime
    viewed_at: Optional[datetime] = None
    pushed_at: Optional[datetime] = None
    is_pinned: bool = False
    is_archived: bool = False
    tags: List[str] = []
    # Full summary content
    summary_text: str
    key_points: List[str] = []
    action_items: List[ActionItemResponse] = []
    participants: List[ParticipantResponse] = []
    message_count: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    metadata: Optional[SummaryMetadataResponse] = None
    # Push history
    push_deliveries: List[Dict[str, Any]] = []
    has_references: bool = False
    # ADR-004: Source references
    references: List[SummaryReferenceResponse] = Field(default_factory=list)
    # ADR-008: Source tracking
    source: str = "realtime"  # realtime, archive, scheduled, manual, imported
    archive_period: Optional[str] = None
    archive_granularity: Optional[str] = None
    archive_source_key: Optional[str] = None
    # Generation details (prompt data) - for "View Generation Details"
    source_content: Optional[str] = None  # Original messages
    prompt_system: Optional[str] = None  # System prompt used
    prompt_user: Optional[str] = None  # User prompt sent to AI
    prompt_template_id: Optional[str] = None  # Custom template ID if used
    # ADR-020: Navigation
    navigation: Optional[Dict[str, Optional[str]]] = None  # prev/next summary IDs


class StoredSummaryUpdateRequest(BaseModel):
    """Request to update stored summary metadata."""
    title: Optional[str] = None
    is_pinned: Optional[bool] = None
    is_archived: Optional[bool] = None
    tags: Optional[List[str]] = None


# ADR-018: Bulk operation models

class BulkFilters(BaseModel):
    """Filters for bulk operations - alternative to specifying IDs (ADR-018 enhancement)."""
    source: Optional[str] = Field(None, description="Filter by source (realtime, archive, scheduled, manual)")
    archived: Optional[bool] = Field(None, description="Filter by archived status")
    created_after: Optional[str] = Field(None, description="Created after (ISO date)")
    created_before: Optional[str] = Field(None, description="Created before (ISO date)")
    archive_period: Optional[str] = Field(None, description="Filter by archive period (YYYY-MM-DD)")
    channel_mode: Optional[str] = Field(None, description="Filter by channel mode (single, multi)")
    has_grounding: Optional[bool] = Field(None, description="Filter by grounding status")
    has_key_points: Optional[bool] = Field(None, description="Filter by key points presence")
    has_action_items: Optional[bool] = Field(None, description="Filter by action items presence")
    has_participants: Optional[bool] = Field(None, description="Filter by participants presence")
    min_message_count: Optional[int] = Field(None, description="Minimum message count")
    max_message_count: Optional[int] = Field(None, description="Maximum message count")


class BulkDeleteRequest(BaseModel):
    """Request to delete multiple stored summaries (ADR-018).

    Either summary_ids OR filters must be provided (not both).
    When using filters, all summaries matching the filters will be deleted.
    """
    summary_ids: Optional[List[str]] = Field(None, max_length=500, description="Summary IDs to delete")
    filters: Optional[BulkFilters] = Field(None, description="Filters to select summaries for deletion")

    @model_validator(mode='after')
    def validate_ids_or_filters(self):
        if not self.summary_ids and not self.filters:
            raise ValueError("Either summary_ids or filters must be provided")
        if self.summary_ids and self.filters:
            raise ValueError("Provide either summary_ids or filters, not both")
        if self.summary_ids and len(self.summary_ids) == 0:
            raise ValueError("summary_ids cannot be empty if provided")
        return self


class BulkDeleteResponse(BaseModel):
    """Response from bulk delete operation (ADR-018)."""
    deleted_count: int
    failed_ids: List[str] = []
    errors: List[str] = []


class RegenerateOptionsRequest(BaseModel):
    """Optional settings for regenerating a stored summary."""
    model: Optional[str] = Field(None, description="Model to use (e.g., claude-3-5-sonnet-20241022)")
    summary_length: Optional[str] = Field(None, description="Length: brief, detailed, comprehensive")
    perspective: Optional[str] = Field(None, description="Perspective: general, developer, marketing, executive, support")


class BulkRegenerateRequest(BaseModel):
    """Request to regenerate multiple stored summaries (ADR-018).

    Either summary_ids OR filters must be provided (not both).
    When using filters, all summaries matching the filters will be queued for regeneration.
    """
    summary_ids: Optional[List[str]] = Field(None, max_length=100, description="Summary IDs to regenerate")
    filters: Optional[BulkFilters] = Field(None, description="Filters to select summaries for regeneration")

    @model_validator(mode='after')
    def validate_ids_or_filters(self):
        if not self.summary_ids and not self.filters:
            raise ValueError("Either summary_ids or filters must be provided")
        if self.summary_ids and self.filters:
            raise ValueError("Provide either summary_ids or filters, not both")
        if self.summary_ids and len(self.summary_ids) == 0:
            raise ValueError("summary_ids cannot be empty if provided")
        return self


class BulkRegenerateResponse(BaseModel):
    """Response from bulk regenerate operation (ADR-018)."""
    queued_count: int
    skipped_count: int = 0
    skipped_ids: List[str] = []
    task_id: str


class PushToChannelRequest(BaseModel):
    """Request to push a stored summary to channels.

    ADR-014: Template format is now the default, which creates a thread
    and sends content across multiple messages to avoid Discord limits.
    """
    channel_ids: List[str] = Field(..., min_length=1, description="Channel IDs to push to")
    format: str = Field(
        "template",
        description="Format: template (thread with full content), embed, markdown, or plain"
    )
    include_references: bool = Field(True, description="Include ADR-004 source references")
    custom_message: Optional[str] = Field(None, description="Optional intro message")
    # Section toggles - which parts to include in the push
    include_key_points: bool = Field(True, description="Include key points section")
    include_action_items: bool = Field(True, description="Include action items section")
    include_participants: bool = Field(True, description="Include participants section")
    include_technical_terms: bool = Field(True, description="Include technical terms section")
    # Thread options (for template format)
    use_thread: bool = Field(True, description="Create a thread for the summary (template format)")


class PushDeliveryResult(BaseModel):
    """Result of pushing to a single channel."""
    channel_id: str
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None


class PushToChannelResponse(BaseModel):
    """Response for push to channel operation."""
    success: bool
    total_channels: int
    successful_channels: int
    deliveries: List[PushDeliveryResult]


# ============================================================================
# ADR-030: Email Delivery Models
# ============================================================================

class SendToEmailRequest(BaseModel):
    """Request to send a stored summary via email (ADR-030)."""
    recipients: List[str] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Email addresses to send to (max 10)"
    )
    subject: Optional[str] = Field(None, description="Custom email subject")
    include_references: bool = Field(True, description="Include source references")


class EmailDeliveryResult(BaseModel):
    """Result of sending to a single email address."""
    recipient: str
    success: bool
    error: Optional[str] = None


class SendToEmailResponse(BaseModel):
    """Response for send to email operation."""
    success: bool
    total_recipients: int
    successful_recipients: int
    failed_recipients: int
    deliveries: List[EmailDeliveryResult]


# ============================================================================
# ADR-013: Unified Job Tracking Models
# ============================================================================

class JobType(str, Enum):
    """Type of summary generation job."""
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    RETROSPECTIVE = "retrospective"
    REGENERATE = "regenerate"


class JobStatus(str, Enum):
    """Status of a summary generation job."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class JobProgressResponse(BaseModel):
    """Progress information for a job."""
    current: int
    total: int
    percent: float
    message: Optional[str] = None
    current_period: Optional[str] = None


class JobCostResponse(BaseModel):
    """Cost tracking for a job."""
    cost_usd: float = 0.0
    tokens_input: int = 0
    tokens_output: int = 0


class JobListItem(BaseModel):
    """Brief job info for list view."""
    job_id: str
    guild_id: str
    job_type: JobType
    status: JobStatus
    scope: Optional[str] = None
    schedule_id: Optional[str] = None
    progress: JobProgressResponse
    summary_id: Optional[str] = None
    error: Optional[str] = None
    pause_reason: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class JobDetailResponse(BaseModel):
    """Full job details."""
    job_id: str
    guild_id: str
    job_type: JobType
    status: JobStatus
    scope: Optional[str] = None
    channel_ids: List[str] = []
    category_id: Optional[str] = None
    schedule_id: Optional[str] = None
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    progress: JobProgressResponse
    cost: JobCostResponse
    summary_id: Optional[str] = None
    summary_ids: List[str] = []
    error: Optional[str] = None
    pause_reason: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_by: Optional[str] = None
    metadata: Dict[str, Any] = {}


class JobsListResponse(BaseModel):
    """Response for job list endpoint."""
    jobs: List[JobListItem]
    total: int
    limit: int
    offset: int


class JobCancelResponse(BaseModel):
    """Response for job cancel operation."""
    success: bool
    job_id: str
    message: str


class JobRetryResponse(BaseModel):
    """Response for job retry operation."""
    success: bool
    job_id: str
    new_job_id: Optional[str] = None
    message: str
