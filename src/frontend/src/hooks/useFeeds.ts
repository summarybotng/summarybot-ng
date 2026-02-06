import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { Feed, CreateFeedRequest, UpdateFeedRequest } from "@/types";

interface FeedsResponse {
  feeds: Feed[];
}

export function useFeeds(guildId: string) {
  return useQuery({
    queryKey: ["feeds", guildId],
    queryFn: () => api.get<FeedsResponse>(`/guilds/${guildId}/feeds`),
    select: (data) => data.feeds,
    enabled: !!guildId,
  });
}

export function useFeed(guildId: string, feedId: string) {
  return useQuery({
    queryKey: ["feed", guildId, feedId],
    queryFn: () => api.get<Feed>(`/guilds/${guildId}/feeds/${feedId}`),
    enabled: !!guildId && !!feedId,
  });
}

export function useCreateFeed(guildId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (feed: CreateFeedRequest) =>
      api.post<Feed>(`/guilds/${guildId}/feeds`, feed),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["feeds", guildId] });
    },
  });
}

export function useUpdateFeed(guildId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ feedId, feed }: { feedId: string; feed: UpdateFeedRequest }) =>
      api.patch<Feed>(`/guilds/${guildId}/feeds/${feedId}`, feed),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["feeds", guildId] });
    },
  });
}

export function useDeleteFeed(guildId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (feedId: string) =>
      api.delete(`/guilds/${guildId}/feeds/${feedId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["feeds", guildId] });
    },
  });
}

export function useRegenerateToken(guildId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (feedId: string) =>
      api.post<{ token: string; url: string }>(
        `/guilds/${guildId}/feeds/${feedId}/regenerate-token`
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["feeds", guildId] });
    },
  });
}
