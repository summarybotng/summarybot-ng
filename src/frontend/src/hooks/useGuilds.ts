import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/authStore";
import type { Guild, GuildDetail, GuildConfig } from "@/types";

interface GuildsResponse {
  guilds: Guild[];
}

interface RefreshResponse {
  token: string;
  guilds: string[];
}

export function useGuilds() {
  return useQuery({
    queryKey: ["guilds"],
    queryFn: () => api.get<GuildsResponse>("/guilds"),
    select: (data) => data.guilds,
  });
}

export function useRefreshGuilds() {
  const queryClient = useQueryClient();
  const updateToken = useAuthStore((state) => state.updateToken);

  return useMutation({
    mutationFn: () => api.post<RefreshResponse>("/auth/refresh"),
    onSuccess: (data) => {
      // Update the token in auth store
      updateToken(data.token);
      // Invalidate guilds query to refetch with new token
      queryClient.invalidateQueries({ queryKey: ["guilds"] });
    },
  });
}

export function useGuild(id: string) {
  return useQuery({
    queryKey: ["guild", id],
    queryFn: () => api.get<GuildDetail>(`/guilds/${id}`),
    enabled: !!id,
  });
}

export function useUpdateConfig(guildId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (config: Partial<GuildConfig>) =>
      api.patch<GuildConfig>(`/guilds/${guildId}/config`, config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["guild", guildId] });
    },
  });
}

export function useSyncChannels(guildId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post(`/guilds/${guildId}/channels/sync`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["guild", guildId] });
    },
  });
}
