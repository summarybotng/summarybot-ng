import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { Schedule, Destination, SummaryOptions, ExecutionHistoryResponse } from "@/types";

interface SchedulesResponse {
  schedules: Schedule[];
}

interface ScheduleRequest {
  name: string;
  // ADR-011: Scope-based scheduling
  scope?: "channel" | "category" | "guild";
  channel_ids: string[];
  category_id?: string;
  // ADR-089: All schedule types including intervals
  schedule_type: "fifteen-minutes" | "hourly" | "every-4-hours" | "daily" | "weekly" | "monthly" | "once";
  schedule_time: string;
  schedule_days?: number[];
  timezone: string;
  // ADR-051: Platform support
  platform?: "discord" | "slack" | "whatsapp";
  // ADR-087: Weekly continuity
  enable_continuity?: boolean;
  // ADR-089: Lookback period
  time_range_hours?: number;
  destinations: Destination[];
  summary_options: SummaryOptions;
  // ADR-034: Guild prompt templates
  prompt_template_id?: string | null;
  // ADR-101: Rolling period summaries
  rolling_period?: "weekly" | "biweekly" | "monthly";
  rolling_end_day?: number;
  accumulation_strategy?: "append" | "resummarize" | "hybrid";
  // Custom title template
  title_template?: string;
}

export function useSchedules(guildId: string) {
  return useQuery({
    queryKey: ["schedules", guildId],
    queryFn: () => api.get<SchedulesResponse>(`/guilds/${guildId}/schedules`),
    select: (data) => data.schedules,
    enabled: !!guildId,
  });
}

/**
 * Fetch a single schedule by ID.
 * Used for edit mode in the wizard.
 */
export function useSchedule(guildId: string, scheduleId: string | null) {
  return useQuery({
    queryKey: ["schedule", guildId, scheduleId],
    queryFn: () => api.get<Schedule>(`/guilds/${guildId}/schedules/${scheduleId}`),
    enabled: !!guildId && !!scheduleId,
  });
}

export function useCreateSchedule(guildId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (schedule: ScheduleRequest) =>
      api.post<Schedule>(`/guilds/${guildId}/schedules`, schedule),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules", guildId] });
    },
  });
}

export function useUpdateSchedule(guildId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      scheduleId,
      schedule,
    }: {
      scheduleId: string;
      schedule: Partial<ScheduleRequest> & { is_active?: boolean };
    }) => api.patch<Schedule>(`/guilds/${guildId}/schedules/${scheduleId}`, schedule),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules", guildId] });
    },
  });
}

export function useDeleteSchedule(guildId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (scheduleId: string) =>
      api.delete(`/guilds/${guildId}/schedules/${scheduleId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules", guildId] });
    },
  });
}

export function useRunSchedule(guildId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (scheduleId: string) =>
      api.post(`/guilds/${guildId}/schedules/${scheduleId}/run`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules", guildId] });
      queryClient.invalidateQueries({ queryKey: ["summaries", guildId] });
    },
  });
}

// ADR-009: Hook for fetching execution history
export function useExecutionHistory(guildId: string, scheduleId: string | null) {
  return useQuery({
    queryKey: ["execution-history", guildId, scheduleId],
    queryFn: () =>
      api.get<ExecutionHistoryResponse>(
        `/guilds/${guildId}/schedules/${scheduleId}/history`
      ),
    select: (data) => data.executions,
    enabled: !!guildId && !!scheduleId,
  });
}

// ADR-104: Rolling schedule summaries
interface RollingCurrentSummary {
  summary_id: string;
  title: string;
  period_start: string;
  rollover_date: string;
  accumulation_count: number;
  total_days_in_period: number;
  last_updated: string | null;
  message_count: number;
}

interface RollingPreviousSummary {
  summary_id: string;
  title: string;
  period_start: string;
  period_end: string | null;
  message_count: number;
  accumulation_count: number;
}

interface RollingScheduleSummariesResponse {
  current: RollingCurrentSummary | null;
  previous: RollingPreviousSummary[];
  total_finalized_count: number;
}

export function useRollingSummaries(guildId: string, scheduleId: string | null, enabled: boolean = true) {
  return useQuery({
    queryKey: ["rolling-summaries", guildId, scheduleId],
    queryFn: () =>
      api.get<RollingScheduleSummariesResponse>(
        `/guilds/${guildId}/schedules/${scheduleId}/rolling-summaries`
      ),
    enabled: !!guildId && !!scheduleId && enabled,
  });
}
