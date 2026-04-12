/**
 * React Query hooks for audit log API (ADR-045)
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { AuditLogListResponse, AuditSummaryResponse, AuditFilters } from "@/types/audit";

export function useAuditLogs(guildId: string, filters: AuditFilters = {}) {
  return useQuery({
    queryKey: ["audit-logs", guildId, filters],
    queryFn: async (): Promise<AuditLogListResponse> => {
      const params = new URLSearchParams();

      if (filters.user_id) params.set("user_id", filters.user_id);
      if (filters.event_type) params.set("event_type", filters.event_type);
      if (filters.category) params.set("category", filters.category);
      if (filters.severity) params.set("severity", filters.severity);
      if (filters.success !== undefined) params.set("success", String(filters.success));
      if (filters.start_date) params.set("start_date", filters.start_date);
      if (filters.end_date) params.set("end_date", filters.end_date);
      if (filters.resource_type) params.set("resource_type", filters.resource_type);
      if (filters.resource_id) params.set("resource_id", filters.resource_id);
      if (filters.limit) params.set("limit", String(filters.limit));
      if (filters.offset) params.set("offset", String(filters.offset));

      const queryString = params.toString();
      const url = `/guilds/${guildId}/audit${queryString ? `?${queryString}` : ""}`;

      return api.get<AuditLogListResponse>(url);
    },
    enabled: !!guildId,
    staleTime: 30000, // 30 seconds
  });
}

export function useAuditSummary(
  guildId: string,
  startDate?: string,
  endDate?: string
) {
  return useQuery({
    queryKey: ["audit-summary", guildId, startDate, endDate],
    queryFn: async (): Promise<AuditSummaryResponse> => {
      const params = new URLSearchParams();
      if (startDate) params.set("start_date", startDate);
      if (endDate) params.set("end_date", endDate);

      const queryString = params.toString();
      const url = `/guilds/${guildId}/audit/summary${queryString ? `?${queryString}` : ""}`;

      return api.get<AuditSummaryResponse>(url);
    },
    enabled: !!guildId,
    staleTime: 60000, // 1 minute
  });
}
