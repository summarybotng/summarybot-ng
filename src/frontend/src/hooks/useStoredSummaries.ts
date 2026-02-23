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

// ADR-017: Channel mode types
export type ChannelModeType = "single" | "multi" | "all";

// ADR-017: Sort options
export type SortByType = "created_at" | "message_count" | "archive_period";
export type SortOrderType = "asc" | "desc";

interface StoredSummariesParams {
  page?: number;
  limit?: number;
  pinned?: boolean;
  archived?: boolean;
  tags?: string[];
  source?: SummarySourceType;  // ADR-008: Filter by source
  // ADR-017: Enhanced filters
  createdAfter?: string;  // ISO date
  createdBefore?: string;  // ISO date
  archivePeriod?: string;  // YYYY-MM-DD
  channelMode?: ChannelModeType;
  hasGrounding?: boolean;
  sortBy?: SortByType;
  sortOrder?: SortOrderType;
  // ADR-018: Content-based filters
  hasKeyPoints?: boolean;
  hasActionItems?: boolean;
  hasParticipants?: boolean;
  minMessageCount?: number;
  maxMessageCount?: number;
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
  // ADR-017: Enhanced filters
  if (params.createdAfter) queryParams.set("created_after", params.createdAfter);
  if (params.createdBefore) queryParams.set("created_before", params.createdBefore);
  if (params.archivePeriod) queryParams.set("archive_period", params.archivePeriod);
  if (params.channelMode && params.channelMode !== "all") queryParams.set("channel_mode", params.channelMode);
  if (params.hasGrounding !== undefined) queryParams.set("has_grounding", params.hasGrounding.toString());
  if (params.sortBy) queryParams.set("sort_by", params.sortBy);
  if (params.sortOrder) queryParams.set("sort_order", params.sortOrder);
  // ADR-018: Content filters
  if (params.hasKeyPoints !== undefined) queryParams.set("has_key_points", params.hasKeyPoints.toString());
  if (params.hasActionItems !== undefined) queryParams.set("has_action_items", params.hasActionItems.toString());
  if (params.hasParticipants !== undefined) queryParams.set("has_participants", params.hasParticipants.toString());
  if (params.minMessageCount !== undefined) queryParams.set("min_message_count", params.minMessageCount.toString());
  if (params.maxMessageCount !== undefined) queryParams.set("max_message_count", params.maxMessageCount.toString());

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

// ADR-017: Calendar data hook
interface CalendarDay {
  date: string;
  count: number;
  sources: string[];
  has_incomplete: boolean;
}

interface CalendarResponse {
  year: number;
  month: number;
  days: CalendarDay[];
}

export function useSummaryCalendar(guildId: string, year: number, month: number) {
  return useQuery({
    queryKey: ["summary-calendar", guildId, year, month],
    queryFn: () =>
      api.get<CalendarResponse>(
        `/guilds/${guildId}/stored-summaries/calendar/${year}/${month}`
      ),
    enabled: !!guildId && !!year && !!month,
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

// ADR-004: Regenerate summary with grounding
interface RegenerateResponse {
  task_id: string;
  status: string;
}

// Regenerate options
export interface RegenerateOptions {
  model?: string;
  summary_length?: string;
  perspective?: string;
}

export function useRegenerateSummary(guildId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ summaryId, options }: { summaryId: string; options?: RegenerateOptions }) =>
      api.post<RegenerateResponse>(
        `/guilds/${guildId}/stored-summaries/${summaryId}/regenerate`,
        options || undefined
      ),
    onSuccess: (_, { summaryId }) => {
      // Invalidate after a delay to allow regeneration to complete
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ["stored-summaries", guildId] });
        queryClient.invalidateQueries({
          queryKey: ["stored-summary", guildId, summaryId],
        });
      }, 5000);
    },
  });
}

// ADR-018: Bulk delete
interface BulkDeleteResponse {
  deleted_count: number;
  failed_ids: string[];
  errors: string[];
}

export function useBulkDeleteSummaries(guildId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (summaryIds: string[]) =>
      api.post<BulkDeleteResponse>(
        `/guilds/${guildId}/stored-summaries/bulk-delete`,
        { summary_ids: summaryIds }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["stored-summaries", guildId] });
      queryClient.invalidateQueries({ queryKey: ["summary-calendar", guildId] });
    },
  });
}

// ADR-018: Bulk regenerate
interface BulkRegenerateResponse {
  queued_count: number;
  skipped_count: number;
  skipped_ids: string[];
  task_id: string;
}

export function useBulkRegenerateSummaries(guildId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (summaryIds: string[]) =>
      api.post<BulkRegenerateResponse>(
        `/guilds/${guildId}/stored-summaries/bulk-regenerate`,
        { summary_ids: summaryIds }
      ),
    onSuccess: () => {
      // Invalidate after a delay to allow regeneration to complete
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ["stored-summaries", guildId] });
      }, 10000);
    },
  });
}
