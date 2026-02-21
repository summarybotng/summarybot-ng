import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { Schedule, Destination, SummaryOptions, ExecutionHistoryResponse } from "@/types";

interface SchedulesResponse {
  schedules: Schedule[];
}

interface ScheduleRequest {
  name: string;
  channel_ids: string[];
  schedule_type: "daily" | "weekly" | "monthly" | "once";
  schedule_time: string;
  schedule_days?: number[];
  timezone: string;
  destinations: Destination[];
  summary_options: SummaryOptions;
}

export function useSchedules(guildId: string) {
  return useQuery({
    queryKey: ["schedules", guildId],
    queryFn: () => api.get<SchedulesResponse>(`/guilds/${guildId}/schedules`),
    select: (data) => data.schedules,
    enabled: !!guildId,
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
