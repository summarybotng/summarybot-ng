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

export interface SummaryDetail extends Omit<Summary, 'preview' | 'summary_length'> {
  summary_text: string;
  key_points: string[];
  action_items: ActionItem[];
  technical_terms: TechnicalTerm[];
  participants: Participant[];
  metadata: SummaryMetadata;
  has_prompt_data?: boolean;
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
  schedule_type: "daily" | "weekly" | "monthly" | "once";
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
  type: "discord_channel" | "webhook";
  target: string;
  format: "embed" | "markdown" | "json";
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
