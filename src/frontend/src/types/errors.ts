// Error types for the Errors page

export type ErrorType =
  | "discord_permission"
  | "discord_not_found"
  | "discord_rate_limit"
  | "api_error"
  | "database_error"
  | "summarization_error"
  | "schedule_error"
  | "webhook_error"
  | "unknown";

export type ErrorSeverity = "info" | "warning" | "error" | "critical";

export interface ErrorLogItem {
  id: string;
  guild_id: string | null;
  channel_id: string | null;
  channel_name: string | null;
  error_type: ErrorType;
  severity: ErrorSeverity;
  error_code: string | null;
  message: string;
  operation: string;
  created_at: string;
  is_resolved: boolean;
  // Detail-only fields (from GET /errors/{errorId})
  details?: Record<string, unknown> | null;
  user_id?: string | null;
  stack_trace?: string | null;
  resolved_at?: string | null;
  resolution_notes?: string | null;
}

export interface ErrorsListResponse {
  errors: ErrorLogItem[];
  total: number;
  unresolved_count: number;
}

export interface ErrorCountsResponse {
  counts: Record<ErrorType, number>;
  total: number;
  period_hours: number;
}

export interface ErrorFilters {
  error_type?: ErrorType;
  error_types?: ErrorType[];
  severity?: ErrorSeverity;
  include_resolved?: boolean;
  limit?: number;
}

export interface ResolveErrorRequest {
  notes?: string;
}
