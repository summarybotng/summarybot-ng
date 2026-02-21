/**
 * Hooks for stored summaries (ADR-005, ADR-008)
 *
 * ADR-008: Extended to support unified summary experience with source filtering.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type {
  StoredSummary,
  StoredSummaryDetail,
  StoredSummaryUpdateRequest,
  PushToChannelRequest,
  PushToChannelResponse,
} from "@/types";

interface StoredSummariesResponse {
  items: StoredSummary[];
  total: number;
  page: number;
  limit: number;
}

// ADR-008: Summary source types
export type SummarySourceType = "realtime" | "scheduled" | "manual" | "archive" | "imported" | "all";

interface StoredSummariesParams {
  page?: number;
  limit?: number;
  pinned?: boolean;
  archived?: boolean;
  tags?: string[];
  source?: SummarySourceType;  // ADR-008: Filter by source
}

export function useStoredSummaries(
  guildId: string,
  params: StoredSummariesParams = {}
) {
  const queryParams = new URLSearchParams();
  if (params.page) queryParams.set("page", params.page.toString());
  if (params.limit) queryParams.set("limit", params.limit.toString());
  if (params.pinned !== undefined) queryParams.set("pinned", params.pinned.toString());
  if (params.archived !== undefined) queryParams.set("archived", params.archived.toString());
  if (params.tags?.length) queryParams.set("tags", params.tags.join(","));
  // ADR-008: Source filtering
  if (params.source && params.source !== "all") queryParams.set("source", params.source);

  const queryString = queryParams.toString();

  return useQuery({
    queryKey: ["stored-summaries", guildId, queryString],
    queryFn: () =>
      api.get<StoredSummariesResponse>(
        `/guilds/${guildId}/stored-summaries${queryString ? `?${queryString}` : ""}`
      ),
    enabled: !!guildId,
  });
}

export function useStoredSummary(guildId: string, summaryId: string) {
  return useQuery({
    queryKey: ["stored-summary", guildId, summaryId],
    queryFn: () =>
      api.get<StoredSummaryDetail>(
        `/guilds/${guildId}/stored-summaries/${summaryId}`
      ),
    enabled: !!guildId && !!summaryId,
  });
}

export function useUpdateStoredSummary(guildId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      summaryId,
      data,
    }: {
      summaryId: string;
      data: StoredSummaryUpdateRequest;
    }) =>
      api.patch<StoredSummaryDetail>(
        `/guilds/${guildId}/stored-summaries/${summaryId}`,
        data
      ),
    onSuccess: (_, { summaryId }) => {
      queryClient.invalidateQueries({ queryKey: ["stored-summaries", guildId] });
      queryClient.invalidateQueries({
        queryKey: ["stored-summary", guildId, summaryId],
      });
    },
  });
}

export function useDeleteStoredSummary(guildId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (summaryId: string) =>
      api.delete(`/guilds/${guildId}/stored-summaries/${summaryId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["stored-summaries", guildId] });
    },
  });
}

export function usePushToChannel(guildId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      summaryId,
      request,
    }: {
      summaryId: string;
      request: PushToChannelRequest;
    }) =>
      api.post<PushToChannelResponse>(
        `/guilds/${guildId}/stored-summaries/${summaryId}/push`,
        request
      ),
    onSuccess: (_, { summaryId }) => {
      queryClient.invalidateQueries({ queryKey: ["stored-summaries", guildId] });
      queryClient.invalidateQueries({
        queryKey: ["stored-summary", guildId, summaryId],
      });
    },
  });
}
