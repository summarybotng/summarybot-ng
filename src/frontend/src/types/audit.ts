/**
 * Audit log types (ADR-045)
 */

export type AuditCategory = 'auth' | 'access' | 'action' | 'source' | 'admin' | 'system';
export type AuditSeverity = 'debug' | 'info' | 'notice' | 'warning' | 'alert';

export interface AuditLogEntry {
  id: string;
  event_type: string;
  category: AuditCategory;
  severity: AuditSeverity;
  user_id?: string;
  user_name?: string;
  guild_id?: string;
  guild_name?: string;
  resource_type?: string;
  resource_id?: string;
  resource_name?: string;
  action?: string;
  details?: Record<string, unknown>;
  success: boolean;
  error_message?: string;
  timestamp: string;
  duration_ms?: number;
}

export interface AuditLogListResponse {
  items: AuditLogEntry[];
  total: number;
  limit: number;
  offset: number;
}

export interface AuditSummaryResponse {
  total_count: number;
  by_category: Record<string, number>;
  by_severity: Record<string, number>;
  by_event_type: Record<string, number>;
  by_user: Record<string, number>;
  failed_count: number;
  alert_count: number;
}

export interface AuditFilters {
  user_id?: string;
  event_type?: string;
  category?: AuditCategory;
  severity?: AuditSeverity;
  success?: boolean;
  start_date?: string;
  end_date?: string;
  resource_type?: string;
  resource_id?: string;
  limit?: number;
  offset?: number;
}
