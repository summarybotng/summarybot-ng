/**
 * ADR-046: Channel Sensitivity Configuration Hooks
 *
 * Provides hooks for managing channel sensitivity configuration
 * to control which channels are marked as sensitive for summary visibility.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { ChannelSensitivityConfig } from "@/types";

interface ChannelSensitivityResponse {
  config: ChannelSensitivityConfig;
}

/**
 * Fetch the channel sensitivity configuration for a guild
 */
export function useChannelSensitivityConfig(guildId: string) {
  return useQuery({
    queryKey: ["channel-sensitivity", guildId],
    queryFn: () =>
      api.get<ChannelSensitivityResponse>(`/guilds/${guildId}/channel-sensitivity`),
    select: (data) => data.config,
    enabled: !!guildId,
  });
}

/**
 * Update the channel sensitivity configuration for a guild
 */
export function useUpdateChannelSensitivity(guildId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (config: Partial<ChannelSensitivityConfig>) =>
      api.patch<ChannelSensitivityConfig>(
        `/guilds/${guildId}/channel-sensitivity`,
        config
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["channel-sensitivity", guildId] });
      // Also invalidate guild query in case config is embedded
      queryClient.invalidateQueries({ queryKey: ["guild", guildId] });
    },
  });
}

/**
 * Add a channel to the sensitive channels list
 */
export function useAddSensitiveChannel(guildId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (channelId: string) =>
      api.post(`/guilds/${guildId}/channel-sensitivity/channels/${channelId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["channel-sensitivity", guildId] });
    },
  });
}

/**
 * Remove a channel from the sensitive channels list
 */
export function useRemoveSensitiveChannel(guildId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (channelId: string) =>
      api.delete(`/guilds/${guildId}/channel-sensitivity/channels/${channelId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["channel-sensitivity", guildId] });
    },
  });
}
