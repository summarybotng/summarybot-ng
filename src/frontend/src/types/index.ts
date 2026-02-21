// Auth types
export interface User {
  id: string;
  username: string;
  avatar_url: string;
}

export interface AuthState {
  token: string | null;
  user: User | null;
  guilds: Guild[];
}

// Guild types
export interface Guild {
  id: string;
  name: string;
  icon_url: string | null;
  member_count: number;
  summary_count: number;
  last_summary_at: string | null;
  config_status: "configured" | "needs_setup" | "inactive";
}

export interface GuildDetail {
  id: string;
  name: string;
  icon_url: string | null;
  member_count: number;
  channels: Channel[];
  categories: Category[];
  config: GuildConfig;
  stats: GuildStats;
}

export interface GuildStats {
  total_summaries: number;
  summaries_this_week: number;
  active_schedules: number;
  last_summary_at: string | null;
}

export interface Channel {
  id: string;
  name: string;
  type: "text" | "voice" | "forum";
  category: string | null;
  enabled: boolean;
}

export interface Category {
  id: string;
  name: string;
  channel_count: number;
}

export interface GuildConfig {
  enabled_channels: string[];
  excluded_channels: string[];
  default_options: SummaryOptions;
}

export interface SummaryOptions {
  summary_length: "brief" | "detailed" | "comprehensive";
  perspective: "general" | "developer" | "marketing" | "executive" | "support";
  include_action_items: boolean;
  include_technical_terms: boolean;
}

// Summary types
export interface Summary {
  id: string;
  channel_id: string;
  channel_name: string;
  start_time: string;
  end_time: string;
  message_count: number;
  created_at: string;
  summary_length: string;
  preview: string;
  has_prompt_data?: boolean;
}

export interface SummaryReference {
  id: number;
  author: string;
  timestamp: string;
  content: string;
  message_id?: string;
}

export interface SummaryDetail extends Omit<Summary, 'preview' | 'summary_length'> {
  summary_text: string;
  key_points: string[];
  action_items: ActionItem[];
  technical_terms: TechnicalTerm[];
  participants: Participant[];
  metadata: SummaryMetadata;
  has_prompt_data?: boolean;
  // ADR-004: Grounded summary references
  references?: SummaryReference[];
}

export interface SummaryPromptData {
  summary_id: string;
  prompt_system: string | null;
  prompt_user: string | null;
  prompt_template_id: string | null;
  source_content: string | null;
}

export interface ActionItem {
  text: string;
  assignee: string | null;
  priority: "low" | "medium" | "high";
}

export interface TechnicalTerm {
  term: string;
  definition: string;
}

export interface Participant {
  username: string;
  message_count: number;
}

export interface PromptSource {
  source: "custom" | "cached" | "default" | "fallback";
  file_path: string | null;
  tried_paths: string[];
  repo_url: string | null;
  github_file_url: string | null;
  version: string;
  is_stale: boolean;
  // Path resolution details - show what parameters drove prompt selection
  path_template?: string | null;  // e.g., "prompts/{perspective}/{type}.md"
  resolved_variables?: Record<string, string>;  // Variables that drove selection
}

export interface SummaryMetadata {
  summary_length?: string;
  perspective?: string;
  model_used?: string;
  model_requested?: string;
  tokens_used?: number;
  generation_time_seconds?: number;
  warnings?: string[];
  prompt_source?: PromptSource;
  // Legacy fields for backwards compatibility
  model?: string;
  processing_time_ms?: number;
}

// Schedule types
export interface Schedule {
  id: string;
  name: string;
  channel_ids: string[];
  schedule_type: "fifteen-minutes" | "hourly" | "every-4-hours" | "daily" | "weekly" | "monthly" | "once";
  schedule_time: string;
  schedule_days: number[] | null;
  timezone: string;
  is_active: boolean;
  destinations: Destination[];
  summary_options: SummaryOptions;
  last_run: string | null;
  next_run: string | null;
  run_count: number;
  failure_count: number;
}

export interface Destination {
  type: "discord_channel" | "webhook" | "dashboard";
  target: string;
  format: "embed" | "markdown" | "json";
  // ADR-005: Dashboard-specific options
  auto_archive_days?: number;
  notify_on_delivery?: boolean;
}

