import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type {
  ErrorLogItem,
  ErrorsListResponse,
  ErrorCountsResponse,
  ErrorFilters,
  ErrorType,
  ResolveErrorRequest,
} from "@/types/errors";

export function useErrors(guildId: string, filters: ErrorFilters = {}) {
  const queryString = new URLSearchParams();
  // Support both single and multiple error types
  if (filters.error_types && filters.error_types.length > 0) {
    filters.error_types.forEach((type) => queryString.append("error_type", type));
  } else if (filters.error_type) {
    queryString.set("error_type", filters.error_type);
  }
  if (filters.severity) queryString.set("severity", filters.severity);
  if (filters.include_resolved !== undefined) {
    queryString.set("include_resolved", String(filters.include_resolved));
  }
  if (filters.limit) queryString.set("limit", String(filters.limit));

  const queryStringStr = queryString.toString();

  return useQuery({
    queryKey: ["errors", guildId, queryStringStr],
    queryFn: async () => {
      const url = queryStringStr
        ? `/guilds/${guildId}/errors?${queryStringStr}`
        : `/guilds/${guildId}/errors`;
      return api.get<ErrorsListResponse>(url);
    },
    enabled: !!guildId,
  });
}

export function useErrorCounts(guildId: string, hours: number = 24) {
  return useQuery({
    queryKey: ["errorCounts", guildId, hours],
    queryFn: async () => {
      return api.get<ErrorCountsResponse>(
        `/guilds/${guildId}/errors/counts?hours=${hours}`
      );
    },
    enabled: !!guildId,
  });
}

export function useErrorDetail(guildId: string, errorId: string | null) {
  return useQuery({
    queryKey: ["error", guildId, errorId],
    queryFn: async () => {
      return api.get<ErrorLogItem>(`/guilds/${guildId}/errors/${errorId}`);
    },
    enabled: !!guildId && !!errorId,
  });
}

export function useResolveError(guildId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      errorId,
      notes,
    }: {
      errorId: string;
      notes?: string;
    }) => {
      const body: ResolveErrorRequest = notes ? { notes } : {};
      return api.post(`/guilds/${guildId}/errors/${errorId}/resolve`, body);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["errors", guildId] });
      queryClient.invalidateQueries({ queryKey: ["errorCounts", guildId] });
    },
  });
}

export function useBulkResolveErrors(guildId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      errorType,
      notes,
    }: {
      errorType: ErrorType;
      notes?: string;
    }) => {
      const body = { error_type: errorType, notes };
      return api.post<{ resolved_count: number }>(
        `/guilds/${guildId}/errors/bulk-resolve`,
        body
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["errors", guildId] });
      queryClient.invalidateQueries({ queryKey: ["errorCounts", guildId] });
    },
  });
}

export function useUnresolvedErrorCount(guildId: string) {
  return useQuery({
    queryKey: ["errors", guildId, "unresolved-count"],
    queryFn: async () => {
      const response = await api.get<ErrorsListResponse>(
        `/guilds/${guildId}/errors?include_resolved=false&limit=1`
      );
      return response.unresolved_count;
    },
    enabled: !!guildId,
    refetchInterval: 60000, // Refresh every minute
  });
}
