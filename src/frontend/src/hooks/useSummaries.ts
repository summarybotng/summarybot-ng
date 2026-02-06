import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { Summary, SummaryDetail, SummaryPromptData, GenerateRequest, TaskStatus } from "@/types";

interface SummariesResponse {
  summaries: Summary[];
  total: number;
  limit: number;
  offset: number;
}

interface SummariesParams {
  channel_id?: string;
  start_date?: string;
  end_date?: string;
  limit?: number;
  offset?: number;
}

export function useSummaries(guildId: string, params: SummariesParams = {}) {
  const queryParams = new URLSearchParams();
  if (params.channel_id) queryParams.set("channel_id", params.channel_id);
  if (params.start_date) queryParams.set("start_date", params.start_date);
  if (params.end_date) queryParams.set("end_date", params.end_date);
  if (params.limit) queryParams.set("limit", params.limit.toString());
  if (params.offset) queryParams.set("offset", params.offset.toString());

  // Stable string for queryKey to prevent infinite refetches
  const queryString = queryParams.toString();

  return useQuery({
    queryKey: ["summaries", guildId, queryString],
    queryFn: () =>
      api.get<SummariesResponse>(
        `/guilds/${guildId}/summaries${queryString ? `?${queryString}` : ""}`
      ),
    enabled: !!guildId,
    retry: 1,
  });
}

export function useSummary(guildId: string, summaryId: string) {
  return useQuery({
    queryKey: ["summary", guildId, summaryId],
    queryFn: () =>
      api.get<SummaryDetail>(`/guilds/${guildId}/summaries/${summaryId}`),
    enabled: !!guildId && !!summaryId,
  });
}

export function useSummaryPrompt(guildId: string, summaryId: string, enabled: boolean = false) {
  return useQuery({
    queryKey: ["summaryPrompt", guildId, summaryId],
    queryFn: () =>
      api.get<SummaryPromptData>(`/guilds/${guildId}/summaries/${summaryId}/prompt`),
    enabled: !!guildId && !!summaryId && enabled,
  });
}

export function useGenerateSummary(guildId: string) {
  return useMutation({
    mutationFn: (request: GenerateRequest) =>
      api.post<{ task_id: string; status: string }>(
        `/guilds/${guildId}/summaries/generate`,
        request
      ),
    // No onSuccess - invalidate after task completes via polling
  });
}

export function useTaskStatus(guildId: string, taskId: string | null) {
  return useQuery({
    queryKey: ["task", guildId, taskId],
    queryFn: () =>
      api.get<TaskStatus>(`/guilds/${guildId}/summaries/tasks/${taskId}`),
    enabled: !!guildId && !!taskId,
    refetchInterval: (query) => {
      if (query.state.data?.status === "processing") return 2000;
      return false;
    },
  });
}
