import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type {
  SlackWorkspace,
  SlackChannel,
  SlackInstallResponse,
  SlackChannelUpdateRequest,
  SlackSyncResponse,
  SlackStatusResponse,
} from "@/types/slack";

// ============================================================================
// Query Hooks
// ============================================================================

/**
 * Fetch list of connected Slack workspaces
 */
export function useSlackWorkspaces() {
  return useQuery({
    queryKey: ["slack", "workspaces"],
    queryFn: () => api.get<SlackWorkspace[]>("/slack/workspaces"),
  });
}

/**
 * Fetch a single Slack workspace by ID
 */
export function useSlackWorkspace(workspaceId: string) {
  return useQuery({
    queryKey: ["slack", "workspace", workspaceId],
    queryFn: () => api.get<SlackWorkspace>(`/slack/workspaces/${workspaceId}`),
    enabled: !!workspaceId,
  });
}

/**
 * Fetch channels for a Slack workspace
 */
export function useSlackChannels(workspaceId: string, includeArchived = false) {
  return useQuery({
    queryKey: ["slack", "channels", workspaceId, { includeArchived }],
    queryFn: () =>
      api.get<SlackChannel[]>(
        `/slack/workspaces/${workspaceId}/channels?include_archived=${includeArchived}`
      ),
    enabled: !!workspaceId,
  });
}

/**
 * Fetch Slack integration status
 */
export function useSlackStatus() {
  return useQuery({
    queryKey: ["slack", "status"],
    queryFn: () => api.get<SlackStatusResponse>("/slack/status"),
  });
}

// ============================================================================
// Mutation Hooks
// ============================================================================

/**
 * Initiate Slack OAuth flow
 */
export function useConnectSlack() {
  return useMutation({
    mutationFn: (params: { guild_id: string; scope_tier: "public" | "full" }) =>
      api.post<SlackInstallResponse>("/slack/install", params),
    onSuccess: (data) => {
      // Redirect to Slack OAuth page
      window.location.href = data.install_url;
    },
  });
}

/**
 * Disconnect a Slack workspace
 */
export function useDisconnectSlack() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (workspaceId: string) =>
      api.delete(`/slack/workspaces/${workspaceId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["slack", "workspaces"] });
    },
  });
}

/**
 * Sync channels and users from Slack
 */
export function useSyncSlackWorkspace() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (workspaceId: string) =>
      api.post<SlackSyncResponse>(`/slack/workspaces/${workspaceId}/sync`),
    onSuccess: (_, workspaceId) => {
      queryClient.invalidateQueries({
        queryKey: ["slack", "workspace", workspaceId],
      });
      queryClient.invalidateQueries({
        queryKey: ["slack", "channels", workspaceId],
      });
    },
  });
}

/**
 * Update Slack channel settings
 */
export function useUpdateSlackChannel(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      channelId,
      updates,
    }: {
      channelId: string;
      updates: SlackChannelUpdateRequest;
    }) => api.patch(`/slack/channels/${channelId}`, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["slack", "channels", workspaceId],
      });
    },
  });
}

/**
 * Link a Slack workspace to a Discord guild
 */
export function useLinkSlackWorkspace() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      workspaceId,
      guildId,
    }: {
      workspaceId: string;
      guildId: string;
    }) =>
      api.post(`/slack/workspaces/${workspaceId}/link`, {
        workspace_id: guildId,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["slack", "workspaces"] });
    },
  });
}
