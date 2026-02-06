import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { Guild, GuildDetail, GuildConfig } from "@/types";

interface GuildsResponse {
  guilds: Guild[];
}

export function useGuilds() {
  return useQuery({
    queryKey: ["guilds"],
    queryFn: () => api.get<GuildsResponse>("/guilds"),
    select: (data) => data.guilds,
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