// Webhook types
export interface Webhook {
  id: string;
  name: string;
  url_preview: string;
  type: "discord" | "slack" | "notion" | "generic";
  enabled: boolean;
  last_delivery: string | null;
  last_status: "success" | "failed" | null;
  created_at: string;
}

// Feed types
export interface Feed {
  id: string;
  channel_id: string | null;
  channel_name: string | null;
  feed_type: "rss" | "atom";
  is_public: boolean;
  url: string;
  token?: string;
  title: string;
  description?: string;
  max_items?: number;
  include_full_content?: boolean;
  created_at: string;
  created_by?: string;
  last_accessed: string | null;
  access_count: number;
}

export interface CreateFeedRequest {
  channel_id: string | null;
  feed_type: "rss" | "atom";
  is_public: boolean;
  title?: string;
  description?: string;
  max_items?: number;
  include_full_content?: boolean;
}

export interface UpdateFeedRequest {
  title?: string;
  description?: string;
  is_public?: boolean;
  max_items?: number;
  include_full_content?: boolean;
}

// API Error
export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

// Task types
export interface TaskStatus {
  task_id: string;
  status: "processing" | "completed" | "failed";
  summary_id?: string;
  error?: string;
}

// Generate Summary Request
export interface GenerateRequest {
  scope: "channel" | "category" | "guild";
  channel_ids?: string[];
  category_id?: string;
  time_range: {
    type: "hours" | "days" | "custom";
    value?: number;
    start?: string;
    end?: string;
  };
  options?: Partial<SummaryOptions>;
}

// ADR-005, ADR-008: Stored Summary types
// ADR-008 adds source tracking for unified summary experience
export type SummarySourceType = "realtime" | "scheduled" | "manual" | "archive" | "imported";

export interface StoredSummary {
  id: string;
  title: string;
  source_channel_ids: string[];
  schedule_id?: string;
  schedule_name?: string;  // ADR-009: For navigation
  created_at: string;
  viewed_at?: string;
  pushed_at?: string;
  pushed_to_channels: string[];
  is_pinned: boolean;
  is_archived: boolean;
  tags: string[];
  key_points_count: number;
  action_items_count: number;
  message_count: number;
  has_references: boolean;
  // ADR-008: Source tracking
  source: SummarySourceType;
  archive_period?: string;
  archive_granularity?: string;
  // Summary generation details
  summary_length?: string;  // brief, detailed, comprehensive
  perspective?: string;  // general, developer, marketing, etc.
  model_used?: string;  // e.g., claude-3-5-sonnet
}

export interface StoredSummaryDetail extends StoredSummary {
  guild_id: string;
  summary_text: string;
  key_points: string[];
  action_items: ActionItem[];
  participants: Participant[];
  start_time?: string;
  end_time?: string;
  metadata?: SummaryMetadata;
  push_deliveries: PushDelivery[];
  references?: SummaryReference[];
  // ADR-008: Archive-specific fields
  archive_source_key?: string;
}

export interface PushDelivery {
  channel_id: string;
  pushed_at: string;
  message_id?: string;
  success: boolean;
  error?: string;
}

export interface PushToChannelRequest {
  channel_ids: string[];
  format: "embed" | "markdown" | "plain";
  include_references: boolean;
  custom_message?: string;
  // Section toggles - which parts to include in the push
  include_key_points?: boolean;
  include_action_items?: boolean;
  include_participants?: boolean;
  include_technical_terms?: boolean;
}

export interface PushToChannelResponse {
  success: boolean;
  total_channels: number;
  successful_channels: number;
  deliveries: {
    channel_id: string;
    success: boolean;
    message_id?: string;
    error?: string;
  }[];
}

export interface StoredSummaryUpdateRequest {
  title?: string;
  is_pinned?: boolean;
  is_archived?: boolean;
  tags?: string[];
}

// ADR-009: Execution history types for schedule → run → summary navigation
export interface ExecutionHistoryItem {
  execution_id: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  started_at: string;
  completed_at: string | null;
  summary_id: string | null;
  error: string | null;
}

export interface ExecutionHistoryResponse {
  executions: ExecutionHistoryItem[];
}
